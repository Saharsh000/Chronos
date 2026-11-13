"""Stats, profile, leaderboard, compare, hall of fame, achievements, dashboard -
the website twin of cogs/stats.py, cogs/social.py and cogs/achievements.py.

Read-only except that, like the bot, viewing achievements first runs a fresh
`check_achievements` so anything earned-but-unrecorded shows up."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from typing import Any, Optional

from aiohttp import web

import config
from utils import xp as xp_utils
from utils.achievements import ACHIEVEMENTS, ACHIEVEMENTS_BY_ID, CATEGORY_ORDER
from utils.subjects import SUBJECT_ALIASES, SUBJECT_INFO, SUBJECTS

from cogs.social import COMPARE_CATEGORIES, HOF_CATEGORIES
from .common import Ctx, Routes, fail, level_block, period_start, period_totals, subject_card, tier_key

log = logging.getLogger("web.stats")
routes = Routes()

PERIODS = {"today": "today", "day": "today", "daily": "today", "week": "week", "weekly": "week",
           "month": "month", "monthly": "month", "all": "alltime", "alltime": "alltime",
           "all-time": "alltime", "total": "alltime"}
PERIOD_LABELS = {"today": "Today", "week": "This week", "month": "This month", "alltime": "All time"}
# how the page should format each value
HOF_FORMAT = {"total_time": "duration", "level": "int", "longest_streak": "days", "sessions": "int",
              "longest_session": "duration", "richest": "coins", "achievements": "int",
              "subject_physics": "duration", "subject_chemistry": "duration", "subject_maths": "duration"}
COMPARE_FORMAT = {"total_seconds": "duration", "level": "int", "xp": "int", "sessions_count": "int",
                  "current_streak": "days", "longest_streak": "days", "avg_session_seconds": "duration",
                  "longest_session_seconds": "duration", "lifetime_earned": "int", "achievements_count": "int",
                  "physics_seconds": "duration", "chemistry_seconds": "duration", "maths_seconds": "duration"}
WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


# ---------------------------------------------------------------------- #
# helpers
# ---------------------------------------------------------------------- #
def target_of(c: Ctx, key: str = "user") -> int:
    raw = c.q(key)
    if not raw or raw in ("me", "@me"):
        return c.uid
    if not raw.isdigit():
        raise fail("That isn't a valid member.", 400, "bad_member")
    uid = int(raw)
    if uid != c.uid and not c.bridge.is_member(c.gid, uid):
        raise fail("I couldn't find that member in this server.", 404, "no_member")
    return uid


async def rank_of(db, gid: int, uid: int) -> Optional[int]:
    totals = await db.get_alltime_totals(gid)
    ranking = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return next((i + 1 for i, (u, _) in enumerate(ranking) if u == uid), None)


async def live_session_extra(db, uid: int, gid: int) -> tuple[Optional[dict], int]:
    s = await db.get_active_session(uid, gid)
    if not s:
        return None, 0
    now = int(time.time())
    return s, max(0, (now - s["start_time"]) - s["credited_seconds"])


def trivia_tier_of(stats: dict) -> dict:
    from cogs.trivia import get_trivia_tier
    t = get_trivia_tier(stats.get("total_marks", 0))
    t["min_marks"] = t.get("cur_min", 0)
    return t


async def build_profile(c: Ctx, uid: int) -> dict[str, Any]:
    """Everything `.stats` shows (all four pages), as data."""
    db, gid = c.db, c.gid
    stats = await db.get_or_create_user_stats(uid, gid)
    currency = await db.get_or_create_currency(uid, gid)
    unlocked = await db.get_unlocked_achievement_ids(uid, gid)
    analytics = await db.get_session_analytics(uid, gid)
    weekly = await db.get_weekly_daily_breakdown(uid, gid)
    sub_details = await db.get_detailed_subject_breakdown(uid, gid)
    sub_seconds = await db.get_subject_stats(uid, gid)
    trivia = await db.get_or_create_trivia_stats(uid, gid)
    trivia_rank = await db.get_user_trivia_rank(uid, gid)
    pet = await db.get_equipped_pet(uid, gid)

    session, live = await live_session_extra(db, uid, gid)
    in_session = None
    if session:
        in_session = int(time.time()) - session["start_time"]
        if session.get("subject"):
            sub_seconds[session["subject"]] = sub_seconds.get(session["subject"], 0) + live
        for d in weekly["days"]:
            if d["is_today"]:
                was_empty = d["seconds"] <= 0
                d["seconds"] += live
                weekly["total_week_seconds"] += live
                if was_empty and d["seconds"] > 0:
                    weekly["active_days_count"] += 1
                if d["seconds"] > weekly["peak_day_seconds"]:
                    weekly["peak_day_seconds"], weekly["peak_day_name"] = d["seconds"], d["day_name"]
                break
    for k, secs in sub_seconds.items():
        row = sub_details.setdefault(k, {"session_count": 0, "avg_seconds": 0, "total_seconds": 0})
        row["total_seconds"] = max(row.get("total_seconds", 0), secs)

    today = (await period_totals(db, gid, "today")).get(uid, 0)
    week = (await period_totals(db, gid, "week")).get(uid, 0)
    lvl = await level_block(c, stats["xp"])
    t_tier = trivia_tier_of(trivia)
    pet_out = None
    if pet:
        pet_out = {"species_id": pet["species_id"], "nickname": pet.get("nickname"), "level": pet["level"], "xp": pet["xp"]}

    return {
        "user": {**c.person(uid), "me": uid == c.uid},
        "level": lvl,
        "rank_position": await rank_of(db, gid, uid),
        "equipped_title": stats.get("equipped_title"),
        "equipped_pet": pet_out,
        "total_seconds": stats["total_seconds"] + live,
        "today_seconds": today, "week_seconds": week,
        "sessions_count": stats["sessions_count"],
        "streak": {"current": stats["current_streak"], "longest": stats["longest_streak"]},
        "wallet": {"coins": currency["coins"], "candy": currency.get("candy", 0),
                   "lifetime_earned": currency["lifetime_earned"]},
        "in_session_seconds": in_session,
        "in_session_subject": subject_card(session.get("subject")) if session else None,
        "achievements": {"unlocked": len(unlocked), "total": len(ACHIEVEMENTS)},
        "analytics": {
            "sessions_logged": analytics["sessions_logged"],
            "avg_session_seconds": analytics["avg_session_seconds"],
            "longest_session_seconds": analytics["longest_session_seconds"],
            "favorite_subject": subject_card(analytics["favorite_subject"]),
            "weekdays": [{"day": WEEKDAYS[i], "short": WEEKDAYS[i][:3], "seconds": analytics["weekday_seconds"].get(i, 0)}
                         for i in (1, 2, 3, 4, 5, 6, 0)],
        },
        "weekly": weekly,
        "subjects": [{**subject_card(k), "seconds": sub_seconds.get(k, 0), **{
            "sessions": sub_details.get(k, {}).get("session_count", 0),
            "avg_seconds": sub_details.get(k, {}).get("avg_seconds", 0)}} for k in SUBJECTS],
        "trivia": {
            "attempted": trivia.get("questions_attempted", 0), "correct": trivia.get("questions_correct", 0),
            "marks": trivia.get("total_marks", 0), "rank": trivia_rank[0], "players": trivia_rank[1],
            "title": t_tier.get("title"), "badge": t_tier.get("badge"), "next_title": t_tier.get("next_title"),
            "next_marks": t_tier.get("next_marks"), "min_marks": t_tier.get("min_marks"),
        },
    }


# ---------------------------------------------------------------------- #
# profile / rank / subjects / card
# ---------------------------------------------------------------------- #
@routes.get("/api/profile")
async def profile(c: Ctx):
    return await build_profile(c, target_of(c))


@routes.get("/api/users/{id}")
async def user_profile(c: Ctx):
    uid = c.request.match_info["id"]
    if not uid.isdigit():
        raise fail("That isn't a valid member.", 400, "bad_member")
    if int(uid) != c.uid and not c.bridge.is_member(c.gid, int(uid)):
        raise fail("I couldn't find that member in this server.", 404, "no_member")
    return await build_profile(c, int(uid))


@routes.get("/api/rank")
async def rank(c: Ctx):
    """`.rank` - level, tier, server position, progress to next level."""
    uid = target_of(c)
    stats = await c.db.get_or_create_user_stats(uid, c.gid)
    lvl = await level_block(c, stats["xp"])
    return {"user": c.person(uid), "level": lvl, "rank_position": await rank_of(c.db, c.gid, uid),
            "to_next": lvl["needed"] - lvl["into"]}


@routes.get("/api/subjects")
async def subjects(c: Ctx):
    """`.subjects` - per-subject time (live session included)."""
    uid = target_of(c)
    totals = await c.db.get_subject_stats(uid, c.gid)
    s, live = await live_session_extra(c.db, uid, c.gid)
    if s and s.get("subject"):
        totals[s["subject"]] = totals.get(s["subject"], 0) + live
    return {"user": c.person(uid), "subjects": [{**subject_card(k), "seconds": totals.get(k, 0)} for k in SUBJECTS]}


@routes.get("/api/stats/card.png")
async def stats_card(c: Ctx):
    """The same PNG cards `.stats` pages through (?page=overview|weekly|subjects|trivia)."""
    from utils import stats_card as sc
    uid = target_of(c)
    page = c.q("page", "overview")
    if page not in ("overview", "weekly", "subjects", "trivia"):
        raise fail("Unknown card page.", 400, "bad_page")
    p = await build_profile(c, uid)
    m = c.bridge.member(c.gid, uid)
    avatar = await c.bridge.avatar_bytes(c.gid, uid)
    lvl = p["level"]
    details = {s["key"]: {"session_count": s["sessions"], "avg_seconds": s["avg_seconds"], "total_seconds": s["seconds"]}
               for s in p["subjects"]}
    loop = asyncio.get_running_loop()
    try:
        if page == "overview":
            pet = None
            if p["equipped_pet"]:
                pet = await c.db.get_equipped_pet(uid, c.gid)
            png = await loop.run_in_executor(None, lambda: sc.render_overview_card_sync(
                display_name=m["name"], username=m["username"], tier_name=lvl["tier"], level=lvl["level"],
                xp_into=lvl["into"], xp_needed=lvl["needed"], total_xp=lvl["xp"], coins=p["wallet"]["coins"],
                candy=p["wallet"]["candy"], total_seconds=p["total_seconds"], today_seconds=p["today_seconds"],
                week_seconds=p["week_seconds"], streak_days=p["streak"]["current"], longest_streak=p["streak"]["longest"],
                sessions_count=p["sessions_count"], unlocked_achievements=p["achievements"]["unlocked"],
                total_achievements=p["achievements"]["total"], rank_position=p["rank_position"],
                equipped_title=p["equipped_title"], equipped_pet=pet,
                subject_seconds={s["key"]: s["seconds"] for s in p["subjects"]},
                in_session_seconds=p["in_session_seconds"], avatar_bytes=avatar))
        elif page == "weekly":
            png = await loop.run_in_executor(None, lambda: sc.render_weekly_card_sync(
                display_name=m["name"], username=m["username"], tier_name=lvl["tier"],
                weekly_breakdown=p["weekly"], avatar_bytes=avatar))
        elif page == "subjects":
            png = await loop.run_in_executor(None, lambda: sc.render_subjects_card_sync(
                display_name=m["name"], username=m["username"], tier_name=lvl["tier"],
                subject_details=details, avatar_bytes=avatar))
        else:
            ts = await c.db.get_or_create_trivia_stats(uid, c.gid)
            rk = await c.db.get_user_trivia_rank(uid, c.gid)
            png = await loop.run_in_executor(None, lambda: sc.render_trivia_card_sync(
                display_name=m["name"], username=m["username"], tier_name=lvl["tier"], trivia_stats=ts,
                rank_info=rk, tier_info=trivia_tier_of(ts), avatar_bytes=avatar))
    except Exception:
        log.exception("stats card render failed")
        raise fail("I couldn't draw that card right now.", 500, "render")
    return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------- #
# leaderboard
# ---------------------------------------------------------------------- #
@routes.get("/api/leaderboard")
async def leaderboard(c: Ctx):
    period = PERIODS.get((c.q("period") or "alltime").lower())
    if not period:
        raise fail("Unknown period. Try today, week, month or alltime.", 400, "bad_period")
    subject = None
    if c.q("subject"):
        subject = SUBJECT_ALIASES.get(c.q("subject").lower().strip())
        if not subject:
            raise fail("Unknown subject. Try physics, chemistry or maths.", 400, "bad_subject")
    totals = await period_totals(c.db, c.gid, period, subject)
    ranking = [(u, s) for u, s in sorted(totals.items(), key=lambda kv: kv[1], reverse=True) if s > 0]
    live = {s["user_id"]: s for s in await c.db.get_active_sessions_for_guild(c.gid)}
    tiers = await c.tiers()
    limit = min(int(c.q("limit", "50") or 50), 100)
    entries = []
    for i, (uid, secs) in enumerate(ranking[:limit]):
        st = await c.db.get_or_create_user_stats(uid, c.gid)
        _, _, lv = xp_utils.xp_progress(st.get("xp", 0))
        tn = xp_utils.tier_for_level(lv, tiers)
        entries.append({**c.person(uid), "rank": i + 1, "seconds": secs, "level": lv, "tier": tn,
                        "tier_key": tier_key(tn), "me": uid == c.uid,
                        "studying_since": live[uid]["start_time"] if uid in live else None})
    me_pos = next((i + 1 for i, (u, _) in enumerate(ranking) if u == c.uid), None)
    return {"period": period, "period_label": PERIOD_LABELS[period], "subject": subject_card(subject),
            "entries": entries, "total": len(ranking), "me": {"rank": me_pos, "seconds": totals.get(c.uid, 0)},
            "now": int(time.time())}


# ---------------------------------------------------------------------- #
# hall of fame + compare
# ---------------------------------------------------------------------- #
@routes.get("/api/halloffame")
async def hall_of_fame(c: Ctx):
    hof = await c.db.get_hall_of_fame(c.gid)
    out = []
    for key, label, _fmt in HOF_CATEGORIES:
        rec = hof.get(key)
        out.append({"key": key, "label": label.split(" ", 1)[1] if " " in label else label, "format": HOF_FORMAT[key],
                    "holder": c.person(rec["user_id"]) if rec else None, "value": rec["value"] if rec else None})
    # Mirrors Database.claim_top3_daily_perk (the first action of each IST day).
    perks = {1: ("Sovereign's Dawn Blessing", 120, "Ancient Mystery Chest", "+100% XP & coins for 2 hours"),
             2: ("Ascendant's Dawn Grace", 80, "Glacial Streak Freeze", "+100% XP for 1.5 hours"),
             3: ("Vanguard's Dawn Resolve", 50, "Bottle o' XP Elixir", "+100% coins for 1 hour")}
    top3 = await c.db.get_top3_members(c.gid)
    return {"records": out, "top3": [
        {"rank": i + 1, "holder": c.person(u), "seconds": secs, "perk": perks[i + 1][0], "coins": perks[i + 1][1],
         "item": perks[i + 1][2], "boost": perks[i + 1][3]} for i, (u, secs) in enumerate(top3)]}


@routes.get("/api/compare")
async def compare(c: Ctx):
    a = target_of(c, "a")
    if not c.q("b"):
        raise fail("Pick someone to compare with.", 400, "missing_b")
    b = target_of(c, "b")
    if a == b:
        raise fail("Pick two different people to compare.", 400, "same_member")
    ca, cb = await c.db.get_compare_context(a, c.gid), await c.db.get_compare_context(b, c.gid)
    rows, wa, wb = [], 0, 0
    for label, key, _fmt in COMPARE_CATEGORIES:
        va, vb = ca[key], cb[key]
        winner = "a" if va > vb else "b" if vb > va else None
        wa += winner == "a"
        wb += winner == "b"
        rows.append({"key": key, "label": label, "format": COMPARE_FORMAT[key], "a": va, "b": vb, "winner": winner})
    return {"a": c.person(a), "b": c.person(b), "rows": rows, "wins": {"a": wa, "b": wb},
            "verdict": "a" if wa > wb else "b" if wb > wa else "tie"}


# ---------------------------------------------------------------------- #
# achievements
# ---------------------------------------------------------------------- #
@routes.get("/api/achievements")
async def achievements(c: Ctx):
    uid = target_of(c)
    await c.db.check_achievements(uid, c.gid)   # like the bot: surface anything freshly earned
    rows = await c.db.get_unlocked_achievements_detailed(uid, c.gid)
    at = {r["achievement_id"]: r["unlocked_at"] for r in rows}
    cats = []
    for cat in CATEGORY_ORDER:
        items = [a for a in ACHIEVEMENTS if a.category == cat]
        cats.append({"name": cat, "unlocked": sum(1 for a in items if a.id in at), "total": len(items),
                     "items": [{"id": a.id, "name": a.name, "emoji": a.emoji, "description": a.description,
                                "reward_coins": a.reward_coins, "unlocked": a.id in at,
                                "unlocked_at": at.get(a.id)} for a in items]})
    recent = [{"id": i, "name": ACHIEVEMENTS_BY_ID[i].name, "emoji": ACHIEVEMENTS_BY_ID[i].emoji, "at": t}
              for i, t in sorted(at.items(), key=lambda kv: kv[1], reverse=True)[:5] if i in ACHIEVEMENTS_BY_ID]
    return {"user": c.person(uid), "unlocked": len(at), "total": len(ACHIEVEMENTS), "categories": cats, "recent": recent}


# ---------------------------------------------------------------------- #
# history / heat-map / members / dashboard
# ---------------------------------------------------------------------- #
@routes.get("/api/sessions/history")
async def history(c: Ctx):
    uid = target_of(c)
    limit = max(1, min(int(c.q("limit", "20") or 20), 100))
    before = c.q("before")
    q = ("SELECT log_id, subject, start_time, end_time, duration_seconds, xp_earned, end_reason "
         "FROM session_log WHERE user_id = ? AND guild_id = ?")
    params: list[Any] = [uid, c.gid]
    if before and before.isdigit():
        q += " AND log_id < ?"
        params.append(int(before))
    q += " ORDER BY log_id DESC LIMIT ?"
    params.append(limit + 1)
    cur = await c.db.conn.execute(q, params)
    rows = [dict(r) for r in await cur.fetchall()]
    more = len(rows) > limit
    rows = rows[:limit]
    return {"sessions": [{"id": r["log_id"], "subject": subject_card(r["subject"]), "start": r["start_time"],
                          "end": r["end_time"], "duration": r["duration_seconds"], "xp": r["xp_earned"],
                          "reason": r["end_reason"]} for r in rows],
            "next": rows[-1]["log_id"] if more and rows else None}


async def daily_seconds(c: Ctx, uid: int, days: int) -> dict[str, int]:
    since = int((dt.datetime.now(config.IST) - dt.timedelta(days=days - 1))
                .replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    cur = await c.db.conn.execute(
        "SELECT strftime('%Y-%m-%d', start_time, 'unixepoch', ?) AS d, SUM(duration_seconds) AS s "
        "FROM session_log WHERE user_id = ? AND guild_id = ? AND start_time >= ? GROUP BY d",
        (config.IST_SQL_MODIFIER, uid, c.gid, since))
    out = {r["d"]: r["s"] for r in await cur.fetchall()}
    s, _ = await live_session_extra(c.db, uid, c.gid)
    if s:   # in-progress session isn't in session_log yet
        today = dt.datetime.now(config.IST).strftime("%Y-%m-%d")
        midnight = period_start("today")
        out[today] = out.get(today, 0) + max(0, int(time.time()) - max(s["start_time"], midnight))
    return out


@routes.get("/api/heatmap")
async def heatmap(c: Ctx):
    uid = target_of(c)
    days = max(7, min(int(c.q("days", "120") or 120), 366))
    m = await daily_seconds(c, uid, days)
    today = dt.datetime.now(config.IST).date()
    series = []
    for i in range(days - 1, -1, -1):
        d = today - dt.timedelta(days=i)
        series.append({"date": d.isoformat(), "weekday": d.weekday(), "seconds": m.get(d.isoformat(), 0)})
    return {"days": series, "max": max([s["seconds"] for s in series] or [0])}


@routes.get("/api/members")
async def members(c: Ctx):
    """Members with stats in this server (for pickers/search)."""
    q = (c.q("q") or "").strip().lower()
    limit = max(1, min(int(c.q("limit", "25") or 25), 100))
    totals = await c.db.get_alltime_totals(c.gid)
    out = []
    for uid, secs in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        if not c.bridge.is_member(c.gid, uid):
            continue
        p = c.person(uid)
        if q and q not in p["name"].lower() and q != str(uid):
            continue
        out.append({**p, "seconds": secs})
        if len(out) >= limit:
            break
    return {"members": out}


@routes.get("/api/dashboard")
async def dashboard(c: Ctx):
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    day_map = await daily_seconds(c, c.uid, 7)
    today = dt.datetime.now(config.IST).date()
    days = []
    for i in range(6, -1, -1):
        d = today - dt.timedelta(days=i)
        ts = int(dt.datetime(d.year, d.month, d.day, tzinfo=config.IST).timestamp())
        days.append({"ts": ts, "label": d.strftime("%a"), "seconds": day_map.get(d.isoformat(), 0)})
    out = {"coins": cur["coins"], "candy": cur.get("candy", 0), "days": days}
    for per in ("today", "week"):
        totals = await period_totals(c.db, c.gid, per)
        ranking = [u for u, s in sorted(totals.items(), key=lambda kv: kv[1], reverse=True) if s > 0]
        out[f"rank_{per}"] = ranking.index(c.uid) + 1 if c.uid in ranking else None
        out[f"{per}_seconds"] = totals.get(c.uid, 0)
    from utils import streaks
    st = await c.db.get_daily_status(c.uid, c.gid)
    out["daily_claimable"] = st["last_claim_date"] != streaks.date_str(int(time.time()))
    out["daily_streak"] = st["daily_streak"]
    return out
