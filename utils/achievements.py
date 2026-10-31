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


# ------------------------------------------------------------------ #
#  Helper factories — each returns one Achievement with a repeatable
#  pattern so the big ACHIEVEMENTS list below stays readable.
# ------------------------------------------------------------------ #

def _time(hours: float, name: str, emoji: str, *, reward: int | None = None) -> Achievement:
    seconds = int(hours * HOUR)
    return Achievement(
        id=f"time_{int(hours)}h",
        name=name,
        emoji=emoji,
        description=f"Accumulate {hours:g} hours of total study time.",
        category="Time Studied",
        check=lambda c, _s=seconds: c["total_seconds"] >= _s,
        reward_coins=reward if reward is not None else int(hours * 15),
    )


def _sessions(count: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"sessions_{count}",
        name=name,
        emoji=emoji,
        description=f"Complete {count:,} study sessions.",
        category="Sessions",
        check=lambda c, _n=count: c["sessions_count"] >= _n,
        reward_coins=count * 8,
    )


def _streak(days: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"streak_{days}",
        name=name,
        emoji=emoji,
        description=f"Reach a {days}-day study streak.",
        category="Streaks",
        check=lambda c, _d=days: c["longest_streak"] >= _d,
        reward_coins=days * 20,
    )


def _daily_streak(days: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"daily_streak_{days}",
        name=name,
        emoji=emoji,
        description=f"Claim `.daily` {days} days in a row.",
        category="Daily Streaks",
        check=lambda c, _d=days: c["daily_streak"] >= _d,
        reward_coins=days * 25,
    )


def _tier(level: int, tier_name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"tier_{level}",
        name=f"Reached {tier_name}",
        emoji=emoji,
        description=f"Reach level {level} and enter the {tier_name} tier.",
        category="Tiers",
        check=lambda c, _l=level: c["level"] >= _l,
        reward_coins=level * 10,
    )


def _subject(subject: str, hours: float, label: str, emoji: str, name: str) -> Achievement:
    seconds = int(hours * HOUR)
    return Achievement(
        id=f"subject_{subject}_{int(hours)}h",
        name=name,
        emoji=emoji,
        description=f"Log {hours:g} hours studying {label}.",
        category="Subjects",
        check=lambda c, _s=subject, _sec=seconds: c["subject_seconds"].get(_s, 0) >= _sec,
        reward_coins=int(hours * 12),
    )


def _milestone_count(kind: str, count: int, name: str, emoji: str, category: str, verb: str) -> Achievement:
    return Achievement(
        id=f"{kind}_{count}",
        name=name,
        emoji=emoji,
        description=f"{verb} {count} {kind}{'s' if count != 1 else ''}.",
        category=category,
        check=lambda c, _kind=kind, _count=count: (c.get(f"{_kind}s_completed", 0) or c.get(f"{_kind}_years_completed", 0)) >= _count,
        reward_coins=count * {"chapter": 10, "subtopic": 8, "book": 100, "pyq": 60}.get(kind, 10),
    )


def _revision(n: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"revision_{n}",
        name=name,
        emoji=emoji,
        description=f"Log your {n}{'st' if n == 1 else 'nd' if n == 2 else 'rd' if n == 3 else 'th'} revision pass.",
        category="Revisions",
        check=lambda c, _n=n: c["max_revision"] >= _n,
        reward_coins=n * 150,
    )


def _coins(amount: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"coins_{amount}",
        name=name,
        emoji=emoji,
        description=f"Earn {amount:,} lifetime coins.",
        category="Economy",
        check=lambda c, _a=amount: c["coins_lifetime"] >= _a,
        reward_coins=int(amount * 0.08),
    )


def _boxes(count: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"boxes_{count}",
        name=name,
        emoji=emoji,
        description=f"Open {count:,} boxes.",
        category="Economy",
        check=lambda c, _n=count: c["boxes_opened"] >= _n,
        reward_coins=count * 15,
    )


def _purchases(count: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"purchases_{count}",
        name=name,
        emoji=emoji,
        description=f"Buy {count} item{'s' if count != 1 else ''} from any shop.",
        category="Economy",
        check=lambda c, _n=count: c["items_purchased"] >= _n,
        reward_coins=count * 25,
    )


def _pets(count: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"pets_{count}",
        name=name,
        emoji=emoji,
        description=f"Own {count} pet{'s' if count != 1 else ''}.",
        category="Pets",
        check=lambda c, _n=count: c.get("pets_owned", 0) >= _n,
        reward_coins=count * 50,
    )


def _candy(amount: int, name: str, emoji: str) -> Achievement:
    return Achievement(
        id=f"candy_{amount}",
        name=name,
        emoji=emoji,
        description=f"Earn {amount:,} total candy.",
        category="Halloween",
        check=lambda c, _a=amount: c.get("candy_earned", 0) >= _a,
        reward_coins=int(amount * 0.5),
    )


def _marathon(hours: float, name: str, emoji: str) -> Achievement:
    """Single session duration achievements."""
    seconds = int(hours * HOUR)
    tag = f"{hours:g}h" if hours >= 1 else f"{int(hours * 60)}m"
    return Achievement(
        id=f"marathon_{tag}",
        name=name,
        emoji=emoji,
        description=f"Complete a single study session of {hours:g}+ hours.",
        category="Marathon",
        check=lambda c, _s=seconds: c.get("longest_session_seconds", 0) >= _s,
        reward_coins=int(hours * 100),
    )


# ------------------------------------------------------------------ #
#  THE BIG LIST  —  175 achievements
# ------------------------------------------------------------------ #

ACHIEVEMENTS: list[Achievement] = [

    # ============================================================== #
    #  TIME STUDIED  (15)
    # ============================================================== #
    _time(1,    "First Hour",               "\u23F1\uFE0F"),
    _time(3,    "Warm-Up Over",             "\U0001F3CB\uFE0F"),
    _time(5,    "Getting Serious",          "\U0001F4DA"),
    _time(10,   "Double Digits",            "\U0001F522"),
    _time(25,   "Quarter Century",          "\U0001F525"),
    _time(50,   "Halfway There",            "\U0001F4AA"),
    _time(75,   "Grindset Unlocked",        "\u2699\uFE0F"),
    _time(100,  "Century Club",             "\U0001F3C6"),
    _time(150,  "Sleep Is Overrated",       "\U0001F634"),
    _time(200,  "Bicentennial Grinder",     "\U0001F30D"),
    _time(250,  "Iron Will",               "\u26CF\uFE0F"),
    _time(300,  "Kota Veteran",             "\U0001F3D8\uFE0F"),
    _time(500,  "Unstoppable Force",        "\U0001F680"),
    _time(750,  "No Scope, No Sleep",       "\U0001F52D"),
    _time(1000, "Thousand Hour Theorem",    "\U0001F451"),

    # ============================================================== #
    #  SESSIONS  (12)
    # ============================================================== #
    _sessions(1,    "First Steps",            "\U0001F476"),
    _sessions(10,   "Warming Up",             "\U0001F3C3"),
    _sessions(25,   "In The Groove",          "\U0001F3B5"),
    _sessions(50,   "Half Century Hustle",    "\U0001F4C8"),
    _sessions(75,   "Consistency Is Key",     "\U0001F511"),
    _sessions(100,  "Triple Digits",          "\U0001F3AF"),
    _sessions(150,  "Creature of Habit",      "\U0001F9A5"),
    _sessions(200,  "Session Veteran",        "\U0001F396\uFE0F"),
    _sessions(300,  "Can't Stop Won't Stop",  "\U0001F525"),
    _sessions(500,  "Session Overlord",       "\u2699\uFE0F"),
    _sessions(750,  "This IS My Desk",        "\U0001F3E0"),
    _sessions(1000, "Four-Figure Flex",       "\U0001F4AA"),

    # ============================================================== #
    #  STREAKS  (12)
    # ============================================================== #
    _streak(3,   "On A Roll",               "\U0001F3B2"),
    _streak(5,   "Weekday Warrior",         "\u2694\uFE0F"),
    _streak(7,   "One Week Strong",         "\U0001F4C5"),
    _streak(14,  "Two Weeks Deep",          "\U0001F4CC"),
    _streak(21,  "Three-Week Titan",        "\U0001F94A"),
    _streak(30,  "Monthly Regular",         "\U0001F4C6"),
    _streak(45,  "Streak Sensei",           "\U0001F94B"),
    _streak(60,  "Two Months Straight",     "\U0001F9F1"),
    _streak(90,  "Quarter-Year Grind",      "\U0001F5C3\uFE0F"),
    _streak(100, "Streak Legend",           "\U0001F525"),
    _streak(180, "Half-Year Hero",          "\U0001F30D"),
    _streak(365, "The Yearly Blaze",        "\u2604\uFE0F"),

    # ============================================================== #
    #  DAILY CLAIM STREAKS  (8)
    # ============================================================== #
    _daily_streak(3,   "Showing Up",        "\U0001F44B"),
    _daily_streak(7,   "Loyal",             "\U0001F49C"),
    _daily_streak(14,  "Committed",         "\U0001F4DD"),
    _daily_streak(21,  "Habit Formed",      "\U0001F9E0"),
    _daily_streak(30,  "Daily Devotee",     "\U0001F3E9"),
    _daily_streak(45,  "Claim Machine",     "\U0001F4E5"),
    _daily_streak(60,  "Daily Disciple",    "\U0001F4BF"),
    _daily_streak(100, "The Daily Legend",  "\U0001F31F"),

    # ============================================================== #
    #  TIERS / LEVELS  (9)  — mirrors utils/xp.py TIERS
    # ============================================================== #
    _tier(5,   "Bronze",     "\U0001F949"),
    _tier(10,  "Silver",     "\U0001F948"),
    _tier(20,  "Gold",       "\U0001F947"),
    _tier(35,  "Platinum",   "\U0001F539"),
    _tier(50,  "Diamond",    "\U0001F48E"),
    _tier(75,  "Ascendant",  "\U0001F343"),
    _tier(100, "Immortal",   "\U0001F480"),
    _tier(150, "Radiant",    "\u2600\uFE0F"),
    _tier(200, "AIR 1",      "\U0001F680"),

    # ============================================================== #
    #  SUBJECTS  (18)  — 6 per subject (1h, 5h, 10h, 25h, 50h, 100h)
    # ============================================================== #
    # Physics
    _subject("physics",   1,   "Physics", "\U0001F4D8", "Newton's Apprentice"),
    _subject("physics",   5,   "Physics", "\U0001F4D8", "Coulomb's Pupil"),
    _subject("physics",   10,  "Physics", "\U0001F4D8", "Faraday's Understudy"),
    _subject("physics",   25,  "Physics", "\U0001F4D8", "Maxwell's Prodigy"),
    _subject("physics",   50,  "Physics", "\U0001F4D8", "Feynman's Shadow"),
    _subject("physics",   100, "Physics", "\U0001F4D8", "Einstein Mode"),

    # Chemistry
    _subject("chemistry", 1,   "Chemistry", "\U0001F9EA", "First Reaction"),
    _subject("chemistry", 5,   "Chemistry", "\U0001F9EA", "Mole Rat"),
    _subject("chemistry", 10,  "Chemistry", "\U0001F9EA", "Titration Titan"),
    _subject("chemistry", 25,  "Chemistry", "\U0001F9EA", "Organic Overlord"),
    _subject("chemistry", 50,  "Chemistry", "\U0001F9EA", "Bond Breaker"),
    _subject("chemistry", 100, "Chemistry", "\U0001F9EA", "Periodic Legend"),

    # Maths
    _subject("maths",     1,   "Maths", "\U0001F4D0", "Derivative Dabbler"),
    _subject("maths",     5,   "Maths", "\U0001F4D0", "Integration Initiate"),
    _subject("maths",     10,  "Maths", "\U0001F4D0", "Matrix Maniac"),
    _subject("maths",     25,  "Maths", "\U0001F4D0", "Limit Breaker"),
    _subject("maths",     50,  "Maths", "\U0001F4D0", "Calculus Conqueror"),
    _subject("maths",     100, "Maths", "\U0001F4D0", "Euler's Heir"),

    # ============================================================== #
    #  ECONOMY — Coins  (7)
    # ============================================================== #
    _coins(500,    "Pocket Change",          "\U0001FA99"),
    _coins(2500,   "Coin Hoarder",           "\U0001F4B0"),
    _coins(5000,   "Nickel & Dimed",         "\U0001F4B5"),
    _coins(10000,  "High Roller",            "\U0001F3B0"),
    _coins(25000,  "Money Talks",            "\U0001F4B8"),
    _coins(50000,  "Scrooge McDuck",         "\U0001F911"),
    _coins(100000, "Six-Figure Salary",      "\U0001F4B3"),

    # ============================================================== #
    #  ECONOMY — Boxes  (5)
    # ============================================================== #
    _boxes(1,   "What's Inside?",           "\U0001F381"),
    _boxes(10,  "Box Enthusiast",           "\U0001F4E6"),
    _boxes(25,  "Loot Goblin",             "\U0001F47A"),
    _boxes(50,  "Unboxing Addict",          "\U0001F3AB"),
    _boxes(100, "Box Annihilator",          "\U0001F4A5"),

    # ============================================================== #
    #  ECONOMY — Purchases  (5)
    # ============================================================== #
    _purchases(1,  "First Purchase",         "\U0001F6D2"),
    _purchases(5,  "Repeat Customer",        "\U0001F6CD\uFE0F"),
    _purchases(10, "Big Spender",            "\U0001F4B8"),
    _purchases(25, "Shopping Spree",         "\U0001F6D2"),
    _purchases(50, "The Collector",          "\U0001F5C4\uFE0F"),

    # ============================================================== #
    #  PETS  (7)
    # ============================================================== #
    _pets(1,  "First Companion",             "\U0001F43E"),
    _pets(2,  "Dynamic Duo",                 "\U0001F415"),
    _pets(3,  "Pokémon Trainer",             "\U0001F3C3"),
    _pets(5,  "Pet Collector",               "\U0001F431"),
    _pets(8,  "Animal Shelter",              "\U0001F3E0"),
    _pets(10, "Pet Hoarder",                 "\U0001F98E"),
    _pets(15, "Professor Oak",               "\U0001F9D1\u200D\U0001F52C"),

    # ============================================================== #
    #  CHAPTERS / SUBTOPICS / BOOKS / PYQs / REVISIONS  (19)
    # ============================================================== #
    # Chapters
    _milestone_count("chapter",  1,  "First Chapter Down",   "\U0001F4D1", "Chapters",  "Complete"),
    _milestone_count("chapter",  5,  "Chapter Chipper",      "\U0001F4D1", "Chapters",  "Complete"),
    _milestone_count("chapter",  15, "Chapter Crusher",      "\U0001F4DA", "Chapters",  "Complete"),
    _milestone_count("chapter",  30, "Chapter Machine",      "\U0001F5C2\uFE0F", "Chapters",  "Complete"),
    _milestone_count("chapter",  50, "Syllabus Slayer",      "\U0001F4D6", "Chapters",  "Complete"),
    _milestone_count("chapter",  75, "Syllabus Annihilator", "\U0001F4DA", "Chapters",  "Complete"),

    # Subtopics
    _milestone_count("subtopic", 5,  "Subtopic Starter",     "\U0001F9E9", "Subtopics", "Complete"),
    _milestone_count("subtopic", 10, "Subtopic Grinder",     "\U0001F52C", "Subtopics", "Complete"),
    _milestone_count("subtopic", 30, "Detail Oriented",      "\U0001F50E", "Subtopics", "Complete"),
    _milestone_count("subtopic", 60, "Subtopic Master",      "\U0001F393", "Subtopics", "Complete"),
    _milestone_count("subtopic", 100,"Micro Manager",        "\U0001F9EC", "Subtopics", "Complete"),

    # Books
    _milestone_count("book", 1,  "First Book Down",          "\U0001F4D7", "Books",     "Complete"),
    _milestone_count("book", 3,  "Bookworm",                 "\U0001F4DA", "Books",     "Complete"),
    _milestone_count("book", 5,  "Library Clearer",          "\U0001F3DB\uFE0F", "Books", "Complete"),
    _milestone_count("book", 10, "Shelf Destroyer",          "\U0001F4D5", "Books",     "Complete"),

    # PYQs
    _milestone_count("pyq", 1,  "PYQ Rookie",                "\U0001F4DD", "PYQs",     "Complete"),
    _milestone_count("pyq", 3,  "PYQ Regular",               "\U0001F4CB", "PYQs",     "Complete"),
    _milestone_count("pyq", 5,  "PYQ Veteran",               "\U0001F3AF", "PYQs",     "Complete"),
    _milestone_count("pyq", 10, "PYQ Conqueror",             "\U0001F9E0", "PYQs",     "Complete"),

    # Revisions
    _revision(1, "1st Revision Done",       "\U0001F501"),
    _revision(2, "2nd Revision Done",       "\U0001F504"),
    _revision(3, "3rd Revision Done",       "\U0001F3C1"),
    _revision(4, "4th Time's The Charm",    "\U0001F504"),
    _revision(5, "Revision Demon",          "\U0001F525"),

    # ============================================================== #
    #  MARATHON  — single-session length  (7)
    # ============================================================== #
    _marathon(1,   "Hour Block",             "\u23F0"),
    _marathon(1.5, "90-Minute Sprint",       "\U0001F3C3"),
    _marathon(2,   "Focus Fortress",         "\U0001F3F0"),
    _marathon(3,   "Tunnel Vision",          "\U0001F4A1"),
    _marathon(4,   "Endurance Engine",       "\U0001F6E0\uFE0F"),
    _marathon(5,   "Iron Seat",              "\U0001F9F2"),
    _marathon(6,   "Absolute Unit",          "\U0001F4AA"),

    # ============================================================== #
    #  HALLOWEEN / SEASONAL  (8)
    # ============================================================== #
    _candy(50,    "Trick or Treat",          "\U0001F36C"),
    _candy(100,   "Sugar Rush",              "\U0001F36D"),
    _candy(250,   "Cavity Creator",          "\U0001F9B7"),
    _candy(500,   "Willy Wonka",             "\U0001F36B"),
    _candy(1000,  "Candy Overlord",          "\U0001F383"),

    Achievement(
        id="halloween_pass_5", name="Pumpkin Carver", emoji="\U0001F383",
        description="Reach level 5 on your Jack-o'-Lantern pass.",
        category="Halloween",
        check=lambda c: c.get("halloween_pass_level", 0) >= 5,
        reward_coins=200,
    ),
    Achievement(
        id="halloween_pass_10", name="Haunted Scholar", emoji="\U0001F47B",
        description="Reach level 10 on your Jack-o'-Lantern pass.",
        category="Halloween",
        check=lambda c: c.get("halloween_pass_level", 0) >= 10,
        reward_coins=500,
    ),
    Achievement(
        id="halloween_pass_max", name="The Great Pumpkin", emoji="\U0001F451",
        description="Max out your Jack-o'-Lantern pass (level 14).",
        category="Halloween",
        check=lambda c: c.get("halloween_pass_level", 0) >= 14,
        reward_coins=1000,
    ),

    # ============================================================== #
    #  SPECIAL / FUN  (18)
    # ============================================================== #
    Achievement(
        id="early_bird", name="Early Bird", emoji="\U0001F305",
        description="Start a session between 4 AM and 7 AM (IST).",
        category="Special",
        check=lambda c: c["early_bird_count"] >= 1,
        reward_coins=100,
    ),
    Achievement(
        id="early_bird_10", name="Sunrise Soldier", emoji="\U0001F31E",
        description="Start 10 sessions between 4 AM and 7 AM (IST).",
        category="Special",
        check=lambda c: c["early_bird_count"] >= 10,
        reward_coins=300,
    ),
    Achievement(
        id="early_bird_50", name="Dawn Deity", emoji="\u2600\uFE0F",
        description="Start 50 sessions between 4 AM and 7 AM (IST).",
        category="Special",
        check=lambda c: c["early_bird_count"] >= 50,
        reward_coins=750,
    ),
    Achievement(
        id="night_owl", name="Night Owl", emoji="\U0001F989",
        description="Start a session between 11 PM and 3 AM (IST).",
        category="Special",
        check=lambda c: c["night_owl_count"] >= 1,
        reward_coins=100,
    ),
    Achievement(
        id="night_owl_10", name="Midnight Maniac", emoji="\U0001F319",
        description="Start 10 sessions between 11 PM and 3 AM (IST).",
        category="Special",
        check=lambda c: c["night_owl_count"] >= 10,
        reward_coins=300,
    ),
    Achievement(
        id="night_owl_50", name="Vampire Scholar", emoji="\U0001F9DB",
        description="Start 50 sessions between 11 PM and 3 AM (IST).",
        category="Special",
        check=lambda c: c["night_owl_count"] >= 50,
        reward_coins=750,
    ),
    Achievement(
        id="perfect_week", name="Perfect Week", emoji="\U0001F4AF",
        description="Study on all 7 days of the last week.",
        category="Special",
        check=lambda c: c["perfect_week"],
        reward_coins=500,
    ),
    Achievement(
        id="perfect_weeks_4", name="Monthly Perfection", emoji="\U0001F4C5",
        description="Achieve 4 perfect study weeks.",
        category="Special",
        check=lambda c: c.get("perfect_week_count", 0) >= 4,
        reward_coins=1000,
    ),
    Achievement(
        id="weekend_warrior", name="Weekend Warrior", emoji="\u2694\uFE0F",
        description="Study on both Saturday and Sunday in the same week.",
        category="Special",
        check=lambda c: c.get("weekend_warrior", False),
        reward_coins=200,
    ),
    Achievement(
        id="subject_all_3", name="Triple Threat", emoji="\u2728",
        description="Study all 3 subjects (Physics, Chemistry, Maths) in one day.",
        category="Special",
        check=lambda c: c.get("all_subjects_today", False),
        reward_coins=250,
    ),
    Achievement(
        id="daily_double", name="Daily Double", emoji="\u26A1",
        description="Complete 2 study sessions in a single day.",
        category="Special",
        check=lambda c: c.get("sessions_today", 0) >= 2,
        reward_coins=75,
    ),
    Achievement(
        id="hat_trick", name="Hat Trick", emoji="\U0001F3A9",
        description="Complete 3 study sessions in a single day.",
        category="Special",
        check=lambda c: c.get("sessions_today", 0) >= 3,
        reward_coins=150,
    ),
    Achievement(
        id="pentakill", name="Penta-Study", emoji="\U0001F525",
        description="Complete 5 study sessions in a single day.",
        category="Special",
        check=lambda c: c.get("sessions_today", 0) >= 5,
        reward_coins=400,
    ),
    Achievement(
        id="daily_3h", name="Three-Hour Tour", emoji="\u26F5",
        description="Accumulate 3+ hours of study in a single day.",
        category="Special",
        check=lambda c: c.get("today_seconds", 0) >= 3 * HOUR,
        reward_coins=200,
    ),
    Achievement(
        id="daily_5h", name="Full Work Day", emoji="\U0001F4BC",
        description="Accumulate 5+ hours of study in a single day.",
        category="Special",
        check=lambda c: c.get("today_seconds", 0) >= 5 * HOUR,
        reward_coins=400,
    ),
    Achievement(
        id="daily_8h", name="Corporate Grind", emoji="\U0001F3E2",
        description="Accumulate 8+ hours of study in a single day.",
        category="Special",
        check=lambda c: c.get("today_seconds", 0) >= 8 * HOUR,
        reward_coins=750,
    ),
    Achievement(
        id="daily_12h", name="JEE Sigma Mode", emoji="\U0001F9E0",
        description="Accumulate 12+ hours of study in a single day.",
        category="Special",
        check=lambda c: c.get("today_seconds", 0) >= 12 * HOUR,
        reward_coins=1500,
    ),

    # ============================================================== #
    #  META — achievement collection  (7)
    # ============================================================== #
    Achievement(
        id="collector_10", name="Badge Collector", emoji="\U0001F3C5",
        description="Unlock 10 achievements.",
        category="Meta",
        check=lambda c: c["achievements_count"] >= 10,
        reward_coins=200,
    ),
    Achievement(
        id="collector_25", name="Achievement Hunter", emoji="\U0001F31F",
        description="Unlock 25 achievements.",
        category="Meta",
        check=lambda c: c["achievements_count"] >= 25,
        reward_coins=500,
    ),
    Achievement(
        id="collector_50", name="Trophy Room", emoji="\U0001F3C6",
        description="Unlock 50 achievements.",
        category="Meta",
        check=lambda c: c["achievements_count"] >= 50,
        reward_coins=1000,
    ),
    Achievement(
        id="collector_75", name="Walking Museum", emoji="\U0001F3DB\uFE0F",
        description="Unlock 75 achievements.",
        category="Meta",
        check=lambda c: c["achievements_count"] >= 75,
        reward_coins=1500,
    ),
    Achievement(
        id="collector_100", name="Centurion", emoji="\U0001F396\uFE0F",
        description="Unlock 100 achievements.",
        category="Meta",
        check=lambda c: c["achievements_count"] >= 100,
        reward_coins=2500,
    ),
    Achievement(
        id="collector_125", name="Completionist", emoji="\U0001F48E",
        description="Unlock 125 achievements.",
        category="Meta",
        check=lambda c: c["achievements_count"] >= 125,
        reward_coins=4000,
    ),
    Achievement(
        id="collector_150", name="100%'er", emoji="\U0001F451",
        description="Unlock 150 achievements.",
        category="Meta",
        check=lambda c: c["achievements_count"] >= 150,
        reward_coins=6000,
    ),
]


ACHIEVEMENTS_BY_ID: dict[str, Achievement] = {a.id: a for a in ACHIEVEMENTS}

CATEGORY_ORDER: list[str] = [
    "Time Studied", "Sessions", "Streaks", "Daily Streaks", "Tiers",
    "Subjects", "Marathon", "Chapters", "Subtopics", "Books", "PYQs",
    "Revisions", "Economy", "Pets", "Halloween", "Special", "Meta",
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
