"""Signed upload/download endpoints for LocalStorage (stand-in for R2 pre-signed URLs)."""

import os
import uuid
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse

from doctune.core.errors import AppError, Forbidden, LimitExceeded, NotFound
from doctune.core.storage import InvalidKey, LocalStorage, get_storage

router = APIRouter(prefix="/storage", include_in_schema=False)


def local_storage() -> LocalStorage:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise NotFound()
    return storage


Store = Annotated[LocalStorage, Depends(local_storage)]


class UnsupportedContentType(AppError):
    status_code, code, message = 415, "unsupported_content_type", "Content-Type does not match the upload URL"


@router.put("/{key:path}", status_code=204)
async def put_object(
    key: str,
    request: Request,
    storage: Store,
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query()],
    ct: Annotated[str, Query()],
    max_bytes: Annotated[int, Query(alias="max")],
) -> Response:
    try:
        path = storage.path_for(key)
    except InvalidKey as exc:
        raise NotFound() from exc
    if not storage.check_signature("put", key, exp, sig, ct, max_bytes):
        raise Forbidden("Upload link is invalid or expired")
    if request.headers.get("content-type", "").split(";")[0].strip() != ct:
        raise UnsupportedContentType()

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
    written = 0
    try:
        async with await anyio.open_file(tmp, "wb") as f:
            async for chunk in request.stream():
                written += len(chunk)
                if written > max_bytes:
                    raise LimitExceeded("File is larger than allowed")
                await f.write(chunk)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return Response(status_code=204)


@router.get("/{key:path}")
async def get_object(
    key: str,
    storage: Store,
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query()],
    fn: Annotated[str | None, Query()] = None,
) -> FileResponse:
    try:
        path = storage.path_for(key)
    except InvalidKey as exc:
        raise NotFound() from exc
    if not storage.check_signature("get", key, exp, sig):
        raise Forbidden("Download link is invalid or expired")
    if not path.is_file():
        raise NotFound()
    return FileResponse(path, filename=fn, media_type="application/octet-stream")
