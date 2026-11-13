"""Server admin and developer tools on the web: the twin of cogs/admin.py
(.config, .setcheckin, .make), cogs/customization.py (.tiers, .tags, .settier,
.resettier, .resettiers, .addtag, .removetag) and the grant/diagnostic half of
cogs/dev.py (.addtime/.removetime, .addxp/.removexp, .addcoins/.removecoins,
.addcandy, .addbox, .addpasstime, .checkdb). Permissions are enforced here, on
the server, with the same rules the bot uses: Manage Server for config,
Administrator for rooms, the developer for everything that edits other people's
numbers or the shop. (.backupdb / .restoredb / .forceseed / .syncguild / the
announcement commands touch files and other servers, so they stay bot-only.)"""
from __future__ import annotations

import logging
from typing import Any, Optional

from utils import economy
from utils import halloween as halloween_catalog
from utils.subjects import SUBJECT_ALIASES, SUBJECT_HINT, SUBJECT_INFO, normalize_subject_key
from utils.time_format import format_duration, parse_duration
from utils.xp import TIERS, tier_for_level

from .common import Ctx, Routes, fail

log = logging.getLogger("web.admin")
routes = Routes()

MAX_AMOUNT = 10_000_000
MAX_NAME = 40
DIAG_TABLES = ["user_stats", "subject_stats", "sessions", "session_log", "user_currency", "user_inventory", "achievements_unlocked", "user_pets"]
ROOM_KEYS = ("physics", "chemistry", "maths")


def need_manager(c: Ctx) -> None:
    if not c.bridge.is_manager(c.gid, c.uid):
        raise fail("You need the Manage Server permission for that.", 403, "forbidden")


def need_dev(c: Ctx) -> None:
    if not c.bridge.is_dev(c.uid):
        raise fail("This is developer-only.", 403, "forbidden")


def whole(v: Any, *, lo: int = -MAX_AMOUNT, hi: int = MAX_AMOUNT, what: str = "amount") -> int:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise fail(f"The {what} must be a whole number.", 400, "bad_amount")
    if n < lo or n > hi:
        raise fail(f"The {what} must be between {lo:,} and {hi:,}.", 400, "bad_amount")
    return n


def target_of(c: Ctx, b: dict[str, Any]) -> int:
    raw = str(b.get("user") or "").strip()
    if not raw.isdigit() or not c.bridge.is_member(c.gid, int(raw)):
        raise fail("Pick a member of this server.", 404, "no_member")
    return int(raw)


# ---------------------------------------------------------------------- #
# Readable by everyone in the server: `.tiers`, `.tags`
# ---------------------------------------------------------------------- #
@routes.get("/api/tiers")
async def tiers(c: Ctx):
    over = await c.db.get_tier_overrides(c.gid)
    return {"tiers": [{"level": lvl, "default": name, "name": over.get(lvl, name), "renamed": lvl in over} for lvl, name in TIERS],
            "can_edit": c.bridge.is_dev(c.uid)}


@routes.get("/api/tags")
async def tags(c: Ctx):
    custom = await c.db.get_custom_tags(c.gid)
    return {"builtin": [{"title": it["title_text"], "price": it["price"]} for it in economy.SHOP_ITEMS.values() if it["type"] == "title"],
            "custom": [{"id": iid, "title": it["title_text"], "price": it["price"]} for iid, it in custom.items()],
            "can_edit": c.bridge.is_dev(c.uid)}


# ---------------------------------------------------------------------- #
# Server config (Manage Server / Administrator)
# ---------------------------------------------------------------------- #
@routes.get("/api/admin/config")
async def config_view(c: Ctx):
    """`.config`."""
    need_manager(c)
    cfg = await c.db.get_guild_config(c.gid)
    chans = c.bridge.channels(c.gid)
    names = {ch["id"]: ch["name"] for ch in chans["text"] + chans["voice"]}

    def chan(cid: Optional[int]):
        return {"id": str(cid), "name": names.get(str(cid))} if cid else None
    return {"checkin": chan(cfg.get("checkin_channel_id")),
            "rooms": [{"key": k, "label": SUBJECT_INFO[k]["label"], "channel": chan(cfg.get(f"{k}_channel_id"))} for k in ROOM_KEYS],
            "text_channels": chans["text"], "can_make_rooms": c.bridge.is_admin(c.gid, c.uid), "is_dev": c.bridge.is_dev(c.uid)}


@routes.post("/api/admin/checkin")
async def set_checkin(c: Ctx):
    """`.setcheckin #channel`."""
    need_manager(c)
    b = await c.body()
    cid = str(b.get("channel") or "").strip()
    if not cid.isdigit() or cid not in {ch["id"] for ch in c.bridge.channels(c.gid)["text"]}:
        raise fail("Pick one of this server's text channels.", 404, "bad_channel")
    await c.db.set_checkin_channel(c.gid, int(cid))
    log.info("SET CHECKIN  | %s set check-in channel to %s in guild %s via web", c.uid, cid, c.gid)
    return {"checkin": {"id": cid, "name": next(ch["name"] for ch in c.bridge.channels(c.gid)["text"] if ch["id"] == cid)}}


@routes.post("/api/admin/rooms")
async def make_rooms(c: Ctx):
    """`.make`: create (or verify) the Physics / Chemistry / Maths study voice rooms."""
    if not c.bridge.is_admin(c.gid, c.uid):
        raise fail("You need the Administrator permission to create study rooms.", 403, "forbidden")
    try:
        r = await c.bridge.create_study_rooms(c.gid, c.me["name"])
    except NotImplementedError:
        raise fail("Creating rooms needs the live bot connection, which this server isn't running right now.", 501, "needs_bot")
    except PermissionError:
        raise fail("I need the Manage Channels permission to create study rooms.", 403, "bot_forbidden")
    except LookupError:
        raise fail("I can't see that server right now.", 503, "guild_unavailable")
    return r


# ---------------------------------------------------------------------- #
# Developer: tiers and tags (cogs/customization.py)
# ---------------------------------------------------------------------- #
def clean_name(v: Any, what: str) -> str:
    s = " ".join(str(v or "").split())
    if not s:
        raise fail(f"Give the {what} a name.", 400, "empty")
    if len(s) > MAX_NAME:
        raise fail(f"The {what} can be {MAX_NAME} characters at most.", 400, "too_long")
    return s


@routes.post("/api/admin/tiers/set")
async def tier_set(c: Ctx):
    """`.settier <level> <name>`."""
    need_dev(c)
    b = await c.body()
    level = whole(b.get("level"), lo=0, hi=10_000, what="level")
    if level not in {lvl for lvl, _ in TIERS}:
        raise fail(f"{level} isn't a tier threshold. Valid levels: {', '.join(str(l) for l, _ in TIERS)}.", 400, "bad_level")
    name = clean_name(b.get("name"), "tier")
    await c.db.set_tier_override(c.gid, level, name)
    log.info("TIER RENAME   | %s renamed tier %s to '%s' in guild %s via web", c.uid, level, name, c.gid)
    return {"level": level, "name": name}


@routes.post("/api/admin/tiers/reset")
async def tier_reset(c: Ctx):
    """`.resettier <level>` or, with no level, `.resettiers`."""
    need_dev(c)
    b = await c.body()
    if b.get("level") in (None, ""):
        return {"reset": await c.db.reset_all_tier_overrides(c.gid), "all": True}
    level = whole(b.get("level"), lo=0, hi=10_000, what="level")
    if not await c.db.reset_tier_override(c.gid, level):
        raise fail(f"Level {level} wasn't renamed, so there's nothing to reset.", 404, "not_renamed")
    return {"reset": 1, "all": False, "level": level}


@routes.post("/api/admin/tags/add")
async def tag_add(c: Ctx):
    """`.addtag <price> <text>`."""
    need_dev(c)
    b = await c.body()
    price = whole(b.get("price"), lo=0, what="price")
    text = clean_name(b.get("title"), "tag")
    iid = await c.db.add_custom_tag(c.gid, text, price)
    log.info("TAG ADD       | %s added tag '%s' (id=%s) in guild %s via web", c.uid, text, iid, c.gid)
    return {"id": iid, "title": text, "price": price}


@routes.post("/api/admin/tags/remove")
async def tag_remove(c: Ctx):
    """`.removetag <text>`: by id or by title, custom tags only."""
    need_dev(c)
    q = str((await c.body()).get("tag") or "").strip()
    custom = await c.db.get_custom_tags(c.gid)
    hit = next((iid for iid, it in custom.items() if iid == q or it["title_text"].lower() == q.lower()), None) if q else None
    if hit is None:
        raise fail("No custom tag matches that. Built-in tags can't be removed here.", 404, "no_tag")
    await c.db.remove_custom_tag(c.gid, hit)
    return {"removed": hit}


# ---------------------------------------------------------------------- #
# Developer: grants (cogs/dev.py)
# ---------------------------------------------------------------------- #
@routes.get("/api/admin/members")
async def members(c: Ctx):
    """Members with stats in this server, for the grant picker."""
    need_dev(c)
    cur = await c.db.conn.execute("SELECT user_id, level, xp FROM user_stats WHERE guild_id = ? ORDER BY xp DESC LIMIT 300", (c.gid,))
    rows = [dict(r) for r in await cur.fetchall()]
    return {"members": [{**c.person(r["user_id"]), "level": r["level"], "xp": r["xp"]} for r in rows if c.bridge.is_member(c.gid, r["user_id"])]}


@routes.post("/api/admin/grant")
async def grant(c: Ctx):
    """.addtime/.removetime, .addxp/.removexp, .addcoins/.removecoins, .addcandy, .addbox, .addpasstime."""
    need_dev(c)
    b = await c.body()
    uid = target_of(c, b)
    kind, remove = str(b.get("kind") or ""), str(b.get("mode") or "add") == "remove"
    tiers_ = await c.db.get_effective_tiers(c.gid)
    out: dict[str, Any] = {"kind": kind, "mode": "remove" if remove else "add", "user": c.person(uid)}

    if kind in ("time",):
        seconds = parse_duration(str(b.get("duration") or ""))
        if not seconds:
            raise fail("Couldn't read that duration. Try 3h, 45m or 1h30m.", 400, "bad_duration")
        subject = None
        if b.get("subject"):
            subject = SUBJECT_ALIASES.get(normalize_subject_key(str(b["subject"])))
            if subject is None:
                raise fail(f"Unknown subject. {SUBJECT_HINT}", 400, "bad_subject")
        if remove:
            r = await c.db.remove_time(uid, c.gid, seconds, subject)
            out.update(seconds=r["seconds_removed"], xp=r["xp_removed"], coins=r["coins_removed"], level_changed=bool(r["leveled_down"]), new_level=r["new_level"])
        else:
            r = await c.db.grant_time(uid, c.gid, seconds, subject)
            out.update(seconds=seconds, xp=r["xp_earned"], coins=r["coins_earned"], level_changed=bool(r["leveled_up"]), new_level=r.get("new_level"))
        out["text"] = f"{'Removed' if remove else 'Added'} {format_duration(out['seconds'])}, {out['xp']} XP and {out['coins']} Chronocoins."
        if subject:
            out["subject"] = SUBJECT_INFO[subject]["label"]
    elif kind == "xp":
        n = whole(b.get("amount"), lo=1 if remove else -MAX_AMOUNT, what="amount")
        if n == 0:
            raise fail("Give a non-zero XP amount.", 400, "bad_amount")
        r = await c.db.grant_xp(uid, c.gid, -n if remove else n)
        out.update(new_level=r["new_level"], level_changed=r["new_level"] != r["old_level"], text=f"{'Removed' if remove else 'Added'} {abs(n):,} XP.")
    elif kind == "coins":
        n = whole(b.get("amount"), lo=1 if remove else -MAX_AMOUNT, what="amount")
        if n == 0:
            raise fail("Give a non-zero Chronocoin amount.", 400, "bad_amount")
        bal = await (c.db.remove_coins(uid, c.gid, n) if remove else c.db.grant_coins(uid, c.gid, n))
        out.update(balance=bal, text=f"{'Removed' if remove else 'Added'} {abs(n):,} Chronocoins. New balance {bal:,}.")
    elif kind == "candy":
        n = whole(b.get("amount"), what="amount")
        if n == 0:
            raise fail("Give a non-zero Candy amount.", 400, "bad_amount")
        n = -abs(n) if remove else n
        bal = await c.db.add_candy(uid, c.gid, n)
        out.update(balance=bal, text=f"{'Removed' if n < 0 else 'Added'} {abs(n):,} Candy. New balance {bal:,}.")
    elif kind == "box":
        if remove:
            raise fail("Boxes can only be added.", 400, "bad_mode")
        box_id = halloween_catalog.resolve_box_id(str(b.get("box") or ""))
        if not box_id:
            raise fail("Unknown box tier. Valid tiers: common, uncommon, rare, epic, legendary.", 400, "invalid_box")
        qty = whole(b.get("quantity", 1), lo=1, hi=1000, what="quantity")
        await c.db.add_item(uid, c.gid, box_id, qty)
        out.update(text=f"Added {qty} x {halloween_catalog.get_box(box_id)['name']}.")
    elif kind == "passtime":
        if remove:
            raise fail("Pass time can only be added.", 400, "bad_mode")
        minutes = whole(b.get("minutes"), lo=1, hi=100_000, what="minutes")
        r = await c.db.credit_halloween_study(uid, c.gid, minutes * 60)
        un = r.get("new_level_unlocked")
        total = r["pass"]["study_seconds"] // 60
        out.update(text=f"Added {minutes} pass minutes. Event total {total} min." + (f" Unlocked level {un['level']}: {un['level_name']}." if un else ""))
    else:
        raise fail("Pick what to grant: time, xp, coins, candy, box or passtime.", 400, "bad_kind")
    if out.get("level_changed") and out.get("new_level") is not None:
        out["tier"] = tier_for_level(out["new_level"], tiers_)
    c.hub.publish(uid, c.gid, "refresh", {})                  # the target's open pages re-read their numbers
    log.info("DEV GRANT     | %s %s %s for %s in guild %s via web: %s", c.uid, "removed" if remove else "granted", kind, uid, c.gid, out.get("text"))
    return out


@routes.get("/api/admin/diagnostics")
async def diagnostics(c: Ctx):
    """`.checkdb`."""
    need_dev(c)
    counts: dict[str, Any] = {}
    for t in DIAG_TABLES:
        try:
            cur = await c.db.conn.execute(f"SELECT COUNT(*) AS cnt FROM {t}")
            counts[t] = (await cur.fetchone())["cnt"]
        except Exception as e:           # a missing table is information, not a crash
            counts[t] = f"Error: {e}"
    cur = await c.db.conn.execute("SELECT DISTINCT guild_id FROM user_currency")
    guilds = [str(r["guild_id"]) for r in await cur.fetchall()]
    currency, stats = await c.db.get_or_create_currency(c.uid, c.gid), await c.db.get_or_create_user_stats(c.uid, c.gid)
    pets = await c.db.get_owned_pets(c.uid, c.gid)
    return {"guild": str(c.gid), "known_guilds": guilds, "counts": counts,
            "you": {"level": stats.get("level", 0), "xp": stats.get("xp", 0), "coins": currency.get("coins", 0), "lifetime": currency.get("lifetime_earned", 0),
                    "streak": stats.get("current_streak", 0), "pets": [p.get("nickname") or p.get("species_id") for p in pets]}}


# ---------------------------------------------------------------------- #
@routes.get("/api/help")
async def help_info(c: Ctx):
    """The numbers the Help page quotes, so they always match this server's config."""
    import config
    return {"prefix": config.PREFIX, "pet_unlock_level": config.PET_UNLOCK_LEVEL, "checkin_minutes": config.CHECKIN_INTERVAL_MINUTES,
            "afk_grace_minutes": config.AFK_GRACE_MINUTES, "trivia_cooldown": config.TRIVIA_COOLDOWN_SECONDS,
            "is_manager": c.bridge.is_manager(c.gid, c.uid), "is_dev": c.bridge.is_dev(c.uid)}
