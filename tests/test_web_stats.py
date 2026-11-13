from __future__ import annotations

import time

from tests.web_helpers import GID, OTHER, UID, WebCase


class StatsApiTests(WebCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        now = int(time.time())
        for uid, secs in ((UID, 7200), (OTHER, 1800)):
            sid = await self.db.start_session(uid, GID, None, "physics", now - secs)
            await self.db.end_session(sid, now, "manual_stop")

    async def test_requires_login(self) -> None:
        r = await self.client.get("/api/profile")
        self.assertEqual(r.status, 401)

    async def test_profile_matches_database(self) -> None:
        st, d = await self.get("/api/profile")
        stats = await self.db.get_or_create_user_stats(UID, GID)
        self.assertEqual(st, 200)
        self.assertEqual(d["user"]["id"], str(UID))        # big ids arrive as strings
        self.assertEqual(d["total_seconds"], stats["total_seconds"])
        self.assertEqual(d["level"]["xp"], stats["xp"])
        self.assertEqual(d["rank_position"], 1)
        self.assertEqual(len(d["subjects"]), 3)
        self.assertEqual(len(d["weekly"]["days"]), 7)

    async def test_leaderboard_orders_and_filters(self) -> None:
        st, d = await self.get("/api/leaderboard?period=alltime")
        self.assertEqual([e["id"] for e in d["entries"]][:2], [str(UID), str(OTHER)])
        self.assertTrue(d["entries"][0]["me"])
        st, d = await self.get("/api/leaderboard?period=today&subject=maths")
        self.assertEqual(d["entries"], [])
        st, d = await self.get("/api/leaderboard?period=nope")
        self.assertEqual(st, 400)
        st, d = await self.get("/api/leaderboard?subject=biology")
        self.assertEqual(st, 400)

    async def test_live_session_counts_on_leaderboard(self) -> None:
        await self.db.start_session(OTHER + 5, GID, None, None, int(time.time()) - 600)
        await self.db.get_or_create_user_stats(OTHER + 5, GID)
        st, d = await self.get("/api/leaderboard?period=today")
        live = [e for e in d["entries"] if e["id"] == str(OTHER + 5)]
        self.assertTrue(live and live[0]["studying_since"])

    async def test_compare_rules(self) -> None:
        st, d = await self.get(f"/api/compare?b={OTHER}")
        self.assertEqual(st, 200)
        self.assertEqual(d["verdict"], "a")
        row = next(r for r in d["rows"] if r["key"] == "total_seconds")
        self.assertEqual(row["winner"], "a")
        self.assertEqual((await self.get(f"/api/compare?b={UID}"))[0], 400)    # same person
        self.assertEqual((await self.get("/api/compare"))[0], 400)             # missing b
        self.assertEqual((await self.get("/api/compare?b=abc"))[0], 400)

    async def test_hall_of_fame_and_top3(self) -> None:
        st, d = await self.get("/api/halloffame")
        rec = {r["key"]: r for r in d["records"]}
        self.assertEqual(rec["total_time"]["holder"]["id"], str(UID))
        self.assertEqual(d["top3"][0]["rank"], 1)
        self.assertEqual(len(d["records"]), 10)

    async def test_achievements_shape(self) -> None:
        st, d = await self.get("/api/achievements")
        self.assertEqual(d["total"], sum(c["total"] for c in d["categories"]))
        first = next(i for c in d["categories"] for i in c["items"] if i["id"] == "time_1h")
        self.assertTrue(first["unlocked"])            # 2h studied -> "First Hour"

    async def test_history_heatmap_members_dashboard_card(self) -> None:
        st, d = await self.get("/api/sessions/history?limit=5")
        self.assertEqual(len(d["sessions"]), 1)
        self.assertGreater(d["sessions"][0]["end"], d["sessions"][0]["start"])
        st, d = await self.get("/api/heatmap?days=14")
        self.assertEqual(len(d["days"]), 14)
        self.assertGreaterEqual(d["max"], 7000)
        st, d = await self.get("/api/members?q=&limit=5")
        self.assertEqual(len(d["members"]), 2)
        st, d = await self.get("/api/dashboard")
        self.assertEqual(len(d["days"]), 7)
        self.assertEqual(d["rank_today"], 1)
        self.assertTrue(d["daily_claimable"])
        st, png = await self.get("/api/stats/card.png")
        self.assertEqual((st, png[:4]), (200, b"\x89PNG"))
        self.assertEqual((await self.get("/api/stats/card.png?page=zzz"))[0], 400)
