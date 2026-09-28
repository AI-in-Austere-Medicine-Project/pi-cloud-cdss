"""
EdgeCDSS — A13: the dead safety_rules.json path is removed.

Found in #98. clinical_router.check_safety_rules() substring-matched
safety_rules.json against the query, and its result (RoutingResult.
safety_concerns) went only to a console print: it reached no answer and no
hold. Its dose_limits were also a stale mirror of the dose bank (FINDINGS
DP-7). Owner, #98 review: remove it, with a test that nothing depended on it.

Nothing depended on it: the protections its rules described are enforced
elsewhere, deterministically, and still hold (below). The pipeline replay in
the PR shows every stored query byte-identical.

    cd server && ./run_unit_tests.sh
"""
import os
import pathlib

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import clinical_router as cr  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402

SERVER = pathlib.Path(__file__).resolve().parent.parent


def test_the_router_no_longer_loads_or_checks_safety_rules():
    router = cr.ClinicalRouter()
    assert not hasattr(router, "safety_rules")
    assert not hasattr(cr.ClinicalRouter, "check_safety_rules")
    assert "safety_concerns" not in cr.RoutingResult.__dataclass_fields__


def test_the_file_and_its_generator_are_gone():
    assert not (SERVER / "safety_rules.json").exists()
    gen = (SERVER / "tools" / "build_protocol_index.py").read_text()
    assert "safety_rules" not in gen


def test_no_server_code_reads_it():
    for path in SERVER.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        assert "safety_rules" not in text and "safety_concerns" not in text, path


# ── Nothing depended on it: the protections live elsewhere ─────────────────

class _Retrieval:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: "STUB")
    return lambda q: oc._query_with_rag_internal(q, _Retrieval(), conversation_history=[])


def test_wpw_drugs_are_still_blocked(run):
    r = run("patient with WPW in a fast irregular rhythm, can I give adenosine")
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", r["source_mode"]
    assert "adenosine" in r["response"].lower()


def test_steroids_in_tbi_are_still_held():
    check = oc.run_deterministic_checks(
        "severe head injury, GCS 7", "Give dexamethasone 10 mg IV.", oc.PatientContext(), [])
    assert any("CRASH" in i for i in check.issues), check.issues
