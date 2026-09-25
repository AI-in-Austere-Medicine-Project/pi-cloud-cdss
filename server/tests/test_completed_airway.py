"""
EdgeCDSS — A3: a patient whose airway is already done does not get the RSI bundle.

Feedback review 2026-09-03, section 1: four field reports, the most repeated
complaint in the corpus. A medic said the tube was in and asked for vent or
TBI management, and got an induction-and-paralytic bundle: a dose bundle for
an indication that has passed. should_use_rsi_pregate() matched the bare
substrings "intubat" and "ventilator"; the vent-settings diversion (S-4) did
not know "ventilator rate" or "being ventilated". The review's point: a
vocabulary chase is the wrong shape of fix. What is missing is a completed-
airway detector that suppresses the RSI pre-gate regardless of what else the
query asks.

The queries below are the field reports, verbatim from feedback.log.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

RSI_MARK = "Pre-oxygenate and prepare suction"

COMPLETED_AIRWAY = [
    # entry 38, 2026-08-22
    "Standard ventilator rate for an RSI patient with a TBI he is 54 and 150 pounds I’ve established",
    # entry 36, 2026-08-22
    "Patient is being ventilated at a rate of 12. He’s already intubated and he is not 450 his 150.",
    # entry 26, 2026-08-20
    ("I am managing a nine-year-old male that weighs approximately 75 pounds. He’s been hit ejected "
     "from a motorcycle as a traumatic brain injury and I have him intubated. Give me some further "
     "care steps I need to consider."),
    # entry 0, 2026-07-18
    ("We have successfully RSI a traumatic brain injury patient we will now be managing this patient "
     "for the next 4 to 10 hours."),
    # found in A1/A2: took the RSI pre-gate once a weight and height were added
    "penetrating chest injury intubated, vent setup, 80kg male 180cm",
]

PRE_INTUBATION = [
    # entry 35, 2026-08-22
    ("Just about to RSI a patient I would like my Ketamine and rock Aaron dose. This is for a "
     "25-year-old male with a clothes head injury. We are about to do RSI I have an IV established "
     "and he is 150"),
    # entry 49, 2026-09-04
    "need to RSI a 50kg patient Iv established. Vitals: 80/40,HR 140, SpO2 89%",
    # entry 6, 2026-07-19
    "have a 56kg patient with 3rd degree burns. I need to RSI. IV is established",
    "RSI a TBI patient 80kg male",
]


class _Retrieval:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: "STUB")


def run(q):
    return oc._query_with_rag_internal(q, _Retrieval())


@pytest.mark.parametrize("query", COMPLETED_AIRWAY)
def test_a_completed_airway_never_gets_the_rsi_bundle(query):
    assert oc.already_intubated(query), "the completed airway was not detected"
    assert not oc.should_use_rsi_pregate(query)
    assert RSI_MARK not in run(query)["response"]


@pytest.mark.parametrize("query", COMPLETED_AIRWAY[:2])
def test_the_vent_questions_reach_the_vent_path(query):
    assert run(query)["source_mode"] in ("VENT_CARD", "VENT_GATE")


@pytest.mark.parametrize("query", PRE_INTUBATION)
def test_a_genuine_pre_intubation_request_still_gets_the_rsi_bundle(query):
    assert not oc.already_intubated(query), "a planned RSI was read as done"
    assert oc.should_use_rsi_pregate(query)


def test_the_rsi_card_is_still_served_before_intubation():
    assert RSI_MARK in run("RSI a TBI patient 80kg male")["response"]


@pytest.mark.parametrize("text,expected", [
    ("already intubated", True), ("I have him intubated", True), ("we RSI'd him", True),
    ("tube is in", True), ("on the vent", True), ("being ventilated", True),
    ("successfully RSI a patient", True), ("post-RSI, what next", True), ("GCS 3T", True),
    ("about to intubate", False), ("needs to be intubated", False), ("prepare to RSI", False),
    ("going to intubate him", False), ("before we intubate", False),
])
def test_the_completed_airway_detector(text, expected):
    assert oc.already_intubated(text) is expected, text


@pytest.mark.parametrize("text,expected", [
    ("standard ventilator rate", True), ("what vent rate", True), ("being ventilated at 14", True),
    ("minute ventilation target", True), ("I:E ratio", True), ("plateau pressure is 32", True),
    ("driving pressure", True), ("vent rate of 12", True),
    ("heart rate of 120", False), ("rate of 12 per minute on the BVM", False),
])
def test_the_vent_settings_vocabulary(text, expected):
    assert oc.is_vent_settings_query(text) is expected, text
