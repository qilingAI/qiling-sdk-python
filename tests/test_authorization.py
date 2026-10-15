from __future__ import annotations

import io
import json
import unittest
from urllib.error import URLError
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
