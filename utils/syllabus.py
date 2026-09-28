"""Reference copy of the JEE Main syllabus (Physics / Chemistry /
Maths), used by `.syllabus` for browsing and by `.chapterdone` /
`.subtopicdone` (see cogs/progress.py) to validate what a user logs -
chapters can *only* be logged from this list, not free text.

This is a condensed, own-words study aid built from the current
(NTA's 2024-reduced syllabus, unchanged through the 2026 sessions)
syllabus structure - not a verbatim copy of the official NTA
document, and topic lists are trimmed to the highlights rather than
the full official wording. Chapter names themselves are the standard
ones used across every JEE textbook/coaching resource. Always check
the official NTA brochure (jeemain.nta.nic.in) for the authoritative,
definitive syllabus text.
"""
from __future__ import annotations

from typing import Any, Optional

# Each subject: an ordered list of chapters, in standard syllabus
# order. `topics` is a short, non-exhaustive list of highlights within
# that chapter - useful for `.subtopicdone`, not a complete index.
SYLLABUS: dict[str, list[dict[str, Any]]] = {
    "physics": [
        {"name": "Physics and Measurement", "topics": ["Units & dimensions", "Errors in measurement", "Dimensional analysis"]},
        {"name": "Kinematics", "topics": ["Motion in a straight line", "Relative velocity", "Projectile motion", "Circular motion"]},
        {"name": "Laws of Motion", "topics": ["Newton's laws", "Friction", "Circular motion dynamics", "Momentum & impulse"]},
        {"name": "Work, Energy and Power", "topics": ["Work-energy theorem", "Conservation of energy", "Collisions", "Power"]},
        {"name": "Rotational Motion", "topics": ["Centre of mass", "Moment of inertia", "Angular momentum", "Rolling motion"]},
        {"name": "Gravitation", "topics": ["Kepler's laws", "Gravitational potential", "Escape velocity", "Satellites"]},
        {"name": "Properties of Solids and Liquids", "topics": ["Elasticity", "Surface tension", "Viscosity", "Bernoulli's principle", "Heat transfer"]},
        {"name": "Thermodynamics", "topics": ["Laws of thermodynamics", "Heat engines", "Entropy", "Thermodynamic processes"]},
        {"name": "Kinetic Theory of Gases", "topics": ["Gas laws", "Kinetic energy of gases", "Degrees of freedom"]},
        {"name": "Oscillations and Waves", "topics": ["SHM", "Damped/forced oscillations", "Wave motion", "Sound waves", "Doppler effect"]},
        {"name": "Electrostatics", "topics": ["Coulomb's law", "Electric field & potential", "Capacitors", "Gauss's law"]},
        {"name": "Current Electricity", "topics": ["Ohm's law", "Circuits", "Kirchhoff's laws", "Wheatstone bridge"]},
        {"name": "Magnetic Effects of Current and Magnetism", "topics": ["Biot-Savart law", "Ampere's law", "Force on a current", "Magnetic materials"]},
        {"name": "Electromagnetic Induction and Alternating Currents", "topics": ["Faraday's law", "Lenz's law", "AC circuits", "Transformers"]},
        {"name": "Electromagnetic Waves", "topics": ["EM spectrum", "Properties of EM waves"]},
        {"name": "Optics", "topics": ["Reflection & refraction", "Lenses & mirrors", "Optical instruments", "Wave optics & interference"]},
        {"name": "Dual Nature of Matter and Radiation", "topics": ["Photoelectric effect", "de Broglie wavelength"]},
        {"name": "Atoms and Nuclei", "topics": ["Atomic models", "Radioactivity", "Nuclear binding energy"]},
        {"name": "Electronic Devices", "topics": ["Semiconductors", "Diodes", "Transistors", "Logic gates"]},
        {"name": "Experimental Skills", "topics": ["Vernier caliper & screw gauge", "Simple pendulum", "Ohm's law verification", "Common lab experiments"]},
    ],
    "chemistry": [
        {"name": "Some Basic Concepts in Chemistry", "topics": ["Mole concept", "Stoichiometry", "Equivalent concept"]},
        {"name": "Atomic Structure", "topics": ["Quantum numbers", "Electronic configuration", "Bohr model"]},
        {"name": "Chemical Bonding and Molecular Structure", "topics": ["Ionic/covalent bonding", "VSEPR theory", "Hybridization", "Molecular orbital theory"]},
        {"name": "Chemical Thermodynamics", "topics": ["Enthalpy", "Entropy", "Gibbs free energy", "Hess's law"]},
        {"name": "Solutions", "topics": ["Concentration terms", "Colligative properties", "Raoult's law"]},
        {"name": "Equilibrium", "topics": ["Chemical equilibrium", "Le Chatelier's principle", "Ionic equilibrium", "pH & buffers"]},
        {"name": "Redox Reactions and Electrochemistry", "topics": ["Oxidation numbers", "Electrochemical cells", "Nernst equation", "Conductance"]},
        {"name": "Chemical Kinetics", "topics": ["Rate laws", "Order & molecularity", "Arrhenius equation"]},
        {"name": "Classification of Elements and Periodicity", "topics": ["Periodic trends", "Periodic table structure"]},
        {"name": "p-Block Elements", "topics": ["Group 13-18 trends", "Important compounds"]},
        {"name": "d- and f-Block Elements", "topics": ["Transition metals", "Lanthanides & actinides"]},
        {"name": "Coordination Compounds", "topics": ["Nomenclature", "Bonding theories", "Isomerism"]},
        {"name": "Purification and Characterisation of Organic Compounds", "topics": ["Purification techniques", "Qualitative/quantitative analysis"]},
        {"name": "Some Basic Principles of Organic Chemistry", "topics": ["Nomenclature", "Isomerism", "Reaction mechanisms", "Inductive/resonance effects"]},
        {"name": "Hydrocarbons", "topics": ["Alkanes/alkenes/alkynes", "Aromatic hydrocarbons"]},
        {"name": "Organic Compounds Containing Halogens", "topics": ["Nomenclature", "Reactions"]},
        {"name": "Organic Compounds Containing Oxygen", "topics": ["Alcohols/phenols/ethers", "Aldehydes/ketones", "Carboxylic acids"]},
        {"name": "Organic Compounds Containing Nitrogen", "topics": ["Amines", "Diazonium salts"]},
        {"name": "Biomolecules", "topics": ["Carbohydrates", "Proteins", "Nucleic acids", "Vitamins"]},
        {"name": "Practical Chemistry", "topics": ["Salt analysis", "Titrations", "Chemistry involved in common experiments"]},
    ],
    "maths": [
        {"name": "Sets, Relations and Functions", "topics": ["Set operations", "Types of relations", "Types of functions"]},
        {"name": "Complex Numbers and Quadratic Equations", "topics": ["Algebra of complex numbers", "Argand plane", "Quadratic roots"]},
        {"name": "Matrices and Determinants", "topics": ["Matrix operations", "Determinants", "Inverse of a matrix", "Solving linear systems"]},
        {"name": "Permutations and Combinations", "topics": ["Fundamental counting principle", "Permutations", "Combinations"]},
        {"name": "Binomial Theorem", "topics": ["General term", "Middle term", "Properties of coefficients"]},
        {"name": "Sequences and Series", "topics": ["AP & GP", "Special series", "Sum to n terms"]},
        {"name": "Limits, Continuity and Differentiability", "topics": ["Limits", "Continuity", "Differentiability", "Derivatives"]},
        {"name": "Integral Calculus", "topics": ["Indefinite integrals", "Definite integrals", "Area under curves"]},
        {"name": "Differential Equations", "topics": ["Order & degree", "Formation", "Solving first-order equations"]},
        {"name": "Coordinate Geometry", "topics": ["Straight lines", "Circles", "Parabola/ellipse/hyperbola"]},
        {"name": "Three Dimensional Geometry", "topics": ["Direction cosines/ratios", "Lines & planes in space"]},
        {"name": "Vector Algebra", "topics": ["Vector operations", "Dot & cross product", "Scalar triple product"]},
        {"name": "Statistics and Probability", "topics": ["Mean/variance", "Probability theory", "Bayes' theorem"]},
        {"name": "Trigonometry", "topics": ["Identities", "Trigonometric equations", "Inverse trig functions", "Heights & distances"]},
    ],
}


def get_chapters(subject: str) -> list[dict[str, Any]]:
    return SYLLABUS.get(subject, [])


def find_chapter(subject: str, query: str) -> Optional[dict[str, Any]]:
    """Match a chapter within `subject` by 1-based number, exact name,
    or a substring of the name. Returns the chapter dict plus a
    'number' key, or None if nothing matches."""
    chapters = SYLLABUS.get(subject, [])
    query = query.strip()

    if query.isdigit():
        idx = int(query) - 1
        if 0 <= idx < len(chapters):
            return {**chapters[idx], "number": idx + 1}
        return None

    query_lower = query.lower()
    for i, ch in enumerate(chapters):
        if query_lower == ch["name"].lower():
            return {**ch, "number": i + 1}
    for i, ch in enumerate(chapters):
        if query_lower in ch["name"].lower():
            return {**ch, "number": i + 1}
    return None


def find_subtopic(chapter: dict[str, Any], query: str) -> Optional[str]:
    """Match a subtopic within an already-resolved chapter dict (from
    find_chapter) by 1-based number, exact name, or substring."""
    topics = chapter.get("topics", [])
    query = query.strip()

    if query.isdigit():
        idx = int(query) - 1
        if 0 <= idx < len(topics):
            return topics[idx]
        return None

    query_lower = query.lower()
    for t in topics:
        if query_lower == t.lower():
            return t
    for t in topics:
        if query_lower in t.lower():
            return t
    return None
