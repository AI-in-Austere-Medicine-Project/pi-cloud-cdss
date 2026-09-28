"""
EdgeCDSS — A9: every active-seizure phrasing reaches the signed entry.

Work order A9 (found in #91): "80kg male actively seizing" never reached the
dose builder. The fixed ACTIVE SEIZURE card answered "benzodiazepine per local
protocol" with no signed dose, even with a weight and a signed entry.

It was wider than the example: the card intercepted "active seizure" itself,
and every phrasing containing "seizing", before any dose path. Only phrasings
the card did not catch ("having a seizure", "status epilepticus", "in status")
reached the builder and the model, so the same patient got a signed dose or
none depending on the verb.

Owner ruling (A9): the card carries the dose. Every active-seizure phrasing
gets the deterministic ACTIVE SEIZURE card, with the signed GIVE line the
builder resolves for this patient (A2's severe-TBI pattern). No weight: it asks
for one and states no number. A benzodiazepine already given ("maxed out on
versed"): no further benzodiazepine dose is served. Eclampsia stays off the
card.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402


class _Ret:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                "distances": [[0.2]]}


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda system, messages, **k: (
        '{"result":"SAFE","issues":[],"rationale":"stub"}'
        if "Clinical Safety Validator" in (system or "") else "MODEL ANSWER"))

    def _run(query):
        return oc._query_with_rag_internal(query, _Ret(), conversation_history=[])
    return _run


def _card(r):
    return (r.get("response") or "")


# ── Every phrasing, 80 kg: the card, with the signed lorazepam line ────────

PHRASINGS = [
    "80kg male, active seizure",
    "80kg male actively seizing",
    "80kg male actively seizing, what do I give",
    "80kg male seizing now",
    "80kg male still seizing",
    "80kg male in status",
    "80kg male having a seizure",
    "80kg male in status epilepticus",
    "80kg male, active seizure, lorazepam dose",
]


@pytest.mark.parametrize("query", PHRASINGS)
def test_every_phrasing_gets_the_card_with_the_signed_dose(run, query):
    r = run(query)
    text = _card(r)
    assert text.startswith("**ACTIVE SEIZURE**"), (query, text[:80])
    assert "lorazepam" in text and "(4 mg)" in text and "Indication: active seizure" in text, text
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE"


def test_midazolam_named_gets_the_signed_midazolam_seizure_line(run):
    text = _card(run("80kg male actively seizing, what dose of midazolam"))
    assert "midazolam" in text and "Indication: active seizure" in text, text
    assert "lorazepam IV" not in text, "one benzodiazepine, not two"


def test_levetiracetam_named_gets_the_status_epilepticus_line(run):
    text = _card(run("80kg male in status epilepticus, keppra dose"))
    assert "levetiracetam" in text and "Indication: status epilepticus" in text, text


# ── No weight: no number, and the card says what would give one ─────────────

@pytest.mark.parametrize("query", ["male actively seizing", "adult having a seizure",
                                   "6 year old seizing"])
def test_no_weight_no_dose_and_the_card_asks_for_one(run, query):
    text = _card(run(query))
    assert text.startswith("**ACTIVE SEIZURE**"), text[:80]
    assert "weight in kg" in text, text
    assert " mg" not in text.split("**WATCH**")[0], text


# ── A benzodiazepine already given: no further benzodiazepine dose ──────────

@pytest.mark.parametrize("query", [
    "80 kg TBI patient that is having ststus SZ, maxed out on versed",
    "80kg male still in status after 10 mg of versed",
    "80kg male still seizing after 4 mg of lorazepam",
])
def test_after_a_benzodiazepine_the_card_serves_no_further_benzodiazepine(run, query):
    text = _card(run(query))
    assert text.startswith("**ACTIVE SEIZURE**"), text[:80]
    give = text.split("**GIVE**")[1].split("**")[0] if "**GIVE**" in text else ""
    for benzo in ("lorazepam", "midazolam", "diazepam"):
        assert f"{benzo} IV" not in give and f"{benzo} IM" not in give, (benzo, give)
    assert "already been given" in text, text


# ── Not an active seizure: not the card ─────────────────────────────────────

@pytest.mark.parametrize("query", [
    "80kg male, history of seizures, femur fracture, ketamine for pain",
    "80kg male, no seizures, ketamine for pain",
    "severe TBI, 80kg, levetiracetam for seizure prophylaxis",
    "70kg, 34 weeks pregnant, eclamptic seizure, what do I give",
])
def test_not_an_active_seizure_is_not_the_card(run, query):
    assert not _card(run(query)).startswith("**ACTIVE SEIZURE**"), query


# ── Refractory to benzodiazepines: second line (owner, #103 review) ─────────
# "If patient does not respond to benzos, you can offer levetiracetam";
# ketamine is a known second- and third-line drug for status, and most rescue
# and EMS systems don't carry levetiracetam. Levetiracetam is offered by role
# from its signed status-epilepticus entries. Ketamine is named with its JTS
# source (Prolonged Casualty Care Guidelines, ID91 p.28: "consider ketamine for
# refractory seizures") and served only when a ketamine entry is signed.

def _give(text):
    return text.split("**GIVE**")[1].split("**WATCH**")[0] if "**GIVE**" in text else ""


@pytest.mark.parametrize("query", [
    "80kg male still in status after 10 mg of versed",
    "80 kg TBI patient that is having ststus SZ, maxed out on versed",
    # H-S3 verbatim, no weight: the adult status-epilepticus dose is fixed.
    "Have a TBI patient that is having ststus SZ, maxed out on versed",
])
def test_refractory_adult_is_offered_levetiracetam(run, query):
    give = _give(_card(run(query)))
    assert "levetiracetam" in give and "2000 mg" in give, give
    assert "Indication: status epilepticus" in give, give


def test_refractory_child_with_a_weight_gets_the_paediatric_entry(run):
    give = _give(_card(run("6 year old, 20kg, still seizing after midazolam")))
    assert "levetiracetam" in give and "1200 mg" in give, give
    assert "status epilepticus, refractory" in give, give


def test_refractory_child_without_a_weight_gets_no_number(run):
    give = _give(_card(run("6 year old still seizing after midazolam")))
    lev = [l for l in give.splitlines() if "levetiracetam" in l.lower()]
    assert not any(re.search(r"\d\s*mg", l) for l in lev), lev
    assert "weight in kg" in give, give


@pytest.mark.parametrize("query", [
    "80kg male still in status after 10 mg of versed",
    "Have a TBI patient that is having ststus SZ, maxed out on versed",
])
def test_refractory_names_ketamine_with_its_source_and_no_unsigned_dose(run, query):
    give = _give(_card(run(query)))
    line = [l for l in give.splitlines() if "ketamine" in l.lower()]
    assert line, give
    assert "ID91" in line[0] and "p.28" in line[0], line[0]
    assert "no signed ketamine dose" in line[0].lower(), line[0]
    assert not re.search(r"\d\s*mg", line[0]), line[0]


def test_first_line_does_not_offer_second_line(run):
    give = _give(_card(run("80kg male actively seizing")))
    assert "levetiracetam" not in give and "ketamine" not in give.lower(), give
