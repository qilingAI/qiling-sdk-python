"""Exercise the official OpenAI SDK against the documented gateway wire format."""
from __future__ import annotations

import json
import io
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch
from email.parser import BytesParser
from email.policy import default

try:
    import httpx
    from openai import OpenAI, BadRequestError
except ImportError:
    OpenAI = None


@unittest.skipIf(OpenAI is None, "Install openai and httpx to run the official SDK compatibility checks.")
class OfficialOpenAiTests(unittest.TestCase):
    def client(self, handler):
        return OpenAI(
            api_key="fixture-api-key", base_url="https://api.example.test/v1", max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    def test_standard_chat_images_and_models_only_need_three_settings(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"object": "list", "data": [{"id": "platform-model", "object": "model", "created": 0, "owned_by": "qiling", "qiling": {"config": {}}}]})
            if request.url.path == "/v1/images/generations":
                return httpx.Response(200, json={"created": 1, "data": [{"url": "https://example.test/cat.png"}], "qiling": {"id": 43}})
            return httpx.Response(200, json={
                "id": "chatcmpl-42", "object": "chat.completion", "created": 1, "model": "platform-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, "qiling": {"id": 42},
            })

        with self.client(handler) as client:
            result = client.chat.completions.create(model="platform-model", messages=[{"role": "user", "content": "hi"}], max_completion_tokens=50)
            self.assertEqual(result.choices[0].message.content, "hello")
            images = client.images.generate(model="platform-model", prompt="cat", response_format="url")
            self.assertEqual(images.data[0].url, "https://example.test/cat.png")
            self.assertEqual(client.models.list().data[0].id, "platform-model")
        for request in requests:
            self.assertEqual(request.headers["authorization"], "Bearer fixture-api-key")
            self.assertNotIn("x-api-key", request.headers)
            if request.method == "POST":
                self.assertNotIn("request_id", json.loads(request.content))

    def test_official_sdk_consumes_sse_chunks_and_usage_without_resubmitting(self):
        requests = []
        frames = [
            {"id": "chatcmpl-42", "object": "chat.completion.chunk", "created": 1, "model": "platform-model", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "hello"}, "finish_reason": None}]},
            {"id": "chatcmpl-42", "object": "chat.completion.chunk", "created": 1, "model": "platform-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {"id": "chatcmpl-42", "object": "chat.completion.chunk", "created": 1, "model": "platform-model", "choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
        ]

        def handler(request):
            requests.append(request)
            data = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames) + "data: [DONE]\n\n"
            return httpx.Response(200, content=data, headers={"content-type": "text/event-stream"})

        with self.client(handler) as client:
            stream = client.chat.completions.create(model="platform-model", messages=[{"role": "user", "content": "hi"}], stream=True, stream_options={"include_usage": True}, extra_headers={"Idempotency-Key": "business-1"})
            try:
                chunks = list(stream)
            finally:
                stream.close()
        self.assertEqual(chunks[0].choices[0].delta.content, "hello")
        self.assertEqual(chunks[-1].usage.total_tokens, 2)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].headers["Idempotency-Key"], "business-1")
        self.assertTrue(json.loads(requests[0].content)["stream"])

    def test_official_sdk_reads_standard_error_structure(self):
        def handler(request):
            return httpx.Response(400, json={"error": {"message": "Unsupported tools", "type": "invalid_request_error", "param": "tools", "code": "UNSUPPORTED_PARAMETER"}}, headers={"x-should-retry": "false"})

        with self.client(handler) as client:
            with self.assertRaises(BadRequestError) as raised:
                client.chat.completions.create(model="platform-model", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(raised.exception.code, "UNSUPPORTED_PARAMETER")
        self.assertEqual(raised.exception.param, "tools")

    def test_thinking_cli_sends_extension_at_top_level_and_prints_final_only(self):
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "chatcmpl-42", "object": "chat.completion", "created": 1, "model": "platform-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "final", "reasoning_content": "separate reasoning"}, "finish_reason": "stop"}],
            })

        example = Path(__file__).resolve().parents[1] / 'examples/openai_chat.py'
        with self.client(handler) as client, patch('openai.OpenAI', return_value=client), patch.dict(os.environ, {'QILING_API_KEY': 'fixture-key', 'QILING_BASE_URL': 'https://api.example.test/v1', 'QILING_MODEL': 'platform-model'}), patch('sys.argv', [str(example), '--prompt', 'hello', '--thinking', 'disabled']), patch('sys.stdout', new_callable=io.StringIO) as output:
            runpy.run_path(str(example), run_name='__main__')
        self.assertEqual(requests[0]['thinking'], {'type': 'disabled'})
        self.assertNotIn('extra_body', requests[0])
        self.assertEqual(output.getvalue().strip(), 'final')

    def test_tools_structured_output_and_tool_result_round_trip(self):
        requests = []
        tool_call = {"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": '{"query":"test"}'}}

        def handler(request):
            requests.append(json.loads(request.content))
            message = {"role": "assistant", "content": None, "tool_calls": [tool_call], "reasoning_content": "preserve this"} if len(requests) == 1 else {"role": "assistant", "content": '{"answer":"found"}'}
            return httpx.Response(200, json={"id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "platform-model", "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}]})

        messages = [{"role": "user", "content": [{"type": "text", "text": "find it"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,Zml4dHVyZQ=="}}]}]
        tools = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}]
        schema = {"type": "json_schema", "json_schema": {"name": "answer", "schema": {"type": "object", "properties": {"answer": {"type": "string"}}}, "strict": True}}
        with self.client(handler) as client:
            first = client.chat.completions.create(model="platform-model", messages=messages, tools=tools, tool_choice="required", parallel_tool_calls=True)
            assistant = first.choices[0].message.model_dump(exclude_none=True)
            self.assertEqual(first.choices[0].message.tool_calls[0].function.name, "lookup")
            messages.extend([assistant, {"role": "tool", "tool_call_id": "call-1", "content": "found"}])
            final = client.chat.completions.create(model="platform-model", messages=messages, response_format=schema)
        self.assertEqual(requests[0]['tools'], tools)
        self.assertTrue(requests[0]['parallel_tool_calls'])
        self.assertEqual(requests[1]['messages'][1]['reasoning_content'], "preserve this")
        self.assertEqual(requests[1]['messages'][2]['tool_call_id'], "call-1")
        self.assertEqual(requests[1]['response_format'], schema)
        self.assertEqual(json.loads(final.choices[0].message.content), {"answer": "found"})

    def test_image_edit_multipart_preserves_uploads_and_standard_response(self):
        uploads = []

        def handler(request):
            self.assertEqual(request.url.path, '/v1/images/edits')
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-api-key')
            mime = BytesParser(policy=default).parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + request.content)
            fields = {}
            for part in mime.iter_parts():
                name = part.get_param('name', header='content-disposition')
                if part.get_filename():
                    uploads.append((name, part.get_filename(), part.get_payload(decode=True)))
                else:
                    fields[name] = part.get_payload(decode=True).decode()
            self.assertEqual(fields['model'], 'image-model')
            self.assertEqual(fields['prompt'], 'edit the images')
            return httpx.Response(200, json={"created": 1, "data": [{"b64_json": "Zml4dHVyZQ=="}]})

        with self.client(handler) as client:
            result = client.images.edit(model='image-model', prompt='edit the images', image=[('first.png', b'first-image', 'image/png'), ('second.png', b'second-image', 'image/png')])
        self.assertEqual(result.data[0].b64_json, 'Zml4dHVyZQ==')
        self.assertEqual([u[2] for u in uploads], [b'first-image', b'second-image'])
        self.assertTrue(all(u[0] == 'image[]' for u in uploads))

    def test_official_sdk_reads_image_generation_and_edit_streams(self):
        for edit in [False, True]:
            with self.subTest(edit=edit):
                prefix = 'image_edit' if edit else 'image_generation'
                event = {"type": prefix + '.completed', "b64_json": 'Zml4dHVyZQ==', "created_at": 1, "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}

                def handler(request):
                    self.assertEqual(request.url.path, '/v1/images/edits' if edit else '/v1/images/generations')
                    data = 'event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n'
                    return httpx.Response(200, content=data, headers={'content-type': 'text/event-stream'})

                with self.client(handler) as client:
                    stream = client.images.edit(model='image-model', prompt='edit', image=('fixture.png', b'fixture', 'image/png'), stream=True) if edit else client.images.generate(model='image-model', prompt='cat', stream=True)
                    try:
                        events = list(stream)
                    finally:
                        stream.close()
                self.assertEqual(events[0].type, prefix + '.completed')
                self.assertEqual(events[0].b64_json, 'Zml4dHVyZQ==')
