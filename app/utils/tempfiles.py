"""Temporary file helpers for endpoints that must hand data to a C library.

pysam and parts of Biopython need a real path on disk. These helpers stream an
upload to a temporary file in bounded chunks — never ``await file.read()`` on a
whole upload — and guarantee cleanup even when the handler raises.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from fastapi import UploadFile

from app.core.errors import PayloadTooLargeError

CHUNK_SIZE = 1024 * 1024


def remove_quietly(path: str | os.PathLike[str]) -> None:
    """Delete a path, ignoring the case where it is already gone."""
    with suppress(FileNotFoundError, OSError):
        Path(path).unlink()


async def spool_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    """Stream ``upload`` to ``destination``, enforcing ``max_bytes``.

    Returns the number of bytes written. The size is checked while copying, so
    a client that omits ``Content-Length`` still cannot exhaust the disk.
    """
    written = 0
    await upload.seek(0)
    with destination.open("wb") as sink:
        while chunk := await upload.read(CHUNK_SIZE):
            written += len(chunk)
            if written > max_bytes:
                sink.close()
                remove_quietly(destination)
                raise PayloadTooLargeError(
                    f"'{upload.filename or 'upload'}' exceeds the "
                    f"{max_bytes // (1024 * 1024)} MB limit.",
                    details={"limit_bytes": max_bytes},
                )
            sink.write(chunk)
    await upload.seek(0)
    return written


@contextmanager
def temporary_path(suffix: str = "") -> Iterator[Path]:
    """Yield a path to a fresh temporary file and remove it on exit."""
    handle, raw_path = tempfile.mkstemp(suffix=suffix)
    os.close(handle)
    path = Path(raw_path)
    try:
        yield path
    finally:
        remove_quietly(path)


@contextmanager
def temporary_paths(*suffixes: str) -> Iterator[tuple[Path, ...]]:
    """Yield several temporary paths at once, cleaning all of them up."""
    paths: list[Path] = []
    try:
        for suffix in suffixes:
            handle, raw_path = tempfile.mkstemp(suffix=suffix)
            os.close(handle)
            paths.append(Path(raw_path))
        yield tuple(paths)
    finally:
        for path in paths:
            remove_quietly(path)
