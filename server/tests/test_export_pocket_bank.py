"""The Pocket bank exporter (owner, 2026-11-04).

EdgeCDSS Pocket signs nothing: every number on the device comes from this
export. So the tests pin the one promise that matters: an unsigned entry cannot
leave this repo, whichever way it arrives. Fixtures use the same obviously
synthetic drug as test_drug_contracts.py.
"""
import copy
import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import drug_concentrations as cc
import drug_contracts as dc
import export_pocket_bank as ex


def _source(tier=1, **extra):
    return {"citation": "TEST guideline, p.7", "tier": tier, "url": "test://source",
            "retrieved_date": "2026-08-24", **extra}


def _entry(**over):
    e = {"indication": "moderate to severe pain / analgesia", "population": "adult",
         "route": "IV",
         "dose_range": {"min": 1.0, "max": 1.0, "units": "mg/kg", "per_kg": True},
         "max_single": {"value": 50.0, "units": "mg", "rule": "max 50 mg"},
         "max_cumulative": None,
         "contraindications": ["Test contraindication"],
         "cautions": ["First serve caution.", "Repeat q5min.",
                      {"tier": "detail", "text": "A detail line."}],
         "sources": [_source(page=7, quote="1 mg/kg", supports="1 mg/kg IV")],
         "signoff": True, "reviewed_by": "AI-AIM", "review_date": "2026-11-01",
         "version": "1.0.0"}
    e.update(over)
    return e


def _drug(*entries, name="testosteril", aliases=("testo",)):
    return {"generic_name": name, "aliases": list(aliases), "forms": [],
            "routes": ["IV"], "dose_entries": list(entries)}


def _names(drugs):
    return {d["generic_name"]: d for d in drugs}


GIT = {"commit": "a" * 40, "date": "2026-11-04"}


def _vial(**over):
    p = {"label_text": "100 mg / 10 mL vial", "mass_mg": 100.0, "volume_ml": 10.0,
         "concentration_mg_ml": 10.0, "signoff": True, "reviewed_by": "clinician",
         "review_date": "2026-10-28"}
    p.update(over)
    return p


def _kit_raw(*pres, kit_id="test-kit", name="testosteril"):
    return {"schema_version": "1.0.0", "kit_id": kit_id,
            "entries": [{"generic_name": name, "confirm_required": False,
                         "presentations": list(pres)}]}


# ── what an entry carries ──────────────────────────────────────────────────

def test_every_requested_field_is_on_the_entry():
    bank = ex.build_bank(_names([_drug(_entry())]), version="v", classify=lambda _l: "pain")
    e = bank["entries"][0]
    for field in ("drug", "aliases", "indication", "population", "route", "rule", "cap",
                  "repeat", "cautions", "dilution", "source", "page", "quote",
                  "signer", "date"):
        assert field in e, field
    assert e["drug"] == "testosteril"
    assert "testo" in e["aliases"]
    assert e["rule"] == {"min": 1.0, "max": 1.0, "units": "mg/kg", "per_kg": True}
    assert e["cap"]["max_single"]["value"] == 50.0
    assert e["signer"] == "AI-AIM"
    assert e["date"] == "2026-11-01"
    assert e["page"] == 7
    assert e["quote"] == "1 mg/kg"


def test_the_fields_a_dose_cannot_be_read_without_also_travel():
    """Not on the requested list, but the engine fails unsafe without them."""
    e = ex.build_bank(_names([_drug(_entry(
        min_single={"value": 0.1, "units": "mg", "rule": "floor"}, min_age_months=3))]),
        version="v", classify=lambda _l: "pain")["entries"][0]
    assert e["floor"]["value"] == 0.1
    assert e["min_age_months"] == 3
    assert e["contraindications"] == ["Test contraindication"]
    assert e["indication_class"] == "pain"
    assert e["serve_cautions"] == ["First serve caution.", "Repeat q5min."]


def test_repeat_is_the_signed_wording_verbatim_and_never_parsed():
    e = ex.build_bank(_names([_drug(_entry())]), version="v",
                      classify=lambda _l: "pain")["entries"][0]
    assert e["repeat"] == ["Repeat q5min."]
    bare = _entry(cautions=["No such line."])
    e = ex.build_bank(_names([_drug(bare)]), version="v",
                      classify=lambda _l: "pain")["entries"][0]
    assert e["repeat"] == []


def test_a_page_stated_only_in_the_citation_is_read_from_it_and_no_quote_stays_null():
    entry = _entry(sources=[_source()])  # "TEST guideline, p.7", no page, no quote
    e = ex.build_bank(_names([_drug(entry)]), version="v",
                      classify=lambda _l: "pain")["entries"][0]
    assert e["page"] == 7
    assert e["quote"] is None


def test_the_named_source_is_not_one_cited_only_for_another_field():
    entry = _entry(sources=[
        _source(citation="MIGRATION", tier=0),
        _source(citation="SMOG, p.127, cited for the age floor only, not the dose"),
        _source(citation="JTS, p.33", page=33, quote="the dose", supports="contraindications"),
        _source(citation="JTS ID91, p.9", page=9, quote="1 mg/kg", supports="1 mg/kg IV"),
    ])
    e = ex.build_bank(_names([_drug(entry)]), version="v",
                      classify=lambda _l: "pain")["entries"][0]
    assert e["source"] == "JTS ID91, p.9"
    assert e["source_basis"] == "dose"
    assert len(e["sources"]) == 4


def test_an_owner_declared_entry_names_the_declaration_as_its_source():
    entry = next(e for d in dc.DRUGS.values() for e in d["dose_entries"]
                 if dc.is_owner_declared(e) and dc.entry_is_servable(e, d)[0])
    out = ex.export_entry("ketamine", {"aliases": []}, entry, classify=lambda _l: "pain")
    assert out["owner_declared"] is True
    assert out["source"].startswith("Owner declaration")
    assert entry["owner_declaration"]["declared_by"] in out["source"]
    assert out["serve_cautions"][0] == "OWNER-DECLARED dose — not a guideline value."


# ── the refusal ────────────────────────────────────────────────────────────

def test_an_unsigned_entry_is_left_out_and_counted():
    drugs = _names([_drug(_entry(), _entry(route="IM", signoff=False))])
    bank = ex.build_bank(drugs, version="v", classify=lambda _l: "pain")
    assert [e["route"] for e in bank["entries"]] == ["IV"]
    assert bank["unsigned_left_out"] == 1


def test_a_signed_entry_that_fails_the_fence_refuses_the_whole_export():
    """Signed but unservable is a contradiction, not a filter: dropping it
    quietly would ship a smaller bank nobody decided on."""
    bad = _entry(reviewed_by="somebody")
    with pytest.raises(ex.ExportRefused, match="testosteril"):
        ex.build_bank(_names([_drug(_entry(), bad)]), version="v", classify=lambda _l: "pain")


@pytest.mark.parametrize("field,value", [
    ("signoff", False),
    ("signer", "PENDING_CLINICAL_SIGNOFF"),
    ("signer", "somebody"),
    ("date", ""),
    ("quote", "NEEDS_MANUAL_ENTRY"),
])
def test_the_writer_itself_refuses_an_unsigned_entry(tmp_path, field, value):
    """The last guard: even a bank built some other way cannot be written."""
    bank = ex.build_bank(_names([_drug(_entry())]), version="v", classify=lambda _l: "pain")
    bank["entries"][0][field] = value
    with pytest.raises(ex.ExportRefused):
        ex.write_export(tmp_path, bank, {"kit_id": "k", "vials": []}, GIT, {})
    assert list(tmp_path.iterdir()) == []


def test_an_entry_with_no_class_refuses_the_export():
    """Pocket cannot ask for what it has no word for."""
    with pytest.raises(ex.ExportRefused, match="class"):
        ex.build_bank(_names([_drug(_entry())]), version="v", classify=lambda _l: None)


def test_a_drug_with_nothing_signed_exports_its_names_and_no_number():
    drugs = _names([_drug(_entry()),
                    _drug(_entry(signoff=False), name="unsignedol", aliases=("unsi",))])
    bank = ex.build_bank(drugs, version="v", classify=lambda _l: "pain")
    names = {n["drug"]: n for n in bank["no_signed_dose"]}
    assert names["unsignedol"]["aliases"] == ["unsi"]
    assert set(names["unsignedol"]) == {"drug", "aliases"}
    assert all(e["drug"] != "unsignedol" for e in bank["entries"])


# ── the kit ────────────────────────────────────────────────────────────────

def test_the_kit_carries_signed_vials_only(tmp_path):
    raw = _kit_raw(_vial(), _vial(label_text="5 mg / 1 mL vial", mass_mg=5.0, volume_ml=1.0,
                                  concentration_mg_ml=5.0, signoff=False))
    path = tmp_path / "kit.json"
    path.write_text(json.dumps(raw))
    kit = ex.build_kit(path)
    assert kit["kit_id"] == "test-kit"
    assert [v["label"] for v in kit["vials"]] == ["100 mg / 10 mL vial"]
    v = kit["vials"][0]
    assert (v["drug"], v["concentration_mg_ml"]) == ("testosteril", 10.0)
    assert (v["signer"], v["date"]) == ("clinician", "2026-10-28")


def test_the_shipped_example_kit_is_refused():
    example = pathlib.Path(cc.__file__).parent / "drug_concentrations.example.json"
    with pytest.raises(ex.ExportRefused, match="(?i)example"):
        ex.build_kit(example)


def test_an_example_kit_under_any_filename_is_refused(tmp_path):
    path = tmp_path / "kit.json"
    path.write_text(json.dumps(_kit_raw(_vial(), kit_id="example-unsigned")))
    with pytest.raises(ex.ExportRefused, match="(?i)example"):
        ex.build_kit(path)


def test_a_missing_kit_is_refused_not_exported_empty(tmp_path):
    with pytest.raises(ex.ExportRefused):
        ex.build_kit(tmp_path / "absent.json")


def test_the_writer_refuses_an_unsigned_vial(tmp_path):
    bank = ex.build_bank(_names([_drug(_entry())]), version="v", classify=lambda _l: "pain")
    kit = {"kit_id": "k", "vials": [{"drug": "testosteril", "label": "x", "mass_mg": 1.0,
                                     "volume_ml": 1.0, "concentration_mg_ml": 1.0,
                                     "signer": "PENDING_CLINICAL_SIGNOFF", "date": ""}]}
    with pytest.raises(ex.ExportRefused):
        ex.write_export(tmp_path, bank, kit, GIT, {})


# ── the manifest ───────────────────────────────────────────────────────────

def test_the_manifest_hashes_what_was_written(tmp_path):
    bank = ex.build_bank(_names([_drug(_entry())]), version="1.4.0+x", classify=lambda _l: "pain")
    ex.write_export(tmp_path, bank, {"kit_id": "k", "vials": []}, GIT, {"drug_contracts.json": "f" * 64})
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["bank_version"] == "1.4.0+x"
    assert man["edgecdss_commit"] == "a" * 40
    for name in ("bank.json", "kit.json"):
        assert man["sha256"][name] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    assert man["inputs_sha256"]["drug_contracts.json"] == "f" * 64
    assert man["counts"]["entries"] == 1


def test_the_export_is_byte_for_byte_repeatable(tmp_path):
    """No clock in the output: a hash that moves on every run proves nothing."""
    bank = ex.build_bank(_names([_drug(_entry())]), version="v", classify=lambda _l: "pain")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    for d in (a, b):
        ex.write_export(d, copy.deepcopy(bank), {"kit_id": "k", "vials": []}, GIT, {})
    for name in ("bank.json", "kit.json", "manifest.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_a_dirty_contract_file_refuses_the_export(monkeypatch, tmp_path):
    """The manifest names a commit, so the commit has to be what was read."""
    monkeypatch.setattr(ex, "git_state", lambda: (_ for _ in ()).throw(
        ex.ExportRefused("server/drug_contracts.json has uncommitted changes")))
    with pytest.raises(ex.ExportRefused, match="uncommitted"):
        ex.export(tmp_path / "out", kit_path=tmp_path / "kit.json")


# ── the real bank ──────────────────────────────────────────────────────────

def test_the_real_bank_exports_every_servable_entry_and_no_other():
    bank = ex.build_bank(dc.DRUGS, version="v")
    live = dc.servable_entries()
    assert len(bank["entries"]) == sum(len(v) for v in live.values())
    got = {(e["drug"], e["indication"], e["route"], e["population"]) for e in bank["entries"]}
    want = {(n, e["indication"], e["route"], e["population"])
            for n, es in live.items() for e in es}
    assert got == want
    assert all(e["signer"] in dc.SIGNOFF_AUTHORS for e in bank["entries"])
    assert not dc.has_sentinel(bank)


def test_the_real_bank_names_the_drugs_it_has_no_dose_for():
    bank = ex.build_bank(dc.DRUGS, version="v")
    names = {n["drug"] for n in bank["no_signed_dose"]}
    assert {"ketorolac", "magnesium sulfate"} <= names
    assert not names & {e["drug"] for e in bank["entries"]}
    ketorolac = next(n for n in bank["no_signed_dose"] if n["drug"] == "ketorolac")
    assert "toradol" in ketorolac["aliases"]
