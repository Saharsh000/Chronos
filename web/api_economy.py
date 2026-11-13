"""Economy on the web: wallet, daily/work/beg/weekly, shop, bag, boosts, boxes,
titles and the Top-3 perks - the twin of cogs/economy.py (+ `.openbox` from
cogs/halloween.py). Same DB methods, same random ranges, same cooldowns, same
Halloween extras as the bot. Replies stay in the browser; only what the bot
announces on its own (achievements, Top-3 perk) is mirrored to Discord."""
from __future__ import annotations

import datetime as dt
import logging
import random
import time
from typing import Any, Optional

import config
from utils import economy, streaks
from utils import food as food_catalog
from utils import halloween as halloween_catalog
from utils import pets as pet_catalog
from utils.beg_scenarios import roll_beg_scenario

from .common import Ctx, Routes, fail

log = logging.getLogger("web.economy")
routes = Routes()

MAX_BUY = 1000


# ---------------------------------------------------------------------- #
# catalog helpers
# ---------------------------------------------------------------------- #
async def full_catalog(c: Ctx) -> list[dict[str, Any]]:
    """The shop exactly as `.shop` lists it: SHOP_ORDER, then this server's custom tags."""
    out = []
    for n, item_id in enumerate(economy.SHOP_ORDER, start=1):
        si = economy.SHOP_ITEMS.get(item_id)
        if not si:
            continue
        t = si["type"]
        icon = ("xp_boost" if "xp" in item_id else "coin_boost") if t == "boost" else \
               ("mystery_box" if "box" in item_id else "streak_freeze") if t == "consumable" else "title_scroll"
        out.append({"id": item_id, "num": n, "name": si["name"], "type": t, "desc": si.get("description", ""),
                    "price": si["price"], "emoji": si.get("emoji", ""), "icon": icon,
                    "title_text": si.get("title_text"),
                    "duration_minutes": si.get("duration_minutes"), "multiplier": si.get("multiplier")})
    try:
        for item_id, ct in (await c.db.get_custom_tags(c.gid)).items():
            out.append({"id": item_id, "num": len(out) + 1, "name": ct.get("name", item_id), "type": "title",
                        "server_role": True, "desc": ct.get("description", "Server custom cosmetic tag"),
                        "price": ct.get("price", 500), "emoji": ct.get("emoji", ""), "icon": "title_scroll",
                        "title_text": ct.get("title_text")})
    except Exception:
        log.exception("custom tags failed")
    return out


def item_meta(item_id: str, custom: dict[str, Any]) -> dict[str, Any]:
    """Name/icon/kind/help for anything that can sit in an inventory."""
    si = economy.SHOP_ITEMS.get(item_id) or custom.get(item_id)
    if si:
        t = si.get("type", "item")
        icon = ("xp_boost" if "xp" in item_id else "coin_boost") if t == "boost" else \
               ("mystery_box" if "box" in item_id else "streak_freeze") if t == "consumable" else "title_scroll"
        kind = {"boost": "Boost", "consumable": "Consumable", "title": "Title"}.get(t, "Item")
        return {"name": si.get("name", item_id), "icon": icon, "kind": kind, "desc": si.get("description", ""),
                "emoji": si.get("emoji", ""), "usable": t == "boost", "title_text": si.get("title_text")}
    fd = food_catalog.FOODS.get(item_id)
    if fd:
        return {"name": fd.get("name", item_id), "icon": f"food/{item_id}", "kind": "Pet food",
                "desc": f"+{fd.get('xp', 50)} pet XP. Feed it from the Pets page.", "emoji": fd.get("emoji", ""),
                "usable": False, "feedable": True}
    hb = halloween_catalog.HALLO_BOXES.get(item_id)
    if hb:
        return {"name": hb["name"], "icon": "mystery_box", "kind": "Hallo-Box", "desc": hb["description"],
                "emoji": hb.get("emoji", ""), "openable": True, "tier": hb["tier"], "color": f"#{hb['color']:06x}"}
    return {"name": item_id.replace("_", " ").title(), "icon": "mystery_box", "kind": "Item", "desc": "", "emoji": ""}


def resolve_item(text: str, custom: dict[str, Any]) -> Optional[str]:
    text = str(text).strip()
    if text.isdigit():
        i = int(text) - 1
        return economy.SHOP_ORDER[i] if 0 <= i < len(economy.SHOP_ORDER) else None
    found = economy.resolve_item_id(text)
    if found:
        return found
    if text in custom:
        return text
    return next((iid for iid, it in custom.items() if str(it.get("title_text", "")).lower() == text.lower()), None)


def level_events(c: Ctx, r: dict) -> None:
    if r.get("leveled_up"):
        c.emit("level_up", old_level=r["old_level"], new_level=r["new_level"])


def box_info(box_id: str) -> dict[str, Any]:
    b = halloween_catalog.get_box(box_id)
    return {"id": box_id, "name": b["name"], "emoji": b["emoji"], "tier": b["tier"], "color": f"#{b['color']:06x}"}


# ---------------------------------------------------------------------- #
# wallet
# ---------------------------------------------------------------------- #
@routes.get("/api/wallet")
async def wallet(c: Ctx):
    uid = c.uid
    if c.q("user"):
        if not (c.q("user") or "").isdigit() or not c.bridge.is_member(c.gid, int(c.q("user"))):
            raise fail("I couldn't find that member in this server.", 404, "no_member")
        uid = int(c.q("user"))
    cur = await c.db.get_or_create_currency(uid, c.gid)
    return {"user": c.person(uid), "coins": cur["coins"], "candy": cur.get("candy", 0),
            "lifetime_earned": cur["lifetime_earned"], "boxes_opened": cur.get("boxes_opened", 0),
            "items_purchased": cur.get("items_purchased", 0)}


# ---------------------------------------------------------------------- #
# rewards: daily / work / beg / weekly
# ---------------------------------------------------------------------- #
def _next_ist_midnight(now: int) -> int:
    d = dt.datetime.fromtimestamp(now, config.IST)
    return int((d + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


@routes.get("/api/rewards")
async def rewards(c: Ctx):
    now = int(time.time())
    st = await c.db.get_daily_status(c.uid, c.gid)
    claimed = st["last_claim_date"] == streaks.date_str(now)
    out: dict[str, Any] = {"now": now, "daily": {
        "available": not claimed, "next_at": _next_ist_midnight(now) if claimed else None,
        "streak": st["daily_streak"], "last_claim_date": st["last_claim_date"],
        "coins": [economy.DAILY_COINS_MIN, economy.DAILY_COINS_MAX], "xp": [economy.DAILY_XP_MIN, economy.DAILY_XP_MAX],
        "bonus_per_day": economy.DAILY_STREAK_BONUS_PER_DAY, "bonus_cap_days": economy.DAILY_STREAK_BONUS_CAP_DAYS,
        "box_every": economy.DAILY_BOX_STREAK_INTERVAL,
        "milestones": [{"days": d, "coins": m["coins"], "item": m.get("item")} for d, m in sorted(economy.DAILY_MILESTONES.items())]}}
    for key, cd, lo, hi, extra in (
        ("work", config.WORK_COOLDOWN_SECONDS, config.WORK_COINS_MIN, config.WORK_COINS_MAX, [config.WORK_XP_MIN, config.WORK_XP_MAX]),
        ("beg", config.BEG_COOLDOWN_SECONDS, config.BEG_COINS_MIN, config.BEG_COINS_MAX, None),
        ("weekly", config.WEEKLY_COOLDOWN_SECONDS, config.WEEKLY_COINS_MIN, config.WEEKLY_COINS_MAX, None),
    ):
        last = await c.db.get_cooldown(c.uid, c.gid, key)
        ready_at = (last + cd) if last is not None else now
        out[key] = {"available": ready_at <= now, "ready_at": ready_at, "retry_after": max(0, ready_at - now),
                    "cooldown": cd, "coins": [lo, hi], "xp": extra}
    out["beg"]["fail_chance"] = config.BEG_FAIL_CHANCE
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    out["wallet"] = {"coins": cur["coins"], "candy": cur.get("candy", 0)}
    return out


@routes.post("/api/rewards/daily")
async def claim_daily(c: Ctx):
    r = await c.db.claim_daily(c.uid, c.gid)
    if not r["success"]:
        raise fail(f"You've already claimed today's reward. Come back after 00:00 IST (current streak: {r['daily_streak']} days).",
                   409, "already_claimed", streak=r["daily_streak"], next_at=_next_ist_midnight(int(time.time())))
    out: dict[str, Any] = {k: r[k] for k in ("coins", "base_coins", "streak_bonus", "xp", "daily_streak", "new_balance", "bonus_box",
                                              "leveled_up", "old_level", "new_level")}
    if r["milestone"]:
        mi = r["milestone_item"]
        out["milestone"] = {"days": r["daily_streak"], "coins": r["milestone"]["coins"],
                            "item": ({"id": mi, "name": economy.SHOP_ITEMS.get(mi, {}).get("name", mi)} if mi else None)}
    # Halloween extras, exactly as `.daily` does
    candy = random.randint(30, 60)
    await c.db.add_candy(c.uid, c.gid, candy)
    streak = r["daily_streak"]
    box = "hbox_epic" if streak >= 30 else "hbox_rare" if streak >= 7 else "hbox_uncommon" if random.random() < 0.35 else "hbox_common"
    await c.db.add_item(c.uid, c.gid, box, 1)
    out["hallo"] = {"box": box_info(box), "candy": candy}
    log.info("DAILY CLAIM   | %s claimed in guild %s via web (streak=%s, coins=%s, xp=%s)", c.uid, c.gid, streak, r["coins"], r["xp"])
    level_events(c, r)
    out["achievements"] = [a.id for a in await c.after()]
    return out


@routes.post("/api/rewards/work")
async def claim_work(c: Ctx):
    r = await c.db.claim_work(c.uid, c.gid)
    if not r["success"]:
        raise fail("Not yet. Try again later.", 429, "cooldown", retry_after=r["retry_after"])
    out: dict[str, Any] = {k: r[k] for k in ("coins", "xp", "new_balance", "leveled_up", "old_level", "new_level")}
    if random.random() < 0.35:
        box = random.choices(["hbox_common", "hbox_uncommon", "hbox_rare"], weights=[0.75, 0.20, 0.05])[0]
        candy = random.randint(8, 18)
        await c.db.add_item(c.uid, c.gid, box, 1)
        await c.db.add_candy(c.uid, c.gid, candy)
        out["hallo"] = {"box": box_info(box), "candy": candy}
    log.info("WORK CLAIM    | %s claimed in guild %s via web (coins=%s)", c.uid, c.gid, r["coins"])
    level_events(c, r)
    out["achievements"] = [a.id for a in await c.after()]
    return out


@routes.post("/api/rewards/beg")
async def claim_beg(c: Ctx):
    r = await c.db.claim_beg(c.uid, c.gid)
    if not r["success"]:
        raise fail("Not yet. Try again later.", 429, "cooldown", retry_after=r["retry_after"])
    is_success = r["coins"] > 0
    scenario, payout = roll_beg_scenario(c.uid, is_success, r["coins"])
    balance = r["new_balance"]
    if payout > r["coins"]:
        extra = payout - r["coins"]
        await c.db._add_coins_raw(c.uid, c.gid, extra)
        await c.db.conn.commit()
        balance += extra
    out: dict[str, Any] = {"success": is_success, "coins": payout, "new_balance": balance,
                           "scene": {"npc": scenario.npc, "role": scenario.role, "title": scenario.title,
                                     "story": scenario.story, "quote": scenario.quote, "emoji": scenario.emoji}}
    if random.random() < 0.25:
        box = "hbox_common" if random.random() < 0.85 else "hbox_uncommon"
        candy = random.randint(4, 10)
        await c.db.add_item(c.uid, c.gid, box, 1)
        await c.db.add_candy(c.uid, c.gid, candy)
        out["hallo"] = {"box": box_info(box), "candy": candy}
    log.info("BEG CLAIM     | %s claimed in guild %s via web (npc=%r, coins=%s)", c.uid, c.gid, scenario.npc, payout)
    out["achievements"] = [a.id for a in await c.after()]
    return out


@routes.post("/api/rewards/weekly")
async def claim_weekly(c: Ctx):
    r = await c.db.claim_weekly(c.uid, c.gid)
    if not r["success"]:
        raise fail("Not yet. Try again later.", 429, "cooldown", retry_after=r["retry_after"])
    box = "hbox_legendary" if random.random() < 0.20 else "hbox_epic"
    candy = random.randint(180, 300)
    await c.db.add_item(c.uid, c.gid, box, 1)
    await c.db.add_candy(c.uid, c.gid, candy)
    log.info("WEEKLY CLAIM  | %s claimed in guild %s via web (coins=%s)", c.uid, c.gid, r["coins"])
    return {"coins": r["coins"], "new_balance": r["new_balance"], "mystery_box": True,
            "hallo": {"box": box_info(box), "candy": candy}, "achievements": [a.id for a in await c.after()]}


# ---------------------------------------------------------------------- #
# shop
# ---------------------------------------------------------------------- #
@routes.get("/api/shop")
async def shop(c: Ctx):
    cat = await full_catalog(c)
    inv = await c.db.get_inventory(c.uid, c.gid)
    stats = await c.db.get_or_create_user_stats(c.uid, c.gid)
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    equipped = stats.get("equipped_title")
    for it in cat:
        it["owned_qty"] = inv.get(it["id"], 0)
        if it["type"] == "title":
            it["owned"] = it["owned_qty"] > 0
            it["equipped"] = bool(equipped and equipped == it.get("title_text"))
    return {"items": cat, "coins": cur["coins"], "candy": cur.get("candy", 0), "equipped_title": equipped}


@routes.post("/api/shop/buy")
async def buy(c: Ctx):
    b = await c.body()
    custom = await c.db.get_custom_tags(c.gid)
    item_id = resolve_item(b.get("item", ""), custom)
    if item_id is None:
        raise fail("Couldn't find that item. Check the shop for the list.", 404, "not_found")
    try:
        qty = int(b.get("quantity", 1))
    except (TypeError, ValueError):
        raise fail("Quantity must be a whole number.", 400, "bad_quantity")
    if qty < 1 or qty > MAX_BUY:
        raise fail(f"Quantity must be between 1 and {MAX_BUY}.", 400, "bad_quantity")
    r = await c.db.buy_item(c.uid, c.gid, item_id, qty)
    if not r["success"]:
        reasons = {
            "insufficient_funds": ("You don't have enough Chronocoins for that.", 402),
            "already_owned": ("You already own that title.", 409),
            "not_found": ("That item doesn't exist.", 404),
            "title_quantity": ("You can only buy 1 of a title at a time - it's a one-time unlock.", 400),
            "event_item": ("That's a Halloween event item - get it from the Halloween page.", 400),
        }
        msg, status = reasons.get(r["reason"], ("Purchase failed.", 400))
        raise fail(msg, status, r["reason"])
    it = r["item"]
    log.info("SHOP BUY      | %s bought '%s' x%s in guild %s via web", c.uid, item_id, r["quantity"], c.gid)
    newly = await c.after()
    cur = await c.db.get_or_create_currency(c.uid, c.gid)
    return {"item": {"id": item_id, "name": it["name"], "emoji": it.get("emoji", ""), "type": it["type"],
                     "title_text": it.get("title_text")},
            "quantity": r["quantity"], "total_price": r["total_price"], "coins": cur["coins"],
            "owned_qty": await c.db.get_item_qty(c.uid, c.gid, item_id), "achievements": [a.id for a in newly]}


# ---------------------------------------------------------------------- #
# bag
# ---------------------------------------------------------------------- #
@routes.get("/api/bag")
async def bag(c: Ctx):
    uid = c.uid
    if c.q("user"):
        if not (c.q("user") or "").isdigit() or not c.bridge.is_member(c.gid, int(c.q("user"))):
            raise fail("I couldn't find that member in this server.", 404, "no_member")
        uid = int(c.q("user"))
    now = int(time.time())
    inv = await c.db.get_inventory(uid, c.gid)
    stats = await c.db.get_or_create_user_stats(uid, c.gid)
    cur = await c.db.get_or_create_currency(uid, c.gid)
    custom = await c.db.get_custom_tags(c.gid)
    items = []
    for item_id, qty in sorted(inv.items(), key=lambda kv: kv[0]):
        if qty <= 0:
            continue
        items.append({"id": item_id, "qty": qty, **item_meta(item_id, custom)})
    effects = []
    for eid, label in (("xp_boost", "XP Boost"), ("coin_boost", "Chronocoin Boost")):
        e = await c.db.get_active_effect(uid, c.gid, eid, now)
        if e:
            effects.append({"id": eid, "label": label, "multiplier": e["multiplier"], "expires_at": e["expires_at"],
                            "remaining": max(0, e["expires_at"] - now)})
    titles = []
    for item_id, it in list(economy.SHOP_ITEMS.items()) + list(custom.items()):
        if it.get("type") == "title" and inv.get(item_id, 0) > 0:
            titles.append({"id": item_id, "text": it["title_text"], "name": it.get("name", item_id)})
    return {"now": now, "user": c.person(uid), "me": uid == c.uid, "items": items, "effects": effects, "titles": titles,
            "equipped_title": stats.get("equipped_title"), "coins": cur["coins"], "candy": cur.get("candy", 0),
            "total_qty": sum(i["qty"] for i in items)}


@routes.post("/api/bag/use")
async def use_item(c: Ctx):
    b = await c.body()
    item_id = resolve_item(b.get("item", ""), {})
    if item_id is None or economy.SHOP_ITEMS.get(item_id, {}).get("type") != "boost":
        raise fail("That's not a usable boost. Try the XP Boost or the Chronocoin Boost.", 400, "not_a_boost")
    r = await c.db.use_boost_item(c.uid, c.gid, item_id)
    if not r["success"]:
        raise fail(f"You don't own a {economy.SHOP_ITEMS[item_id]['name']}.", 404, "not_owned")
    it = r["item"]
    return {"item": {"id": item_id, "name": it["name"]}, "multiplier": it["multiplier"],
            "duration_minutes": it["duration_minutes"], "expires_at": r["expires_at"]}


@routes.post("/api/bag/title")
async def set_title(c: Ctx):
    b = await c.body()
    title = b.get("title")
    if title is None or str(title).strip().lower() in ("", "none", "clear", "remove"):
        await c.db.set_equipped_title(c.uid, c.gid, None)
        return {"equipped_title": None}
    title = str(title).strip()
    lookup = {it["title_text"].lower(): (iid, it) for iid, it in economy.SHOP_ITEMS.items() if it["type"] == "title"}
    lookup.update({it["title_text"].lower(): (iid, it) for iid, it in (await c.db.get_custom_tags(c.gid)).items()})
    found = lookup.get(title.lower())
    if not found:
        raise fail("That's not a known title. Check the shop for available titles.", 404, "unknown_title")
    item_id, it = found
    if await c.db.get_item_qty(c.uid, c.gid, item_id) <= 0:
        hint = ("It's a Halloween event title - earn it from the Halloween page." if it.get("price", 0) <= 0
                else f"Buy it in the shop first: {it['title_text']}.")
        raise fail(f"You don't own that title yet. {hint}", 403, "not_owned")
    await c.db.set_equipped_title(c.uid, c.gid, it["title_text"])
    return {"equipped_title": it["title_text"]}


async def _open_hallo(c: Ctx, box_id: str, qty: int) -> dict[str, Any]:
    r = await c.db.open_hallo_box(c.uid, c.gid, box_id, qty)
    if not r["success"]:
        if r.get("reason") == "insufficient_qty":
            raise fail(f"You only have x{r.get('owned', 0)} of that box (tried to open x{qty}).", 409, "insufficient")
        raise fail("Failed to open box.", 400, "invalid_box")
    pets_out = []
    for p in r["pets"]:
        sid = p["species_id"]
        pd = pet_catalog.PETS.get(sid, {})
        stages = pd.get("stages", [])
        pets_out.append({"species_id": sid, "name": pd.get("name", sid.capitalize()), "species": pd.get("species", "Companion"),
                         "new_pet": bool(p.get("new_pet")), "pet_xp_bonus": p.get("pet_xp_bonus", 0), "coin_bonus": p.get("coin_bonus", 0),
                         "sprite": stages[0]["sprite"] if stages else None})
        if p.get("new_pet"):
            c.emit("pet_unlocked", species_id=sid, name=pd.get("name", sid))
    log.info("HALLO BOX OPEN | %s opened %s x%s in guild %s via web", c.uid, box_id, qty, c.gid)
    return {"kind": "hallo", "box": box_info(box_id), "quantity": qty, "candy": r["candy"], "coins": r["coins"], "pets": pets_out,
            "food": [{"id": f, "name": food_catalog.FOODS.get(f, {}).get("name", f), "qty": q} for f, q in r["food"].items()],
            "items": [{"id": i, "name": economy.SHOP_ITEMS.get(i, {}).get("name", i.replace("_", " ").title()), "qty": q}
                      for i, q in r["items"].items()]}


async def _open_mystery(c: Ctx) -> dict[str, Any]:
    r = await c.db.open_mystery_box(c.uid, c.gid)
    if not r["success"]:
        raise fail("You don't have a Mystery Box. Buy one in the shop.", 404, "not_owned")
    rw = r["reward"]
    out: dict[str, Any] = {"kind": "mystery", "reward": {"kind": rw["kind"]}}
    if rw["kind"] in ("coins", "xp"):
        out["reward"]["amount"] = rw["amount"]
    else:
        si = economy.SHOP_ITEMS.get(rw["item_id"], {})
        out["reward"].update({"item_id": rw["item_id"], "name": si.get("name", rw["item_id"]), "emoji": si.get("emoji", ""), "qty": rw["qty"]})
    out.update({k: r[k] for k in ("leveled_up", "old_level", "new_level")})
    level_events(c, r)
    return out


@routes.post("/api/bag/open")
async def open_boxes(c: Ctx):
    """`.openbox`: box = auto | all | mystery | common|uncommon|rare|epic|legendary."""
    b = await c.body()
    try:
        qty = int(b.get("qty", 1))
    except (TypeError, ValueError):
        raise fail("Quantity must be a whole number.", 400, "bad_quantity")
    if qty < 1 or qty > 1000:
        raise fail("Quantity must be at least 1.", 400, "bad_quantity")
    which = str(b.get("box") or "auto").strip().lower()
    inv = await c.db.get_inventory(c.uid, c.gid)
    openings: list[dict[str, Any]] = []
    if which in ("all", "every", "everything"):
        owned = [(bid, inv[bid]) for bid in halloween_catalog.HALLO_BOX_ORDER if inv.get(bid, 0) > 0]
        if not owned:
            raise fail("You don't have any Hallo-Boxes to open. Find them while studying or in your daily reward.", 404, "no_boxes")
        for bid, q in owned:
            openings.append(await _open_hallo(c, bid, q))
    elif which == "auto":
        pick = next((bid for bid in reversed(halloween_catalog.HALLO_BOX_ORDER) if inv.get(bid, 0) > 0), None)
        if pick:
            openings.append(await _open_hallo(c, pick, 1))
        elif inv.get("mystery_box", 0) > 0:
            openings.append(await _open_mystery(c))
        else:
            raise fail("You don't have any boxes to open. Study, claim your daily, or buy a Mystery Box in the shop.", 404, "no_boxes")
    elif which in ("mystery", "mystery_box", "mysterybox", "gift"):
        openings.append(await _open_mystery(c))
    else:
        box_id = halloween_catalog.resolve_box_id(which)
        if not box_id:
            raise fail("Unknown box tier. Valid tiers: common, uncommon, rare, epic, legendary.", 400, "invalid_box")
        openings.append(await _open_hallo(c, box_id, qty))
    return {"openings": openings, "achievements": [a.id for a in await c.after()]}


# ---------------------------------------------------------------------- #
# Top-3 daily perks (`.dailyperks`)
# ---------------------------------------------------------------------- #
PERK_TEXT = {
    1: ("Rank #1 Sovereign", "+100% XP & coin gain (2h)", 120, "1x Ancient Mystery Chest"),
    2: ("Rank #2 Ascendant", "+100% XP boost (1.5h)", 80, "1x Glacial Streak Freeze"),
    3: ("Rank #3 Vanguard", "+100% coin boost (1h)", 50, "1x Bottle o' XP Elixir"),
}


@routes.get("/api/perks")
async def perks(c: Ctx):
    now = int(time.time())
    today = streaks.date_str(now)
    top3 = await c.db.get_top3_members(c.gid)
    holders, my_rank = [], None
    for i in range(3):
        title, boost, coins, item = PERK_TEXT[i + 1]
        row: dict[str, Any] = {"rank": i + 1, "title": title, "boost": boost, "coins": coins, "item": item, "holder": None, "claimed": False}
        if i < len(top3):
            uid, secs = top3[i]
            row["holder"] = c.person(uid)
            row["seconds"] = secs
            row["claimed"] = bool(await c.db.get_top3_daily_claim(uid, c.gid, today))
            if uid == c.uid:
                my_rank = i + 1
        holders.append(row)
    status, perk = "outside", None
    if my_rank:
        if await c.db.get_top3_daily_claim(c.uid, c.gid, today):
            status = "claimed"
        else:   # like the bot: viewing the perks on your first command of the day activates them
            perk = await c.db.claim_top3_daily_perk(c.uid, c.gid, my_rank, today, now=now)
            status = "activated" if perk else "ready"
            if perk:
                c.emit("top3_perk", **perk)
                from . import mirror
                await c.mirror(embed=mirror.top3_embed(c.me, c.uid, perk, my_rank))
    return {"holders": holders, "my_rank": my_rank, "status": status, "perk": perk}
