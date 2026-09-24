"""
EdgeCDSS — A2: a deterministic severe-TBI card.

Generated TBI answers left out the specifics in about 4 of 5 runs even with
correct retrieval (SBP floor, hypertonic saline, seizure prophylaxis), and on
the local model the harness case was held for a levetiracetam dose the query
never named. The card is deterministic:

  - GCS <= 8 (or "severe TBI") with a head injury;
  - SBP > 110 mmHg (ID30 p.7); EtCO2 35-45 (ID30 p.7, ID63 p.6); head of bed
    30-45 degrees (ID30 p.10); DO NOT hyperventilate (ID30 p.7); no steroids
    (ID30 p.7); evacuate to neurosurgical care (ID63 p.7);
  - levetiracetam 1500 mg from the SIGNED contract, verbatim;
  - 3% hypertonic saline for herniation signs from a signed entry, and held
    (named, no number) while none is signed — the bank has none today;
  - an already-intubated patient gets the same card without the airway line;
  - a child gets the card with the levetiracetam line held unless a paediatric
    TBI entry is signed (none is), and SMOG's paediatric hypotension limit.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import brief as brief_mod  # noqa: E402
import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402

HARNESS = "severe TBI patient GCS 6 BP 90/60 needs management"
TBI_MARK = "Keep SBP above 110 mmHg"


class _NoRetrieval:
    def query(self, *a, **k):
        raise AssertionError("the TBI card reached retrieval")


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("the TBI card called a model")
    monkeypatch.setattr(providers, "chat", _refuse)


def run(q, retrieval=None):
    return oc._query_with_rag_internal(q, retrieval or _NoRetrieval())


def _signed_lev_line():
    served = oc._served_from_pairs(
        [(n, e) for n, e in dc.signed_entries_by_indication(("severe TBI",), False, None)
         if n == "levetiracetam"], oc.PatientContext())
    assert len(served) == 1, "premise: one signed adult levetiracetam TBI entry"
    return oc.render_range_line(served[0]), served[0]


# ── the harness case is deterministic and stable ─────────────────────────────

def test_the_harness_case_is_the_card_and_stable_across_five_runs():
    outs = [run(HARNESS) for _ in range(5)]
    assert all(r["source_mode"] == "DETERMINISTIC_PRE_GATE" for r in outs)
    assert len({r["response"] for r in outs}) == 1, "the card is not stable"
    assert TBI_MARK in outs[0]["response"]


def test_the_card_carries_every_specific_with_its_source():
    t = run(HARNESS)["response"]
    for needed in ("110 mmHg", "EtCO2 35-45 mmHg", "30-45°", "DO NOT hyperventilate",
                   "steroids", "neurosurgical care"):
        assert needed in t, needed
    source = t.split("**SOURCE**:")[1]
    assert "ID30" in source and "p.7" in source and "ID63" in source and "p.6" in source, source


# ── doses from the signed contract, verbatim ─────────────────────────────────

def test_the_levetiracetam_line_is_the_signed_entry_verbatim():
    line, served = _signed_lev_line()
    t = run(HARNESS)["response"]
    give = t.split("**GIVE**")[1].split("\n\n")[0]
    assert line in give, (line, give)
    for c in served.cautions:
        assert c in t, f"a serve-tier caution of the signed entry is missing: {c}"


def test_hypertonic_saline_is_named_and_held_while_unsigned():
    assert not any("saline" in n or "sodium chloride" in n for n in dc.servable_entries()), \
        "premise: no hypertonic saline entry is signed; if one is, serve it"
    t = run(HARNESS)["response"]
    hts = [l for l in t.splitlines() if "hypertonic saline" in l.lower() and l.startswith("- ")]
    assert hts, "the hypertonic saline line is missing"
    assert not re.search(r"\d+\s*(?:mL|ml|cc|%)?\s*(?:bolus|over)", hts[0]) and "250" not in hts[0], hts[0]
    assert "no signed" in hts[0].lower(), hts[0]


# ── already intubated: same card, airway line suppressed ─────────────────────

@pytest.mark.parametrize("query", [
    "TBI patient, already intubated, GCS 3T, BP 118/70, what now",
    "head injury, GCS 5, we RSI'd him 10 minutes ago, tube is in",
])
def test_an_intubated_patient_gets_the_card_without_the_airway_line(query):
    t = run(query)["response"]
    assert TBI_MARK in t
    assert "definitive airway" not in t
    assert "Pre-oxygenate" not in t, "the RSI bundle was served to an intubated patient"


def test_an_explicit_rsi_request_still_gets_the_rsi_card():
    t = run("RSI a TBI patient 80kg male")["response"]
    assert TBI_MARK not in t
    assert "Pre-oxygenate" in t


# ── paediatric ───────────────────────────────────────────────────────────────

def test_a_child_gets_the_card_with_the_levetiracetam_line_held():
    assert not [e for e in dc.DRUGS["levetiracetam"]["dose_entries"]
                if e["signoff"] and "peds" in e["population"] and "TBI" in e["indication"]], \
        "premise: no paediatric TBI levetiracetam entry is signed"
    t = run("6 year old, severe head injury, GCS 7, 20 kg, BP 96/60")["response"]
    assert "levetiracetam" in t.lower()
    give = t.split("**GIVE**")[1].split("\n\n")[0]
    assert "1500" not in give and "no signed" in give.lower(), give
    assert "82 mmHg" in t, "SMOG's paediatric hypotension limit for 6 years (70 + 2x6)"
    assert "110 mmHg" not in t, "the adult SBP target was given to a child"


# ── who gets the card ────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected", [
    (HARNESS, True),
    ("head injury, GCS is seven, BP 120/80", True),
    ("fell off a truck, hit his head, GCS 8", True),
    ("severe TBI, not following commands", True),
    ("head injury, GCS 9, BP 130/80", False),
    ("GCS 6 after an overdose, no trauma", False),
])
def test_who_gets_the_card(query, expected):
    assert oc.looks_like_severe_tbi(query) is expected


def test_haemorrhagic_shock_with_tbi_takes_the_dcr_card_first():
    """MARCH: massive haemorrhage before the head."""
    t = run("severe TBI GCS 6, GSW left thigh, massive hemorrhage, tourniquet on")["response"]
    assert "Start damage-control resuscitation" in t


# ── the brief: three slots ───────────────────────────────────────────────────

def test_the_brief_follows_the_three_slot_rule():
    t = run(HARNESS)["response"]
    b = brief_mod.build_brief(t)
    text = b["brief"] if isinstance(b, dict) else b
    lines = [l for l in text.splitlines() if l.strip()]
    assert len(lines) <= 3, lines
    assert "levetiracetam" in lines[0].lower() and "1500 mg" in lines[0], lines
    assert "110" in lines[1] or "airway" in lines[1].lower(), lines
    assert "steroid" in lines[-1].lower(), lines
