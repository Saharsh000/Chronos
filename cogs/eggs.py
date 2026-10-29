"""THE EGG UPDATE - Egg inventory, incubation, and hatching cog for Chronos.

Commands:
  .eggs / .incubator     View incubator status & egg inventory
  .incubate <egg>        Start incubating an egg with study time
  .hatch [slot]          Hatch a fully-incubated egg for maximum loot & pets
  .crack <egg>           Instantly crack an egg for quick rewards
  .eggshop               Browse and purchase eggs from the shop
  .buyegg <egg> [qty]    Purchase an egg with coins
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import economy, embeds
from utils import eggs as egg_catalog
from utils import pets as pet_catalog
from utils.time_format import format_duration
from utils.views import ChronosView

log = logging.getLogger("eggs")


class EggActionView(ChronosView):
    """Interactive button controls for incubator and egg inventory."""

    def __init__(self, cog: "Eggs", ctx: commands.Context):
        super().__init__(author_id=ctx.author.id, timeout=120.0)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="\U0001F423 Hatch Ready", style=discord.ButtonStyle.success, emoji="\U0001F423")
    async def hatch_ready_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        slots = await self.cog.db.get_incubators(self.ctx.author.id, self.ctx.guild.id)
        ready_slot = next((s for s in slots if s["credited_seconds"] >= s["required_seconds"]), None)
        if not ready_slot:
            await interaction.response.send_message(
                embed=embeds.info_embed(
                    "No Ready Eggs", "None of your eggs have finished incubating yet! Keep studying to warm them up."
                ),
                ephemeral=True,
            )
            return

        result = await self.cog.db.claim_hatch(self.ctx.author.id, self.ctx.guild.id, ready_slot["slot"])
        if not result["success"]:
            await interaction.response.send_message(
                embed=embeds.error_embed("Failed to hatch this egg."), ephemeral=True
            )
            return

        hatch_embed = self.cog._build_hatch_embed(self.ctx.author, result)
        await interaction.response.send_message(embed=hatch_embed)
        # Update original incubator embed
        updated_embed = await self.cog._build_incubator_embed(self.ctx.author, self.ctx.guild)
        await interaction.message.edit(embed=updated_embed, view=self)

    @discord.ui.button(label="\U0001F6D2 Egg Shop", style=discord.ButtonStyle.primary, emoji="\U0001F6D2")
    async def shop_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        shop_embed = self.cog._build_shop_embed(self.ctx)
        await interaction.response.send_message(embed=shop_embed, ephemeral=True)


class Eggs(commands.Cog, name="Eggs"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ------------------------------------------------------------------ #
    # Embed Builders
    # ------------------------------------------------------------------ #

    async def _build_incubator_embed(self, user: discord.Member, guild: discord.Guild) -> discord.Embed:
        embed = embeds.base_embed(
            title="\U0001F95A Egg Incubator & Nest",
            description=(
                f"Eggs warm and hatch by **gaining active study time**! "
                f"Start a study session with `{config.PREFIX}start` to incubate."
            ),
            color=embeds.COLOR_PETS,
        )

        # Incubator slots
        slots = await self.db.get_incubators(user.id, guild.id)
        max_slots = 2
        slot_map = {s["slot"]: s for s in slots}

        incubator_lines = []
        for s in range(1, max_slots + 1):
            if s in slot_map:
                info = slot_map[s]
                egg = egg_catalog.get_egg(info["egg_id"]) or {}
                credited = info["credited_seconds"]
                needed = info["required_seconds"]
                progress_bar = embeds.bar(credited, needed, length=10)
                pct = int(min(1.0, credited / needed) * 100) if needed else 100

                if credited >= needed:
                    status = f"**READY TO HATCH!** \u2014 Use `{config.PREFIX}hatch {s}`"
                else:
                    left = needed - credited
                    status = f"Incubating: **{format_duration(left)}** study time left"

                egg_emoji = egg.get("emoji", "\U0001F95A")
                egg_name = egg.get("name", "Egg")
                incubator_lines.append(
                    f"**Slot {s}:** {egg_emoji} **{egg_name}**\n"
                    f"`{progress_bar}` {pct}%\n"
                    f"\u25B8 {status}\n"
                )
            else:
                incubator_lines.append(f"**Slot {s}:** *Empty* \u2014 `{config.PREFIX}incubate <egg>`\n")

        embed.add_field(name="\U0001F525 Active Incubator Slots", value="\n".join(incubator_lines), inline=False)

        # Egg Inventory
        inv = await self.db.get_inventory(user.id, guild.id)
        owned_eggs = []
        for egg_id in egg_catalog.EGG_ORDER:
            qty = inv.get(egg_id, 0)
            if qty > 0:
                egg = egg_catalog.EGGS[egg_id]
                owned_eggs.append(
                    f"{egg['emoji']} **{egg['name']}** \u00D7 {qty}  "
                    f"(`{config.PREFIX}incubate {egg['tier']}` or `{config.PREFIX}crack {egg['tier']}`)"
                )

        if owned_eggs:
            embed.add_field(name="\U0001F95A Unhatched Eggs", value="\n".join(owned_eggs), inline=False)
        else:
            embed.add_field(
                name="\U0001F95A Unhatched Eggs",
                value=(
                    f"*You don't have any eggs in your nest right now.*\n"
                    f"\u25B8 Study, `{config.PREFIX}daily`, `{config.PREFIX}work`, or check `{config.PREFIX}eggshop`!"
                ),
                inline=False,
            )

        return embed

    def _build_hatch_embed(self, user: discord.Member, result: dict) -> discord.Embed:
        egg = result.get("egg") or {}
        loot = result.get("loot") or {}
        color = egg.get("color", embeds.COLOR_SUCCESS)
        egg_emoji = egg.get("emoji", "\U0001F95A")
        egg_name = egg.get("name", "Egg")

        embed = embeds.base_embed(
            title=f"\U0001F389 {egg_emoji} {egg_name} Hatched!",
            description=f"<@{user.id}>, your egg was nurtured by your study dedication and hatched!",
            color=color,
        )

        pet_res = result.get("pet_result")
        if pet_res:
            species_id = pet_res.get("species_id")
            spec = pet_catalog.PETS.get(species_id, {})
            tier_info = pet_catalog.TIER_INFO.get(spec.get("tier", "common"), {})
            pet_emoji = tier_info.get("emoji", "\U0001F43E")

            if pet_res.get("new_pet"):
                equipped_note = " *(Auto-equipped!)*" if pet_res.get("auto_equipped") else ""
                embed.add_field(
                    name=f"{pet_emoji} NEW PET ADOPTED!",
                    value=(
                        f"You adopted **{pet_res['nickname']}** the {spec.get('name', 'Pet')}! "
                        f"({tier_info.get('label', 'Common')} Tier){equipped_note}\n"
                        f"Check your pet with `{config.PREFIX}pet` or feed it with `{config.PREFIX}feed`!"
                    ),
                    inline=False,
                )
            else:
                embed.add_field(
                    name=f"\U0001F504 Duplicate Pet Converted!",
                    value=(
                        f"You already own a **{spec.get('name', 'Pet')}**!\n"
                        f"\u25B8 **+{pet_res['pet_xp_bonus']} Pet XP** awarded to your pet!\n"
                        f"\u25B8 **+{pet_res['coin_bonus']} Bonus Coins** compensation!"
                    ),
                    inline=False,
                )

        rewards_lines = []
        if result.get("coins", 0) > 0:
            rewards_lines.append(f"\U0001F4B0 **+{result['coins']:,} Coins** (Balance: {result['new_balance']:,})")
        if result.get("xp", 0) > 0:
            rewards_lines.append(f"\U0001F525 **+{result['xp']:,} Study XP**")

        if loot.get("type") == "food" and loot.get("food_id"):
            food_name = loot["food_id"].replace("_", " ").title()
            rewards_lines.append(f"\U0001F371 **\u00D7{loot.get('qty', 1)} {food_name}** (Pet Food)")

        if loot.get("type") == "item" and loot.get("item_id"):
            item_name = loot["item_id"].replace("_", " ").title()
            rewards_lines.append(f"\U0001F381 **\u00D7{loot.get('qty', 1)} {item_name}**")

        if loot.get("title"):
            rewards_lines.append(f"\U0001F451 **Unlocked Title:** `{loot['title']}`!")

        if rewards_lines:
            embed.add_field(name="\U0001F381 Stash & Rewards", value="\n".join(rewards_lines), inline=False)

        if result.get("leveled_up"):
            embed.add_field(name="\U0001F389 Level Up!", value="You gained enough XP to level up!", inline=False)

        return embed

    def _build_shop_embed(self, ctx: commands.Context) -> discord.Embed:
        embed = embeds.base_embed(
            title="\U0001F95A The Egg Hatchery Shop",
            description=(
                f"Purchase eggs to incubate with your study sessions or crack open immediately!\n"
                f"Buy with `{ctx.prefix}buyegg <tier>` or `{ctx.prefix}buyegg <number>`."
            ),
            color=embeds.COLOR_ECONOMY,
        )

        for i, egg_id in enumerate(egg_catalog.EGG_ORDER, start=1):
            egg = egg_catalog.EGGS[egg_id]
            inc_mins = egg["incubation_seconds"] // 60
            embed.add_field(
                name=f"`#{i}` {egg['emoji']} {egg['name']} \u2014 {egg['price']:,} coins",
                value=(
                    f"{egg['desc']}\n"
                    f"\u25B8 **Study to Hatch:** {inc_mins} mins \u00B7 **Pet Tier:** {egg['tier'].capitalize()}"
                ),
                inline=False,
            )
        return embed

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    @commands.command(name="eggs", aliases=["incubator", "nest", "egg"])
    @commands.guild_only()
    async def eggs_cmd(self, ctx: commands.Context) -> None:
        """View your active incubator slots and unhatched eggs."""
        embed = await self._build_incubator_embed(ctx.author, ctx.guild)
        view = EggActionView(self, ctx)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="incubate", aliases=["warm"])
    @commands.guild_only()
    async def incubate_cmd(self, ctx: commands.Context, *, egg_query: str) -> None:
        """Place an egg into your incubator to hatch it with your study time.

        Usage: .incubate common / .incubate rare / .incubate 1
        """
        egg_id = egg_catalog.resolve_egg_id(egg_query)
        if not egg_id:
            await ctx.send(
                embed=embeds.error_embed(
                    f"Unknown egg `{egg_query}`. Valid tiers: `common`, `uncommon`, `rare`, `epic`, `legendary`."
                )
            )
            return

        result = await self.db.start_incubation(ctx.author.id, ctx.guild.id, egg_id)
        if not result["success"]:
            reason = result["reason"]
            if reason == "not_owned":
                egg = egg_catalog.get_egg(egg_id)
                await ctx.send(
                    embed=embeds.error_embed(
                        f"You don't own any **{egg['name']}**! "
                        f"Get them from study sessions, `{ctx.prefix}daily`, or buy one in `{ctx.prefix}eggshop`."
                    )
                )
            elif reason == "slots_full":
                await ctx.send(
                    embed=embeds.error_embed(
                        f"All your incubator slots are full! "
                        f"Check `{ctx.prefix}eggs` or hatch ready eggs with `{ctx.prefix}hatch`."
                    )
                )
            else:
                await ctx.send(embed=embeds.error_embed("Couldn't start incubation."))
            return

        egg = result["egg"]
        inc_mins = result["required_seconds"] // 60
        embed = embeds.success_embed(
            f"{egg['emoji']} Egg Placed in Incubator Slot {result['slot']}!",
            f"Your **{egg['name']}** is now resting in Slot {result['slot']}.\n\n"
            f"\u25B8 **Study Required:** {inc_mins} minutes of active study\n"
            f"\u25B8 **Start Studying:** `{ctx.prefix}start` to warm the egg\n"
            f"\u25B8 **Check Progress:** `{ctx.prefix}eggs`",
        )
        await ctx.send(embed=embed)

    @commands.command(name="hatch")
    @commands.guild_only()
    async def hatch_cmd(self, ctx: commands.Context, slot: Optional[int] = None) -> None:
        """Hatch a fully-incubated egg from your incubator.

        Usage: .hatch (hatches first ready egg) or .hatch 1 / .hatch 2
        """
        slots = await self.db.get_incubators(ctx.author.id, ctx.guild.id)
        if not slots:
            await ctx.send(
                embed=embeds.info_embed(
                    "No Incubating Eggs",
                    f"You don't have any eggs in your incubator! Place one with `{ctx.prefix}incubate <tier>`.",
                )
            )
            return

        if slot is None:
            ready = next((s for s in slots if s["credited_seconds"] >= s["required_seconds"]), None)
            if not ready:
                # Find the one closest to ready
                closest = min(slots, key=lambda s: s["required_seconds"] - s["credited_seconds"])
                left = closest["required_seconds"] - closest["credited_seconds"]
                egg = egg_catalog.get_egg(closest["egg_id"])
                await ctx.send(
                    embed=embeds.info_embed(
                        "Not Ready Yet",
                        f"Your **{egg.get('name', 'Egg')}** in Slot {closest['slot']} still needs **{format_duration(left)}** "
                        f"of study time to hatch! Keep studying with `{ctx.prefix}start`.",
                    )
                )
                return
            target_slot = ready["slot"]
        else:
            target_slot = slot

        result = await self.db.claim_hatch(ctx.author.id, ctx.guild.id, target_slot)
        if not result["success"]:
            reason = result["reason"]
            if reason == "not_found":
                await ctx.send(embed=embeds.error_embed(f"Slot {target_slot} is empty."))
            elif reason == "still_incubating":
                left = result.get("remaining_seconds", 0)
                await ctx.send(
                    embed=embeds.info_embed(
                        "Still Incubating",
                        f"That egg needs **{format_duration(left)}** more study time to hatch!",
                    )
                )
            return

        embed = self._build_hatch_embed(ctx.author, result)
        await ctx.send(embed=embed)

    @commands.command(name="crack", aliases=["instantcrack", "smash"])
    @commands.guild_only()
    async def crack_cmd(self, ctx: commands.Context, *, egg_query: str) -> None:
        """Instantly crack an egg from your inventory without waiting for incubation.

        Usage: .crack common / .crack rare / .crack 1
        """
        egg_id = egg_catalog.resolve_egg_id(egg_query)
        if not egg_id:
            await ctx.send(
                embed=embeds.error_embed(f"Unknown egg tier `{egg_query}`. Try `common`, `rare`, `epic`, etc.")
            )
            return

        result = await self.db.crack_egg_direct(ctx.author.id, ctx.guild.id, egg_id)
        if not result["success"]:
            egg = egg_catalog.get_egg(egg_id)
            await ctx.send(embed=embeds.error_embed(f"You don't have any **{egg['name']}** in your inventory!"))
            return

        egg = result["egg"]
        embed = embeds.base_embed(
            title=f"\U0001F528 {egg['emoji']} Cracked Open a {egg['name']}!",
            description=f"<@{ctx.author.id}> cracked open an unincubated egg for instant loot:",
            color=egg["color"],
        )

        pet_res = result.get("pet_result")
        if pet_res:
            species_id = pet_res.get("species_id")
            spec = pet_catalog.PETS.get(species_id, {})
            tier_info = pet_catalog.TIER_INFO.get(spec.get("tier", "common"), {})
            lucky_emoji = tier_info.get("emoji", "\U0001F43E")
            embed.add_field(
                name=f"{lucky_emoji} LUCKY FIND!",
                value=f"Against the odds, a **{spec.get('name', 'Pet')}** was inside!",
                inline=False,
            )

        rewards_lines = []
        if result.get("coins", 0) > 0:
            rewards_lines.append(f"\U0001F4B0 **+{result['coins']:,} Coins** (Balance: {result['new_balance']:,})")
        if result.get("xp", 0) > 0:
            rewards_lines.append(f"\U0001F525 **+{result['xp']:,} Study XP**")

        loot = result.get("loot") or {}
        if loot.get("type") == "food" and loot.get("food_id"):
            food_name = loot["food_id"].replace("_", " ").title()
            rewards_lines.append(f"\U0001F371 **\u00D7{loot.get('qty', 1)} {food_name}** (Pet Food)")

        if rewards_lines:
            embed.add_field(name="\U0001F381 Loot Unlocked", value="\n".join(rewards_lines), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="eggshop", aliases=["hatchery"])
    @commands.guild_only()
    async def eggshop_cmd(self, ctx: commands.Context) -> None:
        """Browse all 5 tiers of eggs available in the hatchery."""
        embed = self._build_shop_embed(ctx)
        await ctx.send(embed=embed)

    @commands.command(name="buyegg")
    @commands.guild_only()
    async def buyegg_cmd(self, ctx: commands.Context, egg_query: str, quantity: int = 1) -> None:
        """Purchase eggs with coins directly from the hatchery.

        Usage: .buyegg common / .buyegg rare 2 / .buyegg 3
        """
        if quantity <= 0:
            await ctx.send(embed=embeds.error_embed("Quantity must be positive."))
            return

        egg_id = egg_catalog.resolve_egg_id(egg_query)
        if not egg_id:
            await ctx.send(embed=embeds.error_embed(f"Unknown egg tier `{egg_query}`. See `{ctx.prefix}eggshop`."))
            return

        egg = egg_catalog.get_egg(egg_id)
        total_price = egg["price"] * quantity

        spent = await self.db.spend_coins(ctx.author.id, ctx.guild.id, total_price)
        if not spent:
            currency = await self.db.get_currency(ctx.author.id, ctx.guild.id)
            bal = currency.get("coins", 0) if currency else 0
            await ctx.send(
                embed=embeds.error_embed(
                    f"You don't have enough coins! Total cost: **{total_price:,}** coins (You have: **{bal:,}**)."
                )
            )
            return

        await self.db.add_item(ctx.author.id, ctx.guild.id, egg_id, quantity)
        currency = await self.db.get_currency(ctx.author.id, ctx.guild.id)
        new_balance = currency.get("coins", 0) if currency else 0

        embed = embeds.success_embed(
            f"{egg['emoji']} Eggs Purchased!",
            f"Bought **\u00D7{quantity} {egg['name']}** for **{total_price:,}** coins.\n"
            f"New Balance: **{new_balance:,}** coins.\n\n"
            f"\u25B8 Incubate with `{ctx.prefix}incubate {egg['tier']}` or check `{ctx.prefix}eggs`!",
        )
        await ctx.send(embed=embed)

    @incubate_cmd.error
    @hatch_cmd.error
    @crack_cmd.error
    @buyegg_cmd.error
    async def egg_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=embeds.error_embed(f"Usage: `{ctx.prefix}{ctx.command.name} <tier>`"))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("This command can only be used inside a server."))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Eggs(bot))
