"""JEE Trivia on the web: the twin of cogs/trivia.py (.trivia hub / p / c / m /
<chapter> / random / me / lb, plus .wave's read-only cache stats).

Same pipeline as the bot: pre-generated cache -> live CJA -> offline pool.
Grading is remote (CJA's /check) and the question is fetched with hideAnswer, so
the answer never reaches the browser. Rewards, streaks, marks, tiers, the 10 s
cooldown (shared with the bot's own dict when the cog is loaded), the 15 coin
skip and the `active_trivia_games` counter (which pauses the pre-generator)
follow cogs/trivia.py. Question text is turned into structured JSON by distexer
(web/trivia_fmt.py); no images are generated. Replies stay in the browser, but
every attempt lands in the same tables the bot's `.trivia me` / `.trivia lb` read."""
from __future__ import annotations

import logging
import random
import re
import secrets
import time
from typing import Any, Optional

import config
from cogs.trivia import TRIVIA_RANKS, get_trivia_tier
from services import cja as cja_mod
from services.cja import CJAError, cja_client

from . import trivia_fmt as fmt
from .common import Ctx, Routes, fail

log = logging.getLogger("web.trivia")
routes = Routes()

SKIP_COST = 15
ANSWER_GRACE = 3.0                 # seconds of network slack past the server deadline
KEEP_AFTER_DONE = 600.0
SUBJECT_ALIASES = {"p": "physics", "phys": "physics", "physics": "physics", "c": "chemistry", "chem": "chemistry", "chemistry": "chemistry",
                   "m": "mathematics", "math": "mathematics", "maths": "mathematics", "mathematics": "mathematics"}
KEY_RE = re.compile(r"^[A-Z]$")
INT_RE = re.compile(r"^[+-]?\d{1,6}$")

SESSIONS: dict[str, dict[str, Any]] = {}           # token -> live question (never holds an answer)
_LOCAL_COOLDOWNS: dict[int, float] = {}            # used when the bot's Trivia cog isn't loaded (tests, standalone)
_LOCAL_ACTIVE = [0]


# ---------------------------------------------------------------------- #
# Shared in-memory state (same objects the bot's cog uses when it is loaded)
# ---------------------------------------------------------------------- #
def _bot(c: Ctx):
    return getattr(c.bridge, "bot", None)


def cooldowns(c: Ctx) -> dict[int, float]:
    bot = _bot(c)
    cog = bot.get_cog("Trivia") if bot is not None else None
    cd = getattr(cog, "user_cooldowns", None)
    return cd if isinstance(cd, dict) else _LOCAL_COOLDOWNS


def active_games(c: Ctx, delta: int) -> None:
    """bot.active_trivia_games pauses the pre-generator while someone is playing."""
    bot = _bot(c)
    if bot is None:
        _LOCAL_ACTIVE[0] = max(0, _LOCAL_ACTIVE[0] + delta)
        return
    cur = getattr(bot, "active_trivia_games", 0)
    bot.active_trivia_games = max(0, cur + delta)


def cooldown_left(c: Ctx) -> float:
    return max(0.0, config.TRIVIA_COOLDOWN_SECONDS - (time.time() - cooldowns(c).get(c.uid, 0)))


def conclude(c: Ctx, s: dict[str, Any]) -> None:
    """Round over (answered, skipped, timed out or abandoned): release the pre-generator exactly once."""
    if not s["concluded"]:
        s["concluded"] = True
        s["ended_at"] = time.time()
        active_games(c, -1)


def sweep(c: Ctx) -> None:
    now = time.time()
    for tok, s in list(SESSIONS.items()):
        if not s["concluded"] and now > s["deadline"] + ANSWER_GRACE + 30:
            conclude(c, s)                              # nobody came back: free the counter
        if s["concluded"] and now - s["ended_at"] > KEEP_AFTER_DONE:
            SESSIONS.pop(tok, None)


# ---------------------------------------------------------------------- #
# Question shaping
# ---------------------------------------------------------------------- #
def time_limit(q: dict[str, Any]) -> int:
    return config.TRIVIA_ADVANCED_TIME_LIMIT if (q.get("exam") or {}).get("id") == "advanced" else config.TRIVIA_MAIN_TIME_LIMIT


def marking(q: dict[str, Any]) -> dict[str, int]:
    m = q.get("marking") or {}
    return {"correct": int(m.get("correct", 4)), "incorrect": int(m.get("incorrect", -1))}


def reveal_block(res: dict[str, Any]) -> dict[str, Any]:
    ans = res.get("answer") or {}
    return {"answer": {"display": str(ans.get("display", "N/A")), "options": [str(o) for o in (ans.get("options") or [])], "integer": ans.get("integer")},
            "explanation": fmt.blocks(res.get("explanation") or "No explanation available."),
            "concept": fmt.text_segs(res.get("concept") or "JEE Core Concept")}


def public_question(token: str, q: dict[str, Any], deadline: float, limit: int, from_cache: bool) -> dict[str, Any]:
    typ = q.get("type") or {}
    tid = str(typ.get("id", "single"))
    raw_opts = q.get("options") or []
    options = []
    for o in raw_opts:
        key = str(o.get("key", "")).strip().upper()
        item: dict[str, Any] = {"key": key, "segs": fmt.text_segs(o.get("text", ""))}
        if tid == "match":
            pairs = fmt.match_pairs(o.get("text", ""))
            if pairs:
                item["pairs"] = pairs
        options.append(item)
    body = {"blocks": fmt.blocks(q.get("question", ""))}
    if tid == "match":
        table = fmt.match_table(q.get("question", ""))
        if table:
            body = {"match": table, "blocks": []}
    cid = str(q.get("id", ""))
    return {
        "token": token, "offline": cid.startswith("offline_"), "from_cache": from_cache,
        "exam": {"id": (q.get("exam") or {}).get("id", "main"), "name": (q.get("exam") or {}).get("name", "JEE Main")},
        "subject": {"id": (q.get("subject") or {}).get("id", "chemistry"), "name": (q.get("subject") or {}).get("name", "Chemistry")},
        "chapter": {"id": (q.get("chapter") or {}).get("id"), "name": (q.get("chapter") or {}).get("name", "General Theory"), "section": (q.get("chapter") or {}).get("section")},
        "topic": {"id": (q.get("topic") or {}).get("id"), "name": (q.get("topic") or {}).get("name", "Concept Analysis")},
        "type": {"id": tid, "name": typ.get("name", "Single Correct"), "instructions": typ.get("instructions", "Choose the one correct option.")},
        "difficulty": q.get("difficulty") if q.get("difficulty") in ("easy", "medium", "hard") else "medium",
        "marking": marking(q), "body": body, "options": options,
        "time_limit": limit, "deadline": deadline, "skip_cost": SKIP_COST,
    }


def cja_error(e: CJAError):
    status = 503 if e.code in ("CJA_UNAVAILABLE", "UNCONFIGURED", "TIMEOUT", "NETWORK_ERROR") else 429 if e.retry_after else 502
    return fail(e.message, status, e.code.lower(), suggestions=list(e.suggestions or []), retry_after=e.retry_after or 0)


def tier_block(marks: int) -> dict[str, Any]:
    t = get_trivia_tier(marks)
    nxt, cur = t["next_marks"], t["cur_min"]
    pct = min(100, int(max(0, marks - cur) / max(1, nxt - cur) * 100)) if nxt is not None else 100
    return {"title": t["title"], "badge": t["badge"], "next_title": t["next_title"], "next_marks": nxt, "cur_min": cur,
            "progress": pct, "needed": max(0, nxt - marks) if nxt is not None else 0}


def stats_block(st: dict[str, Any]) -> dict[str, Any]:
    att, cor = st["questions_attempted"], st["questions_correct"]
    return {"attempted": att, "correct": cor, "marks": st["total_marks"], "coins_won": st["total_coins_won"],
            "streak": st["current_streak"], "best_streak": st["best_streak"], "accuracy": (cor / att * 100) if att else 0.0,
            "last_played_at": st.get("last_played_at")}


# ---------------------------------------------------------------------- #
# Reading: syllabus, stats, leaderboard, cache
# ---------------------------------------------------------------------- #
@routes.get("/api/trivia/syllabus")
async def syllabus(c: Ctx):
    """The subject -> section -> chapter -> topic picker (Hub, chapter browser and topic menu in one)."""
    syl = cja_mod.get_syllabus()
    subjects = []
    for s in syl.get("subjects", []):
        chs = s.get("chapters", [])
        sections: list[str] = []
        for ch in chs:
            if ch.get("section", "General") not in sections:
                sections.append(ch.get("section", "General"))
        subjects.append({"id": s["id"], "name": s["name"], "sections": sections, "chapters": [
            {"id": ch["id"], "name": ch["name"], "section": ch.get("section", "General"), "exams": ch.get("exams", []), "aliases": ch.get("aliases", []),
             "topics": [{"id": t["id"], "name": t["name"], "exams": t.get("exams", [])} for t in ch.get("topics", [])]} for ch in chs]})
    return {"subjects": subjects, "stats": syl.get("stats", {}), "skip_cost": SKIP_COST,
            "limits": {"main": config.TRIVIA_MAIN_TIME_LIMIT, "advanced": config.TRIVIA_ADVANCED_TIME_LIMIT, "cooldown": config.TRIVIA_COOLDOWN_SECONDS}}


@routes.get("/api/trivia/stats")
async def my_stats(c: Ctx):
    """`.trivia me`."""
    st = await c.db.get_or_create_trivia_stats(c.uid, c.gid)         # create first: a never-played user is unranked, not #1
    rank, players = await c.db.get_user_trivia_rank(c.uid, c.gid)
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    return {"me": c.person(c.uid), "stats": stats_block(st), "tier": tier_block(st["total_marks"]),
            "rank": rank if st["questions_attempted"] else None, "players": players, "coins": cur["coins"],
            "cooldown": round(cooldown_left(c), 1), "ladder": [{"min": m, "title": t, "badge": b} for m, t, _e, b, _n in reversed(TRIVIA_RANKS)]}


@routes.get("/api/trivia/leaderboard")
async def leaderboard(c: Ctx):
    """`.trivia lb`: top players plus "Your Climb"."""
    try:
        limit = max(1, min(50, int(c.q("limit") or 10)))
    except ValueError:
        limit = 10
    rows = await c.db.get_trivia_leaderboard(c.gid, limit)
    out = []
    for i, r in enumerate(rows, start=1):
        att = r["questions_attempted"]
        out.append({"rank": i, "user": c.person(r["user_id"]), "me": r["user_id"] == c.uid, "marks": r["total_marks"], "attempted": att, "correct": r["questions_correct"],
                    "accuracy": r["questions_correct"] / att * 100 if att else 0.0, "streak": r["current_streak"], "best_streak": r["best_streak"],
                    "tier": tier_block(r["total_marks"])["title"], "badge": tier_block(r["total_marks"])["badge"]})
    st = await c.db.get_or_create_trivia_stats(c.uid, c.gid)
    rank, players = await c.db.get_user_trivia_rank(c.uid, c.gid)
    return {"rows": out, "players": players, "you": {"rank": rank if st["questions_attempted"] else None, "stats": stats_block(st), "tier": tier_block(st["total_marks"])}}


@routes.get("/api/trivia/cache")
async def cache(c: Ctx):
    """`.wave` (read-only): how many pre-generated questions are waiting."""
    st = await c.db.get_cache_stats()
    bot = _bot(c)
    gen = bot.get_cog("QuestionCache") if bot is not None else None
    out = {"total": st["total"], "by_subject": st["by_subject"], "chapters": st["distinct_chapters"], "topics": st["distinct_topics"], "pregen": None}
    if gen is not None:
        out["pregen"] = {"wave": getattr(gen, "current_wave", None), "paused": bool(getattr(gen, "is_paused", False)),
                         "reason": getattr(gen, "pause_reason", None), "fetched": getattr(gen, "total_fetched", None)}
    return out


# ---------------------------------------------------------------------- #
# Playing
# ---------------------------------------------------------------------- #
def resolve_filters(b: dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    sub = str(b.get("subject") or "").strip().lower() or None
    ch = str(b.get("chapter") or "").strip().lower() or None
    top = str(b.get("topic") or "").strip().lower() or None
    if sub:
        sub = SUBJECT_ALIASES.get(sub)
        if not sub:
            raise fail("Pick Physics, Chemistry or Mathematics.", 400, "bad_subject")
    if ch:
        chapter = cja_mod.get_chapter_by_id(ch)
        if not chapter:
            raise fail("That chapter isn't in the JEE syllabus.", 404, "bad_chapter")
        if sub and chapter.get("subject") not in (None, sub) and str(chapter.get("subject", "")).lower() != sub:
            raise fail("That chapter belongs to a different subject.", 400, "bad_chapter")
        sub = sub or str(chapter.get("subject") or "").lower() or None
        if top and top not in {t["id"].lower() for t in chapter.get("topics", [])}:
            raise fail("That topic isn't part of this chapter.", 404, "bad_topic")
        ch = chapter["id"]
    elif top:
        raise fail("Pick a chapter before a topic.", 400, "bad_topic")
    return sub, ch, top


@routes.post("/api/trivia/question")
async def question(c: Ctx):
    """Start a question: `.trivia r`, a subject/chapter/topic pick, or the "Next question" button."""
    b = await c.body()
    sub, ch, top = resolve_filters(b)
    sweep(c)
    left = cooldown_left(c)
    if left > 0:
        raise fail(f"You can start another trivia question in {left:.1f}s.", 429, "cooldown", retry_after=round(left, 1))
    for old in SESSIONS.values():                        # one live question per player: starting a new one drops the old round
        if old["uid"] == c.uid and old["gid"] == c.gid and not old["concluded"]:
            conclude(c, old)
    cooldowns(c)[c.uid] = time.time()                    # stamped at start and kept if the fetch fails, like the bot

    q, from_cache = None, False
    try:
        q = await c.db.pop_cached_question(sub, ch, top)
        from_cache = q is not None
    except Exception:
        log.exception("trivia cache pop failed")
    if q is None:
        try:
            q = await cja_client.get_question(sub, ch, top, fast=True, hide_answer=True, embed=True)
        except CJAError as e:
            raise cja_error(e)
        except Exception:
            log.exception("trivia fetch failed")
            raise fail("Couldn't load a trivia question right now. Try again in a few seconds.", 503, "unavailable")
    if not isinstance(q, dict) or not q.get("id"):
        raise fail("The question service sent something unreadable. Try again.", 502, "bad_response")
    q = {k: v for k, v in q.items() if k not in ("answer", "solution", "explanation", "correct")}    # belt and braces: never forward an answer

    limit = time_limit(q)
    token, now = secrets.token_urlsafe(18), time.time()
    SESSIONS[token] = {"uid": c.uid, "gid": c.gid, "q": q, "started": now, "deadline": now + limit, "answered": False, "concluded": False, "ended_at": 0.0}
    active_games(c, +1)
    log.info("TRIVIA START  | User %s got %s (%s) in guild %s via web%s", c.uid, q.get("id"), (q.get("type") or {}).get("id"), c.gid, " [cache]" if from_cache else "")
    return public_question(token, q, now + limit, limit, from_cache)


def session_of(c: Ctx, b: dict[str, Any]) -> dict[str, Any]:
    s = SESSIONS.get(str(b.get("token") or ""))
    if not s or s["uid"] != c.uid or s["gid"] != c.gid:
        raise fail("That question has expired. Start a new one.", 404, "no_question")
    return s


def clean_answer(q: dict[str, Any], raw: Any) -> Any:
    """The wire format CJA expects: a key, sorted keys joined by commas, or an int."""
    tid = str((q.get("type") or {}).get("id", "single"))
    keys = [str(o.get("key", "")).strip().upper() for o in (q.get("options") or [])]
    if tid == "integer" or (not keys and tid not in ("single", "multiple", "match", "assertion_reason", "statements")):
        txt = str(raw if raw is not None else "").strip()
        if not INT_RE.match(txt):
            raise fail("Enter a whole number, like 4 or -2.", 400, "bad_answer")
        return int(txt)
    if tid == "multiple":
        vals = raw if isinstance(raw, list) else str(raw or "").split(",")
        picked = sorted({str(v).strip().upper() for v in vals if str(v).strip()})
        if not picked or len(picked) > len(keys) or any(p not in keys for p in picked):
            raise fail("Pick at least one valid option.", 400, "bad_answer")
        return ",".join(picked)
    key = str(raw or "").strip().upper()
    if not KEY_RE.match(key) or key not in keys:
        raise fail("Pick one of the options.", 400, "bad_answer")
    return key


def rewards(q: dict[str, Any], correct: bool) -> tuple[int, int]:
    if not correct:
        return 5, 5
    coins, xp = random.randint(40, 80), random.randint(25, 50)
    if (q.get("exam") or {}).get("id") == "advanced":
        coins += random.randint(20, 40)
        xp += 20
    return coins, xp


async def reveal(s: dict[str, Any]) -> dict[str, Any]:
    """Fetch the solution without an answer (timeout / skip): no stats change."""
    try:
        res = await cja_client.check_answer(str(s["q"]["id"]), None)
    except Exception:
        res = {"answer": {"display": "Revealed"}, "explanation": "The solution couldn't be fetched this time.", "concept": "JEE Core Concept"}
    return reveal_block(res)


@routes.post("/api/trivia/answer")
async def answer(c: Ctx):
    """Grade an answer (CJA /check), then pay out exactly like the bot's handle_answer."""
    b = await c.body()
    s = session_of(c, b)
    q = s["q"]
    if s["answered"] or s["concluded"]:
        raise fail("You've already answered this question.", 409, "already_answered")
    if time.time() > s["deadline"] + ANSWER_GRACE:
        conclude(c, s)
        return {"expired": True, **await reveal(s)}
    wire = clean_answer(q, b.get("answer"))
    s["answered"] = True                                  # claim the attempt before the network call, so double clicks can't double-pay
    try:
        res = await cja_client.check_answer(str(q["id"]), wire)
    except CJAError as e:
        s["answered"] = False                             # a failed check doesn't burn the attempt
        raise cja_error(e)
    except Exception:
        s["answered"] = False
        log.exception("trivia check failed")
        raise fail("Couldn't check your answer. Try again.", 503, "unavailable")
    correct = bool(res.get("correct", False))
    try:
        marks = int(res.get("marks", 4 if correct else -1))
    except (TypeError, ValueError):
        marks = 4 if correct else -1
    coins, xp = rewards(q, correct)
    before = tier_block((await c.db.get_or_create_trivia_stats(c.uid, c.gid))["total_marks"])
    st = await c.db.record_trivia_attempt(user_id=c.uid, guild_id=c.gid, correct=correct, marks=marks, coins_won=coins)   # credits the coins itself
    xp_res = await c.db.grant_xp(c.uid, c.gid, xp)
    candy = 0
    if correct and random.random() < 0.35:
        candy = random.randint(3, 10)
        try:
            await c.db.add_candy(c.uid, c.gid, candy)
        except Exception:
            candy = 0
            log.exception("trivia candy drop failed")
    conclude(c, s)
    if xp_res.get("leveled_up"):
        c.emit("level_up", old_level=xp_res["old_level"], new_level=xp_res["new_level"])
    tier = tier_block(st["total_marks"])
    log.info("TRIVIA ANSWER | User %s %s %+d marks (+%d coins, +%d xp) in guild %s via web", c.uid, "correct" if correct else "wrong", marks, coins, xp, c.gid)
    newly = await c.after()
    rank, players = await c.db.get_user_trivia_rank(c.uid, c.gid)
    return {"expired": False, "correct": correct, "marks": marks, "marking": marking(q), **reveal_block(res),
            "rewards": {"coins": coins, "xp": xp, "candy": candy}, "leveled_up": bool(xp_res.get("leveled_up")), "new_level": xp_res.get("new_level"),
            "stats": stats_block(st), "tier": tier, "tier_up": tier["title"] if tier["title"] != before["title"] and st["total_marks"] > 0 else None,
            "rank": rank, "players": players, "achievements": [a.id for a in newly]}


@routes.post("/api/trivia/skip")
async def skip(c: Ctx):
    """The Skip button: costs 15 Chronocoins, shows the solution, changes no stats."""
    s = session_of(c, await c.body())
    if s["answered"] or s["concluded"]:
        raise fail("This round is already over.", 409, "already_answered")
    if not await c.db.spend_coins(c.uid, c.gid, SKIP_COST):
        raise fail(f"Skipping costs {SKIP_COST} Chronocoins and you don't have enough.", 402, "insufficient_coins")
    s["answered"] = True
    conclude(c, s)
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    return {"skipped": True, "cost": SKIP_COST, "coins": cur["coins"], **await reveal(s)}


@routes.post("/api/trivia/reveal")
async def timeout(c: Ctx):
    """The clock ran out: show the solution. No marks, no penalty, streak untouched (as in the bot)."""
    s = session_of(c, await c.body())
    if s["answered"]:
        raise fail("This round is already over.", 409, "already_answered")
    if time.time() < s["deadline"] - 0.5:
        raise fail("There's still time on the clock.", 409, "not_yet")
    s["answered"] = True
    conclude(c, s)
    return {"expired": True, **await reveal(s)}
