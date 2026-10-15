"""Open APIs use a user API Key, separate from account and SDK sessions."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from .client import QilingAiClient


class QilingOpenClient:
    def __init__(self, base_url: str, api_key: str, *, app_key: str | None = None, timeout: int = 600):
        base_url = base_url.rstrip("/")
        if urlsplit(base_url).path.endswith("/v1"):
            base_url = base_url[:-3]
        self._http = QilingAiClient(base_url, timeout=timeout)
        self._api_key = api_key
        self.app_key = app_key

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None, *,
        model_api: bool = False, idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"} if model_api else {"x-api-key": self._api_key}
        if self.app_key:
            headers["x-qiling-app-key"] = self.app_key
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        prefix = "/v1" if model_api else "/api/v1/open"
        return self._http._request(method, prefix + path, payload, auth=False, extra_headers=headers)

    def endpoints(self) -> dict[str, Any]:
        return self._request("GET", "/endpoints")

    def models(self) -> dict[str, Any]:
        return self._request("GET", "/models", model_api=True)

    def model(self, model_id: str) -> dict[str, Any]:
        return self._request("GET", "/models/" + quote(model_id, safe=""), model_api=True)

    def model_docs(self) -> dict[str, Any]:
        return self._request("GET", "/model-docs")

    def balance(self) -> dict[str, Any]:
        return self._request("GET", "/balance")

    def usage(self, *, days: int = 30, endpoint: str = "") -> dict[str, Any]:
        return self._request("GET", "/usage?" + urlencode({"days": days, "endpoint": endpoint}))

    def logs(self, *, limit: int = 50, offset: int = 0, days: int = 30, endpoint: str = "") -> dict[str, Any]:
        return self._request("GET", "/logs?" + urlencode({"limit": limit, "offset": offset, "days": days, "endpoint": endpoint}))

    def submit_task(self, endpoint: str, input: str = "", *, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/tasks", {"endpoint": endpoint, "input": input, "options": options or {}})

    def task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", "/tasks/" + quote(str(task_id), safe=""))

    def remove_ai(self, text: str) -> dict[str, Any]:
        """Submit text verbatim, preserving real line breaks and paragraph spacing."""
        return self._request("POST", "/remove-ai", {"text": text})

    def chat(
        self, messages: list[dict[str, str]], *, model: str, request_id: str | None = None,
        max_tokens: int | None = None, temperature: float | None = None,
        idempotency_key: str | None = None, **options: Any,
    ) -> dict[str, Any]:
        """Return OpenAI choices/usage/qiling JSON. Use the official OpenAI SDK for SSE."""
        if options.get("stream"):
            raise ValueError("流式调用请使用官方 OpenAI SDK，base_url 设置为已确认的平台根地址加 /v1。")
        payload = {"model": model, "messages": messages, **options}
        for key, value in {"request_id": request_id, "max_tokens": max_tokens, "temperature": temperature}.items():
            if value is not None:
                payload[key] = value
        return self._request("POST", "/chat/completions", payload, model_api=True, idempotency_key=idempotency_key)

    def image(
        self, prompt: str, *, model: str, request_id: str | None = None, n: int = 1, size: str | None = None,
        reference_images: list[str] | None = None, layer_decomposition: bool = False,
        response_format: str | None = None, idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Return the OpenAI created/data/qiling JSON without reshaping image entries."""
        payload = {"model": model, "prompt": prompt, "n": n}
        for key, value in {"request_id": request_id, "size": size, "reference_images": reference_images, "response_format": response_format}.items():
            if value is not None:
                payload[key] = value
        if layer_decomposition:
            payload["layer_decomposition"] = True
        return self._request("POST", "/images/generations", payload, model_api=True, idempotency_key=idempotency_key)

    def video(
        self, prompt: str, *, model: str, request_id: str, duration: int = 5, resolution: str = "720p",
        reference_images: list[str] | None = None, reference_video: str | None = None, reference_seconds: int = 0,
    ) -> dict[str, Any]:
        return self._request("POST", "/videos", {
            "request_id": request_id, "model": model, "prompt": prompt,
            "duration": duration, "resolution": resolution, "reference_images": reference_images or [],
            "reference_video": reference_video, "reference_seconds": reference_seconds,
        }, model_api=True)

    def estimate(self, kind: str, request: dict[str, Any]) -> dict[str, Any]:
        """Estimate the maximum fee without submitting to a provider or freezing balance."""
        return self._request("POST", "/models/estimate", {"kind": kind, "request": request}, model_api=True)

    def model_call(self, call_id: int) -> dict[str, Any]:
        return self._request("GET", f"/model-calls/{int(call_id)}", model_api=True)

    def cancel_video(self, call_id: int) -> dict[str, Any]:
        """Request cancellation; the final task status determines settlement."""
        return self._request("DELETE", f"/model-calls/{int(call_id)}", model_api=True)
