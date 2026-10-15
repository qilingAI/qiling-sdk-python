"""Exercise the official OpenAI SDK against the documented gateway wire format."""
from __future__ import annotations

import json
import unittest

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
