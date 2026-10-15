"""SDK capability inputs, optional bridge and video contract; no paid requests."""
import io
import json
import unittest
from unittest.mock import patch
from qiling_ai_sdk import QilingOpenClient, QilingAiClient
from qiling_ai_sdk import client as http


class ModelCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.client = QilingOpenClient('https://example.test/v1', 'fixture-key', app_key='registered-app')

    def test_tools_multimodal_and_json_options_are_preserved(self):
        messages = [{'role': 'user', 'content': [{'type': 'text', 'text': '识图'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,Zml4dHVyZQ=='}}]}]
        tools = [{'type': 'function', 'function': {'name': 'lookup', 'parameters': {'type': 'object'}}}]
        with patch.object(http, 'urlopen', return_value=io.BytesIO(b'{}')) as send:
            self.client.chat(messages, model='model', tools=tools, tool_choice='required', parallel_tool_calls=True, response_format={'type': 'json_object'}, idempotency_key='business')
        request = send.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body['messages'], messages)
        self.assertEqual(body['tools'], tools)
        self.assertTrue(body['parallel_tool_calls'])
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertEqual(request.get_header('Idempotency-key'), 'business')

    def test_video_content_and_optional_fields(self):
        parts = [{'type': 'text', 'text': '场景'}, {'type': 'image_url', 'image_url': {'url': 'https://example.test/a.png'}, 'role': 'reference_image'}, {'type': 'audio_url', 'audio_url': {'url': 'https://example.test/a.mp3'}, 'role': 'reference_audio'}]
        with patch.object(http, 'urlopen', return_value=io.BytesIO(b'{}')) as send:
            self.client.video(model='video-model', content=parts, ratio='9:16', generate_audio=True, return_last_frame=True, idempotency_key='video-business')
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, 'https://example.test/v1/videos')
        body = json.loads(request.data)
        self.assertEqual(body['content'], parts)
        self.assertNotIn('prompt', body)
        self.assertNotIn('request_id', body)
        self.assertEqual(body['ratio'], '9:16')
        self.assertTrue(body['generate_audio'])
        self.assertTrue(body['return_last_frame'])
        self.assertEqual(request.get_header('Idempotency-key'), 'video-business')

    def test_sdk_bearer_video_supports_content_frames_and_audio_options(self):
        sdk = QilingAiClient('https://example.test', token='sdk-token')
        sdk.license_session = {'app': {'app_key': 'registered-app'}}
        parts = [{'type': 'text', 'text': '场景'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,Zml4dHVyZQ=='}, 'role': 'first_frame'}]
        with patch.object(http, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(b'{}')) as send:
            sdk.ai_video(model='video-model', request_id='same-business', content=parts, ratio='9:16', generate_audio=False, return_last_frame=True)
            request = send.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(request.full_url, 'https://example.test/api/v1/sdk/ai/video')
            self.assertEqual(request.get_header('Authorization'), 'Bearer sdk-token')
            self.assertEqual(body['content'], parts)
            self.assertNotIn('prompt', body)
            self.assertFalse(body['generate_audio'])
            self.assertTrue(body['return_last_frame'])
            self.assertEqual(body['request_id'], 'same-business')
            sdk.ai_video('场景', model='video-model', request_id='frames', first_frame='https://example.test/first.png', last_frame='https://example.test/last.png')
            self.assertEqual(json.loads(send.call_args.args[0].data)['last_frame'], 'https://example.test/last.png')
        with patch.object(http, 'urlopen') as send:
            with self.assertRaises(ValueError):
                sdk.ai_video('场景', model='video-model', request_id='mixed', content=parts)
            send.assert_not_called()

    def test_image_stream_is_rejected_before_json_request_with_bridge_guidance(self):
        with patch.object(http, 'urlopen') as send:
            with self.assertRaisesRegex(ValueError, 'openai'):
                self.client.image('场景', model='image-model', stream=True)
            send.assert_not_called()

    def test_video_convenience_references_and_ambiguous_fields(self):
        with patch.object(http, 'urlopen', return_value=io.BytesIO(b'{}')) as send:
            self.client.video('场景', model='video-model', reference_images=['https://example.test/a.png'], reference_audios=['https://example.test/a.mp3'])
            body = json.loads(send.call_args.args[0].data)
            self.assertEqual(body['reference_audios'], ['https://example.test/a.mp3'])
        with patch.object(http, 'urlopen') as send:
            with self.assertRaises(ValueError):
                self.client.video('场景', model='video-model', content=[{'type': 'text', 'text': '场景'}])
            send.assert_not_called()

    def test_optional_official_bridge_uses_same_key_url_context_and_no_auto_retry(self):
        try:
            import openai
        except ImportError:
            self.skipTest('optional official SDK not installed')
        with patch.object(openai, 'OpenAI') as bridge:
            self.client.openai()
        self.assertEqual(bridge.call_args.kwargs, {
            'base_url': 'https://example.test/v1', 'api_key': 'fixture-key',
            'default_headers': {'x-qiling-app-key': 'registered-app'}, 'timeout': 600, 'max_retries': 0,
        })
        with patch.object(openai, 'OpenAI') as bridge:
            QilingOpenClient('https://example.test', 'fixture-key').openai()
        self.assertEqual(bridge.call_args.kwargs['default_headers'], {})
