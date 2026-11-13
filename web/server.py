"""aiohttp application factory for Chronos Web.

The app is handed the bot's own `Database`, a `Bridge` (Discord access) and an
`EventHub` (live notifications). It never opens a database of its own.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any

from aiohttp import web

import config

from . import auth
from .common import ApiError, Routes, current_user, fail, ok, resolve_ctx, wire
from .events import EventHub

log = logging.getLogger("web.server")

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
ASSET_DIRS = ("icons", "discord_emojis")

# Each module exposes `routes = Routes()`. A missing module is skipped so the
# site still boots while pieces are being added.
API_MODULES = [
    "api_session", "api_stats", "api_economy", "api_pets", "api_progress",
    "api_notes", "api_trivia", "api_halloween", "api_admin",
]

CSP = (
    "default-src 'self'; img-src 'self' data: https://cdn.discordapp.com https://media.discordapp.net https://raw.githubusercontent.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@web.middleware
async def security_headers(request: web.Request, handler):
    try:
        resp = await handler(request)
    except web.HTTPNotFound:
        if request.path.startswith("/api/"):
            resp = web.json_response({"error": "Not found.", "code": "not_found"}, status=404)
        else:
            raise
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Content-Security-Policy", CSP)
    return resp


def _cookie_kwargs() -> dict[str, Any]:
    return {"max_age": auth.SESSION_TTL, "httponly": True, "samesite": "Lax", "path": "/",
            "secure": config.WEB_BASE_URL.startswith("https://") and not config.WEB_DEV_MODE}


def _login(resp: web.StreamResponse, uid: int, gid: int | None = None) -> None:
    resp.set_cookie(auth.COOKIE, auth.make_session_cookie(uid, gid), **_cookie_kwargs())


# ---------------------------------------------------------------------- #
# Auth routes
# ---------------------------------------------------------------------- #
async def magic(request: web.Request):
    got = auth.consume_magic(request.query.get("t", ""))
    if not got:
        raise web.HTTPFound("/?login=expired")
    uid, gid = got
    resp = web.HTTPFound("/")
    _login(resp, uid, gid)
    raise resp


async def oauth_login(request: web.Request):
    if not (auth.oauth_enabled() and config.DISCORD_CLIENT_ID):
        raise web.HTTPFound("/?login=help")
    state = secrets.token_urlsafe(16)
    resp = web.HTTPFound(auth.oauth_url(config.DISCORD_CLIENT_ID, state))
    resp.set_cookie("chronos_oauth", state, max_age=600, httponly=True, samesite="Lax", path="/")
    raise resp


async def oauth_callback(request: web.Request):
    state, code = request.query.get("state"), request.query.get("code")
    if not code or not state or state != request.cookies.get("chronos_oauth"):
        raise web.HTTPFound("/?login=failed")
    uid = await auth.oauth_exchange(config.DISCORD_CLIENT_ID, code)
    if not uid:
        raise web.HTTPFound("/?login=failed")
    if not await request.app["bridge"].guilds_for(uid):
        raise web.HTTPFound("/?login=noguild")
    resp = web.HTTPFound("/")
    _login(resp, uid)
    resp.del_cookie("chronos_oauth", path="/")
    raise resp


async def dev_login(request: web.Request):
    if not config.WEB_DEV_MODE:
        raise web.HTTPNotFound()
    uid = int(request.query.get("user", "0") or 0)
    gid = int(request.query["guild"]) if request.query.get("guild", "").isdigit() else None
    if not uid:
        raise web.HTTPBadRequest(text="user=<id> required")
    resp = web.HTTPFound(request.query.get("next", "/"))
    _login(resp, uid, gid)
    raise resp


async def logout(request: web.Request):
    if request.headers.get("X-Requested-With") != "chronos":
        return web.json_response({"error": "Missing request header.", "code": "csrf"}, status=403)
    resp = web.json_response({"ok": True})
    resp.del_cookie(auth.COOKIE, path="/")
    return resp


# ---------------------------------------------------------------------- #
# Identity + realtime
# ---------------------------------------------------------------------- #
async def me(request: web.Request):
    base = {
        "oauth": bool(auth.oauth_enabled() and config.DISCORD_CLIENT_ID),
        "live": request.app["bridge"].live,
        "dev_mode": config.WEB_DEV_MODE,
        "prefix": config.PREFIX,
        "now": int(time.time()),
    }
    if current_user(request) is None:
        return ok({"authed": False, **base})
    try:
        c = await resolve_ctx(request, True)
    except ApiError as e:
        if e.code == "no_guild":
            uid = current_user(request)
            m = request.app["bridge"].member(0, uid)
            return ok({"authed": True, "guild": None, "guilds": [], "no_guild": True,
                       "user": {"id": uid, "name": m["name"], "avatar": m["avatar"]}, **base})
        raise
    stats = await c.db.get_or_create_user_stats(c.uid, c.gid)
    from .common import level_block
    return ok({
        "authed": True,
        "user": {**c.person(c.uid), "is_manager": c.bridge.is_manager(c.gid, c.uid),
                 "is_dev": c.bridge.is_dev(c.uid)},
        "guild": str(c.gid), "guilds": c.guilds, "level": await level_block(c, stats["xp"]),
        **base,
    })


async def set_guild(request: web.Request):
    if request.headers.get("X-Requested-With") != "chronos":
        return web.json_response({"error": "Missing request header.", "code": "csrf"}, status=403)
    uid = current_user(request)
    if uid is None:
        return web.json_response({"error": "Sign in to continue.", "code": "unauthorized"}, status=401)
    body = await request.json()
    gid = str(body.get("id", ""))
    ids = [g["id"] for g in await request.app["bridge"].guilds_for(uid)]
    if gid not in ids:
        return web.json_response({"error": "You're not in that server.", "code": "no_guild"}, status=403)
    resp = web.json_response({"ok": True, "guild": gid})
    _login(resp, uid, int(gid))
    return resp


async def events(request: web.Request):
    uid = current_user(request)
    if uid is None:
        return web.json_response({"error": "Sign in to continue.", "code": "unauthorized"}, status=401)
    hub: EventHub = request.app["hub"]
    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream", "Cache-Control": "no-store",
        "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })
    await resp.prepare(request)
    q = hub.subscribe(uid)

    async def send(ev: dict) -> None:
        await resp.write(f"id: {ev['id']}\ndata: {json.dumps(wire(ev), ensure_ascii=False)}\n\n".encode())

    try:
        await resp.write(b"retry: 3000\n\n")
        last = request.headers.get("Last-Event-ID") or request.query.get("last") or "0"
        if last.isdigit():
            for ev in hub.since(uid, int(last)):
                await send(ev)
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=20)
                await send(ev)
            except asyncio.TimeoutError:
                await resp.write(b": ping\n\n")
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        hub.unsubscribe(uid, q)
    return resp


async def notifications(request: web.Request):
    uid = current_user(request)
    if uid is None:
        return web.json_response({"error": "Sign in to continue.", "code": "unauthorized"}, status=401)
    last = request.query.get("since", "0")
    items = request.app["hub"].since(uid, int(last) if last.isdigit() else 0)
    return ok({"events": items})


async def health(request: web.Request):
    return web.json_response({"ok": True, "live": request.app["bridge"].live, "t": int(time.time())})


# ---------------------------------------------------------------------- #
# Static / SPA
# ---------------------------------------------------------------------- #
async def index(request: web.Request):
    f = STATIC / "index.html"
    if not f.exists():
        return web.Response(text="Chronos Web is starting up.", status=503)
    return web.FileResponse(f, headers={"Cache-Control": "no-cache"})


def build_app(db, bridge, hub: EventHub | None = None) -> web.Application:
    app = web.Application(middlewares=[security_headers], client_max_size=2 * 1024 * 1024)
    app["db"], app["bridge"], app["hub"] = db, bridge, hub or EventHub()
    app["locks"] = {}

    app.router.add_get("/auth/magic", magic)
    app.router.add_get("/auth/login", oauth_login)
    app.router.add_get("/auth/callback", oauth_callback)
    app.router.add_get("/auth/dev", dev_login)
    app.router.add_post("/auth/logout", logout)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/me", me)
    app.router.add_post("/api/guild", set_guild)
    app.router.add_get("/api/events", events)
    app.router.add_get("/api/notifications", notifications)

    for name in API_MODULES:
        try:
            mod = importlib.import_module(f"web.{name}")
        except ModuleNotFoundError as e:
            if e.name == f"web.{name}":
                log.debug("web module %s not present, skipping", name)
                continue
            log.exception("web module %s failed to import", name)
            continue
        except Exception:
            log.exception("web module %s failed to import", name)
            continue
        mod.routes.install(app)

    if STATIC.exists():
        app.router.add_static("/static", STATIC, follow_symlinks=False)
    for d in ASSET_DIRS:
        p = ROOT / "assets" / d
        if p.exists():
            app.router.add_static(f"/assets/{d}", p, follow_symlinks=False)

    app.router.add_get("/", index)

    async def spa(request: web.Request):
        if request.path.startswith(("/api/", "/auth/", "/assets/", "/static/")):
            raise web.HTTPNotFound()
        return await index(request)
    app.router.add_get("/{tail:.*}", spa)
    return app


async def start(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner
