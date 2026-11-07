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

import asyncio
import datetime as dt
import io
import logging
import time
from typing import Optional, Union

import discord
from discord.ext import commands

import config
from utils import embeds
from utils.views import LeaderboardView, StatsPaginationView
from cogs.trivia import get_trivia_tier
from utils import xp as xp_utils
from utils.achievements import ACHIEVEMENTS
from utils.subjects import SUBJECT_ALIASES, SUBJECT_INFO, SUBJECTS
from utils.time_format import discord_timestamp, format_duration
from utils.stats_card import render_leaderboard_card_sync

log = logging.getLogger("stats")

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

        embed = embeds.base_embed(title="\U0001F4D6 Active Study Session", color=embeds.COLOR_STUDY)
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

        embed = embeds.base_embed(
            title="\U0001F7E2 Studying Now",
            description=f"Live sessions in **{ctx.guild.name}**",
            color=embeds.COLOR_STUDY,
        )

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
        chunk_number = 1
        for line in lines:
            if length + len(line) + 1 > 1000:
                heading = "Students" if chunk_number == 1 else "More students"
                embed.add_field(name=heading, value="\n".join(chunk), inline=False)
                chunk, length = [], 0
                chunk_number += 1
            chunk.append(line)
            length += len(line) + 1
        if chunk:
            heading = "Students" if chunk_number == 1 else "More students"
            embed.add_field(name=heading, value="\n".join(chunk), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="stats", aliases=["profile", "me"])
    async def stats_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Paginated study profile with large graph cards: overview,
        weekly activity, subject split, and trivia."""
        target = member or ctx.author
        stats = await self.db.get_or_create_user_stats(target.id, ctx.guild.id)
        active_session = await self.db.get_active_session(target.id, ctx.guild.id)
        currency = await self.db.get_or_create_currency(target.id, ctx.guild.id)
        unlocked_ids = await self.db.get_unlocked_achievement_ids(target.id, ctx.guild.id)
        analytics = await self.db.get_session_analytics(target.id, ctx.guild.id)
        weekly_breakdown = await self.db.get_weekly_daily_breakdown(target.id, ctx.guild.id)
        subject_details = await self.db.get_detailed_subject_breakdown(target.id, ctx.guild.id)
        subject_seconds = await self.db.get_subject_stats(target.id, ctx.guild.id)
        trivia_stats = await self.db.get_or_create_trivia_stats(target.id, ctx.guild.id)
        trivia_rank = await self.db.get_user_trivia_rank(target.id, ctx.guild.id)
        equipped_pet = await self.db.get_equipped_pet(target.id, ctx.guild.id)

        now = int(time.time())
        live_uncredited = 0
        in_session_seconds = None
        if active_session:
            elapsed = now - active_session["start_time"]
            live_uncredited = max(0, elapsed - active_session["credited_seconds"])
            in_session_seconds = elapsed
            if active_session.get("subject"):
                subj = active_session["subject"]
                subject_seconds[subj] = subject_seconds.get(subj, 0) + live_uncredited
                details = subject_details.setdefault(subj, {
                    "session_count": 0, "avg_seconds": 0, "total_seconds": 0,
                })
                details["total_seconds"] = details.get("total_seconds", 0) + live_uncredited
            for day in weekly_breakdown.get("days", []):
                if day.get("is_today"):
                    was_empty = day.get("seconds", 0) <= 0
                    day["seconds"] = day.get("seconds", 0) + live_uncredited
                    weekly_breakdown["total_week_seconds"] = weekly_breakdown.get("total_week_seconds", 0) + live_uncredited
                    if was_empty and day["seconds"] > 0:
                        weekly_breakdown["active_days_count"] = weekly_breakdown.get("active_days_count", 0) + 1
                    if day["seconds"] > weekly_breakdown.get("peak_day_seconds", 0):
                        weekly_breakdown["peak_day_seconds"] = day["seconds"]
                        weekly_breakdown["peak_day_name"] = day["day_name"]
                    break

        for key, seconds in subject_seconds.items():
            details = subject_details.setdefault(key, {
                "session_count": 0, "avg_seconds": 0, "total_seconds": 0,
            })
            details["total_seconds"] = max(details.get("total_seconds", 0), seconds)

        current_into, needed_for_next, level = xp_utils.xp_progress(stats["xp"])
        effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
        tier = xp_utils.tier_for_level(level, effective_tiers)

        today_totals = await self._period_totals(ctx.guild.id, "today")
        week_totals = await self._period_totals(ctx.guild.id, "week")
        alltime_totals = await self.db.get_alltime_totals(ctx.guild.id)
        ranking = sorted(alltime_totals.items(), key=lambda kv: kv[1], reverse=True)
        rank_position = next((i + 1 for i, (uid, _) in enumerate(ranking) if uid == target.id), None)

        trivia_tier = get_trivia_tier(trivia_stats.get("total_marks", 0))
        trivia_tier["min_marks"] = trivia_tier.get("cur_min", 0)

        avatar_bytes: Optional[bytes] = None
        try:
            avatar_bytes = await target.display_avatar.with_format("png").with_size(256).read()
        except Exception:
            avatar_bytes = None

        view = StatsPaginationView(
            author_id=ctx.author.id,
            context={
                "target": target,
                "guild": ctx.guild,
                "stats": stats,
                "currency": currency,
                "candy": currency.get("candy", 0),
                "analytics": analytics,
                "weekly_breakdown": weekly_breakdown,
                "subject_details": subject_details,
                "subject_seconds": subject_seconds,
                "trivia_stats": trivia_stats,
                "trivia_rank": trivia_rank,
                "trivia_tier": trivia_tier,
                "tier": tier,
                "level": level,
                "current_into": current_into,
                "needed_for_next": needed_for_next,
                "total_seconds": stats["total_seconds"] + live_uncredited,
                "today_seconds": today_totals.get(target.id, 0),
                "week_seconds": week_totals.get(target.id, 0),
                "unlocked_count": len(unlocked_ids),
                "total_achievements": len(ACHIEVEMENTS),
                "rank_position": rank_position,
                "equipped_title": stats.get("equipped_title"),
                "equipped_pet": equipped_pet,
                "in_session_seconds": in_session_seconds,
                "avatar_bytes": avatar_bytes,
            },
        )
        try:
            await view.send_initial(ctx)
        except Exception as e:
            log.error("Failed to render paginated stats cards", exc_info=e)
            await ctx.send(embed=embeds.info_embed(
                "Study Profile",
                f"**{target.display_name}** · {tier} · Level {level}\n"
                f"Could not render the visual cards, but your stats are still here: "
                f"{format_duration(stats['total_seconds'] + live_uncredited)} all-time.",
            ))

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
            title=f"\U0001F4DA Subject Breakdown \u2014 {target.display_name}", color=embeds.COLOR_SOCIAL
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

        embed = embeds.base_embed(title=f"\U0001F3C5 Rank Card \u2014 {target.display_name}", color=embeds.COLOR_SOCIAL)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Tier", value=tier, inline=True)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Server Rank", value=f"#{rank_position}" if rank_position else "Unranked", inline=True)
        embed.add_field(name="XP", value=f"{stats['xp']:,} total XP", inline=False)
        embed.add_field(name="Next level in", value=f"`{bar}` {needed_for_next - current_into} XP to go", inline=False)
        await ctx.send(embed=embed)

    async def _render_leaderboard(
        self, ctx: commands.Context, period: str, subject: Optional[str],
    ) -> Union[tuple[discord.Embed, discord.File], discord.Embed]:
        """Build the visual leaderboard card and embed for one period. Called on the
        initial send and again each time a period button is pressed
        (see utils/views.py LeaderboardView)."""
        totals = await self._totals(ctx.guild.id, period, subject)
        ranking = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        active_ranking = [(uid, s) for (uid, s) in ranking if s > 0]

        period_label = PERIOD_LABELS.get(period, period.title())
        title_text = f"🏆 Leaderboard — {period_label}"
        subtitle = period_label
        if subject:
            info = SUBJECT_INFO[subject]
            title_text += f" · {info['emoji']} {info['label']}"
            subtitle = f"{period_label} · {info['label']}"

        if not active_ranking:
            return embeds.base_embed(
                title=title_text,
                description="No study time has been logged yet for this filter.",
                color=embeds.COLOR_MUTED,
            )

        effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
        top_6 = active_ranking[:6]

        # Fetch avatar bytes and user stats concurrently for top 6
        async def _fetch_entry(rank_num: int, user_id: int, seconds: int) -> dict[str, Any]:
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            avatar_bytes = None
            if member:
                try:
                    avatar_bytes = await member.display_avatar.with_format("png").with_size(64).read()
                except Exception:
                    avatar_bytes = None

            u_stats = await self.db.get_or_create_user_stats(user_id, ctx.guild.id)
            _, _, lvl = xp_utils.xp_progress(u_stats.get("xp", 0))
            t_name = xp_utils.tier_for_level(lvl, effective_tiers)
            clean_t = t_name.replace(" Tier", "").strip()

            return {
                "rank": rank_num,
                "user_id": user_id,
                "name": name,
                "sub": f"Level {lvl} · {clean_t} Tier",
                "score": format_duration(seconds),
                "avatar_bytes": avatar_bytes,
                "is_author": (user_id == ctx.author.id),
                "icon": "chronos_streak",
            }

        entries = list(await asyncio.gather(*[
            _fetch_entry(i + 1, uid, sec) for i, (uid, sec) in enumerate(top_6)
        ]))

        author_position = next((i + 1 for i, (uid, _) in enumerate(active_ranking) if uid == ctx.author.id), None)
        author_score = format_duration(totals.get(ctx.author.id, 0)) if ctx.author.id in totals else None

        loop = asyncio.get_running_loop()
        try:
            card_bytes = await loop.run_in_executor(
                None,
                render_leaderboard_card_sync,
                "LEADERBOARD",
                subtitle,
                ctx.guild.name,
                period,
                entries,
                author_position,
                author_score,
                ctx.author.id,
                subject,
                "chronos_streak",
                len(active_ranking),
                "chronos_streak",
            )
            file = discord.File(io.BytesIO(card_bytes), filename="leaderboard.png")
            embed = embeds.base_embed(
                title=title_text,
                description=f"Showing top academic contenders in **{ctx.guild.name}**",
                color=embeds.COLOR_LEVELUP,
            )
            embed.set_image(url="attachment://leaderboard.png")
            if author_position:
                embeds.set_footer(
                    embed,
                    f"Your rank: #{author_position} ({author_score}) · Click a period button below to switch",
                )
            else:
                embeds.set_footer(embed, "Live rankings · Click a period button below to switch views")
            return embed, file
        except Exception as e:
            log.error("Failed to render visual leaderboard card", exc_info=e)
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, (user_id, seconds) in enumerate(active_ranking[:10]):
                member = ctx.guild.get_member(user_id)
                name = member.display_name if member else f"Unknown User ({user_id})"
                prefix = medals[i] if i < 3 else f"`#{i + 1:>2}`"
                you = " ← *you*" if user_id == ctx.author.id else ""
                lines.append(f"{prefix} **{name}** — {format_duration(seconds)}{you}")

            embed = embeds.base_embed(title=title_text, description="\n".join(lines), color=embeds.COLOR_LEVELUP)
            return embed

    @commands.command(name="leaderboard", aliases=["lb", "top"])
    async def leaderboard_cmd(self, ctx: commands.Context, *args: str) -> None:
        """Server leaderboard with clickable period switching.

        Opens on All Time by default; the Today / This Week / This
        Month / All Time buttons re-query live. Optional filters, in
        any order: a period and/or a subject.
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

        async def render(selected_period: str) -> Union[tuple[discord.Embed, discord.File], discord.Embed]:
            return await self._render_leaderboard(ctx, selected_period, subject)

        view = LeaderboardView(author_id=ctx.author.id, initial_period=period, render=render)
        res = await self._render_leaderboard(ctx, period, subject)
        if isinstance(res, tuple):
            embed, file = res
            view.message = await ctx.send(file=file, embed=embed, view=view)
        else:
            view.message = await ctx.send(embed=res, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
