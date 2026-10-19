import httpx


async def test_healthz(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-request-id"]


async def test_readyz_reports_db_and_redis(client: httpx.AsyncClient) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": True, "redis": True}


async def test_meta_exposes_limits(client: httpx.AsyncClient) -> None:
    r = await client.get("/meta")
    assert r.status_code == 200
    assert r.json()["limits"] == {"file_mb": 20, "project_mb": 50, "max_pairs": 2000}


async def test_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
