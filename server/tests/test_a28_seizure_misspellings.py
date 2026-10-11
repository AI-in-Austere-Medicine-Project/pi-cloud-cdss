"""A28 (owner, 2026-10-11): the seizure trigger tolerates common misspellings
(siezing, seizeing, siezure); found in the D7 v3 re-bench, G-TYP-06.

"pt siezing for 4 min now, adult, no iv yet" missed the ACTIVE SEIZURE card
and went to the model; edgecdss-v3 served "Treat as a presumed cardiac arrest
… chest compressions … Defibrillation is the highest priority". The correctly
spelled question gets the card.

The card and the dose builder share one detector (A9), so a misspelled active
seizure gets the same card and the same signed dose as the spelled one. The
exclusions are unchanged: a negated or past seizure, prophylaxis, eclampsia.
"""
import pytest

import openai_client as oc

CARD = "**ACTIVE SEIZURE**"


def _card(q):
    return (oc.build_general_case_response(q, None, q) or "").startswith(CARD)


@pytest.mark.parametrize("q", [
    "pt siezing for 4 min now, adult, no iv yet",          # the bench question
    "adult seizeing for 5 minutes, no access",
    "having a siezure, 70 kg",
    "multiple siezures and still going",
    "he is seizeing again",
])
def test_a_misspelled_active_seizure_gets_the_card(q):
    assert _card(q), q
    assert oc.is_active_seizure_query(q), q


@pytest.mark.parametrize("q", [
    "pt seizing for 4 min now, adult, no iv yet",
    "having a seizure, 70 kg",
])
def test_the_spelled_trigger_is_unchanged(q):
    assert _card(q), q


@pytest.mark.parametrize("q", [
    "no siezure activity, alert and talking",
    "history of siezures, now alert",
    "severe TBI, levetiracetam for siezure prophylaxis",
    "34 weeks pregnant, eclamptic siezure",
    "seize the airway early",
])
def test_the_exclusions_hold_for_the_misspellings(q):
    assert not _card(q), q


def test_a_misspelled_seizure_builds_the_same_dose_as_the_spelled_one():
    ctx = oc.PatientContext(confirmed_weight_kg=70.0)
    spelled = oc.build_allowed_doses("70 kg adult, seizing for 5 minutes", ctx)
    misspelled = oc.build_allowed_doses("70 kg adult, siezing for 5 minutes", ctx)
    key = lambda al: sorted((d.drug, d.indication, d.route, d.dose_mg) for d in al)
    assert key(spelled) and key(misspelled) == key(spelled)


def test_the_bench_question_is_answered_by_the_card_end_to_end(monkeypatch):
    def no_model(*a, **k):
        raise AssertionError("the model was called for an active seizure")

    class Hit:
        def query(self, *a, **k):
            return {"documents": [["seizure"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                    "distances": [[0.4]]}

    monkeypatch.setattr(oc.providers, "chat", no_model)
    r = oc._query_with_rag_internal("pt siezing for 4 min now, adult, no iv yet", Hit())
    assert CARD in r["response"], r["response"][:300]
