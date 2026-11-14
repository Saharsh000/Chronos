"""Build script for Chronos Christmas Toys.

Regenerates all toy sprites, part icons, and preview contact sheets.
Deterministic & idempotent: running twice generates byte-identical files.

Usage:
  python tools/toys/build.py
  python tools/toys/build.py --toy teddy_wheels_glow
  python tools/toys/build.py --finish candy_red
  python tools/toys/build.py --preview
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Root directory of Chronos repository
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.toys.composite import (  # noqa: E402
    composite_toy_grid,
    load_grid_file,
    render_image,
    upscale_nearest,
)
from tools.toys.palette import FINISH_DEFS, get_finish_palette  # noqa: E402
from utils.toys import BODIES, CORES, FINISHES, MOVERS, RECIPES, TAGS  # noqa: E402

TOY_ICONS_DIR = REPO_ROOT / "assets" / "icons" / "toys"
ASSETS_ICONS_DIR = REPO_ROOT / "assets" / "icons"
TOOLS_TOYS_DIR = REPO_ROOT / "tools" / "toys"
DATA_DIR = REPO_ROOT / "data"

ICON_SIZES = [16, 32, 64, 128, 256]


def build_toy_icon(recipe_id: str, finish_id: str, out_dir: Path) -> Path:
    """Build and save a 64x64 toy icon (4x nearest upscale from native 16x16)."""
    r = RECIPES[recipe_id]
    grid = composite_toy_grid(r["body"], r["mover"], r["core"])
    im16 = render_image(grid, finish_id)
    im64 = upscale_nearest(im16, 4)

    out_file = out_dir / f"{recipe_id}__{finish_id}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    im64.save(out_file, format="PNG", optimize=True)
    return out_file


def build_part_icons(out_dir: Path) -> list[Path]:
    """Build the 20 inventory part icons in assets/icons/ at all standard sizes."""
    generated: list[Path] = []
    # 20 parts: 7 bodies, 5 movers, 2 cores, 6 finish swatches
    part_keys = [
        "toy_body_teddy", "toy_body_robot", "toy_body_train", "toy_body_duck",
        "toy_body_soldier", "toy_body_doll", "toy_body_snowman",
        "toy_mover_wheels", "toy_mover_spring", "toy_mover_propeller",
        "toy_mover_windup_key", "toy_mover_rocket",
        "toy_core_glow", "toy_core_music",
        "toy_finish_candy_red", "toy_finish_pine_green", "toy_finish_frost_blue",
        "toy_finish_gold", "toy_finish_violet_night", "toy_finish_peppermint",
    ]

    for pkey in part_keys:
        grid = load_grid_file(f"parts/{pkey}.txt")
        # For finish swatches, use their own finish palette; for others use candy_red/neutral
        finish = pkey.replace("toy_finish_", "") if pkey.startswith("toy_finish_") else "candy_red"
        im16 = render_image(grid, finish)

        # Base 16x16 icon: <name>.png
        base_path = out_dir / f"{pkey}.png"
        im16.save(base_path, format="PNG", optimize=True)
        generated.append(base_path)

        # Size variants: _16, _32, _64, _128, _256
        for size in ICON_SIZES:
            scaled = upscale_nearest(im16, size // 16)
            s_path = out_dir / f"{pkey}_{size}.png"
            scaled.save(s_path, format="PNG", optimize=True)
            generated.append(s_path)

        # Emoji variant (128x128 matching Chronos repo style)
        emoji_path = out_dir / f"{pkey}_emoji.png"
        upscale_nearest(im16, 8).save(emoji_path, format="PNG", optimize=True)
        generated.append(emoji_path)

    return generated


def build_data_json() -> Path:
    """Export complete workshop catalog to data/toys.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "tags": TAGS,
        "bodies": BODIES,
        "movers": MOVERS,
        "cores": CORES,
        "finishes": FINISHES,
        "recipes": RECIPES,
    }
    out_file = DATA_DIR / "toys.json"
    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out_file


def generate_preview_all_70(out_path: Path) -> Path:
    """Generate a high-res contact sheet of all 70 toys on a labelled grid."""
    cols = 10
    rows = 7
    cell_w = 120
    cell_h = 115
    pad_top = 70
    pad_side = 30
    pad_bottom = 30

    w = pad_side * 2 + cols * cell_w
    h = pad_top + rows * cell_h + pad_bottom

    canvas = Image.new("RGBA", (w, h), (23, 17, 30, 255))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    # Header title
    draw.text((pad_side, 20), "CHRONOS CHRISTMAS TOY WORKSHOP — ALL 70 TOYS", fill=(255, 230, 160, 255), font=font)
    draw.text((pad_side, 40), "Native 16x16 Pixel Art (Previewed at 4x upscale) • Base Finish: Candy Red", fill=(180, 170, 195, 255), font=font)

    recipe_items = list(RECIPES.values())
    for idx, r in enumerate(recipe_items):
        col = idx % cols
        row = idx // cols

        x = pad_side + col * cell_w
        y = pad_top + row * cell_h

        # Cell background card
        draw.rounded_rectangle([x + 2, y + 2, x + cell_w - 4, y + cell_h - 4], radius=6, fill=(34, 25, 44, 255), outline=(58, 43, 74, 255))

        # Render 16x16 toy in candy_red finish, upscale 4x to 64x64
        grid = composite_toy_grid(r["body"], r["mover"], r["core"])
        im16 = render_image(grid, "candy_red")
        im64 = upscale_nearest(im16, 4)

        sprite_x = x + (cell_w - 64) // 2
        sprite_y = y + 8
        canvas.paste(im64, (sprite_x, sprite_y), im64)

        # Label: Toy Name & ID
        name = r["name"]
        rid = r["id"]
        # Abbreviate name if too long for card
        name_line = name if len(name) <= 16 else name[:15] + "…"
        id_line = rid if len(rid) <= 18 else rid[:17] + "…"
        draw.text((x + 8, y + 78), name_line, fill=(245, 240, 250, 255), font=font)
        draw.text((x + 8, y + 92), id_line, fill=(140, 130, 155, 255), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG", optimize=True)
    return out_path


def generate_preview_finishes(out_path: Path, showcase_recipe: str = "teddy_wheels_glow") -> Path:
    """Generate a contact sheet showing a showcase toy in all 6 finishes."""
    finish_list = list(FINISH_DEFS.keys())
    n = len(finish_list)
    cell_w = 150
    cell_h = 190
    pad_top = 80
    pad_side = 40
    pad_bottom = 40

    w = pad_side * 2 + n * cell_w
    h = pad_top + cell_h + pad_bottom

    canvas = Image.new("RGBA", (w, h), (23, 17, 30, 255))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    rec = RECIPES.get(showcase_recipe, list(RECIPES.values())[0])
    draw.text((pad_side, 20), f"CHRONOS CHRISTMAS TOY FINISH PALETTES — SHOWCASE: {rec['name'].upper()}", fill=(255, 230, 160, 255), font=font)
    draw.text((pad_side, 42), f"Recipe: {rec['id']} • Native 16x16 Pixel Art (Previewed at 6x upscale / 96x96)", fill=(180, 170, 195, 255), font=font)

    grid = composite_toy_grid(rec["body"], rec["mover"], rec["core"])

    for idx, fid in enumerate(finish_list):
        fdef = FINISH_DEFS[fid]
        x = pad_side + idx * cell_w
        y = pad_top

        # Card
        draw.rounded_rectangle([x + 4, y + 4, x + cell_w - 8, y + cell_h - 8], radius=8, fill=(34, 25, 44, 255), outline=(58, 43, 74, 255))

        im16 = render_image(grid, fid)
        im96 = upscale_nearest(im16, 6)

        sprite_x = x + (cell_w - 96) // 2
        sprite_y = y + 16
        canvas.paste(im96, (sprite_x, sprite_y), im96)

        # Finish Name & Base Hex
        fname = fdef["name"]
        fhex = fdef["base"]
        draw.text((x + 16, y + 124), fname, fill=(255, 255, 255, 255), font=font)
        draw.text((x + 16, y + 140), f"Base: {fhex}", fill=(180, 170, 195, 255), font=font)

        # Color swatch dot
        r_p = get_finish_palette(fid)["P"]
        draw.ellipse([x + 16, y + 158, x + 30, y + 172], fill=r_p, outline=(255, 255, 255, 180))
        if fdef.get("accent"):
            r_a = get_finish_palette(fid)["A"]
            draw.ellipse([x + 36, y + 158, x + 50, y + 172], fill=r_a, outline=(255, 255, 255, 180))
            draw.text((x + 56, y + 160), "two-tone", fill=(140, 130, 155, 255), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Chronos Christmas Toy Workshop build tool")
    parser.add_argument("--toy", help="Build only specific toy recipe ID")
    parser.add_argument("--finish", help="Build only specific finish ID")
    parser.add_argument("--preview", action="store_true", help="Generate only preview contact sheets")

    args = parser.parse_args()

    # If only preview requested
    if args.preview:
        p1 = generate_preview_all_70(TOOLS_TOYS_DIR / "preview_all_70.png")
        p2 = generate_preview_finishes(TOOLS_TOYS_DIR / "preview_finishes.png")
        print(f"Generated previews:\n  {p1}\n  {p2}")
        return

    # Specific toy / finish filters
    recipes_to_build = [args.toy] if args.toy else list(RECIPES.keys())
    finishes_to_build = [args.finish] if args.finish else list(FINISH_DEFS.keys())

    # Ensure output directories exist
    TOY_ICONS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_ICONS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Building {len(recipes_to_build)} recipes across {len(finishes_to_build)} finishes...")

    toy_count = 0
    for rid in recipes_to_build:
        for fid in finishes_to_build:
            build_toy_icon(rid, fid, TOY_ICONS_DIR)
            toy_count += 1

    print(f"  Generated {toy_count} toy icons in {TOY_ICONS_DIR}")

    # Build 20 part icons (only if full build)
    part_count = 0
    if not args.toy and not args.finish:
        parts_gen = build_part_icons(ASSETS_ICONS_DIR)
        part_count = len(parts_gen)
        print(f"  Generated {part_count} part icon files across 20 parts in {ASSETS_ICONS_DIR}")

        # Build data json
        json_file = build_data_json()
        print(f"  Exported catalog data to {json_file}")

        # Build preview contact sheets
        p1 = generate_preview_all_70(TOOLS_TOYS_DIR / "preview_all_70.png")
        p2 = generate_preview_finishes(TOOLS_TOYS_DIR / "preview_finishes.png")
        print(f"  Generated contact sheets:\n    {p1}\n    {p2}")

    print("Build complete!")


if __name__ == "__main__":
    main()
