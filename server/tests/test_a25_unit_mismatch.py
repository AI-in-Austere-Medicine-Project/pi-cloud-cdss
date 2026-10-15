"""A25 (owner, 2026-10-10): a model-written dose in a unit other than the
signed dose's unit holds, even when it converts to the signed value.

edgecdss-v3's answer to run_tests.sh case B1 (D6 bench 20261009T123013Z) put
the signed "fentanyl IV: 50 mcg" in GIVE, then "Draw 50 mcg of fentanyl IV
(50 mg)" in DO THIS. The free-text dose check already holds that line: it
converts every amount to mg, and 50 mg is not 0.05 mg. What it let through is
the same dose in the other unit: "0.05 mg" of fentanyl, signed as 50 mcg,
converts equal and served. A medic reading mg where the source writes mcg is
one slip from a thousandfold error.

The owner's rule (2026-10-10, "any other-unit dose"): the stated unit must be
the unit of the signed entry the value matched (its display_units), else the
answer holds; "50 mcg (0.05 mg)" holds too. The unit is the matched entry's,
not the drug's: epinephrine is signed in mg for IM and arrest, in mcg for the
push dose. The canonical GIVE line ("Draw X mL of Y mg/mL drug (Z mg)") is the
pipeline's own instructed mg format and is not read here.
"""
import openai_client as oc

B1_QUERY = "80 kg adult, severe pain from a femur fracture, fentanyl IV"
EPI_QUERY = "70kg, anaphylaxis, epinephrine IM"
DEX_QUERY = "soldier collapsed, sugar 32, dextrose IV"


def _issues(query, weight, text):
    ctx = oc.PatientContext(confirmed_weight_kg=weight)
    allowed = oc.build_allowed_doses(query, ctx)
    return oc.free_text_dose_issues(text, allowed, ctx, query)


def _unit_issue(issues, drug):
    return [i for i in issues if i.startswith(f"The answer stated {drug}") and "written in" in i]


# ── the gap: the signed value in another unit ────────────────────────────────

def test_fentanyl_in_mg_for_a_mcg_signed_dose_holds():
    issues = _issues(B1_QUERY, 80.0, "**DO THIS**\n2. Draw 0.05 mg of fentanyl IV. Indication: acute pain / analgesia.")
    assert _unit_issue(issues, "fentanyl"), issues


def test_both_units_side_by_side_hold():
    issues = _issues(B1_QUERY, 80.0, "**DO THIS**\n2. Draw 50 mcg (0.05 mg) of fentanyl IV.")
    assert _unit_issue(issues, "fentanyl"), issues


def test_epinephrine_push_dose_in_mg_holds():
    issues = _issues(EPI_QUERY, 70.0, "**DO THIS**\n1. Push-dose epinephrine 0.01 mg IV.")
    assert _unit_issue(issues, "epinephrine"), issues


def test_dextrose_in_mg_for_a_gram_signed_dose_holds():
    issues = _issues(DEX_QUERY, 80.0, "**DO THIS**\n1. Give dextrose 25000 mg IV.")
    assert _unit_issue(issues, "dextrose"), issues


def test_the_hold_names_the_unit_not_the_signed_number():
    (issue,) = _unit_issue(_issues(B1_QUERY, 80.0, "**DO THIS**\n2. Draw 0.05 mg of fentanyl IV."), "fentanyl")
    assert "mcg" in issue and "50" not in issue   # owner ruling 12: no signed number in a hold


def test_the_whole_pipeline_check_holds_it():
    ctx = oc.PatientContext(confirmed_weight_kg=80.0)
    allowed = oc.build_allowed_doses(B1_QUERY, ctx)
    det = oc.run_deterministic_checks(B1_QUERY, "**DO THIS**\n2. Draw 0.05 mg of fentanyl IV.",
                                      ctx, allowed, current_query=B1_QUERY)
    assert not det.passed and _unit_issue(det.issues, "fentanyl"), det.issues


# ── guards: what must not change ─────────────────────────────────────────────

def test_b1_slip_still_holds_by_value():
    issues = _issues(B1_QUERY, 80.0, "**DO THIS**\n2. Draw 50 mcg of fentanyl IV (50 mg). Indication: acute pain / analgesia.")
    assert any("fentanyl 50 mg, which is not the signed fentanyl dose" in i for i in issues), issues


def test_signed_units_pass():
    assert _issues(B1_QUERY, 80.0, "**DO THIS**\n2. Draw 50 mcg of fentanyl IV.") == []
    assert _issues(B1_QUERY, 80.0, "**GIVE**\n- fentanyl IV: 50 mcg. NO VOLUME — confirm concentration to compute volume.") == []
    assert _issues(EPI_QUERY, 70.0, "**DO THIS**\n1. Epinephrine 0.3 mg IM, anterolateral thigh.") == []
    assert _issues(EPI_QUERY, 70.0, "**DO THIS**\n1. Push-dose epinephrine 10 mcg IV.") == []
    assert _issues(DEX_QUERY, 80.0, "**DO THIS**\n1. Give dextrose 25 g IV.") == []


def test_a_per_kg_dose_in_the_signed_unit_passes():
    assert _issues(B1_QUERY, 80.0, "**DO THIS**\n1. Fentanyl IN 1 mcg/kg.") == []


def test_a_per_kg_dose_in_another_unit_holds():
    issues = _issues(B1_QUERY, 80.0, "**DO THIS**\n1. Fentanyl IN 0.001 mg/kg.")
    assert _unit_issue(issues, "fentanyl"), issues


def test_the_canonical_give_line_is_not_read():
    text = "**GIVE**\n- Draw 2 mL of 1000mg/mL tranexamic acid IV (2000 mg)."
    issues = _issues("80 kg, TXA for hemorrhagic shock", 80.0, text)
    assert not _unit_issue(issues, "tranexamic acid"), issues
