"""XP accumulation and level/tier calculations.

The level curve is a simple quadratic (MEE6-style) ramp: each level
requires progressively more XP than the last. XP itself is awarded in
randomized per-minute amounts (see config.XP_MIN_PER_MINUTE /
XP_MAX_PER_MINUTE and database.py's credit_progress) rather than a
flat rate. This module is pure math with no side effects.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

# Named tiers a user progresses through as their level climbs.
TIERS: list[tuple[int, str]] = [
    (0, "\u2699\uFE0F Iron"),        # ⚙️
    (5, "\U0001F949 Bronze"),        # 🥉
    (10, "\U0001F948 Silver"),       # 🥈
    (20, "\U0001F947 Gold"),         # 🥇
    (35, "\U0001F539 Platinum"),     # 🔹
    (50, "\U0001F48E Diamond"),      # 💎
    (75, "\U0001F343 Ascendant"),    # 🍃
    (100, "\U0001F480 Immortal"),    # 💀
    (150, "\u2600\uFE0F Radiant"),   # ☀️
    (200, "\U0001F680 AIR 1"),       # 🚀
]

_MAX_LEVEL_LOOKUP = 1000


@lru_cache(maxsize=None)
def xp_required_for_level(level: int) -> int:
    """XP required to go from `level` to `level + 1`."""
    level = max(0, level)
    return 5 * (level ** 2) + 50 * level + 100


@lru_cache(maxsize=None)
def total_xp_for_level(level: int) -> int:
    """Cumulative XP required to *reach* `level`, starting from 0 at level 0."""
    if level <= 0:
        return 0
    return total_xp_for_level(level - 1) + xp_required_for_level(level - 1)


def level_from_xp(xp: int) -> int:
    """Derive a user's current level from their total accumulated XP."""
    level = 0
    while level < _MAX_LEVEL_LOOKUP and total_xp_for_level(level + 1) <= xp:
        level += 1
    return level


def xp_progress(xp: int) -> tuple[int, int, int]:
    """Return (xp_into_current_level, xp_needed_for_next_level, level)."""
    level = level_from_xp(xp)
    floor = total_xp_for_level(level)
    ceiling = total_xp_for_level(level + 1)
    return xp - floor, ceiling - floor, level


def tier_for_level(level: int, tiers: Optional[list[tuple[int, str]]] = None) -> str:
    """Name of the tier `level` falls into. Pass a guild's effective
    tier list (see database.py's get_effective_tiers) to respect any
    dev-configured renames; omit it to use the hardcoded defaults."""
    tiers = tiers if tiers is not None else TIERS
    tier = tiers[0][1]
    for threshold, name in tiers:
        if level >= threshold:
            tier = name
        else:
            break
    return tier


def progress_bar(current: int, needed: int, length: int = 14) -> str:
    if needed <= 0:
        filled = length
    else:
        filled = round(length * min(1.0, current / needed))
    filled = max(0, min(length, filled))
    return "\u2588" * filled + "\u2591" * (length - filled)
