"""Miscellaneous helper utilities (placeholder)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def chunked(iterable: Iterable[T], size: int) -> list[list[T]]:
    """Simple chunking helper used in later phases for batching LLM calls."""
    chunk: list[T] = []
    output: list[list[T]] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            output.append(chunk)
            chunk = []
    if chunk:
        output.append(chunk)
    return output


def compute_file_sha256(path: str | Path, *, chunk_size: int = 65536) -> str:
    """Return the SHA256 hex digest for a file without loading it entirely into memory."""

    digest = hashlib.sha256()
    with Path(path).expanduser().open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()
