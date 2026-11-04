"""Med sweep 2026-10-30, PR 3: parser and withheld.

Owner, 2026-10-30: "PR 3 (parser and withheld): glucose values never read as
temperature; midazolam indication list includes procedural sedation;
"intranasal"/"IN" is a route; "fighting us"/"combative"/"kicking our ass" ->
agitation; atropine nerve-agent escalation within the signed 16 mg; calcium
with no salt asks "chloride or gluconate?". Brief tidy: no contradictory
"NO VOLUME" beside a volume line, no extra ranges, no "confirm concentration"
for tablets."

Owner, 2026-11-03 (found in PR 1, folded in here): "signed infusion entries
enter the allowed list as rates (per-kg/min or per-kg/hr with the signed
range), and a correct signed infusion line serves; a bolus for an infusion
question still holds."

Each test is a sweep row: the question the sweep asked the live service
(a7c9043, Offline mode, qwen2.5:3b) and, where a model wrote it, the text it
wrote, run through this tree.

    cd server && ./run_unit_tests.sh
"""
import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402
import providers  # noqa: E402
import vitals as v  # noqa: E402


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture
def card_only(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("this row called a model")
    monkeypatch.setattr(providers, "chat", _refuse)


@pytest.fixture
def model_says(monkeypatch):
    """The generator writes `text`; the validator says SAFE, so what is held
    is held by the deterministic checks."""
    def _set(text):
        monkeypatch.setattr(providers, "chat", lambda *a, **k: (
            '{"result":"SAFE","issues":[],"rationale":"stub"}'
            if "Clinical Safety Validator" in (a[0] if a else "") else text))
    return _set


def run(q, history=None):
    return oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=history or [])


def _ctx(q):
    return oc.rebuild_patient_context_from_history(q)


def _issues(q, text):
    ctx = _ctx(q)
    doses = oc.build_allowed_doses(q, ctx)
    return oc.run_deterministic_checks(q, text, ctx, doses, current_query=q).issues


def _held(r):
    return r["response"].startswith("Clinical safety hold")


def _section(text, head):
    assert f"**{head}**" in text, text
    return text.split(f"**{head}**")[1].split("\n**", 1)[0]


# ── dextrose[0][1][2]: a glucose is never read as a temperature ─────────────

@pytest.mark.parametrize("text", ["glucose 2.1", "glucose 1.8", "sugar 2000"])
def test_a_glucose_rejection_never_says_temperature(text):
    _readings, rejections = v.parse_vitals(text, ts=None)
    assert [r.name for r in rejections] == ["glucose"], rejections
    assert "temperature" not in rejections[0].reason.lower(), rejections[0].reason
    assert "glucose" in rejections[0].reason.lower()


def test_the_dextrose_row_notice_says_glucose_not_temperature(card_only, monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: (
        '{"result":"SAFE","issues":[],"rationale":"stub"}'
        if "Clinical Safety Validator" in (a[0] if a else "") else "STUB"))
    r = run("80 kg adult, hypoglycaemic, glucose 2.1, not alert, dextrose IV")
    assert "temperature" not in r["response"].lower(), r["response"][:300]


# ── midazolam[2][7]: procedural sedation is an indication ───────────────────

def test_procedural_sedation_is_a_stated_indication():
    assert "procedural sedation" in oc.stated_indication_classes(
        "80 kg adult, procedural sedation for a shoulder reduction, midazolam IV")


def test_midazolam_procedural_sedation_is_not_asked_which_indication(model_says):
    model_says("STUB")
    r = run("80 kg adult, procedural sedation for a shoulder reduction, midazolam IV")
    assert not r["response"].startswith(oc.INDICATION_QUESTION_PREFIX), r["response"]


def test_midazolam_procedural_sedation_offers_the_procedural_entry():
    q = "80 kg adult, procedural sedation for a shoulder reduction, midazolam IV"
    doses = oc.build_allowed_doses(q, _ctx(q))
    first = [d for d in doses if d.drug == "midazolam"][0]
    assert first.indication == "procedural sedation", [d.indication for d in doses]


def test_the_midazolam_indication_question_offers_procedural_sedation():
    q = "80 kg adult, midazolam IV"
    ask = oc.which_indication_question(q, _ctx(q))
    assert ask and "procedural sedation" in ask, ask


# ── ketamine[18], midazolam[7]: "intranasal" / "IN" is a route ─────────────

@pytest.mark.parametrize("q", [
    "80 kg adult, prolonged field care, breakthrough pain, ketamine intranasal",
    "80 kg adult, breakthrough pain, ketamine IN",
    "80 kg adult, breakthrough pain, give ketamine intranasally",
])
def test_intranasal_is_a_route(q):
    assert _ctx(q).route_preference == "IN", q


@pytest.mark.parametrize("q", [
    "80 kg adult, pain in the leg, ketamine",
    "80 KG ADULT IN PAIN, KETAMINE",
    "80 kg adult, nasal fracture, severe pain, ketamine",
])
def test_the_word_in_and_a_nasal_injury_are_not_a_route(q):
    assert _ctx(q).route_preference != "IN", q


def test_ketamine_intranasal_is_not_asked_iv_or_im(model_says):
    model_says("STUB")
    r = run("80 kg adult, prolonged field care, breakthrough pain, ketamine intranasal")
    assert not r["response"].startswith("IV or IM?"), r["response"]


def test_ketamine_intranasal_offers_the_signed_in_entry_only():
    q = "80 kg adult, prolonged field care, breakthrough pain, ketamine intranasal"
    doses = [d for d in oc.build_allowed_doses(q, _ctx(q)) if d.drug == "ketamine"]
    assert doses and {d.route for d in doses} == {"IN"}, [(d.route, d.indication) for d in doses]


def test_midazolam_intranasal_child_procedural_sedation_offers_the_in_entry(model_says):
    q = "20 kg 6 year old, needs procedural sedation for a reduction, midazolam intranasal"
    model_says("STUB")
    r = run(q)
    assert not r["response"].startswith(oc.INDICATION_QUESTION_PREFIX), r["response"]
    doses = [d for d in oc.build_allowed_doses(q, _ctx(q)) if d.drug == "midazolam"]
    assert doses and {d.route for d in doses} == {"IN"}, [(d.route, d.indication) for d in doses]
    assert doses[0].indication == "procedural / conscious sedation"


# ── T1: "fighting us" / "combative" / "kicking our ass" is agitation ───────

@pytest.mark.parametrize("q", [
    "this guy's fighting us, 250 lb, ketamine IM",
    "80 kg adult, combative, ketamine IM",
    "he's kicking our ass, 90 kg, ketamine IM",
    "patient is fighting the crew, 80 kg, ketamine IM",
])
def test_agitation_slang_states_agitation(q):
    assert "agitation" in oc.stated_indication_classes(q), q


def test_fighting_us_is_not_asked_which_indication(model_says):
    model_says("STUB")
    r = run("this guy's fighting us, 250 lb, ketamine IM")
    assert not r["response"].startswith(oc.INDICATION_QUESTION_PREFIX), r["response"]


def test_fighting_words_that_are_not_a_patient_are_not_agitation():
    assert "agitation" not in oc.stated_indication_classes(
        "80 kg adult, fighting position, GSW to the leg, severe pain")


# ── atropine[3]: the nerve-agent escalation, within the signed 16 mg ───────

ATROPINE_Q = "80 kg adult, nerve agent exposure, severe secretions, escalating doses, atropine IV"
ATROPINE_ESCALATION = (
    "**GIVE**\n"
    "- atropine IV: 2 mg. Indication: nerve agent poisoning — escalating IV/IO bolus.\n"
    "- If secretions persist, double the dose every 5 minutes: 4 mg, then 8 mg, then 16 mg.\n")


def test_the_signed_nerve_agent_escalation_serves():
    issues = _issues(ATROPINE_Q, ATROPINE_ESCALATION)
    assert issues == [], issues


def test_a_dose_line_that_gives_the_ceiling_as_the_dose_holds():
    """Found in this PR's replay (live, 2026-10-30): the steps escalated 2, 4,
    8, 16 mg, and the GIVE line gave 16 mg under the escalation's label."""
    text = ("**DO THIS**\n1. Administer atropine IV: 2 mg.\n2. Administer atropine IV: 4 mg.\n"
            "3. Administer atropine IV: 8 mg.\n4. Administer atropine IV: 16 mg.\n\n"
            "**GIVE**\n- Atropine IV: 16 mg. Indication: nerve agent poisoning — escalating "
            "IV/IO bolus.\n")
    issues = _issues(ATROPINE_Q, text)
    assert any("16 mg" in i for i in issues), issues
    assert _issues(ATROPINE_Q, text.replace("- Atropine IV: 16 mg.", "- Atropine IV: 2 mg.")) == []


def test_an_escalation_past_the_signed_16_mg_holds():
    text = ATROPINE_ESCALATION.replace("then 16 mg.", "then 16 mg, then 32 mg.")
    issues = _issues(ATROPINE_Q, text)
    assert any("32" in i for i in issues), issues


def test_an_escalation_step_that_is_not_a_doubling_holds():
    text = ATROPINE_ESCALATION.replace("4 mg, then 8 mg", "6 mg, then 8 mg")
    issues = _issues(ATROPINE_Q, text)
    assert any("6 mg" in i for i in issues), issues


def test_the_escalation_is_not_a_bradycardia_dose():
    q = "80 kg adult, symptomatic bradycardia, HR 38, atropine IV"
    issues = _issues(q, "**GIVE**\n- atropine IV: 4 mg. Indication: symptomatic bradycardia.\n")
    assert any("atropine" in i for i in issues), issues


# ── T9: calcium with no salt asks which salt ────────────────────────────────

def test_calcium_with_no_salt_asks_chloride_or_gluconate(card_only):
    r = run("calcium after 4 units of blood")
    assert r["response"] == oc.CALCIUM_SALT_ASK, r["response"][:300]
    assert "chloride" in oc.CALCIUM_SALT_ASK and "gluconate" in oc.CALCIUM_SALT_ASK


@pytest.mark.parametrize("q", [
    "calcium chloride after 4 units of blood",
    "80 kg adult, massive transfusion, ionized calcium is low, what next",
    "check a calcium level",
])
def test_a_named_salt_or_a_calcium_level_is_not_asked(q, model_says):
    model_says("STUB")
    r = run(q)
    assert r["response"] != oc.CALCIUM_SALT_ASK, q


def test_the_salt_answer_carries_the_request(card_only):
    first = "calcium after 4 units of blood"
    hist = [{"query": first, "response": oc.CALCIUM_SALT_ASK}]
    r = run("chloride", hist)
    # No age yet: the fixed adult dose waits for an adult, as #181 rules.
    assert r["response"].startswith(oc.ADULT_CONFIRM_ASK), r["response"][:300]
    assert "calcium chloride" in oc.drug_contracts.resolve_drugs(
        oc.scope_request("chloride", first, oc.CALCIUM_SALT_ASK)[1])


# ── Brief tidy ──────────────────────────────────────────────────────────────

# The vial is named: the sweep's kit served its one ketamine vial, and a
# kit file with more than one asks which.
KETAMINE6_Q = ("20 kg 6 year old, combative, need dissociative sedation, ketamine IV, "
               "500 mg / 10 mL vial")
KETAMINE6_SERVED = (
    "**BRIEF**\n"
    "- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg) (kit vial). Indication: agitated or "
    "violent patient — dissociative sedation.\n"
    "- Ketamine IV: 20 mg. NO VOLUME — confirm concentration to compute volume. "
    "Indication: agitated or violent patient — dissociative sedation.\n\n"
    "**DO THIS**\n1. Administer ketamine IV.\n2. Monitor for adverse reactions.\n\n"
    "**GIVE**\n"
    "- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg) (kit vial). Indication: agitated or "
    "violent patient — dissociative sedation.\n")


def test_no_no_volume_line_beside_a_volume_line(model_says):
    model_says(KETAMINE6_SERVED)
    r = run(KETAMINE6_Q)
    assert not _held(r), r["response"][:400]
    assert "NO VOLUME" not in r["response"], r["response"]
    assert "Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)" in _section(r["response"], "BRIEF")


NALOXONE2_Q = "20 kg 6 year old, opioid overdose, RR 6, naloxone IV"
NALOXONE2_SERVED = (
    "**BRIEF**\n"
    "- Draw 5 mL of 0.4mg/mL naloxone IV (2 mg).\n"
    "- Reversal of respiratory depression with therapeutic opioid doses: 0.001-0.015 "
    "mg/kg/dose; repeat as needed.\n\n"
    "**DO THIS**\n1. Reassess respiratory rate.\n2. Administer naloxone IV.\n\n"
    "**GIVE**\n"
    "- Draw 5 mL of 0.4mg/mL naloxone IV (2 mg). Indication: opioid-induced "
    "respiratory depression.\n")


def test_the_sweeps_extra_range_now_holds(model_says):
    """Served SAFE live: "mg/kg/dose" was read as neither a dose nor a rate.
    It is a dose now, and not naloxone's signed one."""
    model_says(NALOXONE2_SERVED)
    r = run(NALOXONE2_Q)
    assert _held(r) and "0.001-0.015 mg/kg" in r["response"], r["response"][:400]


def test_no_extra_range_in_the_brief():
    """A range the check let through (every value signed) is still not the
    brief's: the brief carries the dose lines."""
    q = NALOXONE2_Q
    doses = oc.build_allowed_doses(q, _ctx(q))
    text = ("**BRIEF**\n- Draw 5 mL of 0.4mg/mL naloxone IV (2 mg).\n"
            "- Naloxone 2-2 mg IV, repeat as needed.\n\n**GIVE**\n"
            "- Draw 5 mL of 0.4mg/mL naloxone IV (2 mg). Indication: opioid-induced "
            "respiratory depression.\n")
    out = oc.tidy_dose_lines(text, doses)
    assert "2-2 mg" not in out, out
    assert "Draw 5 mL of 0.4mg/mL naloxone IV (2 mg)." in _section(out, "BRIEF")


def test_a_signed_rate_in_the_brief_stays():
    ctx = _ctx(EPI6_Q)
    rates = oc.build_allowed_rates(EPI6_Q, ctx)
    line = oc.render_range_line(rates[0])
    text = f"**BRIEF**\n{line}\n\n**GIVE**\n{line}\n"
    assert oc.tidy_dose_lines(text, oc.build_allowed_doses(EPI6_Q, ctx), rates) == text


MOXI_Q = "80 kg adult, combat wound, can swallow, antibiotic prophylaxis, moxifloxacin PO"


def test_a_tablet_line_does_not_ask_for_a_concentration():
    q = MOXI_Q
    doses = [d for d in oc.build_allowed_doses(q, _ctx(q)) if d.drug == "moxifloxacin"]
    line = oc.render_give_line(doses[0])
    assert "400 mg" in line and "confirm concentration" not in line.lower(), line
    assert "NO VOLUME" not in line and "Draw" not in line, line


def test_a_tablet_answer_is_tidied(model_says):
    model_says(
        "**BRIEF**\n"
        "- moxifloxacin PO: 400 mg. NO VOLUME — confirm concentration to compute volume. "
        "Indication: combat wound prophylaxis (oral).\n\n"
        "**DO THIS**\n1. Administer moxifloxacin 400 mg PO.\n\n"
        "**GIVE**\n"
        "- Draw 400 mg of moxifloxacin PO (400 mg). Indication: combat wound prophylaxis (oral).\n")
    r = run(MOXI_Q)
    assert not _held(r), r["response"][:400]
    assert "confirm concentration" not in r["response"].lower(), r["response"]
    assert "Draw 400 mg" not in r["response"], r["response"]
    assert "moxifloxacin PO: 400 mg" in _section(r["response"], "GIVE")


def test_a_draw_line_with_no_volume_is_tidied(model_says):
    """propofol[0] on PR 2's branch: qwen wrote "Draw 40 mg of propofol IV (40 mg)"."""
    model_says(
        "**BRIEF**\n- Draw 40 mg of propofol IV (40 mg).\n\n"
        "**DO THIS**\n1. Draw 40 mg of propofol IV (40 mg).\n\n"
        "**GIVE**\n- Draw 40 mg of propofol IV (40 mg). Indication: induction of "
        "anaesthesia, hypotensive trauma patient (reduced dose).\n")
    r = run("80 kg adult, hypotensive trauma patient, need induction, propofol IV")
    assert not _held(r), r["response"][:400]
    assert "Draw 40 mg" not in r["response"], r["response"]
    assert "propofol IV: 40 mg" in _section(r["response"], "GIVE"), r["response"]
    assert "1. Give 40 mg of propofol IV (40 mg)." in r["response"], r["response"]


def test_an_extra_per_dose_range_holds():
    """Found on this PR's harness (qwen, live): the range moved from BRIEF to
    DO THIS. "mg/kg/dose" was read as neither a dose nor a rate."""
    text = NALOXONE2_SERVED.replace(
        "2. Administer naloxone IV.",
        "2. Administer naloxone 0.001-0.015 mg/kg/dose (up to 2 mg) IV.")
    issues = _issues(NALOXONE2_Q, text)
    assert any("0.001-0.015 mg/kg" in i for i in issues), issues


# ── The infusion ruling: a signed rate is an allowed dose ───────────────────

EPI6_Q = "80 kg adult, symptomatic bradycardia HR 35, atropine failed, infusion, epinephrine IV"


def test_signed_rates_enter_the_allowed_list():
    rates = oc.build_allowed_rates(EPI6_Q, _ctx(EPI6_Q))
    assert [(s.drug, s.indication) for s in rates] == [
        ("epinephrine", "symptomatic bradycardia — infusion")], rates
    assert "0.02-0.2 mcg/kg/min" in oc.render_range_line(rates[0])


def test_the_generator_is_offered_the_signed_rate():
    ctx = _ctx(EPI6_Q)
    block = oc.build_allowed_dose_block(oc.build_allowed_doses(EPI6_Q, ctx),
                                        oc.build_allowed_rates(EPI6_Q, ctx))
    assert "0.02-0.2 mcg/kg/min" in block, block
    assert "symptomatic bradycardia — infusion" in block


@pytest.mark.parametrize("q,line", [
    (EPI6_Q, "- epinephrine IV: 0.02-0.2 mcg/kg/min. Indication: symptomatic bradycardia — infusion."),
    ("80 kg adult, intubated, sedation infusion, propofol IV",
     "- propofol IV: 10-75 mcg/kg/min. Indication: sedation infusion."),
    ("80 kg adult, intubated, prolonged sedation infusion, ketamine IV",
     "- ketamine IV: 0.5-2 mg/kg/hr. Indication: prolonged sedation infusion."),
    ("80 kg adult, refractory shock, need an infusion, epinephrine IV",
     "- epinephrine IV: 2-10 mcg/min. Indication: infusion for refractory shock."),
])
def test_a_correct_signed_infusion_line_serves(q, line):
    issues = _issues(q, f"**GIVE**\n{line}\n")
    assert issues == [], issues


def test_a_correct_signed_infusion_line_serves_through_the_pipeline(model_says):
    model_says("**BRIEF**\n- epinephrine IV: 0.02-0.2 mcg/kg/min. Indication: symptomatic "
               "bradycardia — infusion.\n\n**DO THIS**\n1. Start the infusion.\n\n**GIVE**\n"
               "- epinephrine IV: 0.02-0.2 mcg/kg/min. Indication: symptomatic bradycardia — infusion.\n")
    r = run(EPI6_Q)
    assert not _held(r), r["response"][:500]


def test_a_bolus_for_an_infusion_question_still_holds():
    issues = _issues(EPI6_Q, "**GIVE**\n- epinephrine IV: 10 mcg. Indication: symptomatic "
                             "bradycardia — push dose.\n")
    assert any("epinephrine" in i for i in issues), issues


def test_a_rate_outside_the_signed_range_still_holds():
    issues = _issues(EPI6_Q, "**GIVE**\n- epinephrine IV: 0.5 mcg/kg/min. Indication: "
                             "symptomatic bradycardia — infusion.\n")
    assert any("epinephrine" in i for i in issues), issues


def test_another_indications_rate_still_holds():
    """Shock's 0.05-0.3 overlaps bradycardia's range: the label decides."""
    issues = _issues(EPI6_Q, "**GIVE**\n- epinephrine IV: 0.05-0.3 mcg/kg/min. Indication: "
                             "shock unresponsive to IV fluids — infusion.\n")
    assert any("epinephrine" in i for i in issues), issues


def test_a_child_gets_no_adult_rate():
    q = "20 kg 6 year old, intubated, sedation infusion, propofol IV"
    assert oc.build_allowed_rates(q, _ctx(q)) == []
