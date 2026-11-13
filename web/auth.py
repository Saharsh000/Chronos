"""Authentication and Discord OAuth2 handling for Chronoweb."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import quote, urlencode

import aiohttp
from aiohttp import web

import config

log = logging.getLogger("web.auth")

COOKIE_NAME = "chronos_session"
DEFAULT_GUILD_ID = 1483039226693030083
TOKEN_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _sign_payload(payload: dict[str, Any]) -> str:
    """Create a URL-safe signed session token: payload_b64.signature_b64"""
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    
    secret = config.JWT_SECRET.encode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    
    return f"{payload_b64}.{sig_b64}"


def _verify_token(token: str) -> Optional[dict[str, Any]]:
    """Verify signature and expiration of a signed session token."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        secret = config.JWT_SECRET.encode("utf-8")
        
        # Verify HMAC signature
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
        
        # Pad base64 for decoding
        rem = len(sig_b64) % 4
        padded_sig = sig_b64 + ("=" * (4 - rem) if rem else "")
        actual_sig = base64.urlsafe_b64decode(padded_sig.encode("utf-8"))
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        rem = len(payload_b64) % 4
        padded_payload = payload_b64 + ("=" * (4 - rem) if rem else "")
        payload_bytes = base64.urlsafe_b64decode(padded_payload.encode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))
        
        # Check expiry
        if payload.get("exp", 0) < int(time.time()):
            return None
            
        return payload
    except Exception:
        return None


def get_current_user(request: web.Request) -> Optional[dict[str, Any]]:
    """Retrieve verified user from request context."""
    return request.get("user")


def require_auth(handler):
    """Decorator requiring active user authentication."""
    async def wrapper(request: web.Request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return web.json_response({"error": "Unauthorized", "login_required": True}, status=401)
        return await handler(request, *args, **kwargs)
    return wrapper


@web.middleware
async def auth_middleware(request: web.Request, handler):
    """Extract and attach user session to request."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    user_data = _verify_token(token) if token else None
    request["user"] = user_data
    return await handler(request)


# --------------------------------------------------------------------- #
# Route Handlers
# --------------------------------------------------------------------- #

async def handle_discord_login(request: web.Request) -> web.Response:
    """Redirect to Discord OAuth2 authorize endpoint."""
    client_id = config.DISCORD_CLIENT_ID
    if not client_id:
        return web.json_response({"error": "DISCORD_CLIENT_ID not configured"}, status=500)
    
    # Check if client secret is configured
    if not config.DISCORD_CLIENT_SECRET:
        # Client secret is not set, redirect to app with clear flag
        return web.HTTPFound("/?oauth_missing_secret=1")

    # Determine redirect URI dynamically if not absolute
    redirect_uri = config.DISCORD_REDIRECT_URI
    if not redirect_uri:
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host", request.host)
        redirect_uri = f"{scheme}://{host}/api/auth/discord/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "prompt": "consent",
    }
    auth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return web.HTTPFound(auth_url)


async def handle_discord_callback(request: web.Request) -> web.Response:
    """Handle Discord OAuth2 callback and token exchange."""
    code = request.query.get("code")
    error = request.query.get("error")
    
    if error or not code:
        log.warning(f"Discord OAuth error: {error}")
        return web.HTTPFound("/?auth_error=denied")
        
    client_id = config.DISCORD_CLIENT_ID
    client_secret = config.DISCORD_CLIENT_SECRET
    
    if not client_secret:
        return web.HTTPFound("/?oauth_missing_secret=1")

    redirect_uri = config.DISCORD_REDIRECT_URI
    if not redirect_uri:
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host", request.host)
        redirect_uri = f"{scheme}://{host}/api/auth/discord/callback"

    # Exchange code for access token
    token_url = "https://discord.com/api/oauth2/token"
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=token_data, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.error(f"Failed to exchange Discord code: {resp.status} - {body}")
                return web.HTTPFound("/?auth_error=token_exchange_failed")
            token_json = await resp.json()
            access_token = token_json.get("access_token")

        # Fetch user info
        user_headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get("https://discord.com/api/users/@me", headers=user_headers) as resp:
            if resp.status != 200:
                return web.HTTPFound("/?auth_error=fetch_user_failed")
            discord_user = await resp.json()

        # Fetch guilds
        user_guilds = []
        async with session.get("https://discord.com/api/users/@me/guilds", headers=user_headers) as resp:
            if resp.status == 200:
                user_guilds = await resp.json()

    user_id = int(discord_user["id"])
    username = discord_user.get("username", "")
    global_name = discord_user.get("global_name") or username
    avatar_hash = discord_user.get("avatar")
    
    if avatar_hash:
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
    else:
        discrim = int(discord_user.get("discriminator", "0")) % 5
        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{discrim}.png"

    # Match guilds with Chronos bot guilds or fallback to default
    matched_guild_id = DEFAULT_GUILD_ID
    bot = request.app.get("bot")
    if bot:
        bot_guild_ids = {g.id for g in bot.guilds}
        for g in user_guilds:
            gid = int(g["id"])
            if gid in bot_guild_ids:
                matched_guild_id = gid
                break

    payload = {
        "user_id": user_id,
        "username": username,
        "global_name": global_name,
        "avatar": avatar_url,
        "guild_id": matched_guild_id,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    
    token = _sign_payload(payload)
    response = web.HTTPFound("/")
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=request.scheme == "https" or "chronos.fadehost.app" in request.host,
    )
    return response


async def handle_dev_login(request: web.Request) -> web.Response:
    """Instant login / account switcher for dev/testing or when OAuth credentials aren't set."""
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    requested_id = body.get("user_id")
    if requested_id:
        try:
            user_id = int(requested_id)
        except ValueError:
            return web.json_response({"error": "Invalid user_id"}, status=400)
    else:
        user_id = config.DEV_USER_ID

    bot = request.app.get("bot")
    db = request.app.get("db")
    
    # Ensure user stats row exists in DB
    guild_id = DEFAULT_GUILD_ID
    if db:
        await db.get_or_create_user_stats(user_id, guild_id)
        await db.get_or_create_currency(user_id, guild_id)

    username = f"User_{user_id}"
    global_name = username
    avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"

    # Try resolving real Discord info if bot is running
    if bot:
        guild = bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        if member:
            username = member.name
            global_name = member.display_name
            avatar_url = member.display_avatar.url
        else:
            try:
                fetched_user = await bot.fetch_user(user_id)
                if fetched_user:
                    username = fetched_user.name
                    global_name = fetched_user.display_name
                    avatar_url = fetched_user.display_avatar.url
            except Exception:
                pass

    payload = {
        "user_id": user_id,
        "username": username,
        "global_name": global_name,
        "avatar": avatar_url,
        "guild_id": guild_id,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }

    token = _sign_payload(payload)
    response = web.json_response({
        "status": "ok",
        "token": token,
        "user": payload,
        "message": f"Logged in as {global_name} ({user_id})",
    })
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=request.scheme == "https" or "chronos.fadehost.app" in request.host,
    )
    return response


async def handle_get_me(request: web.Request) -> web.Response:
    """Return profile, balances, active session, and permissions for current user."""
    user = get_current_user(request)
    if not user:
        return web.json_response({
            "authenticated": False,
            "user": None,
            "oauth_configured": bool(config.DISCORD_CLIENT_SECRET),
        })

    user_id = user["user_id"]
    guild_id = user.get("guild_id", DEFAULT_GUILD_ID)
    db = request.app.get("db")
    bot = request.app.get("bot")

    stats = {}
    currency = {}
    active_session = None
    equipped_pet = None
    effective_tiers = {}

    if db:
        stats = await db.get_or_create_user_stats(user_id, guild_id)
        currency = await db.get_or_create_currency(user_id, guild_id)
        active_session = await db.get_active_session(user_id, guild_id)
        equipped_pet = await db.get_equipped_pet(user_id, guild_id)
        effective_tiers = await db.get_effective_tiers(guild_id)

    from utils.xp import tier_for_level, xp_progress
    level = stats.get("level", 0)
    cur_xp, next_xp, xp_pct = xp_progress(stats.get("xp", 0))
    tier_name = tier_for_level(level, effective_tiers)

    # Server list for switching
    available_guilds = []
    if bot:
        for g in bot.guilds:
            available_guilds.append({
                "id": str(g.id),
                "name": g.name,
                "icon": g.icon.url if g.icon else None,
                "member_count": g.member_count,
            })
    if not available_guilds:
        available_guilds.append({
            "id": str(DEFAULT_GUILD_ID),
            "name": "Chronos Server",
            "icon": None,
            "member_count": 1,
        })

    active_guild_info = next((g for g in available_guilds if g["id"] == str(guild_id)), available_guilds[0])

    return web.json_response({
        "authenticated": True,
        "oauth_configured": bool(config.DISCORD_CLIENT_SECRET),
        "user": {
            "user_id": str(user_id),
            "username": user.get("username"),
            "global_name": user.get("global_name"),
            "avatar": user.get("avatar"),
            "is_dev": user_id == config.DEV_USER_ID,
            "guild_id": str(guild_id),
            "guild_info": active_guild_info,
            "available_guilds": available_guilds,
            "stats": {
                "total_seconds": stats.get("total_seconds", 0),
                "xp": stats.get("xp", 0),
                "level": level,
                "cur_xp": cur_xp,
                "next_xp": next_xp,
                "xp_percentage": xp_pct,
                "tier": tier_name,
                "current_streak": stats.get("current_streak", 0),
                "longest_streak": stats.get("longest_streak", 0),
                "equipped_title": stats.get("equipped_title"),
                "sessions_count": stats.get("sessions_count", 0),
            },
            "wallet": {
                "coins": currency.get("coins", 0),
                "candy": currency.get("candy", 0),
                "lifetime_earned": currency.get("lifetime_earned", 0),
            },
            "active_session": {
                "session_id": active_session["session_id"],
                "start_time": active_session["start_time"],
                "subject": active_session.get("subject"),
                "credited_seconds": active_session.get("credited_seconds", 0),
                "credited_xp": active_session.get("credited_xp", 0),
                "credited_coins": active_session.get("credited_coins", 0),
            } if active_session else None,
            "equipped_pet": {
                "species_id": equipped_pet["species_id"],
                "nickname": equipped_pet["nickname"],
                "level": equipped_pet["level"],
                "xp": equipped_pet["xp"],
            } if equipped_pet else None,
        },
    })


async def handle_select_guild(request: web.Request) -> web.Response:
    """Switch active Discord server for the logged in user."""
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        body = await request.json()
        new_guild_id = int(body.get("guild_id"))
    except Exception:
        return web.json_response({"error": "Invalid guild_id"}, status=400)

    payload = dict(user)
    payload["guild_id"] = new_guild_id
    payload["exp"] = int(time.time()) + TOKEN_TTL_SECONDS
    
    token = _sign_payload(payload)
    response = web.json_response({"status": "ok", "guild_id": str(new_guild_id)})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=request.scheme == "https" or "chronos.fadehost.app" in request.host,
    )
    return response


async def handle_logout(request: web.Request) -> web.Response:
    """Clear session cookie and log user out."""
    response = web.json_response({"status": "ok", "message": "Logged out"})
    response.del_cookie(COOKIE_NAME)
    return response
