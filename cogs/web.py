"""Chronos Web - starts the website inside the bot process.

The site shares this bot's database connection (nothing to sync) and its live
Discord cache. Events the bot fires with `bot.dispatch("chronos_web_event", ...)`
(session start/stop, AFK prompts, level-ups, drops...) are forwarded to any open
browser tab over Server-Sent Events, and any Discord command a user runs makes
their open tabs refresh - so web and bot always show the same thing.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import embeds
from web import auth
from web.bridge import LiveBridge
from web.events import EventHub
from web.server import build_app, start

log = logging.getLogger("web")


class Web(commands.Cog, name="Web"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hub = EventHub()
        self.runner = None

    async def cog_load(self) -> None:
        if not config.WEB_ENABLED:
            log.info("Chronos Web disabled (WEB_ENABLED=0).")
            return
        try:
            app = build_app(self.bot.db, LiveBridge(self.bot), self.hub)
            self.runner = await start(app, config.WEB_HOST, config.WEB_PORT)
            log.info("Chronos Web listening on %s:%s (public URL %s)",
                     config.WEB_HOST, config.WEB_PORT, config.WEB_BASE_URL)
        except OSError as exc:
            # Port busy etc. must never take the bot down with it.
            log.error("Chronos Web could not start on port %s: %s", config.WEB_PORT, exc)
            self.runner = None
        except Exception:
            log.exception("Chronos Web failed to start; the bot keeps running without it.")
            self.runner = None

    async def cog_unload(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    # ------------------------------------------------------------------ #
    # bot -> browser
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_chronos_web_event(self, user_id: int, guild_id: int, kind: str, data: dict) -> None:
        self.hub.publish(user_id, guild_id, kind, data)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        """Any Discord command changes shared state - tell the user's open tabs."""
        if ctx.guild is not None:
            self.hub.publish(ctx.author.id, ctx.guild.id, "refresh", {"command": ctx.command.qualified_name})

    # ------------------------------------------------------------------ #
    # commands
    # ------------------------------------------------------------------ #
    @commands.command(name="weblogin", aliases=["login", "wl"])
    @commands.guild_only()
    async def weblogin(self, ctx: commands.Context) -> None:
        """Get a private one-time link that signs you in to Chronos Web."""
        token = auth.create_magic(ctx.author.id, ctx.guild.id)
        url = f"{config.WEB_BASE_URL}/auth/magic?t={token}"
        e = embeds.base_embed(
            title="\U0001F310 Your Chronos Web link",
            description=(
                f"[**Open Chronos Web**]({url})\n\n"
                "This link works **once** and expires in **10 minutes**. "
                "Don't share it - anyone with it can sign in as you."
            ),
            color=embeds.COLOR_STUDY,
        )
        try:
            await ctx.author.send(embed=e)
        except discord.HTTPException:
            await ctx.send(embed=embeds.error_embed(
                "I couldn't DM you. Turn on **Direct Messages** for this server and try again."))
            return
        if ctx.guild is not None:
            await ctx.send(embed=embeds.success_embed("Check your DMs", "Your sign-in link is waiting there."))

    @commands.command(name="web", aliases=["website", "site", "chronoweb"])
    async def web_cmd(self, ctx: commands.Context) -> None:
        """Where to find Chronos Web."""
        await ctx.send(embed=embeds.base_embed(
            title="\U0001F310 Chronos Web",
            description=(f"{config.WEB_BASE_URL}\n\nSame account, same sessions, same coins - just bigger. "
                         f"Run `{config.PREFIX}weblogin` to get your sign-in link."),
            color=embeds.COLOR_STUDY,
        ))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Web(bot))
