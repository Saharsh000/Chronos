"""Daily study-streak calculations (pure, no side effects, no I/O).

A "streak day" is any IST calendar day (see config.IST - this bot
anchors all day boundaries to India Standard Time) on which a user
has at least one second of study time credited (see database.py's
`record_study_activity`, called from `_apply_time_and_xp` whenever
`delta_seconds > 0`). This module only does date arithmetic on
already-known values - the database layer is responsible for reading/
writing `current_streak` / `longest_streak` / `last_active_date`.
"""
from __future__ import annotations

import datetime as dt
from typing import NamedTuple, Optional

import config


def date_str(epoch: int) -> str:
    """IST calendar date (YYYY-MM-DD) for a unix-epoch timestamp."""
    return dt.datetime.fromtimestamp(epoch, config.IST).strftime("%Y-%m-%d")


def days_between(earlier: str, later: str) -> int:
    return (dt.date.fromisoformat(later) - dt.date.fromisoformat(earlier)).days


class StreakResult(NamedTuple):
    current_streak: int
    longest_streak: int
    last_active_date: str
    changed: bool          # did anything actually update?
    extended: bool         # did the streak count go up?
    freeze_consumed: bool  # was a streak-freeze item used to bridge a gap?
    streak_broken_from: int  # old streak value when reset happened, 0 if no reset


def apply_activity(
    current_streak: int,
    longest_streak: int,
    last_active_date: Optional[str],
    today: str,
    freeze_available: bool,
) -> StreakResult:
    """Roll one day of confirmed study activity into a user's streak.

    - Same day as last activity: no change (already counted today).
    - Exactly one day after: streak continues (+1).
    - A gap of exactly one missed day, with a streak-freeze available:
      the freeze is spent to bridge the gap and the streak continues.
    - Any larger gap (or no freeze available): streak resets to 1.
    """
    if last_active_date == today:
        return StreakResult(current_streak, longest_streak, today, False, False, False, 0)

    if last_active_date is None:
        new_current = 1
        return StreakResult(new_current, max(longest_streak, new_current), today, True, True, False, 0)

    gap = days_between(last_active_date, today)
    if gap <= 0:
        # Clock skew / out-of-order credit; don't corrupt the streak.
        return StreakResult(current_streak, longest_streak, last_active_date, False, False, False, 0)

    if gap == 1:
        new_current = current_streak + 1
        return StreakResult(new_current, max(longest_streak, new_current), today, True, True, False, 0)

    if gap == 2 and freeze_available:
        new_current = current_streak + 1
        return StreakResult(new_current, max(longest_streak, new_current), today, True, True, True, 0)

    new_current = 1
    return StreakResult(new_current, max(longest_streak, new_current), today, True, False, False, current_streak)
