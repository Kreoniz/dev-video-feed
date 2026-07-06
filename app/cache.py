from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheEntry[T]:
    value: T
    expires_at: float


class TTLCache:
    """Small async-safe in-memory TTL cache for endpoint responses."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = max(0, ttl_seconds)
        self._entries: dict[str, CacheEntry[object]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> object | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None

            if entry.expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None

            return entry.value

    async def set(self, key: str, value: object) -> None:
        if self._ttl_seconds <= 0:
            return

        async with self._lock:
            self._entries[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + self._ttl_seconds,
            )

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()
