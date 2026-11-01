"""JEE Theory Trivia command (`.trivia` / `,trivia`) powered by CJA (Chronos JEE API).

Supports:
- `,trivia` / `,trivia r`: instant random question across all subjects
- `,trivia p/c/m`: interactive chapter selection & quick play for Physics, Chem, Maths
- `,trivia lb`: server trivia leaderboard
- `,trivia me`: personal trivia performance stats
- 10-second cooldown between trivia requests
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
from services.cja import CJAError, cja_client
from utils import embeds
from utils import halloween as halloween_catalog
from utils.time_format import format_duration

log = logging.getLogger("trivia")

# Subject name mapping
SUBJECT_MAP = {
    "r": None,
    "random": None,
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
            btn.callback = self._integer_button_callback
            self.add_item(btn)

    def _make_button_callback(self, choice: str):
        async def callback(interaction: discord.Interaction):
            await self.handle_answer(interaction, choice)
        return callback

    async def _select_callback(self, interaction: discord.Interaction) -> None:
        select = interaction.data.get("values", [])
        if not select:
            await interaction.response.send_message("Please select at least one option.", ephemeral=True)
            return
        ans_str = ",".join(sorted(select))
        await self.handle_answer(interaction, ans_str)

    async def _integer_button_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id in self.answered_users:
            await interaction.response.send_message("You have already answered this question!", ephemeral=True)
            return
        modal = TriviaIntegerModal(self)
        await interaction.response.send_modal(modal)

    async def handle_answer(self, interaction: discord.Interaction, answer_val: str | int) -> None:
        user_id = interaction.user.id
        if user_id in self.answered_users:
            if not interaction.response.is_done():
                await interaction.response.send_message("⚠️ You have already submitted an answer for this round!", ephemeral=True)
            return

        self.answered_users.add(user_id)
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            check_res = await cja_client.check_answer(self.q_id, answer_val)
        except CJAError as e:
            await interaction.followup.send(f"❌ Grading error: {e.message}", ephemeral=True)
            return
        except Exception:
            await interaction.followup.send("❌ Could not connect to the grading service. Please try again.", ephemeral=True)
            return

        is_correct = check_res.get("correct", False)
        marks = check_res.get("marks", 0)
        marking = check_res.get("marking", {"correct": 4, "incorrect": -1})
        diff = self.q.get("difficulty", "medium").lower()

        # Calculate coin payout
        base_coins = 50
        if diff == "easy":
            base_coins = 40
        elif diff == "medium":
            base_coins = 70
        elif diff == "hard":
            base_coins = 100

        exam_id = self.q.get("exam", {}).get("id", "main")
        if exam_id == "advanced":
            base_coins = int(base_coins * 1.3)

        coins_won = base_coins if is_correct else 0
        xp_gain = random.randint(20, 35) if is_correct else 5

        # Record in database
        trivia_stats = await self.db.record_trivia_attempt(
            user_id=user_id,
            guild_id=self.guild_id,
            correct=is_correct,
            marks=marks,
            coins_won=coins_won,
        )
        if xp_gain > 0:
            await self.db.grant_xp(user_id, self.guild_id, xp_gain)

        # Halloween Event treat chance
        extra_treat_msg = ""
        if is_correct and random.random() < 0.25:
            candy_drop = random.randint(5, 12)
            await self.db.add_candy(user_id, self.guild_id, candy_drop)
            extra_treat_msg = f"\n🍬 **+{candy_drop} Candy** earned!"

        # Send ephemeral feedback to the user
        streak_txt = f"🔥 Streak: **{trivia_stats['current_streak']}**" if is_correct else "Streak reset to 0."
        if is_correct:
            await interaction.followup.send(
                f"🎉 **Correct!** `+{marks} Marks`\n"
                f"💰 **+{coins_won} Coins** · 📈 **+{xp_gain} XP** · {streak_txt}{extra_treat_msg}",
                ephemeral=True,
            )
        else:
            neg_marks = marks if marks < 0 else marking.get("incorrect", -1)
            await interaction.followup.send(
                f"❌ **Incorrect!** `{neg_marks} Marks`\n"
                f"📈 **+{xp_gain} XP** for attempting · {streak_txt}",
                ephemeral=True,
            )

        self.results_summary.append({
            "user": interaction.user,
            "correct": is_correct,
            "marks": marks,
            "coins": coins_won,
        })

        # If author answered or round should end
        if user_id == self.author_id:
            await self.conclude_round(check_res)

    async def on_timeout(self) -> None:
        # Conclude round on timer expiration
        try:
            check_res = await cja_client.check_answer(self.q_id, "NONE")
        except Exception:
            check_res = {}
        await self.conclude_round(check_res)

    async def conclude_round(self, check_res: dict[str, Any]) -> None:
        self.stop()
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

        if not self.message:
            return

        # Build conclusion embed with full explanation & reveal
        subj_id = self.q.get("subject", {}).get("id", "chemistry")
        color = SUBJECT_COLORS.get(subj_id, 0x38BDF8)
        ans_info = check_res.get("answer", {})
        correct_display = ans_info.get("display") or ans_info.get("options", ["A"])[0] if ans_info.get("options") else "A"
        explanation = check_res.get("explanation") or "Standard conceptual question from the JEE syllabus."
        concept = check_res.get("concept") or self.q.get("topic", {}).get("name", "Core Theory")

        embed = embeds.base_embed(
            title=f"✅ Round Complete · {self.q.get('subject', {}).get('name', 'JEE')} Trivia",
            description=f"**Question:**\n> {self.q.get('question', '')}\n\n🎯 **Correct Answer:** **Option {correct_display}**",
            color=color,
        )

        embed.add_field(name="💡 Official Explanation", value=f"> {explanation}", inline=False)
        embed.add_field(name="🧬 Key Concept", value=f"`{concept}`", inline=True)
        embed.add_field(
            name="📚 Chapter",
            value=f"{self.q.get('chapter', {}).get('name', 'General')} ({self.q.get('exam', {}).get('name', 'JEE Main')})",
            inline=True,
        )

        # Leaderboard of round respondents
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


class TriviaSubjectSelectView(discord.ui.View):
    """Interactive view allowing the user to pick a chapter or quick-play in a subject."""

    def __init__(self, bot: commands.Bot, ctx: commands.Context, subject: str, chapters: list[dict[str, str]]) -> None:
        super().__init__(timeout=45)
        self.bot = bot
        self.ctx = ctx
        self.subject = subject
        self.chapters = chapters
        self.message: Optional[discord.Message] = None
        self._build_components()

    def _build_components(self) -> None:
        # Button: Quick Random in this Subject
        quick_btn = discord.ui.Button(
            label=f"🎲 Random {self.subject.capitalize()}",
            style=discord.ButtonStyle.success,
        )
        quick_btn.callback = self._quick_random_callback
        self.add_item(quick_btn)

        # Select Menu: Choose Chapter
        if self.chapters:
            select_opts = [
                discord.SelectOption(
                    label=ch["name"][:95],
                    value=ch["value"],
                )
                for ch in self.chapters[:25]
            ]
            select = discord.ui.Select(
                placeholder=f"Select a {self.subject.capitalize()} chapter...",
                options=select_opts,
            )
            select.callback = self._chapter_select_callback
            self.add_item(select)

    async def _quick_random_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._start_question(self.ctx, subject=self.subject, edit_msg=self.message)

    async def _chapter_select_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        chapter_val = interaction.data.get("values", [None])[0]
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._start_question(self.ctx, subject=self.subject, chapter=chapter_val, edit_msg=self.message)


class Trivia(commands.Cog, name="Trivia"):
    """JEE Theory Trivia command with instant prefix gameplay."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.user_cooldowns: dict[int, float] = {}

    @commands.command(name="trivia", aliases=["t", "jeequiz", "quiz"])
    @commands.guild_only()
    async def trivia_cmd(self, ctx: commands.Context, *, arg: Optional[str] = None) -> None:
        """Play rapid-fire JEE Theory Trivia powered by CJA.

        Usage:
        `,trivia` or `,trivia r` — Quick random question across all subjects
        `,trivia p` — Physics trivia (interactive chapter selector)
        `,trivia c` — Chemistry trivia (interactive chapter selector)
        `,trivia m` — Mathematics trivia (interactive chapter selector)
        `,trivia lb` — Server trivia leaderboard
        `,trivia me` — Your personal trivia statistics
        """
        sub = arg.strip().lower() if arg else "r"

        # Leaderboard command
        if sub in ("lb", "leaderboard", "top"):
            await self._send_leaderboard(ctx)
            return

        # Personal Stats command
        if sub in ("me", "stats", "profile"):
            await self._send_user_stats(ctx)
            return

        # Check 10-second grind cooldown
        now = time.time()
        last_time = self.user_cooldowns.get(ctx.author.id, 0)
        cooldown_dur = config.TRIVIA_COOLDOWN_SECONDS
        if now - last_time < cooldown_dur:
            rem = cooldown_dur - (now - last_time)
            await ctx.send(embed=embeds.info_embed(
                "⏳ Cooldown Active",
                f"You can start another trivia question in **{rem:.1f}s**.",
            ))
            return

        self.user_cooldowns[ctx.author.id] = now

        # Determine subject
        target_subject = SUBJECT_MAP.get(sub)
        if sub in ("p", "c", "m", "physics", "chemistry", "mathematics", "chem", "math", "maths"):
            # Show interactive chapter selector
            await self._show_subject_menu(ctx, target_subject)
            return

        # Random or immediate start
        await self._start_question(ctx, subject=target_subject)

    async def _show_subject_menu(self, ctx: commands.Context, subject: str) -> None:
        """Display an interactive chapter selector for the chosen subject."""
        try:
            chapters = await cja_client.autocomplete("chapter", subject=subject)
        except Exception:
            chapters = []

        emoji = SUBJECT_EMOJIS.get(subject, "📚")
        color = SUBJECT_COLORS.get(subject, 0x38BDF8)
        embed = embeds.base_embed(
            title=f"{emoji} {subject.capitalize()} Trivia Selection",
            description=(
                f"Choose a specific **{subject.capitalize()}** chapter below, or click **Random** to jump straight in!\n\n"
                f"⏱️ 10s cooldown between rounds · 💰 Payouts up to 100+ coins per question!"
            ),
            color=color,
        )
        embeds.set_footer(embed, "Pick from the menu below or click Random")

        view = TriviaSubjectSelectView(self.bot, ctx, subject, chapters)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    async def _start_question(
        self,
        ctx: commands.Context,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
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
