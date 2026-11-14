"""tests/test_lab_rewards.py - Unit tests for The Lab rewards, category completions, milestones, and achievements."""
import os
import tempfile
import unittest

from database import Database
from utils import achievements as ach_catalog
from utils import lab as lab_catalog

GID = 123456789
UID = 987654321


class TestLabRewards(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self._dir.name, "test_rewards.sqlite3"))
        await self.db.connect()
        await self.db.get_or_create_user_stats(UID, GID)
        await self.db.get_or_create_currency(UID, GID)

        # Unlock lab for UID
        await self.db.conn.execute(
            "INSERT INTO subject_stats (user_id, guild_id, subject, total_seconds, sessions_count) VALUES (?, ?, 'chemistry', 120000, 1)",
            (UID, GID),
        )
        await self.db.add_coins(UID, GID, 100000)
        await self.db.set_lab_unlock(UID, GID)

    async def asyncTearDown(self):
        await self.db.close()
        self._dir.cleanup()

    async def test_lab_unlock_achievement(self):
        new_achs = await self.db.check_achievements(UID, GID)
        ach_ids = {a.id for a in new_achs}
        self.assertIn("lab_unlock", ach_ids)

    async def test_crafting_achievements(self):
        # Give plenty of elements
        await self.db.add_lab_elements(UID, GID, {e: 500 for e in lab_catalog.ELEMENT_LIST})

        # Craft 1 compound -> first synth achievement
        res = await self.db.craft_compound(UID, GID, "methane")
        self.assertIn("lab_first_synth", res["new_achievements"])

    async def test_category_completion_reward(self):
        # Use Monomers category which has exactly 4 compounds — small enough to complete in a test
        monomers = [c for c in lab_catalog.COMPOUNDS if c["category"] == "Monomers"]
        self.assertGreaterEqual(len(monomers), 4, "Monomers category must have at least 4 compounds")

        await self.db.add_lab_elements(UID, GID, {e: 500 for e in lab_catalog.ELEMENT_LIST})

        curr_before = await self.db.get_or_create_currency(UID, GID)
        coins_start = curr_before["coins"]

        # Craft all but the last monomer
        for c in monomers[:-1]:
            res = await self.db.craft_compound(UID, GID, c["id"])
            self.assertFalse(res["newly_completed_category"], f"Should not complete category after crafting {c['id']}")

        # Craft the final monomer -> triggers category completion
        res_last = await self.db.craft_compound(UID, GID, monomers[-1]["id"])
        self.assertTrue(res_last["newly_completed_category"])
        self.assertEqual(res_last["category"], "Monomers")
        self.assertEqual(res_last["category_title"], "Polymer Architect")

        # Verify category title was added to inventory
        inv = await self.db.get_inventory(UID, GID)
        self.assertIn("title_monomers", inv)

    async def test_milestone_reward_25(self):
        await self.db.add_lab_elements(UID, GID, {e: 500 for e in lab_catalog.ELEMENT_LIST})

        # Craft 24 compounds
        for c in lab_catalog.COMPOUNDS[:24]:
            await self.db.craft_compound(UID, GID, c["id"])

        # 25th craft
        res25 = await self.db.craft_compound(UID, GID, lab_catalog.COMPOUNDS[24]["id"])
        self.assertIsNotNone(res25["milestone_reward"])
        self.assertEqual(res25["milestone_reward"]["count"], 25)
        self.assertEqual(res25["milestone_reward"]["type"], "item")
        self.assertEqual(res25["milestone_reward"]["item_id"], "mystery_box")

        # Verify mystery box in inventory
        inv = await self.db.get_inventory(UID, GID)
        self.assertGreaterEqual(inv.get("mystery_box", 0), 1)


if __name__ == "__main__":
    unittest.main()
