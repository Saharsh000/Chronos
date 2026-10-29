"""Central configuration, loaded from environment variables (.env).

Nothing timing-related in this bot is hard-coded as a "tick rate" that
needs to keep running to stay accurate - the intervals below only
control how *often* the background tasks poll the database and compare
stored unix-epoch timestamps. The actual elapsed time is always
`current_time - start_time`, computed fresh every time it's needed.
"""
from __future__ import annotations

import datetime as _dt
import os

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
PREFIX = os.getenv("COMMAND_PREFIX", ".")
DB_PATH = os.getenv("DB_PATH", "chronos.sqlite3")

# --- Timezone -----------------------------------------------------------------
# Every "day" boundary in this bot (streaks, `.daily`, weekday stats,
# early-bird/night-owl achievements, today/week/month leaderboards) is
# anchored to IST (India Standard Time, UTC+5:30) rather than the
# server's local time or plain UTC. IST has no DST, so a fixed offset
# is correct year-round - no timezone database needed.
IST_OFFSET_MINUTES = 330
IST = _dt.timezone(_dt.timedelta(minutes=IST_OFFSET_MINUTES))
# Same offset, as a SQLite datetime-modifier string, for strftime()/date()
# calls in database.py (SQLite has no timezone database of its own).
IST_SQL_MODIFIER = f"+{IST_OFFSET_MINUTES} minutes"

# The bot's hardcoded developer/owner. This user can run dev-only
# commands (e.g. .addtime, .addxp) in ANY server the bot is in,
# regardless of their roles/permissions there - it's a fixed user id,
# not a Discord permission.
DEV_USER_ID = int(os.getenv("DEV_USER_ID", "798537896201420811"))

# --- Study / XP tuning ------------------------------------------------------
# XP is randomized per completed minute of activity, not a flat rate -
# each full minute rolls a random amount in this range.
XP_MIN_PER_MINUTE = int(os.getenv("XP_MIN_PER_MINUTE", "6"))
XP_MAX_PER_MINUTE = int(os.getenv("XP_MAX_PER_MINUTE", "14"))

# Coins are earned the same way XP is - a random per-minute roll,
# credited incrementally alongside XP (see database.py). Spend them in
# the `.shop` (see utils/economy.py for the catalog).
COINS_MIN_PER_MINUTE = int(os.getenv("COINS_MIN_PER_MINUTE", "1"))
COINS_MAX_PER_MINUTE = int(os.getenv("COINS_MAX_PER_MINUTE", "3"))

# --- Pets --------------------------------------------------------------------
# Study level (utils/xp.py, NOT pet level) required before `.buypet` works.
PET_UNLOCK_LEVEL = int(os.getenv("PET_UNLOCK_LEVEL", "10"))

# Pet XP is earned the same incremental way user XP/coins are (see
# credit_progress in database.py) - a random per-minute roll, credited
# to whichever pet the user currently has `.equip`ped. Separate range
# from XP_MIN/MAX_PER_MINUTE since pets level on their own (much
# cheaper) curve - see utils/pets.py's xp_required_for_level.
PET_XP_MIN_PER_MINUTE = int(os.getenv("PET_XP_MIN_PER_MINUTE", "1"))
PET_XP_MAX_PER_MINUTE = int(os.getenv("PET_XP_MAX_PER_MINUTE", "3"))

# `.sellfood` refunds this fraction of a food's shop price.
FOOD_SELL_RATE = float(os.getenv("FOOD_SELL_RATE", "0.5"))

# --- Extra coin-earning commands (pets + food made coins matter more) --------
WORK_COOLDOWN_SECONDS = int(os.getenv("WORK_COOLDOWN_SECONDS", str(60 * 60)))
WORK_COINS_MIN = int(os.getenv("WORK_COINS_MIN", "80"))
WORK_COINS_MAX = int(os.getenv("WORK_COINS_MAX", "180"))
WORK_XP_MIN = int(os.getenv("WORK_XP_MIN", "10"))
WORK_XP_MAX = int(os.getenv("WORK_XP_MAX", "25"))

# `.beg` - a much shorter cooldown than `.work`, smaller (and sometimes
# zero) payout, purely for flavor/frequent small top-ups.
BEG_COOLDOWN_SECONDS = int(os.getenv("BEG_COOLDOWN_SECONDS", str(10 * 60)))
BEG_COINS_MIN = int(os.getenv("BEG_COINS_MIN", "10"))
BEG_COINS_MAX = int(os.getenv("BEG_COINS_MAX", "45"))
BEG_FAIL_CHANCE = float(os.getenv("BEG_FAIL_CHANCE", "0.25"))

# --- Streak break penalty ----------------------------------------------------
# When a study streak resets (missed more than 1 day without a Streak
# Freeze), the user loses coins proportional to the streak they just
# lost. The formula is: min(old_streak * STREAK_BREAK_COINS_PER_DAY, STREAK_BREAK_COINS_CAP)
# Set STREAK_BREAK_COINS_PER_DAY to 0 to disable the penalty entirely.
STREAK_BREAK_COINS_PER_DAY = int(os.getenv("STREAK_BREAK_COINS_PER_DAY", "5"))
STREAK_BREAK_COINS_CAP = int(os.getenv("STREAK_BREAK_COINS_CAP", "500"))

WEEKLY_COOLDOWN_SECONDS = int(os.getenv("WEEKLY_COOLDOWN_SECONDS", str(7 * 24 * 60 * 60)))
WEEKLY_COINS_MIN = int(os.getenv("WEEKLY_COINS_MIN", "900"))
WEEKLY_COINS_MAX = int(os.getenv("WEEKLY_COINS_MAX", "1500"))

# --- AFK check-in system -----------------------------------------------------
# Every CHECKIN_INTERVAL_MINUTES of inactivity, the bot asks "are you
# still here?". If there's no response within AFK_GRACE_MINUTES, the
# session is ended automatically.
CHECKIN_INTERVAL_MINUTES = int(os.getenv("CHECKIN_INTERVAL_MINUTES", "25"))
AFK_GRACE_MINUTES = int(os.getenv("AFK_GRACE_MINUTES", "25"))
CHECKIN_EMOJI = "\u2705"  # ✅

# How often (seconds) the session monitor wakes up. Each tick it does
# two things, both purely by comparing stored timestamps read fresh
# from the database - it never accumulates anything itself:
#   1. Rolls any newly-completed whole minutes of an active session's
#      time/XP into the user's permanent stats (see credit_progress
#      in database.py) - this is what makes `.stats` update in near
#      real time instead of only once a session ends.
#   2. Checks `now - last_checkin` / `now - prompt_sent_at` against
#      the AFK thresholds above.
SESSION_MONITOR_INTERVAL_SECONDS = int(os.getenv("SESSION_MONITOR_INTERVAL_SECONDS", "30"))

# --- Pomodoro -----------------------------------------------------------------
POMODORO_FOCUS_MINUTES = int(os.getenv("POMODORO_FOCUS_MINUTES", "25"))
POMODORO_BREAK_MINUTES = int(os.getenv("POMODORO_BREAK_MINUTES", "5"))
POMODORO_LONG_BREAK_MINUTES = int(os.getenv("POMODORO_LONG_BREAK_MINUTES", "15"))
POMODORO_CYCLES_BEFORE_LONG_BREAK = int(os.getenv("POMODORO_CYCLES_BEFORE_LONG_BREAK", "4"))
POMODORO_MONITOR_INTERVAL_SECONDS = int(os.getenv("POMODORO_MONITOR_INTERVAL_SECONDS", "15"))


def validate() -> None:
    """Fail fast with a clear message if required config is missing/invalid."""
    if not TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and fill in your bot token."
        )
    if XP_MIN_PER_MINUTE > XP_MAX_PER_MINUTE:
        raise RuntimeError("XP_MIN_PER_MINUTE cannot be greater than XP_MAX_PER_MINUTE.")
    if COINS_MIN_PER_MINUTE > COINS_MAX_PER_MINUTE:
        raise RuntimeError("COINS_MIN_PER_MINUTE cannot be greater than COINS_MAX_PER_MINUTE.")
