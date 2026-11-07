"""JEE Theory Trivia command (`.trivia` / `,trivia`) powered by CJA (Chronos JEE API).

Supports:
- `,trivia`: Interactive JEE Trivia Hub & Syllabus Explorer (All 89 Chapters, 737 Topics)
- `,trivia r`: Quick instant random question across all subjects (single-shot mode, stops after answer)
- `,trivia p/c/m`: Continuous study practice mode with section & chapter explorer
- `,trivia <chapter>` (e.g. `,trivia oscillations`, `,trivia goc`, `,trivia emi`): Direct chapter practice
- Continuous mode features:
  - `[▶️ Next Question]`: Seamlessly asks the next question in the active chapter/topic
  - `[🔀 Change Chapter / Topic]`: Switch to another chapter in the subject
  - `[📚 Change Subject]`: Switch between Physics, Chemistry, and Mathematics
  - `[🛑 Stop Trivia]`: Conclude study session with a comprehensive performance summary
- `,trivia lb`: Server trivia leaderboard
- `,trivia me`: Personal trivia performance stats
- 10-second cooldown between trivia question starts
- Official JEE Marking (+4 / -1) and dynamic Chronocoin & XP awards
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
import re
import time
from typing import Any, Optional

import discord
from discord.ext import commands

import config
from distexer.formatters.text import MODE_UNICODE_NATIVE, format_text
try:
    from distexer import arender_question_card
except ImportError:
    try:
        from distexer.renderer.engine import arender_question_card
    except ImportError:
        arender_question_card = None
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
from utils import emojis
from utils.time_format import format_duration
from utils.stats_card import render_leaderboard_card_sync

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

# Competitive JEE AIR Rank Ladder
TRIVIA_RANKS = [
    # (min_marks, title, emoji, badge, next_title)
    (300, "IIT Bombay CSE God", "👑", "AIR 1", None),
    (200, "Top 50 Ranker", "⚡", "AIR < 50", "IIT Bombay CSE God"),
    (120, "Top IITian", "💎", "AIR < 500", "Top 50 Ranker"),
    (70,  "Old IIT Topper", "🏆", "AIR < 2,500", "Top IITian"),
    (40,  "NIT TPG Star", "🥇", "AIR < 10,000", "Old IIT Topper"),
    (20,  "JEE Advanced Qualified", "🥈", "AIR < 25,000", "NIT TPG Star"),
    (8,   "JEE Main Cleared", "🥉", "AIR < 100,000", "JEE Advanced Qualified"),
    (0,   "Serious Aspirant", "📖", "Aspirant", "JEE Main Cleared"),
    (-999999, "Kota Backbencher", "🎒", "Backbencher", "Serious Aspirant"),
]

def get_trivia_tier(marks: int) -> dict[str, Any]:
    """Return the candidate's competitive rank tier and ladder progress."""
    for min_m, title, emoji, badge, next_t in TRIVIA_RANKS:
        if marks >= min_m:
            next_m = None
            if next_t:
                for m, t, _, _, _ in TRIVIA_RANKS:
                    if t == next_t:
                        next_m = m
                        break
            return {
                "title": title,
                "emoji": emoji,
                "badge": badge,
                "next_title": next_t,
                "next_marks": next_m,
                "cur_min": min_m,
            }
    return {
        "title": "Serious Aspirant",
        "emoji": "📖",
        "badge": "Aspirant",
        "next_title": "JEE Main Cleared",
        "next_marks": 8,
        "cur_min": 0,
    }


# ====================================================================== #
# Academic Equation & Question Pretty-Printers                            #
# ====================================================================== #

OPT_EMOJIS: dict[str, str] = {
    "A": "🇦",
    "B": "🇧",
    "C": "🇨",
    "D": "🇩",
}

def format_academic_text(text: str) -> str:
    """Render academic text with distexer for Discord-safe math and symbols."""
    if not text:
        return text

    cleaned = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    try:
        return format_text(cleaned, mode=MODE_UNICODE_NATIVE).strip()
    except (TypeError, ValueError, RecursionError):
        # Keep trivia usable if an unexpected upstream payload defeats the formatter.
        return cleaned.strip()



def format_question_presentation(text: str) -> str:
    """Format run-on questions containing sub-items (reactions, statements, properties) into a neat list."""
    if not text:
        return text
    s = text.strip()

    # 1. Statement-I / Statement-II formatting
    stmt_pattern = re.compile(r'\b(Statement\s*[-–—]?(?:I{1,3}|[123])):?\s*', re.IGNORECASE)
    matches = list(stmt_pattern.finditer(s))
    if len(matches) >= 2:
        parts: list[str] = []
        intro = s[:matches[0].start()].strip()
        if intro:
            parts.append(intro)
        for i, m in enumerate(matches):
            label = m.group(1).title()
            start = m.end()
            if i + 1 < len(matches):
                content = s[start:matches[i+1].start()].strip(' ,;')
                parts.append(f"📋 **{label}:** {content}")
            else:
                rest = s[start:]
                tail_m = re.split(r'\.\s+(?=[A-Z][a-z]+(?:\s+of|\s+is|\s+are))', rest, maxsplit=1)
                content = tail_m[0].strip(' ,;')
                parts.append(f"📋 **{label}:** {content}")
                if len(tail_m) > 1 and tail_m[1].strip():
                    parts.append('\n' + tail_m[1].strip())
        return '\n'.join(parts)

    # 2. Roman numeral sub-items: (i), (ii), (iii), (iv)
    roman_pattern = re.compile(r'[,;]?\s*\(((?:i{1,3}|iv|v|vi{0,3}|ix|x))\)\s*', re.IGNORECASE)
    r_matches = list(roman_pattern.finditer(s))
    if len(r_matches) >= 2:
        parts: list[str] = []
        intro = s[:r_matches[0].start()].strip()
        if intro:
            parts.append(intro)
        for i, m in enumerate(r_matches):
            label = m.group(1).lower()
            start = m.end()
            if i + 1 < len(r_matches):
                item_content = s[start:r_matches[i+1].start()].rstrip(' ,;')
                parts.append(f" ▸ `({label})` {item_content}")
            else:
                rest = s[start:]
                split_rest = re.split(r'\.\s+(?=[A-Z])', rest, maxsplit=1)
                item_content = split_rest[0].rstrip(' ,;')
                parts.append(f" ▸ `({label})` {item_content}")
                if len(split_rest) > 1 and split_rest[1].strip():
                    parts.append('\n' + split_rest[1].strip())
        return '\n'.join(parts)

    # 3. Alphabetic sub-items: (a), (b), (c)
    alpha_pattern = re.compile(r'[,;]?\s*\(([a-d])\)\s*', re.IGNORECASE)
    a_matches = list(alpha_pattern.finditer(s))
    if len(a_matches) >= 2:
        parts: list[str] = []
        intro = s[:a_matches[0].start()].strip()
        if intro:
            parts.append(intro)
        for i, m in enumerate(a_matches):
            label = m.group(1).lower()
            start = m.end()
            if i + 1 < len(a_matches):
                item_content = s[start:a_matches[i+1].start()].rstrip(' ,;')
                parts.append(f" ▸ `({label})` {item_content}")
            else:
                rest = s[start:]
                split_rest = re.split(r'\.\s+(?=[A-Z])', rest, maxsplit=1)
                item_content = split_rest[0].rstrip(' ,;')
                parts.append(f" ▸ `({label})` {item_content}")
                if len(split_rest) > 1 and split_rest[1].strip():
                    parts.append('\n' + split_rest[1].strip())
        return '\n'.join(parts)

    return s


def format_matching_text(text: str) -> str:
    """Format Match the Following List-I and List-II into clean structured sections."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    header = ""
    list_1: list[str] = []
    list_2: list[str] = []
    current_list = 0

    for line in lines:
        lower = line.lower()
        if "list-i:" in lower or "list 1:" in lower or "list i:" in lower:
            current_list = 1
            continue
        elif "list-ii:" in lower or "list 2:" in lower or "list ii:" in lower:
            current_list = 2
            continue

        if current_list == 0:
            if not header:
                header = line
            else:
                header += " " + line
        elif current_list == 1:
            list_1.append(line)
        elif current_list == 2:
            list_2.append(line)

    if not list_1 or not list_2:
        return format_academic_text(text)

    out = []
    if header:
        out.append(f"**{format_academic_text(header)}**\n")

    out.append("📋 **LIST — I**")
    for item in list_1:
        m = re.match(r"^([A-Za-z0-9]+)[\.\)]\s*(.*)$", item)
        if m:
            clean_item = format_academic_text(m.group(2))
            out.append(f" ▸ `[{m.group(1).upper()}]` {clean_item}")
        else:
            out.append(f" ▸ {format_academic_text(item)}")

    out.append("\n📋 **LIST — II**")
    for item in list_2:
        m = re.match(r"^([A-Za-z0-9]+)[\.\)]\s*(.*)$", item)
        if m:
            clean_item = format_academic_text(m.group(2))
            out.append(f" ▸ `[{m.group(1)}]` {clean_item}")
        else:
            out.append(f" ▸ {format_academic_text(item)}")

    return "\n".join(out)


def format_matching_option(opt_text: str) -> str:
    """Format mapping options like 'P→1, Q→2, R→3, S→4' into clean bullet items."""
    parts = re.split(r"[,;]\s*", opt_text.strip())
    formatted_parts = []
    for p in parts:
        p_clean = re.sub(r"\s*(?:→|->|-)\s*", " ➔ ", p.strip())
        formatted_parts.append(f"`{p_clean}`")
    return "  •  ".join(formatted_parts)


# ====================================================================== #
# 1. Modals & Question Components                                        #
# ====================================================================== #

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


class TriviaContinuousControlsView(discord.ui.View):
    """Controls presented after a question concludes in continuous practice mode."""

    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        subject: Optional[str],
        chapter: Optional[str],
        topic: Optional[str],
        session_stats: dict[str, int],
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.ctx = ctx
        self.subject = subject
        self.chapter = chapter
        self.topic = topic
        self.session_stats = session_stats
        self.message: Optional[discord.Message] = None
        self._build_components()

    def _build_components(self) -> None:
        next_btn = discord.ui.Button(
            label="▶️ Next Question",
            style=discord.ButtonStyle.success,
            row=0,
        )
        next_btn.callback = self._next_callback
        self.add_item(next_btn)

        ch_btn = discord.ui.Button(
            label="🔀 Change Chapter / Topic",
            style=discord.ButtonStyle.primary,
            row=0,
        )
        ch_btn.callback = self._change_chapter_callback
        self.add_item(ch_btn)

        sub_btn = discord.ui.Button(
            label="📚 Change Subject",
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        sub_btn.callback = self._change_subject_callback
        self.add_item(sub_btn)

        stop_btn = discord.ui.Button(
            label="🛑 Stop Trivia",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        stop_btn.callback = self._stop_callback
        self.add_item(stop_btn)

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use these controls.", ephemeral=True)
            return
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if not trivia_cog or not trivia_cog._check_cooldown(self.ctx):
            await interaction.response.send_message("⏳ Please wait a moment for the 10-second cooldown.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        await trivia_cog._start_question(
            self.ctx,
            subject=self.subject,
            chapter=self.chapter,
            topic=self.topic,
            continuous=True,
            session_stats=self.session_stats,
            edit_msg=self.message,
        )

    async def _change_chapter_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use these controls.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._show_chapter_browser(
                self.ctx,
                subject=self.subject or "physics",
                continuous=True,
                session_stats=self.session_stats,
                edit_msg=self.message,
            )

    async def _change_subject_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use these controls.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._show_hub(
                self.ctx,
                continuous=True,
                session_stats=self.session_stats,
                edit_msg=self.message,
            )

    async def _stop_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use these controls.", ephemeral=True)
            return
        self.stop()
        for item in self.children:
            item.disabled = True

        att = self.session_stats.get("attempted", 0)
        cor = self.session_stats.get("correct", 0)
        mks = self.session_stats.get("marks", 0)
        cns = self.session_stats.get("coins", 0)
        acc = (cor / att * 100) if att > 0 else 0

        coin_e = emojis.coin(self.ctx.guild)
        summary_embed = embeds.base_embed(
            title="🏁 Practice Trivia Session Concluded",
            description=(
                f"Great work practicing today, **{self.ctx.author.display_name}**!\n\n"
                f"📝 **Questions Attempted:** `{att}`\n"
                f"🎯 **Accuracy:** `{cor}/{att}` ({acc:.1f}%)\n"
                f"📈 **Net Marks Earned:** `{mks:+} Marks`\n"
                f"{coin_e} **Chronocoins Won:** `+{cns:,}` {coin_e}\n\n"
                f"Type `,trivia` anytime to explore the syllabus or start another practice session!"
            ),
            color=embeds.COLOR_INFO,
        )
        embeds.set_footer(summary_embed, "Session ended. All marks & Chronocoins saved to your profile.")
        await interaction.response.edit_message(embed=summary_embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class TriviaQuestionView(discord.ui.View):
    """Interactive component view for handling user responses to trivia questions."""

    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        question_data: dict[str, Any],
        timeout_seconds: int = 60,
        continuous: bool = False,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
        topic: Optional[str] = None,
        session_stats: Optional[dict[str, int]] = None,
    ) -> None:
        super().__init__(timeout=timeout_seconds)
        self.bot = bot
        self.ctx = ctx
        self.db = bot.db
        self.q = question_data
        self.author_id = ctx.author.id
        self.guild_id = ctx.guild.id
        self.q_id = question_data["id"]
        self.continuous = continuous
        self.subject = subject
        self.chapter = chapter
        self.topic = topic
        self.session_stats = session_stats or {"attempted": 0, "correct": 0, "marks": 0, "coins": 0}
        self.answered_users: set[int] = set()
        self.results_summary: list[dict[str, Any]] = []
        # First successful grading response from CJA. It carries the official
        # answer / explanation / concept, so the round summary can reuse it
        # instead of making a second (dummy) check call.
        self.official_result: Optional[dict[str, Any]] = None
        self.message: Optional[discord.Message] = None
        self._concluded: bool = False
        self.bot.active_trivia_games = getattr(self.bot, "active_trivia_games", 0) + 1
        self._build_components()

    def _build_components(self) -> None:
        q_type = self.q.get("type", {}).get("id", "single")
        options = self.q.get("options", [])

        if q_type in ("single", "assertion_reason", "statements", "match"):
            for opt in options:
                k = opt["key"]
                btn = discord.ui.Button(
                    label=f"Option {k}",
                    emoji=OPT_EMOJIS.get(k),
                    style=discord.ButtonStyle.primary,
                    row=0,
                )
                btn.callback = self._make_button_callback(k)
                self.add_item(btn)

        elif q_type == "multiple":
            select_options = [
                discord.SelectOption(
                    label=f"Option {opt['key']}",
                    value=opt["key"],
                    emoji=OPT_EMOJIS.get(opt["key"]),
                    description=format_academic_text(opt.get("text", ""))[:95],
                )
                for opt in options
            ]
            if not select_options:
                select_options = [
                    discord.SelectOption(label=f"Option {k}", value=k, emoji=OPT_EMOJIS.get(k))
                    for k in ["A", "B", "C", "D"]
                ]

            select = discord.ui.Select(
                placeholder="Select one or more options (A, B, C, D)...",
                min_values=1,
                max_values=min(4, len(select_options)),
                options=select_options,
                row=0,
            )
            select.callback = self._select_callback
            self.add_item(select)

        elif q_type == "integer":
            btn = discord.ui.Button(
                label="Submit Integer Answer",
                style=discord.ButtonStyle.success,
                emoji="🔢",
                row=0,
            )
            btn.callback = self._integer_callback
            self.add_item(btn)

        # Skip Question Button (costs 15 Chronocoins)
        skip_btn = discord.ui.Button(
            label="Skip (15 Coins)",
            style=discord.ButtonStyle.secondary,
            emoji="⏩",
            row=1,
        )
        skip_btn.callback = self._skip_callback
        self.add_item(skip_btn)

    async def _skip_callback(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        if user.id != self.author_id:
            await interaction.response.send_message(
                "Only the candidate who started this trivia question can skip it!",
                ephemeral=True,
            )
            return

        SKIP_COST = 15
        success = await self.db.spend_coins(user.id, self.guild_id, SKIP_COST)
        coin_e = emojis.coin(self.ctx.guild)
        if not success:
            curr = await self.db.get_or_create_currency(user.id, self.guild_id)
            await interaction.response.send_message(
                f"❌ You need **{SKIP_COST} Chronocoins** to skip this question! (Current balance: `{curr['coins']}` {coin_e})",
                ephemeral=True,
            )
            return

        self.stop()
        await interaction.response.send_message(
            f"⏩ **Question Skipped!** Spent **{SKIP_COST} Chronocoins**.",
            ephemeral=True,
        )
        await self.conclude_round(skipped_by=user)

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
            # The answer was never graded, so let them try again.
            self.answered_users.discard(user.id)
            await interaction.followup.send("⚠️ Error verifying your answer with CJA. Please try again.", ephemeral=True)
            return

        if self.official_result is None:
            self.official_result = check_res

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

        # Update Database. record_trivia_attempt() already credits `coins_won`
        # to the user's Chronocoin balance, so do NOT call add_coins() again
        # (that used to pay every answer out twice).
        stats = await self.db.record_trivia_attempt(
            user_id=user.id,
            guild_id=self.guild_id,
            correct=is_correct,
            marks=marks,
            coins_won=coins_won,
        )

        if xp_won > 0:
            await self.db.grant_xp(user.id, self.guild_id, xp_won)

        # Update session stats for author in continuous mode
        if user.id == self.author_id:
            self.session_stats["attempted"] += 1
            if is_correct:
                self.session_stats["correct"] += 1
            self.session_stats["marks"] += marks
            self.session_stats["coins"] += coins_won

        # Halloween candy drop. Candy is a plain currency (user_currency.candy),
        # so award a small random amount. This is a bonus only - it must never
        # be able to break the answer flow, hence the try/except.
        candy_str = ""
        if is_correct and random.random() < 0.35:
            try:
                candy_won = random.randint(3, 10)
                await self.db.add_candy(user.id, self.guild_id, candy_won)
                candy_str = f"\n🎃 **Bonus Drop:** Found **{candy_won} 🍬 Candy**!"
            except Exception as e:
                log.warning(f"Candy drop failed (ignored): {e}")

        self.results_summary.append({
            "user": user,
            "correct": is_correct,
            "marks": marks,
            "coins": coins_won,
            "xp": xp_won,
            "streak": stats["current_streak"],
        })

        # Send personalized feedback to the user
        tier_info = get_trivia_tier(stats["total_marks"])
        official_ans_fmt = format_academic_text(str(official_ans))
        explanation_fmt = format_academic_text(explanation)
        coin_e = emojis.coin(self.ctx.guild)
        xp_e = emojis.xp(self.ctx.guild)
        streak_e = emojis.streak(self.ctx.guild)
        if is_correct:
            result_embed = embeds.base_embed(
                title=f"🎉 SPOT ON! CORRECT (+{marks} Marks)",
                description=(
                    f"🏆 **Official Answer:** `[ {official_ans_fmt} ]`\n\n"
                    f"💡 **Explanation:** {explanation_fmt}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 **Rewards:** `+{coins_won}` {coin_e}  •  {xp_e} `+{xp_won}` XP\n"
                    f"{streak_e} **Streak:** `{stats['current_streak']}` in a row (Peak: `{stats['best_streak']}`)\n"
                    f"🎖️ **Rank Status:** {tier_info['emoji']} `{tier_info['title']}` ({stats['total_marks']:,} marks){candy_str}"
                ),
                color=embeds.COLOR_SUCCESS,
            )
        else:
            result_embed = embeds.base_embed(
                title=f"❌ MISSED! ({marks:+} Marks)",
                description=(
                    f"🏆 **Official Answer:** `[ {official_ans_fmt} ]`\n\n"
                    f"💡 **Explanation:** {explanation_fmt}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{coin_e} **Consolation:** `+{coins_won}` {coin_e}  •  {xp_e} `+{xp_won}` XP\n"
                    f"🔥 *Streak reset to 0. Study the concept above and bounce back!*"
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

    async def conclude_round(self, skipped_by: Optional[discord.User] = None) -> None:
        """Edit the message to show the finalized answer, explanation, and results."""
        if not self._concluded:
            self._concluded = True
            current_active = getattr(self.bot, "active_trivia_games", 0)
            if current_active > 0:
                self.bot.active_trivia_games = current_active - 1

        for item in self.children:
            item.disabled = True

        if not self.message:
            return

        # Official answer: reuse what CJA already told us when someone answered.
        # Only if nobody answered (timeout/skip) do we fetch it from CJA with None (unattempted).
        try:
            full_check = self.official_result
            if full_check is None:
                full_check = await cja_client.check_answer(self.q_id, None)
            official_ans = full_check.get("answer", {}).get("display") or "Revealed"
            explanation = full_check.get("explanation") or "No explanation available."
            concept = full_check.get("concept") or "JEE Core Concept"
        except Exception as e:
            log.warning(f"Could not fetch official answer for round summary: {e}")
            official_ans = "Revealed"
            explanation = "Round ended."
            concept = "JEE Core Concept"

        # Apply academic formatting to answer, concept, and explanation
        official_ans_fmt = format_academic_text(str(official_ans))
        concept_fmt = format_academic_text(concept)
        explanation_fmt = format_academic_text(explanation)

        # Update Embed
        subj_info = self.q.get("subject", {})
        subj_name = subj_info.get("name", "JEE")
        subj_id = subj_info.get("id", "chemistry")
        color = SUBJECT_COLORS.get(subj_id, 0x38BDF8)
        emoji = SUBJECT_EMOJIS.get(subj_id, "🧠")
        exam_name = self.q.get("exam", {}).get("name", "JEE")
        q_type = self.q.get("type", {}).get("id", "single")

        coin_e = emojis.coin(self.ctx.guild)
        if skipped_by:
            status_banner = f"⏩ **QUESTION SKIPPED BY {skipped_by.display_name.upper()} (15 {coin_e})**"
        elif self.results_summary:
            status_banner = "🎉 **ROUND CONCLUDED — SCORES LOCKED IN!**"
        else:
            status_banner = "⏰ **TIME'S UP — SOLUTION REVEALED!**"

        if q_type == "match":
            formatted_q = format_matching_text(self.q.get("question", ""))
        else:
            raw_q = format_academic_text(self.q.get("question", ""))
            formatted_q = format_question_presentation(raw_q)

        desc_parts = [
            f"{status_banner}\n",
            f"### 📋 Question\n{formatted_q}\n",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🏆 **OFFICIAL ANSWER KEY:**  `[ {official_ans_fmt} ]`",
            f"💡 **CORE CONCEPT:** *{concept_fmt}*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
            f"📖 **Detailed Theory Breakdown:**\n{explanation_fmt}\n",
        ]

        embed = embeds.base_embed(
            title=f"{emoji} {subj_name} Trivia  •  {exam_name} Solution",
            description="\n".join(desc_parts),
            color=color,
        )

        if self.results_summary:
            summary_lines = []
            sorted_res = sorted(self.results_summary, key=lambda x: x["marks"], reverse=True)
            for r in sorted_res:
                status = "✅" if r["correct"] else "❌"
                streak_txt = f" • 🔥 `{r['streak']}` streak" if r["streak"] > 1 else ""
                summary_lines.append(
                    f"{status} **{r['user'].display_name}**: `{r['marks']:+} Marks` (+{r['coins']} Coins · +{r['xp']} XP){streak_txt}"
                )
            embed.add_field(name="👥 Candidate Performance", value="\n".join(summary_lines), inline=False)
        elif skipped_by:
            embed.add_field(
                name="⏩ Question Skipped",
                value=f"*{skipped_by.display_name} paid 15 Chronocoins to reveal the solution and proceed.*",
                inline=False,
            )
        else:
            embed.add_field(
                name="⌛ Solution Revealed",
                value="*Timer expired with no submissions. Review the full explanation above to master this concept for next time!*",
                inline=False,
            )

        # If continuous mode is enabled, show the next question controls!
        # Strip attachments=[] so the large question card image is deleted when the round concludes
        if self.continuous:
            embeds.set_footer(embed, "Practice Mode Active · Click Next Question to continue or Stop to finish")
            controls_view = TriviaContinuousControlsView(
                bot=self.bot,
                ctx=self.ctx,
                subject=self.subject,
                chapter=self.chapter,
                topic=self.topic,
                session_stats=self.session_stats,
            )
            controls_view.message = self.message
            try:
                await self.message.edit(embed=embed, view=controls_view, attachments=[])
            except Exception as e:
                log.warning(f"Failed to edit trivia message with continuous controls: {e}")
        else:
            embeds.set_footer(embed, "Use ,trivia r for another question | ,trivia p/c/m for continuous practice")
            try:
                await self.message.edit(embed=embed, view=self, attachments=[])
            except Exception as e:
                log.warning(f"Failed to edit trivia message on conclusion: {e}")


# ====================================================================== #
# 2. Interactive Navigation Views (Hub, Chapter Browser, Topic Selector)  #
# ====================================================================== #

class TriviaHubView(discord.ui.View):
    """Main interactive Hub for exploring all 89 chapters and 737 topics."""

    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        continuous: bool = False,
        session_stats: Optional[dict[str, int]] = None,
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.continuous = continuous
        self.session_stats = session_stats or {"attempted": 0, "correct": 0, "marks": 0, "coins": 0}
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
            await trivia_cog._show_chapter_browser(
                self.ctx,
                subject=subject,
                continuous=True,
                session_stats=self.session_stats,
                edit_msg=self.message,
            )

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
        await trivia_cog._start_question(self.ctx, continuous=False, edit_msg=self.message)

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
        continuous: bool = True,
        session_stats: Optional[dict[str, int]] = None,
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.subject = subject
        self.sections = get_sections(subject)
        self.selected_section = selected_section or (self.sections[0] if self.sections else None)
        self.continuous = continuous
        self.session_stats = session_stats or {"attempted": 0, "correct": 0, "marks": 0, "coins": 0}
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
            await trivia_cog._show_topic_menu(
                self.ctx,
                self.subject,
                ch_data,
                continuous=self.continuous,
                session_stats=self.session_stats,
                edit_msg=self.message,
            )

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
        await trivia_cog._start_question(
            self.ctx,
            subject=self.subject,
            chapter=chosen_ch["id"],
            continuous=True,
            session_stats=self.session_stats,
            edit_msg=self.message,
        )

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
        await trivia_cog._start_question(
            self.ctx,
            subject=self.subject,
            continuous=True,
            session_stats=self.session_stats,
            edit_msg=self.message,
        )

    async def _back_hub_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command caller can use this menu.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        trivia_cog: Trivia = self.bot.get_cog("Trivia")
        if trivia_cog:
            await trivia_cog._show_hub(
                self.ctx,
                continuous=self.continuous,
                session_stats=self.session_stats,
                edit_msg=self.message,
            )


class TriviaTopicSelectView(discord.ui.View):
    """Chapter details and specific topic picker."""

    def __init__(
        self,
        bot: commands.Bot,
        ctx: commands.Context,
        subject: str,
        chapter: dict[str, Any],
        continuous: bool = True,
        session_stats: Optional[dict[str, int]] = None,
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.subject = subject
        self.chapter = chapter
        self.continuous = continuous
        self.session_stats = session_stats or {"attempted": 0, "correct": 0, "marks": 0, "coins": 0}
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
            label="▶️ Start Chapter Practice",
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
            f"✅ Target topic set to: **{self.selected_topic_id or 'Any in Chapter'}**.\nClick **Start Chapter Practice** to begin!",
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
            continuous=True,
            session_stats=self.session_stats,
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
                continuous=self.continuous,
                session_stats=self.session_stats,
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
        `,trivia r` — Quick instant random question across all subjects (single-shot)
        `,trivia p` — Physics section & chapter practice (29 chapters, continuous practice)
        `,trivia c` — Chemistry section & chapter practice (34 chapters, continuous practice)
        `,trivia m` — Mathematics section & chapter practice (26 chapters, continuous practice)
        `,trivia <chapter>` (e.g. `,trivia oscillations`, `,trivia goc`, `,trivia emi`) — Direct chapter practice
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

        # 4. Instant Random Question (single-shot mode, stops after answer)
        if sub in ("r", "rand", "random"):
            if not self._check_cooldown(ctx):
                return
            await self._start_question(ctx, continuous=False)
            return

        # 5. Subject shortcuts (enters continuous practice mode)
        if sub in ("p", "physics", "phys"):
            await self._show_chapter_browser(ctx, "physics", continuous=True)
            return
        if sub in ("c", "chemistry", "chem"):
            await self._show_chapter_browser(ctx, "chemistry", continuous=True)
            return
        if sub in ("m", "mathematics", "math", "maths"):
            await self._show_chapter_browser(ctx, "mathematics", continuous=True)
            return

        # 6. Direct Chapter Search! (e.g. ,trivia oscillations, ,trivia goc, ,trivia emi)
        matched_sub, matched_ch = find_chapter(sub)
        if matched_ch and matched_sub:
            await self._show_topic_menu(ctx, matched_sub["id"], matched_ch, continuous=True)
            return

        # 7. Fallback to start random question
        if not self._check_cooldown(ctx):
            return
        await self._start_question(ctx, continuous=False)

    def _make_hub_embed(self) -> discord.Embed:
        embed = embeds.base_embed(
            title="🧠 Chronos JEE Theory Trivia Hub",
            description=(
                "Master JEE Main & JEE Advanced with 100% verified theory trivia questions powered by **CJA**!\n\n"
                "⚛️ **Physics** — `29 Chapters` · `260 Topics`\n"
                "🧪 **Chemistry** — `34 Chapters` · `311 Topics`\n"
                "📐 **Mathematics** — `26 Chapters` · `166 Topics`\n\n"
                "⚡ **89 Chapters** & **737 Topics** total · Official JEE Marking (`+4` / `-1`)\n"
                "💰 Earn Chronocoins & XP · ⏱️ 10-second cooldown between rounds\n\n"
                "👇 *Click a subject below to enter continuous practice mode, or click Instant Random!*"
            ),
            color=0x38BDF8,
        )
        embeds.set_footer(embed, "Tip: Use shortcuts like ,trivia oscillations or ,trivia goc directly!")
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
        embeds.set_footer(embed, "Practice Mode · Continuous trivia with Next Question controls")
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
                f"🎯 *Select a specific topic from the dropdown below, or click **Start Chapter Practice** to begin!*"
            ),
            color=color,
        )
        embeds.set_footer(embed, "100% JEE Theory Trivia · Continuous Practice Mode Enabled")
        return embed

    async def _show_hub(
        self,
        ctx: commands.Context,
        continuous: bool = False,
        session_stats: Optional[dict[str, int]] = None,
        edit_msg: Optional[discord.Message] = None,
    ) -> None:
        """Display the main interactive syllabus hub."""
        embed = self._make_hub_embed()
        view = TriviaHubView(self.bot, ctx, continuous=continuous, session_stats=session_stats)
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
        continuous: bool = True,
        session_stats: Optional[dict[str, int]] = None,
        edit_msg: Optional[discord.Message] = None,
    ) -> None:
        """Display the section and chapter browser for a subject."""
        view = TriviaChapterBrowserView(
            self.bot,
            ctx,
            subject,
            selected_section,
            continuous=continuous,
            session_stats=session_stats,
        )
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
        continuous: bool = True,
        session_stats: Optional[dict[str, int]] = None,
        edit_msg: Optional[discord.Message] = None,
    ) -> None:
        """Display chapter details and topic selector."""
        embed = self._make_topic_embed(subject, chapter)
        view = TriviaTopicSelectView(
            self.bot,
            ctx,
            subject,
            chapter,
            continuous=continuous,
            session_stats=session_stats,
        )
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
        continuous: bool = False,
        session_stats: Optional[dict[str, int]] = None,
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

        # 1. Try to serve instantly from pre-generated question cache
        q_data: Optional[dict[str, Any]] = None
        try:
            q_data = await self.db.pop_cached_question(
                subject=subject,
                chapter=chapter,
                topic=topic,
            )
            if q_data:
                log.info(f"Served question {q_data.get('id')} from pre-generator cache ({subject=}, {chapter=}, {topic=})")
        except Exception as e:
            log.warning(f"Error popping question from cache: {e}")

        # 2. Fall back to live CJA request on cache miss
        if not q_data:
            try:
                q_data = await cja_client.get_question(
                    subject=subject,
                    chapter=chapter,
                    topic=topic,
                    fast=True,
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
        diff_badge = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴"}.get(diff, "🟡")
        q_type_info = q_data.get("type", {})
        q_type_id = q_type_info.get("id", "single")
        q_type_name = q_type_info.get("name", "Single Correct")
        instructions = q_type_info.get("instructions", "Choose the correct option.")
        timeout_sec = config.TRIVIA_ADVANCED_TIME_LIMIT if exam_id == "advanced" else config.TRIVIA_MAIN_TIME_LIMIT

        marking = q_data.get("marking", {})
        pos_mark = marking.get("correct", 4)
        neg_mark = marking.get("incorrect", -1)

        # Format Question & Options
        if q_type_id == "match":
            formatted_question = format_matching_text(q_data.get("question", ""))
        else:
            raw_question = format_academic_text(q_data.get("question", ""))
            formatted_question = format_question_presentation(raw_question)

        options_text = []
        for opt in q_data.get("options", []):
            k = opt["key"]
            opt_emoji = OPT_EMOJIS.get(k, f"[{k}]")
            if q_type_id == "match":
                opt_str = format_matching_option(opt["text"])
                options_text.append(f"{opt_emoji} **({k})**  {opt_str}")
            else:
                opt_str = format_academic_text(opt["text"])
                options_text.append(f"{opt_emoji} **({k})**  {opt_str}")

        if options_text:
            options_block = "\n\n".join(options_text)
        elif q_type_id == "integer":
            options_block = "*🔢 Numerical integer type (range 0–99). Use the button below to submit your answer.*"
        else:
            options_block = "*Choose from the components below.*"

        # Render high-res textbook question card image
        card_file: Optional[discord.File] = None
        if arender_question_card is not None:
            try:
                card_buf = await arender_question_card(
                    question=q_data.get("question", ""),
                    options=q_data.get("options", []),
                    subject=subj_name,
                    chapter=chapter_name,
                    fontsize=22,
                    dpi=200,
                )
                card_file = discord.File(card_buf, filename="question.png")
            except Exception as e:
                log.info(f"Could not render question card image: {e}")

        if card_file is not None:
            embed_desc = (
                f"📌 *{instructions}*\n"
                f"⚖️ **Scoring:** `+{pos_mark}` for correct  •  `{neg_mark}` for incorrect"
            )
        else:
            embed_desc = (
                f"### 📋 Question\n"
                f"{formatted_question}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"### 🎯 Options\n"
                f"{options_block}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 *{instructions}*\n"
                f"⚖️ **Scoring:** `+{pos_mark}` for correct  •  `{neg_mark}` for incorrect"
            )

        embed = embeds.base_embed(
            title=f"{emoji} {subj_name.upper()} TRIVIA  •  {exam_info.upper()}",
            description=embed_desc,
            color=color,
        )
        if card_file is not None:
            embed.set_image(url="attachment://question.png")

        embed.add_field(
            name="📚 Syllabus Path",
            value=f"**{subj_name}** ▸ `{chapter_name}`\n└ *{topic_name}*",
            inline=True,
        )
        embed.add_field(
            name="⚡ Classification",
            value=f"{diff_badge} **{diff}**\n📝 `{q_type_name}`",
            inline=True,
        )
        coin_e = emojis.coin(ctx.guild)
        embed.add_field(
            name="⏱️ Round Clock",
            value=f"**{timeout_sec}s** timer\n⏩ Skip: **15** {coin_e}",
            inline=True,
        )

        footer_text = f"⏱️ {timeout_sec}s limit • Submit with buttons below • Skip costs 15 🪙"
        if continuous:
            footer_text += " • Practice Mode"
        embeds.set_footer(embed, footer_text)

        view = TriviaQuestionView(
            bot=self.bot,
            ctx=ctx,
            question_data=q_data,
            timeout_seconds=timeout_sec,
            continuous=continuous,
            subject=subject,
            chapter=chapter or q_data.get("chapter", {}).get("id"),
            topic=topic,
            session_stats=session_stats,
        )

        if card_file is not None:
            try:
                await msg.edit(embed=embed, view=view, attachments=[card_file])
            except Exception as edit_err:
                log.warning(f"Failed to edit msg with attachments ({edit_err}), re-sending fresh: {edit_err}")
                try:
                    await msg.delete()
                except Exception:
                    pass
                msg = await ctx.send(embed=embed, file=card_file, view=view)
        else:
            await msg.edit(embed=embed, view=view)
        view.message = msg

    async def _send_leaderboard(self, ctx: commands.Context) -> None:
        """Display the server trivia leaderboard with JEE AIR ladder climb and visual card."""
        rows = await self.db.get_trivia_leaderboard(ctx.guild.id, limit=10)
        if not rows:
            await ctx.send(embed=embeds.info_embed(
                "🏆 Trivia Leaderboard",
                "No trivia matches have been recorded yet in this server! Be the first by typing `,trivia r`.",
            ))
            return

        embed = embeds.base_embed(
            title=f"🏆 JEE AIR Leaderboard • {ctx.guild.name}",
            description="Official server rankings based on net JEE marks earned in `,trivia`:\n",
            color=embeds.COLOR_LEVELUP,
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            rank_badge = medals[i] if i < 3 else f"`#{i + 1:02d}`"
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else f"User {row['user_id']}"
            acc = (row["questions_correct"] / row["questions_attempted"] * 100) if row["questions_attempted"] > 0 else 0
            tier = get_trivia_tier(row["total_marks"])
            streak_txt = f" • 🔥 `{row['current_streak']}` streak" if row["current_streak"] > 0 else ""
            lines.append(
                f"{rank_badge} **{name}** {tier['emoji']} `[{tier['badge']}]`\n"
                f"   └ **{row['total_marks']:+,} Marks** · `{acc:.0f}%` ({row['questions_correct']}/{row['questions_attempted']}){streak_txt}"
            )

        embed.add_field(name="🏅 Top Academic Contenders", value="\n".join(lines), inline=False)

        # Personal climb section for the caller
        author_rank, total_players = await self.db.get_user_trivia_rank(ctx.author.id, ctx.guild.id)
        author_stats = await self.db.get_or_create_trivia_stats(ctx.author.id, ctx.guild.id)
        author_tier = get_trivia_tier(author_stats["total_marks"])
        author_score = f"{author_stats['total_marks']:+,} M"

        climb_lines = [
            f"**Current Standing:** Rank `#{author_rank}` of `{total_players}` candidates",
            f"**Rank Tier:** {author_tier['emoji']} **{author_tier['title']}** (`{author_tier['badge']}`)",
            f"**Net Score:** `{author_stats['total_marks']:+,} Marks`",
        ]

        if author_tier["next_title"] and author_tier["next_marks"] is not None:
            needed = author_tier["next_marks"] - author_stats["total_marks"]
            cur_prog = max(0, author_stats["total_marks"] - author_tier["cur_min"])
            tot_prog = max(1, author_tier["next_marks"] - author_tier["cur_min"])
            pct = min(100, int((cur_prog / tot_prog) * 100))
            p_bar = embeds.bar(cur_prog, tot_prog, 12)
            climb_lines.append(
                f"**Ladder Progress:** `{p_bar}` **{pct}%**\n"
                f"└ *Need **{needed} more marks** to unlock **{author_tier['next_title']}**!*"
            )
        else:
            climb_lines.append("👑 **Apex Achieved!** You hold the highest possible rank (AIR 1)!")

        embed.add_field(name="🧗 Your Climb Progress", value="\n".join(climb_lines), inline=False)
        embeds.set_footer(embed, f"{ctx.prefix}trivia r to play • {ctx.prefix}trivia me for full candidate profile")

        # Top 6 entries for visual card
        top_6 = rows[:6]

        async def _fetch_trivia_entry(rank_num: int, r: dict[str, Any]) -> dict[str, Any]:
            user_id = r["user_id"]
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            avatar_bytes = None
            if member:
                try:
                    avatar_bytes = await member.display_avatar.with_format("png").with_size(64).read()
                except Exception:
                    avatar_bytes = None

            att = r.get("questions_attempted", 0)
            cor = r.get("questions_correct", 0)
            acc = (cor / att * 100) if att > 0 else 0
            tier = get_trivia_tier(r.get("total_marks", 0))

            return {
                "rank": rank_num,
                "user_id": user_id,
                "name": name,
                "sub": f"{tier['badge']} · {acc:.0f}% acc ({cor}/{att})",
                "score": f"{r['total_marks']:+,} M",
                "avatar_bytes": avatar_bytes,
                "is_author": (user_id == ctx.author.id),
                "icon": "mystery_box",
            }

        entries = list(await asyncio.gather(*[
            _fetch_trivia_entry(i + 1, row) for i, row in enumerate(top_6)
        ]))

        loop = asyncio.get_running_loop()
        card_file = None
        try:
            card_bytes = await loop.run_in_executor(
                None,
                render_leaderboard_card_sync,
                "JEE AIR LADDER",
                "JEE Main & Advanced",
                ctx.guild.name,
                "trivia",
                entries,
                author_rank,
                author_score,
                ctx.author.id,
                None,
                "mystery_box",
                total_players,
                "chronos_xp",
            )
            card_file = discord.File(io.BytesIO(card_bytes), filename="trivia_leaderboard.png")
            embed.set_image(url="attachment://trivia_leaderboard.png")
        except Exception as e:
            log.error("Failed to render visual trivia leaderboard card", exc_info=e)

        if card_file:
            await ctx.send(file=card_file, embed=embed)
        else:
            await ctx.send(embed=embed)

    async def _send_user_stats(self, ctx: commands.Context) -> None:
        """Display personal trivia metrics and ladder climb for the author."""
        stats = await self.db.get_or_create_trivia_stats(ctx.author.id, ctx.guild.id)
        rank, total_players = await self.db.get_user_trivia_rank(ctx.author.id, ctx.guild.id)
        tier = get_trivia_tier(stats["total_marks"])
        currency = await self.db.get_or_create_currency(ctx.author.id, ctx.guild.id)

        att = stats["questions_attempted"]
        cor = stats["questions_correct"]
        acc = (cor / att * 100) if att > 0 else 0

        embed = embeds.base_embed(
            title=f"🎓 JEE Candidate Profile • {ctx.author.display_name}",
            description=(
                f"### {tier['emoji']} **{tier['title']}** `[{tier['badge']}]`\n"
                f"Server Standing: **Rank #{rank}** of `{total_players}` candidates"
            ),
            color=embeds.COLOR_LEVELUP,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        # Ladder progress
        if tier["next_title"] and tier["next_marks"] is not None:
            needed = tier["next_marks"] - stats["total_marks"]
            cur_prog = max(0, stats["total_marks"] - tier["cur_min"])
            tot_prog = max(1, tier["next_marks"] - tier["cur_min"])
            pct = min(100, int((cur_prog / tot_prog) * 100))
            p_bar = embeds.bar(cur_prog, tot_prog, 14)
            progress_desc = (
                f"`{p_bar}` **{pct}%**\n"
                f"🎯 **{needed} marks** needed to rank up to **{tier['next_title']}**"
            )
        else:
            progress_desc = "👑 **MAX RANK ACHIEVED** — You reign supreme at AIR 1!"

        embed.add_field(name="🧗 Next Rank Target", value=progress_desc, inline=False)

        # Core Exam Metrics
        embed.add_field(name="📈 Net Marks", value=f"**{stats['total_marks']:+,}** Marks", inline=True)
        embed.add_field(name="🎯 Accuracy", value=f"**{acc:.1f}%** ({cor}/{att})", inline=True)
        # Economy & Status
        coin_e = emojis.coin(ctx.guild)
        streak_e = emojis.streak(ctx.guild)
        embed.add_field(
            name=f"{streak_e} Streak",
            value=f"**{stats['current_streak']}** current · Peak **{stats['best_streak']}**",
            inline=True,
        )
        embed.add_field(name=f"{coin_e} Chronocoins", value=f"**{currency['coins']:,}** balance", inline=True)
        embed.add_field(name="💰 Trivia Earnings", value=f"**+{stats['total_coins_won']:,}** {coin_e} won", inline=True)
        is_ready = time.time() - self.user_cooldowns.get(ctx.author.id, 0) >= config.TRIVIA_COOLDOWN_SECONDS
        status_txt = "🟢 **Ready to grind!**" if is_ready else "⏳ Cooldown active"
        embed.add_field(name="⏱️ Status", value=status_txt, inline=True)

        embeds.set_footer(embed, f"Use {ctx.prefix}trivia r to attempt a question • Skip costs 15 🪙")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Trivia(bot))
