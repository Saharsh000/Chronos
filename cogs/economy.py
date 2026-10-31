"""Coin economy: `.shop` / `.buy` / `.inventory` / `.use` / `.openbox` /
`.settitle` / `.balance`, plus the `.daily` claim command.

Coins themselves are earned automatically while studying (see
database.py's `_random_minute_coins`, credited alongside XP) - this
cog is just the spending/claiming side of the economy.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Optional

import discord
from discord.ext import commands

from utils import economy
from utils import embeds
from utils import food as food_catalog
from utils import halloween as halloween_catalog
from utils.time_format import format_duration

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
    @commands.command(name="balance", aliases=["coins", "bal"])
    @commands.guild_only()
    async def balance_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Check your (or someone else's) coin balance."""
        target = member or ctx.author
        currency = await self.db.get_or_create_currency(target.id, ctx.guild.id)
        candy = currency.get("candy", 0)
        embed = embeds.base_embed(
            title=f"\U0001FA99 {target.display_name}'s Wallet",
            description=(
                f"\U0001F4B0 **Balance**\n{currency['coins']:,} coins\n\n"
                f"\U0001F36C **Candy**\n{candy:,} candy\n\n"
                f"\U0001F4C8 **Lifetime earned**\n{currency['lifetime_earned']:,} coins"
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
        """Browse the coin shop."""
        currency = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
        embed = embeds.base_embed(
            title="\U0001F6D2 Chronos Shop",
            description=(
                f"\U0001FA99 **{currency['coins']:,} coins available**\n"
                "Pick an item by its number or name."
            ),
            color=embeds.COLOR_ECONOMY,
        )
        for i, item_id in enumerate(economy.SHOP_ORDER, start=1):
            item = economy.SHOP_ITEMS[item_id]
            embed.add_field(
                name=f"`{i}.` {item['emoji']} {item['name']} \u2014 **{item['price']:,}** \U0001FA99",
                value=f"\u25B9 {item['description']}",
                inline=False,
            )
        custom_tags = await self.db.get_custom_tags(ctx.guild.id)
        for item_id, item in custom_tags.items():
            embed.add_field(
                name=f"{item['emoji']} {item['name']} \u2014 **{item['price']:,}** \U0001FA99",
                value=f"\u25B9 {item['description']}",
                inline=False,
            )
        embeds.set_footer(embed, f"{ctx.prefix}buy <item> [quantity]")
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
                "insufficient_funds": "You don't have enough coins for that.",
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
            f"{purchased['emoji']} **{purchased['name']}**{qty_text} for **{result['total_price']:,} coins**.{note}",
        ))
        await self._announce_achievements(ctx)

    @commands.command(name="inventory", aliases=["inv"])
    @commands.guild_only()
    async def inventory_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """See what you (or someone else) own."""
        target = member or ctx.author
        inventory = await self.db.get_inventory(target.id, ctx.guild.id)
        stats = await self.db.get_or_create_user_stats(target.id, ctx.guild.id)

        embed = embeds.base_embed(title=f"\U0001F392 {target.display_name}'s Inventory", color=embeds.COLOR_ECONOMY)
        embed.set_thumbnail(url=target.display_avatar.url)

        if not inventory:
            embed.description = f"Nothing yet - check out `{ctx.prefix}shop`."
        else:
            custom_tags = await self.db.get_custom_tags(ctx.guild.id)
            lines = []
            for item_id, qty in inventory.items():
                item = economy.SHOP_ITEMS.get(item_id) or custom_tags.get(item_id)
                if item is None:
                    continue
                lines.append(f"{item['emoji']} **{item['name']}** \u00D7{qty}")
            embed.description = "\n".join(lines) if lines else f"Nothing yet - check out `{ctx.prefix}shop`."

        box_lines = [
            f"{halloween_catalog.HALLO_BOXES[bid]['emoji']} **{halloween_catalog.HALLO_BOXES[bid]['name']}** \u00D7{inventory[bid]}"
            for bid in halloween_catalog.HALLO_BOX_ORDER
            if inventory.get(bid, 0) > 0
        ]
        if box_lines:
            embed.add_field(
                name="\U0001F383 Hallo-Boxes",
                value="\n".join(box_lines) + f"\nOpen with `{ctx.prefix}openbox <tier>`",
                inline=False,
            )

        food_inventory = await self.db.get_food_inventory(target.id, ctx.guild.id)
        if food_inventory:
            food_lines = [
                f"{food_catalog.FOOD_TIER_INFO[food_catalog.FOODS[fid]['tier']]['emoji']} "
                f"**{food_catalog.FOODS[fid]['name']}** \u00D7{qty}"
                for fid, qty in food_inventory.items()
            ]
            embed.add_field(name="\U0001F372 Pet Food", value="\n".join(food_lines), inline=False)

        if stats.get("equipped_title"):
            embed.add_field(name="Equipped Title", value=stats["equipped_title"], inline=False)

        now = int(time.time())
        boost_lines = []
        for effect_id, label in (("xp_boost", "\u26A1 XP Boost"), ("coin_boost", "\U0001F4B0 Coin Boost")):
            effect = await self.db.get_active_effect(target.id, ctx.guild.id, effect_id, now)
            if effect:
                remaining = max(0, effect["expires_at"] - now)
                boost_lines.append(f"{label} ({effect['multiplier']}x) \u2014 {format_duration(remaining)} left")
        if boost_lines:
            embed.add_field(name="Active Boosts", value="\n".join(boost_lines), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="use")
    @commands.guild_only()
    async def use_cmd(self, ctx: commands.Context, *, item: str) -> None:
        """Activate a boost item (e.g. XP Boost, Coin Boost) from your inventory."""
        item_id = self._resolve_arg(item)
        if item_id is None or economy.SHOP_ITEMS.get(item_id, {}).get("type") != "boost":
            await ctx.send(embed=embeds.error_embed(
                f"That's not a usable boost. Try `{ctx.prefix}use xp boost` or `{ctx.prefix}use coin boost`."
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
        """Claim your once-per-day coin reward. Streak bonuses stack the more consecutive days you claim."""
        result = await self.db.claim_daily(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Already claimed",
                f"You've already claimed today's reward. Come back after 00:00 IST "
                f"(current streak: **{result['daily_streak']} days**).",
            ))
            return

        embed = embeds.base_embed(
            title="\u2705 Daily reward claimed",
            description="Your daily haul is in. Keep the streak alive tomorrow.",
            color=embeds.COLOR_SUCCESS,
        )
        embed.add_field(name="\U0001FA99 Base coins", value=f"+{result['base_coins']:,}", inline=True)
        embed.add_field(name="\U0001F525 Streak bonus", value=f"+{result['streak_bonus']:,}", inline=True)
        embed.add_field(name="\U0001F4C8 XP earned", value=f"+{result['xp']} XP", inline=True)
        embed.add_field(name="\U0001FA99 Total coins", value=f"**+{result['coins']:,}**", inline=True)
        embed.add_field(name="\U0001F525 Daily streak", value=f"{result['daily_streak']} days", inline=True)
        embed.add_field(name="\U0001F4B0 New balance", value=f"{result['new_balance']:,} coins", inline=True)

        if result["milestone"]:
            milestone_lines = [f"+{result['milestone']['coins']:,} bonus coins"]
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

    # ------------------------------------------------------------------ #
    # Extra coin-earning commands (on top of studying + `.daily`) - added
    # since pets and pet food (see cogs/pets.py) aren't cheap.
    # ------------------------------------------------------------------ #
    @commands.command(name="work", aliases=["grind"])
    @commands.guild_only()
    async def work_cmd(self, ctx: commands.Context) -> None:
        """Do a quick task for some coins (+ a little XP). Short cooldown - meant to be used often."""
        result = await self.db.claim_work(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Not yet",
                f"You can `{ctx.prefix}work` again in {format_duration(result['retry_after'])}.",
            ))
            return

        embed = embeds.base_embed(
            title="\u2705 Quick task complete",
            description="A little extra progress for the grind.",
            color=embeds.COLOR_SUCCESS,
        )
        embed.add_field(name="\U0001FA99 Coins earned", value=f"+{result['coins']:,}", inline=True)
        embed.add_field(name="\U0001F4C8 XP earned", value=f"+{result['xp']} XP", inline=True)
        embed.add_field(name="\U0001F4B0 New balance", value=f"{result['new_balance']:,} coins", inline=True)

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
        """Beg for a few coins. Very short cooldown, small payout, and a chance of nothing."""
        result = await self.db.claim_beg(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Not yet",
                f"You can `{ctx.prefix}beg` again in {format_duration(result['retry_after'])}.",
            ))
            return

        if result["coins"] == 0:
            embed = embeds.base_embed(
                title="\U0001F937 Nothing",
                description="Nobody had any spare coins for you this time. Try again soon.",
                color=embeds.COLOR_WARNING,
            )
        else:
            embed = embeds.success_embed(
                "A kind soul dropped some coins",
                f"+{result['coins']:,} coins. New balance: {result['new_balance']:,} coins.",
            )

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

        log.info(f"BEG CLAIM     | {ctx.author} ({ctx.author.id}) claimed in guild {ctx.guild.id} (coins={result['coins']})")
        await ctx.send(embed=embed)
        await self._announce_achievements(ctx)

    @commands.command(name="weekly")
    @commands.guild_only()
    async def weekly_cmd(self, ctx: commands.Context) -> None:
        """Claim a large once-a-week coin reward, plus a free Mystery Box."""
        result = await self.db.claim_weekly(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.info_embed(
                "\u23F0 Not yet",
                f"You can `{ctx.prefix}weekly` again in {format_duration(result['retry_after'])}.",
            ))
            return

        embed = embeds.base_embed(
            title="\U0001F4C6 Weekly reward claimed",
            description="The big weekly haul has landed.",
            color=embeds.COLOR_SUCCESS,
        )
        embed.add_field(name="\U0001FA99 Coins earned", value=f"+{result['coins']:,}", inline=True)
        embed.add_field(name="\U0001F4B0 New balance", value=f"{result['new_balance']:,} coins", inline=True)
        embed.add_field(name="\U0001F381 Bonus", value="Free Mystery Box", inline=True)

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
