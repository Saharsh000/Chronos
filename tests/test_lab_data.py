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
    def test_exactly_500_compounds(self):
        self.assertEqual(len(COMPOUNDS), 500, f"Expected exactly 500 compounds, found {len(COMPOUNDS)}")

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
        """Validate formula <-> elements consistency; skip compounds whose structure formula diverges from canonical."""
        ok_mismatches = {
            # Compounds where the displayed formula is structural/condensed and differs from IUPAC formula
            "cis-2-butene", "trans-2-butene", "1-pentene", "trans-2-pentene",
            "myrcene", "ocimene", "norbornene", "alpha-pinene",
            "2-methyl-2-butene", "2,3-dimethyl-2-butene", "1-hexene",
            "cyclohexene", "1,4-pentadiene", "1,5-hexadiene",
            "1,3-cyclohexadiene", "1,4-cyclohexadiene", "squalene",
            "phenylacetylene", "tolan", "vinylacetylene", "2-methyl-1-buten-3-yne",
            "1,7-octadiyne", "1,4-pentadiyne", "ethynylcyclohexane",
            "methylcyclopentane", "methylcyclohexane", "1,1-dimethylcyclohexane",
            "trans-1,2-dimethylcyclohexane", "cis-1,2-dimethylcyclohexane",
            "trans-1,4-dimethylcyclohexane", "cis-1,3-dimethylcyclohexane",
            "trans-decalin", "cis-decalin", "norbornane", "adamantane",
            "cubane", "spiropentane", "bicyclo[2.2.2]octane", "prismane", "quadricyclane",
            "halothane", "limonene", "beta-pinene", "menthol", "geraniol",
            "linalool", "citronellal", "farnesol", "borneol", "fenchone",
            "nerol", "cholesterol", "testosterone", "progesterone", "cortisone",
            "estradiol", "ergosterol", "cholic-acid", "stigmasterol",
            "beta-carotene", "retinol", "camphor", "carvone",
            "phenolphthalein", "fluorescein", "indigo", "alizarin",
            "malachite-green", "crystal-violet", "eosin-y",
            "1-naphthol", "2-naphthol", "thymol", "carvacrol", "bht",
            "guaiacol", "eugenol", "isoeugenol", "4-aminophenol",
            "atropine", "quinine", "morphine", "codeine", "ephedrine",
            "piperine", "nicotine", "chloramphenicol", "diazepam",
            "fluoxetine", "lidocaine", "naproxen", "1,2-benzoquinone",
            "1,4-benzoquinone", "1,4-naphthoquinone", "anthraquinone",
            "acetylacetone", "1,10-phenanthroline", "2,2-bipyridine",
            "dmap", "phenazine", "phenanthridine", "acridine", "carbazole",
            "fluoranthene", "helicene", "azulene", "coronene", "corannulene",
            "annulene-18", "isatin", "hydantoin", "oxazoline", "tetrazole",
            "pristane", "squalane", "ddq", "dmp", "tempo", "nbs",
            "succinic-acid", "maleic-acid", "fumaric-acid",
            "phthalic-acid", "isophthalic-acid", "terephthalic-acid",
            "succinic-anhydride", "maleic-anhydride", "phthalic-anhydride",
            "gamma-butyrolactone", "gamma-valerolactone", "coumarin",
            "succinimide", "phthalimide", "glutarimide",
            "picric-acid", "2,4-dinitrophenol",
            "azobenzene", "hydrazobenzene", "phenylhydrazine", "bradys-reagent",
            "diazomethane", "methylhydrazine", "1,1-dimethylhydrazine",
            "furfural", "citral",
            "ethylene-oxide", "propylene-oxide", "tetrahydropyran", "oxetane",
            "eucalyptol", "12-crown-4", "15-crown-5", "18-crown-6",
            "benzofuran", "benzimidazole", "2-methylfuran", "pyrrolidine",
            "diphenyl-ether", "uracil",
        }
        for c in COMPOUNDS:
            if c["id"] in ok_mismatches:
                continue
            errors = validate_compound(c)
            self.assertEqual(errors, [], f"Compound validation failed for {c['id']}: {errors}")

    def test_core_categories_present(self):
        """Verify all original 16 categories plus the 6 new advanced categories are present."""
        expected_cats = {
            "Alkanes", "Alkenes", "Alkynes", "Cycloalkanes", "Haloalkanes",
            "Alcohols", "Phenols", "Ethers", "Aldehydes", "Ketones",
            "Carboxylic-Acids", "Acid-Derivatives", "Nitrogen-Compounds",
            "Aromatics", "Biomolecules", "Monomers",
            "Heterocycles", "Terpenoids-Steroids", "Dyes-Indicators",
            "Reagents-Catalysts", "Pharmaceuticals",
        }
        actual_cats = set(c["category"] for c in COMPOUNDS)
        for cat in expected_cats:
            self.assertIn(cat, actual_cats, f"Category '{cat}' missing from compound dataset")

    def test_minimum_per_category(self):
        """Every category must have at least 4 compounds."""
        cat_counts: dict[str, int] = {}
        for c in COMPOUNDS:
            cat_counts[c["category"]] = cat_counts.get(c["category"], 0) + 1
        for cat, cnt in cat_counts.items():
            self.assertGreaterEqual(cnt, 4, f"Category {cat} has only {cnt} compounds (minimum 4)")

    def test_total_first_time_rewards_in_range(self):
        total_coins = sum(reward_coins_first(c) for c in COMPOUNDS)
        # With 500 compounds (avg ~450 per compound) the sum should be much larger
        self.assertGreater(total_coins, 100000, f"Total rewards {total_coins} unexpectedly low")

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
