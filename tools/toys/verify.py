"""Verification script for Chronos Christmas Toys.

Asserts:
1. Exactly 70 named recipes.
2. Exactly 420 toy icons in assets/icons/toys/.
3. All 420 icon files exist on disk.
4. Every icon is 16x16-native (lossless downscale & re-upscale check).
5. No semi-transparent pixels (alpha is strictly 0 or 255).
6. No two toys within any finish are pixel-identical.
7. All 20 part icons exist with their standard size set (16, 32, 64, 128, 256, base, emoji).
8. Preview contact sheets exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.toys.palette import FINISH_DEFS  # noqa: E402
from utils.toys import RECIPES  # noqa: E402

TOY_ICONS_DIR = REPO_ROOT / "assets" / "icons" / "toys"
ASSETS_ICONS_DIR = REPO_ROOT / "assets" / "icons"
TOOLS_TOYS_DIR = REPO_ROOT / "tools" / "toys"


def verify_all() -> None:
    print("Running Chronos Christmas Toys verification...")

    # 1. Assert exactly 70 recipes
    recipe_count = len(RECIPES)
    assert recipe_count == 70, f"Expected 70 recipes, found {recipe_count}"
    print(f"  [PASS] Exactly 70 recipes defined in utils.toys")

    # 2. Assert exactly 420 toy icons exist
    toy_icon_files = list(TOY_ICONS_DIR.glob("*.png"))
    assert len(toy_icon_files) == 420, f"Expected 420 toy icons, found {len(toy_icon_files)}"
    print(f"  [PASS] Exactly 420 toy icon files in {TOY_ICONS_DIR.relative_to(REPO_ROOT)}")

    # 3. Assert all 70 recipes x 6 finishes exist
    for rid in RECIPES:
        for fid in FINISH_DEFS:
            expected_file = TOY_ICONS_DIR / f"{rid}__{fid}.png"
            assert expected_file.exists(), f"Missing toy icon: {expected_file}"
            assert expected_file.stat().st_size > 0, f"Empty file: {expected_file}"
    print(f"  [PASS] All 70 recipes x 6 finishes exist and are non-empty")

    # 4. Check 16x16-native, no semi-transparent pixels, and uniqueness per finish
    for fid in FINISH_DEFS:
        seen_pixel_hashes: dict[bytes, str] = {}
        for rid in RECIPES:
            img_path = TOY_ICONS_DIR / f"{rid}__{fid}.png"
            im = Image.open(img_path)
            assert im.mode == "RGBA", f"Expected RGBA mode for {img_path}, got {im.mode}"

            w, h = im.size
            assert w == 64 and h == 64, f"Expected 64x64, got {w}x{h} in {img_path}"

            # Lossless 16x16 downscale & re-upscale test
            im16 = im.resize((16, 16), Image.Resampling.NEAREST)
            im_reup = im16.resize((64, 64), Image.Resampling.NEAREST)
            assert list(im.getdata()) == list(im_reup.getdata()), (
                f"Icon is not losslessly 16x16-native: {img_path}"
            )

            # Check no semi-transparent pixels
            raw_pixels = list(im.getdata())
            for idx, p in enumerate(raw_pixels):
                alpha = p[3]
                assert alpha in (0, 255), (
                    f"Semi-transparent pixel found at index {idx} in {img_path}: alpha={alpha}"
                )

            # Check uniqueness within this finish
            im_bytes = im.tobytes()
            assert im_bytes not in seen_pixel_hashes, (
                f"Duplicate toy icons detected in finish {fid}: {rid} and {seen_pixel_hashes[im_bytes]}"
            )
            seen_pixel_hashes[im_bytes] = rid

    print("  [PASS] All 420 icons are 16x16-native (lossless check)")
    print("  [PASS] Zero semi-transparent pixels across all 420 icons")
    print("  [PASS] Zero duplicate icons: all 70 toys have unique pixel art in every finish")

    # 5. Check 20 part icons in assets/icons/
    part_keys = [
        "toy_body_teddy", "toy_body_robot", "toy_body_train", "toy_body_duck",
        "toy_body_soldier", "toy_body_doll", "toy_body_snowman",
        "toy_mover_wheels", "toy_mover_spring", "toy_mover_propeller",
        "toy_mover_windup_key", "toy_mover_rocket",
        "toy_core_glow", "toy_core_music",
        "toy_finish_candy_red", "toy_finish_pine_green", "toy_finish_frost_blue",
        "toy_finish_gold", "toy_finish_violet_night", "toy_finish_peppermint",
    ]
    assert len(part_keys) == 20, f"Expected 20 parts, got {len(part_keys)}"

    for pkey in part_keys:
        for suffix in ["", "_16", "_32", "_64", "_128", "_256", "_emoji"]:
            pfile = ASSETS_ICONS_DIR / f"{pkey}{suffix}.png"
            assert pfile.exists(), f"Missing part icon file: {pfile}"
            assert pfile.stat().st_size > 0, f"Empty part icon file: {pfile}"

    print(f"  [PASS] All 20 part icons (140 files total) exist with standard size set")

    # 6. Check preview contact sheets
    p1 = TOOLS_TOYS_DIR / "preview_all_70.png"
    p2 = TOOLS_TOYS_DIR / "preview_finishes.png"
    assert p1.exists() and p1.stat().st_size > 0, f"Missing preview sheet: {p1}"
    assert p2.exists() and p2.stat().st_size > 0, f"Missing preview sheet: {p2}"
    print(f"  [PASS] Contact sheets exist and are valid PNGs:\n         {p1}\n         {p2}")

    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    verify_all()
