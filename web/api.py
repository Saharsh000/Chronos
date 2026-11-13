"""Comprehensive REST API endpoints for all Chronos study companion features."""
from __future__ import annotations

import base64
import datetime as dt
import logging
import random
import time
from typing import Any, Optional

from aiohttp import web

import config
from utils import achievements as ach_utils
from utils import beg_scenarios
from utils import economy as eco_utils
from utils import food as food_utils
from utils import halloween as hallo_utils
from utils import pets as pet_utils
from utils import streaks as streak_utils
from utils import subjects as subj_utils
from utils import syllabus as syl_utils
from utils import xp as xp_utils
from utils.time_format import format_duration
from web.auth import get_current_user, require_auth
from web.discord_sync import notify_pet_progress, notify_session_start, notify_session_stop

log = logging.getLogger("web.api")

DEFAULT_GUILD_ID = 1483039226693030083


def _user_ctx(request: web.Request) -> tuple[int, int]:
    """Helper to extract user_id and active guild_id from request."""
    user = get_current_user(request)
    user_id = user["user_id"] if user else config.DEV_USER_ID
    guild_id = user.get("guild_id") if user else DEFAULT_GUILD_ID
    return user_id, int(guild_id)


# ===================================================================== #
# 1. Study Sessions & Focus
# ===================================================================== #

@require_auth
async def api_get_active_session(request: web.Request) -> web.Response:
    """Return in-progress session for current user."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    session = await db.get_active_session(user_id, guild_id)
    if not session:
        return web.json_response({"active": False, "session": None})

    now = int(time.time())
    elapsed = max(0, now - session["start_time"])
    
    # Calculate live progress
    credit = await db.credit_progress(session["session_id"], now)
    
    # Refresh session row
    session = await db.get_active_session(user_id, guild_id)
    subject = session.get("subject")
    subject_info = subj_utils.SUBJECT_INFO.get(subject) if subject else None

    return web.json_response({
        "active": True,
        "session": {
            "session_id": session["session_id"],
            "subject": subject,
            "subject_info": subject_info,
            "start_time": session["start_time"],
            "elapsed_seconds": elapsed,
            "credited_seconds": session.get("credited_seconds", 0),
            "credited_xp": session.get("credited_xp", 0),
            "credited_coins": session.get("credited_coins", 0),
        },
    })


@require_auth
async def api_start_session(request: web.Request) -> web.Response:
    """Start a new study session."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    bot = request.app.get("bot")

    existing = await db.get_active_session(user_id, guild_id)
    if existing:
        now = int(time.time())
        elapsed = now - existing["start_time"]
        return web.json_response({
            "error": f"You already have a session running ({format_duration(elapsed)} so far).",
            "session": existing,
        }, status=400)

    try:
        data = await request.json()
    except Exception:
        data = {}

    raw_subject = data.get("subject")
    resolved_subject = None
    if raw_subject:
        norm = subj_utils.normalize_subject_key(raw_subject)
        resolved_subject = subj_utils.SUBJECT_ALIASES.get(norm)

    now = int(time.time())
    session_id = await db.start_session(user_id, guild_id, channel_id=None, subject=resolved_subject, now=now)

    # Dispatch rich Discord announcement to #notifs
    if bot:
        request.app.loop.create_task(
            notify_session_start(bot, guild_id, user_id, resolved_subject, now)
        )

    log.info(f"API | Session started: id={session_id} user={user_id} subject={resolved_subject}")

    return web.json_response({
        "status": "ok",
        "session_id": session_id,
        "start_time": now,
        "subject": resolved_subject,
        "subject_info": subj_utils.SUBJECT_INFO.get(resolved_subject),
    })


@require_auth
async def api_stop_session(request: web.Request) -> web.Response:
    """End the active study session and return full rewards & summary card."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    bot = request.app.get("bot")

    session = await db.get_active_session(user_id, guild_id)
    if not session:
        return web.json_response({"error": "No active study session to stop."}, status=400)

    now = int(time.time())
    result = await db.end_session(session["session_id"], now, reason="web_stop")
    if not result:
        return web.json_response({"error": "Session was already ended."}, status=400)

    # Render card & notify Discord in background
    card_bytes = None
    if bot:
        card_bytes = await notify_session_stop(bot, guild_id, user_id, result)

    card_base64 = None
    if card_bytes:
        card_base64 = f"data:image/png;base64,{base64.b64encode(card_bytes).decode('ascii')}"

    # Get fresh user stats
    stats = await db.get_or_create_user_stats(user_id, guild_id)
    currency = await db.get_or_create_currency(user_id, guild_id)

    return web.json_response({
        "status": "ok",
        "summary": {
            "duration": result["duration"],
            "formatted_duration": format_duration(result["duration"]),
            "xp_earned": result["xp_earned"],
            "coins_earned": result["coins_earned"],
            "subject": result.get("subject"),
            "old_level": result["old_level"],
            "new_level": result["new_level"],
            "leveled_up": result["leveled_up"],
            "current_streak": stats.get("current_streak", 1),
            "streak_broken_from": result.get("streak_broken_from", 0),
            "card_image": card_base64,
        },
        "wallet": {
            "coins": currency.get("coins", 0),
            "candy": currency.get("candy", 0),
        },
    })


@require_auth
async def api_session_heartbeat(request: web.Request) -> web.Response:
    """Heartbeat from web timer to refresh active check-in and prevent false AFK timeout."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    session = await db.get_active_session(user_id, guild_id)
    if not session:
        return web.json_response({"active": False})

    now = int(time.time())
    await db.update_checkin(session["session_id"], now)
    await db.credit_progress(session["session_id"], now)

    session = await db.get_active_session(user_id, guild_id)
    return web.json_response({
        "active": True,
        "elapsed_seconds": max(0, now - session["start_time"]),
        "credited_xp": session.get("credited_xp", 0),
        "credited_coins": session.get("credited_coins", 0),
    })


async def api_server_active(request: web.Request) -> web.Response:
    """List members currently studying in the server (mirror of .active)."""
    user = get_current_user(request)
    guild_id = user.get("guild_id", DEFAULT_GUILD_ID) if user else DEFAULT_GUILD_ID
    db = request.app["db"]
    bot = request.app.get("bot")

    active_sessions = await db.get_active_sessions_for_guild(int(guild_id))
    now = int(time.time())
    studiers = []

    guild = bot.get_guild(int(guild_id)) if bot and bot.is_ready() else None

    for s in active_sessions:
        uid = s["user_id"]
        member = guild.get_member(uid) if guild else None
        name = member.display_name if member else f"User {uid}"
        avatar = member.display_avatar.url if member else "https://cdn.discordapp.com/embed/avatars/0.png"
        elapsed = max(0, now - s["start_time"])
        subj = s.get("subject")
        studiers.append({
            "user_id": str(uid),
            "name": name,
            "avatar": avatar,
            "subject": subj,
            "subject_info": subj_utils.SUBJECT_INFO.get(subj),
            "elapsed_seconds": elapsed,
            "formatted_elapsed": format_duration(elapsed),
        })

    return web.json_response({"count": len(studiers), "studiers": studiers})


async def api_pomodoro_status(request: web.Request) -> web.Response:
    """Get active VC Pomodoro timer state for the guild."""
    user = get_current_user(request)
    guild_id = user.get("guild_id", DEFAULT_GUILD_ID) if user else DEFAULT_GUILD_ID
    db = request.app["db"]

    pomodoros = await db.get_all_active_pomodoros()
    now = int(time.time())
    active_pomo = None

    for p in pomodoros:
        # Find one in current guild if channel belongs to guild
        active_pomo = p
        break

    if not active_pomo:
        return web.json_response({
            "active": False,
            "focus_minutes": config.POMODORO_FOCUS_MINUTES,
            "break_minutes": config.POMODORO_BREAK_MINUTES,
            "long_break_minutes": config.POMODORO_LONG_BREAK_MINUTES,
        })

    phase = active_pomo["phase"]
    phase_start = active_pomo["phase_start"]
    elapsed = max(0, now - phase_start)

    phase_lengths = {
        "focus": config.POMODORO_FOCUS_MINUTES * 60,
        "break": config.POMODORO_BREAK_MINUTES * 60,
        "long_break": config.POMODORO_LONG_BREAK_MINUTES * 60,
    }
    total_seconds = phase_lengths.get(phase, 25 * 60)
    remaining = max(0, total_seconds - elapsed)

    return web.json_response({
        "active": True,
        "phase": phase,
        "cycle_count": active_pomo.get("cycle_count", 0),
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "total_seconds": total_seconds,
        "progress_pct": min(100.0, (elapsed / total_seconds) * 100) if total_seconds > 0 else 0,
    })


# ===================================================================== #
# 2. User Stats & Passport
# ===================================================================== #

@require_auth
async def api_get_stats(request: web.Request) -> web.Response:
    """Return complete user passport, rank, subject stats, and recent session history."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    bot = request.app.get("bot")

    stats = await db.get_or_create_user_stats(user_id, guild_id)
    currency = await db.get_or_create_currency(user_id, guild_id)
    effective_tiers = await db.get_effective_tiers(guild_id)
    subject_stats = await db.get_detailed_subject_breakdown(user_id, guild_id)

    level = stats.get("level", 0)
    tier_name = xp_utils.tier_for_level(level, effective_tiers)
    cur_xp, next_xp, xp_pct = xp_utils.xp_progress(stats.get("xp", 0))

    # Fetch recent session logs
    cur = await db.conn.execute(
        """
        SELECT log_id, subject, start_time, end_time, duration_seconds, xp_earned, end_reason
        FROM session_log
        WHERE user_id = ? AND guild_id = ?
        ORDER BY end_time DESC
        LIMIT 15
        """,
        (user_id, guild_id),
    )
    rows = await cur.fetchall()
    recent_sessions = []
    for r in rows:
        recent_sessions.append({
            "log_id": r["log_id"],
            "subject": r["subject"],
            "subject_info": subj_utils.SUBJECT_INFO.get(r["subject"]),
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "duration": r["duration_seconds"],
            "formatted_duration": format_duration(r["duration_seconds"]),
            "xp_earned": r["xp_earned"],
            "end_reason": r["end_reason"],
        })

    # Subject distribution summary
    total_sec = stats.get("total_seconds", 0)
    subjects_data = []
    for s_key in ["physics", "chemistry", "maths"]:
        s_data = subject_stats.get(s_key, {})
        s_sec = s_data.get("total_seconds", 0) if isinstance(s_data, dict) else (s_data or 0)
        s_count = s_data.get("session_count", 0) if isinstance(s_data, dict) else 0
        s_pct = round((s_sec / total_sec * 100), 1) if total_sec > 0 else 0
        info = subj_utils.SUBJECT_INFO.get(s_key, {})
        subjects_data.append({
            "key": s_key,
            "label": info.get("label", s_key.capitalize()),
            "emoji": info.get("emoji", "📚"),
            "color": info.get("color", 0x8895b3),
            "seconds": s_sec,
            "session_count": s_count,
            "formatted": format_duration(s_sec),
            "percentage": s_pct,
        })

    return web.json_response({
        "stats": {
            "total_seconds": total_sec,
            "formatted_total": format_duration(total_sec),
            "xp": stats.get("xp", 0),
            "level": level,
            "cur_xp": cur_xp,
            "next_xp": next_xp,
            "xp_percentage": xp_pct,
            "tier": tier_name,
            "current_streak": stats.get("current_streak", 0),
            "longest_streak": stats.get("longest_streak", 0),
            "equipped_title": stats.get("equipped_title"),
            "sessions_count": stats.get("sessions_count", 0),
            "last_active_date": stats.get("last_active_date"),
        },
        "wallet": {
            "coins": currency.get("coins", 0),
            "candy": currency.get("candy", 0),
            "lifetime_earned": currency.get("lifetime_earned", 0),
        },
        "subjects": subjects_data,
        "recent_sessions": recent_sessions,
    })


@require_auth
async def api_compare_stats(request: web.Request) -> web.Response:
    """Compare logged in user head-to-head with target member."""
    user_id, guild_id = _user_ctx(request)
    target_id_raw = request.query.get("target_id")
    if not target_id_raw:
        return web.json_response({"error": "target_id parameter required"}, status=400)
    try:
        target_id = int(target_id_raw)
    except ValueError:
        return web.json_response({"error": "Invalid target_id"}, status=400)

    db = request.app["db"]
    bot = request.app.get("bot")

    u_ctx = await db.get_compare_context(user_id, guild_id)
    t_ctx = await db.get_compare_context(target_id, guild_id)

    guild = bot.get_guild(guild_id) if bot and bot.is_ready() else None
    m_user = guild.get_member(user_id) if guild else None
    m_target = guild.get_member(target_id) if guild else None

    return web.json_response({
        "user": {
            "user_id": str(user_id),
            "name": m_user.display_name if m_user else f"User {user_id}",
            "avatar": m_user.display_avatar.url if m_user else None,
            "level": u_ctx["level"],
            "xp": u_ctx["xp"],
            "total_seconds": u_ctx["total_seconds"],
            "formatted_total": format_duration(u_ctx["total_seconds"]),
            "streak": u_ctx["current_streak"],
        },
        "target": {
            "user_id": str(target_id),
            "name": m_target.display_name if m_target else f"User {target_id}",
            "avatar": m_target.display_avatar.url if m_target else None,
            "level": t_ctx["level"],
            "xp": t_ctx["xp"],
            "total_seconds": t_ctx["total_seconds"],
            "formatted_total": format_duration(t_ctx["total_seconds"]),
            "streak": t_ctx["current_streak"],
        },
    })


# ===================================================================== #
# 3. Leaderboards & Hall of Fame
# ===================================================================== #

def _get_period_start_ist(period: str) -> Optional[int]:
    """Calculate epoch second marking period start anchored to India Standard Time."""
    now = dt.datetime.now(config.IST)
    if period == "today":
        return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    elif period == "week":
        start = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(start.timestamp())
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return int(start.timestamp())
    return None


async def api_get_leaderboard(request: web.Request) -> web.Response:
    """Fetch multi-period leaderboards (today / week / month / alltime)."""
    user = get_current_user(request)
    guild_id = int(user.get("guild_id", DEFAULT_GUILD_ID)) if user else DEFAULT_GUILD_ID
    period = request.query.get("period", "today").lower()
    if period not in ("today", "week", "month", "alltime"):
        period = "today"

    db = request.app["db"]
    bot = request.app.get("bot")
    guild = bot.get_guild(guild_id) if bot and bot.is_ready() else None

    period_start = _get_period_start_ist(period)

    # All-time pulls directly from user_stats
    if period == "alltime":
        cur = await db.conn.execute(
            """
            SELECT user_id, total_seconds, xp, level, current_streak, equipped_title
            FROM user_stats
            WHERE guild_id = ? AND total_seconds > 0
            ORDER BY total_seconds DESC
            LIMIT 50
            """,
            (guild_id,),
        )
        rows = await cur.fetchall()
        rankings = []
        for i, r in enumerate(rows):
            uid = r["user_id"]
            member = guild.get_member(uid) if guild else None
            rankings.append({
                "rank": i + 1,
                "user_id": str(uid),
                "name": member.display_name if member else f"User {uid}",
                "avatar": member.display_avatar.url if member else "https://cdn.discordapp.com/embed/avatars/0.png",
                "seconds": r["total_seconds"],
                "formatted_time": format_duration(r["total_seconds"]),
                "xp": r["xp"],
                "level": r["level"],
                "streak": r["current_streak"],
                "title": r["equipped_title"],
            })
    else:
        # Sum from session_log since period start
        cur = await db.conn.execute(
            """
            SELECT user_id, SUM(duration_seconds) as period_seconds, SUM(xp_earned) as period_xp
            FROM session_log
            WHERE guild_id = ? AND start_time >= ?
            GROUP BY user_id
            ORDER BY period_seconds DESC
            LIMIT 50
            """,
            (guild_id, period_start),
        )
        rows = await cur.fetchall()
        totals = {r["user_id"]: {"seconds": r["period_seconds"], "xp": r["period_xp"]} for r in rows}

        # Add live in-progress session delta if active
        now = int(time.time())
        active_sessions = await db.get_active_sessions_for_guild(guild_id)
        for s in active_sessions:
            uid = s["user_id"]
            live_start = max(s["start_time"], period_start)
            live_duration = max(0, now - live_start)
            if uid in totals:
                totals[uid]["seconds"] += live_duration
            else:
                totals[uid] = {"seconds": live_duration, "xp": 0}

        sorted_users = sorted(totals.items(), key=lambda x: x[1]["seconds"], reverse=True)
        rankings = []
        for i, (uid, data) in enumerate(sorted_users):
            member = guild.get_member(uid) if guild else None
            u_stat = await db.get_or_create_user_stats(uid, guild_id)
            rankings.append({
                "rank": i + 1,
                "user_id": str(uid),
                "name": member.display_name if member else f"User {uid}",
                "avatar": member.display_avatar.url if member else "https://cdn.discordapp.com/embed/avatars/0.png",
                "seconds": data["seconds"],
                "formatted_time": format_duration(data["seconds"]),
                "xp": data["xp"],
                "level": u_stat.get("level", 0),
                "streak": u_stat.get("current_streak", 0),
                "title": u_stat.get("equipped_title"),
            })

    # Top 3 perks details
    top3_perks = [
        {"rank": 1, "badge": "Gold Crown", "coins": 250, "buff": "2.0x XP Focus Buff (60m)", "vault": "Legendary Hallo-Box"},
        {"rank": 2, "badge": "Silver Crown", "coins": 150, "buff": "1.5x XP Focus Buff (60m)", "vault": "Epic Hallo-Box"},
        {"rank": 3, "badge": "Bronze Crown", "coins": 100, "buff": "1.25x XP Focus Buff (60m)", "vault": "Rare Hallo-Box"},
    ]

    return web.json_response({
        "period": period,
        "rankings": rankings,
        "top3_perks": top3_perks,
    })


async def api_hall_of_fame(request: web.Request) -> web.Response:
    """Fetch Hall of Fame records for the guild."""
    user = get_current_user(request)
    guild_id = int(user.get("guild_id", DEFAULT_GUILD_ID)) if user else DEFAULT_GUILD_ID
    db = request.app["db"]
    bot = request.app.get("bot")
    guild = bot.get_guild(guild_id) if bot and bot.is_ready() else None

    records = await db.get_hall_of_fame(guild_id)
    
    def _enrich(item_list, key_time="seconds"):
        res = []
        for row in item_list:
            uid = row.get("user_id")
            member = guild.get_member(uid) if guild and uid else None
            item = dict(row)
            item["name"] = member.display_name if member else f"User {uid}"
            item["avatar"] = member.display_avatar.url if member else "https://cdn.discordapp.com/embed/avatars/0.png"
            if key_time in item:
                item["formatted_time"] = format_duration(item[key_time])
            res.append(item)
        return res

    return web.json_response({
        "longest_sessions": _enrich(records.get("longest_sessions", []), "duration_seconds"),
        "top_streaks": _enrich(records.get("top_streaks", [])),
        "top_levels": _enrich(records.get("top_levels", [])),
    })


# ===================================================================== #
# 4. JEE Syllabus & Exam Roadmap
# ===================================================================== #

@require_auth
async def api_get_syllabus(request: web.Request) -> web.Response:
    """Return complete JEE syllabus tree with user's checked off milestones."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]

    completed = await db.get_completed_milestones(user_id, guild_id)
    completed_chapters = {m["label"] for m in completed if m["type"] == "chapter"}
    completed_subtopics = {m["label"] for m in completed if m["type"] == "subtopic"}
    revisions = {}
    pyqs = {}

    for m in completed:
        t_name = m["label"]
        if m["type"] == "revision":
            revisions[t_name] = revisions.get(t_name, 0) + 1
        elif m["type"] == "pyq":
            pyqs[t_name] = pyqs.get(t_name, 0) + 1

    total_chapters = 0
    done_chapters = 0
    syllabus_data = {}

    for subj_key, chapters in syl_utils.SYLLABUS.items():
        s_list = []
        for ch in chapters:
            ch_name = ch["name"]
            is_done = ch_name in completed_chapters
            total_chapters += 1
            if is_done:
                done_chapters += 1

            topics_data = []
            for top in ch.get("topics", []):
                topics_data.append({
                    "name": top,
                    "done": f"{ch_name}::{top}" in completed_subtopics,
                })

            s_list.append({
                "name": ch_name,
                "done": is_done,
                "topics": topics_data,
                "revisions": revisions.get(ch_name, 0),
                "pyqs": pyqs.get(ch_name, 0),
            })
        syllabus_data[subj_key] = s_list

    pct = round((done_chapters / total_chapters * 100), 1) if total_chapters > 0 else 0

    return web.json_response({
        "total_chapters": total_chapters,
        "completed_chapters": done_chapters,
        "progress_percentage": pct,
        "subjects": syllabus_data,
    })


@require_auth
async def api_toggle_chapter(request: web.Request) -> web.Response:
    """Toggle syllabus chapter completion."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        chapter_name = data["chapter_name"]
    except Exception:
        return web.json_response({"error": "Missing chapter_name"}, status=400)

    cur = await db.conn.execute(
        """
        SELECT milestone_id FROM user_milestones
        WHERE user_id = ? AND guild_id = ? AND type = 'chapter' AND label = ?
        """,
        (user_id, guild_id, chapter_name),
    )
    existing = await cur.fetchone()
    if existing:
        await db.conn.execute(
            "DELETE FROM user_milestones WHERE milestone_id = ?", (existing["milestone_id"],)
        )
        await db.conn.commit()
        done = False
    else:
        now = int(time.time())
        await db.log_milestone(user_id, guild_id, "chapter", chapter_name, now=now)
        done = True

    return web.json_response({"status": "ok", "chapter_name": chapter_name, "done": done})


@require_auth
async def api_toggle_subtopic(request: web.Request) -> web.Response:
    """Toggle syllabus subtopic checkbox."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        chapter_name = data["chapter_name"]
        topic_name = data["topic_name"]
    except Exception:
        return web.json_response({"error": "Missing chapter_name or topic_name"}, status=400)

    target_key = f"{chapter_name}::{topic_name}"
    cur = await db.conn.execute(
        """
        SELECT milestone_id FROM user_milestones
        WHERE user_id = ? AND guild_id = ? AND type = 'subtopic' AND label = ?
        """,
        (user_id, guild_id, target_key),
    )
    existing = await cur.fetchone()
    if existing:
        await db.conn.execute(
            "DELETE FROM user_milestones WHERE milestone_id = ?", (existing["milestone_id"],)
        )
        await db.conn.commit()
        done = False
    else:
        now = int(time.time())
        await db.log_milestone(user_id, guild_id, "subtopic", target_key, chapter=chapter_name, now=now)
        done = True

    return web.json_response({"status": "ok", "topic": target_key, "done": done})


@require_auth
async def api_log_revision_pyq(request: web.Request) -> web.Response:
    """Log spaced repetition revision cycle or PYQ milestone."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        action_type = data["action_type"]  # 'revision' or 'pyq'
        chapter_name = data["chapter_name"]
    except Exception:
        return web.json_response({"error": "Invalid request body"}, status=400)

    if action_type not in ("revision", "pyq"):
        return web.json_response({"error": "action_type must be 'revision' or 'pyq'"}, status=400)

    now = int(time.time())
    await db.log_milestone(user_id, guild_id, action_type, chapter_name, now=now)

    # Award bonus XP/coins for studying milestones
    bonus_xp = 25 if action_type == "revision" else 40
    bonus_coins = 15 if action_type == "revision" else 25
    await db.grant_xp(user_id, guild_id, bonus_xp)
    await db.add_coins(user_id, guild_id, bonus_coins)

    return web.json_response({
        "status": "ok",
        "action_type": action_type,
        "chapter_name": chapter_name,
        "xp_awarded": bonus_xp,
        "coins_awarded": bonus_coins,
    })


# ===================================================================== #
# 5. Pets & Companions Menagerie
# ===================================================================== #

@require_auth
async def api_get_pets(request: web.Request) -> web.Response:
    """Get user's equipped pet, menagerie of owned pets, and food satchel."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]

    equipped_raw = await db.get_equipped_pet(user_id, guild_id)
    equipped = None
    if equipped_raw:
        sp_id = equipped_raw["species_id"]
        stage = pet_utils.stage_for_level(sp_id, equipped_raw["level"])
        cur_xp = equipped_raw["xp"]
        next_xp = pet_utils.xp_required_for_level(equipped_raw["level"] + 1)
        prev_xp = pet_utils.xp_required_for_level(equipped_raw["level"])
        stage_xp = max(0, cur_xp - prev_xp)
        stage_req = max(1, next_xp - prev_xp)
        pct = min(100.0, round((stage_xp / stage_req) * 100, 1))

        equipped = {
            "species_id": sp_id,
            "nickname": equipped_raw["nickname"],
            "level": equipped_raw["level"],
            "xp": cur_xp,
            "next_level_xp": next_xp,
            "progress_pct": pct,
            "stage_name": stage["name"],
            "badge": stage["badge"],
            "sprite": stage["sprite"],
            "evolution_info": pet_utils.next_stage(sp_id, equipped_raw["level"]),
        }

    owned_raw = await db.get_owned_pets(user_id, guild_id)
    owned = []
    for p in owned_raw:
        sp_id = p["species_id"]
        stage = pet_utils.stage_for_level(sp_id, p["level"])
        owned.append({
            "species_id": sp_id,
            "nickname": p["nickname"],
            "level": p["level"],
            "equipped": bool(p["equipped"]),
            "stage_name": stage["name"],
            "badge": stage["badge"],
            "sprite": stage["sprite"],
        })

    food_inv = await db.get_food_inventory(user_id, guild_id)

    return web.json_response({
        "equipped_pet": equipped,
        "owned_pets": owned,
        "food_inventory": food_inv,
        "unlock_level": config.PET_UNLOCK_LEVEL,
    })


async def api_get_pet_catalog(request: web.Request) -> web.Response:
    """Return all buyable species organized by tier with animated sprites."""
    catalog_by_tier = {}
    for tier in pet_utils.TIER_ORDER:
        info = pet_utils.TIER_INFO[tier]
        species_list = []
        for sp_id, sp_data in pet_utils.PETS.items():
            if sp_data.get("tier") == tier:
                base_stage = sp_data["stages"]["base"]
                species_list.append({
                    "species_id": sp_id,
                    "name": sp_data["name"],
                    "species": sp_data["species"],
                    "description": sp_data.get("desc", ""),
                    "price": info["base_price"],
                    "sprite": base_stage["sprite"],
                    "base_name": base_stage["name"],
                })
        catalog_by_tier[tier] = {
            "label": info["label"],
            "color": info["color"],
            "emoji": info["emoji"],
            "base_price": info["base_price"],
            "pets": species_list,
        }
    return web.json_response({"catalog": catalog_by_tier})


@require_auth
async def api_buy_pet(request: web.Request) -> web.Response:
    """Adopt and unlock a pet companion."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        species_id = data["species_id"].lower()
    except Exception:
        return web.json_response({"error": "Missing species_id"}, status=400)

    # Check study level
    stats = await db.get_or_create_user_stats(user_id, guild_id)
    if stats.get("level", 0) < config.PET_UNLOCK_LEVEL:
        return web.json_response({
            "error": f"You must reach Study Level {config.PET_UNLOCK_LEVEL} before adopting pets."
        }, status=403)

    result = await db.buy_pet(user_id, guild_id, species_id)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Purchase failed")}, status=400)

    return web.json_response({"status": "ok", "message": f"Adopted {species_id.capitalize()}!"})


@require_auth
async def api_equip_pet(request: web.Request) -> web.Response:
    """Equip an owned companion."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        species_id = data["species_id"].lower()
    except Exception:
        return web.json_response({"error": "Missing or invalid species_id"}, status=400)

    success = await db.equip_pet(user_id, guild_id, species_id)
    if not success:
        return web.json_response({"error": "Failed to equip pet."}, status=400)

    return web.json_response({"status": "ok", "message": "Pet equipped!"})


@require_auth
async def api_rename_pet(request: web.Request) -> web.Response:
    """Rename equipped or owned companion."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        species_id = data["species_id"].lower()
        new_name = data["nickname"].strip()
    except Exception:
        return web.json_response({"error": "Missing species_id or nickname"}, status=400)

    if len(new_name) < 1 or len(new_name) > 32:
        return web.json_response({"error": "Nickname must be between 1 and 32 characters"}, status=400)

    success = await db.rename_pet(user_id, guild_id, species_id, new_name)
    if not success:
        return web.json_response({"error": "Failed to rename pet"}, status=400)

    return web.json_response({"status": "ok", "nickname": new_name})


@require_auth
async def api_feed_pet(request: web.Request) -> web.Response:
    """Feed treats to equipped companion to award pet XP & trigger evolutions."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    bot = request.app.get("bot")

    try:
        data = await request.json()
        food_id = data["food_id"]
        count = int(data.get("count", 1))
    except Exception:
        return web.json_response({"error": "Missing food_id or count"}, status=400)

    result = await db.feed_pet(user_id, guild_id, food_id, qty=count)
    if not result.get("success"):
        reason = result.get("message") or result.get("reason", "Feeding failed")
        if reason == "not_owned":
            reason = "You do not own this treat! Buy it from the Bakery below."
        elif reason == "no_pet_equipped":
            reason = "No pet equipped to feed!"
        return web.json_response({"error": reason}, status=400)

    # If leveled up or evolved, dispatch Discord alert to #notifs
    if result.get("evolved") or result.get("leveled_up"):
        if bot:
            request.app.loop.create_task(
                notify_pet_progress(bot, guild_id, user_id, result)
            )

    return web.json_response({"status": "ok", "result": result})


async def api_get_food_catalog(request: web.Request) -> web.Response:
    """Catalog of pet nutrition and treats."""
    foods = []
    for f_id, f_data in food_utils.FOODS.items():
        tier = f_data.get("tier", "snack")
        foods.append({
            "id": f_id,
            "name": f_data["name"],
            "tier": tier,
            "cost": f_data["cost"],
            "price": f_data["cost"],
            "xp_yield": f_data["xp"],
            "sprite": f_data.get("sprite", ""),
            "emoji": "🍎" if "apple" in f_id else "🥖" if "baguette" in f_id else "🍞" if "bread" in f_id else "🥩" if "meat" in f_id or "steak" in f_id else "🍕" if "pizza" in f_id else "🧁",
            "description": f"Grants +{f_data['xp']} Pet XP ({tier.title()})",
        })
    return web.json_response({"foods": foods})


@require_auth
async def api_buy_food(request: web.Request) -> web.Response:
    """Buy pet food from shop."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        food_id = data["food_id"]
        count = int(data.get("count", 1))
    except Exception:
        return web.json_response({"error": "Invalid food_id or count"}, status=400)

    result = await db.buy_food(user_id, guild_id, food_id, qty=count)
    if not result.get("success"):
        reason = result.get("message") or result.get("reason", "Purchase failed")
        if reason == "insufficient_funds":
            reason = "Insufficient coins to purchase this treat!"
        return web.json_response({"error": reason}, status=400)

    return web.json_response({"status": "ok", "message": f"Purchased {count}x {food_id}!"})


# ===================================================================== #
# 6. Economy, Shop & Mini-Games
# ===================================================================== #

@require_auth
async def api_get_economy(request: web.Request) -> web.Response:
    """Fetch wallet, inventory, active buffs, and claim cooldowns."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]

    currency = await db.get_or_create_currency(user_id, guild_id)
    inventory = await db.get_inventory(user_id, guild_id)
    
    # Active effects
    now = int(time.time())
    active_boosts = []
    for eff in ["xp_boost", "coin_boost"]:
        eff_data = await db.get_active_effect(user_id, guild_id, eff, now=now)
        if eff_data:
            rem = max(0, eff_data["expires_at"] - now)
            active_boosts.append({
                "effect_id": eff,
                "name": eff.replace("_", " ").title(),
                "multiplier": eff_data.get("multiplier", 2),
                "remaining_seconds": rem,
                "formatted_remaining": format_duration(rem),
            })

    # Cooldown statuses
    work_cd = await db.get_cooldown(user_id, guild_id, "work")
    beg_cd = await db.get_cooldown(user_id, guild_id, "beg")
    weekly_cd = await db.get_cooldown(user_id, guild_id, "weekly")

    def _cd_status(cd_time, max_seconds):
        if not cd_time:
            return {"ready": True, "remaining": 0}
        elapsed = now - cd_time
        rem = max(0, max_seconds - elapsed)
        return {"ready": rem == 0, "remaining": rem, "formatted": format_duration(rem)}

    # Daily status
    today = streak_utils.date_str(now)
    daily_row = await db.get_daily_status(user_id, guild_id)
    daily_claimed = daily_row and daily_row.get("last_claim_date") == today

    return web.json_response({
        "wallet": {
            "coins": currency.get("coins", 0),
            "candy": currency.get("candy", 0),
            "lifetime_earned": currency.get("lifetime_earned", 0),
        },
        "inventory": inventory,
        "active_boosts": active_boosts,
        "cooldowns": {
            "daily": {"claimed_today": bool(daily_claimed)},
            "work": _cd_status(work_cd, config.WORK_COOLDOWN_SECONDS),
            "beg": _cd_status(beg_cd, config.BEG_COOLDOWN_SECONDS),
            "weekly": _cd_status(weekly_cd, config.WEEKLY_COOLDOWN_SECONDS),
        },
    })


async def api_get_shop(request: web.Request) -> web.Response:
    """Catalog of items, boosts, and titles."""
    user = get_current_user(request)
    guild_id = int(user.get("guild_id", DEFAULT_GUILD_ID)) if user else DEFAULT_GUILD_ID
    db = request.app["db"]

    items = []
    for item_id, item_data in eco_utils.SHOP_ITEMS.items():
        if item_data.get("price", 0) > 0:
            items.append({
                "id": item_id,
                "name": item_data["name"],
                "icon": f"/assets/discord_emojis/{item_id}.png",
                "emoji": item_data.get("emoji", "🏷️"),
                "price": item_data["price"],
                "type": item_data["type"],
                "description": item_data.get("description", ""),
            })

    # Guild custom tags
    custom_tags = await db.get_custom_tags(guild_id)
    for tag in custom_tags:
        items.append({
            "id": f"tag_{tag['tag_id']}",
            "name": f"Title: {tag['name']}",
            "icon": "/assets/discord_emojis/title_scroll.png",
            "emoji": "🏷️",
            "price": tag["price"],
            "type": "title",
            "description": f"Server-exclusive title: '{tag['name']}'.",
        })

    return web.json_response({"shop_items": items})


@require_auth
async def api_buy_shop_item(request: web.Request) -> web.Response:
    """Purchase item from Chronocoin shop."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        item_id = data["item_id"]
        qty = int(data.get("qty", 1))
    except Exception:
        return web.json_response({"error": "Invalid item_id or qty"}, status=400)

    result = await db.buy_item(user_id, guild_id, item_id, qty)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Purchase failed")}, status=400)

    return web.json_response({"status": "ok", "message": result.get("message", "Item purchased!")})


@require_auth
async def api_use_item(request: web.Request) -> web.Response:
    """Use / consume item from satchel (e.g. Mystery Box, XP Boost)."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        item_id = data["item_id"]
    except Exception:
        return web.json_response({"error": "Missing item_id"}, status=400)

    # Handle Mystery Box
    if item_id == "mystery_box":
        qty = await db.get_item_qty(user_id, guild_id, "mystery_box")
        if qty <= 0:
            return web.json_response({"error": "You don't have any Mystery Boxes."}, status=400)
        now = int(time.time())
        res = await db.open_mystery_box(user_id, guild_id, now=now)
        return web.json_response({"status": "ok", "type": "mystery_box", "reward": res})

    # Handle Boosts
    if item_id in ("xp_boost", "coin_boost", "sugar_rush"):
        now = int(time.time())
        res = await db.use_boost_item(user_id, guild_id, item_id, now=now)
        if not res.get("success"):
            return web.json_response({"error": res.get("message", "Failed to activate boost")}, status=400)
        return web.json_response({"status": "ok", "type": "boost", "result": res})

    return web.json_response({"error": "Item cannot be directly used."}, status=400)


@require_auth
async def api_set_title(request: web.Request) -> web.Response:
    """Equip an unlocked profile title."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        title = data.get("title")
    except Exception:
        return web.json_response({"error": "Missing title"}, status=400)

    await db.set_equipped_title(user_id, guild_id, title)
    return web.json_response({"status": "ok", "equipped_title": title})


@require_auth
async def api_claim_daily(request: web.Request) -> web.Response:
    """Claim once-per-day streak reward."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    now = int(time.time())

    result = await db.claim_daily(user_id, guild_id, now=now)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Daily reward not ready.")}, status=400)

    return web.json_response({"status": "ok", "daily": result})


@require_auth
async def api_claim_work(request: web.Request) -> web.Response:
    """Quick mini-task for extra Chronocoins & XP."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    now = int(time.time())

    result = await db.claim_work(user_id, guild_id, now=now)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Work is on cooldown.")}, status=400)

    return web.json_response({"status": "ok", "work": result})


@require_auth
async def api_claim_beg(request: web.Request) -> web.Response:
    """Flavorful beggar mini-game."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    now = int(time.time())

    result = await db.claim_beg(user_id, guild_id, now=now)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Beg is on cooldown.")}, status=400)

    return web.json_response({"status": "ok", "beg": result})


@require_auth
async def api_claim_weekly(request: web.Request) -> web.Response:
    """Claim weekly jackpot payout."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    now = int(time.time())

    result = await db.claim_weekly(user_id, guild_id, now=now)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Weekly reward is on cooldown.")}, status=400)

    return web.json_response({"status": "ok", "weekly": result})


# ===================================================================== #
# 7. Halloween Seasonal Hub
# ===================================================================== #

@require_auth
async def api_get_halloween(request: web.Request) -> web.Response:
    """Halloween event pass progress, Hallo-Boxes, and Candy Shop."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]

    pass_data = await db.get_or_create_halloween_pass(user_id, guild_id)
    cur_lvl = hallo_utils.get_current_pass_level(pass_data.get("study_seconds", 0))
    next_lvl = hallo_utils.get_next_pass_level(pass_data.get("study_seconds", 0))
    enriched_pass = {
        **pass_data,
        "current_level": cur_lvl,
        "next_level": next_lvl,
        "study_minutes": round(pass_data.get("study_seconds", 0) / 60, 1),
    }

    inv = await db.get_inventory(user_id, guild_id)
    
    # Filter owned boxes
    hallo_boxes = {}
    for b_id, b_info in hallo_utils.HALLO_BOXES.items():
        qty = inv.get(b_id, 0)
        hallo_boxes[b_id] = {
            "id": b_id,
            "name": b_info["name"],
            "tier": b_info["tier"],
            "emoji": b_info["emoji"],
            "count": qty,
            "color": b_info["color"],
            "description": b_info["description"],
        }

    # Spooky Candy Shop items
    candy_items = []
    for item_id, item_data in hallo_utils.CANDY_SHOP_ITEMS.items():
        candy_items.append({
            "id": item_id,
            "name": item_data["name"],
            "candy_price": item_data.get("candy_price", item_data.get("price", 0)),
            "emoji": item_data["emoji"],
            "type": item_data["type"],
            "description": item_data["description"],
        })

    return web.json_response({
        "pass": enriched_pass,
        "stages": hallo_utils.JACK_O_LANTERN_LEVELS,
        "boxes": hallo_boxes,
        "candy_shop": candy_items,
    })


@require_auth
async def api_open_hallo_box(request: web.Request) -> web.Response:
    """Instant unbox Hallo-Boxes (Common -> Legendary)."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        box_tier = data["tier"]  # e.g. "hbox_common" or "common"
        count = int(data.get("count", 1))
    except Exception:
        return web.json_response({"error": "Missing box tier"}, status=400)

    now = int(time.time())
    result = await db.open_hallo_box(user_id, guild_id, box_tier, count, now=now)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Failed to open box")}, status=400)

    return web.json_response({"status": "ok", "loot": result})


@require_auth
async def api_claim_pass_rewards(request: web.Request) -> web.Response:
    """Claim milestone loot from Jack-o'-Lantern season pass."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]

    result = await db.claim_all_halloween_rewards(user_id, guild_id)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "No unclaimed rewards available.")}, status=400)

    return web.json_response({"status": "ok", "claimed": result})


@require_auth
async def api_buy_candy_item(request: web.Request) -> web.Response:
    """Spend Candy on event-exclusive pets, titles & boosts."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        item_id = data["item_id"]
    except Exception:
        return web.json_response({"error": "Missing item_id"}, status=400)

    result = await db.buy_candy_item(user_id, guild_id, item_id)
    if not result.get("success"):
        return web.json_response({"error": result.get("message", "Candy purchase failed")}, status=400)

    return web.json_response({"status": "ok", "message": result.get("message", "Item purchased with Candy!")})


# ===================================================================== #
# 8. Chronotes (Notebook Suite)
# ===================================================================== #

@require_auth
async def api_get_notes(request: web.Request) -> web.Response:
    """Get all study notes with optional subject and query filtering."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    subject = request.query.get("subject")
    query = request.query.get("q")

    notes = await db.get_user_notes(user_id, guild_id, subject=subject, search=query)
    stats = await db.get_note_stats(user_id, guild_id)
    return web.json_response({"notes": notes, "stats": stats})


@require_auth
async def api_create_note(request: web.Request) -> web.Response:
    """Create a new study note."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        title = data["title"].strip()
        content = data["content"].strip()
        subject = data.get("subject", "General").strip()
        pinned = bool(data.get("pinned", False))
    except Exception:
        return web.json_response({"error": "Invalid note payload"}, status=400)

    if not title:
        return web.json_response({"error": "Note title is required"}, status=400)

    note_id = await db.create_note(user_id, guild_id, title, content, subject, is_pinned=pinned)
    return web.json_response({"status": "ok", "note_id": note_id})


@require_auth
async def api_update_note(request: web.Request) -> web.Response:
    """Update existing study note."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    note_id = int(request.match_info["id"])
    try:
        data = await request.json()
        title = data["title"].strip()
        content = data["content"].strip()
        subject = data.get("subject", "General").strip()
        pinned = bool(data.get("pinned", False))
    except Exception:
        return web.json_response({"error": "Invalid note payload"}, status=400)

    success = await db.update_note(note_id, user_id, title=title, content=content, subject=subject, is_pinned=1 if pinned else 0)
    if not success:
        return web.json_response({"error": "Note not found or unauthorized"}, status=404)

    return web.json_response({"status": "ok", "note_id": note_id})


@require_auth
async def api_delete_note(request: web.Request) -> web.Response:
    """Delete a note."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    note_id = int(request.match_info["id"])

    success = await db.delete_note(note_id, user_id)
    if not success:
        return web.json_response({"error": "Note not found or unauthorized"}, status=404)

    return web.json_response({"status": "ok", "message": "Note deleted"})


# ===================================================================== #
# 9. JEE Trivia & Practice Hub
# ===================================================================== #

@require_auth
async def api_get_trivia_question(request: web.Request) -> web.Response:
    """Fetch next JEE practice / trivia question from CJA API or cached pool."""
    db = request.app["db"]
    subject = request.query.get("subject")

    # Try cached questions first
    cached = await db.pop_cached_question(subject=subject)
    if cached:
        return web.json_response({"question": cached})

    # Fallback to CJA client
    try:
        from services.cja import cja_client
        q_raw = await cja_client.get_question(subject=subject)
        if q_raw and "question" in q_raw:
            subj_name = q_raw.get("subject", {}).get("name", "Physics") if isinstance(q_raw.get("subject"), dict) else "Physics"
            ch_name = q_raw.get("chapter", {}).get("name", "JEE Practice") if isinstance(q_raw.get("chapter"), dict) else "General"
            return web.json_response({
                "question": {
                    "id": str(q_raw.get("id")),
                    "subject": subj_name.lower(),
                    "chapter": ch_name,
                    "question": q_raw.get("question", ""),
                    "options": q_raw.get("options", []),
                    "correct_index": 0,
                    "explanation": "Answer evaluation synchronized with CJA.",
                }
            })
    except Exception as exc:
        log.warning(f"Failed to fetch live CJA question: {exc}")

    # Fallback static sample question for instant testing
    fallback = {
        "id": "sample_101",
        "subject": "physics",
        "chapter": "Work, Energy and Power",
        "question": "A body of mass 2 kg moving with velocity 4 m/s collides head-on elastically with another body of mass 2 kg at rest. What is the velocity of the first body after collision?",
        "options": ["4 m/s", "0 m/s", "2 m/s", "-2 m/s"],
        "correct_index": 1,
        "explanation": "In an elastic head-on collision between two equal masses, velocities are completely exchanged. Since the second body was at rest (0 m/s), the first body comes to rest (0 m/s).",
    }
    return web.json_response({"question": fallback})


@require_auth
async def api_submit_trivia_answer(request: web.Request) -> web.Response:
    """Submit MCQ answer and evaluate (+4/-1 scoring + coin/XP reward)."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]
    try:
        data = await request.json()
        question_id = str(data["question_id"])
        selected_index = int(data["selected_index"])
        correct_index = int(data.get("correct_index", -1))
    except Exception:
        return web.json_response({"error": "Invalid answer submission"}, status=400)

    is_correct = False
    explanation = ""

    # Evaluate via CJA API if live question
    if question_id and not question_id.startswith("sample_"):
        try:
            from services.cja import cja_client
            res = await cja_client.check_answer(question_id, answer=selected_index)
            is_correct = bool(res.get("correct"))
            explanation = res.get("explanation", "")
        except Exception:
            is_correct = selected_index == correct_index
    else:
        is_correct = selected_index == correct_index

    score_delta = 4 if is_correct else -1
    coins_awarded = 25 if is_correct else 0
    xp_awarded = 35 if is_correct else 5

    await db.record_trivia_attempt(user_id, guild_id, is_correct)
    if coins_awarded > 0:
        await db.add_coins(user_id, guild_id, coins_awarded)
    await db.grant_xp(user_id, guild_id, xp_awarded)

    stats = await db.get_or_create_trivia_stats(user_id, guild_id)

    return web.json_response({
        "is_correct": is_correct,
        "score_delta": score_delta,
        "coins_awarded": coins_awarded,
        "xp_awarded": xp_awarded,
        "explanation": explanation,
        "stats": stats,
    })


@require_auth
async def api_get_trivia_stats(request: web.Request) -> web.Response:
    """Get personal trivia stats and ranking."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]

    stats = await db.get_or_create_trivia_stats(user_id, guild_id)
    rank = await db.get_user_trivia_rank(user_id, guild_id)
    leaderboard = await db.get_trivia_leaderboard(guild_id)

    return web.json_response({
        "stats": stats,
        "rank": rank,
        "leaderboard": leaderboard,
    })


# ===================================================================== #
# 10. Achievements Catalog & Unlocks
# ===================================================================== #

@require_auth
async def api_get_achievements(request: web.Request) -> web.Response:
    """Get all server achievements grouped by category with unlock status."""
    user_id, guild_id = _user_ctx(request)
    db = request.app["db"]

    unlocked_detailed = await db.get_unlocked_achievements_detailed(user_id, guild_id)
    unlocked_map = {a["achievement_id"]: a["unlocked_at"] for a in unlocked_detailed}

    grouped: dict[str, list] = {}
    for ach in ach_utils.ACHIEVEMENTS:
        cat = ach.category
        if cat not in grouped:
            grouped[cat] = []
        is_unlocked = ach.id in unlocked_map

        cat_lower = cat.lower()
        if "time" in cat_lower or "hour" in cat_lower:
            icon = "/assets/icons/focus_clock_64.png"
        elif "session" in cat_lower:
            icon = "/assets/icons/chrono_clock_64.png"
        elif "streak" in cat_lower:
            icon = "/assets/discord_emojis/chronos_streak.png"
        elif "coin" in cat_lower or "economy" in cat_lower:
            icon = "/assets/discord_emojis/chronocoin.png"
        elif "halloween" in cat_lower:
            icon = "/assets/discord_emojis/halloween_candy.png"
        elif "level" in cat_lower or "tier" in cat_lower:
            icon = "/assets/discord_emojis/trophy.png"
        elif "pet" in cat_lower:
            icon = "/assets/icons/potion_flask_32.png"
        else:
            icon = "/assets/icons/achievement_trophy_64.png"

        grouped[cat].append({
            "id": ach.id,
            "name": ach.name,
            "icon": icon,
            "emoji": ach.emoji,
            "description": ach.description,
            "reward_coins": ach.reward_coins,
            "unlocked": is_unlocked,
            "unlocked_at": unlocked_map.get(ach.id),
        })

    total_count = len(ach_utils.ACHIEVEMENTS)
    unlocked_count = len(unlocked_map)
    pct = round((unlocked_count / total_count * 100), 1) if total_count > 0 else 0

    return web.json_response({
        "total_count": total_count,
        "unlocked_count": unlocked_count,
        "completion_percentage": pct,
        "categories": grouped,
    })
