"""cogs/lab.py - Chronos DLC: The Lab + Compound Synthesis.

Provides:
  - `,lab [unlock]`: The Lab hub, unlock progress, and element inventory
  - `,synth <name or formula>`: Craft organic compounds with interactive confirmation
  - `,compounds [category]`: Compendium of all 100 organic compounds with silhouettes & facts
"""
from __future__ import annotations

import difflib
import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from utils import embeds, emojis
from utils import achievements as ach_catalog
from utils import lab as lab_catalog
from utils.views import ChronosView
from web import mirror

log = logging.getLogger("cogs.lab")


def _format_progress_bar(current: float, target: float, length: int = 12) -> str:
    pct = min(1.0, max(0.0, current / target)) if target > 0 else 1.0
    filled = int(round(length * pct))
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {int(pct * 100)}%"


class ConfirmLabUnlockView(ChronosView):
    def __init__(self, cog: Lab, ctx: commands.Context):
        super().__init__(ctx.author.id, timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.confirmed = False

    @discord.ui.button(label="Unlock The Lab (60,000 Coins)", style=discord.ButtonStyle.success, emoji="⚗️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        self.confirmed = True
        await interaction.response.defer()

        try:
            res = await self.cog.db.set_lab_unlock(self.ctx.author.id, self.ctx.guild.id)
            embed = embeds.base_embed(
                title="🎉 The Lab Unlocked!",
                description=(
                    f"Welcome to **The Lab**, <@{self.ctx.author.id}>!\n\n"
                    f"⚗️ **Organic Chemistry Mode (`.start oc`)** is now unlocked!\n"
                    f"🧪 Earn elements (C, H, O, N, Cl, F, Br, I) live while studying Chemistry.\n"
                    f"🔬 Synthesize 100 syllabus compounds with `.synth <name or formula>`.\n"
                    f"📖 Track your collection with `.compounds`."
                ),
                color=embeds.COLOR_LEVELUP,
            )
            embeds.set_footer(embed, f"{self.ctx.prefix}start oc to begin your first OC session")
            await self.message.edit(embed=embed, view=None)

            # Check achievements
            unlocked = await self.cog.db.check_achievements(self.ctx.author.id, self.ctx.guild.id)
            if unlocked:
                await self.ctx.send(embed=embeds.achievement_unlock_embed(self.ctx.author, unlocked))

        except ValueError as ex:
            await self.message.edit(embed=embeds.error_embed(f"Could not unlock: {ex}"), view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.defer()
        await self.message.edit(content="Lab unlock cancelled.", embed=None, view=None)


class ConfirmSynthView(ChronosView):
    def __init__(self, cog: Lab, ctx: commands.Context, compound: dict[str, Any]):
        super().__init__(ctx.author.id, timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.compound = compound

    @discord.ui.button(label="Synthesize", style=discord.ButtonStyle.primary, emoji="⚗️")
    async def synth_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.defer()

        try:
            res = await self.cog.db.craft_compound(self.ctx.author.id, self.ctx.guild.id, self.compound["id"])
            await self.cog._handle_craft_success(self.ctx, self.message, res)
        except ValueError as ex:
            await self.message.edit(embed=embeds.error_embed(f"Synthesis failed: {ex}"), view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.defer()
        await self.message.edit(content="Synthesis cancelled.", embed=None, view=None)


class CompendiumPaginationView(ChronosView):
    def __init__(self, ctx: commands.Context, embeds_list: list[discord.Embed]):
        super().__init__(ctx.author.id, timeout=120.0)
        self.ctx = ctx
        self.embeds_list = embeds_list
        self.page = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = (self.page == 0)
        self.next_btn.disabled = (self.page >= len(self.embeds_list) - 1)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.embeds_list[self.page], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < len(self.embeds_list) - 1:
            self.page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.embeds_list[self.page], view=self)


class Lab(commands.Cog, name="The Lab"):
    """Chronos DLC: The Lab, Organic Chemistry mode, and Molecular Synthesis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ------------------------------------------------------------------ #
    # Announcements Mirror helper
    # ------------------------------------------------------------------ #
    async def _mirror_to_checkin(self, embed: discord.Embed, guild_id: int) -> None:
        """Proactively post an announcement to the server's check-in channel."""
        try:
            cfg = await self.db.get_guild_config(guild_id)
            cid = cfg.get("checkin_channel_id") if cfg else None
            if cid:
                channel = self.bot.get_channel(cid)
                if channel:
                    await channel.send(embed=embed)
        except Exception:
            log.exception("Failed to mirror lab announcement to check-in channel")

    # ------------------------------------------------------------------ #
    # ,lab Hub Command
    # ------------------------------------------------------------------ #
    @commands.group(name="lab", invoke_without_command=True)
    @commands.guild_only()
    async def lab_cmd(self, ctx: commands.Context) -> None:
        """The Lab central hub. View unlock progress, element stores, and collection counts."""
        unlock = await self.db.get_lab_unlock(ctx.author.id, ctx.guild.id)
        if not unlock:
            # Locked Screen
            chem_hours = await self.db.get_lab_chemistry_hours(ctx.author.id, ctx.guild.id)
            curr = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)

            chem_bar = _format_progress_bar(chem_hours, lab_catalog.LAB_CHEMISTRY_HOURS_REQUIRED)
            coin_bar = _format_progress_bar(curr["coins"], lab_catalog.LAB_UNLOCK_PRICE)

            embed = embeds.base_embed(
                title="🔒 The Lab (Locked)",
                description=(
                    "**The Lab** is a high-level mastery unlock for dedicated chemistry students.\n\n"
                    "**Unlocks:**\n"
                    "• Organic Chemistry study track (`.start oc`)\n"
                    "• Live element harvesting (C, H, O, N, Cl, F, Br, I)\n"
                    "• 100 JEE Organic Compound synthesis & compendium (`.synth`, `.compounds`)\n"
                    "• Collectible titles, badges, and milestone rewards\n\n"
                    "**Requirements:**"
                ),
                color=embeds.COLOR_STUDY,
            )
            embed.add_field(
                name="🧪 Chemistry Study Time",
                value=f"{chem_bar}\n**{chem_hours:.1f}h / {lab_catalog.LAB_CHEMISTRY_HOURS_REQUIRED:.1f}h**",
                inline=False,
            )
            embed.add_field(
                name="💰 Chronocoins",
                value=f"{coin_bar}\n**{curr['coins']:,} / {lab_catalog.LAB_UNLOCK_PRICE:,}**",
                inline=False,
            )

            eligible = (
                chem_hours >= lab_catalog.LAB_CHEMISTRY_HOURS_REQUIRED
                and curr["coins"] >= lab_catalog.LAB_UNLOCK_PRICE
            )
            if eligible:
                embed.add_field(
                    name="✨ Ready to Unlock!",
                    value=f"You meet all requirements! Run `{ctx.prefix}lab unlock` to unlock now.",
                    inline=False,
                )
                view = ConfirmLabUnlockView(self, ctx)
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg
            else:
                embeds.set_footer(embed, f"{ctx.prefix}start chemistry to log more study time")
                await ctx.send(embed=embed)
            return

        # Unlocked Lab Hub
        elements = await self.db.get_lab_elements(ctx.author.id, ctx.guild.id)
        user_compounds = await self.db.get_lab_compounds(ctx.author.id, ctx.guild.id)
        daily = await self.db.get_lab_daily(ctx.author.id, ctx.guild.id)

        unique_count = len(user_compounds)
        total_crafted = sum(c["times_crafted"] for c in user_compounds.values())

        embed = embeds.base_embed(
            title="⚗️ The Lab — Organic Chemistry Hub",
            description=(
                f"Welcome back, Chemist <@{ctx.author.id}>!\n"
                f"Collection Progress: **{unique_count} / 100** unique compounds "
                f"({unique_count}%) · Total Synthesized: **{total_crafted}**"
            ),
            color=embeds.COLOR_STUDY,
        )

        # Element Inventory Field
        elem_lines = [
            f"`{e:2}` **{lab_catalog.ELEMENT_NAMES[e]:10}**: {elements.get(e, 0)}/{lab_catalog.ELEMENT_INVENTORY_CAP}"
            for e in lab_catalog.ELEMENT_LIST
        ]
        # Split into two columns
        mid = len(elem_lines) // 2
        embed.add_field(name="📦 Elements (Part 1)", value="\n".join(elem_lines[:mid]), inline=True)
        embed.add_field(name="📦 Elements (Part 2)", value="\n".join(elem_lines[mid:]), inline=True)

        # Category Progress summary
        cat_summaries = []
        for cat in lab_catalog.CATEGORIES:
            cat_all = [c for c in lab_catalog.COMPOUNDS if c["category"] == cat]
            crafted_in_cat = sum(1 for c in cat_all if c["id"] in user_compounds)
            status = "✅" if crafted_in_cat == len(cat_all) else f"{crafted_in_cat}/{len(cat_all)}"
            cat_summaries.append(f"• **{cat}**: {status}")

        embed.add_field(
            name="📚 Categories",
            value="\n".join(cat_summaries[:8]),
            inline=True,
        )
        embed.add_field(
            name="📚 Categories (cont.)",
            value="\n".join(cat_summaries[8:]),
            inline=True,
        )

        # Daily Repeat Coins
        embed.add_field(
            name="🪙 Daily Repeat Income",
            value=f"**{daily['repeat_coins']:,} / {lab_catalog.DAILY_REPEAT_COIN_CAP:,} coins** earned today (IST).",
            inline=False,
        )

        embeds.set_footer(
            embed,
            f"{ctx.prefix}synth <name> to craft · {ctx.prefix}compounds for compendium · {ctx.prefix}start oc to harvest",
        )
        await ctx.send(embed=embed)

    @lab_cmd.command(name="unlock")
    @commands.guild_only()
    async def lab_unlock_cmd(self, ctx: commands.Context) -> None:
        """Unlock The Lab for 60,000 Chronocoins after 30h of Chemistry study."""
        existing = await self.db.get_lab_unlock(ctx.author.id, ctx.guild.id)
        if existing:
            await ctx.send(embed=embeds.info_embed("Already Unlocked", "You have already unlocked The Lab!"))
            return

        chem_hours = await self.db.get_lab_chemistry_hours(ctx.author.id, ctx.guild.id)
        curr = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)

        if chem_hours < lab_catalog.LAB_CHEMISTRY_HOURS_REQUIRED or curr["coins"] < lab_catalog.LAB_UNLOCK_PRICE:
            await ctx.send(embed=embeds.error_embed(
                f"You do not meet the unlock requirements:\n"
                f"• Chemistry Study: **{chem_hours:.1f}h / {lab_catalog.LAB_CHEMISTRY_HOURS_REQUIRED:.1f}h**\n"
                f"• Chronocoins: **{curr['coins']:,} / {lab_catalog.LAB_UNLOCK_PRICE:,}**"
            ))
            return

        embed = embeds.base_embed(
            title="⚗️ Confirm Lab Unlock",
            description=(
                f"Are you ready to spend **60,000 Chronocoins** to permanently unlock **The Lab**?\n\n"
                f"Current balance: **{curr['coins']:,} Chronocoins**\n"
                f"Remaining after unlock: **{curr['coins'] - lab_catalog.LAB_UNLOCK_PRICE:,} Chronocoins**"
            ),
            color=embeds.COLOR_CONFIRM,
        )
        view = ConfirmLabUnlockView(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ------------------------------------------------------------------ #
    # ,synth Command
    # ------------------------------------------------------------------ #
    @commands.command(name="synth", aliases=["synthesize", "craft-compound", "craft"])
    @commands.guild_only()
    async def synth_cmd(self, ctx: commands.Context, *, query: Optional[str] = None) -> None:
        """Synthesize an organic compound using harvested elements.
        Usage: `.synth methane` or `.synth CH4`
        """
        unlock = await self.db.get_lab_unlock(ctx.author.id, ctx.guild.id)
        if not unlock:
            await ctx.send(embed=embeds.error_embed(
                f"The Lab is locked! Use `{ctx.prefix}lab` to view unlock requirements."
            ))
            return

        if not query or not query.strip():
            await ctx.send(embed=embeds.error_embed(
                f"Please specify a compound name or formula to synthesize!\n"
                f"Examples:\n"
                f"• `{ctx.prefix}synth methane`\n"
                f"• `{ctx.prefix}synth C6H6`\n"
                f"• `{ctx.prefix}synth ethanol`"
            ))
            return

        compound = self._resolve_compound(query.strip())
        if not compound:
            # Try fuzzy suggestions
            suggestions = difflib.get_close_matches(
                query.lower().strip(), list(lab_catalog.COMPOUND_BY_NAME.keys()), n=3, cutoff=0.5
            )
            sugg_str = f"\nDid you mean: {', '.join(suggestions)}?" if suggestions else ""
            await ctx.send(embed=embeds.error_embed(
                f"Unknown compound `{query}`.{sugg_str}\n"
                f"Use `{ctx.prefix}compounds` to browse all 100 synthesizable compounds."
            ))
            return

        inv = await self.db.get_lab_elements(ctx.author.id, ctx.guild.id)
        reqs = compound["elements"]
        missing = []
        cost_parts = []
        for elem, needed in reqs.items():
            if needed > 0:
                have = inv.get(elem, 0)
                cost_parts.append(f"**{needed}** {elem} (have {have})")
                if have < needed:
                    missing.append(f"• **{elem}**: need {needed}, you only have {have}")

        if missing:
            await ctx.send(embed=embeds.error_embed(
                f"**Insufficient elements for {compound['name']} (`{compound['formula']}`):**\n"
                + "\n".join(missing)
                + f"\n\n*Study with `{ctx.prefix}start oc` to harvest more atoms!*"
            ))
            return

        # Check first-time vs repeat
        existing = await self.db.get_lab_compound(ctx.author.id, ctx.guild.id, compound["id"])
        is_first = (existing is None or existing["times_crafted"] == 0)

        if is_first:
            first_coins = lab_catalog.reward_coins_first(compound)
            first_xp = lab_catalog.reward_xp_first(compound)
            reward_desc = f"+{first_coins} Chronocoins · +{first_xp} XP (First-time Synthesis Bonus)"
        else:
            rep_coins = lab_catalog.reward_coins_repeat(compound)
            rep_xp = lab_catalog.reward_xp_repeat(compound)
            reward_desc = f"+{rep_coins} Chronocoins · +{rep_xp} XP (Repeat Craft)"

        embed = embeds.base_embed(
            title=f"⚗️ Synthesize: {compound['name']} ({compound['formula']})",
            description=(
                f"**Category:** {compound['category']}\n"
                f"**Fact:** *\"{compound['fact']}\"*\n\n"
                f"**Element Cost:**\n" + " · ".join(cost_parts) + "\n\n"
                f"**Expected Reward:**\n{reward_desc}"
            ),
            color=embeds.COLOR_CONFIRM,
        )
        embeds.set_footer(embed, "Click 'Synthesize' to confirm and consume elements")
        view = ConfirmSynthView(self, ctx, compound)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    def _resolve_compound(self, q: str) -> Optional[dict[str, Any]]:
        clean_id = q.lower().strip().replace(" ", "-")
        if clean_id in lab_catalog.COMPOUND_BY_ID:
            return lab_catalog.COMPOUND_BY_ID[clean_id]

        clean_name = q.lower().strip()
        if clean_name in lab_catalog.COMPOUND_BY_NAME:
            return lab_catalog.COMPOUND_BY_NAME[clean_name]

        # Check by formula
        f_key = q.upper().strip()
        if f_key in lab_catalog.COMPOUND_BY_FORMULA:
            return lab_catalog.COMPOUND_BY_FORMULA[f_key][0]

        # Fuzzy match name
        matches = difflib.get_close_matches(clean_name, list(lab_catalog.COMPOUND_BY_NAME.keys()), n=1, cutoff=0.75)
        if matches:
            return lab_catalog.COMPOUND_BY_NAME[matches[0]]

        return None

    async def _handle_craft_success(self, ctx: commands.Context, msg: discord.Message, res: dict[str, Any]) -> None:
        c = res["compound"]
        desc_lines = [
            f"Successfully synthesized **{c['name']}** (`{c['formula']}`)!",
            f"*\"{c['fact']}\"*",
            "",
            f"**Rewards Received:**",
            f"• **+{res['coins_earned']}** Chronocoins",
            f"• **+{res['xp_earned']}** XP",
        ]

        if res["is_discoverer"]:
            desc_lines.append(f"\n🌟 **SERVER FIRST DISCOVERY!** You are the first to discover {c['name']}!")

        if res["newly_completed_category"]:
            desc_lines.append(
                f"\n🏆 **CATEGORY COMPLETE: {res['category']}!**\n"
                f"Bonus: **+1,000 Chronocoins** and Unlocked Title: **{res['category_title']}**!"
            )

        if res["milestone_reward"]:
            ms = res["milestone_reward"]
            desc_lines.append(f"\n🎉 **COLLECTION MILESTONE ({ms['count']} Compounds)!**\nReward: {ms['description']}")

        if res["repeat_cap_reached"]:
            desc_lines.append("\n⚠️ *Daily repeat synthesis coin cap reached (1,000 coins/day).*")

        embed = embeds.base_embed(
            title=f"✅ Synthesis Complete: {c['name']} ({c['formula']})",
            description="\n".join(desc_lines),
            color=embeds.COLOR_SUCCESS,
        )
        embeds.set_footer(embed, f"Times crafted: {res['times_crafted']} · Total unique: {res['unique_compounds_count']}/100")
        await msg.edit(embed=embed, view=None)

        # Mirror Proactive Announcements to check-in channel
        member_dict = {"name": ctx.author.display_name, "avatar": ctx.author.display_avatar.url}
        if res["is_discoverer"]:
            disc_embed = mirror.lab_discovery_embed(member_dict, ctx.author.id, c)
            await self._mirror_to_checkin(disc_embed, ctx.guild.id)

        if res["newly_completed_category"]:
            cat_embed = mirror.lab_category_completed_embed(
                member_dict, ctx.author.id, res["category"], res["category_title"]
            )
            await self._mirror_to_checkin(cat_embed, ctx.guild.id)

        if res["milestone_reward"]:
            ms_embed = mirror.lab_milestone_embed(
                member_dict, ctx.author.id, res["milestone_reward"]["count"], res["milestone_reward"]["description"]
            )
            await self._mirror_to_checkin(ms_embed, ctx.guild.id)

        # Check achievements
        if res.get("new_achievements"):
            ach_unlocked = [ach_catalog.ACHIEVEMENTS_BY_ID[aid] for aid in res["new_achievements"] if aid in ach_catalog.ACHIEVEMENTS_BY_ID]
            if ach_unlocked:
                await ctx.send(embed=embeds.achievement_unlock_embed(ctx.author, ach_unlocked))

    # ------------------------------------------------------------------ #
    # ,compounds Compendium Command
    # ------------------------------------------------------------------ #
    @commands.command(name="compounds", aliases=["compendium", "comp"])
    @commands.guild_only()
    async def compounds_cmd(self, ctx: commands.Context, *, category: Optional[str] = None) -> None:
        """Browse the 100-compound Organic Chemistry Compendium.
        Usage: `.compounds` (overview) or `.compounds Alkanes`
        """
        user_compounds = await self.db.get_lab_compounds(ctx.author.id, ctx.guild.id)
        discoveries = await self.db.get_all_lab_discoveries(ctx.guild.id)

        if not category:
            # Overview of all categories
            embed = embeds.base_embed(
                title="📖 Organic Chemistry Compendium",
                description=(
                    f"Collection: **{len(user_compounds)} / 100** compounds discovered "
                    f"({len(user_compounds)}%)\n\n"
                    f"Select or specify a category to view individual entries:\n"
                    f"`{ctx.prefix}compounds <category>`"
                ),
                color=embeds.COLOR_STUDY,
            )

            for cat in lab_catalog.CATEGORIES:
                cat_all = [c for c in lab_catalog.COMPOUNDS if c["category"] == cat]
                discovered_count = sum(1 for c in cat_all if c["id"] in user_compounds)
                pct = int((discovered_count / len(cat_all)) * 100) if cat_all else 0
                badge = "🏆 " if discovered_count == len(cat_all) else ""
                embed.add_field(
                    name=f"{badge}{cat}",
                    value=f"**{discovered_count} / {len(cat_all)}** ({pct}%)\n`{ctx.prefix}compounds {cat}`",
                    inline=True,
                )

            embeds.set_footer(embed, f"Use {ctx.prefix}synth <name> to craft undiscovered compounds")
            await ctx.send(embed=embed)
            return

        # Specific category requested
        target_cat = None
        for cat in lab_catalog.CATEGORIES:
            if cat.lower() == category.lower().strip() or cat.lower().replace("-", " ") == category.lower().strip():
                target_cat = cat
                break

        if not target_cat:
            matches = difflib.get_close_matches(category.strip(), lab_catalog.CATEGORIES, n=1, cutoff=0.5)
            sugg = f" Did you mean `{matches[0]}`?" if matches else ""
            await ctx.send(embed=embeds.error_embed(
                f"Unknown category `{category}`.{sugg}\n"
                f"Available: {', '.join(lab_catalog.CATEGORIES)}"
            ))
            return

        cat_compounds = [c for c in lab_catalog.COMPOUNDS if c["category"] == target_cat]

        # Chunk compounds into pages of 5 per page for clean mobile display
        CHUNK_SIZE = 5
        chunks = [cat_compounds[i:i + CHUNK_SIZE] for i in range(0, len(cat_compounds), CHUNK_SIZE)]
        embeds_list = []

        total_pages = len(chunks)
        for page_idx, chunk in enumerate(chunks):
            e = embeds.base_embed(
                title=f"📖 Compendium: {target_cat} (Page {page_idx + 1}/{total_pages})",
                color=embeds.COLOR_STUDY,
            )
            for c in chunk:
                cid = c["id"]
                discovered = (cid in user_compounds)
                total_atoms = sum(c["elements"].values())

                if not discovered:
                    # Silhouette view
                    e.add_field(
                        name="❓ ???",
                        value=f"**Category:** {target_cat} · **Atoms:** {total_atoms}\n*Undiscovered — craft to reveal formula & fact.*",
                        inline=False,
                    )
                else:
                    # Discovered details
                    uc = user_compounds[cid]
                    disc_info = discoveries.get(cid)
                    first_mark = ""
                    if disc_info:
                        if disc_info["user_id"] == ctx.author.id:
                            first_mark = " · ⭐ *Discovered by YOU!*"
                        else:
                            first_mark = f" · 🌟 *Discovered by <@{disc_info['user_id']}>*"

                    formula_str = c["formula"]
                    condensed = c.get("smiles") or formula_str
                    e.add_field(
                        name=f"🧪 {c['name']} (`{formula_str}`)",
                        value=(
                            f"**Formula:** `{formula_str}` · **Structure:** `{condensed}`\n"
                            f"**Fact:** *\"{c['fact']}\"*\n"
                            f"**Times Crafted:** {uc['times_crafted']}{first_mark}"
                        ),
                        inline=False,
                    )
            embeds.set_footer(e, f"{ctx.prefix}synth <name> to synthesize")
            embeds_list.append(e)

        if len(embeds_list) == 1:
            await ctx.send(embed=embeds_list[0])
        else:
            view = CompendiumPaginationView(ctx, embeds_list)
            msg = await ctx.send(embed=embeds_list[0], view=view)
            view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Lab(bot))
