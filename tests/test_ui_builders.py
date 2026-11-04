"""Regression checks for the shared Discord UI building blocks."""
from __future__ import annotations

import unittest

from cogs.help import _build_pages
from cogs.pets import build_food_shop_page, build_pet_shop_page
from cogs.trivia import format_academic_text, format_question_presentation
from utils import embeds
from utils import stats_card


class EmbedSystemTests(unittest.TestCase):
    def test_footer_keeps_brand_before_screen_context(self) -> None:
        embed = embeds.base_embed(title="Check")
        embeds.set_footer(embed, "Context")

        self.assertEqual(
            embed.footer.text,
            f"{embeds.FOOTER_TEXT} • Context",
        )

    def test_command_line_keeps_the_command_prominent(self) -> None:
        rendered = embeds.command_line(".stats", "Open your profile")

        self.assertIn(".stats", rendered)
        self.assertIn("Open your profile", rendered)


class HelpBuilderTests(unittest.TestCase):
    def test_help_pages_have_consistent_navigation_footers(self) -> None:
        pages = _build_pages(".")

        self.assertEqual(len(pages), 8)
        self.assertTrue(all("━" not in (page.description or "") for page in pages))
        self.assertTrue(all("Help " in (page.footer.text or "") for page in pages))


class ShopBuilderTests(unittest.TestCase):
    def test_shop_headers_are_branded_while_item_cards_stay_compact(self) -> None:
        pet_page = build_pet_shop_page("common", 0, set(), ".", coins=0, level=0)
        food_page = build_food_shop_page("snack", 0, ".", coins=0, owned={})

        for page in (pet_page, food_page):
            self.assertTrue(page[0].footer.text.startswith(embeds.FOOTER_TEXT))
            self.assertTrue(all(not card.footer.text for card in page[1:]))


class TriviaFormattingTests(unittest.TestCase):
    def test_distexer_renders_latex_and_bare_math(self) -> None:
        rendered = format_academic_text(r"The result is $\\frac{A}{\\sqrt{2}}$ and $H_2O$.")

        self.assertIn("A/(√2)", rendered)
        self.assertIn("H₂O", rendered)
        self.assertNotIn("\\\\frac", rendered)

    def test_question_items_remain_readable_after_math_rendering(self) -> None:
        rendered = format_question_presentation(
            format_academic_text(r"Which statements are true? (i) $x^2$ is nonnegative; (ii) \\alpha > 0.")
        )

        self.assertIn("(i)", rendered)
        self.assertIn("x²", rendered)
        self.assertIn("α > 0", rendered)


class StatsCardTests(unittest.TestCase):
    def test_paginated_cards_render_large_pngs(self) -> None:
        weekly = {
            "days": [
                {"day_name": "MON", "seconds": 3600, "is_today": False},
                {"day_name": "TUE", "seconds": 7200, "is_today": True},
                {"day_name": "WED", "seconds": 0, "is_today": False},
                {"day_name": "THU", "seconds": 1800, "is_today": False},
                {"day_name": "FRI", "seconds": 5400, "is_today": False},
                {"day_name": "SAT", "seconds": 0, "is_today": False},
                {"day_name": "SUN", "seconds": 900, "is_today": False},
            ],
            "total_week_seconds": 18900,
            "daily_avg_seconds": 2700,
            "active_days_count": 5,
            "peak_day_name": "TUE",
            "peak_day_seconds": 7200,
        }
        subjects = {
            "physics": {"total_seconds": 10000, "session_count": 4, "avg_seconds": 2500},
            "chemistry": {"total_seconds": 8000, "session_count": 3, "avg_seconds": 2600},
            "maths": {"total_seconds": 12000, "session_count": 5, "avg_seconds": 2400},
        }
        trivia = {
            "total_marks": 42,
            "questions_attempted": 20,
            "questions_correct": 14,
            "current_streak": 3,
            "best_streak": 6,
            "total_coins_won": 120,
        }
        cards = [
            stats_card.render_overview_card_sync(
                display_name="Tester",
                username="tester",
                tier_name="Gold",
                level=12,
                xp_into=400,
                xp_needed=1000,
                total_xp=5400,
                coins=250,
                candy=3,
                total_seconds=36000,
                today_seconds=1800,
                week_seconds=18900,
                streak_days=4,
                longest_streak=11,
                sessions_count=9,
                unlocked_achievements=5,
                total_achievements=20,
                rank_position=2,
            ),
            stats_card.render_weekly_card_sync("Tester", "tester", "Gold", weekly),
            stats_card.render_subjects_card_sync("Tester", "tester", "Gold", subjects),
            stats_card.render_trivia_card_sync(
                "Tester",
                "tester",
                "Gold",
                trivia,
                (3, 12),
                {"title": "NIT TPG Star", "next_marks": 70, "cur_min": 40, "next_title": "Old IIT Topper"},
            ),
        ]
        for png in cards:
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertGreater(len(png), 20_000)


if __name__ == "__main__":
    unittest.main()
