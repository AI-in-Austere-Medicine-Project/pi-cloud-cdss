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
ALIAS_STANDALONE_CASES = [
    ("give k now",            "k",             "ketamine (context-dependent)"),
    ("pa on scene",           "pa",            "physician assistant"),
    ("apply a cat",           "cat",           "combat application tourniquet"),
    ("need to make push dose epi", "push dose epi", "epinephrine 10mcg/mL bolus preparation"),
    ("rocky onium please",    "rocky onium",   "rocuronium"),
    ("vitamin k for pain",    "vitamin k",     "ketamine"),
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
