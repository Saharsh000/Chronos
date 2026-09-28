"""Manually-logged study progress: chapter/subtopic completions
(validated against the JEE Main syllabus - see utils/syllabus.py),
book completions, PYQ (previous-year-questions) years, and revision
passes.

Chapters and subtopics can *only* be logged from the syllabus list -
`.chapterdone`/`.subtopicdone` reject anything that doesn't match a
real chapter, so progress stays tied to the actual syllabus rather
than arbitrary free text. Books/PYQs/revisions stay free text since
they aren't syllabus-structured the same way.

Each log also earns a flat coin+XP reward (utils/economy.py
MILESTONE_REWARDS) since it represents real study effort.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.ext import commands

from utils import economy, embeds
from utils import syllabus as syllabus_data
from utils.subjects import SUBJECT_ALIASES, SUBJECT_INFO

log = logging.getLogger("progress")

SUBJECTS_WITH_SYLLABUS = tuple(syllabus_data.SYLLABUS.keys())


def _normalize_subject(text: Optional[str]) -> Optional[str]:
    """Best-effort match against the Physics/Chemistry/Maths aliases;
    anything else is kept as free text (title-cased)."""
    if not text:
        return None
    key = text.strip().lower()
    return SUBJECT_ALIASES.get(key, text.strip().title())


class Progress(commands.Cog, name="Progress"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    async def _log_and_reward(
        self, ctx: commands.Context, type_: str, label: str, subject: Optional[str],
        chapter: Optional[str] = None,
    ) -> tuple[int, int]:
        await self.db.log_milestone(ctx.author.id, ctx.guild.id, type_, label, subject, chapter=chapter)
        reward = economy.MILESTONE_REWARDS[type_]
        await self.db.add_coins(ctx.author.id, ctx.guild.id, reward["coins"])
        xp_result = await self.db.grant_xp(ctx.author.id, ctx.guild.id, reward["xp"])
        log.info(
            f"MILESTONE LOG | {ctx.author} ({ctx.author.id}) logged {type_} '{label}' "
            f"(subject={subject}, chapter={chapter}) in guild {ctx.guild.id}"
        )
        return reward["coins"], reward["xp"]

    async def _announce_achievements(self, ctx: commands.Context) -> None:
        newly = await self.db.check_achievements(ctx.author.id, ctx.guild.id)
        if newly:
            await ctx.send(embed=embeds.achievement_unlock_embed(ctx.author, newly))

    @staticmethod
    def _resolve_syllabus_subject(subject: str) -> Optional[str]:
        key = subject.strip().lower()
        key = SUBJECT_ALIASES.get(key, key)
        return key if key in SUBJECTS_WITH_SYLLABUS else None

    # ------------------------------------------------------------------ #
    # .syllabus - browse the JEE Main syllabus reference
    # ------------------------------------------------------------------ #
    @commands.command(name="syllabus", aliases=["syl"])
    async def syllabus_cmd(self, ctx: commands.Context, subject: Optional[str] = None, *, chapter: Optional[str] = None) -> None:
        """Browse the JEE Main syllabus.

        `.syllabus` - list subjects
        `.syllabus physics` - list all Physics chapters (numbered)
        `.syllabus physics 5` - show chapter 5's subtopics
        """
        if subject is None:
            embed = embeds.base_embed(
                title="\U0001F4DA JEE Main Syllabus",
                description=(
                    "A reference copy of the JEE Main syllabus, used to validate `.chapterdone`/`.subtopicdone`.\n"
                    f"Pick a subject: `{ctx.prefix}syllabus physics`, `{ctx.prefix}syllabus chemistry`, "
                    f"`{ctx.prefix}syllabus maths`"
                ),
                color=embeds.COLOR_PRIMARY,
            )
            for key in SUBJECTS_WITH_SYLLABUS:
                info = SUBJECT_INFO.get(key, {"emoji": "\U0001F4D6", "label": key.title()})
                embed.add_field(
                    name=f"{info['emoji']} {info['label']}",
                    value=f"{len(syllabus_data.SYLLABUS[key])} chapters",
                    inline=True,
                )
            await ctx.send(embed=embed)
            return

        subject_key = self._resolve_syllabus_subject(subject)
        if subject_key is None:
            await ctx.send(embed=embeds.error_embed(
                f"Unknown subject `{subject}`. Try `physics`, `chemistry`, or `maths`."
            ))
            return

        info = SUBJECT_INFO.get(subject_key, {"emoji": "\U0001F4D6", "label": subject_key.title()})

        if chapter is None:
            chapters = syllabus_data.get_chapters(subject_key)
            lines = [f"**{i}.** {ch['name']}" for i, ch in enumerate(chapters, start=1)]
            embed = embeds.base_embed(
                title=f"{info['emoji']} {info['label']} \u2014 Syllabus ({len(chapters)} chapters)",
                description="\n".join(lines),
                color=embeds.COLOR_PRIMARY,
            )
            embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 {ctx.prefix}syllabus {subject_key} <number> for subtopics")
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
            title=f"{info['emoji']} {subject_key.title()} Ch. {match['number']} \u2014 {match['name']}",
            description="\n".join(topic_lines) if topic_lines else "No subtopics listed.",
            color=embeds.COLOR_PRIMARY,
        )
        embed.set_footer(
            text=f"{ctx.prefix}chapterdone {subject_key} {match['number']}  \u2022  "
                 f"{ctx.prefix}subtopicdone {subject_key} {match['number']} <subtopic>"
        )
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # Chapters & subtopics (syllabus-validated only)
    # ------------------------------------------------------------------ #
    @commands.command(name="chapterdone", aliases=["chapter"])
    @commands.guild_only()
    async def chapter_done_cmd(self, ctx: commands.Context, subject: str, *, chapter: str) -> None:
        """Log a completed chapter - must match the JEE syllabus (see `.syllabus`).

        Usage: `.chapterdone physics Rotational Motion` or `.chapterdone physics 5`
        """
        subject_key = self._resolve_syllabus_subject(subject)
        if subject_key is None:
            await ctx.send(embed=embeds.error_embed(
                f"Unknown subject `{subject}`. Try `physics`, `chemistry`, or `maths`."
            ))
            return

        match = syllabus_data.find_chapter(subject_key, chapter)
        if match is None:
            await ctx.send(embed=embeds.error_embed(
                f"`{chapter}` isn't a recognized {subject_key} chapter. Chapters can only be logged from the "
                f"official syllabus - run `{ctx.prefix}syllabus {subject_key}` to see the numbered list."
            ))
            return

        coins, xp = await self._log_and_reward(ctx, "chapter", match["name"], subject_key)
        await ctx.send(embed=embeds.success_embed(
            "\U0001F4D1 Chapter logged!",
            f"**{subject_key.title()} Ch. {match['number']} \u2014 {match['name']}** marked complete. "
            f"+{coins} coins, +{xp} XP.",
        ))
        await self._announce_achievements(ctx)

    @commands.command(name="subtopicdone", aliases=["subtopic", "sub"])
    @commands.guild_only()
    async def subtopic_done_cmd(self, ctx: commands.Context, subject: str, chapter: str, *, subtopic: str) -> None:
        """Log a completed subtopic within a chapter - both must match the syllabus.

        Usage: `.subtopicdone physics 5 Moment of inertia` or `.subtopicdone physics "Rotational Motion" 2`
        """
        subject_key = self._resolve_syllabus_subject(subject)
        if subject_key is None:
            await ctx.send(embed=embeds.error_embed(
                f"Unknown subject `{subject}`. Try `physics`, `chemistry`, or `maths`."
            ))
            return

        chapter_match = syllabus_data.find_chapter(subject_key, chapter)
        if chapter_match is None:
            await ctx.send(embed=embeds.error_embed(
                f"`{chapter}` isn't a recognized {subject_key} chapter. Run `{ctx.prefix}syllabus {subject_key}` "
                f"to see the numbered list."
            ))
            return

        subtopic_match = syllabus_data.find_subtopic(chapter_match, subtopic)
        if subtopic_match is None:
            await ctx.send(embed=embeds.error_embed(
                f"`{subtopic}` isn't a listed subtopic of **{chapter_match['name']}**. Run "
                f"`{ctx.prefix}syllabus {subject_key} {chapter_match['number']}` to see the numbered list."
            ))
            return

        coins, xp = await self._log_and_reward(
            ctx, "subtopic", subtopic_match, subject_key, chapter=chapter_match["name"]
        )
        await ctx.send(embed=embeds.success_embed(
            "\U0001F9E9 Subtopic logged!",
            f"**{subtopic_match}** ({chapter_match['name']}, {subject_key.title()}) marked complete. "
            f"+{coins} coins, +{xp} XP.",
        ))
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # Books, PYQs, revisions (free text - not syllabus-chapter-shaped)
    # ------------------------------------------------------------------ #
    @commands.command(name="bookdone", aliases=["book"])
    @commands.guild_only()
    async def book_done_cmd(self, ctx: commands.Context, subject: str, *, book: str) -> None:
        """Log a completed book. Usage: `.bookdone chemistry NCERT Organic Chemistry`"""
        norm_subject = _normalize_subject(subject)
        coins, xp = await self._log_and_reward(ctx, "book", book, norm_subject)
        await ctx.send(embed=embeds.success_embed(
            "\U0001F4D7 Book logged!",
            f"**{book}** ({norm_subject}) marked complete. +{coins} coins, +{xp} XP.",
        ))
        await self._announce_achievements(ctx)

    @commands.command(name="pyq")
    @commands.guild_only()
    async def pyq_cmd(self, ctx: commands.Context, year: str, subject: Optional[str] = None) -> None:
        """Log a completed year of PYQs (previous-year questions).
        Usage: `.pyq 2023` or `.pyq 2023 physics`"""
        if not year.isdigit() or not (1990 <= int(year) <= 2100):
            await ctx.send(embed=embeds.error_embed("Give a 4-digit year, e.g. `.pyq 2023` or `.pyq 2023 physics`."))
            return
        norm_subject = _normalize_subject(subject)
        coins, xp = await self._log_and_reward(ctx, "pyq", year, norm_subject)
        subj_text = f" ({norm_subject})" if norm_subject else ""
        await ctx.send(embed=embeds.success_embed(
            "\U0001F4DD PYQ logged!",
            f"**{year}**{subj_text} marked complete. +{coins} coins, +{xp} XP.",
        ))
        await self._announce_achievements(ctx)

    @commands.command(name="revision", aliases=["rev"])
    @commands.guild_only()
    async def revision_cmd(self, ctx: commands.Context, number: str, subject: Optional[str] = None) -> None:
        """Log a completed revision pass. Usage: `.revision 1` or `.revision 2 maths`"""
        if not number.isdigit() or int(number) <= 0:
            await ctx.send(embed=embeds.error_embed("Give a revision number, e.g. `.revision 1` or `.revision 2 maths`."))
            return
        norm_subject = _normalize_subject(subject)
        coins, xp = await self._log_and_reward(ctx, "revision", number, norm_subject)
        ordinal = {"1": "1st", "2": "2nd", "3": "3rd"}.get(number, f"{number}th")
        subj_text = f" ({norm_subject})" if norm_subject else ""
        await ctx.send(embed=embeds.success_embed(
            "\U0001F501 Revision logged!",
            f"{ordinal} revision{subj_text} marked complete. +{coins} coins, +{xp} XP.",
        ))
        await self._announce_achievements(ctx)

    # ------------------------------------------------------------------ #
    # .progress - summary view
    # ------------------------------------------------------------------ #
    @commands.command(name="progress")
    @commands.guild_only()
    async def progress_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """See logged chapters/subtopics/books/PYQs/revisions for you (or someone else)."""
        target = member or ctx.author
        counts = await self.db.get_milestone_counts(target.id, ctx.guild.id)

        embed = embeds.base_embed(title=f"\U0001F4C8 Study Progress \u2014 {target.display_name}", color=embeds.COLOR_PRIMARY)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="\U0001F4D1 Chapters Completed",
            value=f"{counts['chapters_completed']} / {sum(len(v) for v in syllabus_data.SYLLABUS.values())}",
            inline=True,
        )
        embed.add_field(name="\U0001F9E9 Subtopics Completed", value=str(counts["subtopics_completed"]), inline=True)
        embed.add_field(name="\U0001F4D7 Books Completed", value=str(counts["books_completed"]), inline=True)
        embed.add_field(name="\U0001F4DD PYQ Years Done", value=str(counts["pyq_years_completed"]), inline=True)
        embed.add_field(
            name="\U0001F501 Revisions",
            value=f"Up to revision {counts['max_revision']}" if counts["max_revision"] else "None yet",
            inline=True,
        )

        recent = await self.db.get_recent_milestones(target.id, ctx.guild.id, limit=5)
        if recent:
            type_emoji = {"chapter": "\U0001F4D1", "subtopic": "\U0001F9E9", "book": "\U0001F4D7", "pyq": "\U0001F4DD", "revision": "\U0001F501"}
            lines = []
            for m in recent:
                subj = f" ({m['subject']})" if m["subject"] else ""
                chap = f" \u2014 {m['chapter']}" if m.get("chapter") else ""
                lines.append(f"{type_emoji.get(m['type'], '\u2022')} {m['label']}{chap}{subj}")
            embed.add_field(name="Recently Logged", value="\n".join(lines), inline=False)

        embed.set_footer(text=f"{embeds.FOOTER_TEXT} \u2022 {ctx.prefix}syllabus \u2022 .chapterdone / .subtopicdone / .bookdone / .pyq / .revision")
        await ctx.send(embed=embed)

    @chapter_done_cmd.error
    @subtopic_done_cmd.error
    @book_done_cmd.error
    @pyq_cmd.error
    @revision_cmd.error
    async def progress_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            usage = {
                "chapterdone": ".chapterdone <subject> <chapter name or number>",
                "subtopicdone": ".subtopicdone <subject> <chapter> <subtopic name or number>",
                "bookdone": ".bookdone <subject> <book name>",
                "pyq": ".pyq <year> [subject]",
                "revision": ".revision <number> [subject]",
            }.get(ctx.command.name, f".{ctx.command.name} <...>")
            await ctx.send(embed=embeds.error_embed(f"Usage: `{usage}`"))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(embed=embeds.error_embed("That command only works inside a server."))
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Progress(bot))
