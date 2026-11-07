"""Reusable `discord.ui` components - button paginators and the
leaderboard period switcher.

Everything here is presentation-only: a view never touches the
database directly, it calls a builder callback supplied by the cog
(see cogs/pets.py's shop page builders and cogs/stats.py's
leaderboard renderer). That keeps the data logic testable without
instantiating Discord UI objects.

Views are author-locked (only the person who ran the command can
click) and disable themselves on timeout so stale messages don't look
interactive forever.
"""
from __future__ import annotations

import asyncio
import io
from typing import Any, Awaitable, Callable, Optional, Sequence

import discord

from utils import embeds
from utils import stats_card
from utils.embeds import error_embed

# How long a menu stays clickable before its buttons grey out.
DEFAULT_TIMEOUT = 180.0


class ChronosView(discord.ui.View):
    """Base view: author-locked, self-disabling on timeout."""

    def __init__(self, author_id: int, timeout: float = DEFAULT_TIMEOUT):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error_embed(
                    "That menu belongs to someone else. Run the command to open your own view."
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# --------------------------------------------------------------------- #
# Shop / catalogue paginator
# --------------------------------------------------------------------- #
# A builder takes (tier_key, page_index) and returns the embeds for that
# page. Cogs supply this; the view only drives navigation.
PageBuilder = Callable[[str, int], Sequence[discord.Embed]]
PageCounter = Callable[[str], int]


class TierSelect(discord.ui.Select):
    """Dropdown that jumps the paginator to a different tier."""

    def __init__(self, tiers: Sequence[tuple[str, str, str]], current: str):
        options = [
            discord.SelectOption(label=label, value=key, emoji=emoji, default=(key == current))
            for key, label, emoji in tiers
        ]
        super().__init__(placeholder="Jump to a tier...", options=options, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ShopPaginator = self.view  # type: ignore[assignment]
        view.tier = self.values[0]
        view.page = 0
        await view.refresh(interaction)


class ShopPaginator(ChronosView):
    """Tier dropdown + prev/next buttons over a paged catalogue.

    `tiers` is a list of (key, label, emoji). `build_page` returns the
    embeds for a given (tier, page); `count_pages` returns how many
    pages a tier has.
    """

    def __init__(
        self,
        author_id: int,
        tiers: Sequence[tuple[str, str, str]],
        initial_tier: str,
        build_page: PageBuilder,
        count_pages: PageCounter,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        super().__init__(author_id, timeout=timeout)
        self.tiers = tiers
        self.tier = initial_tier
        self.page = 0
        self._build_page = build_page
        self._count_pages = count_pages
        self.add_item(TierSelect(tiers, initial_tier))
        self._sync_buttons()

    @property
    def total_pages(self) -> int:
        return max(1, self._count_pages(self.tier))

    def embeds(self) -> list[discord.Embed]:
        return list(self._build_page(self.tier, self.page))

    def _sync_buttons(self) -> None:
        """Grey out prev/next at the ends and keep the counter label
        current. Also refreshes the dropdown's checked option."""
        total = self.total_pages
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= total - 1
        self.page_label.label = f"Page {self.page + 1}/{total}"
        for child in self.children:
            if isinstance(child, TierSelect):
                for option in child.options:
                    option.default = option.value == self.tier

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._sync_buttons()
        await interaction.response.edit_message(embeds=self.embeds(), view=self)

    @discord.ui.button(emoji="\u25C0\uFE0F", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Never fires - the button exists purely as a page counter.
        pass

    @discord.ui.button(emoji="\u25B6\uFE0F", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.total_pages - 1, self.page + 1)
        await self.refresh(interaction)


# --------------------------------------------------------------------- #
# Leaderboard period switcher
# --------------------------------------------------------------------- #
# Renders the leaderboard embed for a given period key.
LeaderboardRenderer = Callable[[str], Awaitable[discord.Embed]]

LEADERBOARD_PERIODS: list[tuple[str, str]] = [
    ("today", "Today"),
    ("week", "This Week"),
    ("month", "This Month"),
    ("alltime", "All Time"),
]


class PeriodButton(discord.ui.Button):
    def __init__(self, period: str, label: str, active: bool):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary if active else discord.ButtonStyle.secondary,
            disabled=active,
            row=0,
        )
        self.period = period

    async def callback(self, interaction: discord.Interaction) -> None:
        view: LeaderboardView = self.view  # type: ignore[assignment]
        view.period = self.period
        view.sync()
        res = await view.render(self.period)
        if isinstance(res, tuple):
            embed, file = res
            await interaction.response.edit_message(embed=embed, attachments=[file], view=view)
        else:
            await interaction.response.edit_message(embed=res, view=view)


class LeaderboardView(ChronosView):
    """Today / This Week / This Month / All Time switcher. The active
    period's button is highlighted and disabled."""

    def __init__(
        self,
        author_id: int,
        initial_period: str,
        render: LeaderboardRenderer,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        super().__init__(author_id, timeout=timeout)
        self.period = initial_period
        self.render = render
        for key, label in LEADERBOARD_PERIODS:
            self.add_item(PeriodButton(key, label, active=(key == initial_period)))

    def sync(self) -> None:
        for child in self.children:
            if isinstance(child, PeriodButton):
                active = child.period == self.period
                child.disabled = active
                child.style = discord.ButtonStyle.primary if active else discord.ButtonStyle.secondary


# --------------------------------------------------------------------- #
# Paginated Study Profile & Analytics View (.stats)
# --------------------------------------------------------------------- #
STATS_PAGES = [
    ("overview", "Overview", "📊"),
    ("weekly", "Activity", "📈"),
    ("subjects", "Subjects", "📚"),
    ("trivia", "Trivia", "🧠"),
]


class StatsTabButton(discord.ui.Button["StatsPaginationView"]):
    def __init__(self, page_id: str, label: str, emoji: str, active: bool = False):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.primary if active else discord.ButtonStyle.secondary,
            disabled=active,
            row=0,
        )
        self.page_id = page_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view is not None:
            await self.view.switch_page(interaction, self.page_id)


class StatsPaginationView(ChronosView):
    """Interactive 4-tab paginator for `.stats` with custom visual cards:
    1. Overview (Profile dashboard, XP, coins, streak, achievements)
    2. Activity (7-day bar chart, weekly total, daily avg, peak day)
    3. Subjects (PCM distribution bar, subject cards, balance index)
    4. Trivia (AIR rank, net marks, solve accuracy, streak, rewards)
    """

    def __init__(
        self,
        author_id: int,
        context: dict[str, Any],
        initial_image_bytes: Optional[bytes] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        super().__init__(author_id, timeout=timeout)
        self.ctx_data = context
        self.current_page = "overview"
        self._image_cache: dict[str, bytes] = {}
        if initial_image_bytes:
            self._image_cache["overview"] = initial_image_bytes

        for p_id, label, emoji in STATS_PAGES:
            self.add_item(StatsTabButton(p_id, label, emoji, active=(p_id == "overview")))
        self._sync_buttons()

    def _page_index(self) -> int:
        return next((i for i, (p_id, _, _) in enumerate(STATS_PAGES) if p_id == self.current_page), 0)

    def _sync_buttons(self) -> None:
        idx = self._page_index()
        total = len(STATS_PAGES)
        for child in self.children:
            if isinstance(child, StatsTabButton):
                active = (child.page_id == self.current_page)
                child.disabled = active
                child.style = discord.ButtonStyle.primary if active else discord.ButtonStyle.secondary
        self.prev_page.disabled = idx <= 0
        self.next_page.disabled = idx >= total - 1
        self.page_label.label = f"Page {idx + 1}/{total}"

    def _render_page_image(self, page_id: str) -> bytes:
        d = self.ctx_data
        target = d["target"]
        if page_id == "overview":
            return stats_card.render_overview_card_sync(
                display_name=target.display_name,
                username=target.name,
                tier_name=d["tier"],
                level=d["level"],
                xp_into=d["current_into"],
                xp_needed=d["needed_for_next"],
                total_xp=d["stats"]["xp"],
                coins=d["currency"]["coins"],
                candy=d["candy"],
                total_seconds=d["total_seconds"],
                today_seconds=d["today_seconds"],
                week_seconds=d["week_seconds"],
                streak_days=d["stats"]["current_streak"],
                longest_streak=d["stats"]["longest_streak"],
                sessions_count=d["stats"]["sessions_count"],
                unlocked_achievements=d["unlocked_count"],
                total_achievements=d["total_achievements"],
                rank_position=d["rank_position"],
                equipped_title=d["equipped_title"],
                equipped_pet=d["equipped_pet"],
                subject_seconds=d["subject_seconds"],
                in_session_seconds=d["in_session_seconds"],
                avatar_bytes=d["avatar_bytes"],
            )
        elif page_id == "weekly":
            return stats_card.render_weekly_card_sync(
                display_name=target.display_name,
                username=target.name,
                tier_name=d["tier"],
                weekly_breakdown=d["weekly_breakdown"],
                avatar_bytes=d["avatar_bytes"],
            )
        elif page_id == "subjects":
            return stats_card.render_subjects_card_sync(
                display_name=target.display_name,
                username=target.name,
                tier_name=d["tier"],
                subject_details=d["subject_details"],
                avatar_bytes=d["avatar_bytes"],
            )
        elif page_id == "trivia":
            return stats_card.render_trivia_card_sync(
                display_name=target.display_name,
                username=target.name,
                tier_name=d["tier"],
                trivia_stats=d["trivia_stats"],
                rank_info=d["trivia_rank"],
                tier_info=d["trivia_tier"],
                avatar_bytes=d["avatar_bytes"],
            )
        return b""

    def build_page_embed(self, page_id: str) -> discord.Embed:
        d = self.ctx_data
        target: discord.Member = d["target"]
        idx = self._page_index()
        total = len(STATS_PAGES)
        titles = {
            "overview": "Study Profile · Overview",
            "weekly": "Weekly Activity · Graphs",
            "subjects": "Subjects · PCM Split",
            "trivia": "Trivia · AIR Scorecard",
        }
        colors = {
            "overview": embeds.COLOR_SOCIAL,
            "weekly": embeds.COLOR_INFO,
            "subjects": embeds.COLOR_PRIMARY,
            "trivia": embeds.COLOR_WARNING,
        }
        live = " · in session" if d.get("in_session_seconds") else ""
        embed = embeds.base_embed(
            title=titles.get(page_id, "Study Profile"),
            description=f"**{target.display_name}** · {d['tier']} · Lv {d['level']}{live}",
            color=colors.get(page_id, embeds.COLOR_SOCIAL),
        )
        embed.set_author(name=str(target), icon_url=target.display_avatar.url)
        embeds.set_footer(embed, f"Page {idx + 1}/{total} · tap tabs or arrows for graphs")
        return embed

    def _page_payload(self, page_id: str, img_bytes: bytes) -> tuple[discord.Embed, discord.File]:
        embed = self.build_page_embed(page_id)
        filename = f"stats_{page_id}.png"
        file = discord.File(io.BytesIO(img_bytes), filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        return embed, file

    async def _image_for(self, page_id: str) -> bytes:
        cached = self._image_cache.get(page_id)
        if cached:
            return cached
        loop = asyncio.get_running_loop()
        img_bytes = await loop.run_in_executor(None, self._render_page_image, page_id)
        self._image_cache[page_id] = img_bytes
        return img_bytes

    async def send_initial(self, destination: Any) -> None:
        img_bytes = await self._image_for("overview")
        embed, file = self._page_payload("overview", img_bytes)
        self.message = await destination.send(file=file, embed=embed, view=self)

    async def switch_page(self, interaction: discord.Interaction, page_id: str) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer()
        if page_id != self.current_page:
            self.current_page = page_id
            self._sync_buttons()

        img_bytes = await self._image_for(self.current_page)
        embed, file = self._page_payload(self.current_page, img_bytes)
        if interaction.message:
            await interaction.message.edit(embed=embed, attachments=[file], view=self)

    @discord.ui.button(emoji="\u25C0\uFE0F", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        idx = max(0, self._page_index() - 1)
        await self.switch_page(interaction, STATS_PAGES[idx][0])

    @discord.ui.button(label="Page 1/4", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        return

    @discord.ui.button(emoji="\u25B6\uFE0F", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        idx = min(len(STATS_PAGES) - 1, self._page_index() + 1)
        await self.switch_page(interaction, STATS_PAGES[idx][0])
