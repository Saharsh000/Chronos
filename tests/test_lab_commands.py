"""tests/test_lab_commands.py - Unit tests for The Lab bot command logic and resolution."""
import unittest

from cogs.lab import _format_progress_bar, Lab
from utils import lab as lab_catalog


class DummyBot:
    def __init__(self):
        self.db = None


class TestLabCommands(unittest.TestCase):
    def setUp(self):
        self.cog = Lab(DummyBot())

    def test_progress_bar_format(self):
        self.assertEqual(_format_progress_bar(0, 30, length=10), "[░░░░░░░░░░] 0%")
        self.assertEqual(_format_progress_bar(15, 30, length=10), "[█████░░░░░] 50%")
        self.assertEqual(_format_progress_bar(30, 30, length=10), "[██████████] 100%")
        self.assertEqual(_format_progress_bar(45, 30, length=10), "[██████████] 100%")

    def test_resolve_compound_by_id(self):
        c = self.cog._resolve_compound("methane")
        self.assertIsNotNone(c)
        self.assertEqual(c["id"], "methane")

    def test_resolve_compound_by_name_case_insensitive(self):
        c = self.cog._resolve_compound("Carbon Tetrachloride")
        self.assertIsNotNone(c)
        self.assertEqual(c["id"], "carbon-tetrachloride")

    def test_resolve_compound_by_formula(self):
        c = self.cog._resolve_compound("C6H6")
        self.assertIsNotNone(c)
        self.assertEqual(c["name"], "Benzene")

        c2 = self.cog._resolve_compound("CH4")
        self.assertIsNotNone(c2)
        self.assertEqual(c2["name"], "Methane")

    def test_resolve_compound_fuzzy(self):
        c = self.cog._resolve_compound("propanone")
        self.assertIsNotNone(c)
        self.assertEqual(c["id"], "propanone")

        # slight typo
        c_typo = self.cog._resolve_compound("propanon")
        self.assertIsNotNone(c_typo)
        self.assertEqual(c_typo["id"], "propanone")

    def test_reward_math_constants(self):
        # Methane: 1 C, 4 H -> 1 heavy atom, 0 halogens
        # formula: 5 * (30 + 10*1 + 40*0) = 5 * 40 = 200
        methane = lab_catalog.COMPOUND_BY_ID["methane"]
        self.assertEqual(lab_catalog.reward_coins_first(methane), 200)
        self.assertEqual(lab_catalog.reward_xp_first(methane), 100)
        self.assertEqual(lab_catalog.reward_coins_repeat(methane), 40)  # 20% of 200

        # Chloroform: CHCl3 -> C, 3 Cl -> 4 heavy, 0 F/Br/I
        # formula: 5 * (30 + 10*4 + 40*0) = 5 * 70 = 350
        chloroform = lab_catalog.COMPOUND_BY_ID["chloroform"]
        self.assertEqual(lab_catalog.reward_coins_first(chloroform), 350)

        # Bromomethane: CH3Br -> C, Br -> 2 heavy, 1 Br -> 5 * (30 + 10*2 + 40*1) = 5 * 90 = 450
        bromo = lab_catalog.COMPOUND_BY_ID["bromomethane"]
        self.assertEqual(lab_catalog.reward_coins_first(bromo), 450)


if __name__ == "__main__":
    unittest.main()
