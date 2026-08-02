from __future__ import annotations

import re
from pathlib import PurePath
from typing import Iterable, Optional

from fastapi import HTTPException, UploadFile, status

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


def safe_filename(filename: Optional[str], *, fallback: str) -> str:
    candidate = (filename or fallback).replace("\\", "/")
    if "/" in candidate or "\x00" in candidate or not _SAFE_FILENAME.fullmatch(candidate):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid filename"
        )
    if PurePath(candidate).name != candidate or candidate in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid filename"
        )
    return candidate


async def read_limited_upload(
    file: UploadFile,
    *,
    maximum_bytes: int,
    fallback_filename: str,
    allowed_suffixes: Iterable[str],
    require_nonempty: bool = True,
) -> tuple[str, bytes]:
    filename = safe_filename(file.filename, fallback=fallback_filename)
    suffix = PurePath(filename.lower()).suffix
    allowed = {item.lower() for item in allowed_suffixes}
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"unsupported upload type; allowed extensions: {', '.join(sorted(allowed))}",
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > maximum_bytes:
            raise HTTPException(status_code=413, detail="upload exceeds configured size limit")
        chunks.append(chunk)
    payload = b"".join(chunks)
    if require_nonempty and not payload:
        raise HTTPException(status_code=422, detail="upload is empty")
    return filename, payload
