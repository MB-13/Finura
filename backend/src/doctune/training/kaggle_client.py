"""A small sync client for Kaggle's public API (https://api.kaggle.com/v1/{service}/{method}).

We deliberately don't depend on the `kaggle` package: it authenticates on import and falls back to files and
environment variables. Used from Celery workers (and from the API only through a threadpool or a task).
The token is only ever placed in the Authorization header; it never appears in errors or logs.
"""

import base64
import contextlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

import httpx
import structlog

from doctune.core.config import get_settings

log = structlog.get_logger()

BASE_URL = "https://api.kaggle.com/v1"
KERNELS = "kernels.KernelsApiService"

# tests inject an httpx.MockTransport here so nothing reaches the internet
test_transport: httpx.BaseTransport | None = None

SESSION_STATUSES = {
    0: "QUEUED",
    1: "RUNNING",
    2: "COMPLETE",
    3: "ERROR",
    4: "CANCEL_REQUESTED",
    5: "CANCEL_ACKNOWLEDGED",
    6: "NEW_SCRIPT",
}
ENDED_STATUSES = frozenset({"COMPLETE", "ERROR", "CANCEL_REQUESTED", "CANCEL_ACKNOWLEDGED"})


class KaggleError(Exception):
    """Anything that went wrong talking to Kaggle. `transient` errors are worth retrying."""

    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.message = message
        self.transient = transient


class KaggleAuthError(KaggleError):
    """Kaggle rejected the username or token (401), or denied a permission (403, `status`)."""

    def __init__(self, message: str, *, status: int = 401):
        super().__init__(message)
        self.status = status


class KaggleRateLimited(KaggleError):
    def __init__(self, message: str = "Kaggle is rate limiting requests", retry_after: float | None = None):
        super().__init__(message, transient=True)
        self.retry_after = retry_after


class KaggleQuotaError(KaggleError):
    """No GPU time left (or the account can't use GPUs)."""


@dataclass(frozen=True)
class SaveResult:
    ref: str
    url: str
    version: int | None


@dataclass(frozen=True)
class SessionStatus:
    status: str  # one of SESSION_STATUSES values
    failure_message: str | None

    @property
    def ended(self) -> bool:
        return self.status in ENDED_STATUSES


@dataclass(frozen=True)
class GpuQuota:
    used_s: int
    reserved_s: int
    total_s: int
    refresh_at: datetime | None

    @property
    def remaining_s(self) -> int:
        return max(0, self.total_s - self.used_s - self.reserved_s)

    @property
    def exhausted(self) -> bool:
        return self.total_s > 0 and self.remaining_s <= 0


def parse_duration(value: Any) -> int:
    """Protobuf JSON durations arrive as "3600s", a number, or {"seconds": n}; anything unknown counts as 0."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, dict):
        return parse_duration(value.get("seconds"))
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*s?\s*", str(value))
    return int(float(match.group(1))) if match else 0


def parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def normalize_status(value: Any) -> str:
    """Accept enum names ("COMPLETE", "KernelWorkerStatus.COMPLETE", "kernel_worker_status_complete") or ints."""
    if isinstance(value, int) and not isinstance(value, bool):
        return SESSION_STATUSES.get(value, "UNKNOWN")
    if value is None or value == "":
        return "QUEUED"  # protobuf JSON omits the zero enum value, so a queued kernel answers `{}`
    text = str(value).strip().upper()
    if text.isdigit():
        return SESSION_STATUSES.get(int(text), "UNKNOWN")
    for name in SESSION_STATUSES.values():
        if text == name or text.endswith("." + name) or text.endswith("_" + name):
            return name
    return "UNKNOWN"


def auth_header(username: str, token: str) -> str:
    """New tokens (KGAT_...) are bearer tokens; legacy 32-hex keys use HTTP Basic with the username."""
    if token.startswith("KGAT_"):
        return f"Bearer {token}"
    return "Basic " + base64.b64encode(f"{username}:{token}".encode()).decode()


class KaggleClient:
    def __init__(
        self,
        username: str,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        base_url: str = BASE_URL,
    ):
        self.username = username
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport or test_transport,
            headers={
                "Authorization": auth_header(username, token),
                "Content-Type": "application/json",
                "User-Agent": f"doctune/{get_settings().app_version}",
            },
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _call(self, service: str, method: str, body: dict[str, Any]) -> dict[str, Any]:
        # Kaggle answers with a `ka_sessionid` cookie; sending it back makes Kaggle treat the call as an
        # anonymous browser session and ignore the token (401 on kernel calls). Never send cookies.
        self._http.cookies.clear()
        try:
            response = self._http.post(f"/{service}/{method}", json=body)
        except httpx.HTTPError as exc:
            raise KaggleError(f"Couldn't reach Kaggle ({type(exc).__name__}).", transient=True) from None
        data: Any = None
        with contextlib.suppress(ValueError):
            data = response.json()
        payload: dict[str, Any] = data if isinstance(data, dict) else {}
        code = response.status_code
        body_code = payload.get("code")
        if isinstance(body_code, int) and body_code >= 400:
            code = max(code, body_code)
        err = payload.get("error")
        if isinstance(err, dict):  # {"error": {"code": 401, "message": "Unauthenticated", ...}}
            if isinstance(err.get("code"), int) and err["code"] >= 400:
                code = max(code, err["code"])
            err = err.get("message")
        message = str(payload.get("message") or err or "")[:300]
        if code >= 400:
            log.info("kaggle_call_failed", method=method, status=code, message=message)
        if code in (401, 403):
            raise KaggleAuthError(message or "Kaggle rejected this username or token.", status=code)
        if code == 429:
            retry_after = response.headers.get("retry-after", "")
            raise KaggleRateLimited(retry_after=float(retry_after) if retry_after.isdigit() else None)
        if code >= 500:
            raise KaggleError(message or f"Kaggle returned HTTP {code}.", transient=True)
        if code >= 400:
            raise KaggleError(message or f"Kaggle returned HTTP {code}.")
        return payload

    def save_kernel(
        self,
        slug: str,
        title: str,
        source: str,
        *,
        session_timeout_s: int,
        machine_shape: str = "NvidiaTeslaT4",
    ) -> SaveResult:
        """Create or update a private GPU script kernel in the user's account and start a run."""
        payload = self._call(
            KERNELS,
            "SaveKernel",
            {
                "slug": f"{self.username}/{slug}",
                "newTitle": title,
                "text": source,
                "language": "python",
                "kernelType": "script",
                "isPrivate": True,
                "enableGpu": True,
                "enableInternet": True,
                "machineShape": machine_shape,
                "sessionTimeoutSeconds": session_timeout_s,
                "datasetDataSources": [],
                "kernelDataSources": [],
                "competitionDataSources": [],
                "modelDataSources": [],
                "categoryIds": [],
            },
        )
        error = str(payload.get("error") or "").strip()
        if error:
            lowered = error.lower()
            if "quota" in lowered:
                raise KaggleQuotaError(error[:300])
            raise KaggleError(error[:300])
        # Kaggle's `ref` looks like "/code/<user>/<slug>"; keep our own "<user>/<slug>" for later status calls
        ref = f"{self.username}/{slug}"
        url = str(payload.get("url") or f"https://www.kaggle.com/code/{ref}")
        version = payload.get("versionNumber")
        return SaveResult(ref=ref, url=url, version=version if isinstance(version, int) else None)

    def session_status(self, slug: str) -> SessionStatus:
        payload = self._call(KERNELS, "GetKernelSessionStatus", {"userName": self.username, "kernelSlug": slug})
        message = str(payload.get("failureMessage") or "").strip()
        return SessionStatus(status=normalize_status(payload.get("status")), failure_message=message or None)

    def check_kernel_access(self) -> None:
        """Raises KaggleAuthError when the token can't use notebooks (some tokens can still read the quota)."""
        self._call(KERNELS, "ListKernels", {"user": self.username, "pageSize": 1})

    def gpu_quota(self) -> GpuQuota:
        payload = self._call(KERNELS, "GetAcceleratorQuotaStatistics", {})
        gpu = payload.get("gpuQuota")
        gpu = gpu if isinstance(gpu, dict) else {}
        return GpuQuota(
            used_s=parse_duration(gpu.get("timeUsed")),
            reserved_s=parse_duration(gpu.get("timeReserved")),
            total_s=parse_duration(gpu.get("totalTimeAllowed")),
            refresh_at=parse_time(payload.get("quotaRefreshTime")),
        )
