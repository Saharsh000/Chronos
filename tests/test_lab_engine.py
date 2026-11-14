"""tests/test_lab_engine.py - Unit tests for the OC session element engine."""
import os
import tempfile
import time
import unittest

from database import Database
from utils import lab as lab_catalog

GID = 123456789
UID = 987654321


class TestLabEngine(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._dir.name, "test_engine.sqlite3"))
        await self.db.connect()
        await self.db.get_or_create_user_stats(UID, GID)
        await self.db.get_or_create_currency(UID, GID)

    async def asyncTearDown(self):
        await self.db.close()
        self._dir.cleanup()

    async def test_session_track_persistence(self):
        now = int(time.time())
        sess_id = await self.db.start_session(UID, GID, None, "chemistry", now=now, track="oc")
        sess = await self.db.get_active_session(UID, GID)
        self.assertIsNotNone(sess)
        self.assertEqual(sess["track"], "oc")
        self.assertEqual(sess["subject"], "chemistry")

    async def test_credit_progress_rolls_elements_for_oc_only(self):
        now = int(time.time())
        # Start standard chemistry session (track=None)
        sess_std = await self.db.start_session(UID, GID, None, "chemistry", now=now)
        credit_std = await self.db.credit_progress(sess_std, now + 120)
        self.assertIsNotNone(credit_std)
        self.assertEqual(credit_std["track"], None)
        self.assertEqual(credit_std.get("element_drops", {}), {})

        # End it
        await self.db.end_session(sess_std, now + 120, "test_end")

        # Start OC chemistry session (track="oc")
        sess_oc = await self.db.start_session(UID, GID, None, "chemistry", now=now + 125, track="oc")
        credit_oc = await self.db.credit_progress(sess_oc, now + 125 + 180)  # 3 minutes
        self.assertIsNotNone(credit_oc)
        self.assertEqual(credit_oc["track"], "oc")
        drops = credit_oc["element_drops"]
        self.assertGreater(drops.get("C", 0), 0)
        self.assertGreater(drops.get("H", 0), 0)

        # Verify elements deposited in inventory
        inv = await self.db.get_lab_elements(UID, GID)
        self.assertEqual(inv["C"], drops["C"])
        self.assertEqual(inv["H"], drops["H"])

    async def test_end_session_returns_oc_summary(self):
        now = int(time.time())
        sess_oc = await self.db.start_session(UID, GID, None, "chemistry", now=now, track="oc")
        # Credit 2 minutes
        await self.db.credit_progress(sess_oc, now + 120)
        summary = await self.db.end_session(sess_oc, now + 130, "manual_stop")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["track"], "oc")
        self.assertIn("credited_elements", summary)
        self.assertGreater(summary["credited_elements"]["C"], 0)
        self.assertGreater(summary["credited_elements"]["H"], 0)


if __name__ == "__main__":
    unittest.main()
