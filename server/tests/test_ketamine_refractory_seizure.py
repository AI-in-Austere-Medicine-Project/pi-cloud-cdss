"""
EdgeCDSS — A15: ketamine for a benzodiazepine-refractory seizure.

Owner, #103 review (2026-09-28): ketamine is the second drug for status
epilepticus after benzodiazepines. Option B, signed by the owner:
  adult  IV/IO 2 mg/kg; IM 3-4 mg/kg (the engine serves a range's minimum)
  child  IV/IO 1 mg/kg; IM 3 mg/kg (3 months and over)

No approved source (NASEMSO, JTS, SMOG, WHO EML) states a ketamine SEIZURE dose.
JTS ID91 p.28 states the indication ("consider ketamine for refractory
seizures"); Finney 2026 (Prehosp Emerg Care 30(2):323-331) reports the doses
EMS gave (IM mean 3.3 mg/kg, IV/IO 2.2 mg/kg; 38/42 stopped). The value is the
owner's declaration (OWNER_DECLARED), the mechanism SIGNING.md provides when no
source states the dose. Evidence: docs/authoring/KETAMINE_SECOND_LINE_SEIZURE_EVIDENCE.md.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402

INDICATION = "refractory seizure (benzodiazepine-refractory)"
EXPECTED = {
    ("adult", "IV"): (2.0, 2.0),
    ("adult", "IM"): (3.0, 4.0),
    ("peds", "IV"): (1.0, 1.0),
    ("peds", "IM"): (3.0, 3.0),
}


def _entries():
    return {(e["population"], e["route"]): e
            for e in dc.servable_entries().get("ketamine", [])
            if e["indication"] == INDICATION}


def test_the_four_entries_are_signed_and_serve():
    got = _entries()
    assert set(got) == set(EXPECTED), sorted(got)
    for key, (lo, hi) in EXPECTED.items():
        r = got[key]["dose_range"]
        assert (r["min"], r["max"], r["units"], r["per_kg"]) == (lo, hi, "mg/kg", True), key


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_each_is_the_owners_declaration(key):
    e = _entries()[key]
    assert e["reviewed_by"] == "AI-AIM" and e["signoff"] is True
    assert "OWNER_DECLARED" in e["flags"]
    d = e["owner_declaration"]
    assert d["declared_by"] == "Andrew Azelton - AI-AIM"
    cites = " ".join(x["citation"] for x in d["supporting_doctrine"])
    assert "ID91" in cites and "p.28" in cites, cites
    assert "Finney" in cites, cites
    assert any("ID91" in s["citation"] for s in e["sources"])


def test_a_child_under_3_months_is_not_offered_it():
    for key in (("peds", "IV"), ("peds", "IM")):
        assert _entries()[key].get("min_age_months") == 3


# ── The card serves it: the second drug after a benzodiazepine ──────────────

def _give(query):
    ctx = oc.extract_patient_context(query)
    text = oc.build_seizure_response(query, ctx)
    return text.split("**GIVE**")[1].split("**WATCH**")[0]


def test_an_adult_gets_ketamine_first_by_both_routes():
    give = _give("80kg male still in status after 10 mg of versed")
    assert "ketamine IV" in give and "160 mg" in give, give
    assert "ketamine IM" in give and "240 mg" in give, give
    assert "Indication: refractory seizure" in give, give
    assert give.index("ketamine") < give.index("levetiracetam"), give
    assert "No signed ketamine dose" not in give, give


def test_with_iv_access_only_the_iv_dose():
    give = _give("80kg male, IV in, still seizing after 10 mg of versed")
    assert "ketamine IV" in give and "ketamine IM" not in give, give


def test_a_20kg_child_gets_the_paediatric_doses():
    give = _give("6 year old, 20kg, still seizing after midazolam")
    assert "20 mg" in give and "60 mg" in give, give
    assert "Indication: refractory seizure" in give, give


def test_no_weight_no_ketamine_number():
    give = _give("Have a TBI patient that is having ststus SZ, maxed out on versed")
    ket = [l for l in give.splitlines() if "ketamine" in l.lower()]
    assert ket and all("mg" not in l or "mg/kg" in l for l in ket), ket
    assert any("weight in kg" in l for l in ket), ket


def test_first_line_is_unchanged():
    give = _give("80kg male actively seizing")
    assert "lorazepam" in give and "ketamine" not in give.lower(), give


# Owner, 2026-09-28 (#103 merged): cautions for hypoxia and BVM readiness, as
# two lines a medic reads with the dose.

@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_hypoxia_and_bvm_readiness_are_separate_served_cautions(key):
    served = dc.serve_cautions(_entries()[key])
    hyp = [c for c in served if "hypoxia" in c.lower()]
    bvm = [c for c in served if "bvm" in c.lower() or "bag-valve-mask" in c.lower()]
    assert hyp and "SpO2" in hyp[0] and "EtCO2" in hyp[0], served
    assert bvm and "ready before giving" in bvm[0], served
    assert hyp[0] != bvm[0], "two lines, not one"


def test_the_card_shows_both_cautions():
    ctx = oc.extract_patient_context("80kg male still in status after 10 mg of versed")
    text = oc.build_seizure_response("80kg male still in status after 10 mg of versed", ctx)
    cautions = text.split("**CAUTIONS**")[1].split("**WATCH**")[0]
    assert "Monitor SpO2 and EtCO2" in cautions and "ready before giving" in cautions, cautions
