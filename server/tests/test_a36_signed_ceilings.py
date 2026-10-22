"""A36: the requested-overdose ceilings come from the signed entries.

Owner, 2026-10-22 (v5.1.0 freeze, item A36): "ceilings from signed entries".

Found in the A35 sweep: the pre-gate held a requested ketamine dose above
2 mg/kg, rocuronium above 1.2 mg/kg and succinylcholine above 2 mg/kg. None of
the three numbers is in a signed entry, and the ketamine one sat below the
signed IM doses: "ketamine 320 mg IM" for an agitated 80 kg adult is the
signed 4 mg/kg and was held as an overdose.

The ceiling is now the highest signed single dose of that drug for this
patient: the drug's signed bolus entries for the patient's population, on the
stated route (IV and IO one route; every route when none is stated), each at
its range maximum for the confirmed weight and capped at its own maximum single
dose. An age-banded entry counts only for its band; with no age, the lowest
band's maximum. A drug with no signed bolus entry has no ceiling here (the
dose check downstream still holds anything unsigned). The hold names no
number.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _issues(q):
    ctx = oc.rebuild_patient_context_from_history(q)
    return oc.detect_requested_medication_overdose(q, ctx)


def _ctx(q):
    return oc.rebuild_patient_context_from_history(q)


@pytest.mark.parametrize("q, drug, mg", [
    # adult ketamine: IM agitation 4 mg/kg; IV agitation / RSI / seizure 2 mg/kg
    ("80 kg adult, agitated and violent, ketamine IM", "ketamine", 320.0),
    ("80 kg adult, ketamine IV", "ketamine", 160.0),
    ("80 kg adult, ketamine", "ketamine", 320.0),
    # rocuronium adult 1.2 mg/kg; succinylcholine adult 1.5 mg/kg
    ("80 kg adult, rocuronium IV", "rocuronium", 96.0),
    ("80 kg adult, succinylcholine IV", "succinylcholine", 120.0),
    # child: ketamine IV 2 mg/kg (RSI), IM 3 mg/kg
    ("20 kg child, 6 years old, ketamine IV", "ketamine", 40.0),
    ("20 kg child, 6 years old, ketamine IM", "ketamine", 60.0),
    # child succinylcholine is age-banded: 5 years and above 1.5 mg/kg,
    # under 5 years 2 mg/kg; with no age, the lower band
    ("20 kg child, 6 years old, succinylcholine IV", "succinylcholine", 30.0),
    ("12 kg child, 2 years old, succinylcholine IV", "succinylcholine", 24.0),
])
def test_the_ceiling_is_the_highest_signed_dose_for_this_patient(q, drug, mg):
    assert oc.signed_ceiling_mg(drug, _ctx(q)) == pytest.approx(mg)


def test_a_signed_im_dose_is_not_an_overdose():
    assert _issues("80 kg adult, agitated and violent, give ketamine 320 mg IM") == []


@pytest.mark.parametrize("q, drug", [
    ("80 kg adult, agitated and violent, give ketamine 330 mg IM", "ketamine"),
    ("80 kg adult, give ketamine 200 mg IV", "ketamine"),
    ("80 kg adult, give rocuronium 100 mg", "rocuronium"),
    ("80 kg adult, give succinylcholine 130 mg", "succinylcholine"),
    ("RSI a 6 year old 20kg give ketamine 300mg and rocuronium 60mg", "ketamine"),
])
def test_above_the_highest_signed_dose_holds(q, drug):
    issues = _issues(q)
    assert any(drug in i for i in issues), issues


def test_the_hold_names_no_number_but_the_request():
    (issue,) = _issues("80 kg adult, give ketamine 500 mg IV")
    assert "500" in issue
    for unsigned in ("160", "320", "ceiling of", "mg/kg"):
        assert unsigned not in issue, issue
    assert "highest signed ketamine dose" in issue, issue


def test_the_ceiling_moves_with_the_signed_entry(monkeypatch):
    """No number of its own: change the signed entry and the ceiling follows."""
    real = oc.drug_contracts.servable_entries

    def fewer():
        live = {k: list(v) for k, v in real().items()}
        live["ketamine"] = [e for e in live["ketamine"]
                            if not e["indication"].startswith("agitated")]
        return live
    monkeypatch.setattr(oc.drug_contracts, "servable_entries", fewer)
    # Without the 4 mg/kg IM agitation entry the adult IM maximum is the
    # refractory-seizure 3-4 mg/kg entry; without both it would fall again.
    assert oc.signed_ceiling_mg("ketamine", _ctx("80 kg adult, ketamine IM")) == pytest.approx(320.0)
    live = fewer()
    live["ketamine"] = [e for e in live["ketamine"] if not e["indication"].startswith("refractory")]
    monkeypatch.setattr(oc.drug_contracts, "servable_entries", lambda: live)
    assert oc.signed_ceiling_mg("ketamine", _ctx("80 kg adult, ketamine IM")) == pytest.approx(80.0)


def test_no_signed_entry_means_no_ceiling(monkeypatch):
    monkeypatch.setattr(oc, "drug_contracts", None)
    assert oc.signed_ceiling_mg("ketamine", _ctx("80 kg adult, ketamine IV")) is None
    assert _issues("80 kg adult, give ketamine 500 mg IV") == []


def test_the_unsigned_multipliers_are_gone():
    import inspect
    src = inspect.getsource(oc.detect_requested_medication_overdose)
    for unsigned in ("wt * 2.0", "wt * 1.2"):
        assert unsigned not in src
