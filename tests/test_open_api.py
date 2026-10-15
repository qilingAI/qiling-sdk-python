from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from qiling_ai_sdk import QilingAiClient, QilingAiError, QilingOpenClient
from qiling_ai_sdk import client as http


class OpenApiTests(unittest.TestCase):
    def setUp(self):
        self.client = QilingOpenClient("https://api.example.test", "user-key", app_key="registered-app")

    def test_open_requests_use_api_key_and_optional_software_context(self):
        with patch.object(http, "urlopen", return_value=io.BytesIO(b'{}')) as request:
            self.client.balance()
        req = request.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.example.test/api/v1/open/balance")
        self.assertEqual(req.get_header("X-api-key"), "user-key")
        self.assertEqual(req.get_header("X-qiling-app-key"), "registered-app")
        self.assertIsNone(req.get_header("Authorization"))
        direct = QilingOpenClient("https://api.example.test", "user-key")
        with patch.object(http, "urlopen", return_value=io.BytesIO(b'{}')) as request:
            direct.models()
        self.assertIsNone(request.call_args.args[0].get_header("X-qiling-app-key"))

    def test_generation_keeps_business_request_id_and_all_supported_inputs(self):
        calls = []

        def response(req, **kwargs):
            calls.append(req)
            return io.BytesIO(b'{"id": 42, "status": "queued", "ok": false}')

        with patch.object(http, "urlopen", side_effect=response):
            for _ in range(2):
                result = self.client.chat([{"role": "user", "content": "hello"}], model="text-model", request_id="business-1", max_tokens=50)
            self.client.image("layers", model="image-model", request_id="business-2", n=2, size="auto", reference_images=["https://example.test/a.png"], layer_decomposition=True)
            self.client.video("waves", model="video-model", request_id="business-3", duration=10, reference_video="https://example.test/a.mp4", reference_seconds=5)
        self.assertFalse(result["ok"])
        self.assertEqual([json.loads(r.data)["request_id"] for r in calls], ["business-1", "business-1", "business-2", "business-3"])
        self.assertEqual(json.loads(calls[2].data)["reference_images"], ["https://example.test/a.png"])
        self.assertTrue(json.loads(calls[2].data)["layer_decomposition"])
        self.assertEqual(json.loads(calls[3].data)["reference_seconds"], 5)
        self.assertEqual(len(calls), 4)

    def test_model_and_request_id_are_required_before_network(self):
        with patch.object(http, "urlopen") as request:
            for method, value in [(self.client.chat, []), (self.client.image, "cat"), (self.client.video, "cat")]:
                with self.subTest(method=method.__name__):
                    with self.assertRaises(TypeError):
                        method(value, request_id="business-1")
                    with self.assertRaises(TypeError):
                        method(value, model="model")
            request.assert_not_called()

    def test_query_cancel_estimate_and_generic_tasks_use_distinct_routes(self):
        calls = []

        def response(req, **kwargs):
            calls.append(req)
            return io.BytesIO(b'{}')

        with patch.object(http, "urlopen", side_effect=response):
            self.client.model_call(42)
            self.client.cancel_video(42)
            self.client.estimate("video", {"model": "video-model", "request_id": "business-1", "prompt": "cat"})
            self.client.submit_task("tool", "hello", options={"language": "zh"})
            self.client.task("task/with?reserved")
            self.client.logs(limit=10, offset=20, days=7, endpoint="tool / one")
            self.client.usage(days=7, endpoint="tool / one")
            self.client.remove_ai("text")
            self.client.endpoints()
            self.client.model_docs()
        self.assertEqual([(r.method, urlsplit(r.full_url).path) for r in calls[:3]], [
            ("GET", "/api/v1/open/model-calls/42"),
            ("DELETE", "/api/v1/open/model-calls/42"),
            ("POST", "/api/v1/open/models/estimate"),
        ])
        self.assertEqual(json.loads(calls[2].data)["request"]["request_id"], "business-1")
        self.assertEqual(json.loads(calls[3].data), {"endpoint": "tool", "input": "hello", "options": {"language": "zh"}})
        self.assertTrue(calls[4].full_url.endswith("/tasks/task%2Fwith%3Freserved"))
        self.assertEqual(parse_qs(urlsplit(calls[5].full_url).query), {"limit": ["10"], "offset": ["20"], "days": ["7"], "endpoint": ["tool / one"]})

    def test_api_errors_and_unknown_network_results_are_not_retried(self):
        for status in [401, 402, 403, 409, 429, 503]:
            with self.subTest(status=status):
                error = HTTPError("https://api.example.test", status, "error", {}, io.BytesIO(b'{"detail":{"code":"FAILED"}}'))
                with patch.object(http, "urlopen", side_effect=error) as request:
                    with self.assertRaises(QilingAiError) as raised:
                        self.client.video("cat", model="video-model", request_id="business-1")
                self.assertEqual(raised.exception.status, status)
                self.assertEqual(raised.exception.detail, {"code": "FAILED"})
                self.assertEqual(request.call_count, 1)
        with patch.object(http, "urlopen", side_effect=URLError("timeout")) as request:
            with self.assertRaises(URLError):
                self.client.video("cat", model="video-model", request_id="business-1")
        self.assertEqual(request.call_count, 1)

    def test_remove_ai_preserves_paragraphs_through_http_json(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=repr(newline)):
                text = newline + "  第一段第一行" + newline + "第二行" + newline * 3 + "\t第二段，含字面量 \\n。" + newline * 2
                for submit, field in ((lambda: self.client.remove_ai(text), "text"),
                                      (lambda: self.client.submit_task("remove_ai", input=text), "input")):
                    with patch.object(http, "urlopen", return_value=io.BytesIO(b'{"task_id":"paragraph-task"}')) as request:
                        submit()
                    payload = json.loads(request.call_args.args[0].data.decode("utf-8"))
                    self.assertEqual(payload[field], text)

    def test_sdk_ai_uses_sdk_session_and_preserves_request_id(self):
        sdk = QilingAiClient("https://api.example.test", token="sdk-token")
        with patch.object(http, "urlopen") as request:
            with self.assertRaises(RuntimeError):
                sdk.ai_video("cat", model="video-model", request_id="business-1")
            request.assert_not_called()
        sdk.license_session = {"app": {"app_key": "registered-app"}}
        calls = []

        def response(req, **kwargs):
            calls.append(req)
            return io.BytesIO(b'{}')

        with patch.object(http, "urlopen", side_effect=response):
            sdk.ai_models()
            sdk.ai_estimate("video", model="video-model", request_id="business-1", prompt="cat", app_key="wrong-app")
            sdk.ai_video("cat", model="video-model", request_id="business-1")
            sdk.ai_task(42)
            sdk.ai_cancel_video(42)
            sdk.ai_bills(page=2, page_size=10)
        self.assertTrue(all(r.get_header("Authorization") == "Bearer sdk-token" for r in calls))
        self.assertTrue(all(r.get_header("X-api-key") is None for r in calls))
        self.assertEqual(json.loads(calls[1].data)["request"]["app_key"], "registered-app")
        self.assertEqual(json.loads(calls[2].data)["request_id"], "business-1")
        self.assertEqual(calls[4].method, "POST")
        self.assertTrue(calls[4].full_url.endswith("/sdk/ai/tasks/42/cancel"))
