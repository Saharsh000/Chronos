"""Entrypoint: launches the Discord bot and the Chronoweb server concurrently."""
from __future__ import annotations

import asyncio
import logging

import config
from bot import ChronosBot
from utils.logger import setup_logging
from web.server import start_web_server

log = logging.getLogger("main")


async def main() -> None:
    setup_logging()
    config.validate()
    
    bot = ChronosBot()
    # Ensure database is connected
    await bot.db.connect()
    
    # Start web server sharing the same bot instance and SQLite database
    runner, site = await start_web_server(bot=bot, db=bot.db)
    log.info(f"Chronoweb running on http://{config.WEB_HOST}:{config.PORT}")

    try:
        async with bot:
            await bot.start(config.TOKEN)
    finally:
        log.info("Shutting down Chronoweb...")
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Exiting on user interrupt.")
