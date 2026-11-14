"""Deterministic color ramp derivation and palette mapping for Chronos toys.

Rules:
- Native 16x16 pixels, transparent background.
- 1px dark outline: #2b1d2e (warm dark, never pure black).
- 3-tone shading ramp per colour region (dark / base / light).
- Light from top-left.
- Non-recolourable fixed regions (eyes, metal, snow/white, glow, music note).
- 6 Finishes defined by base colour (and optional accent), ramps derived deterministically.
"""
from __future__ import annotations

import colorsys
from typing import Any


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def rgb_to_hex(rgb: tuple[float, float, float] | tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        *(max(0, min(255, int(round(c)))) for c in rgb)
    )


def derive_ramp(hex_color: str) -> dict[str, str]:
    """Derive dark, base, and light tones deterministically from a base hex colour.
    
    Rule:
    - Light: higher lightness, hue nudged slightly toward warm yellow (60 deg / 0.1667).
    - Dark: lower lightness, hue nudged slightly toward cool blue (240 deg / 0.6667).
    """
    r, g, b = [c / 255.0 for c in hex_to_rgb(hex_color)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    # Light tone: higher lightness, gentle desaturation if saturated, warm shift
    l_light = min(0.92, l + 0.18 + (1.0 - l) * 0.10)
    s_light = max(0.18, s * 0.88)
    dh_light = (60.0 / 360.0 - h + 0.5) % 1.0 - 0.5
    h_light = (h + dh_light * 0.18) % 1.0
    r_l, g_l, b_l = colorsys.hls_to_rgb(h_light, l_light, s_light)

    # Dark tone: lower lightness, slight saturation boost, cool shift
    l_dark = max(0.10, l * 0.48)
    s_dark = min(1.0, s * 1.06 + 0.05)
    dh_dark = (240.0 / 360.0 - h + 0.5) % 1.0 - 0.5
    h_dark = (h + dh_dark * 0.16) % 1.0
    r_d, g_d, b_d = colorsys.hls_to_rgb(h_dark, l_dark, s_dark)

    return {
        "dark": rgb_to_hex((r_d * 255, g_d * 255, b_d * 255)),
        "base": hex_color,
        "light": rgb_to_hex((r_l * 255, g_l * 255, b_l * 255)),
    }


# -------------------------------------------------------------------------
# Finish Definitions
# Adding a 7th finish later only requires 1 new line!
# -------------------------------------------------------------------------
FINISH_DEFS: dict[str, dict[str, Any]] = {
    "candy_red":     {"name": "Candy Red",     "base": "#d42436"},
    "pine_green":    {"name": "Pine Green",    "base": "#237d45"},
    "frost_blue":    {"name": "Frost Blue",    "base": "#3ba8e0"},
    "gold":          {"name": "Gold",          "base": "#e5a924", "accent": "#9c2033"},
    "violet_night":  {"name": "Violet Night",  "base": "#6b3ba8"},
    "peppermint":    {"name": "Peppermint",    "base": "#d42436", "accent": "#f4f6fa"},
}


def get_finish_palette(finish_id: str) -> dict[str, tuple[int, int, int, int]]:
    """Build the full RGBA color mapping for a given finish."""
    fdef = FINISH_DEFS[finish_id]
    pri_ramp = derive_ramp(fdef["base"])

    # If accent is not explicitly provided, derive a warm golden/ivory toy trim
    acc_base = fdef.get("accent") or "#f0d080"
    acc_ramp = derive_ramp(acc_base)

    # Palette table mapping character keys to RGBA tuples
    def c(hex_s: str, a: int = 255) -> tuple[int, int, int, int]:
        rgb = hex_to_rgb(hex_s)
        return (rgb[0], rgb[1], rgb[2], a)

    return {
        ".": (0, 0, 0, 0),             # Transparent
        "#": c("#2b1d2e"),             # 1px dark warm outline (never pure black)

        # Recolourable Primary ramp (3 keys)
        "D": c(pri_ramp["dark"]),
        "P": c(pri_ramp["base"]),
        "L": c(pri_ramp["light"]),

        # Recolourable Accent ramp (2 keys)
        "a": c(acc_ramp["dark"]),
        "A": c(acc_ramp["base"]),

        # Fixed colors (NOT recoloured)
        "e": c("#18111c"),             # Eye pupils / dark coal
        "w": c("#f6f9fc"),             # White highlight / snow base
        "W": c("#ffffff"),             # Pure white highlight
        "g": c("#c5d4e6"),             # Snow / white shadow
        "G": c("#92a4bc"),             # Deep snow shadow

        "m": c("#7c778a"),             # Metal base
        "M": c("#4e4858"),             # Metal dark
        "h": c("#c5c0d2"),             # Metal light / highlight

        "o": c("#e86a17"),             # Carrot / beak orange base
        "O": c("#9e3b08"),             # Orange dark
        "Y": c("#fca038"),             # Orange light

        "f": c("#f5cb98"),             # Flesh / face base
        "F": c("#e49870"),             # Flesh dark / rosy cheek blush

        "y": c("#ffd028"),             # Duck yellow base
        "Y": c("#e29c12"),             # Duck yellow shadow

        "v": c("#3fe0e0"),             # Visor / glass cyan base
        "V": c("#168a98"),             # Visor / glass cyan dark

        "k": c("#8a4e23"),             # Wood / brown base
        "K": c("#542d10"),             # Wood / brown dark

        # Brown fur ramp (teddy)
        "b": c("#b46a36"),             # Brown fur base
        "B": c("#6e3914"),             # Brown fur dark / shadow
        "l": c("#d9925e"),             # Brown fur light / muzzle

        # Crimson red ramp (soldier coat, train cab, rocket nose, paint)
        "r": c("#d82436"),             # Crimson red base
        "R": c("#7a0f1d"),             # Crimson red dark
        "p": c("#ea5665"),             # Crimson red light

        # Gold / brass ramp (epaulets, bells, hubcaps, windup key)
        "j": c("#f8c538"),             # Gold base
        "J": c("#ad7a10"),             # Gold dark

        # Blue / sapphire (doll dress, frost finish)
        "c": c("#3ba8e0"),             # Blue base
        "C": c("#195682"),             # Blue dark

        # Green / emerald (pine finish, scarf)
        "u": c("#288e4e"),             # Green base
        "U": c("#144e27"),             # Green dark

        # Violet / purple (violet finish)
        "x": c("#8642bd"),             # Violet base
        "X": c("#4a1873"),             # Violet dark

        # Extended master shading tones (for rich pixel art)
        "q": c("#fff9e6"),             # Warm ivory / specular highlight
        "s": c("#e2e8f0"),             # Cool light glass / slate highlight
        "t": c("#94a3b8"),             # Cool slate / glass midtone
        "z": c("#1e293b"),             # Deep slate / shadow
        "d": c("#fed7aa"),             # Soft peach / snout highlight
        "n": c("#881337"),             # Deep ruby / crimson shadow
        "1": c("#fef08a"),             # Soft gold / light sparkle
        "2": c("#86efac"),             # Bright emerald / mint highlight
        "3": c("#064e3b"),             # Deep pine forest shadow
        "4": c("#7dd3fc"),             # Ice blue / frost highlight
        "5": c("#0369a1"),             # Deep ocean blue shadow
        "6": c("#fde047"),             # Brilliant gold highlight
        "7": c("#78350f"),             # Deep warm amber shadow
        "8": c("#c084fc"),             # Radiant lavender / violet highlight
        "9": c("#581c87"),             # Deep twilight purple shadow
        "0": c("#0f172a"),             # Deep midnight black shadow

        # Glow core colors
        "*": c("#ffffcc"),             # Glow bulb core / bright sparkle
        "+": c("#ffcc22"),             # Golden glow radiant aura
        "!": c("#ff7700"),             # Orange outer glow / flame spark

        # Music core colors
        "~": c("#ffd538"),             # Music note glyph / brass yellow
        "^": c("#c99014"),             # Music note shadow / deep brass
    }
