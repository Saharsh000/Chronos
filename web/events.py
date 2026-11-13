"""Tiny in-process pub/sub that carries live notifications to browsers.

Everything that happens to a user - from the bot *or* the website - is
published here as `(user_id, guild_id, kind, data)`. Open tabs receive it over
Server-Sent Events; tabs that were closed catch up from a short per-user
history via `Last-Event-ID` / `/api/notifications`.
"""
from __future__ import annotations

import asyncio
import collections
import itertools
import time
from typing import Any

_HISTORY = 60


class EventHub:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._subs: dict[int, set[asyncio.Queue]] = collections.defaultdict(set)
        self._history: dict[int, collections.deque] = collections.defaultdict(
            lambda: collections.deque(maxlen=_HISTORY)
        )

    def publish(self, user_id: int, guild_id: int, kind: str, data: dict[str, Any] | None = None) -> dict:
        event = {
            "id": next(self._ids),
            "t": int(time.time()),
            "guild_id": str(guild_id),  # ids are strings on the wire - JS can't hold 64-bit ints
            "kind": kind,
            "data": data or {},
        }
        self._history[user_id].append(event)
        for q in list(self._subs.get(user_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs[user_id].add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        self._subs[user_id].discard(q)
        if not self._subs[user_id]:
            self._subs.pop(user_id, None)

    def since(self, user_id: int, last_id: int, guild_id: int | None = None) -> list[dict]:
        return [
            e for e in self._history.get(user_id, ())
            if e["id"] > last_id and (guild_id is None or e["guild_id"] == str(guild_id))
        ]

    def online_users(self) -> set[int]:
        return set(self._subs.keys())
