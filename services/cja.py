"""Client service for CJA (Chronos JEE API).

Handles all HTTP communication with the CJA backend:
- `get_question(params)` with 30s timeout and automatic retry on GENERATION_FAILED
- `check_answer(question_id, answer)` to verify user answers against official marking
- `autocomplete(params)` with 2.5s timeout for chapter/topic lookups

Keeps CJA_KEY private and never leaks secrets to logs or messages.
Includes offline verified question fallbacks when CJA_URL is unconfigured.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import aiohttp

import config

log = logging.getLogger("cja")

# Fallback pool when CJA_URL / CJA_KEY is not configured or network unreachable
OFFLINE_QUESTION_POOL: list[dict[str, Any]] = [
    {
        "id": "offline_chem_coord_01",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "chemistry", "name": "Chemistry"},
        "chapter": {"id": "coordination-compounds", "name": "Coordination Compounds", "section": "Inorganic Chemistry"},
        "topic": {"id": "cft", "name": "Crystal Field Theory & Magnetic Nature"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "medium",
        "question": "Which of the following complex ions is diamagnetic and forms an inner orbital octahedral complex?",
        "options": [
            {"key": "A", "text": "[Fe(CN)₆]⁴⁻"},
            {"key": "B", "text": "[CoF₆]³⁻"},
            {"key": "C", "text": "[Ni(NH₃)₆]²⁺"},
            {"key": "D", "text": "[Fe(H₂O)₆]²⁺"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["A"], "integer": None, "display": "A"},
            "explanation": "In [Fe(CN)₆]⁴⁻, Fe is in the +2 state (d⁶). CN⁻ is a strong field ligand causing pairing of electrons into t₂g⁶ e_g⁰. This results in d²sp³ inner orbital hybridization with zero unpaired electrons (diamagnetic).",
            "concept": "Crystal Field Splitting & Ligand Field Strength (Spectrochemical Series)",
        },
    },
    {
        "id": "offline_chem_organic_02",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "chemistry", "name": "Chemistry"},
        "chapter": {"id": "amines", "name": "Amines & Nitrogen Compounds", "section": "Organic Chemistry"},
        "topic": {"id": "hinsberg", "name": "Hinsberg Reagent Test"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "easy",
        "question": "An organic compound reacts with benzene sulfonyl chloride (Hinsberg's reagent) to form a precipitate that is completely soluble in aqueous KOH. The compound is a:",
        "options": [
            {"key": "A", "text": "Primary (1°) amine"},
            {"key": "B", "text": "Secondary (2°) amine"},
            {"key": "C", "text": "Tertiary (3°) amine"},
            {"key": "D", "text": "Quaternary ammonium salt"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["A"], "integer": None, "display": "A"},
            "explanation": "Primary amines react with benzene sulfonyl chloride to yield N-alkyl benzene sulfonamide, which contains an acidic hydrogen attached to nitrogen. This acidic proton allows it to dissolve readily in aqueous KOH.",
            "concept": "Differentiation of 1°, 2°, and 3° Amines via Hinsberg Reagent",
        },
    },
    {
        "id": "offline_phys_modern_03",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "physics", "name": "Physics"},
        "chapter": {"id": "dual-nature", "name": "Dual Nature of Matter & Radiation", "section": "Modern Physics"},
        "topic": {"id": "photoelectric", "name": "Photoelectric Effect Stopping Potential"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "medium",
        "question": "In a photoelectric experiment, if the intensity of incident monochromatic light is doubled while keeping its frequency constant above the threshold, which of the following quantities doubles?",
        "options": [
            {"key": "A", "text": "Maximum kinetic energy of photoelectrons"},
            {"key": "B", "text": "Stopping potential (V₀)"},
            {"key": "C", "text": "Saturation photocurrent"},
            {"key": "D", "text": "Threshold wavelength (λ₀)"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["C"], "integer": None, "display": "C"},
            "explanation": "Photocurrent is directly proportional to the number of incident photons per second (intensity). Stopping potential and max kinetic energy depend strictly on the frequency of incident radiation, not on intensity.",
            "concept": "Einstein's Photoelectric Equation: eV₀ = hν - Φ",
        },
    },
    {
        "id": "offline_phys_semi_04",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "physics", "name": "Physics"},
        "chapter": {"id": "semiconductors", "name": "Semiconductor Electronics", "section": "Modern Physics"},
        "topic": {"id": "zener-diode", "name": "Zener Diode Voltage Regulation"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "easy",
        "question": "A Zener diode is primarily designed to operate in which of the following biasing conditions for voltage regulation?",
        "options": [
            {"key": "A", "text": "Forward bias above the knee voltage"},
            {"key": "B", "text": "Reverse bias in the breakdown region"},
            {"key": "C", "text": "Zero bias with thermal equilibrium"},
            {"key": "D", "text": "Forward bias in the diffusion region"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["B"], "integer": None, "display": "B"},
            "explanation": "Zener diodes are heavily doped p-n junctions designed to operate stably in the reverse breakdown region, where the voltage across the diode remains practically constant over a wide range of reverse currents.",
            "concept": "Zener Breakdown & Voltage Stabilization",
        },
    },
    {
        "id": "offline_math_conics_05",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "mathematics", "name": "Mathematics"},
        "chapter": {"id": "hyperbola", "name": "Conic Sections: Hyperbola", "section": "Coordinate Geometry"},
        "topic": {"id": "director-circle", "name": "Director Circle Properties"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "medium",
        "question": "The locus of the point of intersection of perpendicular tangents to the rectangular hyperbola x² - y² = a² is:",
        "options": [
            {"key": "A", "text": "A circle of radius a√2"},
            {"key": "B", "text": "The point circle at the origin (x² + y² = 0)"},
            {"key": "C", "text": "An ellipse of eccentricity 1/√2"},
            {"key": "D", "text": "The director circle does not exist (imaginary locus)"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["B"], "integer": None, "display": "B"},
            "explanation": "For hyperbola x²/a² - y²/b² = 1, the director circle is x² + y² = a² - b². In a rectangular hyperbola where a = b, this becomes x² + y² = 0, which represents the point circle (origin).",
            "concept": "Director Circle of Conic Sections & Rectangular Hyperbola",
        },
    },
    {
        "id": "offline_math_matrices_06",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "mathematics", "name": "Mathematics"},
        "chapter": {"id": "matrices-determinants", "name": "Matrices & Determinants", "section": "Algebra"},
        "topic": {"id": "orthogonal", "name": "Orthogonal & Involutary Matrix Properties"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "easy",
        "question": "If A is a real orthogonal matrix of order 3, which of the following is strictly guaranteed regarding its determinant |A|?",
        "options": [
            {"key": "A", "text": "|A| = 0"},
            {"key": "B", "text": "|A| = 1 or -1"},
            {"key": "C", "text": "|A| must be strictly positive (|A| > 0)"},
            {"key": "D", "text": "|A| equals the trace of matrix A"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["B"], "integer": None, "display": "B"},
            "explanation": "By definition of an orthogonal matrix, A · Aᵀ = I. Taking the determinant of both sides: |A| · |Aᵀ| = |I| => |A|² = 1 => |A| = ±1.",
            "concept": "Orthogonal Matrices: Properties of Determinant and Transpose",
        },
    },
    {
        "id": "offline_phys_optics_07",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "physics", "name": "Physics"},
        "chapter": {"id": "wave-optics", "name": "Wave Optics", "section": "Optics"},
        "topic": {"id": "brewsters-law", "name": "Polarization by Reflection (Brewster's Law)"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "medium",
        "question": "When unpolarized light is incident on a transparent dielectric medium at the polarizing angle (Brewster's angle θ_p), which of the following statements is strictly true?",
        "options": [
            {"key": "A", "text": "The reflected and refracted rays are parallel to each other"},
            {"key": "B", "text": "The reflected and refracted rays are mutually perpendicular (angle = 90°)"},
            {"key": "C", "text": "The refracted ray is 100% completely linearly polarized"},
            {"key": "D", "text": "No light enters the refracting medium (total internal reflection)"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["B"], "integer": None, "display": "B"},
            "explanation": "According to Brewster's law, at the polarizing angle of incidence θ_p, the reflected ray is completely linearly polarized with vibrations perpendicular to the plane of incidence, and the reflected and refracted rays are at right angles (θ_p + r = 90°).",
            "concept": "Brewster's Law: tan(θ_p) = μ and Perpendicular Rays",
        },
    },
    {
        "id": "offline_chem_salt_08",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "chemistry", "name": "Chemistry"},
        "chapter": {"id": "qualitative-analysis", "name": "Qualitative Salt Analysis", "section": "Inorganic Chemistry"},
        "topic": {"id": "brown-ring", "name": "Brown Ring Test for Nitrate Ion"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "hard",
        "question": "In the brown ring test for the detection of nitrate (NO₃⁻) ion, what is the chemical formula and oxidation state of iron in the brown ring complex?",
        "options": [
            {"key": "A", "text": "[Fe(H₂O)₅(NO)]²⁺ with Fe in +1 oxidation state"},
            {"key": "B", "text": "[Fe(H₂O)₅(NO₂)]³⁺ with Fe in +3 oxidation state"},
            {"key": "C", "text": "[Fe(H₂O)₄(NO)₂]²⁺ with Fe in +2 oxidation state"},
            {"key": "D", "text": "[Fe(NO)₆]³⁺ with Fe in +3 oxidation state"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["A"], "integer": None, "display": "A"},
            "explanation": "The brown ring is formed by the pentaaquanitrosyliron(I) complex [Fe(H₂O)₅(NO)]²⁺. Nitric oxide acts as NO⁺, transferring an electron to Fe²⁺ to yield Fe⁺ (+1 state) with 3 unpaired electrons (magnetic moment ~ 3.87 BM).",
            "concept": "Brown Ring Complex: [Fe(H₂O)₅(NO)]SO₄ and Fe(I) State",
        },
    },
    {
        "id": "offline_math_calculus_09",
        "exam": {"id": "main", "name": "JEE Main"},
        "subject": {"id": "mathematics", "name": "Mathematics"},
        "chapter": {"id": "definite-integrals", "name": "Definite Integrals", "section": "Calculus"},
        "topic": {"id": "kings-rule", "name": "King's Property of Definite Integrals"},
        "type": {"id": "single", "name": "Single Correct", "instructions": "Choose the one correct option."},
        "difficulty": "medium",
        "question": "What is the value of the definite integral ∫₀^(π/2) [sin³(x) / (sin³(x) + cos³(x))] dx?",
        "options": [
            {"key": "A", "text": "π"},
            {"key": "B", "text": "π/2"},
            {"key": "C", "text": "π/4"},
            {"key": "D", "text": "0"},
        ],
        "verified": True,
        "_answer": {
            "result": "correct",
            "correct": True,
            "marks": 4,
            "marking": {"correct": 4, "incorrect": -1},
            "answer": {"options": ["C"], "integer": None, "display": "C"},
            "explanation": "Applying King's property ∫ₐᵇ f(x) dx = ∫ₐᵇ f(a+b-x) dx: Replace x with (π/2 - x) to get I = ∫₀^(π/2) [cos³(x) / (cos³(x) + sin³(x))] dx. Adding the two integrals gives 2I = ∫₀^(π/2) 1 dx = π/2 => I = π/4.",
            "concept": "King's Property: ∫₀ᵃ f(x) dx = ∫₀ᵃ f(a-x) dx",
        },
    },
]

# In-memory store for offline question answers
_OFFLINE_ANSWERS: dict[str, dict[str, Any]] = {q["id"]: q["_answer"] for q in OFFLINE_QUESTION_POOL}


class CJAError(Exception):
    """Base exception for CJA API errors."""
    def __init__(self, code: str, message: str, suggestions: Optional[list[str]] = None, retry_after: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestions = suggestions or []
        self.retry_after = retry_after


class CJAService:
    """Async client for CJA endpoints."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base_url(self) -> str:
        return config.CJA_URL

    @property
    def api_key(self) -> str:
        return config.CJA_KEY

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self, require_auth: bool = True) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if require_auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------ #
    # 1. GET /api/v1/question
    # ------------------------------------------------------------------ #
    async def get_question(
        self,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
        topic: Optional[str] = None,
        exam: Optional[str] = None,
        q_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        hide_answer: bool = True,
        embed: bool = True,
    ) -> dict[str, Any]:
        """Fetch a trivia question from CJA with 30s timeout and automatic retry on GENERATION_FAILED."""
        # Fallback to local verified pool if CJA is unconfigured
        if not self.base_url:
            return self._get_offline_question(subject)

        params: dict[str, Any] = {"hideAnswer": "true" if hide_answer else "false"}
        if embed:
            params["embed"] = "true"
        if subject:
            params["subject"] = subject.lower()
        if chapter:
            params["chapter"] = chapter
        if topic:
            params["topic"] = topic
        if exam:
            params["exam"] = exam.lower()
        if q_type:
            params["type"] = q_type
        if difficulty:
            params["difficulty"] = difficulty.lower()

        url = f"{self.base_url}/api/v1/question"
        headers = self._headers(require_auth=True)
        timeout = aiohttp.ClientTimeout(total=30)

        for attempt in range(2):
            try:
                session = await self._get_session()
                async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                    payload = await resp.json()
                    if payload.get("ok"):
                        return payload["data"]

                    err = payload.get("error", {})
                    code = err.get("code", "UNKNOWN_ERROR")
                    msg = err.get("message", "An error occurred fetching the question.")
                    sugg = err.get("suggestions", [])
                    retry_after = err.get("retryAfterSeconds", 0)

                    # Retry once automatically on GENERATION_FAILED, then fallback
                    if code == "GENERATION_FAILED":
                        if attempt == 0:
                            log.warning("CJA generation failed, retrying once...")
                            await asyncio.sleep(1)
                            continue
                        log.warning("CJA generation failed twice; using verified question fallback.")
                        return self._get_offline_question(subject)

                    raise CJAError(code=code, message=msg, suggestions=sugg, retry_after=retry_after)

            except aiohttp.ClientConnectorError as e:
                log.warning(f"Could not connect to CJA ({e}); using offline question fallback.")
                return self._get_offline_question(subject)
            except asyncio.TimeoutError:
                if attempt == 0:
                    log.warning("CJA request timed out; retrying once...")
                    await asyncio.sleep(1)
                    continue
                log.warning("CJA request timed out twice; falling back to offline question pool.")
                return self._get_offline_question(subject)
            except CJAError:
                raise
            except Exception as e:
                log.error(f"Unexpected error in get_question: {e}", exc_info=True)
                return self._get_offline_question(subject)

        return self._get_offline_question(subject)

    # ------------------------------------------------------------------ #
    # 2. POST /api/v1/question/:id/check
    # ------------------------------------------------------------------ #
    async def check_answer(self, question_id: str, answer: str | int) -> dict[str, Any]:
        """Verify the user's submitted answer with CJA."""
        # Handle offline pool answers
        if question_id in _OFFLINE_ANSWERS:
            off_ans = _OFFLINE_ANSWERS[question_id]
            is_correct = str(answer).strip().upper() in off_ans["answer"]["options"]
            return {
                "result": "correct" if is_correct else "incorrect",
                "correct": is_correct,
                "marks": off_ans["marks"] if is_correct else off_ans["marking"]["incorrect"],
                "marking": off_ans["marking"],
                "answer": off_ans["answer"],
                "explanation": off_ans["explanation"],
                "concept": off_ans["concept"],
            }

        if not self.base_url:
            raise CJAError("UNCONFIGURED", "CJA_URL is not set and question was not found in offline cache.")

        url = f"{self.base_url}/api/v1/question/{question_id}/check"
        headers = self._headers(require_auth=True)
        timeout = aiohttp.ClientTimeout(total=30)
        body = {"answer": answer}

        try:
            session = await self._get_session()
            async with session.post(url, json=body, headers=headers, timeout=timeout) as resp:
                payload = await resp.json()
                if payload.get("ok"):
                    return payload["data"]

                err = payload.get("error", {})
                code = err.get("code", "UNKNOWN_ERROR")
                msg = err.get("message", "Could not check answer.")
                raise CJAError(code=code, message=msg)
        except asyncio.TimeoutError:
            raise CJAError("TIMEOUT", "Verification timed out with the grading server.")
        except CJAError:
            raise
        except Exception as e:
            log.error(f"Error checking answer on CJA: {e}", exc_info=True)
            raise CJAError("NETWORK_ERROR", "Could not connect to grading server.")

    # ------------------------------------------------------------------ #
    # 3. GET /api/v1/autocomplete
    # ------------------------------------------------------------------ #
    async def autocomplete(
        self,
        field: str,
        query: str = "",
        subject: Optional[str] = None,
        exam: Optional[str] = None,
        chapter: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """Autocomplete helper for chapter and topic selection with 2.5s timeout."""
        if not self.base_url:
            return self._offline_autocomplete(field, subject)

        params: dict[str, Any] = {"field": field, "q": query}
        if subject:
            params["subject"] = subject.lower()
        if exam:
            params["exam"] = exam.lower()
        if chapter:
            params["chapter"] = chapter

        url = f"{self.base_url}/api/v1/autocomplete"
        headers = self._headers(require_auth=False)
        timeout = aiohttp.ClientTimeout(total=2.5)

        try:
            session = await self._get_session()
            async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                payload = await resp.json()
                if payload.get("ok"):
                    return payload["data"].get("choices", [])
                return []
        except Exception:
            return self._offline_autocomplete(field, subject)

    # ------------------------------------------------------------------ #
    # Offline fallbacks & helpers
    # ------------------------------------------------------------------ #
    def _get_offline_question(self, subject: Optional[str] = None) -> dict[str, Any]:
        """Return a random question matching the subject filter from the offline pool."""
        import random
        pool = OFFLINE_QUESTION_POOL
        if subject:
            filtered = [q for q in pool if q["subject"]["id"].lower() == subject.lower() or subject.lower() in q["subject"]["id"].lower()]
            if filtered:
                pool = filtered
        q = random.choice(pool).copy()
        # Ensure answer is hidden
        q.pop("_answer", None)
        return q

    def _offline_autocomplete(self, field: str, subject: Optional[str] = None) -> list[dict[str, str]]:
        """Static offline chapter/topic choices."""
        if field == "chapter":
            if subject == "physics":
                return [
                    {"name": "Electrostatics & Gauss's Law", "value": "electrostatics"},
                    {"name": "Current Electricity", "value": "current-electricity"},
                    {"name": "Electromagnetic Induction (EMI)", "value": "emi"},
                    {"name": "Optics (Wave & Ray)", "value": "optics"},
                    {"name": "Modern Physics (Photoelectric & Nuclei)", "value": "modern-physics"},
                    {"name": "Semiconductors & Logic Gates", "value": "semiconductors"},
                    {"name": "Thermodynamics & Heat", "value": "thermodynamics"},
                ]
            elif subject == "chemistry":
                return [
                    {"name": "Coordination Compounds", "value": "coordination-compounds"},
                    {"name": "General Organic Chemistry (GOC)", "value": "goc"},
                    {"name": "Chemical Bonding & VSEPR", "value": "chemical-bonding"},
                    {"name": "p-Block & d-Block Elements", "value": "p-block"},
                    {"name": "Amines & Diazonium Salts", "value": "amines"},
                    {"name": "Chemical Kinetics", "value": "chemical-kinetics"},
                    {"name": "Aldehydes, Ketones & Carboxylic Acids", "value": "aldehydes-ketones"},
                ]
            elif subject == "mathematics":
                return [
                    {"name": "Calculus: Definite Integrals", "value": "definite-integrals"},
                    {"name": "Vectors & 3D Geometry", "value": "vectors-3d"},
                    {"name": "Matrices & Determinants", "value": "matrices-determinants"},
                    {"name": "Conic Sections (Parabola, Ellipse, Hyperbola)", "value": "conic-sections"},
                    {"name": "Complex Numbers", "value": "complex-numbers"},
                    {"name": "Probability & Statistics", "value": "probability"},
                ]
        return []


# Global singleton client instance
cja_client = CJAService()
