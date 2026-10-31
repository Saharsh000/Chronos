"""Regression checks for the shared Discord UI building blocks."""
from __future__ import annotations

import unittest

from cogs.help import _build_pages
from cogs.pets import build_food_shop_page, build_pet_shop_page
from utils import embeds


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


if __name__ == "__main__":
    unittest.main()
