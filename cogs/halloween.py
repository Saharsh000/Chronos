"""Halloween Seasonal Event Cog for Chronos.

Features:
  - Jack-o'-Lantern Season Pass (.pumpkin / .pass / .jackolantern)
  - Hallo-Boxes (.boxes / .halloboxes / .openbox / .open)
  - Candy Shop (.candyshop / .spookyshop / .buycandy)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ext import commands

import config
from utils import economy
from utils import embeds
from utils import food as food_catalog
from utils import halloween as halloween_catalog
from utils import pets as pet_catalog
from utils.time_format import format_duration

log = logging.getLogger("halloween")


def _hm(hours: float) -> str:
    """Format a fractional hour count as e.g. '2h 28m'."""
    total_min = int(round(hours * 60))
    hh, mm = divmod(total_min, 60)
    if hh <= 0:
        return f"{mm}m"
    return f"{hh}h {mm:02d}m" if mm else f"{hh}h"


# --------------------------------------------------------------------- #
# Interactive UI Views
# --------------------------------------------------------------------- #
class PumpkinPassView(discord.ui.View):
    """Interactive view for the Jack-o'-Lantern Season Pass."""

    def __init__(self, author_id: int, db: Any, pass_data: dict[str, Any]):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.db = db
        self.pass_data = pass_data
        self._update_buttons()

    def _update_buttons(self) -> None:
        study_seconds = self.pass_data.get("study_seconds", 0)
        claimed_level = self.pass_data.get("claimed_level", 0)
        current_lvl_info = halloween_catalog.get_current_pass_level(study_seconds)
        max_unlocked = current_lvl_info["level"]

        has_unclaimed = max_unlocked > claimed_level
        self.claim_btn.disabled = not has_unclaimed
        if has_unclaimed:
            if max_unlocked == claimed_level + 1:
                self.claim_btn.label = f"Claim Level {max_unlocked} Reward!"
            else:
                self.claim_btn.label = f"Claim Levels {claimed_level + 1}-{max_unlocked} Rewards!"
        else:
            self.claim_btn.label = "All Unlocked Rewards Claimed"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This is not your personal Jack-o'-Lantern pass! Check yours with `.pumpkin`.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Claim Rewards", style=discord.ButtonStyle.success, emoji="🍬")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        result = await self.db.claim_all_halloween_rewards(self.author_id, interaction.guild.id)
        if not result["success"]:
            await interaction.response.send_message(
                "You have already claimed all rewards unlocked so far! Keep studying to unlock more.",
                ephemeral=True,
            )
            return

        self.pass_data["claimed_level"] = result["new_claimed_level"]
        self._update_buttons()

        # Build celebration embed
        reward_lines = []
        if result["candy"] > 0:
            reward_lines.append(f"🍬 **+{result['candy']:,} Candy**")
        if result["coins"] > 0:
            reward_lines.append(f"🪙 **+{result['coins']:,} Coins**")
        for box_id, qty in result["boxes"].items():
            b = halloween_catalog.get_box(box_id)
            box_name = b["name"] if b else box_id
            box_emoji = b["emoji"] if b else "📦"
            reward_lines.append(f"{box_emoji} **x{qty} {box_name}**")
        for item_id, qty in result["items"]:
            if item_id == "sugar_rush":
                reward_lines.append(f"⚡ **x{qty} Sugar Rush Boost**")
            elif item_id == "mystery_box":
                reward_lines.append(f"🎁 **x{qty} Mystery Box**")
            else:
                f = food_catalog.FOODS.get(item_id, {})
                fname = f.get("name", item_id)
                reward_lines.append(f"🍛 **x{qty} {fname}**")
        for title in result["titles"]:
            reward_lines.append(f"👑 **Title Unlocked: {title}**")

        rewards_text = "\n".join(reward_lines)
        claim_embed = embeds.base_embed(
            title="🎃 Jack-o'-Lantern Rewards Claimed!",
            description=(
                f"Successfully claimed milestones up to **Level {result['new_claimed_level']}**!\n\n"
                f"**Rewards Received:**\n{rewards_text}\n\n"
                f"Open your Hallo-Boxes with `{config.PREFIX}openbox` or browse the `{config.PREFIX}candyshop`!"
            ),
            color=0xFF7518,
        )

        # Update original message and send confirmation
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(embed=claim_embed)


class HalloBoxQuickOpenView(discord.ui.View):
    """Interactive view allowing one-click Hallo-Box opening."""

    def __init__(self, author_id: int, cog: Halloween, inv: dict[str, int]):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.cog = cog
        self.inv = inv

        for box_id in halloween_catalog.HALLO_BOX_ORDER:
            qty = inv.get(box_id, 0)
            box = halloween_catalog.get_box(box_id)
            if not box:
                continue
            btn = discord.ui.Button(
                label=f"Open {box['tier'].capitalize()} ({qty})",
                style=discord.ButtonStyle.secondary if qty == 0 else discord.ButtonStyle.primary,
                emoji=box["emoji"],
                custom_id=f"open_{box_id}",
                disabled=(qty == 0),
            )
            btn.callback = self._make_callback(box_id)
            self.add_item(btn)

    def _make_callback(self, box_id: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message(
                    "This isn't your inventory! Check yours with `.boxes`.", ephemeral=True
                )
                return
            await interaction.response.defer()
            await self.cog._do_open_box(interaction, box_id, 1)
        return callback


class CandyShopView(discord.ui.View):
    """Interactive view for the Candy Shop with quick-buy buttons."""

    def __init__(self, author_id: int, cog: Halloween, candy_balance: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.cog = cog
        self.candy_balance = candy_balance

        for item_key in halloween_catalog.CANDY_SHOP_ORDER:
            item = halloween_catalog.CANDY_SHOP_ITEMS[item_key]
            cost = item["candy_price"]
            btn = discord.ui.Button(
                label=f"{item['name']} ({cost} 🍬)",
                style=discord.ButtonStyle.success if candy_balance >= cost else discord.ButtonStyle.secondary,
                emoji=item["emoji"],
                custom_id=f"buy_{item_key}",
            )
            btn.callback = self._make_callback(item_key)
            self.add_item(btn)

    def _make_callback(self, item_key: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message(
                    "This isn't your shop view! Open yours with `.candyshop`.", ephemeral=True
                )
                return
            await interaction.response.defer()
            await self.cog._do_buy_candy(interaction, item_key, 1)
        return callback


# --------------------------------------------------------------------- #
# Halloween Cog
# --------------------------------------------------------------------- #
class Halloween(commands.Cog, name="Halloween"):
    """Halloween Seasonal Event: Jack-o'-Lantern Season Pass, Hallo-Boxes & Candy Shop."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ------------------------------------------------------------------ #
    # 1. THE JACK-O'-LANTERN SEASON PASS
    # ------------------------------------------------------------------ #
    @commands.command(name="pumpkin", aliases=["pass", "jackolantern", "seasonpass"])
    @commands.guild_only()
    async def pumpkin_cmd(self, ctx: commands.Context, action: Optional[str] = None) -> None:
        """View your 1 personal Jack-o'-Lantern pass, study carving progress, and claim rewards.
        
        Usage:
          .pumpkin         — View pass, current carving stage, and progress bar
          .pumpkin claim   — Claim all unlocked pass rewards
        """
        if action and action.strip().lower() in ("claim", "collect", "get", "claimall"):
            result = await self.db.claim_all_halloween_rewards(ctx.author.id, ctx.guild.id)
            if not result["success"]:
                await ctx.send(embed=embeds.info_embed(
                    "No Pending Rewards",
                    "You have already claimed all milestone rewards unlocked so far!\n"
                    f"Keep studying with `{ctx.prefix}start` to carve your Jack-o'-Lantern further."
                ))
                return

            reward_lines = []
            if result["candy"] > 0:
                reward_lines.append(f"🍬 **+{result['candy']:,} Candy**")
            if result["coins"] > 0:
                reward_lines.append(f"🪙 **+{result['coins']:,} Coins**")
            for box_id, qty in result["boxes"].items():
                b = halloween_catalog.get_box(box_id)
                bname = b["name"] if b else box_id
                bemoji = b["emoji"] if b else "📦"
                reward_lines.append(f"{bemoji} **x{qty} {bname}**")
            for item_id, qty in result["items"]:
                if item_id == "sugar_rush":
                    reward_lines.append(f"⚡ **x{qty} Sugar Rush Boost**")
                elif item_id == "mystery_box":
                    reward_lines.append(f"🎁 **x{qty} Mystery Box**")
                else:
                    f = food_catalog.FOODS.get(item_id, {})
                    reward_lines.append(f"🍛 **x{qty} {f.get('name', item_id)}**")
            for title in result["titles"]:
                reward_lines.append(f"👑 **Title Unlocked: {title}**")

            rewards_text = "\n".join(reward_lines)
            claim_embed = embeds.base_embed(
                title="🎃 Jack-o'-Lantern Rewards Claimed!",
                description=(
                    f"Successfully claimed all milestone rewards up to **Level {result['new_claimed_level']}**!\n\n"
                    f"**Rewards Received:**\n{rewards_text}\n\n"
                    f"Open your Hallo-Boxes with `{ctx.prefix}openbox` or browse the `{ctx.prefix}candyshop`!"
                ),
                color=0xFF7518,
            )
            await ctx.send(embed=claim_embed)
            return

        pass_data = await self.db.get_or_create_halloween_pass(ctx.author.id, ctx.guild.id)
        study_seconds = pass_data.get("study_seconds", 0)
        claimed_level = pass_data.get("claimed_level", 0)

        current_lvl = halloween_catalog.get_current_pass_level(study_seconds)
        next_lvl = halloween_catalog.get_next_pass_level(study_seconds)

        stage_num = current_lvl["stage"]
        stage_name = current_lvl["stage_name"]
        level_num = current_lvl["level"]
        level_name = current_lvl["level_name"]
        stage_emoji = current_lvl["emoji"]

        curr_mins = study_seconds // 60
        curr_hours = curr_mins / 60.0

        if next_lvl:
            needed_secs = next_lvl["required_seconds"]
            needed_mins = needed_secs // 60
            bar = halloween_catalog.format_progress_bar(study_seconds, needed_secs, length=12)
            progress_line = f"`{bar}` **{curr_mins}m / {needed_mins}m** ({curr_hours:.1f}h study)"
            
            # Next reward preview
            next_reward_parts = []
            if next_lvl["candy"] > 0:
                next_reward_parts.append(f"{next_lvl['candy']} 🍬")
            if next_lvl["coins"] > 0:
                next_reward_parts.append(f"{next_lvl['coins']:,} 🪙")
            for bid, bqty in next_lvl.get("boxes", []):
                bx = halloween_catalog.get_box(bid)
                b_lbl = bx["name"] if bx else bid
                next_reward_parts.append(f"x{bqty} {b_lbl}")
            for iid, iqty in next_lvl.get("items", []):
                next_reward_parts.append(f"x{iqty} {iid.replace('_', ' ').capitalize()}")
            if next_lvl.get("title"):
                next_reward_parts.append(f"👑 Title: {next_lvl['title']}")
            next_reward_str = " + ".join(next_reward_parts)
            next_text = f"**Next Milestone:** Level {next_lvl['level']} ({next_lvl['level_name']})\n↳ Rewards: {next_reward_str}"
        else:
            bar = "▰" * 12
            progress_line = f"`{bar}` **MAX LEVEL REACHED!** ({curr_hours:.1f}h total study)"
            next_text = "👑 **Congratulations!** You have fully completed the Jack-o'-Lantern Season Pass!"

        # Unclaimed status
        if level_num > claimed_level:
            unclaimed_count = level_num - claimed_level
            claim_status = (
                f"⚠️ **{unclaimed_count} unclaimed reward milestone{'s' if unclaimed_count > 1 else ''}!**\n"
                f"Click the button below or type `{ctx.prefix}pumpkin claim`."
            )
        else:
            claim_status = "✅ All current milestone rewards have been claimed!"

        embed = embeds.base_embed(
            title=f"🎃 {ctx.author.display_name}'s Jack-o'-Lantern",
            description=(
                f"**Stage {stage_num}: {stage_name}** — *{level_name}*\n"
                f"*{current_lvl['desc']}*\n\n"
                f"**Halloween Study Progress:**\n"
                f"{progress_line}\n\n"
                f"{next_text}\n\n"
                f"**Milestone Level:** Level **{level_num}** / {halloween_catalog.MAX_PASS_LEVEL}\n"
                f"**Claimed Level:** Level **{claimed_level}**\n"
                f"{claim_status}"
            ),
            color=0xFF7518,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embeds.set_footer(embed, "Event active for 10 days", "Study in any VC to progress")

        view = PumpkinPassView(ctx.author.id, self.db, pass_data)
        await ctx.send(embed=embed, view=view)

    # ------------------------------------------------------------------ #
    # 2. HALLO-BOXES INVENTORY & INSTANT OPENING
    # ------------------------------------------------------------------ #
    @commands.command(name="boxes", aliases=["halloboxes", "myboxes"])
    @commands.guild_only()
    async def boxes_cmd(self, ctx: commands.Context) -> None:
        """View your unboxed Hallo-Boxes inventory."""
        inv = await self.db.get_inventory(ctx.author.id, ctx.guild.id)
        currency = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
        candy = currency.get("candy", 0)

        box_lines = []
        total_boxes = 0
        for box_id in halloween_catalog.HALLO_BOX_ORDER:
            qty = inv.get(box_id, 0)
            total_boxes += qty
            box = halloween_catalog.get_box(box_id)
            if not box:
                continue
            box_lines.append(
                f"{box['emoji']} **{box['name']}** ··· **x{qty}**\n"
                f"   ↳ *{box['description']}*"
            )

        boxes_text = "\n\n".join(box_lines)
        embed = embeds.base_embed(
            title=f"🎃 {ctx.author.display_name}'s Hallo-Boxes",
            description=(
                f"🍬 **Current Candy:** **{candy:,} Candy**\n"
                f"📦 **Total Hallo-Boxes:** **{total_boxes}**\n\n"
                f"{boxes_text}\n\n"
                f"💡 **NO INCUBATION NEEDED!** Open boxes instantly:\n"
                f"`{ctx.prefix}openbox <tier> [qty]` (e.g. `{ctx.prefix}openbox common 3`)\n"
                f"`{ctx.prefix}openbox all` to open all boxes at once!"
            ),
            color=0xFF7518,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        view = HalloBoxQuickOpenView(ctx.author.id, self, inv)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="openbox", aliases=["open", "openboxes"])
    @commands.guild_only()
    async def openbox_cmd(self, ctx: commands.Context, tier_query: Optional[str] = None, qty: int = 1) -> None:
        """Instantly open Hallo-Box(es) or Mystery Box(es) without waiting!
        
        Usage:
          .openbox                  — Open your best available box
          .openbox common           — Open 1 Common Hallo-Box
          .openbox rare 3           — Open 3 Rare Hallo-Boxes
          .openbox all              — Open all Hallo-Boxes in inventory
          .openbox mystery          — Open a Mystery Box
        """
        if qty < 1:
            await ctx.send(embed=embeds.error_embed("Quantity must be at least 1."))
            return

        inv = await self.db.get_inventory(ctx.author.id, ctx.guild.id)

        # Handle 'all' keyword: open all boxes owned across all tiers
        if tier_query and tier_query.strip().lower() in ("all", "every", "everything"):
            owned_boxes = [(bid, inv[bid]) for bid in halloween_catalog.HALLO_BOX_ORDER if inv.get(bid, 0) > 0]
            if not owned_boxes:
                await ctx.send(embed=embeds.error_embed(
                    f"You don't have any Hallo-Boxes to open! Find them while studying or in `{ctx.prefix}daily`."
                ))
                return
            for bid, bqty in owned_boxes:
                await self._do_open_box(ctx, bid, bqty)
            return

        # Handle no argument: intelligent auto-select
        if tier_query is None:
            # Check for Hallo-Boxes from highest tier down
            chosen_box_id = None
            for bid in reversed(halloween_catalog.HALLO_BOX_ORDER):
                if inv.get(bid, 0) > 0:
                    chosen_box_id = bid
                    break

            if chosen_box_id:
                await self._do_open_box(ctx, chosen_box_id, 1)
                return

            # Check if user has a standard Mystery Box
            if inv.get("mystery_box", 0) > 0:
                await self._open_mystery_box(ctx)
                return

            await ctx.send(embed=embeds.error_embed(
                f"You don't have any boxes to open!\n"
                f"Find Hallo-Boxes by studying (`{ctx.prefix}start`), claiming `{ctx.prefix}daily`, or doing `{ctx.prefix}work`.\n"
                f"Or buy a Mystery Box from `{ctx.prefix}shop`."
            ))
            return

        # Check if user asked to open a mystery box
        clean_q = tier_query.strip().lower()
        if clean_q in ("mystery", "mystery_box", "mysterybox", "gift"):
            await self._open_mystery_box(ctx)
            return

        # Resolve Hallo-Box tier
        box_id = halloween_catalog.resolve_box_id(tier_query)
        if not box_id:
            await ctx.send(embed=embeds.error_embed(
                f"Unknown box tier `{tier_query}`. Valid tiers: `common`, `uncommon`, `rare`, `epic`, `legendary`."
            ))
            return

        await self._do_open_box(ctx, box_id, qty)

    async def _do_open_box(self, ctx_or_interaction: Any, box_id: str, qty: int) -> None:
        """Worker that executes the instant Hallo-Box opening."""
        user = ctx_or_interaction.author if hasattr(ctx_or_interaction, "author") else ctx_or_interaction.user
        guild_id = ctx_or_interaction.guild.id
        prefix = config.PREFIX

        result = await self.db.open_hallo_box(user.id, guild_id, box_id, qty)
        if not result["success"]:
            reason = result.get("reason")
            if reason == "insufficient_qty":
                owned = result.get("owned", 0)
                msg = f"You only have **x{owned}** of that box (tried to open x{qty})."
            else:
                msg = "Failed to open box."
            if hasattr(ctx_or_interaction, "followup"):
                await ctx_or_interaction.followup.send(embed=embeds.error_embed(msg))
            else:
                await ctx_or_interaction.send(embed=embeds.error_embed(msg))
            return

        box = result["box"]
        reward_lines = [
            f"🍬 **+{result['candy']:,} Candy**",
            f"🪙 **+{result['coins']:,} Coins**",
        ]

        # Pets
        for pet_res in result["pets"]:
            sid = pet_res["species_id"]
            p_data = pet_catalog.PETS.get(sid, {})
            p_name = p_data.get("name", sid.capitalize())
            p_species = p_data.get("species", "Companion")
            if pet_res["new_pet"]:
                reward_lines.append(f"✨ 🐾 **NEW PET UNLOCKED! {p_name} the {p_species}!**")
            else:
                b_xp = pet_res.get("pet_xp_bonus", 500)
                b_c = pet_res.get("coin_bonus", 500)
                reward_lines.append(f"🐾 **Duplicate Pet ({p_name}):** +{b_xp} Pet XP & +{b_c} bonus coins!")

        # Food
        for fid, fqty in result["food"].items():
            f = food_catalog.FOODS.get(fid, {})
            fname = f.get("name", fid)
            reward_lines.append(f"🍛 **x{fqty} {fname}**")

        # Items & Boosts
        for iid, iqty in result["items"].items():
            if iid == "sugar_rush":
                reward_lines.append(f"⚡ **x{iqty} Sugar Rush Boost** (1h 2x Study XP)")
            elif iid == "mystery_box":
                reward_lines.append(f"🎁 **x{iqty} Mystery Box**")
            else:
                reward_lines.append(f"📦 **x{iqty} {iid.replace('_', ' ').capitalize()}**")

        loot_str = "\n".join(reward_lines)
        embed = embeds.base_embed(
            title=f"{box['emoji']} {box['name']} Opened! (x{qty})",
            description=(
                f"**Spoils Revealed:**\n"
                f"{loot_str}\n\n"
                f"Spend your Candy in the `{prefix}candyshop`!"
            ),
            color=box["color"],
        )

        # Set thumbnail to first pet unlocked if available
        if result["pets"] and result["pets"][0].get("species_id"):
            sid = result["pets"][0]["species_id"]
            stages = pet_catalog.PETS.get(sid, {}).get("stages", [])
            if stages:
                embed.set_thumbnail(url=stages[0]["sprite"])

        log.info(f"HALLO BOX OPEN | {user} opened {box_id} x{qty} in guild {guild_id}")
        if hasattr(ctx_or_interaction, "followup"):
            await ctx_or_interaction.followup.send(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    async def _open_mystery_box(self, ctx: commands.Context) -> None:
        """Backwards-compatible Mystery Box opener."""
        result = await self.db.open_mystery_box(ctx.author.id, ctx.guild.id)
        if not result["success"]:
            await ctx.send(embed=embeds.error_embed(
                f"You don't have a Mystery Box. Buy one with `{ctx.prefix}buy mystery box`."
            ))
            return

        reward = result["reward"]
        if reward["kind"] == "coins":
            desc = f"🪙 You got **{reward['amount']:,} coins**!"
        elif reward["kind"] == "xp":
            desc = f"✨ You got **{reward['amount']:,} XP**!"
        else:
            item = economy.SHOP_ITEMS.get(reward["item_id"], {})
            desc = f"{item.get('emoji', '')} You got a **{item.get('name', reward['item_id'])}**!"

        embed = embeds.base_embed(title="🎁 Mystery Box Opened!", description=desc, color=embeds.COLOR_LEVELUP)
        if result.get("leveled_up"):
            embed.add_field(
                name="🎉 Level Up!",
                value=f"Level {result['old_level']} → **Level {result['new_level']}**",
                inline=False,
            )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # 3. THE LIMITED CANDY SHOP
    # ------------------------------------------------------------------ #

    @commands.command(name="candyshop", aliases=["spookyshop", "cshop", "halloween"])
    @commands.guild_only()
    async def candyshop_cmd(self, ctx: commands.Context) -> None:
        """Browse the exclusive limited-time Halloween Candy Shop."""
        currency = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
        candy = currency.get("candy", 0)

        item_lines = []
        for item_key in halloween_catalog.CANDY_SHOP_ORDER:
            item = halloween_catalog.CANDY_SHOP_ITEMS[item_key]
            cost = item["candy_price"]
            can_afford = "✅" if candy >= cost else "🔒"
            item_lines.append(
                f"{item['emoji']} **{item['name']}** — **{cost:,} 🍬 Candy** {can_afford}\n"
                f"   ↳ *{item['description']}*\n"
                f"   ↳ Purchase: `{ctx.prefix}buycandy {item_key}`"
            )

        items_text = "\n\n".join(item_lines)
        embed = embeds.base_embed(
            title="🎃 The Halloween Candy Shop",
            description=(
                f"🍬 **Your Candy:** **{candy:,} Candy**\n\n"
                f"{items_text}\n\n"
                f"Earn Candy by studying (`{ctx.prefix}start`), opening Hallo-Boxes (`{ctx.prefix}openbox`), "
                f"and progressing your personal Jack-o'-Lantern pass (`{ctx.prefix}pumpkin`)!"
            ),
            color=0xFF7518,
        )
        embeds.set_footer(embed, "Limited event shop", f"{ctx.prefix}buycandy <item>")

        view = CandyShopView(ctx.author.id, self, candy)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="buycandy", aliases=["candypurchase", "spookybuy"])
    @commands.guild_only()
    async def buycandy_cmd(self, ctx: commands.Context, item: str, qty: int = 1) -> None:
        """Purchase an exclusive Halloween reward using Candy."""
        if qty < 1:
            await ctx.send(embed=embeds.error_embed("Quantity must be at least 1."))
            return
        await self._do_buy_candy(ctx, item, qty)

    async def _do_buy_candy(self, ctx_or_interaction: Any, item_key: str, qty: int) -> None:
        """Worker that handles purchasing items with Candy."""
        user = ctx_or_interaction.author if hasattr(ctx_or_interaction, "author") else ctx_or_interaction.user
        guild_id = ctx_or_interaction.guild.id
        prefix = config.PREFIX

        result = await self.db.buy_candy_item(user.id, guild_id, item_key, qty)
        if not result["success"]:
            reason = result.get("reason")
            if reason == "insufficient_candy":
                req = result.get("required", 0)
                cur = result.get("current", 0)
                msg = f"You don't have enough Candy! Need **{req:,} 🍬**, you have **{cur:,} 🍬**."
            elif reason == "already_owned":
                msg = "You already own this event-exclusive item!"
            elif reason == "single_only":
                msg = "You can only purchase 1 of this item at a time."
            else:
                msg = f"Couldn't find that item in the Candy Shop. Check `{prefix}candyshop`."

            if hasattr(ctx_or_interaction, "followup"):
                await ctx_or_interaction.followup.send(embed=embeds.error_embed(msg))
            else:
                await ctx_or_interaction.send(embed=embeds.error_embed(msg))
            return

        item = result["item"]
        price = result["price"]

        if item["type"] == "pet":
            pet_res = result.get("pet_result", {})
            species = pet_catalog.PETS["pumpkaboo"]
            note = "\nEquipped automatically as your active study companion!" if pet_res.get("auto_equipped") else (
                f"\nEquip it anytime with `{prefix}equip Pumpkaboo`."
            )
            embed = embeds.success_embed(
                "🎃 Event Pet Adopted!",
                f"You adopted **Pumpkaboo** the Pumpkin Pokémon for **{price:,} 🍬 Candy**!{note}\n"
                f"It gains XP and evolves into Gourgeist as you study!",
            )
            embed.color = 0xFF7518
            embed.set_thumbnail(url=species["stages"][0]["sprite"])

        elif item["type"] == "title":
            title_text = item.get("title_text", item["name"])
            embed = embeds.success_embed(
                "👑 Title Unlocked!",
                f"You purchased the exclusive title **\"{title_text}\"** for **{price:,} 🍬 Candy**!\n"
                f"Equip it to your profile with `{prefix}settitle {title_text}`.",
            )
            embed.color = 0xFF7518

        elif item["type"] == "boost":
            qty_text = f" x{qty}" if qty > 1 else ""
            embed = embeds.success_embed(
                "⚡ Sugar Rush Activated!",
                f"Purchased **Sugar Rush{qty_text}** for **{price:,} 🍬 Candy**!\n"
                f"Use it with `{prefix}use sugar rush` to receive **2x Study XP for 1 hour**!",
            )
            embed.color = 0xFF7518
        else:
            embed = embeds.success_embed("Purchase Complete", f"Bought {item['name']} for {price:,} Candy.")

        log.info(f"CANDY BUY      | {user} bought '{item_key}' x{qty} for {price} candy in guild {guild_id}")
        if hasattr(ctx_or_interaction, "followup"):
            await ctx_or_interaction.followup.send(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    # ------------------------------------------------------------------ #
    # 4. EVENT ANNOUNCEMENT (prefix-aware, rates pulled from the catalog)
    # ------------------------------------------------------------------ #
    @commands.command(name="event", aliases=["halloweeninfo", "spooky", "eventinfo"])
    @commands.guild_only()
    async def event_cmd(self, ctx: commands.Context) -> None:
        """Post the Halloween event announcement with live drop rates and reward maths."""
        p = ctx.prefix
        cat = halloween_catalog

        chances = cat.tier_chances()
        per_box = cat.expected_box_rates()
        hourly = cat.study_hourly_estimate()
        totals = cat.pass_reward_totals()
        max_hours = cat.JACK_O_LANTERN_LEVELS[-1]["required_seconds"] / 3600.0
        per_hour = hourly["candy_total"]
        shop = cat.CANDY_SHOP_ITEMS

        supply = " · ".join(
            f"{cat.HALLO_BOXES[bid]['emoji']} {cat.HALLO_BOXES[bid]['tier'].capitalize()} "
            f"**{chances[bid] * 100:.0f}%**"
            for bid, _ in cat.STUDY_BOX_ROLL_WEIGHTS
        )
        box_totals = " ".join(
            f"{cat.HALLO_BOXES[bid]['emoji']} {qty}" for bid, qty in totals["boxes"].items()
        )

        embed = embeds.base_embed(
            title="\U0001F383 CHRONOS HALLOWEEN EVENT \u00B7 10 Days",
            description=(
                "> *Something is stirring in the pumpkin patch...*\n"
                "> The patch pays in **\U0001F36C Candy** now: study, carve, and spend before the candles go out.\n\n"
                "**\U0001F36C Candy** \u00B7 event currency, shown in "
                f"`{p}balance`. Earned while studying, from dailies, and from every box.\n"
                "**\U0001F383 Jack-o'-Lantern** \u00B7 one per account, carved by your study time. No timers.\n"
                "**\U0001F4E6 Hallo-Boxes** \u00B7 100% drop-only, **opened instantly, no incubation**."
            ),
            color=0xFF7518,
        )

        embed.add_field(
            name="\U0001F383 Your Jack-o'-Lantern",
            value=(
                "Levels up through 5 carving stages as you study:\n"
                "\U0001FAB5 Raw Gourd (0h) \u2192 \U0001F56F\uFE0F Candlelit (2h) \u2192 "
                "\U0001F383 Smiling Jack (5h) \u2192 \U0001FAA6 Haunted Jack (10h) \u2192 "
                "\U0001F451 The Great Pumpkin (20h)\n"
                f"14 milestone levels \u00B7 claim with `{p}pumpkin claim`"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F4E6 Where boxes come from",
            value=(
                f"Study drops (~1 every 18 min), plus `{p}daily`, `{p}work`, `{p}beg`, "
                f"`{p}weekly`, and pass milestones.\n"
                f"Open: `{p}openbox <tier> [qty]` or `{p}openbox all`"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F56F\uFE0F The Drop Table (lore of the patch)",
            value=(
                f"{supply}\n"
                "*The patch is generous with kindling and stingy with crowns: one box in a hundred "
                "is Legendary. When the Great Pumpkin blinks, you blink back.*\n\n"
                f"Per box on average: **~{per_box['candy']:.0f} \U0001F36C**, "
                f"**~{per_box['coins']:,.0f} \U0001F4B0**, "
                f"{per_box['pet'] * 100:.0f}% pet \u00B7 {per_box['food'] * 100:.0f}% food \u00B7 "
                f"{per_box['item'] * 100:.1f}% boost/mystery"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F4CA The Maths of the Patch (per hour of study)",
            value=(
                f"\U0001F4E6 **{hourly['boxes']:.1f} boxes** \u00B7 "
                f"\U0001F36C **~{hourly['candy_total']:.0f} Candy** "
                f"({hourly['candy_direct']:.0f} study + {hourly['candy_boxes']:.0f} boxes)\n"
                f"\U0001F4B0 **~{hourly['coins_boxes']:,.0f} coins/hr** from boxes \u00B7 "
                f"\U0001F43E ~{hourly['pets']:.2f} pets \u00B7 \U0001F35B ~{hourly['food']:.1f} food\n\n"
                f"**Pace:** maxing the pass takes **{max_hours:.0f}h** \u2014 about "
                f"**{max_hours / 10:.1f}h/day** across the 10 days.\n"
                f"**Full pass payout:** {totals['candy']:,} \U0001F36C \u00B7 {totals['coins']:,} \U0001F4B0 \u00B7 "
                f"{box_totals} boxes \u00B7 {totals['items'].get('sugar_rush', 0)} \u26A1 \u00B7 "
                f"\u201C{totals['titles'][0]}\u201D title"
            ),
            inline=False,
        )
        embed.add_field(
            name="\U0001F6D2 Candy Shop",
            value=(
                f"\U0001F383 **Pumpkaboo** \u2014 {shop['pumpkaboo']['candy_price']:,} \U0001F36C "
                f"(~{_hm(shop['pumpkaboo']['candy_price'] / per_hour)} of study) \u00B7 evolves into Gourgeist\n"
                f"\U0001F9EA **Inorganic Nightmare** \u2014 {shop['title_inorganic']['candy_price']:,} \U0001F36C "
                f"(~{_hm(shop['title_inorganic']['candy_price'] / per_hour)})\n"
                f"\U0001F47B **The Shift 1 Phantom** \u2014 {shop['title_shift1']['candy_price']:,} \U0001F36C "
                f"(~{_hm(shop['title_shift1']['candy_price'] / per_hour)})\n"
                f"\u26A1 **Sugar Rush** (1h \u00D7 2 XP) \u2014 {shop['sugar_rush']['candy_price']:,} \U0001F36C "
                f"(~{_hm(shop['sugar_rush']['candy_price'] / per_hour)})"
            ),
            inline=False,
        )
        embed.add_field(
            name="\u2328\uFE0F Commands",
            value=(
                f"`{p}pumpkin` \u00B7 `{p}boxes` \u00B7 `{p}openbox <tier> [qty]`\n"
                f"`{p}candyshop` \u00B7 `{p}buycandy <item>` \u00B7 `{p}balance`"
            ),
            inline=False,
        )
        embeds.set_footer(embed, "10 days only", "Rates live from the patch")

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Halloween(bot))
