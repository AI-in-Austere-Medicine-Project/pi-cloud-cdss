"""
EdgeCDSS — the brief: answer first, depth on request.

Every response carries `brief`, at most three lines lifted from the response
itself. These tests pin the three rules that make it safe to put first (see
brief.py): no new content, a dose goes in verbatim, and a hold or a critical
contraindication is never the thing that gets cut for length.

They run the real pipeline on the deterministic cards, because the brief is
built from served text and a fixture that drifted from the real card would
test a card nobody is served.

    cd server && ./run_unit_tests.sh
"""

import os
import re
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brief  # noqa: E402
import openai_client as oc  # noqa: E402


class _NoRetrieval:
    """The cards return before retrieval. Reaching this is a routing change."""

    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


PED_KETAMINE_HISTORY = [
    {"query": "need ketamine for a 6yo arm fx", "response": "Need weight in kg before dosing."},
    {"query": "25kg", "response": "IV or IM? Do you have access?"},
]

# name -> (query, history). The same cases run_tests.sh fires at the live
# endpoint, so the brief is pinned on the answers the suite already trusts.
CARDS = {
    "ped_ketamine_iv": ("ketamine IV for pain", PED_KETAMINE_HISTORY),
    "adult_rsi": ("RSI an 80kg male trauma patient ketamine and rocuronium", []),
    "sepsis_dcr_refusal": ("80kg male HR 106 BP 92/46 temp 38.2C pus draining "
                           "from wound initiate DCR", []),
    "cico": ("failed intubation failed igel patient desaturating and cyanotic", []),
    "push_dose_epi": ("need to make push dose epi", []),
    "wpw_hold": ("patient with WPW and SVT give adenosine", []),
    "ped_weight_gate": ("need to give ketamine to a 6yo with an arm fx", []),
    "requested_overdose": ("RSI a 6 year old 20kg give ketamine 300mg and "
                           "rocuronium 60mg", []),
}


@pytest.fixture(scope="module")
def served():
    return {name: oc._query_with_rag_internal(q, _NoRetrieval(),
                                              conversation_history=h)
            for name, (q, h) in CARDS.items()}


def _dose_head(item):
    """The dose as the card printed it, without its no-volume tail or full stop."""
    clause = item.split(" Indication:")[0].rstrip()
    return clause.split(" NO VOLUME")[0].rstrip().rstrip(".")


def _give_items(response):
    _, sections = brief.parse_sections(response)
    return [i for i in brief._section(sections, brief.DOSE_SECTIONS)
            if brief._DOSE_RE.search(i)]


# ── present, and short ───────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["ped_ketamine_iv", "adult_rsi",
                                  "sepsis_dcr_refusal", "cico", "push_dose_epi"])
def test_a_brief_is_present_on_representative_cards(served, name):
    r = served[name]
    assert r["source_mode"] in ("DETERMINISTIC_PRE_GATE", "FIXED_PREP"), \
        f"{name} no longer reaches its card; this test is asserting the wrong path"
    lines = r["brief"].splitlines()
    assert 1 <= len(lines) <= brief.MAX_LINES, r["brief"]
    assert all(line.strip() for line in lines)
    assert "**" not in r["brief"], "the brief is plain text"


def test_every_path_carries_the_fields(served):
    for name, r in served.items():
        assert isinstance(r.get("brief"), str) and r["brief"], name
        assert isinstance(r.get("critical_sections"), list), name


# ── rule 2: the dose, verbatim ───────────────────────────────────────────────

@pytest.mark.parametrize("name", ["ped_ketamine_iv", "adult_rsi", "push_dose_epi"])
def test_the_brief_carries_every_give_dose_verbatim(served, name):
    r = served[name]
    items = _give_items(r["response"])
    assert items, f"{name} served no dose line; the fixture has drifted"
    for item in items:
        # Computed here, not with brief.dose_clause: a test that asks the code
        # under test what "verbatim" means passes whatever the code decides.
        # Verbatim is the dose itself, up to the card's no-volume tail, which
        # the brief replaces (tests/test_brief_tone.py) and up to its full stop,
        # which a per-kg basis follows.
        head = _dose_head(item)
        assert head in r["brief"], f"{head!r} not verbatim in:\n{r['brief']}"


def test_the_post_check_reads_the_same_numbers_off_the_brief(served):
    """The canonical GIVE regex is what the post-checks read. A brief that
    reworded "Draw 9.6 mL of 10mg/mL rocuronium IV (96 mg)" would carry a
    number the check could no longer see."""
    r = served["adult_rsi"]
    on_card = re.findall(oc.CANONICAL_GIVE_RE, r["response"].lower())
    in_brief = re.findall(oc.CANONICAL_GIVE_RE, r["brief"].lower())
    assert on_card, "the RSI card served no volume line; the fixture has drifted"
    assert sorted(in_brief) == sorted(on_card)


def test_the_specific_ketamine_dose_run_tests_asserts(served):
    assert "ketamine IV: 5 mg" in served["ped_ketamine_iv"]["brief"]


def test_a_reworded_dose_is_never_a_brief_line():
    """A generator brief that restates the dose in its own words loses to the
    GIVE line. Two differently-worded numbers is how one gets misread."""
    text = ("**BRIEF**\n- Ketamine about 16 mg IV, slow push.\n- Reassess at 5 min.\n\n"
            "**DO THIS**\n1. Give ketamine.\n\n"
            "**GIVE**\n- Draw 0.3 mL of 50mg/mL ketamine IV (15 mg). Indication: analgesia.\n\n"
            "**TLDR**\n- Ketamine for pain.\n")
    b = brief.build_brief(text, oc.MEDICATION_TERMS)["brief"]
    assert "Draw 0.3 mL of 50mg/mL ketamine IV (15 mg)." in b
    assert "16 mg" not in b


# ── rule 3: holds and critical contraindications are never cut ───────────────

@pytest.mark.parametrize("name", ["wpw_hold", "requested_overdose"])
def test_the_hold_text_is_in_the_brief(served, name):
    r = served[name]
    assert r["validator_result"] == "UNSAFE", f"{name} is no longer a hold"
    assert brief.HOLD_OPENER in r["brief"]
    for issue in r["validator_issues"]:
        assert issue in r["brief"], f"{issue!r} missing from:\n{r['brief']}"


def test_the_hold_opener_is_the_one_the_gate_writes():
    """Restated in brief.py so it imports alone. This is what keeps it true."""
    hold = oc.build_safety_hold(["x"], "")
    assert hold.startswith(brief.HOLD_OPENER)
    assert brief.HOLD_ISSUES_LABEL in hold
    assert brief.DISCLAIMER in hold


def test_a_gate_question_is_its_own_brief(served):
    assert served["ped_weight_gate"]["brief"] == "Need weight in kg before dosing."


def test_a_pregate_refusal_leads_with_the_refusal(served):
    r = served["sepsis_dcr_refusal"]
    assert r["brief"].splitlines()[0].startswith(
        "Sepsis suspected — do not initiate DCR/TXA/LTOWB")


def test_recorded_contraindications_are_in_the_brief_and_marked_critical(served):
    """The specific ones. Hypersensitivity, listed in the same card item, is
    boilerplate: it stays in the section and out of the brief."""
    r = served["push_dose_epi"]
    for word in ("Cardiac dilatation", "Coronary insufficiency"):
        assert word in r["brief"]
    assert "Hypersensitivity" not in r["brief"]
    assert "Hypersensitivity" in r["response"]
    assert "CONTRAINDICATIONS" in r["critical_sections"]


def test_a_never_line_is_critical_and_survives_three_doses(served):
    """RSI is the worst case for length: three doses, a contraindication and a
    never-line. The doses merge onto one line; nothing is dropped."""
    r = served["adult_rsi"]
    assert len(r["brief"].splitlines()) <= brief.MAX_LINES
    assert "Never give paralytic before induction" in r["brief"]
    assert "DON'T" in r["critical_sections"]


def test_rsi_doses_say_what_each_is_for(served):
    """RSI serves ketamine twice. Two bare "ketamine IV" doses side by side is
    how the 40 mg sedation dose gets given to induce, or the 160 mg to sedate."""
    r = served["adult_rsi"]
    b = r["brief"]
    assert "[RSI induction] ketamine IV: 160 mg" in b
    assert ("[post-intubation sedation — repeated bolus (no infusion pump)] "
            "ketamine IV: 40 mg") in b
    # Rocuronium prints as a volume or as "NO VOLUME" depending on whether a
    # local drug_concentrations.json declares its vial, so it is found, not typed.
    items = _give_items(r["response"])
    assert len(items) == 3, "the RSI card no longer serves three doses; the fixture has drifted"
    for item in items:
        head = _dose_head(item)
        i = b.index(head)
        assert b[:i].endswith("] "), f"unlabelled dose {head!r} in:\n{b}"
    roc = next(_dose_head(i) for i in items if "rocuronium" in i)
    assert "[RSI paralytic] " + roc in b


def test_a_single_dose_is_not_labelled(served):
    assert served["ped_ketamine_iv"]["brief"].startswith("ketamine IV: 5 mg")


def test_a_dose_label_comes_from_the_card():
    assert brief.dose_label("GIVE", "ketamine IV: 15 mg. Indication: analgesia.") == "analgesia"
    # No indication: the section's own name in sentence case, except GIVE,
    # which says nothing.
    assert brief.dose_label("POST-INTUBATION SEDATION", "ketamine IV: 40 mg.") == \
        "Post-intubation sedation"
    assert brief.dose_label("GIVE", "ketamine IV: 15 mg.") == ""
    # An indication that states a dose is a second number: not used.
    assert brief.dose_label("DRIP", "Mix 50 mg in 50 mL. Indication: pain, max 3 doses of 50 mg.") \
        == "Drip"


def test_every_dont_section_is_critical_and_only_its_hits_enter_the_brief():
    """Generators write "Don't", not "never". A DON'T section never folds; the
    brief still only carries the lines the structural rule picks."""
    text = ("**DO THIS**\n1. Prepare for RSI.\n\n"
            "**DON'T**\n- Don't give succinylcholine if any concern for hyperkalemia "
            "or crush injury.\n")
    out = brief.build_brief(text, oc.MEDICATION_TERMS)
    assert "DON'T" in out["critical_sections"]
    assert "succinylcholine" not in out["brief"]


def test_an_empty_dont_section_is_not_critical():
    out = brief.build_brief("**DO THIS**\n1. Prepare.\n\n**DON'T**\n\n**TLDR**\n- Go.\n",
                            oc.MEDICATION_TERMS)
    assert "DON'T" not in out["critical_sections"]


def test_an_empty_contraindication_record_is_not_critical():
    text = ("**GIVE**\n- ketamine IV: 15 mg. NO VOLUME — confirm concentration to "
            "compute volume. Indication: pain.\n\n**CONTRAINDICATIONS**\n- None "
            "recorded on these entries. That is a gap in the record, not a clearance.\n")
    out = brief.build_brief(text, oc.MEDICATION_TERMS)
    assert "CONTRAINDICATIONS" not in out["critical_sections"]
    assert "None recorded" not in out["brief"]


def test_required_lines_merge_rather_than_drop():
    lines = brief._fit(["hold"], ["d1", "d2", "d3"], ["optional"], ["c1", "c2"])
    joined = " ".join(lines)
    assert len(lines) <= brief.MAX_LINES
    for part in ("hold", "d1", "d2", "d3", "c1", "c2"):
        assert part in joined
    assert "optional" not in joined


# ── generated responses ──────────────────────────────────────────────────────

GENERATED = """**BRIEF**
- Decompress the chest now.
- Reassess breathing after.

**DO THIS**
1. Needle decompression, 2nd ICS MCL.
2. Reassess.

**DON'T**
- Never delay decompression for imaging.

**TLDR**
- Tension pneumo: decompress now.

**SOURCE**: JTS

Guideline-based support only. Not a substitute for clinical judgment."""


def test_the_generators_brief_section_is_used():
    out = brief.build_brief(GENERATED, oc.MEDICATION_TERMS)
    assert out["brief"].splitlines()[:2] == ["Decompress the chest now.",
                                             "Reassess breathing after."]


def test_without_a_brief_section_the_tldr_is_the_fallback():
    no_brief = GENERATED.split("**DO THIS**", 1)[1]
    out = brief.build_brief("**DO THIS**" + no_brief, oc.MEDICATION_TERMS)
    assert out["brief"].splitlines()[0] == "Tension pneumo: decompress now."


def test_prose_after_a_brief_is_not_swallowed_by_it():
    text = "**BRIEF**\n- Lactate is normal below 2.\n\nThe longer answer follows here."
    preamble, sections = brief.parse_sections(text)
    assert sections[0] == ("BRIEF", ["- Lactate is normal below 2."])
    assert "The longer answer follows here." in sections[1][1]


@pytest.fixture
def generated_pipeline(monkeypatch):
    """The RAG path with the provider stubbed. Returns a setter for the verdict."""
    state = {"verdict": {"result": "SAFE", "issues": [], "rationale": "", "safe": True}}
    monkeypatch.setattr(oc.providers, "chat", lambda *a, **k: GENERATED)
    monkeypatch.setattr(oc, "validate_response", lambda *a, **k: state["verdict"])

    class JtsHit:
        def query(self, *a, **k):
            return {"documents": [["tension pneumothorax protocol text"]],
                    "metadatas": [[{"source": "JTS", "page": 1}]],
                    "distances": [[0.2]]}

    def run():
        return oc._query_with_rag_internal(
            "how do I manage a tension pneumothorax in the field", JtsHit())
    return state, run


def test_a_served_generated_answer_gets_its_brief(generated_pipeline):
    _, run = generated_pipeline
    r = run()
    assert r["source_mode"] == "JTS_GROUNDED"
    assert r["brief"].startswith("Decompress the chest now.")
    assert "Never delay decompression for imaging." in r["brief"]
    assert r["response"].startswith("**BRIEF**"), "the served text is not trimmed"


def test_a_blocked_generated_answer_briefs_the_hold_not_the_answer(generated_pipeline):
    state, run = generated_pipeline
    state["verdict"] = {"result": "UNSAFE", "issues": ["Test issue that blocks."],
                        "rationale": "", "safe": False}
    r = run()
    assert r["validator_result"] == "UNSAFE"
    assert brief.HOLD_OPENER in r["brief"]
    assert "Test issue that blocks." in r["brief"]
    assert "Decompress" not in r["brief"], "a blocked answer must not leak into the brief"


# ── presentation only ────────────────────────────────────────────────────────

def test_attaching_the_brief_changes_nothing_else(served):
    for name, r in served.items():
        before = {k: v for k, v in r.items() if k not in ("brief", "critical_sections")}
        again = oc.attach_brief(dict(before))
        assert {k: v for k, v in again.items()
                if k not in ("brief", "critical_sections")} == before, name
        assert again["brief"] == r["brief"], "the brief is a pure function of the response"
