"""
EdgeCDSS — session log contract (T-13, T-1, T-2).

The session JSONL is the only audit surface this system has. These tests pin
its shape so a field cannot quietly disappear or go constant.

    cd server && ./run_unit_tests.sh
"""

import json
import os
import sys
import tempfile

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pathlib  # noqa: E402

import openai_client as oc  # noqa: E402
from openai_client import SAFETY_OVERRIDES  # noqa: E402


def log_and_read(result, query="test query", history=None):
    """Run log_query against a throwaway log dir and return the written entry."""
    with tempfile.TemporaryDirectory() as tmp:
        original = oc._LOG_DIR
        oc._LOG_DIR = pathlib.Path(tmp)
        try:
            oc.log_query(query, result, history)
            written = sorted(pathlib.Path(tmp).glob("*.jsonl"))
            assert len(written) == 1, f"expected one log file, got {written}"
            lines = written[0].read_text().strip().splitlines()
            assert len(lines) == 1
            return json.loads(lines[0])
        finally:
            oc._LOG_DIR = original


BASE_RESULT = {
    "response": "**DO THIS**\n1. Reassess.\n",
    "sources": [],
    "source_mode": "GENERAL_MEDICAL",
    "validator_result": "SAFE",
    "validator_issues": [],
    "patient_context": {"age_years": None, "confirmed_weight_kg": None,
                        "is_pediatric": False, "access_state": "UNKNOWN",
                        "route_preference": "UNKNOWN"},
}


# ── T-13: which override released a response must be recoverable ────────────

def test_override_fired_is_logged():
    """The one question the v4.0 log could not answer about S-1.

    The issue list was discarded and the branch only printed, so two overrides
    were equally plausible explanations for cdss_session_2026-07-18.jsonl:8 and
    nothing distinguished them.
    """
    result = dict(BASE_RESULT, validator_result="NEEDS_HUMAN_REVIEW",
                  validator_issues=["Dose without confirmed weight for pediatric patient."],
                  override_fired="pediatric_weight_confirmed")
    entry = log_and_read(result)
    assert entry["override_fired"] == "pediatric_weight_confirmed"
    assert entry["validator_issues"], "issues must survive alongside the branch name"


def test_override_fired_null_when_none_fires():
    """Present-and-null, not absent. Absent is indistinguishable from an old log."""
    entry = log_and_read(dict(BASE_RESULT))
    assert "override_fired" in entry
    assert entry["override_fired"] is None


def test_logged_override_name_is_in_registry():
    """A renamed branch must not silently orphan historical log analysis."""
    for override in SAFETY_OVERRIDES:
        entry = log_and_read(dict(BASE_RESULT, override_fired=override.name))
        assert entry["override_fired"] in {o.name for o in SAFETY_OVERRIDES}


def test_log_entry_keeps_its_existing_shape():
    """Pin the v4.0 fields so a schema change is deliberate."""
    entry = log_and_read(dict(BASE_RESULT), history=[{"query": "a", "response": "b"}])
    for key in ("ts", "debug_warn_only", "query", "response_preview", "source_mode",
                "validator_result", "validator_issues", "history_turns", "patient_ctx"):
        assert key in entry, key
    assert entry["history_turns"] == 1
    assert len(entry["response_preview"]) <= 200


def test_call_site_does_not_re_derive_the_verdict():
    """Source-level guard on the one line that caused S-2.

    The pipeline call site cannot be exercised offline (it needs ChromaDB and
    two LLM calls), so this pins it by inspection instead: validator_result must
    come from the gate's verdict, never be recomputed from `blocked`.
    """
    import inspect
    # Comments are stripped first: the call site's own comment quotes the removed
    # expression to explain why it went, and that must not satisfy the grep.
    source = "\n".join(
        line for line in inspect.getsource(oc._query_with_rag_internal).splitlines()
        if not line.strip().startswith("#")
    )
    assert '"UNSAFE" if blocked' not in source
    assert '"validator_result": outcome.verdict' in source
    assert '"validator_issues": outcome.issues' in source
    assert '"override_fired": outcome.override_fired' in source


def test_no_served_response_is_logged_unsafe_end_to_end():
    """The S-2 class, asserted at the log surface rather than the gate surface."""
    from openai_client import DeterministicCheck, PatientContext, apply_safety_gate
    outcome = apply_safety_gate(
        "**DO THIS**\n1. Give 500 mL crystalloid.\n",
        DeterministicCheck(passed=True),
        {"result": "UNSAFE", "issues": ["Response recommends resuscitation without an endpoint."],
         "rationale": ""},
        PatientContext(), "",
    )
    entry = log_and_read(dict(BASE_RESULT,
                              response=outcome.response,
                              validator_result=outcome.verdict,
                              validator_issues=outcome.issues,
                              override_fired=outcome.override_fired))
    assert entry["validator_result"] != "UNSAFE"
    assert entry["override_fired"] == "fluids_resuscitation"
    assert entry["validator_issues"] != []
