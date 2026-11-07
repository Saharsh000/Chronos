import asyncio
import os
import tempfile
import unittest

from database import Database


class TestQuestionCacheDatabase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite3")
        self.tmp.close()
        self.db = Database(self.tmp.name)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    async def test_cache_and_pop_lifecycle(self):
        # 1. Initially empty
        stats = await self.db.get_cache_stats()
        self.assertEqual(stats["total"], 0)

        # 2. Cache questions
        q1 = {
            "id": "q-phys-01",
            "subject": {"id": "physics", "name": "Physics"},
            "chapter": {"id": "units-and-measurements", "name": "Units and Measurements"},
            "topic": {"id": "dimensions-of-physical-quantities", "name": "Dimensions"},
            "question": "What is the dimension of force?",
            "options": [{"key": "A", "text": "[M L T^-2]"}],
        }
        q2 = {
            "id": "q-chem-01",
            "subject": {"id": "chemistry", "name": "Chemistry"},
            "chapter": {"id": "atomic-structure", "name": "Atomic Structure"},
            "topic": {"id": "bohr-model", "name": "Bohr Model"},
            "question": "Radius of first orbit in hydrogen is?",
            "options": [{"key": "A", "text": "0.529 A"}],
        }

        saved1 = await self.db.cache_question(
            question_id=q1["id"],
            subject_id=q1["subject"]["id"],
            chapter_id=q1["chapter"]["id"],
            topic_id=q1["topic"]["id"],
            question_data=q1,
        )
        saved2 = await self.db.cache_question(
            question_id=q2["id"],
            subject_id=q2["subject"]["id"],
            chapter_id=q2["chapter"]["id"],
            topic_id=q2["topic"]["id"],
            question_data=q2,
        )
        self.assertTrue(saved1)
        self.assertTrue(saved2)

        # 3. Check stats
        stats = await self.db.get_cache_stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["by_subject"].get("physics"), 1)
        self.assertEqual(stats["by_subject"].get("chemistry"), 1)
        self.assertEqual(stats["distinct_chapters"], 2)
        self.assertEqual(stats["distinct_topics"], 2)

        # 4. Check topic count
        cnt = await self.db.count_cached_questions("dimensions-of-physical-quantities")
        self.assertEqual(cnt, 1)

        # 5. Pop by specific topic
        popped = await self.db.pop_cached_question(topic="dimensions-of-physical-quantities")
        self.assertIsNotNone(popped)
        self.assertEqual(popped["id"], "q-phys-01")

        # 6. Verify deleted on pop (no reuse)
        cnt_after = await self.db.count_cached_questions("dimensions-of-physical-quantities")
        self.assertEqual(cnt_after, 0)
        popped_again = await self.db.pop_cached_question(topic="dimensions-of-physical-quantities")
        self.assertIsNone(popped_again)

        # 7. Pop random (should return q2)
        popped_random = await self.db.pop_cached_question()
        self.assertIsNotNone(popped_random)
        self.assertEqual(popped_random["id"], "q-chem-01")

        # 8. Cache is now empty
        stats_empty = await self.db.get_cache_stats()
        self.assertEqual(stats_empty["total"], 0)


if __name__ == "__main__":
    unittest.main()
