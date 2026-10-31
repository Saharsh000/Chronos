"""Shared-room Pomodoro timer.

The first person to join a voice channel starts a 25/5 focus-break
cycle *for that channel*. Anyone else who joins the same channel is
simply joining the cycle already in progress - they don't get their
own separate timer. The cycle ends when the channel empties out.

Like session tracking, phase timing is derived from a stored
`phase_start` timestamp (`current_time - phase_start`). The monitor
loop below only polls that timestamp; if the bot is offline when a
phase would have flipped, the loop below catches up in one pass the
moment it's back online, without drifting.
"""
from __future__ import annotations

import logging
import time

import discord
from discord.ext import commands, tasks

import config
from utils import embeds
from utils.time_format import format_duration

log = logging.getLogger("pomodoro")

FOCUS_SECONDS = config.POMODORO_FOCUS_MINUTES * 60
BREAK_SECONDS = config.POMODORO_BREAK_MINUTES * 60
LONG_BREAK_SECONDS = config.POMODORO_LONG_BREAK_MINUTES * 60
CYCLES_BEFORE_LONG_BREAK = max(1, config.POMODORO_CYCLES_BEFORE_LONG_BREAK)

PHASE_TITLES = {
    "focus": "\U0001F3AF Focus time!",
    "break": "\u2615 Short break",
    "long_break": "\U0001F6CB\uFE0F Long break",
}


class Pomodoro(commands.Cog, name="Pomodoro"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self.pomodoro_monitor.start()

    def cog_unload(self) -> None:
        self.pomodoro_monitor.cancel()

    # ------------------------------------------------------------------ #
    # Voice state listener - fully self-contained. This is independent
    # of the `.start`/`.stop` study-session commands: the Pomodoro cycle
    # is just about who's hanging out in a voice channel, regardless of
    # whether they've started a tracked session.
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot:
            return
        guild = member.guild
        afk_channel = guild.afk_channel

        before_tracked = before.channel is not None and before.channel != afk_channel
        after_tracked = after.channel is not None and after.channel != afk_channel

        if not before_tracked and after_tracked:
            await self.ensure_pomodoro(after.channel)
        elif before_tracked and not after_tracked:
            await self.maybe_end_pomodoro(before.channel)
        elif before_tracked and after_tracked and before.channel != after.channel:
            await self.ensure_pomodoro(after.channel)
            await self.maybe_end_pomodoro(before.channel)

    # ------------------------------------------------------------------ #
    # Lifecycle hooks
    # ------------------------------------------------------------------ #
    async def ensure_pomodoro(self, channel: discord.VoiceChannel) -> None:
        """Start a fresh cycle for `channel` if one isn't already running."""
        if channel is None or channel.guild.afk_channel == channel:
            return
        existing = await self.db.get_pomodoro(channel.id)
        if existing:
            return  # someone's already running this cycle - just join it

        guild_config = await self.db.get_guild_config(channel.guild.id)
        announce_channel_id = guild_config.get("pomodoro_channel_id") or guild_config.get("checkin_channel_id")
        now = int(time.time())
        await self.db.start_pomodoro(channel.id, channel.guild.id, announce_channel_id, FOCUS_SECONDS, now)
        log.info(f"POMODORO START| #{channel.name} in '{channel.guild.name}' began a fresh focus cycle")

        await self._announce(
            channel, announce_channel_id,
            title="\U0001F345 Pomodoro started",
            description=(
                f"A **{config.POMODORO_FOCUS_MINUTES}-minute focus session** just began in "
                f"\U0001F50A **{channel.name}**. Anyone who joins follows the same cycle."
            ),
            color=embeds.COLOR_POMODORO_FOCUS,
        )

    async def maybe_end_pomodoro(self, channel: discord.VoiceChannel) -> None:
        """Stop the cycle for `channel` once no humans remain in it."""
        if channel is None:
            return
        remaining = [m for m in channel.members if not m.bot]
        if remaining:
            return
        existing = await self.db.get_pomodoro(channel.id)
        if not existing:
            return
        await self.db.stop_pomodoro(channel.id)
        log.info(f"POMODORO STOP | #{channel.name}: channel is empty, cycle ended")

    # ------------------------------------------------------------------ #
    # Phase monitor (polls, never counts)
    # ------------------------------------------------------------------ #
    @tasks.loop(seconds=config.POMODORO_MONITOR_INTERVAL_SECONDS)
    async def pomodoro_monitor(self) -> None:
        now = int(time.time())
        for pomo in await self.db.get_all_active_pomodoros():
            if now - pomo["phase_start"] >= pomo["phase_duration"]:
                await self._advance_phase(pomo, now)

    @pomodoro_monitor.before_loop
    async def before_pomodoro_monitor(self) -> None:
        await self.bot.wait_until_ready()

    async def _advance_phase(self, pomo: dict, now: int) -> None:
        channel = self.bot.get_channel(pomo["channel_id"])
        if channel is None or not [m for m in channel.members if not m.bot]:
            await self.db.stop_pomodoro(pomo["channel_id"])
            log.info(f"POMODORO STOP | channel {pomo['channel_id']} vanished or emptied; cycle ended")
            return

        phase = pomo["phase"]
        phase_start = pomo["phase_start"]
        phase_duration = pomo["phase_duration"]
        cycle_count = pomo["cycle_count"]

        # Step forward in fixed increments so a long bot downtime catches
        # up correctly in one pass instead of drifting - still just
        # repeated `elapsed >= duration` checks against stored timestamps.
        while now - phase_start >= phase_duration:
            phase_start += phase_duration
            if phase == "focus":
                cycle_count += 1
                if cycle_count % CYCLES_BEFORE_LONG_BREAK == 0:
                    phase, phase_duration = "long_break", LONG_BREAK_SECONDS
                else:
                    phase, phase_duration = "break", BREAK_SECONDS
            else:
                phase, phase_duration = "focus", FOCUS_SECONDS

        await self.db.update_pomodoro_phase(pomo["channel_id"], phase, phase_start, phase_duration, cycle_count)
        log.info(
            f"POMODORO PHASE| #{channel.name} -> {phase} ({format_duration(phase_duration)}), cycle {cycle_count}"
        )

        await self._announce(
            channel, pomo.get("announce_channel_id"),
            title=PHASE_TITLES[phase],
            description=self._phase_description(phase, channel, phase_duration),
            color=embeds.COLOR_POMODORO_FOCUS if phase == "focus" else embeds.COLOR_POMODORO_BREAK,
        )

    @staticmethod
    def _phase_description(phase: str, channel: discord.VoiceChannel, duration: int) -> str:
        minutes = duration // 60
        if phase == "focus":
            return f"Back to work in \U0001F50A **{channel.name}** for **{minutes} minutes**."
        return f"Take **{minutes} minutes** to recharge before the next focus round in \U0001F50A **{channel.name}**."

    async def _announce(
        self, voice_channel: discord.VoiceChannel, announce_channel_id: int | None,
        title: str, description: str, color: int,
    ) -> None:
        target = self.bot.get_channel(announce_channel_id) if announce_channel_id else None
        if target is None:
            target = getattr(voice_channel.guild, "system_channel", None)
        if target is None:
            return
        try:
            await target.send(embed=embeds.base_embed(title=title, description=description, color=color))
        except discord.Forbidden:
            log.warning(f"Missing permission to post Pomodoro update in channel {target.id}.")
        except discord.HTTPException as exc:
            log.error(f"Failed to post Pomodoro update: {exc}")

    # ------------------------------------------------------------------ #
    # Command
    # ------------------------------------------------------------------ #
    @commands.command(name="pomodoro", aliases=["pomo"])
    async def pomodoro_status(self, ctx: commands.Context) -> None:
        """Show the current Pomodoro phase running in your voice channel."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=embeds.error_embed("Join a voice channel first to check its Pomodoro status."))
            return

        channel = ctx.author.voice.channel
        pomo = await self.db.get_pomodoro(channel.id)
        if not pomo:
            await ctx.send(embed=embeds.info_embed(
                "\U0001F345 No Pomodoro running",
                f"There's no active Pomodoro cycle in \U0001F50A **{channel.name}** yet.",
            ))
            return

        now = int(time.time())
        remaining = max(0, pomo["phase_duration"] - (now - pomo["phase_start"]))
        participants = [m for m in channel.members if not m.bot]

        embed = embeds.base_embed(
            title=PHASE_TITLES[pomo["phase"]],
            description=f"Channel: \U0001F50A **{channel.name}**",
            color=embeds.COLOR_POMODORO_FOCUS if pomo["phase"] == "focus" else embeds.COLOR_POMODORO_BREAK,
        )
        embed.add_field(name="\u23F1\uFE0F Time remaining", value=format_duration(remaining), inline=True)
        embed.add_field(name="\U0001F504 Completed cycles", value=str(pomo["cycle_count"]), inline=True)
        embed.add_field(
            name=f"\U0001F465 Participants ({len(participants)})",
            value=", ".join(m.mention for m in participants) or "\u2014",
            inline=False,
        )
        embeds.set_footer(embed, f"{ctx.prefix}pomodoro refreshes this status")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Pomodoro(bot))
