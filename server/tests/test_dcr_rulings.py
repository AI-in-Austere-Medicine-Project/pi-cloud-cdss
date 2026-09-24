"""
EdgeCDSS — A1 owner rulings, 2026-09-24, on the false positives the A1 replay
found when the DCR pre-gate was widened.

  1. Tension pneumothorax signs route to needle decompression (Wartime
     Thoracic Injury ID74), never to the DCR card. With shock physiology as
     well, the tension card fires FIRST and says "then reassess for
     hemorrhage — DCR", so the bleeding is not lost.
  2. An injury pattern alone does not fire DCR when the query asks something
     else specific, and the DCR check runs after the vent card and the dose
     paths.
  3. No adult HR > 100 rule under 16: SMOG's cited paediatric ranges (pp.49-50,
     PALS) decide tachycardia and hypotension for a child.
  4. "Bleeding controlled / TQ effective" is not a bleeding term for the HR and
     shock-index rules.
  B1 (with the card): the DCR card's SOURCE is ID18 with printed pages, and its
     TXA line is the signed dose, not "Consider TXA".

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402

DCR_MARK = "Start damage-control resuscitation"
REASSESS = "then reassess for hemorrhage — DCR"


class _Retrieval:
    def __init__(self):
        self.calls = 0

    def query(self, *a, **k):
        self.calls += 1
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


class _NoRetrieval:
    def query(self, *a, **k):
        raise AssertionError("a deterministic card reached retrieval")


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: "STUB")


def run(q, retrieval=None):
    return oc._query_with_rag_internal(q, retrieval or _Retrieval())


# ── 1. tension pneumothorax ──────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    # tension signs, then shock physiology
    "penetrating chest wound, absent breath sounds on the right, JVD, hypotensive",
    # shock physiology first, then tension signs
    "GSW to the chest, BP 82/50, HR 130, now tracheal deviation and no breath sounds on the left",
])
def test_tension_signs_with_shock_take_the_tension_card_first(query):
    r = run(query, _NoRetrieval())
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "needle decompression" in r["response"].lower()
    assert "4th or 5th intercostal space" in r["response"]
    assert "ID74" in r["response"] and "p.8" in r["response"]
    assert DCR_MARK not in r["response"], "the DCR card fired instead of decompression"
    assert REASSESS in r["response"], "the haemorrhage was dropped"


def test_tension_signs_without_shock_take_the_tension_card_alone():
    r = run("blunt chest trauma, decreased breath sounds on the left, tracheal deviation, hyperresonant",
            _NoRetrieval())
    assert "needle decompression" in r["response"].lower()
    assert DCR_MARK not in r["response"]
    assert REASSESS not in r["response"]


# ── 2. a specific question is answered, not replaced by the DCR card ─────────

def test_intubated_vent_setup_reaches_the_vent_card():
    # The replayed query, verbatim. With a weight and height added it takes the
    # RSI pre-gate instead — an already-intubated patient given the RSI
    # bundle, which is work item A3 and happens on main too.
    r = run("penetrating chest injury intubated, vent setup")
    assert DCR_MARK not in r["response"]
    assert r["source_mode"] in ("VENT_CARD", "VENT_GATE"), r["source_mode"]


def test_an_ertapenem_question_reaches_the_dose_path():
    rec = _Retrieval()
    r = run("ertapenem dose for penetrating abdominal injury", rec)
    assert DCR_MARK not in r["response"]
    assert r["source_mode"] != "DETERMINISTIC_PRE_GATE" or "ertapenem" in r["response"].lower()


def test_the_junctional_packing_question_is_answered_as_a_procedure():
    rec = _Retrieval()
    r = run("junctional groin wound, tourniquet won't seat, what packing and pressure "
            "sequence does TCCC want", rec)
    assert DCR_MARK not in r["response"]
    assert rec.calls == 1, "the procedure question did not reach retrieval"


def test_a_txa_question_with_massive_bleeding_still_reaches_the_dcr_card():
    r = run("GSW to the pelvis with massive bleeding, 40 minutes since injury, should I give TXA",
            _NoRetrieval())
    assert DCR_MARK in r["response"]


# ── 3. paediatrics: cited thresholds only ────────────────────────────────────

def test_the_eight_year_old_asking_for_pain_relief_goes_to_analgesia():
    q = ("Have a 8 year old with an ambulated arm.  BP 100/70 HR 120 Spo2 100. "
         "Have bleeding controlled. Need ketamine pain mgmt. 60kg")
    assert not oc.looks_like_hemorrhagic_shock(q)
    r = run(q)
    assert DCR_MARK not in r["response"]
    assert "ketamine" in r["response"].lower() or "IV or IM" in r["response"], r["response"][:200]


@pytest.mark.parametrize("query,expected,why", [
    ("8 year old, GSW to the leg, HR 150, BP 110/70", True, "HR above SMOG's 60-140 for 2-10 y"),
    ("8 year old, GSW to the leg, HR 120, BP 110/70", False, "HR within 60-140 for 2-10 y"),
    ("12 year old, stab wound to the thigh, HR 110, BP 118/72", True, "HR above 60-100 for >10 y"),
    ("5 year old, dog bite bleeding from the leg, BP 76/50", True, "SBP below 70 + 2x5 = 80"),
    ("5 year old, bleeding from a leg laceration, BP 86/54, HR 110", False, "SBP 86 not below 80; HR within 140"),
])
def test_paediatric_thresholds_are_smogs(query, expected, why):
    assert oc.looks_like_hemorrhagic_shock(query) is expected, why


# ── 4. controlled bleeding ───────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected,why", [
    ("GSW thigh, bleeding controlled, TQ effective, HR 112, BP 124/80", False,
     "controlled bleeding is not a bleeding term for the HR rule"),
    ("stab wound to the arm, hemorrhage controlled, HR 100, BP 105/70", False,
     "nor for the shock-index rule (0.95)"),
    ("GSW thigh, bleeding controlled, BP 88/50", True, "SBP < 100 still counts"),
])
def test_controlled_bleeding(query, expected, why):
    assert oc.looks_like_hemorrhagic_shock(query) is expected, why


# ── B1: the DCR card's SOURCE and its TXA line ──────────────────────────────

def test_the_dcr_card_cites_id18_and_serves_the_signed_txa_dose():
    r = run("80 kg male, GSW left thigh, tourniquet on 20 min, HR 118, BP 104/68", _NoRetrieval())
    text = r["response"]
    assert "Consider TXA" not in text
    assert "tranexamic acid IV: 2 g" in text, text
    source = text.split("**SOURCE**:")[1]
    assert "ID18" in source and "p.10" in source, source
    assert "General Evidence-Based Medicine" not in source
    # The signed entry's contraindications ride with the dose (owner ruling 12).
    assert "more than 3 hours after injury" in text


def test_a_child_with_a_weight_gets_the_signed_paediatric_txa_dose():
    r = run("20 kg 6 year old, bilateral leg amputations from a blast, TQs on", _NoRetrieval())
    assert "tranexamic acid IV: 15 mg/kg" in r["response"], r["response"]
    assert "300 mg" in r["response"]


def test_with_txa_unsigned_the_card_states_no_txa_number(monkeypatch):
    for e in dc.DRUGS["tranexamic acid"]["dose_entries"]:
        monkeypatch.setitem(e, "signoff", False)
    r = run("80 kg male, GSW left thigh, tourniquet on 20 min, HR 118, BP 104/68", _NoRetrieval())
    give = r["response"].split("**GIVE**")[1].split("**")[0]
    assert "2 g" not in give and "2g" not in give
    assert "no signed" in give.lower()
