"""
set_contract.py — the signing tool's refusals.

Every test here writes to a COPY of drug_contracts.json in tmp_path. The
shipped file is asserted unsigned at the end of the module, because a signing
tool whose own test suite signs the real file is the accident it exists to
prevent.

WHY THE TOOL RE-CHECKS WHAT THE ENGINE ALREADY CHECKS
─────────────────────────────────────────────────────
All four named refusals are also in entry_is_servable(), and that is the point:
the fence must not be bypassable, and a tool is bypassable by not using it. So
these tests assert the two agree — test_the_tool_never_signs_what_the_engine
_would_not_serve walks every entry in the shipped file and checks that the tool
refuses whatever the engine refuses. The tool is allowed to be STRICTER; it is
never allowed to be looser.
"""
import json
import shutil

import pytest

import drug_contracts as dc
import set_contract as sc


SIGNER = dc.SIGNOFF_AUTHORS[0]
DATE = "2026-08-25"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A private copy of the contract file plus its log."""
    cfg = tmp_path / "drug_contracts.json"
    shutil.copy(dc._DIR / "drug_contracts.json", cfg)
    monkeypatch.setattr(sc, "CONFIG", cfg)
    monkeypatch.setattr(sc, "CHANGE_LOG", tmp_path / "contracts.log.jsonl")
    return cfg


class Args:
    def __init__(self, **kw):
        self.drug = kw.get("drug", "ketamine")
        self.indication = kw.get("indication", "RSI induction")
        self.population = kw.get("population", "adult")
        self.route = kw.get("route", "IV")
        self.by = kw.get("by", SIGNER)
        self.date = kw.get("date", DATE)
        self.reason = kw.get("reason", "")


def _entry(cfg, drug, indication, population, route):
    doc = json.loads(cfg.read_text())
    d = next(x for x in doc["drugs"] if x["generic_name"] == drug)
    return next(e for e in d["dose_entries"]
                if (e["indication"], e["population"], e["route"])
                == (indication, population, route))


def _mutate(cfg, drug, indication, population, route, **changes):
    doc = json.loads(cfg.read_text())
    d = next(x for x in doc["drugs"] if x["generic_name"] == drug)
    e = next(x for x in d["dose_entries"]
             if (x["indication"], x["population"], x["route"])
             == (indication, population, route))
    e.update(changes)
    cfg.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return e


# ── the signer ──────────────────────────────────────────────────────────────

def test_an_unauthorised_signer_is_refused(sandbox, capsys):
    assert sc.cmd_sign(Args(by="andrew")) == 1
    assert "must be one of" in capsys.readouterr().out
    assert _entry(sandbox, "ketamine", "RSI induction", "adult",
                  "IV")["signoff"] is False


def test_an_empty_signer_is_refused(sandbox):
    assert sc.cmd_sign(Args(by=None)) == 1


def test_a_signature_without_a_date_is_refused(sandbox, capsys):
    assert sc.cmd_sign(Args(date=None)) == 1
    assert "--date is required" in capsys.readouterr().out


# ── the four content refusals ───────────────────────────────────────────────

def test_a_sentinel_anywhere_is_refused(sandbox, capsys):
    args = Args(indication="prolonged sedation infusion",
                population="adult|peds")
    assert sc.cmd_sign(args) == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out and "sentinel" in out


def test_a_sentinel_in_a_caution_alone_is_refused(sandbox, capsys):
    """Not just the clinical fields. A cautions[] line reading
    NEEDS_MANUAL_ENTRY is text a medic would be shown."""
    _mutate(sandbox, "ketamine", "RSI induction", "adult", "IV",
            cautions=["fine", dc.NEEDS_MANUAL])
    assert sc.cmd_sign(Args()) == 1
    assert "cautions" in capsys.readouterr().out


def test_the_pending_signature_fields_are_not_read_as_a_blocking_sentinel(sandbox):
    """reviewed_by is PENDING on every unsigned entry — that is what unsigned
    MEANS. Counting it as a sentinel would refuse every entry in the file."""
    assert sc.sign_refusal(_entry(sandbox, "ketamine", "RSI induction",
                                  "adult", "IV")) == ""


def test_a_tier_0_only_entry_is_refused(sandbox, capsys):
    _mutate(sandbox, "ketamine", "RSI induction", "adult", "IV",
            sources=[{"citation": "EdgeCDSS pre-contract hardcode", "tier": 0,
                      "url": "internal:openai_client.py",
                      "retrieved_date": "2026-08-24"}])
    assert sc.cmd_sign(Args()) == 1
    assert "tier 1 or tier 2" in capsys.readouterr().out


def test_an_entry_with_no_sources_at_all_is_refused(sandbox, capsys):
    _mutate(sandbox, "ketamine", "RSI induction", "adult", "IV", sources=[])
    assert sc.cmd_sign(Args()) == 1
    assert "cites no sources" in capsys.readouterr().out


def test_an_unadjudicated_source_conflict_is_refused(sandbox, capsys):
    e = _entry(sandbox, "ketamine", "RSI induction", "adult", "IV")
    e.pop("adjudication", None)
    _mutate(sandbox, "ketamine", "RSI induction", "adult", "IV",
            flags=["SOURCE_CONFLICT"], conflict_group="synthetic",
            adjudication=None)
    assert sc.cmd_sign(Args()) == 1
    out = capsys.readouterr().out
    assert "SOURCE_CONFLICT" in out and "adjudication" in out


def test_an_adjudicated_conflict_may_be_signed(sandbox):
    """Signing one of two conflicting entries IS the adjudication. Once it is
    written down, the flag stops blocking."""
    _mutate(sandbox, "ketamine", "RSI induction", "adult", "IV",
            flags=["SOURCE_CONFLICT"], conflict_group="synthetic",
            adjudication="OWNER RULING 2026-08-25: ID39 wins.")
    assert sc.cmd_sign(Args()) == 0


def test_a_migrated_unsourced_entry_is_refused(sandbox, capsys):
    args = Args(indication="post-intubation sedation — repeated bolus "
                           "(no infusion pump)", population="adult|peds")
    assert sc.cmd_sign(args) == 1
    assert "MIGRATED_UNSOURCED" in capsys.readouterr().out


def test_a_tier_1_citation_on_another_field_does_not_source_the_dose(sandbox):
    """WHY THE FLAG AND NOT THE TIER CHECK.

    Ketamine post-intubation sedation cites NASEMSO tier 1 — for its
    contraindications. Its dose_range is still the pre-contract hardcode. The
    tier check alone would pass it, because a tier number cannot say which
    FIELD its source backs. Both layers therefore gate on the flag.
    """
    e = _entry(sandbox, "ketamine",
               "post-intubation sedation — repeated bolus (no infusion pump)",
               "adult|peds", "IV")
    assert {s["tier"] for s in e["sources"]} == {0, 1}, \
        "premise is stale: this entry no longer carries a tier 1 citation"
    assert "MIGRATED_UNSOURCED" in sc.sign_refusal(e)
    candidate = dict(e, signoff=True, reviewed_by=SIGNER, review_date=DATE)
    assert "MIGRATED_UNSOURCED" in dc.entry_is_servable(candidate)[1]


def test_the_tool_never_signs_what_the_engine_would_not_serve(sandbox):
    """The tool may be stricter than the fence. It may never be looser."""
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            candidate = dict(e, signoff=True, reviewed_by=SIGNER,
                             review_date=DATE)
            engine_ok = dc.entry_is_servable(candidate, drug)[0]
            tool_ok = sc.sign_refusal(e) == ""
            assert engine_ok or not tool_ok, (
                f"{name}/{e['indication']}: the tool would sign an entry the "
                f"engine refuses to serve — {dc.entry_is_servable(candidate)[1]}")


# ── selection ───────────────────────────────────────────────────────────────

def test_the_selector_identifies_exactly_one_entry_everywhere():
    """drug + indication + population + route must never match two entries:
    the second one would be signed without being read."""
    seen = set()
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            key = (name, e["indication"], e["population"], e["route"])
            assert key not in seen, f"ambiguous selector: {key}"
            seen.add(key)


def test_a_selector_that_matches_nothing_lists_what_exists(sandbox, capsys):
    assert sc.cmd_sign(Args(indication="RSI paralytic")) == 1
    out = capsys.readouterr().out
    assert "no entry of ketamine matches" in out
    assert "--indication 'RSI induction'" in out


def test_an_ambiguous_selector_refuses_rather_than_guessing(sandbox, capsys):
    doc = json.loads(sandbox.read_text())
    ket = next(x for x in doc["drugs"] if x["generic_name"] == "ketamine")
    twin = next(e for e in ket["dose_entries"]
                if e["indication"] == "RSI induction"
                and e["population"] == "adult")
    ket["dose_entries"].append(json.loads(json.dumps(twin)))
    sandbox.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    assert sc.cmd_sign(Args()) == 1
    assert "refusing to guess" in capsys.readouterr().out


def test_an_unknown_drug_is_refused(sandbox, capsys):
    assert sc.cmd_sign(Args(drug="asprin")) == 1
    assert "no such drug" in capsys.readouterr().out


# ── what a signature actually writes ────────────────────────────────────────

def test_signing_writes_the_three_fields_and_nothing_else(sandbox):
    before = _entry(sandbox, "ketamine", "RSI induction", "adult", "IV")
    assert sc.cmd_sign(Args(reason="JTS ID39")) == 0
    after = _entry(sandbox, "ketamine", "RSI induction", "adult", "IV")
    changed = {k for k in set(before) | set(after)
               if before.get(k) != after.get(k)}
    assert changed == {"signoff", "reviewed_by", "review_date", "version"}
    assert (after["signoff"], after["reviewed_by"], after["review_date"]) == \
           (True, SIGNER, DATE)


def test_signing_drops_the_draft_suffix(sandbox):
    assert _entry(sandbox, "ketamine", "RSI induction", "adult",
                  "IV")["version"].endswith("-draft")
    sc.cmd_sign(Args())
    assert _entry(sandbox, "ketamine", "RSI induction", "adult",
                  "IV")["version"] == "0.3.0"


def test_a_signed_entry_becomes_servable(sandbox, monkeypatch):
    sc.cmd_sign(Args())
    doc = json.loads(sandbox.read_text())
    monkeypatch.setattr(dc, "DRUGS",
                        {d["generic_name"]: d for d in doc["drugs"]})
    assert any(e["indication"] == "RSI induction"
               for e in dc.servable_entries().get("ketamine", []))


def test_signing_twice_is_a_no_op(sandbox, capsys):
    assert sc.cmd_sign(Args()) == 0
    capsys.readouterr()
    assert sc.cmd_sign(Args(by="AI-AIM", date="2027-01-01")) == 0
    assert "already signed" in capsys.readouterr().out
    e = _entry(sandbox, "ketamine", "RSI induction", "adult", "IV")
    assert (e["reviewed_by"], e["review_date"]) == (SIGNER, DATE)


def test_a_refused_signature_writes_nothing_at_all(sandbox):
    before = sandbox.read_text()
    sc.cmd_sign(Args(indication="prolonged sedation infusion",
                     population="adult|peds"))
    assert sandbox.read_text() == before
    assert not sc.CHANGE_LOG.exists()


# ── the audit log ───────────────────────────────────────────────────────────

def test_the_audit_log_records_signer_date_and_what(sandbox):
    sc.cmd_sign(Args(reason="JTS ID39 standard induction"))
    rec = json.loads(sc.CHANGE_LOG.read_text().strip())
    assert rec["event"] == "SIGN"
    assert rec["signer"] == SIGNER and rec["date"] == DATE
    assert (rec["drug"], rec["indication"], rec["population"], rec["route"]) \
        == ("ketamine", "RSI induction", "adult", "IV")
    assert rec["dose_range"]["min"] == 2.0
    assert any("ID39" in c for c in rec["sources"])
    assert rec["reason"] == "JTS ID39 standard induction"
    assert rec["ts"] and rec["config_hash"]


def test_the_log_appends_rather_than_replaces(sandbox):
    sc.cmd_sign(Args())
    sc.cmd_sign(Args(population="peds"))
    lines = [l for l in sc.CHANGE_LOG.read_text().split("\n") if l.strip()]
    assert len(lines) == 2


def test_the_config_hash_follows_the_file(sandbox):
    sc.cmd_sign(Args())
    sc.cmd_sign(Args(population="peds"))
    hashes = [json.loads(l)["config_hash"]
              for l in sc.CHANGE_LOG.read_text().strip().split("\n")]
    assert hashes[0] != hashes[1]


# ── unsigning ───────────────────────────────────────────────────────────────

def test_unsigning_needs_no_signer(sandbox):
    """Withdrawing a dose claim degrades the system to silence. Requiring a
    credential to do it would be the failure mode this layer prevents."""
    sc.cmd_sign(Args())
    assert sc.cmd_unsign(Args(by=None, date=None)) == 0
    e = _entry(sandbox, "ketamine", "RSI induction", "adult", "IV")
    assert e["signoff"] is False
    assert e["reviewed_by"] == dc.PENDING
    assert e["version"] == "0.3.0-draft"


def test_unsigning_is_logged_with_who_it_was_signed_by(sandbox):
    sc.cmd_sign(Args())
    sc.cmd_unsign(Args(reason="value withdrawn"))
    rec = json.loads(sc.CHANGE_LOG.read_text().strip().split("\n")[-1])
    assert rec["event"] == "UNSIGN"
    assert rec["was_signed_by"] == [SIGNER, DATE]
    assert rec["reason"] == "value withdrawn"


def test_an_unsigned_entry_stops_serving(sandbox, monkeypatch):
    sc.cmd_sign(Args())
    sc.cmd_unsign(Args())
    doc = json.loads(sandbox.read_text())
    monkeypatch.setattr(dc, "DRUGS",
                        {d["generic_name"]: d for d in doc["drugs"]})
    assert "ketamine" not in dc.servable_entries()


# ── --list ──────────────────────────────────────────────────────────────────

def test_list_splits_ready_from_blocked(sandbox, capsys):
    assert sc.cmd_list() == 0
    out = capsys.readouterr().out
    assert "ready to sign" in out and "blocked on work" in out
    assert "0 signed" in out


def test_list_names_the_blocking_reason(sandbox, capsys):
    sc.cmd_list("ketamine")
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "MIGRATED_UNSOURCED" in out


def test_list_flags_a_signature_that_does_not_serve(sandbox, capsys, monkeypatch):
    """A signature by somebody not on the list looks signed in the file and
    serves nothing. Silence there would be the worst of both."""
    doc = json.loads(sandbox.read_text())
    ket = next(x for x in doc["drugs"] if x["generic_name"] == "ketamine")
    e = next(x for x in ket["dose_entries"]
             if x["indication"] == "RSI induction" and x["population"] == "adult")
    e.update({"signoff": True, "reviewed_by": "somebody",
              "review_date": "2026-08-25"})
    monkeypatch.setattr(dc, "DRUGS",
                        {d["generic_name"]: d for d in doc["drugs"]})
    sc.cmd_list("ketamine")
    assert "BROKEN" in capsys.readouterr().out


def test_list_refuses_an_unknown_drug(sandbox, capsys):
    assert sc.cmd_list("asprin") == 1
    assert "no such drug" in capsys.readouterr().out


# ── the shipped file ────────────────────────────────────────────────────────

def test_the_real_contract_file_is_still_entirely_unsigned():
    """Last line of defence. Nothing in this module may touch the real file."""
    raw = json.loads((dc._DIR / "drug_contracts.json").read_text())
    for d in raw["drugs"]:
        for e in d["dose_entries"]:
            assert e["signoff"] is False, f"{d['generic_name']}/{e['indication']}"


def test_the_tool_points_at_the_file_the_engine_reads():
    assert sc.CONFIG == dc._DIR / "drug_contracts.json"
