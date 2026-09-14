"""Helpers for formatting durations, building Discord timestamp markdown,
and parsing human-typed duration strings (for the dev `.addtime` command).
"""
from __future__ import annotations

import re
from typing import Optional

_DURATION_RE = re.compile(r"(\d+)\s*(d|h|m|s)", re.IGNORECASE)
_UNIT_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def format_duration(seconds: int, always_show_seconds: bool = True) -> str:
    """Format a duration given in whole seconds into a compact human string.

    Examples:
        65      -> "1m 5s"
        3661    -> "1h 1m 1s"
        90005   -> "1d 1h 0m 5s"
        0       -> "0s"
    """
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    if always_show_seconds or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def discord_timestamp(epoch: int, style: str = "R") -> str:
    """Return Discord markdown for a timestamp, e.g. <t:12345:R>.

    Styles: t (short time), T (long time), d (short date), D (long date),
    f (short date/time), F (long date/time), R (relative, e.g. "3 minutes ago").
    Discord renders this client-side in the viewer's own timezone, so it's
    always accurate without the bot needing to track per-user timezones.
    """
    return f"<t:{int(epoch)}:{style}>"


def parse_duration(text: str) -> Optional[int]:
    """Parse a compact duration string into whole seconds.

    Accepts combinations like '3h', '45m', '1h30m', '2d 4h', '90s'.
    A bare number with no unit (e.g. '90') is treated as minutes, since
    that's the most natural default for study-time grants. Returns
    None if nothing usable could be parsed.
    """
    text = text.strip()
    if not text:
        return None

    matches = _DURATION_RE.findall(text)
    if not matches:
        if text.isdigit():
            return int(text) * 60
        return None

    total = 0
    for value, unit in matches:
        total += int(value) * _UNIT_SECONDS[unit.lower()]
    return total or None
