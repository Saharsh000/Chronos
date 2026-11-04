"""High-resolution study stats image generator for `.stats` / `.profile`.

Generates an ultra-crisp, modern 1200x680 dark-themed card using Pillow.
Clean typography, high-contrast metrics, dynamic Tier color accents,
and zero cluttered AI artifacts.
"""
from __future__ import annotations

import io
import os
from typing import Any, Optional
from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 1200
CARD_HEIGHT = 680

# Dark obsidian theme palette
BG_COLOR = (11, 14, 20, 255)           # Deep slate / obsidian
CARD_BG = (20, 25, 34, 255)            # Elevated surface
CARD_BORDER = (45, 55, 72, 255)        # Subtle border
PANEL_BG = (16, 20, 28, 255)          # Micro card surface
PANEL_BORDER = (35, 43, 56, 255)      # Micro card border
TEXT_MUTED = (148, 163, 184, 255)      # Slate-400
TEXT_WHITE = (248, 250, 252, 255)      # Slate-50
TEXT_SUB = (203, 213, 225, 255)        # Slate-300
ACCENT_GOLD = (251, 191, 36, 255)      # Amber-400
ACCENT_GREEN = (16, 185, 129, 255)     # Emerald-500
ACCENT_CYAN = (56, 189, 248, 255)      # Sky-400
ACCENT_PURPLE = (167, 139, 250, 255)   # Violet-400
ACCENT_ORANGE = (249, 115, 22, 255)    # Orange-500

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


def render_stats_card_sync(
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
    """Synchronously renders the high-res 1200x680 stats card PNG."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 1. Determine Tier accent color
    clean_tier = tier_name.split()[-1].lower() if tier_name else "iron"
    tier_rgb = TIER_COLORS.get(clean_tier, (148, 163, 184))
    tier_rgba = (*tier_rgb, 255)

    # 2. Outer Card Border & Ambient Top Glow Line
    draw.rounded_rectangle([20, 20, CARD_WIDTH - 20, CARD_HEIGHT - 20], radius=20, fill=None, outline=(30, 41, 59, 255), width=2)
    # Sleek 4px glowing accent bar at the top of the card
    draw.rounded_rectangle([35, 20, CARD_WIDTH - 35, 25], radius=2, fill=tier_rgba)

    # 3. Avatar Rendering
    avatar_size = 96
    av_x, av_y = 50, 45
    if avatar_bytes:
        try:
            raw_av = Image.open(io.BytesIO(avatar_bytes))
            circle_av = _make_circular_avatar(raw_av, size=avatar_size)
            img.paste(circle_av, (av_x, av_y), mask=circle_av)
        except Exception:
            # Fallback avatar circle
            draw.ellipse([av_x, av_y, av_x + avatar_size, av_y + avatar_size], fill=(30, 41, 59, 255), outline=tier_rgba, width=3)
    else:
        # Fallback circle with initial
        draw.ellipse([av_x, av_y, av_x + avatar_size, av_y + avatar_size], fill=(30, 41, 59, 255), outline=tier_rgba, width=3)
        initial = (display_name[:1] or "C").upper()
        f_init = _get_font(42, bold=True)
        draw.text((av_x + 32, av_y + 24), initial, font=f_init, fill=TEXT_WHITE)

    # Avatar ring border
    draw.ellipse([av_x - 3, av_y - 3, av_x + avatar_size + 3, av_y + avatar_size + 3], outline=tier_rgba, width=3)

    # 4. Header Details: Display Name, Username, Title
    f_name = _get_font(34, bold=True)
    f_sub = _get_font(18, bold=False)
    f_badge = _get_font(15, bold=True)
    f_mono = _get_font(14, bold=True)

    name_x, name_y = 165, 46
    # Truncate display name if extremely long
    disp = display_name if len(display_name) <= 18 else display_name[:17] + "…"
    draw.text((name_x, name_y), disp, font=f_name, fill=TEXT_WHITE)

    user_text = f"@{username}" if username else ""
    draw.text((name_x, name_y + 40), user_text, font=f_sub, fill=TEXT_MUTED)

    # Equipped Title Pill
    if equipped_title:
        title_disp = f"“{equipped_title}”"
        pill_w = len(title_disp) * 9 + 20
        draw.rounded_rectangle([name_x, name_y + 68, name_x + pill_w, name_y + 92], radius=6, fill=(30, 27, 75, 255), outline=(99, 102, 241, 200), width=1)
        draw.text((name_x + 10, name_y + 72), title_disp, font=f_mono, fill=(199, 210, 254, 255))

    # 5. Header Right: Rank Pill, Level & Tier Pill, In-Session Dot
    rx = 1140
    # Tier & Level pill on top right
    tier_clean_title = tier_name.replace("⚙️", "").replace("🥉", "").replace("🥈", "").replace("🥇", "").replace("🔹", "").replace("💎", "").replace("🍃", "").replace("💀", "").replace("☀️", "").replace("🚀", "").strip().upper()
    level_badge_text = f"LVL {level} · {tier_clean_title}"
    badge_w = len(level_badge_text) * 10 + 24
    draw.rounded_rectangle([rx - badge_w, 48, rx, 80], radius=8, fill=CARD_BG, outline=tier_rgba, width=2)
    draw.text((rx - badge_w + 12, 55), level_badge_text, font=f_badge, fill=TEXT_WHITE)

    # Server Rank pill
    rank_str = f"RANK #{rank_position}" if rank_position else "UNRANKED"
    rank_w = len(rank_str) * 9 + 20
    draw.rounded_rectangle([rx - badge_w - rank_w - 12, 48, rx - badge_w - 12, 80], radius=8, fill=(30, 41, 59, 200), outline=(51, 65, 85, 255), width=1)
    draw.text((rx - badge_w - rank_w - 2, 56), rank_str, font=f_mono, fill=ACCENT_GOLD)

    # Active Session Indicator
    if in_session_seconds is not None:
        sess_text = f"IN FOCUS · {_format_time(in_session_seconds)}"
        sw = len(sess_text) * 8 + 30
        draw.rounded_rectangle([rx - sw, 92, rx, 118], radius=6, fill=(6, 78, 59, 200), outline=(16, 185, 129, 255), width=1)
        # Green pulsing dot
        draw.ellipse([rx - sw + 10, 101, rx - sw + 18, 109], fill=(52, 211, 153, 255))
        draw.text((rx - sw + 24, 98), sess_text, font=f_mono, fill=(167, 243, 208, 255))

    # 6. XP Progress Bar (Span full width)
    bar_x0, bar_y0 = 50, 160
    bar_w, bar_h = 1100, 14
    pct = min(1.0, max(0.0, xp_into / xp_needed)) if xp_needed > 0 else 1.0

    f_xp_lbl = _get_font(14, bold=True)
    draw.text((bar_x0, bar_y0 - 20), f"LEVEL PROGRESS (Lvl {level} → {level + 1})", font=f_xp_lbl, fill=TEXT_MUTED)
    prog_str = f"{xp_into:,} / {xp_needed:,} XP ({int(pct * 100)}%)"
    draw.text((bar_x0 + bar_w - len(prog_str) * 8 - 5, bar_y0 - 20), prog_str, font=f_xp_lbl, fill=TEXT_SUB)

    # Background track
    draw.rounded_rectangle([bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h], radius=7, fill=(30, 41, 59, 255))
    # Filled bar
    filled_w = max(14, int(bar_w * pct))
    draw.rounded_rectangle([bar_x0, bar_y0, bar_x0 + filled_w, bar_y0 + bar_h], radius=7, fill=tier_rgba)

    # 7. Big Three Hero Metric Cards
    card_w = 345
    card_h = 195
    c1_x, c1_y = 50, 205
    c2_x = c1_x + card_w + 32
    c3_x = c2_x + card_w + 32

    f_card_tag = _get_font(14, bold=True)
    f_big_val = _get_font(42, bold=True)
    f_card_sub = _get_font(15, bold=False)

    # Card 1: Total Study Time
    draw.rounded_rectangle([c1_x, c1_y, c1_x + card_w, c1_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.text((c1_x + 22, c1_y + 20), "⏱️ TOTAL STUDY TIME", font=f_card_tag, fill=ACCENT_CYAN)
    time_str = _format_time(total_seconds)
    draw.text((c1_x + 22, c1_y + 48), time_str, font=f_big_val, fill=TEXT_WHITE)
    draw.text((c1_x + 22, c1_y + 115), f"Today: {_format_time(today_seconds)}", font=f_card_sub, fill=ACCENT_GREEN)
    draw.text((c1_x + 22, c1_y + 145), f"This Week: {_format_time(week_seconds)}", font=f_card_sub, fill=TEXT_SUB)

    # Card 2: Total XP & Sessions
    draw.rounded_rectangle([c2_x, c1_y, c2_x + card_w, c1_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.text((c2_x + 22, c1_y + 20), "⚡ EXPERIENCE & FOCUS", font=f_card_tag, fill=ACCENT_PURPLE)
    xp_str = f"{total_xp:,} XP"
    draw.text((c2_x + 22, c1_y + 48), xp_str, font=f_big_val, fill=TEXT_WHITE)
    # Paste actual Chronos XP pixel art icon if available
    try:
        xp_bbox = draw.textbbox((c2_x + 22, c1_y + 48), xp_str, font=f_big_val)
        xp_w = xp_bbox[2] - xp_bbox[0]
    except Exception:
        xp_w = len(xp_str) * 20
    xp_icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "chronos_xp_128.png")
    if os.path.exists(xp_icon_path):
        try:
            with Image.open(xp_icon_path) as x_icon:
                x_icon = x_icon.convert("RGBA").resize((34, 34), Image.Resampling.NEAREST)
                img.paste(x_icon, (c2_x + 22 + xp_w + 14, c1_y + 50), x_icon)
        except Exception:
            pass
    draw.text((c2_x + 22, c1_y + 115), f"{sessions_count} Study Sessions Logged", font=f_card_sub, fill=TEXT_SUB)
    avg_m = (total_seconds // (sessions_count * 60)) if sessions_count > 0 else 0
    draw.text((c2_x + 22, c1_y + 145), f"Avg Session: {avg_m} minutes", font=f_card_sub, fill=TEXT_MUTED)

    # Card 3: Wealth & Seasonal Candy
    draw.rounded_rectangle([c3_x, c1_y, c3_x + card_w, c1_y + card_h], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.text((c3_x + 22, c1_y + 20), "💰 CHRONOCOINS & EVENT STASH", font=f_card_tag, fill=ACCENT_GOLD)
    coins_str = f"{coins:,}"
    draw.text((c3_x + 22, c1_y + 48), coins_str, font=f_big_val, fill=ACCENT_GOLD)
    # Paste actual Chronocoin pixel art icon next to coin value
    try:
        coin_bbox = draw.textbbox((c3_x + 22, c1_y + 48), coins_str, font=f_big_val)
        coin_w = coin_bbox[2] - coin_bbox[0]
    except Exception:
        coin_w = len(coins_str) * 22
    coin_icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "chronocoin_128.png")
    if os.path.exists(coin_icon_path):
        try:
            with Image.open(coin_icon_path) as c_icon:
                c_icon = c_icon.convert("RGBA").resize((36, 36), Image.Resampling.NEAREST)
                img.paste(c_icon, (c3_x + 22 + coin_w + 14, c1_y + 49), c_icon)
        except Exception:
            draw.text((c3_x + 22 + coin_w + 10, c1_y + 48), "🪙", font=f_big_val, fill=ACCENT_GOLD)
    else:
        draw.text((c3_x + 22 + coin_w + 10, c1_y + 48), "🪙", font=f_big_val, fill=ACCENT_GOLD)

    draw.text((c3_x + 22, c1_y + 115), f"🍬 {candy:,} Candy in Inventory", font=f_card_sub, fill=TEXT_WHITE)
    draw.text((c3_x + 22, c1_y + 145), "Ready for Halloween Shop", font=f_card_sub, fill=TEXT_MUTED)

    # 8. Bottom Micro-Panels (4 Columns)
    panel_w = 250
    panel_h = 160
    p1_x, p_y = 50, 430
    p2_x = p1_x + panel_w + 33
    p3_x = p2_x + panel_w + 33
    p4_x = p3_x + panel_w + 33

    f_p_tag = _get_font(13, bold=True)
    f_p_val = _get_font(28, bold=True)
    f_p_sub = _get_font(13, bold=False)

    # Panel 1: Study Streak
    draw.rounded_rectangle([p1_x, p_y, p1_x + panel_w, p_y + panel_h], radius=12, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    draw.text((p1_x + 18, p_y + 16), "🔥 STUDY STREAK", font=f_p_tag, fill=ACCENT_ORANGE)
    streak_str = f"{streak_days} Days"
    draw.text((p1_x + 18, p_y + 46), streak_str, font=f_p_val, fill=TEXT_WHITE)
    # Paste Minecraft Chronos Streak flame icon
    try:
        s_bbox = draw.textbbox((p1_x + 18, p_y + 46), streak_str, font=f_p_val)
        s_w = s_bbox[2] - s_bbox[0]
    except Exception:
        s_w = len(streak_str) * 16
    streak_icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "chronos_streak_128.png")
    if os.path.exists(streak_icon_path):
        try:
            with Image.open(streak_icon_path) as s_icon:
                s_icon = s_icon.convert("RGBA").resize((26, 26), Image.Resampling.NEAREST)
                img.paste(s_icon, (p1_x + 18 + s_w + 10, p_y + 48), s_icon)
        except Exception:
            pass
    draw.text((p1_x + 18, p_y + 105), f"Longest: {longest_streak} Days", font=f_p_sub, fill=TEXT_MUTED)

    # Panel 2: Subject Specialty
    subject_sec = subject_seconds or {}
    top_subject = "General"
    top_time = 0
    if subject_sec:
        top_k, top_v = max(subject_sec.items(), key=lambda kv: kv[1])
        top_subject = top_k.capitalize()
        top_time = top_v

    draw.rounded_rectangle([p2_x, p_y, p2_x + panel_w, p_y + panel_h], radius=12, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    draw.text((p2_x + 18, p_y + 16), "📚 TOP SUBJECT", font=f_p_tag, fill=ACCENT_CYAN)
    draw.text((p2_x + 18, p_y + 46), top_subject, font=f_p_val, fill=TEXT_WHITE)
    draw.text((p2_x + 18, p_y + 105), f"Hours: {_format_time(top_time)}", font=f_p_sub, fill=TEXT_MUTED)

    # Panel 3: Achievements
    draw.rounded_rectangle([p3_x, p_y, p3_x + panel_w, p_y + panel_h], radius=12, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    draw.text((p3_x + 18, p_y + 16), "🏆 ACHIEVEMENTS", font=f_p_tag, fill=ACCENT_PURPLE)
    draw.text((p3_x + 18, p_y + 46), f"{unlocked_achievements} / {total_achievements}", font=f_p_val, fill=TEXT_WHITE)
    pct_ach = int((unlocked_achievements / total_achievements) * 100) if total_achievements > 0 else 0
    draw.text((p3_x + 18, p_y + 105), f"{pct_ach}% Completed", font=f_p_sub, fill=TEXT_MUTED)

    # Panel 4: Equipped Pet
    pet_name = "None"
    pet_sub = "Visit .petshop"
    if equipped_pet:
        pet_name = equipped_pet.get("nickname") or equipped_pet.get("species_id", "Pet").capitalize()
        pet_sub = f"Level {equipped_pet.get('level', 1)}"

    draw.rounded_rectangle([p4_x, p_y, p4_x + panel_w, p_y + panel_h], radius=12, fill=PANEL_BG, outline=PANEL_BORDER, width=1)
    draw.text((p4_x + 18, p_y + 16), "🐾 EQUIPPED PET", font=f_p_tag, fill=ACCENT_GREEN)
    draw.text((p4_x + 18, p_y + 46), pet_name[:12], font=f_p_val, fill=TEXT_WHITE)
    draw.text((p4_x + 18, p_y + 105), pet_sub, font=f_p_sub, fill=TEXT_MUTED)

    # 9. Minimalist Footer
    f_foot = _get_font(12, bold=False)
    draw.text((50, 642), "CHRONOS STUDY OS · IST TIMEZONE", font=f_foot, fill=(71, 85, 105, 255))
    draw.text((CARD_WIDTH - 220, 642), "OFFICIAL STUDY PROFILE", font=f_foot, fill=(71, 85, 105, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
