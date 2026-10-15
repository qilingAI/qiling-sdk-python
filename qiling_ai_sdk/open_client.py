"""Open APIs use a user API Key, separate from account and SDK sessions."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from .client import QilingAiClient


class QilingOpenClient:
    def __init__(self, base_url: str, api_key: str, *, app_key: str | None = None, timeout: int = 600):
        self._http = QilingAiClient(base_url, timeout=timeout)
        self._api_key = api_key
        self.app_key = app_key

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"x-api-key": self._api_key}
        if self.app_key:
            headers["x-qiling-app-key"] = self.app_key
        return self._http._request(method, "/api/v1/open" + path, payload, auth=False, extra_headers=headers)

    def endpoints(self) -> dict[str, Any]:
        return self._request("GET", "/endpoints")

    def models(self) -> dict[str, Any]:
        return self._request("GET", "/models")

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
        self, messages: list[dict[str, str]], *, model: str, request_id: str,
        max_tokens: int | None = None, temperature: float | None = None,
    ) -> dict[str, Any]:
        """Submit once; persist request_id and reuse it for the same business request."""
        return self._request("POST", "/chat/completions", {
            "request_id": request_id, "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
        })

    def image(
        self, prompt: str, *, model: str, request_id: str, n: int = 1, size: str | None = None,
        reference_images: list[str] | None = None, layer_decomposition: bool = False,
    ) -> dict[str, Any]:
        return self._request("POST", "/images/generations", {
            "request_id": request_id, "model": model, "prompt": prompt, "n": n, "size": size,
            "reference_images": reference_images or [], "layer_decomposition": layer_decomposition,
        })

    def video(
        self, prompt: str, *, model: str, request_id: str, duration: int = 5, resolution: str = "720p",
        reference_images: list[str] | None = None, reference_video: str | None = None, reference_seconds: int = 0,
    ) -> dict[str, Any]:
        return self._request("POST", "/videos", {
            "request_id": request_id, "model": model, "prompt": prompt,
            "duration": duration, "resolution": resolution, "reference_images": reference_images or [],
            "reference_video": reference_video, "reference_seconds": reference_seconds,
        })

    def estimate(self, kind: str, request: dict[str, Any]) -> dict[str, Any]:
        """Estimate the maximum fee without submitting to a provider or freezing balance."""
        return self._request("POST", "/models/estimate", {"kind": kind, "request": request})

    def model_call(self, call_id: int) -> dict[str, Any]:
        return self._request("GET", f"/model-calls/{int(call_id)}")

    def cancel_video(self, call_id: int) -> dict[str, Any]:
        """Request cancellation; the final task status determines settlement."""
        return self._request("DELETE", f"/model-calls/{int(call_id)}")
