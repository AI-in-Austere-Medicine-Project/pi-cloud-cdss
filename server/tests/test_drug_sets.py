"""Drug sets (owner, 2026-11-12, signing batch 4): EMS beside PFC.

Owner: "This formulary is its own drug set, "EMS", separate from the existing
JTS/SMOG bank, which becomes the "PFC" set. Add a set field to the contract
format and the exporter (one bank file per set), with a test that an entry from
one set is never served under another."

The pins:
  - every dose entry names its set; the existing bank is PFC;
  - an entry with no set, or an unknown one, never serves;
  - a server serves one set (CDSS_DRUG_SET, default PFC): an entry of the other
    set is not servable, is not in servable_entries(), and a question about a
    drug signed only in the other set holds "no signed dose" before the model;
  - the exporter writes one bank per set, and a set's bank holds only its own
    entries.

    cd server && ./run_unit_tests.sh
"""
import copy
import json
import os
import pathlib
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import drug_contracts as dc  # noqa: E402

CONTRACTS = pathlib.Path(dc.__file__).resolve().parent / "drug_contracts.json"


def _a_signed_pfc_entry():
    """A real signed entry of the live bank, with its drug."""
    for name, drug in dc.DRUGS.items():
        for e in drug.get("dose_entries", []):
            if dc.entry_is_servable(e, drug)[0]:
                return name, drug, e
    raise AssertionError("no signed entry in the bank")


# ── the format ──────────────────────────────────────────────────────────────

def test_the_sets_are_pfc_and_ems():
    assert dc.KNOWN_SETS == ("PFC", "EMS")


def test_every_entry_in_the_bank_names_its_set_and_the_existing_bank_is_pfc():
    raw = json.loads(CONTRACTS.read_text())
    sets = [e.get("set") for d in raw["drugs"] for e in d["dose_entries"]]
    assert sets and all(s in dc.KNOWN_SETS for s in sets), sorted({str(s) for s in sets})
    # The 118 entries of the bank before batch 4 are PFC; batch 4 added EMS only.
    assert sets.count("PFC") == 118


def test_set_is_a_required_entry_field():
    assert "set" in dc._ENTRY_REQUIRED


def test_an_entry_with_no_set_never_serves():
    _, drug, e = _a_signed_pfc_entry()
    bare = {k: v for k, v in e.items() if k != "set"}
    ok, why = dc.entry_is_servable(bare, drug)
    assert not ok and "set" in why, why


def test_an_unknown_set_never_serves():
    _, drug, e = _a_signed_pfc_entry()
    ok, why = dc.entry_is_servable(dict(e, set="JTS"), drug)
    assert not ok and "JTS" in why, why


# ── served under its own set only ───────────────────────────────────────────

def test_this_server_serves_pfc_by_default():
    assert dc.SERVED_SET == "PFC"


def test_an_ems_entry_is_not_servable_on_a_pfc_server():
    _, drug, e = _a_signed_pfc_entry()
    ems = dict(e, set="EMS", indication_class="test", kit_vial=None)
    ok, why = dc.entry_is_servable(ems, drug)
    assert not ok and "EMS" in why and "PFC" in why, why
    assert dc.entry_is_servable(ems, drug, served_set="EMS")[0]


def test_a_pfc_entry_is_not_servable_on_an_ems_server():
    _, drug, e = _a_signed_pfc_entry()
    assert dc.entry_is_servable(e, drug, served_set="PFC")[0]
    ok, why = dc.entry_is_servable(e, drug, served_set="EMS")
    assert not ok and "PFC" in why, why


def test_an_unknown_served_set_serves_nothing(monkeypatch):
    _, drug, e = _a_signed_pfc_entry()
    monkeypatch.setattr(dc, "SERVED_SET", "pfc ")
    assert not dc.entry_is_servable(e, drug)[0]
    assert dc.servable_entries() == {}


def test_served_set_comes_from_the_environment():
    assert dc._served_set({"CDSS_DRUG_SET": "EMS"}) == "EMS"
    assert dc._served_set({}) == "PFC"
    assert dc._served_set({"CDSS_DRUG_SET": "ems"}) == "EMS"
    assert dc._served_set({"CDSS_DRUG_SET": "SMOG"}) is None


def _with_ems_magnesium(monkeypatch):
    """The live bank plus one signed EMS magnesium entry (magnesium has no
    PFC entry), made from a real signed entry so only the set and drug differ."""
    _, _, e = _a_signed_pfc_entry()
    drugs = copy.deepcopy(dc.DRUGS)
    mg = drugs.get("magnesium sulfate") or {"generic_name": "magnesium sulfate",
                                            "aliases": ["magnesium", "mag"], "drug_class": "electrolyte",
                                            "forms": [], "routes": ["IV"], "dose_entries": []}
    mg["dose_entries"] = list(mg.get("dose_entries", [])) + [
        dict(copy.deepcopy(e), set="EMS", indication="torsades de pointes",
             indication_class="torsades", kit_vial=None)]
    drugs["magnesium sulfate"] = mg
    monkeypatch.setattr(dc, "DRUGS", drugs)
    return mg


def test_servable_entries_holds_no_entry_of_the_other_set(monkeypatch):
    _with_ems_magnesium(monkeypatch)
    live = dc.servable_entries()
    assert "magnesium sulfate" not in live
    assert all(e.get("set") == "PFC" for es in live.values() for e in es)
    monkeypatch.setattr(dc, "SERVED_SET", "EMS")
    live = dc.servable_entries()
    assert "magnesium sulfate" in live
    assert all(e.get("set") == "EMS" for es in live.values() for e in es)


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


def test_a_drug_signed_only_in_ems_holds_on_a_pfc_server(monkeypatch):
    """End to end: the EMS magnesium entry exists, and a PFC server still
    answers "no signed dose" for magnesium before the model runs (A39)."""
    import openai_client as oc
    import providers
    _with_ems_magnesium(monkeypatch)
    calls = []

    def chat(system, messages, **k):
        calls.append(system)
        if "Clinical Safety Validator" in (system or ""):
            return '{"result": "SAFE", "issues": [], "rationale": "ok"}'
        return "Magnesium 2 g IV over 15 minutes."
    monkeypatch.setattr(providers, "chat", chat)
    r = oc._query_with_rag_internal("magnesium for torsades, 75 kg adult", _JtsHit(), conversation_history=[])
    assert calls == [], "the model was called"
    assert "no signed dose" in r["response"] and "magnesium" in r["response"].lower(), r["response"]


# ── the exporter: one bank per set ──────────────────────────────────────────

def test_the_exporter_takes_a_set():
    import export_pocket_bank as ex
    assert ex.parse_args(["--out", "x"]).set == "PFC"
    assert ex.parse_args(["--out", "x", "--set", "EMS"]).set == "EMS"
    with pytest.raises(SystemExit):
        ex.parse_args(["--out", "x", "--set", "JTS"])


def test_a_sets_bank_holds_only_its_own_entries(monkeypatch):
    import export_pocket_bank as ex
    _with_ems_magnesium(monkeypatch)
    cls = lambda *a, **k: "other"  # noqa: E731
    pfc = ex.build_bank(dc.DRUGS, "t", classify=cls, set_name="PFC")
    ems = ex.build_bank(dc.DRUGS, "t", classify=cls, set_name="EMS")
    assert pfc["set"] == "PFC" and ems["set"] == "EMS"
    assert pfc["entries"] and all(e["set"] == "PFC" for e in pfc["entries"])
    assert "magnesium sulfate" in {e["drug"] for e in ems["entries"]}
    assert all(e["set"] == "EMS" for e in ems["entries"])
    assert "magnesium sulfate" in {d["drug"] for d in pfc["no_signed_dose"]}
    assert "magnesium sulfate" not in {d["drug"] for d in ems["no_signed_dose"]}
