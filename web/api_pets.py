"""Pets on the web: the twin of cogs/pets.py (.petshop .buypet .pets .pet .equip
.nickname .foodshop .buyfood .feed .sellfood). Same DB methods, prices, level
curve and error wording. Replies stay in the browser; a pet evolution is the one
thing the bot announces on its own, so that is mirrored to the check-in channel."""
from __future__ import annotations

import logging
from typing import Any, Optional

import config
from utils import food as food_catalog
from utils import pets as pet_catalog

from .common import Ctx, Routes, fail

log = logging.getLogger("web.pets")
routes = Routes()

MAX_QTY = 1000


# ---------------------------------------------------------------------- #
# serialisers
# ---------------------------------------------------------------------- #
def tier_block(tier: str) -> dict[str, Any]:
    t = pet_catalog.TIER_INFO[tier]
    return {"key": tier, "label": t["label"], "color": f"#{t['color']:06x}"}


def stage_block(s: dict[str, Any]) -> dict[str, Any]:
    return {"name": s["name"], "sprite": s["sprite"], "level": s["level"], "badge": s["badge"],
            "badge_label": pet_catalog.BADGE_LABELS[s["badge"]]}


def pet_block(row: dict[str, Any]) -> dict[str, Any]:
    sid = row["species_id"]
    sp = pet_catalog.PETS[sid]
    stage = pet_catalog.stage_for_level(sid, row["level"])
    nxt = pet_catalog.next_stage(sid, row["level"])
    into, needed, _ = pet_catalog.xp_progress(row["xp"])
    return {"species_id": sid, "nickname": row["nickname"], "default_name": sp["name"], "archetype": sp["species"],
            "desc": sp.get("desc", ""), "tier": tier_block(sp["tier"]), "level": row["level"], "xp": row["xp"],
            "xp_into": into, "xp_needed": needed, "equipped": bool(row["equipped"]), "acquired_at": row.get("acquired_at"),
            "stage": stage_block(stage), "next_stage": stage_block(nxt) if nxt else None,
            "stages": [stage_block(s) for s in sp["stages"]]}


def food_block(fid: str, owned: int = 0) -> dict[str, Any]:
    f = food_catalog.FOODS[fid]
    ti = food_catalog.FOOD_TIER_INFO[f["tier"]]
    return {"id": fid, "name": f["name"], "xp": f["xp"], "cost": f["cost"],
            "sell": round(f["cost"] * config.FOOD_SELL_RATE), "owned": owned,
            "tier": {"key": f["tier"], "label": ti["label"], "color": f"#{ti['color']:06x}"}}


async def resolve_owned(c: Ctx, text: Any) -> Optional[dict[str, Any]]:
    """Same matching as the bot: nickname first, then species id / default name / stage name."""
    owned = await c.db.get_owned_pets(c.uid, c.gid)
    needle = str(text or "").strip().lower()
    if not needle:
        return None
    for row in owned:
        if row["nickname"].lower() == needle:
            return row
    sid = pet_catalog.resolve_species(needle)
    if sid:
        for row in owned:
            if row["species_id"] == sid:
                return row
    return None


def qty_of(b: dict[str, Any]) -> int:
    try:
        q = int(b.get("quantity", 1))
    except (TypeError, ValueError):
        raise fail("Quantity must be a whole number.", 400, "bad_quantity")
    if q < 1 or q > MAX_QTY:
        raise fail(f"Quantity must be between 1 and {MAX_QTY}.", 400, "bad_quantity")
    return q


def food_id_of(b: dict[str, Any]) -> str:
    fid = food_catalog.resolve_food(str(b.get("food", "")))
    if fid is None:
        raise fail("Couldn't find that food. Check the food shop for names.", 404, "not_found")
    return fid


# ---------------------------------------------------------------------- #
# reads
# ---------------------------------------------------------------------- #
@routes.get("/api/pets")
async def pets(c: Ctx):
    """`.pets` (+ `.pet`): everything owned with full detail, food bag and wallet."""
    uid = c.uid
    if c.q("user"):
        if not (c.q("user") or "").isdigit() or not c.bridge.is_member(c.gid, int(c.q("user"))):
            raise fail("I couldn't find that member in this server.", 404, "no_member")
        uid = int(c.q("user"))
    owned = await c.db.get_owned_pets(uid, c.gid)
    food = await c.db.get_food_inventory(uid, c.gid)
    cur = await c.db.get_or_create_currency(uid, c.gid)
    stats = await c.db.get_or_create_user_stats(uid, c.gid)
    return {"user": c.person(uid), "me": uid == c.uid, "pets": [pet_block(r) for r in owned],
            "food": [food_block(f, q) for f, q in food.items() if q > 0],
            "coins": cur["coins"], "level": stats["level"], "unlock_level": config.PET_UNLOCK_LEVEL}


@routes.get("/api/pets/shop")
async def pet_shop(c: Ctx):
    """`.petshop`: every species by tier, with price and whether you can buy it right now."""
    owned = {p["species_id"] for p in await c.db.get_owned_pets(c.uid, c.gid)}
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    stats = await c.db.get_or_create_user_stats(c.uid, c.gid)
    tiers = []
    for tier in pet_catalog.TIER_ORDER:
        items = []
        for sid in pet_catalog.PETS_BY_TIER[tier]:
            sp = pet_catalog.PETS[sid]
            price = pet_catalog.pet_cost(sid)
            items.append({"species_id": sid, "name": sp["name"], "archetype": sp["species"], "desc": sp.get("desc", ""),
                          "price": price, "owned": sid in owned, "stages": [stage_block(s) for s in sp["stages"]],
                          "affordable": price <= cur["coins"]})
        tiers.append({**tier_block(tier), "base_price": pet_catalog.TIER_INFO[tier]["base_price"], "pets": items})
    return {"tiers": tiers, "coins": cur["coins"], "level": stats["level"], "unlock_level": config.PET_UNLOCK_LEVEL,
            "can_buy": stats["level"] >= config.PET_UNLOCK_LEVEL}


@routes.get("/api/pets/foodshop")
async def food_shop(c: Ctx):
    """`.foodshop`: every food by tier with XP, price, sell value and how many you own."""
    owned = await c.db.get_food_inventory(c.uid, c.gid)
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    tiers = []
    for tier in food_catalog.FOOD_TIER_ORDER:
        ti = food_catalog.FOOD_TIER_INFO[tier]
        tiers.append({"key": tier, "label": ti["label"], "color": f"#{ti['color']:06x}",
                      "foods": [food_block(f, owned.get(f, 0)) for f in food_catalog.FOODS_BY_TIER[tier]]})
    return {"tiers": tiers, "coins": cur["coins"], "sell_rate": config.FOOD_SELL_RATE}


# ---------------------------------------------------------------------- #
# pet actions
# ---------------------------------------------------------------------- #
@routes.post("/api/pets/buy")
async def buy_pet(c: Ctx):
    b = await c.body()
    sid = pet_catalog.resolve_species(str(b.get("species", "")))
    if sid is None:
        raise fail("Couldn't find that pet. Check the pet shop for names.", 404, "not_found")
    r = await c.db.buy_pet(c.uid, c.gid, sid)
    if not r["success"]:
        reasons = {
            "already_owned": ("You already own that pet.", 409),
            "not_found": ("That pet doesn't exist.", 404),
            "level_too_low": (f"You need to be Level {config.PET_UNLOCK_LEVEL}+ to buy a pet.", 403),
            "insufficient_funds": ("You don't have enough Chronocoins for that.", 402),
            "event_exclusive": ("That's a seasonal event pet. Earn it from the Halloween page.", 400),
        }
        msg, status = reasons.get(r["reason"], ("Purchase failed.", 400))
        raise fail(msg, status, r["reason"])
    log.info("PET BUY       | %s bought '%s' in guild %s for %s via web", c.uid, sid, c.gid, r["price"])
    newly = await c.after()
    sp = pet_catalog.PETS[sid]
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    return {"species_id": sid, "name": sp["name"], "archetype": sp["species"], "price": r["price"],
            "auto_equipped": r["auto_equipped"], "coins": cur["coins"], "sprite": sp["stages"][0]["sprite"],
            "achievements": [a.id for a in newly]}


@routes.post("/api/pets/equip")
async def equip(c: Ctx):
    row = await resolve_owned(c, (await c.body()).get("species"))
    if row is None:
        raise fail("You don't own a pet with that name. Check your pets.", 404, "not_owned")
    await c.db.equip_pet(c.uid, c.gid, row["species_id"])
    return {"species_id": row["species_id"], "nickname": row["nickname"]}


@routes.post("/api/pets/nickname")
async def nickname(c: Ctx):
    b = await c.body()
    row = await resolve_owned(c, b.get("species"))
    if row is None:
        raise fail("You don't own a pet with that name. Check your pets.", 404, "not_owned")
    new = str(b.get("nickname") or "").strip().replace("`", "'")
    if not new:
        raise fail("Nicknames can't be empty.", 400, "empty")
    if len(new) > 32:
        raise fail("Nicknames must be 32 characters or fewer.", 400, "too_long")
    await c.db.rename_pet(c.uid, c.gid, row["species_id"], new)
    return {"species_id": row["species_id"], "old": row["nickname"], "nickname": new}


# ---------------------------------------------------------------------- #
# food actions
# ---------------------------------------------------------------------- #
@routes.post("/api/pets/food/buy")
async def buy_food(c: Ctx):
    b = await c.body()
    fid, qty = food_id_of(b), qty_of(b)
    r = await c.db.buy_food(c.uid, c.gid, fid, qty)
    if not r["success"]:
        msg, status = {"not_found": ("That food doesn't exist.", 404),
                       "insufficient_funds": ("You don't have enough Chronocoins for that.", 402)}.get(r["reason"], ("Purchase failed.", 400))
        raise fail(msg, status, r["reason"])
    newly = await c.after()
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    return {"food": food_block(fid, (await c.db.get_food_inventory(c.uid, c.gid)).get(fid, 0)), "qty": r["qty"],
            "total_price": r["total_price"], "coins": cur["coins"], "achievements": [a.id for a in newly]}


@routes.post("/api/pets/feed")
async def feed(c: Ctx):
    b = await c.body()
    fid, qty = food_id_of(b), qty_of(b)
    r = await c.db.feed_pet(c.uid, c.gid, fid, qty)
    if not r["success"]:
        msg, status = {"not_found": ("That food doesn't exist.", 404),
                       "no_pet_equipped": ("You don't have a pet equipped. Equip one first.", 409),
                       "not_owned": ("You don't have enough of that. Buy some in the food shop.", 409)}.get(r["reason"], ("Feeding failed.", 400))
        raise fail(msg, status, r["reason"])
    f = food_catalog.FOODS[fid]
    log.info("PET FEED      | %s fed '%s' x%s to '%s' in guild %s via web", c.uid, fid, r["qty"], r["species_id"], c.gid)
    if r["evolved"] or r["leveled_up"]:
        c.emit("pet_evolved" if r["evolved"] else "pet_level_up", nickname=r["nickname"], species_id=r["species_id"],
               new_level=r["new_level"], new_stage=r["new_stage"]["name"])
    if r["evolved"]:   # the bot announces evolutions on its own, so Discord hears about this one too
        try:
            await c.mirror(content=f"<@{c.uid}>'s **{r['nickname']}** evolved: {r['old_stage']['name']} → **{r['new_stage']['name']}**!")
        except Exception:
            log.exception("pet evolution mirror failed")
    await c.after()
    return {"nickname": r["nickname"], "species_id": r["species_id"], "food": {"id": fid, "name": f["name"]}, "qty": r["qty"],
            "xp_gained": f["xp"] * r["qty"], "leveled_up": r["leveled_up"], "evolved": r["evolved"],
            "old_level": r["old_level"], "new_level": r["new_level"],
            "old_stage": stage_block(r["old_stage"]), "new_stage": stage_block(r["new_stage"])}


@routes.post("/api/pets/food/sell")
async def sell_food(c: Ctx):
    b = await c.body()
    fid, qty = food_id_of(b), qty_of(b)
    r = await c.db.sell_food(c.uid, c.gid, fid, qty)
    if not r["success"]:
        msg, status = {"not_found": ("That food doesn't exist.", 404),
                       "not_owned": ("You don't own that much of it.", 409)}.get(r["reason"], ("Sale failed.", 400))
        raise fail(msg, status, r["reason"])
    return {"food": {"id": fid, "name": food_catalog.FOODS[fid]["name"]}, "qty": r["qty"], "refund": r["refund"], "coins": r["new_balance"]}
