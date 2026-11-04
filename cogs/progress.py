"""JEE Command Centre & Study Progress Suite.

Interactive, intelligent JEE Main prep tracker:
- All-in-one JEE Command Centre (.jee / .prep / .tracker) with syllabus progress bars.
- Interactive dropdown & button selectors for .chapterdone, .topicdone, .pyqsdone, and .revision.
- Smart auto-resolution: logs chapters/subtopics across subjects even when subject is omitted.
- Visual completion indicators (✅ vs ○), duplicate detection, and celebration embeds.
- Full rewards (+coins, +XP) wired to economy and achievements.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from utils import economy, embeds, emojis
from utils import syllabus as syllabus_data
from utils.subjects import SUBJECT_ALIASES, SUBJECT_HINT, SUBJECT_INFO, normalize_subject_key

log = logging.getLogger("progress")

SUBJECTS_WITH_SYLLABUS = tuple(syllabus_data.SYLLABUS.keys())

POPULAR_JEE_BOOKS = [
    ("HC Verma - Concepts of Physics Vol 1", "physics"),
    ("HC Verma - Concepts of Physics Vol 2", "physics"),
    ("DC Pandey - Understanding Physics", "physics"),
    ("IE Irodov - Problems in General Physics", "physics"),
    ("Cengage Physics - BM Sharma", "physics"),
    ("MS Chouhan - Advanced Problems in Organic Chemistry", "chemistry"),
    ("RC Mukherjee - Modern Approach to Chemical Calculations", "chemistry"),
    ("OP Tandon - Physical / Inorganic Chemistry", "chemistry"),
    ("Himanshu Pandey - Organic Chemistry", "chemistry"),
    ("Cengage Mathematics - G. Tewani", "maths"),
    ("Black Book - Advanced Problems in Mathematics (Vikas Gupta)", "maths"),
    ("SL Loney - Plane Trigonometry / Coordinate Geometry", "maths"),
    ("Amit M Agarwal - Integral / Differential Calculus", "maths"),
]


def _normalize_subject(text: Optional[str]) -> Optional[str]:
    """Best-effort match against the Physics/Chemistry/Maths aliases;
    anything else is kept as free text (title-cased)."""
    if not text:
        return None
    key = normalize_subject_key(text)
    return SUBJECT_ALIASES.get(key, text.strip().title())


def _make_progress_bar(current: int, total: int, length: int = 12) -> str:
    """Generate a clean visual text progress bar."""
    if total <= 0:
        return f"[{'░' * length}] 0%"
    pct = min(1.0, max(0.0, current / total))
    filled = int(round(length * pct))
    bar = "█" * filled + "░" * (length - filled)
    return f"`[{bar}]` {current}/{total} ({int(pct * 100)}%)"


# ==============================================================================
# Interactive UI Views
# ==============================================================================

class SubjectSelect(discord.ui.Select):
    def __init__(self, active_sub: str = "physics"):
        options = [
            discord.SelectOption(label="Physics", value="physics", emoji="⚛️", default=(active_sub == "physics")),
            discord.SelectOption(label="Chemistry", value="chemistry", emoji="🧪", default=(active_sub == "chemistry")),
            discord.SelectOption(label="Mathematics", value="maths", emoji="📐", default=(active_sub == "maths")),
        ]
        super().__init__(placeholder="📚 Pick Subject...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: InteractiveChapterSelectorView = self.view  # type: ignore
        await view.update_subject(interaction, self.values[0])


class ChapterSelect(discord.ui.Select):
    def __init__(self, subject: str, chapters: list[dict[str, Any]], completed_set: set[str]):
        options = []
        for i, ch in enumerate(chapters[:25], start=1):
            is_done = ch["name"].strip().lower() in completed_set
            icon = "✅ " if is_done else f"{i}. "
            label = f"{icon}{ch['name']}"[:95]
            desc = "Already completed!" if is_done else f"Chapter {i} of {len(chapters)}"
            options.append(discord.SelectOption(label=label, value=str(i), description=desc))

        super().__init__(
            placeholder=f"📖 Choose {subject.title()} Chapter...",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: InteractiveChapterSelectorView = self.view  # type: ignore
        chap_num = int(self.values[0])
        await view.log_chapter(interaction, chap_num)


class InteractiveChapterSelectorView(discord.ui.View):
    def __init__(self, author_id: int, cog: "Progress", subject: str = "physics"):
        super().__init__(timeout=180.0)
        self.author_id = author_id
        self.cog = cog
        self.subject = subject
        self.completed_set: set[str] = set()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command caller can use this selector.", ephemeral=True)
            return False
        return True

    async def init_data(self, guild_id: int) -> None:
        self.completed_set = await self.cog.db.get_completed_chapter_names(self.author_id, guild_id)
        self.clear_items()
        self.add_item(SubjectSelect(self.subject))
        chaps = syllabus_data.get_chapters(self.subject)
        self.add_item(ChapterSelect(self.subject, chaps, self.completed_set))

    async def update_subject(self, interaction: discord.Interaction, new_sub: str) -> None:
        self.subject = new_sub
        chaps = syllabus_data.get_chapters(self.subject)
        self.clear_items()
        self.add_item(SubjectSelect(self.subject))
        self.add_item(ChapterSelect(self.subject, chaps, self.completed_set))
        info = SUBJECT_INFO.get(self.subject, {"emoji": "📖", "label": self.subject.title()})
        embed = embeds.base_embed(
            title=f"{info['emoji']} Select {info['label']} Chapter",
            description=f"Pick the chapter you just mastered from the dropdown below:\n\n"
                        f"• Completed chapters are marked with ✅\n"
                        f"• Each logged chapter grants **+35 Chronocoins** 🪙 and **+40 XP** ⚡",
            color=embeds.COLOR_PROGRESS,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def log_chapter(self, interaction: discord.Interaction, chap_num: int) -> None:
        chaps = syllabus_data.get_chapters(self.subject)
        if chap_num < 1 or chap_num > len(chaps):
            await interaction.response.send_message("Invalid chapter number.", ephemeral=True)
            return

        chapter = chaps[chap_num - 1]
        chap_name = chapter["name"]
        is_already_done = chap_name.strip().lower() in self.completed_set

        coins, xp = await self.cog.log_and_reward_direct(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            type_="chapter" if not is_already_done else "revision",
            label=chap_name,
            subject=self.subject,
            chapter=chap_name,
        )

        self.completed_set.add(chap_name.strip().lower())
        sub_chaps = syllabus_data.get_chapters(self.subject)
        done_in_sub = sum(1 for c in sub_chaps if c["name"].strip().lower() in self.completed_set)
        bar = _make_progress_bar(done_in_sub, len(sub_chaps))

        title = "🎉 Chapter Completed!" if not is_already_done else "🔁 Chapter Revision Logged!"
        desc = (
            f"**{self.subject.title()} Ch. {chap_num} — {chap_name}**\n\n"
            f"🪙 **Reward:** `+{coins}` Chronocoins · ⚡ `+{xp}` XP\n"
            f"📊 **{self.subject.title()} Progress:** {bar}\n\n"
            f"*{'First time completion recorded!' if not is_already_done else 'Marked as an additional revision pass.'}*"
        )
        embed = embeds.success_embed(title, desc)
        self.clear_items()
        await interaction.response.edit_message(embed=embed, view=self)


class PyqQuickView(discord.ui.View):
    def __init__(self, author_id: int, cog: "Progress", subject: Optional[str] = None):
        super().__init__(timeout=120.0)
        self.author_id = author_id
        self.cog = cog
        self.subject = subject

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command caller can use these buttons.", ephemeral=True)
            return False
        return True

    async def _handle_year(self, interaction: discord.Interaction, year: str) -> None:
        coins, xp = await self.cog.log_and_reward_direct(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            type_="pyq",
            label=year,
            subject=self.subject,
        )
        subj_str = f" ({self.subject.title()})" if self.subject else ""
        embed = embeds.success_embed(
            "🎯 PYQ Year Logged!",
            f"**JEE Main {year}**{subj_str} marked complete.\n\n"
            f"🪙 **Reward:** `+{coins}` Chronocoins · ⚡ `+{xp}` XP",
        )
        self.clear_items()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="2025", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def btn_2025(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_year(interaction, "2025")

    @discord.ui.button(label="2024", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def btn_2024(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_year(interaction, "2024")

    @discord.ui.button(label="2023", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def btn_2023(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_year(interaction, "2023")

    @discord.ui.button(label="2022", style=discord.ButtonStyle.secondary, emoji="📝", row=1)
    async def btn_2022(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_year(interaction, "2022")

    @discord.ui.button(label="2021", style=discord.ButtonStyle.secondary, emoji="📝", row=1)
    async def btn_2021(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_year(interaction, "2021")


class RevisionQuickView(discord.ui.View):
    def __init__(self, author_id: int, cog: "Progress", subject: Optional[str] = None):
        super().__init__(timeout=120.0)
        self.author_id = author_id
        self.cog = cog
        self.subject = subject

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command caller can use these buttons.", ephemeral=True)
            return False
        return True

    async def _handle_pass(self, interaction: discord.Interaction, pass_num: str) -> None:
        coins, xp = await self.cog.log_and_reward_direct(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            type_="revision",
            label=pass_num,
            subject=self.subject,
        )
        ordinal = {"1": "1st", "2": "2nd", "3": "3rd", "4": "4th", "5": "5th"}.get(pass_num, f"{pass_num}th")
        subj_str = f" ({self.subject.title()})" if self.subject else ""
        embed = embeds.success_embed(
            "🔁 Revision Pass Logged!",
            f"**{ordinal} Complete Revision**{subj_str} marked done.\n\n"
            f"🪙 **Reward:** `+{coins}` Chronocoins · ⚡ `+{xp}` XP",
        )
        self.clear_items()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="1st Pass", style=discord.ButtonStyle.success, emoji="🔁", row=0)
    async def btn_p1(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_pass(interaction, "1")

    @discord.ui.button(label="2nd Pass", style=discord.ButtonStyle.primary, emoji="🔁", row=0)
    async def btn_p2(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_pass(interaction, "2")

    @discord.ui.button(label="3rd Pass", style=discord.ButtonStyle.primary, emoji="🔁", row=0)
    async def btn_p3(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_pass(interaction, "3")

    @discord.ui.button(label="4th Pass", style=discord.ButtonStyle.secondary, emoji="🔁", row=0)
    async def btn_p4(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_pass(interaction, "4")


class JeeCommandCentreView(discord.ui.View):
    def __init__(self, author_id: int, cog: "Progress", target_user: discord.User | discord.Member):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.cog = cog
        self.target_user = target_user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command caller can use this command centre.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Log Chapter", style=discord.ButtonStyle.success, emoji="📖", row=0)
    async def btn_log_chapter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = InteractiveChapterSelectorView(interaction.user.id, self.cog, "physics")
        await view.init_data(interaction.guild_id or 0)
        embed = embeds.base_embed(
            title="⚛️ Select Physics Chapter",
            description="Pick a chapter to log as completed from the dropdown below:",
            color=embeds.COLOR_PROGRESS,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Log PYQ Year", style=discord.ButtonStyle.primary, emoji="🎯", row=0)
    async def btn_log_pyq(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = PyqQuickView(interaction.user.id, self.cog)
        embed = embeds.base_embed(
            title="🎯 Quick Log PYQ Year",
            description="Click a year button below to record completing its JEE Main PYQs:",
            color=embeds.COLOR_PROGRESS,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Log Revision", style=discord.ButtonStyle.secondary, emoji="🔁", row=0)
    async def btn_log_rev(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = RevisionQuickView(interaction.user.id, self.cog)
        embed = embeds.base_embed(
            title="🔁 Log Revision Pass",
            description="Select which complete syllabus revision pass you just concluded:",
            color=embeds.COLOR_PROGRESS,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Refresh Dashboard", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        embed = await self.cog.build_dashboard_embed(self.target_user, interaction.guild_id or 0)
        await interaction.response.edit_message(embed=embed, view=self)


# ==============================================================================
# Cog Implementation
# ==============================================================================

class Progress(commands.Cog, name="Progress"):
    """JEE Command Centre, syllabus tracker, and milestone progress logger."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def log_and_reward_direct(
        self, user_id: int, guild_id: int, type_: str, label: str,
        subject: Optional[str] = None, chapter: Optional[str] = None,
    ) -> tuple[int, int]:
        await self.db.log_milestone(user_id, guild_id, type_, label, subject, chapter=chapter)
        reward = economy.MILESTONE_REWARDS.get(type_, {"coins": 20, "xp": 25})
        await self.db.add_coins(user_id, guild_id, reward["coins"])
        await self.db.grant_xp(user_id, guild_id, reward["xp"])
        log.info(
            f"MILESTONE LOG | User {user_id} logged {type_} '{label}' "
            f"(subject={subject}, chapter={chapter}) in guild {guild_id}"
        )
        return reward["coins"], reward["xp"]

    async def _log_and_reward(
        self, ctx: commands.Context, type_: str, label: str, subject: Optional[str],
        chapter: Optional[str] = None,
    ) -> tuple[int, int]:
        return await self.log_and_reward_direct(ctx.author.id, ctx.guild.id, type_, label, subject, chapter)

    async def _announce_achievements(self, ctx: commands.Context) -> None:
        newly = await self.db.check_achievements(ctx.author.id, ctx.guild.id)
        if newly:
            await ctx.send(embed=embeds.achievement_unlock_embed(ctx.author, newly))

    @staticmethod
    def _resolve_syllabus_subject(subject: str) -> Optional[str]:
        key = normalize_subject_key(subject)
        key = SUBJECT_ALIASES.get(key, key)
        return key if key in SUBJECTS_WITH_SYLLABUS else None

    async def build_dashboard_embed(self, user: discord.User | discord.Member, guild_id: int) -> discord.Embed:
        completed_set = await self.db.get_completed_chapter_names(user.id, guild_id)
        counts = await self.db.get_milestone_counts(user.id, guild_id)

        phy_total = len(syllabus_data.SYLLABUS["physics"])
        chem_total = len(syllabus_data.SYLLABUS["chemistry"])
        math_total = len(syllabus_data.SYLLABUS["maths"])
        total_chaps = phy_total + chem_total + math_total

        phy_done = sum(1 for c in syllabus_data.SYLLABUS["physics"] if c["name"].strip().lower() in completed_set)
        chem_done = sum(1 for c in syllabus_data.SYLLABUS["chemistry"] if c["name"].strip().lower() in completed_set)
        math_done = sum(1 for c in syllabus_data.SYLLABUS["maths"] if c["name"].strip().lower() in completed_set)
        total_done = phy_done + chem_done + math_done

        embed = embeds.base_embed(
            title=f"⚡ JEE Command Centre — {user.display_name}",
            description=(
                f"Track your path to the 99th percentile. Real-time NTA syllabus tracking, "
                f"PYQs cleared, and revision cycles.\n\n"
                f"🏆 **Overall JEE Mastery:** {_make_progress_bar(total_done, total_chaps, 16)}"
            ),
            color=embeds.COLOR_PROGRESS,
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name="⚛️ Physics Syllabus",
            value=_make_progress_bar(phy_done, phy_total, 12),
            inline=False,
        )
        embed.add_field(
            name="🧪 Chemistry Syllabus",
            value=_make_progress_bar(chem_done, chem_total, 12),
            inline=False,
        )
        embed.add_field(
            name="📐 Mathematics Syllabus",
            value=_make_progress_bar(math_done, math_total, 12),
            inline=False,
        )

        stat_lines = [
            f"🎯 **PYQ Years Completed:** `{counts['pyq_years_completed']}`",
            f"🔁 **Revision Passes:** `Pass #{counts['max_revision']}`" if counts["max_revision"] else "🔁 **Revision Passes:** `None yet`",
            f"📚 **Reference Books Finished:** `{counts['books_completed']}`",
            f"🧩 **Subtopics Mastered:** `{counts['subtopics_completed']}`",
        ]
        embed.add_field(name="📋 Prep Metrics", value="\n".join(stat_lines), inline=True)

        recent = await self.db.get_recent_milestones(user.id, guild_id, limit=4)
        if recent:
            type_emoji = {"chapter": "📖", "subtopic": "🧩", "book": "📚", "pyq": "🎯", "revision": "🔁"}
            rlines = []
            for m in recent:
                e = type_emoji.get(m["type"], "•")
                s = f" ({m['subject'].title()})" if m.get("subject") else ""
                rlines.append(f"{e} **{m['label']}**{s}")
            embed.add_field(name="🕒 Recently Logged", value="\n".join(rlines), inline=True)

        embeds.set_footer(
            embed,
            "Use buttons below to log progress, or run .chapterdone / .pyqsdone directly!",
        )
        return embed

    # ------------------------------------------------------------------ #
    # .jee - All-in-one JEE Command Centre
    # ------------------------------------------------------------------ #
    @commands.command(name="jee", aliases=["prep", "tracker", "commandcentre", "jeecommandcentre"])
    @commands.guild_only()
    async def jee_dashboard_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Open the all-in-one JEE Command Centre dashboard."""
        target = member or ctx.author
        embed = await self.build_dashboard_embed(target, ctx.guild.id)
        view = JeeCommandCentreView(ctx.author.id, self, target)
        await ctx.send(embed=embed, view=view)

    # ------------------------------------------------------------------ #
    # .chapterdone - Log a completed chapter
    # ------------------------------------------------------------------ #
    @commands.command(name="chapterdone", aliases=["cdone", "chapdone", "chapter"])
    @commands.guild_only()
    async def chapter_done_cmd(self, ctx: commands.Context, *, args: Optional[str] = None) -> None:
        """Log a completed chapter. Interactive if no arguments given!

        Examples:
          .chapterdone
          .chapterdone physics Rotational Motion
          .chapterdone Rotational Motion
          .chapterdone chem 4
        """
        if not args:
            view = InteractiveChapterSelectorView(ctx.author.id, self, "physics")
            await view.init_data(ctx.guild.id)
            embed = embeds.base_embed(
                title="⚛️ Select Physics Chapter",
                description="Pick the chapter you completed from the dropdown below:",
                color=embeds.COLOR_PROGRESS,
            )
            await ctx.send(embed=embed, view=view)
            return

        parts = args.strip().split(None, 1)
        first_token = parts[0].lower()
        subject_key = self._resolve_syllabus_subject(first_token)

        if subject_key and len(parts) > 1:
            chap_query = parts[1].strip()
        elif subject_key:
            # Only subject given, open selector for that subject
            view = InteractiveChapterSelectorView(ctx.author.id, self, subject_key)
            await view.init_data(ctx.guild.id)
            info = SUBJECT_INFO.get(subject_key, {"emoji": "📖", "label": subject_key.title()})
            embed = embeds.base_embed(
                title=f"{info['emoji']} Select {info['label']} Chapter",
                description=f"Pick the {info['label']} chapter you completed below:",
                color=embeds.COLOR_PROGRESS,
            )
            await ctx.send(embed=embed, view=view)
            return
        else:
            chap_query = args.strip()
            # Smart match across all subjects
            matches = syllabus_data.search_chapter_across_subjects(chap_query)
            if not matches:
                await ctx.send(embed=embeds.error_embed(
                    f"Couldn't find any chapter matching `{chap_query}` in Physics, Chemistry, or Maths.\n"
                    f"Run `{ctx.prefix}chapterdone` with no arguments to pick from the interactive dropdown!"
                ))
                return
            if len(matches) == 1:
                subject_key, chapter_match = matches[0]
            else:
                # Chapter in multiple subjects (e.g. Thermodynamics)
                view = discord.ui.View(timeout=60.0)
                for s, ch in matches:
                    info = SUBJECT_INFO.get(s, {"emoji": "📖", "label": s.title()})
                    btn = discord.ui.Button(label=f"{info['label']} Ch. {ch['number']}", emoji=info["emoji"])

                    async def _btn_cb(interaction: discord.Interaction, sub=s, c=ch):
                        if interaction.user.id != ctx.author.id:
                            await interaction.response.send_message("Not your command.", ephemeral=True)
                            return
                        coins, xp = await self._log_and_reward(ctx, "chapter", c["name"], sub)
                        await interaction.response.edit_message(
                            embed=embeds.success_embed(
                                "🎉 Chapter logged!",
                                f"**{sub.title()} Ch. {c['number']} — {c['name']}** marked complete!\n"
                                f"🪙 +{coins} Chronocoins · ⚡ +{xp} XP",
                            ),
                            view=None,
                        )
                        await self._announce_achievements(ctx)

                    btn.callback = _btn_cb
                    view.add_item(btn)

                await ctx.send(
                    f"`{chap_query}` appears in multiple subjects. Which one did you complete?",
                    view=view,
                )
                return

        match = syllabus_data.find_chapter(subject_key, chap_query)
        if match is None:
            await ctx.send(embed=embeds.error_embed(
                f"`{chap_query}` isn't a recognized {subject_key.title()} chapter.\n"
                f"Run `{ctx.prefix}chapterdone` without arguments to choose interactively!"
            ))
            return

        completed_set = await self.db.get_completed_chapter_names(ctx.author.id, ctx.guild.id)
        is_already_done = match["name"].strip().lower() in completed_set

        coins, xp = await self._log_and_reward(
            ctx,
            "chapter" if not is_already_done else "revision",
            match["name"],
            subject_key,
            chapter=match["name"],
        )

        chaps = syllabus_data.get_chapters(subject_key)
        done_count = sum(1 for c in chaps if c["name"].strip().lower() in completed_set or c["name"] == match["name"])
        bar = _make_progress_bar(done_count, len(chaps))

        title = "🎉 Chapter logged!" if not is_already_done else "🔁 Chapter Revision Logged!"
        desc = (
            f"**{subject_key.title()} Ch. {match['number']} — {match['name']}** marked complete!\n\n"
            f"🪙 **Reward:** `+{coins}` Chronocoins · ⚡ `+{xp}` XP\n"
            f"📊 **{subject_key.title()} Progress:** {bar}\n\n"
            f"*{'First time completion recorded!' if not is_already_done else 'You had already logged this chapter; counted as a revision pass.'}*"
        )
        await ctx.send(embed=embeds.success_embed(title, desc))
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .topicdone - Log a completed subtopic
    # ------------------------------------------------------------------ #
    @commands.command(name="subtopicdone", aliases=["topicdone", "tdone", "subtopic", "topic"])
    @commands.guild_only()
    async def subtopic_done_cmd(self, ctx: commands.Context, *, args: Optional[str] = None) -> None:
        """Log a completed subtopic/topic.

        Examples:
          .topicdone Newton's laws
          .topicdone physics 3 Newton's laws
          .subtopicdone physics "Rotational Motion" Moment of inertia
        """
        if not args:
            await ctx.send(embed=embeds.info_embed(
                "Subtopic Logger",
                "Log any specific subtopic or concept!\n"
                f"Usage: `{ctx.prefix}topicdone <topic name>` or `{ctx.prefix}topicdone <subject> <chapter> <topic>`\n"
                f"Example: `{ctx.prefix}topicdone Newton's laws` or `{ctx.prefix}topicdone physics 5 Moment of inertia`",
            ))
            return

        parts = args.strip().split()
        subject_key = self._resolve_syllabus_subject(parts[0])

        if subject_key and len(parts) >= 3:
            chap_token = parts[1]
            subtopic_query = " ".join(parts[2:])
            chapter_match = syllabus_data.find_chapter(subject_key, chap_token)
            if chapter_match:
                sub_match = syllabus_data.find_subtopic(chapter_match, subtopic_query)
                if sub_match:
                    coins, xp = await self._log_and_reward(
                        ctx, "subtopic", sub_match, subject_key, chapter=chapter_match["name"]
                    )
                    await ctx.send(embed=embeds.success_embed(
                        "🧩 Subtopic logged!",
                        f"**{sub_match}** ({chapter_match['name']}, {subject_key.title()}) marked complete.\n"
                        f"🪙 +{coins} Chronocoins · ⚡ +{xp} XP",
                    ))
                    await self._announce_achievements(ctx)
                    return

        # Smart search across all chapters
        matches = syllabus_data.search_subtopic_across_subjects(args.strip())
        if not matches:
            await ctx.send(embed=embeds.error_embed(
                f"Couldn't match `{args.strip()}` to a listed syllabus subtopic.\n"
                f"Check `{ctx.prefix}syllabus` to see standard chapter topics!"
            ))
            return

        sub_key, ch_dict, matched_topic = matches[0]
        coins, xp = await self._log_and_reward(
            ctx, "subtopic", matched_topic, sub_key, chapter=ch_dict["name"]
        )
        await ctx.send(embed=embeds.success_embed(
            "🧩 Subtopic logged!",
            f"**{matched_topic}** ({ch_dict['name']}, {sub_key.title()}) marked complete.\n"
            f"🪙 +{coins} Chronocoins · ⚡ +{xp} XP",
        ))
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .pyq - Log completed PYQ years
    # ------------------------------------------------------------------ #
    @commands.command(name="pyq", aliases=["pyqdone", "pyqs", "pyqsdone"])
    @commands.guild_only()
    async def pyq_cmd(self, ctx: commands.Context, year: Optional[str] = None, subject: Optional[str] = None) -> None:
        """Log a completed year of JEE Main PYQs.

        Examples:
          .pyq
          .pyq 2024
          .pyqsdone 2023 physics
        """
        if not year:
            view = PyqQuickView(ctx.author.id, self, _normalize_subject(subject))
            embed = embeds.base_embed(
                title="🎯 Select PYQ Year",
                description="Click one of the recent JEE Main years below to log your solved paper:",
                color=embeds.COLOR_PROGRESS,
            )
            await ctx.send(embed=embed, view=view)
            return

        if not year.isdigit() or not (1990 <= int(year) <= 2100):
            await ctx.send(embed=embeds.error_embed("Please provide a valid 4-digit year (e.g. `.pyq 2024`)."))
            return

        norm_subject = _normalize_subject(subject)
        coins, xp = await self._log_and_reward(ctx, "pyq", year, norm_subject)
        subj_text = f" ({norm_subject})" if norm_subject else ""
        await ctx.send(embed=embeds.success_embed(
            "🎯 PYQ Year logged!",
            f"**JEE Main {year}**{subj_text} marked complete.\n"
            f"🪙 +{coins} Chronocoins · ⚡ +{xp} XP",
        ))
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .revision - Log revision cycles
    # ------------------------------------------------------------------ #
    @commands.command(name="revision", aliases=["rev", "revisiondone", "revdone"])
    @commands.guild_only()
    async def revision_cmd(self, ctx: commands.Context, number: Optional[str] = None, subject: Optional[str] = None) -> None:
        """Log a completed revision pass.

        Examples:
          .revision
          .revision 1
          .revision 2 maths
        """
        if not number:
            view = RevisionQuickView(ctx.author.id, self, _normalize_subject(subject))
            embed = embeds.base_embed(
                title="🔁 Log Revision Pass",
                description="Click a pass button below to record your syllabus revision:",
                color=embeds.COLOR_PROGRESS,
            )
            await ctx.send(embed=embed, view=view)
            return

        if not number.isdigit() or int(number) <= 0:
            await ctx.send(embed=embeds.error_embed("Give a revision number (e.g. `.revision 1` or `.revision 2 maths`)."))
            return

        norm_subject = _normalize_subject(subject)
        coins, xp = await self._log_and_reward(ctx, "revision", number, norm_subject)
        ordinal = {"1": "1st", "2": "2nd", "3": "3rd", "4": "4th", "5": "5th"}.get(number, f"{number}th")
        subj_text = f" ({norm_subject})" if norm_subject else ""
        await ctx.send(embed=embeds.success_embed(
            "🔁 Revision logged!",
            f"**{ordinal} Complete Revision**{subj_text} marked complete.\n"
            f"🪙 +{coins} Chronocoins · ⚡ +{xp} XP",
        ))
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .bookdone - Log finished reference books
    # ------------------------------------------------------------------ #
    @commands.command(name="bookdone", aliases=["bdone", "book", "books"])
    @commands.guild_only()
    async def book_done_cmd(self, ctx: commands.Context, *, book: Optional[str] = None) -> None:
        """Log a completed reference book.

        Examples:
          .bookdone
          .bookdone HC Verma Concepts of Physics
          .bookdone MS Chouhan Organic Chemistry
        """
        if not book:
            options = []
            for bname, bsub in POPULAR_JEE_BOOKS[:25]:
                emoji = "⚛️" if bsub == "physics" else ("🧪" if bsub == "chemistry" else "📐")
                options.append(discord.SelectOption(label=bname[:95], value=bname[:95], emoji=emoji))

            select = discord.ui.Select(placeholder="📚 Select a popular JEE book...", options=options)
            view = discord.ui.View(timeout=120.0)

            async def _select_cb(interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Not your command.", ephemeral=True)
                    return
                chosen = select.values[0]
                coins, xp = await self._log_and_reward(ctx, "book", chosen, None)
                await interaction.response.edit_message(
                    embed=embeds.success_embed(
                        "📚 Book Logged!",
                        f"**{chosen}** marked complete.\n🪙 +{coins} Chronocoins · ⚡ +{xp} XP",
                    ),
                    view=None,
                )
                await self._announce_achievements(ctx)

            select.callback = _select_cb
            view.add_item(select)
            embed = embeds.base_embed(
                title="📚 Select Completed Reference Book",
                description="Pick from popular JEE prep classics, or type `.bookdone <book name>`:",
                color=embeds.COLOR_PROGRESS,
            )
            await ctx.send(embed=embed, view=view)
            return

        coins, xp = await self._log_and_reward(ctx, "book", book.strip(), None)
        await ctx.send(embed=embeds.success_embed(
            "📚 Book Logged!",
            f"**{book.strip()}** marked complete.\n🪙 +{coins} Chronocoins · ⚡ +{xp} XP",
        ))
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .syllabus - Browse the JEE Main syllabus
    # ------------------------------------------------------------------ #
    @commands.command(name="syllabus", aliases=["syl"])
    async def syllabus_cmd(self, ctx: commands.Context, subject: Optional[str] = None, *, chapter: Optional[str] = None) -> None:
        """Browse the JEE Main syllabus reference."""
        if subject is None:
            embed = embeds.base_embed(
                title="📚 JEE Main Official Syllabus",
                description=(
                    "Reference copy of the NTA JEE Main syllabus.\n"
                    f"Pick a subject: `{ctx.prefix}syllabus physics`, `{ctx.prefix}syllabus chemistry`, `{ctx.prefix}syllabus maths`\n"
                    f"Shorthands work too: `{ctx.prefix}syl phy`, `{ctx.prefix}syl chem`, `{ctx.prefix}syl math`"
                ),
                color=embeds.COLOR_PROGRESS,
            )
            for key in SUBJECTS_WITH_SYLLABUS:
                info = SUBJECT_INFO.get(key, {"emoji": "📖", "label": key.title()})
                embed.add_field(
                    name=f"{info['emoji']} {info['label']}",
                    value=f"{len(syllabus_data.SYLLABUS[key])} chapters",
                    inline=True,
                )
            await ctx.send(embed=embed)
            return

        subject_key = self._resolve_syllabus_subject(subject)
        if subject_key is None:
            await ctx.send(embed=embeds.error_embed(f"Unknown subject `{subject}`. {SUBJECT_HINT}"))
            return

        info = SUBJECT_INFO.get(subject_key, {"emoji": "📖", "label": subject_key.title()})

        if chapter is None:
            chapters = syllabus_data.get_chapters(subject_key)
            lines = [f"**{i}.** {ch['name']}" for i, ch in enumerate(chapters, start=1)]
            embed = embeds.base_embed(
                title=f"{info['emoji']} {info['label']} — Syllabus ({len(chapters)} chapters)",
                description="\n".join(lines),
                color=embeds.COLOR_PROGRESS,
            )
            embeds.set_footer(embed, f"{ctx.prefix}syllabus {subject_key} <number> for subtopics")
            await ctx.send(embed=embed)
            return

        match = syllabus_data.find_chapter(subject_key, chapter)
        if match is None:
            await ctx.send(embed=embeds.error_embed(
                f"Couldn't find that chapter. Run `{ctx.prefix}syllabus {subject_key}` to see the numbered list."
            ))
            return

        topic_lines = [f"**{i}.** {t}" for i, t in enumerate(match["topics"], start=1)]
        embed = embeds.base_embed(
            title=f"{info['emoji']} {subject_key.title()} Ch. {match['number']} — {match['name']}",
            description="\n".join(topic_lines) if topic_lines else "No subtopics listed.",
            color=embeds.COLOR_PROGRESS,
        )
        embeds.set_footer(
            embed,
            f"{ctx.prefix}chapterdone {subject_key} {match['number']}",
            f"{ctx.prefix}subtopicdone {subject_key} {match['number']} <subtopic>",
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # .progress - Detailed overview
    # ------------------------------------------------------------------ #
    @commands.command(name="progress")
    @commands.guild_only()
    async def progress_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """See logged chapters/subtopics/books/PYQs/revisions for you (or someone else)."""
        target = member or ctx.author
        embed = await self.build_dashboard_embed(target, ctx.guild.id)
        view = JeeCommandCentreView(ctx.author.id, self, target)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Progress(bot))
