"""tests/test_web_lab.py - Tests for Chronoweb Lab DLC endpoints."""
from __future__ import annotations

import unittest

from tests.web_helpers import GID, UID, OTHER, WebCase
from utils import lab as lab_catalog


class WebLabTests(WebCase):
    async def _give_chem_hours(self, uid: int, hours: float):
        seconds = int(hours * 3600)
        await self.db.conn.execute(
            """
            INSERT INTO subject_stats (user_id, guild_id, subject, total_seconds, sessions_count)
            VALUES (?, ?, 'chemistry', ?, 1)
            ON CONFLICT(user_id, guild_id, subject) DO UPDATE SET total_seconds = total_seconds + ?
            """,
            (uid, GID, seconds, seconds),
        )
        await self.db.conn.commit()

    async def test_get_lab_status_locked(self):
        st, data = await self.get("/api/lab")
        self.assertEqual(st, 200)
        self.assertFalse(data["unlocked"])
        self.assertEqual(data["required_chemistry_hours"], 30.0)
        self.assertEqual(data["required_coins"], 80000)
        self.assertFalse(data["can_unlock"])

    async def test_unlock_lab_insufficient_hours(self):
        await self.db.add_coins(UID, GID, 80000)
        st, data = await self.post("/api/lab/unlock")
        self.assertEqual(st, 400)
        self.assertEqual(data["code"], "insufficient_chemistry_hours")

    async def test_unlock_lab_insufficient_coins(self):
        await self._give_chem_hours(UID, 35.0)
        await self.db.add_coins(UID, GID, 10000)
        st, data = await self.post("/api/lab/unlock")
        self.assertEqual(st, 400)
        self.assertEqual(data["code"], "insufficient_coins")

    async def test_unlock_lab_success(self):
        await self._give_chem_hours(UID, 32.0)
        await self.db.add_coins(UID, GID, 90000)
        st, data = await self.post("/api/lab/unlock")
        self.assertEqual(st, 200)
        self.assertTrue(data["unlocked"])

        # Check status endpoint now reports unlocked
        st_status, status_data = await self.get("/api/lab")
        self.assertEqual(st_status, 200)
        self.assertTrue(status_data["unlocked"])
        self.assertEqual(status_data["coins"], 10000)  # 90k - 80k

    async def test_unlock_lab_already_unlocked(self):
        await self._give_chem_hours(UID, 32.0)
        await self.db.add_coins(UID, GID, 90000)
        await self.post("/api/lab/unlock")

        # Second attempt
        st2, data2 = await self.post("/api/lab/unlock")
        self.assertEqual(st2, 400)
        self.assertEqual(data2["code"], "already_unlocked")

    async def test_synth_dry_run_and_confirm(self):
        # Unlock lab
        await self._give_chem_hours(UID, 32.0)
        await self.db.add_coins(UID, GID, 90000)
        await self.post("/api/lab/unlock")

        # Add elements for methane (1 C, 4 H)
        await self.db.add_lab_elements(UID, GID, {"C": 5, "H": 10})

        # Dry run
        st_dry, dry_data = await self.post("/api/lab/synth", {"compound": "methane", "confirm": False})
        self.assertEqual(st_dry, 200)
        self.assertTrue(dry_data["dry_run"])
        self.assertTrue(dry_data["can_afford"])
        self.assertEqual(dry_data["compound"]["id"], "methane")

        # Confirm synthesis
        st_synth, synth_data = await self.post("/api/lab/synth", {"compound": "methane", "confirm": True})
        self.assertEqual(st_synth, 200)
        self.assertFalse(synth_data["dry_run"])
        self.assertTrue(synth_data["first_time"])
        self.assertTrue(synth_data["is_discoverer"])

        # Check elements decreased
        inv = await self.db.get_lab_elements(UID, GID)
        self.assertEqual(inv["C"], 4)
        self.assertEqual(inv["H"], 6)

    async def test_compendium_lists_all_compounds(self):
        # Unlock lab
        await self._give_chem_hours(UID, 32.0)
        await self.db.add_coins(UID, GID, 90000)
        await self.post("/api/lab/unlock")

        st, comp_data = await self.get("/api/lab/compendium")
        self.assertEqual(st, 200)
        self.assertEqual(comp_data["total_compounds"], 500)
        self.assertEqual(comp_data["total_discovered"], 0)

        # First entry should be uncrafted but have its name, formula, and elements visible
        c0 = comp_data["compounds"][0]
        self.assertFalse(c0["discovered"])
        self.assertIn("name", c0)
        self.assertIn("formula", c0)
        self.assertIn("elements", c0)
        self.assertIn("fact", c0)

    async def test_start_session_oc_mode_requires_unlock(self):
        st, data = await self.post("/api/session/start", {"mode": "oc"})
        self.assertEqual(st, 403)
        self.assertEqual(data["code"], "lab_locked")

    async def test_start_session_oc_mode_success(self):
        await self._give_chem_hours(UID, 32.0)
        await self.db.add_coins(UID, GID, 90000)
        await self.post("/api/lab/unlock")

        st, data = await self.post("/api/session/start", {"mode": "oc"})
        self.assertEqual(st, 200)
        self.assertEqual(data["session"]["track"], "oc")


if __name__ == "__main__":
    unittest.main()
