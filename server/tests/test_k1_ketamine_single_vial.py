"""K1: ketamine 500 mg / 10 mL (50 mg/mL) is the kit's single ketamine vial.

Owner, 2026-10-28: "sign ketamine 500 mg/10 mL (50 mg/mL) as the kit's
single ketamine vial, owner declaration Andrew Azelton, dated. Failing test
first: "ketamine for pain, 75 kg IV" with no vial stated serves mg and mL
("0.375 mL of 50 mg/mL, kit") without the vial question; a different
concentration stated in the question still overrides it."

The signature itself is deployment state (drug_concentrations.json is
gitignored: a claim about one bag), made with
tools/set_concentration.py --single. These tests pin the kit they need, as
the suite does (conftest.py):
- `single_vial`: ketamine's one presentation, signed, confirm_required off;
- the conftest kit (two presentations, confirm_required) for the tool tests.

"Overrides" here: a strength stated in the question that is not the kit's
signed vial withholds the kit's volume (mg only, the vial question) rather
than computing one from it. No path believes a concentration read from free
text (drug_concentrations.match_confirmation).

    cd server && ./run_unit_tests.sh
"""
import copy
import json
import os
import re
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_concentrations as dcn  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
ASK = "ketamine for pain, 75 kg IV"
DRAW = "Draw 0.375 mL of 50mg/mL ketamine IV (18.75 mg)"
VIAL_Q = "Which ketamine do you have"

_LABEL_RE = re.compile(r"\d+(?:\.\d+)?\s*mg\s*/\s*\d+(?:\.\d+)?\s*mL\s*(?:vial|ampoule|amp)\b"
                       r"|\d+(?:\.\d+)?\s*(?:mg|mcg)\s*/\s*mL", re.IGNORECASE)
_ML_RE = re.compile(r"\d(?:\.\d+)?\s*mL\b", re.IGNORECASE)


def ml_volumes(text):
    return _ML_RE.findall(_LABEL_RE.sub(" ", text or ""))


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def single_vial(monkeypatch):
    """The K1 kit: ketamine's 500 mg / 10 mL vial alone, signed, no vial question."""
    entries = copy.deepcopy(dcn.ENTRIES)
    k = entries["ketamine"]
    k["presentations"] = [p for p in k["presentations"] if p["label_text"] == "500 mg / 10 mL vial"]
    assert len(k["presentations"]) == 1 and dcn.presentation_is_signed(k["presentations"][0])
    k["confirm_required"] = False
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    return entries


@pytest.fixture
def gen(monkeypatch):
    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        return "STUB"
    monkeypatch.setattr(providers, "chat", chat)


def ask(q, history=()):
    return oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(history))["response"]


# ── the kit's single vial: mg and mL, no question ───────────────────────────

def test_no_vial_stated_serves_mg_and_ml_from_the_kit_vial(single_vial, gen):
    r = ask(ASK)
    assert DRAW in r, r
    assert VIAL_Q not in r
    assert "NO VOLUME" not in r


def test_the_kit_resolves_ketamine_without_asking(single_vial):
    status, conc, pres = dcn.resolve("ketamine")
    assert (status, conc) == (dcn.RESOLVED, 50.0)
    assert pres["label_text"] == "500 mg / 10 mL vial"


@pytest.mark.parametrize("stated", ["500 mg / 10 mL", "50 mg/mL", "the 500 mg in 10 mL vial"])
def test_stating_the_kit_vial_serves_the_same_volume(single_vial, gen, stated):
    r = ask(f"{ASK}, I have {stated}")
    assert DRAW in r, r


# ── a different concentration stated in the question overrides the kit ─────

@pytest.mark.parametrize("stated", ["100 mg/mL", "10 mg/mL vial", "200 mg / 20 mL", "500 mg / 5 mL"])
def test_a_different_concentration_stated_withholds_the_kit_volume(single_vial, gen, stated):
    r = ask(f"{ASK}, I have the {stated}")
    assert "18.75 mg" in r, r
    assert "50mg/mL" not in r.replace(" ", "") or "Draw" not in r, r
    assert ml_volumes(r) == [], r
    assert "NO VOLUME" in r or VIAL_Q in r, r


def test_an_override_said_earlier_in_the_patient_still_holds(single_vial, gen):
    first = f"{ASK}, I have the 100 mg/mL"
    r = ask("ketamine for pain again, 75 kg IV", history=[{"query": first, "response": ask(first)}])
    assert "18.75 mg" in r, r
    assert ml_volumes(r) == [], r


def test_the_override_is_never_used_to_compute_a_volume(single_vial, gen):
    # 18.75 mg of a 100 mg/mL vial would be 0.1875 mL. That number must not appear.
    r = ask(f"{ASK}, I have the 100 mg/mL")
    assert "0.188" not in r and "0.1875" not in r and "0.19 mL" not in r, r


def test_the_override_applies_to_any_single_vial_drug(gen):
    # The conftest kit's rocuronium: one signed vial, 100 mg / 10 mL (10 mg/mL).
    status, conc, _ = dcn.resolve("rocuronium")
    assert (status, conc) == (dcn.RESOLVED, 10.0)
    ctx = oc.extract_patient_context("80 kg adult RSI, rocuronium, I have the 20 mg/mL vials")
    assert oc.vial_unconfirmed("rocuronium", ctx)


# ── the declaration: set_concentration.py --single ──────────────────────────

@pytest.fixture
def kit_file(tmp_path, monkeypatch):
    """The conftest kit written to a temp file the tool edits."""
    raw = copy.deepcopy(dcn._RAW)
    path = tmp_path / "drug_concentrations.json"
    path.write_text(json.dumps(raw))
    monkeypatch.setattr(dcn, "CONFIG", path)
    monkeypatch.setattr(dcn, "CHANGE_LOG", tmp_path / "log.jsonl")
    return path


def run_tool(monkeypatch, *argv):
    sys.path.insert(0, str(dcn._DIR / "tools"))
    import set_concentration
    monkeypatch.setattr(sys, "argv", ["set_concentration.py", *argv])
    return set_concentration.main()


DECLARE = ["--drug", "ketamine", "--single", "500 mg / 10 mL vial", "--by", "clinician",
           "--date", "2026-10-28", "--reason",
           "Owner declaration, Andrew Azelton, 2026-10-28: the kit's single ketamine vial"]


def test_single_declares_the_one_vial_and_drops_the_question(kit_file, monkeypatch):
    assert run_tool(monkeypatch, *DECLARE) == 0
    k = [e for e in json.loads(kit_file.read_text())["entries"] if e["generic_name"] == "ketamine"][0]
    assert k["confirm_required"] is False
    assert [p["label_text"] for p in k["presentations"]] == ["500 mg / 10 mL vial"]
    p = k["presentations"][0]
    assert p["signoff"] is True and p["reviewed_by"] == "clinician" and p["review_date"] == "2026-10-28"
    assert "Andrew Azelton" in k["single_vial"]["declaration"]
    assert k["single_vial"]["date"] == "2026-10-28"
    entries, rejections, _ = dcn._load()
    assert rejections == []
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    assert dcn.resolve("ketamine")[:2] == (dcn.RESOLVED, 50.0)


def test_single_is_logged_with_what_it_removed(kit_file, monkeypatch):
    run_tool(monkeypatch, *DECLARE)
    rec = json.loads(dcn.CHANGE_LOG.read_text().strip().split("\n")[-1])
    assert rec["event"] == "SINGLE_VIAL" and rec["drug"] == "ketamine"
    assert rec["removed"] == ["200 mg / 20 mL vial"]
    assert "Andrew Azelton" in rec["reason"] and rec["snapshot"] and rec["config_hash"]


@pytest.mark.parametrize("bad", [
    ["--by", "someone"],             # not an authorised signer
    ["--date", ""],                  # no date
    ["--reason", ""],                # no declaration
])
def test_single_needs_a_signer_a_date_and_the_declaration(kit_file, monkeypatch, bad):
    argv = list(DECLARE)
    flag = bad[0]
    argv[argv.index(flag) + 1] = bad[1]
    before = kit_file.read_text()
    assert run_tool(monkeypatch, *argv) == 1
    assert kit_file.read_text() == before


def test_single_refuses_a_vial_the_kit_does_not_declare(kit_file, monkeypatch):
    argv = list(DECLARE)
    argv[argv.index("--single") + 1] = "1000 mg / 10 mL vial"
    before = kit_file.read_text()
    assert run_tool(monkeypatch, *argv) == 1
    assert kit_file.read_text() == before
