"""Pet food catalog - `.foodshop` / `.buyfood` / `.feed` / `.sellfood`
(see cogs/pets.py).

Food stacks in the same `user_inventory` table the coin shop's
consumables use (see database.py) - it's just a second catalog keyed
by its own ids, kept separate from `utils/economy.py`'s SHOP_ITEMS
since it's bought/consumed through its own commands. Pure and
content-only, no database access here. Ported directly from the
pet-system prototype so ids, tiers, XP amounts, and prices match it
exactly. Sprites come from the public Sorseg/jemerje icon set.
"""
from __future__ import annotations

from typing import Any, Optional

_JEM_BASE = "https://raw.githubusercontent.com/Sorseg/jemerje/main/assets/icons"


def _sprite(name: str) -> str:
    return f"{_JEM_BASE}/{name}.png"


FOOD_TIER_INFO: dict[str, dict[str, Any]] = {
    "snack":  {"label": "Snack",  "color": 0x8895B3, "emoji": "\U0001F36A"},  # 🍪
    "meal":   {"label": "Meal",   "color": 0x34D399, "emoji": "\U0001F35B"},  # 🍛
    "feast":  {"label": "Feast",  "color": 0xA78BFA, "emoji": "\U0001F357"},  # 🍗
    "golden": {"label": "Golden", "color": 0xFBBF24, "emoji": "\u2728"},      # ✨
}
FOOD_TIER_ORDER: list[str] = ["snack", "meal", "feast", "golden"]

FOODS: dict[str, dict[str, Any]] = {
    # ---- SNACK TIER ----
    "apple_pie":   {"name": "Apple Pie",       "tier": "snack", "xp": 40,  "cost": 100,  "sprite": _sprite("05_apple_pie")},
    "bread":       {"name": "Bread",           "tier": "snack", "xp": 45,  "cost": 110,  "sprite": _sprite("07_bread")},
    "baguette":    {"name": "Baguette",        "tier": "snack", "xp": 45,  "cost": 110,  "sprite": _sprite("09_baguette")},
    "bun":         {"name": "Bun",             "tier": "snack", "xp": 48,  "cost": 115,  "sprite": _sprite("11_bun")},
    "bacon":       {"name": "Bacon",           "tier": "snack", "xp": 50,  "cost": 120,  "sprite": _sprite("13_bacon")},
    "bagel":       {"name": "Bagel",           "tier": "snack", "xp": 52,  "cost": 125,  "sprite": _sprite("20_bagel")},
    "cheesepuff":  {"name": "Cheese Puff",     "tier": "snack", "xp": 55,  "cost": 130,  "sprite": _sprite("24_cheesepuff")},
    "chocolate":   {"name": "Chocolate",       "tier": "snack", "xp": 55,  "cost": 130,  "sprite": _sprite("26_chocolate")},
    "cookies":     {"name": "Cookies",         "tier": "snack", "xp": 58,  "cost": 135,  "sprite": _sprite("28_cookies")},
    "donut":       {"name": "Donut",           "tier": "snack", "xp": 60,  "cost": 140,  "sprite": _sprite("34_donut")},
    "dumplings":   {"name": "Dumplings",       "tier": "snack", "xp": 60,  "cost": 140,  "sprite": _sprite("36_dumplings")},
    "fried_egg":   {"name": "Fried Egg",       "tier": "snack", "xp": 62,  "cost": 145,  "sprite": _sprite("38_friedegg")},
    "egg_salad":   {"name": "Egg Salad",       "tier": "snack", "xp": 62,  "cost": 145,  "sprite": _sprite("40_eggsalad")},
    "egg_tart":    {"name": "Egg Tart",        "tier": "snack", "xp": 65,  "cost": 150,  "sprite": _sprite("42_eggtart")},

    # ---- MEAL TIER ----
    "fries":         {"name": "French Fries",    "tier": "meal", "xp": 200, "cost": 450, "sprite": _sprite("44_frenchfries")},
    "fruitcake":     {"name": "Fruitcake",       "tier": "meal", "xp": 210, "cost": 470, "sprite": _sprite("46_fruitcake")},
    "garlic_bread":  {"name": "Garlic Bread",    "tier": "meal", "xp": 215, "cost": 480, "sprite": _sprite("48_garlicbread")},
    "gingerbread":   {"name": "Gingerbread",     "tier": "meal", "xp": 220, "cost": 490, "sprite": _sprite("52_gingerbreadman")},
    "hotdog":        {"name": "Hot Dog",         "tier": "meal", "xp": 225, "cost": 500, "sprite": _sprite("54_hotdog")},
    "icecream":      {"name": "Ice Cream",       "tier": "meal", "xp": 230, "cost": 510, "sprite": _sprite("57_icecream")},
    "jelly":         {"name": "Jelly",           "tier": "meal", "xp": 235, "cost": 520, "sprite": _sprite("59_jelly")},
    "jam":           {"name": "Jam",             "tier": "meal", "xp": 240, "cost": 530, "sprite": _sprite("61_jam")},
    "lemon_pie":     {"name": "Lemon Pie",       "tier": "meal", "xp": 245, "cost": 540, "sprite": _sprite("63_lemonpie")},
    "loaf":          {"name": "Loaf Bread",      "tier": "meal", "xp": 248, "cost": 545, "sprite": _sprite("65_loafbread")},
    "mac_cheese":    {"name": "Mac & Cheese",    "tier": "meal", "xp": 250, "cost": 550, "sprite": _sprite("67_macncheese")},
    "meatball":      {"name": "Meatball",        "tier": "meal", "xp": 252, "cost": 555, "sprite": _sprite("69_meatball")},
    "nachos":        {"name": "Nachos",          "tier": "meal", "xp": 255, "cost": 560, "sprite": _sprite("71_nacho")},
    "omelette":      {"name": "Omelette",        "tier": "meal", "xp": 258, "cost": 565, "sprite": _sprite("73_omlet")},
    "pudding":       {"name": "Pudding",         "tier": "meal", "xp": 260, "cost": 570, "sprite": _sprite("75_pudding")},

    # ---- FEAST TIER ----
    "chips":         {"name": "Potato Chips",    "tier": "feast", "xp": 800,  "cost": 1600, "sprite": _sprite("77_potatochips")},
    "pancakes":      {"name": "Pancakes",        "tier": "feast", "xp": 820,  "cost": 1640, "sprite": _sprite("79_pancakes")},
    "pizza":         {"name": "Pizza",           "tier": "feast", "xp": 840,  "cost": 1680, "sprite": _sprite("81_pizza")},
    "popcorn":       {"name": "Popcorn",         "tier": "feast", "xp": 860,  "cost": 1720, "sprite": _sprite("83_popcorn")},
    "roast_chicken": {"name": "Roast Chicken",   "tier": "feast", "xp": 880,  "cost": 1760, "sprite": _sprite("85_roastedchicken")},
    "ramen":         {"name": "Ramen",           "tier": "feast", "xp": 900,  "cost": 1800, "sprite": _sprite("87_ramen")},
    "salmon":        {"name": "Salmon",          "tier": "feast", "xp": 920,  "cost": 1840, "sprite": _sprite("88_salmon")},
    "straw_cake":    {"name": "Strawberry Cake", "tier": "feast", "xp": 940,  "cost": 1880, "sprite": _sprite("90_strawberrycake")},
    "sandwich":      {"name": "Sandwich",        "tier": "feast", "xp": 960,  "cost": 1920, "sprite": _sprite("92_sandwich")},
    "spaghetti":     {"name": "Spaghetti",       "tier": "feast", "xp": 980,  "cost": 1960, "sprite": _sprite("94_spaghetti")},
    "steak":         {"name": "Steak",           "tier": "feast", "xp": 1000, "cost": 2000, "sprite": _sprite("95_steak")},

    # ---- GOLDEN TIER ----
    "sushi":         {"name": "Sushi",         "tier": "golden", "xp": 3000, "cost": 5500, "sprite": _sprite("97_sushi")},
    "taco":          {"name": "Taco",          "tier": "golden", "xp": 3200, "cost": 5800, "sprite": _sprite("99_taco")},
    "waffle":        {"name": "Waffle",        "tier": "golden", "xp": 3500, "cost": 6200, "sprite": _sprite("101_waffle")},
    "gummy_bear":    {"name": "Giant Gummy",   "tier": "golden", "xp": 3800, "cost": 6600, "sprite": _sprite("50_giantgummybear")},
    "straw_cake_g":  {"name": "Royal Cake",    "tier": "golden", "xp": 4000, "cost": 7000, "sprite": _sprite("90_strawberrycake")},
}

# Stable display order for `.foodshop <tier>`, matching the prototype.
FOOD_ORDER: list[str] = list(FOODS.keys())

FOODS_BY_TIER: dict[str, list[str]] = {
    tier: [fid for fid in FOOD_ORDER if FOODS[fid]["tier"] == tier] for tier in FOOD_TIER_ORDER
}


def resolve_food(text: str) -> Optional[str]:
    """Match user-typed text (id, or a loose name match) to a food id."""
    key = text.strip().lower().replace(" ", "_").replace("-", "_")
    if key in FOODS:
        return key
    needle = text.strip().lower()
    for fid, f in FOODS.items():
        if f["name"].lower() == needle:
            return fid
    return None
