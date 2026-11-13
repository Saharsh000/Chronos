from __future__ import annotations

from tests.web_helpers import GID, OTHER, UID, WebCase


class NotesApiTests(WebCase):
    async def patch(self, path, body, uid=UID):
        r = await self.client.patch(path, json=body, headers=self.headers(uid, True))
        return r.status, await r.json()

    async def delete(self, path, uid=UID):
        r = await self.client.delete(path, headers=self.headers(uid, True))
        return r.status, await r.json()

    async def test_create_matches_bot_row_and_validates(self) -> None:
        st, r = await self.post("/api/notes", {"title": "  Rotational   formulas ", "subject": "physics", "content": "I = mr^2\r\nτ = Iα"})
        self.assertEqual(st, 200)
        n = r["note"]
        self.assertEqual((n["title"], n["subject"], n["pinned"]), ("Rotational formulas", "Physics", False))
        row = await self.db.get_note_by_id(n["id"], UID)           # the bot reads the very same row
        self.assertEqual((row["guild_id"], row["subject"], row["content"]), (GID, "Physics", "I = mr^2\nτ = Iα"))
        st, r = await self.post("/api/notes", {"title": "Plain", "content": "x"})
        self.assertEqual(r["note"]["subject"], "General")
        for body, code in [({"title": "", "content": "x"}, "empty_title"), ({"title": "t", "content": " "}, "empty_content"),
                           ({"title": "t" * 81, "content": "x"}, "title_too_long"), ({"title": "t", "content": "x" * 3501}, "content_too_long"),
                           ({"title": "t", "content": "x", "subject": "s" * 31}, "subject_too_long"),
                           ({"title": "t", "content": "x", "image_url": "https://evil.example/a.png"}, "bad_image")]:
            st, e = await self.post("/api/notes", body)
            self.assertEqual((st, e["code"]), (400, code), body)
        st, r = await self.post("/api/notes", {"title": "Img", "content": "x", "image_url": "https://cdn.discordapp.com/attachments/1/2/a.png"})
        self.assertEqual(st, 200)

    async def test_list_filter_search_pin_edit_delete(self) -> None:
        a = (await self.post("/api/notes", {"title": "Bernoulli", "subject": "Physics", "content": "pressure and speed"}))[1]["note"]["id"]
        b = (await self.post("/api/notes", {"title": "Mole", "subject": "Chemistry", "content": "n = m/M"}))[1]["note"]["id"]
        st, h = await self.get("/api/notes")
        self.assertEqual((st, h["stats"]["total"], h["stats"]["pinned"]), (200, 2, 0))
        self.assertEqual(len(h["notes"]), 2)
        self.assertNotIn("content", h["notes"][0])
        self.assertEqual([n["id"] for n in (await self.get("/api/notes?subject=chemistry"))[1]["notes"]], [b])
        self.assertEqual([n["id"] for n in (await self.get("/api/notes?q=speed"))[1]["notes"]], [a])
        st, r = await self.patch(f"/api/notes/{a}", {"pinned": True})
        self.assertEqual((st, r["note"]["pinned"]), (200, True))
        self.assertEqual((await self.get("/api/notes"))[1]["notes"][0]["id"], a)       # pinned first, like the bot
        self.assertEqual([n["id"] for n in (await self.get("/api/notes?pinned=1"))[1]["notes"]], [a])
        st, r = await self.patch(f"/api/notes/{a}", {"title": "Bernoulli's principle", "content": "p + ½ρv² = const"})
        self.assertEqual((r["note"]["title"], r["note"]["subject"], r["note"]["pinned"]), ("Bernoulli's principle", "Physics", True))
        self.assertEqual((await self.patch(f"/api/notes/{a}", {"title": ""}))[1]["code"], "empty_title")
        self.assertEqual((await self.patch(f"/api/notes/{a}", {}))[1]["code"], "nothing")
        st, r = await self.delete(f"/api/notes/{b}")
        self.assertEqual((st, r["deleted"]), (200, b))
        self.assertIsNone(await self.db.get_note_by_id(b, UID))
        self.assertEqual((await self.delete(f"/api/notes/{b}"))[1]["code"], "no_note")

    async def test_notes_are_private_and_export_card(self) -> None:
        nid = (await self.post("/api/notes", {"title": "Mine", "content": "secret"}))[1]["note"]["id"]
        self.assertEqual((await self.get(f"/api/notes/{nid}", uid=OTHER))[0], 404)
        self.assertEqual((await self.patch(f"/api/notes/{nid}", {"title": "hax"}, uid=OTHER))[0], 404)
        self.assertEqual((await self.delete(f"/api/notes/{nid}", uid=OTHER))[0], 404)
        self.assertEqual((await self.get("/api/notes", uid=OTHER))[1]["stats"]["total"], 0)
        self.assertEqual((await self.get("/api/notes/abc"))[0], 404)
        st, ex = await self.get("/api/notes/export")
        self.assertEqual(st, 200)
        self.assertIn("## Mine", ex["markdown"]); self.assertIn("secret", ex["markdown"]); self.assertEqual(ex["filename"], "Chronotes_Notebook.md")
        self.assertEqual((await self.get("/api/notes/export", uid=OTHER))[0], 404)
        st, png = await self.get(f"/api/notes/{nid}/card")
        self.assertEqual(st, 200)
        self.assertTrue(png.startswith(b"\x89PNG"))
