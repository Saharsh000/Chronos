"""Bespoke JEE-themed lore scenarios for the `.beg` command.

100% English, razor-sharp academic satire, zero generic fillers,
featuring iconic JEE authors, textbook legends, renowned professors,
exam invigilators, and competitive exam lore.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Optional

# Maximum number of recent scenarios remembered per user to prevent repeats
HISTORY_CAPACITY = 25
_USER_HISTORY: dict[int, deque[str]] = {}


@dataclass(frozen=True)
class BegScenario:
    id: str
    npc: str
    role: str
    title: str
    story: str
    emoji: str
    is_success: bool
    quote: Optional[str] = None


# --------------------------------------------------------------------- #
# SUCCESS SCENARIOS (40+ unique characters & storylines)
# --------------------------------------------------------------------- #
SUCCESS_SCENARIOS: list[BegScenario] = [
    # --- Classic Physics Legends ---
    BegScenario(
        id="hcv_pulley",
        npc="Prof. H.C. Verma",
        role="Author of Concepts of Physics",
        title="Ideal Pulley Equilibrium",
        story="You approached Prof. H.C. Verma outside his lecture hall. He studied your posture, sketched a monkey of mass m ascending a massless rope on a frictionless pulley, and muttered: 'Fortunately for you, today the friction between your palm and my wallet is non-zero.'",
        quote="Never approximate g as 10 m/s² unless explicitly commanded.",
        emoji="🐒",
        is_success=True,
    ),
    BegScenario(
        id="irodov_helical",
        npc="I.E. Irodov",
        role="Author of Problems in General Physics",
        title="Siberian Compassion",
        story="You knocked on I.E. Irodov's frost-covered study door. He peered over his wire-rimmed spectacles and said: 'Derive the magnetic flux through a superconducting loop in four steps.' You swiftly wrote Faraday's law. In a historic display of Russian warmth, he conceded a stipend.",
        quote="The remaining debt is left as an exercise for the reader.",
        emoji="❄️",
        is_success=True,
    ),
    BegScenario(
        id="dc_pandey_mechanics",
        npc="D.C. Pandey",
        role="Architect of Understanding Physics",
        title="Level 3 Objective Clearance",
        story="You bumped into D.C. Pandey at a book fair. He flipped open his Mechanics Vol. 2 and pointed to an archer on an accelerating flatcar. You instantly picked option (c). He grinned, signed your rough sheet, and slipped you a crisp stipend.",
        quote="Always draw the free-body diagram before asking for charity.",
        emoji="🏹",
        is_success=True,
    ),
    BegScenario(
        id="krotov_mercy",
        npc="Prof. S.S. Krotov",
        role="Russian Olympiad Mastermind",
        title="Aptitude in Generosity",
        story="Prof. Krotov handed you a problem involving a charged cylinder oscillating inside a plasma stream. Seeing the profound exhaustion etched onto your face, he closed the manuscript with a sigh and rewarded your sheer courage.",
        quote="Theoretical survival deserves empirical compensation.",
        emoji="⚡",
        is_success=True,
    ),
    BegScenario(
        id="halliday_resnick",
        npc="Halliday & Resnick",
        role="Fundamentals of Physics Co-Authors",
        title="Rigid Body Rotation Grant",
        story="The legendary duo watched you struggle to compute the rotational inertia of a hollow sphere. 'Look at the symmetry of the integral!' they exclaimed together, handing you a research endowment.",
        quote="Energy is conserved, and today, so is your budget.",
        emoji="🪐",
        is_success=True,
    ),
    BegScenario(
        id="bm_sharma_cengage",
        npc="B.M. Sharma",
        role="Author of Cengage Physics Series",
        title="Six-Volume Cargo Bonus",
        story="You assisted B.M. Sharma in transporting all six volumes of Cengage Physics up three flights of stairs. Drenched in sweat under 22 kilograms of illustrations, you were generously tipped for saving his spinal cord.",
        quote="Volume 1: Mechanics. Volume 2: Waves. Volume 3: Your reward.",
        emoji="📚",
        is_success=True,
    ),

    # --- Chemistry Pioneers ---
    BegScenario(
        id="jd_lee_inert_pair",
        npc="J.D. Lee",
        role="Author of Concise Inorganic Chemistry",
        title="Inert Pair Dividends",
        story="You found J.D. Lee pacing in the library archives. 'Why is Lead(II) more stable than Lead(IV)?' he interrogated. You answered without flinching: 'Relativistic inert pair effect!' His eyes lit up like a strontium flame test as he tossed you a reward.",
        quote="Never disrespect the poor shielding of 4f and 5d orbitals.",
        emoji="🧪",
        is_success=True,
    ),
    BegScenario(
        id="ms_chouhan_grignard",
        npc="M.S. Chouhan (MSC Sir)",
        role="Advanced Organic Chemistry Master",
        title="Grignard Reagent Bounty",
        story="M.S. Chouhan stopped you in the coaching corridor. 'Dry ether medium! Carbonyl attack! Nucleophile ready!' You identified the tertiary alcohol product instantly. He slammed his hand on the desk in delight and paid you out.",
        quote="Mechanism intact. Target achieved.",
        emoji="🧬",
        is_success=True,
    ),
    BegScenario(
        id="morrison_boyd_resonance",
        npc="Morrison & Boyd",
        role="Organic Chemistry Authorities",
        title="Resonance Stabilization Grant",
        story="The authors inspected your reaction coordinate diagram. 'Notice how the carbocation rearranges into a resonance-stabilized allylic intermediate,' they observed gently, funding your academic survival.",
        quote="Structure dictates function; dedication dictates reward.",
        emoji="🔬",
        is_success=True,
    ),
    BegScenario(
        id="op_tandon_equilibrium",
        npc="O.P. Tandon",
        role="Physical Chemistry Authority",
        title="Le Chatelier's Shift",
        story="O.P. Tandon calculated your financial deficit on a sheet of graph paper. 'Applying stress to your wallet will predictably shift the system toward equilibrium,' he noted, transferring compensatory funds.",
        quote="Equilibrium constant remains constant; student capital increases.",
        emoji="⚖️",
        is_success=True,
    ),
    BegScenario(
        id="rc_mukherjee_stoichiometry",
        npc="R.C. Mukherjee",
        role="Author of Modern Chemical Calculations",
        title="Exact Equivalent Weight",
        story="R.C. Mukherjee scrutinized your mole concept calculations. You accurately accounted for the n-factor of Potassium Dichromate in acidic medium. Nodding with methodical satisfaction, he handed over your dues.",
        quote="Equivalent weight equals molecular weight divided by six. Flawless.",
        emoji="⚗️",
        is_success=True,
    ),
    BegScenario(
        id="n_awasthi_thermo",
        npc="N. Awasthi",
        role="Problems in Physical Chemistry Author",
        title="Reversible Work Done",
        story="N. Awasthi watched you integrate -nRT ln(V2/V1) for an isothermal reversible expansion. 'Maximum work obtained!' he congratulated you, handing over the proceeds.",
        quote="Entropy of the universe increased, but your coins did too.",
        emoji="🔥",
        is_success=True,
    ),
    BegScenario(
        id="himanshu_pandey_aromaticity",
        npc="Himanshu Pandey",
        role="GRB Organic Chemistry Creator",
        title="Hückel's Rule Approval",
        story="Himanshu Pandey demanded to know if the cyclopropenyl cation was aromatic. You yelled: '4n+2 where n=0, completely aromatic!' He grinned and handed you an immediate honorarium.",
        quote="Two pi electrons of pure aromatic stability.",
        emoji="💍",
        is_success=True,
    ),

    # --- Mathematics Architects ---
    BegScenario(
        id="sl_loney_trig",
        npc="S.L. Loney",
        role="Author of Coordinate Geometry (1893)",
        title="Victorian Hyperbola Protocol",
        story="A distinguished Victorian gentleman from Cambridge materialized holding an antique fountain pen. 'Young scholar, let the orthogonal tangents of thy hyperbola intersect upon the director circle!' In honor of classical rigor, he gifted you a historic treasury.",
        quote="Geometry is the poetry of space and reason.",
        emoji="📐",
        is_success=True,
    ),
    BegScenario(
        id="vikas_gupta_blackbook",
        npc="Vikas Gupta (The Black Book Author)",
        role="Advanced Mathematics Authority",
        title="Improper Integral Mastery",
        story="The author of the feared Advanced Math Black Book challenged you to evaluate a continuous fractional-part definite integral in under 30 seconds. You evaluated it without substitution. Impressed, he stamped your work with an AIR 50 endorsement and paid you.",
        quote="Calculus is not difficult; candidates are simply undisciplined.",
        emoji="📖",
        is_success=True,
    ),
    BegScenario(
        id="amit_agarwal_vectors",
        npc="Amit M. Agarwal",
        role="Arihant Mathematics Architect",
        title="Scalar Triple Product Clearance",
        story="Amit M. Agarwal placed three non-coplanar vectors before you. You showed that their scalar triple product represented the exact volume of the parallelepiped. He praised your spatial intuition and handed over a cash prize.",
        quote="Coplanarity rejected; prosperity accepted.",
        emoji="📏",
        is_success=True,
    ),
    BegScenario(
        id="ia_maron_calculus",
        npc="I.A. Maron",
        role="Author of Problems in Calculus",
        title="L'Hôpital's Resolution",
        story="I.A. Maron watched your limit evaluation hit an indeterminate 0/0 form. You applied L'Hôpital's rule twice and determined the finite limit. He smiled warmly through his trench coat and dropped a pouch of coins.",
        quote="Continuous and differentiable throughout its entire domain.",
        emoji="📈",
        is_success=True,
    ),

    # --- Coaching Luminaries & Academic Staff ---
    BegScenario(
        id="whiteboard_lecturer",
        npc="The Legendary Online Physics Mentor",
        role="Revolutionary Digital Educator",
        title="Whiteboard Passion Payout",
        story="The internet's favorite physics teacher slammed his marker on the whiteboard and roared: 'Work hard in silence, let your rank make the noise!' Feeling your unyielding dedication through the screen, he transferred emergency study aid.",
        quote="Every drop of sweat invested today returns compound interest tomorrow.",
        emoji="🖥️",
        is_success=True,
    ),
    BegScenario(
        id="kota_director_desk",
        npc="The Coaching Institute Director",
        role="Managing 10,000 Aspirants",
        title="Scholarship Discretionary Fund",
        story="You walked straight into the Director's corner office. Seeing your worn-out highlighter and bloodshot eyes, he approved an instant discretionary grant. 'Keep your head down and get that top-hundred rank.'",
        quote="We do not build billboards; we build selections.",
        emoji="🏢",
        is_success=True,
    ),
    BegScenario(
        id="dummy_school_registrar",
        npc="The Dummy School Registrar",
        role="Attendance Certificate Wizard",
        title="Perfect Attendance Protocol",
        story="The registrar stamped '75% Mandatory Attendance Satisfied' without even looking up from his cup of tea. He slipped a stipend into your admit card sleeve and gave you a conspiratorial nod.",
        quote="Officially, you were here every single morning.",
        emoji="📋",
        is_success=True,
    ),
    BegScenario(
        id="library_night_custodian",
        npc="The Reading Hall Custodian",
        role="Silent Watcher of the Stacks",
        title="Midnight Cleaners' Pity",
        story="At 3:15 AM, the custodian vacuuming between the physics reference stacks found you asleep on a volume of Inorganic Chemistry. Instead of waking you, he tucked a small coin envelope under your keyboard.",
        quote="I have seen five hundred toppers; they all slept like that.",
        emoji="🧹",
        is_success=True,
    ),
    BegScenario(
        id="senior_iitian_mentor",
        npc="The 4th-Year IITian",
        role="Campus Placement Survivor",
        title="Senior Year Empathy",
        story="A final-year engineering senior on holiday walked past your desk. Recognizing the same haunted look he had four years ago, he chuckled softly and bought you a full lunch and a generous stipend.",
        quote="It gets better after the counseling round. Hold the line.",
        emoji="🎓",
        is_success=True,
    ),

    # --- Peer & Environment Lore ---
    BegScenario(
        id="shift1_veteran",
        npc="The 27th Jan Shift 1 Survivor",
        role="Normalized Percentile Martyr",
        title="Trauma Solidarity",
        story="You found a veteran candidate staring into the distance outside the testing center. 'I scored 220 marks and received a 98.4 percentile,' he whispered calmly. Recognizing a fellow fighter in the trenches, he shared his remaining canteen balance.",
        quote="We bear the scars of the bell curve together.",
        emoji="🪦",
        is_success=True,
    ),
    BegScenario(
        id="mock_hall_topper",
        npc="The All-India Mock Topper",
        role="Completed the Exam in 40 Minutes",
        title="Coins from the Clouds",
        story="The genius who scored 295/300 in Sunday's national mock woke up from his scheduled desk nap. Seeing your eraser worn down to the nub, he flicked a coin pouch toward you like it was negligible loose change.",
        quote="I will not be needing these where I am going.",
        emoji="👑",
        is_success=True,
    ),
    BegScenario(
        id="third_year_dropper",
        npc="The Multi-Year Aspirant",
        role="Walking Archive of Every PYQ",
        title="Archival Generosity",
        story="A candidate who has attempted every single JEE paper from 1982 to 2024 took pity on you. He identified the year and question number of the problem on your desk from three meters away and rewarded your hustle.",
        quote="Question 14, 2016 Paper 1, Multiple Correct. Here is your coin.",
        emoji="⏳",
        is_success=True,
    ),
    BegScenario(
        id="roommate_who_cracked_adv",
        npc="The Former Desk Partner",
        role="Currently in Department of Computer Science",
        title="The Alumni Transfer",
        story="Your former hostel desk partner dropped by for a weekend visit with brand-new noise-canceling headphones. Remembering your countless 4 AM problem-solving sessions, he wire-transferred a generous allowance.",
        quote="Your turn next year. Don't let the momentum slip.",
        emoji="💻",
        is_success=True,
    ),
    BegScenario(
        id="david_morin_limerick",
        npc="David Morin",
        role="Author of Classical Mechanics",
        title="The Mechanics Limerick",
        story="David Morin greeted you with an acoustic guitar and recited: 'There once was a student in flight, whose Lagrangian was balanced and right!' Delighted by your understanding of generalized coordinates, he tossed you a prize.",
        quote="Poetry and physics obey the exact same conservation laws.",
        emoji="🎸",
        is_success=True,
    ),
    BegScenario(
        id="peter_sykes_curly_arrow",
        npc="Peter Sykes",
        role="Pioneer of Reaction Mechanisms",
        title="Curly Arrow Precision",
        story="Peter Sykes examined your nucleophilic addition mechanism. 'Look at that tail-to-head electron curve—not a single charge misplaced!' He stamped your diagram with distinction and rewarded your organic discipline.",
        quote="Never start an arrow from a positive charge, young scholar.",
        emoji="🏹",
        is_success=True,
    ),
    BegScenario(
        id="atkins_physical_thermo",
        npc="Peter Atkins",
        role="Author of Physical Chemistry",
        title="Gibbs Free Energy Equilibrium",
        story="Peter Atkins computed your standard chemical potential. 'Delta G is strongly negative; this financial transfer is purely spontaneous,' he proclaimed, disbursing university funds into your account.",
        quote="Thermodynamics reigns supreme throughout the cosmos.",
        emoji="⚛️",
        is_success=True,
    ),
    BegScenario(
        id="tewani_cengage_math",
        npc="G. Tewani",
        role="Cengage Mathematics Titan",
        title="Conic Section Alignment",
        story="G. Tewani flipped open his Vectors & 3D Geometry volume and asked for the shortest distance between two skew lines. You applied the cross-product formula flawlessly. He smiled proudly and handed you an honorarium.",
        quote="Skew lines never intersect, but hard work always meets its reward.",
        emoji="📐",
        is_success=True,
    ),
    BegScenario(
        id="hall_knight_algebra",
        npc="Hall & Knight",
        role="Authors of Higher Algebra (1887)",
        title="Harmonic Progression Tribute",
        story="The 19th-century British algebraists evaluated your knowledge of mathematical induction and arithmetic-geometric series. Convinced of your classical algebra pedigree, they released a sterling reward.",
        quote="Sound algebraic foundations shall outlive the centuries.",
        emoji="🏛️",
        is_success=True,
    ),
    BegScenario(
        id="kota_photostat_stall",
        npc="The Spiral Binding & Photostat Vendor",
        role="Keeper of All Topper Handwritten Notes",
        title="Photostat Loyalty Dividend",
        story="You spent your last ten coins printing 400 pages of inorganic summary notes. The shopkeeper, deeply moved by your dedication to color-coded reaction charts, waived the fee and tipped you extra.",
        quote="Take these coins; just make sure your photo ends up on my wall.",
        emoji="🖨️",
        is_success=True,
    ),
    BegScenario(
        id="aits_setter_mercy",
        npc="The All-India Test Series Setter",
        role="Designer of Negative-Marking Nightmares",
        title="The Rare Concession",
        story="The professor infamous for designing mock tests with a national average of -4 marks encountered you analyzing question 18. Seeing your notebook filled with thorough derivations, his stony demeanor cracked.",
        quote="You are the only candidate in the nation who didn't guess option C.",
        emoji="🎯",
        is_success=True,
    ),
    BegScenario(
        id="colored_chalk_lecturer",
        npc="The Multi-Colored Chalk Maestro",
        role="Kota Organic Chemistry Legend",
        title="Four-Chalk Mechanism Masterclass",
        story="The senior chemistry teacher completed an entire 15-step total synthesis using four different colors of imported chalk. He pointed his yellow chalk directly at you: 'You! Catch this coin and never forget the anti-Markovnikov rule!'",
        quote="Peroxide effect acknowledged. Payout confirmed.",
        emoji="🖍️",
        is_success=True,
    ),
    BegScenario(
        id="chem_geek_xenon",
        npc="The 99.9% Inorganic Specialist",
        role="Master of Noble Gas Fluorides",
        title="Xenon Hexafluoride Distorted Geometry",
        story="A chemistry prodigy challenged you on the spot: 'What is the hybridization and molecular geometry of XeF6?' You answered: 'sp3d3, distorted octahedral!' Overjoyed to meet someone with culture, he split his weekly allowance.",
        quote="Seven electron pairs of pure aesthetic triumph.",
        emoji="💎",
        is_success=True,
    ),
    BegScenario(
        id="cengage_skew_lines",
        npc="The 3D Geometry Specialist",
        role="Author of Vector Space Problems",
        title="Shortest Distance Calculated",
        story="You were stopped at the department gate and asked to compute the volume of a tetrahedron given four vertex coordinates. You solved the 4x4 determinant mentally. The examiner handed you a scholarship envelope.",
        quote="Determinant evaluated to a non-zero constant. Excellent.",
        emoji="📊",
        is_success=True,
    ),
]


# --------------------------------------------------------------------- #
# FAIL SCENARIOS (30+ sharp, witty rejections with 0 coins)
# --------------------------------------------------------------------- #
FAIL_SCENARIOS: list[BegScenario] = [
    BegScenario(
        id="nta_system_error",
        npc="The Central Testing Server",
        role="Algorithmic Normalization Gatekeeper",
        title="Server Gateway Timeout",
        story="You submitted your financial plea to the official examination portal. The progress bar spun continuously for three minutes before throwing 'HTTP 504: Normalization Error - Your request was lost during server migration.'",
        quote="Answer key challenge window is closed. No refunds issued.",
        emoji="⚠️",
        is_success=False,
    ),
    BegScenario(
        id="hcv_negative_work",
        npc="Prof. H.C. Verma",
        role="Author of Concepts of Physics",
        title="Normal Reaction Defiance",
        story="You asked Prof. H.C. Verma for pocket money. He stared at your empty palm and asked: 'Can a conservative force cause mechanical dissipation in a perpetual cycle?' You blinked silently. He noted down: 'Coefficient of comprehension: zero.'",
        quote="Zero work performed on your balance.",
        emoji="🛑",
        is_success=False,
    ),
    BegScenario(
        id="irodov_unsolved_exercise",
        npc="I.E. Irodov",
        role="Author of Problems in General Physics",
        title="Trivial Exercise for the Reader",
        story="Irodov handed you Problem 4.112 involving an relativistic ellipsoid orbiting a charged spinning sphere. 'The liquidation of currency to this specific candidate is left as an unsolved exercise for the reader.'",
        quote="Zero rubles. Zero excuses.",
        emoji="🥶",
        is_success=False,
    ),
    BegScenario(
        id="jd_lee_exceptions",
        npc="J.D. Lee",
        role="Author of Concise Inorganic Chemistry",
        title="The Lanthanoid Contraction Rebuff",
        story="J.D. Lee slammed his 1,040-page textbook on the table. 'You claimed that atomic radii monotonically decrease across the row without citing the 14 exceptions in the transition series! Leave my sight at once!'",
        quote="Exception number 42: You receive nothing.",
        emoji="📖",
        is_success=False,
    ),
    BegScenario(
        id="hostel_curfew_warden",
        npc="The Chief Hostel Warden",
        role="Enforcer of the 10:30 PM Curfew",
        title="Curfew Violation Confiscation",
        story="You attempted to ask the hostel warden for pocket money. He shined a 500-lumen flashlight into your face, confiscated your illegal electric immersion rod, and filed a formal disciplinary inquiry.",
        quote="Lights out means lights out. Account frozen.",
        emoji="🔦",
        is_success=False,
    ),
    BegScenario(
        id="uncalibrated_mouse",
        npc="The Examination Terminal Mouse",
        role="Hardware Veteran of 4,000 Candidates",
        title="Hardware Malfunction",
        story="You attempted to click 'Claim Coins' on the testing terminal. The optical sensor skipped three inches across the screen, clicked 'Submit Entire Examination' with 42 questions unanswered, and locked the session.",
        quote="Candidate response successfully recorded. Score: 0.",
        emoji="🖱️",
        is_success=False,
    ),
    BegScenario(
        id="invigilator_cardamom",
        npc="The Hall Invigilator",
        role="Loud Cardamom Chewer",
        title="Admit Card Cross-Examination",
        story="The invigilator spent four minutes matching your face with your 8-year-old passport photo while loudly chewing cardamom seeds. He decided your signature was three millimeters too short and declined your claim.",
        quote="Only transparent ballpoint pens allowed in this perimeter.",
        emoji="🧐",
        is_success=False,
    ),
    BegScenario(
        id="blackbook_derivation_fail",
        npc="The Advanced Calculus Author",
        role="Author of the Black Book",
        title="Discontinuous at All Points",
        story="The author glanced at your calculus rough work and pointed out that you applied Leibniz's rule without establishing uniform convergence on the open interval. He retracted his coin pouch with disgust.",
        quote="Rigor is non-negotiable. Return when your function is analytic.",
        emoji="✒️",
        is_success=False,
    ),
    BegScenario(
        id="sharma_sons_shadow",
        npc="Sharma's Accomplished Offspring",
        role="Holder of All-India Rank 12",
        title="The Intimidating Transcript",
        story="You tried to ask your neighborhood peer for a loan. He pulled out his verified scorecard featuring 100 percentile in all three subjects, stared at you with serene pity, and recommended a six-month internet detox instead.",
        quote="Coins will not elevate your percentile, my friend.",
        emoji="🏆",
        is_success=False,
    ),
    BegScenario(
        id="mess_caterer_paneer",
        npc="The Hostel Mess Manager",
        role="Master of Diluted Nutrition",
        title="Sub-Zero Canteen Credit",
        story="You asked the mess manager for an advance. He served you a single lukewarm bowl of yellow-tinted water containing exactly one microscopic cube of boiled potato and declared your credit fully exhausted.",
        quote="Special Sunday Feast fee has already been deducted.",
        emoji="🥣",
        is_success=False,
    ),
    BegScenario(
        id="rotational_mechanics_toppling",
        npc="The Rigid Body Incline",
        role="The Classic Frictionless Trap",
        title="Angular Momentum Deficit",
        story="You reached for a coin resting atop a solid cylinder on an inclined plane. The cylinder began pure rolling without slipping, toppled past your fingers, and accelerated off the edge of the table.",
        quote="Torque about the center of mass was non-zero. The coin has vanished.",
        emoji="🔄",
        is_success=False,
    ),
    BegScenario(
        id="coaching_counselor",
        npc="The Coaching Admission Executive",
        role="Target Batch Sales Representative",
        title="Tuition Fee Installment Pending",
        story="You attempted to collect funds from the institute counter. The counselor printed an updated invoice for the 'Super Advanced Crash Revision Booster Test Series Package' and requested an immediate remittance.",
        quote="Your registration deposit is currently past due.",
        emoji="📠",
        is_success=False,
    ),
    BegScenario(
        id="omr_row_shift",
        npc="The Optical Mark Recognition Scanner",
        role="Mechanical Evaluator of Destinies",
        title="The Fatal One-Row Offset",
        story="You reached for your reward, but the automated grading scanner detected that you marked question 14's bubble in question 15's row, triggering a 20-question domino cascade of negative marking.",
        quote="Cascading offset detected. Total score eliminated.",
        emoji="⭕",
        is_success=False,
    ),
    BegScenario(
        id="biometric_sweaty_thumb",
        npc="The National Biometric Console",
        role="Gatekeeper of Gate 4",
        title="Fingerprint Verification Refused",
        story="You pressed your thumb against the optical scanner to authenticate your coin withdrawal. Nervous sweat obscured your epidermal ridges. The device beeped angrily and flagged your application for manual review.",
        quote="Authentication status: Impostor suspected.",
        emoji="🛑",
        is_success=False,
    ),
    BegScenario(
        id="unit_conversion_joules",
        npc="The International System of Units",
        role="Vigilant Guardian of SI Standards",
        title="Atmosphere-Liter Catastrophe",
        story="You computed work done as P*deltaV in atmosphere-liters but forgot to multiply by 101.325 to convert to Joules. The thermodynamics grader silently highlighted your answer in crimson red and awarded zero marks.",
        quote="Dimensionally inconsistent requests will not be processed.",
        emoji="📉",
        is_success=False,
    ),
    BegScenario(
        id="integer_type_roundoff",
        npc="The Integer Evaluation Algorithm",
        role="Zero-Tolerance Grader",
        title="Truncation Tragedy",
        story="You evaluated an intricate rotational kinematics question and derived exactly 4.9998 meters per second. The terminal software strictly expected the integer '5'. Your appeal was denied.",
        quote="Input value rejected. Strict integer truncation enforced.",
        emoji="🔢",
        is_success=False,
    ),
    BegScenario(
        id="metal_detector_jeans_rivet",
        npc="The Security Screening Officer",
        role="Operative of the Handheld Wand",
        title="Metal Detector False Positive",
        story="The security wand shrieked as it passed your pocket rivet. You were escorted to an interrogation booth and forced to surrender all metallic possessions, including your loose pocket coins.",
        quote="Metallic rivets prohibited inside the testing perimeter.",
        emoji="🚨",
        is_success=False,
    ),
    BegScenario(
        id="dropped_question_nta",
        npc="The Final Answer Key Notification",
        role="Midnight PDF Release",
        title="Question Dropped from Scoring",
        story="You spent 25 minutes deriving an intricate electromagnetic induction problem correctly. At 2 AM, the official revision declared the question ambiguous and dropped it from the aggregate calculation.",
        quote="Question 62 has been expunged from the scoring ledger.",
        emoji="📄",
        is_success=False,
    ),
    BegScenario(
        id="kota_broker_soundproof",
        npc="The Kota Real Estate Agent",
        role="Purveyor of Quiet Study Havens",
        title="The Industrial Jackhammer Symphony",
        story="You begged the landlord for a rent rebate. He reminded you that the 24-hour highway flyover construction directly outside your window was 'ambient white noise for optimal concentration.'",
        quote="No security deposit refund under any circumstances.",
        emoji="🏗️",
        is_success=False,
    ),
]


def roll_beg_scenario(user_id: int, success: bool, base_coins: int) -> tuple[BegScenario, int]:
    """Roll a context-rich, non-repeating JEE scenario for the user.

    Uses an in-memory sliding window history to guarantee no duplicate
    encounters for at least 25 consecutive `.beg` commands per user.
    """
    history = _USER_HISTORY.setdefault(user_id, deque(maxlen=HISTORY_CAPACITY))

    pool = SUCCESS_SCENARIOS if success else FAIL_SCENARIOS
    candidates = [s for s in pool if s.id not in history]
    if not candidates:
        # If pool exhausted by recent history, reset user history
        history.clear()
        candidates = pool

    scenario = random.choice(candidates)
    history.append(scenario.id)

    # Dynamic payout tuning:
    if not success:
        return scenario, 0

    # Rare jackpot roll (8% chance of getting 1.8x - 2.5x coins)
    if random.random() < 0.08:
        payout = int(base_coins * random.uniform(1.8, 2.5))
    else:
        payout = base_coins

    return scenario, payout
