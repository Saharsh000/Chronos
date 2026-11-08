"""High-resolution study stats image generator suite for `.stats` / `.profile`.

Generates ultra-crisp, modern 1200x680 dark-themed cards using Pillow:
1. Overview Card (Main profile, study time, XP, coins, streak, achievements)
2. Weekly Activity Card (7-day bar chart, consistency, peak day, momentum)
3. Subject Breakdown Card (PCM distribution bar, subject cards, balance index)
4. Trivia Mastery Card (AIR rank tier, net marks, accuracy gauge, streak)

Zero tofu box rectangles, clean typography, dynamic Tier accents,
and authentic Minecraft pixel art icon integration.
"""
from __future__ import annotations

import io
import os
import re
from typing import Any, Optional
from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 1200
CARD_HEIGHT = 680
# Discord shows embed images sharper (and bigger when opened) at ~1080p.
EXPORT_SCALE = 1.6

# Dark obsidian theme palette
BG_COLOR = (11, 14, 20, 255)           # Deep slate / obsidian
CARD_BG = (20, 25, 34, 255)            # Elevated surface
CARD_BORDER = (45, 55, 72, 255)        # Subtle border
PANEL_BG = (16, 20, 28, 255)          # Micro card surface
PANEL_BORDER = (35, 43, 56, 255)      # Micro card border
BAR_BG = (30, 41, 59, 255)            # Track background
GRID_COLOR = (30, 41, 59, 160)        # Chart grid line

TEXT_MUTED = (148, 163, 184, 255)      # Slate-400
TEXT_WHITE = (248, 250, 252, 255)      # Slate-50
TEXT_SUB = (203, 213, 225, 255)        # Slate-300

ACCENT_GOLD = (251, 191, 36, 255)      # Amber-400
ACCENT_GREEN = (16, 185, 129, 255)     # Emerald-500
ACCENT_CYAN = (56, 189, 248, 255)      # Sky-400
ACCENT_PURPLE = (167, 139, 250, 255)   # Violet-400
ACCENT_ORANGE = (249, 115, 22, 255)    # Orange-500
ACCENT_ROSE = (244, 63, 94, 255)       # Rose-500

TIER_COLORS = {
    "iron": (86, 97, 112),         # Cast Iron Slate (Dark Neutral)
    "bronze": (194, 94, 26),       # Rustic Copper (Warm Orange-Brown)
    "silver": (220, 230, 242),     # Mirror Chrome Silver (Bright Light Neutral)
    "gold": (245, 179, 0),         # Imperial Yellow Gold (Pure Yellow)
    "platinum": (37, 99, 235),     # Royal Sapphire Blue (Deep Blue)
    "diamond": (46, 230, 205),     # Minecraft Aqua (Cyan)
    "ascendant": (34, 197, 94),    # Emerald Leaf Green (Vibrant Green)
    "immortal": (147, 51, 234),    # Void Amethyst (Deep Purple)
    "radiant": (239, 68, 68),      # Solar Crimson (Scorching Scarlet Red)
    "air 1": (217, 70, 239),       # Cosmic Prismatic (Hot Neon Magenta / Indigo)
    "air1": (217, 70, 239),
}

# Regex to strip emojis and non-standard symbols that cause tofu rectangles (▯) in TTF fonts
_EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff]|[\u200d\ufe0e\ufe0f\u200b-\u200f]|[\u2600-\u27bf]",
    flags=re.UNICODE,
)


def _sanitize_text(text: Optional[str]) -> str:
    """Strips emoji glyphs that lack TTF font representation, preventing tofu rectangles."""
    if not text:
        return ""
    cleaned = _EMOJI_RE.sub("", str(text))
    return re.sub(r"\s+", " ", cleaned).strip()


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load the best available modern sans-serif font cross-platform."""
    candidates = []
    if bold:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/Library/Fonts/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "Arial Bold.ttf",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "Arial.ttf",
        ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _format_time(seconds: int) -> str:
    """Format duration compactly: 142h 30m, 45m, or 0m."""
    if seconds <= 0:
        return "0m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    return f"{minutes}m"


def _make_circular_avatar(avatar_img: Image.Image, size: int = 96) -> Image.Image:
    """Crop an avatar image into an anti-aliased circle."""
    avatar_img = avatar_img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    circle_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    circle_img.paste(avatar_img, (0, 0), mask=mask)
    return circle_img


def _draw_badge_dot(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple[int, int, int, int], radius: int = 4) -> None:
    """Draw a vibrant indicator dot with a subtle outer glow."""
    glow_col = (color[0], color[1], color[2], 55)
    draw.ellipse([x - radius - 2, y - radius - 2, x + radius + 2, y + radius + 2], fill=glow_col)
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    pct: float,
    fill_color: tuple[int, int, int, int],
    bg_color: tuple[int, int, int, int] = BAR_BG,
    radius: int = 6,
) -> None:
    """Draw a smooth rounded progress bar."""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=bg_color)
    pct = max(0.0, min(1.0, pct))
    if pct > 0:
        fill_w = max(h, int(w * pct))
        draw.rounded_rectangle([x, y, x + fill_w, y + h], radius=radius, fill=fill_color)


def _export_png(img: Image.Image) -> bytes:
    """Upscale the card so Discord renders a large, crisp profile image."""
    if EXPORT_SCALE != 1:
        img = img.resize(
            (int(img.width * EXPORT_SCALE), int(img.height * EXPORT_SCALE)),
            Image.Resampling.LANCZOS,
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _paste_pixel_icon(img: Image.Image, icon_name: str, x: int, y: int, size: int) -> bool:
    """Safely paste a pixel-art icon (Minecraft items, food sprites, tier shields, etc.) with nearest-neighbor scaling."""
    base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
    clean_name = icon_name.replace("food/", "").replace("tiers/", "").replace("tier_", "")
    candidates = [
        os.path.join(base_dir, f"{icon_name}_128.png"),
        os.path.join(base_dir, f"{icon_name}.png"),
        os.path.join(base_dir, "tiers", f"{clean_name}.png"),
        os.path.join(base_dir, f"tier_{clean_name}.png"),
        os.path.join(base_dir, "food", f"{clean_name}.png"),
        os.path.join(base_dir, f"{clean_name}.png"),
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with Image.open(c) as p_icon:
                    p_icon = p_icon.convert("RGBA").resize((size, size), Image.Resampling.NEAREST)
                    img.paste(p_icon, (x, y), p_icon)
                    return True
            except Exception:
                return False
    return False


# ==============================================================================
# CARD 1: OVERVIEW DASHBOARD (Page 1) — PokeOne-Style Warm Parchment
# ==============================================================================
def render_overview_card_sync(
    display_name: str,
    username: str,
    tier_name: str,
    level: int,
    xp_into: int,
    xp_needed: int,
    total_xp: int,
    coins: int,
    candy: int,
    total_seconds: int,
    today_seconds: int,
    week_seconds: int,
    streak_days: int,
    longest_streak: int,
    sessions_count: int,
    unlocked_achievements: int,
    total_achievements: int,
    rank_position: Optional[int] = None,
    equipped_title: Optional[str] = None,
    equipped_pet: Optional[dict[str, Any]] = None,
    subject_seconds: Optional[dict[str, int]] = None,
    in_session_seconds: Optional[int] = None,
    avatar_bytes: Optional[bytes] = None,
) -> bytes:
    """Synchronously renders the 920x580 PokeOne-style study profile overview PNG."""
    img = Image.new("RGBA", (POKE_W, POKE_H), _P_BG)
    draw = ImageDraw.Draw(img)
    m = _P_MARGIN
    sw = _P_SIDEBAR_W

    # Outer border
    draw.rounded_rectangle([m, m, POKE_W - m, POKE_H - m], radius=20, fill=None, outline=_P_BORDER, width=2)

    # Left sidebar container
    draw.rounded_rectangle([m + 4, m + 4, m + sw, POKE_H - m - 4], radius=18, fill=_P_SIDEBAR)
    draw.line([(m + sw, m + 14), (m + sw, POKE_H - m - 14)], fill=_P_BORDER, width=2)

    # Avatar box (72x72 container)
    av_box = 72
    av_x = m + 4 + (sw - av_box) // 2
    av_y = m + 16
    draw.rounded_rectangle([av_x, av_y, av_x + av_box, av_y + av_box], radius=14, fill=_P_BG, outline=_P_BORDER, width=1)

    clean_disp = _sanitize_text(display_name) or "Aspirant"
    clean_tier = tier_name.replace(" Tier", "").strip().title() if tier_name else "Iron"
    tier_key = clean_tier.lower().replace(" ", "")

    av_pasted = False
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as raw_av:
                circle_av = _make_circular_avatar(raw_av, 60)
                img.paste(circle_av, (av_x + 6, av_y + 6), circle_av)
                av_pasted = True
        except Exception:
            pass
    if not av_pasted:
        if not _paste_pixel_icon(img, f"tier_{tier_key}", av_x + 6, av_y + 6, 60):
            _paste_pixel_icon(img, "chronocoin", av_x + 6, av_y + 6, 60)
    else:
        # Tier Shield Badge on bottom-right of avatar box
        badge_box_x = av_x + av_box - 24
        badge_box_y = av_y + av_box - 24
        draw.rounded_rectangle([badge_box_x - 1, badge_box_y - 1, badge_box_x + 25, badge_box_y + 25], radius=6, fill=_P_SIDEBAR, outline=_P_BORDER, width=1)
        _paste_pixel_icon(img, f"tier_{tier_key}", badge_box_x, badge_box_y, 24)

    # Name and Level/Tier
    ty = av_y + av_box + 12
    draw.text((m + 4 + sw // 2, ty), clean_disp.upper()[:16], font=_get_font(23, bold=True), fill=_P_DARK, anchor="mt")
    ty += 30
    draw.text((m + 4 + sw // 2, ty), f"Level {level} · {clean_tier} Tier", font=_get_font(15, bold=False), fill=_P_MUTED, anchor="mt")
    ty += 30

    # 4 Stat Pills
    stat_pills = [
        ("TOTAL XP", f"{total_xp:,}"),
        ("STREAK", f"{streak_days} DAYS"),
        ("SESSIONS", f"{sessions_count} LOGGED"),
        ("BADGES", f"{unlocked_achievements} / {total_achievements}"),
    ]
    pill_x = m + 18
    pill_w = sw - 28
    for label, val in stat_pills:
        pill_h = 42
        draw.rounded_rectangle([pill_x, ty, pill_x + pill_w, ty + pill_h], radius=10, fill=_P_BG, outline=_P_BORDER, width=1)
        draw.text((pill_x + 14, ty + 10), label, font=_get_font(15, bold=True), fill=_P_MUTED)
        draw.text((pill_x + pill_w - 14, ty + 10), val, font=_get_font(16, bold=True), fill=_P_DARK, anchor="rt")
        ty += pill_h + 8

    # Bottom Wallet Pill
    wy = POKE_H - m - 16 - 44
    draw.rounded_rectangle([pill_x, wy, pill_x + pill_w, wy + 42], radius=10, fill=_P_BG, outline=_P_BORDER, width=1)
    _paste_pixel_icon(img, "chronocoin", pill_x + 10, wy + 9, 24)
    w_text = f"{coins:,} Coins · {candy:,} Candy"
    draw.text((pill_x + 38, wy + 11), w_text, font=_get_font(13, bold=True), fill=_P_GOLD_PILL)

    # Right Panel Header
    cx = _P_CONTENT_X
    hy = m + 10
    draw.text((cx, hy), f"{clean_disp}'s Profile", font=_get_font(32, bold=True), fill=_P_DARK)
    rank_str = f"Rank #{rank_position}" if rank_position else "Unranked"
    sub_title = f"Total Study: {_format_time(total_seconds)} · Server {rank_str}"
    draw.text((cx, hy + 38), sub_title, font=_get_font(15, bold=False), fill=_P_MUTED)
    draw.text((POKE_W - m - 14, hy + 4), "PAGE 1/4", font=_get_font(18, bold=True), fill=_P_MUTED, anchor="rt")
    draw.text((POKE_W - m - 14, hy + 34), "OVERVIEW", font=_get_font(14, bold=False), fill=_P_MUTED, anchor="rt")

    div_y = hy + 64
    draw.line([(cx, div_y), (POKE_W - m - 10, div_y)], fill=_P_BORDER, width=2)

    # Subjects calculation
    subj = subject_seconds or {}
    p_sec = subj.get("physics", 0)
    c_sec = subj.get("chemistry", 0)
    m_sec = subj.get("maths", 0)

    # Level progress
    tot_needed = max(1, xp_needed)
    pct = min(100, int((xp_into / tot_needed) * 100))

    # Active session check
    is_live = in_session_seconds is not None and in_session_seconds > 0

    # Pet companion info
    pet_name = "No Pet"
    pet_sub = "Adopt a study companion with .pets"
    pet_icon = "mystery_box"
    pet_badge = "ADOPT"
    pet_color = _P_MUTED
    if equipped_pet:
        p_spec = equipped_pet.get("species", "companion")
        p_name = equipped_pet.get("name", p_spec.title())
        p_lvl = equipped_pet.get("level", 1)
        p_hap = equipped_pet.get("happiness", 100)
        pet_name = f"Pet: {p_name} (Lv {p_lvl})"
        pet_sub = f"{p_spec.title()} · Happiness: {p_hap}%"
        pet_icon = f"food/{p_spec}"
        pet_badge = "PET ACTIVE"
        pet_color = (180, 100, 200, 255)

    rows = [
        {
            "icon": "chronos_streak",
            "name": "Recent Study Activity",
            "sub": f"Today: {_format_time(today_seconds)} · This Week: {_format_time(week_seconds)}",
            "right": f"Best: {longest_streak}d",
            "right_color": _P_GOLD_PILL,
        },
        {
            "icon": "chronos_xp",
            "name": f"Level {level} Experience",
            "sub": f"{xp_into:,} / {xp_needed:,} XP to next level",
            "right": f"{pct}%",
            "right_color": (56, 140, 200, 255),
        },
        {
            "icon": "food/apple_pie",
            "name": "PCM Subject Grinding",
            "sub": f"Phys: {_format_time(p_sec)} · Chem: {_format_time(c_sec)} · Math: {_format_time(m_sec)}",
            "right": "3 Subjects",
            "right_color": _P_GREEN,
        },
        {
            "icon": "xp_boost",
            "name": "Focus Session Status",
            "sub": f"Elapsed: {_format_time(in_session_seconds)} in study room" if is_live else "Ready to start grinding with .start <subject>",
            "right": "STUDYING" if is_live else "IDLE",
            "right_color": _P_ACCENT if is_live else _P_MUTED,
        },
        {
            "icon": pet_icon,
            "name": pet_name,
            "sub": pet_sub,
            "right": pet_badge,
            "right_color": pet_color,
        },
        {
            "icon": "title_scroll",
            "name": f"Title: {equipped_title or 'Dedicated Grinder'}",
            "sub": "Equipped prestige title displayed on profile",
            "right": "PRESTIGE",
            "right_color": _P_GOLD_PILL,
        },
    ]

    row_h = 68
    row_gap = 6
    ry = div_y + 8

    for i, row in enumerate(rows):
        bg = _P_ROW if i % 2 == 0 else _P_ROW_ALT
        draw.rounded_rectangle([cx, ry, POKE_W - m - 10, ry + row_h], radius=12, fill=bg)

        icon_x = cx + 10
        draw.rounded_rectangle([icon_x, ry + 8, icon_x + 52, ry + 60], radius=10, fill=_P_SIDEBAR, outline=_P_BORDER, width=1)
        if not _paste_pixel_icon(img, row["icon"], icon_x + 4, ry + 12, 44):
            _paste_pixel_icon(img, "mystery_box", icon_x + 4, ry + 12, 44)

        draw.text((cx + 72, ry + 10), row["name"][:36], font=_get_font(23, bold=True), fill=_P_DARK)
        draw.text((cx + 72, ry + 39), row["sub"][:60], font=_get_font(15, bold=False), fill=(110, 115, 125, 255))

        draw.text((POKE_W - m - 20, ry + 20), row["right"], font=_get_font(22, bold=True), fill=row["right_color"], anchor="rt")
        ry += row_h + row_gap

    # Footer
    draw.line([(cx, POKE_H - m - 18), (POKE_W - m - 10, POKE_H - m - 18)], fill=_P_BORDER, width=1)
    draw.text((cx + 6, POKE_H - m - 15), "Chronos · Study smarter, one session at a time", font=_get_font(11, bold=False), fill=_P_MUTED)

    return _poke_export(img)


# Alias for backwards compatibility
render_stats_card_sync = render_overview_card_sync


# ==============================================================================
# CARD: POKEONE LEADERBOARD CARD (Top 6 Grinders & Academic Contenders)
# ==============================================================================
def render_leaderboard_card_sync(
    title: str,
    subtitle: str,
    guild_name: str,
    period_key: str,
    entries: list[dict[str, Any]],
    author_rank: Optional[int] = None,
    author_score: Optional[str] = None,
    author_id: Optional[int] = None,
    subject: Optional[str] = None,
    hero_icon: Optional[str] = None,
    total_members: Optional[int] = None,
    score_unit_icon: str = "chronos_streak",
) -> bytes:
    """Synchronously renders a 920x580 PokeOne-style warm parchment leaderboard card PNG."""
    img = Image.new("RGBA", (POKE_W, POKE_H), _P_BG)
    draw = ImageDraw.Draw(img)
    m = _P_MARGIN
    sw = _P_SIDEBAR_W

    # Outer border
    draw.rounded_rectangle([m, m, POKE_W - m, POKE_H - m], radius=20, fill=None, outline=_P_BORDER, width=2)

    # Sidebar container
    draw.rounded_rectangle([m + 4, m + 4, m + sw, POKE_H - m - 4], radius=18, fill=_P_SIDEBAR)
    draw.line([(m + sw, m + 14), (m + sw, POKE_H - m - 14)], fill=_P_BORDER, width=2)

    # Hero icon container
    icon_box = 72
    icon_x = m + 4 + (sw - icon_box) // 2
    icon_y = m + 16
    draw.rounded_rectangle([icon_x, icon_y, icon_x + icon_box, icon_y + icon_box], radius=14, fill=_P_BG, outline=_P_BORDER, width=1)
    if not hero_icon:
        if subject:
            sub_clean = subject.lower().strip()
            if "phys" in sub_clean:
                h_icon = "physics"
            elif "chem" in sub_clean:
                h_icon = "chemistry"
            elif "math" in sub_clean:
                h_icon = "maths"
            else:
                h_icon = "chronos_streak"
        elif "TRIVIA" in title.upper() or period_key == "trivia":
            h_icon = "trophy"
        else:
            h_icon = "chronos_streak"
    else:
        h_icon = hero_icon

    if score_unit_icon == "chronos_streak":
        if subject:
            sub_clean = subject.lower().strip()
            if "phys" in sub_clean:
                score_unit_icon = "physics"
            elif "chem" in sub_clean:
                score_unit_icon = "chemistry"
            elif "math" in sub_clean:
                score_unit_icon = "maths"
        elif "TRIVIA" in title.upper() or period_key == "trivia":
            score_unit_icon = "trophy"

    _paste_pixel_icon(img, h_icon, icon_x + 6, icon_y + 6, 60)

    # Sidebar Title & Subtitle
    ty = icon_y + icon_box + 12
    draw.text((m + 4 + sw // 2, ty), title.upper()[:16], font=_get_font(23, bold=True), fill=_P_DARK, anchor="mt")
    ty += 30
    draw.text((m + 4 + sw // 2, ty), subtitle[:24], font=_get_font(15, bold=False), fill=_P_MUTED, anchor="mt")
    ty += 30

    # Category / Period Pills
    pill_x = m + 18
    pill_w = sw - 28
    if "TRIVIA" in title.upper() or period_key == "trivia":
        cats = [("JEE AIR TOP 10", True), ("MATHS TOP", False), ("PHYSICS TOP", False), ("CHEMISTRY TOP", False)]
    elif subject:
        cats = [
            ("OVERALL", subject is None),
            ("PHYSICS", subject == "physics"),
            ("CHEMISTRY", subject == "chemistry"),
            ("MATHS", subject == "maths"),
        ]
    else:
        cats = [
            ("TODAY", period_key == "today"),
            ("THIS WEEK", period_key == "week"),
            ("THIS MONTH", period_key == "month"),
            ("ALL TIME", period_key == "alltime"),
        ]

    for label, is_act in cats:
        pill_h = 42
        if is_act:
            draw.rounded_rectangle([pill_x, ty, pill_x + pill_w, ty + pill_h], radius=10, fill=_P_ACCENT)
            draw.text((pill_x + pill_w // 2, ty + 11), label, font=_get_font(16, bold=True), fill=(255, 255, 255, 255), anchor="mt")
        else:
            draw.rounded_rectangle([pill_x, ty, pill_x + pill_w, ty + pill_h], radius=10, fill=_P_BG, outline=_P_BORDER, width=1)
            draw.text((pill_x + pill_w // 2, ty + 11), label, font=_get_font(16, bold=True), fill=_P_DARK, anchor="mt")
        ty += pill_h + 8

    # Author Standing Pill at bottom
    wy = POKE_H - m - 16 - 44
    draw.rounded_rectangle([pill_x, wy, pill_x + pill_w, wy + 42], radius=10, fill=_P_BG, outline=_P_BORDER, width=1)
    _paste_pixel_icon(img, score_unit_icon, pill_x + 10, wy + 9, 24)
    if author_rank:
        auth_txt = f"Your Rank: #{author_rank}" + (f" ({author_score})" if author_score else "")
    else:
        auth_txt = "Rank outside top list"
    draw.text((pill_x + 38, wy + 11), auth_txt[:26], font=_get_font(13, bold=True), fill=_P_GOLD_PILL)

    # Right Panel Header
    cx = _P_CONTENT_X
    hy = m + 10
    g_title = f"{guild_name[:18]} Leaderboard" if guild_name else "Server Leaderboard"
    draw.text((cx, hy), g_title, font=_get_font(32, bold=True), fill=_P_DARK)
    sub_title = f"Top Academic Contenders · {subtitle}"
    draw.text((cx, hy + 38), sub_title[:45], font=_get_font(15, bold=False), fill=_P_MUTED)
    draw.text((POKE_W - m - 14, hy + 4), "TOP 6", font=_get_font(18, bold=True), fill=_P_MUTED, anchor="rt")
    tot_txt = f"{total_members} Members" if total_members else "Live Synced"
    draw.text((POKE_W - m - 14, hy + 34), tot_txt, font=_get_font(14, bold=False), fill=_P_MUTED, anchor="rt")

    div_y = hy + 64
    draw.line([(cx, div_y), (POKE_W - m - 10, div_y)], fill=_P_BORDER, width=2)

    # Rows (6 rows)
    row_h = 68
    row_gap = 6
    ry = div_y + 8

    rank_colors = {
        1: (251, 191, 36, 255),   # Gold
        2: (156, 163, 175, 255),  # Silver
        3: (205, 127, 50, 255),   # Bronze
    }

    for i in range(6):
        if i < len(entries):
            row = entries[i]
            is_you = row.get("is_author", False) or (author_id and row.get("user_id") == author_id)
            bg = (248, 238, 215, 255) if is_you else (_P_ROW if i % 2 == 0 else _P_ROW_ALT)
            border = _P_ACCENT if is_you else None

            draw.rounded_rectangle([cx, ry, POKE_W - m - 10, ry + row_h], radius=12, fill=bg, outline=border, width=2 if is_you else 0)

            # Rank badge
            rn = row.get("rank", i + 1)
            rb_w = 46
            rb_h = 52
            rx = cx + 8
            ry_b = ry + 8
            r_color = rank_colors.get(rn, (120, 125, 135, 255))
            draw.rounded_rectangle([rx, ry_b, rx + rb_w, ry_b + rb_h], radius=10, fill=_P_SIDEBAR, outline=r_color, width=2 if rn <= 3 else 1)
            if rn in (1, 2, 3):
                # Authentic pixel-art medal for podium ranks
                _paste_pixel_icon(img, f"medal_{rn}", rx + (rb_w - 38) // 2, ry_b + (rb_h - 38) // 2, 38)
            else:
                rank_str = f"#{rn}"
                draw.text((rx + rb_w // 2, ry_b + 12), rank_str, font=_get_font(20, bold=True), fill=_P_DARK, anchor="mt")

            # Detect tier from subtitle for badge/fallback
            sub_str = str(row.get("sub", "")).lower()
            tier_icon = None
            for t_name in ["air1", "air 1", "radiant", "immortal", "ascendant", "diamond", "platinum", "gold", "silver", "bronze", "iron"]:
                if t_name in sub_str:
                    tier_icon = f"tier_{t_name.replace(' ', '')}"
                    break

            # Avatar or icon
            av_x = rx + rb_w + 10
            draw.rounded_rectangle([av_x, ry + 8, av_x + 52, ry + 60], radius=10, fill=_P_SIDEBAR, outline=_P_BORDER, width=1)
            av_pasted = False
            if row.get("avatar_bytes"):
                try:
                    with Image.open(io.BytesIO(row["avatar_bytes"])) as raw_av:
                        c_av = _make_circular_avatar(raw_av, 44)
                        img.paste(c_av, (av_x + 4, ry + 12), c_av)
                        av_pasted = True
                except Exception:
                    pass
            if av_pasted:
                # Overlay mini tier shield badge on avatar corner
                if tier_icon:
                    bx = av_x + 32
                    by = ry + 38
                    draw.rounded_rectangle([bx, by, bx + 20, by + 20], radius=5, fill=_P_BG, outline=_P_BORDER, width=1)
                    _paste_pixel_icon(img, tier_icon, bx + 1, by + 1, 18)
            else:
                row_icon = row.get("icon") or tier_icon or "chronocoin"
                _paste_pixel_icon(img, row_icon, av_x + 6, ry + 14, 40)

            # Name & Subtitle
            name_x = av_x + 64
            name_str = _sanitize_text(str(row.get("name", "User")))
            if is_you and "(You)" not in name_str:
                name_str += " (You)"
            if len(name_str) > 24:
                name_str = name_str[:22] + ".."
            draw.text((name_x, ry + 10), name_str, font=_get_font(23, bold=True), fill=_P_ACCENT if is_you else _P_DARK)

            sub_txt = _sanitize_text(str(row.get("sub", "")))
            if len(sub_txt) > 42:
                sub_txt = sub_txt[:40] + ".."
            draw.text((name_x, ry + 40), sub_txt, font=_get_font(15, bold=False), fill=(110, 115, 125, 255))

            # Right side: Score & Icon
            sc_font = _get_font(24, bold=True)
            sc_val = str(row.get("score", ""))
            draw.text((POKE_W - m - 46, ry + 20), sc_val, font=sc_font, fill=_P_GOLD_PILL, anchor="rt")
            _paste_pixel_icon(img, score_unit_icon, POKE_W - m - 40, ry + 22, 24)
        else:
            # Empty slot
            draw.rounded_rectangle([cx, ry, POKE_W - m - 10, ry + row_h], radius=12, fill=_P_ROW_ALT)
            draw.text((cx + 220, ry + 24), "[ EMPTY LEADERBOARD SLOT ]", font=_get_font(16, bold=True), fill=(160, 165, 175, 255))

        ry += row_h + row_gap

    # Footer
    draw.line([(cx, POKE_H - m - 18), (POKE_W - m - 10, POKE_H - m - 18)], fill=_P_BORDER, width=1)
    draw.text((cx + 6, POKE_H - m - 15), "Chronos · Study smarter, one session at a time", font=_get_font(11, bold=False), fill=_P_MUTED)

    return _poke_export(img)


# ==============================================================================
# CARD 2: WEEKLY PERFORMANCE & 7-DAY BAR CHART (Page 2)
# ==============================================================================
def render_weekly_card_sync(
    display_name: str,
    username: str,
    tier_name: str,
    weekly_breakdown: dict[str, Any],
    avatar_bytes: Optional[bytes] = None,
) -> bytes:
    """Synchronously renders the high-res 1200x680 weekly activity bar chart card PNG."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    clean_tier = tier_name.split()[-1].lower() if tier_name else "iron"
    tier_rgb = TIER_COLORS.get(clean_tier, (148, 163, 184))
    tier_rgba = (*tier_rgb, 255)

    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, CARD_HEIGHT - 20], radius=20, fill=None, outline=(30, 41, 59, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=ACCENT_CYAN, width=4)

    # Header
    av_size = 64
    av_x, av_y = 50, 44
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as raw_av:
                circle_av = _make_circular_avatar(raw_av, av_size)
                img.paste(circle_av, (av_x, av_y), circle_av)
                draw.ellipse([av_x - 2, av_y - 2, av_x + av_size + 2, av_y + av_size + 2], outline=tier_rgba, width=2)
        except Exception:
            draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=2)
    else:
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=2)

    f_title = _get_font(26, bold=True)
    f_sub = _get_font(14, bold=False)
    draw.text((av_x + av_size + 20, av_y + 4), "WEEKLY PERFORMANCE & STUDY ACTIVITY", font=f_title, fill=TEXT_WHITE)
    clean_disp = _sanitize_text(display_name) or "Candidate"
    draw.text((av_x + av_size + 20, av_y + 36), f"7-Day Focus Distribution · {clean_disp} · India Standard Time (IST)", font=f_sub, fill=TEXT_MUTED)

    # Page indicator pill
    draw.rounded_rectangle([CARD_WIDTH - 220, av_y + 12, CARD_WIDTH - 50, av_y + 44], radius=8, fill=CARD_BG, outline=ACCENT_CYAN, width=1)
    draw.text((CARD_WIDTH - 202, av_y + 19), "PAGE 2/4 · ACTIVITY", font=_get_font(12, bold=True), fill=ACCENT_CYAN)

    # 7-Day Vertical Bar Chart Area
    chart_x, chart_y = 50, 135
    chart_w = 720
    chart_h = 485
    draw.rounded_rectangle([chart_x, chart_y, chart_x + chart_w, chart_y + chart_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, chart_x + 24, chart_y + 24, ACCENT_CYAN, radius=4)
    draw.text((chart_x + 36, chart_y + 17), "DAILY STUDY HOURS (THIS WEEK)", font=_get_font(13, bold=True), fill=ACCENT_CYAN)

    days_data = weekly_breakdown.get("days", [])
    max_seconds = max([d["seconds"] for d in days_data] + [14400])  # scale to at least 4 hours
    plot_bottom = chart_y + chart_h - 75
    plot_top = chart_y + 70
    plot_height = plot_bottom - plot_top

    # Horizontal grid lines
    f_grid = _get_font(11, bold=False)
    for step_h in (1, 2, 3, 4, 6):
        step_sec = step_h * 3600
        if step_sec <= max_seconds * 1.15:
            grid_y = int(plot_bottom - (step_sec / max_seconds) * plot_height)
            draw.line([(chart_x + 30, grid_y), (chart_x + chart_w - 30, grid_y)], fill=GRID_COLOR, width=1)
            draw.text((chart_x + 32, grid_y - 14), f"{step_h}h", font=f_grid, fill=(100, 116, 139, 255))

    # Draw 7 Columns
    col_w = 56
    spacing = (chart_w - 80 - (col_w * 7)) // 6
    f_bar_lbl = _get_font(12, bold=True)
    f_day_lbl = _get_font(13, bold=True)

    for i, d in enumerate(days_data[:7]):
        bx = chart_x + 40 + i * (col_w + spacing)
        sec = d["seconds"]
        is_today = d.get("is_today", False)
        bh = max(6, int((sec / max_seconds) * plot_height)) if sec > 0 else 4
        by = plot_bottom - bh

        # Bar column fill
        if sec > 0:
            bar_color = ACCENT_GOLD if is_today else ACCENT_CYAN
            draw.rounded_rectangle([bx, by, bx + col_w, plot_bottom], radius=6, fill=bar_color)
            # Duration label above bar
            time_txt = _format_time(sec)
            draw.text((bx + (col_w // 2) - (len(time_txt) * 3), by - 18), time_txt, font=f_bar_lbl, fill=TEXT_WHITE)
        else:
            draw.rounded_rectangle([bx, plot_bottom - 6, bx + col_w, plot_bottom], radius=3, fill=(45, 55, 72, 255))
            draw.text((bx + (col_w // 2) - 8, plot_bottom - 20), "0m", font=_get_font(10, bold=False), fill=TEXT_MUTED)

        # Day label below baseline
        day_str = d["day_name"]
        day_color = ACCENT_GOLD if is_today else TEXT_SUB
        draw.text((bx + (col_w // 2) - 14, plot_bottom + 12), day_str, font=f_day_lbl, fill=day_color)
        if is_today:
            draw.rounded_rectangle([bx + 6, plot_bottom + 34, bx + col_w - 6, plot_bottom + 48], radius=4, fill=(113, 63, 18, 200))
            draw.text((bx + 11, plot_bottom + 35), "TODAY", font=_get_font(9, bold=True), fill=ACCENT_GOLD)

    # Right Side Analytics Panels
    right_x = chart_x + chart_w + 25
    right_w = CARD_WIDTH - right_x - 50

    p_h = 108
    # Panel 1: Weekly Total
    p1_y = chart_y
    draw.rounded_rectangle([right_x, p1_y, right_x + right_w, p1_y + p_h], radius=14, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, right_x + 20, p1_y + 22, ACCENT_CYAN, radius=3)
    draw.text((right_x + 30, p1_y + 16), "WEEKLY TOTAL", font=_get_font(12, bold=True), fill=ACCENT_CYAN)
    tot_sec = weekly_breakdown.get("total_week_seconds", 0)
    draw.text((right_x + 18, p1_y + 40), _format_time(tot_sec), font=_get_font(30, bold=True), fill=TEXT_WHITE)
    draw.text((right_x + 18, p1_y + 82), "This week's focus time logged", font=_get_font(12, bold=False), fill=TEXT_MUTED)

    # Panel 2: Daily Average
    p2_y = p1_y + p_h + 18
    draw.rounded_rectangle([right_x, p2_y, right_x + right_w, p2_y + p_h], radius=14, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, right_x + 20, p2_y + 22, ACCENT_PURPLE, radius=3)
    draw.text((right_x + 30, p2_y + 16), "DAILY AVERAGE", font=_get_font(12, bold=True), fill=ACCENT_PURPLE)
    avg_sec = weekly_breakdown.get("daily_avg_seconds", 0)
    draw.text((right_x + 18, p2_y + 40), f"{_format_time(avg_sec)} / day", font=_get_font(30, bold=True), fill=TEXT_WHITE)
    act_days = weekly_breakdown.get("active_days_count", 0)
    draw.text((right_x + 18, p2_y + 82), f"Across {act_days}/7 active study days", font=_get_font(12, bold=False), fill=TEXT_MUTED)

    # Panel 3: Peak Study Day
    p3_y = p2_y + p_h + 18
    draw.rounded_rectangle([right_x, p3_y, right_x + right_w, p3_y + p_h], radius=14, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, right_x + 20, p3_y + 22, ACCENT_GOLD, radius=3)
    draw.text((right_x + 30, p3_y + 16), "PEAK STUDY DAY", font=_get_font(12, bold=True), fill=ACCENT_GOLD)
    peak_name = weekly_breakdown.get("peak_day_name", "None")
    peak_sec = weekly_breakdown.get("peak_day_seconds", 0)
    draw.text((right_x + 18, p3_y + 40), f"{peak_name} ({_format_time(peak_sec)})", font=_get_font(26, bold=True), fill=ACCENT_GOLD)
    draw.text((right_x + 18, p3_y + 82), "Personal record day for the week", font=_get_font(12, bold=False), fill=TEXT_MUTED)

    # Panel 4: Consistency Rating
    p4_y = p3_y + p_h + 18
    draw.rounded_rectangle([right_x, p4_y, right_x + right_w, p4_y + p_h], radius=14, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, right_x + 20, p4_y + 22, ACCENT_GREEN, radius=3)
    draw.text((right_x + 30, p4_y + 16), "STUDY VELOCITY", font=_get_font(12, bold=True), fill=ACCENT_GREEN)
    consistency_pct = (act_days / 7)
    rating_lbl = "High Velocity" if consistency_pct >= 0.7 else "Steady Grind" if consistency_pct >= 0.4 else "Building Pace"
    draw.text((right_x + 18, p4_y + 40), rating_lbl, font=_get_font(24, bold=True), fill=TEXT_WHITE)
    _draw_progress_bar(draw, right_x + 18, p4_y + 76, right_w - 36, 6, consistency_pct, ACCENT_GREEN, radius=3)
    draw.text((right_x + 18, p4_y + 88), f"{int(consistency_pct * 100)}% weekly consistency score", font=_get_font(11, bold=False), fill=TEXT_MUTED)

    # Footer
    f_foot = _get_font(12, bold=False)
    draw.text((50, 642), "CHRONOS STUDY OS · IST TIMEZONE", font=f_foot, fill=(71, 85, 105, 255))
    draw.text((CARD_WIDTH - 280, 642), "WEEKLY ACTIVITY LOG · PAGE 2/4", font=f_foot, fill=(71, 85, 105, 255))

    return _export_png(img)


# ==============================================================================
# CARD 3: SUBJECT BREAKDOWN & TIME DISTRIBUTION (Page 3)
# ==============================================================================
def render_subjects_card_sync(
    display_name: str,
    username: str,
    tier_name: str,
    subject_details: dict[str, dict[str, Any]],
    avatar_bytes: Optional[bytes] = None,
) -> bytes:
    """Synchronously renders the high-res 1200x680 subject breakdown & PCM distribution card PNG."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    clean_tier = tier_name.split()[-1].lower() if tier_name else "iron"
    tier_rgb = TIER_COLORS.get(clean_tier, (148, 163, 184))
    tier_rgba = (*tier_rgb, 255)

    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, CARD_HEIGHT - 20], radius=20, fill=None, outline=(30, 41, 59, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=ACCENT_PURPLE, width=4)

    # Header
    av_size = 64
    av_x, av_y = 50, 44
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as raw_av:
                circle_av = _make_circular_avatar(raw_av, av_size)
                img.paste(circle_av, (av_x, av_y), circle_av)
                draw.ellipse([av_x - 2, av_y - 2, av_x + av_size + 2, av_y + av_size + 2], outline=tier_rgba, width=2)
        except Exception:
            draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=2)
    else:
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=2)

    f_title = _get_font(26, bold=True)
    f_sub = _get_font(14, bold=False)
    draw.text((av_x + av_size + 20, av_y + 4), "SUBJECT MASTERY & TIME DISTRIBUTION", font=f_title, fill=TEXT_WHITE)
    clean_disp = _sanitize_text(display_name) or "Candidate"
    draw.text((av_x + av_size + 20, av_y + 36), f"PCM Split & JEE Focus Breakdown · {clean_disp}", font=f_sub, fill=TEXT_MUTED)

    draw.rounded_rectangle([CARD_WIDTH - 220, av_y + 12, CARD_WIDTH - 50, av_y + 44], radius=8, fill=CARD_BG, outline=ACCENT_PURPLE, width=1)
    draw.text((CARD_WIDTH - 202, av_y + 19), "PAGE 3/4 · SUBJECTS", font=_get_font(12, bold=True), fill=ACCENT_PURPLE)

    # Calculate Totals
    phy_sec = subject_details.get("physics", {}).get("total_seconds", 0)
    chem_sec = subject_details.get("chemistry", {}).get("total_seconds", 0)
    mat_sec = subject_details.get("maths", {}).get("total_seconds", 0)
    gen_sec = subject_details.get("general", {}).get("total_seconds", 0)
    total_sec = max(1, phy_sec + chem_sec + mat_sec + gen_sec)

    phy_pct = phy_sec / total_sec
    chem_pct = chem_sec / total_sec
    mat_pct = mat_sec / total_sec
    gen_pct = gen_sec / total_sec

    # Top Section: Horizontal Segmented Bar
    bar_box_x, bar_box_y = 50, 135
    bar_box_w, bar_box_h = CARD_WIDTH - 100, 105
    draw.rounded_rectangle([bar_box_x, bar_box_y, bar_box_x + bar_box_w, bar_box_y + bar_box_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, bar_box_x + 24, bar_box_y + 24, ACCENT_PURPLE, radius=4)
    draw.text((bar_box_x + 36, bar_box_y + 17), "OVERALL PCM TIME DISTRIBUTION", font=_get_font(13, bold=True), fill=ACCENT_PURPLE)

    # Segmented Bar
    seg_x, seg_y = bar_box_x + 24, bar_box_y + 48
    seg_w, seg_h = bar_box_w - 48, 22
    draw.rounded_rectangle([seg_x, seg_y, seg_x + seg_w, seg_y + seg_h], radius=8, fill=BAR_BG)

    # Segments
    curr_x = seg_x
    if phy_pct > 0:
        w_p = int(seg_w * phy_pct)
        draw.rounded_rectangle([curr_x, seg_y, curr_x + w_p, seg_y + seg_h], radius=8, fill=ACCENT_CYAN)
        curr_x += w_p
    if chem_pct > 0:
        w_c = int(seg_w * chem_pct)
        draw.rounded_rectangle([curr_x, seg_y, curr_x + w_c, seg_y + seg_h], radius=8, fill=ACCENT_GREEN)
        curr_x += w_c
    if mat_pct > 0:
        w_m = int(seg_w * mat_pct)
        draw.rounded_rectangle([curr_x, seg_y, curr_x + w_m, seg_y + seg_h], radius=8, fill=ACCENT_PURPLE)
        curr_x += w_m
    if gen_pct > 0:
        w_g = seg_x + seg_w - curr_x
        if w_g > 0:
            draw.rounded_rectangle([curr_x, seg_y, curr_x + w_g, seg_y + seg_h], radius=8, fill=ACCENT_GOLD)

    # Legend under bar
    f_leg = _get_font(12, bold=True)
    leg_y = bar_box_y + 78
    draw.text((seg_x, leg_y), f"Physics: {int(phy_pct * 100)}%", font=f_leg, fill=ACCENT_CYAN)
    draw.text((seg_x + 260, leg_y), f"Chemistry: {int(chem_pct * 100)}%", font=f_leg, fill=ACCENT_GREEN)
    draw.text((seg_x + 530, leg_y), f"Mathematics: {int(mat_pct * 100)}%", font=f_leg, fill=ACCENT_PURPLE)
    draw.text((seg_x + 820, leg_y), f"General: {int(gen_pct * 100)}%", font=f_leg, fill=ACCENT_GOLD)

    # 3 Detailed PCM Cards
    pcm_w = (CARD_WIDTH - 100 - 56) // 3
    pcm_h = 245
    pcm_y = bar_box_y + bar_box_h + 20

    pcm_items = [
        ("PHYSICS", ACCENT_CYAN, phy_sec, phy_pct, subject_details.get("physics", {}), "physics"),
        ("CHEMISTRY", ACCENT_GREEN, chem_sec, chem_pct, subject_details.get("chemistry", {}), "chemistry"),
        ("MATHEMATICS", ACCENT_PURPLE, mat_sec, mat_pct, subject_details.get("maths", {}), "maths"),
    ]

    for idx, (s_name, s_color, s_sec, s_pct, s_data, s_icon) in enumerate(pcm_items):
        px = 50 + idx * (pcm_w + 28)
        draw.rounded_rectangle([px, pcm_y, px + pcm_w, pcm_y + pcm_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
        draw.line([(px + 20, pcm_y), (px + pcm_w - 20, pcm_y)], fill=s_color, width=3)
        _draw_badge_dot(draw, px + 24, pcm_y + 24, s_color, radius=3)
        draw.text((px + 36, pcm_y + 18), s_name, font=_get_font(13, bold=True), fill=s_color)
        _paste_pixel_icon(img, s_icon, px + pcm_w - 44, pcm_y + 12, 32)

        draw.text((px + 22, pcm_y + 48), _format_time(s_sec), font=_get_font(34, bold=True), fill=TEXT_WHITE)
        _draw_progress_bar(draw, px + 22, pcm_y + 98, pcm_w - 44, 8, s_pct, s_color, radius=4)

        sess_count = s_data.get("session_count", 0)
        draw.text((px + 22, pcm_y + 120), f"Sessions: {sess_count} Logged", font=_get_font(13, bold=False), fill=TEXT_SUB)
        avg_s = s_data.get("avg_seconds", 0)
        draw.text((px + 22, pcm_y + 148), f"Avg Session: {avg_s // 60}m", font=_get_font(13, bold=False), fill=TEXT_MUTED)
        draw.text((px + 22, pcm_y + 176), f"Syllabus Share: {int(s_pct * 100)}%", font=_get_font(13, bold=False), fill=s_color)

    # Bottom JEE Preparation Balance Analysis
    bot_y = pcm_y + pcm_h + 20
    bot_h = 105
    draw.rounded_rectangle([50, bot_y, CARD_WIDTH - 50, bot_y + bot_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, 74, bot_y + 24, ACCENT_GOLD, radius=4)
    draw.text((86, bot_y + 17), "JEE SYLLABUS BALANCE EVALUATION", font=_get_font(13, bold=True), fill=ACCENT_GOLD)

    # Determine balance evaluation
    shares = [phy_pct, chem_pct, mat_pct]
    max_share = max(shares)
    min_share = min(shares)
    if (max_share - min_share) <= 0.18 and min_share > 0.15:
        balance_txt = "Well-Balanced Preparation: Your study time is evenly distributed across Physics, Chemistry, and Mathematics."
        advice_txt = "Keep up this consistent equilibrium to maximize overall JEE All India Rank (AIR)."
        b_color = ACCENT_GREEN
    else:
        top_name = "Physics" if max_share == phy_pct else "Chemistry" if max_share == chem_pct else "Mathematics"
        low_name = "Physics" if min_share == phy_pct else "Chemistry" if min_share == chem_pct else "Mathematics"
        balance_txt = f"{top_name} Specialist ({int(max_share * 100)}% share): Prioritizing strengths while {low_name} ({int(min_share * 100)}%) has less focus."
        advice_txt = f"Tip: Dedicate at least two upcoming sessions to {low_name} to maintain tripartite cutoff stability."
        b_color = ACCENT_ORANGE

    draw.text((74, bot_y + 44), balance_txt, font=_get_font(14, bold=True), fill=b_color)
    draw.text((74, bot_y + 70), advice_txt, font=_get_font(13, bold=False), fill=TEXT_MUTED)

    # Footer
    f_foot = _get_font(12, bold=False)
    draw.text((50, 642), "CHRONOS STUDY OS · IST TIMEZONE", font=f_foot, fill=(71, 85, 105, 255))
    draw.text((CARD_WIDTH - 280, 642), "PCM SYLLABUS SPLIT · PAGE 3/4", font=f_foot, fill=(71, 85, 105, 255))

    return _export_png(img)


# ==============================================================================
# CARD 4: JEE TRIVIA MASTERY & AIR RANK SCORECARD (Page 4)
# ==============================================================================
def render_trivia_card_sync(
    display_name: str,
    username: str,
    tier_name: str,
    trivia_stats: dict[str, Any],
    rank_info: tuple[int, int],
    tier_info: dict[str, Any],
    avatar_bytes: Optional[bytes] = None,
) -> bytes:
    """Synchronously renders the high-res 1200x680 JEE trivia & AIR rank scorecard PNG."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    clean_tier = tier_name.split()[-1].lower() if tier_name else "iron"
    tier_rgb = TIER_COLORS.get(clean_tier, (148, 163, 184))
    tier_rgba = (*tier_rgb, 255)

    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, CARD_HEIGHT - 20], radius=20, fill=None, outline=(30, 41, 59, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=ACCENT_GOLD, width=4)

    # Header
    av_size = 64
    av_x, av_y = 50, 44
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as raw_av:
                circle_av = _make_circular_avatar(raw_av, av_size)
                img.paste(circle_av, (av_x, av_y), circle_av)
                draw.ellipse([av_x - 2, av_y - 2, av_x + av_size + 2, av_y + av_size + 2], outline=tier_rgba, width=2)
        except Exception:
            draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=2)
    else:
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=2)

    f_title = _get_font(26, bold=True)
    f_sub = _get_font(14, bold=False)
    draw.text((av_x + av_size + 20, av_y + 4), "JEE TRIVIA & ACADEMIC SCORECARD", font=f_title, fill=TEXT_WHITE)
    clean_disp = _sanitize_text(display_name) or "Candidate"
    draw.text((av_x + av_size + 20, av_y + 36), f"Competitive Candidate Evaluation · {clean_disp} · JEE Theory Mastery", font=f_sub, fill=TEXT_MUTED)

    draw.rounded_rectangle([CARD_WIDTH - 220, av_y + 12, CARD_WIDTH - 50, av_y + 44], radius=8, fill=CARD_BG, outline=ACCENT_GOLD, width=1)
    draw.text((CARD_WIDTH - 202, av_y + 19), "PAGE 4/4 · TRIVIA", font=_get_font(12, bold=True), fill=ACCENT_GOLD)

    # Left Side: AIR Ladder & Rank Showcase Box
    showcase_x, showcase_y = 50, 135
    showcase_w = 460
    showcase_h = 485
    draw.rounded_rectangle([showcase_x, showcase_y, showcase_x + showcase_w, showcase_y + showcase_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, showcase_x + 24, showcase_y + 24, ACCENT_GOLD, radius=4)
    draw.text((showcase_x + 36, showcase_y + 17), "ALL INDIA RANK STANDING", font=_get_font(13, bold=True), fill=ACCENT_GOLD)

    # Rank Badge & Tier
    rank_pos, total_cand = rank_info
    r_str = f"SERVER RANK #{rank_pos} OF {total_cand}" if rank_pos > 0 else "UNRANKED"
    draw.rounded_rectangle([showcase_x + 24, showcase_y + 50, showcase_x + showcase_w - 24, showcase_y + 86], radius=8, fill=(30, 41, 59, 200))
    draw.text((showcase_x + 36, showcase_y + 58), r_str, font=_get_font(13, bold=True), fill=ACCENT_GOLD)

    tier_title = _sanitize_text(tier_info.get("title", "Aspirant"))
    draw.text((showcase_x + 24, showcase_y + 105), tier_title, font=_get_font(30, bold=True), fill=TEXT_WHITE)

    marks = trivia_stats.get("total_marks", 0)
    marks_str = f"{marks:+,} Marks"
    draw.text((showcase_x + 24, showcase_y + 155), marks_str, font=_get_font(44, bold=True), fill=ACCENT_GOLD)

    # Climb progress bar to next tier
    next_m = tier_info.get("next_marks")
    draw.text((showcase_x + 24, showcase_y + 230), "LADDER CLIMB TO NEXT TIER", font=_get_font(12, bold=True), fill=TEXT_MUTED)
    if next_m is not None:
        curr_min = tier_info.get("min_marks", tier_info.get("cur_min", 0))
        needed = next_m - curr_min
        into = max(0, marks - curr_min)
        climb_pct = min(1.0, max(0.0, into / needed)) if needed > 0 else 1.0
        _draw_progress_bar(draw, showcase_x + 24, showcase_y + 252, showcase_w - 48, 10, climb_pct, ACCENT_GOLD, radius=5)
        climb_lbl = f"{into}/{needed} marks to {tier_info.get('next_title', 'Next Tier')} ({int(climb_pct * 100)}%)"
        draw.text((showcase_x + 24, showcase_y + 272), climb_lbl, font=_get_font(12, bold=False), fill=TEXT_SUB)
    else:
        _draw_progress_bar(draw, showcase_x + 24, showcase_y + 252, showcase_w - 48, 10, 1.0, ACCENT_GOLD, radius=5)
        draw.text((showcase_x + 24, showcase_y + 272), "MAX TIER ACHIEVED · SUPREME ASPIRANT", font=_get_font(12, bold=False), fill=ACCENT_GOLD)

    # Evaluative summary
    draw.rounded_rectangle([showcase_x + 24, showcase_y + 320, showcase_x + showcase_w - 24, showcase_y + showcase_h - 24], radius=12, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    draw.text((showcase_x + 40, showcase_y + 338), "COMPETITIVE EVALUATION", font=_get_font(11, bold=True), fill=ACCENT_CYAN)
    draw.text((showcase_x + 40, showcase_y + 364), "• 100% Verified Theory Solves", font=_get_font(13, bold=False), fill=TEXT_WHITE)
    draw.text((showcase_x + 40, showcase_y + 392), "• Negative Marking Penalty Active", font=_get_font(13, bold=False), fill=TEXT_WHITE)
    draw.text((showcase_x + 40, showcase_y + 420), "• Full JEE Advanced Syllabus Coverage", font=_get_font(13, bold=False), fill=TEXT_MUTED)

    # Right Side: 4 Metric Cards
    right_x = showcase_x + showcase_w + 25
    right_w = CARD_WIDTH - right_x - 50
    card_half_w = (right_w - 20) // 2
    card_half_h = (showcase_h - 20) // 2

    att = trivia_stats.get("questions_attempted", 0)
    cor = trivia_stats.get("questions_correct", 0)
    acc = (cor / att * 100) if att > 0 else 0.0

    # Metric 1: Solve Accuracy
    m1_x, m1_y = right_x, showcase_y
    draw.rounded_rectangle([m1_x, m1_y, m1_x + card_half_w, m1_y + card_half_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, m1_x + 20, m1_y + 22, ACCENT_GREEN, radius=3)
    draw.text((m1_x + 30, m1_y + 16), "SOLVE ACCURACY", font=_get_font(12, bold=True), fill=ACCENT_GREEN)
    draw.text((m1_x + 18, m1_y + 44), f"{acc:.1f}%", font=_get_font(38, bold=True), fill=TEXT_WHITE)
    _draw_progress_bar(draw, m1_x + 18, m1_y + 98, card_half_w - 36, 8, acc / 100.0, ACCENT_GREEN, radius=4)
    draw.text((m1_x + 18, m1_y + 120), f"{cor} Solved / {att} Attempted", font=_get_font(13, bold=False), fill=TEXT_SUB)
    draw.text((m1_x + 18, m1_y + 148), "Calculated across PCM theory", font=_get_font(12, bold=False), fill=TEXT_MUTED)

    # Metric 2: Streak Multiplier
    m2_x, m2_y = right_x + card_half_w + 20, showcase_y
    draw.rounded_rectangle([m2_x, m2_y, m2_x + card_half_w, m2_y + card_half_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, m2_x + 20, m2_y + 22, ACCENT_ORANGE, radius=3)
    draw.text((m2_x + 30, m2_y + 16), "CURRENT STREAK", font=_get_font(12, bold=True), fill=ACCENT_ORANGE)
    cur_strk = trivia_stats.get("current_streak", 0)
    draw.text((m2_x + 18, m2_y + 44), f"{cur_strk} Streak", font=_get_font(38, bold=True), fill=TEXT_WHITE)
    _paste_pixel_icon(img, "chronos_streak", m2_x + card_half_w - 55, m2_y + 46, 34)
    best_strk = trivia_stats.get("best_streak", 0)
    draw.text((m2_x + 18, m2_y + 120), f"Personal Best: {best_strk} in a row", font=_get_font(13, bold=False), fill=TEXT_SUB)
    draw.text((m2_x + 18, m2_y + 148), "Hot streak reward active", font=_get_font(12, bold=False), fill=TEXT_MUTED)

    # Metric 3: Rewards Earned
    m3_x, m3_y = right_x, showcase_y + card_half_h + 20
    draw.rounded_rectangle([m3_x, m3_y, m3_x + card_half_w, m3_y + card_half_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, m3_x + 20, m3_y + 22, ACCENT_GOLD, radius=3)
    draw.text((m3_x + 30, m3_y + 16), "TRIVIA REWARDS", font=_get_font(12, bold=True), fill=ACCENT_GOLD)
    c_won = trivia_stats.get("total_coins_won", 0)
    draw.text((m3_x + 18, m3_y + 44), f"+{c_won:,}", font=_get_font(38, bold=True), fill=ACCENT_GOLD)
    _paste_pixel_icon(img, "chronocoin", m3_x + card_half_w - 55, m3_y + 46, 36)
    draw.text((m3_x + 18, m3_y + 120), "Chronocoins earned from theory", font=_get_font(13, bold=False), fill=TEXT_SUB)
    draw.text((m3_x + 18, m3_y + 148), "Redeemable in Chronos shop", font=_get_font(12, bold=False), fill=TEXT_MUTED)

    # Metric 4: Theory Focus
    m4_x, m4_y = right_x + card_half_w + 20, showcase_y + card_half_h + 20
    draw.rounded_rectangle([m4_x, m4_y, m4_x + card_half_w, m4_y + card_half_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, m4_x + 20, m4_y + 22, ACCENT_PURPLE, radius=3)
    draw.text((m4_x + 30, m4_y + 16), "EXAM STATUS", font=_get_font(12, bold=True), fill=ACCENT_PURPLE)
    draw.text((m4_x + 18, m4_y + 44), "Active Grinder", font=_get_font(28, bold=True), fill=TEXT_WHITE)
    draw.text((m4_x + 18, m4_y + 105), "• Standard NTA Scoring (+4/-1)", font=_get_font(12, bold=False), fill=TEXT_SUB)
    draw.text((m4_x + 18, m4_y + 130), "• Full LaTeX Render Support", font=_get_font(12, bold=False), fill=TEXT_SUB)
    draw.text((m4_x + 18, m4_y + 155), "• Interactive Practice Mode", font=_get_font(12, bold=False), fill=TEXT_MUTED)

    # Footer
    f_foot = _get_font(12, bold=False)
    draw.text((50, 642), "CHRONOS STUDY OS · IST TIMEZONE", font=f_foot, fill=(71, 85, 105, 255))
    draw.text((CARD_WIDTH - 280, 642), "JEE TRIVIA MASTERY · PAGE 4/4", font=f_foot, fill=(71, 85, 105, 255))

    return _export_png(img)


# ==============================================================================
# SHOP CARD & INVENTORY SATCHEL CARD GENERATORS — PokeOne-style Parchment
# ==============================================================================
# Canvas is 920x580 (crisp 16:10 format, no EXPORT_SCALE downscaling penalty).
# Extra-large typography (24px names, 32px headers) guarantees instant readability
# on Discord mobile & desktop at 1:1 natural zoom.
POKE_W = 920
POKE_H = 580

# Warm cream parchment palette (authentic PokeOne satchel aesthetic)
_P_BG        = (246, 243, 231, 255)   # Cream parchment base
_P_SIDEBAR   = (236, 231, 213, 255)   # Left sidebar panel
_P_ROW       = (240, 235, 218, 255)   # Item row alternate fill
_P_ROW_ALT   = (246, 243, 231, 255)   # Item row base (matches BG)
_P_BORDER    = (214, 207, 187, 255)   # Crisp parchment dividers
_P_DARK      = (38, 42, 48, 255)      # Primary dark charcoal text
_P_MUTED     = (120, 125, 135, 255)   # Muted secondary text
_P_ACCENT    = (204, 75, 62, 255)     # Active/selected category capsule (warm crimson)
_P_GOLD_PILL = (185, 130, 20, 255)    # Rich amber gold price text
_P_CANDY     = (190, 60, 120, 255)    # Candy pink accent
_P_GREEN     = (60, 140, 90, 255)     # Forest green accent
_P_SIDEBAR_W = 240                    # Wide spacious sidebar
_P_CONTENT_X = 280                    # Content area left edge
_P_MARGIN    = 16                     # Outer margin
_P_ITEMS_PER_PAGE = 6                 # Exactly 6 massive, comfortable rows per page

SHOP_ITEMS_DATA = [
    {
        "id": "mystery_box",
        "num": 1,
        "name": "Mystery Box",
        "type": "CONSUMABLE",
        "price": 150,
        "icon": "mystery_box",
        "color": ACCENT_PURPLE,
        "desc": "Box of random rewards: Coins, XP, or rare items. Open with .openbox.",
    },
    {
        "id": "streak_freeze",
        "num": 2,
        "name": "Streak Freeze",
        "type": "CONSUMABLE",
        "price": 250,
        "icon": "streak_freeze",
        "color": ACCENT_CYAN,
        "desc": "Automatically shields your study streak when you miss exactly one day.",
    },
    {
        "id": "xp_boost",
        "num": 3,
        "name": "XP Boost",
        "type": "60M BOOST (2X)",
        "price": 300,
        "icon": "xp_boost",
        "color": ACCENT_GREEN,
        "desc": ".use to double study XP for 60 minutes. Stacks as inventory charges.",
    },
    {
        "id": "coin_boost",
        "num": 4,
        "name": "Chronocoin Boost",
        "type": "60M BOOST (2X)",
        "price": 300,
        "icon": "coin_boost",
        "color": ACCENT_GOLD,
        "desc": ".use to double Chronocoins earned from studying for 60 minutes.",
    },
    {
        "id": "title_scholar",
        "num": 5,
        "name": "Title: The Scholar",
        "type": "PRESTIGE TITLE",
        "price": 400,
        "icon": "title_scroll",
        "color": (217, 119, 6, 255),
        "desc": "Unlocks custom title 'The Scholar' to display on your .stats profile.",
    },
    {
        "id": "title_grinder",
        "num": 6,
        "name": "Title: The Grinder",
        "type": "PRESTIGE TITLE",
        "price": 400,
        "icon": "title_scroll",
        "color": (217, 119, 6, 255),
        "desc": "Unlocks custom title 'The Grinder' to display on your .stats profile.",
    },
    {
        "id": "title_insomniac",
        "num": 7,
        "name": "Title: Insomniac",
        "type": "PRESTIGE TITLE",
        "price": 400,
        "icon": "title_scroll",
        "color": (217, 119, 6, 255),
        "desc": "Unlocks custom title 'Insomniac' to display on your .stats profile.",
    },
    {
        "id": "title_legend",
        "num": 8,
        "name": "Title: Legend",
        "type": "PRESTIGE TITLE",
        "price": 1000,
        "icon": "title_scroll",
        "color": ACCENT_GOLD,
        "desc": "A supreme prestige title for the most dedicated study grinders.",
    },
]

ITEM_METADATA = {
    "mystery_box": {
        "name": "Mystery Box",
        "icon": "mystery_box",
        "type": "CONSUMABLE",
        "action": ".openbox to open for rewards",
        "color": ACCENT_PURPLE,
    },
    "streak_freeze": {
        "name": "Streak Freeze",
        "icon": "streak_freeze",
        "type": "CONSUMABLE",
        "action": "Passive protection on missed day",
        "color": ACCENT_CYAN,
    },
    "xp_boost": {
        "name": "XP Boost",
        "icon": "xp_boost",
        "type": "BOOST CHARGES",
        "action": ".use xp boost to activate 2x XP (60m)",
        "color": ACCENT_GREEN,
    },
    "coin_boost": {
        "name": "Chronocoin Boost",
        "icon": "coin_boost",
        "type": "BOOST CHARGES",
        "action": ".use coin boost to activate 2x coins (60m)",
        "color": ACCENT_GOLD,
    },
    "sugar_rush": {
        "name": "Sugar Rush",
        "icon": "sugar_rush",
        "type": "2X STUDY BOOST",
        "action": ".use sugar rush to activate 2x XP (60m)",
        "color": (217, 70, 239, 255),
    },
    "halloween_candy": {
        "name": "Halloween Candy",
        "icon": "halloween_candy",
        "type": "EVENT CANDY",
        "action": ".candyshop to exchange for rare rewards",
        "color": (249, 115, 22, 255),
    },
    "candy": {
        "name": "Halloween Candy",
        "icon": "halloween_candy",
        "type": "EVENT CANDY",
        "action": ".candyshop to exchange for rare rewards",
        "color": (249, 115, 22, 255),
    },
    "title_scholar": {
        "name": "Title: The Scholar",
        "icon": "title_scroll",
        "type": "PRESTIGE TITLE",
        "action": ".settitle The Scholar to equip",
        "color": (217, 119, 6, 255),
    },
    "title_grinder": {
        "name": "Title: The Grinder",
        "icon": "title_scroll",
        "type": "PRESTIGE TITLE",
        "action": ".settitle The Grinder to equip",
        "color": (217, 119, 6, 255),
    },
    "title_insomniac": {
        "name": "Title: Insomniac",
        "icon": "title_scroll",
        "type": "PRESTIGE TITLE",
        "action": ".settitle Insomniac to equip",
        "color": (217, 119, 6, 255),
    },
    "title_legend": {
        "name": "Title: Legend",
        "icon": "title_scroll",
        "type": "PRESTIGE TITLE",
        "action": ".settitle Legend to equip",
        "color": ACCENT_GOLD,
    },
    "title_inorganic": {
        "name": "Title: Inorganic Nightmare",
        "icon": "title_scroll",
        "type": "EVENT TITLE",
        "action": ".settitle Inorganic Nightmare to equip",
        "color": (217, 119, 6, 255),
    },
    "title_shift1": {
        "name": "Title: Shift 1 Phantom",
        "icon": "title_scroll",
        "type": "EVENT TITLE",
        "action": ".settitle The Shift 1 Phantom to equip",
        "color": (217, 119, 6, 255),
    },
    "title_great_pumpkin": {
        "name": "Title: The Great Pumpkin",
        "icon": "title_scroll",
        "type": "EVENT TITLE",
        "action": ".settitle The Great Pumpkin to equip",
        "color": ACCENT_GOLD,
    },
}


# Legacy height aliases (kept for any stray references)
SHOP_CARD_HEIGHT = 1100
INV_CARD_HEIGHT = 1100


# ── PokeOne-style helpers ────────────────────────────────────────────────────
def _poke_export(img: Image.Image) -> bytes:
    """Export a PokeOne-style 920x580 card directly — no upscale penalty."""
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _poke_draw_sidebar(
    img: Image.Image,
    draw: ImageDraw.Draw,
    *,
    hero_icon: str,
    title: str,
    subtitle: str,
    categories: list[tuple[str, int, bool]],
    wallet_lines: list[tuple[str, str, tuple[int, int, int, int]]],
) -> None:
    """Draw the left PokeOne parchment sidebar: large hero icon, bold title, category pills, wallet."""
    sw = _P_SIDEBAR_W
    m = _P_MARGIN
    # Sidebar container
    draw.rounded_rectangle(
        [m + 4, m + 4, m + sw, POKE_H - m - 4],
        radius=18, fill=_P_SIDEBAR,
    )
    draw.line([(m + sw, m + 14), (m + sw, POKE_H - m - 14)], fill=_P_BORDER, width=2)

    # Hero icon (centered 72x72 container with 60x60 icon)
    icon_box = 72
    icon_x = m + 4 + (sw - icon_box) // 2
    icon_y = m + 16
    draw.rounded_rectangle(
        [icon_x, icon_y, icon_x + icon_box, icon_y + icon_box],
        radius=14, fill=_P_BG, outline=_P_BORDER, width=1,
    )
    _paste_pixel_icon(img, hero_icon, icon_x + 6, icon_y + 6, 60)

    # Title & Subtitle (Big & punchy)
    ty = icon_y + icon_box + 12
    f_title = _get_font(23, bold=True)
    draw.text((m + 4 + sw // 2, ty), title, font=f_title, fill=_P_DARK, anchor="mt")
    ty += 30
    f_sub = _get_font(15, bold=False)
    draw.text((m + 4 + sw // 2, ty), subtitle, font=f_sub, fill=_P_MUTED, anchor="mt")
    ty += 30

    # Category pills (Big 42px height, 16px bold text)
    pill_x = m + 18
    pill_w = sw - 28
    for cat_name, count, is_active in categories:
        pill_h = 42
        if is_active:
            draw.rounded_rectangle(
                [pill_x, ty, pill_x + pill_w, ty + pill_h],
                radius=10, fill=_P_ACCENT,
            )
            draw.text((pill_x + 14, ty + 10), cat_name.upper(), font=_get_font(16, bold=True), fill=(255, 255, 255, 255))
            draw.text((pill_x + pill_w - 14, ty + 10), str(count), font=_get_font(16, bold=True), fill=(255, 255, 255, 255), anchor="rt")
        else:
            draw.rounded_rectangle(
                [pill_x, ty, pill_x + pill_w, ty + pill_h],
                radius=10, fill=_P_BG, outline=_P_BORDER, width=1,
            )
            draw.text((pill_x + 14, ty + 10), cat_name.upper(), font=_get_font(16, bold=True), fill=_P_DARK)
            draw.text((pill_x + pill_w - 14, ty + 10), str(count), font=_get_font(16, bold=True), fill=_P_MUTED, anchor="rt")
        ty += pill_h + 8

    # Wallet pills at bottom of sidebar (40px tall, big 17px text + icon)
    wy = POKE_H - m - 16 - len(wallet_lines) * 48
    for wicon, wtxt, wcolor in wallet_lines:
        draw.rounded_rectangle(
            [pill_x, wy, pill_x + pill_w, wy + 40],
            radius=10, fill=_P_BG, outline=_P_BORDER, width=1,
        )
        _paste_pixel_icon(img, wicon, pill_x + 10, wy + 8, 24)
        draw.text((pill_x + 40, wy + 9), wtxt, font=_get_font(17, bold=True), fill=wcolor)
        wy += 48


def _poke_draw_item_rows(
    img: Image.Image,
    draw: ImageDraw.Draw,
    *,
    header_title: str,
    header_sub: str,
    page_str: str,
    items_count_str: str,
    rows: list[dict[str, Any]],
) -> None:
    """Draw the right-side item table: header + up to 6 spacious, high-readability item rows."""
    cx = _P_CONTENT_X
    m = _P_MARGIN

    # Header row (Big 32px title)
    hy = m + 10
    draw.text((cx, hy), header_title, font=_get_font(32, bold=True), fill=_P_DARK)
    draw.text((cx, hy + 38), header_sub, font=_get_font(15, bold=False), fill=_P_MUTED)
    # Page indicator & entries count
    f_page = _get_font(18, bold=True)
    draw.text((POKE_W - m - 14, hy + 4), page_str, font=f_page, fill=_P_MUTED, anchor="rt")
    draw.text((POKE_W - m - 14, hy + 34), items_count_str, font=_get_font(14, bold=False), fill=_P_MUTED, anchor="rt")

    # Horizontal divider
    div_y = hy + 64
    draw.line([(cx, div_y), (POKE_W - m - 10, div_y)], fill=_P_BORDER, width=2)

    # 6 Spacious Item rows (height=68px each, gap=6px)
    row_h = 68
    row_gap = 6
    ry = div_y + 8

    for i, row in enumerate(rows):
        bg = _P_ROW if i % 2 == 0 else _P_ROW_ALT
        draw.rounded_rectangle(
            [cx, ry, POKE_W - m - 10, ry + row_h],
            radius=12, fill=bg,
        )

        # 52x52 icon frame with 44x44 pixel art icon
        icon_x = cx + 10
        icon_y = ry + 8
        draw.rounded_rectangle(
            [icon_x, icon_y, icon_x + 52, icon_y + 52],
            radius=10, fill=_P_SIDEBAR, outline=_P_BORDER, width=1,
        )
        _paste_pixel_icon(img, row.get("icon", "mystery_box"), icon_x + 4, icon_y + 4, 44)

        # Item name (23px bold)
        name = row.get("name", "Unknown")
        if len(name) > 36:
            name = name[:34] + ".."
        draw.text((cx + 72, ry + 10), name, font=_get_font(23, bold=True), fill=_P_DARK)

        # Subtitle / description (15px)
        sub = row.get("subtitle", "")
        if len(sub) > 62:
            sub = sub[:60] + ".."
        if sub:
            draw.text((cx + 72, ry + 39), sub, font=_get_font(15, bold=False), fill=(110, 115, 125, 255))

        # Right-aligned value & optional currency icon
        val = row.get("right_text", "")
        curr_icon = row.get("curr_icon")
        val_color = row.get("right_color", _P_DARK)
        f_val = _get_font(24, bold=True)
        if curr_icon:
            draw.text((POKE_W - m - 46, ry + 20), val, font=f_val, fill=val_color, anchor="rt")
            _paste_pixel_icon(img, curr_icon, POKE_W - m - 40, ry + 22, 24)
        else:
            draw.text((POKE_W - m - 20, ry + 20), val, font=f_val, fill=val_color, anchor="rt")

        ry += row_h + row_gap

    # Footer line
    draw.line(
        [(cx, POKE_H - m - 18), (POKE_W - m - 10, POKE_H - m - 18)],
        fill=_P_BORDER, width=1,
    )
    draw.text(
        (cx + 6, POKE_H - m - 15),
        "Chronos · Study smarter, one session at a time",
        font=_get_font(11, bold=False), fill=_P_MUTED,
    )


# ── PokeOne-style Shop Card ─────────────────────────────────────────────────
def render_shop_card_sync(
    user_coins: int,
    items: Optional[list[dict[str, Any]]] = None,
    page: int = 0,
    per_page: int = 6,
) -> bytes:
    """920x580 PokeOne-style parchment shop card — massive typography & pixel icons."""
    if items is None:
        from utils.economy import SHOP_ITEMS, SHOP_ORDER
        items = []
        for num, item_id in enumerate(SHOP_ORDER, start=1):
            if item_id in SHOP_ITEMS:
                si = SHOP_ITEMS[item_id]
                itype = str(si.get("type", "item")).upper()
                if itype == "BOOST":
                    icon = "xp_boost" if "xp" in item_id else "coin_boost"
                elif itype == "CONSUMABLE":
                    icon = "mystery_box" if "box" in item_id else "streak_freeze"
                elif itype == "TITLE":
                    icon = "title_scroll"
                else:
                    icon = "mystery_box"
                items.append({
                    "id": item_id,
                    "num": num,
                    "name": si["name"],
                    "icon": icon,
                    "desc": si.get("description", ""),
                    "price": si["price"],
                })

    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    curr_page = max(0, min(page, total_pages - 1))
    start_idx = curr_page * per_page
    page_items = items[start_idx : start_idx + per_page]

    # Canvas
    img = Image.new("RGBA", (POKE_W, POKE_H), _P_BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [_P_MARGIN, _P_MARGIN, POKE_W - _P_MARGIN, POKE_H - _P_MARGIN],
        radius=20, fill=None, outline=_P_BORDER, width=2,
    )

    # Sidebar categories
    from utils.economy import SHOP_ITEMS, SHOP_ORDER
    cat_counts: dict[str, int] = {}
    for sid in SHOP_ORDER:
        if sid in SHOP_ITEMS:
            t = str(SHOP_ITEMS[sid].get("type", "item")).upper()
            cat_counts[t] = cat_counts.get(t, 0) + 1
    cats = [(name, cnt, i == 0) for i, (name, cnt) in enumerate(cat_counts.items())]
    if not cats:
        cats = [("ALL", total_items, True)]

    _poke_draw_sidebar(
        img, draw,
        hero_icon="chronocoin",
        title="CHRONOS SHOP",
        subtitle=f"{total_items} items catalog",
        categories=cats,
        wallet_lines=[("chronocoin", f"{user_coins:,} Coins", _P_GOLD_PILL)],
    )

    # Item rows
    rows = []
    for item in page_items:
        rows.append({
            "icon": item["icon"],
            "name": f"{item['num']}. {item['name']}",
            "subtitle": item["desc"],
            "right_text": f"{item['price']:,}",
            "curr_icon": "chronocoin",
            "right_color": _P_GOLD_PILL,
        })

    _poke_draw_item_rows(
        img, draw,
        header_title="Coin Shop",
        header_sub="Use .buy <item> [qty] to purchase",
        page_str=f"PAGE {curr_page + 1}/{total_pages}",
        items_count_str=f"{total_items} entries",
        rows=rows,
    )

    return _poke_export(img)


# ── PokeOne-style Food Shop Card ─────────────────────────────────────────────
def render_food_shop_card_sync(
    tier: str,
    user_coins: int,
    owned_food: Optional[dict[str, int]] = None,
    page: int = 0,
    per_page: int = 6,
) -> bytes:
    """920x580 PokeOne-style parchment food shop card — massive typography & food sprites."""
    from utils.food import FOODS, FOODS_BY_TIER, FOOD_TIER_INFO

    clean_tier = tier.lower().strip()
    if clean_tier not in FOODS_BY_TIER:
        clean_tier = "snack"

    tier_info = FOOD_TIER_INFO.get(clean_tier, {"label": clean_tier.title(), "color": 0x34D399})

    tier_food_ids = FOODS_BY_TIER.get(clean_tier, [])
    total_items = len(tier_food_ids)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    curr_page = max(0, min(page, total_pages - 1))
    start_idx = curr_page * per_page
    page_ids = tier_food_ids[start_idx : start_idx + per_page]

    if owned_food is None:
        owned_food = {}

    # Canvas
    img = Image.new("RGBA", (POKE_W, POKE_H), _P_BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [_P_MARGIN, _P_MARGIN, POKE_W - _P_MARGIN, POKE_H - _P_MARGIN],
        radius=20, fill=None, outline=_P_BORDER, width=2,
    )

    # Sidebar — tier categories
    tier_cats = []
    for tk in ["snack", "meal", "feast", "golden"]:
        ti = FOOD_TIER_INFO.get(tk, {"label": tk.title()})
        cnt = len(FOODS_BY_TIER.get(tk, []))
        tier_cats.append((ti["label"], cnt, tk == clean_tier))

    first_icon = f"food/{page_ids[0]}" if page_ids else "food/apple_pie"
    _poke_draw_sidebar(
        img, draw,
        hero_icon=first_icon,
        title="PET BAKERY",
        subtitle=f"{tier_info['label']} tier · {total_items} foods",
        categories=tier_cats,
        wallet_lines=[("chronocoin", f"{user_coins:,} Coins", _P_GOLD_PILL)],
    )

    # Item rows
    rows = []
    for fid in page_ids:
        food = FOODS[fid]
        have = owned_food.get(fid, 0)
        own_str = f" (Owned: x{have})" if have > 0 else ""
        rows.append({
            "icon": f"food/{fid}",
            "name": food["name"],
            "subtitle": f"+{food['xp']:,} Pet XP{own_str}",
            "right_text": f"{food['cost']:,}",
            "curr_icon": "chronocoin",
            "right_color": _P_GOLD_PILL,
        })

    _poke_draw_item_rows(
        img, draw,
        header_title=f"{tier_info['label']} Foods",
        header_sub=".buyfood <item> [qty] · .feed <item>",
        page_str=f"PAGE {curr_page + 1}/{total_pages}",
        items_count_str=f"{total_items} entries",
        rows=rows,
    )

    return _poke_export(img)


# ── PokeOne-style Candy Shop Card ────────────────────────────────────────────
def render_candy_shop_card_sync(
    user_candy: int,
    owned_titles: Optional[set[str]] = None,
    owned_pets: Optional[set[str]] = None,
    sugar_rush_qty: int = 0,
) -> bytes:
    """920x580 PokeOne-style parchment candy shop card — massive typography & event rewards."""
    from utils.halloween import CANDY_SHOP_ITEMS, CANDY_SHOP_ORDER

    if owned_titles is None:
        owned_titles = set()
    if owned_pets is None:
        owned_pets = set()

    # Canvas
    img = Image.new("RGBA", (POKE_W, POKE_H), _P_BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [_P_MARGIN, _P_MARGIN, POKE_W - _P_MARGIN, POKE_H - _P_MARGIN],
        radius=20, fill=None, outline=_P_BORDER, width=2,
    )

    # Build items list
    shop_rows: list[dict[str, Any]] = []
    for key in CANDY_SHOP_ORDER:
        item = CANDY_SHOP_ITEMS[key]
        if key == "pumpkaboo":
            icon = "mystery_box"
            sub = "Event-exclusive pet companion"
            owned = "pumpkaboo" in owned_pets
        elif key == "sugar_rush":
            icon = "sugar_rush"
            sub = f"2x XP boost (60m) · Owned: x{sugar_rush_qty}"
            owned = False
        else:
            icon = "title_scroll"
            t_title = item.get("title_text", key)
            sub = f'Prestige Title: "{t_title}"'
            owned = key in owned_titles or t_title in owned_titles

        own_tag = " [OWNED]" if owned else ""
        shop_rows.append({
            "icon": icon,
            "name": item["name"] + own_tag,
            "subtitle": sub,
            "right_text": f"{item['candy_price']:,}",
            "curr_icon": "halloween_candy",
            "right_color": _P_CANDY,
        })

    # Sidebar
    _poke_draw_sidebar(
        img, draw,
        hero_icon="halloween_candy",
        title="CANDY BAZAAR",
        subtitle=f"Halloween 2026 · {len(shop_rows)} items",
        categories=[("ALL REWARDS", len(shop_rows), True)],
        wallet_lines=[("halloween_candy", f"{user_candy:,} Candy", _P_CANDY)],
    )

    _poke_draw_item_rows(
        img, draw,
        header_title="Halloween Rewards",
        header_sub=".buycandy <item> [qty] to purchase",
        page_str="PAGE 1/1",
        items_count_str=f"{len(shop_rows)} entries",
        rows=shop_rows,
    )

    return _poke_export(img)


def _wrap_text_lines(text: str, max_chars: int = 36, max_lines: int = 2) -> list[str]:
    """Wrap text neatly across up to `max_lines` with ellipsis if overflow."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    curr = ""
    i = 0
    while i < len(words):
        w = words[i]
        if not curr:
            curr = w
            i += 1
        elif len(curr) + 1 + len(w) <= max_chars:
            curr += " " + w
            i += 1
        else:
            lines.append(curr)
            curr = ""
            if len(lines) == max_lines - 1:
                rem_curr = ""
                while i < len(words):
                    nw = words[i]
                    if not rem_curr:
                        rem_curr = nw
                    elif len(rem_curr) + 1 + len(nw) <= max_chars - 3:
                        rem_curr += " " + nw
                    else:
                        rem_curr += "..."
                        break
                    i += 1
                lines.append(rem_curr)
                break
    if curr and len(lines) < max_lines:
        lines.append(curr)
    return lines


def get_item_display_meta(item_id: str) -> dict[str, Any]:
    """Resolve rich metadata (name, icon, type, action, color) for any inventory item."""
    if item_id in ITEM_METADATA:
        return dict(ITEM_METADATA[item_id])

    # 1. Economy shop catalog
    try:
        from utils.economy import SHOP_ITEMS
        if item_id in SHOP_ITEMS:
            si = SHOP_ITEMS[item_id]
            itype = str(si.get("type", "item")).lower()
            if itype == "boost":
                color = ACCENT_GREEN if "xp" in item_id else ACCENT_GOLD
                icon = "xp_boost" if "xp" in item_id else "coin_boost"
                type_label = "BOOST CHARGES"
                dur = si.get("duration_minutes", 60)
                action = f".use {item_id.replace('_', ' ')} to activate ({dur}m)"
            elif itype == "consumable":
                color = ACCENT_PURPLE if "box" in item_id else ACCENT_CYAN
                icon = "mystery_box" if "box" in item_id else "streak_freeze"
                type_label = "CONSUMABLE"
                action = ".openbox to open for rewards" if "box" in item_id else "Auto streak protection"
            elif itype == "title":
                color = (245, 158, 11, 255)
                icon = "title_scroll"
                type_label = "PRESTIGE TITLE"
                action = f".settitle {si.get('title_text', item_id)} to equip"
            else:
                color = ACCENT_CYAN
                icon = "mystery_box"
                type_label = "VAULT ITEM"
                action = si.get("description", "Owned item in satchel")
            return {
                "name": si.get("name", item_id.replace("_", " ").title()),
                "icon": icon,
                "type": type_label,
                "action": action,
                "color": color,
            }
    except Exception:
        pass

    # 2. Food catalog
    try:
        from utils.food import FOODS, FOOD_TIER_INFO
        if item_id in FOODS:
            f = FOODS[item_id]
            tier_key = str(f.get("tier", "snack")).lower()
            tier_str = tier_key.upper()
            tier_color_int = FOOD_TIER_INFO.get(tier_key, {}).get("color", 0x34D399)
            r = (tier_color_int >> 16) & 0xFF
            g = (tier_color_int >> 8) & 0xFF
            b = tier_color_int & 0xFF
            return {
                "name": f.get("name", item_id.replace("_", " ").title()),
                "icon": f"food/{item_id}",
                "type": f"PET FOOD ({tier_str})",
                "action": f"+{f.get('xp', 50)} Pet XP • Use .feed {item_id}",
                "color": (r, g, b, 255),
            }
    except Exception:
        pass

    # 2.5 Hallo-Boxes
    try:
        from utils.halloween import HALLO_BOXES
        if item_id in HALLO_BOXES:
            hb = HALLO_BOXES[item_id]
            c_int = hb.get("color", 0x34D399)
            r = (c_int >> 16) & 0xFF
            g = (c_int >> 8) & 0xFF
            b = c_int & 0xFF
            return {
                "name": hb.get("name", item_id.replace("_", " ").title()),
                "icon": "mystery_box",
                "type": "HALLOWEEN BOX",
                "action": f".openbox {item_id} to open",
                "color": (r, g, b, 255),
            }
    except Exception:
        pass

    # 3. Halloween catalog
    try:
        from utils.halloween import CANDY_SHOP_ITEMS
        if item_id in CANDY_SHOP_ITEMS:
            c = CANDY_SHOP_ITEMS[item_id]
            return {
                "name": c.get("name", item_id.replace("_", " ").title()),
                "icon": "xp_boost" if "rush" in item_id else "mystery_box",
                "type": "HALLOWEEN REWARD",
                "action": c.get("description", "Seasonal event item"),
                "color": (244, 114, 182, 255),
            }
    except Exception:
        pass

    # 4. Title check
    if item_id.startswith("title_"):
        t_name = item_id.replace("title_", "").replace("_", " ").title()
        return {
            "name": f"Title: {t_name}",
            "icon": "title_scroll",
            "type": "PRESTIGE TITLE",
            "action": f".settitle {t_name} to equip",
            "color": ACCENT_GOLD,
        }

    # 5. Generic fallback
    return {
        "name": item_id.replace("_", " ").title(),
        "icon": "mystery_box",
        "type": "VAULT ITEM",
        "action": "Owned item in your satchel",
        "color": ACCENT_CYAN,
    }


# ── PokeOne-style Inventory/Bag Card ────────────────────────────────────────
def render_inventory_card_sync(
    display_name: str,
    username: str,
    tier_name: str,
    coins: int,
    candy: int,
    inventory: dict[str, int],
    active_boosts: list[dict[str, Any]],
    equipped_title: Optional[str] = None,
    avatar_bytes: Optional[bytes] = None,
    page: int = 0,
    per_page: int = 6,
) -> bytes:
    """920x580 PokeOne-style parchment inventory card — massive typography & satchel items."""
    # Collect valid items
    valid_items = [(k, v) for k, v in inventory.items() if v > 0]
    total_items = len(valid_items)
    total_qty = sum(v for _, v in valid_items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    curr_page = max(0, min(page, total_pages - 1))
    start_idx = curr_page * per_page
    page_items = valid_items[start_idx : start_idx + per_page]

    # Categorize items for sidebar
    cat_counts: dict[str, int] = {}
    for item_id, qty in valid_items:
        meta = get_item_display_meta(item_id)
        t = meta.get("type", "ITEM")
        if "BOOST" in t:
            cat_key = "BOOSTS"
        elif "FOOD" in t:
            cat_key = "PET FOOD"
        elif "TITLE" in t:
            cat_key = "TITLES"
        elif "CONSUMABLE" in t:
            cat_key = "CONSUMABLE"
        elif "HALLOWEEN" in t or "EVENT" in t:
            cat_key = "EVENT"
        else:
            cat_key = "MISC"
        cat_counts[cat_key] = cat_counts.get(cat_key, 0) + qty

    cats = [(name, cnt, i == 0) for i, (name, cnt) in enumerate(cat_counts.items())]
    if not cats:
        cats = [("EMPTY", 0, True)]

    # Canvas
    img = Image.new("RGBA", (POKE_W, POKE_H), _P_BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [_P_MARGIN, _P_MARGIN, POKE_W - _P_MARGIN, POKE_H - _P_MARGIN],
        radius=20, fill=None, outline=_P_BORDER, width=2,
    )

    clean_disp = _sanitize_text(display_name) or "Bag"
    hero_icon = "chronocoin"

    _poke_draw_sidebar(
        img, draw,
        hero_icon=hero_icon,
        title=f"{clean_disp.upper()}'S BAG",
        subtitle=f"{total_items} unique · {total_qty:,} total",
        categories=cats,
        wallet_lines=[
            ("chronocoin", f"{coins:,} Coins", _P_GOLD_PILL),
            ("halloween_candy", f"{candy:,} Candy", _P_CANDY),
        ],
    )

    # If avatar_bytes available, paste over the hero icon area
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as raw_av:
                circle_av = _make_circular_avatar(raw_av, 60)
                icon_box = 72
                ax = _P_MARGIN + 4 + (_P_SIDEBAR_W - icon_box) // 2 + 6
                ay = _P_MARGIN + 16 + 6
                img.paste(circle_av, (ax, ay), circle_av)
        except Exception:
            pass

    # Item rows
    rows = []
    for item_id, qty in page_items:
        meta = get_item_display_meta(item_id)
        rows.append({
            "icon": meta["icon"],
            "name": meta["name"],
            "subtitle": meta["action"],
            "right_text": f"{qty}x",
            "right_color": _P_DARK,
        })

    boost_hint = ""
    if active_boosts:
        b = active_boosts[0]
        boost_hint = f" · {b['name']} active"

    _poke_draw_item_rows(
        img, draw,
        header_title="Satchel" + boost_hint,
        header_sub=".use <item> · .openbox · .settitle",
        page_str=f"PAGE {curr_page + 1}/{total_pages}",
        items_count_str=f"{total_items} entries",
        rows=rows,
    )

    return _poke_export(img)


# ==============================================================================
# 7. CHRONOTES INDEX CARD (1200x680)
# ==============================================================================
def render_note_card_sync(
    title: str,
    subject: str,
    content: str,
    author_name: str,
    date_str: str,
    is_pinned: bool = False,
    note_id: Optional[int] = None,
) -> bytes:
    """Renders a digital notebook index card preview (1200x680 HD)."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Outer border & canvas
    draw.rounded_rectangle([30, 30, CARD_WIDTH - 30, CARD_HEIGHT - 30], radius=24, fill=CARD_BG, outline=CARD_BORDER, width=2)

    # Subject accent colors
    sub_lower = subject.lower()
    if "phys" in sub_lower:
        sub_color = ACCENT_CYAN
    elif "chem" in sub_lower:
        sub_color = ACCENT_GREEN
    elif "math" in sub_lower:
        sub_color = ACCENT_ROSE
    elif "form" in sub_lower:
        sub_color = ACCENT_GOLD
    elif "rev" in sub_lower:
        sub_color = ACCENT_PURPLE
    else:
        sub_color = ACCENT_ORANGE

    # Top pills row
    cur_x = 60
    # Subject pill
    sub_tag = _sanitize_text(subject.upper())[:18]
    f_tag = _get_font(13, bold=True)
    tb = draw.textbbox((0, 0), sub_tag, font=f_tag)
    tw = tb[2] - tb[0]
    draw.rounded_rectangle([cur_x, 56, cur_x + tw + 24, 88], radius=8, fill=(sub_color[0], sub_color[1], sub_color[2], 40), outline=sub_color, width=1)
    draw.text((cur_x + 12, 63), sub_tag, font=f_tag, fill=sub_color)
    cur_x += tw + 36

    # Pinned pill if pinned
    if is_pinned:
        draw.rounded_rectangle([cur_x, 56, cur_x + 95, 88], radius=8, fill=(251, 191, 36, 40), outline=ACCENT_GOLD, width=1)
        draw.text((cur_x + 10, 63), "PINNED", font=f_tag, fill=ACCENT_GOLD)
        cur_x += 107

    # Note ID pill
    if note_id:
        id_str = f"NOTE #{note_id}"
        draw.rounded_rectangle([cur_x, 56, cur_x + 90, 88], radius=8, fill=(30, 41, 59, 180), outline=PANEL_BORDER, width=1)
        draw.text((cur_x + 10, 63), id_str, font=f_tag, fill=TEXT_MUTED)

    # Author & Date on top right
    meta_text = f"by {_sanitize_text(author_name)[:20]}  •  {date_str}"
    f_meta = _get_font(13, bold=False)
    m_bbox = draw.textbbox((0, 0), meta_text, font=f_meta)
    mw = m_bbox[2] - m_bbox[0]
    draw.text((CARD_WIDTH - 60 - mw, 63), meta_text, font=f_meta, fill=TEXT_MUTED)

    # Title
    f_title = _get_font(30, bold=True)
    clean_title = _sanitize_text(title)[:60]
    draw.text((60, 108), clean_title, font=f_title, fill=TEXT_WHITE)

    # Divider bar
    draw.line([(60, 160), (CARD_WIDTH - 60, 160)], fill=CARD_BORDER, width=2)
    draw.line([(60, 160), (220, 160)], fill=sub_color, width=3)

    # Note notebook body container
    body_x = 60
    body_y = 180
    body_w = CARD_WIDTH - 120
    body_h = 420
    draw.rounded_rectangle([body_x, body_y, body_x + body_w, body_y + body_h], radius=16, fill=PANEL_BG, outline=PANEL_BORDER, width=1)

    # Draw ruled lines like a clean digital notebook
    for ly in range(body_y + 45, body_y + body_h - 15, 34):
        draw.line([(body_x + 20, ly), (body_x + body_w - 20, ly)], fill=(26, 33, 46, 200), width=1)

    # Format and render note content
    f_content = _get_font(16, bold=False)
    clean_content = _sanitize_text(content)
    raw_lines = clean_content.split("\n")

    # Wrap lines to fit width
    wrapped_lines: list[str] = []
    max_char_width = 82
    for rline in raw_lines:
        rline = rline.rstrip()
        if not rline:
            wrapped_lines.append("")
            continue
        while len(rline) > max_char_width:
            cut = rline[:max_char_width].rfind(" ")
            if cut == -1:
                cut = max_char_width
            wrapped_lines.append(rline[:cut])
            rline = rline[cut:].lstrip()
        if rline:
            wrapped_lines.append(rline)

    text_y = body_y + 18
    for i, line in enumerate(wrapped_lines[:11]):
        if i == 10 and len(wrapped_lines) > 11:
            line = "... (Note truncated in visual preview · Read full note in Discord)"
            draw.text((body_x + 30, text_y), line, font=_get_font(14, bold=True), fill=ACCENT_CYAN)
        else:
            draw.text((body_x + 30, text_y), line, font=f_content, fill=TEXT_SUB)
        text_y += 34

    # Footer
    draw.text((60, 624), "CHRONOTES · IN-DISCORD STUDY NOTEBOOK", font=_get_font(12, bold=True), fill=TEXT_MUTED)
    draw.text((CARD_WIDTH - 280, 624), "SECURE & SYNCHRONIZED STORAGE", font=_get_font(12, bold=False), fill=(71, 85, 105, 255))

    return _export_png(img)


