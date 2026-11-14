"""web/api_lab.py - Web API endpoints for The Lab DLC & Compound Synthesis.

CSRF-protected endpoints mirroring all bot Lab features to Chronoweb:
  - GET  /api/lab: unlock status, progress, element stores, daily stats
  - POST /api/lab/unlock: unlock The Lab (pays 60k coins atomically)
  - GET  /api/lab/elements: element inventory
  - POST /api/lab/synth: dry-run inspection & confirmed molecular synthesis
  - GET  /api/lab/compendium: 500-compound compendium with ??? silhouettes & facts
  - GET  /api/lab/discoveries: server-wide first discoverers map
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from utils import lab as lab_catalog

from . import mirror
from .common import Ctx, Routes, fail, ok

log = logging.getLogger("web.lab")
routes = Routes()


@routes.get("/api/lab", lock=False)
async def get_lab_status(c: Ctx):
    unlock = await c.db.get_lab_unlock(c.uid, c.gid)
    chem_hours = await c.db.get_lab_chemistry_hours(c.uid, c.gid)
    curr = await c.db.get_or_create_currency(c.uid, c.gid)
    unlocked = unlock is not None

    elements = await c.db.get_lab_elements(c.uid, c.gid) if unlocked else {e: 0 for e in lab_catalog.ELEMENT_LIST}
    user_compounds = await c.db.get_lab_compounds(c.uid, c.gid) if unlocked else {}
    daily = await c.db.get_lab_daily(c.uid, c.gid) if unlocked else {"repeat_coins": 0, "oc_minutes": 0}

    # Category progress
    cats_progress = []
    for cat in lab_catalog.CATEGORIES:
        cat_all = [comp for comp in lab_catalog.COMPOUNDS if comp["category"] == cat]
        crafted_in_cat = sum(1 for comp in cat_all if comp["id"] in user_compounds)
        cats_progress.append({
            "category": cat,
            "total": len(cat_all),
            "discovered": crafted_in_cat,
            "completed": (crafted_in_cat == len(cat_all)),
            "title": lab_catalog.CATEGORY_TITLES.get(cat),
        })

    can_unlock = (
        not unlocked
        and chem_hours >= lab_catalog.LAB_CHEMISTRY_HOURS_REQUIRED
        and curr["coins"] >= lab_catalog.LAB_UNLOCK_PRICE
    )

    return {
        "unlocked": unlocked,
        "unlocked_at": unlock["unlocked_at"] if unlock else None,
        "can_unlock": can_unlock,
        "chemistry_hours": round(chem_hours, 2),
        "required_chemistry_hours": lab_catalog.LAB_CHEMISTRY_HOURS_REQUIRED,
        "coins": curr["coins"],
        "required_coins": lab_catalog.LAB_UNLOCK_PRICE,
        "elements": elements,
        "element_cap": lab_catalog.ELEMENT_INVENTORY_CAP,
        "collection_count": len(user_compounds),
        "total_compounds": len(lab_catalog.COMPOUNDS),
        "categories": cats_progress,
        "daily": {
            "repeat_coins": daily["repeat_coins"],
            "repeat_cap": lab_catalog.DAILY_REPEAT_COIN_CAP,
            "oc_minutes": daily["oc_minutes"],
            "full_rate_minutes": lab_catalog.OC_FULL_RATE_MINUTES,
        },
    }


@routes.post("/api/lab/unlock")
async def unlock_lab(c: Ctx):
    existing = await c.db.get_lab_unlock(c.uid, c.gid)
    if existing:
        raise fail("The Lab is already unlocked for your account in this server.", 400, "already_unlocked")

    try:
        res = await c.db.set_lab_unlock(c.uid, c.gid)
    except ValueError as ex:
        err_msg = str(ex).lower()
        if "chemistry" in err_msg:
            raise fail("Insufficient chemistry hours. 30.0 hours required.", 400, "insufficient_chemistry_hours")
        if "chronocoins" in err_msg:
            raise fail(f"Insufficient Chronocoins. {lab_catalog.LAB_UNLOCK_PRICE:,} coins required.", 400, "insufficient_coins")
        raise fail(str(ex), 400, "unlock_failed")

    c.emit("lab_unlocked")
    await c.top3_perk()
    return {"ok": True, "unlocked": True, "unlocked_at": res["unlocked_at"]}


@routes.get("/api/lab/elements", lock=False)
async def get_elements(c: Ctx):
    unlock = await c.db.get_lab_unlock(c.uid, c.gid)
    if not unlock:
        raise fail("The Lab is locked. Unlock it first.", 403, "lab_locked")
    elements = await c.db.get_lab_elements(c.uid, c.gid)
    return {"elements": elements, "cap": lab_catalog.ELEMENT_INVENTORY_CAP}


@routes.post("/api/lab/synth")
async def synthesize_compound(c: Ctx):
    unlock = await c.db.get_lab_unlock(c.uid, c.gid)
    if not unlock:
        raise fail("The Lab is locked. Unlock it first.", 403, "lab_locked")

    body = await c.body()
    compound_query = str(body.get("compound", "")).strip()
    confirmed = bool(body.get("confirm", False))

    if not compound_query:
        raise fail("No compound specified.", 400, "missing_compound")

    clean_id = compound_query.lower().replace(" ", "-")
    compound = lab_catalog.COMPOUND_BY_ID.get(clean_id)
    if not compound:
        clean_name = compound_query.lower()
        compound = lab_catalog.COMPOUND_BY_NAME.get(clean_name)
    if not compound:
        f_key = compound_query.upper()
        if f_key in lab_catalog.COMPOUND_BY_FORMULA:
            compound = lab_catalog.COMPOUND_BY_FORMULA[f_key][0]

    if not compound:
        raise fail(f"Unknown compound '{compound_query}'.", 404, "unknown_compound")

    inv = await c.db.get_lab_elements(c.uid, c.gid)
    reqs = compound["elements"]
    missing = {}
    can_afford = True
    for elem, needed in reqs.items():
        have = inv.get(elem, 0)
        if have < needed:
            can_afford = False
            missing[elem] = {"needed": needed, "have": have, "short": needed - have}

    existing = await c.db.get_lab_compound(c.uid, c.gid, compound["id"])
    is_first = (existing is None or existing["times_crafted"] == 0)

    # If not confirmed, return dry-run inspection info
    if not confirmed:
        return {
            "ok": True,
            "dry_run": True,
            "compound": compound,
            "is_first_time": is_first,
            "cost": reqs,
            "can_afford": can_afford,
            "missing": missing,
            "expected_coins": lab_catalog.reward_coins_first(compound) if is_first else lab_catalog.reward_coins_repeat(compound),
            "expected_xp": lab_catalog.reward_xp_first(compound) if is_first else lab_catalog.reward_xp_repeat(compound),
        }

    if not can_afford:
        raise fail("Insufficient elements to synthesize this compound.", 400, "insufficient_elements", missing=missing)

    try:
        res = await c.db.craft_compound(c.uid, c.gid, compound["id"])
    except ValueError as ex:
        raise fail(str(ex), 400, "craft_failed")

    # Proactive Announcements via mirror
    if res["is_discoverer"]:
        await c.mirror(embed=mirror.lab_discovery_embed(c.me, c.uid, compound))
    if res["newly_completed_category"]:
        await c.mirror(embed=mirror.lab_category_completed_embed(c.me, c.uid, res["category"], res["category_title"]))
    if res["milestone_reward"]:
        await c.mirror(embed=mirror.lab_milestone_embed(c.me, c.uid, res["milestone_reward"]["count"], res["milestone_reward"]["description"]))

    c.emit("lab_compound_crafted", compound=compound["id"], times_crafted=res["times_crafted"])
    await c.top3_perk()

    return {"ok": True, "dry_run": False, **res}


@routes.get("/api/lab/compendium", lock=False)
async def get_compendium(c: Ctx):
    user_compounds = await c.db.get_lab_compounds(c.uid, c.gid)
    discoveries = await c.db.get_all_lab_discoveries(c.gid)

    filter_cat = c.request.query.get("category")
    compounds_out = []

    for comp in lab_catalog.COMPOUNDS:
        if filter_cat and comp["category"].lower() != filter_cat.lower().strip():
            continue

        cid = comp["id"]
        discovered = cid in user_compounds
        disc_info = discoveries.get(cid)
        first_discoverer_uid = disc_info["user_id"] if disc_info else None

        compounds_out.append({
            "id": cid,
            "name": comp["name"],
            "formula": comp["formula"],
            "structure": comp.get("structure") or comp.get("smiles") or comp["formula"],
            "category": comp["category"],
            "elements": comp["elements"],
            "smiles": comp.get("smiles"),
            "fact": comp["fact"],
            "total_atoms": sum(comp["elements"].values()),
            "discovered": discovered,
            "times_crafted": user_compounds[cid]["times_crafted"] if discovered else 0,
            "first_crafted_at": user_compounds[cid]["first_crafted_at"] if discovered else None,
            "first_discoverer_id": first_discoverer_uid,
            "is_your_discovery": (first_discoverer_uid == c.uid),
        })

    return {
        "compounds": compounds_out,
        "total_discovered": len(user_compounds),
        "total_compounds": len(lab_catalog.COMPOUNDS),
        "categories": lab_catalog.CATEGORIES,
    }


@routes.get("/api/lab/discoveries", lock=False)
async def get_discoveries(c: Ctx):
    discoveries = await c.db.get_all_lab_discoveries(c.gid)
    return {"discoveries": discoveries}
