"""Personal statistics, rank/level, subject breakdowns, and server
leaderboard commands.

All-time totals come straight from `user_stats` / `subject_stats`,
which the session monitor keeps near-real-time via incremental
crediting (see database.py's credit_progress) - no extra "live bonus"
math needed there. Period-filtered totals (today/week/month) are
summed from `session_log`, which only gets a row once a session ends,
so for those we still add the live elapsed time of any in-progress
session that falls within the period. Either way, nothing here is
ever computed from anything but fresh `current_time - start_time`
math against stored timestamps.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import embeds
from utils import xp as xp_utils
from utils.achievements import ACHIEVEMENTS
from utils.subjects import SUBJECT_ALIASES, SUBJECT_INFO, SUBJECTS
from utils.time_format import discord_timestamp, format_duration

PERIOD_ALIASES = {
    "today": "today", "day": "today", "daily": "today",
    "week": "week", "weekly": "week",
    "month": "month", "monthly": "month",
    "all": "alltime", "alltime": "alltime", "all-time": "alltime", "total": "alltime",
}
PERIOD_LABELS = {"today": "Today", "week": "This Week", "month": "This Month", "alltime": "All Time"}

# SQLite strftime('%w', ...) is 0=Sunday .. 6=Saturday.
WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _period_start(period: str) -> Optional[int]:
    """Epoch second marking the start of the given period, anchored to
    IST (see config.IST) - "today" means the current calendar day in
    India Standard Time, not the server's local time or plain UTC."""
    now = dt.datetime.now(config.IST)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return None
    return int(start.timestamp())


class Stats(commands.Cog, name="Stats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ------------------------------------------------------------------ #
    # Shared aggregation helpers
    # ------------------------------------------------------------------ #
    async def _period_totals(self, guild_id: int, period: str, subject: Optional[str] = None) -> dict[int, int]:
        """{user_id: seconds} for today/week/month, with live in-progress
        sessions added on top (they haven't hit session_log yet)."""
        since = _period_start(period)
        totals = await self.db.sum_seconds(guild_id, since, subject)

        now = int(time.time())
        for session in await self.db.get_all_active_sessions():
            if session["guild_id"] != guild_id:
                continue
            if subject is not None and session.get("subject") != subject:
                continue
            start = max(session["start_time"], since) if since is not None else session["start_time"]
            live = max(0, now - start)
            if live:
                totals[session["user_id"]] = totals.get(session["user_id"], 0) + live
        return totals

    async def _totals(self, guild_id: int, period: str, subject: Optional[str] = None) -> dict[int, int]:
        if period == "alltime":
            if subject:
                return await self.db.get_subject_totals(guild_id, subject)
            return await self.db.get_alltime_totals(guild_id)
        return await self._period_totals(guild_id, period, subject)

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    @commands.command(name="session", aliases=["current"])
    async def session_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Show your (or someone else's) currently running study session."""
        target = member or ctx.author
        session = await self.db.get_active_session(target.id, ctx.guild.id)
        if not session:
            who = "You don't have" if target == ctx.author else f"{target.mention} doesn't have"
            await ctx.send(embed=embeds.info_embed(
                "No active session",
                f"{who} an active study session. Use `{ctx.prefix}start` to begin one!",
            ))
            return

        now = int(time.time())
        elapsed = now - session["start_time"]
        channel = ctx.guild.get_channel(session["channel_id"]) if session["channel_id"] else None

        embed = embeds.base_embed(title="\U0001F4D6 Active Study Session", color=embeds.COLOR_PRIMARY)
        embed.set_author(name=str(target), icon_url=target.display_avatar.url)
        embed.add_field(name="Channel", value=channel.mention if channel else "Not in voice", inline=True)
        embed.add_field(name="Elapsed", value=format_duration(elapsed), inline=True)
        embed.add_field(name="Started", value=discord_timestamp(session["start_time"], "R"), inline=True)
        if session.get("subject"):
            info = SUBJECT_INFO[session["subject"]]
            embed.add_field(name="Subject", value=f"{info['emoji']} {info['label']}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="active", aliases=["whosactive", "online"])
    @commands.guild_only()
    async def active_cmd(self, ctx: commands.Context) -> None:
        """See everyone currently in an active study session in this server."""
        sessions = await self.db.get_active_sessions_for_guild(ctx.guild.id)
        now = int(time.time())

        embed = embeds.base_embed(title=f"\U0001F7E2 Active Right Now \u2014 {ctx.guild.name}", color=embeds.COLOR_SUCCESS)

        if not sessions:
            embed.description = f"Nobody's currently studying. Use `{ctx.prefix}start` to be the first!"
            await ctx.send(embed=embed)
            return

        lines = []
        for session in sessions:
            member = ctx.guild.get_member(session["user_id"])
            if member is None:
                continue
            elapsed = now - session["start_time"]
            channel = ctx.guild.get_channel(session["channel_id"]) if session["channel_id"] else None
            subj = f" \u2022 {SUBJECT_INFO[session['subject']]['emoji']} {SUBJECT_INFO[session['subject']]['label']}" if session.get("subject") else ""
            chan = f" \u2022 {channel.mention}" if channel else ""
            lines.append(f"**{member.display_name}** \u2014 {format_duration(elapsed)}{subj}{chan}")

        if not lines:
            embed.description = f"Nobody's currently studying. Use `{ctx.prefix}start` to be the first!"
            await ctx.send(embed=embed)
            return

        embed.description = f"**{len(lines)}** studying right now, longest session first:"
        chunk: list[str] = []
        length = 0
        for line in lines:
            if length + len(line) + 1 > 1000:
                embed.add_field(name="\u200b", value="\n".join(chunk), inline=False)
                chunk, length = [], 0
            chunk.append(line)
            length += len(line) + 1
        if chunk:
            embed.add_field(name="\u200b", value="\n".join(chunk), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="stats", aliases=["profile", "me"])
    async def stats_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """View in-depth personal study statistics: time, XP, level,
        streaks, coins, achievements, and behavioral analytics."""
        target = member or ctx.author
        stats = await self.db.get_or_create_user_stats(target.id, ctx.guild.id)
        active_session = await self.db.get_active_session(target.id, ctx.guild.id)
        currency = await self.db.get_or_create_currency(target.id, ctx.guild.id)
        unlocked_ids = await self.db.get_unlocked_achievement_ids(target.id, ctx.guild.id)
        analytics = await self.db.get_session_analytics(target.id, ctx.guild.id)

        now = int(time.time())
        live_uncredited = 0
        if active_session:
            elapsed = now - active_session["start_time"]
            live_uncredited = max(0, elapsed - active_session["credited_seconds"])

        current_into, needed_for_next, level = xp_utils.xp_progress(stats["xp"])
        effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
        tier = xp_utils.tier_for_level(level, effective_tiers)
        bar = xp_utils.progress_bar(current_into, needed_for_next)

        today_totals = await self._period_totals(ctx.guild.id, "today")
        week_totals = await self._period_totals(ctx.guild.id, "week")
        alltime_totals = await self.db.get_alltime_totals(ctx.guild.id)
        ranking = sorted(alltime_totals.items(), key=lambda kv: kv[1], reverse=True)
        rank_position = next((i + 1 for i, (uid, _) in enumerate(ranking) if uid == target.id), None)

        header = f"\U0001F4CA Study Stats \u2014 {target.display_name}"
        if stats.get("equipped_title"):
            header += f"  \u00B7  \u201C{stats['equipped_title']}\u201D"

        embed = embeds.base_embed(title=header, color=embeds.COLOR_PRIMARY)
        embed.set_thumbnail(url=target.display_avatar.url)

        # --- Core progression ------------------------------------------------ #
        embed.add_field(name="Tier / Level", value=f"{tier} \u00B7 **Lv. {level}**", inline=True)
        embed.add_field(name="XP", value=f"{stats['xp']:,} XP", inline=True)
        embed.add_field(name="Server Rank", value=f"#{rank_position}" if rank_position else "Unranked", inline=True)
        embed.add_field(name="Progress to next level", value=f"`{bar}` {current_into}/{needed_for_next} XP", inline=False)

        # --- Time totals ------------------------------------------------------#
        embed.add_field(name="Today", value=format_duration(today_totals.get(target.id, 0)), inline=True)
        embed.add_field(name="This Week", value=format_duration(week_totals.get(target.id, 0)), inline=True)
        embed.add_field(name="All Time", value=format_duration(stats["total_seconds"] + live_uncredited), inline=True)

        # --- Streaks & economy -------------------------------------------------#
        embed.add_field(
            name="\U0001F525 Study Streak",
            value=f"{stats['current_streak']} days (best: {stats['longest_streak']})",
            inline=True,
        )
        embed.add_field(name="\U0001FA99 Coins", value=f"{currency['coins']:,}", inline=True)
        embed.add_field(
            name="\U0001F3C5 Achievements",
            value=f"{len(unlocked_ids)}/{len(ACHIEVEMENTS)}",
            inline=True,
        )

        # --- Session analysis ----------------------------------------------- #
        embed.add_field(name="Sessions Completed", value=str(stats["sessions_count"]), inline=True)
        embed.add_field(
            name="Avg Session Length",
            value=format_duration(analytics["avg_session_seconds"]) if analytics["sessions_logged"] else "\u2014",
            inline=True,
        )
        embed.add_field(
            name="Longest Session",
            value=format_duration(analytics["longest_session_seconds"]) if analytics["sessions_logged"] else "\u2014",
            inline=True,
        )

        if analytics["weekday_seconds"]:
            best_weekday, best_seconds = max(analytics["weekday_seconds"].items(), key=lambda kv: kv[1])
            embed.add_field(
                name="Most Active Day",
                value=f"{WEEKDAY_NAMES[best_weekday]} ({format_duration(best_seconds)})",
                inline=True,
            )
        if analytics["favorite_subject"]:
            info = SUBJECT_INFO[analytics["favorite_subject"]]
            embed.add_field(name="Favorite Subject", value=f"{info['emoji']} {info['label']}", inline=True)

        if active_session:
            live_total = now - active_session["start_time"]
            embed.add_field(name="Right now", value=f"\U0001F7E2 In progress \u2014 {format_duration(live_total)} so far", inline=True)

        cfg = await self.db.get_guild_config(ctx.guild.id)
        if any(cfg.get(f"{s}_channel_id") for s in SUBJECTS):
            subj_totals = await self.db.get_subject_stats(target.id, ctx.guild.id)
            if active_session and active_session.get("subject"):
                subj_totals[active_session["subject"]] = subj_totals.get(active_session["subject"], 0) + live_uncredited
            subj_text = " \u00A0|\u00A0 ".join(
                f"{SUBJECT_INFO[s]['emoji']} {format_duration(subj_totals.get(s, 0), always_show_seconds=False)}"
                for s in SUBJECTS
            )
            embed.add_field(name="Subjects", value=subj_text, inline=False)

        embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 {ctx.prefix}achievements \u00B7 {ctx.prefix}compare \u00B7 {ctx.prefix}halloffame")
        await ctx.send(embed=embed)

    @commands.command(name="subjects", aliases=["subjectstats"])
    async def subjects_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """View a per-subject (Physics/Chemistry/Maths) time breakdown."""
        target = member or ctx.author
        totals = await self.db.get_subject_stats(target.id, ctx.guild.id)

        active_session = await self.db.get_active_session(target.id, ctx.guild.id)
        if active_session and active_session.get("subject"):
            now = int(time.time())
            live_uncredited = max(0, (now - active_session["start_time"]) - active_session["credited_seconds"])
            totals[active_session["subject"]] = totals.get(active_session["subject"], 0) + live_uncredited

        embed = embeds.base_embed(
            title=f"\U0001F4DA Subject Breakdown \u2014 {target.display_name}", color=embeds.COLOR_PRIMARY
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        for key in SUBJECTS:
            info = SUBJECT_INFO[key]
            embed.add_field(name=f"{info['emoji']} {info['label']}", value=format_duration(totals.get(key, 0)), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="rank", aliases=["level", "lvl"])
    async def rank_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """View level/XP progress and tier."""
        target = member or ctx.author
        stats = await self.db.get_or_create_user_stats(target.id, ctx.guild.id)
        current_into, needed_for_next, level = xp_utils.xp_progress(stats["xp"])
        effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
        tier = xp_utils.tier_for_level(level, effective_tiers)
        bar = xp_utils.progress_bar(current_into, needed_for_next)

        alltime_totals = await self.db.get_alltime_totals(ctx.guild.id)
        ranking = sorted(alltime_totals.items(), key=lambda kv: kv[1], reverse=True)
        rank_position = next((i + 1 for i, (uid, _) in enumerate(ranking) if uid == target.id), None)

        embed = embeds.base_embed(title=f"\U0001F3C5 {target.display_name}'s Rank", color=embeds.COLOR_PRIMARY)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Tier", value=tier, inline=True)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Server Rank", value=f"#{rank_position}" if rank_position else "Unranked", inline=True)
        embed.add_field(name="XP", value=f"{stats['xp']:,} total XP", inline=False)
        embed.add_field(name="Next level in", value=f"`{bar}` {needed_for_next - current_into} XP to go", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="leaderboard", aliases=["lb", "top"])
    async def leaderboard_cmd(self, ctx: commands.Context, *args: str) -> None:
        """Server leaderboard. Optional filters, in any order:
        a period (today/week/month/alltime) and/or a subject
        (physics/chemistry/maths). Examples:
          .leaderboard
          .leaderboard week
          .leaderboard physics
          .leaderboard month chemistry
        """
        period = "alltime"
        subject = None
        for arg in args:
            key = arg.lower()
            if key in PERIOD_ALIASES:
                period = PERIOD_ALIASES[key]
            elif key in SUBJECT_ALIASES:
                subject = SUBJECT_ALIASES[key]
            else:
                await ctx.send(embed=embeds.error_embed(
                    f"Unknown option `{arg}`. Try a period (`today`/`week`/`month`/`alltime`) "
                    f"and/or a subject (`physics`/`chemistry`/`maths`)."
                ))
                return

        totals = await self._totals(ctx.guild.id, period, subject)
        ranking = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

        title = f"\U0001F3C6 Leaderboard \u2014 {PERIOD_LABELS[period]}"
        if subject:
            info = SUBJECT_INFO[subject]
            title += f" \u00B7 {info['emoji']} {info['label']}"

        if not ranking or ranking[0][1] <= 0:
            await ctx.send(embed=embeds.info_embed(
                title, "No study time has been logged yet for this filter."
            ))
            return

        medals = ["\U0001F947", "\U0001F948", "\U0001F949"]
        lines = []
        for i, (user_id, seconds) in enumerate(ranking[:10]):
            if seconds <= 0:
                break
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"Unknown User ({user_id})"
            prefix = medals[i] if i < 3 else f"`#{i + 1}`"
            lines.append(f"{prefix} **{name}** \u2014 {format_duration(seconds)}")

        embed = embeds.base_embed(title=title, description="\n".join(lines), color=embeds.COLOR_LEVELUP)

        author_position = next((i + 1 for i, (uid, _) in enumerate(ranking) if uid == ctx.author.id), None)
        if author_position and author_position > 10:
            embed.set_footer(text=f"You're ranked #{author_position} with {format_duration(totals[ctx.author.id])}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
