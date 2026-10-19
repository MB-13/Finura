"""Object storage behind one interface.

`LocalStorage` keeps files on disk and imitates R2 pre-signed URLs with HMAC-signed, expiring links
served by this API (`routers/storage.py`). An R2 implementation will provide the same methods.
"""

import hashlib
import hmac
import os
import re
import shutil
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote, urlencode

from doctune.core.config import Settings, get_settings

KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.\-]{0,511}$")
Op = Literal["put", "get"]


class InvalidKey(ValueError):
    pass


def validate_key(key: str) -> str:
    if not KEY_RE.match(key) or ".." in key.split("/") or "//" in key or key.endswith("/"):
        raise InvalidKey(key)
    return key


@dataclass(frozen=True)
class SignedUrl:
    url: str
    method: Literal["PUT", "GET"]
    headers: dict[str, str]
    expires_at: int


@dataclass(frozen=True)
class ObjectInfo:
    size: int


class Storage(Protocol):
    def presign_put(self, key: str, *, content_type: str, max_bytes: int, ttl: int = 900) -> SignedUrl: ...
    def presign_get(self, key: str, *, ttl: int = 900, filename: str | None = None) -> SignedUrl: ...
    def head(self, key: str) -> ObjectInfo | None: ...
    def read_bytes(self, key: str, limit: int | None = None) -> bytes: ...
    def write_bytes(self, key: str, data: bytes) -> None: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path, signing_key: bytes, public_base_url: str):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._key = signing_key
        self._base = public_base_url.rstrip("/")

    # ---- paths ----
    def path_for(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise InvalidKey(key)
        return path

    # ---- signing ----
    def signature(self, op: Op, key: str, exp: int, content_type: str = "", max_bytes: int = 0) -> str:
        msg = f"{op}\n{key}\n{exp}\n{content_type}\n{max_bytes}".encode()
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def check_signature(self, op: Op, key: str, exp: int, sig: str, content_type: str = "", max_bytes: int = 0) -> bool:
        if exp < int(time.time()):
            return False
        expected = self.signature(op, key, exp, content_type, max_bytes)
        return hmac.compare_digest(expected, sig)

    def _url(self, key: str, params: dict[str, str | int]) -> str:
        return f"{self._base}/storage/{quote(key)}?{urlencode(params)}"

    def presign_put(self, key: str, *, content_type: str, max_bytes: int, ttl: int = 900) -> SignedUrl:
        validate_key(key)
        exp = int(time.time()) + ttl
        sig = self.signature("put", key, exp, content_type, max_bytes)
        url = self._url(key, {"op": "put", "exp": exp, "ct": content_type, "max": max_bytes, "sig": sig})
        return SignedUrl(url=url, method="PUT", headers={"Content-Type": content_type}, expires_at=exp)

    def presign_get(self, key: str, *, ttl: int = 900, filename: str | None = None) -> SignedUrl:
        validate_key(key)
        exp = int(time.time()) + ttl
        params: dict[str, str | int] = {"op": "get", "exp": exp, "sig": self.signature("get", key, exp)}
        if filename:
            params["fn"] = filename
        return SignedUrl(url=self._url(key, params), method="GET", headers={}, expires_at=exp)

    # ---- direct access (API + workers) ----
    def head(self, key: str) -> ObjectInfo | None:
        path = self.path_for(key)
        return ObjectInfo(size=path.stat().st_size) if path.is_file() else None

    def read_bytes(self, key: str, limit: int | None = None) -> bytes:
        with self.path_for(key).open("rb") as f:
            return f.read() if limit is None else f.read(limit)

    def write_bytes(self, key: str, data: bytes) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        target = (self.root / validate_key(prefix.rstrip("/"))).resolve()
        if target.is_relative_to(self.root) and target != self.root and target.is_dir():
            shutil.rmtree(target)


def build_storage(settings: Settings) -> Storage:
    return LocalStorage(
        settings.storage_local_dir,
        settings.storage_signing_key.get_secret_value().encode(),
        settings.public_api_url,
    )


@lru_cache
def get_storage() -> Storage:
    return build_storage(get_settings())
