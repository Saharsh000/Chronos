"""`.achievements` - browse unlocked/locked badges, by category."""
from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from utils import embeds
from utils.achievements import ACHIEVEMENTS, ACHIEVEMENTS_BY_ID, CATEGORY_ORDER, Achievement
from utils.time_format import discord_timestamp


def _progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "\u2591" * length
    filled = round(length * min(1.0, current / total))
    return "\u2588" * filled + "\u2591" * (length - filled)


class Achievements(commands.Cog, name="Achievements"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(name="achievements", aliases=["badges", "ach"])
    @commands.guild_only()
    async def achievements_cmd(
        self, ctx: commands.Context, *, arg: Optional[str] = None
    ) -> None:
        """View your (or someone else's) unlocked achievements.

        `.achievements` - overview with progress per category
        `.achievements <category>` - full list for one category (e.g. `.achievements Streaks`)
        `.achievements @user` - view someone else's overview
        """
        target = ctx.author
        category_filter: Optional[str] = None

        if arg:
            member = await self._try_resolve_member(ctx, arg)
            if member is not None:
                target = member
            else:
                match = next((c for c in CATEGORY_ORDER if c.lower() == arg.strip().lower()), None)
                if match is None:
                    await ctx.send(embed=embeds.error_embed(
                        f"Unknown category `{arg}`. Try one of: {', '.join(CATEGORY_ORDER)}."
                    ))
                    return
                category_filter = match

        # Trigger a fresh check so anything earned but not yet recorded
        # (e.g. right after a dev grant) shows up immediately.
        await self.db.check_achievements(target.id, ctx.guild.id)
        unlocked_rows = await self.db.get_unlocked_achievements_detailed(target.id, ctx.guild.id)
        unlocked_at = {r["achievement_id"]: r["unlocked_at"] for r in unlocked_rows}

        if category_filter:
            await self._send_category(ctx, target, category_filter, unlocked_at)
        else:
            await self._send_overview(ctx, target, unlocked_at)

    async def _send_overview(
        self, ctx: commands.Context, target: discord.Member, unlocked_at: dict[str, int]
    ) -> None:
        embed = embeds.base_embed(
            title=f"\U0001F3C5 Achievements \u2014 {target.display_name}",
            description=(
                f"**{len(unlocked_at)} / {len(ACHIEVEMENTS)}** unlocked overall.\n"
                f"Use `{ctx.prefix}achievements <category>` to see the full list for one category."
            ),
            color=embeds.COLOR_LEVELUP,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        by_category: dict[str, list[Achievement]] = {}
        for a in ACHIEVEMENTS:
            by_category.setdefault(a.category, []).append(a)

        for category in CATEGORY_ORDER:
            items = by_category.get(category, [])
            done = sum(1 for a in items if a.id in unlocked_at)
            bar = _progress_bar(done, len(items))
            embed.add_field(name=category, value=f"`{bar}` {done}/{len(items)}", inline=True)

        recent = sorted(unlocked_at.items(), key=lambda kv: kv[1], reverse=True)[:3]
        if recent:
            lines = []
            for achievement_id, ts in recent:
                a = ACHIEVEMENTS_BY_ID.get(achievement_id)
                if a:
                    lines.append(f"{a.emoji} **{a.name}** \u2014 {discord_timestamp(ts, 'R')}")
            if lines:
                embed.add_field(name="Most Recent", value="\n".join(lines), inline=False)

        await ctx.send(embed=embed)

    async def _send_category(
        self, ctx: commands.Context, target: discord.Member, category: str, unlocked_at: dict[str, int]
    ) -> None:
        items = [a for a in ACHIEVEMENTS if a.category == category]
        done = sum(1 for a in items if a.id in unlocked_at)

        embed = embeds.base_embed(
            title=f"\U0001F3C5 {category} \u2014 {target.display_name}",
            description=f"**{done} / {len(items)}** unlocked in this category.",
            color=embeds.COLOR_LEVELUP,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        lines = []
        for a in items:
            reward = f" (+{a.reward_coins:,} coins)" if a.reward_coins else ""
            if a.id in unlocked_at:
                lines.append(f"\u2705 {a.emoji} **{a.name}** \u2014 {a.description}{reward}")
            else:
                lines.append(f"\U0001F512 {a.emoji} {a.name} \u2014 {a.description}{reward}")

        # Embed field values cap at 1024 chars - chunk if a category gets long.
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

    @staticmethod
    async def _try_resolve_member(ctx: commands.Context, text: str) -> Optional[discord.Member]:
        try:
            converter = commands.MemberConverter()
            return await converter.convert(ctx, text)
        except commands.BadArgument:
            return None

    @achievements_cmd.error
    async def achievements_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Achievements(bot))
