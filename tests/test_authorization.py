from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from qiling_ai_sdk import QilingAuthorizationClient, QilingAiError
from qiling_ai_sdk import authorization as auth
from qiling_ai_sdk import client as http


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = QilingAuthorizationClient("https://api.example.test", app_key="registered-app")
        self.start = {"device_code": "private-device-code", "verification_url": "https://api.example.test/confirm?request=public-code", "expires_in": 600, "interval": 3}

    def test_credentials_only_travel_in_post_body(self):
        with patch.object(http, "urlopen", side_effect=[io.BytesIO(json.dumps(self.start).encode()), io.BytesIO(b'{"status":"pending"}')]) as request:
            self.client.start()
            self.client.poll("private-device-code")
        first, second = [c.args[0] for c in request.call_args_list]
        self.assertEqual(first.method, "POST")
        self.assertTrue(first.full_url.endswith("/auth/api-key/requests"))
        self.assertEqual(json.loads(first.data)["app_key"], "registered-app")
        self.assertTrue(second.full_url.endswith("/auth/api-key/token"))
        self.assertEqual(json.loads(second.data), {"device_code": "private-device-code"})
        self.assertNotIn("private-device-code", second.full_url)
        self.assertIsNone(second.get_header("Authorization"))
        self.assertNotIn("site_code", json.loads(first.data))

    def test_site_source_is_sent_but_server_controls_confirmation_url(self):
        client = QilingAuthorizationClient("https://api.example.test", app_key="registered-app", site_code="agent-source")
        request = {**self.start, "verification_url": "https://custom.agent.test/account/api-authorize?request=public-code&site=agent-source"}
        with patch.object(http, "urlopen", return_value=io.BytesIO(json.dumps(request).encode())) as send:
            result = client.start()
        self.assertEqual(json.loads(send.call_args.args[0].data)["site_code"], "agent-source")
        with patch.object(client, "start", return_value=result), patch.object(client, "poll", return_value={"status": "authorized", "api_key": "private-key"}), patch.object(auth.webbrowser, "open", return_value=True) as browser:
            client.authorize()
        browser.assert_called_once_with(request["verification_url"])

    def test_invalid_site_does_not_fall_back_to_main_site_or_open_browser(self):
        for status in (404, 409):
            with self.subTest(status=status):
                client = QilingAuthorizationClient("https://api.example.test", site_code="agent-source")
                error = HTTPError("https://api.example.test", status, "site error", {}, io.BytesIO(b'{"detail":"site error"}'))
                with patch.object(http, "urlopen", side_effect=error) as send, patch.object(auth.webbrowser, "open") as browser:
                    with self.assertRaises(QilingAiError) as raised:
                        client.authorize()
                self.assertEqual(raised.exception.status, status)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(json.loads(send.call_args.args[0].data)["site_code"], "agent-source")
                browser.assert_not_called()

    def test_main_site_source_and_agent_key_keep_configured_api_origin(self):
        for source in ("", "platform"):
            with self.subTest(source=source):
                client = QilingAuthorizationClient("https://api.example.test", site_code=source)
                with patch.object(http, "urlopen", return_value=io.BytesIO(json.dumps(self.start).encode())) as send:
                    client.start()
                body = json.loads(send.call_args.args[0].data)
                self.assertEqual(body.get("site_code", ""), source)
        client = QilingAuthorizationClient("https://api.example.test", site_code="agent-source", app_key="registered-app")
        with patch.object(client, "authorize", return_value={"api_key": "billing-B-key", "app_key": "registered-app", "base_url": "https://custom.agent.test"}):
            connected = client.connect()
        with patch.object(http, "urlopen", return_value=io.BytesIO(b'{}')) as send:
            connected.balance()
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/api/v1/open/balance")
        self.assertEqual(request.get_header("X-api-key"), "billing-B-key")

    def test_pending_and_rate_limit_wait_before_one_time_success(self):
        success = {"status": "authorized", "api_key": "private-key", "app_key": "registered-app"}
        shown = []
        with patch.object(self.client, "start", return_value=self.start), patch.object(self.client, "poll", side_effect=[{"status": "pending"}, QilingAiError(429, "slow down"), success]) as poll, patch.object(auth.time, "sleep") as sleep, patch.object(auth.webbrowser, "open", return_value=True) as browser:
            result = self.client.authorize(on_authorization_url=shown.append)
        self.assertEqual(result, success)
        self.assertEqual(poll.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [3, 3])
        self.assertEqual(shown, [self.start["verification_url"]])
        browser.assert_called_once_with(self.start["verification_url"])

    def test_terminal_states_and_expiry_stop_polling(self):
        for result in [{"status": "denied"}, {"status": "consumed"}, {"status": "expired"}, QilingAiError(410, "expired")]:
            with self.subTest(result=result):
                results = [result] if isinstance(result, Exception) else None
                with patch.object(self.client, "start", return_value=self.start), patch.object(self.client, "poll", return_value=result, side_effect=results) as poll, patch.object(auth.time, "sleep") as sleep:
                    with self.assertRaises(QilingAiError):
                        self.client.authorize(open_browser=False)
                self.assertEqual(poll.call_count, 1)
                sleep.assert_not_called()

    def test_timeout_is_bounded_by_server_expiry(self):
        clock = [0]
        request = {**self.start, "expires_in": 5}

        def sleep(seconds):
            clock[0] += seconds

        with patch.object(self.client, "start", return_value=request), patch.object(self.client, "poll", return_value={"status": "pending"}) as poll, patch.object(auth.time, "monotonic", side_effect=lambda: clock[0]), patch.object(auth.time, "sleep", side_effect=sleep):
            with self.assertRaises(QilingAiError) as raised:
                self.client.authorize(open_browser=False, timeout=20)
        self.assertEqual(raised.exception.status, 410)
        self.assertEqual(clock[0], 5)
        self.assertEqual(poll.call_count, 2)

    def test_lost_response_is_not_polled_again(self):
        with patch.object(self.client, "start", return_value=self.start), patch.object(self.client, "poll", side_effect=URLError("lost response")) as poll:
            with self.assertRaises(URLError):
                self.client.authorize(open_browser=False)
        self.assertEqual(poll.call_count, 1)

    def test_browser_failure_can_use_a_visible_link_callback(self):
        with patch.object(self.client, "start", return_value=self.start), patch.object(auth.webbrowser, "open", return_value=False), patch.object(self.client, "poll") as poll:
            with self.assertRaises(QilingAiError):
                self.client.authorize()
            poll.assert_not_called()
        shown = []
        success = {"status": "authorized", "api_key": "private-key"}
        with patch.object(self.client, "start", return_value=self.start), patch.object(auth.webbrowser, "open", return_value=False), patch.object(self.client, "poll", return_value=success):
            result = self.client.authorize(on_authorization_url=shown.append)
        self.assertEqual(result, success)
        self.assertEqual(shown, [self.start["verification_url"]])

    def test_connect_keeps_configured_origin_and_software_context(self):
        with patch.object(self.client, "authorize", return_value={"api_key": "private-key", "app_key": "registered-app", "base_url": "https://other.example.test"}):
            client = self.client.connect(open_browser=False)
        self.assertEqual(client._http.base_url, "https://api.example.test")
        self.assertEqual(client.app_key, "registered-app")
