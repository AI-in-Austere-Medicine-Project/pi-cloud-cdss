"""Med sweep 2026-10-30, PR 1: wrong numbers served.

Owner, 2026-10-30: "From the 2026-10-30 med sweep. Hold M1. Three PRs in
order, each: failing test from the sweep row first, then fix ..."

Each test below is a sweep row: the question the sweep asked the live service
(a7c9043, Offline mode, qwen2.5:3b) and the text it served, run through this
tree's checks.

- calcium gluconate[2]: "mL/kg" volumes are checked like any mL.
- midazolam[8]: the brief's first line names the drug that was asked; and the
  0.5 mg (the prolonged-field-care entry) does not pass for post-intubation
  sedation.
- propofol[1], cefazolin[7], epinephrine[6]: A32 accepted a dose from another
  indication or form. Three gaps, closed generally:
    1. a class stated only by a generic word ("antibiotic", "prophylaxis",
       "intubated") yields to a class the question states specifically;
    2. inside one class, the entries whose label the question's words name
       are the ones accepted ("post-intubation", "background", "infusion");
    3. an infusion asked for accepts only the drug's infusion (and a loading
       dose), never a bolus, where the drug has a signed infusion for it.
- ketamine[12]: "background pain" / "prolonged field care pain" resolves to
  the PFC low-dose entry, not acute pain.

    cd server && ./run_unit_tests.sh
"""
import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brief  # noqa: E402
import openai_client as oc  # noqa: E402
import spoken  # noqa: E402


def _issues(history, text, vials=None):
    ctx = oc.rebuild_patient_context_from_history(history)
    ctx.confirmed_concentrations = dict(vials or {})
    doses = oc.build_allowed_doses(history, ctx)
    return oc.run_deterministic_checks(history, text, ctx, doses, current_query=history).issues


# ── calcium gluconate[2]: a per-kg volume is a volume ───────────────────────

CA_Q = "20 kg 6 year old, hyperkalaemia with peaked T waves, calcium gluconate IV"
CA_SERVED = ("**GIVE**\n- Calcium gluconate IV: 100 mg/kg (10 mL/kg of 10% solution). "
             "Indication: hyperkalaemia — membrane stabilisation.")


def test_calcium_gluconate_ml_per_kg_holds():
    """Served SAFE: 10 mL/kg of 10% is 200 mL at 20 kg, ten times the dose's
    volume, and calcium gluconate has no kit vial at all."""
    issues = _issues(CA_Q, CA_SERVED)
    assert any("calcium gluconate" in i and "mL" in i for i in issues), issues


def test_a_per_kg_volume_that_does_not_follow_from_the_vial_holds():
    """The 50 mg/mL vial confirmed: 0.25 mg/kg is 0.005 mL/kg, not 0.05."""
    q = "80 kg adult, femur fracture, severe pain, ketamine IV"
    text = ("**GIVE**\n- Ketamine IV: 0.25 mg/kg (0.05 mL/kg of 50 mg/mL). "
            "Indication: moderate to severe pain / analgesia.")
    issues = _issues(q, text, {"ketamine": 50.0})
    assert any("ketamine" in i and "mL" in i for i in issues), issues


def test_a_per_kg_volume_that_follows_from_the_vial_serves():
    q = "80 kg adult, femur fracture, severe pain, ketamine IV"
    text = ("**GIVE**\n- Ketamine IV: 0.25 mg/kg (0.005 mL/kg of 50 mg/mL). "
            "Indication: moderate to severe pain / analgesia.")
    assert _issues(q, text, {"ketamine": 50.0}) == []


def test_a_per_kg_volume_with_no_weight_holds():
    q = "adult, femur fracture, severe pain, ketamine IV"
    text = ("**GIVE**\n- Ketamine IV: 0.25 mg/kg (0.005 mL/kg of 50 mg/mL). "
            "Indication: moderate to severe pain / analgesia.")
    issues = _issues(q, text, {"ketamine": 50.0})
    assert any("ketamine" in i and "per kg" in i for i in issues), issues


# ── midazolam[8]: the asked drug leads; 0.5 mg is not post-intubation ───────

MID_Q = "80 kg adult, just intubated, post-intubation sedation, midazolam IV"
MID_SERVED = (
    "**BRIEF**  \n"
    "- Draw 0.8 mL of 50mg/mL ketamine IV (40 mg) (kit vial). Indication: post-intubation "
    "sedation — repeated bolus (no infusion pump).\n\n"
    "**DO THIS**  \n"
    "1. Administer midazolam IV: 0.5 mg. NO VOLUME — confirm concentration to compute volume. "
    "Indication: post-intubation sedation bolus.\n\n"
    "**GIVE**  \n"
    "- Draw 0.5 mg of midazolam IV (0.5 mg). Indication: post-intubation sedation bolus.\n")


def test_midazolam_half_a_milligram_holds_for_post_intubation_sedation():
    """0.5 mg is the "ongoing sedation (prolonged field care)" entry; the
    post-intubation bolus is 1-4 mg. Both labels are A32's one "sedation"
    class, so the check could not tell them apart."""
    issues = _issues(MID_Q, MID_SERVED)
    assert any("ongoing sedation (prolonged field care)" in i for i in issues), issues


TWO_DRUGS = (
    "**BRIEF**\n"
    "- Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — "
    "repeated bolus (no infusion pump).\n"
    "- midazolam IV: 2 mg. NO VOLUME — confirm concentration to compute volume. "
    "Indication: post-intubation sedation bolus.\n\n"
    "**GIVE**\n"
    "- Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — "
    "repeated bolus (no infusion pump).\n"
    "- midazolam IV: 2 mg. NO VOLUME — confirm concentration to compute volume. "
    "Indication: post-intubation sedation bolus.\n\n"
    "**WATCH**\n- RASS.\n")


def test_the_response_brief_section_leads_with_the_asked_drug():
    out = brief.asked_drug_leads(TWO_DRUGS, ["midazolam"])
    section = out.split("**BRIEF**")[1].split("**", 1)[0]
    first = [l for l in section.splitlines() if l.strip()][0]
    assert "midazolam" in first.lower(), section
    assert "ketamine" in section, "nothing is removed"


def test_a_brief_section_with_no_line_for_the_asked_drug_gets_its_give_line_first():
    out = brief.asked_drug_leads(MID_SERVED, ["midazolam"])
    section = out.split("**BRIEF**")[1].split("**", 1)[0]
    first = [l for l in section.splitlines() if l.strip()][0]
    assert first.startswith("- Draw 0.5 mg of midazolam IV (0.5 mg)."), section


def test_the_brief_and_the_spoken_brief_lead_with_the_asked_drug():
    r = oc.attach_brief({"response": TWO_DRUGS, "model": "qwen2.5:3b"}, query=MID_Q)
    first = r["brief"].splitlines()[0]
    assert "midazolam" in first.lower() and first.lower().index("midazolam") < (
        first.lower().index("ketamine") if "ketamine" in first.lower() else 10**6), r["brief"]
    said = r["spoken_brief"].lower()
    assert said.index("midazolam") < said.index("ketamine"), r["spoken_brief"]


def test_a_brief_whose_doses_never_name_the_asked_drug_says_so_first():
    text = ("**GIVE**\n- Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: "
            "post-intubation sedation — repeated bolus (no infusion pump).\n")
    r = oc.attach_brief({"response": text, "model": "qwen2.5:3b"}, query=MID_Q)
    assert r["brief"].splitlines()[0] == "No midazolam dose in this answer.", r["brief"]
    assert r["spoken_brief"].startswith("No midazolam dose in this answer."), r["spoken_brief"]


def test_no_asked_drug_leaves_the_order_alone():
    r = oc.attach_brief({"response": TWO_DRUGS, "model": "qwen2.5:3b"}, query="80 kg, intubated")
    assert r["brief"].lower().index("ketamine") < r["brief"].lower().index("midazolam")


# ── propofol[1]: an infusion asked, an induction bolus served ───────────────

PROP_Q = "80 kg adult, intubated, sedation infusion, propofol IV"
PROP_SERVED = ("**GIVE**\n- Draw 40 mg propofol IV (no volume) (40 mg). Indication: induction "
               "of anesthesia, hypotensive trauma patient (reduced dose).")


def test_propofol_induction_bolus_holds_for_a_sedation_infusion():
    issues = _issues(PROP_Q, PROP_SERVED)
    assert any("propofol" in i and "induction" in i for i in issues), issues


def _form_or_indication_holds(issues):
    """The holds this PR adds: A32's another-indication line and the bolus-for-
    an-infusion line. The label check (A1b) still holds a signed rate's own
    label, because rate entries are never built as doses: a separate finding,
    not this PR's (it would release)."""
    return [i for i in issues if "another indication" in i or "bolus" in i]


def test_the_signed_propofol_sedation_rate_is_not_held_as_another_form():
    text = ("**DRIP**\n- propofol IV infusion: 10–75 mcg/kg/min. "
            "Indication: sedation infusion.")
    assert _form_or_indication_holds(_issues(PROP_Q, text)) == []


# ── cefazolin[7]: "antibiotic prophylaxis" opened the wound class ───────────

CEF_Q = "80 kg adult, ventriculostomy in place, antibiotic prophylaxis, cefazolin IV"
CEF_SERVED = ("**GIVE**\n- cefazolin IV: 2 g. NO VOLUME — confirm concentration to compute "
              "volume. Indication: ventriculostomy in place (prophylaxis).")


def test_cefazolin_two_grams_holds_for_a_ventriculostomy():
    issues = _issues(CEF_Q, CEF_SERVED)
    assert any("cefazolin" in i for i in issues), issues


def test_cefazolin_one_gram_serves_for_a_ventriculostomy():
    text = CEF_SERVED.replace("2 g.", "1 g.")
    assert _issues(CEF_Q, text) == []


def test_cefazolin_for_an_open_fracture_still_takes_two_grams():
    q = "80 kg adult, open tib fib fracture, antibiotics, cefazolin IV"
    text = ("**GIVE**\n- cefazolin IV: 2 g. NO VOLUME — confirm concentration to compute "
            "volume. Indication: open fracture / wound prophylaxis.")
    assert _issues(q, text) == []


# ── epinephrine[6]: an infusion asked, a push dose served ───────────────────

EPI_Q = "80 kg adult, symptomatic bradycardia HR 35, atropine failed, infusion, epinephrine IV"
EPI_SERVED = ("**GIVE**\n- Atropine IV: 1 mg.  \n- Epinephrine IV: 10 mcg.\n")


def test_epinephrine_push_dose_holds_when_an_infusion_was_asked():
    issues = _issues(EPI_Q, EPI_SERVED)
    assert any("epinephrine" in i.lower() and "push dose" in i for i in issues), issues


def test_the_signed_bradycardia_infusion_rate_is_not_held_as_another_form():
    text = ("**DRIP**\n- epinephrine IV infusion: 0.02–0.2 mcg/kg/min. "
            "Indication: symptomatic bradycardia — infusion.")
    assert _form_or_indication_holds(_issues(EPI_Q, text)) == []


def test_the_push_dose_still_serves_when_a_push_dose_is_asked():
    q = "80 kg adult, symptomatic bradycardia HR 35, push dose epinephrine IV"
    text = "**GIVE**\n- Epinephrine IV: 10 mcg. Indication: symptomatic bradycardia — push dose."
    assert _issues(q, text) == []


def test_a_heart_rate_is_not_an_infusion_request():
    q = "80 kg adult, symptomatic bradycardia, heart rate 35, push dose epinephrine IV"
    text = "**GIVE**\n- Epinephrine IV: 10 mcg. Indication: symptomatic bradycardia — push dose."
    assert _issues(q, text) == []


def test_a_loading_dose_still_serves_with_an_infusion():
    q = "80 kg adult, intubated, sedation infusion, ketamine IV, pump available"
    text = ("**GIVE**\n- ketamine IV: 80 mg. NO VOLUME — confirm concentration to compute "
            "volume. Indication: ongoing sedation — loading dose (infusion pump available).")
    assert _issues(q, text) == []


# ── ketamine[12]: background pain is the PFC low-dose entry ─────────────────

KET_Q = "80 kg adult, prolonged field care, ongoing background pain, ketamine IV"


def test_the_acute_pain_dose_holds_for_background_pain():
    text = ("**GIVE**\n- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg). "
            "Indication: moderate to severe pain / analgesia.")
    issues = _issues(KET_Q, text)
    assert any("moderate to severe pain" in i for i in issues), issues


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.mark.parametrize("q", [
    KET_Q,
    "80 kg adult, background pain, ketamine IV",
    "80 kg adult, prolonged field care pain, ketamine IV",
])
def test_the_card_serves_the_pfc_low_dose_entry(q):
    r = oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=[])
    give = r["response"].split("**GIVE**")[1].split("**", 1)[0]
    assert "background pain — low-dose analgesia (prolonged field care)" in give, r["response"]
    assert "(20 mg)" not in give and "20 mg" not in give, give


def test_acute_pain_still_gets_the_acute_entry():
    r = oc._query_with_rag_internal("80 kg adult, femur fracture, severe pain, ketamine IV",
                                    _NoRetrieval(), conversation_history=[])
    give = r["response"].split("**GIVE**")[1].split("**", 1)[0]
    assert "moderate to severe pain / analgesia" in give, r["response"]


# ── Found in this PR's replay: a held label stays held ──────────────────────
# Live, 2026-10-27 (session log line 145): held by the label check (A1b)
# because propofol was built only for induction. With the narrower A32 list
# the label check had no propofol to judge against and the row released. The
# label check keeps the class-level list.

def test_the_2026_10_27_propofol_template_line_stays_held():
    q = "80 kg adult, intubated, propofol infusion rate for sedation"
    text = ("**BRIEF**\n- Propofol NO VOLUME — confirm concentration to compute volume.\n"
            "- Start propofol infusion at 10-75 mcg/kg/min via infusion pump or Dial-a-Drip.\n\n"
            "**DO THIS**\n1. Start propofol infusion at 10-75 mcg/kg/min.\n\n"
            "**GIVE**\n- Draw X mL of Y mg/mL propofol IV (Z mg). Indication: sedation.\n")
    ctx = oc.PatientContext(confirmed_weight_kg=80.0, is_pediatric=False)
    doses = oc.build_allowed_doses(q, ctx)
    issues = oc.run_deterministic_checks(q, text, ctx, doses, current_query=q).issues
    assert any('propofol for "sedation"' in i for i in issues), issues
