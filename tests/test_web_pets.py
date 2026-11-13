from __future__ import annotations

import config
from utils import food as food_catalog
from utils import pets as pet_catalog
from tests.web_helpers import GID, OTHER, UID, WebCase


class PetsApiTests(WebCase):
    async def _level(self, lvl: int) -> None:
        await self.db.conn.execute("UPDATE user_stats SET level = ? WHERE user_id = ? AND guild_id = ?", (lvl, UID, GID))
        await self.db.conn.commit()

    async def test_shop_lists_tiers_and_prices(self) -> None:
        st, s = await self.get("/api/pets/shop")
        self.assertEqual(st, 200)
        self.assertEqual([t["key"] for t in s["tiers"]], pet_catalog.TIER_ORDER)
        bulb = next(p for t in s["tiers"] for p in t["pets"] if p["species_id"] == "bulbasaur")
        self.assertEqual(bulb["price"], pet_catalog.pet_cost("bulbasaur"))
        self.assertFalse(s["can_buy"])                      # level gate, same as `.buypet`

    async def test_buy_equip_rename_flow(self) -> None:
        st, e = await self.post("/api/pets/buy", {"species": "bulbasaur"})
        self.assertEqual((st, e["code"]), (403, "level_too_low"))
        await self._level(config.PET_UNLOCK_LEVEL)
        st, e = await self.post("/api/pets/buy", {"species": "bulbasaur"})
        self.assertEqual((st, e["code"]), (402, "insufficient_funds"))
        await self.db.add_coins(UID, GID, 100000)
        st, b = await self.post("/api/pets/buy", {"species": "Sprout"})   # nickname resolves like the bot
        self.assertEqual((st, b["species_id"], b["auto_equipped"]), (200, "bulbasaur", True))
        self.assertEqual(b["coins"], (await self.db.get_or_create_currency(UID, GID))["coins"])
        self.assertGreaterEqual(b["coins"], 100000 - pet_catalog.pet_cost("bulbasaur"))   # + any achievement payout
        self.assertEqual((await self.post("/api/pets/buy", {"species": "bulbasaur"}))[1]["code"], "already_owned")
        self.assertEqual((await self.post("/api/pets/buy", {"species": "pumpkaboo"}))[1]["code"], "event_exclusive")
        self.assertEqual((await self.post("/api/pets/buy", {"species": "nope"}))[0], 404)
        await self.post("/api/pets/buy", {"species": "squirtle"})
        st, q = await self.post("/api/pets/equip", {"species": "squirtle"})
        self.assertEqual(st, 200)
        eq = await self.db.get_equipped_pet(UID, GID)
        self.assertEqual(eq["species_id"], "squirtle")
        st, n = await self.post("/api/pets/nickname", {"species": "squirtle", "nickname": "  Shelly `x` "})
        self.assertEqual((st, n["nickname"]), (200, "Shelly 'x'"))
        self.assertEqual((await self.post("/api/pets/nickname", {"species": "squirtle", "nickname": "x" * 33}))[1]["code"], "too_long")
        self.assertEqual((await self.post("/api/pets/nickname", {"species": "squirtle", "nickname": "  "}))[1]["code"], "empty")
        self.assertEqual((await self.post("/api/pets/equip", {"species": "mewtwo"}))[0], 404)
        st, mine = await self.get("/api/pets")
        self.assertEqual({p["species_id"] for p in mine["pets"]}, {"bulbasaur", "squirtle"})
        self.assertEqual(next(p for p in mine["pets"] if p["equipped"])["nickname"], "Shelly 'x'")

    async def test_food_buy_feed_sell_and_evolution(self) -> None:
        await self._level(config.PET_UNLOCK_LEVEL)
        await self.db.add_coins(UID, GID, 200000)
        st, e = await self.post("/api/pets/feed", {"food": "bread"})
        self.assertEqual((st, e["code"]), (409, "no_pet_equipped"))
        await self.post("/api/pets/buy", {"species": "bulbasaur"})
        st, e = await self.post("/api/pets/feed", {"food": "bread"})
        self.assertEqual((st, e["code"]), (409, "not_owned"))
        before = (await self.db.get_or_create_currency(UID, GID))["coins"]
        st, b = await self.post("/api/pets/food/buy", {"food": "Bread", "quantity": 4})
        self.assertEqual((st, b["total_price"]), (200, 600))
        self.assertEqual(b["coins"], (await self.db.get_or_create_currency(UID, GID))["coins"])
        self.assertGreaterEqual(b["coins"], before - 600)
        self.assertEqual((await self.post("/api/pets/food/buy", {"food": "bread", "quantity": 0}))[1]["code"], "bad_quantity")
        st, f = await self.post("/api/pets/feed", {"food": "bread", "quantity": 2})
        self.assertEqual((st, f["xp_gained"]), (200, 90))
        self.assertEqual((await self.db.get_equipped_pet(UID, GID))["xp"], 90)
        st, s = await self.post("/api/pets/food/sell", {"food": "bread", "quantity": 2})
        self.assertEqual((st, s["refund"]), (200, 150))
        self.assertEqual((await self.post("/api/pets/food/sell", {"food": "bread"}))[1]["code"], "not_owned")
        # a golden feast pushes it through Ivysaur (Lv16) and Venusaur (Lv36): evolution is surfaced + mirrored
        await self.db.set_checkin_channel(GID, 777)
        await self.post("/api/pets/food/buy", {"food": "sushi", "quantity": 2})
        st, big = await self.post("/api/pets/feed", {"food": "sushi", "quantity": 2})
        self.assertTrue(big["evolved"] and big["leveled_up"])
        self.assertEqual(big["new_stage"]["name"], pet_catalog.stage_for_level("bulbasaur", big["new_level"])["name"])
        self.assertTrue(any("evolved" in str(m) for m in self.bridge.outbox))
        kinds = [e.get("kind") or e.get("type") for e in self.hub.since(UID, 0)]
        self.assertTrue(any(k in ("pet_evolved", "pet_level_up") for k in kinds), kinds)

    async def test_foodshop_and_other_members_pets(self) -> None:
        await self.db.add_item(UID, GID, "pizza", 3)
        st, fs = await self.get("/api/pets/foodshop")
        pizza = next(f for t in fs["tiers"] for f in t["foods"] if f["id"] == "pizza")
        self.assertEqual((st, pizza["owned"], pizza["sell"]), (200, 3, round(2400 * config.FOOD_SELL_RATE)))
        st, o = await self.get(f"/api/pets?user={OTHER}")
        self.assertEqual((st, o["me"]), (200, False))
        self.assertEqual((await self.get("/api/pets?user=abc"))[0], 404)
