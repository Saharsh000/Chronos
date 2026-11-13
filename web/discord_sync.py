"""Real-time Discord bot bridge and notification dispatcher for Chronoweb."""
from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any, Optional

import discord

import config
from utils import embeds, emojis
from utils.stats_card import render_session_summary_card_sync
from utils.subjects import SUBJECT_INFO
from utils.time_format import discord_timestamp, format_duration
from utils.xp import tier_for_level, xp_progress

log = logging.getLogger("web.discord_sync")


async def get_checkin_channel(bot: Any, guild_id: int) -> Optional[discord.TextChannel]:
    """Retrieve designated notification / check-in channel for guild."""
    if not bot or not bot.is_ready():
        return None
    guild = bot.get_guild(guild_id)
    if not guild:
        return None
    guild_config = await bot.db.get_guild_config(guild_id)
    channel_id = guild_config.get("checkin_channel_id")
    if not channel_id:
        # Fallback to system channel or first text channel
        return guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
    return bot.get_channel(channel_id)


async def notify_session_start(
    bot: Any,
    guild_id: int,
    user_id: int,
    subject: Optional[str] = None,
    now: Optional[int] = None,
) -> None:
    """Post rich Discord embed when a study session starts on Chronoweb."""
    if not bot or not bot.is_ready():
        return
    try:
        now = now or int(time.time())
        channel = await get_checkin_channel(bot, guild_id)
        if not channel:
            return

        guild = bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        mention = member.mention if member else f"<@{user_id}>"

        subject_note = ""
        if subject and subject in SUBJECT_INFO:
            info = SUBJECT_INFO[subject]
            subject_note = f"\n{info['emoji']} Tagged as **{info['label']}** — focus hard!"

        embed = embeds.base_embed(
            title="📖 Study Session Started",
            description=(
                f"{mention} locked in via **[Chronoweb](https://chronos.fadehost.app)**!\n"
                f"Started {discord_timestamp(now, 'R')}. Make it count.{subject_note}"
            ),
            color=embeds.COLOR_STUDY,
        )
        if member and member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embeds.set_footer(embed, "Live from Chronoweb · chronos.fadehost.app")
        await channel.send(embed=embed)
        log.info(f"DISCORD_SYNC | Session start notified for user {user_id} in guild {guild_id}")
    except Exception as exc:
        log.exception(f"DISCORD_SYNC | Failed to notify session start: {exc}")


async def notify_session_stop(
    bot: Any,
    guild_id: int,
    user_id: int,
    session_result: dict[str, Any],
) -> Optional[bytes]:
    """Post session completion embed and render high-res summary card to Discord."""
    rendered_card_bytes = None
    if not bot:
        return None
    try:
        guild = bot.get_guild(guild_id) if bot.is_ready() else None
        member = guild.get_member(user_id) if guild else None
        mention = member.mention if member else f"<@{user_id}>"
        name = member.display_name if member else f"User {user_id}"

        # Fetch fresh stats for card rendering
        user_stats = await bot.db.get_or_create_user_stats(user_id, guild_id)
        effective_tiers = await bot.db.get_effective_tiers(guild_id)
        cur_xp, next_xp, _ = xp_progress(user_stats.get("xp", 0))
        tier_name = tier_for_level(session_result.get("new_level", 0), effective_tiers)

        avatar_bytes = None
        if member:
            try:
                avatar_bytes = await member.display_avatar.read()
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        try:
            rendered_card_bytes = await loop.run_in_executor(
                None,
                render_session_summary_card_sync,
                name,
                session_result["duration"],
                session_result["xp_earned"],
                session_result["coins_earned"],
                session_result.get("subject"),
                session_result["old_level"],
                session_result["new_level"],
                cur_xp,
                next_xp,
                tier_name,
                user_stats.get("current_streak", 1),
                avatar_bytes,
            )
        except Exception as exc:
            log.warning(f"Failed to render session summary card: {exc}")

        channel = await get_checkin_channel(bot, guild_id)
        if not channel:
            return rendered_card_bytes

        coin_e = emojis.coin(guild)
        xp_e = emojis.xp(guild)
        embed = embeds.base_embed(
            title="✅ Session Complete",
            description=f"{mention} focused for **{format_duration(session_result['duration'])}** via **[Chronoweb](https://chronos.fadehost.app)**.",
            color=embeds.COLOR_SUCCESS,
        )

        card_file = None
        if rendered_card_bytes:
            card_file = discord.File(io.BytesIO(rendered_card_bytes), filename="session_summary.png")
            embed.set_image(url="attachment://session_summary.png")
        else:
            embed.add_field(name="⏱️ Focus Time", value=format_duration(session_result["duration"]), inline=True)
            embed.add_field(name=f"{xp_e} XP Gained", value=f"+{session_result['xp_earned']} XP", inline=True)
            embed.add_field(name=f"{coin_e} Coins", value=f"+{session_result['coins_earned']} {coin_e}", inline=True)
            if session_result.get("subject"):
                info = SUBJECT_INFO.get(session_result["subject"])
                if info:
                    embed.add_field(name="Subject", value=f"{info['emoji']} {info['label']}", inline=True)

        if session_result.get("leveled_up"):
            t_emoji = emojis.tier(tier_name, guild)
            t_str = f"{t_emoji} **{tier_name}**" if t_emoji else f"**{tier_name}**"
            embed.add_field(
                name="🎉 Level Up!",
                value=f"Level {session_result['old_level']} → **Level {session_result['new_level']}** — {t_str}",
                inline=False,
            )

        embeds.set_footer(embed, "Logged via Chronoweb · chronos.fadehost.app")
        if card_file:
            await channel.send(embed=embed, file=card_file)
        else:
            await channel.send(embed=embed)

        # Check streak break
        if session_result.get("streak_broken_from", 0) > 0:
            broken_from = session_result["streak_broken_from"]
            penalty = min(broken_from * config.STREAK_BREAK_COINS_PER_DAY, config.STREAK_BREAK_COINS_CAP)
            break_embed = embeds.base_embed(
                title="💔 Streak Lost!",
                description=(
                    f"{mention} lost their **{broken_from}-day** study streak "
                    f"and was penalized **{penalty} Chronocoins**.\n"
                    f"Keep studying to reignite your flame!"
                ),
                color=embeds.COLOR_ERROR,
            )
            await channel.send(embed=break_embed)

        # Check newly unlocked achievements
        now = int(time.time())
        newly_unlocked = await bot.db.check_achievements(user_id, guild_id, now)
        if newly_unlocked and member:
            await channel.send(embed=embeds.achievement_unlock_embed(member, newly_unlocked))

        log.info(f"DISCORD_SYNC | Session complete notified for user {user_id} in guild {guild_id}")
    except Exception as exc:
        log.exception(f"DISCORD_SYNC | Failed to notify session stop: {exc}")

    return rendered_card_bytes


async def notify_pet_progress(
    bot: Any,
    guild_id: int,
    user_id: int,
    pet_result: dict[str, Any],
) -> None:
    """Notify mid-session or feeding pet evolution/level-up to Discord."""
    if not bot or not bot.is_ready():
        return
    try:
        channel = await get_checkin_channel(bot, guild_id)
        if not channel:
            return

        guild = bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        mention = member.mention if member else f"<@{user_id}>"

        if pet_result.get("evolved"):
            embed = embeds.base_embed(
                title="✨ Pet Evolved! (via Chronoweb)",
                description=(
                    f"{mention}'s companion **{pet_result['nickname']}** evolved: "
                    f"{pet_result['old_stage']['name']} ➔ **{pet_result['new_stage']['name']}**!"
                ),
                color=embeds.COLOR_LEVELUP,
            )
        elif pet_result.get("leveled_up"):
            embed = embeds.base_embed(
                title="🐾 Pet Level Up! (via Chronoweb)",
                description=f"{mention}'s companion **{pet_result['nickname']}** reached **Level {pet_result['new_level']}**!",
                color=embeds.COLOR_LEVELUP,
            )
        else:
            return

        await channel.send(embed=embed)
    except Exception as exc:
        log.exception(f"DISCORD_SYNC | Failed to notify pet progress: {exc}")
