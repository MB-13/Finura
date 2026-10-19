"""HTTP client for the DocTune notebook API (`/jobs/current/*`, job token auth) and pre-signed R2 transfers.

Rules:
- Retries with exponential backoff on network errors and 5xx; never retries 4xx.
- The job token is only sent to the DocTune API, never to pre-signed storage URLs, and never printed.
- Errors carry the server's message ({"error": code, "message": text}) so the notebook can show it as-is.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import requests

from doctune_nb import __version__, ui

API_PREFIX = "/jobs/current"
CHUNK = 1024 * 1024


# --------------------------------------------------------------------------------------------- errors


class DocTuneError(Exception):
    """Base error with a user-friendly message."""

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status

    def __str__(self) -> str:
        return self.message

    def _render_traceback_(self) -> list[str]:  # short output in IPython
        return [f"{ui.PREFIX} {type(self).__name__}: {self.message}"]


class TokenError(DocTuneError):
    """401: token missing / invalid / revoked / expired."""


class TokenExpired(TokenError):
    pass


class TokenRevoked(TokenError):
    pass


class NotebookOutdated(DocTuneError):
    """426: the server needs a newer notebook."""


class ConflictError(DocTuneError):
    """409: job_ended, adapter_missing, upload_mismatch, too_large, ..."""


class ApiUnavailable(DocTuneError):
    """Network errors / 5xx after all retries."""


class ChecksumMismatch(DocTuneError):
    pass


_TOKEN_HINTS = {
    "token_expired": "Create a new token on the project page and paste it in the token cell.",
    "token_revoked": "Copy the current token from the project page (or start a new training run).",
    "token_invalid": "Check that you pasted the whole token (it starts with dtj_).",
    "token_missing": "Run the token cell and paste your DocTune job token.",
}


def _error_from_response(resp: requests.Response) -> DocTuneError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    code = body.get("error") if isinstance(body, dict) else None
    message = (body.get("message") if isinstance(body, dict) else None) or f"HTTP {resp.status_code}"
    status = resp.status_code
    if status == 401:
        hint = _TOKEN_HINTS.get(code or "", "")
        cls: type[DocTuneError] = {"token_expired": TokenExpired, "token_revoked": TokenRevoked}.get(
            code or "", TokenError
        )
        return cls(f"{message} {hint}".strip(), code=code, status=status)
    if status == 426:
        return NotebookOutdated(message, code=code or "notebook_outdated", status=status)
    if status == 409:
        return ConflictError(message, code=code, status=status)
    if status >= 500:
        return ApiUnavailable(f"DocTune is temporarily unavailable ({message}).", code=code, status=status)
    return DocTuneError(message, code=code, status=status)


# --------------------------------------------------------------------------------------------- config


def _from_dict(cls: Any, data: dict[str, Any]) -> Any:
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Hyperparams:
    epochs: int
    lora_r: int
    lora_alpha: int
    learning_rate: float
    batch_size: int
    grad_accum: int
    max_seq_len: int
    warmup_ratio: float = 0.05
    weight_decay: float = 0.01
    lr_scheduler: str = "cosine"
    optim: str = "adamw_8bit"
    checkpoint_minutes: int = 7


@dataclass
class DatasetRef:
    train_url: str
    eval_url: str
    sha256_train: str
    sha256_eval: str
    train_count: int
    eval_count: int
    system_prompt: str | None = None


@dataclass
class JobConfig:
    job_id: str
    project_name: str
    base_model_id: str
    base_model_license: str | None
    is_llama: bool
    train_mode: str  # "lora16" | "qlora4"
    hyperparams: Hyperparams
    seed: int
    max_steps: int
    lib_versions: dict[str, str]
    dataset: DatasetRef
    checkpoint_every_minutes: int = 7
    heartbeat_every_seconds: int = 30
    eval_max_items: int = 100
    notebook_min_version: str = "0.0.0"
    project_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobConfig:
        d = dict(data)
        d["job_id"] = str(d["job_id"])
        d["hyperparams"] = _from_dict(Hyperparams, d["hyperparams"])
        d["dataset"] = _from_dict(DatasetRef, d["dataset"])
        cfg = _from_dict(cls, d)
        cfg.raw = data
        if cfg.train_mode not in ("lora16", "qlora4"):
            raise DocTuneError(f"Unknown training mode {cfg.train_mode!r}; update the notebook.")
        return cfg


# --------------------------------------------------------------------------------------------- helpers


def sha256_file(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


class DocTuneClient:
    """Talks to `{api_url}/jobs/current/*` with the job token."""

    def __init__(
        self,
        token: str,
        api_url: str,
        *,
        retries: int = 4,
        backoff_s: float = 2.0,
        timeout_s: float = 30.0,
        transfer_timeout_s: float = 900.0,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        token = (token or "").strip()
        if not token:
            raise TokenError("No job token entered. Run the token cell again and paste your DocTune job token.")
        if not token.startswith("dtj_"):
            raise TokenError("That doesn't look like a DocTune job token (it starts with dtj_). Copy it again.")
        self._token = token
        self.api_url = api_url.rstrip("/")
        self.retries = retries
        self.backoff_s = backoff_s
        self.timeout_s = timeout_s
        self.transfer_timeout_s = transfer_timeout_s
        # The session carries no default auth header: the token is attached per API request only.
        self._http = session or requests.Session()
        self._sleep = sleep

    def __repr__(self) -> str:  # never show the token
        return f"DocTuneClient(api_url={self.api_url!r}, token={ui.mask(self._token)})"

    # ---------------------------------------------------------------- low level

    def _with_retries(self, what: str, fn: Callable[[], requests.Response]) -> requests.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = fn()
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = ApiUnavailable(f"Network problem during {what}: {type(exc).__name__}.")
            else:
                if resp.status_code < 400:
                    return resp
                err = _error_from_response(resp)
                if resp.status_code < 500:
                    raise err  # 4xx: never retry
                last = err
            if attempt < self.retries:
                self._sleep(min(self.backoff_s * (2**attempt), 60.0))
        assert last is not None
        raise last

    def _request(self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.api_url}{API_PREFIX}{path}"
        headers = {"Authorization": f"Bearer {self._token}", "User-Agent": f"doctune-nb/{__version__}"}
        resp = self._with_retries(
            f"{method} {path}",
            lambda: self._http.request(method, url, json=json, params=params, headers=headers, timeout=self.timeout_s),
        )
        return resp.json() if resp.content else {}

    # ---------------------------------------------------------------- signed transfers (no auth header)

    def put_signed(self, url: str, path: str | os.PathLike[str], headers: dict[str, str] | None = None) -> None:
        """Stream a file to a pre-signed PUT URL. Only the signed headers are sent."""
        size = os.path.getsize(path)

        def do() -> requests.Response:
            with open(path, "rb") as f:
                h = {**(headers or {}), "Content-Length": str(size)}
                return self._http.put(url, data=f, headers=h, timeout=self.transfer_timeout_s)

        try:
            self._with_retries("upload", do)
        except DocTuneError as exc:
            if exc.status and 400 <= exc.status < 500:
                raise DocTuneError(
                    f"The storage upload was rejected (HTTP {exc.status}); the upload link may have expired.",
                    code="upload_rejected",
                    status=exc.status,
                ) from None
            raise

    def download_signed(
        self, url: str, dest: str | os.PathLike[str], *, sha256: str | None = None, desc: str = "download"
    ) -> Path:
        """Stream a pre-signed GET to `dest` and verify its sha256 (raises ChecksumMismatch)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")

        def do() -> requests.Response:
            resp = self._http.get(url, stream=True, timeout=self.transfer_timeout_s)
            if resp.status_code >= 400:
                return resp
            h = hashlib.sha256()
            total = int(resp.headers.get("Content-Length") or 0) or None
            with open(tmp, "wb") as f:
                for chunk in ui.progress(
                    resp.iter_content(CHUNK), total=(total // CHUNK + 1) if total else None, desc=desc
                ):
                    f.write(chunk)
                    h.update(chunk)
            resp.digest = h.hexdigest()  # type: ignore[attr-defined]
            return resp

        try:
            resp = self._with_retries(desc, do)
        except DocTuneError as exc:
            tmp.unlink(missing_ok=True)
            if exc.status and 400 <= exc.status < 500:
                raise DocTuneError(
                    f"The {desc} link was rejected (HTTP {exc.status}); it may have expired. Run the cell again.",
                    code="download_rejected",
                    status=exc.status,
                ) from None
            raise
        digest = getattr(resp, "digest", None)
        if sha256 and digest != sha256:
            tmp.unlink(missing_ok=True)
            raise ChecksumMismatch(f"The {desc} is corrupted (checksum mismatch). Run the cell again.")
        os.replace(tmp, dest)
        return dest

    # ---------------------------------------------------------------- endpoints

    def config(self) -> JobConfig:
        data = self._request("GET", "/config", params={"notebook_version": __version__})
        return JobConfig.from_dict(data)

    def start(self, runtime: dict[str, Any], resumed_from_step: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"runtime": runtime}
        if resumed_from_step is not None:
            body["resumed_from_step"] = resumed_from_step
        return self._request("POST", "/start", json=body)

    def heartbeat(
        self,
        step: int,
        max_steps: int,
        loss: float | None = None,
        lr: float | None = None,
        epoch: float | None = None,
    ) -> dict[str, Any]:
        body = {"step": max(0, int(step)), "max_steps": max(1, int(max_steps)), "loss": loss, "lr": lr, "epoch": epoch}
        return self._request("POST", "/heartbeat", json=body)

    def checkpoint_latest(self) -> dict[str, Any]:
        return self._request("GET", "/checkpoint/latest")

    def download_checkpoint(self, dest: str | os.PathLike[str], latest: dict[str, Any] | None = None) -> Path | None:
        latest = latest if latest is not None else self.checkpoint_latest()
        if not latest.get("exists"):
            return None
        return self.download_signed(latest["url"], dest, sha256=latest.get("sha256"), desc="checkpoint")

    def upload_checkpoint(self, zip_path: str | os.PathLike[str], step: int) -> dict[str, Any]:
        size, digest = os.path.getsize(zip_path), sha256_file(zip_path)
        signed = self._request("POST", "/checkpoint/upload-url", json={"size_bytes": size, "step": step})
        self.put_signed(signed["url"], zip_path, signed.get("headers"))
        return self._request("POST", "/checkpoint/complete", json={"sha256": digest, "size_bytes": size, "step": step})

    def pause(self, reason: str, step: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"reason": reason}
        if step is not None:
            body["step"] = max(0, int(step))
        return self._request("POST", "/pause", json=body)

    def training_complete(
        self, final_step: int, final_loss: float | None = None, train_runtime_s: float | None = None
    ) -> dict[str, Any]:
        body = {"final_step": int(final_step), "final_loss": final_loss, "train_runtime_s": train_runtime_s}
        return self._request("POST", "/training-complete", json=body)

    def upload_artifact(self, kind: str, path: str | os.PathLike[str]) -> dict[str, Any]:
        if kind not in ("adapter_safetensors", "eval_generations"):
            raise ValueError(f"unknown artifact kind {kind}")
        size, digest = os.path.getsize(path), sha256_file(path)
        signed = self._request("POST", "/artifacts/upload-url", json={"kind": kind, "size_bytes": size})
        self.put_signed(signed["url"], path, signed.get("headers"))
        return self._request("POST", "/artifacts/complete", json={"kind": kind, "sha256": digest, "size_bytes": size})

    def finish(
        self, metrics: dict[str, float | None] | None = None, exports: dict[str, str | None] | None = None
    ) -> dict[str, Any]:
        return self._request("POST", "/finish", json={"metrics": metrics or {}, "exports": exports or {}})

    def fail(self, error: str, step: int | None = None, fatal: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {"error": error[:2000], "fatal": fatal}
        if step is not None:
            body["step"] = int(step)
        return self._request("POST", "/fail", json=body)
