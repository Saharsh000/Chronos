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

from typing import Awaitable, Callable, Optional, Sequence

import discord

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
        embed = await view.render(self.period)
        await interaction.response.edit_message(embed=embed, view=view)


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
