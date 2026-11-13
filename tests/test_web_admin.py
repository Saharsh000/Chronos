from __future__ import annotations

from unittest import mock

import config
from tests.web_helpers import GID, OTHER, UID, WebCase


class AdminApiTests(WebCase):
    """Permissions follow the bot: Manage Server (config), Administrator (rooms), developer (grants, tiers, tags)."""

    def as_dev(self):
        p = mock.patch.object(config, "DEV_USER_ID", UID); p.start(); self.addCleanup(p.stop)

    def as_manager_only(self):
        # OfflineBridge treats dev mode as manager; make OTHER a plain member and UID the dev
        p = mock.patch.object(config, "WEB_DEV_MODE", False); p.start(); self.addCleanup(p.stop)

    async def test_non_privileged_members_are_refused_everywhere(self):
        self.as_manager_only()
        for path, body in [("/api/admin/checkin", {"channel": "111"}), ("/api/admin/rooms", {}), ("/api/admin/tiers/set", {"level": 5, "name": "x"}), ("/api/admin/tiers/reset", {}),
                           ("/api/admin/tags/add", {"price": 1, "title": "x"}), ("/api/admin/tags/remove", {"tag": "x"}), ("/api/admin/grant", {"user": str(OTHER), "kind": "coins", "amount": 5})]:
            st, e = await self.post(path, body, uid=OTHER)
            self.assertEqual((st, e["code"]), (403, "forbidden"), path)
        for path in ("/api/admin/config", "/api/admin/members", "/api/admin/diagnostics"):
            self.assertEqual((await self.get(path, uid=OTHER))[0], 403, path)
        self.assertEqual((await self.get("/api/tiers", uid=OTHER))[0], 200)            # `.tiers` and `.tags` are public
        self.assertFalse((await self.get("/api/tags", uid=OTHER))[1]["can_edit"])

    async def test_config_and_checkin(self):
        self.as_dev()
        st, cfg = await self.get("/api/admin/config")
        self.assertEqual((st, cfg["checkin"], len(cfg["rooms"])), (200, None, 3))
        self.assertEqual((await self.post("/api/admin/checkin", {"channel": "999"}))[1]["code"], "bad_channel")
        st, r = await self.post("/api/admin/checkin", {"channel": "111"})
        self.assertEqual((st, r["checkin"]["name"]), (200, "study-log"))
        self.assertEqual((await self.db.get_guild_config(GID))["checkin_channel_id"], 111)        # the bot reads the same row
        self.assertEqual((await self.get("/api/admin/config"))[1]["checkin"]["id"], "111")
        st, e = await self.post("/api/admin/rooms", {})
        self.assertEqual((st, e["code"]), (501, "needs_bot"))                                      # offline bridge can't create channels

    async def test_tiers_and_tags_match_the_bot(self):
        self.as_dev()
        st, t = await self.get("/api/tiers")
        self.assertEqual((t["tiers"][0]["name"], t["can_edit"]), ("Iron", True))
        st, r = await self.post("/api/admin/tiers/set", {"level": 100, "name": "  Grand   Master "})
        self.assertEqual((st, r["name"]), (200, "Grand Master"))
        self.assertEqual((await self.db.get_tier_overrides(GID))[100], "Grand Master")
        t = (await self.get("/api/tiers"))[1]["tiers"]
        self.assertEqual([(x["name"], x["renamed"]) for x in t if x["level"] == 100], [("Grand Master", True)])
        self.assertEqual((await self.post("/api/admin/tiers/set", {"level": 7, "name": "x"}))[1]["code"], "bad_level")
        self.assertEqual((await self.post("/api/admin/tiers/set", {"level": 5, "name": ""}))[1]["code"], "empty")
        self.assertEqual((await self.post("/api/admin/tiers/reset", {"level": 100}))[0], 200)
        self.assertEqual((await self.post("/api/admin/tiers/reset", {"level": 100}))[1]["code"], "not_renamed")
        await self.post("/api/admin/tiers/set", {"level": 5, "name": "A"}); await self.post("/api/admin/tiers/set", {"level": 10, "name": "B"})
        self.assertEqual((await self.post("/api/admin/tiers/reset", {}))[1]["reset"], 2)
        st, r = await self.post("/api/admin/tags/add", {"price": 500, "title": "The Grinder"})
        self.assertEqual(st, 200)
        self.assertEqual([c["title"] for c in (await self.get("/api/tags"))[1]["custom"]], ["The Grinder"])
        st, shop = await self.get("/api/shop")                                                       # and it is buyable in the shop like in the bot
        self.assertIn("The Grinder", str(shop))
        self.assertEqual((await self.post("/api/admin/tags/add", {"price": -1, "title": "x"}))[1]["code"], "bad_amount")
        self.assertEqual((await self.post("/api/admin/tags/remove", {"tag": "nope"}))[1]["code"], "no_tag")
        self.assertEqual((await self.post("/api/admin/tags/remove", {"tag": "the grinder"}))[0], 200)
        self.assertEqual((await self.get("/api/tags"))[1]["custom"], [])

    async def test_grants_change_the_same_rows_the_bot_reads(self):
        self.as_dev()
        who = {"user": str(OTHER)}
        c0 = (await self.db.get_or_create_currency(OTHER, GID))["coins"]
        st, r = await self.post("/api/admin/grant", {**who, "kind": "coins", "amount": 500})
        self.assertEqual((st, r["balance"]), (200, c0 + 500))
        st, r = await self.post("/api/admin/grant", {**who, "kind": "coins", "mode": "remove", "amount": 100})
        self.assertEqual(r["balance"], c0 + 400)
        self.assertEqual((await self.db.get_or_create_currency(OTHER, GID))["coins"], c0 + 400)
        x0 = (await self.db.get_or_create_user_stats(OTHER, GID))["xp"]
        await self.post("/api/admin/grant", {**who, "kind": "xp", "amount": 250})
        self.assertEqual((await self.db.get_or_create_user_stats(OTHER, GID))["xp"], x0 + 250)
        await self.post("/api/admin/grant", {**who, "kind": "xp", "mode": "remove", "amount": 10_000_000})
        self.assertEqual((await self.db.get_or_create_user_stats(OTHER, GID))["xp"], 0)             # floors at zero like the bot
        st, r = await self.post("/api/admin/grant", {**who, "kind": "time", "duration": "1h30m", "subject": "phy"})
        self.assertEqual((st, r["seconds"], r["subject"]), (200, 5400, "Physics"))
        self.assertEqual((await self.db.get_or_create_user_stats(OTHER, GID))["total_seconds"], 5400)
        st, r = await self.post("/api/admin/grant", {**who, "kind": "time", "mode": "remove", "duration": "30m"})
        self.assertEqual(r["seconds"], 1800)
        self.assertEqual((await self.db.get_or_create_user_stats(OTHER, GID))["total_seconds"], 3600)
        st, r = await self.post("/api/admin/grant", {**who, "kind": "candy", "amount": 40})
        self.assertEqual((st, r["balance"]), (200, 40))
        st, r = await self.post("/api/admin/grant", {**who, "kind": "box", "box": "legendary", "quantity": 3})
        self.assertEqual(st, 200)
        self.assertEqual(sum(q for k, q in (await self.db.get_inventory(OTHER, GID)).items() if "legendary" in k), 3)
        st, r = await self.post("/api/admin/grant", {**who, "kind": "passtime", "minutes": 120})
        self.assertEqual(st, 200)
        self.assertEqual((await self.db.get_or_create_halloween_pass(OTHER, GID))["study_seconds"], 7200)
        # the target's open tabs are told to refresh
        self.assertTrue(any(e["kind"] == "refresh" for e in self.hub.since(OTHER, 0, GID)))

    async def test_grant_validation(self):
        self.as_dev()
        who = {"user": str(OTHER)}
        self.bridge.is_member = lambda g, u: u in (UID, OTHER)
        for body, code in [({"user": "123", "kind": "coins", "amount": 5}, "no_member"), ({**who, "kind": "coins", "amount": 0}, "bad_amount"),
                           ({**who, "kind": "coins", "amount": "abc"}, "bad_amount"), ({**who, "kind": "coins", "amount": 10**12}, "bad_amount"),
                           ({**who, "kind": "coins", "mode": "remove", "amount": -5}, "bad_amount"), ({**who, "kind": "time", "duration": "soon"}, "bad_duration"),
                           ({**who, "kind": "time", "duration": "1h", "subject": "bio"}, "bad_subject"), ({**who, "kind": "box", "box": "zzz"}, "invalid_box"),
                           ({**who, "kind": "box", "box": "rare", "mode": "remove"}, "bad_mode"), ({**who, "kind": "wat"}, "bad_kind")]:
            st, e = await self.post("/api/admin/grant", body)
            self.assertEqual((st >= 400, e["code"]), (True, code), body)

    async def test_members_diagnostics_help(self):
        self.as_dev()
        st, m = await self.get("/api/admin/members")
        self.assertEqual({x["id"] for x in m["members"]}, {str(UID), str(OTHER)})
        st, d = await self.get("/api/admin/diagnostics")
        self.assertEqual((st, d["guild"], d["counts"]["user_stats"] >= 2), (200, str(GID), True))
        st, h = await self.get("/api/help")
        self.assertEqual((h["prefix"], h["pet_unlock_level"], h["is_dev"]), (config.PREFIX, config.PET_UNLOCK_LEVEL, True))
