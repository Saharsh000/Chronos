"""Shared embed helpers so every command replies with a consistent look.

Per the project requirements, ALL bot output uses embeds - there is no
plain-text command response anywhere in this codebase.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from utils.achievements import Achievement

COLOR_PRIMARY = 0x5865F2  # Discord blurple
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C
COLOR_ERROR = 0xED4245
COLOR_LEVELUP = 0xF1C40F
COLOR_POMODORO_FOCUS = 0xE67E22
COLOR_POMODORO_BREAK = 0x2ECC71

FOOTER_TEXT = "Chronos \u00B7 Study & Activity Tracker"


def base_embed(
    title: str | None = None,
    description: str | None = None,
    color: int = COLOR_PRIMARY,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    embed.timestamp = discord.utils.utcnow()
    return embed


def error_embed(message: str) -> discord.Embed:
    return base_embed(title="\u26A0\uFE0F Error", description=message, color=COLOR_ERROR)


def success_embed(title: str, description: str | None = None) -> discord.Embed:
    return base_embed(title=f"\u2705 {title}", description=description, color=COLOR_SUCCESS)


def info_embed(title: str, description: str | None = None) -> discord.Embed:
    return base_embed(title=title, description=description, color=COLOR_PRIMARY)


def achievement_unlock_embed(member: discord.abc.User, achievements: list["Achievement"]) -> discord.Embed:
    """Shared "you just unlocked N achievements" embed, used whenever
    `Database.check_achievements()` returns something new - after a
    session ends, mid-session, after `.daily`, after opening a box,
    etc. (see cogs/sessions.py and cogs/economy.py)."""
    if len(achievements) == 1:
        a = achievements[0]
        embed = base_embed(
            title="\U0001F3C5 Achievement Unlocked!",
            description=f"{a.emoji} **{a.name}**\n{a.description}",
            color=COLOR_LEVELUP,
        )
    else:
        lines = [f"{a.emoji} **{a.name}** \u2014 {a.description}" for a in achievements]
        embed = base_embed(
            title=f"\U0001F3C5 {len(achievements)} Achievements Unlocked!",
            description="\n".join(lines),
            color=COLOR_LEVELUP,
        )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    return embed
