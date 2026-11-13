"""HTTP Server for Chronoweb, integrating aiohttp, discord.py, and aiosqlite."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

import config
from database import Database
from web import api, auth

log = logging.getLogger("web.server")
BASE_DIR = Path(__file__).resolve().parent


def build_app(bot: Optional[Any] = None, db: Optional[Database] = None) -> web.Application:
    """Build and configure the aiohttp Web Application."""
    app = web.Application(middlewares=[auth.auth_middleware])
    
    app["bot"] = bot
    app["db"] = db

    # Auth routes
    app.router.add_get("/api/auth/me", auth.handle_get_me)
    app.router.add_get("/api/auth/discord/login", auth.handle_discord_login)
    app.router.add_get("/api/auth/discord/callback", auth.handle_discord_callback)
    app.router.add_post("/api/auth/dev-login", auth.handle_dev_login)
    app.router.add_post("/api/auth/select-guild", auth.handle_select_guild)
    app.router.add_post("/api/auth/logout", auth.handle_logout)

    # Study Sessions & Pomodoro
    app.router.add_get("/api/sessions/active", api.api_get_active_session)
    app.router.add_post("/api/sessions/start", api.api_start_session)
    app.router.add_post("/api/sessions/stop", api.api_stop_session)
    app.router.add_post("/api/sessions/heartbeat", api.api_session_heartbeat)
    app.router.add_get("/api/sessions/server-active", api.api_server_active)
    app.router.add_get("/api/pomodoro/status", api.api_pomodoro_status)

    # Stats & Profile
    app.router.add_get("/api/stats", api.api_get_stats)
    app.router.add_get("/api/stats/compare", api.api_compare_stats)

    # Leaderboards & Hall of Fame
    app.router.add_get("/api/leaderboard", api.api_get_leaderboard)
    app.router.add_get("/api/leaderboard/hall-of-fame", api.api_hall_of_fame)

    # JEE Syllabus
    app.router.add_get("/api/syllabus", api.api_get_syllabus)
    app.router.add_post("/api/syllabus/chapter/toggle", api.api_toggle_chapter)
    app.router.add_post("/api/syllabus/subtopic/toggle", api.api_toggle_subtopic)
    app.router.add_post("/api/syllabus/revision", api.api_log_revision_pyq)

    # Pets & Companions
    app.router.add_get("/api/pets", api.api_get_pets)
    app.router.add_get("/api/pets/catalog", api.api_get_pet_catalog)
    app.router.add_post("/api/pets/buy", api.api_buy_pet)
    app.router.add_post("/api/pets/equip", api.api_equip_pet)
    app.router.add_post("/api/pets/rename", api.api_rename_pet)
    app.router.add_post("/api/pets/feed", api.api_feed_pet)
    app.router.add_get("/api/pets/food-catalog", api.api_get_food_catalog)
    app.router.add_post("/api/pets/food-buy", api.api_buy_food)

    # Economy & Shop
    app.router.add_get("/api/economy/overview", api.api_get_economy)
    app.router.add_get("/api/economy/shop", api.api_get_shop)
    app.router.add_post("/api/economy/buy", api.api_buy_shop_item)
    app.router.add_post("/api/economy/use", api.api_use_item)
    app.router.add_post("/api/economy/set-title", api.api_set_title)
    app.router.add_post("/api/economy/daily", api.api_claim_daily)
    app.router.add_post("/api/economy/work", api.api_claim_work)
    app.router.add_post("/api/economy/beg", api.api_claim_beg)
    app.router.add_post("/api/economy/weekly", api.api_claim_weekly)

    # Halloween Hub
    app.router.add_get("/api/halloween/status", api.api_get_halloween)
    app.router.add_post("/api/halloween/open-box", api.api_open_hallo_box)
    app.router.add_post("/api/halloween/claim-pass", api.api_claim_pass_rewards)
    app.router.add_post("/api/halloween/candy-buy", api.api_buy_candy_item)

    # Chronotes
    app.router.add_get("/api/notes", api.api_get_notes)
    app.router.add_post("/api/notes", api.api_create_note)
    app.router.add_put("/api/notes/{id}", api.api_update_note)
    app.router.add_delete("/api/notes/{id}", api.api_delete_note)

    # JEE Trivia
    app.router.add_get("/api/trivia/question", api.api_get_trivia_question)
    app.router.add_post("/api/trivia/answer", api.api_submit_trivia_answer)
    app.router.add_get("/api/trivia/stats", api.api_get_trivia_stats)

    # Achievements
    app.router.add_get("/api/achievements", api.api_get_achievements)

    # Static files and Chronos assets
    static_dir = BASE_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.router.add_static("/static/", path=str(static_dir), name="static")

    assets_dir = BASE_DIR.parent / "assets"
    if assets_dir.exists():
        app.router.add_static("/assets/", path=str(assets_dir), name="assets")

    # Frontend Single Page App HTML handler
    async def index_handler(request: web.Request) -> web.Response:
        index_file = BASE_DIR / "templates" / "index.html"
        if not index_file.exists():
            return web.Response(text="Chronoweb loading...", content_type="text/html")
        return web.FileResponse(index_file)

    app.router.add_get("/", index_handler)

    # SPA catch-all for direct path reloads
    async def spa_fallback(request: web.Request) -> web.Response:
        if request.path.startswith("/api/") or request.path.startswith("/static/") or request.path.startswith("/assets/"):
            return web.Response(status=404, text="Not Found")
        index_file = BASE_DIR / "templates" / "index.html"
        return web.FileResponse(index_file)

    app.router.add_get("/{tail:.*}", spa_fallback)

    return app


async def start_web_server(
    bot: Optional[Any] = None,
    db: Optional[Database] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> tuple[web.AppRunner, web.TCPSite]:
    """Start web runner asynchronously on configured host/port."""
    host = host or config.WEB_HOST
    port = port or config.PORT
    
    app = build_app(bot=bot, db=db)
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    log.info(f"Chronoweb running on http://{host}:{port} (Domain: {config.WEB_BASE_URL})")
    return runner, site


if __name__ == "__main__":
    # Standalone server runner for testing
    from utils.logger import setup_logging
    setup_logging()
    
    async def _main():
        db = Database(config.DB_PATH)
        await db.connect()
        runner, site = await start_web_server(db=db)
        print(f"🚀 Chronoweb standalone started at http://localhost:{config.PORT}")
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("Stopping web server...")
            await runner.cleanup()
            await db.close()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
