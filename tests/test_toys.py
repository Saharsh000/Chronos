"""Unit tests for Chronos Christmas Toy Crafting Workshop icons and pipeline."""
from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image

from tools.toys.palette import FINISH_DEFS
from utils.toys import BODIES, CORES, FINISHES, MOVERS, RECIPES, TAGS

REPO_ROOT = Path(__file__).resolve().parent.parent
TOY_ICONS_DIR = REPO_ROOT / "assets" / "icons" / "toys"
ASSETS_ICONS_DIR = REPO_ROOT / "assets" / "icons"
TOOLS_TOYS_DIR = REPO_ROOT / "tools" / "toys"


class ToysPipelineTests(unittest.TestCase):
    def test_recipe_counts_and_structure(self) -> None:
        self.assertEqual(len(BODIES), 7)
        self.assertEqual(len(MOVERS), 5)
        self.assertEqual(len(CORES), 2)
        self.assertEqual(len(FINISHES), 6)
        self.assertEqual(len(RECIPES), 70)
        self.assertEqual(len(TAGS), 7)

        for rid, r in RECIPES.items():
            self.assertEqual(r["id"], rid)
            self.assertIn(r["body"], BODIES)
            self.assertIn(r["mover"], MOVERS)
            self.assertIn(r["core"], CORES)
            self.assertEqual(len(r["tags"]), 2)
            self.assertIn(TAGS[r["mover"]], r["tags"])
            self.assertIn(TAGS[r["core"]], r["tags"])
            words = r["name"].split()
            self.assertTrue(2 <= len(words) <= 3, f"Name '{r['name']}' must be 2 or 3 words")

    def test_toy_icon_files_exist_and_native(self) -> None:
        toy_icon_files = list(TOY_ICONS_DIR.glob("*.png"))
        self.assertEqual(len(toy_icon_files), 420)

        for fid in FINISH_DEFS:
            seen_hashes: dict[bytes, str] = {}
            for rid in RECIPES:
                fpath = TOY_ICONS_DIR / f"{rid}__{fid}.png"
                self.assertTrue(fpath.exists(), f"Missing {fpath}")
                self.assertGreater(fpath.stat().st_size, 0)

                im = Image.open(fpath)
                self.assertEqual(im.size, (64, 64))
                self.assertEqual(im.mode, "RGBA")

                # Lossless 16x16 native check
                im16 = im.resize((16, 16), Image.Resampling.NEAREST)
                re_up = im16.resize((64, 64), Image.Resampling.NEAREST)
                self.assertEqual(list(im.getdata()), list(re_up.getdata()))

                # No semi-transparent pixels
                for p in im.getdata():
                    self.assertIn(p[3], (0, 255))

                # Unique pixel layout
                im_bytes = im.tobytes()
                self.assertNotIn(im_bytes, seen_hashes, f"Duplicate found: {rid} == {seen_hashes.get(im_bytes)}")
                seen_hashes[im_bytes] = rid

    def test_part_icons_exist(self) -> None:
        part_keys = [
            "toy_body_teddy", "toy_body_robot", "toy_body_train", "toy_body_duck",
            "toy_body_soldier", "toy_body_doll", "toy_body_snowman",
            "toy_mover_wheels", "toy_mover_spring", "toy_mover_propeller",
            "toy_mover_windup_key", "toy_mover_rocket",
            "toy_core_glow", "toy_core_music",
            "toy_finish_candy_red", "toy_finish_pine_green", "toy_finish_frost_blue",
            "toy_finish_gold", "toy_finish_violet_night", "toy_finish_peppermint",
        ]
        self.assertEqual(len(part_keys), 20)
        for pkey in part_keys:
            for suffix in ["", "_16", "_32", "_64", "_128", "_256", "_emoji"]:
                pfile = ASSETS_ICONS_DIR / f"{pkey}{suffix}.png"
                self.assertTrue(pfile.exists(), f"Missing {pfile}")

    def test_preview_contact_sheets_exist(self) -> None:
        p1 = TOOLS_TOYS_DIR / "preview_all_70.png"
        p2 = TOOLS_TOYS_DIR / "preview_finishes.png"
        self.assertTrue(p1.exists() and p1.stat().st_size > 0)
        self.assertTrue(p2.exists() and p2.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
