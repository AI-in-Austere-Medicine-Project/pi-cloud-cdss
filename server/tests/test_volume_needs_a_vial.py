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
    "Run the morphine infusion at 0.02 mL/kg/hr.",
])
def test_a_rate_is_not_read_as_a_volume(line):
    ctx = oc.extract_patient_context("80 kg adult, morphine")
    assert oc.unconfirmed_volume_issues(line, ctx) == []


def test_a_per_kg_volume_is_a_volume():
    """Was a "not a volume" case. Med sweep PR 1 (owner, 2026-10-30): "mL/kg"
    volumes are checked like any mL — live served calcium gluconate "10 mL/kg
    of 10% solution", ten times the dose's volume (test_sweep_pr1_wrong_numbers)."""
    ctx = oc.extract_patient_context("80 kg adult, morphine")
    issues = oc.unconfirmed_volume_issues("Morphine 0.1 mL/kg is not used here.", ctx)
    assert len(issues) == 1 and "morphine" in issues[0], issues


# ── Owner ruling on recipes (2026-10-25) ────────────────────────────────────
# "An mL serves when it comes from a confirmed vial OR from a signed entry's
# own recipe line (the concentration stated in the signed quote, e.g. E05's
# 10 mcg/mL push-dose syringe). Any other preparation or volume holds."

ADULT = oc.PatientContext(adult_confirmed=True)


@pytest.mark.parametrize("line", [
    # E05's own recipe line, verbatim from its signed caution.
    "Push-dose syringe: 1 mL of 1:10,000 (100 mcg/mL) epinephrine in 9 mL NS gives "
    "10 mcg/mL; 5-20 mcg is 0.5-2 mL (JTS ID83 p.24).",
    # A dose drawn from that signed syringe, which the line names.
    "Draw 2 mL of 10 mcg/mL epinephrine IV (20 mcg).",
    # The signed cardiac-arrest syringe (0.1 mg/mL, 10 mL for 1 mg).
    "Draw 10 mL of the 0.1 mg/mL (1:10,000) epinephrine syringe IV (1 mg).",
])
def test_a_signed_recipe_volume_serves(line):
    assert oc.unconfirmed_volume_issues(line, ADULT) == []


def test_a_recipe_from_a_vial_waits_for_the_vial():
    """Ketamine's declared 5 mg/mL push dilution starts from the 50 mg/mL vial:
    it serves once that vial is confirmed, and holds while the kit asks (#181)."""
    line = "Draw 4 mL of 5 mg/mL ketamine IV (20 mg)."
    issues = oc.unconfirmed_volume_issues(line, ADULT)
    assert len(issues) == 1 and "no confirmed vial" in issues[0], issues
    confirmed = oc.PatientContext(adult_confirmed=True, confirmed_concentrations={"ketamine": 50.0})
    assert oc.unconfirmed_volume_issues(line, confirmed) == []
    quoted = ("OWNER-DECLARED dilution for IV push (no guideline states one): 5 mg/mL — "
              "1 mL of ketamine 50 mg/mL in 9 mL of normal saline.")
    assert oc.unconfirmed_volume_issues(quoted, ADULT), "a quoted recipe waits for the vial too"


@pytest.mark.parametrize("line,drug", [
    # No signed norepinephrine preparation exists.
    ("Mix 4 mg norepinephrine in 250 mL NS (16 mcg/mL).", "norepinephrine"),
    # The epinephrine bag left the cards in A35; nothing signed prepares it.
    ("Add 1 mg epinephrine to a 250 mL bag of NS.", "epinephrine"),
    # The 1:1,000 ampoule IV: signed text names 1 mg/mL only as the vial for IM
    # and as what NOT to push; neither is a preparation.
    ("Draw 1 mL of 1 mg/mL epinephrine IV (1 mg).", "epinephrine"),
    # A recipe volume with no concentration named: from the ampoule, 2 mg.
    ("Give 2 mL of epinephrine IV (20 mcg).", "epinephrine"),
    # The old push-dose card's own copy of the recipe, not the signed line.
    ("Draw 1 mL of 1:10,000 epinephrine (0.1mg/mL) into a 10 mL syringe.", "epinephrine"),
])
def test_any_other_preparation_or_volume_holds(line, drug):
    issues = oc.unconfirmed_volume_issues(line, ADULT)
    assert len(issues) == 1 and drug in issues[0] and "no confirmed vial" in issues[0], issues


def test_the_push_dose_card_serves():
    """The card prints the signed entry's recipe (A35), so it passes."""
    q = "need to make push dose epi"
    card = oc.build_fixed_prep_response(q, ADULT)
    assert "10 mcg/mL" in card
    assert oc.unconfirmed_volume_issues(card, ADULT) == []


def test_the_fentanyl_ml_with_no_vial_holds():
    """Owner: the fentanyl "1 mL of 0.05 mg/mL" hold is correct (no signed vial,
    no signed fentanyl preparation)."""
    issues = oc.unconfirmed_volume_issues(
        "Draw 1 mL of 0.05mg/mL fentanyl IV (0.05mg). Indication: acute pain.", ADULT)
    assert len(issues) == 1 and "fentanyl" in issues[0], issues
