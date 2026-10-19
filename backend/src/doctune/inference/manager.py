"""One warm llama-server at a time (Oracle free VM: 2 OCPU / 12 GB, plan D19).

The inference worker owns the process; its state lives in Redis so the API can read it. Loading a
different (job, source) stops the current server first. Idle servers stop after IDLE_SECONDS.
"""

import json
import os
import signal
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import redis
import structlog

from doctune.core.config import get_settings
from doctune.core.storage import get_storage

log = structlog.get_logger()

STATE_KEY = "playground:server"
LOADING_KEY = "playground:loading"
IDLE_SECONDS = 600
PORT = 8091
CONTEXT = 4096


@dataclass
class ServerState:
    key: str  # f"{job_id}:{source}"
    port: int
    pid: int
    started_at: float
    last_used: float

    @property
    def url(self) -> str:
        return f"http://{get_settings().llama_host}:{self.port}"


def _redis() -> "redis.Redis":
    return redis.Redis.from_url(get_settings().redis_url)


def server_key(job_id: uuid.UUID | str, source: str) -> str:
    return f"{job_id}:{source}"


def current() -> ServerState | None:
    raw = _redis().get(STATE_KEY)
    return ServerState(**json.loads(raw)) if raw else None  # type: ignore[arg-type]


def is_loading(key: str) -> bool:
    return _redis().get(LOADING_KEY) == key.encode()


def touch() -> None:
    state = current()
    if state:
        state.last_used = time.time()
        _redis().set(STATE_KEY, json.dumps(asdict(state)))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop() -> None:
    state = current()
    if state and _alive(state.pid):
        os.kill(state.pid, signal.SIGTERM)
        for _ in range(50):
            if not _alive(state.pid):
                break
            time.sleep(0.1)
        else:
            os.kill(state.pid, signal.SIGKILL)
    _redis().delete(STATE_KEY)


def base_gguf_path(repo: str, filename: str) -> Path:
    """Download the base model GGUF once (cached on the models volume)."""
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(repo, filename, cache_dir=str(get_settings().llama_models_dir / "gguf")))


def adapter_path(storage_key: str) -> Path:
    cache = get_settings().llama_models_dir / "adapters"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / storage_key.replace("/", "_")
    if not target.exists():
        target.write_bytes(get_storage().read_bytes(storage_key))
    return target


def spawn(base: Path, adapter: Path, port: int) -> subprocess.Popen[bytes]:
    settings = get_settings()
    return subprocess.Popen(  # noqa: S603 - fixed argv
        [
            settings.llama_server_bin,
            "-m",
            str(base),
            "--lora",
            str(adapter),
            "-c",
            str(CONTEXT),
            "-t",
            str(settings.llama_threads),
            "--port",
            str(port),
            "--host",
            "0.0.0.0" if settings.llama_host != "127.0.0.1" else "127.0.0.1",  # noqa: S104
            "--parallel",
            "1",
            "--no-webui",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_healthy(url: str, timeout: float = 180.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def load(key: str, base_repo: str, base_file: str, adapter_key: str) -> ServerState:
    state = current()
    if state and state.key == key and _alive(state.pid):
        touch()
        return state
    r = _redis()
    r.set(LOADING_KEY, key, ex=300)
    try:
        stop()
        base = base_gguf_path(base_repo, base_file)
        adapter = adapter_path(adapter_key)
        proc = spawn(base, adapter, PORT)
        now = time.time()
        state = ServerState(key=key, port=PORT, pid=proc.pid, started_at=now, last_used=now)
        if not wait_healthy(state.url):
            proc.kill()
            raise RuntimeError("llama-server did not become healthy")
        r.set(STATE_KEY, json.dumps(asdict(state)))
        log.info("playground_loaded", key=key)
        return state
    finally:
        r.delete(LOADING_KEY)


def stop_if_idle() -> bool:
    state = current()
    if state and time.time() - state.last_used > IDLE_SECONDS:
        stop()
        return True
    return False
