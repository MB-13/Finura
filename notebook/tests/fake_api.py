"""A small in-process fake of the DocTune notebook API + pre-signed storage (stdlib http.server in a thread).

Mirrors backend/src/doctune/routers/notebook.py: `/jobs/current/*` with Bearer job token, {error, message} errors,
staging key for checkpoint uploads, and signed URLs under `/storage/<key>` that reject an Authorization header.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

TOKEN = "dtj_test_token_abcdefghijklmnopqrstuvwxyz"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_jsonl(pairs: list[tuple[str, str]], system: str | None = None) -> bytes:
    lines = []
    for q, a in pairs:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": q},
            {"role": "assistant", "content": a},
        ]
        lines.append(json.dumps({"messages": msgs}))
    return ("\n".join(lines) + "\n").encode()


@dataclass
class Recorded:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes
    query: dict[str, list[str]]

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


@dataclass
class FakeState:
    token: str = TOKEN
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    base_model_id: str = "unsloth/Qwen3.5-4B"
    train_mode: str = "lora16"
    is_llama: bool = False
    max_steps: int = 10
    min_version: str = "0.1.0"
    storage: dict[str, bytes] = field(default_factory=dict)
    checkpoint: dict[str, Any] | None = None  # {"step", "sha256", "key"}
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)
    # path -> list of (status, body) to return before normal handling (consumed in order)
    inject: dict[str, list[tuple[int, dict[str, Any]]]] = field(default_factory=dict)
    cancel_requested: bool = False
    job_state: str = "created"
    train_pairs: list[tuple[str, str]] = field(default_factory=list)
    eval_pairs: list[tuple[str, str]] = field(default_factory=list)
    system_prompt: str | None = None
    hyperparams: dict[str, Any] = field(default_factory=dict)
    seed: int = 1234

    def calls(self, method: str, path: str) -> list[Recorded]:
        return [r for r in self.requests if r.method == method and r.path == path]


class FakeApi:
    def __init__(self, state: FakeState | None = None):
        self.state = state or FakeState()
        if not self.state.train_pairs:
            self.state.train_pairs = [(f"Question {i}?", f"Answer number {i}.") for i in range(16)]
        if not self.state.eval_pairs:
            self.state.eval_pairs = [(f"Eval question {i}?", f"Reference answer {i}.") for i in range(4)]
        self.state.storage["d/train.jsonl"] = make_jsonl(self.state.train_pairs, self.state.system_prompt)
        self.state.storage["d/eval.jsonl"] = make_jsonl(self.state.eval_pairs, self.state.system_prompt)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)

    def __enter__(self) -> FakeApi:
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()

    def signed(self, key: str, op: str) -> str:
        return f"{self.url}/storage/{key}?op={op}&sig=fake"

    # ------------------------------------------------------------------ config

    def config(self) -> dict[str, Any]:
        s = self.state
        hp = {
            "epochs": 1,
            "lora_r": 8,
            "lora_alpha": 16,
            "learning_rate": 2e-4,
            "batch_size": 2,
            "grad_accum": 1,
            "max_seq_len": 512,
            "warmup_ratio": 0.05,
            "weight_decay": 0.01,
            "lr_scheduler": "cosine",
            "optim": "adamw_8bit",
            "checkpoint_minutes": 7,
            **s.hyperparams,
        }
        return {
            "job_id": s.job_id,
            "project_name": "Lumio Support Bot",
            "base_model_id": s.base_model_id,
            "base_model_license": "apache-2.0" if not s.is_llama else "llama3.1",
            "is_llama": s.is_llama,
            "train_mode": s.train_mode,
            "hyperparams": hp,
            "seed": s.seed,
            "max_steps": s.max_steps,
            "lib_versions": {"transformers": "5.17.0"},
            "dataset": {
                "train_url": self.signed("d/train.jsonl", "get"),
                "eval_url": self.signed("d/eval.jsonl", "get"),
                "sha256_train": sha(s.storage["d/train.jsonl"]),
                "sha256_eval": sha(s.storage["d/eval.jsonl"]),
                "train_count": len(s.train_pairs),
                "eval_count": len(s.eval_pairs),
                "system_prompt": s.system_prompt,
            },
            "checkpoint_every_minutes": 7,
            "heartbeat_every_seconds": 30,
            "eval_max_items": 100,
            "notebook_min_version": s.min_version,
            "project_url": "https://app.doctune.example/projects/p1",
        }

    # ------------------------------------------------------------------ handler

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        api = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _read(self) -> bytes:
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _send(self, status: int, body: Any = None, raw: bytes | None = None) -> None:
                data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
                self.send_response(status)
                self.send_header("Content-Type", "application/json" if raw is None else "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _err(self, status: int, code: str, message: str) -> None:
                self._send(status, {"error": code, "message": message})

            def _handle(self, method: str) -> None:
                u = urlparse(self.path)
                body = self._read()
                rec = Recorded(method, u.path, {k: v for k, v in self.headers.items()}, body, parse_qs(u.query))
                api.state.requests.append(rec)
                queue = api.state.inject.get(u.path)
                if queue:
                    status, payload = queue.pop(0)
                    return self._send(status, payload)
                if u.path.startswith("/storage/"):
                    return self._storage(method, u.path[len("/storage/") :], rec)
                if u.path.startswith("/jobs/current/"):
                    auth = self.headers.get("Authorization", "")
                    if auth != f"Bearer {api.state.token}":
                        return self._err(401, "token_invalid", "This job token isn't valid.")
                    return self._job(method, u.path[len("/jobs/current") :], rec)
                return self._err(404, "not_found", "Not found")

            def _storage(self, method: str, key: str, rec: Recorded) -> None:
                if "Authorization" in rec.headers:
                    return self._err(400, "bad_request", "signed URLs must not carry Authorization")
                if method == "PUT":
                    api.state.storage[key] = rec.body
                    return self._send(200, {})
                if key not in api.state.storage:
                    return self._err(404, "not_found", "no such object")
                return self._send(200, raw=api.state.storage[key])

            def _job(self, method: str, path: str, rec: Recorded) -> None:
                s = api.state
                b = rec.json() or {}
                if method == "GET" and path == "/config":
                    v = (rec.query.get("notebook_version") or ["0"])[0]
                    if tuple(int(x) for x in v.split(".")) < tuple(int(x) for x in s.min_version.split(".")):
                        return self._err(426, "notebook_outdated", "This notebook is outdated. Open the latest one.")
                    return self._send(200, api.config())
                if method == "POST" and path == "/start":
                    if s.job_state in ("completed", "failed"):
                        return self._err(409, "job_ended", "This job has already ended.")
                    s.job_state = "running"
                    return self._send(200, {"ok": True, "project_url": "https://app.doctune.example/projects/p1"})
                if method == "POST" and path == "/heartbeat":
                    return self._send(200, {"ok": True, "cancel_requested": s.cancel_requested})
                if method == "GET" and path == "/checkpoint/latest":
                    c = s.checkpoint
                    if not c:
                        return self._send(200, {"exists": False})
                    return self._send(
                        200,
                        {"exists": True, "step": c["step"], "sha256": c["sha256"], "url": api.signed(c["key"], "get")},
                    )
                if method == "POST" and path == "/checkpoint/upload-url":
                    return self._send(
                        200,
                        {
                            "url": api.signed("ckpt/upload.zip", "put"),
                            "headers": {"Content-Type": "application/zip"},
                            "expires_at": 0,
                        },
                    )
                if method == "POST" and path == "/checkpoint/complete":
                    data = s.storage.get("ckpt/upload.zip")
                    if data is None or len(data) != b["size_bytes"]:
                        return self._err(409, "upload_mismatch", "Checkpoint upload is missing or incomplete.")
                    s.storage["ckpt/latest.zip"] = s.storage.pop("ckpt/upload.zip")
                    s.checkpoint = {"step": b.get("step"), "sha256": b["sha256"], "key": "ckpt/latest.zip"}
                    return self._send(200, {"ok": True})
                if method == "POST" and path == "/pause":
                    s.job_state = "paused"
                    return self._send(200, {"ok": True})
                if method == "POST" and path == "/training-complete":
                    s.job_state = "evaluating"
                    return self._send(200, {"ok": True})
                if method == "POST" and path == "/artifacts/upload-url":
                    return self._send(
                        200,
                        {
                            "url": api.signed(f"art/{b['kind']}", "put"),
                            "headers": {"Content-Type": "application/octet-stream"},
                            "expires_at": 0,
                        },
                    )
                if method == "POST" and path == "/artifacts/complete":
                    data = s.storage.get(f"art/{b['kind']}")
                    if data is None or len(data) != b["size_bytes"]:
                        return self._err(409, "upload_mismatch", "Upload is missing or incomplete.")
                    s.artifacts[b["kind"]] = {"sha256": b["sha256"], "size": b["size_bytes"], "data": data}
                    return self._send(200, {"ok": True})
                if method == "POST" and path == "/finish":
                    if "adapter_safetensors" not in s.artifacts:
                        return self._err(409, "adapter_missing", "Upload the adapter before finishing.")
                    s.job_state = "completed"
                    return self._send(200, {"ok": True, "project_url": "https://app.doctune.example/projects/p1"})
                if method == "POST" and path == "/fail":
                    s.job_state = "failed" if b.get("fatal") else "paused"
                    return self._send(200, {"ok": True})
                return self._err(404, "not_found", "Not found")

            def do_GET(self) -> None:
                self._handle("GET")

            def do_POST(self) -> None:
                self._handle("POST")

            def do_PUT(self) -> None:
                self._handle("PUT")

        return H
