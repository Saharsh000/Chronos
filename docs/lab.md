# The Lab DLC — Design Document

> Phase 0 recon: deep-read of existing codebase + balance math.  
> Branch: `feat/lab-oc` · Author: recon agent · Date: 2026-11-15

---

## 1. Recon Summary

### 1.1 Coin and XP rates (from `config.py`)

| Metric | Min / tick | Max / tick | Source |
|---|---|---|---|
| **Coins per minute** | 1 | 3 | `COINS_MIN_PER_MINUTE` / `COINS_MAX_PER_MINUTE` |
| **XP per minute** | 6 | 14 | `XP_MIN_PER_MINUTE` / `XP_MAX_PER_MINUTE` |

Both are rolled independently per complete minute, summed, and credited during the session via `credit_progress()`.  IST day boundaries use `IST = timezone(timedelta(minutes=330))`; SQLite queries use `IST_SQL_MODIFIER = "+330 minutes"`.

### 1.2 Daily income breakdown ("dedicated study day" D)

A "dedicated study day" assumes: 8 h of OC study, `.daily` at max streak (40-day cap), `.work` × 8 (once per hour for 8 active hours), `.weekly` amortised, and `.beg` × 20 typical uses.

| Source | Calculation | Coins |
|---|---|---|
| `.daily` base (avg) | (120 + 220) / 2 = 170 | 170 |
| Max streak bonus (40 days) | 40 × 15 = 600 | 600 |
| **`.daily` total (max streak)** | | **820** |
| `.work` × 8 uses | avg 130 × 8 | 1,040 |
| `.weekly` / 7 | avg 1,200 / 7 | 171 |
| `.beg` × 20 (75% success) | avg 27.5 × 0.75 × 20 | 412 |
| Study coins (8 h × avg 2/min) | 480 min × 2 | 960 |
| **D (total)** | | **~3,404** |

> **Config values used:**  
> `DAILY_COINS_MIN=120`, `DAILY_COINS_MAX=220`, `DAILY_STREAK_BONUS_PER_DAY=15`, `DAILY_STREAK_BONUS_CAP_DAYS=40`  
> `WORK_COINS_MIN=80`, `WORK_COINS_MAX=180`, `WORK_COOLDOWN_SECONDS=3600`  
> `WEEKLY_COINS_MIN=900`, `WEEKLY_COINS_MAX=1500`  
> `BEG_COINS_MIN=10`, `BEG_COINS_MAX=45`, `BEG_FAIL_CHANCE=0.25`

### 1.3 OC repeat-craft daily cap verification

**Target:** OC repeat-craft income ≤ 15 % × D

```
15% × D = 0.15 × 3,404 ≈ 510 coins/day
```

> ⚠️ **The proposed cap of 1,000 coins/day exceeds 15 % × D (≈ 510).**  
> At the current economy calibration, 1,000 is ~**29 % of D**, not 15 %.  
> **Decision needed:** either lower the cap to ≤ 510, or increase D (by raising `.work` payouts or adding more coin sources). The design document records 1,000 as the placeholder; the implementation team must confirm before shipping.

---

## 2. DB Migration Plan

All new tables follow the existing pattern: `CREATE TABLE IF NOT EXISTS` in `SCHEMA` (or the `_migrate()` guard) so the bot can start against an older database without data loss. New columns on existing tables go through `_migrate_table()` exactly like `SESSIONS_MIGRATIONS` and `USER_STATS_MIGRATIONS`.

### 2.1 New tables

#### `lab_unlocks`
```sql
CREATE TABLE IF NOT EXISTS lab_unlocks (
    user_id     INTEGER NOT NULL,
    guild_id    INTEGER NOT NULL,
    unlocked_at INTEGER NOT NULL,          -- unix epoch; when user ran ,lab unlock
    PRIMARY KEY (user_id, guild_id)
);
```
One row per (user, guild) — presence means The Lab DLC is active for this user.

#### `lab_elements`
```sql
CREATE TABLE IF NOT EXISTS lab_elements (
    user_id  INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    element  TEXT    NOT NULL,            -- 'C' | 'H' | 'O' | 'N' | 'Cl' | 'F' | 'Br' | 'I'
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id, element)
);
```
Stock of each element. Capped at 500 per element per user (enforced in application code, not DB constraint).

#### `lab_compounds`
```sql
CREATE TABLE IF NOT EXISTS lab_compounds (
    user_id         INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    compound_id     TEXT    NOT NULL,     -- matches data/compounds.json[].id
    times_crafted   INTEGER NOT NULL DEFAULT 0,
    first_crafted_at INTEGER NOT NULL,   -- unix epoch
    PRIMARY KEY (user_id, guild_id, compound_id)
);
```

#### `lab_daily`
```sql
CREATE TABLE IF NOT EXISTS lab_daily (
    user_id      INTEGER NOT NULL,
    guild_id     INTEGER NOT NULL,
    date_ist     TEXT    NOT NULL,        -- IST date string 'YYYY-MM-DD' (same format as user_daily.last_claim_date)
    repeat_coins INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id, date_ist)
);
```
Tracks repeat-craft coins earned today (IST). Resets each IST midnight; the daily cap is enforced by checking `repeat_coins < 1000` (or whichever final cap is chosen) before crediting.

### 2.2 New columns on existing tables

Added via `_migrate_table()` on startup:

| Table | Column | DDL |
|---|---|---|
| `sessions` | `track TEXT` | `ALTER TABLE sessions ADD COLUMN track TEXT` |
| `sessions` | `credited_elements TEXT` | `ALTER TABLE sessions ADD COLUMN credited_elements TEXT` |

**`sessions.track`** — nullable string, set to `"oc"` when the session was started with `,start oc` / `,start organic` / web `mode:"oc"`. Used by `credit_progress()` to decide whether to roll element drops.

**`sessions.credited_elements`** — JSON blob, e.g. `{"C": 3, "H": 7, "O": 1}`.  Accumulates all elements credited so far during this session. On every tick, `credit_progress()` reads this, computes new drops for the newly-credited minutes only, and writes the updated totals back atomically — the same idempotency pattern used by `credited_seconds` / `credited_xp` / `credited_coins`.

```python
# Idempotency sketch (mirrors credit_progress structure):
already = json.loads(session["credited_elements"] or "{}")
new_drops = _roll_elements(new_minutes, ist_day_oc_minutes)
merged = {el: already.get(el, 0) + new_drops.get(el, 0) for el in ELEMENTS}
await conn.execute(
    "UPDATE sessions SET credited_elements = ? WHERE session_id = ?",
    (json.dumps(merged), session_id)
)
```

### 2.3 Migration dict additions (placed in `database.py`)

```python
LAB_SESSIONS_MIGRATIONS: dict[str, str] = {
    "track":              "ALTER TABLE sessions ADD COLUMN track TEXT",
    "credited_elements":  "ALTER TABLE sessions ADD COLUMN credited_elements TEXT",
}
```

---

## 3. Element Engine Design

### 3.1 Elements and per-minute drop rates

Eight elements are dropped during OC sessions. Rates are probabilities per minute of credited OC time:

| Element | Symbol | Drop prob / min | Notes |
|---|---|---|---|
| Carbon | C | 0.90 | Backbone; almost every drop |
| Hydrogen | H | 0.85 | Pairs with C |
| Oxygen | O | 0.60 | Very common in OC |
| Nitrogen | N | 0.35 | Amines, amides |
| Chlorine | Cl | 0.15 | Halogenated; uncommon |
| Fluorine | F | 0.08 | Rare halogen |
| Bromine | Br | 0.08 | Rare halogen |
| Iodine | I | 0.04 | Very rare; high reward value |

Each minute, for each element, roll `random.random() < rate`. On a hit, add 1 unit to the pending drop for that element. This is `_roll_elements(minutes, ist_day_oc_minutes)` called from `credit_progress()`.

### 3.2 6-hour per-IST-day cap

The element drop engine runs at **full rate** for the first 6 hours (360 credited OC minutes) of a user's OC sessions within an IST calendar day, and at **50 % rate** thereafter:

```python
ELEMENT_FULL_RATE_MINUTES = 360   # 6 h
ELEMENT_HALF_RATE_AFTER   = True  # 50% after cap

def _effective_rate(base_rate: float, ist_day_oc_minutes_so_far: int) -> float:
    if ist_day_oc_minutes_so_far >= ELEMENT_FULL_RATE_MINUTES:
        return base_rate * 0.5
    return base_rate
```

`ist_day_oc_minutes_so_far` is queried from `session_log` (OC sessions completed today) + the live session's current credited OC time. This keeps the cap restart-safe.

### 3.3 Per-element inventory cap (500)

Before writing new drops to `lab_elements`, the engine checks the current stock:

```python
for element, qty in new_drops.items():
    current = await db.get_lab_element(user_id, guild_id, element)
    actual  = min(qty, 500 - current)   # never exceed 500
    if actual > 0:
        await db.add_lab_element(user_id, guild_id, element, actual)
        if actual < qty:
            capped_elements.append(element)   # surfaced in ,stop summary
```

Capped elements are reported in the `,stop` OC session summary (e.g., "⚠️ Carbon is full — 500/500. Craft compounds to make room.").

### 3.4 Idempotency via `credited_elements`

`sessions.credited_elements` (JSON) is the Lab's exact equivalent of `credited_seconds` / `credited_xp`:

- **On each monitor tick**, `credit_progress()` reads `credited_elements`, computes drops for `new_minutes` (the minutes not yet credited), merges the result, and writes it back in the same DB transaction.
- Because the source of truth is `credited_seconds` (already restart-safe), a crash between ticks never double-counts: on restart the formula recalculates from the same `credited_seconds` baseline.
- `end_session()` does one final `credit_progress()` call (already the pattern) and then reads `credited_elements` for the `,stop` summary exactly as it reads `credited_coins`.

---

## 4. Synthesis / Compound Data

### 4.1 `data/compounds.json`

100 organic compounds stored as a JSON array. The file is loaded once at bot startup into an in-memory dict keyed by `id`. It is **never written at runtime**.

#### Schema of each entry

```json
{
  "id":       "ethanol",
  "name":     "Ethanol",
  "formula":  "C2H6O",
  "elements": { "C": 2, "H": 6, "O": 1, "N": 0, "Cl": 0, "F": 0, "Br": 0, "I": 0 },
  "category": "alcohol",
  "smiles":   "CCO",
  "fact":     "The intoxicating component of alcoholic beverages; also used as a solvent and fuel."
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | Snake-case unique key; matches `lab_compounds.compound_id` |
| `name` | string | Display name |
| `formula` | string | Hill notation (C first, then H, then alphabetical) |
| `elements` | object | Exact atom counts for all 8 elements; `0` for absent ones |
| `category` | string | One of: `alcohol`, `aldehyde`, `ketone`, `carboxylic_acid`, `ester`, `amine`, `amide`, `halide`, `aromatic`, `heterocycle` |
| `smiles` | string \| null | SMILES string for rendering; `null` if unavailable |
| `fact` | string | One-sentence flavour fact shown on first synthesis |

#### Categories (10)

`alcohol`, `aldehyde`, `ketone`, `carboxylic_acid`, `ester`, `amine`, `amide`, `halide`, `aromatic`, `heterocycle` — ~10 compounds per category.

### 4.2 Formula validator test

`tests/test_lab_compounds.py` loads `data/compounds.json` and asserts:

1. Exactly 100 entries.
2. Each `id` is unique and matches `^[a-z0-9_]+$`.
3. `formula` is parseable Hill notation and matches the sum of `elements`.
4. All 8 element keys present in every `elements` object.
5. `category` is one of the 10 valid values.
6. `smiles` is `null` or a non-empty string.
7. `fact` is a non-empty string.
8. At least 8 compounds per category.
9. Total first-time reward sum (`Σ 3×(30 + 10×heavy + 40×halogen)`) lands in `[40,000, 50,000]`.

---

## 5. Reward Math

### 5.1 First-time synthesis coins

```
first_time_coins(compound) = 3 × (30 + 10 × heavy_atoms + 40 × halogen_count)

where:
  heavy_atoms   = C + N + O + Cl + F + Br + I   (all non-H atoms)
  halogen_count = F + Br + I                      (not Cl — Cl is too common)
```

**Worked example — Ethanol (C₂H₆O):**
- heavy = 2 (C) + 1 (O) = 3
- halogen = 0
- reward = 3 × (30 + 30 + 0) = **180 coins**

**Expected sum over all 100 compounds:** ~42,000–46,000 coins (target 45,000 ± 5,000).  
Validation: average heavy ≈ 8, average halogen ≈ 0.8 → avg reward ≈ 426 → 100 × 426 ≈ 42,600. ✓

### 5.2 Repeat-craft coins

- **Per craft:** 20 % of that compound's first-time value (rounded to nearest integer).
- **Daily cap:** 1,000 coins/day from repeats (tracked in `lab_daily.repeat_coins`).
  - ⚠️ See §1.3: at the current economy this cap is ~29 % of D, not 15 %. Needs confirmation.

### 5.3 Category completion rewards

When a user synthesises the last compound in a category for the first time (all ~10 compounds first-crafted):

- **+1,000 Chronocoins**
- **Title unlock:** category-specific title (e.g., "Alcohol Alchemist", "Halide Handler", etc.)
- Announced to the check-in channel (see §8).

### 5.4 Collection milestones

| Milestone | Reward |
|---|---|
| 25 unique compounds | 1 × Mystery Box |
| 50 unique compounds | 2 × Mystery Box |
| 75 unique compounds | Exclusive title |
| 100 unique compounds | Title **"Grandmaster Chemist"** + badge + 5,000 coins |

Milestones are checked after every successful synthesis (first-craft only). Announced to the check-in channel.

---

## 6. Bot Commands

### `,lab [unlock]`

**Hub command.** No argument → shows the user's Lab overview: unlock status, element inventory, compounds synthesised/total, daily repeat-coin budget remaining.  
`,lab unlock` — pay the unlock cost (TBD: free or coin-gated) and insert a row into `lab_unlocks`. One-time per (user, guild).

### `,start oc` / `,start organic`

**Special-cased before `SUBJECT_ALIASES`** in `start_cmd`. When the subject argument normalises to `"oc"` or `"organic"`, the session is started with:
- `subject = "chemistry"` (counts toward chemistry stats as now)
- `track = "oc"` (new column — enables element drops)

```python
# In start_cmd, before the SUBJECT_ALIASES lookup:
raw = normalize_subject_key(subject or "")
if raw in ("oc", "organic"):
    resolved_subject = "chemistry"
    track = "oc"
else:
    subject_key = SUBJECT_ALIASES.get(raw)
    ...
    track = None
```

The session is started via a new `start_session(... track=track)` overload that writes the `track` column.

### `,stop`

Existing command, **extended** for OC sessions: if `session.track == "oc"`, the stop summary card additionally shows:

```
🧪 Elements earned this session
  C: +12  H: +9  O: +4  N: +2  Cl: +1
⚠️ Carbon is full (500/500) — craft compounds to make room.
```

Elements are read from `credited_elements` (the JSON column written throughout the session).

### `,synth <name|formula>`

Synthesise a compound. Accepts compound name (fuzzy match) or molecular formula.

1. Check user has Lab unlocked.
2. Resolve compound from `data/compounds.json`.
3. Check element inventory — deduct required atoms or error with what's missing.
4. Determine first vs. repeat craft (`lab_compounds` row exists?).
5. Award coins (§5.1 / §5.2); check/enforce daily repeat cap.
6. Upsert `lab_compounds` row (increment `times_crafted`, set `first_crafted_at` if first).
7. Post response in invoking channel.
8. Check category completion + milestones → announce if triggered (§8).

### `,compounds [category]`

**Compendium.** Lists the user's collection status.  
No argument → all categories with completion %  
`,compounds alcohol` → paginated list of alcohol compounds (name, formula, ✅/❌ first-crafted, times crafted).

---

## 7. Chronoweb Parity

### 7.1 New API module: `web/api_lab.py`

Registered in `web/server.py`'s `API_MODULES` list.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/lab` | Hub: unlock status, element stock, compound counts, daily cap remaining |
| `POST` | `/api/lab/unlock` | Unlock The Lab for this user |
| `GET` | `/api/lab/elements` | Full element inventory as `{C: 12, H: 9, ...}` |
| `POST` | `/api/lab/synth` | Body: `{compound: "ethanol"}`. Synthesise; returns reward, updated inventory |
| `GET` | `/api/lab/compendium` | Query: `?category=alcohol`. Returns compound list with user's craft data |

All follow the existing `Ctx` / `Routes` / `ok()` / `fail()` pattern from `web/common.py`.

### 7.2 Session start extension

`POST /api/session/start` gains an optional `mode` field:

```json
{ "subject": "chemistry", "mode": "oc" }
```

When `mode == "oc"`, the handler sets `track = "oc"` before calling `db.start_session(... track="oc")`. The `subject` override to `"chemistry"` is applied automatically server-side (same as the bot's special-case).

### 7.3 New frontend files

| File | Purpose |
|---|---|
| `web/static/views/lab.js` | Lab hub view: element inventory bars, compound grid, synth form, compendium |
| `web/static/views/lab.css` | Lab-specific styles (molecule card, element chip, progress ring per category) |

Both follow the existing view pattern: default-export async function `lab(root, ctx)`, using `h()`, `get()`, `post()`, `mount()`, `on()` from `core.js`.

### 7.4 Sidebar, Help, and Home/Live additions

- **Sidebar:** Add "🧪 The Lab" nav entry between Economy and Pets.
- **Help page:** Add Lab section with command reference.
- **Home page live strip:** Show element drops as float-text notifications alongside XP/coin toasts when `m.kind === "elements_dropped"` arrives on the SSE stream.
- **Live page (`/live`):** Show OC tag on session rows where `track == "oc"`.

### 7.5 SSE events emitted

| Event kind | Payload | When |
|---|---|---|
| `elements_dropped` | `{elements: {C:3, H:2, ...}}` | Every `credit_progress()` tick with new element drops |
| `compound_synth` | `{compound_id, name, coins, first_time}` | On successful `,synth` or POST /api/lab/synth |
| `lab_milestone` | `{milestone: "25", reward: "mystery_box"}` | On collection milestone |
| `lab_category` | `{category: "alcohol", coins: 1000, title: "..."}` | On category completion |

---

## 8. Announcement Policy

Mirrors the existing pattern: **check-in channel** (`guild_config.checkin_channel_id`) for server-wide events; **invoking channel** for personal command responses.

### Goes to the check-in channel

| Event | Trigger |
|---|---|
| **First-in-server compound discovery** | First user in this guild to synthesise compound X |
| **Category completion** | User first-crafts all compounds in a category |
| **Collection milestone** | User hits 25 / 50 / 75 / 100 unique compounds |

### Stays in the invoking channel (or API response only)

- `,lab`, `,synth`, `,compounds` replies
- Repeat-craft coin notifications
- Element inventory cap warnings in `,stop`

### Implementation note

Before posting a "first-in-server" announcement, query:

```sql
SELECT COUNT(*) FROM lab_compounds
WHERE guild_id = ? AND compound_id = ? AND times_crafted >= 1
```

If count was 0 before this synthesis and 1 after → first discovery.

---

## 9. Balance Targets

| Target | Value | Notes |
|---|---|---|
| OC time to first compound | ≤ 2 min | Drop rates (C=0.90, H=0.85, O=0.60) mean Methanol (CH₃OH: 1C, 4H, 1O) reachable in ~2 min |
| OC time for all 100 (once) | 8 – 12 h | At avg 426 coins/compound, 100 compounds ≈ ~10 h of full-rate OC drop time |
| No single compound | > 30 min avg OC time | Heaviest compounds need ~20–25 min of full-rate OC; none should exceed 30 min |
| Total first-time rewards | ~45,000 coins | Σ over all 100 compounds at formula above; validated by test |
| Repeat-craft daily income | ≤ 1,000 coins/day | ⚠️ Currently ~29% of D; target was 15%. See §1.3 |

### 9.1 Drop-rate tuning knobs

The element drop rates in §3.1 are constants in a new `utils/lab.py` module. Adjust to hit targets:

- **Time to first compound:** raise C, H, O base rates.
- **Halogenated compound time:** raise F, Br, I rates (or they'll always take 20–30 min).
- **6 h cap:** adjustable via `ELEMENT_FULL_RATE_MINUTES` in `config.py` or `utils/lab.py`.

---

## Appendix: Halloween Credit Hook Pattern (reference for Lab implementation)

The Halloween seasonal event used the exact pattern The Lab will use. From `database.py` `credit_progress()` (now commented out):

```python
# Roll for a surprise Hallo-Box drop while studying (~1 box every 15-20 min)
hallo_box_dropped = halloween_catalog.roll_study_hallo_box(new_minutes)
if hallo_box_dropped:
    await self.add_item(session["user_id"], session["guild_id"], hallo_box_dropped, 1)
# Roll for direct Candy drops earned while studying
candy_earned = halloween_catalog.roll_study_candy(new_minutes)
if candy_earned > 0:
    await self._add_candy_raw(session["user_id"], session["guild_id"], candy_earned)
```

The Lab's element drop hook slots in at exactly the same point:

```python
# Element drops (OC sessions only)
element_drops: dict[str, int] = {}
if session.get("track") == "oc" and config.LAB_EVENT:
    element_drops = await self._credit_lab_elements(
        session["user_id"], session["guild_id"],
        session_id, new_minutes, session.get("credited_elements"),
    )
```

Announced mid-session via `_announce_elements(credit)` → SSE `elements_dropped` event (§7.5).  
The git history for this pattern: `535b718 Hallo Event`, `f57345b Event announcement + drop rate tuning`, `52b3c8c feat(candyshop)`.
