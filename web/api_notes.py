"""Chronotes on the web: the twin of cogs/notes.py (.notes, .notes new/view/pin/
delete/search/export, the Edit modal and the Visual Card button). Same table
(user_notes), same limits (title 80, subject 30, content 3500), subjects are
title-cased like the bot does. Notes are private: every read and write is scoped
to the signed-in user. Image attachments come from Discord uploads, so the web
keeps an existing image but only accepts Discord CDN links for new ones."""
from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any, Optional
from urllib.parse import urlparse

from aiohttp import web

from utils import stats_card, streaks

from .common import Ctx, Routes, fail

log = logging.getLogger("web.notes")
routes = Routes()

MAX_TITLE, MAX_SUBJECT, MAX_CONTENT, MAX_SEARCH = 80, 30, 3500, 50
IMAGE_HOSTS = {"cdn.discordapp.com", "media.discordapp.net"}
SUBJECTS = [  # the bot's filter dropdown: (label, key)
    ("Physics", "physics"), ("Chemistry", "chemistry"), ("Mathematics", "mathematics"),
    ("Formulas & Shortcuts", "formulas"), ("Revision Checklist", "revision"), ("General Notes", "general"),
]


def shape(n: dict[str, Any], *, full: bool = True) -> dict[str, Any]:
    out = {"id": n["note_id"], "title": n["title"], "subject": n["subject"], "pinned": bool(n["is_pinned"]),
           "image_url": n.get("image_url"), "color": n.get("color_hex") or "#38BDF8",
           "created_at": n["created_at"], "updated_at": n["updated_at"], "date": streaks.date_str(n["updated_at"])}
    if full:
        out["content"] = n["content"]
    else:
        out["excerpt"] = " ".join(n["content"].split())[:180]
        out["chars"] = len(n["content"])
    return out


def clean_fields(b: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    """Validate title / subject / content exactly like the modals do."""
    out: dict[str, Any] = {}
    if "title" in b or not partial:
        t = " ".join(str(b.get("title") or "").split())
        if not t:
            raise fail("Give the note a title.", 400, "empty_title")
        if len(t) > MAX_TITLE:
            raise fail(f"Titles can be {MAX_TITLE} characters at most.", 400, "title_too_long")
        out["title"] = t
    if "subject" in b or not partial:
        s = " ".join(str(b.get("subject") or "").split()).title() or "General"
        if len(s) > MAX_SUBJECT:
            raise fail(f"Categories can be {MAX_SUBJECT} characters at most.", 400, "subject_too_long")
        out["subject"] = s
    if "content" in b or not partial:
        text = str(b.get("content") or "").replace("\r\n", "\n").strip()
        if not text:
            raise fail("A note needs some content.", 400, "empty_content")
        if len(text) > MAX_CONTENT:
            raise fail(f"Notes can be {MAX_CONTENT:,} characters at most. This one is {len(text):,}.", 400, "content_too_long")
        out["content"] = text
    return out


def image_of(v: Any) -> Optional[str]:
    url = str(v or "").strip()
    if not url:
        return None
    u = urlparse(url)
    if u.scheme != "https" or (u.hostname or "") not in IMAGE_HOSTS or len(url) > 1000:
        raise fail("Only images uploaded to Discord can be attached.", 400, "bad_image")
    return url


def note_id_of(c: Ctx) -> int:
    raw = c.request.match_info["id"]
    if not raw.isdigit() or int(raw) > 2 ** 62:
        raise fail("That note doesn't exist.", 404, "no_note")
    return int(raw)


async def mine(c: Ctx) -> dict[str, Any]:
    n = await c.db.get_note_by_id(note_id_of(c), c.uid)
    if not n or n["guild_id"] != c.gid:
        raise fail("That note isn't in your notebook.", 404, "no_note")
    return n


# ---------------------------------------------------------------------- #
@routes.get("/api/notes")
async def hub(c: Ctx):
    """`.notes` / `.notes search`: the hub, filterable by subject, pinned and text."""
    subject = (c.q("subject") or "").strip().lower() or None
    search = (c.q("q") or "").strip()[:MAX_SEARCH] or None
    pinned = c.q("pinned") in ("1", "true")
    notes = await c.db.get_user_notes(c.uid, c.gid, subject=subject, search=search, pinned_only=pinned, limit=200)
    stats = await c.db.get_note_stats(c.uid, c.gid)
    return {"notes": [shape(n, full=False) for n in notes], "stats": stats, "filtered": bool(subject or search or pinned),
            "subjects": [{"label": a, "key": b} for a, b in SUBJECTS], "limits": {"title": MAX_TITLE, "subject": MAX_SUBJECT, "content": MAX_CONTENT}}


@routes.get("/api/notes/export")
async def export(c: Ctx):
    """`.notes export`: the whole notebook as one Markdown file (same layout as the bot's)."""
    notes = await c.db.get_user_notes(c.uid, c.gid, limit=500)
    if not notes:
        raise fail("You have no notes to export yet.", 404, "empty")
    lines = [f"# Chronotes Notebook - {c.me['name']}\n\nExported on {streaks.date_str(int(time.time()))} (IST)\n\n---\n"]
    for n in notes:
        lines.append(f"## {'[Pinned] ' if n['is_pinned'] else ''}{n['title']}\n")
        lines.append(f"**Category:** {n['subject']} | **Date:** {streaks.date_str(n['updated_at'])}\n\n")
        if n.get("image_url"):
            lines.append(f"![Attached Image]({n['image_url']})\n\n")
        lines.append(f"{n['content']}\n\n---\n")
    return {"filename": "Chronotes_Notebook.md", "markdown": "\n".join(lines), "count": len(notes)}


@routes.post("/api/notes")
async def create(c: Ctx):
    """`.notes new` / the New Note modal."""
    b = await c.body()
    f = clean_fields(b, partial=False)
    img = image_of(b.get("image_url"))
    nid = await c.db.create_note(c.uid, c.gid, f["title"], f["content"], subject=f["subject"], image_url=img)
    log.info("NOTE CREATE | User %s created note #%s in guild %s via web", c.uid, nid, c.gid)
    await c.after()
    return {"note": shape(await c.db.get_note_by_id(nid, c.uid))}


@routes.get("/api/notes/{id}")
async def view(c: Ctx):
    """`.notes view <id>`."""
    return {"note": shape(await mine(c))}


@routes.patch("/api/notes/{id}")
async def edit(c: Ctx):
    """The Edit modal and `.notes pin`: any of title / subject / content / pinned."""
    n = await mine(c)
    b = await c.body()
    f = clean_fields({k: b[k] for k in ("title", "subject", "content") if k in b}, partial=True)
    pinned = None
    if "pinned" in b:
        pinned = 1 if b["pinned"] else 0
    img = image_of(b["image_url"]) if "image_url" in b else None
    if not f and pinned is None and img is None:
        raise fail("Nothing to change.", 400, "nothing")
    await c.db.update_note(n["note_id"], c.uid, title=f.get("title"), content=f.get("content"), subject=f.get("subject"), is_pinned=pinned, image_url=img)
    return {"note": shape(await c.db.get_note_by_id(n["note_id"], c.uid))}


@routes.delete("/api/notes/{id}")
async def remove(c: Ctx):
    """`.notes delete <id>`."""
    n = await mine(c)
    await c.db.delete_note(n["note_id"], c.uid)
    return {"deleted": n["note_id"]}


@routes.get("/api/notes/{id}/card")
async def card(c: Ctx):
    """The bot's Visual Card button: the same PIL index card, as a PNG download."""
    n = await mine(c)
    png = await asyncio.get_running_loop().run_in_executor(
        None, lambda: stats_card.render_note_card_sync(
            title=n["title"], subject=n["subject"], content=n["content"], author_name=c.me["name"],
            date_str=streaks.date_str(n["updated_at"]), is_pinned=bool(n["is_pinned"]), note_id=n["note_id"]))
    return web.Response(body=png, content_type="image/png", headers={
        "Cache-Control": "no-store", "Content-Disposition": f'inline; filename="chronote_{n["note_id"]}.png"'})
