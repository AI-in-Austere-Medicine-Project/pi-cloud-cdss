"""E05: relabelled to ID83's wording, re-signed, and served for a shock patient.

Owner, 2026-10-21 (freeze plan to v5.1.0, item 3): "E05 label: relabel to
'push-dose vasopressor for hypotension / shock (SBP < 90)' per ID83 p.24
wording, re-sign (Andrew Azelton), and the prep card serves it for a shock
patient. Failing test first." Confirmed the same day: "I re-sign E05
relabelled, Andrew Azelton, AI-AIM."

Found in the signing batch 3 live harness: the push-dose prep card narrowed
the signed entries by the word "shock" in the label, and E05's label
("push-dose vasopressor for hypotension") had none, so an adult in shock was
refused. Its pattern ("push dose") did not match "push-dose" either.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402

LABEL = "push-dose vasopressor for hypotension / shock (SBP < 90)"
OLD = "push-dose vasopressor for hypotension"


def _entry():
    found = [e for e in dc.servable_entries().get("epinephrine", [])
             if e["indication"] == LABEL]
    assert len(found) == 1, [e["indication"] for e in dc.servable_entries()["epinephrine"]]
    return found[0]


def test_the_entry_carries_the_new_label_and_the_old_is_gone():
    e = _entry()
    assert (e["population"], e["route"]) == ("adult", "IV")
    labels = [x["indication"] for x in dc.DRUGS["epinephrine"]["dose_entries"]]
    assert OLD not in labels


def test_it_is_re_signed_for_the_owner():
    e = _entry()
    assert e["signoff"] is True and e["reviewed_by"] == "AI-AIM"
    assert e["review_date"] == "2026-10-22"


def test_the_dose_is_unchanged():
    e = _entry()
    assert e["dose_range"] == {"min": 5.0, "max": 20.0, "units": "mcg", "per_kg": False}


def test_it_is_the_shock_class():
    assert oc.indication_class(LABEL) == "shock"


@pytest.mark.parametrize("q", [
    "need push dose epi, BP 70/40 shocky",
    "80 kg adult trauma, BP 78/40, push dose epinephrine for hypotension",
    "push-dose epi for this hypotensive patient, SBP 80",
])
def test_the_prep_card_serves_it_for_a_shock_patient(q):
    card = oc.build_fixed_prep_response(q)
    give = card.split("**GIVE**")[1].split("\n**")[0]
    assert "epinephrine IV: 5-20 mcg" in give and LABEL in give, card
    assert "No signed entry" not in give, card
    assert "symptomatic bradycardia" not in give, card
    assert "10 mcg/mL" in card.split("**CAUTIONS**")[1], card


def test_bradycardia_still_gets_the_bradycardia_entry_only():
    card = oc.build_fixed_prep_response("push dose epi for bradycardia HR 38")
    give = card.split("**GIVE**")[1].split("\n**")[0]
    assert "symptomatic bradycardia" in give and LABEL not in give, give
