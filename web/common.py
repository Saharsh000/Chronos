"""Shared plumbing for every API route: auth, guild resolution, JSON, errors,
per-user locking, and the "after you did something" hooks (achievements, Top-3
perk) that the bot runs after commands."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web

import config
from utils import embeds, streaks
from utils.subjects import SUBJECT_INFO
from utils.xp import tier_for_level, xp_progress

from . import auth
from . import mirror

log = logging.getLogger("web")

MAX_SAFE = 2 ** 53


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "error", **extra: Any) -> None:
        super().__init__(message)
        self.status, self.message, self.code, self.extra = status, message, code, extra


def wire(obj: Any) -> Any:
    """JSON-safe copy: 64-bit Discord ids become strings (JS would corrupt them)."""
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, int):
        return str(obj) if abs(obj) >= MAX_SAFE else obj
    if isinstance(obj, dict):
        return {str(k): wire(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [wire(v) for v in obj]
    return obj


def ok(data: Any = None, **extra: Any) -> web.Response:
    body = data if isinstance(data, dict) else {"data": data}
    body = {**body, **extra}
    return web.Response(
        text=json.dumps(wire(body), ensure_ascii=False, separators=(",", ":")),
        content_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@dataclass
class Ctx:
    request: web.Request
    uid: int
    gid: int
    guilds: list[dict[str, Any]] = field(default_factory=list)

    # --- app services ---------------------------------------------------
    @property
    def app(self) -> web.Application:
        return self.request.app

    @property
    def db(self):
        return self.app["db"]

    @property
    def bridge(self):
        return self.app["bridge"]

    @property
    def hub(self):
        return self.app["hub"]

    @property
    def me(self) -> dict[str, Any]:
        return self.bridge.member(self.gid, self.uid)

    def name_of(self, uid: int) -> str:
        return self.bridge.member(self.gid, uid)["name"]

    def person(self, uid: int) -> dict[str, Any]:
        m = self.bridge.member(self.gid, uid)
        return {"id": uid, "name": m["name"], "avatar": m["avatar"]}

    def emit(self, kind: str, **data: Any) -> None:
        self.hub.publish(self.uid, self.gid, kind, data)

    async def tiers(self) -> list[tuple[int, str]]:
        return await self.db.get_effective_tiers(self.gid)

    async def tier_name(self, level: int) -> str:
        return tier_for_level(level, await self.tiers())

    async def mirror(self, **kw: Any):
        return await self.bridge.post(self.gid, **kw)

    # --- request helpers ------------------------------------------------
    async def body(self) -> dict[str, Any]:
        try:
            data = await self.request.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def q(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.request.query.get(key, default)

    # --- the bot's "after a command" behaviour --------------------------
    async def after(self, *, announce: bool = True) -> list:
        """Everything the bot does after a command: unlock achievements (and
        announce them), and hand out the Top-3 Daily Dawn perk on the first
        action of the day (bot.py's on_command_completion)."""
        newly = []
        try:
            newly = await self.db.check_achievements(self.uid, self.gid)
        except Exception:
            log.exception("achievement check failed")
        if newly:
            self.emit("achievement", items=[
                {"id": a.id, "name": a.name, "emoji": a.emoji, "description": a.description,
                 "reward_coins": a.reward_coins} for a in newly
            ])
            if announce:
                await self.mirror(embed=mirror.achievements_embed(self.me, newly), content=None)
        try:
            await self.top3_perk()
        except Exception:
            log.exception("top3 perk failed")
        return newly

    async def top3_perk(self) -> Optional[dict]:
        now = int(time.time())
        today = streaks.date_str(now)
        if await self.db.get_top3_daily_claim(self.uid, self.gid, today):
            return None
        top3 = await self.db.get_top3_members(self.gid)
        rank = next((i + 1 for i, (u, _) in enumerate(top3) if u == self.uid), None)
        if not rank:
            return None
        perk = await self.db.claim_top3_daily_perk(self.uid, self.gid, rank, today, now=now)
        if not perk:
            return None
        self.emit("top3_perk", **perk)
        await self.mirror(embed=mirror.top3_embed(self.me, self.uid, perk, rank))
        return perk


# ---------------------------------------------------------------------- #
# Route decorator
# ---------------------------------------------------------------------- #
Handler = Callable[[Ctx], Awaitable[Any]]


def current_user(request: web.Request) -> Optional[int]:
    tok = request.cookies.get(auth.COOKIE)
    data = auth.unsign(tok) if tok else None
    return int(data["u"]) if data else None


async def resolve_ctx(request: web.Request, need_guild: bool = True) -> Ctx:
    uid = current_user(request)
    if uid is None:
        raise ApiError(401, "Sign in to continue.", "unauthorized")
    bridge = request.app["bridge"]
    guilds = await bridge.guilds_for(uid)
    gid = 0
    if need_guild:
        wanted = request.headers.get("X-Guild") or request.query.get("guild")
        if not wanted:
            tok = auth.unsign(request.cookies.get(auth.COOKIE, "")) or {}
            wanted = tok.get("g")
        ids = [int(g["id"]) for g in guilds]
        if wanted and wanted.isdigit() and int(wanted) in ids:
            gid = int(wanted)
        elif ids:
            gid = ids[0]
        else:
            raise ApiError(403, "You aren't in any server that uses Chronos.", "no_guild")
    return Ctx(request, uid, gid, guilds)


def api(handler: Handler, *, need_guild: bool = True, lock: Optional[bool] = None):
    """Wrap `handler(ctx)` into an aiohttp handler. Mutating verbs run under a
    per-(user, guild) lock so two tabs (or web + Discord) can't race a wallet."""
    async def wrapped(request: web.Request) -> web.Response:
        try:
            mutating = request.method in ("POST", "PUT", "PATCH", "DELETE")
            if mutating and request.headers.get("X-Requested-With") != "chronos":
                raise ApiError(403, "Missing request header.", "csrf")
            c = await resolve_ctx(request, need_guild)
            use_lock = mutating if lock is None else lock
            if use_lock:
                async with request.app["locks"].setdefault((c.uid, c.gid), asyncio.Lock()):
                    result = await handler(c)
            else:
                result = await handler(c)
            if isinstance(result, web.StreamResponse):
                return result
            return ok(result)
        except ApiError as e:
            return web.Response(
                text=json.dumps(wire({"error": e.message, "code": e.code, **e.extra}), ensure_ascii=False),
                status=e.status, content_type="application/json",
            )
        except web.HTTPException:
            raise
        except Exception:
            log.exception("Unhandled error in %s %s", request.method, request.path)
            return web.Response(
                text=json.dumps({"error": "Something went wrong on our side. Try again.", "code": "server"}),
                status=500, content_type="application/json",
            )
    return wrapped


class Routes:
    """Collects `@routes.get("/api/x")` style declarations."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, Callable, dict]] = []

    def _add(self, method: str, path: str, **opts):
        def deco(fn: Handler):
            self.items.append((method, path, fn, opts))
            return fn
        return deco

    def get(self, path: str, **o): return self._add("GET", path, **o)
    def post(self, path: str, **o): return self._add("POST", path, **o)
    def patch(self, path: str, **o): return self._add("PATCH", path, **o)
    def delete(self, path: str, **o): return self._add("DELETE", path, **o)

    def install(self, app: web.Application) -> None:
        for method, path, fn, opts in self.items:
            app.router.add_route(method, path, api(fn, **opts))


# ---------------------------------------------------------------------- #
# Small shared helpers
# ---------------------------------------------------------------------- #
def fail(message: str, status: int = 400, code: str = "bad_request", **extra: Any) -> ApiError:
    return ApiError(status, message, code, **extra)


async def level_block(c: Ctx, xp: int) -> dict[str, Any]:
    into, needed, level = xp_progress(xp)
    tier = await c.tier_name(level)
    return {"level": level, "into": into, "needed": needed, "xp": xp, "tier": tier,
            "tier_key": tier_key(tier)}


def tier_key(tier: str) -> str:
    clean = "".join(ch for ch in tier if ch.isalnum() or ch.isspace()).replace("Tier", "").strip()
    return clean.lower().replace(" ", "")


def subject_card(key: Optional[str]) -> Optional[dict[str, str]]:
    if not key or key not in SUBJECT_INFO:
        return None
    i = SUBJECT_INFO[key]
    return {"key": key, "label": i["label"], "emoji": i["emoji"]}


def period_start(period: str) -> Optional[int]:
    """Start of today / this week (Mon) / this month, all in IST - same as cogs/stats.py."""
    import datetime as dt
    now = dt.datetime.now(config.IST)
    if period == "today":
        s = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        s = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        s = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return None
    return int(s.timestamp())


async def period_totals(db, guild_id: int, period: str, subject: Optional[str] = None) -> dict[int, int]:
    """{user_id: seconds}, live sessions included - mirrors Stats._totals."""
    if period == "alltime":
        if subject:
            return await db.get_subject_totals(guild_id, subject)
        return await db.get_alltime_totals(guild_id)
    since = period_start(period)
    totals = await db.sum_seconds(guild_id, since, subject)
    now = int(time.time())
    for s in await db.get_all_active_sessions():
        if s["guild_id"] != guild_id:
            continue
        if subject is not None and s.get("subject") != subject:
            continue
        start = max(s["start_time"], since) if since is not None else s["start_time"]
        live = max(0, now - start)
        if live:
            totals[s["user_id"]] = totals.get(s["user_id"], 0) + live
    return totals
