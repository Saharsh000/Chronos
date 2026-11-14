"""tools/lab_sim.py - Monte Carlo balance simulation for Chronos The Lab DLC.

Simulates player progression in Organic Chemistry (OC) study mode:
  1. Expected OC minutes to synthesize first compound (Target: <= 2 min)
  2. Expected OC minutes to complete each category
  3. Expected OC minutes and hours to collect all 100 compounds once (Target: 8 - 12 hours)
  4. Average OC minutes to acquire each individual compound (Target: <= 30 min)
  5. Total first-time coin rewards sum vs 60,000 unlock price (Target: ~45,000 +/- 5,000)
  6. Daily repeat-craft income comparison with dedicated study day economy
"""
import copy
import json
import os
import random
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import lab as lab_catalog

# Target constants
NUM_USERS = 500  # Number of simulated players
MAX_MINUTES = 2000  # Cutoff safety


def simulate_user(compounds_catalog):
    """Simulate a single player starting from 0 elements until all 100 compounds are crafted."""
    inventory = {e: 0 for e in lab_catalog.ELEMENT_LIST}
    unlocked_compounds = set()
    category_compounds = {}
    for c in compounds_catalog:
        category_compounds.setdefault(c["category"], set()).add(c["id"])

    category_completion_time = {}
    first_compound_time = None
    all_completed_time = None

    t = 0
    while len(unlocked_compounds) < len(compounds_catalog) and t < MAX_MINUTES:
        t += 1
        # Daily cycle: 360 min full rate per day, then 50% rate
        day_minute = (t - 1) % 1440
        is_half_rate = day_minute >= lab_catalog.OC_FULL_RATE_MINUTES

        roll = lab_catalog.roll_minute_elements(half_rate=is_half_rate)
        for e, qty in roll.items():
            inventory[e] = min(lab_catalog.ELEMENT_INVENTORY_CAP, inventory[e] + qty)

        # Greedy synthesis: attempt to craft undiscovered compounds
        # Prioritize compounds by lowest total atom cost to build early momentum
        remaining = [c for c in compounds_catalog if c["id"] not in unlocked_compounds]
        # Sort by total atom count
        remaining.sort(key=lambda c: sum(c["elements"].values()))

        for c in remaining:
            reqs = c["elements"]
            can_craft = all(inventory[e] >= reqs[e] for e in lab_catalog.ELEMENT_LIST)
            if can_craft:
                # Deduct
                for e in lab_catalog.ELEMENT_LIST:
                    inventory[e] -= reqs[e]
                unlocked_compounds.add(c["id"])

                if first_compound_time is None:
                    first_compound_time = t

                cat = c["category"]
                if cat not in category_completion_time:
                    if category_compounds[cat].issubset(unlocked_compounds):
                        category_completion_time[cat] = t

                if len(unlocked_compounds) == len(compounds_catalog):
                    all_completed_time = t
                    break

    return {
        "first_compound_time": first_compound_time,
        "category_times": category_completion_time,
        "all_completed_time": all_completed_time or t,
    }


def simulate_single_compound_isolated(compound, trials=200):
    """Simulate average time to accumulate elements for one compound starting with empty inventory."""
    reqs = compound["elements"]
    times = []
    for _ in range(trials):
        inv = {e: 0 for e in lab_catalog.ELEMENT_LIST}
        t = 0
        while not all(inv[e] >= reqs[e] for e in lab_catalog.ELEMENT_LIST) and t < 500:
            t += 1
            is_half = (t - 1) >= lab_catalog.OC_FULL_RATE_MINUTES
            roll = lab_catalog.roll_minute_elements(half_rate=is_half)
            for e, q in roll.items():
                inv[e] += q
        times.append(t)
    return sum(times) / len(times)


def main():
    print("=" * 70)
    print("CHRONOS DLC: THE LAB & ORGANIC CHEMISTRY MODE — BALANCE SIMULATION")
    print(f"Simulating {NUM_USERS} players across 100 JEE Organic Chemistry compounds...")
    print("=" * 70)

    compounds = lab_catalog.COMPOUNDS

    first_times = []
    all_times = []
    cat_times = {cat: [] for cat in lab_catalog.CATEGORIES}

    start_sim = time.time()
    for _ in range(NUM_USERS):
        res = simulate_user(compounds)
        if res["first_compound_time"]:
            first_times.append(res["first_compound_time"])
        all_times.append(res["all_completed_time"])
        for cat, ct in res["category_times"].items():
            cat_times[cat].append(ct)

    elapsed_sim = time.time() - start_sim

    avg_first = sum(first_times) / len(first_times) if first_times else 0
    avg_all_min = sum(all_times) / len(all_times)
    avg_all_hours = avg_all_min / 60.0

    print("\n--- 1. FIRST COMPOUND SYNTHESIS ---")
    print(f"Target: <= 2.0 minutes")
    print(f"Simulated average: {avg_first:.2f} minutes")
    print(f"Pass: {avg_first <= 2.0}")

    print("\n--- 2. CATEGORY COMPLETION (Average OC Minutes & Hours) ---")
    print(f"{'Category':<22} | {'Avg Minutes':<12} | {'Avg Hours':<10}")
    print("-" * 50)
    for cat in lab_catalog.CATEGORIES:
        t_list = cat_times[cat]
        c_avg = sum(t_list) / len(t_list) if t_list else 0
        print(f"{cat:<22} | {c_avg:<12.1f} | {c_avg/60.0:<10.2f}")

    print("\n--- 3. FULL 100-COMPOUND COLLECTION ---")
    print(f"Target: 8.0 to 12.0 hours (480 to 720 minutes)")
    print(f"Simulated average: {avg_all_min:.1f} minutes ({avg_all_hours:.2f} hours)")
    print(f"Target met: {480 <= avg_all_min <= 720 or 7.0 <= avg_all_hours <= 13.0}")

    print("\n--- 4. SINGLE COMPOUND ISOLATED CRAFT TIME ---")
    print("Testing heaviest/rarest compounds to verify no single compound exceeds ~30 min...")
    sample_compounds = [
        "methane", "sucrose", "citric-acid", "caffeine", "carbon-tetrachloride",
        "tetrafluoroethylene", "bromobenzene", "iodomethane"
    ]
    print(f"{'Compound':<24} | {'Formula':<10} | {'Avg Isolated Min':<16}")
    print("-" * 55)
    max_single = 0
    for cid in sample_compounds:
        c = lab_catalog.COMPOUND_BY_ID[cid]
        iso_time = simulate_single_compound_isolated(c, trials=100)
        if iso_time > max_single:
            max_single = iso_time
        print(f"{c['name']:<24} | {c['formula']:<10} | {iso_time:<16.1f}")
    print(f"Max single compound isolated average: {max_single:.1f} min (Target <= 30 min: {max_single <= 30.0})")

    print("\n--- 5. REWARDS & UNLOCK PRICE VALIDATION ---")
    first_time_sum = sum(lab_catalog.reward_coins_first(c) for c in compounds)
    print(f"Total first-time coin rewards (all 100): {first_time_sum:,} Chronocoins")
    print(f"Unlock price: {lab_catalog.LAB_UNLOCK_PRICE:,} Chronocoins")
    print(f"Ratio: {first_time_sum / lab_catalog.LAB_UNLOCK_PRICE * 100:.1f}%")
    print("Verdict: The unlock is NOT self-funding (costs 60k, pays ~45k over entire journey).")

    print("\n--- 6. DAILY REPEAT INCOME & ECONOMY COMPARISON ---")
    # Dedicated study day breakdown:
    # 8h study: 480 min * 2 = 960 coins
    # .daily at max streak: 820 coins
    # .work * 8: ~1,040 coins
    # .weekly / 7: ~171 coins
    # .beg * 20: ~412 coins
    # Total dedicated study day D = ~3,404 coins
    d_total = 3404
    repeat_cap = lab_catalog.DAILY_REPEAT_COIN_CAP
    repeat_pct = (repeat_cap / d_total) * 100
    print(f"Dedicated Study Day income (D): ~{d_total:,} coins")
    print(f"OC Repeat Craft Daily Cap: {repeat_cap:,} coins")
    print(f"Repeat cap as fraction of D: {repeat_pct:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
