"""Multi-step setups shared by tests (run inside `fake_groq()`)."""

import httpx
from fake_llm import FakeProvider
from fixtures import LOREM
from helpers import create_project, upload

STYLE = {
    "description": "A friendly support agent. Short sentences, end by offering more help.",
    "tone": "friendly",
    "length": "short",
    "format": "plain",
    "language": "en",
    "examples": [
        {"input": "How do I reset it?", "output": "Hold the button for 5 seconds. Anything else?"},
        {"input": "Does it work offline?", "output": "Yes, the buttons still work offline. Anything else?"},
    ],
}


def long_markdown(sections: int = 10) -> bytes:
    body = "\n\n".join(f"## Topic {i}\n\n" + (f"Section {i} fact. " + LOREM) * 12 for i in range(sections))
    return f"# Manual\n\n{body}\n".encode()


async def approved_project(client: httpx.AsyncClient, headers: dict[str, str], fake: FakeProvider) -> str:
    """Project with an approved dataset (status in_review, dataset_version set)."""
    pid = str((await create_project(client, headers))["id"])
    await upload(client, headers, pid, "manual.md", long_markdown())
    await client.post(f"/projects/{pid}/process", headers=headers)
    await client.patch(f"/projects/{pid}", json={"target_pairs": 50}, headers=headers)
    await client.put("/keys/groq", json={"api_key": "gsk_test_1234567890"}, headers=headers)
    await client.put(f"/projects/{pid}/style", json=STYLE, headers=headers)
    await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2}, headers=headers)
    await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=headers)
    r = await client.post(f"/projects/{pid}/dataset/approve", headers=headers)
    assert r.status_code == 200, r.text
    return pid


async def ready_project(client: httpx.AsyncClient, headers: dict[str, str], fake: FakeProvider) -> tuple[str, str]:
    """A project trained end to end through the notebook API (status ready). Returns (project_id, job_id)."""
    import hashlib
    import io
    import json
    import zipfile

    from helpers import local_path

    pid = await approved_project(client, headers, fake)
    r = await client.post(f"/projects/{pid}/training", json={"base_model_id": "unsloth/Qwen3.5-4B"}, headers=headers)
    body = r.json()
    job_id, nb = body["job"]["id"], {"Authorization": f"Bearer {body['token']}"}
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb)
    await client.post("/jobs/current/training-complete", json={"final_step": 10}, headers=nb)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("adapter_config.json", json.dumps({"base_model_name_or_path": "unsloth/Qwen3.5-4B"}))
        z.writestr("adapter_model.safetensors", b"\x00" * 64)
    data = buf.getvalue()
    up = (
        await client.post(
            "/jobs/current/artifacts/upload-url",
            json={"kind": "adapter_safetensors", "size_bytes": len(data)},
            headers=nb,
        )
    ).json()
    await client.put(local_path(up["url"]), content=data, headers=up["headers"])
    await client.post(
        "/jobs/current/artifacts/complete",
        json={"kind": "adapter_safetensors", "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)},
        headers=nb,
    )
    r = await client.post("/jobs/current/finish", json={}, headers=nb)
    assert r.status_code == 200, r.text
    return pid, job_id
