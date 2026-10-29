"""Shared helpers for the Physics / Chemistry / Maths subject-room feature.

A server's admin runs `.make` once to create three voice channels. If
a user is connected to one of those three channels when they run
`.start`, their session gets tagged with that subject and its time
rolls up into per-subject stats (and subject-filtered leaderboards)
on top of their overall totals.
"""
from __future__ import annotations

from typing import Optional

SUBJECTS: tuple[str, ...] = ("physics", "chemistry", "maths")

SUBJECT_INFO: dict[str, dict[str, str]] = {
    "physics": {
        "emoji": "\U0001F4D8",
        "label": "Physics",
        "channel_name": "\U0001F4D8\u30FBPhysics",
    },
    "chemistry": {
        "emoji": "\U0001F9EA",
        "label": "Chemistry",
        "channel_name": "\U0001F9EA\u30FBChemistry",
    },
    "maths": {
        "emoji": "\U0001F4D0",
        "label": "Maths",
        "channel_name": "\U0001F4D0\u30FBMaths",
    },
}

SUBJECT_ALIASES: dict[str, str] = {
    "physics": "physics", "phy": "physics", "phys": "physics", "physic": "physics", "p": "physics",
    "chemistry": "chemistry", "chem": "chemistry", "chm": "chemistry", "c": "chemistry",
    "maths": "maths", "math": "maths", "mathematics": "maths", "mats": "maths", "m": "maths",
}


def normalize_subject_key(text: str) -> str:
    """Lowercase + strip whitespace and trailing punctuation (periods,
    commas, etc.) so `"Phy."`, `" PHY "`, and `"phy"` all resolve the
    same way. Used everywhere a subject alias is looked up."""
    return text.strip().lower().strip(".,!?;:")


# Shown in every "unknown subject" error so the accepted shorthands are
# discoverable rather than hidden in the source.
SUBJECT_HINT = (
    "Try `physics`/`phy`/`p`, `chemistry`/`chem`/`c`, or `maths`/`math`/`m`."
)


def detect_subject(guild_config: dict, channel_id: Optional[int]) -> Optional[str]:
    """Given a guild's config and a voice channel id, return which
    subject (if any) that channel is registered as."""
    if channel_id is None:
        return None
    mapping = {
        guild_config.get("physics_channel_id"): "physics",
        guild_config.get("chemistry_channel_id"): "chemistry",
        guild_config.get("maths_channel_id"): "maths",
    }
    return mapping.get(channel_id)
