"""Login for Chronos Web.

Two ways in, both ending in the same signed cookie:

* `.weblogin` in Discord -> the bot DMs a one-time link (works with nothing but
  the bot token - this is the default).
* "Login with Discord" (OAuth2, `identify` scope only) - lights up automatically
  once DISCORD_CLIENT_SECRET is set in the environment.

The cookie only proves *who you are*. Which servers you can see is always decided
by the bot's own view of Discord (see web/bridge.py), never by the browser.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

import aiohttp

import config

COOKIE = "chronos_sid"
SESSION_TTL = 30 * 24 * 3600
MAGIC_TTL = 10 * 60
DISCORD_API = "https://discord.com/api/v10"


def _secret() -> bytes:
    raw = config.WEB_SECRET or f"chronos-web::{config.TOKEN}" or "chronos-web::dev"
    return hashlib.sha256(raw.encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    mac = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def unsign(token: str) -> Optional[dict]:
    try:
        body, mac = token.split(".", 1)
        good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(mac, good):
            return None
        data = json.loads(_unb64(body))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def make_session_cookie(user_id: int, guild_id: Optional[int] = None) -> str:
    now = int(time.time())
    return sign({"u": str(user_id), "g": str(guild_id) if guild_id else None, "iat": now, "exp": now + SESSION_TTL})


# ---------------------------------------------------------------------- #
# One-time magic links (`.weblogin`)
# ---------------------------------------------------------------------- #
_magic: dict[str, tuple[int, Optional[int], float]] = {}


def create_magic(user_id: int, guild_id: Optional[int] = None) -> str:
    _purge()
    token = secrets.token_urlsafe(24)
    _magic[token] = (user_id, guild_id, time.time() + MAGIC_TTL)
    return token


def consume_magic(token: str) -> Optional[tuple[int, Optional[int]]]:
    _purge()
    entry = _magic.pop(token, None)
    if not entry:
        return None
    return entry[0], entry[1]


def _purge() -> None:
    now = time.time()
    for k in [k for k, v in _magic.items() if v[2] < now]:
        _magic.pop(k, None)


# ---------------------------------------------------------------------- #
# Discord OAuth2 (optional)
# ---------------------------------------------------------------------- #
def oauth_enabled() -> bool:
    return bool(config.DISCORD_CLIENT_SECRET)


def oauth_url(client_id: str, state: str) -> str:
    from urllib.parse import urlencode
    q = urlencode({
        "client_id": client_id,
        "redirect_uri": f"{config.WEB_BASE_URL}/auth/callback",
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "none",
    })
    return f"https://discord.com/oauth2/authorize?{q}"


async def oauth_exchange(client_id: str, code: str) -> Optional[int]:
    """Trade an OAuth code for the Discord user id (and nothing else)."""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        async with http.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": config.DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{config.WEB_BASE_URL}/auth/callback",
            },
        ) as resp:
            if resp.status != 200:
                return None
            tok = (await resp.json()).get("access_token")
        if not tok:
            return None
        async with http.get(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {tok}"}) as resp:
            if resp.status != 200:
                return None
            return int((await resp.json())["id"])
