"""Custom embed-based help command (this bot is prefix-only - no slash commands)."""
from __future__ import annotations

from discord.ext import commands

import config
from utils import embeds


class Help(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_cmd(self, ctx: commands.Context) -> None:
        prefix = ctx.prefix
        embed = embeds.base_embed(
            title="\u23F3 Chronos \u2014 Commands",
            description=(
                "A study/focus tracker: `.start`/`.stop` sessions, randomized XP and coins, "
                "levels, streaks, a coin shop, achievements, and leaderboards."
            ),
            color=embeds.COLOR_PRIMARY,
        )
        embed.add_field(
            name="\U0001F4D6 Study Sessions",
            value=(
                f"`{prefix}start [subject]` \u2014 start a session, optionally tagged: "
                f"`{prefix}start physics`/`phy`/`p` (same for chemistry/`chem`/`c`, maths/`math`/`m`)\n"
                f"`{prefix}stop` \u2014 end your current session\n"
                f"`{prefix}session` \u2014 view your current live session\n"
                f"`{prefix}active` \u2014 see everyone currently studying in this server"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F4C8 Stats & Leaderboards",
            value=(
                f"`{prefix}stats [@user]` \u2014 in-depth study statistics: time, level, streak, "
                f"coins, achievements, and behavioral analytics\n"
                f"`{prefix}rank [@user]` \u2014 view level, XP, and tier\n"
                f"`{prefix}subjects [@user]` \u2014 Physics/Chemistry/Maths time breakdown\n"
                f"`{prefix}leaderboard [period] [subject]` \u2014 server leaderboard, e.g. "
                f"`{prefix}leaderboard week physics` (aliases: `{prefix}lb`, `{prefix}top`)\n"
                f"`{prefix}halloffame` \u2014 this server's permanent all-time records (alias: `{prefix}hof`)\n"
                f"`{prefix}compare @user [@user2]` \u2014 head-to-head stat comparison (alias: `{prefix}vs`)"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F3C5 Achievements",
            value=(
                f"`{prefix}achievements [@user | category]` \u2014 browse unlocked/locked badges "
                f"(aliases: `{prefix}badges`, `{prefix}ach`)"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F4DA JEE Syllabus & Progress",
            value=(
                f"`{prefix}syllabus [subject] [chapter]` \u2014 browse the JEE Main syllabus (alias: `{prefix}syl`)\n"
                f"`{prefix}chapterdone <subject> <chapter>` \u2014 log a completed chapter (must match the syllabus)\n"
                f"`{prefix}subtopicdone <subject> <chapter> <subtopic>` \u2014 log a completed subtopic\n"
                f"`{prefix}bookdone <subject> <book>` \u2014 log a completed book\n"
                f"`{prefix}pyq <year> [subject]` \u2014 log a completed year of previous-year questions\n"
                f"`{prefix}revision <number> [subject]` \u2014 log a completed revision pass\n"
                f"`{prefix}progress [@user]` \u2014 see everything you've logged so far"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001FA99 Coin Economy",
            value=(
                f"`{prefix}daily` \u2014 claim your once-a-day coin reward (streak bonuses stack)\n"
                f"`{prefix}work` \u2014 quick task for coins + XP, short cooldown (alias: `{prefix}grind`)\n"
                f"`{prefix}weekly` \u2014 a big once-a-week coin reward + a free Mystery Box\n"
                f"`{prefix}balance` \u2014 check your coin balance (aliases: `{prefix}bal`, `{prefix}coins`)\n"
                f"`{prefix}shop` \u2014 browse purchasable items\n"
                f"`{prefix}buy <item> [quantity]` \u2014 purchase an item, optionally several at once\n"
                f"`{prefix}inventory` \u2014 see what you own, including pet food (alias: `{prefix}inv`)\n"
                f"`{prefix}use <item>` \u2014 activate a boost item\n"
                f"`{prefix}openbox` \u2014 open a Mystery Box\n"
                f"`{prefix}settitle <title|none>` \u2014 equip an owned cosmetic title"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F43E Pets & Food",
            value=(
                f"`{prefix}petshop [tier]` \u2014 browse buyable pets, by tier (alias: `{prefix}pshop`)\n"
                f"`{prefix}buypet <name>` \u2014 unlock a pet species (requires Level 10+)\n"
                f"`{prefix}pets [@user]` \u2014 see owned pets\n"
                f"`{prefix}pet [name]` \u2014 detailed stats for one pet (defaults to your equipped pet)\n"
                f"`{prefix}equip <name>` \u2014 set your active pet - only it earns XP and gets fed\n"
                f"`{prefix}nickname <name> <new name>` \u2014 rename an owned pet (alias: `{prefix}nick`)\n"
                f"`{prefix}foodshop [tier]` \u2014 browse pet food, by tier (alias: `{prefix}fshop`)\n"
                f"`{prefix}buyfood <name> [qty]` \u2014 buy food\n"
                f"`{prefix}feed <name> [qty]` \u2014 feed your equipped pet\n"
                f"`{prefix}sellfood <name> [qty]` \u2014 sell food back for half price"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F345 Pomodoro",
            value=f"`{prefix}pomodoro` \u2014 check the Pomodoro cycle running in your voice channel (alias: `{prefix}pomo`)",
            inline=False,
        )
        embed.add_field(
            name="\U0001F3F7\uFE0F Customization",
            value=(
                f"`{prefix}tiers` \u2014 see this server's current tier names\n"
                f"`{prefix}tags` \u2014 see purchasable profile titles/tags"
            ),
            inline=False,
        )
        embed.add_field(
            name="\u2699\uFE0F Admin",
            value=(
                f"`{prefix}make` \u2014 *(Administrator)* create the Physics/Chemistry/Maths study rooms\n"
                f"`{prefix}setcheckin #channel` \u2014 *(Manage Server)* set the AFK/announcements channel\n"
                f"`{prefix}config` \u2014 *(Manage Server)* show current server configuration"
            ),
            inline=False,
        )
        embed.add_field(
            name="\u2139\uFE0F How it works",
            value=(
                f"XP and coins are earned in randomized per-minute amounts while your session runs - "
                f"they show up within about a minute, not just when you `{prefix}stop`.\n"
                f"Your equipped pet (`{prefix}equip`) also earns a little XP passively while you study, "
                f"on top of whatever you `{prefix}feed` it.\n"
                f"Every **{config.CHECKIN_INTERVAL_MINUTES} minutes** you'll be asked to confirm you're "
                f"still active; react within **{config.AFK_GRACE_MINUTES} minutes** or the session ends "
                f"automatically.\n"
                f"All \"day\" boundaries (streaks, `{prefix}daily`, weekday stats) are anchored to **IST**, "
                f"not UTC or your local time.\n"
                f"Studying on consecutive days builds a **study streak** - a Streak Freeze item (from the "
                f"shop) auto-protects it if you miss exactly one day.\n"
                f"Chapters/subtopics can only be logged from the official JEE syllabus (`{prefix}syllabus`) - "
                f"books, PYQs, and revisions are free text.\n"
                f"If you're connected to a Physics/Chemistry/Maths room when you `{prefix}start`, that "
                f"session also counts toward your subject-specific stats."
            ),
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
