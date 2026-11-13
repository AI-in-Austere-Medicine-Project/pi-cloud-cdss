"""EMS-TEST: a bench-testing set that EdgeCDSS never serves (owner, 2026-11-13).

Owner: "the 184 unsigned EMS entries stay unsigned. Add a third set, "EMS-TEST":
all 206 formulary entries as transcribed, status "test", for bench testing
only. Exporter: a --test flag writes bank-ems-test.json with test:true in the
manifest. Without the flag it still refuses anything unsigned. EdgeCDSS never
serves a test set; pin that with a test. ... Entries that failed check (a) or
(b), or contradict their own card, are included but marked check_failed with
the reason ... The 22 signed entries stay in the real EMS set unchanged."

The test entries reproduce the agency's formulary, so they never enter this
public repo: they live in a gitignored file (server/drug_contracts_ems_test.json)
that only the exporter reads, and only with --test. These tests use synthetic
fixtures.

    cd server && ./run_unit_tests.sh
"""
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import drug_contracts as dc  # noqa: E402
import export_pocket_bank as ex  # noqa: E402

SERVER = pathlib.Path(dc.__file__).resolve().parent
REPO = SERVER.parent
GIT = {"commit": "a" * 40, "date": "2026-11-13"}


def _signed_pfc():
    for name, drug in dc.DRUGS.items():
        for e in drug.get("dose_entries", []):
            if dc.entry_is_servable(e, drug)[0]:
                return name, drug, e
    raise AssertionError("no signed entry in the bank")


def _test_entry(**over):
    e = {"indication": "Test indication", "population": "adult", "route": "IV",
         "dose_range": {"min": 1.0, "max": 1.0, "units": "mg/kg", "per_kg": True},
         "max_single": {"value": 50.0, "units": "mg", "rule": "max 50 mg"},
         "max_cumulative": None,
         "contraindications": ["Test contraindication"],
         "cautions": [{"tier": "serve", "text": "Repeat: none."},
                      {"tier": "detail", "text": "Adverse/side effects: test."}],
         "sources": [{"citation": "TEST formulary p.3 (PDF p.3)", "tier": 1, "source_class": "EMS",
                      "url": "local:test", "retrieved_date": "2026-11-13", "page": 3,
                      "quote": "Test | 1 mg/kg | IV/IO", "supports": "dose, max, route"}],
         "signoff": False, "reviewed_by": None, "review_date": None, "version": "1.0.0",
         "set": "EMS-TEST", "status": "test", "indication_class": "test class",
         "kit_vial": None, "check_failed": []}
    e.update(over)
    return e


def _test_doc(*entries, name="testosteril"):
    return {"schema_version": "1.4.0", "set": "EMS-TEST", "test": True,
            "drugs": [{"generic_name": name, "aliases": ["testo"],
                       "dose_entries": list(entries or [_test_entry()])}]}


# ── EdgeCDSS never serves a test set ─────────────────────────────────────────

def test_the_test_set_is_named_and_is_not_a_servable_set():
    assert dc.TEST_SETS == ("EMS-TEST",)
    assert dc.KNOWN_SETS == ("PFC", "EMS")
    assert not set(dc.TEST_SETS) & set(dc.KNOWN_SETS)


@pytest.mark.parametrize("served", [None, "PFC", "EMS", "EMS-TEST"])
def test_a_signed_entry_moved_into_the_test_set_never_serves(served):
    """Even a fully signed entry: the set alone decides it, under any served set."""
    _, drug, e = _signed_pfc()
    ok, why = dc.entry_is_servable(dict(e, set="EMS-TEST"), drug, served_set=served)
    assert not ok
    assert "test set" in why, why


@pytest.mark.parametrize("set_name", ["PFC", "EMS"])
def test_an_entry_with_status_test_never_serves_whatever_set_it_names(set_name):
    _, drug, e = _signed_pfc()
    ok, why = dc.entry_is_servable(dict(e, set=set_name, status="test"), drug,
                                   served_set=set_name)
    assert not ok
    assert "test" in why, why


def test_a_server_started_on_the_test_set_serves_nothing():
    assert dc._served_set({"CDSS_DRUG_SET": "EMS-TEST"}) is None
    assert dc._served_set({"CDSS_DRUG_SET": "ems-test"}) is None


def test_the_repo_bank_carries_no_test_entry():
    raw = json.loads((SERVER / "drug_contracts.json").read_text())
    for d in raw["drugs"]:
        for e in d["dose_entries"]:
            assert e.get("set") not in dc.TEST_SETS, d["generic_name"]
            assert e.get("status") != "test", d["generic_name"]


def test_no_serve_path_reads_the_test_entries_file():
    """Only the exporter names it; the server's modules never load it."""
    readers = [p.name for p in SERVER.glob("*.py")
               if "drug_contracts_ems_test" in p.read_text(encoding="utf-8")]
    assert readers == []
    assert "drug_contracts_ems_test" in (SERVER / "tools" / "export_pocket_bank.py").read_text()


def test_the_test_entries_file_is_gitignored():
    """It reproduces the agency's formulary; the repo is public."""
    lines = (REPO / ".gitignore").read_text().splitlines()
    assert "server/drug_contracts_ems_test.json" in lines


def test_the_real_ems_set_still_holds_the_22_signed_entries():
    ems = [e for d in dc.DRUGS.values() for e in d.get("dose_entries", [])
           if e.get("set") == "EMS"]
    assert len(ems) == 22
    assert all(dc.entry_is_servable(e, served_set="EMS")[0] for e in ems)


# ── the exporter: --test writes bank-ems-test.json, test:true ────────────────

def test_the_test_set_file_names():
    assert ex.file_names("EMS-TEST") == {"bank": "bank-ems-test.json",
                                         "kit": "kit-ems-test.json",
                                         "manifest": "manifest-ems-test.json"}


def test_a_test_bank_carries_its_entries_unsigned_with_status_test():
    bank = ex.build_test_bank(_test_doc(), version="v")
    assert bank["set"] == "EMS-TEST" and bank["test"] is True
    (e,) = bank["entries"]
    assert e["status"] == "test" and e["set"] == "EMS-TEST"
    assert e["signoff"] is False
    assert e["check_failed"] == []
    assert e["drug"] == "testosteril" and e["rule"]["units"] == "mg/kg"


def test_check_failed_travels_with_its_reasons():
    why = ["check (a): dose 1 mg/kg not in the row", "contradicts its own card: x"]
    bank = ex.build_test_bank(_test_doc(_test_entry(check_failed=why)), version="v")
    assert bank["entries"][0]["check_failed"] == why


@pytest.mark.parametrize("over, match", [
    ({"set": "EMS"}, "EMS-TEST"),
    ({"set": "PFC"}, "EMS-TEST"),
    ({"status": None}, "status"),
    ({"signoff": True}, "signed"),
    ({"check_failed": "check (a)"}, "check_failed"),
    ({"dose_range": {"min": 2, "max": 2, "units": "mEq", "per_kg": False}}, "dose"),
    ({"indication_class": None}, "class"),
])
def test_a_test_bank_holds_test_entries_only(over, match):
    with pytest.raises(ex.ExportRefused, match=match):
        ex.build_test_bank(_test_doc(_test_entry(**over)), version="v")


def test_a_test_bank_is_written_under_its_own_names_with_test_true(tmp_path):
    bank = ex.build_test_bank(_test_doc(), version="v")
    man = ex.write_export(tmp_path, bank, {"kit_id": "k", "vials": []}, GIT, {}, test=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "bank-ems-test.json", "kit-ems-test.json", "manifest-ems-test.json"]
    on_disk = json.loads((tmp_path / "manifest-ems-test.json").read_text())
    assert on_disk == man
    assert man["test"] is True and man["set"] == "EMS-TEST"
    assert json.loads((tmp_path / "bank-ems-test.json").read_text())["test"] is True


def test_without_the_flag_a_test_bank_is_refused(tmp_path):
    bank = ex.build_test_bank(_test_doc(), version="v")
    with pytest.raises(ex.ExportRefused, match="--test"):
        ex.write_export(tmp_path, bank, {"kit_id": "k", "vials": []}, GIT, {})
    assert not any(tmp_path.iterdir())


def test_without_the_flag_anything_unsigned_is_still_refused(tmp_path):
    bank = {"set": "EMS", "bank_version": "v", "no_signed_dose": [],
            "unsigned_left_out": 0, "other_set_left_out": 0,
            "entries": [dict(_test_entry(set="EMS"), drug="testosteril", signer=None, date=None)]}
    with pytest.raises(ex.ExportRefused, match="signoff"):
        ex.write_export(tmp_path, bank, {"kit_id": "k", "vials": []}, GIT, {})


def test_the_flag_does_not_turn_a_signed_bank_into_a_test_bank(tmp_path):
    bank = {"set": "EMS", "bank_version": "v", "entries": [], "no_signed_dose": [],
            "unsigned_left_out": 0, "other_set_left_out": 0}
    with pytest.raises(ex.ExportRefused, match="test"):
        ex.write_export(tmp_path, bank, {"kit_id": "k", "vials": []}, GIT, {}, test=True)


def test_a_signed_export_manifest_carries_no_test_key(tmp_path):
    """The PFC and EMS exports keep their bytes."""
    bank = {"set": "EMS", "bank_version": "v", "entries": [], "no_signed_dose": [],
            "unsigned_left_out": 0, "other_set_left_out": 0}
    man = ex.write_export(tmp_path, bank, {"kit_id": "k", "vials": []}, GIT, {})
    assert "test" not in man


def test_the_signed_exporter_never_builds_the_test_set():
    with pytest.raises(ex.ExportRefused, match="EMS-TEST"):
        ex.build_bank(dc.DRUGS, version="v", classify=lambda _l: "c", set_name="EMS-TEST")


def test_a_test_entry_reaching_the_signed_exporter_is_left_out_or_refused():
    """Unsigned: left out and counted. Marked signed: it fails the gate, so the
    whole export is refused."""
    drugs = {"testosteril": {"generic_name": "testosteril", "aliases": [],
                             "dose_entries": [_test_entry(set="EMS")]}}
    bank = ex.build_bank(drugs, version="v", classify=lambda _l: "c", set_name="EMS")
    assert bank["entries"] == [] and bank["unsigned_left_out"] == 1
    signed = dict(_test_entry(set="EMS"), signoff=True, reviewed_by="clinician",
                  review_date="2026-11-13")
    drugs["testosteril"]["dose_entries"] = [signed]
    with pytest.raises(ex.ExportRefused, match="test"):
        ex.build_bank(drugs, version="v", classify=lambda _l: "c", set_name="EMS")


def test_the_cli_test_flag_selects_the_test_set():
    args = ex.parse_args(["--out", "x", "--test"])
    assert args.test is True
    with pytest.raises(SystemExit):
        ex.parse_args(["--out", "x", "--set", "EMS-TEST"])  # the set needs the flag


def test_the_cli_refuses_the_flag_with_a_signed_set(tmp_path, capsys):
    assert ex.main(["--out", str(tmp_path), "--test", "--set", "PFC"]) == 1
    assert "EMS-TEST" in capsys.readouterr().err


def test_the_test_export_reads_the_gitignored_file_and_pins_its_hash(tmp_path, monkeypatch):
    entries = tmp_path / "drug_contracts_ems_test.json"
    entries.write_text(json.dumps(_test_doc()))
    kit = tmp_path / "kit.json"
    kit.write_text(json.dumps({"schema_version": "1.0.0", "kit_id": "test-kit", "entries": [
        {"generic_name": "testosteril", "confirm_required": False, "presentations": [
            {"label_text": "100 mg / 10 mL", "mass_mg": 100.0, "volume_ml": 10.0,
             "concentration_mg_ml": 10.0, "signoff": True, "reviewed_by": "clinician",
             "review_date": "2026-11-12"}]}]}))
    monkeypatch.setattr(ex, "git_state", lambda: GIT)
    man = ex.export(tmp_path / "out", kit_path=kit, test=True, entries_path=entries)
    assert man["test"] is True and man["set"] == "EMS-TEST"
    assert re.fullmatch(r"[0-9a-f]{64}", man["inputs_sha256"]["drug_contracts_ems_test.json"])
    assert man["counts"]["entries"] == 1
    assert ex.DEFAULT_TEST_ENTRIES == SERVER / "drug_contracts_ems_test.json"
