from __future__ import annotations

from utils import economy
from utils import syllabus as syl
from tests.web_helpers import GID, OTHER, UID, WebCase


class ProgressApiTests(WebCase):
    async def _wallet(self):
        return await self.db.get_or_create_currency(UID, GID)

    async def test_chapter_reward_revision_and_validation(self) -> None:
        c0 = (await self._wallet())["coins"]
        st, r = await self.post("/api/progress/chapter", {"subject": "phy", "chapter": "Rotational Motion"})
        self.assertEqual(st, 200)
        self.assertEqual((r["name"], r["number"], r["revision"], r["done"], r["total"]), ("Rotational Motion", 5, False, 1, len(syl.SYLLABUS["physics"])))
        rw = economy.MILESTONE_REWARDS["chapter"]
        self.assertEqual((r["coins"], r["xp"]), (rw["coins"], rw["xp"]))
        self.assertGreaterEqual((await self._wallet())["coins"], c0 + rw["coins"])
        self.assertEqual((await self.db.get_milestone_counts(UID, GID))["chapters_completed"], 1)
        st, r2 = await self.post("/api/progress/chapter", {"subject": "physics", "chapter": "5"})   # by number, repeat = revision
        self.assertEqual((st, r2["revision"], r2["coins"]), (200, True, economy.MILESTONE_REWARDS["revision"]["coins"]))
        self.assertEqual((await self.post("/api/progress/chapter", {"subject": "physics", "chapter": "made up"}))[1]["code"], "bad_chapter")
        self.assertEqual((await self.post("/api/progress/chapter", {"subject": "biology", "chapter": "1"}))[1]["code"], "bad_subject")
        self.assertEqual((await self.post("/api/progress/chapter", {"chapter": "1"}))[1]["code"], "bad_subject")

    async def test_subtopic_pyq_revision_book(self) -> None:
        st, r = await self.post("/api/progress/subtopic", {"subject": "physics", "chapter": "Rotational Motion", "subtopic": "moment of inertia"})
        self.assertEqual((st, r["subtopic"]), (200, "Moment of inertia"))
        self.assertEqual((await self.post("/api/progress/subtopic", {"subject": "physics", "chapter": "2", "subtopic": "zzz"}))[1]["code"], "bad_subtopic")
        self.assertEqual((await self.post("/api/progress/pyq", {"year": "2024", "subject": "maths"}))[0], 200)
        self.assertEqual((await self.post("/api/progress/pyq", {"year": "2024"}))[0], 200)
        self.assertEqual((await self.post("/api/progress/pyq", {"year": "1800"}))[1]["code"], "bad_year")
        self.assertEqual((await self.post("/api/progress/revision", {"number": "2"}))[0], 200)
        self.assertEqual((await self.post("/api/progress/revision", {"number": "0"}))[1]["code"], "bad_number")
        st, b = await self.post("/api/progress/book", {"book": "  HC Verma   Vol 1 "})
        self.assertEqual((st, b["book"]), (200, "HC Verma Vol 1"))
        self.assertEqual((await self.post("/api/progress/book", {"book": "x" * 101}))[1]["code"], "too_long")
        self.assertEqual((await self.post("/api/progress/book", {"book": " "}))[1]["code"], "empty")
        cnt = await self.db.get_milestone_counts(UID, GID)
        self.assertEqual((cnt["subtopics_completed"], cnt["pyq_years_completed"], cnt["max_revision"], cnt["books_completed"]), (1, 1, 2, 1))

    async def test_dashboard_and_syllabus_views(self) -> None:
        await self.post("/api/progress/chapter", {"subject": "maths", "chapter": "Trigonometry"})
        await self.post("/api/progress/subtopic", {"subject": "maths", "chapter": "Trigonometry", "subtopic": "identities"})
        st, d = await self.get("/api/progress")
        self.assertEqual(st, 200)
        self.assertEqual(d["total"], sum(len(v) for v in syl.SYLLABUS.values()))
        self.assertEqual(next(s for s in d["subjects"] if s["key"] == "maths")["done"], 1)
        self.assertEqual({m["type"] for m in d["recent"]}, {"chapter", "subtopic"})   # same-second rows tie on order
        st, s = await self.get("/api/syllabus")
        tri = next(ch for sj in s["subjects"] if sj["key"] == "maths" for ch in sj["chapters"] if ch["name"] == "Trigonometry")
        self.assertTrue(tri["done"] and next(t for t in tri["topics"] if t["name"] == "Identities")["done"])
        st, o = await self.get(f"/api/progress?user={OTHER}")
        self.assertEqual((st, o["me"], o["total_done"]), (200, False, 0))
        self.assertEqual((await self.get("/api/progress?user=x"))[0], 404)
