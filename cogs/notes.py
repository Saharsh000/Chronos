"""Chronotes - The Ultimate In-Discord Study Notebook Suite.

Inspired by Samsung Notes, Apple Notes, and Notion:
- Interactive dashboard with modal text input (full markdown notes & formulas).
- Support for image attachments (diagrams, formula sheets, handwritten notes).
- High-resolution PIL visual index cards (1200x680 HD).
- Instant filtering by subject (Physics, Chemistry, Maths, Formulas, Revision, General).
- Pinned notes, live search, and full Markdown (.md) notebook export.
"""
from __future__ import annotations

import io
import time
from typing import Any, Optional

import discord
from discord.ext import commands

from utils import embeds, stats_card, streaks

SUBJECT_OPTIONS = [
    ("All Subjects", "all", "🌐"),
    ("Physics", "physics", "⚛️"),
    ("Chemistry", "chemistry", "🧪"),
    ("Mathematics", "mathematics", "📐"),
    ("Formulas & Shortcuts", "formulas", "⚡"),
    ("Revision Checklist", "revision", "🔁"),
    ("General Notes", "general", "📝"),
]


class CreateNoteModal(discord.ui.Modal, title="📝 Chronotes · New Note"):
    note_title = discord.ui.TextInput(
        label="Note Title",
        placeholder="e.g. Rotational Mechanics Important Formulas",
        min_length=1,
        max_length=80,
    )
    subject = discord.ui.TextInput(
        label="Subject / Category",
        placeholder="Physics / Chem / Maths / Formulas / Revision / General",
        default="General",
        min_length=1,
        max_length=30,
        required=False,
    )
    content = discord.ui.TextInput(
        label="Note Content (Markdown & Formulas Supported)",
        style=discord.TextStyle.paragraph,
        placeholder="Write your study notes, key equations, concepts, or reminders here...",
        min_length=1,
        max_length=3500,
    )

    def __init__(self, cog: "Notes", parent_view: Optional["ChronotesHubView"] = None):
        super().__init__()
        self.cog = cog
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = self.note_title.value.strip()
        sub = self.subject.value.strip().title() or "General"
        text = self.content.value.strip()

        note_id = await self.cog.db.create_note(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            title=title,
            content=text,
            subject=sub,
        )

        note = await self.cog.db.get_note_by_id(note_id, interaction.user.id)
        if not note:
            await interaction.response.send_message("Note created successfully!", ephemeral=True)
            return

        reader_view = NoteReaderView(interaction.user.id, self.cog, note)
        embed = self.cog.build_note_embed(note, interaction.user)
        await interaction.response.send_message(
            f"✅ **Saved to Chronotes!** (Note `#{note_id}`)",
            embed=embed,
            view=reader_view,
            ephemeral=True,
        )


class EditNoteModal(discord.ui.Modal, title="✏️ Chronotes · Edit Note"):
    def __init__(self, cog: "Notes", note: dict[str, Any], reader_view: "NoteReaderView"):
        super().__init__()
        self.cog = cog
        self.note = note
        self.reader_view = reader_view

        self.note_title = discord.ui.TextInput(
            label="Note Title",
            default=note["title"],
            min_length=1,
            max_length=80,
        )
        self.subject = discord.ui.TextInput(
            label="Subject / Category",
            default=note["subject"],
            min_length=1,
            max_length=30,
            required=False,
        )
        self.content = discord.ui.TextInput(
            label="Note Content",
            style=discord.TextStyle.paragraph,
            default=note["content"],
            min_length=1,
            max_length=3500,
        )

        self.add_item(self.note_title)
        self.add_item(self.subject)
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = self.note_title.value.strip()
        sub = self.subject.value.strip().title() or "General"
        text = self.content.value.strip()

        await self.cog.db.update_note(
            note_id=self.note["note_id"],
            user_id=interaction.user.id,
            title=title,
            content=text,
            subject=sub,
        )

        updated = await self.cog.db.get_note_by_id(self.note["note_id"], interaction.user.id)
        if updated:
            self.reader_view.note = updated
            embed = self.cog.build_note_embed(updated, interaction.user)
            await interaction.response.edit_message(embed=embed, view=self.reader_view)
        else:
            await interaction.response.send_message("Note updated!", ephemeral=True)


class SearchNoteModal(discord.ui.Modal, title="🔍 Chronotes · Search"):
    query = discord.ui.TextInput(
        label="Search Query",
        placeholder="Enter keyword or concept (e.g. Bernoulli, thermodynamics, limits)...",
        min_length=1,
        max_length=50,
    )

    def __init__(self, cog: "Notes", hub_view: "ChronotesHubView"):
        super().__init__()
        self.cog = cog
        self.hub_view = hub_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        q = self.query.value.strip()
        notes = await self.cog.db.get_user_notes(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            search=q,
        )
        embed = await self.cog.build_hub_embed(interaction.user, interaction.guild_id or 0, notes=notes, search_query=q)
        view = ChronotesHubView(interaction.user.id, self.cog, notes, search_query=q)
        await interaction.response.edit_message(embed=embed, view=view)


class NoteSelect(discord.ui.Select):
    def __init__(self, notes: list[dict[str, Any]]):
        options = []
        for n in notes[:25]:
            pin = "📌 " if n.get("is_pinned") else ""
            title = n["title"][:70]
            label = f"{pin}{title}"[:95]
            sub = n.get("subject", "General")
            date_s = streaks.date_str(n["updated_at"])
            desc = f"[{sub}] • {date_s}"[:100]
            options.append(discord.SelectOption(label=label, value=str(n["note_id"]), description=desc))

        super().__init__(
            placeholder="📖 Select a note to read or edit...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ChronotesHubView = self.view  # type: ignore
        note_id = int(self.values[0])
        note = await view.cog.db.get_note_by_id(note_id, interaction.user.id)
        if not note:
            await interaction.response.send_message("That note could not be found.", ephemeral=True)
            return

        embed = view.cog.build_note_embed(note, interaction.user)
        reader = NoteReaderView(interaction.user.id, view.cog, note, parent_view=view)
        await interaction.response.edit_message(embed=embed, view=reader)


class SubjectFilterSelect(discord.ui.Select):
    def __init__(self, active_sub: str = "all"):
        options = []
        for name, key, emoji in SUBJECT_OPTIONS:
            options.append(discord.SelectOption(
                label=name,
                value=key,
                emoji=emoji,
                default=(key == active_sub),
            ))

        super().__init__(
            placeholder="🏷️ Filter by Subject / Category...",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ChronotesHubView = self.view  # type: ignore
        chosen = self.values[0]
        notes = await view.cog.db.get_user_notes(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            subject=chosen if chosen != "all" else None,
            pinned_only=view.pinned_only,
        )
        embed = await view.cog.build_hub_embed(
            interaction.user, interaction.guild_id or 0, notes=notes, active_subject=chosen, pinned_only=view.pinned_only
        )
        new_view = ChronotesHubView(
            interaction.user.id, view.cog, notes, active_subject=chosen, pinned_only=view.pinned_only
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class ChronotesHubView(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        cog: "Notes",
        notes: list[dict[str, Any]],
        active_subject: str = "all",
        pinned_only: bool = False,
        search_query: Optional[str] = None,
    ):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.cog = cog
        self.notes = notes
        self.active_subject = active_subject
        self.pinned_only = pinned_only
        self.search_query = search_query

        if notes:
            self.add_item(NoteSelect(notes))
        self.add_item(SubjectFilterSelect(active_subject))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the notebook owner can interact with this view.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="New Note", style=discord.ButtonStyle.success, emoji="➕", row=2)
    async def btn_new(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(CreateNoteModal(self.cog, self))

    @discord.ui.button(label="Pinned Only", style=discord.ButtonStyle.secondary, emoji="📌", row=2)
    async def btn_pinned(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.pinned_only = not self.pinned_only
        notes = await self.cog.db.get_user_notes(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            subject=self.active_subject if self.active_subject != "all" else None,
            pinned_only=self.pinned_only,
        )
        embed = await self.cog.build_hub_embed(
            interaction.user, interaction.guild_id or 0, notes=notes, active_subject=self.active_subject, pinned_only=self.pinned_only
        )
        new_view = ChronotesHubView(
            interaction.user.id, self.cog, notes, active_subject=self.active_subject, pinned_only=self.pinned_only
        )
        await interaction.response.edit_message(embed=embed, view=new_view)

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary, emoji="🔍", row=2)
    async def btn_search(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SearchNoteModal(self.cog, self))

    @discord.ui.button(label="Export Notebook", style=discord.ButtonStyle.secondary, emoji="📤", row=2)
    async def btn_export(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        all_notes = await self.cog.db.get_user_notes(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            limit=500,
        )
        if not all_notes:
            await interaction.response.send_message("You have no notes to export yet!", ephemeral=True)
            return

        lines = [f"# 📓 Chronotes Notebook — {interaction.user.display_name}\n\nExported on {streaks.date_str(int(time.time()))} (IST)\n\n---\n"]
        for n in all_notes:
            pin = "📌 " if n.get("is_pinned") else ""
            date_s = streaks.date_str(n["updated_at"])
            lines.append(f"## {pin}{n['title']}\n")
            lines.append(f"**Category:** {n['subject']} | **Date:** {date_s}\n\n")
            if n.get("image_url"):
                lines.append(f"![Attached Image]({n['image_url']})\n\n")
            lines.append(f"{n['content']}\n\n---\n")

        md_content = "\n".join(lines).encode("utf-8")
        file = discord.File(io.BytesIO(md_content), filename="Chronotes_Notebook.md")
        await interaction.response.send_message(
            content="📤 **Here is your full Chronotes notebook export:**",
            file=file,
            ephemeral=True,
        )


class NoteReaderView(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        cog: "Notes",
        note: dict[str, Any],
        parent_view: Optional[ChronotesHubView] = None,
    ):
        super().__init__(timeout=300.0)
        self.author_id = author_id
        self.cog = cog
        self.note = note
        self.parent_view = parent_view

        pin_label = "Unpin" if note.get("is_pinned") else "Pin"
        self.btn_pin.label = pin_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the note owner can interact with this view.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Pin", style=discord.ButtonStyle.secondary, emoji="📌", row=0)
    async def btn_pin(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        new_pinned = 0 if self.note.get("is_pinned") else 1
        await self.cog.db.update_note(self.note["note_id"], interaction.user.id, is_pinned=new_pinned)
        self.note["is_pinned"] = new_pinned
        button.label = "Unpin" if new_pinned else "Pin"
        embed = self.cog.build_note_embed(self.note, interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(EditNoteModal(self.cog, self.note, self))

    @discord.ui.button(label="Visual Card", style=discord.ButtonStyle.success, emoji="🎨", row=0)
    async def btn_visual(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=False)
        date_s = streaks.date_str(self.note["updated_at"])
        png_bytes = stats_card.render_note_card_sync(
            title=self.note["title"],
            subject=self.note["subject"],
            content=self.note["content"],
            author_name=interaction.user.display_name,
            date_str=date_s,
            is_pinned=bool(self.note.get("is_pinned")),
            note_id=self.note["note_id"],
        )
        file = discord.File(io.BytesIO(png_bytes), filename="chronote_card.png")
        await interaction.followup.send(file=file)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.db.delete_note(self.note["note_id"], interaction.user.id)
        notes = await self.cog.db.get_user_notes(interaction.user.id, interaction.guild_id or 0)
        embed = await self.cog.build_hub_embed(interaction.user, interaction.guild_id or 0, notes=notes)
        view = ChronotesHubView(interaction.user.id, self.cog, notes)
        await interaction.response.edit_message(content="🗑️ **Note deleted.**", embed=embed, view=view)

    @discord.ui.button(label="Back to Notes Hub", style=discord.ButtonStyle.secondary, emoji="◀", row=0)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        notes = await self.cog.db.get_user_notes(interaction.user.id, interaction.guild_id or 0)
        embed = await self.cog.build_hub_embed(interaction.user, interaction.guild_id or 0, notes=notes)
        view = ChronotesHubView(interaction.user.id, self.cog, notes)
        await interaction.response.edit_message(content=None, embed=embed, view=view)


class Notes(commands.Cog, name="Chronotes"):
    """In-Discord study notebook with text, formulas, images, and visual cards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    def build_note_embed(self, note: dict[str, Any], user: discord.User | discord.Member) -> discord.Embed:
        pin = "📌 " if note.get("is_pinned") else ""
        date_s = streaks.date_str(note["updated_at"])
        sub = note.get("subject", "General")

        embed = embeds.base_embed(
            title=f"{pin}{note['title']}",
            description=note["content"],
            color=embeds.COLOR_STUDY,
        )
        embed.set_author(name=f"{user.display_name}'s Chronotes", icon_url=user.display_avatar.url)
        embed.add_field(name="📚 Category", value=f"`{sub}`", inline=True)
        embed.add_field(name="🗓️ Saved", value=f"`{date_s}`", inline=True)
        embed.add_field(name="🆔 Note ID", value=f"`#{note['note_id']}`", inline=True)

        if note.get("image_url"):
            embed.set_image(url=note["image_url"])

        embeds.set_footer(embed, "Chronotes · Use buttons below to edit, pin, render visual card or delete")
        return embed

    async def build_hub_embed(
        self,
        user: discord.User | discord.Member,
        guild_id: int,
        notes: list[dict[str, Any]],
        active_subject: str = "all",
        pinned_only: bool = False,
        search_query: Optional[str] = None,
    ) -> discord.Embed:
        stats = await self.db.get_note_stats(user.id, guild_id)
        total = stats["total"]
        pinned = stats["pinned"]

        title = f"📓 Chronotes Hub — {user.display_name}"
        desc_lines = [
            f"Welcome to your private study notebook! Store formulas, concept notes, "
            f"mistake logs, and diagrams with easy interactive tools.\n",
            f"📊 **Stats:** `{total}` Total Notes  •  `{pinned}` Pinned  •  Filter: `{active_subject.upper()}`",
        ]

        if search_query:
            desc_lines.append(f"🔍 **Search Filter:** `{search_query}` (found {len(notes)} note{'s' if len(notes) != 1 else ''})")
        elif pinned_only:
            desc_lines.append(f"📌 **Showing Pinned Notes Only** ({len(notes)} shown)")

        desc_lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n**Your Saved Notes:**")

        if not notes:
            desc_lines.append("*No notes found in this view. Click `➕ New Note` below to write one!*")
        else:
            for i, n in enumerate(notes[:10], start=1):
                p = "📌 " if n.get("is_pinned") else ""
                s = n.get("subject", "General")
                d = streaks.date_str(n["updated_at"])
                desc_lines.append(f"`#{n['note_id']:>2}` {p}**{n['title']}** — `{s}` · *{d}*")

            if len(notes) > 10:
                desc_lines.append(f"\n*... and {len(notes) - 10} more notes (use select menu below to view)*")

        embed = embeds.base_embed(
            title=title,
            description="\n".join(desc_lines),
            color=embeds.COLOR_STUDY,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embeds.set_footer(embed, "Chronotes · Click 'New Note' to write, or select a note to read")
        return embed

    @commands.group(name="notes", aliases=["note", "chronotes", "notebook"], invoke_without_command=True)
    @commands.guild_only()
    async def notes_cmd(self, ctx: commands.Context) -> None:
        """Open your interactive Chronotes study notebook."""
        notes = await self.db.get_user_notes(ctx.author.id, ctx.guild.id)
        embed = await self.build_hub_embed(ctx.author, ctx.guild.id, notes=notes)
        view = ChronotesHubView(ctx.author.id, self, notes)
        await ctx.send(embed=embed, view=view)

    @notes_cmd.command(name="new", aliases=["add", "create"])
    @commands.guild_only()
    async def note_new_cmd(self, ctx: commands.Context, *, title: Optional[str] = None) -> None:
        """Create a new note. You can attach an image to your message!"""
        image_url = None
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if att.content_type and att.content_type.startswith("image/"):
                image_url = att.url

        if not title:
            # Send message with button to open modal
            view = discord.ui.View()
            btn = discord.ui.Button(label="Open Note Creator", style=discord.ButtonStyle.success, emoji="📝")

            async def _cb(interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Not your command.", ephemeral=True)
                    return
                modal = CreateNoteModal(self)
                await interaction.response.send_modal(modal)

            btn.callback = _cb
            view.add_item(btn)
            await ctx.send("Click below to open the **Chronotes Note Creator**:", view=view)
            return

        # Title given: if pipe '|' exists, parse title | content
        if "|" in title:
            parts = title.split("|", 1)
            t = parts[0].strip()
            c = parts[1].strip()
        else:
            t = title.strip()
            c = "Note created via command. Use `.note edit` or `.notes` to add full content."

        note_id = await self.db.create_note(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            title=t,
            content=c,
            subject="General",
            image_url=image_url,
        )
        note = await self.db.get_note_by_id(note_id, ctx.author.id)
        if note:
            embed = self.build_note_embed(note, ctx.author)
            reader = NoteReaderView(ctx.author.id, self, note)
            await ctx.send(f"✅ **Saved note `#{note_id}` to Chronotes!**", embed=embed, view=reader)

    @notes_cmd.command(name="view", aliases=["read", "open"])
    @commands.guild_only()
    async def note_view_cmd(self, ctx: commands.Context, note_id: int) -> None:
        """View a specific note by ID."""
        note = await self.db.get_note_by_id(note_id, ctx.author.id)
        if not note:
            await ctx.send(embed=embeds.error_embed(f"Note `#{note_id}` not found in your notebook."))
            return
        embed = self.build_note_embed(note, ctx.author)
        reader = NoteReaderView(ctx.author.id, self, note)
        await ctx.send(embed=embed, view=reader)

    @notes_cmd.command(name="pin")
    @commands.guild_only()
    async def note_pin_cmd(self, ctx: commands.Context, note_id: int) -> None:
        """Toggle pinned status for a note."""
        note = await self.db.get_note_by_id(note_id, ctx.author.id)
        if not note:
            await ctx.send(embed=embeds.error_embed(f"Note `#{note_id}` not found."))
            return
        new_pinned = 0 if note.get("is_pinned") else 1
        await self.db.update_note(note_id, ctx.author.id, is_pinned=new_pinned)
        status = "pinned 📌" if new_pinned else "unpinned"
        await ctx.send(embed=embeds.success_embed("Chronotes Updated", f"Note `#{note_id}` is now **{status}**."))

    @notes_cmd.command(name="delete", aliases=["del", "rm"])
    @commands.guild_only()
    async def note_delete_cmd(self, ctx: commands.Context, note_id: int) -> None:
        """Delete a note from your notebook."""
        success = await self.db.delete_note(note_id, ctx.author.id)
        if success:
            await ctx.send(embed=embeds.success_embed("Note Deleted", f"Note `#{note_id}` was removed."))
        else:
            await ctx.send(embed=embeds.error_embed(f"Note `#{note_id}` not found."))

    @notes_cmd.command(name="search", aliases=["find"])
    @commands.guild_only()
    async def note_search_cmd(self, ctx: commands.Context, *, query: str) -> None:
        """Search your notes by keyword."""
        notes = await self.db.get_user_notes(ctx.author.id, ctx.guild.id, search=query)
        embed = await self.build_hub_embed(ctx.author, ctx.guild.id, notes=notes, search_query=query)
        view = ChronotesHubView(ctx.author.id, self, notes, search_query=query)
        await ctx.send(embed=embed, view=view)

    @notes_cmd.command(name="export")
    @commands.guild_only()
    async def note_export_cmd(self, ctx: commands.Context) -> None:
        """Export all your notes into a clean Markdown file."""
        all_notes = await self.db.get_user_notes(ctx.author.id, ctx.guild.id, limit=500)
        if not all_notes:
            await ctx.send(embed=embeds.info_embed("Chronotes", "You have no notes to export yet!"))
            return

        lines = [f"# 📓 Chronotes Notebook — {ctx.author.display_name}\n\nExported on {streaks.date_str(int(time.time()))} (IST)\n\n---\n"]
        for n in all_notes:
            pin = "📌 " if n.get("is_pinned") else ""
            date_s = streaks.date_str(n["updated_at"])
            lines.append(f"## {pin}{n['title']}\n")
            lines.append(f"**Category:** {n['subject']} | **Date:** {date_s}\n\n")
            if n.get("image_url"):
                lines.append(f"![Attached Image]({n['image_url']})\n\n")
            lines.append(f"{n['content']}\n\n---\n")

        md_content = "\n".join(lines).encode("utf-8")
        file = discord.File(io.BytesIO(md_content), filename="Chronotes_Notebook.md")
        await ctx.send(content="📤 **Here is your full Chronotes notebook export:**", file=file)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Notes(bot))
