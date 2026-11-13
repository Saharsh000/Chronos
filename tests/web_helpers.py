"""Shared harness for Chronos Web API tests: throwaway DB + OfflineBridge + aiohttp test client."""
from __future__ import annotations

import os
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

from database import Database
from web import auth
from web.bridge import OfflineBridge
from web.events import EventHub
from web.server import build_app

GID = 5550001
UID = 1000000000000000001      # > 2**53 on purpose: ids must survive JSON as strings
OTHER = 1000000000000000002


class WebCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._dir.name, "t.sqlite3"))
        await self.db.connect()
        self.bridge = OfflineBridge(self.db)
        self.hub = EventHub()
        self.app = build_app(self.db, self.bridge, self.hub)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        for u in (UID, OTHER):
            await self.db.get_or_create_user_stats(u, GID)
            await self.db.get_or_create_currency(u, GID)

    async def asyncTearDown(self) -> None:
        await self.client.close()
        await self.db.close()
        self._dir.cleanup()

    def headers(self, uid: int = UID, mutating: bool = False) -> dict:
        h = {"Cookie": f"{auth.COOKIE}={auth.make_session_cookie(uid, GID)}"}
        if mutating:
            h["X-Requested-With"] = "chronos"
        return h

    async def get(self, path: str, uid: int = UID):
        r = await self.client.get(path, headers=self.headers(uid))
        return r.status, await r.json() if r.content_type == "application/json" else await r.read()

    async def post(self, path: str, body: dict | None = None, uid: int = UID):
        r = await self.client.post(path, json=body or {}, headers=self.headers(uid, True))
        return r.status, await r.json()
