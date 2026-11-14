"""tests/test_lab_db.py - Unit tests for The Lab DLC database operations."""
import os
import tempfile
import time
import unittest

from database import Database
from utils import lab as lab_catalog

GID = 123456789
UID = 987654321
UID2 = 987654322


class TestLabDatabase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._dir.name, "test_lab.sqlite3"))
        await self.db.connect()
        await self.db.get_or_create_user_stats(UID, GID)
        await self.db.get_or_create_currency(UID, GID)
        await self.db.get_or_create_user_stats(UID2, GID)
        await self.db.get_or_create_currency(UID2, GID)

    async def asyncTearDown(self):
        await self.db.close()
        self._dir.cleanup()

    async def _give_chem_hours(self, user_id: int, hours: float):
        seconds = int(hours * 3600)
        await self.db.conn.execute(
            """
            INSERT INTO subject_stats (user_id, guild_id, subject, total_seconds, sessions_count)
            VALUES (?, ?, 'chemistry', ?, 1)
            ON CONFLICT(user_id, guild_id, subject) DO UPDATE SET total_seconds = total_seconds + ?
            """,
            (user_id, GID, seconds, seconds),
        )
        await self.db.conn.commit()

    async def test_lab_unlock_requires_30h_chemistry(self):
        await self.db.add_coins(UID, GID, 100000)
        await self._give_chem_hours(UID, 29.5)
        with self.assertRaises(ValueError) as ctx:
            await self.db.set_lab_unlock(UID, GID)
        self.assertIn("chemistry", str(ctx.exception).lower())

    async def test_lab_unlock_requires_60k_coins(self):
        await self._give_chem_hours(UID, 35.0)
        await self.db.add_coins(UID, GID, 50000)  # only 50k
        with self.assertRaises(ValueError) as ctx:
            await self.db.set_lab_unlock(UID, GID)
        self.assertIn("chronocoins", str(ctx.exception).lower())

    async def test_lab_unlock_deducts_coins(self):
        await self._give_chem_hours(UID, 30.0)
        await self.db.add_coins(UID, GID, 70000)
        res = await self.db.set_lab_unlock(UID, GID)
        self.assertTrue(res["success"])
        self.assertFalse(res["already_unlocked"])

        curr = await self.db.get_or_create_currency(UID, GID)
        self.assertEqual(curr["coins"], 10000)  # 70k - 60k = 10k

        unlock = await self.db.get_lab_unlock(UID, GID)
        self.assertIsNotNone(unlock)

    async def test_lab_unlock_idempotent(self):
        await self._give_chem_hours(UID, 30.0)
        await self.db.add_coins(UID, GID, 70000)
        await self.db.set_lab_unlock(UID, GID)

        # Second call should not deduct coins again
        res2 = await self.db.set_lab_unlock(UID, GID)
        self.assertTrue(res2["already_unlocked"])
        curr = await self.db.get_or_create_currency(UID, GID)
        self.assertEqual(curr["coins"], 10000)

    async def test_add_lab_elements_cap_at_500(self):
        added, capped = await self.db.add_lab_elements(UID, GID, {"C": 450, "H": 600})
        self.assertEqual(added["C"], 450)
        self.assertEqual(added["H"], 500)
        self.assertIn("H", capped)

        elems = await self.db.get_lab_elements(UID, GID)
        self.assertEqual(elems["C"], 450)
        self.assertEqual(elems["H"], 500)

        # Add more to C
        added2, capped2 = await self.db.add_lab_elements(UID, GID, {"C": 100})
        self.assertEqual(added2["C"], 50)  # 450 + 50 = 500
        self.assertIn("C", capped2)

        elems2 = await self.db.get_lab_elements(UID, GID)
        self.assertEqual(elems2["C"], 500)

    async def test_craft_compound_lifecycle(self):
        # Unlock lab
        await self._give_chem_hours(UID, 30.0)
        await self.db.add_coins(UID, GID, 60000)
        await self.db.set_lab_unlock(UID, GID)

        # Add methane elements (1 C, 4 H)
        await self.db.add_lab_elements(UID, GID, {"C": 2, "H": 10})

        # Craft methane
        res = await self.db.craft_compound(UID, GID, "methane")
        self.assertTrue(res["first_time"])
        self.assertTrue(res["is_discoverer"])
        self.assertEqual(res["times_crafted"], 1)
        self.assertGreater(res["coins_earned"], 0)
        self.assertGreater(res["xp_earned"], 0)

        # Verify elements deducted
        elems = await self.db.get_lab_elements(UID, GID)
        self.assertEqual(elems["C"], 1)  # 2 - 1 = 1
        self.assertEqual(elems["H"], 6)  # 10 - 4 = 6

        # Second craft (repeat) by same user
        res2 = await self.db.craft_compound(UID, GID, "methane")
        self.assertFalse(res2["first_time"])
        self.assertFalse(res2["is_discoverer"])
        self.assertEqual(res2["times_crafted"], 2)

    async def test_craft_compound_discoverer_flag(self):
        # User 1 unlocks and crafts methane
        await self._give_chem_hours(UID, 30.0)
        await self.db.add_coins(UID, GID, 60000)
        await self.db.set_lab_unlock(UID, GID)
        await self.db.add_lab_elements(UID, GID, {"C": 10, "H": 20})
        res1 = await self.db.craft_compound(UID, GID, "methane")
        self.assertTrue(res1["is_discoverer"])

        # User 2 unlocks and crafts methane
        await self._give_chem_hours(UID2, 30.0)
        await self.db.add_coins(UID2, GID, 60000)
        await self.db.set_lab_unlock(UID2, GID)
        await self.db.add_lab_elements(UID2, GID, {"C": 10, "H": 20})
        res2 = await self.db.craft_compound(UID2, GID, "methane")
        self.assertTrue(res2["first_time"])  # first time for User 2
        self.assertFalse(res2["is_discoverer"])  # but not first in server!

    async def test_credit_lab_elements_idempotent(self):
        now = int(time.time())
        sess_id = await self.db.start_session(UID, GID, None, "chemistry", now=now, track="oc")

        deltas, capped = await self.db.credit_lab_elements(sess_id, UID, GID, 5, now=now)
        self.assertGreater(deltas["C"], 0)
        self.assertGreater(deltas["H"], 0)

        inv1 = await self.db.get_lab_elements(UID, GID)
        self.assertEqual(inv1["C"], deltas["C"])
        self.assertEqual(inv1["H"], deltas["H"])

        # Check session credited_elements JSON
        cur = await self.db.conn.execute("SELECT credited_elements FROM sessions WHERE session_id = ?", (sess_id,))
        row = await cur.fetchone()
        self.assertIsNotNone(row["credited_elements"])


if __name__ == "__main__":
    unittest.main()
