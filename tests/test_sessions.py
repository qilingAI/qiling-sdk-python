from __future__ import annotations

import io
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from unittest.mock import patch

from qiling_ai_sdk import client as sdk


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())


class PythonSdkSessionTests(unittest.TestCase):
    def test_draft_bootstrap_credential_is_scoped_to_header(self):
        calls=[]
        def request(req, timeout):
            calls.append(req)
            return Response({})
        client=self.client()
        with patch.object(sdk,"urlopen",side_effect=request):
            client.bootstrap("draft-app",test_license_key="test-secret")
            client.get_storefront(app_key="draft-app",test_license_key="test-secret")
            client.bootstrap("live-app")
        self.assertEqual(calls[0].get_header("X-qiling-test-license"),"test-secret")
        self.assertEqual(calls[1].get_header("X-qiling-test-license"),"test-secret")
        self.assertIsNone(calls[2].get_header("X-qiling-test-license"))
        for req in calls:
            self.assertNotIn("test-secret",req.full_url)
            self.assertIsNone(req.get_header("Authorization"))

    def client(self):
        return sdk.QilingAiClient(
            "https://test.invalid",
            token="old",
            refresh_token="refresh",
            device_provider=lambda: sdk.DeviceDescriptor("device", "test", "web"),
        )

    def test_quick_authorization_boolean_tracks_login_and_check_without_an_extra_request(self):
        client = self.client()
        calls = []
        def request(req, **kwargs):
            calls.append(req.full_url)
            enabled = req.full_url.endswith('/login')
            return Response({'valid': True, 'sdk_token': 'sdk-session', 'refresh_token': 'sdk-refresh',
                             'product': {'ai_quick_authorization_enabled': enabled}})
        with patch.object(sdk, 'urlopen', side_effect=request):
            logged_in = client.license_login('tool', 'license')
            self.assertIs(logged_in['product']['ai_quick_authorization_enabled'], True)
            checked = client.license_check('tool')
            self.assertIs(checked['product']['ai_quick_authorization_enabled'], False)
            self.assertIs(client.license_session['product']['ai_quick_authorization_enabled'], False)
        self.assertEqual(calls, ['https://test.invalid/api/v1/sdk/license/login',
                                 'https://test.invalid/api/v1/sdk/license/check'])

    def test_product_details_preserve_html_markdown_and_optional_values(self):
        client = self.client()
        html = '<h2>软件详情</h2>\n<p>第一段 &amp; 第二段</p><img src="https://example.test/a.png"><video controls src="https://example.test/a.mp4"></video>'
        markdown = '## 历史详情\n\n第一段\n\n- 示例'
        for content in (html, markdown, '', None):
            with self.subTest(content=content):
                product = {'slug': 'tool', 'detail_content': content, 'ai_quick_authorization_enabled': False}
                session = {'valid': True, 'sdk_token': 'sdk-session', 'refresh_token': 'sdk-refresh', 'product': product}
                storefront = {'products': [product]}
                with patch.object(sdk, 'urlopen', side_effect=[Response(session), Response(session), Response({'product': product}), Response(storefront)]) as send:
                    self.assertEqual(client.license_login('tool', 'license')['product']['detail_content'], content)
                    self.assertEqual(client.license_check('tool')['product']['detail_content'], content)
                    self.assertEqual(client.get_license_session()['product']['detail_content'], content)
                    self.assertEqual(client.bootstrap('tool')['product']['detail_content'], content)
                    self.assertEqual(client.get_storefront(app_key='tool')['products'][0]['detail_content'], content)
                self.assertEqual(send.call_count, 4)
                self.assertIs(client.get_license_session()['product']['ai_quick_authorization_enabled'], False)

    def test_concurrent_requests_share_refresh_and_keep_credentials(self):
        client = self.client()
        refreshes = []
        barrier = threading.Barrier(2)

        def request(req, **kwargs):
            if req.full_url.endswith("/refresh"):
                refreshes.append(req.full_url)
                time.sleep(0.02)
                return Response({"access_token": "new", "sdk_token": "new", "refresh_token": "refresh"})
            if req.get_header("Authorization") != "Bearer new":
                barrier.wait(timeout=3)
                raise HTTPError(req.full_url, 401, "expired", {}, io.BytesIO(b'{"detail":"expired"}'))
            return Response({"valid": True, "license": {"id": 1}})

        with patch.object(sdk, "urlopen", side_effect=request), ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: client.license_check("app"), range(2)))
        self.assertEqual(len(refreshes), 1)
        self.assertTrue(all(result["valid"] for result in results))
        self.assertEqual(client.get_token(), "new")
        self.assertEqual(client.get_license_session()["refresh_token"], "refresh")

    def test_failed_authentication_is_not_retried_indefinitely(self):
        calls = []

        def request(req, **kwargs):
            calls.append(req.full_url)
            if req.full_url.endswith("/refresh"):
                return Response({"access_token": "new", "refresh_token": "refresh"})
            raise HTTPError(req.full_url, 401, "expired", {}, io.BytesIO(b'{"detail":"expired"}'))

        with patch.object(sdk, "urlopen", side_effect=request), self.assertRaises(sdk.QilingAiError) as error:
            self.client().license_check("app")
        self.assertEqual(error.exception.status, 401)
        self.assertEqual(sum(path.endswith("/refresh") for path in calls), 1)
        self.assertEqual(len(calls), 3)

    def test_logout_and_explicit_identity_change_clear_the_old_session(self):
        client = self.client()
        with patch.object(sdk, "urlopen", return_value=Response({"success": True})) as call:
            client.logout()
        self.assertTrue(call.call_args.args[0].full_url.endswith("/sdk/session/logout"))
        self.assertIsNone(client.get_token())
        self.assertIsNone(client.get_refresh_token())
        client.license_session = {"license": {"id": 1}}
        client.set_token("other", "other-refresh")
        self.assertIsNone(client.get_license_session())
        self.assertEqual(client.get_refresh_token(), "other-refresh")
