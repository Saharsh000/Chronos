from __future__ import annotations

import time
from unittest import mock

from services.cja import CJAError
from tests.web_helpers import GID, OTHER, UID, WebCase
from web import api_trivia

CHEM = {"id": "chemistry", "name": "Chemistry"}


def mk(qid, tid="single", options=None, text="Which is correct?", **extra):
    q = {"id": qid, "exam": {"id": "main", "name": "JEE Main"}, "subject": CHEM,
         "chapter": {"id": "chemical-equilibrium", "name": "Chemical Equilibrium", "section": "Physical Chemistry"}, "topic": {"id": "law-of-mass-action-kp-and-kc", "name": "Le Chatelier"},
         "type": {"id": tid, "name": tid.title(), "instructions": "Choose."}, "difficulty": "hard", "question": text,
         "options": options if options is not None else [{"key": k, "text": f"opt {k}"} for k in "ABCD"]}
    q.update(extra)
    return q


class FakeCJA:
    """Stands in for the remote service: remembers the answer key per question and records every call."""
    def __init__(self):
        self.queue, self.keys, self.calls, self.fail_check = [], {}, [], None

    def add(self, q, correct, marks=4):
        self.queue.append(q); self.keys[q["id"]] = (correct, marks)

    async def get_question(self, subject=None, chapter=None, topic=None, **kw):
        self.calls.append(("get", subject, chapter, topic))
        if not self.queue:
            raise CJAError("CJA_UNAVAILABLE", "down")
        return self.queue.pop(0)

    async def check_answer(self, qid, answer=None):
        self.calls.append(("check", qid, answer))
        if self.fail_check:
            e, self.fail_check = self.fail_check, None
            raise e
        right, marks = self.keys[qid]
        res = {"answer": {"display": str(right), "options": [str(right)]}, "explanation": "Because $K_c = \\frac{[C]}{[A]}$ &lt; 1.", "concept": "Equilibrium", "marking": {"correct": 4, "incorrect": -1}}
        if answer is None:
            return {**res, "result": "unattempted", "correct": False, "marks": 0}
        ok = str(answer) == str(right)
        return {**res, "result": "correct" if ok else "incorrect", "correct": ok, "marks": marks if ok else -1}


class TriviaApiTests(WebCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.fake = FakeCJA()
        api_trivia.SESSIONS.clear(); api_trivia._LOCAL_COOLDOWNS.clear(); api_trivia._LOCAL_ACTIVE[0] = 0
        p = mock.patch.object(api_trivia, "cja_client", self.fake); p.start(); self.addCleanup(p.stop)

    async def start(self, q, correct, marks=4, body=None, uid=UID):
        self.fake.add(q, correct, marks)
        api_trivia._LOCAL_COOLDOWNS.pop(uid, None)
        return await self.post("/api/trivia/question", body or {}, uid=uid)

    async def coins(self, uid=UID):
        return (await self.db.get_or_create_currency(uid, GID))["coins"]

    async def test_syllabus_and_filters(self):
        st, s = await self.get("/api/trivia/syllabus")
        self.assertEqual(st, 200)
        self.assertEqual([x["id"] for x in s["subjects"]], ["physics", "chemistry", "mathematics"])
        self.assertGreater(sum(len(x["chapters"]) for x in s["subjects"]), 80)
        for body, code in [({"subject": "biology"}, "bad_subject"), ({"chapter": "nope"}, "bad_chapter"), ({"topic": "x"}, "bad_topic"),
                           ({"chapter": "chemical-equilibrium", "topic": "nope"}, "bad_topic")]:
            st, e = await self.post("/api/trivia/question", body)
            self.assertEqual(e["code"], code, body)
        self.assertEqual(self.fake.calls, [])

    async def test_question_hides_answer_and_uses_distexer_structure(self):
        q = mk("q1", text="Statement I: pH is $\\log_{10}$ based. Statement II: HCl is strong. Choose the correct option.")
        st, r = await self.start(q, "B", body={"subject": "chem", "chapter": "chemical-equilibrium", "topic": "law-of-mass-action-kp-and-kc"})
        self.assertEqual(st, 200)
        self.assertEqual(self.fake.calls[0], ("get", "chemistry", "chemical-equilibrium", "law-of-mass-action-kp-and-kc"))
        self.assertNotIn("explanation", r); self.assertNotIn("answer", r)
        self.assertEqual((r["time_limit"], r["difficulty"], r["skip_cost"], r["type"]["id"]), (60, "hard", 15, "single"))
        items = [b for b in r["body"]["blocks"] if b["t"] == "item"]
        self.assertEqual([i["label"] for i in items], ["Statement I", "Statement II"])
        self.assertTrue(any(sg["k"] == "math" and sg["tex"].startswith("\\log") for sg in items[0]["segs"]))
        self.assertEqual([o["key"] for o in r["options"]], list("ABCD"))
        self.assertEqual(api_trivia._LOCAL_ACTIVE[0], 1)
        # cooldown applies to the next start, like the bot
        self.fake.add(mk("q2"), "A")
        st, e = await self.post("/api/trivia/question", {})
        self.assertEqual((st, e["code"]), (429, "cooldown"))
        self.assertGreater(e["retry_after"], 0)

    async def test_correct_and_wrong_match_the_bot_rules(self):
        c0 = await self.coins()
        st, r = await self.start(mk("q1"), "B")
        st, a = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "b"})
        self.assertEqual(st, 200)
        self.assertTrue(a["correct"]); self.assertEqual(a["marks"], 4)
        self.assertTrue(40 <= a["rewards"]["coins"] <= 80); self.assertTrue(25 <= a["rewards"]["xp"] <= 50)
        self.assertEqual(a["explanation"][0]["segs"][1]["k"], "math")
        self.assertIn("<", a["explanation"][0]["segs"][2]["v"])                         # &lt; was unescaped
        row = await self.db.get_or_create_trivia_stats(UID, GID)
        self.assertEqual((row["questions_attempted"], row["questions_correct"], row["total_marks"], row["current_streak"]), (1, 1, 4, 1))
        self.assertGreaterEqual(await self.coins(), c0 + a["rewards"]["coins"])
        self.assertEqual(api_trivia._LOCAL_ACTIVE[0], 0)
        st, again = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "B"})
        self.assertEqual((st, again["code"]), (409, "already_answered"))
        self.assertEqual((await self.db.get_or_create_trivia_stats(UID, GID))["questions_attempted"], 1)
        # wrong answer: flat 5 / 5, streak resets, -1 marks
        st, r = await self.start(mk("q2"), "C")
        st, a = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "A"})
        self.assertEqual((a["correct"], a["marks"], a["rewards"]["coins"], a["rewards"]["xp"], a["stats"]["streak"]), (False, -1, 5, 5, 0))
        row = await self.db.get_or_create_trivia_stats(UID, GID)
        self.assertEqual((row["questions_attempted"], row["total_marks"], row["best_streak"]), (2, 3, 1))

    async def test_advanced_pays_more_and_has_longer_clock(self):
        st, r = await self.start(mk("qa", exam={"id": "advanced", "name": "JEE Advanced"}), "A")
        self.assertEqual(r["time_limit"], 90)
        st, a = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "A"})
        self.assertTrue(60 <= a["rewards"]["coins"] <= 120); self.assertTrue(45 <= a["rewards"]["xp"] <= 70)

    async def test_multiple_integer_validation_and_wire_format(self):
        st, r = await self.start(mk("m1", "multiple"), "A,C")
        for bad in ([], ["Z"], ["A", "Q"], ""):
            st, e = await self.post("/api/trivia/answer", {"token": r["token"], "answer": bad})
            self.assertEqual((st, e["code"]), (400, "bad_answer"), bad)
        self.assertFalse([c for c in self.fake.calls if c[0] == "check"])                # invalid input never reaches CJA or burns the attempt
        st, a = await self.post("/api/trivia/answer", {"token": r["token"], "answer": ["c", "a", "A"]})
        self.assertEqual(self.fake.calls[-1], ("check", "m1", "A,C"))
        self.assertTrue(a["correct"])
        st, r = await self.start(mk("i1", "integer", options=[]), "4")
        for bad in ("4.5", "abc", "", "1234567"):
            self.assertEqual((await self.post("/api/trivia/answer", {"token": r["token"], "answer": bad}))[1]["code"], "bad_answer", bad)
        st, a = await self.post("/api/trivia/answer", {"token": r["token"], "answer": " 4 "})
        self.assertEqual(self.fake.calls[-1], ("check", "i1", 4)); self.assertIsInstance(self.fake.calls[-1][2], int)
        self.assertTrue(a["correct"])

    async def test_failed_check_does_not_burn_the_attempt(self):
        st, r = await self.start(mk("q1"), "B")
        self.fake.fail_check = CJAError("TIMEOUT", "CJA took too long")
        st, e = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "B"})
        self.assertEqual((st, e["code"]), (503, "timeout"))
        self.assertEqual((await self.db.get_or_create_trivia_stats(UID, GID))["questions_attempted"], 0)
        st, a = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "B"})
        self.assertEqual((st, a["correct"]), (200, True))

    async def test_skip_costs_coins_and_changes_no_stats(self):
        await self.db.add_coins(UID, GID, 100)
        c0 = await self.coins()
        st, r = await self.start(mk("q1"), "B")
        st, s = await self.post("/api/trivia/skip", {"token": r["token"]})
        self.assertEqual((st, s["skipped"], s["cost"]), (200, True, 15))
        self.assertEqual(s["answer"]["display"], "B"); self.assertEqual(await self.coins(), c0 - 15)
        self.assertEqual(self.fake.calls[-1], ("check", "q1", None))
        self.assertEqual((await self.db.get_or_create_trivia_stats(UID, GID))["questions_attempted"], 0)
        self.assertEqual(api_trivia._LOCAL_ACTIVE[0], 0)
        self.assertEqual((await self.post("/api/trivia/skip", {"token": r["token"]}))[1]["code"], "already_answered")
        # broke player can't skip
        await self.db.conn.execute("UPDATE user_currency SET coins = 3 WHERE user_id = ? AND guild_id = ?", (OTHER, GID)); await self.db.conn.commit()
        st, r2 = await self.start(mk("q2"), "A", uid=OTHER)
        st, e = await self.post("/api/trivia/skip", {"token": r2["token"]}, uid=OTHER)
        self.assertEqual((st, e["code"]), (402, "insufficient_coins"))

    async def test_timeout_reveals_without_penalty_and_late_answers_are_refused(self):
        st, r = await self.start(mk("q1"), "B")
        st, e = await self.post("/api/trivia/reveal", {"token": r["token"]})
        self.assertEqual((st, e["code"]), (409, "not_yet"))
        api_trivia.SESSIONS[r["token"]]["deadline"] = time.time() - 10
        st, a = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "B"})
        self.assertEqual((st, a["expired"], a["answer"]["display"]), (200, True, "B"))
        self.assertNotIn("correct", a)
        self.assertEqual((await self.db.get_or_create_trivia_stats(UID, GID))["questions_attempted"], 0)
        self.assertEqual(api_trivia._LOCAL_ACTIVE[0], 0)
        st, r = await self.start(mk("q2"), "C")
        api_trivia.SESSIONS[r["token"]]["deadline"] = time.time() - 1
        st, a = await self.post("/api/trivia/reveal", {"token": r["token"]})
        self.assertEqual((st, a["expired"]), (200, True))

    async def test_tokens_are_bound_and_new_question_releases_the_old_one(self):
        st, r = await self.start(mk("q1"), "B")
        st, e = await self.post("/api/trivia/answer", {"token": r["token"], "answer": "B"}, uid=OTHER)
        self.assertEqual((st, e["code"]), (404, "no_question"))
        self.assertEqual((await self.post("/api/trivia/answer", {"token": "nope", "answer": "B"}))[0], 404)
        st, r2 = await self.start(mk("q2"), "B")
        self.assertEqual(api_trivia._LOCAL_ACTIVE[0], 1)                                 # old round dropped, counter not leaked
        self.assertEqual((await self.post("/api/trivia/answer", {"token": r["token"], "answer": "B"}))[0], 409)

    async def test_match_table_and_cache_first(self):
        text = "Match the following:\nList-I\n(A) Work\n(B) Power\nList-II\n(P) Watt\n(Q) Joule\nChoose the correct answer."
        opts = [{"key": "A", "text": "A→Q, B→P"}, {"key": "B", "text": "A→P, B→Q"}]
        st, r = await self.start(mk("mt", "match", options=opts, text=text), "A")
        m = r["body"]["match"]
        self.assertEqual([x["key"] for x in m["list_i"]], ["A", "B"]); self.assertEqual([x["key"] for x in m["list_ii"]], ["P", "Q"])
        self.assertEqual(r["options"][0]["pairs"], [{"from": "A", "to": "Q"}, {"from": "B", "to": "P"}])
        # a pre-generated question is served before CJA is called, and only once
        await self.db.cache_question("cached1", "chemistry", "chemical-equilibrium", "law-of-mass-action-kp-and-kc", mk("cached1"))
        api_trivia._LOCAL_COOLDOWNS.clear(); self.fake.calls.clear()
        st, r = await self.post("/api/trivia/question", {"subject": "chemistry"})
        self.assertEqual((st, r["from_cache"]), (200, True)); self.assertEqual(self.fake.calls, [])
        self.assertEqual((await self.db.get_cache_stats())["total"], 0)

    async def test_cja_errors_map_to_statuses_and_keep_cooldown(self):
        self.fake.queue.clear()
        st, e = await self.post("/api/trivia/question", {})
        self.assertEqual((st, e["code"]), (503, "cja_unavailable"))
        st, e = await self.post("/api/trivia/question", {})
        self.assertEqual(e["code"], "cooldown")                                          # consumed even though the fetch failed
        self.assertEqual(api_trivia._LOCAL_ACTIVE[0], 0)

    async def test_stats_leaderboard_cache(self):
        st, s = await self.get("/api/trivia/stats")
        self.assertEqual((s["rank"], s["stats"]["attempted"], s["tier"]["title"]), (None, 0, "Serious Aspirant"))
        self.assertEqual(s["ladder"][0]["title"], "Kota Backbencher")
        st, r = await self.start(mk("q1"), "B"); await self.post("/api/trivia/answer", {"token": r["token"], "answer": "B"})
        st, r = await self.start(mk("q2"), "B", uid=OTHER); await self.post("/api/trivia/answer", {"token": r["token"], "answer": "A"}, uid=OTHER)
        st, s = await self.get("/api/trivia/stats")
        self.assertEqual((s["rank"], s["players"], s["stats"]["marks"], s["stats"]["accuracy"]), (1, 2, 4, 100.0))
        st, lb = await self.get("/api/trivia/leaderboard")
        self.assertEqual([(x["rank"], x["me"], x["marks"]) for x in lb["rows"]], [(1, True, 4), (2, False, -1)])
        self.assertEqual(lb["rows"][1]["tier"], "Kota Backbencher"); self.assertEqual(lb["you"]["rank"], 1)
        st, ca = await self.get("/api/trivia/cache")
        self.assertEqual((st, ca["total"]), (200, 0))
