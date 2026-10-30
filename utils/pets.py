"""Pet species catalog, evolution chains, pricing, and the pet XP/level
curve.

Pure and content-only (like `utils/economy.py`'s SHOP_ITEMS or
`utils/xp.py`'s TIERS) - no database access here. Ported directly from
the pet-system prototype so ids, tiers, evolution levels, and prices
match it exactly. Sprites are pulled at render time from two public,
community-maintained sprite repos (no images are stored in this repo):
  - PokeAPI/sprites (animated base/mid/final sprites)
  - msikma/pokesprite (static mega/primal sprites)

Pet leveling is completely separate from a user's own study level/XP
(see `utils/xp.py`) - it uses its own linear curve (see
`xp_required_for_level` below) and its own `xp`/`level` columns on the
`user_pets` table (see database.py).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

_POKE_BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
_MEGA_BASE = "https://raw.githubusercontent.com/msikma/pokesprite/master/pokemon-gen8/regular"


def _anim(dex_id: int) -> str:
    return f"{_POKE_BASE}/versions/generation-v/black-white/animated/{dex_id}.gif"


def _mega(slug: str) -> str:
    return f"{_MEGA_BASE}/{slug}.png"


def _stage(name: str, sprite: str, level: int, badge: str) -> dict[str, Any]:
    return {"name": name, "sprite": sprite, "level": level, "badge": badge}


# --------------------------------------------------------------------- #
# Tiers - base price + display color/emoji, used to "color code" shop
# and pet embeds consistently.
# --------------------------------------------------------------------- #
TIER_INFO: dict[str, dict[str, Any]] = {
    "common":    {"label": "Common",    "base_price": 500,   "color": 0x8895B3, "emoji": "\u26AA"},
    "uncommon":  {"label": "Uncommon",  "base_price": 1200,  "color": 0x34D399, "emoji": "\U0001F7E2"},
    "rare":      {"label": "Rare",      "base_price": 2500,  "color": 0x22D3EE, "emoji": "\U0001F535"},
    "epic":      {"label": "Epic",      "base_price": 5000,  "color": 0xA78BFA, "emoji": "\U0001F7E3"},
    "legendary": {"label": "Legendary", "base_price": 50000, "color": 0xFBBF24, "emoji": "\U0001F7E1"},
    "event":     {"label": "Seasonal Event", "base_price": 0, "color": 0xFF7518, "emoji": "\U0001F383"},
}
TIER_ORDER: list[str] = ["common", "uncommon", "rare", "epic", "legendary"]

BADGE_LABELS = {"base": "Base", "mid": "Stage 2", "final": "Final", "mega": "Mega"}

# --------------------------------------------------------------------- #
# Species catalog
# --------------------------------------------------------------------- #
PETS: dict[str, dict[str, Any]] = {
    # ============ COMMON ============
    "bulbasaur": {"name": "Sprout", "species": "Bulb", "tier": "common", "stage_type": "three",
        "desc": "Photosynthesizes your desk lamp into motivation.",
        "stages": [
            _stage("Bulbasaur", _anim(1), 1, "base"),
            _stage("Ivysaur", _anim(2), 16, "mid"),
            _stage("Venusaur", _anim(3), 36, "final"),
            _stage("Mega Venusaur", _mega("venusaur-mega"), 75, "mega"),
        ]},
    "squirtle": {"name": "Bubbles", "species": "Turtle", "tier": "common", "stage_type": "three",
        "desc": "Carries your water bottle. Refuses to leave the library until you do.",
        "stages": [
            _stage("Squirtle", _anim(7), 1, "base"),
            _stage("Wartortle", _anim(8), 16, "mid"),
            _stage("Blastoise", _anim(9), 36, "final"),
            _stage("Mega Blastoise", _mega("blastoise-mega"), 75, "mega"),
        ]},
    "weedle": {"name": "Sting", "species": "Bug", "tier": "common", "stage_type": "three",
        "desc": "Shows up uninvited. Refuses to leave. Somehow useful anyway.",
        "stages": [
            _stage("Weedle", _anim(13), 1, "base"),
            _stage("Kakuna", _anim(14), 16, "mid"),
            _stage("Beedrill", _anim(15), 36, "final"),
            _stage("Mega Beedrill", _mega("beedrill-mega"), 75, "mega"),
        ]},
    "pidgey": {"name": "Wing", "species": "Bird", "tier": "common", "stage_type": "three",
        "desc": "Perches on your shoulder. Judges your posture silently.",
        "stages": [
            _stage("Pidgey", _anim(16), 1, "base"),
            _stage("Pidgeotto", _anim(17), 16, "mid"),
            _stage("Pidgeot", _anim(18), 36, "final"),
            _stage("Mega Pidgeot", _mega("pidgeot-mega"), 75, "mega"),
        ]},
    "slowpoke": {"name": "Doodle", "species": "Sloth", "tier": "common", "stage_type": "two",
        "desc": "Takes 5 minutes to realize you asked a question. Still finishes first.",
        "stages": [
            _stage("Slowpoke", _anim(79), 1, "base"),
            _stage("Slowbro", _anim(80), 36, "final"),
            _stage("Mega Slowbro", _mega("slowbro-mega"), 75, "mega"),
        ]},
    "magikarp": {"name": "Flop", "species": "Fish", "tier": "common", "stage_type": "two",
        "desc": "Useless for 35 levels. Absolute god after 36.",
        "stages": [
            _stage("Magikarp", _anim(129), 1, "base"),
            _stage("Gyarados", _anim(130), 36, "final"),
            _stage("Mega Gyarados", _mega("gyarados-mega"), 75, "mega"),
        ]},
    "houndour": {"name": "Biscuit", "species": "Dog", "tier": "common", "stage_type": "two",
        "desc": "Follows you to every study block. Breathes fire on distractions.",
        "stages": [
            _stage("Houndour", _anim(228), 1, "base"),
            _stage("Houndoom", _anim(229), 36, "final"),
            _stage("Mega Houndoom", _mega("houndoom-mega"), 75, "mega"),
        ]},

    # ============ UNCOMMON ============
    "abra": {"name": "Hocus", "species": "Psychic", "tier": "uncommon", "stage_type": "three",
        "desc": "Teleports your distractions away. Occasionally teleports your notes too.",
        "stages": [
            _stage("Abra", _anim(63), 1, "base"),
            _stage("Kadabra", _anim(64), 16, "mid"),
            _stage("Alakazam", _anim(65), 36, "final"),
            _stage("Mega Alakazam", _mega("alakazam-mega"), 75, "mega"),
        ]},
    "ralts": {"name": "Ribbon", "species": "Fae", "tier": "uncommon", "stage_type": "three",
        "desc": "Senses your emotions. Gently reminds you to drink water.",
        "stages": [
            _stage("Ralts", _anim(280), 1, "base"),
            _stage("Kirlia", _anim(281), 16, "mid"),
            _stage("Gardevoir", _anim(282), 36, "final"),
            _stage("Mega Gardevoir", _mega("gardevoir-mega"), 75, "mega"),
        ]},
    "aron": {"name": "Clank", "species": "Armor", "tier": "uncommon", "stage_type": "three",
        "desc": "Eats iron filings. Makes an excellent paperweight.",
        "stages": [
            _stage("Aron", _anim(304), 1, "base"),
            _stage("Lairon", _anim(305), 16, "mid"),
            _stage("Aggron", _anim(306), 36, "final"),
            _stage("Mega Aggron", _mega("aggron-mega"), 75, "mega"),
        ]},
    "electrike": {"name": "Sparky", "species": "Puppy", "tier": "uncommon", "stage_type": "two",
        "desc": "Static builds up in its fur. Shocks you awake at 3 AM.",
        "stages": [
            _stage("Electrike", _anim(309), 1, "base"),
            _stage("Manectric", _anim(310), 36, "final"),
            _stage("Mega Manectric", _mega("manectric-mega"), 75, "mega"),
        ]},
    "carvanha": {"name": "Chomp", "species": "Piranha", "tier": "uncommon", "stage_type": "two",
        "desc": "Bites through your procrastination. Literally.",
        "stages": [
            _stage("Carvanha", _anim(318), 1, "base"),
            _stage("Sharpedo", _anim(319), 36, "final"),
            _stage("Mega Sharpedo", _mega("sharpedo-mega"), 75, "mega"),
        ]},
    "numel": {"name": "Lava", "species": "Camel", "tier": "uncommon", "stage_type": "two",
        "desc": "Stores magma in its hump. Warm study buddy in winter.",
        "stages": [
            _stage("Numel", _anim(322), 1, "base"),
            _stage("Camerupt", _anim(323), 36, "final"),
            _stage("Mega Camerupt", _mega("camerupt-mega"), 75, "mega"),
        ]},
    "swablu": {"name": "Cloud", "species": "Bird", "tier": "uncommon", "stage_type": "two",
        "desc": "Soft, fluffy, and sings you to sleep.",
        "stages": [
            _stage("Swablu", _anim(333), 1, "base"),
            _stage("Altaria", _anim(334), 36, "final"),
            _stage("Mega Altaria", _mega("altaria-mega"), 75, "mega"),
        ]},
    "shuppet": {"name": "Spook", "species": "Puppet", "tier": "uncommon", "stage_type": "two",
        "desc": "Feeds on negative thoughts. Thrives during exam season.",
        "stages": [
            _stage("Shuppet", _anim(353), 1, "base"),
            _stage("Banette", _anim(354), 36, "final"),
            _stage("Mega Banette", _mega("banette-mega"), 75, "mega"),
        ]},

    # ============ RARE ============
    "bagon": {"name": "Rocky", "species": "Hatchling", "tier": "rare", "stage_type": "three",
        "desc": "Dreams of flying. Settles for sitting on your desk and looking determined.",
        "stages": [
            _stage("Bagon", _anim(371), 1, "base"),
            _stage("Shelgon", _anim(372), 16, "mid"),
            _stage("Salamence", _anim(373), 36, "final"),
            _stage("Mega Salamence", _mega("salamence-mega"), 75, "mega"),
        ]},
    "beldum": {"name": "Magnet", "species": "Metallic", "tier": "rare", "stage_type": "three",
        "desc": "Hums quietly. Redirects paper clips. Weirdly calming.",
        "stages": [
            _stage("Beldum", _anim(374), 1, "base"),
            _stage("Metang", _anim(375), 16, "mid"),
            _stage("Metagross", _anim(376), 36, "final"),
            _stage("Mega Metagross", _mega("metagross-mega"), 75, "mega"),
        ]},
    "snorunt": {"name": "Frost", "species": "Snowcap", "tier": "rare", "stage_type": "two",
        "desc": "Chills your coffee. Sits quietly in the corner. Ideal.",
        "stages": [
            _stage("Snorunt", _anim(361), 1, "base"),
            _stage("Glalie", _anim(362), 36, "final"),
            _stage("Mega Glalie", _mega("glalie-mega"), 75, "mega"),
        ]},
    "sableye": {"name": "Gem", "species": "Gremlin", "tier": "rare", "stage_type": "two",
        "desc": "Eats gemstones. Steals your highlighters. Offers nothing in return.",
        "stages": [
            _stage("Sableye", _anim(302), 1, "base"),
            _stage("Mega Sableye", _mega("sableye-mega"), 75, "mega"),
        ]},
    "absol": {"name": "Omen", "species": "Disaster", "tier": "rare", "stage_type": "two",
        "desc": "Appears before deadlines. Warns you. You ignore it. It tries again.",
        "stages": [
            _stage("Absol", _anim(359), 1, "base"),
            _stage("Mega Absol", _mega("absol-mega"), 75, "mega"),
        ]},
    "buneary": {"name": "Marshmallow", "species": "Bunny", "tier": "rare", "stage_type": "two",
        "desc": "Ears twitch when you solve a hard problem. Runs on carrots and momentum.",
        "stages": [
            _stage("Buneary", _anim(427), 1, "base"),
            _stage("Lopunny", _anim(428), 36, "final"),
            _stage("Mega Lopunny", _mega("lopunny-mega"), 75, "mega"),
        ]},
    "scyther": {"name": "Slash", "species": "Mantis", "tier": "rare", "stage_type": "two",
        "desc": "Slices through your to-do list. Efficient but scary.",
        "stages": [
            _stage("Scyther", _anim(123), 1, "base"),
            _stage("Scizor", _anim(212), 36, "final"),
            _stage("Mega Scizor", _mega("scizor-mega"), 75, "mega"),
        ]},
    "heracross": {"name": "Herc", "species": "Beetle", "tier": "rare", "stage_type": "two",
        "desc": "Lifts heavy textbooks without complaining. Shows off constantly.",
        "stages": [
            _stage("Heracross", _anim(214), 1, "base"),
            _stage("Mega Heracross", _mega("heracross-mega"), 75, "mega"),
        ]},
    "onix": {"name": "Boulder", "species": "Serpent", "tier": "rare", "stage_type": "two",
        "desc": "Wraps around your desk. Blocks exits. Keeps you studying.",
        "stages": [
            _stage("Onix", _anim(95), 1, "base"),
            _stage("Steelix", _anim(208), 36, "final"),
            _stage("Mega Steelix", _mega("steelix-mega"), 75, "mega"),
        ]},

    # ============ EPIC ============
    "gastly": {"name": "Boo", "species": "Ghost", "tier": "epic", "stage_type": "three",
        "desc": "Haunts your skipped topics. Appears at 2am with a list.",
        "stages": [
            _stage("Gastly", _anim(92), 1, "base"),
            _stage("Haunter", _anim(93), 16, "mid"),
            _stage("Gengar", _anim(94), 36, "final"),
            _stage("Mega Gengar", _mega("gengar-mega"), 75, "mega"),
        ]},
    "mareep": {"name": "Fluff", "species": "Sheep", "tier": "epic", "stage_type": "three",
        "desc": "Counts itself when you can't sleep. Very meta.",
        "stages": [
            _stage("Mareep", _anim(179), 1, "base"),
            _stage("Flaaffy", _anim(180), 16, "mid"),
            _stage("Ampharos", _anim(181), 36, "final"),
            _stage("Mega Ampharos", _mega("ampharos-mega"), 75, "mega"),
        ]},
    "larvitar": {"name": "Titan", "species": "Rock", "tier": "epic", "stage_type": "three",
        "desc": "Eats mountains for breakfast. Still complains about the workload.",
        "stages": [
            _stage("Larvitar", _anim(246), 1, "base"),
            _stage("Pupitar", _anim(247), 16, "mid"),
            _stage("Tyranitar", _anim(248), 36, "final"),
            _stage("Mega Tyranitar", _mega("tyranitar-mega"), 75, "mega"),
        ]},
    "riolu": {"name": "Punchy", "species": "Pup", "tier": "epic", "stage_type": "two",
        "desc": "Trains harder than you do. Sets a bad example for work-life balance.",
        "stages": [
            _stage("Riolu", _anim(447), 1, "base"),
            _stage("Lucario", _anim(448), 36, "final"),
            _stage("Mega Lucario", _mega("lucario-mega"), 75, "mega"),
        ]},
    "gible": {"name": "Chomp Jr", "species": "Land Shark", "tier": "epic", "stage_type": "three",
        "desc": "Bites everything. Including your pens, your notes, and your resolve.",
        "stages": [
            _stage("Gible", _anim(443), 1, "base"),
            _stage("Gabite", _anim(444), 16, "mid"),
            _stage("Garchomp", _anim(445), 36, "final"),
            _stage("Mega Garchomp", _mega("garchomp-mega"), 75, "mega"),
        ]},
    "torchic": {"name": "Yolk", "species": "Chick", "tier": "epic", "stage_type": "three",
        "desc": "Two days old. Already better at organic chemistry than you.",
        "stages": [
            _stage("Torchic", _anim(255), 1, "base"),
            _stage("Combusken", _anim(256), 16, "mid"),
            _stage("Blaziken", _anim(257), 36, "final"),
            _stage("Mega Blaziken", _mega("blaziken-mega"), 75, "mega"),
        ]},
    "treecko": {"name": "Leaf", "species": "Gecko", "tier": "epic", "stage_type": "three",
        "desc": "Climbs walls. Sits on your ceiling. Judges you from above.",
        "stages": [
            _stage("Treecko", _anim(252), 1, "base"),
            _stage("Grovyle", _anim(253), 16, "mid"),
            _stage("Sceptile", _anim(254), 36, "final"),
            _stage("Mega Sceptile", _mega("sceptile-mega"), 75, "mega"),
        ]},
    "mudkip": {"name": "Muddy", "species": "Mudfish", "tier": "epic", "stage_type": "three",
        "desc": "Thrives in chaos. Feels nothing during exam week.",
        "stages": [
            _stage("Mudkip", _anim(258), 1, "base"),
            _stage("Marshtomp", _anim(259), 16, "mid"),
            _stage("Swampert", _anim(260), 36, "final"),
            _stage("Mega Swampert", _mega("swampert-mega"), 75, "mega"),
        ]},

    # ============ LEGENDARY TRIO 1 - KANTO BIRDS ============
    "articuno": {"name": "Freeze", "species": "Legendary Bird", "tier": "legendary", "stage_type": "single",
        "desc": "Kanto Bird Trio. Cools the air around your desk. Excellent for hot days.",
        "stages": [_stage("Articuno", _anim(144), 1, "base")]},
    "zapdos": {"name": "Thunder", "species": "Legendary Bird", "tier": "legendary", "stage_type": "single",
        "desc": "Kanto Bird Trio. Static crackles when you procrastinate.",
        "stages": [_stage("Zapdos", _anim(145), 1, "base")]},
    "moltres": {"name": "Blaze", "species": "Legendary Bird", "tier": "legendary", "stage_type": "single",
        "desc": "Kanto Bird Trio. Lights your fireplace. Warms your ambition.",
        "stages": [_stage("Moltres", _anim(146), 1, "base")]},

    # ============ LEGENDARY TRIO 2 - JOHTO BEASTS ============
    "raikou": {"name": "Volt", "species": "Legendary Beast", "tier": "legendary", "stage_type": "single",
        "desc": "Johto Beast Trio. Runs across the clouds. Faster than your deadline.",
        "stages": [_stage("Raikou", _anim(243), 1, "base")]},
    "entei": {"name": "Ember", "species": "Legendary Beast", "tier": "legendary", "stage_type": "single",
        "desc": "Johto Beast Trio. Burns everything it touches - including your excuses.",
        "stages": [_stage("Entei", _anim(244), 1, "base")]},
    "suicune": {"name": "Crystal", "species": "Legendary Beast", "tier": "legendary", "stage_type": "single",
        "desc": "Johto Beast Trio. Purifies polluted water. Also purifies bad vibes.",
        "stages": [_stage("Suicune", _anim(245), 1, "base")]},

    # ============ LEGENDARY TRIO 3 - HOENN WEATHER ============
    "kyogre": {"name": "Tide", "species": "Legendary Sea", "tier": "legendary", "stage_type": "single",
        "desc": "Hoenn Weather Trio. Brings rain. Fills your water bottle automatically.",
        "stages": [
            _stage("Kyogre", _anim(382), 1, "base"),
            _stage("Primal Kyogre", _mega("kyogre-primal"), 75, "mega"),
        ]},
    "groudon": {"name": "Quake", "species": "Legendary Land", "tier": "legendary", "stage_type": "single",
        "desc": "Hoenn Weather Trio. Raises continents. Also raises your GPA.",
        "stages": [
            _stage("Groudon", _anim(383), 1, "base"),
            _stage("Primal Groudon", _mega("groudon-primal"), 75, "mega"),
        ]},
    "rayquaza": {"name": "Sky", "species": "Legendary Sky", "tier": "legendary", "stage_type": "single",
        "desc": "Hoenn Weather Trio. Lives in the ozone layer. Drops by to check on you.",
        "stages": [
            _stage("Rayquaza", _anim(384), 1, "base"),
            _stage("Mega Rayquaza", _mega("rayquaza-mega"), 75, "mega"),
        ]},

    # ============ EXTRA LEGENDARIES ============
    "mewtwo": {"name": "Origin", "species": "Legendary Psychic", "tier": "legendary", "stage_type": "single",
        "desc": "Created in a lab. Has two megas. Still can't figure out your sleep schedule.",
        "stages": [
            _stage("Mewtwo", _anim(150), 1, "base"),
            _stage("Mega Mewtwo X", _mega("mewtwo-mega-x"), 75, "mega"),
            _stage("Mega Mewtwo Y", _mega("mewtwo-mega-y"), 75, "mega"),
        ]},
    "diancie": {"name": "Jewel", "species": "Mythical Rock", "tier": "legendary", "stage_type": "single",
        "desc": "A mutated Carbink. Shoots diamonds. Funds your study snacks.",
        "stages": [
            _stage("Diancie", _anim(719), 1, "base"),
            _stage("Mega Diancie", _mega("diancie-mega"), 75, "mega"),
        ]},
    "charmander": {"name": "Ember", "species": "Legendary Dragon", "tier": "legendary", "stage_type": "three",
        "desc": "Guards your study desk. Breathes fire on distractions. Loyal to the end.",
        "stages": [
            _stage("Charmander", _anim(4), 1, "base"),
            _stage("Charmeleon", _anim(5), 16, "mid"),
            _stage("Charizard", _anim(6), 36, "final"),
            _stage("Mega Charizard X", _mega("charizard-mega-x"), 75, "mega"),
            _stage("Mega Charizard Y", _mega("charizard-mega-y"), 75, "mega"),
        ]},

    # ============ SEASONAL EVENT EXCLUSIVE ============
    "pumpkaboo": {"name": "Spooky", "species": "Pumpkin", "tier": "event", "stage_type": "two",
        "exclusive": True,
        "desc": "Carries wandering spirits. Grows warmer and brighter the more you study.",
        "stages": [
            _stage("Pumpkaboo", "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/showdown/710.gif", 1, "base"),
            _stage("Gourgeist", "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/showdown/711.gif", 36, "final"),
        ]},
}

PETS_BY_TIER: dict[str, list[str]] = {
    tier: [sid for sid, p in PETS.items() if p["tier"] == tier] for tier in TIER_ORDER
}


def pet_cost(species_id: str) -> int:
    """Coin price to unlock a species - identical formula to the
    prototype: legendaries are a flat 50,000; everything else scales
    off its tier's base price depending on how long its evolution
    line is (a 3-stage line costs more than a 2-stage one)."""
    pet = PETS[species_id]
    if pet["tier"] == "event" or pet.get("exclusive"):
        return 0
    if pet["tier"] == "legendary":
        return 50000
    base = TIER_INFO[pet["tier"]]["base_price"]
    if pet["stage_type"] == "three":
        return base * 2
    return round(base * 1.5)


def stage_for_level(species_id: str, level: int) -> dict[str, Any]:
    """The evolution stage a pet displays as at a given level - the
    highest stage whose level requirement has been met."""
    pet = PETS[species_id]
    stage = pet["stages"][0]
    for s in pet["stages"]:
        if level >= s["level"]:
            stage = s
    return stage


def next_stage(species_id: str, level: int) -> Optional[dict[str, Any]]:
    """The next not-yet-reached evolution stage, or None if already at
    the final one."""
    pet = PETS[species_id]
    current = stage_for_level(species_id, level)
    reached = False
    for s in pet["stages"]:
        if reached:
            return s
        if s is current:
            reached = True
    return None


def resolve_species(text: str) -> Optional[str]:
    """Match user-typed text to a species id: the id itself, its
    default nickname, or any of its evolution-stage names."""
    key = text.strip().lower().replace(" ", "_").replace("-", "_")
    if key in PETS:
        return key
    needle = text.strip().lower()
    for sid, p in PETS.items():
        if p["name"].lower() == needle:
            return sid
    for sid, p in PETS.items():
        if any(s["name"].lower() == needle for s in p["stages"]):
            return sid
    return None


# --------------------------------------------------------------------- #
# Pet XP/level curve - per project spec: leveling a pet from `level` to
# `level + 1` costs `30 + 10 * (level - 1)` XP. Kept as its own curve,
# fully independent of a user's own study level (utils/xp.py).
# --------------------------------------------------------------------- #
def xp_required_for_level(level: int) -> int:
    level = max(1, level)
    return 30 + 10 * (level - 1)


@lru_cache(maxsize=None)
def total_xp_for_level(level: int) -> int:
    """Cumulative XP required to *reach* `level`, starting from 0 at level 1."""
    if level <= 1:
        return 0
    return total_xp_for_level(level - 1) + xp_required_for_level(level - 1)


_MAX_LEVEL_LOOKUP = 500


def level_from_xp(xp: int) -> int:
    level = 1
    while level < _MAX_LEVEL_LOOKUP and total_xp_for_level(level + 1) <= xp:
        level += 1
    return level


def xp_progress(xp: int) -> tuple[int, int, int]:
    """Return (xp_into_current_level, xp_needed_for_next_level, level)."""
    level = level_from_xp(xp)
    floor = total_xp_for_level(level)
    ceiling = total_xp_for_level(level + 1)
    return xp - floor, ceiling - floor, level
