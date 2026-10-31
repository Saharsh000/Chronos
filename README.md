<div align="center">

# ⏳ CHRONOS

**A high-performance, gamified Discord study companion built for competitive students.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py 2.4+](https://img.shields.io/badge/discord.py-2.4%2B-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![Database SQLite3](https://img.shields.io/badge/Database-SQLite%20(aiosqlite)-003B57?logo=sqlite&logoColor=white)](https://sqlite.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status Production](https://img.shields.io/badge/Status-Production%20Ready-success)](#)

*Restart-safe study tracking · Real-time analytics · Dynamic Pomodoro · JEE syllabus roadmaps · Collectible evolving pets · Drop-box economy · Seasonal events*

[Quickstart](#-quickstart) • [Features](#-features) • [Command Reference](#-command-reference) • [Configuration](#-configuration) • [Architecture](#-architecture)

---

</div>

## ⚡ Overview

**Chronos** transforms study channels into a productive, gamified community. Unlike standard timer bots that rely on fragile in-memory clocks, Chronos uses an asynchronous, transaction-safe SQLite database with live per-minute XP/coin crediting, daily streak preservation, custom audio study-rooms, and rich interactive Discord embeds.

---

## ✨ Features

### ⏱️ Rock-Solid Study Tracking
* **Explicit Control**: Start and stop sessions on your terms (`.start [subject]` / `.stop`) with zero phantom sessions.
* **Crash-Resilient**: Tracks start timestamps directly in SQLite — bot reboots or disconnects never wipe active study time.
* **Auto Subject Detection**: Join a dedicated Physics, Chemistry, or Maths VC created via `.make`, and Chronos automatically tags your session.
* **Shared VC Pomodoro**: Run synchronized work/break intervals directly in your voice channel (`.pomodoro`).

### 📊 Deep Analytics & Social Competition
* **Rich Profiles**: Comprehensive `.stats` cards with time breakdowns, streak shields, and equipped titles.
* **Multi-Period Leaderboards**: Daily, weekly, monthly, and all-time leaderboards (`.lb`) with sub-tier rankings.
* **Head-to-Head**: Compare historical study output with server peers via `.compare @user`.
* **Hall of Fame**: All-time record boards honoring server marathoners and top streaks (`.hof`).

### 🎯 Syllabus & Roadmap Tracker
* Built-in completion tracker tailored for competitive exam prep (JEE Main & Advanced).
* Log theory completion, NCERT checklists, revision cycles, and PYQ milestones with `.syllabus` and `.progress`.

### 🐾 Collectible Pets & Companions
* Adopt Pokemon study companions (`.petshop`) that earn independent pet XP while you study.
* Watch them evolve through base, mid, and final evolutionary stages as your hours accumulate.
* Feed them treats (`.foodshop`, `.feed`) to boost growth and companionship.

### 🪙 Economy, Loot & Seasonal Passes
* **Coin Economy**: Earn currency per study minute, daily streaks (`.daily`), work tasks, and weekly bonuses.
* **Interactive Shop**: Buy XP boosts, streak freezes, mystery boxes, and server-exclusive titles (`.shop`).
* **Halloween Seasonal Event**:
  * **Jack-o'-Lantern Pass** (`.pumpkin`): 1-per-account seasonal study pass with 5 carving stages and milestone loot.
  * **Hallo-Boxes** (`.boxes` / `.openbox`): 100% drop-only loot boxes opened instantly without incubation.
  * **Candy Currency & Shop** (`.candyshop`): Spend study-earned 🍬 Candy on exclusive pets (*Pumpkaboo*), JEE titles, and Sugar Rush boosts.

---

## 🕹️ Command Reference

> **Default Prefix:** `.` (Every response renders as a polished Discord embed)

### ⏱️ Study Sessions & Pomodoro
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `.start [subject]` | — | Begin a tracked study session (e.g. `.start Physics`) |
| `.stop` | `.end` | End session, log stats, and claim XP/coins earned |
| `.session` | `.current` | View your active live study session timer |
| `.active` | `.online` | List everyone currently studying in the server |
| `.pomodoro` | `.pomo` | Check or join the synchronized VC Pomodoro cycle |

### 📈 Stats & Leaderboards
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `.stats [@user]` | `.me`, `.profile` | Open your comprehensive study passport & analytics |
| `.leaderboard` | `.lb`, `.top` | Display server leaderboards (day/week/month/all-time) |
| `.rank` | `.lvl` | Check your tier rank, level, and next milestone |
| `.subjects` | — | View total time distribution across subjects |
| `.compare @user` | `.vs` | Side-by-side study comparison with a peer |
| `.halloffame` | `.hof` | Server record holders (longest sessions, highest streaks) |
| `.achievements` | `.badges` | Inspect unlocked and locked accomplishment badges |

### 📚 Syllabus & Exam Roadmaps
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `.syllabus [subject]`| `.syl` | Open interactive syllabus explorer & completion % |
| `.progress` | — | Summary of completed chapters, revisions & backlogs |
| `.chapterdone <name>`| `.chapter` | Mark an entire syllabus chapter completed |
| `.subtopicdone <id>` | `.sub` | Check off an individual subtopic |
| `.revision <chapter>`| `.rev` | Log a spaced-repetition revision session |
| `.pyq <chapter>` | — | Record past-year question paper practice |

### 🪙 Economy & Items
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `.balance` | `.bal`, `.coins` | Check your wallet (Coins & Seasonal Candy) |
| `.daily` | — | Claim once-per-day streak rewards & bonus loot |
| `.shop` | `.store` | Browse boosts, streak freezes, and profile titles |
| `.buy <item> [qty]` | — | Purchase items using earned coins |
| `.inventory` | `.inv` | View your owned consumables, boosts, and titles |
| `.use <item>` | — | Activate consumable items (e.g. XP Boost, Sugar Rush) |
| `.settitle <title>` | — | Equip an owned title to your profile card |
| `.work` / `.beg` | `.grind` | Quick mini-tasks for extra coins and random drops |
| `.weekly` | — | Weekly jackpot payout and rare box drops |

### 🐾 Pets & Companions
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `.petshop [tier]` | `.pshop` | Browse buyable pets across 5 rarity tiers |
| `.buypet <name>` | — | Adopt and unlock a permanent study companion |
| `.pets` | — | View all companions in your personal menagerie |
| `.pet [name]` | — | Inspect detailed stats, XP curve, and evolution progress |
| `.equip <name>` | — | Select active pet to accompany your study sessions |
| `.nickname <new>` | `.nick` | Rename your equipped pet |
| `.foodshop` | `.fshop` | Browse nutritional pet treats & meals |
| `.feed <food> [qty]`| — | Feed your equipped companion to award instant pet XP |

### 🎃 Seasonal Event (Halloween)
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `.pumpkin` | `.pass` | Personal Jack-o'-Lantern pass & study carving progress |
| `.pumpkin claim` | — | Claim unlocked stage milestone rewards |
| `.boxes` | `.halloboxes`| Inspect your inventory of drop-only Hallo-Boxes |
| `.openbox [tier] [n]`| `.open` | Instantly open Hallo-Boxes (Common → Legendary) |
| `.candyshop` | `.spookyshop`| Limited seasonal shop: Pumpkaboo pet, titles & boosts |
| `.buycandy <item>` | — | Spend 🍬 Candy on event-exclusive rewards |

### ⚙️ Server Admin & Customization
| Command | Description |
| :--- | :--- |
| `.make` | Automatically create Physics, Chemistry, and Maths study VCs |
| `.setcheckin #channel` | Designate the server announcement and drop channel |
| `.tiers` / `.settier` | View and customize server role and level tier names |
| `.tags` / `.addtag` | Create and manage custom server shop titles |
| `.config` | Display active server settings and channel bindings |

---

## 🚀 Quickstart

### Prerequisites
* **Python 3.11** or newer
* Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))
* Enable **Message Content Intent** and **Server Members Intent** under bot settings.

### 1. Clone & Install
```bash
git clone https://github.com/Saharsh000/Chronos.git
cd Chronos
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file in the project root:
```env
DISCORD_TOKEN=your_bot_token_here
PREFIX=.
DEV_USER_ID=your_discord_id_here
```

### 3. Run Chronos
```bash
python3 main.py
```

Chronos automatically initialises the SQLite database, verifies migrations, seeds default catalogs, and connects to Discord.

---

## 🏗️ Architecture

```
Chronos/
├── bot.py             # Bot initialization & extension loader
├── config.py          # Centralized configuration & environment loader
├── database.py        # Async SQLite layer (aiosqlite) with WAL mode & auto-migrations
├── main.py            # Entry point
├── cogs/              # Modular feature extensions (discord.ext.commands.Cog)
│   ├── sessions.py    # Live session monitor loop & VC checkins
│   ├── stats.py       # User profile cards, leaderboards & metrics
│   ├── economy.py     # Coin wallet, shop, inventory, daily/work/weekly
│   ├── pets.py        # Companions, evolution engine & feeding
│   ├── halloween.py   # Jack-o'-Lantern season pass & Hallo-Boxes
│   ├── progress.py    # Syllabus tracker & chapter logs
│   ├── pomodoro.py    # Synchronized voice-channel pomodoro state
│   ├── achievements.py# Achievement evaluation & badge grants
│   ├── customization.py# Guild-specific role tiers & custom title tags
│   ├── admin.py       # VC study-room provisioning & guild config
│   └── dev.py         # Diagnostic utilities & data backup commands
└── utils/             # Pure catalogs & data models (Zero DB dependency)
    ├── pets.py        # 40+ species definitions & evolution paths
    ├── food.py        # Treat catalog & XP yield values
    ├── halloween.py   # Hallo-Box loot tables & Season Pass curves
    ├── economy.py     # Base shop inventory & mystery box probabilities
    ├── embeds.py      # Standardized UI theme & embed builders
    └── streaks.py     # Timezone-aware streak validation logic
```

* **Zero-Lock Database**: Uses SQLite Write-Ahead Logging (`WAL`) with pooled async transactions.
* **Separation of Concerns**: Catalogs and loot equations (`utils/`) are strictly isolated from database I/O (`database.py`) and presentation (`cogs/`).
* **Python 3.11+ Optimized**: Strict type annotations, async-safe task scheduling, and defensive migration fallbacks.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.
