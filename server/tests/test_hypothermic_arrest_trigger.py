"""Hypothermic arrest card: "no pulse" or "pulseless" with hypothermia fires it,
not only the words "cardiac arrest" (owner, 2026-10-11; found in the D7 v3
re-bench, G-TYP-07).

The card fired on `"cardiac arrest" in q` plus a cold word. "hypothermic arest,
found in the snow, no pulse" went to the model, and so did the correctly
spelled "hypothermic arrest, found in the snow, no pulse"; edgecdss-v3 served
"Do not re-warm until professional help arrives" (SAFE).

Pulselessness is the patient's: "no pulse ox", a limb's pulse ("no pulse in the
left foot", "pulseless leg") and "no radial pulse" (shock, not arrest) are not
arrest. The new path pairs it with hypothermia wording (hypotherm-, snow,
frozen, cold water, found cold); bare "cold" stays on the "cardiac arrest" path
only, so "cold leg, no pulse" is not read as a hypothermic arrest.
"""
import pytest

import openai_client as oc

CARD = "**HYPOTHERMIC ARREST**"


def _card(q):
    return (oc.build_general_case_response(q, None, q) or "").startswith(CARD)


@pytest.mark.parametrize("q", [
    "hypothermic arest, found in the snow, no pulse",        # the bench question
    "hypothermic arrest, found in the snow, no pulse",
    "found in the snow, pulseless",
    "hypothermia, no pulse, what do I do",
    "pulled from cold water, no palpable pulse",
    "found cold on the mountain, pulseless and not breathing",
    "frozen, no carotid pulse",
])
def test_no_pulse_with_hypothermia_gets_the_card(q):
    assert _card(q), q


@pytest.mark.parametrize("q", [
    "hypothermic cardiac arrest, found in the snow",          # the existing trigger
    "cardiac arrest, he was found cold",
])
def test_the_cardiac_arrest_trigger_is_unchanged(q):
    assert _card(q), q


@pytest.mark.parametrize("q", [
    "hypothermic, no pulse ox reading, shivering",
    "hypothermic but has a pulse, HR 40",
    "cold leg, no pulse in the foot after the tourniquet",
    "pulseless left leg, cold to touch",
    "snow ambulance crash, no radial pulse, BP 70/40",
    "no pulse in the right arm after the cast, hypothermia risk",
    "found in the snow, shivering, talking",
])
def test_not_an_arrest(q):
    assert not _card(q), q


def test_the_bench_question_is_answered_by_the_card_end_to_end(monkeypatch):
    def no_model(*a, **k):
        raise AssertionError("the model was called for a hypothermic arrest")

    class Hit:
        def query(self, *a, **k):
            return {"documents": [["hypothermia"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                    "distances": [[0.4]]}

    monkeypatch.setattr(oc.providers, "chat", no_model)
    r = oc._query_with_rag_internal("hypothermic arest, found in the snow, no pulse", Hit())
    assert r["response"].lstrip().startswith(CARD) or CARD in r["response"], r["response"][:300]
