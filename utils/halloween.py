"""Halloween Seasonal Event catalog, Hallo-Boxes, Jack-o'-Lantern pass, and Candy Shop.

Content-only and pure (like utils/pets.py and utils/economy.py) - no direct DB access.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from utils import food as food_catalog
from utils import pets as pet_catalog

# --------------------------------------------------------------------- #
# Hallo-Boxes Catalog (100% Drop-Only - Instant Open - NO Incubation)
# --------------------------------------------------------------------- #
HALLO_BOXES: dict[str, dict[str, Any]] = {
    "hbox_common": {
        "id": "hbox_common",
        "tier": "common",
        "name": "Common Hallo-Box",
        "emoji": "🪵",
        "color": 0x8895B3,
        "description": "A spooky wooden crate tied with dried pumpkin vines. Opens instantly!",
        "candy_min": 15,
        "candy_max": 35,
        "coin_min": 150,
        "coin_max": 400,
        "pet_chance": 0.15,
        "food_chance": 0.35,
        "aliases": ["common", "wood", "wooden", "hbox1", "commonbox"],
    },
    "hbox_uncommon": {
        "id": "hbox_uncommon",
        "tier": "uncommon",
        "name": "Uncommon Hallo-Box",
        "emoji": "🟢",
        "color": 0x34D399,
        "description": "An eerie green-tinted chest humming with faint ghostly energy. Opens instantly!",
        "candy_min": 35,
        "candy_max": 75,
        "coin_min": 400,
        "coin_max": 900,
        "pet_chance": 0.25,
        "food_chance": 0.50,
        "aliases": ["uncommon", "green", "hbox2", "uncommonbox"],
    },
    "hbox_rare": {
        "id": "hbox_rare",
        "tier": "rare",
        "name": "Rare Hallo-Box",
        "emoji": "🔵",
        "color": 0x22D3EE,
        "description": "A spectral cobalt reliquary radiating chilled midnight mist. Opens instantly!",
        "candy_min": 75,
        "candy_max": 150,
        "coin_min": 1000,
        "coin_max": 2500,
        "pet_chance": 0.40,
        "food_chance": 0.65,
        "aliases": ["rare", "blue", "hbox3", "rarebox"],
    },
    "hbox_epic": {
        "id": "hbox_epic",
        "tier": "epic",
        "name": "Epic Hallo-Box",
        "emoji": "🟣",
        "color": 0xA78BFA,
        "description": "A glowing violet vault etched with ancient pumpkin glyphs. Opens instantly!",
        "candy_min": 160,
        "candy_max": 320,
        "coin_min": 2500,
        "coin_max": 6000,
        "pet_chance": 0.65,
        "food_chance": 0.85,
        "aliases": ["epic", "purple", "violet", "hbox4", "epicbox"],
    },
    "hbox_legendary": {
        "id": "hbox_legendary",
        "tier": "legendary",
        "name": "Legendary Hallo-Box",
        "emoji": "🟡",
        "color": 0xFBBF24,
        "description": "A crowned Jack-o'-Lantern treasure trove. Guaranteed high-tier pet & jackpot loot!",
        "candy_min": 400,
        "candy_max": 800,
        "coin_min": 7000,
        "coin_max": 16000,
        "pet_chance": 1.0,
        "food_chance": 1.0,
        "aliases": ["legendary", "gold", "golden", "hbox5", "legendarybox", "mythic"],
    },
}

HALLO_BOX_ORDER: list[str] = ["hbox_common", "hbox_uncommon", "hbox_rare", "hbox_epic", "hbox_legendary"]


def get_box(box_id: str) -> Optional[dict[str, Any]]:
    return HALLO_BOXES.get(box_id)


def resolve_box_id(query: str) -> Optional[str]:
    q = query.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    for box_id, box in HALLO_BOXES.items():
        clean_id = box_id.replace("_", "")
        if q == clean_id or q == box["tier"]:
            return box_id
        for alias in box["aliases"]:
            if q == alias.replace(" ", "").replace("-", "").replace("_", ""):
                return box_id
    return None


# --------------------------------------------------------------------- #
# Study Drop Rolls
# --------------------------------------------------------------------- #
def roll_study_hallo_box(new_minutes: int) -> Optional[str]:
    """Roll for a Hallo-Box drop during active study sessions.
    
    Generous ~5% chance per minute, averaging ~1 box every 15-20 minutes of study.
    """
    if new_minutes <= 0:
        return None
    chance_per_minute = 0.055
    drop_roll = random.random()
    threshold = 1.0 - ((1.0 - chance_per_minute) ** new_minutes)
    if drop_roll > threshold:
        return None

    roll = random.random()
    if roll < 0.60:
        return "hbox_common"
    elif roll < 0.85:
        return "hbox_uncommon"
    elif roll < 0.95:
        return "hbox_rare"
    elif roll < 0.99:
        return "hbox_epic"
    else:
        return "hbox_legendary"


def roll_study_candy(new_minutes: int) -> int:
    """Roll for direct Candy drops earned from active studying."""
    if new_minutes <= 0:
        return 0
    # Every minute gives between 1 and 3 Candy
    return sum(random.randint(1, 3) for _ in range(new_minutes))


# --------------------------------------------------------------------- #
# Hallo-Box Loot Generation
# --------------------------------------------------------------------- #
PET_POOLS: dict[str, list[str]] = {
    "common": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "common"],
    "uncommon": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "uncommon"],
    "rare": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "rare"],
    "epic": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "epic"],
    "legendary": [s for s, p in pet_catalog.PETS.items() if p["tier"] == "legendary"],
}


def generate_box_loot(box_id: str) -> dict[str, Any]:
    box = HALLO_BOXES.get(box_id, HALLO_BOXES["hbox_common"])
    tier = box["tier"]

    candy = random.randint(box["candy_min"], box["candy_max"])
    coins = random.randint(box["coin_min"], box["coin_max"])

    pet_dropped: Optional[str] = None
    if random.random() < box["pet_chance"]:
        if tier == "common":
            pet_dropped = random.choice(PET_POOLS["common"])
        elif tier == "uncommon":
            pool = PET_POOLS["uncommon"] if random.random() < 0.65 else PET_POOLS["common"]
            pet_dropped = random.choice(pool)
        elif tier == "rare":
            r = random.random()
            if r < 0.50:
                pet_dropped = random.choice(PET_POOLS["rare"])
            elif r < 0.85:
                pet_dropped = random.choice(PET_POOLS["uncommon"])
            else:
                pet_dropped = random.choice(PET_POOLS["common"])
        elif tier == "epic":
            r = random.random()
            if r < 0.08:
                pet_dropped = "pumpkaboo"  # Special jackpot chance!
            elif r < 0.55:
                pet_dropped = random.choice(PET_POOLS["epic"])
            elif r < 0.85:
                pet_dropped = random.choice(PET_POOLS["rare"])
            else:
                pet_dropped = random.choice(PET_POOLS["uncommon"])
        elif tier == "legendary":
            r = random.random()
            if r < 0.15:
                pet_dropped = "pumpkaboo"
            elif r < 0.65:
                pet_dropped = random.choice(PET_POOLS["legendary"])
            else:
                pet_dropped = random.choice(PET_POOLS["epic"])

    food_dropped: Optional[str] = None
    food_qty = 0
    if random.random() < box["food_chance"]:
        food_qty = 1 if tier != "legendary" else random.randint(1, 2)
        if tier == "common":
            food_dropped = random.choice(food_catalog.FOODS_BY_TIER["snack"])
        elif tier == "uncommon":
            pool = food_catalog.FOODS_BY_TIER["snack"] + food_catalog.FOODS_BY_TIER["meal"]
            food_dropped = random.choice(pool)
        elif tier == "rare":
            pool = food_catalog.FOODS_BY_TIER["meal"] + food_catalog.FOODS_BY_TIER["feast"]
            food_dropped = random.choice(pool)
        elif tier == "epic":
            food_dropped = random.choice(food_catalog.FOODS_BY_TIER["feast"])
        elif tier == "legendary":
            pool = food_catalog.FOODS_BY_TIER.get("golden", food_catalog.FOODS_BY_TIER["feast"])
            food_dropped = random.choice(pool)

    item_dropped: Optional[str] = None
    item_qty = 0
    if tier == "uncommon" and random.random() < 0.12:
        item_dropped = "mystery_box"
        item_qty = 1
    elif tier == "rare" and random.random() < 0.25:
        item_dropped = "sugar_rush" if random.random() < 0.50 else "mystery_box"
        item_qty = 1
    elif tier == "epic" and random.random() < 0.50:
        item_dropped = "sugar_rush"
        item_qty = 1
    elif tier == "legendary":
        item_dropped = "sugar_rush"
        item_qty = 1

    return {
        "box": box,
        "candy": candy,
        "coins": coins,
        "pet": pet_dropped,
        "food": food_dropped,
        "food_qty": food_qty,
        "item": item_dropped,
        "item_qty": item_qty,
    }


# --------------------------------------------------------------------- #
# THE JACK-O'-LANTERN (1-Per-Account Halloween Study Season Pass)
# --------------------------------------------------------------------- #
# Designed for a 10-day event window with 5 stages and sublevels.
JACK_O_LANTERN_LEVELS: list[dict[str, Any]] = [
    {
        "level": 1,
        "stage": 1,
        "stage_name": "Raw Gourd",
        "level_name": "Fresh Harvest Gourd",
        "emoji": "🪵",
        "required_seconds": 0,  # Unlocks immediately upon participation!
        "candy": 50,
        "coins": 250,
        "boxes": [],
        "items": [],
        "title": None,
        "desc": "Freshly harvested from the patch. Welcome to the Halloween Season Pass!",
    },
    {
        "level": 2,
        "stage": 1,
        "stage_name": "Raw Gourd",
        "level_name": "Chiseled Outlines",
        "emoji": "🔪",
        "required_seconds": 30 * 60,  # 30 mins
        "candy": 40,
        "coins": 350,
        "boxes": [("hbox_common", 1)],
        "items": [],
        "title": None,
        "desc": "Guidelines carved into the orange flesh. The first cuts are made.",
    },
    {
        "level": 3,
        "stage": 1,
        "stage_name": "Raw Gourd",
        "level_name": "Hollowed Core",
        "emoji": "🪚",
        "required_seconds": 60 * 60,  # 1 hour
        "candy": 60,
        "coins": 500,
        "boxes": [("hbox_common", 1)],
        "items": [],
        "title": None,
        "desc": "Pulp and seeds scooped clean. The hollow shell is ready for glowing light.",
    },
    {
        "level": 4,
        "stage": 1,
        "stage_name": "Raw Gourd",
        "level_name": "Carved Silhouette",
        "emoji": "🪓",
        "required_seconds": 90 * 60,  # 1.5 hours
        "candy": 80,
        "coins": 650,
        "boxes": [],
        "items": [("cookies", 2)],
        "title": None,
        "desc": "Eye sockets cut cleanly through the rind. It peers intently at your books.",
    },
    {
        "level": 5,
        "stage": 2,
        "stage_name": "Candlelit Pumpkin",
        "level_name": "Candlelit Pumpkin",
        "emoji": "🕯️",
        "required_seconds": 120 * 60,  # 2 hours
        "candy": 120,
        "coins": 1000,
        "boxes": [("hbox_common", 2)],
        "items": [],
        "title": None,
        "desc": "Stage 2 Milestone! A beeswax candle flickers within, casting spooky shadows.",
    },
    {
        "level": 6,
        "stage": 2,
        "stage_name": "Candlelit Pumpkin",
        "level_name": "Flickering Hearth",
        "emoji": "🕯️",
        "required_seconds": 180 * 60,  # 3 hours
        "candy": 140,
        "coins": 1200,
        "boxes": [("hbox_uncommon", 1)],
        "items": [],
        "title": None,
        "desc": "The flame burns bright against the midnight chill, dispelling procrastination.",
    },
    {
        "level": 7,
        "stage": 2,
        "stage_name": "Candlelit Pumpkin",
        "level_name": "Blazing Core",
        "emoji": "🕯️",
        "required_seconds": 240 * 60,  # 4 hours
        "candy": 160,
        "coins": 1400,
        "boxes": [],
        "items": [("ramen", 1)],
        "title": None,
        "desc": "The glow illuminates your desk with warm, steady discipline.",
    },
    {
        "level": 8,
        "stage": 3,
        "stage_name": "Smiling Jack",
        "level_name": "Smiling Jack",
        "emoji": "🎃",
        "required_seconds": 300 * 60,  # 5 hours
        "candy": 220,
        "coins": 2000,
        "boxes": [("hbox_rare", 1)],
        "items": [("sugar_rush", 1)],
        "title": None,
        "desc": "Stage 3 Milestone! A wicked grin is carved from cheek to cheek!",
    },
    {
        "level": 9,
        "stage": 3,
        "stage_name": "Smiling Jack",
        "level_name": "Grinning Specter",
        "emoji": "🎃",
        "required_seconds": 420 * 60,  # 7 hours
        "candy": 260,
        "coins": 2500,
        "boxes": [("hbox_uncommon", 2)],
        "items": [("mystery_box", 1)],
        "title": None,
        "desc": "The toothy smirk widens as chapter after chapter falls before you.",
    },
    {
        "level": 10,
        "stage": 3,
        "stage_name": "Smiling Jack",
        "level_name": "Sinister Jack",
        "emoji": "🎃",
        "required_seconds": 540 * 60,  # 9 hours
        "candy": 300,
        "coins": 3000,
        "boxes": [("hbox_rare", 1)],
        "items": [],
        "title": None,
        "desc": "Sharp jagged teeth gleaming in the dark. Ready for the toughest problem sets.",
    },
    {
        "level": 11,
        "stage": 4,
        "stage_name": "Haunted Jack",
        "level_name": "Haunted Jack",
        "emoji": "🪦",
        "required_seconds": 600 * 60,  # 10 hours
        "candy": 400,
        "coins": 4500,
        "boxes": [("hbox_epic", 1)],
        "items": [],
        "title": None,
        "desc": "Stage 4 Milestone! Eerie violet flames swirl through its hollow eyes!",
    },
    {
        "level": 12,
        "stage": 4,
        "stage_name": "Haunted Jack",
        "level_name": "Spectral Apparition",
        "emoji": "🪦",
        "required_seconds": 750 * 60,  # 12.5 hours
        "candy": 450,
        "coins": 5500,
        "boxes": [("hbox_rare", 2)],
        "items": [("sugar_rush", 1)],
        "title": None,
        "desc": "Ghostly vapors curl around your chair, shielding your focus from all distractions.",
    },
    {
        "level": 13,
        "stage": 4,
        "stage_name": "Haunted Jack",
        "level_name": "Phantom Warden",
        "emoji": "🪦",
        "required_seconds": 900 * 60,  # 15 hours
        "candy": 500,
        "coins": 6500,
        "boxes": [("hbox_epic", 1)],
        "items": [("sushi", 1)],
        "title": None,
        "desc": "The pumpkin whispers forgotten formulas and advanced derivations.",
    },
    {
        "level": 14,
        "stage": 5,
        "stage_name": "The Great Pumpkin",
        "level_name": "The Great Pumpkin",
        "emoji": "👑",
        "required_seconds": 1200 * 60,  # 20 hours
        "candy": 1000,
        "coins": 12000,
        "boxes": [("hbox_legendary", 1)],
        "items": [("sugar_rush", 2)],
        "title": "The Great Pumpkin",
        "desc": "Grand Finale Milestone! Crowned sovereign of Halloween study mastery!",
    },
]

MAX_PASS_LEVEL = len(JACK_O_LANTERN_LEVELS)


def get_pass_level(level_num: int) -> Optional[dict[str, Any]]:
    if 1 <= level_num <= len(JACK_O_LANTERN_LEVELS):
        return JACK_O_LANTERN_LEVELS[level_num - 1]
    return None


def get_current_pass_level(study_seconds: int) -> dict[str, Any]:
    current = JACK_O_LANTERN_LEVELS[0]
    for lvl in JACK_O_LANTERN_LEVELS:
        if study_seconds >= lvl["required_seconds"]:
            current = lvl
        else:
            break
    return current


def get_next_pass_level(study_seconds: int) -> Optional[dict[str, Any]]:
    for lvl in JACK_O_LANTERN_LEVELS:
        if study_seconds < lvl["required_seconds"]:
            return lvl
    return None


def format_progress_bar(current: int, target: int, length: int = 12) -> str:
    if target <= 0:
        return "▰" * length
    ratio = min(1.0, max(0.0, current / target))
    filled = int(round(ratio * length))
    empty = length - filled
    return "▰" * filled + "▱" * empty


# --------------------------------------------------------------------- #
# Candy Shop Catalog (`.candyshop`)
# --------------------------------------------------------------------- #
CANDY_SHOP_ITEMS: dict[str, dict[str, Any]] = {
    "pumpkaboo": {
        "id": "pumpkaboo",
        "type": "pet",
        "name": "Pumpkaboo",
        "emoji": "🎃",
        "candy_price": 750,
        "species_id": "pumpkaboo",
        "description": "Event-Exclusive Pokémon! Evolves into Gourgeist at Level 36. Never in regular pet shop!",
        "aliases": ["pumpkin", "pumpka", "gourgeist"],
    },
    "title_inorganic": {
        "id": "title_inorganic",
        "type": "title",
        "name": "Title: Inorganic Nightmare",
        "title_text": "Inorganic Nightmare",
        "emoji": "🧪",
        "candy_price": 400,
        "description": "Exclusive JEE Title: You survived qualitative analysis and p-block horrors.",
        "aliases": ["inorganic", "nightmare", "inorganic nightmare"],
    },
    "title_shift1": {
        "id": "title_shift1",
        "type": "title",
        "name": "Title: The Shift 1 Phantom",
        "title_text": "The Shift 1 Phantom",
        "emoji": "👻",
        "candy_price": 400,
        "description": "Exclusive JEE Title: Braved the cursed 27 Jan Shift 1.",
        "aliases": ["shift1", "shift 1", "phantom", "the shift 1 phantom"],
    },
    "sugar_rush": {
        "id": "sugar_rush",
        "type": "boost",
        "name": "Sugar Rush",
        "emoji": "⚡",
        "candy_price": 120,
        "description": "Consumable: Gives a 1-Hour 2x Study XP boost during your active study sessions!",
        "aliases": ["sugar", "sugarrush", "rush", "boost"],
    },
}

CANDY_SHOP_ORDER: list[str] = ["pumpkaboo", "title_inorganic", "title_shift1", "sugar_rush"]


def resolve_candy_shop_item(query: str) -> Optional[dict[str, Any]]:
    q = query.strip().lower().replace(" ", "_").replace("-", "_")
    if q in CANDY_SHOP_ITEMS:
        return CANDY_SHOP_ITEMS[q]
    clean_q = query.strip().lower()
    for item_id, item in CANDY_SHOP_ITEMS.items():
        if clean_q == item["name"].lower():
            return item
        if clean_q == item.get("title_text", "").lower():
            return item
        for alias in item.get("aliases", []):
            if clean_q == alias.lower():
                return item
    return None
