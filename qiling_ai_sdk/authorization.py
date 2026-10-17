"""Browser approval and one-time API Key retrieval without a local callback server."""
from __future__ import annotations

import time
import webbrowser
from typing import Any, Callable

from .client import QilingAiClient, QilingAiError
from .open_client import QilingOpenClient


class QilingAuthorizationClient:
    def __init__(self, base_url: str, *, app_key: str = "", client_name: str = "器灵 Skills", site_code: str = "", timeout: int = 30):
        self._http = QilingAiClient(base_url, timeout=timeout)
        self.app_key = app_key
        self.client_name = client_name
        self.site_code = site_code

    def start(self) -> dict[str, Any]:
        payload = {"app_key": self.app_key, "client_name": self.client_name}
        if self.site_code:
            payload["site_code"] = self.site_code
        return self._http._request("POST", "/api/v1/auth/api-key/requests", payload, auth=False)

    def poll(self, device_code: str) -> dict[str, Any]:
        """Retrieve once. If the response is lost, start a new authorization request."""
        return self._http._request("POST", "/api/v1/auth/api-key/token", {"device_code": device_code}, auth=False)

    def authorize(
        self, *, open_browser: bool = True, on_authorization_url: Callable[[str], None] | None = None,
        timeout: int = 600,
    ) -> dict[str, Any]:
        """Blocking helper for CLI/background workers; GUI event loops can use start/poll."""
        request = self.start()
        end = time.monotonic() + min(timeout, request["expires_in"])
        if on_authorization_url:
            on_authorization_url(request["verification_url"])
        if open_browser:
            opened = webbrowser.open(request["verification_url"])
            if not opened and not on_authorization_url:
                raise QilingAiError(503, "无法打开浏览器，请使用 on_authorization_url 展示授权地址")
        while time.monotonic() < end:
            try:
                result = self.poll(request["device_code"])
            except QilingAiError as error:
                if error.status != 429:
                    raise
                result = {"status": "pending"}
            if result["status"] == "authorized":
                return result
            if result["status"] != "pending":
                raise QilingAiError(409, "授权已结束或已领取，请重新授权")
            time.sleep(min(max(3, request["interval"]), max(0, end - time.monotonic())))
        raise QilingAiError(410, "授权等待超时，请重新发起")

    def connect(self, **options: Any) -> QilingOpenClient:
        result = self.authorize(**options)
        return QilingOpenClient(self._http.base_url, result["api_key"], app_key=self.app_key or result.get("app_key") or None)
