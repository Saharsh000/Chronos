"""Pet system: `.petshop` / `.buypet` / `.pets` / `.pet` / `.equip` /
`.nickname`, and pet food: `.foodshop` / `.buyfood` / `.feed` /
`.sellfood`.

Pets are a one-time-per-species unlock (like the coin shop's titles -
see cogs/economy.py) bought with the same shared coin balance,
requiring `config.PET_UNLOCK_LEVEL`. Whichever pet you `.equip` is the
one that passively earns XP while you study (see credit_progress in
database.py) and the one `.feed` feeds. See utils/pets.py and
utils/food.py for the full catalogs.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import embeds
from utils import food as food_catalog
from utils import pets as pet_catalog
from utils.xp import progress_bar

log = logging.getLogger("pets")


def _pet_line(species_id: str, pet_row: dict) -> str:
    species = pet_catalog.PETS[species_id]
    tier = pet_catalog.TIER_INFO[species["tier"]]
    stage = pet_catalog.stage_for_level(species_id, pet_row["level"])
    star = " \u2B50" if pet_row["equipped"] else ""
    return (
        f"{tier['emoji']} **{pet_row['nickname']}** ({stage['name']}) "
        f"\u2014 Lv. {pet_row['level']}{star}"
    )


def _pet_embed_color(species_id: str) -> int:
    return pet_catalog.TIER_INFO[pet_catalog.PETS[species_id]["tier"]]["color"]


class Pets(commands.Cog, name="Pets"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def _announce_achievements(self, ctx: commands.Context) -> None:
        newly = await self.db.check_achievements(ctx.author.id, ctx.guild.id)
        if newly:
            await ctx.send(embed=embeds.achievement_unlock_embed(ctx.author, newly))

    async def _resolve_owned(self, ctx: commands.Context, text: str) -> Optional[dict]:
        """Match typed text against the caller's owned pets: current
        nickname first, then species id/default-name/stage-name."""
        owned = await self.db.get_owned_pets(ctx.author.id, ctx.guild.id)
        needle = text.strip().lower()
        for row in owned:
            if row["nickname"].lower() == needle:
                return row
        species_id = pet_catalog.resolve_species(text)
        if species_id:
            for row in owned:
                if row["species_id"] == species_id:
                    return row
        return None

    # ------------------------------------------------------------------ #
    # .petshop
    # ------------------------------------------------------------------ #
    @commands.command(name="petshop", aliases=["pshop"])
    @commands.guild_only()
    async def petshop_cmd(self, ctx: commands.Context, tier: Optional[str] = None) -> None:
        """Browse buyable pets. `.petshop` for the tier overview, or
        `.petshop <tier>` (common/uncommon/rare/epic/legendary) to see
        every pet in that tier and its price."""
        if tier is None:
            currency = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
            stats = await self.db.get_or_create_user_stats(ctx.author.id, ctx.guild.id)
            embed = embeds.base_embed(
                title="\U0001F43E Chronos Pet Shop",
                description=(
                    f"You have **{currency['coins']:,}** coins and are **Level {stats['level']}** "
                    f"(pets unlock at Level {config.PET_UNLOCK_LEVEL}).\n"
                    f"Use `{ctx.prefix}petshop <tier>` to see pets in a tier, then "
                    f"`{ctx.prefix}buypet <name>` to buy one."
                ),
                color=embeds.COLOR_PRIMARY,
            )
            for t in pet_catalog.TIER_ORDER:
                info = pet_catalog.TIER_INFO[t]
                ids = pet_catalog.PETS_BY_TIER[t]
                prices = sorted({pet_catalog.pet_cost(i) for i in ids})
                price_text = f"{prices[0]:,}" if len(prices) == 1 else f"{prices[0]:,}\u2013{prices[-1]:,}"
                embed.add_field(
                    name=f"{info['emoji']} {info['label']} ({len(ids)} pets)",
                    value=f"{price_text} coins",
                    inline=True,
                )
            embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 e.g. \"{ctx.prefix}petshop rare\"")
            await ctx.send(embed=embed)
            return

        tier_key = tier.strip().lower()
        if tier_key not in pet_catalog.TIER_INFO:
            await ctx.send(embed=embeds.error_embed(
                f"Unknown tier `{tier}`. Try one of: {', '.join(pet_catalog.TIER_ORDER)}."
            ))
            return

        info = pet_catalog.TIER_INFO[tier_key]
        owned_ids = {p["species_id"] for p in await self.db.get_owned_pets(ctx.author.id, ctx.guild.id)}
        embed = embeds.base_embed(
            title=f"{info['emoji']} {info['label']} Pets",
            description=f"Buy with `{ctx.prefix}buypet <name>`. \u2B50 = already owned.",
            color=info["color"],
        )
        for species_id in pet_catalog.PETS_BY_TIER[tier_key]:
            species = pet_catalog.PETS[species_id]
            price = pet_catalog.pet_cost(species_id)
            chain = " \u2192 ".join(s["name"] for s in species["stages"])
            owned_mark = " \u2B50" if species_id in owned_ids else ""
            embed.add_field(
                name=f"{species['name']} \u2014 {species['species']} ({price:,} coins){owned_mark}",
                value=f"*{species['desc']}*\n{chain}",
                inline=False,
            )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # .buypet
    # ------------------------------------------------------------------ #
    @commands.command(name="buypet")
    @commands.guild_only()
    async def buypet_cmd(self, ctx: commands.Context, *, name: str) -> None:
        """Buy (permanently unlock) a pet species from `.petshop`."""
        species_id = pet_catalog.resolve_species(name)
        if species_id is None:
            await ctx.send(embed=embeds.error_embed(
                f"Couldn't find that pet. Check `{ctx.prefix}petshop <tier>` for names."
            ))
            return

        result = await self.db.buy_pet(ctx.author.id, ctx.guild.id, species_id)
        if not result["success"]:
            reasons = {
                "already_owned": "You already own that pet.",
                "not_found": "That pet doesn't exist.",
                "level_too_low": f"You need to be Level {config.PET_UNLOCK_LEVEL}+ to buy a pet.",
                "insufficient_funds": "You don't have enough coins for that.",
            }
            await ctx.send(embed=embeds.error_embed(reasons.get(result["reason"], "Purchase failed.")))
            return

        species = pet_catalog.PETS[species_id]
        note = f"\nEquipped automatically since it's your first pet!" if result["auto_equipped"] else (
            f"\nEquip it with `{ctx.prefix}equip {species['name']}`."
        )
        log.info(
            f"PET BUY       | {ctx.author} ({ctx.author.id}) bought '{species_id}' "
            f"in guild {ctx.guild.id} for {result['price']}"
        )
        embed = embeds.success_embed(
            "Pet unlocked!",
            f"You got **{species['name']}** the {species['species']} for **{result['price']:,} coins**.{note}",
        )
        embed.color = _pet_embed_color(species_id)
        embed.set_thumbnail(url=species["stages"][0]["sprite"])
        await ctx.send(embed=embed)
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .pets
    # ------------------------------------------------------------------ #
    @commands.command(name="pets")
    @commands.guild_only()
    async def pets_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """See your (or someone else's) owned pets."""
        target = member or ctx.author
        owned = await self.db.get_owned_pets(target.id, ctx.guild.id)
        embed = embeds.base_embed(title=f"\U0001F43E {target.display_name}'s Pets", color=embeds.COLOR_PRIMARY)
        embed.set_thumbnail(url=target.display_avatar.url)

        if not owned:
            embed.description = f"No pets yet - check out `{ctx.prefix}petshop`."
        else:
            lines = [_pet_line(row["species_id"], row) for row in owned]
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 {ctx.prefix}pet <name> for details, {ctx.prefix}equip <name> to switch")

        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # .pet
    # ------------------------------------------------------------------ #
    @commands.command(name="pet")
    @commands.guild_only()
    async def pet_cmd(self, ctx: commands.Context, *, name: Optional[str] = None) -> None:
        """View one pet's stats in detail. Defaults to your equipped pet."""
        if name is None:
            row = await self.db.get_equipped_pet(ctx.author.id, ctx.guild.id)
            if row is None:
                await ctx.send(embed=embeds.error_embed(
                    f"You don't have a pet equipped. `{ctx.prefix}pets` to see what you own, "
                    f"or `{ctx.prefix}petshop` to get one."
                ))
                return
        else:
            row = await self._resolve_owned(ctx, name)
            if row is None:
                await ctx.send(embed=embeds.error_embed(f"You don't own a pet called `{name}`."))
                return

        species = pet_catalog.PETS[row["species_id"]]
        tier = pet_catalog.TIER_INFO[species["tier"]]
        stage = pet_catalog.stage_for_level(row["species_id"], row["level"])
        into, needed, _ = pet_catalog.xp_progress(row["xp"])
        bar = progress_bar(into, needed)

        embed = embeds.base_embed(
            title=f"{tier['emoji']} {row['nickname']}",
            color=tier["color"],
        )
        embed.set_image(url=stage["sprite"])
        embed.add_field(name="Species", value=f"{species['name']} the {species['species']}", inline=True)
        embed.add_field(name="Tier", value=tier["label"], inline=True)
        embed.add_field(name="Level", value=str(row["level"]), inline=True)
        embed.add_field(name="Stage", value=f"{stage['name']} ({pet_catalog.BADGE_LABELS[stage['badge']]})", inline=True)
        embed.add_field(name="XP", value=f"{bar}\n{into:,} / {needed:,} XP", inline=False)

        nxt = pet_catalog.next_stage(row["species_id"], row["level"])
        if nxt:
            embed.add_field(name="Next Evolution", value=f"{nxt['name']} at Lv. {nxt['level']}", inline=False)
        else:
            embed.add_field(name="Next Evolution", value="Fully evolved!", inline=False)

        if row["equipped"]:
            embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 \u2B50 Equipped")
        else:
            embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 {ctx.prefix}equip {row['nickname']} to switch to this pet")

        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # .equip
    # ------------------------------------------------------------------ #
    @commands.command(name="equip")
    @commands.guild_only()
    async def equip_cmd(self, ctx: commands.Context, *, name: str) -> None:
        """Equip an owned pet - only your equipped pet earns XP while
        studying and gets fed by `.feed`."""
        row = await self._resolve_owned(ctx, name)
        if row is None:
            await ctx.send(embed=embeds.error_embed(
                f"You don't own a pet called `{name}`. Check `{ctx.prefix}pets`."
            ))
            return
        await self.db.equip_pet(ctx.author.id, ctx.guild.id, row["species_id"])
        await ctx.send(embed=embeds.success_embed("Pet equipped", f"**{row['nickname']}** is now your active pet."))

    # ------------------------------------------------------------------ #
    # .nickname
    # ------------------------------------------------------------------ #
    @commands.command(name="nickname", aliases=["nick", "renamepet"])
    @commands.guild_only()
    async def nickname_cmd(self, ctx: commands.Context, current: str, *, new_name: str) -> None:
        """Rename an owned pet: `.nickname <current name> <new nickname>`."""
        row = await self._resolve_owned(ctx, current)
        if row is None:
            await ctx.send(embed=embeds.error_embed(
                f"You don't own a pet called `{current}`. Check `{ctx.prefix}pets`."
            ))
            return

        new_name = new_name.strip().replace("`", "'")
        if not new_name:
            await ctx.send(embed=embeds.error_embed("Nicknames can't be empty."))
            return
        if len(new_name) > 32:
            await ctx.send(embed=embeds.error_embed("Nicknames must be 32 characters or fewer."))
            return

        await self.db.rename_pet(ctx.author.id, ctx.guild.id, row["species_id"], new_name)
        await ctx.send(embed=embeds.success_embed(
            "Pet renamed", f"**{row['nickname']}** is now called **{new_name}**."
        ))

    # ------------------------------------------------------------------ #
    # .foodshop
    # ------------------------------------------------------------------ #
    @commands.command(name="foodshop", aliases=["fshop"])
    @commands.guild_only()
    async def foodshop_cmd(self, ctx: commands.Context, tier: Optional[str] = None) -> None:
        """Browse pet food. `.foodshop` for the tier overview, or
        `.foodshop <tier>` (snack/meal/feast/golden) for the full list."""
        if tier is None:
            currency = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)
            embed = embeds.base_embed(
                title="\U0001F372 Chronos Food Shop",
                description=(
                    f"You have **{currency['coins']:,}** coins. Use `{ctx.prefix}foodshop <tier>` to browse, "
                    f"`{ctx.prefix}buyfood <name>` to buy, and `{ctx.prefix}feed <name>` to feed your equipped pet."
                ),
                color=embeds.COLOR_PRIMARY,
            )
            for t in food_catalog.FOOD_TIER_ORDER:
                info = food_catalog.FOOD_TIER_INFO[t]
                ids = food_catalog.FOODS_BY_TIER[t]
                prices = [food_catalog.FOODS[i]["cost"] for i in ids]
                embed.add_field(
                    name=f"{info['emoji']} {info['label']} ({len(ids)} items)",
                    value=f"{min(prices):,}\u2013{max(prices):,} coins",
                    inline=True,
                )
            embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 e.g. \"{ctx.prefix}foodshop feast\"")
            await ctx.send(embed=embed)
            return

        tier_key = tier.strip().lower()
        if tier_key not in food_catalog.FOOD_TIER_INFO:
            await ctx.send(embed=embeds.error_embed(
                f"Unknown tier `{tier}`. Try one of: {', '.join(food_catalog.FOOD_TIER_ORDER)}."
            ))
            return

        info = food_catalog.FOOD_TIER_INFO[tier_key]
        embed = embeds.base_embed(
            title=f"{info['emoji']} {info['label']} Food",
            description=f"Buy with `{ctx.prefix}buyfood <name> [quantity]`.",
            color=info["color"],
        )
        lines = []
        for food_id in food_catalog.FOODS_BY_TIER[tier_key]:
            f = food_catalog.FOODS[food_id]
            lines.append(f"**{f['name']}** \u2014 {f['cost']:,} coins \u2192 +{f['xp']:,} pet XP")
        embed.description += "\n\n" + "\n".join(lines)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # .buyfood
    # ------------------------------------------------------------------ #
    @commands.command(name="buyfood")
    @commands.guild_only()
    async def buyfood_cmd(self, ctx: commands.Context, *, item: str) -> None:
        """Buy pet food: `.buyfood <name> [quantity]`."""
        food_id, qty = self._parse_food_arg(item)
        if food_id is None:
            await ctx.send(embed=embeds.error_embed(
                f"Couldn't find that food. Check `{ctx.prefix}foodshop <tier>` for names."
            ))
            return

        result = await self.db.buy_food(ctx.author.id, ctx.guild.id, food_id, qty)
        if not result["success"]:
            reasons = {
                "not_found": "That food doesn't exist.",
                "insufficient_funds": "You don't have enough coins for that.",
            }
            await ctx.send(embed=embeds.error_embed(reasons.get(result["reason"], "Purchase failed.")))
            return

        f = food_catalog.FOODS[food_id]
        qty_text = f" \u00D7{result['qty']}" if result["qty"] > 1 else ""
        embed = embeds.success_embed(
            "Purchased!",
            f"**{f['name']}**{qty_text} for **{result['total_price']:,} coins**.\n"
            f"Feed it to your equipped pet with `{ctx.prefix}feed {f['name']}`.",
        )
        embed.color = food_catalog.FOOD_TIER_INFO[f["tier"]]["color"]
        await ctx.send(embed=embed)
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .feed
    # ------------------------------------------------------------------ #
    @commands.command(name="feed")
    @commands.guild_only()
    async def feed_cmd(self, ctx: commands.Context, *, item: str) -> None:
        """Feed owned food to your equipped pet: `.feed <name> [quantity]`."""
        food_id, qty = self._parse_food_arg(item)
        if food_id is None:
            await ctx.send(embed=embeds.error_embed(
                f"Couldn't find that food. Check `{ctx.prefix}inventory` for what you own."
            ))
            return

        result = await self.db.feed_pet(ctx.author.id, ctx.guild.id, food_id, qty)
        if not result["success"]:
            reasons = {
                "not_found": "That food doesn't exist.",
                "no_pet_equipped": f"You don't have a pet equipped. `{ctx.prefix}equip <name>` first.",
                "not_owned": f"You don't have enough of that. Buy some with `{ctx.prefix}buyfood`.",
            }
            await ctx.send(embed=embeds.error_embed(reasons.get(result["reason"], "Feeding failed.")))
            return

        f = food_catalog.FOODS[food_id]
        qty_text = f" \u00D7{result['qty']}" if result["qty"] > 1 else ""
        total_xp = f["xp"] * result["qty"]

        embed = embeds.base_embed(
            title="\U0001F37D\uFE0F Fed!",
            description=f"**{result['nickname']}** ate **{f['name']}**{qty_text} and gained **{total_xp:,} XP**!",
            color=embeds.COLOR_SUCCESS,
        )
        if result["evolved"]:
            embed.add_field(
                name="\u2728 Evolved!",
                value=f"{result['old_stage']['name']} \u2192 **{result['new_stage']['name']}**!",
                inline=False,
            )
        elif result["leveled_up"]:
            embed.add_field(
                name="\U0001F389 Level Up!",
                value=f"Level {result['old_level']} \u2192 **Level {result['new_level']}**",
                inline=False,
            )
        embed.set_thumbnail(url=result["new_stage"]["sprite"])
        log.info(
            f"PET FEED      | {ctx.author} ({ctx.author.id}) fed '{food_id}' x{result['qty']} "
            f"to '{result['species_id']}' in guild {ctx.guild.id}"
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # .sellfood
    # ------------------------------------------------------------------ #
    @commands.command(name="sellfood")
    @commands.guild_only()
    async def sellfood_cmd(self, ctx: commands.Context, *, item: str) -> None:
        """Sell owned food back for half its price: `.sellfood <name> [quantity]`."""
        food_id, qty = self._parse_food_arg(item)
        if food_id is None:
            await ctx.send(embed=embeds.error_embed(
                f"Couldn't find that food. Check `{ctx.prefix}inventory` for what you own."
            ))
            return

        result = await self.db.sell_food(ctx.author.id, ctx.guild.id, food_id, qty)
        if not result["success"]:
            reasons = {
                "not_found": "That food doesn't exist.",
                "not_owned": "You don't own that much of it.",
            }
            await ctx.send(embed=embeds.error_embed(reasons.get(result["reason"], "Sale failed.")))
            return

        f = food_catalog.FOODS[food_id]
        qty_text = f" \u00D7{result['qty']}" if result["qty"] > 1 else ""
        await ctx.send(embed=embeds.success_embed(
            "Sold!",
            f"Sold **{f['name']}**{qty_text} for **{result['refund']:,} coins**. "
            f"New balance: {result['new_balance']:,} coins.",
        ))

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_food_arg(text: str) -> tuple[Optional[str], int]:
        """Parse "<food name> [qty]" the same way cogs/economy.py's
        `.buy` parses "<item> [qty]" - a trailing integer is treated as
        a quantity if what remains still resolves to a food."""
        text = text.strip()
        qty = 1
        tokens = text.split()
        if len(tokens) > 1 and tokens[-1].isdigit():
            candidate_qty = int(tokens[-1])
            candidate_text = " ".join(tokens[:-1])
            if candidate_qty > 0 and food_catalog.resolve_food(candidate_text) is not None:
                text = candidate_text
                qty = candidate_qty
        return food_catalog.resolve_food(text), qty

    @petshop_cmd.error
    @buypet_cmd.error
    @pets_cmd.error
    @pet_cmd.error
    @equip_cmd.error
    @nickname_cmd.error
    @foodshop_cmd.error
    @buyfood_cmd.error
    @feed_cmd.error
    @sellfood_cmd.error
    async def pets_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        usage = {
            "buypet": f"`{ctx.prefix}buypet <pet name>`",
            "equip": f"`{ctx.prefix}equip <pet name>`",
            "nickname": f"`{ctx.prefix}nickname <current name> <new nickname>` (quote multi-word current names)",
            "buyfood": f"`{ctx.prefix}buyfood <food name> [quantity]`",
            "feed": f"`{ctx.prefix}feed <food name> [quantity]`",
            "sellfood": f"`{ctx.prefix}sellfood <food name> [quantity]`",
        }
        if isinstance(error, commands.MissingRequiredArgument):
            hint = usage.get(ctx.command.name, f"`{ctx.prefix}{ctx.command.name}`")
            await ctx.send(embed=embeds.error_embed(f"Usage: {hint}"))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Pets(bot))
