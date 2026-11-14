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
        # Phenols has only 3 compounds: phenol, catechol, p-cresol
        phenols = [c for c in lab_catalog.COMPOUNDS if c["category"] == "Phenols"]
        self.assertEqual(len(phenols), 3)

        await self.db.add_lab_elements(UID, GID, {e: 500 for e in lab_catalog.ELEMENT_LIST})

        curr_before = await self.db.get_or_create_currency(UID, GID)
        coins_start = curr_before["coins"]

        # Craft first 2
        await self.db.craft_compound(UID, GID, phenols[0]["id"])
        await self.db.craft_compound(UID, GID, phenols[1]["id"])

        # Craft 3rd -> category complete!
        res3 = await self.db.craft_compound(UID, GID, phenols[2]["id"])
        self.assertTrue(res3["newly_completed_category"])
        self.assertEqual(res3["category"], "Phenols")
        self.assertEqual(res3["category_title"], "Aromatic Hydroxylist")

        # Verify category title in inventory
        inv = await self.db.get_inventory(UID, GID)
        self.assertIn("title_phenols", inv)

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
