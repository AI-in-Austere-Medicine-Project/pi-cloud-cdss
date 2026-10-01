"""D1b: docs/EVALUATION_SET_30.md is the frozen 30-set, with a failure criterion
for every scenario (owner, 2026-09-28; drafted for sign-off).

The doc's query text is tied to the pinned bank: every query must hash into
tools/distill/eval_exclusions.json, so the document cannot drift from the exam
the benchmarks run.
"""
import importlib.util
import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DOC = REPO / "docs/EVALUATION_SET_30.md"
BANK = pathlib.Path("/home/andrew/projects/cdss-eval/runs/run-tests-mm3-20260925/scenarios-30.jsonl")

spec = importlib.util.spec_from_file_location("build_distill_dataset", REPO / "tools/build_distill_dataset.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)


def _sections():
    text = DOC.read_text()
    parts = re.split(r"^### \d+\. `([^`]+)`\s*$", text, flags=re.M)
    return [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]


def test_thirty_distinct_scenarios():
    ids = [sid for sid, _ in _sections()]
    assert len(ids) == 30 and len(set(ids)) == 30


def test_every_scenario_has_a_failure_criterion_and_a_gate():
    for sid, body in _sections():
        assert "**Fails if**" in body, sid
        assert re.search(r"^\s+1\. \S", body, re.M), sid
        assert re.search(r"\*\*Gate:\*\* (SERVE|SERVE_NO_DOSE)\.", body), sid


def test_the_universal_criteria_are_stated():
    text = DOC.read_text()
    for u in ("U1", "U2", "U3", "U4", "U5"):
        assert f"**{u}," in text, u


def test_every_query_in_the_doc_is_in_the_pinned_bank():
    pin = json.loads((REPO / "tools/distill/eval_exclusions.json").read_text())
    hashes = set(pin["query_sha256"])
    queries = [m.group(1) for _, body in _sections()
               for m in [re.search(r'^- \*\*Query:\*\* "(.*)"$', body, re.M)]]
    assert len(queries) == 30
    for q in queries:
        assert bd.qhash(q) in hashes, q
    assert pin["scenarios_30_sha256"] in DOC.read_text()


@pytest.mark.skipif(not BANK.exists(), reason="cdss-eval bank not on this machine")
def test_the_doc_matches_the_bank_in_order():
    bank = [json.loads(l) for l in open(BANK)]
    secs = _sections()
    assert [s["id"] for s in bank] == [sid for sid, _ in secs]
    for s, (_, body) in zip(bank, secs):
        assert f'- **Query:** "{s["query"]}"' in body, s["id"]


def test_the_set_is_signed_by_the_owner_with_no_open_decisions():
    # Signed by Andrew Azelton on 2026-10-01, marked on the owner's instruction (#119 review).
    text = DOC.read_text()
    assert "**Status: SIGNED** by Andrew Azelton (owner), 2026-10-01." in text
    assert "**Signed: Andrew Azelton (owner), 2026-10-01.**" in text
    assert "Signing is the owner's act" in text
    for marker in ("[draft:", "[owner decision]", "DRAFT", "Unsigned"):
        assert marker not in text, marker


def test_the_owner_rulings_are_in_the_signed_text():
    secs = dict(_sections())
    assert "signed levetiracetam dose or a signed ketamine second-line" in secs["H-S3"]
    assert "The universal criteria only" in secs["H-IM-06"] and "guidance gap" in secs["H-IM-06"]
    assert "not from the signed concentrations kit" in secs["G-ADV-10"]
    marked = re.findall(r"^\s+\d+\. .*\[guideline-derived; read by the owner\]", DOC.read_text(), re.M)
    assert len(marked) == 17
