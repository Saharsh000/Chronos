"""Compositing engine for Chronos Christmas toys.

Loads 16x16 source grids from tools/toys/src/, composites layers
(back mover, body, front/top/bottom mover, core, overrides),
applies finish palettes, and renders deterministic PNG images.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from tools.toys.palette import get_finish_palette

SRC_DIR = Path(__file__).resolve().parent / "src"


def parse_grid(text: str) -> list[list[str]]:
    """Parse a multi-line string into a 16x16 character grid."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) != 16:
        raise ValueError(f"Expected 16 rows, got {len(lines)}")
    grid: list[list[str]] = []
    for r, line in enumerate(lines):
        if len(line) != 16:
            raise ValueError(f"Row {r} expected 16 cols, got {len(line)}: {line!r}")
        grid.append(list(line))
    return grid


def load_grid_file(rel_path: str) -> list[list[str]]:
    """Load a text grid from tools/toys/src/."""
    fpath = SRC_DIR / rel_path
    if not fpath.exists():
        raise FileNotFoundError(f"Missing grid file: {fpath}")
    return parse_grid(fpath.read_text(encoding="utf-8"))


# Defined core patches per body: list of (x, y, char) tuples
CORE_PATCHES: dict[tuple[str, str], list[tuple[int, int, str]]] = {
    # --- TEDDY ---
    ("teddy", "glow"): [
        (7, 8, "*"),
        (6, 9, "#"), (7, 9, "*"), (8, 9, "+"), (9, 9, "!"),
        (7, 10, "#"), (8, 10, "+"),
    ],
    ("teddy", "music"): [
        (7, 8, "#"), (8, 8, "~"), (9, 8, "#"),
        (7, 9, "#"), (8, 9, "~"), (9, 9, "^"),
        (6, 10, "#"), (7, 10, "^"), (8, 10, "#"),
    ],

    # --- ROBOT ---
    ("robot", "glow"): [
        (7, 8, "*"),
        (6, 9, "#"), (7, 9, "*"), (8, 9, "+"), (9, 9, "!"),
        (7, 10, "#"), (8, 10, "+"),
    ],
    ("robot", "music"): [
        (7, 8, "#"), (8, 8, "~"), (9, 8, "#"),
        (7, 9, "#"), (8, 9, "~"), (9, 9, "^"),
        (6, 10, "#"), (7, 10, "^"), (8, 10, "#"),
    ],

    # --- TRAIN ---
    # Glow: Locomotive front lantern headlamp projecting beam right
    ("train", "glow"): [
        (13, 6, "#"), (14, 6, "*"), (15, 6, "*"),
        (12, 7, "#"), (13, 7, "+"), (14, 7, "*"), (15, 7, "!"),
        (12, 8, "#"), (13, 8, "+"), (14, 8, "#"),
    ],
    # Music: Brass chime whistle / bell on cab roof
    ("train", "music"): [
        (5, 2, "#"), (6, 2, "~"), (7, 2, "#"),
        (5, 3, "#"), (6, 3, "~"), (7, 3, "^"),
        (6, 4, "#"),
    ],

    # --- DUCK ---
    ("duck", "glow"): [
        (6, 8, "*"),
        (5, 9, "#"), (6, 9, "*"), (7, 9, "+"), (8, 9, "!"),
        (6, 10, "#"), (7, 10, "+"),
    ],
    ("duck", "music"): [
        (6, 8, "#"), (7, 8, "~"), (8, 8, "#"),
        (6, 9, "#"), (7, 9, "~"), (8, 9, "^"),
        (5, 10, "#"), (6, 10, "^"), (7, 10, "#"),
    ],

    # --- SOLDIER ---
    ("soldier", "glow"): [
        (7, 8, "*"),
        (6, 9, "#"), (7, 9, "*"), (8, 9, "+"), (9, 9, "!"),
        (7, 10, "#"), (8, 10, "+"),
    ],
    ("soldier", "music"): [
        (7, 8, "#"), (8, 8, "~"), (9, 8, "#"),
        (7, 9, "#"), (8, 9, "~"), (9, 9, "^"),
        (6, 10, "#"), (7, 10, "^"), (8, 10, "#"),
    ],

    # --- DOLL ---
    ("doll", "glow"): [
        (7, 8, "*"),
        (6, 9, "#"), (7, 9, "*"), (8, 9, "+"), (9, 9, "!"),
        (7, 10, "#"), (8, 10, "+"),
    ],
    ("doll", "music"): [
        (7, 8, "#"), (8, 8, "~"), (9, 8, "#"),
        (7, 9, "#"), (8, 9, "~"), (9, 9, "^"),
        (6, 10, "#"), (7, 10, "^"), (8, 10, "#"),
    ],

    # --- SNOWMAN ---
    ("snowman", "glow"): [
        (7, 9, "*"),
        (6, 10, "#"), (7, 10, "*"), (8, 10, "+"), (9, 10, "!"),
        (7, 11, "#"), (8, 11, "+"),
    ],
    ("snowman", "music"): [
        (6, 7, "#"), (7, 7, "~"), (8, 7, "#"),
        (6, 8, "#"), (7, 8, "~"), (8, 8, "^"),
        (5, 9, "#"), (6, 9, "^"), (7, 9, "#"),
    ],
}


def composite_toy_grid(body_id: str, mover_id: str, core_id: str) -> list[list[str]]:
    """Composite the 16x16 grid for a toy recipe."""
    override_path = SRC_DIR / "overrides" / f"{body_id}__{mover_id}.txt"

    if override_path.exists():
        # Bespoke handcrafted composite for clashing/special combos
        base_grid = load_grid_file(f"overrides/{body_id}__{mover_id}.txt")
    else:
        # Standard layered compositing
        body_grid = load_grid_file(f"bodies/{body_id}.txt")
        mover_grid = load_grid_file(f"movers/{mover_id}.txt")

        base_grid = [["." for _ in range(16)] for _ in range(16)]

        # Back movers go behind body (e.g. windup key, rocket)
        if mover_id in ("windup_key", "rocket"):
            for y in range(16):
                for x in range(16):
                    ch = mover_grid[y][x]
                    if ch != ".":
                        base_grid[y][x] = ch
            for y in range(16):
                for x in range(16):
                    ch = body_grid[y][x]
                    if ch != ".":
                        base_grid[y][x] = ch
        else:
            # Body first
            for y in range(16):
                for x in range(16):
                    ch = body_grid[y][x]
                    if ch != ".":
                        base_grid[y][x] = ch
            # Top / bottom movers overlay
            for y in range(16):
                for x in range(16):
                    ch = mover_grid[y][x]
                    if ch != ".":
                        # For wheels/spring at bottom, don't erase existing body outline if transparent
                        base_grid[y][x] = ch

    # Apply core patch
    core_patch = CORE_PATCHES.get((body_id, core_id), [])
    toy_grid = [list(row) for row in base_grid]
    for x, y, ch in core_patch:
        if 0 <= x < 16 and 0 <= y < 16:
            toy_grid[y][x] = ch

    return toy_grid


def render_image(grid: list[list[str]], finish_id: str) -> Image.Image:
    """Render a 16x16 grid to an RGBA PIL Image using a finish palette."""
    palette = get_finish_palette(finish_id)
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    pixels = im.load()

    for y in range(16):
        for x in range(16):
            ch = grid[y][x]
            if ch not in palette:
                raise ValueError(f"Unknown symbol {ch!r} at ({x}, {y})")
            pixels[x, y] = palette[ch]

    return im


def upscale_nearest(im: Image.Image, scale: int) -> Image.Image:
    """Upscale an image by integer scale factor using nearest-neighbor interpolation."""
    w, h = im.size
    return im.resize((w * scale, h * scale), Image.Resampling.NEAREST)
