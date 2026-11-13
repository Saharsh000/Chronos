"""Run Chronos Web WITHOUT Discord, against a database file - for local dev/tests.

    WEB_DEV_MODE=1 python -m web.standalone --db /path/copy.sqlite3 --port 8099

Never point this at the live bot database while the bot is running.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

import config
from database import Database

from .bridge import OfflineBridge
from .events import EventHub
from .server import build_app, start


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = Database(a.db)
    await db.connect()
    app = build_app(db, OfflineBridge(db), EventHub())
    await start(app, a.host, a.port)
    logging.info("Chronos Web (offline bridge) on http://%s:%s  dev=%s", a.host, a.port, config.WEB_DEV_MODE)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
