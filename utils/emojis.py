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
    elif clean == "sugar_rush":
        return sugar_rush(guild)
    elif clean == "xp_boost":
        return xp_boost(guild)
    elif clean == "coin_boost":
        return coin_boost(guild)
    elif clean in ("candy", "halloween_candy", "spooky_candy"):
        return candy(guild)
    elif clean.startswith("title_"):
        return title_scroll(guild)
    return "📦"


def candy(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Halloween Candy Corn emoji."""
    e = _find_emoji(("halloween_candy", "candy", "spooky_candy"), guild)
    return str(e) if e else "🍬"


def sugar_rush(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Sugar Rush 2x boost potion emoji."""
    e = _find_emoji(("sugar_rush", "sugarrush"), guild)
    return str(e) if e else "⚡"


def physics(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Physics Quantum Orbital Atom emoji."""
    e = _find_emoji(("physics", "subject_physics", "atom"), guild)
    return str(e) if e else "⚛️"


def chemistry(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Chemistry Alchemical Bubble Flask emoji."""
    e = _find_emoji(("chemistry", "subject_chemistry", "flask"), guild)
    return str(e) if e else "🧪"


def maths(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Maths Golden Drafting Compass emoji."""
    e = _find_emoji(("maths", "subject_maths", "compass"), guild)
    return str(e) if e else "📐"


def pomodoro(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Pomodoro / Chrono Pocket Clock emoji."""
    e = _find_emoji(("pomodoro", "focus_clock", "chrono_clock", "clock"), guild)
    return str(e) if e else "⏱️"


def book(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Study Book / Gilded Grimoire emoji."""
    e = _find_emoji(("study_book", "notes", "notebook", "book"), guild)
    return str(e) if e else "📖"


def crown(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Champion Gilded Crown emoji."""
    e = _find_emoji(("crown", "champion_crown", "rank_crown"), guild)
    return str(e) if e else "👑"


def trophy(guild: Optional[discord.Guild] = None) -> str:
    """Return the unique Grandmaster Trophy Chalice emoji."""
    e = _find_emoji(("trophy", "achievement_trophy", "chalice"), guild)
    return str(e) if e else "🏆"


def medal(rank: int, guild: Optional[discord.Guild] = None) -> str:
    """Return the authentic Minecraft pixel medal emoji for top 3 ranks."""
    fallbacks = {1: "🥇", 2: "🥈", 3: "🥉"}
    if rank in (1, 2, 3):
        e = _find_emoji((f"medal_{rank}", f"rank_{rank}"), guild)
        return str(e) if e else fallbacks[rank]
    return f"#{rank}"


def tier(tier_name: str, guild: Optional[discord.Guild] = None) -> str:
    """Return the custom tier shield emoji for a tier name.
    If the custom guild emoji is uploaded, returns it; otherwise returns empty string
    to prevent low-quality unicode emojis in embed texts."""
    clean = "".join(c for c in tier_name if c.isalnum()).lower()
    e = _find_emoji((f"tier_{clean}", clean), guild)
    if e:
        return str(e)
    return ""
