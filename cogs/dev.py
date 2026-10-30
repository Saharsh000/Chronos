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

    @commands.command(name="addcandy")
    @is_dev()
    @commands.guild_only()
    async def add_candy_cmd(
        self, ctx: commands.Context, member: discord.Member, amount: int
    ) -> None:
        """[Dev only] Grant seasonal Candy to a user.
        
        Usage: .addcandy @user 500
        """
        new_balance = await self.db.add_candy(member.id, ctx.guild.id, amount)
        await ctx.send(
            embed=embeds.success_embed(
                "\U0001F36C Candy Granted",
                f"Gave **{amount:,} 🍬 Candy** to {member.mention}! New balance: **{new_balance:,} 🍬**.",
            )
        )

    @commands.command(name="addbox")
    @is_dev()
    @commands.guild_only()
    async def add_box_cmd(
        self, ctx: commands.Context, member: discord.Member, tier_query: str, quantity: int = 1
    ) -> None:
        """[Dev only] Grant Hallo-Boxes to a user directly.

        Usage: .addbox @user common / .addbox @user legendary 3
        """
        from utils import halloween as halloween_catalog
        box_id = halloween_catalog.resolve_box_id(tier_query)
        if not box_id:
            await ctx.send(embed=embeds.error_embed(f"Unknown box tier `{tier_query}`."))
            return

        box = halloween_catalog.get_box(box_id)
        await self.db.add_item(member.id, ctx.guild.id, box_id, quantity)
        await ctx.send(
            embed=embeds.success_embed(
                f"{box['emoji']} Hallo-Boxes Granted",
                f"Gave **\u00D7{quantity} {box['name']}** to {member.mention}!",
            )
        )

    @commands.command(name="addpasstime")
    @is_dev()
    @commands.guild_only()
    async def add_pass_time_cmd(
        self, ctx: commands.Context, member: discord.Member, minutes: int
    ) -> None:
        """[Dev only] Credit Halloween Season Pass study minutes to test carving progression.
        
        Usage: .addpasstime @user 120 (adds 2 hours of pass progress)
        """
        seconds = minutes * 60
        result = await self.db.credit_halloween_study(member.id, ctx.guild.id, seconds)
        pass_data = result["pass"]
        total_m = pass_data["study_seconds"] // 60
        unlocked = result.get("new_level_unlocked")
        unlocked_msg = f"\n🎉 **Unlocked Level {unlocked['level']}: {unlocked['level_name']}!**" if unlocked else ""
        await ctx.send(
            embed=embeds.success_embed(
                "🎃 Pass Progress Credited",
                f"Added **{minutes} minutes** of pass study time to {member.mention}.\n"
                f"Total event study time: **{total_m}m** ({total_m / 60:.1f}h).{unlocked_msg}",
            )
        )

    @commands.command(name="checkdb")
    @is_dev()
    async def check_db_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Inspect database row counts, active guild, and user balances."""
        tables = [
            "user_stats", "subject_stats", "sessions", "session_log",
            "user_currency", "user_inventory", "achievements_unlocked", "user_pets"
        ]
        counts = {}
        for t in tables:
            try:
                cur = await self.db.conn.execute(f"SELECT COUNT(*) as cnt FROM {t}")
                row = await cur.fetchone()
                counts[t] = row["cnt"] if row else 0
            except Exception as e:
                counts[t] = f"Err: {e}"

        cur_curr = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
        cur_stats = await self.db.get_or_create_user_stats(ctx.author.id, ctx.guild.id)
        pets = await self.db.get_owned_pets(ctx.author.id, ctx.guild.id)

        # Get all distinct guilds in database
        cur_g = await self.db.conn.execute("SELECT DISTINCT guild_id FROM user_currency")
        guild_ids = [str(r["guild_id"]) for r in await cur_g.fetchall()]
        guilds_str = ", ".join(guild_ids) if guild_ids else "None"

        embed = embeds.base_embed(
            title="\U0001F50D Database Diagnostics",
            description=f"**Current Server ID:** `{ctx.guild.id}`\n**Known Guild IDs in DB:** `{guilds_str}`",
            color=embeds.COLOR_INFO,
        )

        pet_names = [p.get("nickname", p.get("species_id", "Pet")) for p in pets]
        pets_str = ", ".join(pet_names) if pet_names else "None"

        embed.add_field(
            name="Your Profile in this Server",
            value=(
                f"\u25B8 **Level:** {cur_stats.get('level', 0)} ({cur_stats.get('xp', 0):,} XP)\n"
                f"\u25B8 **Coins:** {cur_curr.get('coins', 0):,} (Lifetime: {cur_curr.get('lifetime_earned', 0):,})\n"
                f"\u25B8 **Streak:** {cur_stats.get('current_streak', 0)} days\n"
                f"\u25B8 **Pets:** {pets_str}"
            ),
            inline=False,
        )

        table_lines = [f"\u25B8 **{t}:** {counts[t]} rows" for t in tables]
        embed.add_field(name="Table Row Counts", value="\n".join(table_lines), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="forceseed")
    @is_dev()
    async def force_seed_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Force restore seed_data.sql and sync all data to the current server."""
        await ctx.send("\u23F3 Importing `seed_data.sql` and restoring all user data...")
        result = await self.db.force_seed(target_guild_id=ctx.guild.id)
        if not result.get("success"):
            await ctx.send(embed=embeds.error_embed(f"Force seed failed: {result.get('reason')}"))
            return

        cur_curr = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
        cur_stats = await self.db.get_or_create_user_stats(ctx.author.id, ctx.guild.id)
        pets = await self.db.get_owned_pets(ctx.author.id, ctx.guild.id)

        embed = embeds.success_embed(
            "\u2705 Database Seeded & Restored Successfully!",
            (
                f"**Target Server:** `{ctx.guild.id}`\n\n"
                f"\u25B8 **Your Balance:** {cur_curr.get('coins', 0):,} coins\n"
                f"\u25B8 **Your Level:** Level {cur_stats.get('level', 0)} ({cur_stats.get('xp', 0):,} XP)\n"
                f"\u25B8 **Your Streak:** {cur_stats.get('current_streak', 0)} days\n"
                f"\u25B8 **Your Pets:** {len(pets)} pet(s) active\n\n"
                f"**Database Totals:**\n"
                f"\u25B8 `user_stats`: {result['user_stats_count']} rows\n"
                f"\u25B8 `user_currency`: {result['user_currency_count']} rows\n"
                f"\u25B8 `sessions`: {result['sessions_count']} rows\n"
                f"\u25B8 `user_pets`: {result['user_pets_count']} rows\n"
                f"\u25B8 Rows synced to this server: {result.get('synced_rows_to_target', 0)}"
            ),
        )
        await ctx.send(embed=embed)

    @commands.command(name="syncguild")
    @is_dev()
    async def sync_guild_cmd(self, ctx: commands.Context, source_guild_id: Optional[int] = 1483039226693030083) -> None:
        """[Dev only] Copy all stats, coins, pets, and inventory from source guild to current guild."""
        total = await self.db.sync_guild_data(source_guild_id, ctx.guild.id)
        cur_curr = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
        await ctx.send(embed=embeds.success_embed(
            "Guild Data Synced",
            f"Synced **{total}** rows from `{source_guild_id}` to `{ctx.guild.id}`!\n"
            f"Your balance in this server is now **{cur_curr.get('coins', 0):,}** coins.",
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
    @add_candy_cmd.error
    @add_box_cmd.error
    @add_pass_time_cmd.error
    @check_db_cmd.error
    @force_seed_cmd.error
    @sync_guild_cmd.error
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
