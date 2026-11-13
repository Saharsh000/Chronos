"""Study sessions - the website twin of `.start` / `.stop` / `.session` / `.active`
/ `.pomodoro`, plus answering the AFK "still studying?" prompt from the browser.

Rules are the bot's rules, because it's the same code path underneath: the
`sessions` table is the single source of truth, the bot's session monitor keeps
crediting XP/coins and sending AFK prompts for web-started sessions, and the
mirror posts below land in your check-in channel just like the bot's own."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import config
from utils.subjects import SUBJECT_ALIASES, SUBJECT_HINT, SUBJECT_INFO, detect_subject, normalize_subject_key
from utils.xp import xp_progress

from . import mirror
from .common import Ctx, Routes, fail, level_block, period_totals, subject_card

log = logging.getLogger("web.session")
routes = Routes()


async def effects_block(c: Ctx, uid: Optional[int] = None) -> list[dict[str, Any]]:
    uid = uid or c.uid
    now = int(time.time())
    out = []
    for effect_id, label in (("xp_boost", "XP Boost"), ("coin_boost", "Chronocoin Boost")):
        e = await c.db.get_active_effect(uid, c.gid, effect_id, now)
        if e:
            out.append({"id": effect_id, "label": label, "multiplier": e["multiplier"],
                        "expires_at": e["expires_at"], "remaining": max(0, e["expires_at"] - now)})
    return out


def session_view(c: Ctx, s: dict[str, Any], now: int) -> dict[str, Any]:
    checkin_interval = config.CHECKIN_INTERVAL_MINUTES * 60
    grace = config.AFK_GRACE_MINUTES * 60
    prompt = s.get("prompt_sent_at")
    return {
        "id": s["session_id"],
        "subject": subject_card(s.get("subject")),
        "start_time": s["start_time"],
        "elapsed": max(0, now - s["start_time"]),
        "credited_seconds": s["credited_seconds"],
        "credited_xp": s["credited_xp"],
        "credited_coins": s.get("credited_coins", 0),
        "channel": c.bridge.channel_name(s.get("channel_id")),
        "last_checkin": s["last_checkin"],
        "next_checkin_at": s["last_checkin"] + checkin_interval,
        "afk": {
            "pending": prompt is not None,
            "sent_at": prompt,
            "deadline": (prompt + grace) if prompt else None,
            "grace_seconds": grace,
        },
    }


@routes.get("/api/session", lock=False)
async def get_session(c: Ctx):
    now = int(time.time())
    s = await c.db.get_active_session(c.uid, c.gid)
    stats = await c.db.get_or_create_user_stats(c.uid, c.gid)
    today = (await period_totals(c.db, c.gid, "today")).get(c.uid, 0)
    lvl = await level_block(c, stats["xp"])
    return {
        "now": now,
        "active": s is not None,
        "session": session_view(c, s, now) if s else None,
        "effects": await effects_block(c),
        "today_seconds": today,
        "streak": {"current": stats["current_streak"], "longest": stats["longest_streak"]},
        "level": lvl,
        "voice": c.bridge.channel_name(c.bridge.voice_channel_of(c.gid, c.uid)),
        "config": {
            "xp_per_min": [config.XP_MIN_PER_MINUTE, config.XP_MAX_PER_MINUTE],
            "coins_per_min": [config.COINS_MIN_PER_MINUTE, config.COINS_MAX_PER_MINUTE],
            "checkin_minutes": config.CHECKIN_INTERVAL_MINUTES,
            "grace_minutes": config.AFK_GRACE_MINUTES,
            "pomodoro": {
                "focus": config.POMODORO_FOCUS_MINUTES, "break": config.POMODORO_BREAK_MINUTES,
                "long_break": config.POMODORO_LONG_BREAK_MINUTES,
                "cycles": config.POMODORO_CYCLES_BEFORE_LONG_BREAK,
            },
        },
    }


@routes.post("/api/session/start")
async def start_session(c: Ctx):
    body = await c.body()
    if await c.db.get_active_session(c.uid, c.gid):
        raise fail("You already have a session running. Stop it first.", 409, "already_active")

    voice_id = c.bridge.voice_channel_of(c.gid, c.uid)
    cfg = await c.db.get_guild_config(c.gid)
    resolved = detect_subject(cfg, voice_id)
    subject = (body.get("subject") or "").strip()
    if subject:
        resolved = SUBJECT_ALIASES.get(normalize_subject_key(subject))
        if resolved is None:
            raise fail(f"Unknown subject '{subject}'. {SUBJECT_HINT}", 400, "bad_subject")

    now = int(time.time())
    sid = await c.db.start_session(c.uid, c.gid, voice_id, resolved, now)
    log.info("SESSION START | %s (%s) in guild %s via web%s", c.me["name"], c.uid, c.gid,
             f" [subject={resolved}]" if resolved else "")
    await c.mirror(embed=mirror.session_started(c.me, c.uid, resolved, now))
    c.emit("session_started", subject=resolved, source="web")
    await c.top3_perk()
    s = await c.db.get_active_session(c.uid, c.gid)
    return {"ok": True, "session": session_view(c, s, now), "id": sid}


@routes.post("/api/session/stop")
async def stop_session(c: Ctx):
    s = await c.db.get_active_session(c.uid, c.gid)
    if not s:
        raise fail("You don't have an active session.", 404, "no_session")
    now = int(time.time())
    result = await c.db.end_session(s["session_id"], now, "manual_stop")
    if not result:
        raise fail("That session was already closed.", 409, "already_closed")

    log.info("SESSION END   | user=%s guild=%s duration=%ss xp+=%s reason=manual_stop (web)",
             c.uid, c.gid, result["duration"], result["xp_earned"])
    stats = await c.db.get_or_create_user_stats(c.uid, c.gid)
    cur_xp, next_xp, _ = xp_progress(stats.get("xp", 0))
    tier_name = await c.tier_name(result["new_level"])

    # --- mirror to Discord exactly like `.stop` does ------------------------
    file = None
    try:
        from utils.stats_card import render_session_summary_card_sync
        avatar = await c.bridge.avatar_bytes(c.gid, c.uid)
        loop = asyncio.get_running_loop()
        png = await loop.run_in_executor(
            None, render_session_summary_card_sync, c.me["name"], result["duration"],
            result["xp_earned"], result["coins_earned"], result.get("subject"),
            result["old_level"], result["new_level"], cur_xp, next_xp, tier_name,
            stats.get("current_streak", 1), avatar,
        )
        file = (png, "session_summary.png")
    except Exception:
        log.exception("Failed to render session summary card image")
    embed = mirror.session_complete(c.me, c.uid, result, tier_name)
    if file:
        embed.set_image(url="attachment://session_summary.png")
    await c.mirror(embed=embed, file=file)
    if result.get("streak_broken_from", 0) > 0:
        await c.mirror(embed=mirror.streak_lost(c.uid, result["streak_broken_from"]))
    newly = await c.after()

    c.emit("session_ended", source="web", reason="manual_stop", duration=result["duration"],
           xp=result["xp_earned"], coins=result["coins_earned"], subject=result.get("subject"),
           leveled_up=result["leveled_up"], old_level=result["old_level"], new_level=result["new_level"])
    if result["leveled_up"]:
        c.emit("level_up", old_level=result["old_level"], new_level=result["new_level"], tier=tier_name)

    return {
        "ok": True,
        "result": {
            "duration": result["duration"], "xp": result["xp_earned"], "coins": result["coins_earned"],
            "subject": subject_card(result.get("subject")), "leveled_up": result["leveled_up"],
            "old_level": result["old_level"], "new_level": result["new_level"], "tier": tier_name,
            "streak": stats.get("current_streak", 1), "streak_broken_from": result.get("streak_broken_from", 0),
            "total_seconds": result["total_seconds"],
            "achievements": [{"id": a.id, "name": a.name, "emoji": a.emoji, "description": a.description,
                              "reward_coins": a.reward_coins} for a in newly],
            "level": await level_block(c, stats["xp"]),
        },
    }


@routes.post("/api/session/checkin")
async def checkin(c: Ctx):
    """Answer the "Still studying?" prompt - same effect as reacting with ✅ in Discord."""
    s = await c.db.get_active_session(c.uid, c.gid)
    if not s:
        raise fail("You don't have an active session.", 404, "no_session")
    prompt_channel, prompt_msg = s.get("prompt_channel_id"), s.get("prompt_message_id")
    await c.db.update_checkin(s["session_id"], int(time.time()))
    log.info("AFK CONFIRM   | user=%s guild=%s checked in (web)", c.uid, c.gid)
    # Tidy the Discord prompt the same way the ✅ reaction handler does.
    await c.bridge.finish_prompt(prompt_channel, prompt_msg, mirror.still_here())
    c.emit("afk_confirmed", source="web")
    return {"ok": True}


@routes.get("/api/active", lock=False)
async def active(c: Ctx):
    now = int(time.time())
    rows = await c.db.get_active_sessions_for_guild(c.gid)
    people = []
    for s in rows:
        m = c.person(s["user_id"])
        people.append({**m, "elapsed": max(0, now - s["start_time"]), "start_time": s["start_time"],
                       "subject": subject_card(s.get("subject")),
                       "channel": c.bridge.channel_name(s.get("channel_id")), "me": s["user_id"] == c.uid})
    people.sort(key=lambda p: -p["elapsed"])
    return {"now": now, "people": people}


@routes.get("/api/pomodoro", lock=False)
async def pomodoro(c: Ctx):
    now = int(time.time())
    out = []
    for p in await c.db.get_all_active_pomodoros():
        if p["guild_id"] != c.gid:
            continue
        members = [c.person(u) for u in c.bridge.voice_members(p["channel_id"])]
        out.append({
            "channel_id": p["channel_id"], "channel": c.bridge.channel_name(p["channel_id"]) or "Voice room",
            "phase": p["phase"], "phase_start": p["phase_start"], "phase_duration": p["phase_duration"],
            "remaining": max(0, p["phase_duration"] - (now - p["phase_start"])),
            "cycles": p["cycle_count"], "members": members,
            "joined": any(m["id"] == c.uid for m in members),
        })
    return {"now": now, "rooms": out}
