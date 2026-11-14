"""Chronos Christmas Event: Toy Crafting Workshop Catalog.

Defines:
- 7 Bodies (teddy, robot, train, duck, soldier, doll, snowman)
- 5 Movers (wheels, spring, propeller, windup_key, rocket)
- 2 Cores (glow, music)
- 6 Finishes (candy_red, pine_green, frost_blue, gold, violet_night, peppermint)
- 7 Tags: wheels=rolls, spring=bounces, propeller=flies, windup_key=winds-up,
          rocket=zooms, glow=glows, music=plays-music
- 70 Named Toy Recipes (7 bodies x 5 movers x 2 cores)
"""
from __future__ import annotations

from typing import Any

TAGS: dict[str, str] = {
    "wheels": "rolls",
    "spring": "bounces",
    "propeller": "flies",
    "windup_key": "winds-up",
    "rocket": "zooms",
    "glow": "glows",
    "music": "plays-music",
}

BODIES: dict[str, dict[str, Any]] = {
    "teddy":   {"id": "teddy",   "name": "Teddy Bear",  "desc": "A soft plush bear with rounded ears and a warm button nose."},
    "robot":   {"id": "robot",   "name": "Tin Robot",   "desc": "A retro tin-plate automaton with an antenna and chest gauge."},
    "train":   {"id": "train",   "name": "Locomotive",  "desc": "A classic wooden holiday steam train with a tall smokestack."},
    "duck":    {"id": "duck",    "name": "Duckie",      "desc": "A perky carved duck with a bright orange bill and upturned tail."},
    "soldier": {"id": "soldier", "name": "Nutcracker",  "desc": "A stately holiday soldier with a tall shako hat and gold epaulets."},
    "doll":    {"id": "doll",    "name": "Porcelain Doll", "desc": "A vintage doll with a ribbon bow, curly locks, and a ruffled apron."},
    "snowman": {"id": "snowman", "name": "Snowman",     "desc": "A frosty holiday snowman with a top hat, carrot nose, and striped scarf."},
}

MOVERS: dict[str, dict[str, Any]] = {
    "wheels":     {"id": "wheels",     "name": "Toy Wheels",    "tag": "rolls",     "desc": "A pair of sturdy wooden toy wheels with metal hub pins."},
    "spring":     {"id": "spring",     "name": "Pogo Spring",   "tag": "bounces",   "desc": "A coiled tempered-steel spring that makes the toy bounce."},
    "propeller":  {"id": "propeller",  "name": "Rotor Propeller", "tag": "flies",   "desc": "A twin-blade aerodynamic spinning rotor cap."},
    "windup_key": {"id": "windup_key", "name": "Clockwork Key", "tag": "winds-up", "desc": "A golden brass winding key that powers internal clockwork gears."},
    "rocket":     {"id": "rocket",     "name": "Rocket Thruster", "tag": "zooms",   "desc": "A miniature retro-futuristic rocket booster with a fiery exhaust."},
}

CORES: dict[str, dict[str, Any]] = {
    "glow":  {"id": "glow",  "name": "Glow Beacon", "tag": "glows",       "desc": "A luminous filament bulb radiating warm festive sparks."},
    "music": {"id": "music", "name": "Music Box",   "tag": "plays-music", "desc": "A delicate clockwork chime mechanism that hums holiday melodies."},
}

FINISHES: dict[str, dict[str, Any]] = {
    "candy_red":    {"id": "candy_red",    "name": "Candy Red",    "base": "#d42436", "desc": "A glossy holiday crimson lacquer with golden accents."},
    "pine_green":   {"id": "pine_green",   "name": "Pine Green",   "base": "#237d45", "desc": "Deep evergreen forest green with warm winter trim."},
    "frost_blue":   {"id": "frost_blue",   "name": "Frost Blue",   "base": "#3ba8e0", "desc": "Glistening glacial cyan-blue with snowy highlights."},
    "gold":         {"id": "gold",         "name": "Gilded Gold",  "base": "#e5a924", "accent": "#9c2033", "desc": "Radiant royal gold leaf with rich velvet ruby accents."},
    "violet_night": {"id": "violet_night", "name": "Violet Night", "base": "#6b3ba8", "desc": "Deep twilight violet with starlight shimmer."},
    "peppermint":   {"id": "peppermint",   "name": "Peppermint",   "base": "#d42436", "accent": "#f4f6fa", "desc": "Festive two-tone candy cane stripes in red and crisp sugar white."},
}

# -------------------------------------------------------------------------
# The 70 Named Toy Recipes (7 bodies x 5 movers x 2 cores)
# -------------------------------------------------------------------------
RECIPES: dict[str, dict[str, Any]] = {
    # --- TEDDY (10) ---
    "teddy_wheels_glow":      {"id": "teddy_wheels_glow",      "name": "Glowbear Roller",        "body": "teddy",   "mover": "wheels",     "core": "glow",  "tags": ["rolls", "glows"]},
    "teddy_wheels_music":     {"id": "teddy_wheels_music",     "name": "Melody Bear Kart",       "body": "teddy",   "mover": "wheels",     "core": "music", "tags": ["rolls", "plays-music"]},
    "teddy_spring_glow":      {"id": "teddy_spring_glow",      "name": "Beacon Bouncer Bear",    "body": "teddy",   "mover": "spring",     "core": "glow",  "tags": ["bounces", "glows"]},
    "teddy_spring_music":     {"id": "teddy_spring_music",     "name": "Musical Jumper Bear",    "body": "teddy",   "mover": "spring",     "core": "music", "tags": ["bounces", "plays-music"]},
    "teddy_propeller_glow":   {"id": "teddy_propeller_glow",   "name": "Skyglow Teddy",          "body": "teddy",   "mover": "propeller",  "core": "glow",  "tags": ["flies", "glows"]},
    "teddy_propeller_music":  {"id": "teddy_propeller_music",  "name": "Whirlybird Songbear",    "body": "teddy",   "mover": "propeller",  "core": "music", "tags": ["flies", "plays-music"]},
    "teddy_windup_glow":      {"id": "teddy_windup_glow",      "name": "Clockwork Glowbear",     "body": "teddy",   "mover": "windup_key", "core": "glow",  "tags": ["winds-up", "glows"]},
    "teddy_windup_music":     {"id": "teddy_windup_music",     "name": "Chimebox Teddy",         "body": "teddy",   "mover": "windup_key", "core": "music", "tags": ["winds-up", "plays-music"]},
    "teddy_rocket_glow":      {"id": "teddy_rocket_glow",      "name": "Starbound Bear",         "body": "teddy",   "mover": "rocket",     "core": "glow",  "tags": ["zooms", "glows"]},
    "teddy_rocket_music":     {"id": "teddy_rocket_music",     "name": "Astro Chime Bear",       "body": "teddy",   "mover": "rocket",     "core": "music", "tags": ["zooms", "plays-music"]},

    # --- ROBOT (10) ---
    "robot_wheels_glow":      {"id": "robot_wheels_glow",      "name": "Lumina Rover",           "body": "robot",   "mover": "wheels",     "core": "glow",  "tags": ["rolls", "glows"]},
    "robot_wheels_music":     {"id": "robot_wheels_music",     "name": "Beatbox Bot",            "body": "robot",   "mover": "wheels",     "core": "music", "tags": ["rolls", "plays-music"]},
    "robot_spring_glow":      {"id": "robot_spring_glow",      "name": "Pulse Pogo Bot",         "body": "robot",   "mover": "spring",     "core": "glow",  "tags": ["bounces", "glows"]},
    "robot_spring_music":     {"id": "robot_spring_music",     "name": "Springtime Synthbot",    "body": "robot",   "mover": "spring",     "core": "music", "tags": ["bounces", "plays-music"]},
    "robot_propeller_glow":   {"id": "robot_propeller_glow",   "name": "Skyward Probe",          "body": "robot",   "mover": "propeller",  "core": "glow",  "tags": ["flies", "glows"]},
    "robot_propeller_music":  {"id": "robot_propeller_music",  "name": "Aero Chime Droid",       "body": "robot",   "mover": "propeller",  "core": "music", "tags": ["flies", "plays-music"]},
    "robot_windup_glow":      {"id": "robot_windup_glow",      "name": "Radiant Clockbot",       "body": "robot",   "mover": "windup_key", "core": "glow",  "tags": ["winds-up", "glows"]},
    "robot_windup_music":     {"id": "robot_windup_music",     "name": "Clockwork Harmonizer",   "body": "robot",   "mover": "windup_key", "core": "music", "tags": ["winds-up", "plays-music"]},
    "robot_rocket_glow":      {"id": "robot_rocket_glow",      "name": "Cosmo Dynamo",           "body": "robot",   "mover": "rocket",     "core": "glow",  "tags": ["zooms", "glows"]},
    "robot_rocket_music":     {"id": "robot_rocket_music",     "name": "Nova Jukebot",           "body": "robot",   "mover": "rocket",     "core": "music", "tags": ["zooms", "plays-music"]},

    # --- TRAIN (10) ---
    "train_wheels_glow":      {"id": "train_wheels_glow",      "name": "Starlight Express",      "body": "train",   "mover": "wheels",     "core": "glow",  "tags": ["rolls", "glows"]},
    "train_wheels_music":     {"id": "train_wheels_music",     "name": "Harmony Locomotive",     "body": "train",   "mover": "wheels",     "core": "music", "tags": ["rolls", "plays-music"]},
    "train_spring_glow":      {"id": "train_spring_glow",      "name": "Bouncing Beacon Train",  "body": "train",   "mover": "spring",     "core": "glow",  "tags": ["bounces", "glows"]},
    "train_spring_music":     {"id": "train_spring_music",     "name": "Rhythmic Hopper Engine", "body": "train",   "mover": "spring",     "core": "music", "tags": ["bounces", "plays-music"]},
    "train_propeller_glow":   {"id": "train_propeller_glow",   "name": "Aero Beacon Zephyr",     "body": "train",   "mover": "propeller",  "core": "glow",  "tags": ["flies", "glows"]},
    "train_propeller_music":  {"id": "train_propeller_music",  "name": "Skycar Symphony",        "body": "train",   "mover": "propeller",  "core": "music", "tags": ["flies", "plays-music"]},
    "train_windup_glow":      {"id": "train_windup_glow",      "name": "Lantern Steamwork",      "body": "train",   "mover": "windup_key", "core": "glow",  "tags": ["winds-up", "glows"]},
    "train_windup_music":     {"id": "train_windup_music",     "name": "Clockwork Conductor",    "body": "train",   "mover": "windup_key", "core": "music", "tags": ["winds-up", "plays-music"]},
    "train_rocket_glow":      {"id": "train_rocket_glow",      "name": "Astro Starline",         "body": "train",   "mover": "rocket",     "core": "glow",  "tags": ["zooms", "glows"]},
    "train_rocket_music":     {"id": "train_rocket_music",     "name": "Rocket Rhapsody Engine", "body": "train",   "mover": "rocket",     "core": "music", "tags": ["zooms", "plays-music"]},

    # --- DUCK (10) ---
    "duck_wheels_glow":       {"id": "duck_wheels_glow",       "name": "Glowquack Cruiser",      "body": "duck",    "mover": "wheels",     "core": "glow",  "tags": ["rolls", "glows"]},
    "duck_wheels_music":      {"id": "duck_wheels_music",      "name": "Melody Duck Cart",       "body": "duck",    "mover": "wheels",     "core": "music", "tags": ["rolls", "plays-music"]},
    "duck_spring_glow":       {"id": "duck_spring_glow",       "name": "Sunbeam Duckling",       "body": "duck",    "mover": "spring",     "core": "glow",  "tags": ["bounces", "glows"]},
    "duck_spring_music":      {"id": "duck_spring_music",      "name": "Pogo Peep Singer",       "body": "duck",    "mover": "spring",     "core": "music", "tags": ["bounces", "plays-music"]},
    "duck_propeller_glow":    {"id": "duck_propeller_glow",    "name": "Lantern Quacker",        "body": "duck",    "mover": "propeller",  "core": "glow",  "tags": ["flies", "glows"]},
    "duck_propeller_music":   {"id": "duck_propeller_music",   "name": "Aviator Mallard",        "body": "duck",    "mover": "propeller",  "core": "music", "tags": ["flies", "plays-music"]},
    "duck_windup_glow":       {"id": "duck_windup_glow",       "name": "Clockwork Glowduck",     "body": "duck",    "mover": "windup_key", "core": "glow",  "tags": ["winds-up", "glows"]},
    "duck_windup_music":      {"id": "duck_windup_music",      "name": "Chimepond Duck",         "body": "duck",    "mover": "windup_key", "core": "music", "tags": ["winds-up", "plays-music"]},
    "duck_rocket_glow":       {"id": "duck_rocket_glow",       "name": "Turbo Glow Drake",       "body": "duck",    "mover": "rocket",     "core": "glow",  "tags": ["zooms", "glows"]},
    "duck_rocket_music":      {"id": "duck_rocket_music",      "name": "Quacksonic Rocket",      "body": "duck",    "mover": "rocket",     "core": "music", "tags": ["zooms", "plays-music"]},

    # --- SOLDIER (10) ---
    "soldier_wheels_glow":    {"id": "soldier_wheels_glow",    "name": "Vanguard Scout",         "body": "soldier", "mover": "wheels",     "core": "glow",  "tags": ["rolls", "glows"]},
    "soldier_wheels_music":   {"id": "soldier_wheels_music",   "name": "Marching Drummer Cart",  "body": "soldier", "mover": "wheels",     "core": "music", "tags": ["rolls", "plays-music"]},
    "soldier_spring_glow":    {"id": "soldier_spring_glow",    "name": "Sentinel Springer",      "body": "soldier", "mover": "spring",     "core": "glow",  "tags": ["bounces", "glows"]},
    "soldier_spring_music":   {"id": "soldier_spring_music",   "name": "Cadence Jumper",         "body": "soldier", "mover": "spring",     "core": "music", "tags": ["bounces", "plays-music"]},
    "soldier_propeller_glow": {"id": "soldier_propeller_glow", "name": "Beacon Paratrooper",     "body": "soldier", "mover": "propeller",  "core": "glow",  "tags": ["flies", "glows"]},
    "soldier_propeller_music":{"id": "soldier_propeller_music","name": "Aero Bugler Guard",      "body": "soldier", "mover": "propeller",  "core": "music", "tags": ["flies", "plays-music"]},
    "soldier_windup_glow":    {"id": "soldier_windup_glow",    "name": "Royal Clockguard",       "body": "soldier", "mover": "windup_key", "core": "glow",  "tags": ["winds-up", "glows"]},
    "soldier_windup_music":   {"id": "soldier_windup_music",   "name": "Nutcracker Chimer",      "body": "soldier", "mover": "windup_key", "core": "music", "tags": ["winds-up", "plays-music"]},
    "soldier_rocket_glow":    {"id": "soldier_rocket_glow",    "name": "Skyburst Sentinel",      "body": "soldier", "mover": "rocket",     "core": "glow",  "tags": ["zooms", "glows"]},
    "soldier_rocket_music":   {"id": "soldier_rocket_music",   "name": "Sonic Striker Guard",    "body": "soldier", "mover": "rocket",     "core": "music", "tags": ["zooms", "plays-music"]},

    # --- DOLL (10) ---
    "doll_wheels_glow":       {"id": "doll_wheels_glow",       "name": "Starlight Carriage",     "body": "doll",    "mover": "wheels",     "core": "glow",  "tags": ["rolls", "glows"]},
    "doll_wheels_music":      {"id": "doll_wheels_music",      "name": "Ballerina Cart",         "body": "doll",    "mover": "wheels",     "core": "music", "tags": ["rolls", "plays-music"]},
    "doll_spring_glow":       {"id": "doll_spring_glow",       "name": "Glowdance Jumper",       "body": "doll",    "mover": "spring",     "core": "glow",  "tags": ["bounces", "glows"]},
    "doll_spring_music":      {"id": "doll_spring_music",      "name": "Musicbox Dancer",        "body": "doll",    "mover": "spring",     "core": "music", "tags": ["bounces", "plays-music"]},
    "doll_propeller_glow":    {"id": "doll_propeller_glow",    "name": "Luminous Pixie",         "body": "doll",    "mover": "propeller",  "core": "glow",  "tags": ["flies", "glows"]},
    "doll_propeller_music":   {"id": "doll_propeller_music",   "name": "Seraphina Flyer",        "body": "doll",    "mover": "propeller",  "core": "music", "tags": ["flies", "plays-music"]},
    "doll_windup_glow":       {"id": "doll_windup_glow",       "name": "Clockwork Maiden",       "body": "doll",    "mover": "windup_key", "core": "glow",  "tags": ["winds-up", "glows"]},
    "doll_windup_music":      {"id": "doll_windup_music",      "name": "Melody Musicbox Doll",   "body": "doll",    "mover": "windup_key", "core": "music", "tags": ["winds-up", "plays-music"]},
    "doll_rocket_glow":       {"id": "doll_rocket_glow",       "name": "Comet Princess",         "body": "doll",    "mover": "rocket",     "core": "glow",  "tags": ["zooms", "glows"]},
    "doll_rocket_music":      {"id": "doll_rocket_music",      "name": "Stardust Songstress",     "body": "doll",    "mover": "rocket",     "core": "music", "tags": ["zooms", "plays-music"]},

    # --- SNOWMAN (10) ---
    "snowman_wheels_glow":    {"id": "snowman_wheels_glow",    "name": "Frostglow Sledder",      "body": "snowman", "mover": "wheels",     "core": "glow",  "tags": ["rolls", "glows"]},
    "snowman_wheels_music":   {"id": "snowman_wheels_music",   "name": "Caroling Snow Cart",     "body": "snowman", "mover": "wheels",     "core": "music", "tags": ["rolls", "plays-music"]},
    "snowman_spring_glow":    {"id": "snowman_spring_glow",    "name": "Bouncing Blizz",         "body": "snowman", "mover": "spring",     "core": "glow",  "tags": ["bounces", "glows"]},
    "snowman_spring_music":   {"id": "snowman_spring_music",   "name": "Jingling Frosthop",      "body": "snowman", "mover": "spring",     "core": "music", "tags": ["bounces", "plays-music"]},
    "snowman_propeller_glow": {"id": "snowman_propeller_glow", "name": "Blizzard Whirler",       "body": "snowman", "mover": "propeller",  "core": "glow",  "tags": ["flies", "glows"]},
    "snowman_propeller_music":{"id": "snowman_propeller_music","name": "Caroling Whirly Frosty", "body": "snowman", "mover": "propeller",  "core": "music", "tags": ["flies", "plays-music"]},
    "snowman_windup_glow":    {"id": "snowman_windup_glow",    "name": "Clockwork Frostman",     "body": "snowman", "mover": "windup_key", "core": "glow",  "tags": ["winds-up", "glows"]},
    "snowman_windup_music":   {"id": "snowman_windup_music",   "name": "Winter Chime Snowman",   "body": "snowman", "mover": "windup_key", "core": "music", "tags": ["winds-up", "plays-music"]},
    "snowman_rocket_glow":    {"id": "snowman_rocket_glow",    "name": "Polar Starshot",         "body": "snowman", "mover": "rocket",     "core": "glow",  "tags": ["zooms", "glows"]},
    "snowman_rocket_music":   {"id": "snowman_rocket_music",   "name": "Hypersonic Snowman",     "body": "snowman", "mover": "rocket",     "core": "music", "tags": ["zooms", "plays-music"]},
}
