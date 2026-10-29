"""Shared embed helpers so every command replies with a consistent look.

Per the project requirements, ALL bot output uses embeds - there is no
plain-text command response anywhere in this codebase.

The palette below is the single source of truth for the bot's look.
Colors are grouped two ways: *semantic* (success/warning/error/info -
what happened) and *accent* (study/economy/pets/progress/social -
which part of the bot you're in). Prefer an accent color for a
feature's normal output and a semantic color for outcomes, so a green
embed always means "that worked" rather than "this is the shop".
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord

if TYPE_CHECKING:
    from utils.achievements import Achievement

# --- Semantic ---------------------------------------------------------- #
COLOR_PRIMARY = 0x6366F1   # indigo - default/neutral
COLOR_SUCCESS = 0x22C55E   # green  - an action completed
COLOR_WARNING = 0xF59E0B   # amber  - heads-up, cooldowns, whiffs
COLOR_ERROR = 0xEF4444     # red    - something went wrong
COLOR_INFO = 0x38BDF8      # sky    - neutral information
COLOR_MUTED = 0x64748B     # slate  - empty states, disabled

# --- Accents (per feature area) ---------------------------------------- #
COLOR_LEVELUP = 0xFBBF24   # gold   - level ups, achievements, leaderboards
COLOR_STUDY = 0x818CF8     # periwinkle - sessions
COLOR_ECONOMY = 0xFACC15   # yellow - coins, shop
COLOR_PETS = 0xF472B6      # pink   - pets & food
COLOR_PROGRESS = 0x2DD4BF  # teal   - syllabus, chapters
COLOR_SOCIAL = 0xA78BFA    # violet - profiles, social

COLOR_POMODORO_FOCUS = 0xF97316  # orange
COLOR_POMODORO_BREAK = 0x14B8A6  # teal

FOOTER_TEXT = "Chronos \u00B7 Study & Activity Tracker"

# Shared progress-bar glyphs, so every bar in the bot looks the same.
BAR_FULL = "\u2588"
BAR_EMPTY = "\u2591"

DIVIDER = "\u2500" * 18

# --- Enhanced visual elements ------------------------------------------ #
DIVIDER_THIN = "\u2501" * 31
DIVIDER_DOTS = "\u00B7 " * 15
BULLET = "\u25B8"
SPARKLE = "\u2728"
ARROW_RIGHT = "\u25B9"

# Compact stat line: "Label \u00B7\u00B7\u00B7\u00B7\u00B7 Value"
def stat_line(label: str, value: str, width: int = 28) -> str:
    """Format a label-value pair with dot-fill for aligned stat displays."""
    dots_needed = max(2, width - len(label) - len(value))
    return f"**{label}** {'`\u00B7`' * dots_needed} {value}"

def section_header(emoji: str, title: str) -> str:
    """Return a visually distinct section header for embed descriptions."""
    return f"\n{emoji} **{title}**\n{DIVIDER_THIN}"


def bar(current: int, needed: int, length: int = 14) -> str:
    """Render a progress bar. Safe against zero/negative denominators."""
    if needed <= 0:
        ratio = 1.0
    else:
        ratio = max(0.0, min(1.0, current / needed))
    filled = int(round(ratio * length))
    return BAR_FULL * filled + BAR_EMPTY * (length - filled)


def base_embed(
    title: str | None = None,
    description: str | None = None,
    color: int = COLOR_PRIMARY,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    embed.timestamp = discord.utils.utcnow()
    return embed


def card_embed(
    title: str | None = None,
    description: str | None = None,
    color: int = COLOR_PRIMARY,
    thumbnail: Optional[str] = None,
) -> discord.Embed:
    """A compact embed for grid/carousel items (shop entries, pet
    cards). Deliberately has no footer or timestamp - those belong on
    the header embed of a multi-embed message, not on every tile."""
    embed = discord.Embed(title=title, description=description, color=color)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed


def error_embed(message: str) -> discord.Embed:
    return base_embed(title="\u26A0\uFE0F Error", description=message, color=COLOR_ERROR)


def success_embed(title: str, description: str | None = None) -> discord.Embed:
    return base_embed(title=f"\u2705 {title}", description=description, color=COLOR_SUCCESS)


def info_embed(title: str, description: str | None = None) -> discord.Embed:
    return base_embed(title=title, description=description, color=COLOR_INFO)


def warning_embed(title: str, description: str | None = None) -> discord.Embed:
    return base_embed(title=title, description=description, color=COLOR_WARNING)


def achievement_unlock_embed(member: discord.abc.User, achievements: list["Achievement"]) -> discord.Embed:
    """Shared "you just unlocked N achievements" embed, used whenever
    `Database.check_achievements()` returns something new - after a
    session ends, mid-session, after `.daily`, after opening a box,
    etc. (see cogs/sessions.py and cogs/economy.py). Each achievement
    also pays out coins (see utils/achievements.py `reward_coins`)."""
    if len(achievements) == 1:
        a = achievements[0]
        reward_line = f"\n\U0001FA99 +{a.reward_coins:,} coins" if a.reward_coins else ""
        embed = base_embed(
            title="\U0001F3C5 Achievement Unlocked!",
            description=f"{a.emoji} **{a.name}**\n{a.description}{reward_line}",
            color=COLOR_LEVELUP,
        )
    else:
        lines = [
            f"{a.emoji} **{a.name}** \u2014 {a.description}"
            + (f" (+{a.reward_coins:,} coins)" if a.reward_coins else "")
            for a in achievements
        ]
        total_coins = sum(a.reward_coins for a in achievements)
        footer_line = f"\n{DIVIDER}\n\U0001FA99 **+{total_coins:,} coins total**" if total_coins else ""
        embed = base_embed(
            title=f"\U0001F3C5 {len(achievements)} Achievements Unlocked!",
            description="\n".join(lines) + footer_line,
            color=COLOR_LEVELUP,
        )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    return embed
