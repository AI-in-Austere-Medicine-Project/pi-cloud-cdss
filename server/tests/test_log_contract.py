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
import time

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    # Mirrors PatientContext.to_dict(), which is what the real pipeline hands
    # log_query. The logger whitelists keys out of this dict, so a field the
    # fixture omits is a field the contract test cannot see.
    "patient_context": {"age_years": None, "confirmed_weight_kg": None,
                        "is_pediatric": False, "access_state": "UNKNOWN",
                        "route_preference": "UNKNOWN", "ams_stated": False},
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
        line for line in inspect.getsource(oc._run_pipeline).splitlines()
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


# ── T-1 / T-2: pipeline timing and synthetic-traffic tagging ────────────────
# Both ride the same log entry, so they share one stub harness. The real
# pipeline needs ChromaDB and two LLM calls; _query_with_rag_internal is
# replaced with a recording stub so query_with_rag's own contract — what it
# times, what it forwards, what it logs — is what gets asserted.

class _RecordingInternal:
    """Stands in for _query_with_rag_internal; records how it was called."""

    def __init__(self, sleep_s=0.0, result=None):
        self.sleep_s = sleep_s
        self.result = result if result is not None else dict(BASE_RESULT)
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return dict(self.result)


def run_and_read(stub, query="test query", history=None, **kwargs):
    """Call query_with_rag against a stubbed pipeline; return the log entry."""
    with tempfile.TemporaryDirectory() as tmp:
        original_dir, original_internal = oc._LOG_DIR, oc._query_with_rag_internal
        oc._LOG_DIR = pathlib.Path(tmp)
        oc._query_with_rag_internal = stub
        try:
            result = oc.query_with_rag(query, None, conversation_history=history, **kwargs)
            written = sorted(pathlib.Path(tmp).glob("*.jsonl"))
            assert len(written) == 1, f"expected one log file, got {written}"
            lines = written[0].read_text().strip().splitlines()
            assert len(lines) == 1
            return json.loads(lines[0]), result
        finally:
            oc._LOG_DIR, oc._query_with_rag_internal = original_dir, original_internal


def test_pipeline_ms_is_logged():
    entry, _ = run_and_read(_RecordingInternal())
    assert "pipeline_ms" in entry
    assert isinstance(entry["pipeline_ms"], int)
    assert entry["pipeline_ms"] >= 0


def test_pipeline_ms_reflects_elapsed_time():
    """Without this, a hard-coded 0 satisfies the existence test forever."""
    slow, fast = _RecordingInternal(sleep_s=0.15), _RecordingInternal(sleep_s=0.0)
    slow_entry, _ = run_and_read(slow)
    fast_entry, _ = run_and_read(fast)
    assert slow_entry["pipeline_ms"] >= 140, slow_entry["pipeline_ms"]
    assert slow_entry["pipeline_ms"] < 5000, "timing the wrong thing entirely"
    assert slow_entry["pipeline_ms"] > fast_entry["pipeline_ms"]


def test_pipeline_ms_is_not_the_http_round_trip():
    """T-1 names the field pipeline_ms, not processing_time_ms, on purpose.

    main.py measures a wider span (request parsing and response serialisation
    included) and reports it to the client. Two different numbers; if the log
    ever adopts the client's name, they will be compared as if they were one.
    """
    entry, _ = run_and_read(_RecordingInternal())
    assert "processing_time_ms" not in entry


def test_synthetic_flag_defaults_false():
    entry, _ = run_and_read(_RecordingInternal())
    assert entry["synthetic"] is False


def test_synthetic_flag_propagates():
    entry, _ = run_and_read(_RecordingInternal(), synthetic=True)
    assert entry["synthetic"] is True


def test_synthetic_does_not_alter_pipeline():
    """The flag must never grow teeth.

    It is self-declared via a request header and trivially spoofable, so any
    behaviour branching on it would be a safety control an attacker sets. The
    pipeline must receive byte-identical arguments either way.
    """
    on, off = _RecordingInternal(), _RecordingInternal()
    entry_on, result_on = run_and_read(on, synthetic=True)
    entry_off, result_off = run_and_read(off, synthetic=False)

    assert on.calls == off.calls, "synthetic must not reach the pipeline"
    assert all("synthetic" not in kwargs for _args, kwargs in on.calls)
    assert result_on == result_off
    for field in ("validator_result", "validator_issues", "response_preview",
                  "source_mode", "override_fired"):
        assert entry_on[field] == entry_off[field], field


def test_run_tests_sends_the_synthetic_header():
    """The half that actually keeps the production log clean.

    run_tests.sh fires 24 cases at the live public endpoint — 48 of the 135
    audit-corpus entries came from two such runs, indistinguishable from real
    traffic.
    """
    here = pathlib.Path(__file__).parent.parent
    script = (here / "run_tests.sh").read_text()
    assert "X-Test-Run: 1" in script
    assert script.count("X-Test-Run: 1") == script.count("X-Access-Token: $TOKEN"), \
        "every authenticated test request must carry the tag"


def test_log_schema_version_is_stamped():
    """Pre-v4.1 entries carry no log_schema key; the formats must be
    distinguishable without inferring one from which fields are present."""
    entry, _ = run_and_read(_RecordingInternal())
    assert entry["log_schema"] == oc.LOG_SCHEMA_VERSION == 9
    for field in ("pipeline_ms", "synthetic", "override_fired"):
        assert field in entry, f"schema 2 must carry {field}"
    for field in ("source", "model"):
        assert field in entry, f"schema 3 must carry {field}"
    for field in ("vitals", "vitals_superseded", "vitals_rejected", "vitals_cautions"):
        assert field in entry, f"schema 4 must carry {field}"
    # Schema 7: a boolean patient fact rather than a measurement, so it lives
    # in patient_ctx and not in vitals. A reader that treats its absence as
    # False would mis-read every entry written before it existed, which is the
    # same rule every field in this block is here to state.
    assert "ams_stated" in entry["patient_ctx"], "schema 7 must carry ams_stated"
    # The fixture above is hand-written, so pin that the REAL context supplies
    # the key too — otherwise this passes on a dict that production never sends.
    assert "ams_stated" in oc.PatientContext().to_dict()
    # Schema 8: present-and-null, not absent — the override_fired rule. Absent
    # is indistinguishable from a log written before suppression existed.
    assert "review_suppressed" in entry
    assert entry["review_suppressed"] is None
    # Schema 9: the card tier. Present-and-null on a non-card answer, so a
    # reader can tell "not a card" from "written before cards existed".
    for field in ("card_id", "card_version"):
        assert field in entry, f"schema 9 must carry {field}"
        assert entry[field] is None


def test_schema_5_logs_a_temperature_in_the_unit_it_was_stated_in():
    """The rename is the reason for the version bump.

    A schema 4 reading was named `temp_c` and its value was always Celsius.
    Reading a schema 5 `temp` the same way would be wrong, so analysis tooling
    has to be able to tell the two apart without inspecting the value.
    """
    readings, _ = oc.vitals_mod.parse_vitals("fever of 104",
                                             ts="2026-08-21T10:00:00+00:00")
    logged = oc.vitals_mod.to_dict(readings)
    assert "temp_c" not in logged
    assert logged["temp"]["value"] == 104.0
    assert logged["temp"]["unit"] == "F"
    assert logged["temp"]["value_c"] == 40.0
    assert logged["temp"]["value_f"] == 104.0


def test_schema_6_flags_every_reading_as_derived_or_stated():
    """The reason for this bump: one vital in the block is now computed.

    A schema 5 reading was always something the medic said. Reading a schema 6
    `map` that way is a coin flip, so the flag is on every reading rather than
    only the derived one — otherwise a stated MAP and a pre-schema-6 log look
    identical.
    """
    readings, _ = oc.vitals_mod.parse_vitals("BP 90/30 HR 128",
                                             ts="2026-08-21T10:00:00+00:00")
    merged, _ = oc.vitals_mod.merge({}, readings)
    logged = oc.vitals_mod.to_dict(merged)
    assert logged["map"]["value"] == 50.0
    assert logged["map"]["derived"] is True
    for name in ("hr", "sbp", "dbp"):
        assert logged[name]["derived"] is False, f"{name} was stated, not computed"


def test_schema_6_records_a_stated_map_as_stated():
    stated, _ = oc.vitals_mod.parse_vitals("MAP 70", ts="2026-08-21T10:00:00+00:00")
    merged, _ = oc.vitals_mod.merge({}, stated)
    assert oc.vitals_mod.to_dict(merged)["map"]["derived"] is False


def test_finalise_can_never_produce_an_unsafe_verdict():
    """_finalise mutates validator_result after the gate. It may only soften it.

    S-2 was a verdict re-derived at the call site. _finalise re-derives one
    again — deliberately, so that a deterministic card recommending lorazepam to
    a patient with RR 6 is flagged — so the direction it can move must be
    pinned. SAFE may become NEEDS_HUMAN_REVIEW; nothing may become UNSAFE, and
    a response already served must not become one that is blocked.
    """
    ctx = oc.PatientContext()
    # 93F is 33.9C: hypothermic, and inside the plausible Fahrenheit band. A
    # Celsius "temp 33" is now rejected rather than stored, so it would arm
    # nothing and this fixture would stop testing what it says it tests.
    found, _ = oc.vitals_mod.parse_vitals("RR 6 BP 82/40 HR 42 GCS 5 temp 93 F",
                                          ts="2026-08-21T10:00:00+00:00")
    # Folded, not just parsed: merge() is where MAP is derived, and the rule it
    # arms has to sit inside this invariant like every other caution.
    ctx.vitals, _ = oc.vitals_mod.merge({}, found)
    assert ctx.vitals["temp"].canonical < 35
    assert ctx.vitals["map"].value == 54
    responses = ["Give lorazepam 4mg IV.", "Give fentanyl 50mcg IV.",
                 "Encourage oral fluids.", "Give TXA 1g IV.",
                 "Need weight in kg before dosing.", "Reassess the patient."]
    verdicts = ["SAFE", "SKIPPED_SAFE_GATE", "NEEDS_HUMAN_REVIEW", "UNSAFE"]
    modes = ["DETERMINISTIC_PRE_GATE", "PRE_GATE", "FIXED_PREP",
             "NON_MEDICAL_PRE_GATE", "DOSE_PROVENANCE", "ERROR", "JTS_GROUNDED"]

    for response in responses:
        for verdict in verdicts:
            for mode in modes:
                out = oc._finalise({"response": response, "source_mode": mode,
                                    "validator_result": verdict,
                                    "validator_issues": []}, ctx)
                assert out["validator_result"] != "UNSAFE" or verdict == "UNSAFE", (
                    f"_finalise invented an UNSAFE verdict: {mode} {verdict} {response!r}")
                if verdict == "UNSAFE":
                    assert out["validator_result"] == "UNSAFE", "a block must stay blocked"
                    assert "VITALS CAUTION" not in out["response"]


def test_a_map_caution_can_only_soften_a_verdict():
    """MAP < 65 arms the existing hypotension pathway, so it inherits the
    existing invariant: it appends a line and downgrades SAFE. It cannot block a
    response, and it cannot release one that was blocked.

    Pinned on a pressure whose SYSTOLIC is not low — 90/30 — so the MAP rule is
    the only thing arming and the assertion cannot pass on the systolic rule's
    behalf. Run through _finalise, the gate-bypassing path, because that is the
    one where a new rule could quietly reach a fixed reviewed string; the gated
    path is covered end to end in test_vitals.py.
    """
    ctx = oc.PatientContext()
    found, _ = oc.vitals_mod.parse_vitals("BP 90/30", ts="2026-08-21T10:00:00+00:00")
    ctx.vitals, _ = oc.vitals_mod.merge({}, found)
    assert ctx.vitals["map"].value == 50

    served = oc._finalise({"response": "Give fentanyl 50mcg IV.",
                           "source_mode": "FIXED_PREP",
                           "validator_result": "SAFE",
                           "validator_issues": []}, ctx)
    assert "MAP is 50" in served["response"], "the caution must be visible"
    assert served["validator_result"] == "NEEDS_HUMAN_REVIEW"

    blocked = oc._finalise({"response": "Give fentanyl 50mcg IV.",
                            "source_mode": "FIXED_PREP",
                            "validator_result": "UNSAFE",
                            "validator_issues": []}, ctx)
    assert blocked["validator_result"] == "UNSAFE", "a caution cannot release a block"
    assert "VITALS CAUTION" not in blocked["response"]


def test_finalise_leaves_gate_questions_alone():
    """SAFE_GATE_RESPONSES is matched exactly; a question is not a plan."""
    ctx = oc.PatientContext()
    ctx.vitals, _ = oc.vitals_mod.parse_vitals("RR 6", ts="2026-08-21T10:00:00+00:00")
    out = oc._finalise({"response": "Need weight in kg before dosing.",
                        "source_mode": "PRE_GATE",
                        "validator_result": "SKIPPED_SAFE_GATE",
                        "validator_issues": []}, ctx)
    assert out["response"] == "Need weight in kg before dosing."
    assert out["validator_result"] == "SKIPPED_SAFE_GATE"
