import asyncio
import json
import uuid

from doctune.core import events
from doctune.routers.events import _stream


class FakeRequest:
    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


async def test_stream_sends_snapshot_then_published_events() -> None:
    pid = str(uuid.uuid4())
    request = FakeRequest()
    stream = _stream(request, pid, {"id": pid, "status": "draft"})  # type: ignore[arg-type]

    first = await anext(stream)
    assert first["event"] == "snapshot"
    assert json.loads(first["data"])["status"] == "draft"

    async def publish_soon() -> None:
        await asyncio.sleep(0.3)
        events.publish(pid, "status", {"status": "uploaded"})
        await asyncio.sleep(0.1)
        events.publish(pid, "deleted", {})

    task = asyncio.create_task(publish_soon())
    second = await asyncio.wait_for(anext(stream), timeout=5)
    assert second == {"event": "status", "data": json.dumps({"status": "uploaded"})}
    third = await asyncio.wait_for(anext(stream), timeout=5)
    assert third["event"] == "deleted"
    await task
    # the stream ends after `deleted`
    try:
        await asyncio.wait_for(anext(stream), timeout=2)
        raise AssertionError("stream should have ended")
    except StopAsyncIteration:
        pass
