"""Standalone entrypoint for running Chronoweb without starting the Discord bot."""
import asyncio
import logging

import config
from database import Database
from utils.logger import setup_logging
from web.server import start_web_server

log = logging.getLogger("web")


async def main() -> None:
    setup_logging()
    db = Database(config.DB_PATH)
    await db.connect()
    
    runner, site = await start_web_server(db=db)
    print(f"🚀 Chronoweb running at http://localhost:{config.PORT}")
    print(f"🌐 Public domain: {config.WEB_BASE_URL}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Shutting down Chronoweb...")
        await runner.cleanup()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
