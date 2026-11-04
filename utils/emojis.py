"""Unique Discord custom emoji helpers with Unicode fallbacks.

If custom emojis are uploaded to the bot's server (or set via environment variables),
these helpers will automatically return the custom emoji string; otherwise,
they cleanly fall back to default Unicode emojis.
"""
from __future__ import annotations

import os
from typing import Optional

import discord

# Fallback or configured custom emoji IDs/tags
_ENV_CHRONOCOIN = os.getenv("EMOJI_CHRONOCOIN")
_ENV_XP = os.getenv("EMOJI_XP")
_ENV_STREAK = os.getenv("EMOJI_STREAK")


def coin(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chronocoin emoji."""
    if _ENV_CHRONOCOIN:
        return _ENV_CHRONOCOIN
    if guild:
        e = discord.utils.get(guild.emojis, name="chronocoin")
        if e:
            return str(e)
    return "🪙"


def xp(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chronos XP crystal emoji."""
    if _ENV_XP:
        return _ENV_XP
    if guild:
        e = discord.utils.get(guild.emojis, name="chronos_xp") or discord.utils.get(guild.emojis, name="xp")
        if e:
            return str(e)
    return "⚡"


def streak(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chronos study flame emoji."""
    if _ENV_STREAK:
        return _ENV_STREAK
    if guild:
        e = discord.utils.get(guild.emojis, name="chronos_streak") or discord.utils.get(guild.emojis, name="streak")
        if e:
            return str(e)
    return "🔥"
