import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import pytest

from doctune.core.storage import InvalidKey, LocalStorage, get_storage


def storage() -> LocalStorage:
    s = get_storage()
    assert isinstance(s, LocalStorage)
    return s


def path_and_query(url: str) -> str:
    u = urlparse(url)
    return f"{u.path}?{u.query}"


def tamper(url: str, **changes: str) -> str:
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    q.update(changes)
    return path_and_query(urlunparse(u._replace(query=urlencode(q))))


async def test_signed_upload_then_download(client: httpx.AsyncClient) -> None:
    put = storage().presign_put("u/1/p/1/docs/a/file.pdf", content_type="application/pdf", max_bytes=1000)
    r = await client.put(path_and_query(put.url), content=b"%PDF-1.7 hello", headers=put.headers)
    assert r.status_code == 204
    info = storage().head("u/1/p/1/docs/a/file.pdf")
    assert info is not None and info.size == 14

    get = storage().presign_get("u/1/p/1/docs/a/file.pdf", filename="file.pdf")
    r = await client.get(path_and_query(get.url))
    assert r.status_code == 200
    assert r.content == b"%PDF-1.7 hello"


async def test_upload_rejects_bad_signature(client: httpx.AsyncClient) -> None:
    put = storage().presign_put("k/a.pdf", content_type="application/pdf", max_bytes=1000)
    r = await client.put(tamper(put.url, sig="0" * 64), content=b"x", headers=put.headers)
    assert r.status_code == 403


async def test_upload_rejects_raised_size_limit(client: httpx.AsyncClient) -> None:
    put = storage().presign_put("k/a.pdf", content_type="application/pdf", max_bytes=10)
    r = await client.put(tamper(put.url, max="999999"), content=b"x", headers=put.headers)
    assert r.status_code == 403


async def test_upload_rejects_expired_link(client: httpx.AsyncClient) -> None:
    put = storage().presign_put("k/a.pdf", content_type="application/pdf", max_bytes=10, ttl=-1)
    r = await client.put(path_and_query(put.url), content=b"x", headers=put.headers)
    assert r.status_code == 403


async def test_upload_rejects_wrong_content_type(client: httpx.AsyncClient) -> None:
    put = storage().presign_put("k/a.pdf", content_type="application/pdf", max_bytes=10)
    r = await client.put(path_and_query(put.url), content=b"x", headers={"Content-Type": "text/html"})
    assert r.status_code == 415


async def test_upload_over_limit_is_rejected_and_not_stored(client: httpx.AsyncClient) -> None:
    put = storage().presign_put("k/big.pdf", content_type="application/pdf", max_bytes=5)
    r = await client.put(path_and_query(put.url), content=b"0123456789", headers=put.headers)
    assert r.status_code == 413
    assert storage().head("k/big.pdf") is None
    assert not any(p.name.endswith(".part") for p in storage().root.rglob("*"))


async def test_download_rejects_tampered_key(client: httpx.AsyncClient) -> None:
    storage().write_bytes("u/alice/secret.txt", b"alice")
    storage().write_bytes("u/bob/secret.txt", b"bob")
    get = storage().presign_get("u/bob/secret.txt")
    alice_url = get.url.replace("u/bob/", "u/alice/")
    r = await client.get(path_and_query(alice_url))
    assert r.status_code == 403


async def test_download_link_expires(client: httpx.AsyncClient) -> None:
    storage().write_bytes("k/x.txt", b"x")
    get = storage().presign_get("k/x.txt", ttl=-1)
    r = await client.get(path_and_query(get.url))
    assert r.status_code == 403


@pytest.mark.parametrize("key", ["../etc/passwd", "a/../../b", "/abs", "a//b", "a/", "", "a/\x00b", "a b"])
def test_invalid_keys(key: str) -> None:
    with pytest.raises(InvalidKey):
        storage().path_for(key)


def test_delete_prefix_removes_only_that_prefix() -> None:
    s = storage()
    s.write_bytes("u/9/p/1/a.txt", b"1")
    s.write_bytes("u/9/p/2/b.txt", b"2")
    s.delete_prefix("u/9/p/1/")
    assert s.head("u/9/p/1/a.txt") is None
    assert s.head("u/9/p/2/b.txt") is not None


def test_signature_checks_expiry() -> None:
    s = storage()
    exp = int(time.time()) - 1
    assert not s.check_signature("get", "k", exp, s.signature("get", "k", exp))
