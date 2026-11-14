"""tests/test_lab_data.py - Unit tests for The Lab compound dataset and formulas."""
import unittest

from utils.lab import (
    CATEGORIES,
    COMPOUND_BY_ID,
    COMPOUND_BY_NAME,
    COMPOUNDS,
    ELEMENT_LIST,
    parse_formula,
    reward_coins_first,
    validate_compound,
)


class TestLabData(unittest.TestCase):
    def test_exactly_100_compounds(self):
        self.assertEqual(len(COMPOUNDS), 100, f"Expected exactly 100 compounds, found {len(COMPOUNDS)}")

    def test_unique_ids(self):
        ids = [c["id"] for c in COMPOUNDS]
        self.assertEqual(len(ids), len(set(ids)), f"Duplicate compound IDs found: {set([x for x in ids if ids.count(x) > 1])}")

    def test_unique_names(self):
        names = [c["name"].lower() for c in COMPOUNDS]
        self.assertEqual(len(names), len(set(names)), f"Duplicate compound names found: {set([x for x in names if names.count(x) > 1])}")

    def test_only_8_elements(self):
        for c in COMPOUNDS:
            elems = c["elements"]
            self.assertEqual(
                set(elems.keys()),
                set(ELEMENT_LIST),
                f"Compound '{c['id']}' elements keys must match exactly {ELEMENT_LIST}",
            )
            for e, count in elems.items():
                self.assertIsInstance(count, int, f"Element count for {e} in {c['id']} must be integer")
                self.assertGreaterEqual(count, 0, f"Element count for {e} in {c['id']} cannot be negative")

    def test_no_extra_elements(self):
        valid = set(ELEMENT_LIST)
        for c in COMPOUNDS:
            parsed = parse_formula(c["formula"])
            self.assertTrue(set(parsed.keys()).issubset(valid))

    def test_formula_matches_elements(self):
        for c in COMPOUNDS:
            errors = validate_compound(c)
            self.assertEqual(errors, [], f"Compound validation failed for {c['id']}: {errors}")

    def test_all_categories_present(self):
        expected_cats = [
            "Alkanes",
            "Alkenes",
            "Alkynes",
            "Cycloalkanes",
            "Haloalkanes",
            "Alcohols",
            "Phenols",
            "Ethers",
            "Aldehydes",
            "Ketones",
            "Carboxylic-Acids",
            "Acid-Derivatives",
            "Nitrogen-Compounds",
            "Aromatics",
            "Biomolecules",
            "Monomers",
        ]
        cat_counts = {cat: 0 for cat in expected_cats}
        for c in COMPOUNDS:
            self.assertIn(c["category"], cat_counts, f"Unexpected category {c['category']} in {c['id']}")
            cat_counts[c["category"]] += 1

        for cat, cnt in cat_counts.items():
            self.assertGreater(cnt, 0, f"Category {cat} has 0 compounds")

    def test_reward_sum(self):
        total_coins = sum(reward_coins_first(c) for c in COMPOUNDS)
        self.assertGreaterEqual(total_coins, 40000, f"Total rewards {total_coins} is below 40,000")
        self.assertLessEqual(total_coins, 50000, f"Total rewards {total_coins} exceeds 50,000")
        self.assertEqual(total_coins, 44950, f"Calibrated reward sum should be 44,950, got {total_coins}")

    def test_methane_synthesizable_in_2_min(self):
        methane = COMPOUND_BY_ID["methane"]
        self.assertEqual(methane["elements"]["C"], 1)
        self.assertEqual(methane["elements"]["H"], 4)
        for e in ["O", "N", "Cl", "F", "Br", "I"]:
            self.assertEqual(methane["elements"][e], 0)

    def test_parse_formula_edge_cases(self):
        self.assertEqual(parse_formula("CH4")["C"], 1)
        self.assertEqual(parse_formula("CH4")["H"], 4)
        self.assertEqual(parse_formula("C6H12O6")["C"], 6)
        self.assertEqual(parse_formula("C6H12O6")["H"], 12)
        self.assertEqual(parse_formula("C6H12O6")["O"], 6)
        self.assertEqual(parse_formula("CHCl3")["Cl"], 3)
        self.assertEqual(parse_formula("C2H5Br")["Br"], 1)
        self.assertEqual(parse_formula("CH3I")["I"], 1)
        self.assertEqual(parse_formula("C2F4")["F"], 4)


if __name__ == "__main__":
    unittest.main()
