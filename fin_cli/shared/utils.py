"""Miscellaneous helper utilities (placeholder)."""

from __future__ import annotations

from collections.abc import Iterable
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
