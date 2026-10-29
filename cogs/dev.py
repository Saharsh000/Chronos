"""Developer-only commands, restricted to a single hardcoded Discord
user id (config.DEV_USER_ID) rather than any guild permission - the
dev can run these in any server the bot is a member of.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import embeds
from utils.checks import is_dev
from utils.subjects import SUBJECT_ALIASES, SUBJECT_HINT, SUBJECT_INFO, normalize_subject_key
from utils.time_format import format_duration, parse_duration
from utils.xp import tier_for_level

log = logging.getLogger("dev")


class Dev(commands.Cog, name="Dev"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(name="addtime")
    @is_dev()
    @commands.guild_only()
    async def add_time_cmd(
        self, ctx: commands.Context, member: discord.Member, duration: str, subject: Optional[str] = None
    ) -> None:
        """[Dev only] Grant a user study time (+ proportional XP) directly.

        Usage: .addtime @user 3h [physics|chemistry|maths]
        """
        seconds = parse_duration(duration)
        if not seconds:
            await ctx.send(embed=embeds.error_embed(
                "Couldn't parse that duration. Try something like `3h`, `45m`, or `1h30m`."
            ))
            return

        subject_key = None
        if subject:
            subject_key = SUBJECT_ALIASES.get(normalize_subject_key(subject))
            if subject_key is None:
                await ctx.send(embed=embeds.error_embed(
                    f"Unknown subject `{subject}`. {SUBJECT_HINT}"
                ))
                return

        result = await self.db.grant_time(member.id, ctx.guild.id, seconds, subject_key)
        log.info(
            f"DEV GRANT     | {ctx.author} ({ctx.author.id}) granted {format_duration(seconds)} "
            f"to {member} ({member.id}) in guild {ctx.guild.id}"
            + (f" [subject={subject_key}]" if subject_key else "")
        )

        embed = embeds.success_embed(
            "Time granted",
            f"Added **{format_duration(seconds)}**, **{result['xp_earned']} XP**, and "
            f"**{result['coins_earned']} coins** to {member.mention}'s stats.",
        )
        if subject_key:
            info = SUBJECT_INFO[subject_key]
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

    @commands.command(name="addxp")
    @is_dev()
    @commands.guild_only()
    async def add_xp_cmd(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        """[Dev only] Grant a user raw XP directly (no time change).

        Usage: .addxp @user 500  (use a negative number to remove XP)
        """
        if amount == 0:
            await ctx.send(embed=embeds.error_embed("Give a non-zero XP amount."))
            return

        result = await self.db.grant_xp(member.id, ctx.guild.id, amount)
        log.info(
            f"DEV XP GRANT  | {ctx.author} ({ctx.author.id}) gave {amount:+d} XP to "
            f"{member} ({member.id}) in guild {ctx.guild.id}"
        )

        embed = embeds.success_embed("XP granted", f"Added **{amount:+d} XP** to {member.mention}.")
        if result["leveled_up"]:
            effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
            tier = tier_for_level(result["new_level"], effective_tiers)
            embed.add_field(
                name="\U0001F389 Level Up!",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}** \u2014 {tier}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="addcoins", aliases=["addcoin"])
    @is_dev()
    @commands.guild_only()
    async def add_coins_cmd(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        """[Dev only] Grant a user raw coins directly.

        Usage: .addcoins @user 500  (use a negative number to remove coins)
        """
        if amount == 0:
            await ctx.send(embed=embeds.error_embed("Give a non-zero coin amount."))
            return

        new_balance = await self.db.grant_coins(member.id, ctx.guild.id, amount)
        log.info(
            f"DEV COIN GRANT| {ctx.author} ({ctx.author.id}) gave {amount:+d} coins to "
            f"{member} ({member.id}) in guild {ctx.guild.id}"
        )
        await ctx.send(embed=embeds.success_embed(
            "Coins granted",
            f"Added **{amount:+d}** coins to {member.mention}. New balance: **{new_balance:,}**.",
        ))

    @commands.command(name="removetime")
    @is_dev()
    @commands.guild_only()
    async def remove_time_cmd(
        self, ctx: commands.Context, member: discord.Member, duration: str, subject: Optional[str] = None
    ) -> None:
        """[Dev only] Subtract study time (+ proportional XP/coins at
        the average rate) from a user's stats. Everything floors at 0.

        Usage: .removetime @user 3h [physics|chemistry|maths]
        """
        seconds = parse_duration(duration)
        if not seconds:
            await ctx.send(embed=embeds.error_embed(
                "Couldn't parse that duration. Try something like `3h`, `45m`, or `1h30m`."
            ))
            return

        subject_key = None
        if subject:
            subject_key = SUBJECT_ALIASES.get(normalize_subject_key(subject))
            if subject_key is None:
                await ctx.send(embed=embeds.error_embed(
                    f"Unknown subject `{subject}`. {SUBJECT_HINT}"
                ))
                return

        result = await self.db.remove_time(member.id, ctx.guild.id, seconds, subject_key)
        log.info(
            f"DEV TIME REMOVE| {ctx.author} ({ctx.author.id}) removed {format_duration(result['seconds_removed'])} "
            f"from {member} ({member.id}) in guild {ctx.guild.id}"
        )

        embed = embeds.success_embed(
            "Time removed",
            f"Removed **{format_duration(result['seconds_removed'])}**, **{result['xp_removed']} XP**, and "
            f"**{result['coins_removed']} coins** from {member.mention}'s stats.",
        )
        if subject_key:
            info = SUBJECT_INFO[subject_key]
            embed.add_field(name="Subject", value=f"{info['emoji']} {info['label']}", inline=True)
        if result["leveled_down"]:
            effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
            tier = tier_for_level(result["new_level"], effective_tiers)
            embed.add_field(
                name="\U0001F4C9 Level Down",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}** \u2014 {tier}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="removexp")
    @is_dev()
    @commands.guild_only()
    async def remove_xp_cmd(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        """[Dev only] Subtract raw XP directly (floors at 0).

        Usage: .removexp @user 500
        """
        if amount <= 0:
            await ctx.send(embed=embeds.error_embed("Give a positive XP amount to remove."))
            return

        result = await self.db.grant_xp(member.id, ctx.guild.id, -amount)
        log.info(
            f"DEV XP REMOVE | {ctx.author} ({ctx.author.id}) removed {amount} XP from "
            f"{member} ({member.id}) in guild {ctx.guild.id}"
        )
        embed = embeds.success_embed("XP removed", f"Removed **{amount} XP** from {member.mention}.")
        if result["new_level"] < result["old_level"]:
            effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
            tier = tier_for_level(result["new_level"], effective_tiers)
            embed.add_field(
                name="\U0001F4C9 Level Down",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}** \u2014 {tier}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="removecoins")
    @is_dev()
    @commands.guild_only()
    async def remove_coins_cmd(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        """[Dev only] Subtract coins directly (floors at 0).

        Usage: .removecoins @user 500
        """
        if amount <= 0:
            await ctx.send(embed=embeds.error_embed("Give a positive coin amount to remove."))
            return

        new_balance = await self.db.remove_coins(member.id, ctx.guild.id, amount)
        log.info(
            f"DEV COIN REMOVE| {ctx.author} ({ctx.author.id}) removed {amount} coins from "
            f"{member} ({member.id}) in guild {ctx.guild.id}"
        )
        await ctx.send(embed=embeds.success_embed(
            "Coins removed",
            f"Removed **{amount}** coins from {member.mention}. New balance: **{new_balance:,}**.",
        ))

    @commands.command(name="backupdb")
    @is_dev()
    async def backup_db_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Download the current SQLite database directly in Discord."""
        await self.db.conn.commit()
        await ctx.send(
            content="\U0001F4BE **Here is your live database backup:**",
            file=discord.File(config.DB_PATH, filename="chronos.sqlite3")
        )

    @commands.command(name="restoredb")
    @is_dev()
    async def restore_db_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Restore the SQLite database by attaching a .sqlite3 or .sql file."""
        if not ctx.message.attachments:
            await ctx.send(embed=embeds.error_embed("Please attach your `chronos.sqlite3` file to this command!"))
            return

        att = ctx.message.attachments[0]
        if not (att.filename.endswith(".sqlite3") or att.filename.endswith(".db")):
            await ctx.send(embed=embeds.error_embed("Attachment must be a `.sqlite3` or `.db` file."))
            return

        await self.db.close()
        await att.save(config.DB_PATH)
        await self.db.connect()

        await ctx.send(embed=embeds.success_embed(
            "Database Restored",
            f"Successfully restored `{config.DB_PATH}`! All progress, stats, and streaks are live.",
        ))

    @add_time_cmd.error
    @add_xp_cmd.error
    @add_coins_cmd.error
    @remove_time_cmd.error
    @remove_xp_cmd.error
    @remove_coins_cmd.error
    @backup_db_cmd.error
    @restore_db_cmd.error
    async def dev_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=embeds.error_embed("This command is restricted to the bot's developer."))
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=embeds.error_embed("I couldn't find that member."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error_embed(
                f"Usage: `{ctx.prefix}{ctx.command.name} @user <amount>` \u2014 see `{ctx.prefix}help`."
            ))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=embeds.error_embed(str(error)))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Dev(bot))
