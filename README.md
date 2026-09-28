# Chronos

A production-quality Discord bot inspired by [LionBot](https://www.lionbot.org/)'s
core study/activity-tracking features: command-driven study sessions,
randomized XP and levels, Physics/Chemistry/Maths subject rooms,
leaderboards across multiple time periods, an AFK check-in system, and
a shared Pomodoro timer. **Prefix commands only - no slash commands.**
Every response is an embed.

## Features

- **`.start` / `.stop`** - explicit, predictable session control. No
  auto-start on voice join; the user decides exactly when their time
  starts and stops counting.
- **Restart-safe timing** - elapsed time is *always* computed as
  `current_time - start_time`, read from SQLite. See
  [How the timing works](#how-the-timing-works) below.
- **Randomized XP + coins, credited live** - each full minute of an
  active session rolls random XP (default 6-14) and coins (default
  1-3), rolling both into your stats *while you're still studying*,
  not just when you `.stop`.
- **Ranked tiers** - \u2699\uFE0F Iron \u2192 \U0001F949 Bronze \u2192 \U0001F948 Silver \u2192 \U0001F947 Gold \u2192
  \U0001F539 Platinum \u2192 \U0001F48E Diamond \u2192 \U0001F343 Ascendant \u2192 \U0001F480 Immortal \u2192
  \u2600\uFE0F Radiant \u2192 \U0001F680 AIR 1.
- **Physics / Chemistry / Maths subject rooms** - an admin runs
  `.make` once to create three voice channels. Start a session while
  connected to one and it's automatically tagged, rolling into
  per-subject stats and subject-filterable leaderboards.
- **All day/time boundaries are IST** - streaks, `.daily`'s reset,
  weekday stats, and Early Bird/Night Owl achievements are all
  anchored to India Standard Time (UTC+5:30), not UTC or the server's
  local time.
- **`.active`** - see everyone currently in a live study session in
  the server right now, with elapsed time, subject, and channel.
- **In-depth personal stats** (`.stats`) - today / this week /
  all-time totals, level, XP progress bar, server rank, study streak,
  coin balance, achievement progress, average/longest session,
  favorite subject, most active day of the week, and a subject
  breakdown if the server has rooms set up.
- **Leaderboards** (`.leaderboard [period] [subject]`) - any
  combination of `today`/`week`/`month`/`alltime` and
  `physics`/`chemistry`/`maths`, including live in-progress sessions.
- **Hall of Fame** (`.halloffame`) - permanent, per-server record
  holders across total time, level, streaks, longest single session,
  lifetime coins, achievements, and each subject.
- **Head-to-head comparisons** (`.compare @user [@user2]`) - stacks
  two users up across ~13 categories (time, level, streaks, sessions,
  coins, achievements, subjects) and declares who "mogs" who.
- **Daily study streaks** - studying on consecutive IST calendar days
  builds a streak (shown on `.stats`); a **Streak Freeze** item from
  the shop automatically protects it the next time you miss exactly
  one day.
- **Coin shop & economy** (`.shop` / `.buy` / `.inventory` / `.use` /
  `.openbox` / `.settitle`) - spend coins earned from studying on
  Mystery Boxes, Streak Freezes, temporary XP/Coin boosts, and
  unlockable cosmetic profile titles (built-in or server-added, see
  Customization below).
- **Pets & pet food** (`.petshop` / `.buypet` / `.pets` / `.pet` /
  `.equip` / `.nickname`, `.foodshop` / `.buyfood` / `.feed` /
  `.sellfood`) - 44 collectible pets across 5 tiers (Common through
  Legendary), each with a multi-stage evolution line and its own
  animated sprite. Unlock a pet at Level 10+ with the same shared
  coins, `.equip` one to make it your active pet, and level it up
  either by studying (equipped pets earn a little XP passively per
  minute, same live-crediting path as user XP/coins) or by `.feed`ing
  it food bought from `.foodshop` (45 items across 4 tiers).
- **Extra coin-earning commands** (`.work` / `.weekly`) - on top of
  studying and `.daily`, `.work` is a short-cooldown coin+XP grant
  meant to be claimed often, and `.weekly` is a large once-a-week
  lump sum plus a free Mystery Box - added since pets and food add
  real coin sinks to spend on.
- **`.daily`** - a once-per-IST-day coin *and* XP claim, plus a
  separate claim streak (distinct from the study streak). Consecutive
  claims raise the coin bonus, every 5th day grants a free Mystery
  Box, and big streak milestones (7/14/30/60/100 days) throw in a
  one-time bonus of extra coins plus a bonus item.
- **JEE Main syllabus reference** (`.syllabus`) - a condensed,
  built-in copy of the current JEE Main syllabus (Physics: 20
  chapters, Chemistry: 20, Maths: 14, each with key subtopics) to
  browse subject \u2192 chapter \u2192 subtopic.
- **Syllabus-validated progress logging** - `.chapterdone` and
  `.subtopicdone` only accept real chapters/subtopics from the JEE
  syllabus (see `.syllabus`); `.bookdone`, `.pyq <year>`, and
  `.revision <number>` log free-text book/PYQ-year/revision-pass
  completions. Each logged item earns a flat coin+XP reward and feeds
  its own achievement categories. `.progress` shows a summary.
- **Achievements** (`.achievements`) - 69 badges across time studied,
  sessions, streaks, tiers, subjects, chapters, subtopics, books,
  PYQs, revisions, the economy, and fun one-offs (Early Bird, Night
  Owl, Perfect Week), unlocked live and announced the moment they're
  earned.
- **AFK check-in** - every 25 minutes (configurable) of inactivity,
  the bot asks the user to react to confirm they're still around; no
  response within another 25 minutes ends the session automatically.
- **Shared Pomodoro** - the first person to join any voice channel
  starts a 25/5 focus/break cycle *for that channel*; everyone who
  joins afterward just follows the cycle already running, with a long
  break every 4 cycles. Fully independent of the `.start`/`.stop`
  session system.
- **Dev-configurable branding, no redeploy needed** (`.settier`,
  `.resettier(s)`, `.addtag`, `.removetag`) - the hardcoded dev id can
  rename tiers and add custom purchasable profile tags per server at
  runtime; `.tiers`/`.tags` let anyone see what's currently active.
  `utils/xp.py`'s `TIERS` and `utils/economy.py`'s `SHOP_ITEMS`
  remain the global defaults/fallback - editing those files directly
  still works too, for a change that should apply everywhere.
- **Dev override commands** (`.addtime`/`.removetime`,
  `.addxp`/`.removexp`, `.addcoins`/`.removecoins`) - a single
  hardcoded Discord user id (not a guild permission) can directly
  grant *or correct* a user's study time, raw XP, or raw coins in any
  server the bot is in. Removals floor at 0 and never go negative;
  `.removetime` removes proportional XP/coins at the average
  configured rate rather than a random roll, since it's meant for
  fixing a mistake, not gameplay.
- **Console logging** - every session start/end, XP/coin credit tick,
  level-up, achievement unlock, shop purchase, daily claim, milestone
  log, tier/tag change, AFK prompt/timeout, room creation, dev grant,
  and Pomodoro phase change is logged with timestamps.

## Updating from an earlier version

This release adds new tables (coins, inventory, boosts, daily
claims, achievements, manually-logged milestones, per-server tier
renames, per-server custom shop tags, owned pets, and generic
per-command cooldowns for `.work`/`.weekly`) and a few new columns on
the existing `user_stats` / `sessions` tables (streaks, equipped
title, credited coins). **Nothing is dropped or rewritten** -
`database.py` runs a one-time, idempotent migration on startup
(`Database._migrate()`) that adds any missing columns with safe
defaults via `ALTER TABLE`, so pointing this version at your existing
`chronos.sqlite3` just works; everyone keeps their existing time, XP,
levels, and pets.

Note also that **day boundaries moved from UTC to IST** (streaks,
`.daily`, weekday stats) - if your server's activity happens well
outside Indian daytime hours this shifts exactly when "today" rolls
over, though it won't retroactively change anything already recorded.

## How the timing works

This was the central design constraint, so it's worth being explicit
about it:

> **The bot never relies on an in-memory timer or a loop that has to
> keep running in order to "count" correctly.**

Every session, in `sessions.start_time`, and every Pomodoro phase, in
`pomodoro_sessions.phase_start`, stores a **unix-epoch integer
timestamp** the instant it's known. From then on, elapsed time is
always:

```python
elapsed = current_time - start_time
```

recomputed fresh, every single time it's displayed or checked - never
incremented by a background loop. Concretely:

- **`.session` / `.stats` / `.leaderboard`** compute elapsed time on
  the fly from `start_time` (and, for in-progress sessions in a
  period leaderboard, from `now - max(start_time, period_start)`), at
  the moment the command runs.
- **Randomized XP crediting** (`database.py::credit_progress`) works
  the same way: it compares `now - start_time` against how many
  seconds have *already* been credited (`sessions.credited_seconds`)
  and, if a new whole minute has elapsed, rolls a fresh random XP
  amount and that time into `user_stats` immediately. If this never
  ran again for an hour and then resumed, it would just see a bigger
  gap and credit all of it at once - no drift, no double-counting,
  no lost minutes.
- **The AFK monitor** (`cogs/sessions.py`, `session_monitor` - a
  `discord.ext.tasks.loop`) wakes up every
  `SESSION_MONITOR_INTERVAL_SECONDS` and does nothing but compare
  `now - last_checkin` and `now - prompt_sent_at` against configured
  thresholds, read straight from the database.
- **The Pomodoro monitor** (`cogs/pomodoro.py`) works the same way,
  polling `now - phase_start >= phase_duration` and stepping the
  stored `phase_start` forward in fixed increments to catch up
  correctly even after a long gap.
- **On startup**, `Sessions._reconcile_sessions()` runs once, right
  after login, and simply reports every session still marked `active`
  in the database (elapsed time computed the usual way). Because
  sessions are now only ever started/stopped by `.start`, `.stop`, or
  an AFK timeout - **never** by voice presence - there's nothing to
  cross-reference against live voice state anymore; a session just
  keeps running exactly as if the bot had never gone down.

This means the timing survives, correctly, through: a bot restart, a
process crash, a temporary Discord gateway disconnect, or the host
machine sleeping.

## Project layout

```
chronos/
├── bot.py                  # entry point
├── config.py                # env-driven settings + fixed IST timezone
├── database.py               # SQLite schema + all persistence logic
├── requirements.txt
├── .env.example
├── cogs/
│   ├── sessions.py          # .start [subject] / .stop / .active, AFK check-in, live XP/coin crediting
│   ├── pomodoro.py          # shared per-channel Pomodoro cycle
│   ├── stats.py               # .stats, .rank, .subjects, .leaderboard, .session
│   ├── economy.py              # .shop, .buy, .inventory, .use, .openbox, .settitle, .balance, .daily, .work, .weekly
│   ├── pets.py                    # .petshop, .buypet, .pets, .pet, .equip, .nickname, .foodshop, .buyfood, .feed, .sellfood
│   ├── achievements.py          # .achievements
│   ├── social.py                 # .halloffame, .compare
│   ├── progress.py                # .syllabus, .chapterdone, .subtopicdone, .bookdone, .pyq, .revision, .progress
│   ├── customization.py            # .settier(s), .addtag/.removetag, .tiers, .tags (dev-only to modify)
│   ├── admin.py                      # .make (subject rooms), .setcheckin, .config
│   ├── dev.py                          # .add/.removetime/xp/coins (hardcoded dev id only)
│   └── help.py                           # .help
└── utils/
    ├── embeds.py            # shared embed styling + achievement-unlock embed
    ├── xp.py                 # XP/level curve + tier names (+ per-guild override support)
    ├── streaks.py             # daily study-streak math (IST-based)
    ├── economy.py               # shop catalog, mystery box rolls, daily reward formula, milestone rewards
    ├── pets.py                     # pet species catalog, evolution chains, tier pricing, pet XP/level curve
    ├── food.py                       # pet food catalog (4 tiers, XP amounts, prices)
    ├── achievements.py            # achievement/badge definitions + evaluation (69 badges)
    ├── syllabus.py                  # condensed JEE Main syllabus reference (Physics/Chemistry/Maths)
    ├── subjects.py                    # Physics/Chemistry/Maths room config + aliases
    ├── checks.py                       # is_dev() command check
    ├── time_format.py                    # duration formatting/parsing, Discord timestamps
    └── logger.py                           # console logging setup
```

## Setup

### 1. Create the Discord application & bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
   → **New Application**.
2. Go to the **Bot** tab → **Add Bot**.
3. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Message Content Intent**
   (Voice State intent is *not* privileged and doesn't need toggling here.)
4. Click **Reset Token** / **Copy** to get your bot token.

### 2. Invite the bot to your server

In the **OAuth2 → URL Generator** tab, select scope `bot`, and these
permissions:

- View Channels
- Send Messages
- Embed Links
- Add Reactions
- Read Message History
- Manage Channels *(only needed if you want to use `.make`)*
- Manage Messages *(optional, lets it clear check-in reactions cleanly)*

Open the generated URL and add it to your server.

### 3. Install & run

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your DISCORD_TOKEN
# (DEV_USER_ID already defaults to 798537896201420811 - change it if that's not you)

python bot.py
```

You should see console output like:

```
2026-09-11 12:00:01 | INFO     | bot              | Loaded extension: cogs.sessions
2026-09-11 12:00:02 | INFO     | bot              | Logged in as Chronos#1234 (ID: ...)
2026-09-11 12:00:02 | INFO     | sessions         | Reconciling 0 stored active session(s)...
2026-09-11 12:00:02 | INFO     | sessions         | Startup reconciliation complete - session commands are now active.
```

### 4. Configure the check-in channel (recommended)

```
.setcheckin #general
```

This is where AFK prompts, mid-session level-ups, and Pomodoro phase
announcements get posted. If it's never set, AFK prompts fall back to
the user's own voice channel (if any) or a DM, and level-up/Pomodoro
announcements are simply skipped (still logged to console either way).

### 5. Set up the subject rooms (optional)

```
.make
```

*(requires Administrator)* Creates a **📚 Study Rooms** category with
three voice channels - Physics, Chemistry, and Maths. Anyone connected
to one of these when they run `.start` gets that session tagged, and
it rolls into `.subjects` and subject-filtered leaderboards. Safe to
run again later - it won't duplicate channels that already exist.

## Commands

All commands use the prefix from `COMMAND_PREFIX` (default `.`).

| Command | Description |
|---|---|
| `.start [subject]` | Start a session, optionally tagged (`.start physics`/`phy`/`p`, `chem`/`c`, `math`/`m`) |
| `.stop` | End your current session (alias: `.end`) |
| `.session` | View your current live session |
| `.active` | See everyone currently studying in this server right now (aliases: `.whosactive`, `.online`) |
| `.stats [@user]` | In-depth study statistics: time, level, streak, coins, achievements, and behavioral analytics |
| `.rank [@user]` | View level, tier, and XP progress |
| `.subjects [@user]` | Physics/Chemistry/Maths time breakdown |
| `.leaderboard [period] [subject]` | Server leaderboard, e.g. `.leaderboard week physics` (aliases: `.lb`, `.top`) |
| `.halloffame` | This server's permanent all-time records (alias: `.hof`) |
| `.compare @user [@user2]` | Head-to-head stat comparison across ~13 categories (alias: `.vs`) |
| `.achievements [@user \| category]` | Browse unlocked/locked achievement badges (aliases: `.badges`, `.ach`) |
| `.syllabus [subject] [chapter]` | Browse the JEE Main syllabus (alias: `.syl`) |
| `.chapterdone <subject> <chapter>` | Log a completed chapter - must match the syllabus (alias: `.chapter`) |
| `.subtopicdone <subject> <chapter> <subtopic>` | Log a completed subtopic (aliases: `.subtopic`, `.sub`) |
| `.bookdone <subject> <book>` | Log a completed book (alias: `.book`) |
| `.pyq <year> [subject]` | Log a completed year of previous-year questions |
| `.revision <number> [subject]` | Log a completed revision pass (alias: `.rev`) |
| `.progress [@user]` | Summary of everything logged: chapters, subtopics, books, PYQs, revisions |
| `.daily` | Claim your once-a-day coin + XP reward; streak bonuses and milestone jackpots stack |
| `.work` | Quick task for coins + a little XP; short cooldown, use often (alias: `.grind`) |
| `.weekly` | Claim a large once-a-week coin reward, plus a free Mystery Box |
| `.balance [@user]` | Check coin balance (aliases: `.bal`, `.coins`) |
| `.shop` | Browse purchasable shop items (alias: `.store`) |
| `.buy <item> [quantity]` | Purchase an item, by name or shop number, optionally several at once |
| `.inventory [@user]` | See what you own, including pet food (alias: `.inv`) |
| `.use <item>` | Activate a boost item (XP Boost / Coin Boost) |
| `.openbox` | Open a Mystery Box (alias: `.open`) |
| `.settitle <title\|none>` | Equip (or clear) an owned cosmetic profile title |
| `.petshop [tier]` | Browse buyable pets, optionally filtered by tier (alias: `.pshop`) |
| `.buypet <name>` | Unlock a pet species permanently (requires Level 10+) |
| `.pets [@user]` | See owned pets, with level and equipped status |
| `.pet [name]` | Detailed stats for one pet - species, stage, level, XP bar (defaults to your equipped pet) |
| `.equip <name>` | Set your active pet - only it earns XP while studying and gets fed |
| `.nickname <current> <new>` | Rename an owned pet (aliases: `.nick`, `.renamepet`) |
| `.foodshop [tier]` | Browse pet food, optionally filtered by tier (alias: `.fshop`) |
| `.buyfood <name> [quantity]` | Buy pet food |
| `.feed <name> [quantity]` | Feed owned food to your equipped pet for XP |
| `.sellfood <name> [quantity]` | Sell owned food back for half its price |
| `.tiers` | See this server's current tier names (defaults + any dev renames) |
| `.tags` | See purchasable profile titles/tags (built-in + custom) |
| `.pomodoro` | Check the Pomodoro cycle running in your voice channel (alias: `.pomo`) |
| `.make` | *(Administrator)* Create the Physics/Chemistry/Maths study rooms |
| `.setcheckin #channel` | *(Manage Server)* Set the AFK/announcements channel |
| `.config` | *(Manage Server)* Show current server configuration |
| `.addtime @user <duration> [subject]` | *(Dev only)* Grant study time + proportional XP/coins |
| `.removetime @user <duration> [subject]` | *(Dev only)* Remove study time + proportional XP/coins (floors at 0) |
| `.addxp @user <amount>` | *(Dev only)* Grant (or remove, with a negative number) raw XP |
| `.removexp @user <amount>` | *(Dev only)* Remove raw XP (floors at 0) |
| `.addcoins @user <amount>` | *(Dev only)* Grant (or remove, with a negative number) raw coins (alias: `.addcoin`) |
| `.removecoins @user <amount>` | *(Dev only)* Remove raw coins (floors at 0) |
| `.settier <level> <name>` | *(Dev only)* Rename a tier for this server |
| `.resettier <level>` / `.resettiers` | *(Dev only)* Reset one/all tier renames back to default |
| `.addtag <price> <name>` | *(Dev only)* Add a custom purchasable profile tag/title to this server's shop |
| `.removetag <name>` | *(Dev only)* Remove a custom tag |
| `.help` | List all commands |

## Configuration reference (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DISCORD_TOKEN` | — | Your bot token (required) |
| `COMMAND_PREFIX` | `.` | Prefix for all commands |
| `DB_PATH` | `chronos.sqlite3` | SQLite file path |
| `DEV_USER_ID` | `798537896201420811` | Hardcoded user id allowed to use the dev-only commands (`.add`/`.remove` time/xp/coins, `.settier`, `.addtag`) anywhere |
| `XP_MIN_PER_MINUTE` / `XP_MAX_PER_MINUTE` | `6` / `14` | Random XP range rolled per completed minute of activity |
| `COINS_MIN_PER_MINUTE` / `COINS_MAX_PER_MINUTE` | `1` / `3` | Random coin range rolled per completed minute of activity |
| `PET_UNLOCK_LEVEL` | `10` | Study level required before `.buypet` works |
| `PET_XP_MIN_PER_MINUTE` / `PET_XP_MAX_PER_MINUTE` | `1` / `3` | Random pet-XP range rolled per completed minute of activity, credited to your equipped pet |
| `FOOD_SELL_RATE` | `0.5` | Fraction of a food's shop price refunded by `.sellfood` |
| `WORK_COOLDOWN_SECONDS` | `3600` | Cooldown between `.work` claims |
| `WORK_COINS_MIN` / `WORK_COINS_MAX` | `80` / `180` | Random coin range for `.work` |
| `WORK_XP_MIN` / `WORK_XP_MAX` | `10` / `25` | Random XP range for `.work` |
| `WEEKLY_COOLDOWN_SECONDS` | `604800` | Cooldown between `.weekly` claims (7 days) |
| `WEEKLY_COINS_MIN` / `WEEKLY_COINS_MAX` | `900` / `1500` | Random coin range for `.weekly` |
| `CHECKIN_INTERVAL_MINUTES` | `25` | How often an AFK check-in is requested |
| `AFK_GRACE_MINUTES` | `25` | Time allowed to respond before the session ends |
| `POMODORO_FOCUS_MINUTES` | `25` | Focus phase length |
| `POMODORO_BREAK_MINUTES` | `5` | Short break length |
| `POMODORO_LONG_BREAK_MINUTES` | `15` | Long break length |
| `POMODORO_CYCLES_BEFORE_LONG_BREAK` | `4` | Focus cycles between long breaks |
| `SESSION_MONITOR_INTERVAL_SECONDS` | `30` | How often the AFK/XP-crediting monitor polls the database |
| `POMODORO_MONITOR_INTERVAL_SECONDS` | `15` | How often the Pomodoro monitor polls the database |

## Notes & design choices

- **Why did I get 0 XP right after starting?** XP is credited in
  whole-minute chunks, and the monitor only ticks every
  `SESSION_MONITOR_INTERVAL_SECONDS` (30s by default). So the first
  credit lands roughly 60-90 seconds into a session, not instantly -
  after that it keeps growing every minute or so while you study,
  well before you `.stop`.
- **Sub-minute remainders don't earn XP.** If you study for 8m33s,
  the trailing 33 seconds still count toward your total *time*
  (`.stats` "All Time" reflects it exactly), just not toward XP -
  only full completed minutes roll a random XP amount.
- **Daily/weekly/monthly boundaries use UTC.** Adjust in
  `cogs/stats.py::_period_start` if you need a fixed local timezone.
- **The dev override is a hardcoded user id, not a Discord
  permission** - `.addtime`/`.addxp`/`.addcoins` check
  `ctx.author.id` against `config.DEV_USER_ID` directly, so that one
  account can adjust stats in *any* server the bot is in, admin role
  or not.
- **Streaks are day-based, not session-based.** Any credited study
  time on a new UTC calendar day extends the streak by one; a gap of
  more than one day resets it, unless a Streak Freeze (from `.shop`)
  is available to auto-bridge exactly one missed day.
- **`.daily`'s streak is separate from the study streak.** One
  rewards showing up and claiming once a day; the other rewards
  actually studying. They're tracked independently on purpose.
- **A pet species is a one-time unlock, not a stack.** `.buypet` can
  only be bought once per species per user (like a shop title) -
  `.pets` shows your whole collection, but only whichever one you
  `.equip` earns passive XP while studying or gets fed by `.feed`.
  Buying your first pet auto-equips it.
- **Pet XP is its own curve, separate from user XP/levels.** Leveling
  a pet from `level` to `level + 1` costs `30 + 10 * (level - 1)` XP
  (see `utils/pets.py::xp_required_for_level`) - unrelated to the
  quadratic curve `utils/xp.py` uses for a user's own study level.
- **The database uses WAL mode** for better concurrent read/write
  behavior under normal bot load.
- This bot **never joins a voice channel itself** - all tracking is
  done via the `voice_states` gateway intent (for Pomodoro and
  subject-room detection only), and all output is text embeds,
  matching the "prefix commands, no slash, everything embeds"
  requirement.

## License

MIT — see `LICENSE`.
