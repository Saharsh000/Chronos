"""Turns raw CJA question text into structured JSON for the web UI, using
distexer (the same package the bot's trivia card is built on) instead of an
image: `normalize` repairs the text, `listify` splits run-on enumerations
(Statement I/II, (i)(ii), (a)(b)), `parse_match` reads List-I / List-II tables,
`find_math` marks every $...$ span and `latex_to_unicode` gives each formula a
plain-Unicode fallback. The browser typesets the formulas with KaTeX when it
can and shows that Unicode when it can't. Nothing here renders an image."""
from __future__ import annotations

import re
from typing import Any, Optional

from distexer import find_math, latex_to_unicode, listify, normalize, parse_match

MAX_TEXT = 8000
_ITEM = re.compile(r"^(\s*)▸\s*(?:\*\*(.+?)\*\*|`(.+?)`)?\s*(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def unescape(text: Any) -> str:
    s = "" if text is None else str(text)
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")[:MAX_TEXT]


def _clean_plain(s: str) -> str:
    return _BOLD.sub(r"\1", s).replace("`", "")


def segments(text: str) -> list[dict[str, Any]]:
    """Plain-text and math pieces in order: {k:'text', v} / {k:'math', tex, uni, display}."""
    out: list[dict[str, Any]] = []
    pos = 0
    try:
        spans = find_math(text)
    except Exception:
        spans = []
    for sp in spans:
        if sp.start > pos:
            out.append({"k": "text", "v": _clean_plain(text[pos:sp.start])})
        tex = sp.content.strip()
        try:
            uni = latex_to_unicode(tex, display=bool(sp.display))
        except Exception:
            uni = tex
        out.append({"k": "math", "tex": tex, "uni": uni, "display": bool(sp.display)})
        pos = sp.end
    if pos < len(text):
        out.append({"k": "text", "v": _clean_plain(text[pos:])})
    return [s for s in out if s["k"] == "math" or s["v"] != ""]


def prepare(text: Any) -> str:
    s = unescape(text)
    try:
        return normalize(s)
    except Exception:
        return s


def blocks(text: Any) -> list[dict[str, Any]]:
    """Paragraphs and list items, e.g. [{t:'p', segs}, {t:'item', label:'Statement I', level:0, segs}]."""
    s = prepare(text).strip()
    if not s:
        return []
    try:
        laid = listify(s)
    except Exception:
        laid = s
    out: list[dict[str, Any]] = []
    for raw in laid.split("\n"):
        if not raw.strip():
            continue
        m = _ITEM.match(raw)
        if m:
            label = (m.group(2) or m.group(3) or "").strip().rstrip(":")
            body = m.group(4).strip()
            out.append({"t": "item", "label": label, "level": min(3, len(m.group(1)) // 2), "segs": segments(body)})
        else:
            out.append({"t": "p", "segs": segments(raw.strip())})
    return out


def text_segs(text: Any) -> list[dict[str, Any]]:
    """Short inline text (an option, a concept line): one list of segments."""
    return segments(prepare(text).replace("\n", " ").strip())


def match_table(text: Any) -> Optional[dict[str, Any]]:
    """List-I / List-II questions as two keyed lists (None when the text isn't a match table)."""
    s = prepare(text)
    try:
        mq = parse_match(s)
    except Exception:
        mq = None
    if not mq or not mq.list_i or not mq.list_ii:
        return None
    list_ii = list(mq.list_ii)
    tail = (mq.tail or "").strip()
    key, last = list_ii[-1]
    if "\n" in last:                                   # parse_match keeps trailing prose on the last row
        last, extra = last.split("\n", 1)
        list_ii[-1] = (key, last.strip())
        tail = (extra.strip() + " " + tail).strip()
    return {
        "stem": segments(mq.stem.strip()) if mq.stem else [],
        "list_i": [{"key": str(k).upper(), "segs": segments(v.strip())} for k, v in mq.list_i],
        "list_ii": [{"key": str(k), "segs": segments(v.strip())} for k, v in list_ii],
        "tail": segments(tail) if tail else [],
        "header_i": "List I", "header_ii": "List II",
    }


_PAIR_SPLIT = re.compile(r"[,;]\s*")
_ARROW = re.compile(r"\s*(?:→|->|➔|-)\s*")


def match_pairs(option_text: Any) -> Optional[list[dict[str, str]]]:
    """'P→1, Q→2, R→3, S→4' as [{from:'P', to:'1'}, ...]; None if it doesn't look like a mapping."""
    parts = _PAIR_SPLIT.split(unescape(option_text).strip())
    pairs = []
    for p in parts:
        bits = _ARROW.split(p.strip(), maxsplit=1)
        if len(bits) != 2 or not bits[0] or not bits[1]:
            return None
        pairs.append({"from": bits[0].strip(), "to": bits[1].strip()})
    return pairs or None
