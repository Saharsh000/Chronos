"""Egg catalog, tier definitions, drop tables, and incubation loot generators.

Part of THE EGG UPDATE for Chronos:
- Eggs drop frequently during study sessions, daily rewards, work, and beg.
- Eggs can be incubated in your incubator by studying to unlock maximum rewards & rare pets!
- Or eggs can be cracked open immediately for instant loot.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from utils import food as food_catalog
from utils import pets as pet_catalog

# --------------------------------------------------------------------- #
# Egg Catalog & Metadata
# --------------------------------------------------------------------- #

EGGS: dict[str, dict[str, Any]] = {
    "egg_common": {
        "id": "egg_common",
        "name": "Common Egg",
        "tier": "common",
        "emoji": "🥚",
        "color": 0x94A3B8,  # Slate / Silver
        "incubation_seconds": 600,  # 10 minutes of study
        "price": 350,
        "desc": "A speckled white egg found frequently while studying. Hatches with basic study warmth.",
        "pet_tier": "common",
        "aliases": ["common", "white", "basic", "egg_common", "c"],
    },
    "egg_uncommon": {
        "id": "egg_uncommon",
        "name": "Verdant Egg",
        "tier": "uncommon",
        "emoji": "🟢🥚",
        "color": 0x22C55E,  # Emerald Green
        "incubation_seconds": 1500,  # 25 minutes of study
        "price": 950,
        "desc": "A smooth forest-green egg humming with focus energy. Yields solid coin stashes and pets.",
        "pet_tier": "uncommon",
        "aliases": ["uncommon", "green", "verdant", "egg_uncommon", "u"],
    },
    "egg_rare": {
        "id": "egg_rare",
        "name": "Azure Egg",
        "tier": "rare",
        "emoji": "🔵🪺",
        "color": 0x38BDF8,  # Sky Blue
        "incubation_seconds": 2700,  # 45 minutes of study
        "price": 2500,
        "desc": "A deep azure egg warm to the touch. Contains rare species, high XP, and feast items.",
        "pet_tier": "rare",
        "aliases": ["rare", "blue", "azure", "egg_rare", "r"],
    },
    "egg_epic": {
        "id": "egg_epic",
        "name": "Mythic Egg",
        "tier": "epic",
        "emoji": "🟣✨",
        "color": 0xA855F7,  # Vivid Purple
        "incubation_seconds": 5400,  # 90 minutes of study
        "price": 6500,
        "desc": "A pulsating amethyst shell crackling with arcane power. Packed with epic pets and treasures.",
        "pet_tier": "epic",
        "aliases": ["epic", "purple", "mythic", "egg_epic", "e"],
    },
    "egg_legendary": {
        "id": "egg_legendary",
        "name": "Cosmic Egg",
        "tier": "legendary",
        "emoji": "🟡🌟",
        "color": 0xF59E0B,  # Radiant Gold
        "incubation_seconds": 10800,  # 180 minutes (3 hours of study)
        "price": 25000,
        "desc": "An ancient celestial egg radiating starlight. Holds guaranteed legendary pets and massive jackpots.",
        "pet_tier": "legendary",
        "aliases": ["legendary", "gold", "cosmic", "egg_legendary", "l"],
    },
}

EGG_ORDER: list[str] = ["egg_common", "egg_uncommon", "egg_rare", "egg_epic", "egg_legendary"]

# --------------------------------------------------------------------- #
# Pet Pools By Tier
# --------------------------------------------------------------------- #

PET_POOLS: dict[str, list[str]] = {
    "common": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "common"],
    "uncommon": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "uncommon"],
    "rare": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "rare"],
    "epic": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "epic"],
    "legendary": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "legendary"],
}


def get_egg(egg_id: str) -> Optional[dict[str, Any]]:
    """Retrieve egg definition by key."""
    return EGGS.get(egg_id)


def resolve_egg_id(query: str) -> Optional[str]:
    """Resolve an egg query (by name, alias, or tier)."""
    q = query.strip().lower()
    if q in EGGS:
        return q

    # Check 1-based index (e.g. 1 -> common, 2 -> uncommon)
    if q.isdigit():
        idx = int(q) - 1
        if 0 <= idx < len(EGG_ORDER):
            return EGG_ORDER[idx]

    for egg_id, egg in EGGS.items():
        if q == egg["name"].lower():
            return egg_id
        if q in egg["aliases"]:
            return egg_id

    return None


# --------------------------------------------------------------------- #
# Drop Logic
# --------------------------------------------------------------------- #

def roll_study_egg(new_minutes: int) -> Optional[str]:
    """Roll for an egg drop during study.

    Called every time study minutes are credited.
    Roughly ~5% chance per minute, meaning ~1 egg every 20 minutes of study!
    """
    if new_minutes <= 0:
        return None

    # Roll chance: each minute gives a roll
    chance = min(0.85, 0.05 * new_minutes)
    if random.random() > chance:
        return None

    # Weighted tier distribution for study drops:
    # 60% Common, 25% Uncommon, 10% Rare, 4% Epic, 1% Legendary
    roll = random.random()
    if roll < 0.60:
        return "egg_common"
    elif roll < 0.85:
        return "egg_uncommon"
    elif roll < 0.95:
        return "egg_rare"
    elif roll < 0.99:
        return "egg_epic"
    else:
        return "egg_legendary"


# --------------------------------------------------------------------- #
# Loot Table Generator
# --------------------------------------------------------------------- #

def generate_hatch_loot(egg_id: str, is_incubated: bool = True) -> dict[str, Any]:
    """Generate rewards from hatching an egg.

    If is_incubated is True, gives full rewards and high pet chances.
    If is_incubated is False (instant crack), gives reduced quick loot.
    """
    egg = EGGS.get(egg_id, EGGS["egg_common"])
    tier = egg["tier"]

    pet_pool = PET_POOLS.get(tier, PET_POOLS["common"])
    chosen_pet = random.choice(pet_pool) if pet_pool else None

    # Common Egg
    if tier == "common":
        if is_incubated:
            roll = random.random()
            if roll < 0.28:
                return {"type": "pet", "species_id": chosen_pet, "coins": 100, "xp": 50}
            elif roll < 0.65:
                coins = random.randint(180, 450)
                xp = random.randint(40, 80)
                return {"type": "coins", "coins": coins, "xp": xp}
            else:
                snack_keys = [k for k, f in food_catalog.FOOD.items() if f["tier"] == "snack"]
                food_id = random.choice(snack_keys) if snack_keys else "apple_pie"
                return {"type": "food", "food_id": food_id, "qty": random.randint(1, 2), "coins": 80, "xp": 40}
        else:
            # Quick crack
            roll = random.random()
            if roll < 0.08:
                return {"type": "pet", "species_id": chosen_pet, "coins": 50, "xp": 25}
            elif roll < 0.70:
                return {"type": "coins", "coins": random.randint(80, 220), "xp": 20}
            else:
                return {"type": "food", "food_id": "cookies", "qty": 1, "coins": 30, "xp": 15}

    # Uncommon Egg
    elif tier == "uncommon":
        if is_incubated:
            roll = random.random()
            if roll < 0.32:
                return {"type": "pet", "species_id": chosen_pet, "coins": 250, "xp": 120}
            elif roll < 0.68:
                return {"type": "coins", "coins": random.randint(550, 1300), "xp": random.randint(100, 200)}
            elif roll < 0.88:
                meal_keys = [k for k, f in food_catalog.FOOD.items() if f["tier"] == "meal"]
                food_id = random.choice(meal_keys) if meal_keys else "bento"
                return {"type": "food", "food_id": food_id, "qty": 1, "coins": 200, "xp": 80}
            else:
                boost = random.choice(["xp_boost", "coin_boost"])
                return {"type": "item", "item_id": boost, "qty": 1, "coins": 200, "xp": 100}
        else:
            roll = random.random()
            if roll < 0.12:
                return {"type": "pet", "species_id": chosen_pet, "coins": 100, "xp": 50}
            elif roll < 0.75:
                return {"type": "coins", "coins": random.randint(250, 650), "xp": 60}
            else:
                return {"type": "food", "food_id": "bread", "qty": 2, "coins": 100, "xp": 30}

    # Rare Egg
    elif tier == "rare":
        if is_incubated:
            roll = random.random()
            if roll < 0.38:
                return {"type": "pet", "species_id": chosen_pet, "coins": 600, "xp": 250}
            elif roll < 0.70:
                return {"type": "coins", "coins": random.randint(1600, 3800), "xp": random.randint(250, 500)}
            elif roll < 0.88:
                feast_keys = [k for k, f in food_catalog.FOOD.items() if f["tier"] == "feast"]
                food_id = random.choice(feast_keys) if feast_keys else "roasted_chicken"
                return {"type": "food", "food_id": food_id, "qty": 1, "coins": 400, "xp": 150}
            else:
                item_id = random.choice(["streak_freeze", "mystery_box"])
                return {"type": "item", "item_id": item_id, "qty": 1, "coins": 500, "xp": 200}
        else:
            roll = random.random()
            if roll < 0.15:
                return {"type": "pet", "species_id": chosen_pet, "coins": 250, "xp": 100}
            elif roll < 0.75:
                return {"type": "coins", "coins": random.randint(800, 1900), "xp": 150}
            else:
                return {"type": "food", "food_id": "pizza", "qty": 1, "coins": 300, "xp": 75}

    # Epic Egg
    elif tier == "epic":
        if is_incubated:
            roll = random.random()
            if roll < 0.45:
                return {"type": "pet", "species_id": chosen_pet, "coins": 1500, "xp": 600}
            elif roll < 0.75:
                return {"type": "coins", "coins": random.randint(4500, 9500), "xp": random.randint(600, 1200)}
            elif roll < 0.90:
                golden_keys = [k for k, f in food_catalog.FOOD.items() if f["tier"] == "golden"]
                food_id = random.choice(golden_keys) if golden_keys else "golden_apple"
                return {"type": "food", "food_id": food_id, "qty": 1, "coins": 1000, "xp": 400}
            else:
                return {"type": "item", "item_id": "mystery_box", "qty": 3, "coins": 1500, "xp": 500}
        else:
            roll = random.random()
            if roll < 0.20:
                return {"type": "pet", "species_id": chosen_pet, "coins": 600, "xp": 250}
            elif roll < 0.80:
                return {"type": "coins", "coins": random.randint(2200, 5000), "xp": 350}
            else:
                return {"type": "food", "food_id": "seafood_platter", "qty": 1, "coins": 800, "xp": 200}

    # Legendary Egg (Cosmic Egg)
    else:
        if is_incubated:
            roll = random.random()
            # 60% chance for a guaranteed legendary pet!
            if roll < 0.60:
                return {"type": "pet", "species_id": chosen_pet, "coins": 5000, "xp": 2000}
            elif roll < 0.85:
                return {"type": "coins", "coins": random.randint(18000, 36000), "xp": random.randint(1800, 3500)}
            else:
                # Cosmic Jackpot!
                return {
                    "type": "jackpot",
                    "coins": 50000,
                    "xp": 5000,
                    "item_id": "mystery_box",
                    "qty": 5,
                    "title": "Cosmic Egg Master",
                }
        else:
            roll = random.random()
            if roll < 0.30:
                return {"type": "pet", "species_id": chosen_pet, "coins": 2000, "xp": 800}
            elif roll < 0.85:
                return {"type": "coins", "coins": random.randint(9000, 18000), "xp": 1000}
            else:
                return {"type": "food", "food_id": "ambrosia", "qty": 1, "coins": 3000, "xp": 600}
