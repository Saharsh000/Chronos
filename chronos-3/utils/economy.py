"""Coin shop catalog, mystery box rolls, and `.daily` reward math.

Kept pure/content-only (like `utils/xp.py`'s TIERS list) - no database
access here. `database.py` and `cogs/economy.py` do the I/O and call
into these helpers for the numbers.
"""
from __future__ import annotations

import random
from typing import Any, Optional

# --------------------------------------------------------------------- #
# Shop catalog
# --------------------------------------------------------------------- #
# type:
#   "consumable" - stacks in inventory, consumed by use (mystery_box) or
#                   automatically by the streak system (streak_freeze)
#   "boost"      - stacks in inventory as charges; `.use` activates one
#                   charge as a timed multiplier on studying
#   "title"      - one-time unlock; `.settitle` equips the unlocked text
SHOP_ITEMS: dict[str, dict[str, Any]] = {
    "mystery_box": {
        "name": "Mystery Box",
        "emoji": "\U0001F381",  # 🎁
        "price": 150,
        "type": "consumable",
        "description": "A box of random goodies - coins, XP, or even a rare item. Open with `.openbox`.",
    },
    "streak_freeze": {
        "name": "Streak Freeze",
        "emoji": "\U0001F9CA",  # 🧊
        "price": 250,
        "type": "consumable",
        "description": "Automatically protects your study streak the next time you miss exactly one day.",
    },
    "xp_boost": {
        "name": "XP Boost",
        "emoji": "\u26A1",  # ⚡
        "price": 300,
        "type": "boost",
        "effect_id": "xp_boost",
        "duration_minutes": 60,
        "multiplier": 2,
        "description": "`.use` to double the XP you earn from studying for the next 60 minutes.",
    },
    "coin_boost": {
        "name": "Coin Boost",
        "emoji": "\U0001F4B0",  # 💰
        "price": 300,
        "type": "boost",
        "effect_id": "coin_boost",
        "duration_minutes": 60,
        "multiplier": 2,
        "description": "`.use` to double the coins you earn from studying for the next 60 minutes.",
    },
    "title_scholar": {
        "name": "Title: The Scholar",
        "emoji": "\U0001F3F7\uFE0F",  # 🏷️
        "price": 400,
        "type": "title",
        "title_text": "The Scholar",
        "description": "Unlocks a custom title to display on your `.stats` profile.",
    },
    "title_grinder": {
        "name": "Title: The Grinder",
        "emoji": "\U0001F3F7\uFE0F",
        "price": 400,
        "type": "title",
        "title_text": "The Grinder",
        "description": "Unlocks a custom title to display on your `.stats` profile.",
    },
    "title_insomniac": {
        "name": "Title: Insomniac",
        "emoji": "\U0001F3F7\uFE0F",
        "price": 400,
        "type": "title",
        "title_text": "Insomniac",
        "description": "Unlocks a custom title to display on your `.stats` profile.",
    },
    "title_legend": {
        "name": "Title: Legend",
        "emoji": "\U0001F3F7\uFE0F",
        "price": 1000,
        "type": "title",
        "title_text": "Legend",
        "description": "A prestige title for the truly dedicated.",
    },
}

# Stable display order for `.shop`.
SHOP_ORDER: list[str] = [
    "mystery_box", "streak_freeze", "xp_boost", "coin_boost",
    "title_scholar", "title_grinder", "title_insomniac", "title_legend",
]


def resolve_item_id(text: str) -> Optional[str]:
    """Match user-typed text (id, or a loose name match) to a shop item id."""
    key = text.strip().lower().replace(" ", "_").replace("-", "_")
    if key in SHOP_ITEMS:
        return key
    for item_id, item in SHOP_ITEMS.items():
        if item["name"].lower() == text.strip().lower():
            return item_id
    return None


# --------------------------------------------------------------------- #
# Mystery box rewards
# --------------------------------------------------------------------- #
# Each entry: relative weight + what it grants when rolled.
BOX_REWARDS: list[dict[str, Any]] = [
    {"weight": 40, "kind": "coins", "min": 50, "max": 150},
    {"weight": 25, "kind": "coins", "min": 150, "max": 300},
    {"weight": 15, "kind": "xp", "min": 100, "max": 300},
    {"weight": 10, "kind": "item", "item_id": "streak_freeze", "qty": 1},
    {"weight": 7, "kind": "coins", "min": 300, "max": 600},
    {"weight": 3, "kind": "item", "item_id": "title_legend", "qty": 1},
]


def roll_mystery_box() -> dict[str, Any]:
    """Return a single resolved reward, e.g. {'kind': 'coins', 'amount': 210}
    or {'kind': 'item', 'item_id': 'streak_freeze', 'qty': 1}."""
    weights = [r["weight"] for r in BOX_REWARDS]
    reward = random.choices(BOX_REWARDS, weights=weights, k=1)[0]
    if reward["kind"] in ("coins", "xp"):
        return {"kind": reward["kind"], "amount": random.randint(reward["min"], reward["max"])}
    return {"kind": "item", "item_id": reward["item_id"], "qty": reward["qty"]}


# --------------------------------------------------------------------- #
# Manually-logged milestone rewards (chapters/books/PYQs/revisions -
# see cogs/progress.py). Flat rewards, not random, since these are
# self-reported one-off events rather than continuous study time.
# --------------------------------------------------------------------- #
MILESTONE_REWARDS: dict[str, dict[str, int]] = {
    "chapter": {"coins": 30, "xp": 20},
    "subtopic": {"coins": 10, "xp": 8},
    "book": {"coins": 200, "xp": 150},
    "pyq": {"coins": 40, "xp": 25},
    "revision": {"coins": 150, "xp": 100},
}

# --------------------------------------------------------------------- #
# `.daily` reward formula
# --------------------------------------------------------------------- #
DAILY_COINS_MIN = 120
DAILY_COINS_MAX = 220
DAILY_XP_MIN = 20
DAILY_XP_MAX = 50
DAILY_STREAK_BONUS_PER_DAY = 15
DAILY_STREAK_BONUS_CAP_DAYS = 40  # streak coin-bonus caps at +600
DAILY_BOX_STREAK_INTERVAL = 5  # every 5th consecutive claim also grants a Mystery Box

# One-time milestone rewards layered on top of the normal roll, keyed
# by the streak count (after this claim) that triggers them. Each adds
# bonus coins and a Mystery Box; the bigger ones also throw in a
# specific item.
DAILY_MILESTONES: dict[int, dict[str, Any]] = {
    7: {"coins": 300, "box": True, "item": None},
    14: {"coins": 600, "box": True, "item": "xp_boost"},
    30: {"coins": 1500, "box": True, "item": "coin_boost"},
    60: {"coins": 3000, "box": True, "item": "streak_freeze"},
    100: {"coins": 6000, "box": True, "item": "title_legend"},
}


def compute_daily_reward(streak_after_claim: int) -> dict[str, Any]:
    """Coins/XP/bonuses for a `.daily` claim landing on the given
    (already-incremented) streak count.

    Returns: base_coins, streak_bonus, coins (total), xp, bonus_box
    (bool), milestone (the DAILY_MILESTONES entry hit, or None).
    """
    base_coins = random.randint(DAILY_COINS_MIN, DAILY_COINS_MAX)
    streak_bonus = min(streak_after_claim, DAILY_STREAK_BONUS_CAP_DAYS) * DAILY_STREAK_BONUS_PER_DAY
    xp = random.randint(DAILY_XP_MIN, DAILY_XP_MAX)

    milestone = DAILY_MILESTONES.get(streak_after_claim)
    bonus_box = streak_after_claim > 0 and streak_after_claim % DAILY_BOX_STREAK_INTERVAL == 0
    if milestone and milestone.get("box"):
        bonus_box = True

    total_coins = base_coins + streak_bonus + (milestone["coins"] if milestone else 0)

    return {
        "base_coins": base_coins,
        "streak_bonus": streak_bonus,
        "coins": total_coins,
        "xp": xp,
        "bonus_box": bonus_box,
        "milestone": milestone,
    }
