"""Discord embeds posted when something happens on the website.

They reuse `utils.embeds` so a web session looks identical in your check-in
channel to one started with `.start` / `.stop`, plus a small "via Chronos Web"
note so people can tell where it came from.
"""
from __future__ import annotations

from typing import Any, Optional

import config
from utils import embeds, emojis
from utils import lab as lab_catalog
from utils.subjects import SUBJECT_INFO
from utils.time_format import discord_timestamp, format_duration

VIA = "via Chronos Web"


def _author(embed, member: dict[str, Any]):
    embed.set_author(name=member["name"], icon_url=member["avatar"])
    return embed


def session_started(member: dict[str, Any], user_id: int, subject: Optional[str], now: int):
    note = ""
    if subject:
        i = SUBJECT_INFO[subject]
        note = f"\n{i['emoji']} Tagged as **{i['label']}**."
    e = embeds.base_embed(
        title="\U0001F4D6 Study session started",
        description=f"<@{user_id}> started {discord_timestamp(now, 'R')}. Lock in and make it count.{note}",
        color=embeds.COLOR_STUDY,
    )
    embeds.set_footer(e, VIA)
    return _author(e, member)


def session_complete(member: dict[str, Any], user_id: int, result: dict[str, Any], tier_name: str, guild=None):
    coin_e, xp_e = emojis.coin(guild), emojis.xp(guild)
    e = embeds.base_embed(
        title="✅ Session complete",
        description=f"<@{user_id}> focused for **{format_duration(result['duration'])}**. Nice work.",
        color=embeds.COLOR_SUCCESS,
    )
    e.add_field(name="⏱️ Focus time", value=format_duration(result["duration"]), inline=True)
    e.add_field(name=f"{xp_e} XP gained", value=f"+{result['xp_earned']} XP", inline=True)
    e.add_field(name=f"{coin_e} Chronocoins earned", value=f"+{result['coins_earned']} {coin_e}", inline=True)
    if result.get("subject"):
        i = SUBJECT_INFO[result["subject"]]
        e.add_field(name="Subject", value=f"{i['emoji']} {i['label']}", inline=True)
    if result["leveled_up"]:
        e.add_field(
            name="\U0001F389 Level Up!",
            value=f"Level {result['old_level']} → **Level {result['new_level']}** — **{tier_name}**",
            inline=False,
        )
    embeds.set_footer(e, VIA)
    return _author(e, member)


def streak_lost(user_id: int, broken_from: int):
    penalty = min(broken_from * config.STREAK_BREAK_COINS_PER_DAY, config.STREAK_BREAK_COINS_CAP)
    return embeds.base_embed(
        title="\U0001F494 Streak Lost!",
        description=(
            f"<@{user_id}> lost their **{broken_from}-day** study streak "
            f"and was penalized **{penalty} Chronocoins**.\nStudy today to start building a new one!"
        ),
        color=embeds.COLOR_ERROR,
    )


def still_here():
    return embeds.base_embed(
        title="✅ Still here!", description="Your session continues. Keep it up!",
        color=embeds.COLOR_SUCCESS,
    )


class _Fake:
    """Just enough of a discord.User for embeds.achievement_unlock_embed."""
    def __init__(self, member):
        self.name = member["name"]
        self.display_avatar = type("A", (), {"url": member["avatar"]})()

    def __str__(self) -> str:
        return self.name


def achievements_embed(member: dict[str, Any], newly: list):
    return embeds.achievement_unlock_embed(_Fake(member), newly)


def top3_embed(member: dict[str, Any], user_id: int, perk: dict[str, Any], rank: int):
    coin_icon = emojis.coin(None)
    box_icon = emojis.item(perk["item_award"], None)
    e = embeds.base_embed(
        title=f"\U0001F451 Top 3 Daily Dawn Perk — {perk['badge']}",
        description=(
            f"Rise and shine, <@{user_id}>! As one of the server's **Top 3 Study Champions**, "
            f"your first action of the day unlocked the **{perk['perk_name']}**!\n\n"
            f"⚡ **Active Focus Buff:** `{perk['boost_desc']}`\n"
            f"\U0001FA99 **Daily Coins:** `+{perk['coins']}` {coin_icon}\n"
            f"\U0001F381 **Vault Drop:** `+1` {box_icon} **{perk['item_name']}**\n\n"
            f"*Keep setting the standard on the study leaderboard!*"
        ),
        color=embeds.COLOR_LEVELUP if rank == 1 else embeds.COLOR_PROGRESS,
    )
    e.set_thumbnail(url=member["avatar"])
    embeds.set_footer(e, "Leaderboard Top 3 Perks · Resets daily at 00:00 IST", VIA)
    return e


def lab_discovery_embed(member: dict[str, Any], user_id: int, compound: dict[str, Any]):
    e = embeds.base_embed(
        title="🔬 Server First Discovery!",
        description=(
            f"**<@{user_id}>** is the first in the server to synthesize **{compound['name']}** (`{compound['formula']}`)!\n\n"
            f"*\"{compound['fact']}\"*"
        ),
        color=embeds.COLOR_LEVELUP,
    )
    embeds.set_footer(e, "The Lab · Organic Compound Synthesis", VIA)
    return _author(e, member)


def lab_category_completed_embed(member: dict[str, Any], user_id: int, category: str, title: Optional[str]):
    t_str = f" and unlocked the title **{title}**" if title else ""
    e = embeds.base_embed(
        title="⚗️ Category Complete!",
        description=f"Congratulations to **<@{user_id}>** for synthesizing all compounds in the **{category}** collection{t_str}! (+1,000 Chronocoins)",
        color=embeds.COLOR_SUCCESS,
    )
    embeds.set_footer(e, "The Lab · Category Mastery", VIA)
    return _author(e, member)


def lab_milestone_embed(member: dict[str, Any], user_id: int, count: int, reward_desc: str):
    e = embeds.base_embed(
        title="🏆 Synthesis Milestone Reached!",
        description=f"**<@{user_id}>** has synthesized **{count} / {len(lab_catalog.COMPOUNDS)}** unique organic compounds in The Lab!\n\n**Reward:** {reward_desc}",
        color=embeds.COLOR_MILESTONE,
    )
    embeds.set_footer(e, "The Lab · Synthesis Milestones", VIA)
    return _author(e, member)

