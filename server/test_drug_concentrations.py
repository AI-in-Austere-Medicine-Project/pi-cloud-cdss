"""
Concentration master list — the fail-closed rule, the guardrails, the gate.

THE HAZARD THIS CLOSES
──────────────────────
Production emitted "Draw 7.1 mL of 20mg/mL succinylcholine IV (142mg)" from a
literal `/ 20.0` in the code. A deployment stocking the WHO/austere strength of
50 mg/mL would draw 7.1 mL of THAT: 355 mg, two and a half times the intended
dose, of a depolarising paralytic, during RSI. The served text carried a
hardcoded "validator_result": "SAFE" and no check anywhere looked at the
millilitre.

Every test below is a piece of that failure made impossible.

NOTHING IN drug_concentrations.json IS SIGNED, so the shipped state is: no
volume is served for any drug. The tests that need a volume sign a synthetic
presentation locally.
"""
import copy
import json

import pytest

import drug_concentrations as dcn
import openai_client as oc
from openai_client import PatientContext


def _sign(pres, by="clinician", date="2026-08-25"):
    return dict(pres, signoff=True, reviewed_by=by, review_date=date)


@pytest.fixture
def signed_ketamine(monkeypatch):
    """Ketamine at 50 mg/mL only — one signed vial, no ambiguity."""
    entries = copy.deepcopy(dcn.ENTRIES)
    entries["ketamine"]["confirm_required"] = False
    entries["ketamine"]["presentations"] = [
        _sign(p) for p in entries["ketamine"]["presentations"]
        if p["concentration_mg_ml"] == 50.0]
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    return entries


@pytest.fixture
def ambiguous_ketamine(monkeypatch):
    """Both vials signed — the system must not pick one."""
    entries = copy.deepcopy(dcn.ENTRIES)
    entries["ketamine"]["presentations"] = [
        _sign(p) for p in entries["ketamine"]["presentations"]]
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    return entries


# ═══════════════════════════════════════════════════════════════════════════
# THE CORE RULE: NO VOLUME WITHOUT A CONFIRMED CONCENTRATION
# ═══════════════════════════════════════════════════════════════════════════

def test_the_shipped_list_is_entirely_unsigned():
    """Merging this must stop the volumes, not wait for a signature."""
    signed = [(n, p.get("label_text"))
              for n, e in dcn.ENTRIES.items()
              for p in e.get("presentations", [])
              if p.get("signoff") is not False]
    assert signed == [], f"presentations ship signed: {signed}"


def test_no_drug_serves_a_volume_as_shipped():
    for name in dcn.ENTRIES:
        assert dcn.volume_ml(name, 100.0) == (None, None)


def test_the_calculators_no_longer_carry_a_concentration():
    """The literals /100.0, /20.0, /10.0, /2.0 are gone.

    A calculator that still knew a concentration would be a second source of
    truth, and the second source is the one that goes stale.
    """
    for cand in (oc.ketamine_analgesia_iv(80), oc.ketamine_analgesia_im(80),
                 oc.ketamine_induction_iv(80, False),
                 oc.ketamine_post_intubation_iv(80),
                 oc.rocuronium_rsi(80, False), oc.succinylcholine_rsi(80, False),
                 oc.lorazepam_seizure(80)):
        assert cand.volume_ml is None, cand
        assert cand.concentration_mg_ml is None, cand
        assert cand.dose_mg > 0, "the milligram dose must be unaffected"


def test_no_concentration_literal_survives_in_the_source():
    """Grep-level guard. The next person to add a calculator must not
    reintroduce the pattern this module exists to remove."""
    src = (dcn._DIR / "openai_client.py").read_text()
    for literal in ("/ 100.0", "/ 20.0", "concentration_mg_ml=100.0",
                    "concentration_mg_ml=20.0", "concentration_mg_ml=10.0",
                    "concentration_mg_ml=2.0"):
        assert literal not in src, f"{literal!r} is back in openai_client.py"


def test_an_unconfirmed_drug_gives_milligrams_and_says_why():
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    doses = oc.build_allowed_doses("ketamine dose for analgesia IV", ctx)
    assert doses and all(d.volume_ml is None for d in doses)
    block = oc.build_allowed_dose_block(doses)
    assert "24 mg" in block
    assert oc.CONFIRM_CONCENTRATION_LINE in block
    assert "mL" not in block.split("NO VOLUME")[0].split("\n")[-1]


def test_a_signed_concentration_produces_a_volume(signed_ketamine):
    """The fence is a gate, not a wall — control for the refusals above."""
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    doses = oc.build_allowed_doses("ketamine dose for analgesia IV", ctx)
    d = next(x for x in doses if x.drug == "ketamine")
    assert d.dose_mg == 24.0
    assert d.concentration_mg_ml == 50.0
    assert d.volume_ml == 0.48                      # 24 mg / 50 mg/mL
    assert "Draw 0.48 mL of 50mg/mL" in oc.render_give_line(d)


def test_the_volume_moves_with_the_declared_concentration(monkeypatch):
    """The whole point: 142 mg is 7.1 mL at 20 mg/mL and 2.84 mL at 50.

    The old code baked 20 into the calculator, so the volume could not follow
    the vial. Now it can only come from the vial.
    """
    got = {}
    for conc in (20.0, 50.0):
        entries = copy.deepcopy(dcn.ENTRIES)
        entries["succinylcholine"]["presentations"] = [_sign({
            "label_text": "TEST", "mass_mg": conc, "volume_ml": 1.0,
            "concentration_mg_ml": conc})]
        monkeypatch.setattr(dcn, "ENTRIES", entries)
        got[conc] = dcn.volume_ml("succinylcholine", 142.0)[0]
    assert got[20.0] == 7.1
    assert got[50.0] == 2.84


# ═══════════════════════════════════════════════════════════════════════════
# SANE-RANGE VALIDATION — REJECTED VISIBLY, NOT STORED
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mass,vol,conc,fragment", [
    (0, 10, 0, "greater than zero"),
    (-5, 10, -0.5, "greater than zero"),
    (500, 10, 5.0, "must agree"),          # label says 50, field says 5
    (500, 10, 500.0, "must agree"),
    (50000, 10, 5000.0, "plausible range"),
])
def test_an_impossible_declaration_is_rejected(mass, vol, conc, fragment):
    pres = {"label_text": "TEST", "mass_mg": mass, "volume_ml": vol,
            "concentration_mg_ml": conc}
    reason = dcn._validate({"generic_name": "ketamine"}, pres)
    assert reason and fragment in reason, reason


def test_the_label_check_catches_a_transcription_slip():
    """Declaring the vial the way it is LABELLED is what makes this possible:
    500 mg in 10 mL is 50 mg/mL, and writing 5 is caught because two
    independently-entered numbers disagree."""
    reason = dcn._validate({"generic_name": "ketamine"},
                           {"label_text": "500 mg / 10 mL", "mass_mg": 500,
                            "volume_ml": 10, "concentration_mg_ml": 5.0})
    assert reason and "50 mg/mL" in reason


def test_a_decimal_slip_is_rejected_against_the_sourced_strengths():
    """WHO cites ketamine at 10 and 50 mg/mL. 500 is 10x every one of them —
    the shape of a misplaced decimal — so it is refused outright, not merely
    flagged."""
    assert dcn._sourced_strengths("ketamine") == [10.0, 50.0]
    reason = dcn._validate({"generic_name": "ketamine"},
                           {"label_text": "TEST", "mass_mg": 500,
                            "volume_ml": 1, "concentration_mg_ml": 500.0})
    assert reason and "decimal" in reason


def test_a_plausible_off_source_strength_is_flagged_not_rejected():
    """25 mg/mL is not a WHO-cited ketamine strength but is within an order of
    magnitude. Refusing it would stop a deployment declaring what it actually
    carries; storing it silently would lose the fact that no source backs it."""
    pres = {"label_text": "TEST", "mass_mg": 250, "volume_ml": 10,
            "concentration_mg_ml": 25.0}
    assert dcn._validate({"generic_name": "ketamine"}, pres) is None
    assert dcn._corroboration("ketamine", 25.0) == "OFF_SOURCE"


def test_an_off_source_strength_cannot_be_signed_without_justification():
    pres = _sign({"label_text": "TEST", "mass_mg": 250, "volume_ml": 10,
                  "concentration_mg_ml": 25.0, "corroboration": "OFF_SOURCE",
                  "justification": ""})
    reason = dcn._validate({"generic_name": "ketamine"}, pres)
    assert reason and "justification" in reason
    ok = dict(pres, justification="this is the vial we carry")
    assert dcn._validate({"generic_name": "ketamine"}, ok) is None


def test_a_rejection_is_visible_and_carries_its_reason():
    """Same discipline as an impossible vital: surfaced, never silently dropped."""
    r = dcn.ConcentrationRejection("ketamine", "TEST", "because")
    assert (r.generic_name, r.raw, r.reason) == ("ketamine", "TEST", "because")
    assert dcn.REJECTIONS == [], "the shipped list should have no rejections"


def test_rocuronium_is_marked_as_the_undefended_one():
    """No approved source lists rocuronium, so tier 2 cannot protect it. That
    has to be visible in the data rather than assumed by a reader."""
    assert dcn._sourced_strengths("rocuronium") == []
    pres = dcn.ENTRIES["rocuronium"]["presentations"][0]
    assert pres["corroboration"] == "NO_SOURCED_STRENGTH"
    assert pres["justification"], "an unsourced declaration must say why"


# ═══════════════════════════════════════════════════════════════════════════
# ASKING WHICH VIAL
# ═══════════════════════════════════════════════════════════════════════════

def test_two_signed_strengths_refuse_to_pick_one(ambiguous_ketamine):
    status, conc, _ = dcn.resolve("ketamine")
    assert status == dcn.NEEDS_CONFIRMATION and conc is None
    assert dcn.volume_ml("ketamine", 120.0) == (None, None)


def test_the_question_is_phrased_in_what_is_on_the_vial(ambiguous_ketamine):
    q = dcn.confirmation_question("ketamine")
    assert "500 mg / 10 mL vial" in q and "200 mg / 20 mL vial" in q
    assert "50 mg/mL" in q and "10 mg/mL" in q


def test_confirming_a_vial_resolves_the_volume(ambiguous_ketamine):
    assert dcn.resolve("ketamine", {"ketamine": 50.0})[1] == 50.0
    assert dcn.volume_ml("ketamine", 120.0, {"ketamine": 50.0}) == (2.4, 50.0)
    assert dcn.volume_ml("ketamine", 120.0, {"ketamine": 10.0}) == (12.0, 10.0)


@pytest.mark.parametrize("answer,expected", [
    ("500 mg / 10 mL", 50.0),
    ("the 500 in 10", 50.0),
    ("50 mg/mL", 50.0),
    ("200mg/20ml", 10.0),
    ("10 mg per mL", 10.0),
])
def test_an_answer_is_matched_to_a_declared_vial(ambiguous_ketamine, answer, expected):
    assert dcn.match_confirmation("ketamine", answer) == expected


@pytest.mark.parametrize("answer", ["75 mg/mL", "whatever we have", "", "yes"])
def test_a_concentration_that_is_not_declared_is_never_accepted(
        ambiguous_ketamine, answer):
    """THE boundary. Asking is disambiguation between signed presentations, not
    an input channel. A number typed under time pressure has no signoff, no
    validation and no audit trail — accepting one would reintroduce the hazard
    by a route with less protection than the one it replaced."""
    assert dcn.match_confirmation("ketamine", answer) is None


def test_the_ask_fires_only_when_it_can_change_the_answer(ambiguous_ketamine):
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    action, question = oc.pre_gate("ketamine dose for analgesia IV", ctx)
    assert action == "ASK" and "500 mg / 10 mL vial" in question


def test_the_ask_is_silent_while_nothing_is_signed():
    """Shipped state: there is nothing to choose between, so asking would be
    noise — the answer is milligrams either way."""
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    assert oc.pre_gate("ketamine dose for analgesia IV", ctx) == ("CONTINUE", None)


def test_the_ask_does_not_fire_before_a_weight(ambiguous_ketamine):
    """Weight gates the milligrams. A question about the vial is wasted on a
    turn that will not produce a dose at all."""
    ctx = PatientContext()
    action, question = oc.pre_gate("how much ketamine for pain", ctx)
    assert action != "ASK" or "vial" not in (question or "")


def test_a_confirmation_survives_the_next_turn(ambiguous_ketamine):
    ctx = oc.rebuild_patient_context_from_history(
        "500 mg / 10 mL",
        conversation_history=[{"query": "80kg male, ketamine dose for pain IV"}])
    assert ctx.confirmed_concentrations.get("ketamine") == 50.0


def test_a_bare_answer_attaches_to_the_drug_under_discussion(ambiguous_ketamine):
    """"50" names no drug. It has to land on what was asked about."""
    ctx = oc.rebuild_patient_context_from_history(
        "50", conversation_history=[{"query": "80kg male, ketamine for pain IV"}])
    assert ctx.confirmed_concentrations.get("ketamine") == 50.0


def test_a_stale_confirmation_asks_again_rather_than_serving_it(signed_ketamine):
    """The kit changed under an answer that is no longer one of the options."""
    status, conc, _ = dcn.resolve("ketamine", {"ketamine": 10.0})
    assert status == dcn.NEEDS_CONFIRMATION and conc is None


def test_a_new_patient_clears_the_confirmed_vial(ambiguous_ketamine):
    ctx = oc.rebuild_patient_context_from_history(
        "new patient, 70kg male",
        conversation_history=[{"query": "80kg male ketamine IV"},
                              {"query": "500 mg / 10 mL"}])
    assert ctx.confirmed_concentrations == {}


# ═══════════════════════════════════════════════════════════════════════════
# THE GATE: vol x conc == mg, AND conc IS THE DECLARED ONE
# ═══════════════════════════════════════════════════════════════════════════

def test_the_exact_production_hazard_is_caught_and_stripped():
    """The real line, from runs/discovery-v43: A1-WT-020."""
    text = ("**GIVE**\n- Draw 7.1 mL of 20mg/mL succinylcholine IV (142mg). "
            "Indication: RSI paralytic.\n")
    out, issues = oc.audit_volume_lines(text)
    assert issues, "the 20mg/mL succinylcholine line was served unchecked"
    assert "7.1 mL" not in out
    assert "142 mg" in out and oc.CONFIRM_CONCENTRATION_LINE in out


def test_a_volume_that_does_not_multiply_out_is_stripped(signed_ketamine):
    """24 mg at 50 mg/mL is 0.48 mL. 4.8 is a decimal slip, and it used to
    pass because nothing multiplied the numbers together."""
    text = "- Draw 4.8 mL of 50mg/mL ketamine IV (24mg). Indication: analgesia."
    out, issues = oc.audit_volume_lines(text)
    assert issues and "0.48 mL" in issues[0]
    assert "4.8 mL" not in out


def test_a_correct_volume_passes_untouched(signed_ketamine):
    text = "- Draw 0.48 mL of 50mg/mL ketamine IV (24mg). Indication: analgesia."
    out, issues = oc.audit_volume_lines(text)
    assert issues == [] and out == text


def test_a_concentration_the_kit_does_not_stock_is_stripped(signed_ketamine):
    """Internally consistent — 2.4 x 100 = 240 — but 100 mg/mL is not the vial."""
    text = "- Draw 2.4 mL of 100mg/mL ketamine IV (240mg). Indication: RSI."
    out, issues = oc.audit_volume_lines(text)
    assert issues and "not a declared concentration" in issues[0]
    assert "2.4 mL" not in out


def test_the_wrong_vial_is_stripped_even_if_it_is_declared(ambiguous_ketamine):
    """The medic confirmed 50 mg/mL. A line computed at 10 is arithmetically
    fine and still the wrong syringe."""
    ctx = PatientContext(confirmed_concentrations={"ketamine": 50.0})
    text = "- Draw 12 mL of 10mg/mL ketamine IV (120mg). Indication: RSI."
    out, issues = oc.audit_volume_lines(text, ctx)
    assert issues and "confirmed vial" in issues[0]
    assert "12 mL" not in out


def test_the_check_is_exact_at_the_printed_precision(signed_ketamine):
    """Not a 5% band. A percentage tolerance is wide enough to hide a real
    error in a small-volume push, which is where the pushes are."""
    ok = "- Draw 0.48 mL of 50mg/mL ketamine IV (24mg). Indication: x."
    off = "- Draw 0.49 mL of 50mg/mL ketamine IV (24mg). Indication: x."
    assert oc.audit_volume_lines(ok)[1] == []
    assert oc.audit_volume_lines(off)[1] != []


def test_a_recipe_is_not_a_prescription():
    """build_fixed_prep_response describes how to MAKE a dilution — its mL is
    not a patient dose and must not be audited as one."""
    recipe = oc.build_fixed_prep_response("how do I mix push dose epi")
    assert recipe and "Draw 1 mL" in recipe
    out, issues = oc.audit_volume_lines(recipe)
    assert issues == [] and out == recipe


# ═══════════════════════════════════════════════════════════════════════════
# PATH A NO LONGER STAMPS ITSELF SAFE
# ═══════════════════════════════════════════════════════════════════════════

def test_no_deterministic_return_claims_SAFE():
    """A deterministic path may skip the LLM validator. It may not claim to
    have passed it. There are eleven of these returns, not the three template
    builders — which is why the fix is the label and the choke point, not a
    patch at three call sites."""
    src = (dcn._DIR / "openai_client.py").read_text().split("\n")
    for i, line in enumerate(src):
        if "DETERMINISTIC_PRE_GATE" in line:
            window = "\n".join(src[i:i + 4])
            assert '"validator_result": "SAFE"' not in window, \
                f"line {i + 1} still stamps itself SAFE"


def test_the_deterministic_templates_are_relabelled():
    src = (dcn._DIR / "openai_client.py").read_text()
    assert src.count('"validator_result": "DETERMINISTIC_CHECKED"') >= 7


def test_finalise_strips_a_bad_volume_on_a_gate_bypassing_path():
    """The end-to-end shape of the original bug: a deterministic template
    returning a wrong volume with a SAFE stamp, now caught at the one place
    every path goes through."""
    result = {"response": "**GIVE**\n- Draw 7.1 mL of 20mg/mL succinylcholine "
                          "IV (142mg). Indication: RSI paralytic.\n",
              "source_mode": "DETERMINISTIC_PRE_GATE",
              "validator_result": "DETERMINISTIC_CHECKED",
              "validator_issues": []}
    out = oc._finalise(result, PatientContext())
    assert "7.1 mL" not in out["response"]
    assert out["validator_result"] == "NEEDS_HUMAN_REVIEW"
    assert out["validator_issues"]
    assert "could not be verified" in out["response"]


def test_finalise_never_escalates_to_a_block():
    """_finalise may downgrade; it may not introduce UNSAFE. The dangerous
    number is already gone from the text."""
    result = {"response": "- Draw 7.1 mL of 20mg/mL succinylcholine IV (142mg).",
              "source_mode": "DETERMINISTIC_PRE_GATE",
              "validator_result": "DETERMINISTIC_CHECKED", "validator_issues": []}
    out = oc._finalise(result, PatientContext())
    assert out["validator_result"] != "UNSAFE"


def test_a_block_stays_blocked():
    result = {"response": "- Draw 7.1 mL of 20mg/mL succinylcholine IV (142mg).",
              "source_mode": "DETERMINISTIC_PRE_GATE",
              "validator_result": "UNSAFE", "validator_issues": []}
    out = oc._finalise(result, PatientContext())
    assert out["validator_result"] == "UNSAFE"


def test_the_rsi_template_emits_no_volume_while_unsigned():
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    text = oc.build_rsi_response(ctx, "rsi now")
    assert "mL of" not in text
    assert "120 mg" in text and oc.CONFIRM_CONCENTRATION_LINE in text


def test_the_tldr_degrades_with_the_give_line():
    """A TLDR still saying "= 1.2mL of 100mg/mL" under a refused GIVE line
    would be the only number on the screen."""
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    text = oc.build_ketamine_analgesia_response(ctx)
    tldr = text.split("**TLDR**")[1]
    assert "mL" not in tldr.split("Volume not computed")[0]


# ═══════════════════════════════════════════════════════════════════════════
# THE WHO / AUSTERE DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("drug,conc", [
    ("ketamine", 50.0),
    ("succinylcholine", 50.0),
    ("rocuronium", 10.0),
    ("lorazepam", 2.0),
    ("epinephrine", 1.0),
    ("tranexamic acid", 100.0),
    ("naloxone", 0.4),
    ("calcium gluconate", 100.0),
])
def test_the_deployment_defaults_are_declared_but_unsigned(drug, conc):
    """Declared as a draft the owner signs, not as another hardcode."""
    concs = [p["concentration_mg_ml"]
             for p in dcn.ENTRIES[drug]["presentations"]]
    assert conc in concs, f"{drug} does not declare {conc} mg/mL"
    assert dcn.signed_presentations(drug) == []


def test_the_austere_strengths_replace_the_old_hardcodes():
    """The point of the exercise: ketamine 100 -> 50, succinylcholine 20 -> 50."""
    assert 50.0 in [p["concentration_mg_ml"]
                    for p in dcn.ENTRIES["ketamine"]["presentations"]]
    assert 100.0 not in [p["concentration_mg_ml"]
                         for p in dcn.ENTRIES["ketamine"]["presentations"]]
    sux = [p["concentration_mg_ml"]
           for p in dcn.ENTRIES["succinylcholine"]["presentations"]]
    assert sux == [50.0], f"succinylcholine still declares {sux}"


def test_every_declaration_is_labelled_the_way_the_vial_is():
    for name, entry in dcn.ENTRIES.items():
        for p in entry["presentations"]:
            assert p["mass_mg"] > 0 and p["volume_ml"] > 0, f"{name}"
            assert abs(p["mass_mg"] / p["volume_ml"]
                       - p["concentration_mg_ml"]) < 1e-6, f"{name}"
            assert "mL" in (p.get("label_text") or ""), \
                f"{name}: label should read like the vial"


def test_multi_strength_drugs_ship_asking():
    """WHO lists morphine at three strengths and midazolam at two. Neither can
    serve a volume until someone says which vial."""
    for drug in ("morphine", "midazolam", "ketamine"):
        assert dcn.ENTRIES[drug].get("confirm_required") is True, drug


# ═══════════════════════════════════════════════════════════════════════════
# SIGNOFF AND THE CHANGE LOG
# ═══════════════════════════════════════════════════════════════════════════

def test_signing_needs_an_authorised_signer():
    pres = {"label_text": "TEST", "mass_mg": 500, "volume_ml": 10,
            "concentration_mg_ml": 50.0}
    assert not dcn.presentation_is_signed(dict(pres, signoff=True,
                                               reviewed_by="nobody",
                                               review_date="2026-08-25"))
    assert not dcn.presentation_is_signed(dict(pres, signoff=True,
                                               reviewed_by="clinician",
                                               review_date=dcn.PENDING))
    assert dcn.presentation_is_signed(dict(pres, signoff=True,
                                           reviewed_by="clinician",
                                           review_date="2026-08-25"))


def test_revoking_degrades_to_milligrams_rather_than_to_a_wrong_volume(monkeypatch):
    """The asymmetry that matters. Pulling a concentration is always safe;
    that is why it needs no signature, and why the kit changing mid-deployment
    cannot leave a stale volume being served."""
    entries = copy.deepcopy(dcn.ENTRIES)
    entries["succinylcholine"]["presentations"] = [
        _sign(entries["succinylcholine"]["presentations"][0])]
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    assert dcn.volume_ml("succinylcholine", 100.0)[0] is not None

    entries["succinylcholine"]["presentations"][0]["signoff"] = False
    assert dcn.volume_ml("succinylcholine", 100.0) == (None, None)


def test_the_change_log_records_old_and_new(tmp_path, monkeypatch):
    monkeypatch.setattr(dcn, "CHANGE_LOG", tmp_path / "conc.log.jsonl")
    dcn.append_log({"event": "SIGN", "drug": "ketamine", "label": "TEST",
                    "old": [50.0, False], "new": [50.0, True],
                    "actor": "clinician"})
    rec = json.loads((tmp_path / "conc.log.jsonl").read_text().strip())
    assert rec["event"] == "SIGN" and rec["old"] == [50.0, False]
    assert rec["new"] == [50.0, True] and rec["ts"]
    assert rec["kit_id"] == dcn.kit_id()


def test_a_hand_edit_is_detected_and_logged(tmp_path, monkeypatch):
    """The most likely way to edit a JSON file is to open it in an editor. A
    change log that the most likely editing method bypasses is not a log."""
    log = tmp_path / "conc.log.jsonl"
    monkeypatch.setattr(dcn, "CHANGE_LOG", log)
    dcn.detect_external_edit()                       # baseline
    entries = copy.deepcopy(dcn.ENTRIES)
    entries["ketamine"]["presentations"][0]["concentration_mg_ml"] = 10.0
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    monkeypatch.setattr(dcn, "_config_hash", lambda: "changed-hash")

    diffs = dcn.detect_external_edit()
    assert diffs, "an external edit went unlogged"
    recs = [json.loads(l) for l in log.read_text().strip().split("\n")]
    assert recs[-1]["event"] == "DETECTED_EXTERNAL_EDIT"
    changed = recs[-1]["changes"][0]
    assert changed["old"][0] == 50.0 and changed["new"][0] == 10.0


def test_an_unwritable_log_does_not_fail_a_clinical_request(monkeypatch):
    monkeypatch.setattr(dcn, "CHANGE_LOG",
                        dcn.pathlib.Path("/proc/nonexistent/conc.log.jsonl"))
    dcn.append_log({"event": "SIGN"})                # must not raise


# ═══════════════════════════════════════════════════════════════════════════
# THE RSI TLDR NAMES THE DRUG THAT WAS ACTUALLY SELECTED
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("query,expected,absent", [
    ("rsi now sux", "succinylcholine", "rocuronium"),
    ("succinylcholine dose for RSI", "succinylcholine", "rocuronium"),
    ("rsi now", "rocuronium", "succinylcholine"),
    ("RSI with a crush injury, which paralytic", "rocuronium", "succinylcholine"),
])
def test_the_rsi_tldr_names_the_paralytic_actually_given(query, expected, absent):
    """The TLDR used to say "rocuronium second" unconditionally.

    It is the line a medic reads when they read nothing else, and it named a
    drug the GIVE block had not given. A summary that contradicts the body is
    worse than no summary: the body is right and the summary is the part that
    gets remembered.
    """
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    text = oc.build_rsi_response(ctx, query)
    tldr = [l for l in text.split("\n") if l.startswith("- RSI:")][0]
    assert expected in tldr, tldr
    assert absent not in tldr, tldr


def test_the_rsi_tldr_agrees_with_its_own_give_block():
    """Stronger than the parametrised case: whatever the GIVE block chose, the
    TLDR must name that, with no list of which drug goes with which query."""
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    for query in ("rsi now sux", "rsi now", "RSI, he has a crush injury",
                  "rapid sequence intubation doses", "RSI succs please"):
        text = oc.build_rsi_response(ctx, query)
        give = text.split("**GIVE**")[1].split("**POST-INTUBATION")[0]
        tldr = [l for l in text.split("\n") if l.startswith("- RSI:")][0]
        for paralytic in ("succinylcholine", "rocuronium"):
            assert (paralytic in give) == (paralytic in tldr), \
                f"{query!r}: GIVE and TLDR disagree about {paralytic}"


# ═══════════════════════════════════════════════════════════════════════════
# THE PROMPT NO LONGER TEACHES THE MODEL STALE CONCENTRATIONS
# ═══════════════════════════════════════════════════════════════════════════

def test_the_prompt_states_no_concentration_at_all():
    """The system prompt used to carry a STANDARD CONCENTRATIONS table listing
    ketamine 100mg/mL, succinylcholine 20mg/mL, rocuronium 10mg/mL — the exact
    hardcodes the master list replaced.

    _finalise would strip a volume built from them, so it was not a live
    hazard. It was a second source of truth being fed to the model, which is
    the class of bug the master list exists to remove — and the stripped-volume
    path is a worse way to find that out than never saying it.
    """
    prompt = oc.GENERATOR_BASE
    assert "STANDARD CONCENTRATIONS" not in prompt
    for stale in ("100mg/mL", "20mg/mL", "10mg/mL", "50mcg/mL", "16mcg/mL"):
        assert stale not in prompt, f"the prompt still asserts {stale}"


def test_the_prompt_tells_the_model_it_does_not_know_concentrations():
    prompt = oc.GENERATOR_BASE
    assert "You do not know any drug concentration" in prompt
    assert "NO VOLUME" in prompt


def test_the_response_format_shows_the_no_volume_shape():
    """The model needs the mg-only line as a FORM it can produce, not only as
    a prohibition on the other one."""
    give_block = oc.GENERATOR_BASE.split("**GIVE**")[1][:400]
    assert "Draw X mL of Y mg/mL" in give_block
    assert "NO VOLUME" in give_block
