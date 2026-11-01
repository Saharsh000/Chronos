"""JEE Theory Trivia command (`.trivia` / `,trivia`) powered by CJA (Chronos JEE API).

Supports:
- `,trivia`: Interactive JEE Trivia Hub & Syllabus Explorer (All 89 Chapters, 737 Topics)
- `,trivia r`: Instant random question across all subjects
- `,trivia p/c/m`: Interactive Section & Chapter selector for Physics, Chem, Maths
- `,trivia <chapter>` (e.g. `,trivia goc`, `,trivia emi`, `,trivia p&c`): Direct chapter lookup & topic selection
- `,trivia lb`: Server trivia leaderboard
- `,trivia me`: Personal trivia performance stats
- 10-second cooldown between trivia question starts
- Dynamic coin rewards, XP grants, Halloween Candy drops, and streak tracking
- Interactive Discord UI (Buttons for Single/Match/Assertion-Reason, Multi-Select for Multiple Correct, Modals for Integers)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Optional

import discord
from discord.ext import commands

import config
from services.cja import (
    CJAError,
    cja_client,
    find_chapter,
    get_chapter_by_id,
    get_chapters_by_section,
    get_sections,
    get_subject_data,
    get_subjects,
)
from utils import embeds
from utils import halloween as halloween_catalog
from utils.time_format import format_duration

log = logging.getLogger("trivia")

# Subject name mapping
SUBJECT_MAP = {
    "p": "physics",
    "physics": "physics",
    "phys": "physics",
    "c": "chemistry",
    "chem": "chemistry",
    "chemistry": "chemistry",
    "m": "mathematics",
    "math": "mathematics",
    "maths": "mathematics",
}

SUBJECT_COLORS = {
    "physics": 0x38BDF8,       # Sky Blue
    "chemistry": 0x34D399,     # Emerald Green
    "mathematics": 0xF59E0B,   # Amber Gold
}

SUBJECT_EMOJIS = {
    "physics": "⚛️",
    "chemistry": "🧪",
    "mathematics": "📐",
}

SECTION_EMOJIS = {
    # Physics
    "General Physics": "📏",
    "Mechanics": "🚗",
    "Properties of Matter": "💧",
    "Thermal Physics": "🌡️",
    "Oscillations and Waves": "🌊",
    "Electricity and Magnetism": "⚡",
    "Optics": "🔭",
    "Modern Physics": "⚛️",
    "Experimental Skills": "🔬",
    # Chemistry
    "Physical Chemistry": "⚗️",
    "Inorganic Chemistry": "🧱",
    "Organic Chemistry": "🧪",
    # Mathematics
    "Algebra": "🔢",
    "Calculus": "📈",
    "Coordinate Geometry": "📐",
    "Vectors and 3D Geometry": "🧭",
    "Statistics and Probability": "📊",
    "Trigonometry": "📏",
}


class TriviaIntegerModal(discord.ui.Modal, title="Submit Integer Answer"):
    """Modal dialog for integer-type JEE questions."""

    answer_input = discord.ui.TextInput(
        label="Enter Integer Answer",
        placeholder="e.g. 4",
        required=True,
        min_length=1,
        max_length=6,
    )

    def __init__(self, view: TriviaQuestionView) -> None:
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val_str = self.answer_input.value.strip()
        try:
            val_int = int(val_str)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid integer (e.g. `4` or `-2`).", ephemeral=True)
            return

        await self.view.handle_answer(interaction, val_int)


class TriviaQuestionView(discord.ui.View):
    """Interactive component view for handling user responses to trivia questions."""

    def __init__(
        self,
        bot: commands.Bot,
        question_data: dict[str, Any],
        author_id: int,
        guild_id: int,
        timeout_seconds: int = 60,
    ) -> None:
        super().__init__(timeout=timeout_seconds)
        self.bot = bot
        self.db = bot.db
        self.q = question_data
        self.author_id = author_id
        self.guild_id = guild_id
        self.q_id = question_data["id"]
        self.answered_users: set[int] = set()
        self.results_summary: list[dict[str, Any]] = []
        self.message: Optional[discord.Message] = None
        self._build_components()

    def _build_components(self) -> None:
        q_type = self.q.get("type", {}).get("id", "single")
        options = self.q.get("options", [])

        if q_type in ("single", "assertion_reason", "statements", "match"):
            for opt in options:
                btn = discord.ui.Button(
                    label=f"Option {opt['key']}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"cja:ans:{self.q_id}:{opt['key']}",
                )
                btn.callback = self._make_button_callback(opt["key"])
                self.add_item(btn)

        elif q_type == "multiple":
            select_options = [
                discord.SelectOption(
                    label=f"Option {opt['key']}",
                    value=opt["key"],
                    description=opt.get("text", "")[:95],
                )
                for opt in options
            ]
            if not select_options:
                select_options = [discord.SelectOption(label=f"Option {k}", value=k) for k in ["A", "B", "C", "D"]]

            select = discord.ui.Select(
                placeholder="Select one or more options (A, B, C, D)...",
                min_values=1,
                max_values=min(4, len(select_options)),
                options=select_options,
                custom_id=f"cja:multi:{self.q_id}",
            )
            select.callback = self._select_callback
            self.add_item(select)

        elif q_type == "integer":
            btn = discord.ui.Button(
                label="Submit Integer Answer",
                style=discord.ButtonStyle.success,
                emoji="🔢",
                custom_id=f"cja:int:{self.q_id}",
            )
            btn.callback = self._integer_callback
            self.add_item(btn)

    def _make_button_callback(self, key: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.handle_answer(interaction, key)
        return callback

    async def _select_callback(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if not values:
            await interaction.response.send_message("Please select at least one option.", ephemeral=True)
            return
        ans_str = ",".join(sorted(values))
        await self.handle_answer(interaction, ans_str)

    async def _integer_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id in self.answered_users:
            await interaction.response.send_message("You have already answered this question!", ephemeral=True)
            return
        modal = TriviaIntegerModal(self)
        await interaction.response.send_modal(modal)

    async def handle_answer(self, interaction: discord.Interaction, answer_val: str | int) -> None:
        user = interaction.user
        if user.id in self.answered_users:
            await interaction.response.send_message("❌ You have already submitted an answer for this round!", ephemeral=True)
            return

        self.answered_users.add(user.id)
        await interaction.response.defer(ephemeral=True)

        try:
            check_res = await cja_client.check_answer(self.q_id, answer_val)
        except Exception as e:
            log.error(f"Error checking answer with CJA: {e}", exc_info=True)
            await interaction.followup.send("⚠️ Error verifying your answer with CJA. Please try again later.", ephemeral=True)
            return

        is_correct = bool(check_res.get("correct", False))
        marks = int(check_res.get("marks", 4 if is_correct else -1))
        official_ans = check_res.get("answer", {}).get("display", "N/A")
        explanation = check_res.get("explanation", "No explanation available.")

        # Currency & XP calculations
        coins_won = 0
        xp_won = 0
        if is_correct:
            coins_won = random.randint(40, 80)
            xp_won = random.randint(25, 50)
            if self.q.get("exam", {}).get("id") == "advanced":
                coins_won += random.randint(20, 40)
                xp_won += 20
        else:
            coins_won = 5
            xp_won = 5

        # Update Database
        stats = await self.db.record_trivia_attempt(
            user_id=user.id,
            guild_id=self.guild_id,
            correct=is_correct,
            marks=marks,
            coins_won=coins_won,
        )

        if coins_won > 0:
            await self.db.add_coins(user.id, coins_won)
        if xp_won > 0:
            await self.db.add_xp(user.id, self.guild_id, xp_won)

        # Halloween candy drop
        candy_str = ""
        if is_correct and random.random() < 0.35:
            dropped_candy = halloween_catalog.pick_random_candy()
            await self.db.add_halloween_candy(user.id, dropped_candy["id"], 1)
            candy_str = f"\n🎃 **Bonus Drop:** Found 1x {dropped_candy['emoji']} **{dropped_candy['name']}**!"

        self.results_summary.append({
            "user": user,
            "correct": is_correct,
            "marks": marks,
            "coins": coins_won,
            "xp": xp_won,
            "streak": stats["current_streak"],
        })

        # Send personalized feedback to the user
        if is_correct:
            result_embed = embeds.base_embed(
                title=f"🎉 Correct Answer! (+{marks} Marks)",
                description=(
                    f"**Official Answer:** `{official_ans}`\n\n"
                    f"💡 **Explanation:** {explanation}\n\n"
                    f"💰 **Rewards:** +{coins_won} Coins · +{xp_won} XP\n"
                    f"🔥 **Streak:** {stats['current_streak']} in a row (Best: {stats['best_streak']}){candy_str}"
                ),
                color=embeds.COLOR_SUCCESS,
            )
        else:
            result_embed = embeds.base_embed(
                title=f"❌ Incorrect Answer ({marks:+} Marks)",
                description=(
                    f"**Official Answer:** `{official_ans}`\n\n"
                    f"💡 **Explanation:** {explanation}\n\n"
                    f"Consolation: +{coins_won} Coins · +{xp_won} XP · Streak reset to 0."
                ),
                color=embeds.COLOR_ERROR,
            )

        await interaction.followup.send(embed=result_embed, ephemeral=True)

        # If author answered or 3 users answered, end early
        if user.id == self.author_id or len(self.answered_users) >= 3:
            self.stop()
            await self.conclude_round()

    async def on_timeout(self) -> None:
        await self.conclude_round()

    async def conclude_round(self) -> None:
        """Edit the message to show the finalized answer, explanation, and results."""
        for item in self.children:
            item.disabled = True

        if not self.message:
            return

        # Fetch official answer from CJA
        try:
            full_check = await cja_client.check_answer(self.q_id, "NONE")
            official_ans = full_check.get("answer", {}).get("display", "N/A")
            explanation = full_check.get("explanation", "")
            concept = full_check.get("concept", "")
        except Exception:
            official_ans = "Revealed"
            explanation = "Round ended."
            concept = ""

        # Update Embed
        subj_info = self.q.get("subject", {})
        color = SUBJECT_COLORS.get(subj_info.get("id"), 0x38BDF8)
        embed = embeds.base_embed(
            title=f"🏁 Trivia Round Concluded · {subj_info.get('name', 'JEE')}",
            description=(
                f"### {self.q.get('question', '')}\n\n"
                f"✅ **Correct Answer:** `{official_ans}`\n\n"
                f"💡 **Concept:** *{concept}*\n"
                f"📖 **Explanation:** {explanation}"
            ),
            color=color,
        )

        if self.results_summary:
            summary_lines = []
            for r in self.results_summary:
                status = "✅" if r["correct"] else "❌"
                summary_lines.append(f"{status} **{r['user'].display_name}**: `{r['marks']:+} Marks` (+{r['coins']} coins)")
            embed.add_field(name="👥 Round Results", value="\n".join(summary_lines), inline=False)
        else:
            embed.add_field(name="⏰ Time Expired", value="Nobody submitted an answer before the timer ran out.", inline=False)

        embeds.set_footer(embed, "Use ,trivia r for another question | ,trivia lb for leaderboard")

        try:
            await self.message.edit(embed=embed, view=self)
        except Exception as e:
            log.warning(f"Failed to edit trivia message on conclusion: {e}")


# ====================================================================== #
# 2. Interactive Navigation Views (Hub, Chapter Browser, Topic Selector)  #
# ====================================================================== #

class TriviaHubView(discord.ui.View):
    """Main interactive Hub for exploring all 89 chapters and 737 topics."""

    def __init__(self, bot: commands.Bot, ctx: commands.Context) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.message: Optional[discord.Message] = None
        self._build_components()

    def _build_components(self) -> None:
        # Row 0: Subject Buttons
        phys_btn = discord.ui.Button(
            label="⚛️ Physics (29 Ch)",
            style=discord.ButtonStyle.primary,
            row=0,
        )
        phys_btn.callback = lambda i: self._subject_callback(i, "physics")
        self.add_item(phys_btn)

        chem_btn = discord.ui.Button(
            label="🧪 Chemistry (34 Ch)",
            style=discord.ButtonStyle.success,
            row=0,
        )
        chem_btn.callback = lambda i: self._subject_callback(i, "chemistry")
        self.add_item(chem_btn)

        math_btn = discord.ui.Button(
            label="📐 Mathematics (26 Ch)",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        math_btn.callback = lambda i: self._subject_callback(i, "mathematics")
        self.add_item(math_btn)

        # Row 1: Actions
        rand_btn = discord.ui.Button(
            label="🎲 Instant Random Question",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        rand_btn.callback = self._random_callback
        self.add_item(rand_btn)

        stats_btn = discord.ui.Button(
            label="📊 My Stats",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        stats_btn.callback = self._stats_callback
        self.add_item(stats_btn)

        lb_btn = discord.ui.Button(
            label="🏆 Leaderboard",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        lb_btn.callback = self._lb_callback
        self.add_item(lb_btn)

    async def _subject_callback(self, interaction: discord.Interaction, subject: str) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._show_chapter_browser(self.ctx, subject=subject, edit_msg=self.message)

    async def _random_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if not trivia_cog or not trivia_cog._check_cooldown(self.ctx):
            await interaction.response.send_message("⏳ Please wait for your 10-second cooldown.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        await trivia_cog._start_question(self.ctx, edit_msg=self.message)

    async def _stats_callback(self, interaction: discord.Interaction) -> None:
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._send_user_stats(self.ctx)

    async def _lb_callback(self, interaction: discord.Interaction) -> None:
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._send_leaderboard(self.ctx)


class TriviaChapterBrowserView(discord.ui.View):
    """Section and Chapter explorer for a selected subject."""

    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        subject: str,
        selected_section: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.subject = subject
        self.sections = get_sections(subject)
        self.selected_section = selected_section or (self.sections[0] if self.sections else None)
        self.message: Optional[discord.Message] = None
        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()

        # 1. Section Select Menu
        if self.sections:
            sec_opts = []
            for sec in self.sections:
                sec_emoji = SECTION_EMOJIS.get(sec, "📚")
                chs = get_chapters_by_section(self.subject, sec)
                sec_opts.append(
                    discord.SelectOption(
                        label=sec[:95],
                        value=sec,
                        description=f"{len(chs)} Chapters in this unit",
                        emoji=sec_emoji,
                        default=(sec == self.selected_section),
                    )
                )
            sec_select = discord.ui.Select(
                placeholder=f"Choose a {self.subject.capitalize()} Section/Unit...",
                options=sec_opts[:25],
                row=0,
            )
            sec_select.callback = self._section_select_callback
            self.add_item(sec_select)

        # 2. Chapter Select Menu (for currently selected section)
        if self.selected_section:
            chs = get_chapters_by_section(self.subject, self.selected_section)
            if chs:
                ch_opts = []
                for ch in chs:
                    topic_count = len(ch.get("topics", []))
                    exams_str = " · ".join(e.upper() for e in ch.get("exams", []))
                    ch_opts.append(
                        discord.SelectOption(
                            label=ch["name"][:95],
                            value=ch["id"],
                            description=f"{topic_count} Topics · Exams: {exams_str}"[:100],
                        )
                    )
                ch_select = discord.ui.Select(
                    placeholder=f"Select a chapter from {self.selected_section[:30]}...",
                    options=ch_opts[:25],
                    row=1,
                )
                ch_select.callback = self._chapter_select_callback
                self.add_item(ch_select)

        # 3. Action Buttons (Row 2)
        rand_sec_btn = discord.ui.Button(
            label=f"🎲 Random in {self.selected_section[:18]}",
            style=discord.ButtonStyle.success,
            row=2,
        )
        rand_sec_btn.callback = self._random_section_callback
        self.add_item(rand_sec_btn)

        rand_sub_btn = discord.ui.Button(
            label=f"⚡ Any {self.subject.capitalize()}",
            style=discord.ButtonStyle.primary,
            row=2,
        )
        rand_sub_btn.callback = self._random_subject_callback
        self.add_item(rand_sub_btn)

        back_btn = discord.ui.Button(
            label="↩️ Back to Hub",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        back_btn.callback = self._back_hub_callback
        self.add_item(back_btn)

    async def _section_select_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        selected = interaction.data.get("values", [None])[0]
        if selected:
            self.selected_section = selected
            self._build_components()
            trivia_cog: Trivia = self.bot.get_cog("Trivia")
            if trivia_cog:
                embed = trivia_cog._make_browser_embed(self.subject, self.selected_section)
                await interaction.response.edit_message(embed=embed, view=self)

    async def _chapter_select_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        chapter_id = interaction.data.get("values", [None])[0]
        ch_data = get_chapter_by_id(chapter_id)
        if not ch_data:
            await interaction.response.send_message("Chapter not found.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._show_topic_menu(self.ctx, self.subject, ch_data, edit_msg=self.message)

    async def _random_section_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        chs = get_chapters_by_section(self.subject, self.selected_section)
        if not chs:
            await interaction.response.send_message("No chapters in this section.", ephemeral=True)
            return
        chosen_ch = random.choice(chs)
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if not trivia_cog or not trivia_cog._check_cooldown(self.ctx):
            await interaction.response.send_message("⏳ Please wait for your 10-second cooldown.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        await trivia_cog._start_question(self.ctx, subject=self.subject, chapter=chosen_ch["id"], edit_msg=self.message)

    async def _random_subject_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if not trivia_cog or not trivia_cog._check_cooldown(self.ctx):
            await interaction.response.send_message("⏳ Please wait for your 10-second cooldown.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        await trivia_cog._start_question(self.ctx, subject=self.subject, edit_msg=self.message)

    async def _back_hub_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._show_hub(self.ctx, edit_msg=self.message)


class TriviaTopicSelectView(discord.ui.View):
    """Chapter details and specific topic picker."""

    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        subject: str,
        chapter: dict[str, Any],
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.subject = subject
        self.chapter = chapter
        self.selected_topic_id: Optional[str] = None
        self.message: Optional[discord.Message] = None
        self._build_components()

    def _build_components(self) -> None:
        topics = self.chapter.get("topics", [])

        # 1. Topic Selector
        if topics:
            top_opts = [
                discord.SelectOption(
                    label="🎲 Any Topic in this Chapter",
                    value="all",
                    description="Questions will cover any topic in this chapter",
                    default=True,
                )
            ]
            for t in topics[:24]:
                exams_str = " · ".join(e.upper() for e in t.get("exams", []))
                top_opts.append(
                    discord.SelectOption(
                        label=t["name"][:95],
                        value=t["id"],
                        description=f"Exams: {exams_str}"[:100],
                    )
                )
            top_select = discord.ui.Select(
                placeholder="Choose a specific topic (or leave Any)...",
                options=top_opts,
                row=0,
            )
            top_select.callback = self._topic_select_callback
            self.add_item(top_select)

        # 2. Action Buttons
        start_btn = discord.ui.Button(
            label="▶️ Start Chapter Question",
            style=discord.ButtonStyle.success,
            emoji="🎯",
            row=1,
        )
        start_btn.callback = self._start_callback
        self.add_item(start_btn)

        back_btn = discord.ui.Button(
            label=f"↩️ Back to {self.chapter.get('section', 'Section')[:18]}",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back_btn.callback = self._back_callback
        self.add_item(back_btn)

    async def _topic_select_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        selected = interaction.data.get("values", [None])[0]
        self.selected_topic_id = None if selected == "all" else selected
        await interaction.response.send_message(
            f"✅ Target topic set to: **{self.selected_topic_id or 'Any in Chapter'}**.\nClick **Start Chapter Question** to begin!",
            ephemeral=True,
        )

    async def _start_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if not trivia_cog or not trivia_cog._check_cooldown(self.ctx):
            await interaction.response.send_message("⏳ Please wait for your 10-second cooldown.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        await trivia_cog._start_question(
            self.ctx,
            subject=self.subject,
            chapter=self.chapter["id"],
            topic=self.selected_topic_id,
            edit_msg=self.message,
        )

    async def _back_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._show_chapter_browser(
                self.ctx,
                subject=self.subject,
                selected_section=self.chapter.get("section"),
                edit_msg=self.message,
            )


# ====================================================================== #
# 3. Main Trivia Cog Class                                               #
# ====================================================================== #

class Trivia(commands.Cog, name="Trivia"):
    """JEE Theory Trivia command with instant prefix gameplay and full syllabus explorer."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.user_cooldowns: dict[int, float] = {}

    def _check_cooldown(self, ctx: commands.Context) -> bool:
        """Returns True if the user is off cooldown, False otherwise (and notifies user)."""
        now = time.time()
        last_time = self.user_cooldowns.get(ctx.author.id, 0)
        cooldown_dur = config.TRIVIA_COOLDOWN_SECONDS
        if now - last_time < cooldown_dur:
            rem = cooldown_dur - (now - last_time)
            asyncio.create_task(ctx.send(embed=embeds.info_embed(
                "⏳ Cooldown Active",
                f"You can start another trivia question in **{rem:.1f}s**.",
            )))
            return False
        self.user_cooldowns[ctx.author.id] = now
        return True

    @commands.command(name="trivia", aliases=["t", "jeequiz", "quiz"])
    @commands.guild_only()
    async def trivia_cmd(self, ctx: commands.Context, *, arg: Optional[str] = None) -> None:
        """Play rapid-fire JEE Theory Trivia powered by CJA.

        Usage:
        `,trivia` — Interactive Syllabus Browser Hub (all 89 chapters & 737 topics)
        `,trivia r` — Quick instant random question across all subjects
        `,trivia p` — Physics section & chapter browser (29 chapters)
        `,trivia c` — Chemistry section & chapter browser (34 chapters)
        `,trivia m` — Mathematics section & chapter browser (26 chapters)
        `,trivia <chapter>` (e.g. `,trivia goc`, `,trivia emi`, `,trivia p&c`) — Direct chapter lookup & topic selection
        `,trivia lb` — Server trivia leaderboard
        `,trivia me` — Your personal trivia statistics
        """
        sub = arg.strip().lower() if arg else None

        # 1. Leaderboard command
        if sub in ("lb", "leaderboard", "top"):
            await self._send_leaderboard(ctx)
            return

        # 2. Personal Stats command
        if sub in ("me", "stats", "profile"):
            await self._send_user_stats(ctx)
            return

        # 3. Main Hub (no arguments or hub/menu)
        if not sub or sub in ("hub", "menu", "all"):
            await self._show_hub(ctx)
            return

        # 4. Instant Random Question
        if sub in ("r", "rand", "random"):
            if not self._check_cooldown(ctx):
                return
            await self._start_question(ctx)
            return

        # 5. Subject shortcuts
        if sub in ("p", "physics", "phys"):
            await self._show_chapter_browser(ctx, "physics")
            return
        if sub in ("c", "chemistry", "chem"):
            await self._show_chapter_browser(ctx, "chemistry")
            return
        if sub in ("m", "mathematics", "math", "maths"):
            await self._show_chapter_browser(ctx, "mathematics")
            return

        # 6. Direct Chapter Search! (e.g. ,trivia goc, ,trivia emi, ,trivia thermodynamics)
        matched_sub, matched_ch = find_chapter(sub)
        if matched_ch and matched_sub:
            await self._show_topic_menu(ctx, matched_sub["id"], matched_ch)
            return

        # 7. Fallback to start random question
        if not self._check_cooldown(ctx):
            return
        await self._start_question(ctx)

    def _make_hub_embed(self) -> discord.Embed:
        embed = embeds.base_embed(
            title="🧠 Chronos JEE Theory Trivia Hub",
            description=(
                "Master JEE Main & JEE Advanced with 100% verified theory trivia questions powered by **CJA**!\n\n"
                "⚛️ **Physics** — `29 Chapters` · `260 Topics`\n"
                "🧪 **Chemistry** — `34 Chapters` · `311 Topics`\n"
                "📐 **Mathematics** — `26 Chapters` · `166 Topics`\n\n"
                "⚡ **89 Chapters** & **737 Topics** total · Official JEE Marking (`+4` / `-1`)\n"
                "💰 Earn coins & XP · ⏱️ 10-second cooldown between rounds\n\n"
                "👇 *Click a subject below to browse all chapters & topics, or click Instant Random!*"
            ),
            color=0x38BDF8,
        )
        embeds.set_footer(embed, "Tip: Use shortcuts like ,trivia goc or ,trivia emi to jump directly to any chapter!")
        return embed

    def _make_browser_embed(self, subject: str, selected_section: Optional[str]) -> discord.Embed:
        emoji = SUBJECT_EMOJIS.get(subject, "📚")
        color = SUBJECT_COLORS.get(subject, 0x38BDF8)
        sub_data = get_subject_data(subject) or {}
        all_chs = sub_data.get("chapters", [])
        total_topics = sum(len(c.get("topics", [])) for c in all_chs)

        chs_in_sec = get_chapters_by_section(subject, selected_section)
        ch_list_lines = []
        for i, ch in enumerate(chs_in_sec, 1):
            ch_list_lines.append(f"`{i:02d}.` **{ch['name']}** *({len(ch.get('topics', []))} topics)*")
        ch_preview = "\n".join(ch_list_lines) if ch_list_lines else "No chapters found."

        embed = embeds.base_embed(
            title=f"{emoji} {subject.capitalize()} Syllabus Browser",
            description=(
                f"**{len(all_chs)} Chapters** · **{total_topics} Topics** in {subject.capitalize()}.\n\n"
                f"📂 **Active Section:** `{selected_section}`\n"
                f"{ch_preview}\n\n"
                f"👇 *Pick a chapter from the dropdown below to select topics or start!*"
            ),
            color=color,
        )
        embeds.set_footer(embed, "Choose a section or chapter below, or click Random")
        return embed

    def _make_topic_embed(self, subject: str, chapter: dict[str, Any]) -> discord.Embed:
        emoji = SUBJECT_EMOJIS.get(subject, "📚")
        color = SUBJECT_COLORS.get(subject, 0x38BDF8)
        topics = chapter.get("topics", [])
        exams_str = " · ".join(e.upper() for e in chapter.get("exams", ["main", "advanced"]))

        topic_preview_lines = []
        for i, t in enumerate(topics[:8], 1):
            topic_preview_lines.append(f"• {t['name']}")
        if len(topics) > 8:
            topic_preview_lines.append(f"• *...and {len(topics) - 8} more topics in dropdown below*")

        topic_text = "\n".join(topic_preview_lines) if topic_preview_lines else "Full chapter coverage."

        embed = embeds.base_embed(
            title=f"{emoji} {chapter['name']} · {chapter.get('section', '')}",
            description=(
                f"**Subject:** {subject.capitalize()} · **Exams:** `{exams_str}`\n"
                f"**Official Topics Covered ({len(topics)} total):**\n"
                f"{topic_text}\n\n"
                f"🎯 *Select a specific topic from the dropdown below, or click **Start Chapter Question** to begin!*"
            ),
            color=color,
        )
        embeds.set_footer(embed, "100% JEE Theory Trivia · Official +4/-1 Marking")
        return embed

    async def _show_hub(self, ctx: commands.Context, edit_msg: Optional[discord.Message] = None) -> None:
        """Display the main interactive syllabus hub."""
        embed = self._make_hub_embed()
        view = TriviaHubView(self.bot, ctx)
        if edit_msg:
            try:
                await edit_msg.edit(embed=embed, view=view)
                view.message = edit_msg
                return
            except Exception:
                pass
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    async def _show_chapter_browser(
        self,
        ctx: commands.Context,
        subject: str,
        selected_section: Optional[str] = None,
        edit_msg: Optional[discord.Message] = None,
    ) -> None:
        """Display the section and chapter browser for a subject."""
        view = TriviaChapterBrowserView(self.bot, ctx, subject, selected_section)
        embed = self._make_browser_embed(subject, view.selected_section)
        if edit_msg:
            try:
                await edit_msg.edit(embed=embed, view=view)
                view.message = edit_msg
                return
            except Exception:
                pass
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    async def _show_topic_menu(
        self,
        ctx: commands.Context,
        subject: str,
        chapter: dict[str, Any],
        edit_msg: Optional[discord.Message] = None,
    ) -> None:
        """Display chapter details and topic selector."""
        embed = self._make_topic_embed(subject, chapter)
        view = TriviaTopicSelectView(self.bot, ctx, subject, chapter)
        if edit_msg:
            try:
                await edit_msg.edit(embed=embed, view=view)
                view.message = edit_msg
                return
            except Exception:
                pass
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    async def _start_question(
        self,
        ctx: commands.Context,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
        topic: Optional[str] = None,
        edit_msg: Optional[discord.Message] = None,
    ) -> None:
        """Fetch question from CJA and render the interactive question embed."""
        loading_embed = embeds.base_embed(
            title="🧠 Loading JEE Theory Question...",
            description="Fetching an official theory question from the Chronos JEE API...",
            color=embeds.COLOR_INFO,
        )

        if edit_msg:
            try:
                await edit_msg.edit(embed=loading_embed, view=None)
                msg = edit_msg
            except Exception:
                msg = await ctx.send(embed=loading_embed)
        else:
            msg = await ctx.send(embed=loading_embed)

        try:
            q_data = await cja_client.get_question(
                subject=subject,
                chapter=chapter,
                topic=topic,
                hide_answer=True,
                embed=True,
            )
        except CJAError as e:
            err_text = f"**CJA Error ({e.code})**: {e.message}"
            if e.suggestions:
                err_text += f"\nSuggestions: {', '.join(e.suggestions)}"
            await msg.edit(embed=embeds.error_embed(err_text))
            return
        except Exception as e:
            log.error(f"Unexpected error in trivia start: {e}", exc_info=True)
            await msg.edit(embed=embeds.error_embed("Could not load a trivia question at this moment. Please try again!"))
            return

        # Build Question Embed
        subj_info = q_data.get("subject", {})
        subj_name = subj_info.get("name", "JEE")
        subj_id = subj_info.get("id", "chemistry")
        color = SUBJECT_COLORS.get(subj_id, 0x38BDF8)
        emoji = SUBJECT_EMOJIS.get(subj_id, "🧠")
        exam_info = q_data.get("exam", {}).get("name", "JEE Main")
        exam_id = q_data.get("exam", {}).get("id", "main")
        chapter_name = q_data.get("chapter", {}).get("name", "General Theory")
        topic_name = q_data.get("topic", {}).get("name", "Concept Analysis")
        diff = q_data.get("difficulty", "medium").capitalize()
        q_type_name = q_data.get("type", {}).get("name", "Single Correct")
        instructions = q_data.get("type", {}).get("instructions", "Choose the correct option.")
        timeout_sec = config.TRIVIA_ADVANCED_TIME_LIMIT if exam_id == "advanced" else config.TRIVIA_MAIN_TIME_LIMIT

        options_text = []
        for opt in q_data.get("options", []):
            options_text.append(f"**`[{opt['key']}]`** {opt['text']}")
        options_block = "\n".join(options_text) if options_text else "*Integer type question: use the button below to submit.*"

        embed = embeds.base_embed(
            title=f"{emoji} {subj_name} Trivia · {exam_info}",
            description=(
                f"### {q_data.get('question', '')}\n\n"
                f"{options_block}\n\n"
                f"📌 *{instructions}*"
            ),
            color=color,
        )

        embed.add_field(name="📚 Chapter", value=f"`{chapter_name}`", inline=True)
        embed.add_field(name="🎯 Topic", value=f"`{topic_name}`", inline=True)
        embed.add_field(name="⚡ Details", value=f"{diff} · {q_type_name}", inline=True)

        embeds.set_footer(
            embed,
            f"⏱️ Time limit: {timeout_sec}s · Answer using the components below!",
        )

        view = TriviaQuestionView(
            bot=self.bot,
            question_data=q_data,
            author_id=ctx.author.id,
            guild_id=ctx.guild.id,
            timeout_seconds=timeout_sec,
        )

        await msg.edit(embed=embed, view=view)
        view.message = msg

    async def _send_leaderboard(self, ctx: commands.Context) -> None:
        """Display the server trivia leaderboard."""
        rows = await self.db.get_trivia_leaderboard(ctx.guild.id, limit=10)
        if not rows:
            await ctx.send(embed=embeds.info_embed(
                "🏆 Trivia Leaderboard",
                "No trivia matches have been recorded yet in this server! Be the first by typing `,trivia r`.",
            ))
            return

        embed = embeds.base_embed(
            title=f"🏆 JEE Trivia Leaderboard · {ctx.guild.name}",
            description="Top academic contenders ranked by official JEE marks earned in `,trivia`:",
            color=0xF59E0B,
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            medal = medals[i] if i < 3 else f"`#{i + 1}`"
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else f"User {row['user_id']}"
            acc = (row["questions_correct"] / row["questions_attempted"] * 100) if row["questions_attempted"] > 0 else 0
            lines.append(
                f"{medal} **{name}** — **{row['total_marks']:,} Marks**\n"
                f"   └ `{row['questions_correct']}/{row['questions_attempted']}` ({acc:.1f}%) · 🔥 Streak: `{row['current_streak']}` (Best: `{row['best_streak']}`) · 🪙 `{row['total_coins_won']:,}` won"
            )

        embed.add_field(name="Rankings", value="\n".join(lines), inline=False)
        embeds.set_footer(embed, f"{ctx.prefix}trivia r to play · {ctx.prefix}trivia me for your personal stats")
        await ctx.send(embed=embed)

    async def _send_user_stats(self, ctx: commands.Context) -> None:
        """Display personal trivia metrics for the author."""
        stats = await self.db.get_or_create_trivia_stats(ctx.author.id, ctx.guild.id)
        att = stats["questions_attempted"]
        cor = stats["questions_correct"]
        acc = (cor / att * 100) if att > 0 else 0

        embed = embeds.base_embed(
            title=f"📊 Trivia Stats · {ctx.author.display_name}",
            description="Your competitive JEE trivia performance record:",
            color=embeds.COLOR_SOCIAL,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        embed.add_field(name="🎯 Accuracy", value=f"**{acc:.1f}%** ({cor}/{att} correct)", inline=True)
        embed.add_field(name="📈 Total Marks", value=f"**{stats['total_marks']:,}** Marks", inline=True)
        embed.add_field(name="💰 Coins Won", value=f"**+{stats['total_coins_won']:,}** 🪙", inline=True)
        embed.add_field(name="🔥 Current Streak", value=f"**{stats['current_streak']}** in a row", inline=True)
        embed.add_field(name="⚡ Best Streak", value=f"**{stats['best_streak']}** all-time", inline=True)
        embed.add_field(
            name="⏱️ Status",
            value="Ready to grind!" if time.time() - self.user_cooldowns.get(ctx.author.id, 0) >= config.TRIVIA_COOLDOWN_SECONDS else "On cooldown",
            inline=True,
        )

        embeds.set_footer(embed, f"Use {ctx.prefix}trivia r to start a new question")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Trivia(bot))
