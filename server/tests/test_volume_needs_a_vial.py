"""Any mL in a served answer must follow from a confirmed or signed vial for that drug.

Owner, #181 review (2026-10-25): "any mL in a served answer for a drug must be
derivable from a confirmed or signed concentration for that drug; otherwise
the answer holds, naming the drug and 'no confirmed vial'."

Found in #181's harness: after "no not ketamine, morphine" the offline model
served "Draw 8 mL of morphine IV (8 mg)" SAFE, for an 80 kg adult. The kit
declares morphine 10, 2 and 1 mg/mL, none signed; from the 10 mg/mL ampoule
8 mL is 80 mg. The mL check covered only a drug whose vial question was
pending. It passed the same line on main.

A volume is derivable when a mass stated in the same sentence, at the
resolved concentration, gives it (within 5%). A pump rate (mL/hr, mL/min,
mL/kg) is not a volume drawn from the vial and is not read here.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
MORPHINE_LINE = "**GIVE**\n- Draw 8 mL of morphine IV (8 mg). Indication: acute pain / analgesia."


def _issues(query, response, confirmed=None):
    ctx = oc.extract_patient_context(query)
    if confirmed:
        ctx.confirmed_concentrations.update(confirmed)
    allowed = oc.build_allowed_doses(query, ctx)
    return oc.run_deterministic_checks(query, response, ctx, allowed).issues


def _volume_issues(issues):
    return [i for i in issues if "volume in mL" in i]


# ── The harness case ────────────────────────────────────────────────────────

def test_the_morphine_ml_with_no_vial_holds():
    issues = _volume_issues(_issues("80 kg adult, IV, morphine for pain", MORPHINE_LINE))
    assert len(issues) == 1, issues
    assert "morphine" in issues[0] and "no confirmed vial" in issues[0], issues[0]


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


def test_the_harness_flow_holds(monkeypatch):
    """need to give ketamine 80kg adult IV -> no not ketamine, morphine."""
    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        return MORPHINE_LINE
    monkeypatch.setattr(providers, "chat", chat)
    hist = []
    for q in ["need to give ketamine 80kg adult IV", "no not ketamine, morphine"]:
        r = oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(hist))
        hist.append({"query": q, "response": r["response"]})
    assert r["validator_result"] == "UNSAFE", r["response"]
    assert "8 mL" not in r["response"]
    assert "no confirmed vial" in r["response"] and "morphine" in r["response"], r["response"]


# ── A confirmed or signed vial: the mL must follow from it ──────────────────

def test_a_confirmed_vial_and_the_right_ml_passes():
    assert _volume_issues(_issues(
        "80 kg adult, IV, ketamine for pain",
        "**GIVE**\n- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg). Indication: pain.",
        {"ketamine": 50.0})) == []


def test_a_confirmed_vial_and_an_ml_from_another_vial_holds():
    """INC-001's 09:12 answer, with the 50 mg/mL vial confirmed."""
    issues = _volume_issues(_issues(
        "80 kg adult, IV, ketamine for pain",
        "**DO THIS**\n1. Draw 0.2 mL of 100mg/mL ketamine IV (20mg). Indication: pain control.",
        {"ketamine": 50.0}))
    assert len(issues) == 1 and "ketamine" in issues[0], issues


def test_a_single_signed_vial_needs_no_confirmation():
    """Naloxone 0.4 mg/mL is the kit's one signed presentation."""
    assert _volume_issues(_issues(
        "adult, naloxone dose",
        "**GIVE**\n- Draw 1 mL of 0.4mg/mL naloxone IV (0.4 mg).")) == []
    issues = _volume_issues(_issues(
        "adult, naloxone dose", "**GIVE**\n- Draw 2 mL of naloxone IV (0.4 mg)."))
    assert len(issues) == 1 and "naloxone" in issues[0], issues


def test_an_ml_with_no_mass_to_derive_it_from_holds():
    issues = _volume_issues(_issues(
        "adult, naloxone dose", "**GIVE**\n- Push 3 mL of naloxone IV."))
    assert len(issues) == 1 and "naloxone" in issues[0], issues


def test_a_pending_vial_still_holds_and_says_so():
    issues = _volume_issues(_issues(
        "80 kg adult, IV, ketamine for pain",
        "**GIVE**\n- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)."))
    assert len(issues) == 1, issues
    assert "ketamine" in issues[0] and "no confirmed vial" in issues[0], issues[0]


# ── Not a volume drawn from the vial ────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "Run the morphine infusion at 2 mL/hr.",
    "Morphine 0.1 mL/kg is not used here.",
])
def test_a_rate_is_not_read_as_a_volume(line):
    ctx = oc.extract_patient_context("80 kg adult, morphine")
    assert oc.unconfirmed_volume_issues(line, ctx) == []
