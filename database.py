"""Async SQLite persistence layer.

DESIGN NOTE (important):
Every duration this bot reports is computed as `current_time - start_time`
(or `- last_checkin`, `- phase_start`, `- credited_seconds`, etc.) using
integer unix-epoch timestamps that are written to disk the moment
they're known. Nothing here relies on an in-memory counter that
increments while the process runs. That means:

  * A crash or restart loses nothing - `start_time` is already on disk.
  * A missed tick in a polling loop doesn't cause drift - the next tick
    just re-reads `now` and `start_time` and computes the same correct
    answer it always would have.
  * On boot, `cogs/sessions.py` simply reports whichever sessions are
    still marked active in the database and lets them keep running -
    since sessions are only ever started/stopped by the `.start`/`.stop`
    commands or an AFK timeout (never by voice presence), there is
    nothing to reconcile against live voice state anymore.

INCREMENTAL XP/TIME CREDITING:
XP is randomized per completed minute of activity (config.XP_MIN_PER_MINUTE
/ XP_MAX_PER_MINUTE), and it is rolled into a user's permanent stats
*while the session is still running* - every polling tick, any whole
minutes that have newly elapsed get credited immediately via
`credit_progress()`. This is still just `current_time - start_time`
math (compared against how much has already been credited), so it's
just as restart-safe as everything else - it's what makes `.stats`
update within roughly a minute of studying instead of only once a
session ends.

Coins ride along the exact same incremental path as XP (see
`_random_minute_coins` / `_apply_time_and_xp`), and confirmed study
time also rolls into the daily streak (`_record_study_activity`),
which is why streaks/coins/XP all update live together instead of
only when a session ends.

MIGRATIONS: this module is an *update* to an existing schema, and per
the project owner it needs to keep working against a database file
that already exists from the previous version. `SCHEMA` below only
ever adds new tables (`CREATE TABLE IF NOT EXISTS`), and `_migrate()`
adds any new columns to pre-existing tables with `ALTER TABLE ... ADD
COLUMN` guarded by a `PRAGMA table_info` check - nothing here ever
drops or rewrites a column, so old data is preserved untouched.
"""
from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Optional

import aiosqlite

import config
from utils import economy, streaks
from utils import eggs as egg_catalog
from utils import food as food_catalog
from utils import pets as pet_catalog
from utils.achievements import Achievement
from utils.achievements import evaluate as evaluate_achievements
from utils.xp import TIERS, level_from_xp

log = logging.getLogger("database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            INTEGER PRIMARY KEY,
    checkin_channel_id  INTEGER,
    pomodoro_channel_id INTEGER,
    physics_channel_id  INTEGER,
    chemistry_channel_id INTEGER,
    maths_channel_id    INTEGER
);

CREATE TABLE IF NOT EXISTS user_stats (
    user_id          INTEGER NOT NULL,
    guild_id         INTEGER NOT NULL,
    total_seconds    INTEGER NOT NULL DEFAULT 0,
    xp               INTEGER NOT NULL DEFAULT 0,
    level            INTEGER NOT NULL DEFAULT 0,
    sessions_count   INTEGER NOT NULL DEFAULT 0,
    last_session_end INTEGER,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS subject_stats (
    user_id        INTEGER NOT NULL,
    guild_id       INTEGER NOT NULL,
    subject        TEXT NOT NULL,
    total_seconds  INTEGER NOT NULL DEFAULT 0,
    sessions_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id, subject)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    guild_id          INTEGER NOT NULL,
    channel_id        INTEGER,            -- nullable: sessions no longer require voice
    subject           TEXT,               -- 'physics' | 'chemistry' | 'maths' | NULL
    start_time        INTEGER NOT NULL,   -- unix epoch seconds; source of truth
    last_checkin      INTEGER NOT NULL,   -- unix epoch seconds of last confirmed activity
    prompt_sent_at    INTEGER,            -- unix epoch seconds an AFK prompt was sent (NULL = none pending)
    prompt_message_id INTEGER,
    prompt_channel_id INTEGER,
    credited_seconds  INTEGER NOT NULL DEFAULT 0,  -- how much of this session is already in user_stats
    credited_xp       INTEGER NOT NULL DEFAULT 0,  -- total XP already rolled in for this session
    status            TEXT NOT NULL DEFAULT 'active',  -- active | ended
    end_time          INTEGER,
    elapsed_seconds   INTEGER,
    end_reason        TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_active
    ON sessions (user_id, guild_id, status);

CREATE TABLE IF NOT EXISTS session_log (
    log_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    guild_id         INTEGER NOT NULL,
    channel_id       INTEGER,
    subject          TEXT,
    start_time       INTEGER NOT NULL,
    end_time         INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL,
    xp_earned        INTEGER NOT NULL,
    end_reason       TEXT
);

CREATE INDEX IF NOT EXISTS idx_session_log_lookup
    ON session_log (guild_id, user_id, start_time);

CREATE INDEX IF NOT EXISTS idx_session_log_subject
    ON session_log (guild_id, subject, start_time);

CREATE TABLE IF NOT EXISTS pomodoro_sessions (
    channel_id          INTEGER PRIMARY KEY,
    guild_id            INTEGER NOT NULL,
    announce_channel_id INTEGER,
    phase               TEXT NOT NULL DEFAULT 'focus',  -- focus | break | long_break
    phase_start         INTEGER NOT NULL,               -- unix epoch seconds; source of truth
    phase_duration      INTEGER NOT NULL,
    cycle_count         INTEGER NOT NULL DEFAULT 0,
    active              INTEGER NOT NULL DEFAULT 1
);

-- Coin balances. Coins are earned the same incremental way XP is (see
-- _random_minute_coins / credit_progress). lifetime_earned only ever
-- goes up (spending doesn't reduce it) - it's what economy-themed
-- achievements and the Hall of Fame "Richest" record check against.
CREATE TABLE IF NOT EXISTS user_currency (
    user_id         INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    coins           INTEGER NOT NULL DEFAULT 0,
    lifetime_earned INTEGER NOT NULL DEFAULT 0,
    boxes_opened    INTEGER NOT NULL DEFAULT 0,
    items_purchased INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
);

CREATE INDEX IF NOT EXISTS idx_currency_guild ON user_currency (guild_id, lifetime_earned);

-- Shop purchases. `quantity` doubles as "owned" for one-time unlocks
-- (titles) and as stacked charges for consumables/boosts.
CREATE TABLE IF NOT EXISTS user_inventory (
    user_id    INTEGER NOT NULL,
    guild_id   INTEGER NOT NULL,
    item_id    TEXT NOT NULL,
    quantity   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id, item_id)
);

-- Timed effects from activated boosts (see utils/economy.py SHOP_ITEMS
-- "boost" entries). `credit_progress` checks this table on every tick
-- and multiplies that tick's XP/coin roll while an effect is active.
CREATE TABLE IF NOT EXISTS user_effects (
    user_id    INTEGER NOT NULL,
    guild_id   INTEGER NOT NULL,
    effect_id  TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    multiplier INTEGER NOT NULL DEFAULT 2,
    PRIMARY KEY (user_id, guild_id, effect_id)
);

-- `.daily` claim tracking. Deliberately separate from the study
-- streak in user_stats - this one tracks consecutive daily *claims*,
-- not days actually spent studying.
CREATE TABLE IF NOT EXISTS user_daily (
    user_id         INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    last_claim_date TEXT,
    daily_streak    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS achievements_unlocked (
    user_id        INTEGER NOT NULL,
    guild_id       INTEGER NOT NULL,
    achievement_id TEXT NOT NULL,
    unlocked_at    INTEGER NOT NULL,
    PRIMARY KEY (user_id, guild_id, achievement_id)
);

CREATE INDEX IF NOT EXISTS idx_achievements_guild ON achievements_unlocked (guild_id, user_id);

-- Manually-logged study progress: chapter/subtopic completions
-- (validated against utils/syllabus.py), book completions, PYQ
-- (previous-year-questions) years, and revision passes. Users log
-- these themselves (see cogs/progress.py) - unlike time/XP/coins,
-- there's no way to infer them automatically.
CREATE TABLE IF NOT EXISTS user_milestones (
    milestone_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    guild_id     INTEGER NOT NULL,
    type         TEXT NOT NULL,   -- 'chapter' | 'subtopic' | 'book' | 'pyq' | 'revision'
    subject      TEXT,            -- free text; not restricted to physics/chemistry/maths
    chapter      TEXT,            -- parent chapter name (used by 'subtopic' logs)
    label        TEXT NOT NULL,   -- chapter/subtopic/book name, PYQ year, or revision number
    logged_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_milestones_user ON user_milestones (user_id, guild_id, type);

-- Dev-configurable branding, per server: rename tiers (utils/xp.py's
-- TIERS is still the global default/fallback) and add extra
-- purchasable profile tags/titles on top of utils/economy.py's
-- built-in SHOP_ITEMS. See cogs/customization.py (dev-only).
CREATE TABLE IF NOT EXISTS guild_tier_overrides (
    guild_id INTEGER NOT NULL,
    level    INTEGER NOT NULL,
    name     TEXT NOT NULL,
    PRIMARY KEY (guild_id, level)
);

CREATE TABLE IF NOT EXISTS guild_custom_tags (
    guild_id   INTEGER NOT NULL,
    item_id    TEXT NOT NULL,
    title_text TEXT NOT NULL,
    price      INTEGER NOT NULL,
    PRIMARY KEY (guild_id, item_id)
);

-- Owned pets - see utils/pets.py for the species catalog. One row per
-- (user, guild, species): a species is a one-time unlock (like a
-- shop title), so there's never more than one copy of the same
-- species per user. `equipped` is exclusive per (user, guild) and is
-- enforced in application code (equip_pet() clears any other row
-- before setting the new one), not by the schema.
CREATE TABLE IF NOT EXISTS user_pets (
    user_id     INTEGER NOT NULL,
    guild_id    INTEGER NOT NULL,
    species_id  TEXT NOT NULL,
    nickname    TEXT NOT NULL,
    level       INTEGER NOT NULL DEFAULT 1,
    xp          INTEGER NOT NULL DEFAULT 0,
    equipped    INTEGER NOT NULL DEFAULT 0,
    acquired_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, guild_id, species_id)
);

CREATE INDEX IF NOT EXISTS idx_user_pets_equipped ON user_pets (user_id, guild_id, equipped);

-- Generic per-(user, guild, cooldown) timestamp store for the extra
-- coin-earning commands (`.work` / `.weekly` - see cogs/economy.py).
-- Kept generic so a future cooldown-based command doesn't need its
-- own table.
CREATE TABLE IF NOT EXISTS user_cooldowns (
    user_id     INTEGER NOT NULL,
    guild_id    INTEGER NOT NULL,
    cooldown_id TEXT NOT NULL,
    last_used   INTEGER NOT NULL,
    PRIMARY KEY (user_id, guild_id, cooldown_id)
);

-- Incubator slots for hatching eggs via study progress.
-- Up to 2 slots per user per server. credited_seconds increases with active study time.
CREATE TABLE IF NOT EXISTS user_incubator (
    user_id           INTEGER NOT NULL,
    guild_id          INTEGER NOT NULL,
    slot              INTEGER NOT NULL,
    egg_id            TEXT NOT NULL,
    started_at        INTEGER NOT NULL,
    required_seconds  INTEGER NOT NULL,
    credited_seconds  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id, slot)
);
"""

# Columns added to `user_stats` after its original release. Applied by
# _migrate() via ALTER TABLE so an existing database file (from before
# this update) gains them without losing any existing data.
USER_STATS_MIGRATIONS: dict[str, str] = {
    "current_streak": "ALTER TABLE user_stats ADD COLUMN current_streak INTEGER NOT NULL DEFAULT 0",
    "longest_streak": "ALTER TABLE user_stats ADD COLUMN longest_streak INTEGER NOT NULL DEFAULT 0",
    "last_active_date": "ALTER TABLE user_stats ADD COLUMN last_active_date TEXT",
    "equipped_title": "ALTER TABLE user_stats ADD COLUMN equipped_title TEXT",
}

# Same idea for `sessions` - tracks live-credited coins the same way
# `credited_xp` already tracked live-credited XP, so `.stop` can show
# total coins earned for the session that just ended.
SESSIONS_MIGRATIONS: dict[str, str] = {
    "credited_coins": "ALTER TABLE sessions ADD COLUMN credited_coins INTEGER NOT NULL DEFAULT 0",
}


def _random_minute_xp(minutes: int) -> int:
    """Randomized XP for `minutes` worth of activity - one independent
    roll per minute, summed. Returns 0 for minutes <= 0."""
    if minutes <= 0:
        return 0
    return sum(
        random.randint(config.XP_MIN_PER_MINUTE, config.XP_MAX_PER_MINUTE)
        for _ in range(minutes)
    )


def _random_minute_coins(minutes: int) -> int:
    """Randomized coins for `minutes` worth of activity - mirrors
    _random_minute_xp above, on its own config range."""
    if minutes <= 0:
        return 0
    return sum(
        random.randint(config.COINS_MIN_PER_MINUTE, config.COINS_MAX_PER_MINUTE)
        for _ in range(minutes)
    )


def _random_minute_pet_xp(minutes: int) -> int:
    """Randomized pet XP for `minutes` worth of activity - mirrors
    _random_minute_xp/_random_minute_coins above. This is what makes
    studying feed your equipped pet passively, on top of `.feed`."""
    if minutes <= 0:
        return 0
    return sum(
        random.randint(config.PET_XP_MIN_PER_MINUTE, config.PET_XP_MAX_PER_MINUTE)
        for _ in range(minutes)
    )


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA busy_timeout=5000;")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        await self._migrate()
        await self._auto_seed()
        log.info(f"Connected to SQLite database at '{self.path}' (WAL mode).")

    async def _auto_seed(self) -> None:
        """Seed previous progress if database is empty/fresh and seed_data.sql exists."""
        seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data.sql")
        if not os.path.exists(seed_path):
            return

        cur = await self._conn.execute("SELECT COUNT(*) as count FROM sessions")
        row = await cur.fetchone()
        if row and row["count"] == 0:
            log.info("Fresh database detected. Auto-seeding previous progress from seed_data.sql...")
            with open(seed_path, "r", encoding="utf-8") as f:
                seed_sql = f.read()
            await self._conn.executescript(seed_sql)
            await self._conn.commit()
            log.info("Auto-seeding complete! Restored all user progress, streaks, and sessions.")

    async def _migrate(self) -> None:
        """Add any columns introduced after the initial release to
        existing tables. Safe to run on every startup - each column is
        only added if it isn't already there."""
        await self._migrate_table("user_stats", USER_STATS_MIGRATIONS)
        await self._migrate_table("sessions", SESSIONS_MIGRATIONS)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS user_incubator (
            user_id           INTEGER NOT NULL,
            guild_id          INTEGER NOT NULL,
            slot              INTEGER NOT NULL,
            egg_id            TEXT NOT NULL,
            started_at        INTEGER NOT NULL,
            required_seconds  INTEGER NOT NULL,
            credited_seconds  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, guild_id, slot)
        );
        """)

    async def _migrate_table(self, table: str, migrations: dict[str, str]) -> None:
        cur = await self._conn.execute(f"PRAGMA table_info({table})")
        existing_cols = {row["name"] for row in await cur.fetchall()}
        added = []
        for column, ddl in migrations.items():
            if column not in existing_cols:
                await self._conn.execute(ddl)
                added.append(column)
        if added:
            await self._conn.commit()
            log.info(f"Migrated {table}: added column(s) {', '.join(added)}.")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            log.info("Database connection closed.")

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() must be awaited before use"
        return self._conn

    # ------------------------------------------------------------------ #
    # Guild configuration
    # ------------------------------------------------------------------ #
    async def get_guild_config(self, guild_id: int) -> dict[str, Any]:
        cur = await self.conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
        return {
            "guild_id": guild_id,
            "checkin_channel_id": None,
            "pomodoro_channel_id": None,
            "physics_channel_id": None,
            "chemistry_channel_id": None,
            "maths_channel_id": None,
        }

    async def set_checkin_channel(self, guild_id: int, channel_id: Optional[int]) -> None:
        await self.conn.execute(
            """
            INSERT INTO guild_config (guild_id, checkin_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET checkin_channel_id = excluded.checkin_channel_id
            """,
            (guild_id, channel_id),
        )
        await self.conn.commit()

    async def set_subject_channels(
        self,
        guild_id: int,
        physics_id: Optional[int],
        chemistry_id: Optional[int],
        maths_id: Optional[int],
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO guild_config (guild_id, physics_channel_id, chemistry_channel_id, maths_channel_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                physics_channel_id = excluded.physics_channel_id,
                chemistry_channel_id = excluded.chemistry_channel_id,
                maths_channel_id = excluded.maths_channel_id
            """,
            (guild_id, physics_id, chemistry_id, maths_id),
        )
        await self.conn.commit()

    # ------------------------------------------------------------------ #
    # User stats
    # ------------------------------------------------------------------ #
    async def get_or_create_user_stats(self, user_id: int, guild_id: int) -> dict[str, Any]:
        await self.conn.execute(
            "INSERT OR IGNORE INTO user_stats (user_id, guild_id) VALUES (?, ?)",
            (user_id, guild_id),
        )
        await self.conn.commit()
        cur = await self.conn.execute(
            "SELECT * FROM user_stats WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        row = await cur.fetchone()
        return dict(row)

    async def get_alltime_totals(self, guild_id: int) -> dict[int, int]:
        """{user_id: total_seconds}, kept near-real-time by credit_progress()."""
        cur = await self.conn.execute(
            "SELECT user_id, total_seconds FROM user_stats WHERE guild_id = ?", (guild_id,)
        )
        rows = await cur.fetchall()
        return {r["user_id"]: r["total_seconds"] for r in rows}

    async def get_subject_stats(self, user_id: int, guild_id: int) -> dict[str, int]:
        cur = await self.conn.execute(
            "SELECT subject, total_seconds FROM subject_stats WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        rows = await cur.fetchall()
        result = {"physics": 0, "chemistry": 0, "maths": 0}
        for r in rows:
            result[r["subject"]] = r["total_seconds"]
        return result

    async def get_subject_totals(self, guild_id: int, subject: str) -> dict[int, int]:
        """{user_id: total_seconds} for one subject, kept near-real-time."""
        cur = await self.conn.execute(
            "SELECT user_id, total_seconds FROM subject_stats WHERE guild_id = ? AND subject = ?",
            (guild_id, subject),
        )
        rows = await cur.fetchall()
        return {r["user_id"]: r["total_seconds"] for r in rows}

    async def _apply_time_and_xp(
        self,
        user_id: int,
        guild_id: int,
        subject: Optional[str],
        delta_seconds: int,
        delta_xp: int,
        delta_coins: int = 0,
        increment_session_count: bool = False,
        now: Optional[int] = None,
    ) -> tuple[int, int, Optional[streaks.StreakResult]]:
        """Roll additional seconds/XP/coins into user_stats (and
        subject_stats, if `subject` is set). If any actual study time
        was credited (`delta_seconds > 0`), also rolls that day into
        the user's daily study streak. Returns (old_level, new_level, streak_result)."""
        now = now if now is not None else int(time.time())
        stats = await self.get_or_create_user_stats(user_id, guild_id)
        old_level = stats["level"]
        new_total_seconds = max(0, stats["total_seconds"] + delta_seconds)
        new_xp = max(0, stats["xp"] + delta_xp)
        new_level = level_from_xp(new_xp)
        count_delta = 1 if increment_session_count else 0

        await self.conn.execute(
            """
            UPDATE user_stats
            SET total_seconds = ?, xp = ?, level = ?, sessions_count = sessions_count + ?
            WHERE user_id = ? AND guild_id = ?
            """,
            (new_total_seconds, new_xp, new_level, count_delta, user_id, guild_id),
        )

        if subject:
            await self.conn.execute(
                """
                INSERT INTO subject_stats (user_id, guild_id, subject, total_seconds, sessions_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id, subject) DO UPDATE SET
                    total_seconds = total_seconds + excluded.total_seconds,
                    sessions_count = sessions_count + excluded.sessions_count
                """,
                (user_id, guild_id, subject, delta_seconds, count_delta),
            )

        if delta_coins:
            await self._add_coins_raw(user_id, guild_id, delta_coins)

        await self.conn.commit()

        streak_res = None
        if delta_seconds > 0:
            streak_res = await self._record_study_activity(user_id, guild_id, now)

        return old_level, new_level, streak_res

    async def _add_coins_raw(self, user_id: int, guild_id: int, amount: int) -> None:
        """INSERT/UPDATE user_currency without committing - callers
        that batch this with other writes commit once at the end."""
        await self.conn.execute(
            "INSERT OR IGNORE INTO user_currency (user_id, guild_id) VALUES (?, ?)",
            (user_id, guild_id),
        )
        lifetime_delta = amount if amount > 0 else 0
        await self.conn.execute(
            """
            UPDATE user_currency
            SET coins = coins + ?, lifetime_earned = lifetime_earned + ?
            WHERE user_id = ? AND guild_id = ?
            """,
            (amount, lifetime_delta, user_id, guild_id),
        )

    async def _record_study_activity(self, user_id: int, guild_id: int, now: int) -> Optional[streaks.StreakResult]:
        """Roll one day of confirmed study time into the user's streak
        (see utils/streaks.py). Automatically spends a Streak Freeze
        from inventory if one is needed and available to bridge a
        single missed day."""
        stats = await self.get_or_create_user_stats(user_id, guild_id)
        freeze_qty = await self.get_item_qty(user_id, guild_id, "streak_freeze")
        today = streaks.date_str(now)
        result = streaks.apply_activity(
            stats["current_streak"], stats["longest_streak"], stats["last_active_date"],
            today, freeze_available=freeze_qty > 0,
        )
        if not result.changed:
            return None

        if result.freeze_consumed:
            await self.conn.execute(
                "UPDATE user_inventory SET quantity = quantity - 1 "
                "WHERE user_id = ? AND guild_id = ? AND item_id = 'streak_freeze' AND quantity > 0",
                (user_id, guild_id),
            )

        await self.conn.execute(
            """
            UPDATE user_stats
            SET current_streak = ?, longest_streak = ?, last_active_date = ?
            WHERE user_id = ? AND guild_id = ?
            """,
            (result.current_streak, result.longest_streak, result.last_active_date, user_id, guild_id),
        )
        await self.conn.commit()

        # Losing streak penalty: deduct coins proportional to the
        # streak that was just lost.
        if result.streak_broken_from > 0 and config.STREAK_BREAK_COINS_PER_DAY > 0:
            penalty = min(
                result.streak_broken_from * config.STREAK_BREAK_COINS_PER_DAY,
                config.STREAK_BREAK_COINS_CAP,
            )
            currency = await self.get_or_create_currency(user_id, guild_id)
            actual_penalty = min(penalty, currency["coins"])  # never go negative
            if actual_penalty > 0:
                await self.conn.execute(
                    "UPDATE user_currency SET coins = coins - ? WHERE user_id = ? AND guild_id = ?",
                    (actual_penalty, user_id, guild_id),
                )
                await self.conn.commit()
                log.info(
                    f"STREAK BREAK  | user={user_id} guild={guild_id} lost {result.streak_broken_from}-day streak, "
                    f"penalty={actual_penalty} coins"
                )

        return result

    # ------------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------------ #
    async def get_active_session(self, user_id: int, guild_id: int) -> Optional[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND guild_id = ? AND status = 'active'",
            (user_id, guild_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_all_active_sessions(self) -> list[dict[str, Any]]:
        cur = await self.conn.execute("SELECT * FROM sessions WHERE status = 'active'")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_active_sessions_for_guild(self, guild_id: int) -> list[dict[str, Any]]:
        """All currently-active sessions in one server - used by `.active`."""
        cur = await self.conn.execute(
            "SELECT * FROM sessions WHERE guild_id = ? AND status = 'active' ORDER BY start_time ASC",
            (guild_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def start_session(
        self,
        user_id: int,
        guild_id: int,
        channel_id: Optional[int],
        subject: Optional[str] = None,
        now: Optional[int] = None,
    ) -> int:
        now = now if now is not None else int(time.time())
        cur = await self.conn.execute(
            """
            INSERT INTO sessions (user_id, guild_id, channel_id, subject, start_time, last_checkin, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
            """,
            (user_id, guild_id, channel_id, subject, now, now),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def update_checkin(self, session_id: int, now: Optional[int] = None) -> None:
        """Refresh a session's 'still active' timestamp and clear any pending AFK prompt."""
        now = now if now is not None else int(time.time())
        await self.conn.execute(
            """
            UPDATE sessions
            SET last_checkin = ?, prompt_sent_at = NULL, prompt_message_id = NULL, prompt_channel_id = NULL
            WHERE session_id = ?
            """,
            (now, session_id),
        )
        await self.conn.commit()

    async def set_prompt_sent(
        self, session_id: int, message_id: int, channel_id: int, now: Optional[int] = None
    ) -> None:
        now = now if now is not None else int(time.time())
        await self.conn.execute(
            """
            UPDATE sessions
            SET prompt_sent_at = ?, prompt_message_id = ?, prompt_channel_id = ?
            WHERE session_id = ?
            """,
            (now, message_id, channel_id, session_id),
        )
        await self.conn.commit()

    async def get_session_by_prompt_message(self, message_id: int) -> Optional[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM sessions WHERE prompt_message_id = ? AND status = 'active'",
            (message_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def credit_progress(self, session_id: int, now: int) -> Optional[dict[str, Any]]:
        """Roll any newly-completed whole minutes of an *active* session
        into user_stats/subject_stats immediately, without waiting for
        the session to end. This is what makes XP show up while you're
        still studying instead of only once you `.stop`.

        Returns a summary of the credited delta, or None if the session
        isn't active or no full minute has elapsed since the last credit.
        """
        cur = await self.conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = await cur.fetchone()
        if not row or row["status"] != "active":
            return None
        session = dict(row)

        elapsed = max(0, now - session["start_time"])
        uncredited_seconds = elapsed - session["credited_seconds"]
        new_minutes = uncredited_seconds // 60
        if new_minutes <= 0:
            return None

        delta_seconds = new_minutes * 60
        delta_xp = _random_minute_xp(new_minutes)
        delta_coins = _random_minute_coins(new_minutes)
        delta_pet_xp = _random_minute_pet_xp(new_minutes)

        # Active boosts (see utils/economy.py "boost" items + `.use`)
        # multiply the live per-minute roll while they're in effect.
        xp_boost = await self.get_active_effect(session["user_id"], session["guild_id"], "xp_boost", now)
        if xp_boost:
            delta_xp *= xp_boost["multiplier"]
        coin_boost = await self.get_active_effect(session["user_id"], session["guild_id"], "coin_boost", now)
        if coin_boost:
            delta_coins *= coin_boost["multiplier"]

        await self.conn.execute(
            "UPDATE sessions SET credited_seconds = credited_seconds + ?, credited_xp = credited_xp + ?, "
            "credited_coins = credited_coins + ? WHERE session_id = ?",
            (delta_seconds, delta_xp, delta_coins, session_id),
        )
        await self.conn.commit()

        old_level, new_level, streak_res = await self._apply_time_and_xp(
            session["user_id"], session["guild_id"], session["subject"], delta_seconds, delta_xp,
            delta_coins=delta_coins, now=now,
        )

        # Feeds whichever pet is currently `.equip`ped, if any - a no-op
        # (returns None) if the user has no pet equipped in this guild.
        pet_result = await self.grant_pet_xp(session["user_id"], session["guild_id"], delta_pet_xp)

        # Warm and progress active incubator slots with study seconds
        ready_incubators = await self.credit_incubator(session["user_id"], session["guild_id"], delta_seconds)

        # Roll for a surprise egg drop while studying!
        egg_dropped = egg_catalog.roll_study_egg(new_minutes)
        if egg_dropped:
            await self.add_item(session["user_id"], session["guild_id"], egg_dropped, 1)

        return {
            "user_id": session["user_id"],
            "guild_id": session["guild_id"],
            "subject": session["subject"],
            "delta_seconds": delta_seconds,
            "delta_xp": delta_xp,
            "delta_coins": delta_coins,
            "old_level": old_level,
            "new_level": new_level,
            "leveled_up": new_level > old_level,
            "delta_pet_xp": delta_pet_xp,
            "pet_result": pet_result,
            "streak_broken_from": streak_res.streak_broken_from if streak_res else 0,
            "egg_drop": egg_dropped,
            "ready_incubators": ready_incubators,
        }

    async def end_session(
        self, session_id: int, end_time: int, reason: str
    ) -> Optional[dict[str, Any]]:
        """Finalize a session: flush any last full minutes via
        credit_progress(), roll the sub-minute remainder in (time only,
        no XP for an incomplete minute), mark it ended, and write a
        session_log row for leaderboard history.

        Returns a summary dict, or None if the session was already
        closed (e.g. by a concurrent event) or doesn't exist.
        """
        await self.credit_progress(session_id, end_time)

        cur = await self.conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = await cur.fetchone()
        if not row or row["status"] != "active":
            return None
        session = dict(row)

        start_time = session["start_time"]
        duration = max(0, end_time - start_time)
        leftover_seconds = max(0, duration - session["credited_seconds"])

        await self.conn.execute(
            """
            UPDATE sessions
            SET status = 'ended', end_time = ?, elapsed_seconds = ?, end_reason = ?
            WHERE session_id = ?
            """,
            (end_time, duration, reason, session_id),
        )
        await self.conn.commit()

        old_level, new_level, streak_res = await self._apply_time_and_xp(
            session["user_id"], session["guild_id"], session["subject"],
            leftover_seconds, 0, increment_session_count=True, now=end_time,
        )

        total_xp_earned = session["credited_xp"]
        total_coins_earned = session["credited_coins"]

        await self.conn.execute(
            """
            INSERT INTO session_log
                (user_id, guild_id, channel_id, subject, start_time, end_time, duration_seconds, xp_earned, end_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"], session["guild_id"], session["channel_id"], session["subject"],
                start_time, end_time, duration, total_xp_earned, reason,
            ),
        )
        await self.conn.commit()

        stats = await self.get_or_create_user_stats(session["user_id"], session["guild_id"])

        return {
            "user_id": session["user_id"],
            "guild_id": session["guild_id"],
            "channel_id": session["channel_id"],
            "subject": session["subject"],
            "duration": duration,
            "xp_earned": total_xp_earned,
            "coins_earned": total_coins_earned,
            "total_seconds": stats["total_seconds"],
            "old_level": old_level,
            "new_level": new_level,
            "leveled_up": new_level > old_level,
            "reason": reason,
            "streak_broken_from": streak_res.streak_broken_from if streak_res else 0,
        }

    # ------------------------------------------------------------------ #
    # Dev-only grants (config.DEV_USER_ID) - see cogs/dev.py
    # ------------------------------------------------------------------ #
    async def grant_time(
        self, user_id: int, guild_id: int, seconds: int, subject: Optional[str] = None,
        now: Optional[int] = None,
    ) -> dict[str, Any]:
        """Directly add study time (+ proportional randomized XP) to a
        user's stats, and log it as a completed session ending now so it
        counts correctly in every leaderboard period. Does not touch the
        `sessions` table - this isn't a live session."""
        now = now if now is not None else int(time.time())
        minutes = seconds // 60
        xp_earned = _random_minute_xp(minutes)
        coins_earned = _random_minute_coins(minutes)

        old_level, new_level, _ = await self._apply_time_and_xp(
            user_id, guild_id, subject, seconds, xp_earned, delta_coins=coins_earned, now=now,
        )

        start_time = now - seconds
        await self.conn.execute(
            """
            INSERT INTO session_log
                (user_id, guild_id, channel_id, subject, start_time, end_time, duration_seconds, xp_earned, end_reason)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 'dev_grant')
            """,
            (user_id, guild_id, subject, start_time, now, seconds, xp_earned),
        )
        await self.conn.commit()

        return {
            "seconds": seconds,
            "xp_earned": xp_earned,
            "coins_earned": coins_earned,
            "old_level": old_level,
            "new_level": new_level,
            "leveled_up": new_level > old_level,
        }

    async def remove_time(
        self, user_id: int, guild_id: int, seconds: int, subject: Optional[str] = None,
    ) -> dict[str, Any]:
        """[Dev only, see cogs/dev.py] Subtract study time from a user's
        stats, along with proportional XP/coins at the *average*
        configured rate (deterministic, unlike the random roll used for
        real studying) - meant for correcting a mistake, not gameplay.
        Everything floors at 0; never goes negative. Does not touch
        `session_log` (nothing to "un-log" cleanly), so leaderboard
        history for the period the time was originally earned in is
        left as-is; only the running totals are corrected.
        """
        stats = await self.get_or_create_user_stats(user_id, guild_id)
        old_level = stats["level"]

        minutes = seconds // 60
        avg_xp_rate = (config.XP_MIN_PER_MINUTE + config.XP_MAX_PER_MINUTE) / 2
        avg_coin_rate = (config.COINS_MIN_PER_MINUTE + config.COINS_MAX_PER_MINUTE) / 2
        xp_to_remove = round(minutes * avg_xp_rate)
        coins_to_remove = round(minutes * avg_coin_rate)

        actual_seconds_removed = min(seconds, stats["total_seconds"])
        actual_xp_removed = min(xp_to_remove, stats["xp"])
        new_total_seconds = stats["total_seconds"] - actual_seconds_removed
        new_xp = stats["xp"] - actual_xp_removed
        new_level = level_from_xp(new_xp)

        await self.conn.execute(
            "UPDATE user_stats SET total_seconds = ?, xp = ?, level = ? WHERE user_id = ? AND guild_id = ?",
            (new_total_seconds, new_xp, new_level, user_id, guild_id),
        )
        if subject:
            await self.conn.execute(
                "UPDATE subject_stats SET total_seconds = MAX(0, total_seconds - ?) "
                "WHERE user_id = ? AND guild_id = ? AND subject = ?",
                (seconds, user_id, guild_id, subject),
            )
        await self.conn.commit()

        currency = await self.get_or_create_currency(user_id, guild_id)
        actual_coins_removed = min(coins_to_remove, currency["coins"])
        new_coins = currency["coins"] - actual_coins_removed
        new_lifetime = max(0, currency["lifetime_earned"] - coins_to_remove)
        await self.conn.execute(
            "UPDATE user_currency SET coins = ?, lifetime_earned = ? WHERE user_id = ? AND guild_id = ?",
            (new_coins, new_lifetime, user_id, guild_id),
        )
        await self.conn.commit()

        return {
            "seconds_removed": actual_seconds_removed,
            "xp_removed": actual_xp_removed,
            "coins_removed": actual_coins_removed,
            "old_level": old_level,
            "new_level": new_level,
            "leveled_down": new_level < old_level,
        }

    async def grant_xp(self, user_id: int, guild_id: int, amount: int) -> dict[str, Any]:
        """Directly add raw XP (no time change) to a user's stats.
        Floors at 0 - a negative amount can remove at most the XP the
        user currently has."""
        old_level, new_level, _ = await self._apply_time_and_xp(user_id, guild_id, None, 0, amount)
        return {"old_level": old_level, "new_level": new_level, "leveled_up": new_level > old_level}

    async def grant_coins(self, user_id: int, guild_id: int, amount: int) -> int:
        """[Dev only, see cogs/dev.py] Directly add raw coins. Returns new balance."""
        return await self.add_coins(user_id, guild_id, amount)

    async def remove_coins(self, user_id: int, guild_id: int, amount: int) -> int:
        """[Dev only, see cogs/dev.py] Subtract coins, floored at 0
        (never goes negative). Doesn't touch lifetime_earned. Returns
        the new balance."""
        currency = await self.get_or_create_currency(user_id, guild_id)
        new_balance = max(0, currency["coins"] - amount)
        await self.conn.execute(
            "UPDATE user_currency SET coins = ? WHERE user_id = ? AND guild_id = ?",
            (new_balance, user_id, guild_id),
        )
        await self.conn.commit()
        return new_balance

    # ------------------------------------------------------------------ #
    # Coins
    # ------------------------------------------------------------------ #
    async def get_or_create_currency(self, user_id: int, guild_id: int) -> dict[str, Any]:
        await self.conn.execute(
            "INSERT OR IGNORE INTO user_currency (user_id, guild_id) VALUES (?, ?)",
            (user_id, guild_id),
        )
        await self.conn.commit()
        cur = await self.conn.execute(
            "SELECT * FROM user_currency WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )
        row = await cur.fetchone()
        return dict(row)

    async def add_coins(self, user_id: int, guild_id: int, amount: int) -> int:
        """Add (or, with a negative amount, remove) coins outside of the
        studying flow - daily rewards, mystery boxes, dev grants.
        Returns the new balance."""
        await self._add_coins_raw(user_id, guild_id, amount)
        await self.conn.commit()
        currency = await self.get_or_create_currency(user_id, guild_id)
        return currency["coins"]

    async def spend_coins(self, user_id: int, guild_id: int, amount: int) -> bool:
        """Attempt to deduct `amount` coins. Returns False (no change
        made) if the balance is insufficient."""
        currency = await self.get_or_create_currency(user_id, guild_id)
        if currency["coins"] < amount:
            return False
        await self.conn.execute(
            "UPDATE user_currency SET coins = coins - ? WHERE user_id = ? AND guild_id = ?",
            (amount, user_id, guild_id),
        )
        await self.conn.commit()
        return True

    # ------------------------------------------------------------------ #
    # Inventory
    # ------------------------------------------------------------------ #
    async def get_inventory(self, user_id: int, guild_id: int) -> dict[str, int]:
        cur = await self.conn.execute(
            "SELECT item_id, quantity FROM user_inventory WHERE user_id = ? AND guild_id = ? AND quantity > 0",
            (user_id, guild_id),
        )
        rows = await cur.fetchall()
        return {r["item_id"]: r["quantity"] for r in rows}

    async def get_item_qty(self, user_id: int, guild_id: int, item_id: str) -> int:
        cur = await self.conn.execute(
            "SELECT quantity FROM user_inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?",
            (user_id, guild_id, item_id),
        )
        row = await cur.fetchone()
        return row["quantity"] if row else 0

    async def add_item(self, user_id: int, guild_id: int, item_id: str, qty: int = 1) -> None:
        await self.conn.execute(
            """
            INSERT INTO user_inventory (user_id, guild_id, item_id, quantity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (user_id, guild_id, item_id, qty),
        )
        await self.conn.commit()

    async def remove_item(self, user_id: int, guild_id: int, item_id: str, qty: int = 1) -> bool:
        """Returns False (no change made) if fewer than `qty` are owned."""
        owned = await self.get_item_qty(user_id, guild_id, item_id)
        if owned < qty:
            return False
        await self.conn.execute(
            "UPDATE user_inventory SET quantity = quantity - ? WHERE user_id = ? AND guild_id = ? AND item_id = ?",
            (qty, user_id, guild_id, item_id),
        )
        await self.conn.commit()
        return True

    # ------------------------------------------------------------------ #
    # Timed boost effects (xp_boost / coin_boost)
    # ------------------------------------------------------------------ #
    async def activate_effect(
        self, user_id: int, guild_id: int, effect_id: str, duration_seconds: int,
        multiplier: int = 2, now: Optional[int] = None,
    ) -> int:
        """Activate a timed effect, extending it if one of the same
        type is already running. Returns the new expiry epoch."""
        now = now if now is not None else int(time.time())
        current = await self.get_active_effect(user_id, guild_id, effect_id, now)
        base = current["expires_at"] if current else now
        expires_at = max(now, base) + duration_seconds
        await self.conn.execute(
            """
            INSERT INTO user_effects (user_id, guild_id, effect_id, expires_at, multiplier)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id, effect_id) DO UPDATE SET
                expires_at = excluded.expires_at, multiplier = excluded.multiplier
            """,
            (user_id, guild_id, effect_id, expires_at, multiplier),
        )
        await self.conn.commit()
        return expires_at

    async def get_active_effect(
        self, user_id: int, guild_id: int, effect_id: str, now: Optional[int] = None
    ) -> Optional[dict[str, Any]]:
        """Returns the effect row if still active, lazily deleting (and
        returning None for) one that has expired."""
        now = now if now is not None else int(time.time())
        cur = await self.conn.execute(
            "SELECT * FROM user_effects WHERE user_id = ? AND guild_id = ? AND effect_id = ?",
            (user_id, guild_id, effect_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        if row["expires_at"] <= now:
            await self.conn.execute(
                "DELETE FROM user_effects WHERE user_id = ? AND guild_id = ? AND effect_id = ?",
                (user_id, guild_id, effect_id),
            )
            await self.conn.commit()
            return None
        return dict(row)

    # ------------------------------------------------------------------ #
    # Titles (cosmetic, unlocked via the shop)
    # ------------------------------------------------------------------ #
    async def set_equipped_title(self, user_id: int, guild_id: int, title_text: Optional[str]) -> None:
        await self.get_or_create_user_stats(user_id, guild_id)
        await self.conn.execute(
            "UPDATE user_stats SET equipped_title = ? WHERE user_id = ? AND guild_id = ?",
            (title_text, user_id, guild_id),
        )
        await self.conn.commit()

    # ------------------------------------------------------------------ #
    # Shop: buying, activating boosts, opening mystery boxes
    # ------------------------------------------------------------------ #
    async def buy_item(self, user_id: int, guild_id: int, item_id: str, quantity: int = 1) -> dict[str, Any]:
        """Purchase a shop item - either a built-in one (see
        utils/economy.py SHOP_ITEMS) or a custom tag this server's dev
        added (see cogs/customization.py). `quantity` stacks for
        consumables/boosts; titles are always exactly 1 (one-time
        unlock). Returns {'success': True, 'item': {...}, 'quantity':
        int, 'total_price': int} or {'success': False, 'reason':
        'not_found' | 'already_owned' | 'title_quantity' | 'insufficient_funds'}.
        """
        item = economy.SHOP_ITEMS.get(item_id)
        if item is None:
            custom = await self.get_custom_tags(guild_id)
            item = custom.get(item_id)
        if item is None:
            return {"success": False, "reason": "not_found"}

        if item["type"] == "title":
            if quantity != 1:
                return {"success": False, "reason": "title_quantity"}
            owned = await self.get_item_qty(user_id, guild_id, item_id)
            if owned > 0:
                return {"success": False, "reason": "already_owned"}

        total_price = item["price"] * quantity
        spent = await self.spend_coins(user_id, guild_id, total_price)
        if not spent:
            return {"success": False, "reason": "insufficient_funds"}

        await self.add_item(user_id, guild_id, item_id, quantity)
        await self.get_or_create_currency(user_id, guild_id)
        await self.conn.execute(
            "UPDATE user_currency SET items_purchased = items_purchased + ? WHERE user_id = ? AND guild_id = ?",
            (quantity, user_id, guild_id),
        )
        await self.conn.commit()
        return {"success": True, "item": item, "quantity": quantity, "total_price": total_price}

    async def use_boost_item(
        self, user_id: int, guild_id: int, item_id: str, now: Optional[int] = None
    ) -> dict[str, Any]:
        """Consume one charge of an owned boost item to activate its effect."""
        item = economy.SHOP_ITEMS.get(item_id)
        if item is None or item["type"] != "boost":
            return {"success": False, "reason": "not_a_boost"}

        removed = await self.remove_item(user_id, guild_id, item_id, 1)
        if not removed:
            return {"success": False, "reason": "not_owned"}

        duration_seconds = item["duration_minutes"] * 60
        expires_at = await self.activate_effect(
            user_id, guild_id, item["effect_id"], duration_seconds, item["multiplier"], now,
        )
        return {"success": True, "item": item, "expires_at": expires_at}

    async def open_mystery_box(self, user_id: int, guild_id: int, now: Optional[int] = None) -> dict[str, Any]:
        """Consume one owned Mystery Box and roll its reward."""
        now = now if now is not None else int(time.time())
        removed = await self.remove_item(user_id, guild_id, "mystery_box", 1)
        if not removed:
            return {"success": False, "reason": "not_owned"}

        reward = economy.roll_mystery_box()
        old_level = new_level = None
        if reward["kind"] == "coins":
            await self.add_coins(user_id, guild_id, reward["amount"])
        elif reward["kind"] == "xp":
            result = await self.grant_xp(user_id, guild_id, reward["amount"])
            old_level, new_level = result["old_level"], result["new_level"]
        elif reward["kind"] == "item":
            await self.add_item(user_id, guild_id, reward["item_id"], reward["qty"])

        await self.get_or_create_currency(user_id, guild_id)
        await self.conn.execute(
            "UPDATE user_currency SET boxes_opened = boxes_opened + 1 WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await self.conn.commit()

        return {
            "success": True,
            "reward": reward,
            "old_level": old_level,
            "new_level": new_level,
            "leveled_up": bool(new_level is not None and old_level is not None and new_level > old_level),
        }

    # ------------------------------------------------------------------ #
    # Pets: buying, equipping, nicknames, feeding (see utils/pets.py for
    # the species catalog, utils/food.py for the food catalog, and
    # cogs/pets.py for the `.petshop`/`.buypet`/`.pets`/`.pet`/`.equip`/
    # `.nickname`/`.foodshop`/`.buyfood`/`.feed`/`.sellfood` commands).
    # ------------------------------------------------------------------ #
    async def get_owned_pets(self, user_id: int, guild_id: int) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM user_pets WHERE user_id = ? AND guild_id = ? ORDER BY acquired_at ASC",
            (user_id, guild_id),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_pet(self, user_id: int, guild_id: int, species_id: str) -> Optional[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM user_pets WHERE user_id = ? AND guild_id = ? AND species_id = ?",
            (user_id, guild_id, species_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_equipped_pet(self, user_id: int, guild_id: int) -> Optional[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM user_pets WHERE user_id = ? AND guild_id = ? AND equipped = 1",
            (user_id, guild_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def buy_pet(self, user_id: int, guild_id: int, species_id: str) -> dict[str, Any]:
        """Unlock a species from `.petshop`. Auto-equips it if this is
        the user's first pet in this server (nothing to conflict with
        yet). Returns {'success': True, 'price': int, 'auto_equipped':
        bool} or {'success': False, 'reason': 'not_found' |
        'already_owned' | 'level_too_low' | 'insufficient_funds'}.
        """
        if species_id not in pet_catalog.PETS:
            return {"success": False, "reason": "not_found"}
        if await self.get_pet(user_id, guild_id, species_id):
            return {"success": False, "reason": "already_owned"}

        stats = await self.get_or_create_user_stats(user_id, guild_id)
        if stats["level"] < config.PET_UNLOCK_LEVEL:
            return {"success": False, "reason": "level_too_low"}

        price = pet_catalog.pet_cost(species_id)
        spent = await self.spend_coins(user_id, guild_id, price)
        if not spent:
            return {"success": False, "reason": "insufficient_funds"}

        now = int(time.time())
        already_has_pets = bool(await self.get_owned_pets(user_id, guild_id))
        auto_equip = not already_has_pets
        if auto_equip:
            await self.conn.execute(
                "UPDATE user_pets SET equipped = 0 WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
            )
        await self.conn.execute(
            """
            INSERT INTO user_pets (user_id, guild_id, species_id, nickname, level, xp, equipped, acquired_at)
            VALUES (?, ?, ?, ?, 1, 0, ?, ?)
            """,
            (user_id, guild_id, species_id, pet_catalog.PETS[species_id]["name"], int(auto_equip), now),
        )
        await self.get_or_create_currency(user_id, guild_id)
        await self.conn.execute(
            "UPDATE user_currency SET items_purchased = items_purchased + 1 WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await self.conn.commit()
        return {"success": True, "price": price, "auto_equipped": auto_equip}

    async def equip_pet(self, user_id: int, guild_id: int, species_id: str) -> bool:
        """Returns False if the user doesn't own that species."""
        if not await self.get_pet(user_id, guild_id, species_id):
            return False
        await self.conn.execute(
            "UPDATE user_pets SET equipped = 0 WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )
        await self.conn.execute(
            "UPDATE user_pets SET equipped = 1 WHERE user_id = ? AND guild_id = ? AND species_id = ?",
            (user_id, guild_id, species_id),
        )
        await self.conn.commit()
        return True

    async def rename_pet(self, user_id: int, guild_id: int, species_id: str, nickname: str) -> bool:
        """Returns False if the user doesn't own that species."""
        if not await self.get_pet(user_id, guild_id, species_id):
            return False
        await self.conn.execute(
            "UPDATE user_pets SET nickname = ? WHERE user_id = ? AND guild_id = ? AND species_id = ?",
            (nickname, user_id, guild_id, species_id),
        )
        await self.conn.commit()
        return True

    async def grant_pet_xp(self, user_id: int, guild_id: int, amount: int) -> Optional[dict[str, Any]]:
        """Add XP to whichever pet is currently `.equip`ped. Returns a
        summary dict, or None if nothing is equipped (or amount <= 0)."""
        if amount <= 0:
            return None
        pet = await self.get_equipped_pet(user_id, guild_id)
        if not pet:
            return None

        old_level = pet["level"]
        old_stage = pet_catalog.stage_for_level(pet["species_id"], old_level)
        new_xp = pet["xp"] + amount
        new_level = pet_catalog.level_from_xp(new_xp)
        new_stage = pet_catalog.stage_for_level(pet["species_id"], new_level)

        await self.conn.execute(
            "UPDATE user_pets SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ? AND species_id = ?",
            (new_xp, new_level, user_id, guild_id, pet["species_id"]),
        )
        await self.conn.commit()

        return {
            "species_id": pet["species_id"],
            "nickname": pet["nickname"],
            "xp_gained": amount,
            "old_level": old_level,
            "new_level": new_level,
            "leveled_up": new_level > old_level,
            "old_stage": old_stage,
            "new_stage": new_stage,
            "evolved": old_stage["name"] != new_stage["name"],
        }

    async def get_food_inventory(self, user_id: int, guild_id: int) -> dict[str, int]:
        inventory = await self.get_inventory(user_id, guild_id)
        return {item_id: qty for item_id, qty in inventory.items() if item_id in food_catalog.FOODS}

    async def buy_food(self, user_id: int, guild_id: int, food_id: str, qty: int = 1) -> dict[str, Any]:
        """Returns {'success': True, 'total_price': int, 'qty': int} or
        {'success': False, 'reason': 'not_found' | 'insufficient_funds'}."""
        if food_id not in food_catalog.FOODS:
            return {"success": False, "reason": "not_found"}

        total_price = food_catalog.FOODS[food_id]["cost"] * qty
        spent = await self.spend_coins(user_id, guild_id, total_price)
        if not spent:
            return {"success": False, "reason": "insufficient_funds"}

        await self.add_item(user_id, guild_id, food_id, qty)
        await self.get_or_create_currency(user_id, guild_id)
        await self.conn.execute(
            "UPDATE user_currency SET items_purchased = items_purchased + ? WHERE user_id = ? AND guild_id = ?",
            (qty, user_id, guild_id),
        )
        await self.conn.commit()
        return {"success": True, "total_price": total_price, "qty": qty}

    async def feed_pet(self, user_id: int, guild_id: int, food_id: str, qty: int = 1) -> dict[str, Any]:
        """Consume `qty` of an owned food item, feeding all of its XP to
        the equipped pet. Returns {'success': False, 'reason':
        'not_found' | 'no_pet_equipped' | 'not_owned'} or a merged
        {'success': True, 'xp_gained', 'qty', **grant_pet_xp() result}."""
        if food_id not in food_catalog.FOODS:
            return {"success": False, "reason": "not_found"}
        if not await self.get_equipped_pet(user_id, guild_id):
            return {"success": False, "reason": "no_pet_equipped"}

        removed = await self.remove_item(user_id, guild_id, food_id, qty)
        if not removed:
            return {"success": False, "reason": "not_owned"}

        total_xp = food_catalog.FOODS[food_id]["xp"] * qty
        result = await self.grant_pet_xp(user_id, guild_id, total_xp)
        return {"success": True, "qty": qty, **result}

    async def sell_food(self, user_id: int, guild_id: int, food_id: str, qty: int = 1) -> dict[str, Any]:
        """Sell owned food back for FOOD_SELL_RATE of its shop price.
        Returns {'success': False, 'reason': 'not_found' | 'not_owned'}
        or {'success': True, 'refund': int, 'qty': int, 'new_balance': int}."""
        if food_id not in food_catalog.FOODS:
            return {"success": False, "reason": "not_found"}
        removed = await self.remove_item(user_id, guild_id, food_id, qty)
        if not removed:
            return {"success": False, "reason": "not_owned"}

        refund = round(food_catalog.FOODS[food_id]["cost"] * config.FOOD_SELL_RATE) * qty
        new_balance = await self.add_coins(user_id, guild_id, refund)
        return {"success": True, "refund": refund, "qty": qty, "new_balance": new_balance}

    # ------------------------------------------------------------------ #
    # Generic per-command cooldowns (`.work` / `.weekly` - see
    # cogs/economy.py). Kept separate from `user_daily`, which is
    # specifically calendar-day-based (IST) rather than a rolling window.
    # ------------------------------------------------------------------ #
    async def get_cooldown(self, user_id: int, guild_id: int, cooldown_id: str) -> Optional[int]:
        cur = await self.conn.execute(
            "SELECT last_used FROM user_cooldowns WHERE user_id = ? AND guild_id = ? AND cooldown_id = ?",
            (user_id, guild_id, cooldown_id),
        )
        row = await cur.fetchone()
        return row["last_used"] if row else None

    async def _set_cooldown(self, user_id: int, guild_id: int, cooldown_id: str, now: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO user_cooldowns (user_id, guild_id, cooldown_id, last_used)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id, cooldown_id) DO UPDATE SET last_used = excluded.last_used
            """,
            (user_id, guild_id, cooldown_id, now),
        )

    async def claim_work(self, user_id: int, guild_id: int, now: Optional[int] = None) -> dict[str, Any]:
        """`.work` - a short-cooldown coin (+small XP) grant, meant to be
        claimed often. Returns {'success': False, 'reason': 'cooldown',
        'retry_after': int} or {'success': True, 'coins', 'xp',
        'new_balance', 'old_level', 'new_level', 'leveled_up'}."""
        now = now if now is not None else int(time.time())
        last = await self.get_cooldown(user_id, guild_id, "work")
        if last is not None and now - last < config.WORK_COOLDOWN_SECONDS:
            return {"success": False, "reason": "cooldown", "retry_after": config.WORK_COOLDOWN_SECONDS - (now - last)}

        coins = random.randint(config.WORK_COINS_MIN, config.WORK_COINS_MAX)
        xp = random.randint(config.WORK_XP_MIN, config.WORK_XP_MAX)
        await self._set_cooldown(user_id, guild_id, "work", now)
        await self.conn.commit()
        new_balance = await self.add_coins(user_id, guild_id, coins)
        xp_result = await self.grant_xp(user_id, guild_id, xp)
        return {"success": True, "coins": coins, "xp": xp, "new_balance": new_balance, **xp_result}

    async def claim_beg(self, user_id: int, guild_id: int, now: Optional[int] = None) -> dict[str, Any]:
        """`.beg` - an even-shorter-cooldown coin grant than `.work`,
        with a chance of coming up empty (see config.BEG_FAIL_CHANCE) -
        pure flavor, meant to be spammed between study blocks. Returns
        {'success': False, 'reason': 'cooldown', 'retry_after': int} or
        {'success': True, 'coins': int (0 on a whiff), 'new_balance': int}."""
        now = now if now is not None else int(time.time())
        last = await self.get_cooldown(user_id, guild_id, "beg")
        if last is not None and now - last < config.BEG_COOLDOWN_SECONDS:
            return {"success": False, "reason": "cooldown", "retry_after": config.BEG_COOLDOWN_SECONDS - (now - last)}

        await self._set_cooldown(user_id, guild_id, "beg", now)
        await self.conn.commit()
        if random.random() < config.BEG_FAIL_CHANCE:
            currency = await self.get_or_create_currency(user_id, guild_id)
            return {"success": True, "coins": 0, "new_balance": currency["coins"]}

        coins = random.randint(config.BEG_COINS_MIN, config.BEG_COINS_MAX)
        new_balance = await self.add_coins(user_id, guild_id, coins)
        return {"success": True, "coins": coins, "new_balance": new_balance}

    async def claim_weekly(self, user_id: int, guild_id: int, now: Optional[int] = None) -> dict[str, Any]:
        """`.weekly` - a large, once-a-week coin grant plus a free
        Mystery Box. Returns {'success': False, 'reason': 'cooldown',
        'retry_after': int} or {'success': True, 'coins', 'new_balance'}."""
        now = now if now is not None else int(time.time())
        last = await self.get_cooldown(user_id, guild_id, "weekly")
        if last is not None and now - last < config.WEEKLY_COOLDOWN_SECONDS:
            return {"success": False, "reason": "cooldown", "retry_after": config.WEEKLY_COOLDOWN_SECONDS - (now - last)}

        coins = random.randint(config.WEEKLY_COINS_MIN, config.WEEKLY_COINS_MAX)
        await self._set_cooldown(user_id, guild_id, "weekly", now)
        await self.conn.commit()
        new_balance = await self.add_coins(user_id, guild_id, coins)
        await self.add_item(user_id, guild_id, "mystery_box", 1)
        return {"success": True, "coins": coins, "new_balance": new_balance}

    # ------------------------------------------------------------------ #
    # `.daily`
    # ------------------------------------------------------------------ #
    async def get_daily_status(self, user_id: int, guild_id: int) -> dict[str, Any]:
        await self.conn.execute(
            "INSERT OR IGNORE INTO user_daily (user_id, guild_id) VALUES (?, ?)",
            (user_id, guild_id),
        )
        await self.conn.commit()
        cur = await self.conn.execute(
            "SELECT * FROM user_daily WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )
        row = await cur.fetchone()
        return dict(row)

    async def claim_daily(self, user_id: int, guild_id: int, now: Optional[int] = None) -> dict[str, Any]:
        """Claim the once-per-IST-day `.daily` reward. Returns
        {'success': False, 'reason': 'already_claimed', ...} if already
        claimed today, otherwise the reward breakdown."""
        now = now if now is not None else int(time.time())
        today = streaks.date_str(now)
        status = await self.get_daily_status(user_id, guild_id)

        if status["last_claim_date"] == today:
            return {"success": False, "reason": "already_claimed", "daily_streak": status["daily_streak"]}

        if status["last_claim_date"] is None:
            new_streak = 1
        elif streaks.days_between(status["last_claim_date"], today) == 1:
            new_streak = status["daily_streak"] + 1
        else:
            new_streak = 1  # missed a day (or more) - streak resets

        reward = economy.compute_daily_reward(new_streak)
        await self.conn.execute(
            "UPDATE user_daily SET last_claim_date = ?, daily_streak = ? WHERE user_id = ? AND guild_id = ?",
            (today, new_streak, user_id, guild_id),
        )
        await self.conn.commit()
        new_balance = await self.add_coins(user_id, guild_id, reward["coins"])
        xp_result = await self.grant_xp(user_id, guild_id, reward["xp"])

        if reward["bonus_box"]:
            await self.add_item(user_id, guild_id, "mystery_box", 1)

        milestone_item = None
        milestone = reward["milestone"]
        if milestone and milestone.get("item"):
            milestone_item = milestone["item"]
            await self.add_item(user_id, guild_id, milestone_item, 1)

        return {
            "success": True,
            "coins": reward["coins"],
            "base_coins": reward["base_coins"],
            "streak_bonus": reward["streak_bonus"],
            "xp": reward["xp"],
            "daily_streak": new_streak,
            "bonus_box": reward["bonus_box"],
            "new_balance": new_balance,
            "leveled_up": xp_result["leveled_up"],
            "old_level": xp_result["old_level"],
            "new_level": xp_result["new_level"],
            "milestone": milestone,
            "milestone_item": milestone_item,
        }

    # ------------------------------------------------------------------ #
    # Dev-configurable branding: tier renames & custom shop tags/titles
    # (see cogs/customization.py, dev-only). utils/xp.py's TIERS and
    # utils/economy.py's SHOP_ITEMS remain the global defaults/fallback
    # if a server never customizes anything - editing those files
    # directly still works too, this is just a no-redeploy option.
    # ------------------------------------------------------------------ #
    async def get_tier_overrides(self, guild_id: int) -> dict[int, str]:
        cur = await self.conn.execute(
            "SELECT level, name FROM guild_tier_overrides WHERE guild_id = ?", (guild_id,)
        )
        rows = await cur.fetchall()
        return {r["level"]: r["name"] for r in rows}

    async def get_effective_tiers(self, guild_id: int) -> list[tuple[int, str]]:
        """utils.xp.TIERS with this guild's renames applied - pass the
        result to utils.xp.tier_for_level(level, tiers=...)."""
        overrides = await self.get_tier_overrides(guild_id)
        if not overrides:
            return TIERS
        return [(level, overrides.get(level, name)) for level, name in TIERS]

    async def set_tier_override(self, guild_id: int, level: int, name: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO guild_tier_overrides (guild_id, level, name) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, level) DO UPDATE SET name = excluded.name
            """,
            (guild_id, level, name),
        )
        await self.conn.commit()

    async def reset_tier_override(self, guild_id: int, level: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM guild_tier_overrides WHERE guild_id = ? AND level = ?", (guild_id, level)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def reset_all_tier_overrides(self, guild_id: int) -> int:
        cur = await self.conn.execute("DELETE FROM guild_tier_overrides WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()
        return cur.rowcount

    async def get_custom_tags(self, guild_id: int) -> dict[str, dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT item_id, title_text, price FROM guild_custom_tags WHERE guild_id = ?", (guild_id,)
        )
        rows = await cur.fetchall()
        return {
            r["item_id"]: {
                "name": f"Title: {r['title_text']}", "emoji": "\U0001F3F7\uFE0F", "price": r["price"],
                "type": "title", "title_text": r["title_text"],
                "description": "A custom title added by this server's admin.",
            }
            for r in rows
        }

    async def add_custom_tag(self, guild_id: int, title_text: str, price: int) -> str:
        """Returns the generated item_id (e.g. 'custom_the_grinder')."""
        item_id = "custom_" + "".join(c.lower() if c.isalnum() else "_" for c in title_text).strip("_")
        await self.conn.execute(
            """
            INSERT INTO guild_custom_tags (guild_id, item_id, title_text, price) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, item_id) DO UPDATE SET title_text = excluded.title_text, price = excluded.price
            """,
            (guild_id, item_id, title_text, price),
        )
        await self.conn.commit()
        return item_id

    async def remove_custom_tag(self, guild_id: int, item_id: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM guild_custom_tags WHERE guild_id = ? AND item_id = ?", (guild_id, item_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Manually-logged progress: chapters, books, PYQs, revisions
    # ------------------------------------------------------------------ #
    async def log_milestone(
        self, user_id: int, guild_id: int, type_: str, label: str,
        subject: Optional[str] = None, chapter: Optional[str] = None, now: Optional[int] = None,
    ) -> None:
        now = now if now is not None else int(time.time())
        await self.conn.execute(
            "INSERT INTO user_milestones (user_id, guild_id, type, subject, chapter, label, logged_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, guild_id, type_, subject, chapter, label, now),
        )
        await self.conn.commit()

    async def get_milestone_counts(self, user_id: int, guild_id: int) -> dict[str, Any]:
        """{'chapters_completed', 'subtopics_completed', 'books_completed',
        'pyq_years_completed', 'max_revision'} for achievement checks
        and `.progress`."""
        cur = await self.conn.execute(
            "SELECT type, COUNT(*) AS n, COUNT(DISTINCT label) AS distinct_n "
            "FROM user_milestones WHERE user_id = ? AND guild_id = ? GROUP BY type",
            (user_id, guild_id),
        )
        rows = {r["type"]: r for r in await cur.fetchall()}

        max_revision = 0
        if "revision" in rows:
            cur = await self.conn.execute(
                "SELECT MAX(CAST(label AS INTEGER)) AS max_n FROM user_milestones "
                "WHERE user_id = ? AND guild_id = ? AND type = 'revision'",
                (user_id, guild_id),
            )
            r = await cur.fetchone()
            max_revision = r["max_n"] or 0

        return {
            "chapters_completed": rows["chapter"]["n"] if "chapter" in rows else 0,
            "subtopics_completed": rows["subtopic"]["n"] if "subtopic" in rows else 0,
            "books_completed": rows["book"]["n"] if "book" in rows else 0,
            "pyq_years_completed": rows["pyq"]["distinct_n"] if "pyq" in rows else 0,
            "max_revision": max_revision,
        }

    async def get_recent_milestones(
        self, user_id: int, guild_id: int, type_: Optional[str] = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM user_milestones WHERE user_id = ? AND guild_id = ?"
        params: list[Any] = [user_id, guild_id]
        if type_:
            query += " AND type = ?"
            params.append(type_)
        query += " ORDER BY logged_at DESC LIMIT ?"
        params.append(limit)
        cur = await self.conn.execute(query, params)
        return [dict(r) for r in await cur.fetchall()]

    # ------------------------------------------------------------------ #
    # Achievements
    # ------------------------------------------------------------------ #
    async def get_unlocked_achievement_ids(self, user_id: int, guild_id: int) -> set[str]:
        cur = await self.conn.execute(
            "SELECT achievement_id FROM achievements_unlocked WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        rows = await cur.fetchall()
        return {r["achievement_id"] for r in rows}

    async def get_unlocked_achievements_detailed(self, user_id: int, guild_id: int) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT achievement_id, unlocked_at FROM achievements_unlocked "
            "WHERE user_id = ? AND guild_id = ? ORDER BY unlocked_at DESC",
            (user_id, guild_id),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_achievement_context(
        self, user_id: int, guild_id: int, now: Optional[int] = None
    ) -> dict[str, Any]:
        """Gather everything utils/achievements.py's predicates need to
        check a user's progress."""
        now = now if now is not None else int(time.time())
        stats = await self.get_or_create_user_stats(user_id, guild_id)
        currency = await self.get_or_create_currency(user_id, guild_id)
        daily = await self.get_daily_status(user_id, guild_id)
        subject_seconds = await self.get_subject_stats(user_id, guild_id)
        unlocked = await self.get_unlocked_achievement_ids(user_id, guild_id)
        milestone_counts = await self.get_milestone_counts(user_id, guild_id)

        week_ago = now - 7 * 86400
        cur = await self.conn.execute(
            """
            SELECT
                SUM(CASE WHEN CAST(strftime('%H', start_time, 'unixepoch', ?) AS INTEGER)
                         BETWEEN 4 AND 6 THEN 1 ELSE 0 END) AS early_bird,
                SUM(CASE WHEN CAST(strftime('%H', start_time, 'unixepoch', ?) AS INTEGER) >= 23
                          OR CAST(strftime('%H', start_time, 'unixepoch', ?) AS INTEGER) <= 2
                         THEN 1 ELSE 0 END) AS night_owl,
                COUNT(DISTINCT CASE WHEN start_time >= ? THEN date(start_time, 'unixepoch', ?) END) AS active_days
            FROM session_log
            WHERE user_id = ? AND guild_id = ?
            """,
            (
                config.IST_SQL_MODIFIER, config.IST_SQL_MODIFIER, config.IST_SQL_MODIFIER,
                week_ago, config.IST_SQL_MODIFIER, user_id, guild_id,
            ),
        )
        row = await cur.fetchone()

        return {
            "total_seconds": stats["total_seconds"],
            "level": stats["level"],
            "xp": stats["xp"],
            "sessions_count": stats["sessions_count"],
            "current_streak": stats["current_streak"],
            "longest_streak": stats["longest_streak"],
            "daily_streak": daily["daily_streak"],
            "coins_lifetime": currency["lifetime_earned"],
            "boxes_opened": currency["boxes_opened"],
            "items_purchased": currency["items_purchased"],
            "subject_seconds": subject_seconds,
            "early_bird_count": row["early_bird"] or 0,
            "night_owl_count": row["night_owl"] or 0,
            "perfect_week": (row["active_days"] or 0) >= 7,
            "achievements_count": len(unlocked),
            **milestone_counts,
        }

    async def check_achievements(self, user_id: int, guild_id: int, now: Optional[int] = None) -> list[Achievement]:
        """Evaluate every achievement against current stats, persist
        any newly-earned ones (crediting each one's one-time
        `reward_coins` payout - see utils/achievements.py), and return
        them so callers can announce them (see cogs/sessions.py,
        cogs/economy.py)."""
        now = now if now is not None else int(time.time())
        unlocked = await self.get_unlocked_achievement_ids(user_id, guild_id)
        context = await self.get_achievement_context(user_id, guild_id, now)
        newly = evaluate_achievements(context, unlocked)
        if not newly:
            return []
        for achievement in newly:
            await self.conn.execute(
                "INSERT OR IGNORE INTO achievements_unlocked (user_id, guild_id, achievement_id, unlocked_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, guild_id, achievement.id, now),
            )
            if achievement.reward_coins:
                await self._add_coins_raw(user_id, guild_id, achievement.reward_coins)
        await self.conn.commit()
        return newly

    # ------------------------------------------------------------------ #
    # Hall of Fame (per-guild all-time record holders)
    # ------------------------------------------------------------------ #
    async def get_hall_of_fame(self, guild_id: int) -> dict[str, Optional[dict[str, Any]]]:
        async def _top(query: str, params: tuple) -> Optional[dict[str, Any]]:
            cur = await self.conn.execute(query, params)
            row = await cur.fetchone()
            if not row or row["value"] is None or row["value"] <= 0:
                return None
            return {"user_id": row["user_id"], "value": row["value"]}

        hof: dict[str, Optional[dict[str, Any]]] = {}
        hof["total_time"] = await _top(
            "SELECT user_id, total_seconds AS value FROM user_stats "
            "WHERE guild_id = ? ORDER BY value DESC LIMIT 1", (guild_id,),
        )
        hof["level"] = await _top(
            "SELECT user_id, level AS value FROM user_stats "
            "WHERE guild_id = ? ORDER BY value DESC LIMIT 1", (guild_id,),
        )
        hof["longest_streak"] = await _top(
            "SELECT user_id, longest_streak AS value FROM user_stats "
            "WHERE guild_id = ? ORDER BY value DESC LIMIT 1", (guild_id,),
        )
        hof["sessions"] = await _top(
            "SELECT user_id, sessions_count AS value FROM user_stats "
            "WHERE guild_id = ? ORDER BY value DESC LIMIT 1", (guild_id,),
        )
        hof["longest_session"] = await _top(
            "SELECT user_id, duration_seconds AS value FROM session_log "
            "WHERE guild_id = ? ORDER BY value DESC LIMIT 1", (guild_id,),
        )
        hof["richest"] = await _top(
            "SELECT user_id, lifetime_earned AS value FROM user_currency "
            "WHERE guild_id = ? ORDER BY value DESC LIMIT 1", (guild_id,),
        )
        hof["achievements"] = await _top(
            "SELECT user_id, COUNT(*) AS value FROM achievements_unlocked "
            "WHERE guild_id = ? GROUP BY user_id ORDER BY value DESC LIMIT 1", (guild_id,),
        )
        for subject in ("physics", "chemistry", "maths"):
            hof[f"subject_{subject}"] = await _top(
                "SELECT user_id, total_seconds AS value FROM subject_stats "
                "WHERE guild_id = ? AND subject = ? ORDER BY value DESC LIMIT 1",
                (guild_id, subject),
            )
        return hof

    # ------------------------------------------------------------------ #
    # `.compare`
    # ------------------------------------------------------------------ #
    async def get_compare_context(self, user_id: int, guild_id: int) -> dict[str, Any]:
        stats = await self.get_or_create_user_stats(user_id, guild_id)
        currency = await self.get_or_create_currency(user_id, guild_id)
        subject_seconds = await self.get_subject_stats(user_id, guild_id)
        unlocked = await self.get_unlocked_achievement_ids(user_id, guild_id)

        cur = await self.conn.execute(
            "SELECT AVG(duration_seconds) AS avg_s, MAX(duration_seconds) AS max_s "
            "FROM session_log WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        row = await cur.fetchone()

        return {
            "total_seconds": stats["total_seconds"],
            "level": stats["level"],
            "xp": stats["xp"],
            "sessions_count": stats["sessions_count"],
            "current_streak": stats["current_streak"],
            "longest_streak": stats["longest_streak"],
            "coins": currency["coins"],
            "lifetime_earned": currency["lifetime_earned"],
            "achievements_count": len(unlocked),
            "avg_session_seconds": int(row["avg_s"] or 0),
            "longest_session_seconds": int(row["max_s"] or 0),
            "physics_seconds": subject_seconds.get("physics", 0),
            "chemistry_seconds": subject_seconds.get("chemistry", 0),
            "maths_seconds": subject_seconds.get("maths", 0),
        }

    # ------------------------------------------------------------------ #
    # Deep stats analytics (see cogs/stats.py `.stats`)
    # ------------------------------------------------------------------ #
    async def get_session_analytics(self, user_id: int, guild_id: int) -> dict[str, Any]:
        """Aggregate, from completed sessions (session_log), the extra
        numbers the revamped `.stats` embed shows: averages, records,
        and a by-weekday breakdown of *when* someone studies."""
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS n, AVG(duration_seconds) AS avg_s, MAX(duration_seconds) AS max_s, "
            "SUM(xp_earned) AS xp_from_log "
            "FROM session_log WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        overall = await cur.fetchone()

        # SQLite %w: 0=Sunday .. 6=Saturday. Shifted to IST (see config.IST).
        cur = await self.conn.execute(
            """
            SELECT CAST(strftime('%w', start_time, 'unixepoch', ?) AS INTEGER) AS weekday,
                   SUM(duration_seconds) AS total
            FROM session_log
            WHERE user_id = ? AND guild_id = ?
            GROUP BY weekday
            """,
            (config.IST_SQL_MODIFIER, user_id, guild_id),
        )
        weekday_rows = await cur.fetchall()
        weekday_seconds = {r["weekday"]: r["total"] for r in weekday_rows}

        cur = await self.conn.execute(
            "SELECT subject, SUM(duration_seconds) AS total FROM session_log "
            "WHERE user_id = ? AND guild_id = ? AND subject IS NOT NULL "
            "GROUP BY subject ORDER BY total DESC LIMIT 1",
            (user_id, guild_id),
        )
        top_subject_row = await cur.fetchone()

        return {
            "sessions_logged": overall["n"] or 0,
            "avg_session_seconds": int(overall["avg_s"] or 0),
            "longest_session_seconds": int(overall["max_s"] or 0),
            "weekday_seconds": weekday_seconds,  # {0..6: seconds}, 0=Sunday
            "favorite_subject": top_subject_row["subject"] if top_subject_row else None,
        }

    # ------------------------------------------------------------------ #
    # Leaderboards (period-filtered; alltime uses get_alltime_totals above)
    # ------------------------------------------------------------------ #
    async def sum_seconds(
        self, guild_id: int, since: Optional[int], subject: Optional[str] = None
    ) -> dict[int, int]:
        """{user_id: seconds} summed from *completed* sessions in the
        guild, optionally restricted to sessions starting on/after
        `since` and/or to one `subject`."""
        query = "SELECT user_id, SUM(duration_seconds) AS total FROM session_log WHERE guild_id = ?"
        params: list[Any] = [guild_id]
        if since is not None:
            query += " AND start_time >= ?"
            params.append(since)
        if subject is not None:
            query += " AND subject = ?"
            params.append(subject)
        query += " GROUP BY user_id"

        cur = await self.conn.execute(query, params)
        rows = await cur.fetchall()
        return {r["user_id"]: r["total"] for r in rows}

    # ------------------------------------------------------------------ #
    # Pomodoro
    # ------------------------------------------------------------------ #
    async def get_pomodoro(self, channel_id: int) -> Optional[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM pomodoro_sessions WHERE channel_id = ? AND active = 1", (channel_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_all_active_pomodoros(self) -> list[dict[str, Any]]:
        cur = await self.conn.execute("SELECT * FROM pomodoro_sessions WHERE active = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def start_pomodoro(
        self,
        channel_id: int,
        guild_id: int,
        announce_channel_id: Optional[int],
        phase_duration: int,
        now: Optional[int] = None,
    ) -> None:
        now = now if now is not None else int(time.time())
        await self.conn.execute(
            """
            INSERT INTO pomodoro_sessions
                (channel_id, guild_id, announce_channel_id, phase, phase_start, phase_duration, cycle_count, active)
            VALUES (?, ?, ?, 'focus', ?, ?, 0, 1)
            ON CONFLICT(channel_id) DO UPDATE SET
                active = 1, phase = 'focus', phase_start = excluded.phase_start,
                phase_duration = excluded.phase_duration, announce_channel_id = excluded.announce_channel_id,
                cycle_count = 0
            """,
            (channel_id, guild_id, announce_channel_id, now, phase_duration),
        )
        await self.conn.commit()

    async def update_pomodoro_phase(
        self, channel_id: int, phase: str, phase_start: int, phase_duration: int, cycle_count: int
    ) -> None:
        await self.conn.execute(
            """
            UPDATE pomodoro_sessions
            SET phase = ?, phase_start = ?, phase_duration = ?, cycle_count = ?
            WHERE channel_id = ?
            """,
            (phase, phase_start, phase_duration, cycle_count, channel_id),
        )
        await self.conn.commit()

    async def stop_pomodoro(self, channel_id: int) -> None:
        await self.conn.execute(
            "UPDATE pomodoro_sessions SET active = 0 WHERE channel_id = ?", (channel_id,)
        )
        await self.conn.commit()

    # ------------------------------------------------------------------ #
    # Eggs & Incubator (THE EGG UPDATE)
    # ------------------------------------------------------------------ #

    async def get_incubators(self, user_id: int, guild_id: int) -> list[dict[str, Any]]:
        """Return all active incubator slots for a user."""
        cur = await self.conn.execute(
            "SELECT * FROM user_incubator WHERE user_id = ? AND guild_id = ? ORDER BY slot ASC",
            (user_id, guild_id),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_incubator_slot(self, user_id: int, guild_id: int, slot: int) -> Optional[dict[str, Any]]:
        """Return a specific incubator slot."""
        cur = await self.conn.execute(
            "SELECT * FROM user_incubator WHERE user_id = ? AND guild_id = ? AND slot = ?",
            (user_id, guild_id, slot),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def start_incubation(
        self, user_id: int, guild_id: int, egg_id: str, max_slots: int = 2
    ) -> dict[str, Any]:
        """Place an egg from inventory into an available incubator slot."""
        egg = egg_catalog.get_egg(egg_id)
        if not egg:
            return {"success": False, "reason": "invalid_egg"}

        qty = await self.get_item_qty(user_id, guild_id, egg_id)
        if qty <= 0:
            return {"success": False, "reason": "not_owned"}

        cur = await self.conn.execute(
            "SELECT slot FROM user_incubator WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        occupied = {row["slot"] for row in await cur.fetchall()}
        free_slot = next((s for s in range(1, max_slots + 1) if s not in occupied), None)
        if free_slot is None:
            return {"success": False, "reason": "slots_full", "max_slots": max_slots}

        # Deduct egg from inventory
        await self.add_item(user_id, guild_id, egg_id, -1)

        now = int(time.time())
        await self.conn.execute(
            """
            INSERT INTO user_incubator (user_id, guild_id, slot, egg_id, started_at, required_seconds, credited_seconds)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (user_id, guild_id, free_slot, egg_id, now, egg["incubation_seconds"]),
        )
        await self.conn.commit()

        return {
            "success": True,
            "slot": free_slot,
            "egg": egg,
            "required_seconds": egg["incubation_seconds"],
        }

    async def credit_incubator(self, user_id: int, guild_id: int, delta_seconds: int) -> list[dict[str, Any]]:
        """Add study seconds to incubating eggs. Returns any slots that newly finished."""
        if delta_seconds <= 0:
            return []

        cur = await self.conn.execute(
            """
            SELECT slot, egg_id, required_seconds, credited_seconds
            FROM user_incubator
            WHERE user_id = ? AND guild_id = ? AND credited_seconds < required_seconds
            """,
            (user_id, guild_id),
        )
        before = [dict(r) for r in await cur.fetchall()]
        if not before:
            return []

        await self.conn.execute(
            """
            UPDATE user_incubator
            SET credited_seconds = MIN(required_seconds, credited_seconds + ?)
            WHERE user_id = ? AND guild_id = ? AND credited_seconds < required_seconds
            """,
            (delta_seconds, user_id, guild_id),
        )
        await self.conn.commit()

        newly_ready = []
        for slot_info in before:
            new_credited = slot_info["credited_seconds"] + delta_seconds
            if new_credited >= slot_info["required_seconds"]:
                egg = egg_catalog.get_egg(slot_info["egg_id"])
                newly_ready.append({
                    "slot": slot_info["slot"],
                    "egg_id": slot_info["egg_id"],
                    "egg": egg,
                })
        return newly_ready

    async def grant_hatched_pet(self, user_id: int, guild_id: int, species_id: str) -> dict[str, Any]:
        """Grant a pet hatched from an egg. If duplicate, award pet XP and bonus coins."""
        existing = await self.get_pet(user_id, guild_id, species_id)
        if existing:
            bonus_coins = 500
            bonus_pet_xp = 600
            await self.add_coins(user_id, guild_id, bonus_coins)
            await self.grant_pet_xp(user_id, guild_id, bonus_pet_xp)
            return {
                "new_pet": False,
                "species_id": species_id,
                "pet_xp_bonus": bonus_pet_xp,
                "coin_bonus": bonus_coins,
            }

        now = int(time.time())
        owned = bool(await self.get_owned_pets(user_id, guild_id))
        auto_equip = not owned
        if auto_equip:
            await self.conn.execute(
                "UPDATE user_pets SET equipped = 0 WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
        nickname = pet_catalog.PETS.get(species_id, {}).get("name", species_id.capitalize())
        await self.conn.execute(
            """
            INSERT INTO user_pets (user_id, guild_id, species_id, nickname, level, xp, equipped, acquired_at)
            VALUES (?, ?, ?, ?, 1, 0, ?, ?)
            """,
            (user_id, guild_id, species_id, nickname, int(auto_equip), now),
        )
        await self.conn.commit()
        return {
            "new_pet": True,
            "species_id": species_id,
            "nickname": nickname,
            "auto_equipped": auto_equip,
        }

    async def claim_hatch(self, user_id: int, guild_id: int, slot: int) -> dict[str, Any]:
        """Hatch a fully-incubated egg from a specific slot."""
        slot_info = await self.get_incubator_slot(user_id, guild_id, slot)
        if not slot_info:
            return {"success": False, "reason": "not_found"}

        if slot_info["credited_seconds"] < slot_info["required_seconds"]:
            return {
                "success": False,
                "reason": "still_incubating",
                "remaining_seconds": slot_info["required_seconds"] - slot_info["credited_seconds"],
            }

        await self.conn.execute(
            "DELETE FROM user_incubator WHERE user_id = ? AND guild_id = ? AND slot = ?",
            (user_id, guild_id, slot),
        )
        await self.conn.commit()

        egg_id = slot_info["egg_id"]
        egg = egg_catalog.get_egg(egg_id)
        loot = egg_catalog.generate_hatch_loot(egg_id, is_incubated=True)

        coins = loot.get("coins", 0)
        xp = loot.get("xp", 0)
        new_balance = await self.add_coins(user_id, guild_id, coins) if coins else 0
        xp_res = await self.grant_xp(user_id, guild_id, xp) if xp else {"leveled_up": False}

        pet_res = None
        if loot.get("type") == "pet" and loot.get("species_id"):
            pet_res = await self.grant_hatched_pet(user_id, guild_id, loot["species_id"])

        if loot.get("type") == "food" and loot.get("food_id"):
            await self.add_item(user_id, guild_id, loot["food_id"], loot.get("qty", 1))

        if loot.get("type") == "item" and loot.get("item_id"):
            await self.add_item(user_id, guild_id, loot["item_id"], loot.get("qty", 1))

        if loot.get("type") == "jackpot":
            if loot.get("item_id"):
                await self.add_item(user_id, guild_id, loot["item_id"], loot.get("qty", 1))
            if loot.get("title"):
                await self.set_equipped_title(user_id, guild_id, loot["title"])

        return {
            "success": True,
            "egg": egg,
            "loot": loot,
            "pet_result": pet_res,
            "coins": coins,
            "xp": xp,
            "new_balance": new_balance,
            "leveled_up": xp_res.get("leveled_up", False),
        }

    async def crack_egg_direct(self, user_id: int, guild_id: int, egg_id: str) -> dict[str, Any]:
        """Instantly crack an egg without waiting for incubation (reduced loot)."""
        egg = egg_catalog.get_egg(egg_id)
        if not egg:
            return {"success": False, "reason": "invalid_egg"}

        qty = await self.get_item_qty(user_id, guild_id, egg_id)
        if qty <= 0:
            return {"success": False, "reason": "not_owned"}

        await self.add_item(user_id, guild_id, egg_id, -1)

        loot = egg_catalog.generate_hatch_loot(egg_id, is_incubated=False)

        coins = loot.get("coins", 0)
        xp = loot.get("xp", 0)
        new_balance = await self.add_coins(user_id, guild_id, coins) if coins else 0
        xp_res = await self.grant_xp(user_id, guild_id, xp) if xp else {"leveled_up": False}

        pet_res = None
        if loot.get("type") == "pet" and loot.get("species_id"):
            pet_res = await self.grant_hatched_pet(user_id, guild_id, loot["species_id"])

        if loot.get("type") == "food" and loot.get("food_id"):
            await self.add_item(user_id, guild_id, loot["food_id"], loot.get("qty", 1))

        return {
            "success": True,
            "egg": egg,
            "loot": loot,
            "pet_result": pet_res,
            "coins": coins,
            "xp": xp,
            "new_balance": new_balance,
            "leveled_up": xp_res.get("leveled_up", False),
        }
