"""Background Trivia Question Pre-Generator & Vault Cog.

Pre-fetches official JEE theory trivia questions across all 737 topics in waves
during bot idle time, stores them in SQLite (`trivia_question_cache`), and serves
them instantly when users play `.trivia`.

Features:
- Continuous wave cycle (Wave 1, Wave 2, ...) iterating through all 737 topics
- Soft-cap of 5 cached questions per topic to ensure balanced coverage
- Automatic pause when users are actively playing trivia to give CJA bandwidth to live players
- Rate-limited to ~1 request every 2.5 seconds (safe for backend)
- Instant atomic pop-and-delete on trivia start so questions are never reused
- `.wave` / `.cacheinfo` command to monitor real-time progress and database question counts
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import discord
from discord.ext import commands, tasks

import config
from services.cja import CJAError, cja_client, get_syllabus
from utils import embeds, emojis
from utils.checks import is_dev

log = logging.getLogger("question_cache")


class QuestionCache(commands.Cog, name="QuestionCache"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db

        self.topics: list[dict[str, Any]] = []
        self.topic_index: int = 0
        self.current_wave: int = 1
        self.wave_start_time: float = time.time()

        self.is_paused: bool = False
        self.pause_reason: str = ""

        self.total_fetched: int = 0
        self.total_skipped: int = 0
        self.total_errors: int = 0
        self.consecutive_errors: int = 0

        self.last_fetched_topic: Optional[dict[str, Any]] = None
        self.last_fetch_timestamp: float = 0

        self._init_syllabus()
        self.wave_worker.start()

    def cog_unload(self) -> None:
        self.wave_worker.cancel()

    def _init_syllabus(self) -> None:
        """Flatten syllabus chapters and topics into a linear list for wave iteration."""
        syllabus = get_syllabus()
        flattened: list[dict[str, Any]] = []
        for sub in syllabus.get("subjects", []):
            sub_id = sub.get("id")
            sub_name = sub.get("name", sub_id)
            for ch in sub.get("chapters", []):
                ch_id = ch.get("id")
                ch_name = ch.get("name", ch_id)
                for top in ch.get("topics", []):
                    top_id = top.get("id")
                    top_name = top.get("name", top_id)
                    flattened.append({
                        "subject_id": sub_id,
                        "subject_name": sub_name,
                        "chapter_id": ch_id,
                        "chapter_name": ch_name,
                        "id": top_id,
                        "name": top_name,
                    })
        self.topics = flattened
        log.info(f"Loaded {len(self.topics)} syllabus topics into wave pre-generator.")

    async def _advance_topic(self) -> None:
        """Advance index to the next topic, looping into next wave if end reached."""
        self.topic_index += 1
        if self.topic_index >= len(self.topics):
            self.current_wave += 1
            self.topic_index = 0
            self.wave_start_time = time.time()
            log.info(
                f"Wave {self.current_wave - 1} completed! Starting Wave {self.current_wave} across {len(self.topics)} topics."
            )
        try:
            await self.db.set_kv("trivia_current_wave", str(self.current_wave))
            await self.db.set_kv("trivia_topic_index", str(self.topic_index))
        except Exception as e:
            log.warning(f"Failed to persist wave state: {e}")

    @tasks.loop(seconds=8.0)
    async def wave_worker(self) -> None:
        """Background worker that continuously pulls 1 question per topic at a safe rate."""
        if not self.topics:
            return

        # 1. Manual pause check
        if self.is_paused:
            return

        # 2. Dynamic pause when trivia is actively being played in any guild
        if getattr(self.bot, "active_trivia_games", 0) > 0:
            self.pause_reason = "Trivia active in server"
            return
        elif self.pause_reason == "Trivia active in server":
            self.pause_reason = ""

        # 3. Current topic
        topic = self.topics[self.topic_index]
        top_id = topic["id"]

        # 4. Skip topics that already have 5 cached questions
        try:
            cached_count = await self.db.count_cached_questions(top_id)
        except Exception as e:
            log.warning(f"Error checking cache count for topic {top_id}: {e}")
            cached_count = 0

        if cached_count >= 5:
            self.total_skipped += 1
            await self._advance_topic()
            return

        # 5. Fetch question from CJA
        try:
            q_data = await cja_client.get_question(
                subject=topic["subject_id"],
                chapter=topic["chapter_id"],
                topic=topic["id"],
                fast=True,
                hide_answer=True,
                embed=True,
            )
            if q_data and q_data.get("id"):
                saved = await self.db.cache_question(
                    question_id=q_data["id"],
                    subject_id=topic["subject_id"],
                    chapter_id=topic["chapter_id"],
                    topic_id=topic["id"],
                    question_data=q_data,
                )
                if saved:
                    self.total_fetched += 1
                    self.consecutive_errors = 0
                    self.last_fetched_topic = topic
                    self.last_fetch_timestamp = time.time()
                    log.info(
                        f"[Wave {self.current_wave}] Cached question for {topic['subject_name']} > "
                        f"{topic['chapter_name']} > {topic['name']} (ID: {q_data['id']})"
                    )

            await self._advance_topic()

        except CJAError as e:
            self.total_errors += 1
            self.consecutive_errors += 1
            log.warning(f"CJA error in wave pre-generator ({e.code}): {e.message}")
            await self._advance_topic()
            if self.consecutive_errors >= 3:
                await asyncio.sleep(25)
        except Exception as e:
            self.total_errors += 1
            self.consecutive_errors += 1
            log.warning(f"Unexpected error in wave pre-generator: {e}")
            await self._advance_topic()
            if self.consecutive_errors >= 3:
                await asyncio.sleep(25)

    @wave_worker.before_loop
    async def before_wave_worker(self) -> None:
        await self.bot.wait_until_ready()
        try:
            saved_wave = await self.db.get_kv("trivia_current_wave", "1")
            saved_idx = await self.db.get_kv("trivia_topic_index", "0")
            self.current_wave = max(1, int(saved_wave))
            self.topic_index = max(0, int(saved_idx))
            if self.topics and self.topic_index >= len(self.topics):
                self.topic_index = 0
            log.info(
                f"Resumed trivia wave generator at Wave {self.current_wave}, Topic {self.topic_index + 1}/{len(self.topics)}"
            )
        except Exception as e:
            log.warning(f"Could not restore saved wave state: {e}")

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    @commands.command(name="wave", aliases=["cacheinfo", "cache", "tcache", "waveinfo", "vault"])
    @commands.guild_only()
    async def wave_cmd(self, ctx: commands.Context) -> None:
        """View the background question pre-generator wave progress and database vault count."""
        stats = await self.db.get_cache_stats()
        total_cached = stats.get("total", 0)
        by_sub = stats.get("by_subject", {})
        phys_cnt = by_sub.get("physics", 0)
        chem_cnt = by_sub.get("chemistry", 0)
        math_cnt = by_sub.get("mathematics", 0)

        total_topics = max(1, len(self.topics))
        curr_idx = min(self.topic_index, total_topics - 1)
        pct = (curr_idx / total_topics) * 100.0
        bar = embeds.bar(curr_idx, total_topics, length=14)

        current_topic = self.topics[curr_idx] if self.topics else None
        if current_topic:
            topic_str = f"**{current_topic['subject_name']}** ▸ `{current_topic['chapter_name']}`\n└ *{current_topic['name']}*"
        else:
            topic_str = "None"

        if self.is_paused:
            status_str = f"⏸️ **Paused** ({self.pause_reason or 'Manual'})"
        elif getattr(self.bot, "active_trivia_games", 0) > 0:
            status_str = "⏸️ **Paused** (Trivia in progress)"
        else:
            status_str = "🟢 **Pre-generating** (~1 req / 8.0s)"

        embed = embeds.base_embed(
            title="🌊 JEE Trivia Pre-Generator & Vault",
            description="Background worker pre-caches verified questions across all 737 topics so trivia plays instantly with zero lag.",
            color=embeds.COLOR_INFO,
        )

        embed.add_field(
            name=f"🌊 Wave Cycle #{self.current_wave}",
            value=(
                f"`{bar}` **{pct:.1f}%**\n"
                f"Topic **{curr_idx + 1}** of **{total_topics}**\n\n"
                f"🎯 **Current Target:**\n{topic_str}"
            ),
            inline=False,
        )

        embed.add_field(
            name="📦 Database Question Vault",
            value=(
                f"⚡ Total Cached: **{total_cached:,}** questions\n"
                f"⚛️ Physics: **{phys_cnt:,}**\n"
                f"🧪 Chemistry: **{chem_cnt:,}**\n"
                f"📐 Mathematics: **{math_cnt:,}**\n"
                f"🗺️ Coverage: **{stats.get('distinct_chapters', 0)} / 89** Ch · **{stats.get('distinct_topics', 0)} / 737** Topics"
            ),
            inline=True,
        )

        last_str = "None yet"
        if self.last_fetched_topic and self.last_fetch_timestamp:
            ago_sec = max(0, int(time.time() - self.last_fetch_timestamp))
            last_name = self.last_fetched_topic['name']
            if len(last_name) > 28:
                last_name = last_name[:25] + "..."
            last_str = f"`{last_name}` ({ago_sec}s ago)"

        embed.add_field(
            name="📊 Worker Metrics",
            value=(
                f"⚡ Status: {status_str}\n"
                f"📥 Fetched: **+{self.total_fetched}**\n"
                f"⏭️ Skipped (cap ≥5): **+{self.total_skipped}**\n"
                f"⚠️ Errors: **{self.total_errors}**\n"
                f"⏱️ Last: {last_str}"
            ),
            inline=True,
        )

        embeds.set_footer(embed, "Questions are automatically served & deleted on use • Cap: 5 per topic")
        await ctx.send(embed=embed)

    @commands.command(name="cachepause")
    @is_dev()
    @commands.guild_only()
    async def cache_pause_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Pause the trivia question pre-generator worker loop."""
        self.is_paused = True
        self.pause_reason = "Manual dev pause"
        await ctx.send(embed=embeds.info_embed("⏸️ Trivia question pre-generator paused."))

    @commands.command(name="cacherun", aliases=["cacheresume"])
    @is_dev()
    @commands.guild_only()
    async def cache_run_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Resume the trivia question pre-generator worker loop."""
        self.is_paused = False
        self.pause_reason = ""
        await ctx.send(embed=embeds.success_embed("▶️ Trivia question pre-generator resumed!"))

    @commands.command(name="cacheclear")
    @is_dev()
    @commands.guild_only()
    async def cache_clear_cmd(self, ctx: commands.Context) -> None:
        """[Dev only] Wipe all cached trivia questions in the database."""
        deleted = await self.db.clear_cache()
        self.current_wave = 1
        self.topic_index = 0
        await self.db.set_kv("trivia_current_wave", "1")
        await self.db.set_kv("trivia_topic_index", "0")
        await ctx.send(embed=embeds.success_embed(f"🗑️ Cleared **{deleted}** cached questions and reset wave loop to Wave 1, Topic 1."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuestionCache(bot))
