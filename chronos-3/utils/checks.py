"""Custom command checks."""
from __future__ import annotations

from discord.ext import commands

import config


def is_dev():
    """Restrict a command to the hardcoded bot developer (config.DEV_USER_ID),
    regardless of server roles/permissions. This is intentionally NOT tied
    to Discord permissions - it's a single fixed user id who can adjust
    stats in any server the bot is a member of.
    """

    async def predicate(ctx: commands.Context) -> bool:
        return ctx.author.id == config.DEV_USER_ID

    return commands.check(predicate)
