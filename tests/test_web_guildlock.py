from __future__ import annotations

from unittest import mock

import config
from tests.web_helpers import GID, UID, WebCase

OTHER_GUILD = 5550002


class GuildLockTests(WebCase):
    """Chronos is only used in the "bored af" server: every other server the bot is in is invisible to the site."""

    async def test_unrestricted_by_default(self):
        st, me = await self.get("/api/me")
        self.assertEqual((st, me["guild"]), (200, str(GID)))

    async def test_only_the_home_guild_is_served(self):
        await self.db.get_or_create_user_stats(UID, OTHER_GUILD)
        await self.db.get_or_create_currency(UID, OTHER_GUILD)
        self.assertEqual({g["id"] for g in await self.bridge.guilds_for(UID)}, {str(GID), str(OTHER_GUILD)})
        with mock.patch.object(config, "WEB_GUILD_ID", GID):
            self.assertEqual([g["id"] for g in await self.bridge.guilds_for(UID)], [str(GID)])
            st, me = await self.get("/api/me")
            self.assertEqual((st, me["guild"], [g["id"] for g in me["guilds"]]), (200, str(GID), [str(GID)]))
            # asking for the other server by header or query is refused, and nothing leaks
            r = await self.client.get("/api/me", headers={**self.headers(), "X-Guild": str(OTHER_GUILD)})
            self.assertEqual(r.status, 200)
            self.assertEqual((await r.json())["guild"], str(GID))
            await self.db.add_coins(UID, GID, 111)
            await self.db.add_coins(UID, OTHER_GUILD, 777)
            r = await self.client.get("/api/pets", headers={**self.headers(), "X-Guild": str(OTHER_GUILD)})
            self.assertEqual(r.status, 200)
            self.assertEqual((await r.json())["coins"], 111)           # the home server's wallet, not the one asked for

    async def test_users_only_in_other_servers_are_locked_out(self):
        with mock.patch.object(config, "WEB_GUILD_ID", OTHER_GUILD):
            st, me = await self.get("/api/me")                         # UID has no data in OTHER_GUILD
            self.assertEqual((st, me.get("no_guild")), (200, True))
            st, e = await self.get("/api/pets")
            self.assertEqual((st, e["code"]), (403, "no_guild"))
