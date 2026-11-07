"""Coin economy: `.shop` / `.buy` / `.inventory` / `.use` / `.openbox` /
`.settitle` / `.balance`, plus the `.daily` claim command.

Coins themselves are earned automatically while studying (see
database.py's `_random_minute_coins`, credited alongside XP) - this
cog is just the spending/claiming side of the economy.
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
import time
from typing import Optional

import discord
from discord.ext import commands

from utils import economy
from utils import embeds
from utils import emojis
from utils import food as food_catalog
from utils import halloween as halloween_catalog
from utils.beg_scenarios import roll_beg_scenario
from utils.stats_card import render_inventory_card_sync, render_shop_card_sync
from utils.time_format import format_duration
from utils.xp import tier_for_level, xp_progress

log = logging.getLogger("economy")


class Economy(commands.Cog, name="Economy"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def _announce_achievements(self, ctx: commands.Context) -> None:
        newly = await self.db.check_achievements(ctx.author.id, ctx.guild.id)
        if newly:
            await ctx.send(embed=embeds.achievement_unlock_embed(ctx.author, newly))

    # ------------------------------------------------------------------ #
    # Balance
    # ------------------------------------------------------------------ #
    @commands.command(name="balance", aliases=["coins", "chronocoins", "chronocoin", "bal"])
    @commands.guild_only()
    async def balance_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Check your (or someone else's) Chronocoin balance."""
        target = member or ctx.author
        currency = await self.db.get_or_create_currency(target.id, ctx.guild.id)
        candy = currency.get("candy", 0)
        coin_e = emojis.coin(ctx.guild)
        embed = embeds.base_embed(
            title=f"{coin_e} {target.display_name}'s Wallet",
            description=(
                f"💰 **Balance**\n{currency['coins']:,} {coin_e} Chronocoins\n\n"
                f"🍬 **Candy**\n{candy:,} candy\n\n"
                f"📈 **Lifetime earned**\n{currency['lifetime_earned']:,} {coin_e} Chronocoins"
            ),
            color=embeds.COLOR_ECONOMY,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # Shop
    # ------------------------------------------------------------------ #
    @commands.command(name="shop", aliases=["store"])
    @commands.guild_only()
    async def shop_cmd(self, ctx: commands.Context) -> None:
        """Browse the Chronocoin shop with high-res visual catalog card."""
        currency = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
        coin_e = emojis.coin(ctx.guild)
        embed = embeds.base_embed(
            title="🛒 Chronos Coin Shop",
            description=(
                f"{coin_e} **{currency['coins']:,} Chronocoins available**\n"
                f"Type `{ctx.prefix}buy <number_or_name> [quantity]` to purchase!"
            ),
            color=embeds.COLOR_ECONOMY,
        )
        embeds.set_footer(embed, f"Example: {ctx.prefix}buy 1 3  •  {ctx.prefix}buy freeze  •  {ctx.prefix}inv to view your satchel")

        loop = asyncio.get_running_loop()
        try:
            card_bytes = await loop.run_in_executor(None, render_shop_card_sync, currency["coins"])
            file = discord.File(io.BytesIO(card_bytes), filename="shop.png")
            embed.set_image(url="attachment://shop.png")
            await ctx.send(file=file, embed=embed)
        except Exception as e:
            log.error("Failed to render visual shop card", exc_info=e)
            for i, item_id in enumerate(economy.SHOP_ORDER, start=1):
                item = economy.SHOP_ITEMS[item_id]
                item_e = emojis.item(item_id, ctx.guild)
                embed.add_field(
                    name=f"`{i}.` {item_e} {item['name']} — **{item['price']:,}** {coin_e}",
                    value=f"▷ {item['description']}",
                    inline=False,
                )
            custom_tags = await self.db.get_custom_tags(ctx.guild.id)
            for item_id, item in custom_tags.items():
                embed.add_field(
                    name=f"{item['emoji']} {item['name']} — **{item['price']:,}** {coin_e}",
                    value=f"▷ {item['description']}",
                    inline=False,
                )
            await ctx.send(embed=embed)

    @commands.command(name="buy")
    @commands.guild_only()
    async def buy_cmd(self, ctx: commands.Context, *, item: str) -> None:
        """Buy an item from the shop, by name or shop number. Add a
        trailing quantity to buy several at once: `.buy mystery box 5`
        (titles are always just 1 - they're a one-time unlock)."""
        text = item.strip()
        quantity = 1
        tokens = text.split()
        if len(tokens) > 1 and tokens[-1].isdigit():
            candidate_qty = int(tokens[-1])
            candidate_text = " ".join(tokens[:-1])
            if candidate_qty > 0 and await self._resolve_item_or_tag(ctx, candidate_text) is not None:
                text = candidate_text
                quantity = candidate_qty

        item_id = await self._resolve_item_or_tag(ctx, text)
        if item_id is None:
            await ctx.send(embed=embeds.error_embed(
                f"Couldn't find that item. Check `{ctx.prefix}shop` for the list."
            ))
            return

        result = await self.db.buy_item(ctx.author.id, ctx.guild.id, item_id, quantity)
        if not result["success"]:
            reasons = {
                "insufficient_funds": "You don't have enough Chronocoins for that.",
                "already_owned": "You already own that title.",
                "not_found": "That item doesn't exist.",
                "title_quantity": "You can only buy 1 of a title at a time - it's a one-time unlock.",
                "event_item": f"That's a Halloween event item - get it from `{ctx.prefix}candyshop` or `{ctx.prefix}pumpkin` rewards.",
            }
            await ctx.send(embed=embeds.error_embed(reasons.get(result["reason"], "Purchase failed.")))
            return

        purchased = result["item"]
        qty_text = f" \u00D7{result['quantity']}" if result["quantity"] > 1 else ""
        note = ""
        if purchased["type"] == "boost":
            note = f"\nUse it with `{ctx.prefix}use {item_id}` when you're ready to study."
        elif purchased["type"] == "title":
            note = f"\nEquip it with `{ctx.prefix}settitle {purchased['title_text']}`."
        elif item_id == "mystery_box":
            note = f"\nOpen it with `{ctx.prefix}openbox`."

        log.info(
            f"SHOP BUY      | {ctx.author} ({ctx.author.id}) bought '{item_id}' x{result['quantity']} "
            f"in guild {ctx.guild.id}"
        )
        await ctx.send(embed=embeds.success_embed(
            "Purchased!",
            f"{purchased['emoji']} **{purchased['name']}**{qty_text} for **{result['total_price']:,} Chronocoins**.{note}",
        ))
        await self._announce_achievements(ctx)

class InventoryView(discord.ui.View):
    """Interactive pagination view for browsing player inventory & satchel."""

    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        target: discord.Member,
        inventory_items: list[tuple[str, int]],
        currency: dict[str, Any],
        stats: dict[str, Any],
        tier: str,
        active_boosts: list[dict[str, Any]],
        avatar_bytes: Optional[bytes],
        page: int = 0,
        per_page: int = 6,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.ctx = ctx
        self.target = target
        self.inventory_items = inventory_items
        self.currency = currency
        self.stats = stats
        self.tier = tier
        self.active_boosts = active_boosts
        self.avatar_bytes = avatar_bytes
        self.per_page = per_page
        self.total_pages = max(1, (len(inventory_items) + per_page - 1) // per_page)
        self.page = max(0, min(page, self.total_pages - 1))
        self.message: Optional[discord.Message] = None
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.clear_items()
        if self.total_pages <= 1:
            return

        btn_first = discord.ui.Button(
            emoji="⏮️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
            row=0,
        )
        btn_first.callback = self._first_callback
        self.add_item(btn_first)

        btn_prev = discord.ui.Button(
            emoji="◀️",
            label="Prev",
            style=discord.ButtonStyle.primary,
            disabled=(self.page == 0),
            row=0,
        )
        btn_prev.callback = self._prev_callback
        self.add_item(btn_prev)

        btn_page = discord.ui.Button(
            label=f"Page {self.page + 1} / {self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=0,
        )
        self.add_item(btn_page)

        btn_next = discord.ui.Button(
            emoji="▶️",
            label="Next",
            style=discord.ButtonStyle.primary,
            disabled=(self.page >= self.total_pages - 1),
            row=0,
        )
        btn_next.callback = self._next_callback
        self.add_item(btn_next)

        btn_last = discord.ui.Button(
            emoji="⏭️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= self.total_pages - 1),
            row=0,
        )
        btn_last.callback = self._last_callback
        self.add_item(btn_last)

    async def _first_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use pagination.", ephemeral=True)
            return
        self.page = 0
        await self._render_page(interaction)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use pagination.", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
        await self._render_page(interaction)

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use pagination.", ephemeral=True)
            return
        if self.page < self.total_pages - 1:
            self.page += 1
        await self._render_page(interaction)

    async def _last_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use pagination.", ephemeral=True)
            return
        self.page = self.total_pages - 1
        await self._render_page(interaction)

    async def _render_page(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        self._update_buttons()

        loop = asyncio.get_running_loop()
        card_bytes = await loop.run_in_executor(
            None,
            render_inventory_card_sync,
            self.target.display_name,
            self.target.name,
            self.tier,
            self.currency["coins"],
            self.currency.get("candy", 0),
            dict(self.inventory_items),
            self.active_boosts,
            self.stats.get("equipped_title"),
            self.avatar_bytes,
            self.page,
            self.per_page,
        )

        coin_e = emojis.coin(self.ctx.guild)
        total_items = len(self.inventory_items)
        total_qty = sum(v for _, v in self.inventory_items)
        embed = embeds.base_embed(
            title=f"🎒 {self.target.display_name}'s Satchel & Inventory",
            description=(
                f"{coin_e} **Wallet:** `{self.currency['coins']:,}` Chronocoins · 🍬 `{self.currency.get('candy', 0):,}` Candy\n"
                f"🏷️ **Equipped Title:** `{self.stats.get('equipped_title') or 'None'}` · 📦 **Total Items:** `{total_qty:,}` ({total_items} unique)"
            ),
            color=embeds.COLOR_ECONOMY,
        )
        embed.set_thumbnail(url=self.target.display_avatar.url)
        embeds.set_footer(
            embed,
            f"Page {self.page + 1}/{self.total_pages} • {self.ctx.prefix}use <item>  •  {self.ctx.prefix}openbox  •  {self.ctx.prefix}shop"
        )
        file = discord.File(io.BytesIO(card_bytes), filename="inventory.png")
        embed.set_image(url="attachment://inventory.png")

        if self.message:
            await self.message.edit(embed=embed, attachments=[file], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


    @commands.command(name="inventory", aliases=["inv", "bag", "satchel"])
    @commands.guild_only()
    async def inventory_cmd(
        self,
        ctx: commands.Context,
        target_or_page: Optional[str] = None,
        page_arg: Optional[int] = None,
    ) -> None:
        """See what you (or someone else) own in your satchel with high-res visual card.
        
        Usage:
            .bag
            .bag 2
            .bag @member
            .bag @member 2
        """
        target = ctx.author
        page = 0

        if target_or_page is not None:
            if target_or_page.isdigit():
                page = max(0, int(target_or_page) - 1)
            else:
                try:
                    target = await commands.MemberConverter().convert(ctx, target_or_page)
                except Exception:
                    target = ctx.author
                if page_arg is not None:
                    page = max(0, page_arg - 1)

        inventory = await self.db.get_inventory(target.id, ctx.guild.id)
        valid_items = [(k, v) for k, v in inventory.items() if v > 0]
        stats = await self.db.get_or_create_user_stats(target.id, ctx.guild.id)
        currency = await self.db.get_or_create_currency(target.id, ctx.guild.id)
        coin_e = emojis.coin(ctx.guild)

        if not valid_items:
            embed = embeds.base_embed(
                title=f"🎒 {target.display_name}'s Satchel & Inventory",
                description=(
                    f"{coin_e} **Wallet:** `{currency['coins']:,}` Chronocoins · 🍬 `{currency.get('candy', 0):,}` Candy\n"
                    f"🏷️ **Equipped Title:** `{stats.get('equipped_title') or 'None'}`\n\n"
                    f"*Your satchel is empty! Check out `{ctx.prefix}shop` to buy boosts, mystery boxes, or prestige titles.*"
                ),
                color=embeds.COLOR_ECONOMY,
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            embeds.set_footer(embed, f"Use {ctx.prefix}shop to buy items • {ctx.prefix}daily to get coins")
            await ctx.send(embed=embed)
            return

        effective_tiers = await self.db.get_effective_tiers(ctx.guild.id)
        _, _, lvl = xp_progress(stats["xp"])
        tier = tier_for_level(lvl, effective_tiers)

        now = int(time.time())
        active_boosts = []
        for effect_id, label in (("xp_boost", "XP Boost"), ("coin_boost", "Chronocoin Boost")):
            effect = await self.db.get_active_effect(target.id, ctx.guild.id, effect_id, now)
            if effect:
                remaining = max(0, effect["expires_at"] - now)
                active_boosts.append({
                    "name": label,
                    "mult": effect["multiplier"],
                    "remaining": remaining,
                })

        avatar_bytes: Optional[bytes] = None
        try:
            avatar_bytes = await target.display_avatar.with_format("png").with_size(128).read()
        except Exception:
            avatar_bytes = None

        view = InventoryView(
            bot=self.bot,
            ctx=ctx,
            target=target,
            inventory_items=valid_items,
            currency=currency,
            stats=stats,
            tier=tier,
            active_boosts=active_boosts,
            avatar_bytes=avatar_bytes,
            page=page,
            per_page=6,
        )

        total_items = len(valid_items)
        total_qty = sum(v for _, v in valid_items)
        embed = embeds.base_embed(
            title=f"🎒 {target.display_name}'s Satchel & Inventory",
            description=(
                f"{coin_e} **Wallet:** `{currency['coins']:,}` Chronocoins · 🍬 `{currency.get('candy', 0):,}` Candy\n"
                f"🏷️ **Equipped Title:** `{stats.get('equipped_title') or 'None'}` · 📦 **Total Items:** `{total_qty:,}` ({total_items} unique)"
            ),
            color=embeds.COLOR_ECONOMY,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embeds.set_footer(
            embed,
            f"Page {view.page + 1}/{view.total_pages} • {ctx.prefix}use <item>  •  {ctx.prefix}openbox  •  {ctx.prefix}shop"
        )

        loop = asyncio.get_running_loop()
        try:
            card_bytes = await loop.run_in_executor(
                None,
                render_inventory_card_sync,
                target.display_name,
                target.name,
                tier,
                currency["coins"],
                currency.get("candy", 0),
                dict(valid_items),
                active_boosts,
                stats.get("equipped_title"),
                avatar_bytes,
                view.page,
                view.per_page,
            )
            file = discord.File(io.BytesIO(card_bytes), filename="inventory.png")
            embed.set_image(url="attachment://inventory.png")
            msg = await ctx.send(file=file, embed=embed, view=view if view.total_pages > 1 else None)
            view.message = msg
        except Exception as e:
            log.error("Failed to render visual inventory card", exc_info=e)
            lines = []
            for item_id, qty in valid_items:
                item_e = emojis.item(item_id, ctx.guild)
                lines.append(f"{item_e} **{item_id.replace('_', ' ').title()}** ×{qty}")
            embed.add_field(name="📦 Items Held", value="\n".join(lines[:15]), inline=False)
            await ctx.send(embed=embed)

    @commands.command(name="use")
    @commands.guild_only()
    async def use_cmd(self, ctx: commands.Context, *, item: str) -> None:
        """Activate a boost item (e.g. XP Boost, Chronocoin Boost) from your inventory."""
        item_id = self._resolve_arg(item)
        if item_id is None or economy.SHOP_ITEMS.get(item_id, {}).get("type") != "boost":
            await ctx.send(embed=embeds.error_embed(
                f"That's not a usable boost. Try `{ctx.prefix}use xp boost` or `{ctx.prefix}use chronocoin boost`."
            ))
            return

        result = await self.db.use_boost_item(ctx.author.id, ctx.guild.id, item_id)
        if not result["success"]:
            await ctx.send(embed=embeds.error_embed(f"You don't own a {economy.SHOP_ITEMS[item_id]['name']}."))
            return

        item = result["item"]
        await ctx.send(embed=embeds.success_embed(
            f"{item['emoji']} {item['name']} activated!",
            f"**{item['multiplier']}x** for the next **{item['duration_minutes']} minutes** of studying "
            f"while you have an active `{ctx.prefix}start` session running.",
        ))

    @commands.command(name="settitle")
    @commands.guild_only()
    async def settitle_cmd(self, ctx: commands.Context, *, title: str) -> None:
        """Equip an owned title (from the shop). Use `.settitle none` to clear it."""
        if title.strip().lower() in ("none", "clear", "remove"):
            await self.db.set_equipped_title(ctx.author.id, ctx.guild.id, None)
            await ctx.send(embed=embeds.success_embed("Title cleared", "Your profile title has been removed."))
            return

        title_lookup = {
            item["title_text"].lower(): (item_id, item)
            for item_id, item in economy.SHOP_ITEMS.items()
            if item["type"] == "title"
        }
        custom_tags = await self.db.get_custom_tags(ctx.guild.id)
        title_lookup.update({
            item["title_text"].lower(): (item_id, item) for item_id, item in custom_tags.items()
        })
        found = title_lookup.get(title.strip().lower())
        if found is None:
            await ctx.send(embed=embeds.error_embed(
                f"That's not a known title. Check `{ctx.prefix}shop` for available titles."
            ))
            return
        item_id, match = found

        owned_qty = await self.db.get_item_qty(ctx.author.id, ctx.guild.id, item_id)
        if owned_qty <= 0:
            if match.get("price", 0) <= 0:
                hint = f"It's a Halloween event title - earn it via `{ctx.prefix}candyshop` or `{ctx.prefix}pumpkin`."
            else:
                hint = f"Buy it with `{ctx.prefix}buy {match['title_text']}`."
            await ctx.send(embed=embeds.error_embed(f"You don't own that title yet. {hint}"))
            return

        await self.db.set_equipped_title(ctx.author.id, ctx.guild.id, match["title_text"])
        await ctx.send(embed=embeds.success_embed("Title equipped", f"Now showing **{match['title_text']}** on your profile."))

    # ------------------------------------------------------------------ #
    # Daily
    # ------------------------------------------------------------------ #
    @commands.command(name="daily")
    @commands.guild_only()
    async def daily_cmd(self, ctx: commands.Context) -> None:
        """Claim your once-per-day Chronocoin reward. Streak bonuses stack the more consecutive days you claim."""
        result = await self.db.claim_daily(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Already claimed",
                f"You've already claimed today's reward. Come back after 00:00 IST "
                f"(current streak: **{result['daily_streak']} days**).",
            ))
            return

        coin_e = emojis.coin(ctx.guild)
        streak_e = emojis.streak(ctx.guild)
        xp_e = emojis.xp(ctx.guild)

        embed = embeds.base_embed(
            title="✅ Daily reward claimed",
            description="Your daily haul is in. Keep the streak alive tomorrow.",
            color=embeds.COLOR_SUCCESS,
        )
        embed.add_field(name=f"{coin_e} Base Chronocoins", value=f"+{result['base_coins']:,}", inline=True)
        embed.add_field(name=f"{streak_e} Streak bonus", value=f"+{result['streak_bonus']:,}", inline=True)
        embed.add_field(name=f"{xp_e} XP earned", value=f"+{result['xp']} XP", inline=True)
        embed.add_field(name=f"{coin_e} Total Chronocoins", value=f"**+{result['coins']:,}**", inline=True)
        embed.add_field(name=f"{streak_e} Daily streak", value=f"{result['daily_streak']} days", inline=True)
        embed.add_field(name="💰 New balance", value=f"{result['new_balance']:,} {coin_e}", inline=True)

        if result["milestone"]:
            milestone_lines = [f"+{result['milestone']['coins']:,} bonus Chronocoins"]
            if result["milestone_item"]:
                item = economy.SHOP_ITEMS.get(result["milestone_item"], {})
                milestone_lines.append(f"{item.get('emoji', '')} Free {item.get('name', result['milestone_item'])}")
            embed.add_field(
                name=f"\U0001F3C6 {result['daily_streak']}-Day Streak Milestone!",
                value="\n".join(milestone_lines),
                inline=False,
            )
        elif result["bonus_box"]:
            embed.add_field(name="\U0001F381 Bonus!", value="A free Mystery Box was added to your inventory!", inline=False)

        # HALLOWEEN EVENT: Daily Candy & Hallo-Box Reward
        daily_candy = random.randint(30, 60)
        await self.db.add_candy(ctx.author.id, ctx.guild.id, daily_candy)

        streak = result["daily_streak"]
        if streak >= 30:
            daily_box = "hbox_epic"
        elif streak >= 7:
            daily_box = "hbox_rare"
        elif random.random() < 0.35:
            daily_box = "hbox_uncommon"
        else:
            daily_box = "hbox_common"

        await self.db.add_item(ctx.author.id, ctx.guild.id, daily_box, 1)
        box_info = halloween_catalog.get_box(daily_box)
        embed.add_field(
            name=f"{box_info['emoji']} Daily Hallo-Box & Candy!",
            value=f"You received a **{box_info['name']}** + **+{daily_candy} \U0001F36C Candy**!\nOpen instantly with `{ctx.prefix}openbox {box_info['tier']}`.",
            inline=False,
        )

        if result["leveled_up"]:
            embed.add_field(
                name="\U0001F389 Level Up!",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}**",
                inline=False,
            )

        log.info(
            f"DAILY CLAIM   | {ctx.author} ({ctx.author.id}) claimed in guild {ctx.guild.id} "
            f"(streak={result['daily_streak']}, coins={result['coins']}, xp={result['xp']})"
        )
        await ctx.send(embed=embed)
        await self._announce_achievements(ctx)

    @commands.command(name="dailyperks", aliases=["dailyperk", "top3perks", "perks", "top3"])
    @commands.guild_only()
    async def top3_perks_cmd(self, ctx: commands.Context) -> None:
        """View the Top 3 Leaderboard Daily Dawn Perks and today's claim status."""
        import time
        from utils import streaks
        now = int(time.time())
        today = streaks.date_str(now)

        top3 = await self.db.get_top3_members(ctx.guild.id)
        coin_e = emojis.coin(ctx.guild)

        embed = embeds.base_embed(
            title="👑 Top 3 Leaderboard Daily Dawn Perks",
            description=(
                "The server's **Top 3 Study Champions** unlock exclusive buffs and daily drops on their "
                "very first command every day (resets 00:00 IST)!\n\n"
                "**Perk Tier Breakdown:**\n"
                "🥇 **Rank #1 Sovereign:** +100% XP & Coin Gain (2h) · +120 Chronocoins · 1× Ancient Mystery Chest\n"
                "🥈 **Rank #2 Ascendant:** +100% XP Boost (1.5h) · +80 Chronocoins · 1× Glacial Streak Freeze\n"
                "🥉 **Rank #3 Vanguard:** +100% Coin Boost (1h) · +50 Chronocoins · 1× Bottle o' XP Elixir\n"
            ),
            color=embeds.COLOR_LEVELUP,
        )

        lines = []
        user_rank = None
        user_claim = await self.db.get_top3_daily_claim(ctx.author.id, ctx.guild.id, today)

        titles = [
            ("👑 Rank #1 Sovereign", "120 🪙 · 1× Mystery Box · 2h XP+Coin Boost"),
            ("⚔️ Rank #2 Ascendant", "80 🪙 · 1× Streak Freeze · 1.5h XP Boost"),
            ("🥉 Rank #3 Vanguard", "50 🪙 · 1× XP Elixir · 1h Coin Boost"),
        ]

        if not top3:
            lines.append("*No members have logged study time yet.*")
        else:
            for i in range(3):
                title, reward_str = titles[i]
                if i < len(top3):
                    uid, secs = top3[i]
                    if uid == ctx.author.id:
                        user_rank = i + 1
                    member = ctx.guild.get_member(uid)
                    name = member.display_name if member else f"User {uid}"
                    claim = await self.db.get_top3_daily_claim(uid, ctx.guild.id, today)
                    status = "✅ *Claimed Today*" if claim else "⏳ *Pending First Command*"
                    lines.append(f"**{title}** — **{name}**\n▸ {reward_str}\n▸ Status: {status}\n")
                else:
                    lines.append(f"**{title}** — *Unclaimed Slot*\n▸ {reward_str}\n")

        embed.add_field(name="🏛️ Today's Throne Holders", value="\n".join(lines), inline=False)

        if user_rank:
            if user_claim:
                status_text = f"You are **Rank #{user_rank}**! You have already claimed today's dawn perk."
            else:
                perk = await self.db.claim_top3_daily_perk(ctx.author.id, ctx.guild.id, user_rank, today, now=now)
                if perk:
                    status_text = f"You are **Rank #{user_rank}**! 🎉 **Just activated:** {perk['perk_name']} (+{perk['coins']} coins, +1 {perk['item_name']})!"
                else:
                    status_text = f"You are **Rank #{user_rank}**! Your perk is ready."
            embed.add_field(name="🎯 Your Standing", value=status_text, inline=False)
        else:
            embed.add_field(
                name="🎯 Your Standing",
                value="You are currently outside the top 3. Log more study sessions with `.start` to climb the leaderboard!",
                inline=False,
            )

        embeds.set_footer(embed, "Perks activate automatically on your first command each IST day!")
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # Extra coin-earning commands (on top of studying + `.daily`) - added
    # since pets and pet food (see cogs/pets.py) aren't cheap.
    # ------------------------------------------------------------------ #
    @commands.command(name="work", aliases=["grind"])
    @commands.guild_only()
    async def work_cmd(self, ctx: commands.Context) -> None:
        """Do a quick task for some Chronocoins (+ a little XP). Short cooldown - meant to be used often."""
        result = await self.db.claim_work(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Not yet",
                f"You can `{ctx.prefix}work` again in {format_duration(result['retry_after'])}.",
            ))
            return

        coin_e = emojis.coin(ctx.guild)
        xp_e = emojis.xp(ctx.guild)
        embed = embeds.base_embed(
            title="✅ Quick task complete",
            description="A little extra progress for the grind.",
            color=embeds.COLOR_SUCCESS,
        )
        embed.add_field(name=f"{coin_e} Chronocoins earned", value=f"+{result['coins']:,}", inline=True)
        embed.add_field(name=f"{xp_e} XP earned", value=f"+{result['xp']} XP", inline=True)
        embed.add_field(name="💰 New balance", value=f"{result['new_balance']:,} {coin_e}", inline=True)

        # HALLOWEEN EVENT: Chance to find a Hallo-Box + Candy while working
        if random.random() < 0.35:
            work_box = random.choices(["hbox_common", "hbox_uncommon", "hbox_rare"], weights=[0.75, 0.20, 0.05])[0]
            work_candy = random.randint(8, 18)
            await self.db.add_item(ctx.author.id, ctx.guild.id, work_box, 1)
            await self.db.add_candy(ctx.author.id, ctx.guild.id, work_candy)
            box_info = halloween_catalog.get_box(work_box)
            embed.add_field(
                name=f"{box_info['emoji']} Hallo-Box Found!",
                value=f"You stumbled upon a **{box_info['name']}** + **+{work_candy} \U0001F36C Candy** on the job!\nOpen with `{ctx.prefix}openbox {box_info['tier']}`.",
                inline=False,
            )

        if result["leveled_up"]:
            embed.add_field(
                name="\U0001F389 Level Up!",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}**",
                inline=False,
            )
        log.info(f"WORK CLAIM    | {ctx.author} ({ctx.author.id}) claimed in guild {ctx.guild.id} (coins={result['coins']})")
        await ctx.send(embed=embed)
        await self._announce_achievements(ctx)

    @commands.command(name="beg")
    @commands.guild_only()
    async def beg_cmd(self, ctx: commands.Context) -> None:
        """Beg for a few Chronocoins. Very short cooldown, small payout, and a chance of nothing."""
        result = await self.db.claim_beg(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Not yet",
                f"You can `{ctx.prefix}beg` again in {format_duration(result['retry_after'])}.",
            ))
            return

        is_success = result["coins"] > 0
        scenario, payout = roll_beg_scenario(ctx.author.id, is_success, result["coins"])

        if payout > result["coins"]:
            extra = payout - result["coins"]
            await self.db._add_coins_raw(ctx.author.id, ctx.guild.id, extra)
            await self.db.conn.commit()
            new_balance = result["new_balance"] + extra
        else:
            new_balance = result["new_balance"]

        quote_text = f"\n\n💬 *\"{scenario.quote}\"*" if scenario.quote else ""
        coin_e = emojis.coin(ctx.guild)

        if is_success:
            embed = embeds.base_embed(
                title=f"{scenario.emoji} {scenario.npc} · {scenario.title}",
                description=f"> {scenario.story}{quote_text}",
                color=embeds.COLOR_SUCCESS,
            )
            embed.add_field(name=f"{coin_e} Chronocoins Received", value=f"+{payout:,} {coin_e}", inline=True)
            embed.add_field(name="🏦 New Balance", value=f"{new_balance:,} {coin_e}", inline=True)
        else:
            embed = embeds.base_embed(
                title=f"{scenario.emoji} {scenario.npc} · {scenario.title}",
                description=f"> {scenario.story}{quote_text}",
                color=embeds.COLOR_WARNING,
            )
            embed.add_field(name="❌ Chronocoins Received", value=f"0 {coin_e}", inline=True)
            embed.add_field(name="🏦 Current Balance", value=f"{new_balance:,} {coin_e}", inline=True)

        embeds.set_footer(embed, f"Role: {scenario.role} \u00B7 {ctx.prefix}beg")

        # HALLOWEEN EVENT: Chance to receive a Hallo-Box + Candy while begging
        if random.random() < 0.25:
            beg_box = "hbox_common" if random.random() < 0.85 else "hbox_uncommon"
            beg_candy = random.randint(4, 10)
            await self.db.add_item(ctx.author.id, ctx.guild.id, beg_box, 1)
            await self.db.add_candy(ctx.author.id, ctx.guild.id, beg_candy)
            box_info = halloween_catalog.get_box(beg_box)
            embed.add_field(
                name=f"{box_info['emoji']} Surprise Treat!",
                value=f"A kind stranger handed you a **{box_info['name']}** + **+{beg_candy} \U0001F36C Candy**!\nOpen with `{ctx.prefix}openbox {box_info['tier']}`.",
                inline=False,
            )

        log.info(f"BEG CLAIM     | {ctx.author} ({ctx.author.id}) claimed in guild {ctx.guild.id} (npc='{scenario.npc}', coins={payout})")
        await ctx.send(embed=embed)
        await self._announce_achievements(ctx)

    @commands.command(name="weekly")
    @commands.guild_only()
    async def weekly_cmd(self, ctx: commands.Context) -> None:
        """Claim a large once-a-week Chronocoin reward, plus a free Mystery Box."""
        result = await self.db.claim_weekly(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Not yet",
                f"You can `{ctx.prefix}weekly` again in {format_duration(result['retry_after'])}.",
            ))
            return

        coin_e = emojis.coin(ctx.guild)
        embed = embeds.base_embed(
            title="📅 Weekly reward claimed",
            description="The big weekly haul has landed.",
            color=embeds.COLOR_SUCCESS,
        )
        embed.add_field(name=f"{coin_e} Chronocoins earned", value=f"+{result['coins']:,}", inline=True)
        embed.add_field(name="💰 New balance", value=f"{result['new_balance']:,} {coin_e}", inline=True)
        embed.add_field(name="🎁 Bonus", value="Free Mystery Box", inline=True)

        # HALLOWEEN EVENT: Guaranteed High-Tier Hallo-Box & Big Candy Stash
        weekly_box = "hbox_legendary" if random.random() < 0.20 else "hbox_epic"
        weekly_candy = random.randint(180, 300)
        await self.db.add_item(ctx.author.id, ctx.guild.id, weekly_box, 1)
        await self.db.add_candy(ctx.author.id, ctx.guild.id, weekly_candy)
        box_info = halloween_catalog.get_box(weekly_box)
        embed.add_field(
            name=f"{box_info['emoji']} Weekly Hallo-Box Jackpot!",
            value=f"Received a prestigious **{box_info['name']}** + **+{weekly_candy} \U0001F36C Candy**!\nOpen with `{ctx.prefix}openbox {box_info['tier']}`.",
            inline=False,
        )

        log.info(f"WEEKLY CLAIM  | {ctx.author} ({ctx.author.id}) claimed in guild {ctx.guild.id} (coins={result['coins']})")
        await ctx.send(embed=embed)
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_arg(text: str) -> Optional[str]:
        text = text.strip()
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(economy.SHOP_ORDER):
                return economy.SHOP_ORDER[index]
            return None
        return economy.resolve_item_id(text)

    async def _resolve_item_or_tag(self, ctx: commands.Context, text: str) -> Optional[str]:
        """Resolve typed text (or a shop number) to an item id, checking
        both the built-in catalog and this server's custom tags."""
        item_id = self._resolve_arg(text)
        if item_id is not None:
            return item_id
        custom_tags = await self.db.get_custom_tags(ctx.guild.id)
        return next(
            (iid for iid, it in custom_tags.items() if it["title_text"].lower() == text.strip().lower()),
            None,
        )

    @buy_cmd.error
    @use_cmd.error
    @settitle_cmd.error
    @shop_cmd.error
    @balance_cmd.error
    @daily_cmd.error
    @inventory_cmd.error
    @work_cmd.error
    @beg_cmd.error
    @weekly_cmd.error
    async def economy_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error_embed(f"Usage: `{ctx.prefix}{ctx.command.name} <item>`"))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
