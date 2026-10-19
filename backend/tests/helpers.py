"""Shared helpers for API tests."""

from typing import Any
from urllib.parse import urlparse

import httpx

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


def local_path(url: str) -> str:
    u = urlparse(url)
    return f"{u.path}?{u.query}"


async def create_project(client: httpx.AsyncClient, headers: dict[str, str], name: str = "My docs") -> dict[str, Any]:
    r = await client.post("/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    filename: str,
    data: bytes,
    *,
    declared_size: int | None = None,
) -> httpx.Response:
    """Full upload flow: register, PUT to the signed URL, complete. Returns the complete response."""
    r = await client.post(
        f"/projects/{project_id}/documents",
        json={"filename": filename, "size_bytes": declared_size or len(data)},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    put = await client.put(local_path(body["upload"]["url"]), content=data, headers=body["upload"]["headers"])
    assert put.status_code in (204, 413), put.text
    return await client.post(f"/projects/{project_id}/documents/{body['document']['id']}/complete", headers=headers)
