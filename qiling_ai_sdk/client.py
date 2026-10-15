from __future__ import annotations

import base64
import json
import os
import platform
import socket
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


@dataclass
class DeviceDescriptor:
    id: str
    name: str
    platform: str
    fingerprint: str = ""
    client_version: str = ""


class QilingAiError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        super().__init__(detail if isinstance(detail, str) else "Qiling AI API request failed")
        self.status = status
        self.detail = detail


def create_desktop_device(app_name: str = "qiling-ai", client_version: str = "") -> DeviceDescriptor:
    home = Path.home() / f".{app_name}"
    home.mkdir(parents=True, exist_ok=True)
    device_file = home / "device_id"
    if device_file.exists():
        device_id = device_file.read_text(encoding="utf-8").strip()
    else:
        device_id = f"python-{uuid.uuid4()}"
        device_file.write_text(device_id, encoding="utf-8")
    system = platform.system().lower()
    platform_name = "windows" if system == "windows" else "macos" if system == "darwin" else "linux"
    return DeviceDescriptor(
        id=device_id,
        name=socket.gethostname() or "Python Client",
        platform=platform_name,
        fingerprint=f"{platform.node()}|{platform.machine()}|{os.name}",
        client_version=client_version,
    )


class QilingAiClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        device_provider: Callable[[], DeviceDescriptor] | None = None,
        timeout: int = 30,
        refresh_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.refresh_token = refresh_token
        self._refresh_lock = threading.RLock()
        self._generation = 0
        self._purpose = self._token_purpose(token)
        self.device_provider = device_provider or create_desktop_device
        self.timeout = timeout
        self.license_session: dict[str, Any] | None = None

    @staticmethod
    def _token_purpose(token: str | None) -> str:
        try:
            body = (token or "").split(".", 1)[0]
            value = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            return "account" if value.get("purpose") == "account" else "sdk"
        except (ValueError, TypeError, AttributeError):
            return "sdk"

    def set_token(self, token: str | None, refresh_token: str | None = None) -> None:
        with self._refresh_lock:
            self._generation += 1
            self.token = token
            self.refresh_token = refresh_token
            self._purpose = self._token_purpose(token)
            self.license_session = None

    def get_refresh_token(self) -> str | None:
        return self.refresh_token

    def refresh_session(self) -> dict[str, Any]:
        with self._refresh_lock:
            if not self.refresh_token:
                raise QilingAiError(401, "SESSION_EXPIRED")
            path = "/api/v1/auth/refresh" if self._purpose == "account" else "/api/v1/sdk/session/refresh"
            result = self._request("POST", path, {"refresh_token": self.refresh_token}, auth=False)
            self.token = result.get("sdk_token") or result["access_token"]
            self.refresh_token = result["refresh_token"]
            if self.license_session is not None:
                self.license_session.update(sdk_token=self.token, refresh_token=self.refresh_token)
            return result

    def logout(self) -> None:
        with self._refresh_lock:
            path = "/api/v1/auth/logout" if self._purpose == "account" else "/api/v1/sdk/session/logout"
            payload = {"refresh_token": self.refresh_token} if self.refresh_token else None
            try:
                self._request("POST", path, payload, _retried=True)
            finally:
                self.set_token(None)

    def get_token(self) -> str | None:
        return self.token

    def get_license_session(self) -> dict[str, Any] | None:
        return self.license_session

    def bootstrap(self, app_key: str, site_code: str = "platform", test_license_key: str | None = None) -> dict[str, Any]:
        query = urlencode({"site_code": site_code})
        return self._request("GET", f"/api/v1/public/apps/{quote(app_key)}/bootstrap?{query}", auth=False,
            extra_headers={"X-Qiling-Test-License": test_license_key} if test_license_key else None)

    def get_storefront(
        self,
        site_code: str | None = None,
        app_key: str | None = None,
        category: str | None = None,
        keyword: str | None = None,
        test_license_key: str | None = None,
    ) -> dict[str, Any]:
        current_site = self.license_session.get("site", {}).get("code") if self.license_session else None
        query: dict[str, str] = {"site_code": current_site or site_code or "platform"}
        if app_key:
            query["app_key"] = app_key
        if category:
            query["category"] = category
        if keyword:
            query["keyword"] = keyword
        return self._request("GET", f"/api/v1/sdk/storefront?{urlencode(query)}", auth=False,
            extra_headers={"X-Qiling-Test-License": test_license_key} if test_license_key else None)

    def create_attribution(
        self, site_code: str, referrer_code: str | None = None, campaign: str | None = None
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/sdk/attribution",
            {"site_code": site_code, "referrer_code": referrer_code, "campaign": campaign},
        )

    def license_login(self, app_key: str, license_key: str) -> dict[str, Any]:
        self.set_token(None)
        generation = self._generation
        device = self.device_provider()
        payload = {
            "app_key": app_key,
            "license_key": license_key,
            "device_id": device.id,
            "device_name": device.name,
            "platform": device.platform,
            "client_version": device.client_version,
            "device_fingerprint": device.fingerprint,
        }
        result = self._request("POST", "/api/v1/sdk/license/login", payload, auth=False)
        if generation != self._generation:
            raise QilingAiError(409, "SESSION_CHANGED")
        self.refresh_token = result.get("refresh_token")
        self._purpose = "sdk"
        self.license_session = result
        token = result.get("sdk_token")
        if token:
            self.token = token
        return result

    def license_check(self, app_key: str) -> dict[str, Any]:
        device = self.device_provider()
        result = self._request(
            "POST",
            "/api/v1/sdk/license/check",
            {
                "app_key": app_key,
                "device_id": device.id,
                "client_version": device.client_version,
            },
        )
        result.update(sdk_token=self.token, refresh_token=self.refresh_token)
        self.license_session = result
        return result

    def create_payment(
        self,
        product_slug: str,
        plan_code: str,
        site_code: str | None = None,
        promoter_code: str | None = None,
    ) -> dict[str, Any]:
        if not self.license_session:
            raise RuntimeError("Please call license_login or license_check before creating a payment.")
        site_code = self.license_session.get("site", {}).get("code") or site_code or "platform"
        return self._request(
            "POST",
            "/api/v1/payments/mediacore/create",
            {
                "product_slug": product_slug,
                "plan_code": plan_code,
                "site_code": site_code or "platform",
                "promoter_code": promoter_code,
                "entitlement_mode": "new_license",
            },
        )

    def create_renewal_payment(self, plan_code: str) -> dict[str, Any]:
        if not self.license_session:
            raise RuntimeError("Please call license_login or license_check before creating a renewal payment.")
        return self._request(
            "POST",
            "/api/v1/payments/mediacore/create",
            {
                "product_slug": self.license_session["product"]["slug"],
                "plan_code": plan_code,
                "site_code": self.license_session["site"]["code"],
                "entitlement_mode": "renew",
                "renew_license_id": self.license_session["license"]["id"],
            },
        )

    def get_payment_status(self, order_no: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/payments/mediacore/status/{quote(order_no)}")

    def claim_free_plan(
        self,
        product_slug: str,
        plan_code: str,
        site_code: str = "platform",
        promoter_code: str | None = None,
    ) -> dict[str, Any]:
        """Claim a free plan without payment. Requires a logged-in user token."""
        return self._request(
            "POST",
            "/api/v1/orders/claim-free",
            {
                "product_slug": product_slug,
                "plan_code": plan_code,
                "site_code": site_code,
                "promoter_code": promoter_code,
            },
        )

    def consume_quota(self, amount: int = 1, feature_code: str = "default") -> dict[str, Any]:
        """Report quota usage back to the platform and atomically deduct it.

        Valid for any entitlement with a configured quota.
        """
        if not self.license_session:
            raise RuntimeError("Please call license_login or license_check before consuming quota.")
        app_key = self.license_session.get("app", {}).get("app_key")
        if not app_key:
            raise RuntimeError("Current license session has no app_key.")
        result = self._request(
            "POST",
            "/api/v1/sdk/licenses/consume",
            {"app_key": app_key, "amount": amount, "feature_code": feature_code},
        )
        if self.license_session and result.get("quota_used") is not None:
            license_info = self.license_session.setdefault("license", {})
            license_info["quota_used"] = result["quota_used"]
            license_info["quota_total"] = result.get("quota_total")
        return result

    def _ai_app_key(self) -> str:
        """当前授权 App Key，不接受客户端上游地址。"""
        key = (self.license_session or {}).get("app", {}).get("app_key")
        if not key:
            raise RuntimeError("请先登录或校验软件授权")
        return key

    def ai_models(self) -> dict[str, Any]:
        """查询平台已启用模型和用户报价；需有效软件授权及套餐 AI 开关。"""
        query = urlencode({"app_key": self._ai_app_key()})
        return self._request("GET", "/api/v1/sdk/ai/models?" + query)

    def ai_estimate(self, kind: str, **request: Any) -> dict[str, Any]:
        """预估最大费用，不产生供应商调用。"""
        return self._request("POST", "/api/v1/sdk/ai/estimate", {
            "kind": kind, "request": {**request, "app_key": self._ai_app_key()},
        })

    def ai_video(
        self, prompt: str, *, request_id: str, model: str, duration: int = 5, resolution: str = "720p",
        reference_images: list[str] | None = None, reference_video: str | None = None, reference_seconds: int = 0,
    ) -> dict[str, Any]:
        """提交一次视频任务；重试复用业务 request_id，随后查询返回的任务 id。"""
        return self._request("POST", "/api/v1/sdk/ai/video", {
            "app_key": self._ai_app_key(), "request_id": request_id, "model": model, "prompt": prompt,
            "duration": duration, "resolution": resolution, "reference_images": reference_images or [],
            "reference_video": reference_video, "reference_seconds": reference_seconds,
        })

    def ai_task(self, task_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/sdk/ai/tasks/{int(task_id)}")

    def ai_cancel_video(self, task_id: int) -> dict[str, Any]:
        """请求取消，以查询到的上游取消状态为准。"""
        return self._request("POST", f"/api/v1/sdk/ai/tasks/{int(task_id)}/cancel", {})

    def ai_bills(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        query = urlencode({"page": page, "page_size": page_size})
        return self._request("GET", "/api/v1/sdk/ai/bills?" + query)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        auth: bool = True,
        *,
        _retried: bool = False,
        _generation: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        with self._refresh_lock:
            generation = self._generation if _generation is None else _generation
            if auth and generation != self._generation:
                raise QilingAiError(409, "SESSION_CHANGED")
            sent_token = self.token
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json", **(extra_headers or {})}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth and sent_token:
            headers["Authorization"] = f"Bearer {sent_token}"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                if auth and generation != self._generation:
                    raise QilingAiError(409, "SESSION_CHANGED")
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 401 and auth and not _retried and self.refresh_token:
                exc.close()
                with self._refresh_lock:
                    if generation != self._generation:
                        raise QilingAiError(409, "SESSION_CHANGED") from None
                    if self.token == sent_token:
                        self.refresh_session()
                return self._request(method, path, payload, auth, _retried=True, _generation=generation, extra_headers=extra_headers)
            raw = exc.read().decode("utf-8", errors="ignore")
            try:
                detail = json.loads(raw).get("detail", raw)
            except json.JSONDecodeError:
                detail = raw or exc.reason
            raise QilingAiError(exc.code, detail) from exc
