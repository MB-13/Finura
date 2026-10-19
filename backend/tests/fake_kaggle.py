"""A fake Kaggle API for tests: records requests, answers from settable fields."""

import json
from typing import Any

import httpx

from doctune.training import kaggle_client

SERVICE = "/v1/kernels.KernelsApiService"


class FakeKaggle:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.session_status: Any = "RUNNING"
        self.failure_message = ""
        self.http_status = 200  # applied to every call when not 200
        self.http_headers: dict[str, str] = {}
        self.save_error = ""
        self.rate_limit_calls = 0  # the next N calls answer 429
        self.quota: dict[str, Any] = {
            "quotaRefreshTime": "2026-10-12T00:00:00Z",
            "gpuQuota": {"timeUsed": "3600s", "timeReserved": "0s", "totalTimeAllowed": "108000s"},
        }
        self.saves = 0
        self.status_http = 200  # only for GetKernelSessionStatus
        self.kernels_unauthenticated = False  # token reads the quota but can't use notebooks (seen live)

    def calls(self, method: str) -> list[dict[str, Any]]:
        return [body for name, body, _ in self.requests if name == method]

    @property
    def last_source(self) -> str:
        return str(self.calls("SaveKernel")[-1]["text"])

    @property
    def last_token(self) -> str:
        import re

        match = re.search(r'JOB_TOKEN = "(dtj_[^"]+)"', self.last_source)
        assert match
        return match.group(1)

    def handle(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.removeprefix(f"{SERVICE}/")
        assert request.url.path.startswith(SERVICE), request.url
        body = json.loads(request.content or b"{}")
        self.requests.append((method, body, dict(request.headers)))
        if "cookie" in request.headers:  # real Kaggle ignores the token when its session cookie comes back
            return httpx.Response(401, json={"error": {"code": 401, "message": "Unauthenticated"}})
        if self.rate_limit_calls > 0:
            self.rate_limit_calls -= 1
            return httpx.Response(429, json={"message": "slow down"}, headers={"retry-after": "1"})
        if self.http_status != 200:
            return httpx.Response(self.http_status, json={"message": "nope"}, headers=self.http_headers)
        if self.kernels_unauthenticated and method != "GetAcceleratorQuotaStatistics":
            err = {"error": {"code": 401, "message": "Unauthenticated", "status": "UNAUTHENTICATED"}}
            return httpx.Response(401, json=err)
        if method == "SaveKernel":
            self.saves += 1
            if self.save_error:
                return httpx.Response(200, json={"error": self.save_error})
            slug = body["slug"]
            return httpx.Response(
                200,
                json={
                    "ref": f"/code/{slug}",
                    "url": f"https://www.kaggle.com/code/{slug}",
                    "versionNumber": self.saves,
                },
            )
        if method == "GetKernelSessionStatus":
            if self.status_http != 200:
                return httpx.Response(self.status_http, json={"error": {"code": self.status_http, "message": "denied"}})
            if self.session_status == "QUEUED":  # real Kaggle omits the zero enum value
                return httpx.Response(200, json={})
            return httpx.Response(200, json={"status": self.session_status, "failureMessage": self.failure_message})
        if method == "GetAcceleratorQuotaStatistics":
            return httpx.Response(200, json=self.quota, headers={"set-cookie": "ka_sessionid=abc; Path=/"})
        if method == "ListKernels":
            return httpx.Response(200, json={"kernels": []})
        return httpx.Response(404, json={"message": "unknown method"})

    def install(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(kaggle_client, "test_transport", httpx.MockTransport(self.handle))
