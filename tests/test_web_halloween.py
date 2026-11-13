from __future__ import annotations

from utils import halloween as hc
from tests.web_helpers import GID, UID, WebCase


class HalloweenApiTests(WebCase):
    async def _study(self, secs: int) -> None:
        await self.db.get_or_create_halloween_pass(UID, GID)
        await self.db.conn.execute("UPDATE halloween_pass SET study_seconds = ? WHERE user_id = ?", (secs, UID))
        await self.db.conn.commit()

    async def test_overview_pass_states_and_shop(self) -> None:
        await self._study(3 * 3600)
        st, d = await self.get("/api/halloween")
        self.assertEqual(st, 200)
        p = d["pass"]
        cur = hc.get_current_pass_level(3 * 3600)
        self.assertEqual((p["level"], p["claimed_level"], p["unclaimed"]), (cur["level"], 0, cur["level"]))
        self.assertEqual(len(p["levels"]), hc.MAX_PASS_LEVEL)
        self.assertEqual({lv["status"] for lv in p["levels"][: cur["level"]]}, {"ready"})
        self.assertEqual(p["levels"][-1]["status"], "locked")
        self.assertEqual([s["id"] for s in d["shop"]], hc.CANDY_SHOP_ORDER)
        self.assertAlmostEqual(sum(x["chance"] for x in d["info"]["drop_table"]), 1.0)

    async def test_claim_matches_db_and_is_idempotent(self) -> None:
        st, e = await self.post("/api/halloween/claim", {})
        self.assertEqual(st, 200)                              # level 1 unlocks immediately (0s required)
        lvl1 = hc.get_pass_level(1)
        self.assertEqual((e["candy"], e["coins"]), (lvl1["candy"], lvl1["coins"]))
        self.assertEqual((await self.db.get_or_create_halloween_pass(UID, GID))["claimed_level"], 1)
        st, e = await self.post("/api/halloween/claim", {})
        self.assertEqual((st, e["code"]), (409, "already_claimed"))
        await self._study(2 * 3600)
        cur = hc.get_current_pass_level(2 * 3600)["level"]
        before = (await self.db.get_or_create_currency(UID, GID))["candy"]
        st, e = await self.post("/api/halloween/claim", {})
        self.assertEqual((st, e["new_claimed_level"], e["from_level"]), (200, cur, 2))
        want = sum(hc.get_pass_level(n)["candy"] for n in range(2, cur + 1))
        self.assertEqual(e["candy"], want)
        self.assertGreaterEqual((await self.db.get_or_create_currency(UID, GID))["candy"], before + want)

    async def test_candy_shop(self) -> None:
        st, e = await self.post("/api/halloween/buy", {"item": "sugar", "quantity": 1})
        self.assertEqual((st, e["code"]), (402, "insufficient_candy"))
        await self.db._add_candy_raw(UID, GID, 5000)
        await self.db.conn.commit()
        st, b = await self.post("/api/halloween/buy", {"item": "sugar_rush", "quantity": 3})
        self.assertEqual((st, b["price"], b["quantity"]), (200, 540, 3))
        self.assertEqual(await self.db.get_item_qty(UID, GID, "sugar_rush"), 3)
        st, b = await self.post("/api/halloween/buy", {"item": "inorganic"})
        self.assertEqual((st, b["title_text"]), (200, "Inorganic Nightmare"))
        self.assertEqual((await self.post("/api/halloween/buy", {"item": "inorganic"}))[1]["code"], "already_owned")
        self.assertEqual((await self.post("/api/halloween/buy", {"item": "shift1", "quantity": 2}))[1]["code"], "single_only")
        st, b = await self.post("/api/halloween/buy", {"item": "pumpkin"})
        self.assertEqual((st, b["item"]["type"]), (200, "pet"))
        self.assertIsNotNone(await self.db.get_pet(UID, GID, "pumpkaboo"))
        self.assertEqual((await self.post("/api/halloween/buy", {"item": "pumpkin"}))[1]["code"], "already_owned")
        self.assertEqual((await self.post("/api/halloween/buy", {"item": "nope"}))[0], 404)
        self.assertEqual((await self.post("/api/halloween/buy", {"item": "sugar", "quantity": 0}))[1]["code"], "bad_quantity")
        st, d = await self.get("/api/halloween")
        owned = {s["id"]: s["owned"] for s in d["shop"]}
        self.assertTrue(owned["pumpkaboo"] and owned["title_inorganic"] and not owned["title_shift1"])
