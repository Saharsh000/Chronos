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
_ENV_MYSTERY_BOX = os.getenv("EMOJI_MYSTERY_BOX")
_ENV_STREAK_FREEZE = os.getenv("EMOJI_STREAK_FREEZE")
_ENV_XP_BOOST = os.getenv("EMOJI_XP_BOOST")
_ENV_COIN_BOOST = os.getenv("EMOJI_COIN_BOOST")
_ENV_TITLE_SCROLL = os.getenv("EMOJI_TITLE_SCROLL")


def _find_emoji(names: tuple[str, ...], guild: Optional[discord.Guild] = None) -> Optional[discord.Emoji]:
    """Find a custom emoji by matching names in the guild or across the bot's connected guilds."""
    if not guild:
        return None
    # 1. Search in local guild emojis
    for name in names:
        e = discord.utils.get(guild.emojis, name=name)
        if e:
            return e
    # 2. Search across all emojis the bot has access to (ConnectionState)
    state = getattr(guild, "_state", None)
    if state and hasattr(state, "emojis"):
        for name in names:
            e = discord.utils.get(state.emojis, name=name)
            if e:
                return e
    return None


def coin(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chronocoin emoji."""
    if _ENV_CHRONOCOIN:
        return _ENV_CHRONOCOIN
    e = _find_emoji(("chronocoin", "chronocoins", "chronos_coin", "coin", "coins"), guild)
    if e:
        return str(e)
    return "🪙"


def xp(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chronos XP crystal emoji."""
    if _ENV_XP:
        return _ENV_XP
    e = _find_emoji(("chronos_xp", "chronoxp", "xp"), guild)
    if e:
        return str(e)
    return "⚡"


def streak(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chronos study flame emoji."""
    if _ENV_STREAK:
        return _ENV_STREAK
    e = _find_emoji(("chronos_streak", "streak", "fire"), guild)
    if e:
        return str(e)
    return "🔥"


def mystery_box(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Mystery Box emoji."""
    if _ENV_MYSTERY_BOX:
        return _ENV_MYSTERY_BOX
    e = _find_emoji(("mystery_box", "mysterybox", "box"), guild)
    if e:
        return str(e)
    return "🎁"


def streak_freeze(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Streak Freeze emoji."""
    if _ENV_STREAK_FREEZE:
        return _ENV_STREAK_FREEZE
    e = _find_emoji(("streak_freeze", "streakfreeze", "freeze"), guild)
    if e:
        return str(e)
    return "🧊"


def xp_boost(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique XP Boost potion emoji."""
    if _ENV_XP_BOOST:
        return _ENV_XP_BOOST
    e = _find_emoji(("xp_boost", "xpboost"), guild)
    if e:
        return str(e)
    return "⚡"


def coin_boost(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chronocoin Boost elixir emoji."""
    if _ENV_COIN_BOOST:
        return _ENV_COIN_BOOST
    e = _find_emoji(("coin_boost", "coinboost"), guild)
    if e:
        return str(e)
    return "💰"


def title_scroll(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Title Scroll deed emoji."""
    if _ENV_TITLE_SCROLL:
        return _ENV_TITLE_SCROLL
    e = _find_emoji(("title_scroll", "titlescroll", "scroll"), guild)
    if e:
        return str(e)
    return "📜"


def item(item_id: str, guild: Optional[discord.Guild] = None) -> str:
    """Return the custom emoji for any item id."""
    clean = item_id.lower().strip()
    if clean == "mystery_box":
        return mystery_box(guild)
    elif clean == "streak_freeze":
        return streak_freeze(guild)
    elif clean == "xp_boost" or clean == "sugar_rush":
        return xp_boost(guild)
    elif clean == "coin_boost":
        return coin_boost(guild)
    elif clean.startswith("title_"):
        return title_scroll(guild)
    return "📦"
