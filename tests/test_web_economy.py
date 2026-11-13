from __future__ import annotations

import time
from unittest import mock

import config
from utils import economy
from tests.web_helpers import GID, OTHER, UID, WebCase


class EconomyApiTests(WebCase):
    async def test_wallet_and_rewards_status(self) -> None:
        await self.db.add_coins(UID, GID, 500)
        st, w = await self.get("/api/wallet")
        self.assertEqual((st, w["coins"]), (200, 500))
        st, r = await self.get("/api/rewards")
        self.assertTrue(r["daily"]["available"] and r["work"]["available"] and r["weekly"]["available"])
        self.assertEqual(r["work"]["cooldown"], config.WORK_COOLDOWN_SECONDS)

    async def test_daily_claim_rules_and_extras(self) -> None:
        before = (await self.db.get_or_create_currency(UID, GID))["coins"]
        st, d = await self.post("/api/rewards/daily")
        self.assertEqual(st, 200)
        self.assertGreaterEqual(d["coins"], economy.DAILY_COINS_MIN + economy.DAILY_STREAK_BONUS_PER_DAY)
        cur = await self.db.get_or_create_currency(UID, GID)
        self.assertGreaterEqual(cur["coins"], before + d["coins"])            # + any achievement coins c.after() paid out
        self.assertGreaterEqual(cur["coins"], d["new_balance"])
        self.assertTrue(30 <= d["hallo"]["candy"] <= 60)                      # bot's Halloween daily candy
        self.assertEqual(cur["candy"], d["hallo"]["candy"])
        self.assertEqual(await self.db.get_item_qty(UID, GID, d["hallo"]["box"]["id"]), 1)
        st, again = await self.post("/api/rewards/daily")                     # once per IST day
        self.assertEqual((st, again["code"]), (409, "already_claimed"))

    async def test_work_beg_weekly_cooldowns(self) -> None:
        st, w = await self.post("/api/rewards/work")
        self.assertEqual(st, 200)
        self.assertTrue(config.WORK_COINS_MIN <= w["coins"] <= config.WORK_COINS_MAX)
        st, w2 = await self.post("/api/rewards/work")
        self.assertEqual((st, w2["code"]), (429, "cooldown"))
        self.assertGreater(w2["retry_after"], 0)
        st, b = await self.post("/api/rewards/beg")
        self.assertEqual(st, 200)
        self.assertIn("scene", b)
        st, wk = await self.post("/api/rewards/weekly")
        self.assertEqual(st, 200)
        self.assertIn(wk["hallo"]["box"]["id"], ("hbox_epic", "hbox_legendary"))
        self.assertTrue(180 <= wk["hallo"]["candy"] <= 300)
        self.assertEqual(await self.db.get_item_qty(UID, GID, "mystery_box"), 1)
        self.assertEqual((await self.post("/api/rewards/weekly"))[0], 429)

    async def test_shop_buy_flow_and_errors(self) -> None:
        st, s = await self.get("/api/shop")
        self.assertEqual([i["id"] for i in s["items"]][:2], ["mystery_box", "streak_freeze"])
        st, e = await self.post("/api/shop/buy", {"item": "mystery_box"})
        self.assertEqual((st, e["code"]), (402, "insufficient_funds"))
        await self.db.add_coins(UID, GID, 2000)
        st, b = await self.post("/api/shop/buy", {"item": "mystery_box", "quantity": 3})
        self.assertEqual((st, b["total_price"], b["owned_qty"]), (200, 660, 3))
        coins = (await self.db.get_or_create_currency(UID, GID))["coins"]
        self.assertEqual(coins, b["coins"])
        self.assertGreaterEqual(coins, 2000 - 660)       # plus any achievement payout (first purchase etc.)
        self.assertEqual(len(b["achievements"]) > 0, coins > 2000 - 660)
        self.assertEqual((await self.post("/api/shop/buy", {"item": "mystery_box", "quantity": 0}))[0], 400)
        self.assertEqual((await self.post("/api/shop/buy", {"item": "nope"}))[0], 404)
        self.assertEqual((await self.post("/api/shop/buy", {"item": "sugar_rush"}))[0], 400)      # event-only
        st, t = await self.post("/api/shop/buy", {"item": "title_scholar"})
        self.assertEqual(st, 200)
        self.assertEqual((await self.post("/api/shop/buy", {"item": "title_scholar"}))[1]["code"], "already_owned")

    async def test_bag_use_boost_titles_and_boxes(self) -> None:
        await self.db.add_item(UID, GID, "xp_boost", 1)
        await self.db.add_item(UID, GID, "mystery_box", 1)
        await self.db.add_item(UID, GID, "title_scholar", 1)
        st, bag = await self.get("/api/bag")
        self.assertEqual({i["id"] for i in bag["items"]}, {"xp_boost", "mystery_box", "title_scholar"})
        st, u = await self.post("/api/bag/use", {"item": "xp boost"})
        self.assertEqual((st, u["multiplier"], u["duration_minutes"]), (200, 2, 60))
        self.assertEqual((await self.post("/api/bag/use", {"item": "xp boost"}))[0], 404)         # none left
        self.assertEqual((await self.post("/api/bag/use", {"item": "mystery_box"}))[0], 400)
        st, bag = await self.get("/api/bag")
        self.assertEqual(bag["effects"][0]["id"], "xp_boost")
        self.assertEqual((await self.post("/api/bag/title", {"title": "The Scholar"}))[1]["equipped_title"], "The Scholar")
        self.assertEqual((await self.post("/api/bag/title", {"title": "Legend"}))[0], 403)       # not owned
        self.assertEqual((await self.post("/api/bag/title", {"title": "Nonsense"}))[0], 404)
        self.assertIsNone((await self.post("/api/bag/title", {"title": None}))[1]["equipped_title"])
        with mock.patch("random.choices", return_value=[{"kind": "coins", "min": 50, "max": 50, "weight": 1}]):
            st, o = await self.post("/api/bag/open", {"box": "mystery"})
        self.assertEqual((st, o["openings"][0]["kind"]), (200, "mystery"))
        self.assertEqual(await self.db.get_item_qty(UID, GID, "mystery_box"), 0)
        self.assertEqual((await self.post("/api/bag/open", {"box": "auto"}))[0], 404)

    async def test_open_hallo_boxes(self) -> None:
        await self.db.add_item(UID, GID, "hbox_common", 3)
        await self.db.add_item(UID, GID, "hbox_rare", 1)
        st, o = await self.post("/api/bag/open", {"box": "common", "qty": 5})
        self.assertEqual((st, o["code"]), (409, "insufficient"))
        st, o = await self.post("/api/bag/open", {"box": "all"})
        self.assertEqual(st, 200)
        self.assertEqual(len(o["openings"]), 2)
        cur = await self.db.get_or_create_currency(UID, GID)
        self.assertGreaterEqual(cur["coins"], sum(x["coins"] for x in o["openings"]))   # + achievement payouts
        self.assertEqual(cur["candy"], sum(x["candy"] for x in o["openings"]))
        self.assertEqual(cur["boxes_opened"], 4)
        self.assertEqual((await self.post("/api/bag/open", {"box": "purple-ish"}))[0], 400)

    async def test_top3_perks_view_activates_like_bot(self) -> None:
        sid = await self.db.start_session(UID, GID, None, None, int(time.time()) - 3600)
        await self.db.end_session(sid, int(time.time()), "manual_stop")
        st, p = await self.get("/api/perks")
        self.assertEqual((p["my_rank"], p["status"]), (1, "activated"))
        self.assertEqual(p["perk"]["coins"], 120)
        st, p = await self.get("/api/perks")
        self.assertEqual(p["status"], "claimed")
        self.assertEqual(await self.db.get_item_qty(UID, GID, "mystery_box"), 1)
        st, p = await self.get("/api/perks", OTHER)
        self.assertEqual(p["status"], "outside")

    async def test_csrf_header_required(self) -> None:
        r = await self.client.post("/api/rewards/work", headers={"Cookie": self.headers()["Cookie"]})
        self.assertEqual(r.status, 403)
