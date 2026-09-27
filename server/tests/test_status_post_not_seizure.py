"""
EdgeCDSS — A8: "status post" must not match status epilepticus.

Found in #91. The dose builder's seizure trigger was the substring 'status',
so "159lb male unable to ventilate effectively status post oral trauma"
(H-SESS-002, also in the live logs) was offered lorazepam 4 mg for active
seizure: a patient who is not seizing, offered a seizure dose.

The same substring caught every "altered mental status", "mental status
changes" and "code status" too. It is the class of "stab" in "stable" and
"14G" read as grams: a lexical match firing on a substring.

"status" is a seizure word only in its seizure senses: "in status", "status
epilepticus", "status seizures", "status SZ". Those keep the seizure dose.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _seizure_doses(query):
    ctx = oc.extract_patient_context(query)
    return sorted({(d.drug, d.indication) for d in oc.build_allowed_doses(query, ctx)
                   if d.indication in oc.SEIZURE_INDICATIONS})


NOT_A_SEIZURE = [
    # H-SESS-002, verbatim
    "159lb male unable to ventilate effectively status post oral trauma",
    "80kg male status post fall from a ladder, what do I give",
    "80kg male, post-status, how is he",
    "80kg male, status: stable, sats 96",
    "80kg male, altered mental status after a blast",
    "80kg male, mental status changes, agitated",
    "80kg male, code status unknown",
]


@pytest.mark.parametrize("query", NOT_A_SEIZURE)
def test_status_in_another_sense_is_not_offered_a_seizure_dose(query):
    assert _seizure_doses(query) == [], query


# These are seizures, and must keep the seizure dose.
SEIZURE = [
    "80kg male in status, what do I give",
    "80kg male still in status after 10 mg of versed",
    "80kg male in status epilepticus",
    "80kg male, status seizures, what now",
    "80 kg TBI patient that is having ststus SZ, maxed out on versed",
    "80kg male actively seizing",
    "80kg male having seizures",
]


@pytest.mark.parametrize("query", SEIZURE)
def test_a_seizure_keeps_its_seizure_dose(query):
    assert _seizure_doses(query), query
