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

    def test_thinking_selection_and_omission_preserve_upstream_defaults(self):
        with patch.object(http, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(b'{}')) as send:
            for mode in ['disabled', 'enabled']:
                self.client.chat([{'role': 'user', 'content': 'hello'}], model='model', thinking={'type': mode})
                self.assertEqual(json.loads(send.call_args.args[0].data)['thinking'], {'type': mode})
            self.client.chat([{'role': 'user', 'content': 'hello'}], model='model')
            self.assertNotIn('thinking', json.loads(send.call_args.args[0].data))

    def test_dynamic_thinking_and_edit_metadata_are_not_dropped(self):
        config = {'supports_thinking': True, 'thinking_modes': ['enabled', 'disabled']}
        model = {'id': 'text-model', 'qiling': {'config': config}}
        schema = {'properties': {'thinking': {'properties': {'type': {'enum': ['enabled', 'disabled']}}}}}
        docs = {'items': [{'model': 'text-model', 'request_schema': schema}, {'model': 'image-model', 'edit': {'path': '/v1/images/edits'}}]}
        with patch.object(http, 'urlopen', side_effect=[io.BytesIO(json.dumps({'data': [model]}).encode()), io.BytesIO(json.dumps(docs).encode())]):
            self.assertEqual(self.client.models()['data'][0]['qiling']['config'], config)
            self.assertEqual(self.client.model_docs(), docs)

    def test_billing_account_key_is_independent_from_software_session(self):
        software = QilingAiClient('https://example.test', token='software-account-A', device_provider=lambda: http.DeviceDescriptor('stable-device', 'test', 'web'))
        billing = QilingOpenClient('https://example.test', 'billing-account-B-key', app_key='registered-app')
        with patch.object(http, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(b'{}')) as send:
            software.license_check('registered-app')
            billing.chat([{'role': 'user', 'content': 'hello'}], model='model')
        self.assertEqual(send.call_args_list[0].args[0].get_header('Authorization'), 'Bearer software-account-A')
        ai_request = send.call_args_list[1].args[0]
        self.assertEqual(ai_request.get_header('Authorization'), 'Bearer billing-account-B-key')
        self.assertEqual(ai_request.get_header('X-qiling-app-key'), 'registered-app')
        self.assertNotIn(b'software-account-A', ai_request.data)

    def test_estimate_does_not_submit_and_wallet_preserves_negative_balance(self):
        quote = {'estimated_fee': '2.123456789', 'currency': 'CNY'}
        wallet = {'balance': '-1.123456789', 'frozen': '0'}
        with patch.object(http, 'urlopen', side_effect=[io.BytesIO(json.dumps(quote).encode()), io.BytesIO(json.dumps(wallet).encode())]) as send:
            self.assertEqual(self.client.estimate('text', {'model': 'model', 'messages': [{'role': 'user', 'content': 'hello'}]}), quote)
            self.assertEqual(self.client.balance(), wallet)
        self.assertEqual([call.args[0].full_url for call in send.call_args_list], ['https://example.test/v1/models/estimate', 'https://example.test/api/v1/open/balance'])

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
