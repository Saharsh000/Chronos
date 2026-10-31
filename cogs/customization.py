"""Dev-only branding customization: rename tiers, and add/remove
custom purchasable profile tags (titles) - per server, at runtime,
no redeploy needed.

utils/xp.py's TIERS and utils/economy.py's SHOP_ITEMS remain the
global defaults/fallback: editing those files directly still works
exactly like before (a full-bot-wide change), and is still the right
move for something that should apply everywhere. This cog is for a
single server wanting its own names without touching code.
"""
from __future__ import annotations

import logging

from discord.ext import commands

from utils import economy, embeds
from utils.checks import is_dev
from utils.xp import TIERS

log = logging.getLogger("customization")


class Customization(commands.Cog, name="Customization"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ------------------------------------------------------------------ #
    # Tiers
    # ------------------------------------------------------------------ #
    @commands.command(name="tiers")
    @commands.guild_only()
    async def tiers_cmd(self, ctx: commands.Context) -> None:
        """Show this server's current tier names (defaults + any dev renames)."""
        overrides = await self.db.get_tier_overrides(ctx.guild.id)
        lines = []
        for level, default_name in TIERS:
            if level in overrides:
                lines.append(f"**Lv. {level}+** \u2014 {overrides[level]} *(renamed from {default_name})*")
            else:
                lines.append(f"**Lv. {level}+** \u2014 {default_name}")
        embed = embeds.base_embed(
            title=f"\U0001F3C5 Tiers \u2014 {ctx.guild.name}", description="\n".join(lines), color=embeds.COLOR_SOCIAL
        )
        await ctx.send(embed=embed)

    @commands.command(name="settier")
    @is_dev()
    @commands.guild_only()
    async def set_tier_cmd(self, ctx: commands.Context, level: int, *, name: str) -> None:
        """[Dev only] Rename the tier at a given level threshold for this server.

        Usage: `.settier 100 \U0001F480 Grandmaster` - level must be one of the
        existing thresholds (see `.tiers`); only the name/emoji changes,
        not the XP required to reach it.
        """
        valid_levels = {lvl for lvl, _ in TIERS}
        if level not in valid_levels:
            await ctx.send(embed=embeds.error_embed(
                f"`{level}` isn't a tier threshold. Valid levels: {', '.join(str(l) for l in sorted(valid_levels))}."
            ))
            return

        await self.db.set_tier_override(ctx.guild.id, level, name)
        log.info(f"TIER RENAME   | {ctx.author} ({ctx.author.id}) renamed tier {level} to '{name}' in guild {ctx.guild.id}")
        await ctx.send(embed=embeds.success_embed(
            "Tier renamed", f"Level {level}+ is now called **{name}** in this server."
        ))

    @commands.command(name="resettier")
    @is_dev()
    @commands.guild_only()
    async def reset_tier_cmd(self, ctx: commands.Context, level: int) -> None:
        """[Dev only] Reset one tier back to its default name."""
        reset = await self.db.reset_tier_override(ctx.guild.id, level)
        if not reset:
            await ctx.send(embed=embeds.error_embed(f"Level {level} wasn't renamed - nothing to reset."))
            return
        await ctx.send(embed=embeds.success_embed("Tier reset", f"Level {level}+ is back to its default name."))

    @commands.command(name="resettiers")
    @is_dev()
    @commands.guild_only()
    async def reset_all_tiers_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Reset all tiers in this server back to defaults."""
        count = await self.db.reset_all_tier_overrides(ctx.guild.id)
        await ctx.send(embed=embeds.success_embed("Tiers reset", f"Reset {count} tier rename(s) back to default."))

    # ------------------------------------------------------------------ #
    # Custom shop tags/titles
    # ------------------------------------------------------------------ #
    @commands.command(name="tags")
    @commands.guild_only()
    async def tags_cmd(self, ctx: commands.Context) -> None:
        """List all purchasable profile titles/tags available in this server."""
        custom = await self.db.get_custom_tags(ctx.guild.id)
        embed = embeds.base_embed(
            title=f"\U0001F3F7\uFE0F Tags & Titles \u2014 {ctx.guild.name}",
            color=embeds.COLOR_SOCIAL,
        )

        builtin_lines = [
            f"{item['emoji']} **{item['title_text']}** \u2014 {item['price']:,} coins"
            for item in economy.SHOP_ITEMS.values() if item["type"] == "title"
        ]
        embed.add_field(name="Built-in", value="\n".join(builtin_lines) or "None", inline=False)

        if custom:
            custom_lines = [
                f"{item['emoji']} **{item['title_text']}** \u2014 {item['price']:,} coins (`{item_id}`)"
                for item_id, item in custom.items()
            ]
            embed.add_field(name="Custom (added by this server)", value="\n".join(custom_lines), inline=False)

        embeds.set_footer(embed, f"{ctx.prefix}buy <title>")
        await ctx.send(embed=embed)

    @commands.command(name="addtag")
    @is_dev()
    @commands.guild_only()
    async def add_tag_cmd(self, ctx: commands.Context, price: int, *, tag_text: str) -> None:
        """[Dev only] Add a new purchasable profile title/tag to this server's shop.

        Usage: `.addtag 500 The Grinder`
        """
        if price < 0:
            await ctx.send(embed=embeds.error_embed("Price must be 0 or higher."))
            return

        item_id = await self.db.add_custom_tag(ctx.guild.id, tag_text, price)
        log.info(f"TAG ADD       | {ctx.author} ({ctx.author.id}) added tag '{tag_text}' (id={item_id}) in guild {ctx.guild.id}")
        await ctx.send(embed=embeds.success_embed(
            "Tag added",
            f"**{tag_text}** is now purchasable for **{price:,} coins** via `{ctx.prefix}buy {tag_text}`.",
        ))

    @commands.command(name="removetag")
    @is_dev()
    @commands.guild_only()
    async def remove_tag_cmd(self, ctx: commands.Context, *, tag_text: str) -> None:
        """[Dev only] Remove a custom tag/title from this server's shop
        (built-in ones from utils/economy.py can't be removed this way)."""
        custom = await self.db.get_custom_tags(ctx.guild.id)
        match_id = None
        for item_id, item in custom.items():
            if item_id == tag_text or item["title_text"].lower() == tag_text.strip().lower():
                match_id = item_id
                break

        if match_id is None:
            await ctx.send(embed=embeds.error_embed(
                f"No custom tag matching `{tag_text}` found. Check `{ctx.prefix}tags`."
            ))
            return

        await self.db.remove_custom_tag(ctx.guild.id, match_id)
        await ctx.send(embed=embeds.success_embed("Tag removed", f"**{tag_text}** is no longer purchasable."))

    @set_tier_cmd.error
    @reset_tier_cmd.error
    @reset_all_tiers_cmd.error
    @add_tag_cmd.error
    @remove_tag_cmd.error
    async def customization_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error_embed(f"Missing an argument for `.{ctx.command.name}`."))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=embeds.error_embed("Couldn't parse that - check the command's argument types."))
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(embed=embeds.error_embed("This command is developer-only."))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Customization(bot))
