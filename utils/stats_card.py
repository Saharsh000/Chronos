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
    "iron": (148, 163, 184),
    "bronze": (205, 127, 50),
    "silver": (192, 192, 192),
    "gold": (245, 158, 11),
    "platinum": (56, 189, 248),
    "diamond": (129, 140, 248),
    "ascendant": (16, 185, 129),
    "immortal": (236, 72, 153),
    "radiant": (251, 191, 36),
    "air 1": (244, 63, 94),
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
    """Safely paste a pixel-art icon (Minecraft items, food sprites, etc.) with nearest-neighbor scaling."""
    base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
    clean_name = icon_name.replace("food/", "")
    candidates = [
        os.path.join(base_dir, f"{icon_name}_128.png"),
        os.path.join(base_dir, f"{icon_name}.png"),
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
# CARD 1: OVERVIEW DASHBOARD (Page 1)
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
    """Synchronously renders the high-res 1200x680 study overview stats card PNG."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    clean_tier = tier_name.split()[-1].lower() if tier_name else "iron"
    tier_rgb = TIER_COLORS.get(clean_tier, (148, 163, 184))
    tier_rgba = (*tier_rgb, 255)

    # Outer border and ambient top glow
    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, CARD_HEIGHT - 20], radius=20, fill=None, outline=(30, 41, 59, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=tier_rgba, width=4)

    # Avatar
    av_size = 92
    av_x, av_y = 50, 48
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as raw_av:
                circle_av = _make_circular_avatar(raw_av, av_size)
                img.paste(circle_av, (av_x, av_y), circle_av)
                draw.ellipse([av_x - 3, av_y - 3, av_x + av_size + 3, av_y + av_size + 3], outline=tier_rgba, width=3)
        except Exception:
            draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=3)
    else:
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=CARD_BG, outline=tier_rgba, width=3)

    # Identity block
    f_name = _get_font(32, bold=True)
    f_user = _get_font(17, bold=False)
    f_badge = _get_font(13, bold=True)
    f_title = _get_font(13, bold=True)

    text_x = av_x + av_size + 24
    clean_display = _sanitize_text(display_name) or "Candidate"
    draw.text((text_x, av_y + 4), clean_display[:20], font=f_name, fill=TEXT_WHITE)
    clean_user = _sanitize_text(username) or "aspirant"
    draw.text((text_x, av_y + 44), f"@{clean_user[:22]}", font=f_user, fill=TEXT_MUTED)

    if equipped_title:
        clean_title = _sanitize_text(equipped_title)
        if clean_title:
            try:
                t_bbox = draw.textbbox((text_x, av_y + 70), clean_title, font=f_title)
                t_w = t_bbox[2] - t_bbox[0]
            except Exception:
                t_w = len(clean_title) * 8
            draw.rounded_rectangle([text_x, av_y + 68, text_x + t_w + 16, av_y + 92], radius=6, fill=(30, 41, 59, 200))
            draw.text((text_x + 8, av_y + 72), clean_title, font=f_title, fill=ACCENT_CYAN)

    # Badges (Rank & Level)
    rank_str = f"RANK #{rank_position}" if rank_position else "UNRANKED"
    lvl_str = f"LVL {level} · {tier_name.upper()}"
    badge_y = av_y + 12
    try:
        lvl_bbox = draw.textbbox((0, 0), lvl_str, font=f_badge)
        lvl_w = lvl_bbox[2] - lvl_bbox[0]
    except Exception:
        lvl_w = len(lvl_str) * 9
    lvl_x = CARD_WIDTH - 50 - lvl_w - 24
    draw.rounded_rectangle([lvl_x, badge_y, lvl_x + lvl_w + 20, badge_y + 32], radius=8, fill=CARD_BG, outline=tier_rgba, width=2)
    draw.text((lvl_x + 10, badge_y + 7), lvl_str, font=f_badge, fill=tier_rgba)

    try:
        rank_bbox = draw.textbbox((0, 0), rank_str, font=f_badge)
        rank_w = rank_bbox[2] - rank_bbox[0]
    except Exception:
        rank_w = len(rank_str) * 8
    rank_x = lvl_x - rank_w - 30
    draw.rounded_rectangle([rank_x, badge_y, rank_x + rank_w + 20, badge_y + 32], radius=8, fill=CARD_BG, outline=(55, 65, 81, 255), width=1)
    draw.text((rank_x + 10, badge_y + 7), rank_str, font=f_badge, fill=TEXT_MUTED)

    # Level progress bar
    pb_x, pb_y = 50, 160
    pb_w = CARD_WIDTH - 100
    pb_h = 10
    pct = (xp_into / xp_needed) if xp_needed > 0 else 1.0
    f_bar = _get_font(13, bold=True)
    draw.text((pb_x, pb_y - 22), f"LEVEL PROGRESS (Lvl {level} -> {level + 1})", font=f_bar, fill=TEXT_MUTED)
    xp_lbl = f"{xp_into:,} / {xp_needed:,} XP ({int(pct * 100)}%)"
    try:
        lbl_bbox = draw.textbbox((0, 0), xp_lbl, font=f_bar)
        lbl_w = lbl_bbox[2] - lbl_bbox[0]
    except Exception:
        lbl_w = len(xp_lbl) * 8
    draw.text((pb_x + pb_w - lbl_w, pb_y - 22), xp_lbl, font=f_bar, fill=TEXT_SUB)
    _draw_progress_bar(draw, pb_x, pb_y, pb_w, pb_h, pct, tier_rgba, BAR_BG, radius=5)

    # 3 Main Cards (Study Time, Focus/XP, Coins)
    card_w = 348
    card_h = 200
    c1_x, c1_y = 50, 195
    c2_x = c1_x + card_w + 28
    c3_x = c2_x + card_w + 28

    f_card_tag = _get_font(13, bold=True)
    f_big_val = _get_font(38, bold=True)
    f_card_sub = _get_font(14, bold=False)

    # Card 1: Total Study Time
    draw.rounded_rectangle([c1_x, c1_y, c1_x + card_w, c1_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, c1_x + 24, c1_y + 27, ACCENT_CYAN, radius=4)
    draw.text((c1_x + 36, c1_y + 20), "TOTAL STUDY TIME", font=f_card_tag, fill=ACCENT_CYAN)
    draw.text((c1_x + 22, c1_y + 50), _format_time(total_seconds), font=f_big_val, fill=TEXT_WHITE)
    draw.text((c1_x + 22, c1_y + 115), f"Today: {_format_time(today_seconds)}", font=f_card_sub, fill=ACCENT_GREEN if today_seconds > 0 else TEXT_MUTED)
    draw.text((c1_x + 22, c1_y + 142), f"This Week: {_format_time(week_seconds)}", font=f_card_sub, fill=TEXT_SUB)
    if in_session_seconds is not None:
        draw.rounded_rectangle([c1_x + card_w - 140, c1_y + 18, c1_x + card_w - 18, c1_y + 40], radius=6, fill=(6, 78, 59, 220))
        draw.text((c1_x + card_w - 132, c1_y + 23), "● ACTIVE NOW", font=_get_font(10, bold=True), fill=(52, 211, 153, 255))

    # Card 2: Experience & Focus
    draw.rounded_rectangle([c2_x, c1_y, c2_x + card_w, c1_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, c2_x + 24, c1_y + 27, ACCENT_PURPLE, radius=4)
    draw.text((c2_x + 36, c1_y + 20), "EXPERIENCE & FOCUS", font=f_card_tag, fill=ACCENT_PURPLE)
    xp_str = f"{total_xp:,} XP"
    draw.text((c2_x + 22, c1_y + 50), xp_str, font=f_big_val, fill=TEXT_WHITE)
    try:
        xp_bbox = draw.textbbox((c2_x + 22, c1_y + 50), xp_str, font=f_big_val)
        xp_w = xp_bbox[2] - xp_bbox[0]
    except Exception:
        xp_w = len(xp_str) * 20
    _paste_pixel_icon(img, "chronos_xp", c2_x + 22 + xp_w + 14, c1_y + 52, 34)
    draw.text((c2_x + 22, c1_y + 115), f"{sessions_count} Study Sessions Logged", font=f_card_sub, fill=TEXT_SUB)
    avg_m = (total_seconds // (sessions_count * 60)) if sessions_count > 0 else 0
    draw.text((c2_x + 22, c1_y + 142), f"Avg Session: {avg_m} minutes", font=f_card_sub, fill=TEXT_MUTED)

    # Card 3: Chronocoins & Stash
    draw.rounded_rectangle([c3_x, c1_y, c3_x + card_w, c1_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_badge_dot(draw, c3_x + 24, c1_y + 27, ACCENT_GOLD, radius=4)
    draw.text((c3_x + 36, c1_y + 20), "CHRONOCOINS & STASH", font=f_card_tag, fill=ACCENT_GOLD)
    coins_str = f"{coins:,}"
    draw.text((c3_x + 22, c1_y + 50), coins_str, font=f_big_val, fill=ACCENT_GOLD)
    try:
        coin_bbox = draw.textbbox((c3_x + 22, c1_y + 50), coins_str, font=f_big_val)
        coin_w = coin_bbox[2] - coin_bbox[0]
    except Exception:
        coin_w = len(coins_str) * 22
    _paste_pixel_icon(img, "chronocoin", c3_x + 22 + coin_w + 14, c1_y + 52, 36)
    draw.text((c3_x + 22, c1_y + 115), f"{candy:,} Candy in Event Stash", font=f_card_sub, fill=TEXT_WHITE)
    draw.text((c3_x + 22, c1_y + 142), "Ready for Halloween Shop", font=f_card_sub, fill=TEXT_MUTED)

    # 4 Bottom Micro-Panels
    panel_w = 254
    panel_h = 165
    p1_x, p_y = 50, 425
    p2_x = p1_x + panel_w + 28
    p3_x = p2_x + panel_w + 28
    p4_x = p3_x + panel_w + 28

    f_p_tag = _get_font(12, bold=True)
    f_p_val = _get_font(28, bold=True)
    f_p_sub = _get_font(13, bold=False)

    # Panel 1: Study Streak
    draw.rounded_rectangle([p1_x, p_y, p1_x + panel_w, p_y + panel_h], radius=14, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    _draw_badge_dot(draw, p1_x + 20, p_y + 22, ACCENT_ORANGE, radius=3)
    draw.text((p1_x + 30, p_y + 16), "STUDY STREAK", font=f_p_tag, fill=ACCENT_ORANGE)
    streak_str = f"{streak_days} Days"
    draw.text((p1_x + 18, p_y + 46), streak_str, font=f_p_val, fill=TEXT_WHITE)
    try:
        s_bbox = draw.textbbox((p1_x + 18, p_y + 46), streak_str, font=f_p_val)
        s_w = s_bbox[2] - s_bbox[0]
    except Exception:
        s_w = len(streak_str) * 16
    _paste_pixel_icon(img, "chronos_streak", p1_x + 18 + s_w + 10, p_y + 48, 26)
    draw.text((p1_x + 18, p_y + 105), f"Longest: {longest_streak} Days", font=f_p_sub, fill=TEXT_MUTED)

    # Panel 2: Top Subject
    subject_sec = subject_seconds or {}
    top_subject = "General"
    top_time = 0
    if subject_sec:
        top_k, top_v = max(subject_sec.items(), key=lambda kv: kv[1])
        top_subject = top_k.capitalize()
        top_time = top_v

    draw.rounded_rectangle([p2_x, p_y, p2_x + panel_w, p_y + panel_h], radius=14, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    _draw_badge_dot(draw, p2_x + 20, p_y + 22, ACCENT_CYAN, radius=3)
    draw.text((p2_x + 30, p_y + 16), "TOP SUBJECT", font=f_p_tag, fill=ACCENT_CYAN)
    draw.text((p2_x + 18, p_y + 46), top_subject, font=f_p_val, fill=TEXT_WHITE)
    draw.text((p2_x + 18, p_y + 105), f"Hours: {_format_time(top_time)}", font=f_p_sub, fill=TEXT_MUTED)

    # Panel 3: Achievements
    draw.rounded_rectangle([p3_x, p_y, p3_x + panel_w, p_y + panel_h], radius=14, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    _draw_badge_dot(draw, p3_x + 20, p_y + 22, ACCENT_PURPLE, radius=3)
    draw.text((p3_x + 30, p_y + 16), "ACHIEVEMENTS", font=f_p_tag, fill=ACCENT_PURPLE)
    draw.text((p3_x + 18, p_y + 46), f"{unlocked_achievements} / {total_achievements}", font=f_p_val, fill=TEXT_WHITE)
    pct_ach = (unlocked_achievements / total_achievements) if total_achievements > 0 else 0
    _draw_progress_bar(draw, p3_x + 18, p_y + 92, panel_w - 36, 6, pct_ach, ACCENT_PURPLE, radius=3)
    draw.text((p3_x + 18, p_y + 112), f"{int(pct_ach * 100)}% Completed", font=f_p_sub, fill=TEXT_MUTED)

    # Panel 4: Equipped Pet
    pet_name = "None"
    pet_sub = "Visit .petshop"
    if equipped_pet:
        pet_name = _sanitize_text(equipped_pet.get("nickname") or equipped_pet.get("species_id", "Pet").capitalize()) or "Pet"
        pet_sub = f"Level {equipped_pet.get('level', 1)} Companion"

    draw.rounded_rectangle([p4_x, p_y, p4_x + panel_w, p_y + panel_h], radius=14, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    _draw_badge_dot(draw, p4_x + 20, p_y + 22, ACCENT_GREEN, radius=3)
    draw.text((p4_x + 30, p_y + 16), "EQUIPPED PET", font=f_p_tag, fill=ACCENT_GREEN)
    draw.text((p4_x + 18, p_y + 46), pet_name[:12], font=f_p_val, fill=TEXT_WHITE)
    draw.text((p4_x + 18, p_y + 105), pet_sub, font=f_p_sub, fill=TEXT_MUTED)

    # Footer
    f_foot = _get_font(12, bold=False)
    draw.text((50, 642), "CHRONOS STUDY OS · IST TIMEZONE", font=f_foot, fill=(71, 85, 105, 255))
    draw.text((CARD_WIDTH - 280, 642), "OFFICIAL STUDY PROFILE · PAGE 1/4", font=f_foot, fill=(71, 85, 105, 255))

    return _export_png(img)


# Alias for backwards compatibility
render_stats_card_sync = render_overview_card_sync


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
        ("PHYSICS", ACCENT_CYAN, phy_sec, phy_pct, subject_details.get("physics", {})),
        ("CHEMISTRY", ACCENT_GREEN, chem_sec, chem_pct, subject_details.get("chemistry", {})),
        ("MATHEMATICS", ACCENT_PURPLE, mat_sec, mat_pct, subject_details.get("maths", {})),
    ]

    for idx, (s_name, s_color, s_sec, s_pct, s_data) in enumerate(pcm_items):
        px = 50 + idx * (pcm_w + 28)
        draw.rounded_rectangle([px, pcm_y, px + pcm_w, pcm_y + pcm_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
        draw.line([(px + 20, pcm_y), (px + pcm_w - 20, pcm_y)], fill=s_color, width=3)
        _draw_badge_dot(draw, px + 24, pcm_y + 24, s_color, radius=3)
        draw.text((px + 36, pcm_y + 18), s_name, font=_get_font(13, bold=True), fill=s_color)

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
# SHOP CARD & INVENTORY SATCHEL CARD GENERATORS
# ==============================================================================
SHOP_CARD_HEIGHT = 1100
INV_CARD_HEIGHT = 1100

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
        "icon": "xp_boost",
        "type": "BOOST CHARGES",
        "action": ".use sugar rush to activate 2x XP (60m)",
        "color": ACCENT_ROSE,
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


def render_shop_card_sync(
    user_coins: int,
    items: Optional[list[dict[str, Any]]] = None,
    page: int = 0,
    per_page: int = 6,
) -> bytes:
    """Synchronously renders the high-res 1200x1080 Shop catalog PNG with big pixel art icons."""
    img = Image.new("RGBA", (CARD_WIDTH, SHOP_CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Outer border & canvas
    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, SHOP_CARD_HEIGHT - 20], radius=24, fill=None, outline=(35, 43, 56, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=ACCENT_GOLD, width=4)

    # Prepare items
    if items is None:
        from utils.economy import SHOP_ITEMS, SHOP_ORDER
        items = []
        for num, item_id in enumerate(SHOP_ORDER, start=1):
            if item_id in SHOP_ITEMS:
                si = SHOP_ITEMS[item_id]
                itype = str(si.get("type", "item")).upper()
                if itype == "BOOST":
                    color = ACCENT_GREEN if "xp" in item_id else ACCENT_GOLD
                    icon = "xp_boost" if "xp" in item_id else "coin_boost"
                    tag = "BOOST CHARGES"
                elif itype == "CONSUMABLE":
                    color = ACCENT_PURPLE if "box" in item_id else ACCENT_CYAN
                    icon = "mystery_box" if "box" in item_id else "streak_freeze"
                    tag = "CONSUMABLE"
                elif itype == "TITLE":
                    color = (245, 158, 11, 255)
                    icon = "title_scroll"
                    tag = "PRESTIGE TITLE"
                else:
                    color = ACCENT_CYAN
                    icon = "mystery_box"
                    tag = "ITEM"
                items.append({
                    "id": item_id,
                    "num": num,
                    "name": si["name"],
                    "icon": icon,
                    "type": tag,
                    "desc": si.get("description", ""),
                    "price": si["price"],
                    "color": color,
                })

    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    curr_page = max(0, min(page, total_pages - 1))
    start_idx = curr_page * per_page
    page_items = items[start_idx : start_idx + per_page]

    # Top Header
    draw.ellipse([50, 42, 130, 122], fill=CARD_BG, outline=ACCENT_GOLD, width=2)
    _paste_pixel_icon(img, "chronocoin", 60, 52, 60)

    draw.text((148, 44), "CHRONOS COIN SHOP", font=_get_font(28, bold=True), fill=TEXT_WHITE)
    draw.text((148, 84), f"Page {curr_page + 1} of {total_pages} · Spend coins on boosts, streak freeze & prestige titles", font=_get_font(16, bold=False), fill=TEXT_MUTED)

    # Wallet Balance Pill
    wallet_w = 340
    wallet_h = 52
    w_x = CARD_WIDTH - 50 - wallet_w
    w_y = 52
    draw.rounded_rectangle([w_x, w_y, w_x + wallet_w, w_y + wallet_h], radius=12, fill=CARD_BG, outline=ACCENT_GOLD, width=2)
    _paste_pixel_icon(img, "chronocoin", w_x + 14, w_y + 10, 32)
    bal_str = f"{user_coins:,} Coins"
    draw.text((w_x + 58, w_y + 12), bal_str, font=_get_font(20, bold=True), fill=ACCENT_GOLD)

    # Pro-tip banner
    banner_y = 138
    banner_h = 56
    draw.rounded_rectangle([50, banner_y, CARD_WIDTH - 50, banner_y + banner_h], radius=12, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.ellipse([70, banner_y + 22, 82, banner_y + 34], fill=ACCENT_GOLD)
    draw.text((92, banner_y + 18), "QUICK PURCHASE:", font=_get_font(14, bold=True), fill=ACCENT_GOLD)
    draw.text((250, banner_y + 19), "Use .buy <item> [qty] or select an item from the menu below to purchase!", font=_get_font(15, bold=False), fill=TEXT_SUB)

    # 2-Column Grid (3 rows x 2 cols = 6 slots per page)
    grid_y = 212
    slot_w = 525
    slot_h = 242
    col_xs = [50, 625]

    for idx in range(6):
        col = idx % 2
        row = idx // 2
        sx = col_xs[col]
        sy = grid_y + row * (slot_h + 22)

        if idx < len(page_items):
            item = page_items[idx]

            # Tile Card
            draw.rounded_rectangle([sx, sy, sx + slot_w, sy + slot_h], radius=18, fill=CARD_BG, outline=CARD_BORDER, width=1)
            # Glowing accent strip & top accent line
            draw.rounded_rectangle([sx, sy, sx + 6, sy + slot_h], radius=3, fill=item["color"])
            draw.line([(sx + 24, sy), (sx + slot_w - 24, sy)], fill=item["color"], width=2)

            # Big 96x96 Icon Frame with 76x76 Pixel Art Icon
            ix = sx + 22
            iy = sy + 38
            frame_size = 96
            draw.rounded_rectangle(
                [ix, iy, ix + frame_size, iy + frame_size],
                radius=16,
                fill=(15, 23, 42, 255),
                outline=(item["color"][0], item["color"][1], item["color"][2], 140),
                width=2,
            )
            _paste_pixel_icon(img, item["icon"], ix + 10, iy + 10, 76)

            # Price Badge (Bottom Right of slot)
            price_str = f"{item['price']:,} Coins"
            p_font = _get_font(19, bold=True)
            p_bbox = draw.textbbox((0, 0), price_str, font=p_font)
            pw = p_bbox[2] - p_bbox[0]
            draw.rounded_rectangle(
                [sx + slot_w - pw - 56, sy + slot_h - 48, sx + slot_w - 18, sy + slot_h - 14],
                radius=10,
                fill=(30, 41, 59, 240),
                outline=ACCENT_GOLD,
                width=1,
            )
            _paste_pixel_icon(img, "chronocoin", sx + slot_w - pw - 48, sy + slot_h - 42, 22)
            draw.text((sx + slot_w - pw - 20, sy + slot_h - 41), price_str, font=p_font, fill=ACCENT_GOLD)

            # Info text block
            tx = sx + 138
            name_str = f"{item['num']}. {item['name']}"
            if len(name_str) > 23:
                name_str = name_str[:21] + "..."
            draw.text((tx, sy + 22), name_str, font=_get_font(26, bold=True), fill=TEXT_WHITE)

            # Type Pill
            tag_str = item["type"]
            f_tag = _get_font(13, bold=True)
            t_bbox = draw.textbbox((0, 0), tag_str, font=f_tag)
            tw = t_bbox[2] - t_bbox[0]
            draw.rounded_rectangle([tx, sy + 60, tx + tw + 16, sy + 84], radius=6, fill=(item["color"][0], item["color"][1], item["color"][2], 40))
            draw.text((tx + 8, sy + 63), tag_str, font=f_tag, fill=item["color"])

            # Description (wrapped)
            desc_lines = _wrap_text_lines(item["desc"], max_chars=34, max_lines=2)
            ay = sy + 98
            for line in desc_lines:
                draw.text((tx, ay), line, font=_get_font(16, bold=False), fill=TEXT_SUB)
                ay += 26
        else:
            # Empty slot
            draw.rounded_rectangle([sx, sy, sx + slot_w, sy + slot_h], radius=18, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
            draw.text((sx + 175, sy + 105), "[ RESERVED SLOT ]", font=_get_font(15, bold=True), fill=(71, 85, 105, 255))

    # Footer
    fy = SHOP_CARD_HEIGHT - 55
    draw.text((50, fy), "COMMAND: .buy <number_or_name> [quantity]  •  Example: .buy 1 3 or .buy freeze", font=_get_font(15, bold=True), fill=TEXT_SUB)
    draw.text((CARD_WIDTH - 290, fy), f"PAGE {curr_page + 1} OF {total_pages} · CHRONOS OS", font=_get_font(14, bold=True), fill=TEXT_MUTED)

    return _export_png(img)


def render_food_shop_card_sync(
    tier: str,
    user_coins: int,
    owned_food: Optional[dict[str, int]] = None,
    page: int = 0,
    per_page: int = 6,
) -> bytes:
    """Synchronously renders the high-res 1200x1100 Food Shop catalog PNG with authentic pixel art food sprites."""
    from utils.food import FOODS, FOODS_BY_TIER, FOOD_TIER_INFO

    img = Image.new("RGBA", (CARD_WIDTH, SHOP_CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    clean_tier = tier.lower().strip()
    if clean_tier not in FOODS_BY_TIER:
        clean_tier = "snack"

    tier_info = FOOD_TIER_INFO.get(clean_tier, {"label": clean_tier.title(), "color": 0x34D399})
    t_color_int = tier_info["color"]
    t_color = ((t_color_int >> 16) & 0xFF, (t_color_int >> 8) & 0xFF, t_color_int & 0xFF, 255)

    # Outer border & canvas
    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, SHOP_CARD_HEIGHT - 20], radius=24, fill=None, outline=(35, 43, 56, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=t_color, width=4)

    tier_food_ids = FOODS_BY_TIER.get(clean_tier, [])
    total_items = len(tier_food_ids)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    curr_page = max(0, min(page, total_pages - 1))
    start_idx = curr_page * per_page
    page_ids = tier_food_ids[start_idx : start_idx + per_page]

    if owned_food is None:
        owned_food = {}

    # Top Header
    draw.ellipse([50, 42, 130, 122], fill=CARD_BG, outline=t_color, width=2)
    first_icon = page_ids[0] if page_ids else "apple_pie"
    _paste_pixel_icon(img, f"food/{first_icon}", 60, 52, 60)

    draw.text((148, 44), f"PET BAKERY — {tier_info['label'].upper()} TIER", font=_get_font(28, bold=True), fill=TEXT_WHITE)
    draw.text((148, 84), f"Page {curr_page + 1} of {total_pages} · Feeds your pet companion for massive XP and evolutions", font=_get_font(16, bold=False), fill=TEXT_MUTED)

    # Wallet Balance Pill
    wallet_w = 340
    wallet_h = 52
    w_x = CARD_WIDTH - 50 - wallet_w
    w_y = 52
    draw.rounded_rectangle([w_x, w_y, w_x + wallet_w, w_y + wallet_h], radius=12, fill=CARD_BG, outline=ACCENT_GOLD, width=2)
    _paste_pixel_icon(img, "chronocoin", w_x + 14, w_y + 10, 32)
    bal_str = f"{user_coins:,} Coins"
    draw.text((w_x + 58, w_y + 12), bal_str, font=_get_font(20, bold=True), fill=ACCENT_GOLD)

    # Pro-tip banner
    banner_y = 138
    banner_h = 56
    draw.rounded_rectangle([50, banner_y, CARD_WIDTH - 50, banner_y + banner_h], radius=12, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.ellipse([70, banner_y + 22, 82, banner_y + 34], fill=t_color)
    draw.text((92, banner_y + 18), "PET NUTRITION PRO-TIP:", font=_get_font(14, bold=True), fill=t_color)
    draw.text((295, banner_y + 19), "Use .buyfood <item> [qty] to purchase or tap quick-buy buttons below! Feed with .feed", font=_get_font(15, bold=False), fill=TEXT_SUB)

    # 2-Column Grid (3 rows x 2 cols = 6 slots per page)
    grid_y = 212
    slot_w = 525
    slot_h = 242
    col_xs = [50, 625]

    for idx in range(6):
        col = idx % 2
        row = idx // 2
        sx = col_xs[col]
        sy = grid_y + row * (slot_h + 22)

        if idx < len(page_ids):
            fid = page_ids[idx]
            food = FOODS[fid]
            have_qty = owned_food.get(fid, 0)

            # Tile Card
            draw.rounded_rectangle([sx, sy, sx + slot_w, sy + slot_h], radius=18, fill=CARD_BG, outline=CARD_BORDER, width=1)
            # Glowing accent strip & top accent line
            draw.rounded_rectangle([sx, sy, sx + 6, sy + slot_h], radius=3, fill=t_color)
            draw.line([(sx + 24, sy), (sx + slot_w - 24, sy)], fill=t_color, width=2)

            # Big 96x96 Icon Frame with 76x76 Pixel Art Icon
            ix = sx + 22
            iy = sy + 38
            frame_size = 96
            draw.rounded_rectangle(
                [ix, iy, ix + frame_size, iy + frame_size],
                radius=16,
                fill=(15, 23, 42, 255),
                outline=(t_color[0], t_color[1], t_color[2], 140),
                width=2,
            )
            _paste_pixel_icon(img, f"food/{fid}", ix + 10, iy + 10, 76)

            # Owned Pill (Top Right)
            if have_qty > 0:
                own_str = f"OWNED: ×{have_qty:,}"
                o_font = _get_font(13, bold=True)
                o_bbox = draw.textbbox((0, 0), own_str, font=o_font)
                ow = o_bbox[2] - o_bbox[0]
                draw.rounded_rectangle(
                    [sx + slot_w - ow - 28, sy + 18, sx + slot_w - 16, sy + 44],
                    radius=6,
                    fill=(30, 41, 59, 240),
                    outline=(t_color[0], t_color[1], t_color[2], 160),
                    width=1,
                )
                draw.text((sx + slot_w - ow - 22, sy + 22), own_str, font=o_font, fill=t_color)

            # Price Badge (Bottom Right of slot)
            price_str = f"{food['cost']:,} Coins"
            p_font = _get_font(19, bold=True)
            p_bbox = draw.textbbox((0, 0), price_str, font=p_font)
            pw = p_bbox[2] - p_bbox[0]
            draw.rounded_rectangle(
                [sx + slot_w - pw - 56, sy + slot_h - 48, sx + slot_w - 18, sy + slot_h - 14],
                radius=10,
                fill=(30, 41, 59, 240),
                outline=ACCENT_GOLD,
                width=1,
            )
            _paste_pixel_icon(img, "chronocoin", sx + slot_w - pw - 48, sy + slot_h - 42, 22)
            draw.text((sx + slot_w - pw - 20, sy + slot_h - 41), price_str, font=p_font, fill=ACCENT_GOLD)

            # Info text block
            tx = sx + 138
            food_name = food["name"]
            if len(food_name) > 21:
                food_name = food_name[:19] + "..."
            draw.text((tx, sy + 22), food_name, font=_get_font(26, bold=True), fill=TEXT_WHITE)

            # XP Pill
            tag_str = f"+{food['xp']:,} PET XP"
            f_tag = _get_font(13, bold=True)
            t_bbox = draw.textbbox((0, 0), tag_str, font=f_tag)
            tw = t_bbox[2] - t_bbox[0]
            draw.rounded_rectangle([tx, sy + 60, tx + tw + 16, sy + 84], radius=6, fill=(t_color[0], t_color[1], t_color[2], 40))
            draw.text((tx + 8, sy + 63), tag_str, font=f_tag, fill=t_color)

            # Subtitle
            sub_txt = f"Feeds active pet • Boosts happiness & level"
            draw.text((tx, sy + 98), sub_txt, font=_get_font(16, bold=False), fill=TEXT_SUB)
            draw.text((tx, sy + 124), f"Quick command: .feed {fid}", font=_get_font(14, bold=False), fill=TEXT_MUTED)
        else:
            # Empty slot
            draw.rounded_rectangle([sx, sy, sx + slot_w, sy + slot_h], radius=18, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
            draw.text((sx + 175, sy + 105), "[ RESERVED SHELF ]", font=_get_font(15, bold=True), fill=(71, 85, 105, 255))

    # Footer
    fy = SHOP_CARD_HEIGHT - 55
    draw.text((50, fy), f"COMMAND: .buyfood <item> [qty]  •  Example: .buyfood pizza 3 or .buyfood bread", font=_get_font(15, bold=True), fill=TEXT_SUB)
    draw.text((CARD_WIDTH - 310, fy), f"{tier_info['label'].upper()} · PAGE {curr_page + 1}/{total_pages} · CHRONOS", font=_get_font(14, bold=True), fill=TEXT_MUTED)

    return _export_png(img)


def render_candy_shop_card_sync(
    user_candy: int,
    owned_titles: Optional[set[str]] = None,
    owned_pets: Optional[set[str]] = None,
    sugar_rush_qty: int = 0,
) -> bytes:
    """Synchronously renders the high-res 1200x1100 Halloween Candy Shop catalog PNG."""
    from utils.halloween import CANDY_SHOP_ITEMS, CANDY_SHOP_ORDER

    img = Image.new("RGBA", (CARD_WIDTH, SHOP_CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    accent_orange = (255, 117, 24, 255)
    accent_purple = (168, 85, 247, 255)

    # Outer border & canvas
    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, SHOP_CARD_HEIGHT - 20], radius=24, fill=None, outline=(35, 43, 56, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=accent_orange, width=4)

    if owned_titles is None:
        owned_titles = set()
    if owned_pets is None:
        owned_pets = set()

    # Top Header
    draw.ellipse([50, 42, 130, 122], fill=CARD_BG, outline=accent_orange, width=2)
    _paste_pixel_icon(img, "mystery_box", 60, 52, 60)

    draw.text((148, 44), "THE HALLOWEEN CANDY BAZAAR", font=_get_font(28, bold=True), fill=TEXT_WHITE)
    draw.text((148, 84), "Limited Event Catalog · Spend collected treats on exclusive unlocks, pets & boosts", font=_get_font(16, bold=False), fill=TEXT_MUTED)

    # Wallet Balance Pill
    wallet_w = 320
    wallet_h = 52
    w_x = CARD_WIDTH - 50 - wallet_w
    w_y = 52
    draw.rounded_rectangle([w_x, w_y, w_x + wallet_w, w_y + wallet_h], radius=12, fill=CARD_BG, outline=(244, 114, 182, 255), width=2)
    bal_str = f"{user_candy:,} 🍬 Candy"
    draw.text((w_x + 36, w_y + 12), bal_str, font=_get_font(20, bold=True), fill=(244, 114, 182, 255))

    # Pro-tip banner
    banner_y = 138
    banner_h = 56
    draw.rounded_rectangle([50, banner_y, CARD_WIDTH - 50, banner_y + banner_h], radius=12, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.ellipse([70, banner_y + 22, 82, banner_y + 34], fill=accent_orange)
    draw.text((92, banner_y + 18), "HALLOWEEN REWARDS PRO-TIP:", font=_get_font(14, bold=True), fill=accent_orange)
    draw.text((320, banner_y + 19), "Earn Candy by studying (.start), opening Hallo-Boxes (.openbox), and pass levels!", font=_get_font(15, bold=False), fill=TEXT_SUB)

    # 4 Big Tiles (2 cols x 2 rows)
    grid_y = 216
    slot_w = 525
    slot_h = 360
    col_xs = [50, 625]

    for idx, item_key in enumerate(CANDY_SHOP_ORDER):
        if idx >= 4:
            break
        item = CANDY_SHOP_ITEMS[item_key]
        col = idx % 2
        row = idx // 2
        sx = col_xs[col]
        sy = grid_y + row * (slot_h + 30)

        # Determine theme color & icon
        if item_key == "pumpkaboo":
            t_color = accent_orange
            icon_name = "mystery_box"
            tag_label = "EVENT-EXCLUSIVE PET"
            is_owned = "pumpkaboo" in owned_pets
            own_badge = "🐾 UNLOCKED" if is_owned else None
        elif item_key == "sugar_rush":
            t_color = (251, 191, 36, 255)
            icon_name = "xp_boost"
            tag_label = "EVENT CONSUMABLE"
            own_badge = f"OWNED: ×{sugar_rush_qty:,}" if sugar_rush_qty > 0 else None
        else:
            t_color = accent_purple if "inorganic" in item_key else (56, 189, 248, 255)
            icon_name = "title_scroll"
            tag_label = "PRESTIGE TITLE"
            t_title = item.get("title_text", item_key)
            is_owned = item_key in owned_titles or t_title in owned_titles
            own_badge = "✅ OWNED" if is_owned else None

        # Tile Card
        draw.rounded_rectangle([sx, sy, sx + slot_w, sy + slot_h], radius=20, fill=CARD_BG, outline=CARD_BORDER, width=1)
        # Glowing accent strip & top accent line
        draw.rounded_rectangle([sx, sy, sx + 6, sy + slot_h], radius=3, fill=t_color)
        draw.line([(sx + 24, sy), (sx + slot_w - 24, sy)], fill=t_color, width=2)

        # Big 104x104 Icon Frame with 82x82 Pixel Art Icon
        ix = sx + 26
        iy = sy + 44
        frame_size = 104
        draw.rounded_rectangle(
            [ix, iy, ix + frame_size, iy + frame_size],
            radius=18,
            fill=(15, 23, 42, 255),
            outline=(t_color[0], t_color[1], t_color[2], 140),
            width=2,
        )
        _paste_pixel_icon(img, icon_name, ix + 11, iy + 11, 82)

        # Owned Pill (Top Right)
        if own_badge:
            o_font = _get_font(14, bold=True)
            o_bbox = draw.textbbox((0, 0), own_badge, font=o_font)
            ow = o_bbox[2] - o_bbox[0]
            draw.rounded_rectangle(
                [sx + slot_w - ow - 28, sy + 20, sx + slot_w - 16, sy + 50],
                radius=8,
                fill=(30, 41, 59, 240),
                outline=(t_color[0], t_color[1], t_color[2], 160),
                width=1,
            )
            draw.text((sx + slot_w - ow - 22, sy + 24), own_badge, font=o_font, fill=t_color)

        # Price Badge (Bottom Right)
        price_str = f"{item['candy_price']:,} Candy"
        p_font = _get_font(21, bold=True)
        p_bbox = draw.textbbox((0, 0), price_str, font=p_font)
        pw = p_bbox[2] - p_bbox[0]
        draw.rounded_rectangle(
            [sx + slot_w - pw - 48, sy + slot_h - 56, sx + slot_w - 18, sy + slot_h - 16],
            radius=12,
            fill=(30, 41, 59, 240),
            outline=(244, 114, 182, 255),
            width=1,
        )
        draw.text((sx + slot_w - pw - 38, sy + slot_h - 48), price_str, font=p_font, fill=(244, 114, 182, 255))

        # Info text block
        tx = sx + 148
        item_name = item["name"]
        draw.text((tx, sy + 28), item_name, font=_get_font(26, bold=True), fill=TEXT_WHITE)

        # Type Pill
        f_tag = _get_font(13, bold=True)
        t_bbox = draw.textbbox((0, 0), tag_label, font=f_tag)
        tw = t_bbox[2] - t_bbox[0]
        draw.rounded_rectangle([tx, sy + 68, tx + tw + 18, sy + 94], radius=6, fill=(t_color[0], t_color[1], t_color[2], 40))
        draw.text((tx + 9, sy + 71), tag_label, font=f_tag, fill=t_color)

        # Description (wrapped)
        desc_lines = _wrap_text_lines(item["description"], max_chars=34, max_lines=4)
        ay = sy + 112
        for line in desc_lines:
            draw.text((tx, ay), line, font=_get_font(16, bold=False), fill=TEXT_SUB)
            ay += 26

        # Command hint
        draw.text((26 + sx, sy + slot_h - 44), f"Command: .buycandy {item_key}", font=_get_font(14, bold=False), fill=TEXT_MUTED)

    # Footer
    fy = SHOP_CARD_HEIGHT - 55
    draw.text((50, fy), "COMMAND: .buycandy <item> [qty]  •  Example: .buycandy pumpkaboo or .buycandy sugar 3", font=_get_font(15, bold=True), fill=TEXT_SUB)
    draw.text((CARD_WIDTH - 290, fy), "HALLOWEEN 2026 · CHRONOS", font=_get_font(14, bold=True), fill=TEXT_MUTED)

    return _export_png(img)


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
    """Synchronously renders the high-res 1200x880 Inventory / Bag card PNG with 2-column big cards and pagination."""
    img = Image.new("RGBA", (CARD_WIDTH, INV_CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    clean_tier = tier_name.split()[-1].lower() if tier_name else "iron"
    tier_rgb = TIER_COLORS.get(clean_tier, (148, 163, 184))
    tier_rgba = (*tier_rgb, 255)

    # Outer border & canvas
    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, INV_CARD_HEIGHT - 20], radius=20, fill=None, outline=(30, 41, 59, 255), width=2)
    draw.line([(50, 20), (CARD_WIDTH - 50, 20)], fill=ACCENT_CYAN, width=4)

    # Collect valid items
    valid_items = [(k, v) for k, v in inventory.items() if v > 0]
    total_items = len(valid_items)
    total_qty = sum(v for _, v in valid_items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    curr_page = max(0, min(page, total_pages - 1))

    # Slice for current page
    start_idx = curr_page * per_page
    page_items = valid_items[start_idx : start_idx + per_page]

    # Header
    av_size = 76
    av_x, av_y = 50, 40
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

    clean_disp = _sanitize_text(display_name) or "Candidate"
    draw.text((av_x + av_size + 20, av_y + 4), f"{clean_disp.upper()}'S SATCHEL & INVENTORY", font=_get_font(26, bold=True), fill=TEXT_WHITE)

    sub_parts = [
        f"Page {curr_page + 1} of {total_pages}",
        f"{total_items} Unique ({total_qty:,} Total Items)",
    ]
    if equipped_title:
        sub_parts.append(f"Title: \"{_sanitize_text(equipped_title)}\"")
    draw.text((av_x + av_size + 20, av_y + 42), " · ".join(sub_parts), font=_get_font(15, bold=False), fill=TEXT_MUTED)

    # Wallet Badges on Top Right
    w_coin_str = f"{coins:,}"
    draw.rounded_rectangle([CARD_WIDTH - 390, av_y + 8, CARD_WIDTH - 215, av_y + 54], radius=10, fill=CARD_BG, outline=ACCENT_GOLD, width=1)
    _paste_pixel_icon(img, "chronocoin", CARD_WIDTH - 380, av_y + 14, 28)
    draw.text((CARD_WIDTH - 344, av_y + 17), w_coin_str, font=_get_font(18, bold=True), fill=ACCENT_GOLD)

    draw.rounded_rectangle([CARD_WIDTH - 200, av_y + 8, CARD_WIDTH - 50, av_y + 54], radius=10, fill=CARD_BG, outline=(236, 72, 153, 255), width=1)
    draw.text((CARD_WIDTH - 190, av_y + 17), f"{candy:,} Candy", font=_get_font(18, bold=True), fill=(244, 114, 182, 255))

    # Active Boosts Banner (y = 132)
    banner_y = 132
    banner_h = 52
    draw.rounded_rectangle([50, banner_y, CARD_WIDTH - 50, banner_y + banner_h], radius=12, fill=CARD_BG, outline=CARD_BORDER, width=1)
    if active_boosts:
        draw.ellipse([70, banner_y + 20, 82, banner_y + 32], fill=ACCENT_GREEN)
        draw.text((92, banner_y + 17), "ACTIVE BOOSTS RUNNING:", font=_get_font(13, bold=True), fill=ACCENT_GREEN)
        bx_curr = 295
        for b in active_boosts:
            rem = _format_time(b["remaining"])
            b_txt = f"{b['name']} ({b['mult']}x) — {rem} left"
            b_w = len(b_txt) * 9 + 20
            draw.rounded_rectangle([bx_curr, banner_y + 10, bx_curr + b_w, banner_y + banner_h - 10], radius=6, fill=(30, 41, 59, 200))
            draw.text((bx_curr + 10, banner_y + 16), b_txt, font=_get_font(13, bold=True), fill=TEXT_WHITE)
            bx_curr += b_w + 15
    else:
        draw.ellipse([70, banner_y + 20, 82, banner_y + 32], fill=(100, 116, 139, 255))
        draw.text((92, banner_y + 17), "NO ACTIVE BOOSTS", font=_get_font(13, bold=True), fill=TEXT_MUTED)
        draw.text((250, banner_y + 18), "Activate an XP or Coin boost from your inventory below with .use <item>", font=_get_font(14, bold=False), fill=TEXT_SUB)

    # 2-Column Spacious Grid (2 cols x 3 rows = 6 items per page)
    grid_y = 212
    slot_w = 525
    slot_h = 242
    col_xs = [50, 625]

    for idx in range(6):
        col = idx % 2
        row = idx // 2
        sx = col_xs[col]
        sy = grid_y + row * (slot_h + 22)

        if idx < len(page_items):
            i_id, qty = page_items[idx]
            meta = get_item_display_meta(i_id)

            # Slot card
            draw.rounded_rectangle([sx, sy, sx + slot_w, sy + slot_h], radius=18, fill=CARD_BG, outline=CARD_BORDER, width=1)
            # Glowing accent strip & top accent line
            draw.rounded_rectangle([sx, sy, sx + 6, sy + slot_h], radius=3, fill=meta["color"])
            draw.line([(sx + 24, sy), (sx + slot_w - 24, sy)], fill=meta["color"], width=2)

            # Big Icon Frame (96x96 with 76x76 pixel art)
            ix = sx + 22
            iy = sy + 38
            frame_size = 96
            draw.rounded_rectangle(
                [ix, iy, ix + frame_size, iy + frame_size],
                radius=16,
                fill=(15, 23, 42, 255),
                outline=(meta["color"][0], meta["color"][1], meta["color"][2], 140),
                width=2,
            )
            _paste_pixel_icon(img, meta["icon"], ix + 10, iy + 10, 76)

            # Quantity pill (Top Right)
            qty_str = f"×{qty:,}"
            q_font = _get_font(22, bold=True)
            q_bbox = draw.textbbox((0, 0), qty_str, font=q_font)
            qw = q_bbox[2] - q_bbox[0]
            draw.rounded_rectangle(
                [sx + slot_w - qw - 32, sy + 18, sx + slot_w - 16, sy + 52],
                radius=8,
                fill=(30, 41, 59, 240),
                outline=(meta["color"][0], meta["color"][1], meta["color"][2], 160),
                width=1,
            )
            draw.text((sx + slot_w - qw - 24, sy + 22), qty_str, font=q_font, fill=meta["color"])

            # Info text block
            tx = sx + 138
            item_name = meta["name"]
            if len(item_name) > 23:
                item_name = item_name[:21] + "..."
            draw.text((tx, sy + 22), item_name, font=_get_font(26, bold=True), fill=TEXT_WHITE)

            # Type Pill
            tag_str = meta["type"]
            f_tag = _get_font(13, bold=True)
            t_bbox = draw.textbbox((0, 0), tag_str, font=f_tag)
            tw = t_bbox[2] - t_bbox[0]
            draw.rounded_rectangle([tx, sy + 60, tx + tw + 16, sy + 84], radius=6, fill=(meta["color"][0], meta["color"][1], meta["color"][2], 40))
            draw.text((tx + 8, sy + 63), tag_str, font=f_tag, fill=meta["color"])

            # Subtitle / Action lines
            action_lines = _wrap_text_lines(meta["action"], max_chars=34, max_lines=2)
            ay = sy + 98
            for line in action_lines:
                draw.text((tx, ay), line, font=_get_font(16, bold=False), fill=TEXT_SUB)
                ay += 26
        else:
            # Empty slot
            draw.rounded_rectangle([sx, sy, sx + slot_w, sy + slot_h], radius=18, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
            draw.text((sx + 165, sy + 105), "[ EMPTY SATCHEL SLOT ]", font=_get_font(15, bold=True), fill=(71, 85, 105, 255))

    # Footer
    fy = INV_CARD_HEIGHT - 55
    draw.text((50, fy), "TIPS: .use <boost> to activate  •  .openbox to roll  •  .settitle to equip", font=_get_font(15, bold=True), fill=TEXT_SUB)
    draw.text((CARD_WIDTH - 290, fy), f"PAGE {curr_page + 1} OF {total_pages} · CHRONOS OS", font=_get_font(14, bold=True), fill=TEXT_MUTED)

    return _export_png(img)


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


