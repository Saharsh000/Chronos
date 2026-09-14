"""Server configuration commands. Requires the Administrator permission
for `.make` (it creates channels) and Manage Server for the rest.
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from utils import embeds
from utils.subjects import SUBJECT_INFO, SUBJECTS

log = logging.getLogger("admin")

CATEGORY_NAME = "\U0001F4DA Study Rooms"


class Admin(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(name="setcheckin")
    @commands.has_permissions(manage_guild=True)
    async def set_checkin(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the channel used for AFK prompts, session summaries, level-ups, and Pomodoro announcements."""
        await self.db.set_checkin_channel(ctx.guild.id, channel.id)
        await ctx.send(embed=embeds.success_embed(
            "Check-in channel set",
            f"AFK prompts, level-ups, and Pomodoro updates will now be posted in {channel.mention}.",
        ))

    @commands.command(name="make")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def make_rooms(self, ctx: commands.Context) -> None:
        """Create (or verify) the Physics / Chemistry / Maths study voice rooms."""
        guild = ctx.guild
        cfg = await self.db.get_guild_config(guild.id)
        existing_ids = {
            "physics": cfg.get("physics_channel_id"),
            "chemistry": cfg.get("chemistry_channel_id"),
            "maths": cfg.get("maths_channel_id"),
        }

        category = None
        for cid in existing_ids.values():
            ch = guild.get_channel(cid) if cid else None
            if ch is not None and ch.category is not None:
                category = ch.category
                break
        if category is None:
            category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if category is None:
            try:
                category = await guild.create_category(CATEGORY_NAME, reason=f"Requested by {ctx.author}")
            except discord.Forbidden:
                await ctx.send(embed=embeds.error_embed(
                    "I need the **Manage Channels** permission to create study rooms."
                ))
                return

        created: list[discord.VoiceChannel] = []
        reused: list[discord.VoiceChannel] = []
        new_ids = dict(existing_ids)

        for key in SUBJECTS:
            current = guild.get_channel(existing_ids.get(key)) if existing_ids.get(key) else None
            if current is not None:
                reused.append(current)
                continue
            try:
                channel = await guild.create_voice_channel(
                    SUBJECT_INFO[key]["channel_name"], category=category, reason=f"Requested by {ctx.author}"
                )
            except discord.Forbidden:
                await ctx.send(embed=embeds.error_embed(
                    "I need the **Manage Channels** permission to create study rooms."
                ))
                return
            new_ids[key] = channel.id
            created.append(channel)
            log.info(f"ROOM CREATED  | #{channel.name} ({key}) in guild '{guild.name}' by {ctx.author}")

        await self.db.set_subject_channels(
            guild.id, new_ids.get("physics"), new_ids.get("chemistry"), new_ids.get("maths")
        )

        lines = []
        if created:
            lines.append("**Created:** " + ", ".join(c.mention for c in created))
        if reused:
            lines.append("**Already existed:** " + ", ".join(c.mention for c in reused))
        lines.append(f"\nJoin one of these and run `{ctx.prefix}start` to get subject-specific credit.")

        await ctx.send(embed=embeds.success_embed("Study rooms ready", "\n".join(lines)))

    @commands.command(name="config")
    @commands.has_permissions(manage_guild=True)
    async def show_config(self, ctx: commands.Context) -> None:
        """Show the current server configuration."""
        cfg = await self.db.get_guild_config(ctx.guild.id)
        channel_id = cfg.get("checkin_channel_id")
        channel = ctx.guild.get_channel(channel_id) if channel_id else None

        embed = embeds.info_embed("\u2699\uFE0F Server Configuration")
        embed.add_field(
            name="Check-in / announcements channel",
            value=channel.mention if channel else f"Not set \u2014 use `{ctx.prefix}setcheckin #channel`",
            inline=False,
        )

        room_lines = []
        for key in SUBJECTS:
            cid = cfg.get(f"{key}_channel_id")
            ch = ctx.guild.get_channel(cid) if cid else None
            info = SUBJECT_INFO[key]
            room_lines.append(f"{info['emoji']} {info['label']}: {ch.mention if ch else 'Not set'}")
        room_lines.append(f"\nUse `{ctx.prefix}make` to create them.")
        embed.add_field(name="Study rooms", value="\n".join(room_lines), inline=False)

        await ctx.send(embed=embed)

    @set_checkin.error
    @make_rooms.error
    @show_config.error
    async def admin_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            perm = "Administrator" if ctx.command.name == "make" else "Manage Server"
            await ctx.send(embed=embeds.error_embed(f"You need the **{perm}** permission to do that."))
        elif isinstance(error, commands.ChannelNotFound):
            await ctx.send(embed=embeds.error_embed("I couldn't find that channel. Try mentioning it, e.g. `#general`."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error_embed(f"Usage: `{ctx.prefix}setcheckin #channel`"))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
