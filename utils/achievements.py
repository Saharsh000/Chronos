"""Achievement/badge definitions and evaluation.

Pure and content-only, like `utils/xp.py`'s TIERS or
`utils/economy.py`'s SHOP_ITEMS - `database.py` gathers a context dict
of a user's stats and calls `evaluate()` to see which *new*
achievements that context satisfies. No database access happens here.

Each achievement also carries a one-time `reward_coins` payout,
credited by `Database.check_achievements()` the moment it's newly
unlocked - one more way to earn coins on top of studying/`.daily`/
`.work`/`.weekly` (see cogs/economy.py), scaled roughly to how hard
the achievement is to get.
"""
from __future__ import annotations

from typing import Any, Callable, NamedTuple

HOUR = 3600


class Achievement(NamedTuple):
    id: str
    name: str
    emoji: str
    description: str
    category: str
    check: Callable[[dict[str, Any]], bool]
    reward_coins: int = 0


def _time(hours: float, name: str, emoji: str) -> Achievement:
    seconds = int(hours * HOUR)
    return Achievement(
        id=f"time_{int(hours)}h",
        name=name,
        emoji=emoji,
        description=f"Accumulate {hours:g} hours of total study time.",
        category="Time Studied",
        check=lambda c: c["total_seconds"] >= seconds,
        reward_coins=int(hours * 15),
    )


def _sessions(count: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"sessions_{count}",
        name=name,
        emoji=emoji,
        description=f"Complete {count} study sessions.",
        category="Sessions",
        check=lambda c: c["sessions_count"] >= count,
        reward_coins=count * 8,
    )


def _streak(days: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"streak_{days}",
        name=name,
        emoji=emoji,
        description=f"Reach a {days}-day study streak.",
        category="Streaks",
        check=lambda c: c["longest_streak"] >= days,
        reward_coins=days * 20,
    )


def _daily_streak(days: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"daily_streak_{days}",
        name=name,
        emoji=emoji,
        description=f"Claim `.daily` {days} days in a row.",
        category="Daily Streaks",
        check=lambda c: c["daily_streak"] >= days,
        reward_coins=days * 25,
    )


def _tier(level: int, tier_name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"tier_{level}",
        name=f"Reached {tier_name}",
        emoji=emoji,
        description=f"Reach level {level} and enter the {tier_name} tier.",
        category="Tiers",
        check=lambda c: c["level"] >= level,
        reward_coins=level * 10,
    )


def _subject(subject: str, hours: float, label: str, emoji: str) -> Achievement:
    seconds = int(hours * HOUR)
    return Achievement(
        id=f"subject_{subject}_{int(hours)}h",
        name=f"{label} \u2014 {hours:g}h",
        emoji=emoji,
        description=f"Log {hours:g} hours studying {label}.",
        category="Subjects",
        check=lambda c: c["subject_seconds"].get(subject, 0) >= seconds,
        reward_coins=int(hours * 12),
    )


def _milestone_count(kind: str, count: int, name: str, emoji: str, category: str, verb: str) -> Achievement:
    return Achievement(
        id=f"{kind}_{count}",
        name=name,
        emoji=emoji,
        description=f"{verb} {count} {kind}{'s' if count != 1 else ''}.",
        category=category,
        check=lambda c, _kind=kind, _count=count: c[f"{_kind}s_completed"] >= _count,
        reward_coins=count * {"chapter": 10, "subtopic": 8, "book": 100, "pyq": 60}.get(kind, 10),
    )


def _revision(n: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"revision_{n}",
        name=name,
        emoji=emoji,
        description=f"Log your {n}{'st' if n == 1 else 'nd' if n == 2 else 'rd' if n == 3 else 'th'} revision pass.",
        category="Revisions",
        check=lambda c: c["max_revision"] >= n,
        reward_coins=n * 150,
    )


ACHIEVEMENTS: list[Achievement] = [
    # --- Time studied ------------------------------------------------- #
    _time(1, "First Hour", "\u23F1\uFE0F"),
    _time(5, "Getting Serious", "\U0001F4DA"),
    _time(10, "Double Digits", "\U0001F522"),
    _time(25, "Quarter Century", "\U0001F525"),
    _time(50, "Halfway to a Hundred", "\U0001F4AA"),
    _time(100, "Century Club", "\U0001F3C6"),
    _time(250, "Iron Will", "\u26CF\uFE0F"),
    _time(500, "Unstoppable", "\U0001F680"),
    _time(1000, "Thousand Hour Grind", "\U0001F451"),

    # --- Sessions ------------------------------------------------------ #
    _sessions(1, "First Steps", "\U0001F476"),
    _sessions(10, "Warming Up", "\U0001F3C3"),
    _sessions(25, "In The Groove", "\U0001F3B5"),
    _sessions(50, "Half Century", "\U0001F4C8"),
    _sessions(100, "Triple Digits", "\U0001F3AF"),
    _sessions(250, "Session Machine", "\u2699\uFE0F"),
    _sessions(500, "Living Here Now", "\U0001F3E0"),

    # --- Streaks --------------------------------------------------------#
    _streak(3, "On A Roll", "\U0001F3B2"),
    _streak(7, "One Week Strong", "\U0001F4C5"),
    _streak(14, "Two Weeks Deep", "\U0001F4CC"),
    _streak(30, "Monthly Regular", "\U0001F4C6"),
    _streak(60, "Two Months Straight", "\U0001F9F1"),
    _streak(100, "Streak Legend", "\U0001F525"),

    # --- Daily claim streaks -------------------------------------------#
    _daily_streak(3, "Showing Up", "\U0001F44B"),
    _daily_streak(7, "Loyal", "\U0001F49C"),
    _daily_streak(30, "Daily Devotee", "\U0001F3E9"),

    # --- Tiers (mirrors utils/xp.py TIERS) ------------------------------#
    _tier(5, "Bronze", "\U0001F949"),
    _tier(10, "Silver", "\U0001F948"),
    _tier(20, "Gold", "\U0001F947"),
    _tier(35, "Platinum", "\U0001F539"),
    _tier(50, "Diamond", "\U0001F48E"),
    _tier(75, "Ascendant", "\U0001F343"),
    _tier(100, "Immortal", "\U0001F480"),
    _tier(150, "Radiant", "\u2600\uFE0F"),
    _tier(200, "AIR 1", "\U0001F680"),

    # --- Subjects -------------------------------------------------------#
    _subject("physics", 5, "Physics", "\U0001F4D8"),
    _subject("physics", 25, "Physics", "\U0001F4D8"),
    _subject("chemistry", 5, "Chemistry", "\U0001F9EA"),
    _subject("chemistry", 25, "Chemistry", "\U0001F9EA"),
    _subject("maths", 5, "Maths", "\U0001F4D0"),
    _subject("maths", 25, "Maths", "\U0001F4D0"),

    # --- Economy ---------------------------------------------------------#
    Achievement(
        id="coins_500", name="Small Change", emoji="\U0001FA99",
        description="Earn 500 lifetime coins.", category="Economy",
        check=lambda c: c["coins_lifetime"] >= 500, reward_coins=100,
    ),
    Achievement(
        id="coins_2500", name="Coin Collector", emoji="\U0001F4B0",
        description="Earn 2,500 lifetime coins.", category="Economy",
        check=lambda c: c["coins_lifetime"] >= 2500, reward_coins=300,
    ),
    Achievement(
        id="coins_10000", name="High Roller", emoji="\U0001F3B0",
        description="Earn 10,000 lifetime coins.", category="Economy",
        check=lambda c: c["coins_lifetime"] >= 10000, reward_coins=750,
    ),
    Achievement(
        id="boxes_1", name="What's Inside?", emoji="\U0001F381",
        description="Open your first Mystery Box.", category="Economy",
        check=lambda c: c["boxes_opened"] >= 1, reward_coins=50,
    ),
    Achievement(
        id="boxes_10", name="Box Enthusiast", emoji="\U0001F4E6",
        description="Open 10 Mystery Boxes.", category="Economy",
        check=lambda c: c["boxes_opened"] >= 10, reward_coins=200,
    ),
    Achievement(
        id="boxes_50", name="Unboxing Addict", emoji="\U0001F3AB",
        description="Open 50 Mystery Boxes.", category="Economy",
        check=lambda c: c["boxes_opened"] >= 50, reward_coins=750,
    ),
    Achievement(
        id="purchases_1", name="First Purchase", emoji="\U0001F6D2",
        description="Buy your first item from the shop.", category="Economy",
        check=lambda c: c["items_purchased"] >= 1, reward_coins=50,
    ),
    Achievement(
        id="purchases_10", name="Big Spender", emoji="\U0001F4B8",
        description="Buy 10 items from the shop.", category="Economy",
        check=lambda c: c["items_purchased"] >= 10, reward_coins=250,
    ),

    # --- Chapters / Books / PYQs / Revisions (manually logged, see cogs/progress.py) --#
    _milestone_count("chapter", 5, "Chapter Chipper", "\U0001F4D1", "Chapters", "Complete"),
    _milestone_count("chapter", 15, "Chapter Crusher", "\U0001F4DA", "Chapters", "Complete"),
    _milestone_count("chapter", 30, "Chapter Machine", "\U0001F5C2\uFE0F", "Chapters", "Complete"),
    _milestone_count("chapter", 50, "Syllabus Slayer", "\U0001F4D6", "Chapters", "Complete"),
    _milestone_count("subtopic", 10, "Subtopic Starter", "\U0001F9E9", "Subtopics", "Complete"),
    _milestone_count("subtopic", 30, "Subtopic Grinder", "\U0001F52C", "Subtopics", "Complete"),
    _milestone_count("subtopic", 60, "Subtopic Master", "\U0001F393", "Subtopics", "Complete"),
    _milestone_count("book", 1, "First Book Down", "\U0001F4D7", "Books", "Complete"),
    _milestone_count("book", 3, "Bookworm", "\U0001F4DA", "Books", "Complete"),
    _milestone_count("book", 5, "Library Clearer", "\U0001F3DB\uFE0F", "Books", "Complete"),
    _milestone_count("pyq", 3, "PYQ Rookie", "\U0001F4DD", "PYQs", "Complete"),
    _milestone_count("pyq", 5, "PYQ Regular", "\U0001F4CB", "PYQs", "Complete"),
    _milestone_count("pyq", 10, "PYQ Veteran", "\U0001F3AF", "PYQs", "Complete"),
    _revision(1, "1st Revision Done", "\U0001F501"),
    _revision(2, "2nd Revision Done", "\U0001F504"),
    _revision(3, "3rd Revision Done", "\U0001F3C1"),

    # --- Special / fun ----------------------------------------------------#
    Achievement(
        id="early_bird", name="Early Bird", emoji="\U0001F305",
        description="Start a session between 4 AM and 7 AM (IST).", category="Special",
        check=lambda c: c["early_bird_count"] >= 1, reward_coins=100,
    ),
    Achievement(
        id="night_owl", name="Night Owl", emoji="\U0001F989",
        description="Start a session between 11 PM and 3 AM (IST).", category="Special",
        check=lambda c: c["night_owl_count"] >= 1, reward_coins=100,
    ),
    Achievement(
        id="perfect_week", name="Perfect Week", emoji="\U0001F4AF",
        description="Study on all 7 days of the last week.", category="Special",
        check=lambda c: c["perfect_week"], reward_coins=500,
    ),
    Achievement(
        id="collector_10", name="Achievement Hunter", emoji="\U0001F3C5",
        description="Unlock 10 achievements.", category="Special",
        check=lambda c: c["achievements_count"] >= 10, reward_coins=300,
    ),
    Achievement(
        id="collector_25", name="Completionist", emoji="\U0001F31F",
        description="Unlock 25 achievements.", category="Special",
        check=lambda c: c["achievements_count"] >= 25, reward_coins=1000,
    ),
]

ACHIEVEMENTS_BY_ID: dict[str, Achievement] = {a.id: a for a in ACHIEVEMENTS}

CATEGORY_ORDER: list[str] = [
    "Time Studied", "Sessions", "Streaks", "Daily Streaks", "Tiers",
    "Subjects", "Chapters", "Subtopics", "Books", "PYQs", "Revisions", "Economy", "Special",
]


def evaluate(context: dict[str, Any], already_unlocked: set[str]) -> list[Achievement]:
    """Return the achievements newly satisfied by `context` that aren't
    already in `already_unlocked`."""
    newly_unlocked = []
    for achievement in ACHIEVEMENTS:
        if achievement.id in already_unlocked:
            continue
        try:
            if achievement.check(context):
                newly_unlocked.append(achievement)
        except (KeyError, TypeError):
            continue
    return newly_unlocked
