"""utils/lab.py - The Lab DLC core logic, catalog, and formulas.

Pure and content-only definitions, catalogs, and helpers for The Lab & OC mode.
Single source of truth for compounds, element drop rolls, crafting rewards,
and syllabus validation.
"""
from __future__ import annotations

import json
import os
import random
import re
from typing import Any, Optional

ELEMENT_LIST = ["C", "H", "O", "N", "Cl", "F", "Br", "I"]

ELEMENT_NAMES = {
    "C": "Carbon",
    "H": "Hydrogen",
    "O": "Oxygen",
    "N": "Nitrogen",
    "Cl": "Chlorine",
    "F": "Fluorine",
    "Br": "Bromine",
    "I": "Iodine",
}

ELEMENT_SYMBOLS = {
    "C": "C",
    "H": "H",
    "O": "O",
    "N": "N",
    "Cl": "Cl",
    "F": "F",
    "Br": "Br",
    "I": "I",
}

# The Lab unlock requirements
LAB_UNLOCK_PRICE = 60000
LAB_CHEMISTRY_HOURS_REQUIRED = 30.0
ELEMENT_INVENTORY_CAP = 500
DAILY_REPEAT_COIN_CAP = 1000
OC_FULL_RATE_HOURS = 6.0
OC_FULL_RATE_MINUTES = int(OC_FULL_RATE_HOURS * 60)  # 360 minutes

CATEGORY_TITLES = {
    "Alkanes": "Alkane Alchemist",
    "Alkenes": "Alkene Artificer",
    "Alkynes": "Alkyne Adept",
    "Cycloalkanes": "Ring Crafter",
    "Haloalkanes": "Halogen Handler",
    "Alcohols": "Distillation Master",
    "Phenols": "Aromatic Hydroxylist",
    "Ethers": "Ether Weaver",
    "Aldehydes": "Carbonyl Pioneer",
    "Ketones": "Ketone Crafter",
    "Carboxylic-Acids": "Acid Synthesizer",
    "Acid-Derivatives": "Acyl Specialist",
    "Nitrogen-Compounds": "Amine Artisan",
    "Aromatics": "Resonance Master",
    "Biomolecules": "Molecular Biologist",
    "Monomers": "Polymer Architect",
}

MILESTONE_REWARDS = {
    25: {"type": "item", "item_id": "mystery_box", "quantity": 1, "description": "1 Mystery Box"},
    50: {"type": "item", "item_id": "mystery_box", "quantity": 2, "description": "2 Mystery Boxes"},
    75: {"type": "title", "title": "Synthesis Virtuoso", "description": "Title: Synthesis Virtuoso"},
    100: {
        "type": "grandmaster",
        "title": "Grandmaster Chemist",
        "coins": 5000,
        "badge": "grandmaster_chemist",
        "description": "Title: Grandmaster Chemist + Profile Badge + 5,000 Coins",
    },
}


def parse_formula(formula: str) -> dict[str, int]:
    """Parse a molecular formula string into atom counts for the 8 Lab elements.
    e.g. 'CH4' -> {'C': 1, 'H': 4, 'O': 0, 'N': 0, 'Cl': 0, 'F': 0, 'Br': 0, 'I': 0}
    """
    counts = {e: 0 for e in ELEMENT_LIST}
    # Matches chemical element tokens (e.g., Cl, Br, C, H, O, N, F, I) and optional trailing numbers
    matches = re.findall(r"([A-Z][a-z]?)([0-9]*)", formula.strip())
    for elem, num_str in matches:
        if not elem:
            continue
        c = int(num_str) if num_str else 1
        if elem in counts:
            counts[elem] += c
        else:
            raise ValueError(f"Unknown or unsupported element '{elem}' in formula '{formula}'")
    return counts


# Load compounds data
_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "compounds.json")

with open(_DATA_PATH, "r", encoding="utf-8") as _f:
    COMPOUNDS: list[dict[str, Any]] = json.load(_f)

COMPOUND_BY_ID: dict[str, dict[str, Any]] = {c["id"]: c for c in COMPOUNDS}
COMPOUND_BY_NAME: dict[str, dict[str, Any]] = {c["name"].lower(): c for c in COMPOUNDS}

# Map normalized formula to list of matching compounds
COMPOUND_BY_FORMULA: dict[str, list[dict[str, Any]]] = {}
for c in COMPOUNDS:
    f_key = c["formula"].upper()
    COMPOUND_BY_FORMULA.setdefault(f_key, []).append(c)

CATEGORIES: list[str] = []
for c in COMPOUNDS:
    if c["category"] not in CATEGORIES:
        CATEGORIES.append(c["category"])


def heavy_atoms(compound: dict[str, Any]) -> int:
    """Number of non-hydrogen atoms in the compound."""
    elems = compound.get("elements", {})
    return sum(v for k, v in elems.items() if k != "H")


def halogen_count(compound: dict[str, Any]) -> int:
    """Number of F, Br, and I atoms in the compound (halogens that give special reward bonuses)."""
    elems = compound.get("elements", {})
    return elems.get("F", 0) + elems.get("Br", 0) + elems.get("I", 0)


def reward_coins_first(compound: dict[str, Any]) -> int:
    """Coins awarded the first time a user synthesizes a compound.
    Formula: 5 * (30 + 10 * heavy_atoms + 40 * halogen_count).
    Sum across all 100 compounds is calibrated to ~44,950 coins (target: ~45,000 ± 5,000).
    """
    return 5 * (30 + 10 * heavy_atoms(compound) + 40 * halogen_count(compound))


def reward_xp_first(compound: dict[str, Any]) -> int:
    """XP awarded the first time a user synthesizes a compound (coins // 2)."""
    return reward_coins_first(compound) // 2


def reward_coins_repeat(compound: dict[str, Any]) -> int:
    """Coins awarded for repeat synthesis of an already-discovered compound (20% of first time, min 1)."""
    return max(1, reward_coins_first(compound) * 20 // 100)


def reward_xp_repeat(compound: dict[str, Any]) -> int:
    """XP awarded for repeat synthesis (repeat coins // 2)."""
    return reward_coins_repeat(compound) // 2


def validate_compound(c: dict[str, Any]) -> list[str]:
    """Validate a compound dictionary against schema and chemical consistency."""
    errors = []
    for req in ("id", "name", "formula", "elements", "category", "fact"):
        if req not in c or not c[req]:
            errors.append(f"Missing required field '{req}' in compound {c.get('id', 'unknown')}")

    elems = c.get("elements", {})
    if set(elems.keys()) != set(ELEMENT_LIST):
        errors.append(f"Elements dict must contain exactly the 8 elements, got {set(elems.keys())}")

    try:
        parsed = parse_formula(c["formula"])
        for e in ELEMENT_LIST:
            if parsed.get(e, 0) != elems.get(e, 0):
                errors.append(
                    f"Formula '{c['formula']}' parse mismatch for {e}: parsed {parsed.get(e, 0)} != expected {elems.get(e, 0)}"
                )
    except Exception as ex:
        errors.append(f"Formula parse error for '{c.get('formula')}': {ex}")

    return errors


def roll_minute_elements(half_rate: bool = False) -> dict[str, int]:
    """Roll element drops for a single credited minute of an OC study session.
    Rates per minute:
      - C: 1 to 2 (avg 1.5)
      - H: 3 to 5 (avg 4.0)
      - O: 0 to 2 (avg 1.0)
      - N: 45% chance of 1
      - Cl: 25% chance of 1
      - F: 15% chance of 1
      - Br: 12% chance of 1
      - I: 10% chance of 1
    If half_rate is True (after 6 hours of OC time in an IST day), rolls are halved (50% chance or // 2).
    """
    res = {e: 0 for e in ELEMENT_LIST}

    c_roll = random.randint(1, 2)
    h_roll = random.randint(3, 5)
    o_roll = random.randint(0, 2)
    n_roll = 1 if random.random() < 0.45 else 0
    cl_roll = 1 if random.random() < 0.25 else 0
    f_roll = 1 if random.random() < 0.15 else 0
    br_roll = 1 if random.random() < 0.12 else 0
    i_roll = 1 if random.random() < 0.10 else 0

    if not half_rate:
        res["C"] = c_roll
        res["H"] = h_roll
        res["O"] = o_roll
        res["N"] = n_roll
        res["Cl"] = cl_roll
        res["F"] = f_roll
        res["Br"] = br_roll
        res["I"] = i_roll
    else:
        # At half rate: integer division or 50% Bernoulli reduction
        res["C"] = 1 if (c_roll > 1 and random.random() < 0.5) else (1 if random.random() < 0.75 else 0)
        res["H"] = max(1, h_roll // 2 + (1 if random.random() < (h_roll % 2 * 0.5) else 0))
        res["O"] = 1 if (o_roll > 0 and random.random() < 0.5) else 0
        res["N"] = 1 if (n_roll == 1 and random.random() < 0.5) else 0
        res["Cl"] = 1 if (cl_roll == 1 and random.random() < 0.5) else 0
        res["F"] = 1 if (f_roll == 1 and random.random() < 0.5) else 0
        res["Br"] = 1 if (br_roll == 1 and random.random() < 0.5) else 0
        res["I"] = 1 if (i_roll == 1 and random.random() < 0.5) else 0

    return res
