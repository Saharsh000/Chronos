# Chronos

> A production-ready Discord study bot built around focused sessions, progression, competition, and a full study-game economy.

It combines **study-session tracking, XP, levels, subject rooms, streaks, leaderboards, achievements, a coin economy, collectible pets, and a shared Pomodoro system** into one bot.

**Prefix commands only. No slash commands. Every bot response is an embed.**

---

## ✨ Features

### 📚 Study Tracking

* **`.start [subject]` / `.stop`** — explicit session control.
* Sessions never auto-start when joining a voice channel.
* **Restart-safe timing** using timestamps stored in SQLite.
* Live tracking of study time, XP, and coins.
* `.session` shows the current active session.
* `.active` shows everyone currently studying in the server.

### 🧪 Subject Rooms

Create dedicated Physics, Chemistry, and Maths voice rooms with:

```text
.make
```

Starting a session while connected to one of these rooms automatically tags the session with that subject.

Subject data feeds directly into:

* `.stats`
* `.subjects`
* `.leaderboard`

### 📊 Stats & Competition

`.stats` provides detailed personal analytics including:

* Today / this week / all-time study time
* Level and XP progress
* Server rank
* Study streak
* Coin balance
* Achievement progress
* Average and longest session
* Favourite subject
* Most active weekday
* Subject breakdown

Leaderboards support:

```text
.leaderboard [period] [subject]
```

Periods:

```text
today
week
month
alltime
```

Subjects:

```text
physics
chemistry
maths
```

Example:

```text
.leaderboard week physics
```

There is also a permanent:

```text
.halloffame
```

for server records across study time, levels, streaks, longest sessions, coins, achievements, and subjects.

### ⚔️ Head-to-Head

Compare two users with:

```text
.compare @user
.compare @user1 @user2
```

Chronos compares roughly 13 categories including study time, levels, streaks, sessions, coins, achievements, and subjects — then declares who **mogs** who.

### 🔥 Streaks

Studying on consecutive calendar days builds a study streak.

A **Streak Freeze** from the shop can automatically protect the streak when exactly one day is missed.

Chronos' study-day calculations are designed around **IST (UTC+5:30)**.

### 💰 Economy

Study to earn coins and spend them through:

```text
.shop
.buy
.inventory
.use
.openbox
.settitle
```

Available rewards include:

* Mystery Boxes
* Streak Freezes
* XP Boosts
* Coin Boosts
* Cosmetic profile titles
* Server-customized tags

Additional earning commands:

```text
.daily
.work
.weekly
```

`.daily` has its own separate claim streak with escalating rewards and milestone bonuses.

### 🐾 Pets

Chronos includes **44 collectible pets across 5 tiers**, each with its own evolution line and animated sprite.

Unlock pets from:

```text
.petshop
.buypet
```

Then manage them with:

```text
.pets
.pet
.equip
.nickname
```

Equipped pets gain XP passively while you study.

### 🍖 Pet Food

Pets can also be levelled through food.

Commands:

```text
.foodshop
.buyfood
.feed
.sellfood
```

There are **45 food items across 4 tiers**.

### 🏆 Achievements

Chronos includes **69 achievements** spanning:

* Study time
* Sessions
* Streaks
* Ranks / tiers
* Subjects
* Chapters
* Subtopics
* Books
* PYQs
* Revisions
* Economy
* Special milestones

Achievements are unlocked live and announced immediately.

### 📖 JEE Main Progress Tracking

Chronos contains a built-in condensed **JEE Main syllabus reference** covering:

* 20 Physics chapters
* 20 Chemistry chapters
* 14 Maths chapters

Browse it with:

```text
.syllabus
```

Progress can be logged with validated commands:

```text
.chapterdone
.subtopicdone
```

Book, PYQ, and revision progress can also be tracked:

```text
.bookdone
.pyq
.revision
.progress
```

Syllabus-backed commands validate chapters and subtopics against Chronos' built-in syllabus data.

### 💤 AFK Protection

Long study sessions can trigger an AFK check-in.

By default:

* Check-in every **25 minutes**
* User gets another **25 minutes** to respond
* No response ends the session automatically

Configure this with:

```text
.setcheckin #channel
```

### 🍅 Shared Pomodoro

Chronos includes a shared voice-channel Pomodoro system.

The default cycle is:

```text
25 min focus
5 min break
25 min focus
5 min break
25 min focus
5 min break
25 min focus
15 min long break
```

The first person joining a voice channel starts the cycle. Everyone joining afterward follows the same timer.

The Pomodoro system is independent from `.start` / `.stop` study sessions.

### 🎨 Runtime Customization

Server branding can be changed without redeploying the bot.

Developer commands include:

```text
.settier
.resettier
.addtag
.removetag
```

Users can view the current configuration with:

```text
.tiers
.tags
```

Global defaults remain available in:

```text
utils/xp.py
utils/economy.py
```

### 🛠️ Developer Overrides

The configured developer account can directly correct or modify:

```text
.addtime
.removetime
.addxp
.removexp
.addcoins
.removecoins
```

These commands are intended for administration and data correction rather than normal gameplay.

### 📝 Console Logging

Chronos logs important runtime events including:

* Session starts / ends
* XP and coin credits
* Level-ups
* Achievement unlocks
* Shop purchases
* Daily claims
* Progress milestones
* Tier and tag changes
* AFK prompts and timeouts
* Subject-room creation
* Developer adjustments
* Pomodoro phase changes

---

# ⏱️ How Timing Works

Timing is one of Chronos' core design constraints.

> **Chronos does not rely on an in-memory timer to keep study time accurate.**

Every active session stores its start timestamp in SQLite:

```python
elapsed = current_time - start_time
```

Elapsed time is recalculated whenever it is needed rather than being continuously incremented in memory.

### XP & Coin Credit

For each session, Chronos tracks how much time has already been credited.

When another full minute has elapsed, it calculates the difference and awards a new randomized XP/coin roll.

This means timing remains correct even when:

* The bot restarts
* The process crashes
* Discord temporarily disconnects
* The host machine sleeps
* Monitoring is temporarily interrupted

No drift. No double-counting. No lost minutes.

### Startup Recovery

When Chronos starts, active sessions are reconciled directly from the database.

Sessions remain active until they are explicitly stopped or terminated by AFK handling.

---

# 🏗️ Project Structure

```text
chronos/
├── bot.py
├── config.py
├── database.py
├── requirements.txt
├── .env.example
│
├── cogs/
│   ├── sessions.py
│   ├── pomodoro.py
│   ├── stats.py
│   ├── economy.py
│   ├── pets.py
│   ├── achievements.py
│   ├── social.py
│   ├── progress.py
│   ├── customization.py
│   ├── admin.py
│   ├── dev.py
│   └── help.py
│
└── utils/
    ├── embeds.py
    ├── xp.py
    ├── streaks.py
    ├── economy.py
    ├── pets.py
    ├── food.py
    ├── achievements.py
    ├── syllabus.py
    ├── subjects.py
    ├── checks.py
    ├── time_format.py
    └── logger.py
```

---

# 🚀 Setup

## 1. Create the Discord Application

Open the [Discord Developer Portal](https://discord.com/developers/applications) and:

1. Create a **New Application**
2. Open the **Bot** tab
3. Click **Add Bot**
4. Enable:

   * **Server Members Intent**
   * **Message Content Intent**
5. Copy the bot token

> Never commit your bot token or `.env` file to Git.

---

## 2. Invite Chronos

In:

**OAuth2 → URL Generator**

Select the:

```text
bot
```

scope.

Recommended permissions:

* View Channels
* Send Messages
* Embed Links
* Add Reactions
* Read Message History
* Manage Channels *(required for `.make`)*
* Manage Messages *(optional)*

Use the generated URL to invite Chronos to your server.

---

## 3. Install Dependencies

Create and activate a virtual environment:

```bash
python -m venv venv
```

### macOS / Linux

```bash
source venv/bin/activate
```

### Windows

```powershell
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create your `.env`:

```bash
cp .env.example .env
```

Then add your Discord bot token:

```env
DISCORD_TOKEN=your_token_here
```

Other settings are optional and can use their defaults.

---

## 5. Start Chronos

```bash
python bot.py
```

A successful startup should look similar to:

```text
2026-09-11 12:00:01 | INFO     | bot      | Loaded extension: cogs.sessions
2026-09-11 12:00:02 | INFO     | bot      | Logged in as Chronos#1234 (ID: ...)
2026-09-11 12:00:02 | INFO     | sessions | Reconciling 0 stored active session(s)...
2026-09-11 12:00:02 | INFO     | sessions | Startup reconciliation complete - session commands are now active.
```

---

# ⚙️ Server Configuration

## Check-in Channel

Set the channel used for AFK prompts and certain announcements:

```text
.setcheckin #general
```

If no channel is configured, Chronos falls back to the user's voice channel or DM where applicable.

## Study Rooms

Administrators can create the three subject rooms with:

```text
.make
```

This creates:

```text
📚 Study Rooms
├── Physics
├── Chemistry
└── Maths
```

Running `.make` again is safe and does not duplicate existing rooms.

---

# 📋 Commands

All commands use the configured prefix.

Default:

```text
.
```

## Study

| Command            | Description                   |
| ------------------ | ----------------------------- |
| `.start [subject]` | Start a study session         |
| `.stop`            | End the current session       |
| `.session`         | View the current session      |
| `.active`          | See who is currently studying |

## Stats

| Command                           | Description              |
| --------------------------------- | ------------------------ |
| `.stats [@user]`                  | Detailed statistics      |
| `.rank [@user]`                   | Level, tier, and XP      |
| `.subjects [@user]`               | Subject breakdown        |
| `.leaderboard [period] [subject]` | Leaderboard              |
| `.halloffame`                     | Permanent server records |
| `.compare @user [@user2]`         | Compare users            |

## Progress

| Command                                        | Description                  |
| ---------------------------------------------- | ---------------------------- |
| `.syllabus [subject] [chapter]`                | Browse the JEE Main syllabus |
| `.chapterdone <subject> <chapter>`             | Mark a chapter complete      |
| `.subtopicdone <subject> <chapter> <subtopic>` | Mark a subtopic complete     |
| `.bookdone <subject> <book>`                   | Log a completed book         |
| `.pyq <year> [subject]`                        | Log PYQ progress             |
| `.revision <number> [subject]`                 | Log a revision pass          |
| `.progress [@user]`                            | View logged progress         |

## Economy

| Command                   | Description                      |
| ------------------------- | -------------------------------- |
| `.daily`                  | Daily coin + XP reward           |
| `.work`                   | Cooldown-based coin + XP reward  |
| `.weekly`                 | Weekly coin reward + Mystery Box |
| `.balance [@user]`        | View coins                       |
| `.shop`                   | View the shop                    |
| `.buy <item> [quantity]`  | Buy shop items                   |
| `.inventory [@user]`      | View inventory                   |
| `.use <item>`             | Activate a boost                 |
| `.openbox`                | Open a Mystery Box               |
| `.settitle <title\|none>` | Set a profile title              |

## Pets

| Command                       | Description             |
| ----------------------------- | ----------------------- |
| `.petshop [tier]`             | Browse pets             |
| `.buypet <name>`              | Unlock a pet            |
| `.pets [@user]`               | View owned pets         |
| `.pet [name]`                 | View detailed pet stats |
| `.equip <name>`               | Equip a pet             |
| `.nickname <current> <new>`   | Rename a pet            |
| `.foodshop [tier]`            | Browse pet food         |
| `.buyfood <name> [quantity]`  | Buy food                |
| `.feed <name> [quantity]`     | Feed your pet           |
| `.sellfood <name> [quantity]` | Sell food               |

## Customization

| Command     | Description                     |
| ----------- | ------------------------------- |
| `.tiers`    | View active tier names          |
| `.tags`     | View purchasable profile tags   |
| `.pomodoro` | View the current Pomodoro cycle |
| `.help`     | Display available commands      |

## Administration

| Command                | Description                    |
| ---------------------- | ------------------------------ |
| `.make`                | Create subject study rooms     |
| `.setcheckin #channel` | Configure the check-in channel |
| `.config`              | View server configuration      |

## Developer

| Command                                  | Description            |
| ---------------------------------------- | ---------------------- |
| `.addtime @user <duration> [subject]`    | Grant study time       |
| `.removetime @user <duration> [subject]` | Remove study time      |
| `.addxp @user <amount>`                  | Grant XP               |
| `.removexp @user <amount>`               | Remove XP              |
| `.addcoins @user <amount>`               | Grant coins            |
| `.removecoins @user <amount>`            | Remove coins           |
| `.settier <level> <name>`                | Rename a tier          |
| `.resettier <level>`                     | Reset a tier           |
| `.resettiers`                            | Reset all tier renames |
| `.addtag <price> <name>`                 | Add a custom shop tag  |
| `.removetag <name>`                      | Remove a custom tag    |

Developer commands are restricted to the configured developer account.

---

# 🔧 Configuration

Chronos can be configured through `.env`.

| Variable                            |           Default | Description               |
| ----------------------------------- | ----------------: | ------------------------- |
| `DISCORD_TOKEN`                     |                 — | Discord bot token         |
| `COMMAND_PREFIX`                    |               `.` | Command prefix            |
| `DB_PATH`                           | `chronos.sqlite3` | SQLite database path      |
| `DEV_USER_ID`                       |  configured value | Developer account ID      |
| `XP_MIN_PER_MINUTE`                 |               `6` | Minimum XP per minute     |
| `XP_MAX_PER_MINUTE`                 |              `14` | Maximum XP per minute     |
| `COINS_MIN_PER_MINUTE`              |               `1` | Minimum coins per minute  |
| `COINS_MAX_PER_MINUTE`              |               `3` | Maximum coins per minute  |
| `PET_UNLOCK_LEVEL`                  |              `10` | Required level for pets   |
| `PET_XP_MIN_PER_MINUTE`             |               `1` | Minimum pet XP per minute |
| `PET_XP_MAX_PER_MINUTE`             |               `3` | Maximum pet XP per minute |
| `FOOD_SELL_RATE`                    |             `0.5` | Food resale multiplier    |
| `WORK_COOLDOWN_SECONDS`             |            `3600` | `.work` cooldown          |
| `WORK_COINS_MIN`                    |              `80` | Minimum `.work` coins     |
| `WORK_COINS_MAX`                    |             `180` | Maximum `.work` coins     |
| `WORK_XP_MIN`                       |              `10` | Minimum `.work` XP        |
| `WORK_XP_MAX`                       |              `25` | Maximum `.work` XP        |
| `WEEKLY_COOLDOWN_SECONDS`           |          `604800` | `.weekly` cooldown        |
| `WEEKLY_COINS_MIN`                  |             `900` | Minimum `.weekly` coins   |
| `WEEKLY_COINS_MAX`                  |            `1500` | Maximum `.weekly` coins   |
| `CHECKIN_INTERVAL_MINUTES`          |              `25` | AFK check-in interval     |
| `AFK_GRACE_MINUTES`                 |              `25` | AFK response window       |
| `POMODORO_FOCUS_MINUTES`            |              `25` | Focus duration            |
| `POMODORO_BREAK_MINUTES`            |               `5` | Short break               |
| `POMODORO_LONG_BREAK_MINUTES`       |              `15` | Long break                |
| `POMODORO_CYCLES_BEFORE_LONG_BREAK` |               `4` | Cycles before long break  |
| `SESSION_MONITOR_INTERVAL_SECONDS`  |              `30` | Session monitor interval  |
| `POMODORO_MONITOR_INTERVAL_SECONDS` |              `15` | Pomodoro monitor interval |

---

# 🗃️ Database & Persistence

Chronos uses **SQLite** with WAL mode for normal concurrent access.

The database contains persistent data for:

* Users
* Sessions
* XP / levels
* Study streaks
* Coins
* Inventory
* Boosts
* Daily claims
* Achievements
* Progress milestones
* Tier customizations
* Custom shop tags
* Pets
* Pet progression
* Pomodoro sessions

Existing installations are migrated automatically.

### Updating an Existing Installation

New releases may introduce new tables or columns.

Chronos runs an idempotent database migration on startup using:

```python
Database._migrate()
```

Existing data is preserved rather than rewritten.

---

# 🧠 Design Principles

Chronos is built around a few simple principles:

**Explicit control**
Users decide when their study session starts and ends.

**Persistent state**
Important state lives in SQLite rather than temporary memory.

**Live progression**
XP and coins are credited while studying instead of waiting until `.stop`.

**Recoverability**
Restarts and temporary outages should not destroy session timing.

**Modularity**
Features are separated into cogs and utility modules so the bot can grow without becoming one giant file.

**Prefix-first UX**
Chronos intentionally uses prefix commands and embeds rather than slash commands.

---

# 📌 Notes

* Study time is tracked exactly, including sub-minute time.
* XP and related progression rewards are granted in whole-minute chunks.
* A session lasting 8m33s records all 8m33s as study time, while XP crediting only uses completed minutes.
* The Pomodoro system is independent from study-session tracking.
* Pets are permanent species unlocks rather than stackable duplicates.
* Only the equipped pet gains passive study XP.
* Pet XP uses its own progression curve separate from user XP.
* The bot never joins voice channels itself.
* Voice state data is used for Pomodoro handling and subject-room detection.

---

# 🔐 Security

Never commit secrets such as:

```text
.env
DISCORD_TOKEN
```

to the repository.

Use `.env.example` as the template and keep real credentials outside version control.

---

# 📄 License

MIT — see [`LICENSE`](LICENSE).
