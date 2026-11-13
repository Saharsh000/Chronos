"""JEE Command Centre on the web: the twin of cogs/progress.py (.jee/.progress,
.chapterdone, .subtopicdone, .pyq, .revision, .bookdone, .syllabus). Same
syllabus data, same rewards (economy.MILESTONE_REWARDS), same DB writes
(user_milestones). A chapter that's already done is logged as a revision, as
in the bot. Replies stay in the browser; achievements are announced by c.after()."""
from __future__ import annotations

import logging
from typing import Any, Optional

from utils import economy
from utils import syllabus as syl
from utils.subjects import SUBJECT_ALIASES, SUBJECT_INFO, normalize_subject_key

from .common import Ctx, Routes, fail

log = logging.getLogger("web.progress")
routes = Routes()

SUBJECTS = tuple(syl.SYLLABUS.keys())
MAX_BOOK_LEN = 100
BOOKS = [  # the dropdown in `.bookdone`
    ("HC Verma - Concepts of Physics Vol 1", "physics"), ("HC Verma - Concepts of Physics Vol 2", "physics"),
    ("DC Pandey - Understanding Physics", "physics"), ("IE Irodov - Problems in General Physics", "physics"),
    ("Cengage Physics - BM Sharma", "physics"), ("MS Chouhan - Advanced Problems in Organic Chemistry", "chemistry"),
    ("RC Mukherjee - Modern Approach to Chemical Calculations", "chemistry"), ("OP Tandon - Physical / Inorganic Chemistry", "chemistry"),
    ("Himanshu Pandey - Organic Chemistry", "chemistry"), ("Cengage Mathematics - G. Tewani", "maths"),
    ("Black Book - Advanced Problems in Mathematics (Vikas Gupta)", "maths"), ("SL Loney - Plane Trigonometry / Coordinate Geometry", "maths"),
    ("Amit M Agarwal - Integral / Differential Calculus", "maths"),
]


def subject_of(text: Any, *, required: bool = True) -> Optional[str]:
    t = str(text or "").strip()
    if not t:
        if required:
            raise fail("Pick a subject: Physics, Chemistry or Maths.", 400, "bad_subject")
        return None
    key = normalize_subject_key(t)
    key = SUBJECT_ALIASES.get(key, key)
    if key in SUBJECTS:
        return key
    if required:
        raise fail("Unknown subject. Try physics, chemistry or maths.", 400, "bad_subject")
    return t.title()[:40]          # optional label on PYQ/revision: free text like the bot


def free_subject(text: Any) -> Optional[str]:
    return subject_of(text, required=False)


def chapter_of(subject: str, q: Any) -> dict[str, Any]:
    m = syl.find_chapter(subject, str(q if q is not None else "").strip()) if str(q if q is not None else "").strip() else None
    if m is None:
        raise fail(f"That isn't a recognised {subject.title()} chapter. Pick one from the list.", 404, "bad_chapter")
    return m


async def reward(c: Ctx, type_: str, label: str, subject: Optional[str], chapter: Optional[str] = None) -> dict[str, Any]:
    """log_and_reward_direct + c.after(), with the numbers the page needs."""
    await c.db.log_milestone(c.uid, c.gid, type_, label, subject, chapter=chapter)
    rw = economy.MILESTONE_REWARDS.get(type_, {"coins": 20, "xp": 25})
    await c.db.add_coins(c.uid, c.gid, rw["coins"])
    xp = await c.db.grant_xp(c.uid, c.gid, rw["xp"])
    if xp.get("leveled_up"):
        c.emit("level_up", old_level=xp["old_level"], new_level=xp["new_level"])
    log.info("MILESTONE LOG | User %s logged %s '%s' (subject=%s, chapter=%s) in guild %s via web", c.uid, type_, label, subject, chapter, c.gid)
    newly = await c.after()
    return {"coins": rw["coins"], "xp": rw["xp"], "leveled_up": bool(xp.get("leveled_up")), "new_level": xp.get("new_level"),
            "achievements": [a.id for a in newly]}


async def dashboard(c: Ctx, uid: int) -> dict[str, Any]:
    done = await c.db.get_completed_chapter_names(uid, c.gid)
    counts = await c.db.get_milestone_counts(uid, c.gid)
    subs = []
    for key in SUBJECTS:
        chs = syl.SYLLABUS[key]
        n = sum(1 for ch in chs if ch["name"].strip().lower() in done)
        subs.append({"key": key, "label": SUBJECT_INFO.get(key, {}).get("label", key.title()), "done": n, "total": len(chs)})
    recent = await c.db.get_recent_milestones(uid, c.gid, limit=12)
    return {"user": c.person(uid), "me": uid == c.uid, "subjects": subs,
            "total_done": sum(s["done"] for s in subs), "total": sum(s["total"] for s in subs),
            "counts": {"pyq_years": counts["pyq_years_completed"], "max_revision": counts["max_revision"],
                       "books": counts["books_completed"], "subtopics": counts["subtopics_completed"], "chapters": counts["chapters_completed"]},
            "recent": [{"type": m["type"], "label": m["label"], "subject": m.get("subject"), "chapter": m.get("chapter"), "logged_at": m["logged_at"]} for m in recent],
            "rewards": economy.MILESTONE_REWARDS}


# ---------------------------------------------------------------------- #
@routes.get("/api/progress")
async def progress(c: Ctx):
    """`.jee` / `.progress [member]`."""
    uid = c.uid
    if c.q("user"):
        raw = c.q("user") or ""
        if not raw.isdigit() or not c.bridge.is_member(c.gid, int(raw)):
            raise fail("I couldn't find that member in this server.", 404, "no_member")
        uid = int(raw)
    return await dashboard(c, uid)


@routes.get("/api/syllabus")
async def syllabus(c: Ctx):
    """`.syllabus [subject] [chapter]`, with your own done-marks on every chapter and subtopic."""
    uid = c.uid
    if c.q("user") and (c.q("user") or "").isdigit() and c.bridge.is_member(c.gid, int(c.q("user"))):
        uid = int(c.q("user"))
    rows = await c.db.get_completed_milestones(uid, c.gid)
    ch_logs: dict[str, list[int]] = {}
    sub_done: set[tuple[str, str]] = set()
    for r in rows:
        if r["type"] == "chapter":
            ch_logs.setdefault(r["label"].strip().lower(), []).append(r["logged_at"])
        elif r["type"] == "subtopic":
            sub_done.add(((r.get("chapter") or "").strip().lower(), r["label"].strip().lower()))
    out = []
    for key in SUBJECTS:
        chs = []
        for i, ch in enumerate(syl.SYLLABUS[key], start=1):
            nm = ch["name"].strip().lower()
            tps = [{"name": t, "done": (nm, t.strip().lower()) in sub_done} for t in ch["topics"]]
            logged = ch_logs.get(nm, [])
            chs.append({"number": i, "name": ch["name"], "done": bool(logged), "done_at": max(logged) if logged else None, "topics": tps})
        out.append({"key": key, "label": SUBJECT_INFO.get(key, {}).get("label", key.title()), "chapters": chs})
    return {"subjects": out, "books": [{"name": n, "subject": s} for n, s in BOOKS], "me": uid == c.uid}


@routes.post("/api/progress/chapter")
async def chapter_done(c: Ctx):
    """`.chapterdone`: chapters can only come from the syllabus list; a repeat counts as a revision."""
    b = await c.body()
    sub = subject_of(b.get("subject"))
    match = chapter_of(sub, b.get("chapter"))
    done = await c.db.get_completed_chapter_names(c.uid, c.gid)
    again = match["name"].strip().lower() in done
    r = await reward(c, "revision" if again else "chapter", match["name"], sub, chapter=match["name"])
    done.add(match["name"].strip().lower())
    chs = syl.get_chapters(sub)
    n = sum(1 for ch in chs if ch["name"].strip().lower() in done)
    return {**r, "subject": sub, "number": match["number"], "name": match["name"], "revision": again, "done": n, "total": len(chs)}


@routes.post("/api/progress/subtopic")
async def subtopic_done(c: Ctx):
    """`.subtopicdone <subject> <chapter> <subtopic>`."""
    b = await c.body()
    sub = subject_of(b.get("subject"))
    ch = chapter_of(sub, b.get("chapter"))
    topic = syl.find_subtopic(ch, str(b.get("subtopic", "")).strip()) if str(b.get("subtopic", "")).strip() else None
    if topic is None:
        raise fail("That isn't a listed subtopic of this chapter.", 404, "bad_subtopic")
    r = await reward(c, "subtopic", topic, sub, chapter=ch["name"])
    return {**r, "subject": sub, "chapter": ch["name"], "subtopic": topic}


@routes.post("/api/progress/pyq")
async def pyq_done(c: Ctx):
    """`.pyq <year> [subject]`."""
    b = await c.body()
    year = str(b.get("year", "")).strip()
    if not year.isdigit() or not (1990 <= int(year) <= 2100):
        raise fail("Give a valid 4-digit year, like 2024.", 400, "bad_year")
    sub = free_subject(b.get("subject"))
    return {**await reward(c, "pyq", year, sub), "year": year, "subject": sub}


@routes.post("/api/progress/revision")
async def revision_done(c: Ctx):
    """`.revision <number> [subject]`."""
    b = await c.body()
    num = str(b.get("number", "")).strip()
    if not num.isdigit() or not (1 <= int(num) <= 99):
        raise fail("Give a revision number from 1 to 99.", 400, "bad_number")
    num = str(int(num))
    sub = free_subject(b.get("subject"))
    return {**await reward(c, "revision", num, sub), "number": int(num), "subject": sub}


@routes.post("/api/progress/book")
async def book_done(c: Ctx):
    """`.bookdone <book>`."""
    b = await c.body()
    name = " ".join(str(b.get("book", "")).split())
    if not name:
        raise fail("Pick a book or type its name.", 400, "empty")
    if len(name) > MAX_BOOK_LEN:
        raise fail(f"Book names must be {MAX_BOOK_LEN} characters or fewer.", 400, "too_long")
    return {**await reward(c, "book", name, None), "book": name}
