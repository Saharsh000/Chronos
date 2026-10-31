"""Server-wide bragging rights: `.halloffame` (permanent per-server
records) and `.compare` (head-to-head stat comparison between two
users).
"""
from __future__ import annotations

from typing import Callable, Optional

import discord
from discord.ext import commands

from utils import embeds
from utils.time_format import format_duration

# (hall_of_fame key, display label, value formatter)
HOF_CATEGORIES: list[tuple[str, str, Callable[[int], str]]] = [
    ("total_time", "\u23F1\uFE0F Most Total Study Time", format_duration),
    ("level", "\U0001F396\uFE0F Highest Level", str),
    ("longest_streak", "\U0001F525 Longest Streak Ever", lambda v: f"{v} day{'s' if v != 1 else ''}"),
    ("sessions", "\U0001F4C8 Most Sessions Completed", str),
    ("longest_session", "\u23F3 Longest Single Session", format_duration),
    ("richest", "\U0001F4B0 Richest (Lifetime Coins)", lambda v: f"{v:,} coins"),
    ("achievements", "\U0001F3C5 Most Achievements Unlocked", str),
    ("subject_physics", "\U0001F4D8 Physics Champion", format_duration),
    ("subject_chemistry", "\U0001F9EA Chemistry Champion", format_duration),
    ("subject_maths", "\U0001F4D0 Maths Champion", format_duration),
]

# (display label, compare-context key, value formatter) - all "higher wins".
COMPARE_CATEGORIES: list[tuple[str, str, Callable[[int], str]]] = [
    ("Total Study Time", "total_seconds", format_duration),
    ("Level", "level", str),
    ("Total XP", "xp", lambda v: f"{v:,}"),
    ("Sessions Completed", "sessions_count", str),
    ("Current Streak", "current_streak", lambda v: f"{v}d"),
    ("Longest Streak", "longest_streak", lambda v: f"{v}d"),
    ("Avg Session Length", "avg_session_seconds", format_duration),
    ("Longest Session", "longest_session_seconds", format_duration),
    ("Coins (Lifetime)", "lifetime_earned", lambda v: f"{v:,}"),
    ("Achievements", "achievements_count", str),
    ("Physics Time", "physics_seconds", format_duration),
    ("Chemistry Time", "chemistry_seconds", format_duration),
    ("Maths Time", "maths_seconds", format_duration),
]


def _chunk_into_fields(embed: discord.Embed, lines: list[str], limit: int = 1000) -> None:
    """Discord field values cap at 1024 chars - split a long list of
    lines across clearly labeled fields."""
    chunk: list[str] = []
    length = 0
    chunk_number = 1
    for line in lines:
        if length + len(line) + 1 > limit:
            heading = "Breakdown" if chunk_number == 1 else "More results"
            embed.add_field(name=heading, value="\n".join(chunk), inline=False)
            chunk, length = [], 0
            chunk_number += 1
        chunk.append(line)
        length += len(line) + 1
    if chunk:
        heading = "Breakdown" if chunk_number == 1 else "More results"
        embed.add_field(name=heading, value="\n".join(chunk), inline=False)


class Social(commands.Cog, name="Social"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(name="halloffame", aliases=["hof"])
    @commands.guild_only()
    async def hof_cmd(self, ctx: commands.Context) -> None:
        """See this server's all-time record holders."""
        hof = await self.db.get_hall_of_fame(ctx.guild.id)
        embed = embeds.base_embed(
            title=f"\U0001F3DB\uFE0F Hall of Fame \u2014 {ctx.guild.name}",
            description="Permanent all-time records for this server.",
            color=embeds.COLOR_LEVELUP,
        )
        for key, label, fmt in HOF_CATEGORIES:
            record = hof.get(key)
            if not record:
                embed.add_field(name=label, value="No record yet", inline=False)
                continue
            member = ctx.guild.get_member(record["user_id"])
            name = member.display_name if member else f"Unknown User ({record['user_id']})"
            embed.add_field(name=label, value=f"**{name}** \u2014 {fmt(record['value'])}", inline=False)
        embeds.set_footer(embed, f"{ctx.prefix}leaderboard for live rankings")
        await ctx.send(embed=embed)

    @commands.command(name="compare", aliases=["vs"])
    @commands.guild_only()
    async def compare_cmd(
        self, ctx: commands.Context, member_a: discord.Member, member_b: Optional[discord.Member] = None
    ) -> None:
        """Compare two users across time, level, streaks, economy, and subjects.

        `.compare @user` - you vs. @user
        `.compare @user1 @user2` - @user1 vs. @user2
        """
        a, b = (ctx.author, member_a) if member_b is None else (member_a, member_b)
        if a.id == b.id:
            await ctx.send(embed=embeds.error_embed("Pick two different people to compare."))
            return

        stats_a = await self.db.get_compare_context(a.id, ctx.guild.id)
        stats_b = await self.db.get_compare_context(b.id, ctx.guild.id)

        wins_a = wins_b = 0
        lines = []
        for label, key, fmt in COMPARE_CATEGORIES:
            va, vb = stats_a[key], stats_b[key]
            if va > vb:
                wins_a += 1
                lines.append(f"**{label}** \u2014 \U0001F3C6 {a.display_name} ({fmt(va)}) vs {b.display_name} ({fmt(vb)})")
            elif vb > va:
                wins_b += 1
                lines.append(f"**{label}** \u2014 {a.display_name} ({fmt(va)}) vs \U0001F3C6 {b.display_name} ({fmt(vb)})")
            else:
                lines.append(f"**{label}** \u2014 {a.display_name} ({fmt(va)}) = {b.display_name} ({fmt(vb)})")

        if wins_a > wins_b:
            verdict = f"\U0001F451 **{a.display_name}** mogs **{b.display_name}** ({wins_a}-{wins_b})"
        elif wins_b > wins_a:
            verdict = f"\U0001F451 **{b.display_name}** mogs **{a.display_name}** ({wins_b}-{wins_a})"
        else:
            verdict = f"\U0001F91D Dead even ({wins_a}-{wins_b})"

        embed = embeds.base_embed(
            title=f"\u2694\uFE0F {a.display_name} vs {b.display_name}",
            description=verdict,
            color=embeds.COLOR_LEVELUP,
        )
        _chunk_into_fields(embed, lines)
        embeds.set_footer(embed, f"{ctx.prefix}stats to inspect a full profile")
        await ctx.send(embed=embed)

    @compare_cmd.error
    async def compare_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=embeds.error_embed("I couldn't find that member."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error_embed(f"Usage: `{ctx.prefix}compare @user [@user2]`"))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
        else:
            raise error

    @hof_cmd.error
    async def hof_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Social(bot))
