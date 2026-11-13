"""Everything the website needs from Discord, in one place.

`LiveBridge` wraps the running bot (guild/member cache, channels, sending
messages). `OfflineBridge` has no Discord connection at all - it's what the site
falls back to for local development and tests (`python -m web.standalone`), and
it keeps every Discord post in an in-memory outbox so tests can assert on them.
Route code never touches `discord` objects directly, so both behave the same.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Optional

import config

log = logging.getLogger("web.bridge")

_DEV_NAMES = [
    "Aarav", "Ishaan", "Meera", "Kabir", "Anaya", "Vihaan", "Diya", "Reyansh",
    "Saanvi", "Arjun", "Tara", "Rohan",
]


class Bridge:
    live = False

    def __init__(self, db) -> None:
        self.db = db

    # -- identity ---------------------------------------------------------
    def is_dev(self, user_id: int) -> bool:
        return user_id == config.DEV_USER_ID

    async def guilds_for(self, user_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def guild_name(self, guild_id: int) -> str:
        return f"Server {str(guild_id)[-4:]}"

    def member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        raise NotImplementedError

    def is_manager(self, guild_id: int, user_id: int) -> bool:
        return self.is_dev(user_id)

    def is_member(self, guild_id: int, user_id: int) -> bool:
        raise NotImplementedError

    def is_admin(self, guild_id: int, user_id: int) -> bool:
        """Administrator permission (what `.make` needs); the developer always counts."""
        return self.is_dev(user_id)

    async def create_study_rooms(self, guild_id: int, who: str) -> dict[str, Any]:
        raise NotImplementedError

    # -- channels / voice -------------------------------------------------
    def channels(self, guild_id: int) -> dict[str, list[dict[str, Any]]]:
        return {"text": [], "voice": []}

    def channel_name(self, channel_id: Optional[int]) -> Optional[str]:
        return None

    def voice_channel_of(self, guild_id: int, user_id: int) -> Optional[int]:
        return None

    def voice_members(self, channel_id: int) -> list[int]:
        return []

    def tz_name(self) -> str:
        return "IST"

    # -- sending ----------------------------------------------------------
    async def post(
        self, guild_id: int, *, embed=None, file: Optional[tuple[bytes, str]] = None,
        content: Optional[str] = None, channel_id: Optional[int] = None,
    ) -> Optional[tuple[int, int]]:
        raise NotImplementedError

    async def finish_prompt(self, channel_id: Optional[int], message_id: Optional[int], embed) -> None:
        raise NotImplementedError

    async def avatar_bytes(self, guild_id: int, user_id: int) -> Optional[bytes]:
        return None

    async def dm(self, user_id: int, content: str) -> bool:
        return False

    async def make_rooms(self, guild_id: int, by_user: int) -> dict[str, Any]:
        return {"ok": False, "error": "Creating rooms needs a live Discord connection."}


# ---------------------------------------------------------------------- #
class LiveBridge(Bridge):
    live = True

    def __init__(self, bot) -> None:
        super().__init__(bot.db)
        self.bot = bot

    def home_guild_ids(self) -> Optional[set[int]]:
        """The one server Chronos Web serves (None = no restriction)."""
        if config.WEB_GUILD_ID:
            return {config.WEB_GUILD_ID}
        want = config.WEB_GUILD_NAME.casefold()
        if not want:
            return None
        ids = {g.id for g in self.bot.guilds if g.name.strip().casefold() == want}
        if not ids:
            if not getattr(self, "_warned_home", False):
                self._warned_home = True
                log.warning("WEB_GUILD_NAME %r matches none of the bot's servers; serving all of them. Set WEB_GUILD_ID.", config.WEB_GUILD_NAME)
            return None
        return ids

    async def guilds_for(self, user_id: int) -> list[dict[str, Any]]:
        home = self.home_guild_ids()
        out = []
        for g in self.bot.guilds:
            if home is not None and g.id not in home:
                continue
            if g.get_member(user_id) is not None:
                out.append({"id": str(g.id), "name": g.name, "icon": g.icon.url if g.icon else None})
        return out

    def guild_name(self, guild_id: int) -> str:
        g = self.bot.get_guild(guild_id)
        return g.name if g else super().guild_name(guild_id)

    def is_member(self, guild_id: int, user_id: int) -> bool:
        g = self.bot.get_guild(guild_id)
        return bool(g and g.get_member(user_id))

    def member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        g = self.bot.get_guild(guild_id)
        m = g.get_member(user_id) if g else None
        if m is not None:
            return {
                "id": str(user_id), "name": m.display_name, "username": m.name,
                "avatar": m.display_avatar.with_size(128).url, "bot": m.bot, "present": True,
            }
        u = self.bot.get_user(user_id)
        if u is not None:
            return {
                "id": str(user_id), "name": u.display_name, "username": u.name,
                "avatar": u.display_avatar.with_size(128).url, "bot": u.bot, "present": False,
            }
        return {
            "id": str(user_id), "name": f"User {str(user_id)[-4:]}", "username": str(user_id),
            "avatar": f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png",
            "bot": False, "present": False,
        }

    def is_manager(self, guild_id: int, user_id: int) -> bool:
        if self.is_dev(user_id):
            return True
        g = self.bot.get_guild(guild_id)
        m = g.get_member(user_id) if g else None
        return bool(m and (m.guild_permissions.manage_guild or m.guild_permissions.administrator))

    def is_admin(self, guild_id: int, user_id: int) -> bool:
        if self.is_dev(user_id):
            return True
        g = self.bot.get_guild(guild_id)
        m = g.get_member(user_id) if g else None
        return bool(m and m.guild_permissions.administrator)

    async def create_study_rooms(self, guild_id: int, who: str) -> dict[str, Any]:
        """`.make`: the same logic as cogs/admin.py, returning what happened instead of an embed."""
        import discord
        from utils.subjects import SUBJECT_INFO, SUBJECTS
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise LookupError("guild_unavailable")
        category_name = "\U0001F4DA Study Rooms"
        cfg = await self.db.get_guild_config(guild_id)
        existing = {k: cfg.get(f"{k}_channel_id") for k in ("physics", "chemistry", "maths")}
        category = None
        for cid in existing.values():
            ch = guild.get_channel(cid) if cid else None
            if ch is not None and ch.category is not None:
                category = ch.category
                break
        if category is None:
            category = discord.utils.get(guild.categories, name=category_name)
        try:
            if category is None:
                category = await guild.create_category(category_name, reason=f"Requested by {who} via web")
            created, reused, new_ids = [], [], dict(existing)
            for key in SUBJECTS:
                cur = guild.get_channel(existing.get(key)) if existing.get(key) else None
                if cur is not None:
                    reused.append(cur.name)
                    continue
                ch = await guild.create_voice_channel(SUBJECT_INFO[key]["channel_name"], category=category, reason=f"Requested by {who} via web")
                new_ids[key] = ch.id
                created.append(ch.name)
                log.info("ROOM CREATED  | #%s (%s) in guild '%s' by %s via web", ch.name, key, guild.name, who)
        except discord.Forbidden:
            raise PermissionError("manage_channels")
        await self.db.set_subject_channels(guild_id, new_ids.get("physics"), new_ids.get("chemistry"), new_ids.get("maths"))
        return {"created": created, "reused": reused}

    def channels(self, guild_id: int) -> dict[str, list[dict[str, Any]]]:
        g = self.bot.get_guild(guild_id)
        if not g:
            return {"text": [], "voice": []}
        return {
            "text": [{"id": str(c.id), "name": c.name} for c in g.text_channels],
            "voice": [{"id": str(c.id), "name": c.name} for c in g.voice_channels],
        }

    def channel_name(self, channel_id: Optional[int]) -> Optional[str]:
        ch = self.bot.get_channel(channel_id) if channel_id else None
        return ch.name if ch else None

    def voice_channel_of(self, guild_id: int, user_id: int) -> Optional[int]:
        g = self.bot.get_guild(guild_id)
        m = g.get_member(user_id) if g else None
        if m and m.voice and m.voice.channel:
            return m.voice.channel.id
        return None

    def voice_members(self, channel_id: int) -> list[int]:
        ch = self.bot.get_channel(channel_id)
        return [m.id for m in getattr(ch, "members", []) if not m.bot]

    async def post(self, guild_id, *, embed=None, file=None, content=None, channel_id=None):
        import discord
        if channel_id is None:
            cfg = await self.db.get_guild_config(guild_id)
            channel_id = cfg.get("checkin_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return None
        kwargs: dict[str, Any] = {}
        if content:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if file is not None:
            kwargs["file"] = discord.File(io.BytesIO(file[0]), filename=file[1])
        try:
            msg = await channel.send(**kwargs)
            return channel.id, msg.id
        except discord.HTTPException as exc:
            log.warning("Could not mirror to Discord channel %s: %s", channel_id, exc)
            return None

    async def finish_prompt(self, channel_id, message_id, embed) -> None:
        import discord
        if not channel_id or not message_id:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed)
            await message.clear_reactions()
        except discord.HTTPException:
            pass

    async def avatar_bytes(self, guild_id, user_id):
        g = self.bot.get_guild(guild_id)
        m = g.get_member(user_id) if g else None
        if m is None:
            return None
        try:
            return await m.display_avatar.with_format("png").with_size(256).read()
        except Exception:
            return None

    async def dm(self, user_id: int, content: str) -> bool:
        import discord
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(content)
            return True
        except (discord.HTTPException, AttributeError):
            return False

    async def make_rooms(self, guild_id: int, by_user: int) -> dict[str, Any]:
        """Same behaviour as the `.make` command (see cogs/admin.py)."""
        import discord
        from utils.subjects import SUBJECT_INFO, SUBJECTS
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"ok": False, "error": "I can't see that server right now."}
        cfg = await self.db.get_guild_config(guild_id)
        existing = {k: cfg.get(f"{k}_channel_id") for k in SUBJECTS}
        category = None
        for cid in existing.values():
            ch = guild.get_channel(cid) if cid else None
            if ch is not None and ch.category is not None:
                category = ch.category
                break
        name = "\U0001F4DA Study Rooms"
        if category is None:
            category = discord.utils.get(guild.categories, name=name)
        try:
            if category is None:
                category = await guild.create_category(name, reason="Requested via Chronos Web")
            created, new_ids = [], dict(existing)
            for key in SUBJECTS:
                cur = guild.get_channel(existing[key]) if existing.get(key) else None
                if cur is not None:
                    continue
                ch = await guild.create_voice_channel(
                    SUBJECT_INFO[key]["channel_name"], category=category, reason="Requested via Chronos Web"
                )
                new_ids[key] = ch.id
                created.append(ch.name)
        except discord.Forbidden:
            return {"ok": False, "error": "I need the Manage Channels permission to create study rooms."}
        await self.db.set_subject_channels(guild_id, new_ids.get("physics"), new_ids.get("chemistry"), new_ids.get("maths"))
        return {"ok": True, "created": created}


# ---------------------------------------------------------------------- #
class OfflineBridge(Bridge):
    """No Discord. Guilds/members are inferred from the database; posts land in `outbox`."""

    def __init__(self, db) -> None:
        super().__init__(db)
        self.outbox: list[dict[str, Any]] = []
        self.voice: dict[int, int] = {}

    async def guilds_for(self, user_id: int) -> list[dict[str, Any]]:
        cur = await self.db.conn.execute(
            "SELECT DISTINCT guild_id FROM user_stats WHERE user_id = ? "
            "UNION SELECT DISTINCT guild_id FROM user_currency WHERE user_id = ?",
            (user_id, user_id),
        )
        ids = [r[0] for r in await cur.fetchall()]
        if config.WEB_GUILD_ID:
            ids = [i for i in ids if i == config.WEB_GUILD_ID]
        return [{"id": str(g), "name": self.guild_name(g), "icon": None} for g in ids]

    def is_member(self, guild_id: int, user_id: int) -> bool:
        return True

    def member(self, guild_id: int, user_id: int) -> dict[str, Any]:
        name = _DEV_NAMES[user_id % len(_DEV_NAMES)] if config.WEB_DEV_MODE else f"User {str(user_id)[-4:]}"
        return {
            "id": str(user_id), "name": name, "username": name.lower(), "bot": False, "present": True,
            "avatar": f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png",
        }

    def is_manager(self, guild_id: int, user_id: int) -> bool:
        return config.WEB_DEV_MODE or self.is_dev(user_id)

    def is_admin(self, guild_id: int, user_id: int) -> bool:
        return config.WEB_DEV_MODE or self.is_dev(user_id)

    def channels(self, guild_id: int):
        return {"text": [{"id": "111", "name": "study-log"}, {"id": "112", "name": "general"}],
                "voice": [{"id": "211", "name": "Physics"}, {"id": "212", "name": "Chemistry"}]}

    def voice_channel_of(self, guild_id, user_id):
        return self.voice.get(user_id)

    async def post(self, guild_id, *, embed=None, file=None, content=None, channel_id=None):
        if channel_id is None:
            cfg = await self.db.get_guild_config(guild_id)
            channel_id = cfg.get("checkin_channel_id")
        if not channel_id:
            return None
        self.outbox.append({
            "guild_id": str(guild_id), "channel_id": str(channel_id), "content": content,
            "embed": embed.to_dict() if embed is not None else None,
            "file": file[1] if file else None, "file_bytes": len(file[0]) if file else 0,
        })
        return channel_id, len(self.outbox)

    async def finish_prompt(self, channel_id, message_id, embed) -> None:
        self.outbox.append({"edit": {"channel_id": str(channel_id), "message_id": str(message_id)},
                            "embed": embed.to_dict() if embed is not None else None})
