"""Entry point: wires together the database, cogs, and Discord client.

Run with:  python bot.py
(after copying .env.example to .env and filling in DISCORD_TOKEN)
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

import config
from database import Database
from utils.logger import setup_logging

log = logging.getLogger("bot")

INITIAL_EXTENSIONS = (
    "cogs.sessions",
    "cogs.pomodoro",
    "cogs.stats",
    "cogs.economy",
    "cogs.pets",
    "cogs.eggs",
    "cogs.achievements",
    "cogs.social",
    "cogs.progress",
    "cogs.customization",
    "cogs.admin",
    "cogs.dev",
    "cogs.help",
)


class ChronosBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # required to read prefix commands
        intents.voice_states = True     # required for Pomodoro + detecting subject rooms
        intents.members = True          # required to resolve members for leaderboards/mentions

        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )
        self.db = Database(config.DB_PATH)

    async def setup_hook(self) -> None:
        # The database must be connected *before* any cog loads, since
        # every cog grabs `bot.db` in its own __init__.
        await self.db.connect()
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                log.info(f"Loaded extension: {extension}")
            except Exception:
                log.exception(f"Failed to load extension: {extension}")

    async def on_ready(self) -> None:
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info(f"Connected to {len(self.guilds)} guild(s) \u00B7 prefix = '{config.PREFIX}'")
        activity = discord.Activity(type=discord.ActivityType.watching, name=f"{config.PREFIX}help")
        await self.change_presence(activity=activity)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        from utils import embeds

        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error_embed(f"Missing argument: `{error.param.name}`."))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=embeds.error_embed(str(error)))
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=embeds.error_embed("You don't have permission to do that."))
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=embeds.error_embed("You can't use that command."))
            return
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=embeds.error_embed(f"Slow down! Try again in {error.retry_after:.1f}s."))
            return

        log.exception(f"Unhandled error in command '{ctx.command}':", exc_info=error)
        await ctx.send(embed=embeds.error_embed("Something went wrong running that command."))

    async def close(self) -> None:
        log.info("Shutting down...")
        await self.db.close()
        await super().close()


async def main() -> None:
    setup_logging()
    config.validate()
    bot = ChronosBot()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user, exiting.")
