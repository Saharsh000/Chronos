"""Halloween event on the web: the twin of cogs/halloween.py (.pumpkin [claim],
.boxes, .candyshop, .buycandy, .event). `.openbox` / `.boxes` actions live in
api_economy (`POST /api/bag/open`); this module adds the Jack-o'-Lantern pass,
the Candy Shop and the event info page. Same DB methods, same prices."""
from __future__ import annotations

import logging
from typing import Any

from utils import food as food_catalog
from utils import halloween as hc
from utils import pets as pet_catalog

from .common import Ctx, Routes, fail

log = logging.getLogger("web.halloween")
routes = Routes()

MAX_QTY = 1000


def box_label(box_id: str) -> dict[str, Any]:
    b = hc.get_box(box_id)
    return {"id": box_id, "name": b["name"] if b else box_id, "tier": b["tier"] if b else "common",
            "color": f"#{b['color']:06x}" if b else "#8895b3"}


def item_label(item_id: str) -> str:
    if item_id == "sugar_rush":
        return "Sugar Rush Boost"
    if item_id == "mystery_box":
        return "Mystery Box"
    return food_catalog.FOODS.get(item_id, {}).get("name", item_id.replace("_", " ").title())


def reward_block(lvl: dict[str, Any]) -> dict[str, Any]:
    return {"candy": lvl.get("candy", 0), "coins": lvl.get("coins", 0),
            "boxes": [{**box_label(b), "qty": q} for b, q in lvl.get("boxes", [])],
            "items": [{"id": i, "name": item_label(i), "qty": q} for i, q in lvl.get("items", [])],
            "title": lvl.get("title")}


def level_block_(lvl: dict[str, Any]) -> dict[str, Any]:
    return {"level": lvl["level"], "stage": lvl["stage"], "stage_name": lvl["stage_name"], "level_name": lvl["level_name"],
            "required_seconds": lvl["required_seconds"], "desc": lvl.get("desc", ""), "rewards": reward_block(lvl)}


def shop_block(key: str, owned_titles: set[str], owned_pets: set[str], sugar_qty: int, candy: int) -> dict[str, Any]:
    it = hc.CANDY_SHOP_ITEMS[key]
    owned = (it["type"] == "pet" and it["species_id"] in owned_pets) or (it["type"] == "title" and it["id"] in owned_titles)
    out = {"id": key, "type": it["type"], "name": it["name"], "desc": it["description"], "price": it["candy_price"],
           "owned": owned, "affordable": candy >= it["candy_price"], "single": it["type"] in ("pet", "title")}
    if it["type"] == "boost":
        out["owned_qty"] = sugar_qty
    if it["type"] == "pet":
        out["sprite"] = pet_catalog.PETS[it["species_id"]]["stages"][0]["sprite"]
    if it.get("title_text"):
        out["title_text"] = it["title_text"]
    return out


@routes.get("/api/halloween")
async def event(c: Ctx):
    """`.pumpkin` + `.boxes` + `.candyshop` + `.event` in one payload."""
    pas = await c.db.get_or_create_halloween_pass(c.uid, c.gid)
    secs, claimed = pas.get("study_seconds", 0), pas.get("claimed_level", 0)
    cur, nxt = hc.get_current_pass_level(secs), hc.get_next_pass_level(secs)
    cur_c = await c.db.get_or_create_currency(c.uid, c.gid)
    inv = await c.db.get_inventory(c.uid, c.gid)
    candy = cur_c.get("candy", 0)
    levels = []
    for lvl in hc.JACK_O_LANTERN_LEVELS:
        b = level_block_(lvl)
        b["status"] = "claimed" if lvl["level"] <= claimed else "ready" if lvl["level"] <= cur["level"] else "locked"
        levels.append(b)
    stats = await c.db.get_or_create_user_stats(c.uid, c.gid)
    owned_titles = set(stats.get("unlocked_titles") or [])
    if stats.get("equipped_title"):
        owned_titles.add(stats["equipped_title"])
    owned_titles |= {k for k in hc.CANDY_SHOP_ITEMS if inv.get(k, 0) > 0}
    owned_pets = {p["species_id"] for p in await c.db.get_owned_pets(c.uid, c.gid)}
    chances, per_box, hourly, totals = hc.tier_chances(), hc.expected_box_rates(), hc.study_hourly_estimate(), hc.pass_reward_totals()
    per_hour = hourly["candy_total"]
    boxes = [{**box_label(b), "qty": inv.get(b, 0), "desc": hc.get_box(b)["description"]} for b in hc.HALLO_BOX_ORDER]
    return {
        "candy": candy, "coins": cur_c["coins"],
        "pass": {"study_seconds": secs, "claimed_level": claimed, "level": cur["level"], "max_level": hc.MAX_PASS_LEVEL,
                 "current": level_block_(cur), "next": level_block_(nxt) if nxt else None,
                 "unclaimed": max(0, cur["level"] - claimed), "levels": levels},
        "boxes": boxes, "total_boxes": sum(b["qty"] for b in boxes), "mystery_boxes": inv.get("mystery_box", 0),
        "shop": [shop_block(k, owned_titles, owned_pets, inv.get("sugar_rush", 0), candy) for k in hc.CANDY_SHOP_ORDER],
        "info": {"drop_table": [{**box_label(b), "chance": chances[b]} for b, _ in hc.STUDY_BOX_ROLL_WEIGHTS],
                 "per_box": per_box, "hourly": hourly, "pace_hours": hc.JACK_O_LANTERN_LEVELS[-1]["required_seconds"] / 3600.0,
                 "totals": {"candy": totals["candy"], "coins": totals["coins"], "boxes": [{**box_label(b), "qty": q} for b, q in totals["boxes"].items()],
                            "items": [{"id": i, "name": item_label(i), "qty": q} for i, q in totals["items"].items()], "titles": totals["titles"]},
                 "shop_hours": {k: hc.CANDY_SHOP_ITEMS[k]["candy_price"] / per_hour for k in hc.CANDY_SHOP_ORDER}},
    }


@routes.post("/api/halloween/claim")
async def claim(c: Ctx):
    """`.pumpkin claim` / the Claim button."""
    r = await c.db.claim_all_halloween_rewards(c.uid, c.gid)
    if not r["success"]:
        raise fail("You've already claimed everything unlocked so far. Study more to carve your Jack-o'-Lantern further.", 409, "already_claimed")
    newly = await c.after()
    return {"new_claimed_level": r["new_claimed_level"], "from_level": r["new_claimed_level"] - len(r["claimed_levels"]) + 1,
            "candy": r["candy"], "coins": r["coins"], "boxes": [{**box_label(b), "qty": q} for b, q in r["boxes"].items()],
            "items": [{"id": i, "name": item_label(i), "qty": q} for i, q in r["items"]], "titles": r["titles"],
            "achievements": [a.id for a in newly]}


@routes.post("/api/halloween/buy")
async def buy(c: Ctx):
    """`.buycandy <item> [qty]` / the Candy Shop buttons."""
    b = await c.body()
    try:
        qty = int(b.get("quantity", 1))
    except (TypeError, ValueError):
        raise fail("Quantity must be a whole number.", 400, "bad_quantity")
    if qty < 1 or qty > MAX_QTY:
        raise fail("Quantity must be at least 1.", 400, "bad_quantity")
    r = await c.db.buy_candy_item(c.uid, c.gid, str(b.get("item", "")), qty)
    if not r["success"]:
        reason = r.get("reason")
        msg, status = {
            "insufficient_candy": (f"You don't have enough Candy. You need {r.get('required', 0):,}, you have {r.get('current', 0):,}.", 402),
            "already_owned": ("You already own this event-exclusive item.", 409),
            "single_only": ("You can only purchase 1 of this item at a time.", 400),
        }.get(reason, ("Couldn't find that item in the Candy Shop.", 404))
        raise fail(msg, status, reason or "not_found")
    item = r["item"]
    log.info("CANDY BUY      | %s bought '%s' x%s for %s candy in guild %s via web", c.uid, item["id"], qty, r["price"], c.gid)
    newly = await c.after()
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    out: dict[str, Any] = {"item": {"id": item["id"], "type": item["type"], "name": item["name"]}, "price": r["price"],
                           "quantity": r.get("quantity", 1), "candy": cur.get("candy", 0), "achievements": [a.id for a in newly]}
    if item["type"] == "pet":
        out["auto_equipped"] = bool(r.get("pet_result", {}).get("auto_equipped"))
    if item.get("title_text"):
        out["title_text"] = item["title_text"]
    return out
