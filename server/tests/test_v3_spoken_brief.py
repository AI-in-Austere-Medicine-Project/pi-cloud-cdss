"""V3.3: a spoken brief for every answer, from fixed templates.

Owner, 2026-10-26: "A spoken brief for every answer: cards and doses speak the
GIVE line and one WATCH line; a hold speaks one sentence ("Held. No signed
dose for magnesium. Use local protocol."); the full text stays on screen.
Numbers and units written out for speech: "zero point one eight millilitres",
"micrograms", "every five minutes", never abbreviations. Fixed templates,
tested, no model wording in the spoken brief."

    cd server && ./run_unit_tests.sh
"""
import os
import pathlib
import re
import sys
import types

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import openai_client as oc  # noqa: E402
import spoken  # noqa: E402

HOLD = spoken.HOLD_OPENER + "\n\n" + spoken.HOLD_ISSUES_LABEL + "\n"
TAIL = ("\n\nReassess patient. Use local protocol. Contact medical control if available."
        "\n\nGuideline-based support only. Not a substitute for clinical judgment.")
# What must never be heard: a digit, a unit or route abbreviation, q5min.
ABBREVIATED = re.compile(r"\d|\b(?:mg|mcg|mL|ml|kg|g|IV|IM|IO|IN|PO|BP|HR|SpO2|ETCO2|EtCO2|GCS|"
                         r"SBP|TXA|q\d+\w*)\b")


@pytest.fixture(autouse=True)
def _log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)


def model_answer(text):
    return {"response": text, "model": "qwen2.5:3b", "source_mode": "JTS_GROUNDED"}


def card(text, brief=""):
    return {"response": text, "model": None, "source_mode": "DETERMINISTIC_PRE_GATE",
            "brief": brief}


# ── Numbers and units, written out ──────────────────────────────────────────

@pytest.mark.parametrize("n, words", [
    ("0.18", "zero point one eight"), ("0.4", "zero point four"), ("1", "one"),
    ("12.5", "twelve point five"), ("20", "twenty"), ("168", "one hundred and sixty-eight"),
    ("1000", "one thousand"), ("1050", "one thousand and fifty"),
    ("1500", "one thousand five hundred"), ("2,000", "two thousand"), ("100", "one hundred"),
])
def test_number_words(n, words):
    assert spoken.number_words(n) == words


@pytest.mark.parametrize("line, said", [
    ("0.18 mL", "zero point one eight millilitres."),
    ("1 mL", "one millilitre."),
    ("50 mcg", "fifty micrograms."),
    ("Repeat q5min", "Repeat every five minutes."),
    ("Repeat every 2-5 minutes", "Repeat every two to five minutes."),
    ("2 g over 10 min", "two grams over ten minutes."),
    ("50 mg/mL", "fifty milligrams per millilitre."),
    ("0.1 mcg/kg/min", "zero point one micrograms per kilogram per minute."),
    ("Need weight in kg before dosing.", "Need weight in kilograms before dosing."),
    ("Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?",
     "Which ketamine do you have, five hundred milligrams in ten millilitres vial, "
     "fifty milligrams per millilitre?"),
    ("BP, HR, SpO2, ETCO2 if available, and ventilator synchrony.",
     "blood pressure, heart rate, oxygen saturation, end-tidal carbon dioxide if available, "
     "and ventilator synchrony."),
    ("Fever or pus plus hypotension = sepsis: fluids.", "Fever or pus plus hypotension means sepsis: fluids."),
])
def test_speak_line_writes_out_numbers_units_and_abbreviations(line, said):
    assert spoken.speak_line(line).lower() == said.lower()


@pytest.mark.parametrize("line", [
    "Check the ABG and FAST.",            # an abbreviation the table does not know
    "Give 1:10,000 epinephrine.",         # a ratio it cannot say
    "TV 6 mL/kg PBW",                     # PBW is not in the table
])
def test_a_line_with_anything_unsayable_is_not_spoken(line):
    assert spoken.speak_line(line) is None


# ── Holds: one sentence ─────────────────────────────────────────────────────

def test_the_magnesium_hold_end_to_end():
    """The A39 fixture, through the real pipeline: held before the model."""
    class NoChroma:
        def get_collection_count(self):
            return 0

        def query(self, *a, **k):
            raise AssertionError("A39 holds before retrieval")

    r = oc.query_with_rag("don't want ketamine, I need magnesium, 75 kg", NoChroma())
    assert r["response"].startswith(spoken.HOLD_OPENER)
    assert r["spoken_brief"] == "Held. No signed dose for magnesium sulfate. Use local protocol."


def test_a_dose_check_hold_names_the_drug_from_the_index():
    r = model_answer(HOLD + "- The answer stated cefazolin 40 mg, which is not the signed "
                     "cefazolin dose for this patient. Ask again for cefazolin dosing." + TAIL)
    assert spoken.build(r) == ("Held. The cefazolin dose in the answer is not the signed dose. "
                               "Use local protocol.")


def test_a_validator_hold_is_not_read_out():
    """The validator is a model: its words are never spoken, even when they
    name a drug."""
    r = model_answer(HOLD + "- Ketamine is dangerous here — awake paralysis risk, says the "
                     "validator in its own words." + TAIL)
    assert spoken.build(r) == spoken.HOLD_OTHER


def test_every_hold_is_one_of_three_sentences():
    shapes = (spoken.HOLD_UNSIGNED.split("{")[0], spoken.HOLD_NOT_SIGNED.split("{")[0],
              spoken.HOLD_OTHER)
    for issue in ("- anything at all", "- Magnesium sulfate: no signed dose. EdgeCDSS has no "
                  "signed entry for magnesium sulfate, so it gives no answer about it: use local "
                  "protocol or medical control.", "- give line states epinephrine 1mg, which "
                  "does not match any ALLOWED_DOSES value (0.005mg IV)."):
        said = spoken.build(card(HOLD + issue + TAIL))
        assert said.startswith(shapes) and said.endswith(spoken.USE_LOCAL)
        assert not ABBREVIATED.search(said)


def test_an_unsigned_hold_naming_an_unknown_word_falls_back():
    """The names come from the index or are not spoken at all."""
    r = card(HOLD + "- Zorbex: no signed dose. EdgeCDSS has no signed entry for zorbex, so it "
             "gives no answer about it: use local protocol." + TAIL)
    assert spoken.build(r) == spoken.HOLD_OTHER


# ── Doses: the GIVE line, written out ───────────────────────────────────────

@pytest.mark.parametrize("line, said", [
    ("Draw 1 mL of 0.4mg/mL naloxone IM (0.4 mg). Indication: opioid-induced respiratory depression.",
     "Give naloxone, zero point four milligrams, intramuscularly. "
     "Draw one millilitre of naloxone, zero point four milligrams per millilitre."),
    ("Draw 0.18 mL of 1mg/mL epinephrine IM (0.18 mg).",
     "Give epinephrine, zero point one eight milligrams, intramuscularly. "
     "Draw zero point one eight millilitres of epinephrine, one milligram per millilitre."),
    ("Draw 168 mg of artesunate IV (168 mg).",
     "Give artesunate, one hundred and sixty-eight milligrams, intravenously. " + spoken.NO_VOLUME),
    ("ketamine IV: 160 mg (2 mg/kg × 80 kg). NO VOLUME — confirm concentration to compute volume.",
     "Give ketamine, one hundred and sixty milligrams, intravenously. " + spoken.NO_VOLUME),
    ("epinephrine IV: 5-20 mcg. Indication: push-dose vasopressor.",
     "Give epinephrine, five to twenty micrograms, intravenously."),
    ("tranexamic acid IV: 2 g.", "Give tranexamic acid, two grams, intravenously."),
    ("sodium chloride 3% IV: 250 mL.",
     "Give sodium chloride three percent, two hundred and fifty millilitres, intravenously."),
])
def test_dose_lines(line, said):
    got = spoken.build(model_answer(f"**GIVE**\n- {line}\n"))
    assert got == said
    assert not ABBREVIATED.search(got)


def test_a_card_speaks_its_give_line_and_one_watch_line():
    r = card("**TXA**\n- Give TXA.\n\n**GIVE**\n- tranexamic acid IV: 2 g.\n\n"
             "**WATCH**\n- Mental status, radial pulse, BP trend.\n- Second watch line.\n")
    assert spoken.build(r) == ("Give tranexamic acid, two grams, intravenously. "
                               "Watch: mental status, radial pulse, blood pressure trend.")


def test_rsi_says_which_ketamine_is_which():
    r = card("**GIVE**\n- ketamine IV: 160 mg. NO VOLUME — confirm concentration to compute volume.\n"
             "- Draw 8 mL of 10mg/mL rocuronium IV (80 mg).\n\n"
             "**POST-INTUBATION SEDATION**\n- ketamine IV: 40 mg.\n")
    said = spoken.build(r)
    assert said.index("Give ketamine, one hundred and sixty") < said.index("rocuronium")
    assert "After intubation, give ketamine, forty milligrams, intravenously." in said


def test_no_more_than_three_doses():
    drugs = ["rocuronium", "ketamine", "fentanyl", "midazolam", "naloxone"]
    lines = "".join(f"- Draw 1 mL of 10mg/mL {d} IV (10 mg).\n" for d in drugs)
    said = spoken.build(card("**GIVE**\n" + lines))
    assert said.count("Give ") == 3 and said.endswith(spoken.MORE_DOSES)


_NOREPI = ("**NOREPINEPHRINE INFUSION**\n- Concentration: prepare per local protocol.\n\n**RATE**\n"
           "- norepinephrine IV: 0.05-0.5 mcg/kg/min. Indication: vasodilatory/haemorrhagic shock infusion.\n"
           "- norepinephrine IV: 0.02-2 mcg/kg/min. Indication: cardiogenic shock / pulmonary oedema "
           "with SBP under 100.\n\n**WATCH**\n- Cardiac monitoring required. Peripheral line — monitor "
           "for extravasation.\n")


def test_a_card_tells_one_drug_s_doses_apart_by_their_signed_indication():
    said = spoken.build(card(_NOREPI))
    assert said == (
        "For vasodilatory or haemorrhagic shock infusion, give norepinephrine, zero point zero five to "
        "zero point five micrograms per kilogram per minute, intravenously. "
        "For cardiogenic shock or pulmonary oedema with systolic blood pressure under one hundred, "
        "give norepinephrine, zero point zero two to two micrograms per kilogram per minute, "
        "intravenously. Watch: cardiac monitoring required. Peripheral line, monitor for extravasation.")


def test_the_same_doses_from_a_model_send_the_medic_to_the_screen():
    assert spoken.build(model_answer(_NOREPI)) == spoken.SAME_DRUG_TWICE.format(drug="norepinephrine")


@pytest.mark.parametrize("line, said", [
    ("Start RR 20-30 and titrate.", "Start respiratory rate twenty to thirty and titrate."),
    ("start RR 20-30, never a normal rate", "start respiratory rate twenty to thirty, never a normal rate."),
    ("FiO2: titrate to SpO2 >= 94%", "inspired oxygen: titrate to oxygen saturation at least ninety-four percent."),
    ("Plateau < 30", "Plateau under thirty."),
    ("Falling pH / rising EtCO2 = under-ventilating",
     "Falling P H or rising end-tidal carbon dioxide means under-ventilating."),
])
def test_vent_card_lines(line, said):
    assert spoken.speak_line(line) == said


def test_a_gate_question_starts_with_a_capital():
    r = {"response": "IV or IM?", "model": None, "source_mode": "PRE_GATE", "brief": "IV or IM?"}
    assert spoken.build(r) == "Intravenous or intramuscular?"


# ── No model wording ────────────────────────────────────────────────────────

_PROSE = ("**BRIEF**\n- Zebra quokka marmalade.\n\n**DO THIS**\n1. Zebra the patient.\n\n"
          "**GIVE**\n- Draw 1 mL of 0.4mg/mL naloxone IM (0.4 mg). Indication: quokka depression.\n\n"
          "**WATCH**\n- Marmalade levels.\n\n**TLDR**\n- Zebra.\n")


def test_a_model_answer_is_heard_only_through_the_templates():
    said = spoken.build(model_answer(_PROSE))
    assert not re.search(r"zebra|quokka|marmalade", said, re.I)
    assert said.startswith("Give naloxone, zero point four milligrams")
    assert "Watch" not in said, "a model's WATCH line is model wording"


def test_the_same_text_from_a_card_speaks_its_watch_line():
    said = spoken.build(card(_PROSE))
    assert said.endswith("Watch: marmalade levels.")


def test_a_model_answer_with_no_dose_is_one_fixed_sentence():
    assert spoken.build(model_answer("**BRIEF**\n- Transfer to surgical support.\n\n"
                                     "**WATCH**\n- Wound assessment\n")) == spoken.MODEL_NO_DOSE


def test_a_model_dose_line_for_an_unknown_drug_is_not_spoken():
    said = spoken.build(model_answer("**GIVE**\n- Draw 1 mL of 2mg/mL zorbex IV (2 mg).\n"))
    assert said == spoken.MODEL_NO_DOSE


def test_two_model_doses_of_one_drug_send_the_medic_to_the_screen():
    """A model answer's indication clause is model wording, and two bare
    doses of one drug are how one gets given for the other."""
    said = spoken.build(model_answer("**GIVE**\n- ketamine IV: 160 mg. Indication: induction.\n"
                                     "- ketamine IV: 40 mg. Indication: sedation.\n"))
    assert said == spoken.SAME_DRUG_TWICE.format(drug="ketamine")


def test_every_word_of_a_model_answer_comes_from_the_templates():
    """Vocabulary check: the words a model answer can make the voice say are
    the templates', numbers', units', routes' and the drug index's."""
    vocab = set()
    for v in vars(spoken).values():
        if isinstance(v, str):
            vocab.update(re.findall(r"[a-z]+", v.lower()))
    for _, one, many in spoken._UNITS:
        vocab.update(re.findall(r"[a-z]+", f"{one} {many}"))
    vocab.update(re.findall(r"[a-z]+", " ".join(spoken.ROUTE_SPOKEN.values())))
    vocab.update(spoken._ONES + spoken._TENS + ["hundred", "thousand", "and", "point"])
    for g in spoken._drug_index().values():
        vocab.update(re.findall(r"[a-z]+", g))
    for text in (_PROSE, "**GIVE**\n- epinephrine IV: 5-20 mcg.\n- tranexamic acid IV: 2 g.\n",
                 HOLD + "- The answer stated cefazolin 40 mg, which is not the signed dose." + TAIL):
        said = spoken.build(model_answer(text))
        assert set(re.findall(r"[a-z]+", said.lower())) <= vocab, said


# ── The answer itself is unchanged ──────────────────────────────────────────

def test_attach_brief_adds_the_spoken_brief_and_changes_nothing_else():
    r = {"response": "**GIVE**\n- tranexamic acid IV: 2 g.\n", "model": None}
    before = dict(r)
    out = oc.attach_brief(dict(r))
    assert out["response"] == before["response"]
    assert out["spoken_brief"] == "Give tranexamic acid, two grams, intravenously."
    assert "brief" in out and "critical_sections" in out


def test_a_failure_in_the_builder_is_a_fixed_sentence(monkeypatch):
    monkeypatch.setattr(spoken, "_build", lambda r: 1 / 0)
    assert spoken.build({"response": "x"}) == spoken.CARD_ON_SCREEN


def test_the_portal_speaks_the_spoken_brief():
    html = (HERE.parent / "static" / "index.html").read_text()
    assert "d.spoken_brief || d.brief || ''" in html


@pytest.mark.parametrize("query", [
    "failed intubation failed igel patient desaturating",
    "80 kg adult, hemorrhagic shock, 4 units of whole blood in, can I give TXA",
    "80 kg adult trauma, BP 78/40, push dose epinephrine for hypotension",
    "80 kg adult, intubated, IV access, ketamine drip for sedation, what rate",
])
def test_real_cards_are_spoken_with_no_abbreviation(query):
    class Chroma:
        def get_collection_count(self):
            return 1

        def query(self, *a, **k):
            return {"documents": [["protocol text"]],
                    "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}

    r = oc.query_with_rag(query, Chroma())
    if r.get("model"):
        pytest.skip(f"{query!r} reached the model offline")
    said = r["spoken_brief"]
    assert said and not ABBREVIATED.search(said), said
    assert said not in (spoken.CARD_ON_SCREEN,), said


# ── Owner, 2026-10-26: the which-indication question's own template ──────────

CEFAZOLIN_Q = ("Which indication for cefazolin — penetrating brain or spinal injury (antibiotic "
               "prophylaxis), ventriculostomy in place or open fracture / wound infection prophylaxis?")


def test_which_indication_is_drug_then_names():
    assert spoken.build({"response": CEFAZOLIN_Q}) == (
        "Cefazolin. Which indication: penetrating brain or spinal injury, antibiotic prophylaxis; "
        "ventriculostomy in place; open fracture or wound infection prophylaxis?")


# ── Owner, 2026-10-26 (round 3): spoken options keep their qualifiers ───────

def test_sedation_keeps_already_intubated():
    assert spoken.indication_name("sedation (already intubated)") == "sedation, already intubated"


def test_no_option_loses_its_qualifier():
    for _name, word, _l, _c in oc.INDICATION_CLASSES:
        said = spoken.indication_name(word)
        for qualifier in re.findall(r"\(([^)]*)\)", word):
            assert said.endswith(", " + qualifier), (word, said)


def test_every_indication_option_has_a_spoken_name():
    for _name, word, _l, _c in oc.INDICATION_CLASSES:
        said = spoken.indication_name(word)
        assert said and "(" not in said and not spoken._unspeakable(said), word


def test_the_question_the_pipeline_writes_gets_the_template():
    # Every drug the bank offers in more than one class, asked about with no
    # indication: the question openai_client writes is the one spoken.
    asked = 0
    for drug in sorted(oc.drug_contracts.servable_entries()):
        h = f"80 kg adult, give {drug}"
        q = oc.which_indication_question(h, oc.rebuild_patient_context_from_history(h))
        if not q:
            continue
        asked += 1
        said = spoken.build({"response": q})
        if said.endswith(". Several indications are on screen. Say one."):
            assert said == spoken.MANY_INDICATIONS.format(
                drug=spoken._capitalised(spoken._say_drug(drug))), q
            continue
        assert said.startswith(spoken._capitalised(spoken._say_drug(drug)) + ". Which indication: "), q
        assert said.endswith("?") and not spoken._unspeakable(said), said
    assert asked >= 3


def test_a_question_that_does_not_rebuild_is_not_templated():
    # An option not in INDICATION_CLASSES: the template is not used.
    odd = "Which indication for cefazolin — sepsis or something unlisted?"
    assert not spoken.build({"response": odd}).startswith("Cefazolin. Which indication:")


# ── Owner, 2026-10-26 (round 3): up to four options, a pause between each ────

def test_options_are_separated_by_a_pause_and_or_stays_inside_one():
    q = ("Which indication for midazolam — agitation, pacing or cardioversion, "
         "sedation (already intubated) or seizure?")
    assert spoken.build({"response": q}) == (
        "Midazolam. Which indication: agitation; pacing or cardioversion; "
        "sedation, already intubated; seizure?")


def test_a_slash_is_or_inside_its_option():
    q = "Which indication for atropine — bradycardia or nerve agent / organophosphate poisoning?"
    assert spoken.build({"response": q}) == (
        "Atropine. Which indication: bradycardia; nerve agent or organophosphate poisoning?")


def test_five_options_are_not_read_out_and_the_drug_is_named():
    # Owner, 2026-10-27: "Ketamine. Several indications are on screen. Say one."
    q = "Which indication for ketamine — agitation, RSI, sedation (already intubated), seizure or pain?"
    assert spoken.build({"response": q}) == "Ketamine. Several indications are on screen. Say one."


def test_no_spoken_question_joins_options_with_or():
    for drug in sorted(oc.drug_contracts.servable_entries()):
        h = f"80 kg adult, give {drug}"
        q = oc.which_indication_question(h, oc.rebuild_patient_context_from_history(h))
        if not q:
            continue
        said = spoken.build({"response": q})
        options = said.partition("Which indication: ")[2].rstrip("?").split("; ")
        assert said.endswith("Say one.") or 2 <= len(options) <= spoken.INDICATION_LIST_MAX, said
