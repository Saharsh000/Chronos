"""Study/focus session commands (`.start` / `.stop`) and the AFK check-in system.

Sessions are controlled explicitly by the user - joining or leaving a
voice channel no longer starts or stops anything by itself. This
keeps "when does my time start/stop counting" fully predictable: it's
exactly `.start`, `.stop`, or an AFK timeout, never a side effect of
Discord's voice-state events.

Nothing here counts time with an in-memory counter. Every elapsed
value is `current_time - start_time` (or `- last_checkin` /
`- prompt_sent_at` / `- credited_seconds`), read fresh from the
database whenever it's needed. The `session_monitor` loop only
*polls* those stored timestamps - if the bot goes down entirely,
sessions simply keep their original `start_time` on disk and are
correct again the instant the bot restarts (see `_reconcile_sessions`).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import embeds
from utils.subjects import SUBJECT_ALIASES, SUBJECT_HINT, SUBJECT_INFO, detect_subject, normalize_subject_key
from utils.time_format import discord_timestamp, format_duration
from utils.xp import tier_for_level

log = logging.getLogger("sessions")


class Sessions(commands.Cog, name="Sessions"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db
        self._reconciled = False
        self.session_monitor.start()

    def cog_unload(self) -> None:
        self.session_monitor.cancel()

    # ------------------------------------------------------------------ #
    # Startup reconciliation - detect active sessions from the database
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._reconciled:
            return
        self._reconciled = True
        await self._reconcile_sessions()
        log.info("Startup reconciliation complete - session commands are now active.")

    async def _reconcile_sessions(self) -> None:
        """Sessions live entirely in the database and are only ever ended
        by `.stop` or an AFK timeout - never by voice presence - so on
        restart there's nothing to repair, just something to report.
        """
        now = int(time.time())
        active_sessions = await self.db.get_all_active_sessions()
        log.info(f"Reconciling {len(active_sessions)} stored active session(s)...")
        for session in active_sessions:
            elapsed = now - session["start_time"]
            log.info(
                f"Resumed session #{session['session_id']} for user {session['user_id']} "
                f"in guild {session['guild_id']} ({format_duration(elapsed)} elapsed so far)."
            )

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    @commands.command(name="start")
    @commands.guild_only()
    async def start_cmd(self, ctx: commands.Context, *, subject: Optional[str] = None) -> None:
        """Start a study/focus session.

        Optionally tag it with a subject: `.start physics` / `.start phy`
        / `.start p` (same idea for chemistry/`chem`/`c` and
        maths/`math`/`m`). This overrides the automatic detection from
        sitting in a Physics/Chemistry/Maths voice room - handy if
        you're not in one, or want to tag it differently.
        """
        existing = await self.db.get_active_session(ctx.author.id, ctx.guild.id)
        if existing:
            now = int(time.time())
            elapsed = now - existing["start_time"]
            await ctx.send(embed=embeds.error_embed(
                f"You already have a session running ({format_duration(elapsed)} so far). "
                f"Use `{ctx.prefix}stop` to end it first."
            ))
            return

        channel_id = ctx.author.voice.channel.id if ctx.author.voice and ctx.author.voice.channel else None
        guild_config = await self.db.get_guild_config(ctx.guild.id)
        resolved_subject = detect_subject(guild_config, channel_id)

        if subject:
            subject_key = SUBJECT_ALIASES.get(normalize_subject_key(subject))
            if subject_key is None:
                await ctx.send(embed=embeds.error_embed(
                    f"Unknown subject `{subject}`. {SUBJECT_HINT}"
                ))
                return
            resolved_subject = subject_key

        now = int(time.time())
        await self.db.start_session(ctx.author.id, ctx.guild.id, channel_id, resolved_subject, now)

        subject_note = ""
        if resolved_subject:
            info = SUBJECT_INFO[resolved_subject]
            subject_note = (
                f"\n{info['emoji']} Tagged as **{info['label']}** - this one "
                f"counts toward your subject stats too."
            )

        log.info(
            f"SESSION START | {ctx.author} ({ctx.author.id}) in guild '{ctx.guild.name}'"
            + (f" [subject={resolved_subject}]" if resolved_subject else "")
        )

        embed = embeds.success_embed(
            "Session started",
            f"Your study session began {discord_timestamp(now, 'R')}. Good luck!{subject_note}",
        )
        await ctx.send(embed=embed)

    @commands.command(name="stop", aliases=["end"])
    @commands.guild_only()
    async def stop_cmd(self, ctx: commands.Context) -> None:
        """Stop your current study/focus session."""
        session = await self.db.get_active_session(ctx.author.id, ctx.guild.id)
        if not session:
            await ctx.send(embed=embeds.error_embed(
                f"You don't have an active session. Use `{ctx.prefix}start` to begin one."
            ))
            return

        now = int(time.time())
        result = await self.db.end_session(session["session_id"], now, "manual_stop")
        if not result:
            await ctx.send(embed=embeds.error_embed("That session was already closed."))
            return

        log.info(
            f"SESSION END   | user={result['user_id']} guild={result['guild_id']} "
            f"duration={format_duration(result['duration'])} xp+={result['xp_earned']} reason=manual_stop"
        )
        if result["leveled_up"]:
            log.info(f"LEVEL UP      | user={result['user_id']} -> level {result['new_level']}")

        embed = embeds.base_embed(title="\u23F9\uFE0F Session ended", color=embeds.COLOR_SUCCESS)
        embed.add_field(name="Duration", value=format_duration(result["duration"]), inline=True)
        embed.add_field(name="XP earned", value=f"+{result['xp_earned']} XP", inline=True)
        embed.add_field(name="Coins earned", value=f"+{result['coins_earned']} \U0001FA99", inline=True)
        if result.get("subject"):
            info = SUBJECT_INFO[result["subject"]]
            embed.add_field(name="Subject", value=f"{info['emoji']} {info['label']}", inline=True)
        if result["leveled_up"]:
            effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
            tier = tier_for_level(result["new_level"], effective_tiers)
            embed.add_field(
                name="\U0001F389 Level Up!",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}** \u2014 {tier}",
                inline=False,
            )
        await ctx.send(embed=embed)

        if result.get("streak_broken_from", 0) > 0:
            broken_from = result["streak_broken_from"]
            penalty = min(
                broken_from * config.STREAK_BREAK_COINS_PER_DAY,
                config.STREAK_BREAK_COINS_CAP
            )
            break_embed = embeds.base_embed(
                title="💔 Streak Lost!",
                description=(
                    f"<@{ctx.author.id}> lost their **{broken_from}-day** study streak "
                    f"and was penalized **{penalty} coins**.\n"
                    f"Study today to start building a new one!"
                ),
                color=embeds.COLOR_ERROR,
            )
            await ctx.send(embed=break_embed)

        newly_unlocked = await self.db.check_achievements(ctx.author.id, ctx.guild.id)
        if newly_unlocked:
            await ctx.send(embed=embeds.achievement_unlock_embed(ctx.author, newly_unlocked))

    # ------------------------------------------------------------------ #
    # Session monitor: incremental XP/time crediting + AFK check-in.
    # Polls, never counts.
    # ------------------------------------------------------------------ #
    @tasks.loop(seconds=config.SESSION_MONITOR_INTERVAL_SECONDS)
    async def session_monitor(self) -> None:
        if not self._reconciled:
            return
        now = int(time.time())
        checkin_interval = config.CHECKIN_INTERVAL_MINUTES * 60
        grace_period = config.AFK_GRACE_MINUTES * 60

        for session in await self.db.get_all_active_sessions():
            # Roll any newly-completed minutes into permanent stats right
            # away, so `.stats` reflects activity within about a minute
            # instead of only once the session ends.
            credit = await self.db.credit_progress(session["session_id"], now)
            if credit:
                if credit.get("streak_broken_from", 0) > 0:
                    await self._announce_streak_break(credit)
                if credit["leveled_up"]:
                    await self._announce_level_up(credit)
                if credit.get("pet_result"):
                    await self._announce_pet_progress(credit["user_id"], credit["guild_id"], credit["pet_result"])
                if credit.get("egg_drop"):
                    await self._announce_egg_drop(credit["user_id"], credit["guild_id"], credit["egg_drop"], credit.get("subject"))
                if credit.get("ready_incubators"):
                    await self._announce_egg_ready(credit["user_id"], credit["guild_id"], credit["ready_incubators"])
                newly_unlocked = await self.db.check_achievements(credit["user_id"], credit["guild_id"], now)
                if newly_unlocked:
                    await self._announce_achievements(credit["user_id"], credit["guild_id"], newly_unlocked)

            if session["prompt_sent_at"] is None:
                if now - session["last_checkin"] >= checkin_interval:
                    await self._send_checkin_prompt(session, now)
            else:
                if now - session["prompt_sent_at"] >= grace_period:
                    await self._timeout_session(session, now)

    @session_monitor.before_loop
    async def before_session_monitor(self) -> None:
        await self.bot.wait_until_ready()

    async def _announce_streak_break(self, credit: dict) -> None:
        broken_from = credit.get("streak_broken_from", 0)
        if broken_from <= 0:
            return
            
        guild_config = await self.db.get_guild_config(credit["guild_id"])
        channel_id = guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
            
        penalty = min(
            broken_from * config.STREAK_BREAK_COINS_PER_DAY,
            config.STREAK_BREAK_COINS_CAP
        )
        embed = embeds.base_embed(
            title="💔 Streak Lost!",
            description=(
                f"<@{credit['user_id']}> lost their **{broken_from}-day** study streak "
                f"and was penalized **{penalty} coins**.\n"
                f"Study today to start building a new one!"
            ),
            color=embeds.COLOR_ERROR,
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _announce_level_up(self, credit: dict) -> None:
        log.info(f"LEVEL UP      | user={credit['user_id']} -> level {credit['new_level']} (mid-session)")
        guild_config = await self.db.get_guild_config(credit["guild_id"])
        channel_id = guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        effective_tiers = await self.db.get_effective_tiers(credit["guild_id"])
        tier = tier_for_level(credit["new_level"], effective_tiers)
        embed = embeds.base_embed(
            title="\U0001F389 Level Up!",
            description=f"<@{credit['user_id']}> reached **Level {credit['new_level']}** \u2014 {tier}!",
            color=embeds.COLOR_LEVELUP,
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _announce_pet_progress(self, user_id: int, guild_id: int, pet_result: dict) -> None:
        """Announce a mid-session pet level-up or evolution, mirroring
        _announce_level_up above but for the equipped pet (see
        grant_pet_xp in database.py)."""
        if not (pet_result["evolved"] or pet_result["leveled_up"]):
            return
        guild_config = await self.db.get_guild_config(guild_id)
        channel_id = guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        if pet_result["evolved"]:
            log.info(
                f"PET EVOLVE    | user={user_id} pet={pet_result['species_id']} -> "
                f"{pet_result['new_stage']['name']} (mid-session)"
            )
            embed = embeds.base_embed(
                title="\u2728 Pet Evolved!",
                description=(
                    f"<@{user_id}>'s **{pet_result['nickname']}** evolved: "
                    f"{pet_result['old_stage']['name']} \u2192 **{pet_result['new_stage']['name']}**!"
                ),
                color=embeds.COLOR_LEVELUP,
            )
        else:
            log.info(f"PET LEVEL UP  | user={user_id} pet={pet_result['species_id']} -> level {pet_result['new_level']} (mid-session)")
            embed = embeds.base_embed(
                title="\U0001F43E Pet Level Up!",
                description=(
                    f"<@{user_id}>'s **{pet_result['nickname']}** reached "
                    f"**Level {pet_result['new_level']}**!"
                ),
                color=embeds.COLOR_LEVELUP,
            )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _announce_achievements(self, user_id: int, guild_id: int, newly_unlocked: list) -> None:
        log.info(
            f"ACHIEVEMENT   | user={user_id} guild={guild_id} unlocked: "
            + ", ".join(a.id for a in newly_unlocked)
        )
        guild_config = await self.db.get_guild_config(guild_id)
        channel_id = guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        if member is None:
            return
        try:
            await channel.send(embed=embeds.achievement_unlock_embed(member, newly_unlocked))
        except discord.HTTPException:
            pass

    async def _announce_egg_drop(self, user_id: int, guild_id: int, egg_id: str, subject: Optional[str]) -> None:
        from utils import eggs as egg_catalog
        egg = egg_catalog.get_egg(egg_id)
        if not egg:
            return

        guild_config = await self.db.get_guild_config(guild_id)
        channel_id = guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return

        subject_str = f" while studying {subject.capitalize()}" if subject else " while studying"
        embed = embeds.base_embed(
            title=f"{egg['emoji']} Egg Discovered!",
            description=(
                f"<@{user_id}> found a **{egg['name']}**{subject_str}!\n"
                f"Use `{config.PREFIX}incubate {egg['tier']}` to hatch it with your study time, "
                f"or `{config.PREFIX}crack {egg['tier']}` to open it right away!"
            ),
            color=egg["color"],
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _announce_egg_ready(self, user_id: int, guild_id: int, ready_slots: list[dict]) -> None:
        guild_config = await self.db.get_guild_config(guild_id)
        channel_id = guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return

        for item in ready_slots:
            egg = item.get("egg") or {}
            embed = embeds.base_embed(
                title=f"\U0001F423 Egg Ready to Hatch!",
                description=(
                    f"<@{user_id}>, your **{egg.get('name', 'Egg')}** in Slot {item['slot']} is fully incubated!\n"
                    f"Run `{config.PREFIX}hatch {item['slot']}` to reveal your pet & rewards!"
                ),
                color=embeds.COLOR_SUCCESS,
            )
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    async def _send_checkin_prompt(self, session: dict, now: int) -> None:
        guild = self.bot.get_guild(session["guild_id"])
        if guild is None:
            return
        member = guild.get_member(session["user_id"])
        if member is None:
            return

        guild_config = await self.db.get_guild_config(session["guild_id"])
        channel_id = guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None and member.voice and member.voice.channel:
            channel = member.voice.channel

        embed = embeds.base_embed(
            title="\U0001F44B Still studying?",
            description=(
                f"{member.mention} you've been in a session for a while. React with "
                f"{config.CHECKIN_EMOJI} within **{config.AFK_GRACE_MINUTES} minutes** "
                f"to keep your session going."
            ),
            color=embeds.COLOR_WARNING,
        )

        msg = None
        destination = channel
        try:
            if destination is not None:
                msg = await destination.send(content=member.mention, embed=embed)
            else:
                msg = await member.send(embed=embed)
                destination = msg.channel
        except discord.HTTPException as exc:
            log.error(f"Failed to send AFK check-in prompt to {member}: {exc}")
            return

        try:
            await msg.add_reaction(config.CHECKIN_EMOJI)
        except discord.HTTPException:
            pass

        await self.db.set_prompt_sent(session["session_id"], msg.id, destination.id, now)
        log.info(f"AFK PROMPT    | sent to {member} ({member.id}) in guild {guild.id}")

    async def _timeout_session(self, session: dict, now: int) -> None:
        # End the session at the moment the prompt was sent - that's the
        # last time we can confirm they were actually still there.
        end_time = session["prompt_sent_at"]
        result = await self.db.end_session(session["session_id"], end_time, "afk_timeout")
        if not result:
            return
        log.info(
            f"AFK TIMEOUT   | user={result['user_id']} guild={result['guild_id']} "
            f"no response - session closed ({format_duration(result['duration'])} counted)"
        )

        newly_unlocked = await self.db.check_achievements(result["user_id"], result["guild_id"], end_time)

        guild_config = await self.db.get_guild_config(session["guild_id"])
        channel_id = session.get("prompt_channel_id") or guild_config.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None

        embed = embeds.base_embed(
            title="\U0001F4A4 Session ended \u2014 no response",
            description=(
                f"<@{result['user_id']}> didn't check in, so their session was closed.\n"
                f"Counted **{format_duration(result['duration'])}** and **{result['xp_earned']} XP** "
                f"up to their last confirmed activity."
            ),
            color=embeds.COLOR_ERROR,
        )
        if result["leveled_up"]:
            embed.add_field(
                name="\U0001F389 Level Up!",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}**",
                inline=False,
            )

        if channel is not None:
            try:
                await channel.send(embed=embed)
                if newly_unlocked:
                    await self._announce_achievements(result["user_id"], result["guild_id"], newly_unlocked)
                return
            except discord.HTTPException:
                pass

        guild = self.bot.get_guild(session["guild_id"])
        member = guild.get_member(session["user_id"]) if guild else None
        if member:
            try:
                await member.send(embed=embed)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------ #
    # Reaction-based check-in confirmation
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        if str(payload.emoji) != config.CHECKIN_EMOJI:
            return

        session = await self.db.get_session_by_prompt_message(payload.message_id)
        if not session or session["user_id"] != payload.user_id:
            return

        now = int(time.time())
        await self.db.update_checkin(session["session_id"], now)
        log.info(f"AFK CONFIRM   | user={session['user_id']} guild={session['guild_id']} checked in")

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            try:
                user = await self.bot.fetch_user(payload.user_id)
                channel = await user.create_dm()
            except discord.HTTPException:
                channel = None
        if channel is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
            await message.edit(
                embed=embeds.base_embed(
                    title="\u2705 Still here!",
                    description="Your session continues. Keep it up!",
                    color=embeds.COLOR_SUCCESS,
                )
            )
            await message.clear_reactions()
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Sessions(bot))
