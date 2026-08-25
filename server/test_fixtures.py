"""
EdgeCDSS — regression fixtures taken verbatim from the v4.1 audit corpus.

Every fixture carries its provenance as `<session file>:<line>` in
data/sessions/ (see AUDIT_v4.1.md §0 for the corpus description). Tests assert
against these strings rather than paraphrases, so a test cannot drift into
restating the implementation.

Where a string is RECONSTRUCTED rather than verbatim, it says so and why: the
session logger stores only the first 200 characters of each response
(openai_client.log_query), so a GIVE line past that offset is not in the log.
"""

# ── S-1: the 12-turn session that carried a child's weight into new patients ─
# cdss_session_2026-07-18.jsonl lines 3-14, queries verbatim and in order.
# The audit numbers these turns 1-12; the logs' own `history_turns` field
# numbers the same turns 0-11. Log line numbers are used here to avoid both.
S1_SEQUENCE = [
    (3,  "I need to intubate a 6 year old"),
    (4,  "34kg"),
    (5,  "TBI mgmt"),
    (6,  "burn care"),
    (7,  "tbi mgmt on vent"),
    (8,  "have a marine that was hit by an IED - he is bleeding out"),
    (9,  "TBI vent mgmt goals - bp threshoholds"),
    (10, "have a 7 year old having a decent time breathing"),
    (11, "he is a normal weight for a 7 year old"),
    (12, "17 kg"),
    (13, "new session"),
    (14, "have a patient 6 months prego - shes bleeding otu"),
]

S1_QUERIES = [q for _, q in S1_SEQUENCE]

# The two turns where a new patient inherited the previous patient's weight.
S1_BOUNDARY_LINES = (8, 10, 13, 14)      # must reset
S1_CONTINUATION_LINES = (5, 6, 7, 9, 11, 12)   # must NOT reset

# ── S-2: the two logged UNSAFE records with an emptied issue list ────────────
# cdss_session_2026-07-18.jsonl:8 and :11. Response text is the stored
# 200-character preview, verbatim.
S2_IED_PREVIEW = (
    "**DO THIS**\n1. Control all sources of external bleeding.\n"
    "2. Initiate fluid resuscitation with IV fluids.\n"
    "3. Assess for signs of shock and consider blood products if available.\n\n"
    "**GIVE**\n- Draw 0.51 mL"
)
S2_GATE_QUESTION_PREVIEW = "Need exact weight in kg before dosing."

# ── S-3: adult, no confirmed weight, empty dose contract, dose served ────────
# cdss_session_2026-07-21.jsonl:2 — query verbatim; patient_ctx from the log.
S3_QUERY = "Have a TBI patient that is having ststus SZ, maxed out on versed"
# RECONSTRUCTED: the stored preview truncates before the GIVE line. The dose is
# the SEIZURE_ADULT_DEFAULT string hard-coded in build_allowed_actions(), and
# the format is openai_client's canonical GIVE line.
S3_GIVE_LINE = "**GIVE**\n- Draw 15 mL of 100mg/mL levetiracetam IV (1500mg). Indication: status epilepticus."

# ── SC-6 negative case: a fixed prep is not a canonical GIVE line ────────────
# cdss_session_2026-07-18.jsonl:40 and :67 — stored preview, verbatim.
FIXED_PREP_PUSH_DOSE_EPI = (
    "**PUSH-DOSE EPINEPHRINE PREP**\n- Make 10 mcg/mL epinephrine.\n"
    "- Draw 1 mL of 1:10,000 epinephrine (0.1mg/mL) into a 10 mL syringe.\n"
    "- Add 9 mL normal sa"
)

# ── S-4: vent-settings query routed to the RSI bundle ───────────────────────
S4_VENT_QUERY = "Ventilator settings for 75kg male in DKA. Ph 7.1"          # 07-20.jsonl:4
S4_VENT_REFUSED = "I need ventilator settings for a DKA patient that I’m managing for the next 24 hours"  # 07-18.jsonl:42

# ── F-2: alias substring poisoning, the four rows from AUDIT_v4.1.md §F-2 ───
# (query, alias keys that plain substring matching wrongly resolved)
F2_ROWS = [
    (S4_VENT_REFUSED,                                        ["k", "pa", "ett"]),   # 07-18.jsonl:42
    ("Medication recommendation for angioedema",              ["cat", "medic"]),    # 07-20.jsonl:6
    ("Vent settings dka",                                     ["k", "ett"]),        # 07-20.jsonl:3
    ("80kg male fx to tib fib, need pain meds IV is established", ["k", "pa"]),     # 08-11.jsonl:7
]

# Aliases that must still resolve when typed as standalone words.
# Unambiguous keys: typed as words, they resolve on their own. This is why
# short keys were word-anchored in v4.1 rather than deleted.
# NOTE: ("vitamin k for pain", "vitamin k", "ketamine") used to live here. It
# was removed with the alias itself: vitamin K (phytomenadione) is a real drug
# with its own indication, so mapping it onto ketamine as a dictation mangling
# shadowed it, and "vitamin K dose for warfarin reversal" resolved to ketamine.
# See ALIAS_SHADOWS_A_REAL_DRUG below and test_drug_contracts.py.
ALIAS_STANDALONE_CASES = [
    ("need to make push dose epi", "push dose epi", "epinephrine 10mcg/mL bolus preparation"),
    ("rocky onium please",    "rocky onium",   "rocuronium"),
    ("start a norepi drip",   "norepi drip",   "norepinephrine infusion"),
    ("apply a tq",            "tq",            "tourniquet"),
]

# An alias may never be another real drug's name. Fifth specimen of the
# substring/shadow collision class: "vitamin k" -> ketamine meant discovery
# scenario A1-COL-004, "vitamin K dose for warfarin reversal", resolved to
# ketamine and enhanced retrieval with it. Each row is (query, forbidden_key).
ALIAS_SHADOWS_A_REAL_DRUG = [
    ("vitamin K dose for warfarin reversal", "vitamin k"),
    ("does he need vitamin K here",          "vitamin k"),
]

# F-6: keys whose collision IS the whole word, so word anchoring cannot help.
# These resolve only when a second term pointing at the same protocol is
# present. Each row is (query_alone, query_corroborated, key).
#
# Measured misroute that motivated the change: "his K is 6.8 and the ECG has
# peaked T waves, what is the order of treatment" resolved k -> ketamine and
# searched a hyperkalaemia emergency as a ketamine question (G-TRP-12).
ALIAS_CONTEXT_DEPENDENT_CASES = [
    ("give k now", "give k now, ketamine 100mg/mL drawn up", "k"),
    ("he is cold", "he is cold, hypothermia after two hours in the water", "cold"),
    ("hs suspected", "hs suspected, hemorrhagic shock from the pelvis", "hs"),
    ("check the pus", "check the pus, sepsis is the working diagnosis", "pus"),
]

# ── SC-6 unchanged-path case: a populated contract, three real issues ────────
# cdss_session_2026-07-19.jsonl:6 — validator_issues verbatim; patient_ctx has
# confirmed_weight_kg 72.1, so the contract was non-empty.
S6_POPULATED_CONTRACT_ISSUES = [
    "GIVE line doses 'ketamine' (75.0mg) but that medication is not in the ALLOWED_DOSES contract.",
    "GIVE line doses 'rocuronium' (75.0mg) but that medication is not in the ALLOWED_DOSES contract.",
    "GIVE line states lorazepam 1mg, which does not match any ALLOWED_DOSES value (4mg IV).",
]
# RECONSTRUCTED: the log stores a 200-character preview of the *blocked* text,
# not the generated response. These are the canonical GIVE lines that produce
# the three issues above; volumes follow from the standard concentrations.
S6_POPULATED_CONTRACT_RESPONSE = (
    "**GIVE**\n"
    "- Draw 0.75 mL of 100mg/mL ketamine IV (75mg). Indication: RSI induction.\n"
    "- Draw 7.5 mL of 10mg/mL rocuronium IV (75mg). Indication: RSI paralysis.\n"
    "- Draw 0.5 mL of 2mg/mL lorazepam IV (1mg). Indication: sedation.\n"
)

# ── General medical reference fixtures (F-4) ────────────────────────────────
# Representative of the three answer shapes the reference tier produces. They
# are run through the SAME gate as every JTS answer, which is the claim the
# invariant matrix in test_safety_gate.py exists to pin.

# The reference-lookup shape. Numbers with units, no drug, no GIVE line.
GENERAL_LAB_REFERENCE = (
    "Normal serum potassium is 3.5-5.0 mEq/L.\n"
    "Below 2.5 or above 6.5 is a critical value.\n"
    "Peaked T waves appear above roughly 6.5.\n\n"
    "General reference, not JTS. Confirm against local protocol."
)

# The recipe shape — allowed. States what a fixed dilution yields. Deliberately
# NOT in canonical GIVE form: this is a fact about the syringe, not a dose for a
# patient, and CANONICAL_GIVE_RE must not match it.
GENERAL_PREP_RECIPE = (
    "**NOREPINEPHRINE INFUSION PREP**\n"
    "- Mix 4 mg norepinephrine in 250 mL NS.\n"
    "- Final concentration: 16 mcg/mL.\n\n"
    "General reference, not JTS. Confirm against local protocol."
)

# The prescription shape — forbidden. What a general-mode answer must never
# produce, and what SC-6 blocks when it does, because general mode never builds
# an ALLOWED_DOSES contract to check it against.
GENERAL_MODE_GIVE_LINE = (
    "**GIVE**\n"
    "- Draw 0.24 mL of 100mg/mL ketamine IV (24mg). Indication: analgesia.\n"
)
