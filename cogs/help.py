"""Custom paginated help command with interactive navigation buttons.

This bot is prefix-only (no slash commands). The help menu is split
across 8 pages so each embed stays well under Discord's 6000-char
limit.  Navigation uses discord.ui buttons (prev / next / home),
author-locked via ChronosView from utils/views.py.
"""
from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

import config
from utils import embeds
from utils.views import ChronosView


# --------------------------------------------------------------------- #
# Paginated view
# --------------------------------------------------------------------- #
class HelpPaginator(ChronosView):
    def __init__(self, author_id: int, pages: list[discord.Embed]):
        super().__init__(author_id=author_id, timeout=180.0)
        self.pages = pages
        self.current_page = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.current_page <= 0
        self.next_btn.disabled = self.current_page >= len(self.pages) - 1
        self.page_label.label = f"{self.current_page + 1} / {len(self.pages)}"

    async def _refresh_page(self, interaction: discord.Interaction) -> None:
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="\u25c0\ufe0f Prev", style=discord.ButtonStyle.primary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_page = max(0, self.current_page - 1)
        await self._refresh_page(interaction)

    @discord.ui.button(label="1 / 8", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass  # display-only counter

    @discord.ui.button(label="\u25b6\ufe0f Next", style=discord.ButtonStyle.primary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        await self._refresh_page(interaction)

    @discord.ui.button(label="\U0001F3E0 Home", style=discord.ButtonStyle.success, row=0)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_page = 0
        await self._refresh_page(interaction)


# --------------------------------------------------------------------- #
# Category keyword → page index mapping
# --------------------------------------------------------------------- #
PAGE_KEYWORDS: dict[str, int] = {
    "overview": 0, "start": 0, "stop": 0, "session": 0, "sessions": 0, "study": 0,
    "stats": 1, "leaderboard": 1, "lb": 1, "rank": 1, "compare": 1, "hof": 1,
    "achievements": 2, "badges": 2, "ach": 2,
    "syllabus": 3, "progress": 3, "jee": 3, "chapter": 3,
    "economy": 4, "coins": 4, "shop": 4, "daily": 4, "work": 4, "buy": 4,
    "pets": 5, "food": 5, "pet": 5, "feed": 5, "eggs": 5, "egg": 5, "incubate": 5, "hatch": 5, "crack": 5,
    "pomodoro": 6, "pomo": 6, "admin": 6, "config": 6, "tiers": 6, "tags": 6,
    "how": 7, "info": 7, "works": 7,
}


# --------------------------------------------------------------------- #
# Page builders
# --------------------------------------------------------------------- #
def _build_pages(prefix: str) -> list[discord.Embed]:
    """Build all 8 help pages, using the bot's current prefix."""

    def _page(title: str, body: str, page_num: int) -> discord.Embed:
        e = embeds.base_embed(title=title, description=body, color=embeds.COLOR_PRIMARY)
        e.set_footer(text=f"Page {page_num}/8 \u2022 {prefix}help \u2022 {embeds.FOOTER_TEXT}")
        return e

    pages: list[discord.Embed] = []

    # 1 — Overview / Quick Start
    pages.append(_page("\u23F3 Chronos \u2014 Help", (
        "\u23F3 **CHRONOS** \u2014 Study & Focus Tracker\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Track your grind. Earn XP & coins. Collect pets.\n"
        "Flex on the leaderboard.\n\n"
        "**\U0001F680 Quick Start**\n"
        f"`{prefix}start [subject]` \u2014 begin a study session\n"
        f"`{prefix}stop` \u2014 end your current session\n"
        f"`{prefix}session` \u2014 view your live session details\n"
        f"`{prefix}active` \u2014 see everyone studying right now\n\n"
        f"*Subjects:* `physics`/`phy`/`p`, `chemistry`/`chem`/`c`, `maths`/`math`/`m`\n\n"
        f"**Tip:** Use `{prefix}help <category>` to jump to a section \u2014\n"
        "e.g. `{prefix}help pets`, `{prefix}help economy`"
    ), 1))

    # 2 — Stats & Leaderboards
    pages.append(_page("\U0001F4C8 Stats & Leaderboards", (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Track your progress and compete with others.\n\n"
        f"`{prefix}stats [@user]` \u2014 full study profile: time, level, streak, coins\n"
        f"`{prefix}rank [@user]` \u2014 level, XP, tier, and server rank\n"
        f"`{prefix}subjects [@user]` \u2014 Physics / Chemistry / Maths breakdown\n"
        f"`{prefix}leaderboard [period] [subject]` \u2014 server leaderboard\n"
        f"  \u2514 periods: `today` `week` `month` `alltime`\n"
        f"  \u2514 aliases: `{prefix}lb`, `{prefix}top`\n"
        f"`{prefix}halloffame` \u2014 permanent all-time server records (`{prefix}hof`)\n"
        f"`{prefix}compare @user [@user2]` \u2014 head-to-head comparison (`{prefix}vs`)"
    ), 2))

    # 3 — Achievements
    pages.append(_page("\U0001F3C5 Achievements", (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Unlock badges as you hit milestones \u2014 each one\n"
        "pays out bonus coins too.\n\n"
        f"`{prefix}achievements [@user | category]`\n"
        f"  \u2514 browse unlocked & locked badges\n"
        f"  \u2514 aliases: `{prefix}badges`, `{prefix}ach`\n\n"
        "Categories cover study time, streaks, economy,\n"
        "sessions, and more. Keep grinding to catch 'em all \U0001F525"
    ), 3))

    # 4 — JEE Syllabus & Progress
    pages.append(_page("\U0001F4DA JEE Syllabus & Progress", (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Log your JEE prep progress manually.\n\n"
        f"`{prefix}syllabus [subject] [chapter]` \u2014 browse the JEE Main syllabus (`{prefix}syl`)\n"
        f"`{prefix}chapterdone <subject> <chapter>` \u2014 log a completed chapter\n"
        f"`{prefix}subtopicdone <subject> <chapter> <subtopic>` \u2014 log a subtopic\n"
        f"`{prefix}bookdone <subject> <book>` \u2014 log a completed book\n"
        f"`{prefix}pyq <year> [subject]` \u2014 log completed PYQs\n"
        f"`{prefix}revision <number> [subject]` \u2014 log a revision pass\n"
        f"`{prefix}progress [@user]` \u2014 see everything you've logged\n\n"
        "*Chapters & subtopics must match the official syllabus;\n"
        "books, PYQs, and revisions are free text.*"
    ), 4))

    # 5 — Coin Economy
    pages.append(_page("\U0001FA99 Coin Economy", (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Coins are earned automatically while studying.\n"
        "Spend them in the shop, or lose them if your streak breaks \U0001F480\n\n"
        f"**Earning**\n"
        f"`{prefix}daily` \u2014 daily reward + streak bonuses\n"
        f"`{prefix}work` \u2014 quick task for coins + XP (`{prefix}grind`)\n"
        f"`{prefix}beg` \u2014 beg for scraps \u2014 10 min cooldown\n"
        f"`{prefix}weekly` \u2014 big weekly reward + free Mystery Box\n\n"
        f"**Spending**\n"
        f"`{prefix}balance` \u2014 check your coins (`{prefix}bal`, `{prefix}coins`)\n"
        f"`{prefix}shop` \u2014 browse items for sale\n"
        f"`{prefix}buy <item> [qty]` \u2014 purchase an item\n"
        f"`{prefix}inventory` \u2014 see what you own (`{prefix}inv`)\n"
        f"`{prefix}use <item>` \u2014 activate a boost\n"
        f"`{prefix}openbox` \u2014 open a Mystery Box\n"
        f"`{prefix}settitle <title|none>` \u2014 equip a cosmetic title"
    ), 5))

    # 6 — Pets & Food
    pages.append(_page("\U0001F43E Pets & Food", (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "Adopt pets that level up while you study.\n"
        f"Requires **Level {config.PET_UNLOCK_LEVEL}+** to start.\n\n"
        f"`{prefix}petshop [tier]` \u2014 browse buyable pets (`{prefix}pshop`)\n"
        f"`{prefix}buypet <name>` \u2014 unlock a species\n"
        f"`{prefix}pets [@user]` \u2014 see owned pets\n"
        f"`{prefix}pet [name]` \u2014 detailed stats for one pet\n"
        f"`{prefix}equip <name>` \u2014 set your active pet\n"
        f"`{prefix}nickname <pet> <new name>` \u2014 rename a pet (`{prefix}nick`)\n\n"
        f"**\U0001F95A Eggs & Incubator (THE EGG UPDATE)**\n"
        f"*(Drop-only — find eggs through study sessions, streaks, & work!)*\n"
        f"`{prefix}eggs` \u2014 view incubator & unhatched eggs (`{prefix}nest`)\n"
        f"`{prefix}incubate <tier>` \u2014 place egg in incubator to hatch via study\n"
        f"`{prefix}hatch [slot]` \u2014 hatch ready egg for pets & max loot!\n"
        f"`{prefix}crack <tier>` \u2014 instantly crack an egg for quick rewards\n\n"
        f"**Food**\n"
        f"`{prefix}foodshop [tier]` \u2014 browse pet food (`{prefix}fshop`)\n"
        f"`{prefix}buyfood <name> [qty]` \u2014 buy food\n"
        f"`{prefix}feed <food> [qty]` \u2014 feed your equipped pet\n"
        f"`{prefix}sellfood <name> [qty]` \u2014 sell food back at half price"
    ), 6))

    # 7 — Pomodoro / Customization / Admin
    pages.append(_page("\U0001F345 Pomodoro \u00B7 Customization \u00B7 Admin", (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "**\U0001F345 Pomodoro**\n"
        f"`{prefix}pomodoro` \u2014 check the Pomodoro cycle in your VC (`{prefix}pomo`)\n\n"
        "**\U0001F3F7\uFE0F Customization**\n"
        f"`{prefix}tiers` \u2014 see this server's tier names\n"
        f"`{prefix}tags` \u2014 see purchasable profile titles\n\n"
        "**\u2699\uFE0F Admin** *(requires permissions)*\n"
        f"`{prefix}make` \u2014 create Physics/Chemistry/Maths study rooms *(Administrator)*\n"
        f"`{prefix}setcheckin #channel` \u2014 set the announcements channel *(Manage Server)*\n"
        f"`{prefix}config` \u2014 show current server config *(Manage Server)*"
    ), 7))

    # 8 — How It Works
    pages.append(_page("\u2139\uFE0F How It Works", (
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"\u25B8 **XP & coins** are earned per-minute while your session runs \u2014 "
        f"they update live, not just at `{prefix}stop`.\n\n"
        f"\u25B8 Your equipped pet (`{prefix}equip`) earns XP passively while you study, "
        f"plus whatever you `{prefix}feed` it.\n\n"
        f"\u25B8 Every **{config.CHECKIN_INTERVAL_MINUTES} min** you'll be asked to confirm you're "
        f"still active \u2014 react with \u2705 within **{config.AFK_GRACE_MINUTES} min** or the session "
        "ends automatically.\n\n"
        "\u25B8 All day boundaries (streaks, daily, leaderboards) use **IST** (UTC+5:30).\n\n"
        "\u25B8 Consecutive study days build a **streak** \u2014 a Streak Freeze from the shop "
        "auto-protects one missed day. **Break your streak and you lose coins.** \U0001F480\n\n"
        f"\u25B8 Subjects accept shorthands: `phy`/`p`, `chem`/`c`, `math`/`m`.\n\n"
        f"\u25B8 Unlocking an **achievement** also pays coins (`{prefix}achievements`)."
    ), 8))

    return pages


# --------------------------------------------------------------------- #
# Cog
# --------------------------------------------------------------------- #
class Help(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h", "cmds", "commands"])
    async def help_cmd(self, ctx: commands.Context, *, category: Optional[str] = None) -> None:
        """Interactive paginated help menu. Use `.help <category>` to jump to a section."""
        pages = _build_pages(ctx.prefix)

        start_page = 0
        if category:
            key = category.strip().lower()
            if key in PAGE_KEYWORDS:
                start_page = PAGE_KEYWORDS[key]
            else:
                # fuzzy: check if any keyword is a substring
                for kw, idx in PAGE_KEYWORDS.items():
                    if kw in key or key in kw:
                        start_page = idx
                        break

        view = HelpPaginator(author_id=ctx.author.id, pages=pages)
        view.current_page = start_page
        view._sync_buttons()
        view.message = await ctx.send(embed=pages[start_page], view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))

