"""
EdgeCDSS — emergency security patch, endpoint behaviour.

Covers the actively-exploitable findings in SECURITY_AUDIT.md:

  AE-1  /feedback took an anonymous, uncapped, append-only write to the root
        filesystem from the public internet. It also stored records as Python
        dict reprs, which no parser reads back — see the note on json.dumps
        below.
  AE-3  /feedback/summary handed the submitter's IP and their free-text
        clinical query back to anyone holding a token that is public by design.
  AE-4  /query awaited a synchronous pipeline inline, so one slow request owned
        the event loop that also answers /health — which edgecdss-watchdog.sh
        reads, restarting the service at three misses and REBOOTING the host at
        six.

_redact (H-1) is covered separately in test_redaction.py, which needs no
third-party import and therefore always runs.

Requires fastapi and httpx. Skipped, not failed, where they are absent — the
offline gate runs on a stdlib-only interpreter by design (the app modules
import their SDKs lazily), and a python environment without fastapi still has a
suite to run. Same rule as test_client_render.py and node. To run these:

    PYTHONPATH=../.venv/lib/python3.12/site-packages python3 -m pytest test_security_patch.py

    cd server && ./run_unit_tests.sh      # skips this module, runs the rest
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import types

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed; endpoint tests cannot run")
httpx = pytest.importorskip("httpx", reason="httpx is not installed; endpoint tests cannot run")

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
# Set before main is imported. load_dotenv() does not override an existing
# variable, so this holds even when the suite is run from a tree with a real
# .env beside it — these tests must never authenticate with the deployed token,
# and must never pass merely because the demo token is the default.
os.environ["CDSS_ACCESS_TOKEN"] = "test-token-not-the-demo-one"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# main.py builds a ChromaDB PersistentClient at import. Stubbed so this stays
# offline and touches no corpus; main is the only module importing embeddings.
_stub = types.ModuleType("embeddings")


class _StubChroma:
    def get_collection_count(self):
        return 0

    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


_stub.ChromaDBClient = _StubChroma
sys.modules["embeddings"] = _stub

import main  # noqa: E402

TOKEN = {"X-Access-Token": os.environ["CDSS_ACCESS_TOKEN"]}
# The token published with the demo. It must open nothing these tests hold.
DEMO = {"X-Access-Token": "edgecdss-demo-2026"}

FEEDBACK_BODY = {"query": "test q", "response": "test r",
                 "feedback_type": "appropriate"}
QUERY_BODY = {"query": "test", "device_id": "test",
              "timestamp": "2026-08-22T00:00:00"}

OK_RESULT = {"response": "ok", "sources": [], "validator_result": "SAFE",
             "validator_issues": [], "model": "", "source": "",
             "patient_context": {}, "vitals_cautions": []}


def call(method, path, **kw):
    """One request against the app in-process. No socket, no server.

    httpx's ASGITransport is async-only, so the sync ergonomics the tests want
    are borrowed from a throwaway loop rather than from a live port.
    """
    async def go():
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://testserver") as c:
            return await c.request(method, path, **kw)
    return asyncio.run(go())


@pytest.fixture
def feedback_log(monkeypatch):
    """A throwaway FEEDBACK_LOG. Never the deployed one."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "feedback.log")
        monkeypatch.setattr(main, "FEEDBACK_LOG", path)
        yield path


def lines_of(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l for l in f.read().splitlines() if l.strip()]


# ═════════════════════════════════════════════════════════════════════════
# The gate runs BEFORE the body is validated
# ═════════════════════════════════════════════════════════════════════════
#
# The bug a naive fix leaves behind. Checked inside the handler, the token test
# happens AFTER pydantic has parsed and validated the body — so an anonymous
# caller sending a malformed body got 422, not 401. That hands out the schema
# and makes the server do the validation work for someone who never
# authenticated. As a dependency, FastAPI solves it before body validation.
#
# Nothing in require_token's signature reveals this ordering, which is exactly
# why it is pinned here.

MALFORMED = [
    ("/feedback", "missing required fields", {}),
    ("/feedback", "oversized query",
     {"query": "x" * (main.MAX_QUERY_CHARS + 1), "response": "r",
      "feedback_type": "appropriate"}),
    ("/feedback", "wrong types",
     {"query": 123, "response": [], "feedback_type": {}}),
    ("/feedback", "too many issues",
     {"query": "q", "response": "r", "feedback_type": "appropriate",
      "issues": ["t"] * (main.MAX_FEEDBACK_ISSUES + 1)}),
    ("/query", "missing required fields", {}),
    ("/query", "oversized query",
     {"query": "x" * (main.MAX_QUERY_CHARS + 1), "device_id": "d",
      "timestamp": "t"}),
    ("/query", "history over the byte budget",
     {"query": "q", "device_id": "d", "timestamp": "t",
      "conversation_history": [{"q": "x" * 40_000} for _ in range(10)]}),
]


@pytest.mark.parametrize("path,label,body",
                         [(p, l, b) for p, l, b in MALFORMED],
                         ids=[f"{p}-{l}" for p, l, _ in MALFORMED])
def test_auth_runs_before_body_validation(feedback_log, path, label, body):
    """An unauthenticated caller gets 401 whatever they sent — never 422."""
    for headers in ({}, DEMO):
        r = call("POST", path, json=body, headers=headers)
        assert r.status_code == 401, (
            f"{path} with {label} returned {r.status_code} to an "
            "unauthenticated caller — the body was validated before the gate")


@pytest.mark.parametrize("path,label,body",
                         [(p, l, b) for p, l, b in MALFORMED],
                         ids=[f"{p}-{l}" for p, l, _ in MALFORMED])
def test_the_same_bodies_are_still_rejected_once_authenticated(
        feedback_log, path, label, body):
    """The gate must not be swallowing the validation, only preceding it."""
    r = call("POST", path, json=body, headers=TOKEN)
    assert r.status_code == 422, (
        f"{path} with {label} returned {r.status_code} to an authenticated "
        "caller — the caps are not being enforced")


def test_a_well_formed_unauthenticated_post_is_still_401(feedback_log):
    """The case that already worked, kept so a refactor cannot regress it."""
    assert call("POST", "/feedback", json=FEEDBACK_BODY).status_code == 401


def test_every_gated_route_uses_the_shared_dependency():
    """One gate, not four copies of an if-statement that can drift apart.

    /status, /models, /health and / are deliberately absent: /status is public
    by design and this patch must not have changed that.
    """
    gated = {"/query", "/feedback", "/feedback/summary", "/speak"}
    for route in main.app.routes:
        path = getattr(route, "path", None)
        if path not in gated:
            continue
        # route.dependencies holds Depends markers (.dependency); the solved
        # Dependant tree holds the callables (.call). Check both, so this keeps
        # working whether the gate is declared on the decorator or in the
        # signature.
        declared = [d.dependency for d in getattr(route, "dependencies", [])]
        solved = [d.call for d in getattr(getattr(route, "dependant", None),
                                          "dependencies", [])]
        assert main.require_token in declared + solved, (
            f"{path} is not behind require_token")


# ═════════════════════════════════════════════════════════════════════════
# AE-1 — /feedback was the only unauthenticated write on the box
# ═════════════════════════════════════════════════════════════════════════

def test_unauthenticated_feedback_is_refused(feedback_log):
    r = call("POST", "/feedback", json=FEEDBACK_BODY)
    assert r.status_code == 401
    assert lines_of(feedback_log) == [], "a refused request still wrote to the log"


def test_feedback_with_the_wrong_token_is_refused(feedback_log):
    r = call("POST", "/feedback", json=FEEDBACK_BODY, headers=DEMO)
    assert r.status_code == 401
    assert lines_of(feedback_log) == []


def test_feedback_with_the_token_still_works(feedback_log):
    r = call("POST", "/feedback", json=FEEDBACK_BODY, headers=TOKEN)
    assert r.status_code == 200
    assert len(lines_of(feedback_log)) == 1


@pytest.mark.parametrize("field,value", [
    ("query", "x" * (main.MAX_QUERY_CHARS + 1)),
    ("response", "x" * (main.MAX_RESPONSE_CHARS + 1)),
    ("suggestion", "x" * (main.MAX_FEEDBACK_TEXT + 1)),
    ("comment", "x" * (main.MAX_FEEDBACK_TEXT + 1)),
    ("feedback_type", "x" * 33),
    ("severity", "x" * 33),
    ("device_id", "x" * 201),
])
def test_an_oversized_feedback_field_is_refused(feedback_log, field, value):
    r = call("POST", "/feedback", json={**FEEDBACK_BODY, field: value},
             headers=TOKEN)
    assert r.status_code == 422, f"{field} was accepted at {len(value)} chars"
    assert lines_of(feedback_log) == []


def test_too_many_issue_tags_are_refused(feedback_log):
    body = {**FEEDBACK_BODY, "issues": ["tag"] * (main.MAX_FEEDBACK_ISSUES + 1)}
    assert call("POST", "/feedback", json=body, headers=TOKEN).status_code == 422
    assert lines_of(feedback_log) == []


def test_an_oversized_single_issue_tag_is_refused(feedback_log):
    body = {**FEEDBACK_BODY, "issues": ["x" * (main.MAX_ISSUE_CHARS + 1)]}
    assert call("POST", "/feedback", json=body, headers=TOKEN).status_code == 422


def test_issues_cannot_carry_arbitrary_nested_json(feedback_log):
    """It was an untyped list — a place to put anything at all, uncounted."""
    body = {**FEEDBACK_BODY, "issues": [{"nested": ["structure"] * 100}]}
    assert call("POST", "/feedback", json=body, headers=TOKEN).status_code == 422


def test_the_documented_issue_tags_are_still_accepted(feedback_log):
    """The caps refuse abuse, not the client's own fixed tag list."""
    body = {**FEEDBACK_BODY,
            "issues": ["wrong dose", "missing contraindication", "unclear"]}
    assert call("POST", "/feedback", json=body, headers=TOKEN).status_code == 200
    assert json.loads(lines_of(feedback_log)[0])["issues"] == body["issues"]


def test_a_newline_in_a_field_stays_inside_the_field(feedback_log):
    """One request, one record, whatever the caller puts in their text.

    NOTE, against the audit: str(entry) was NOT forgeable. str() on a dict
    calls repr() on the values, and repr escapes a newline to a literal \\n —
    so a crafted query never did break the line-per-record invariant. The
    audit called this exploitable and it was wrong; the check is kept as a
    regression guard, not as evidence of a closed hole.

    What json.dumps actually buys is PARSEABILITY, and that is load-bearing
    for AE-3: /feedback/summary can only strip the IP from a record it can
    parse, and a dict repr is not JSON. See the legacy-line test below.
    """
    forged = json.dumps({"timestamp": "2026-01-01T00:00:00", "ip": "127.0.0.1",
                         "feedback_type": "appropriate",
                         "query": "FORGED RECORD"})
    r = call("POST", "/feedback",
             json={**FEEDBACK_BODY, "query": "real\n" + forged}, headers=TOKEN)
    assert r.status_code == 200

    written = lines_of(feedback_log)
    assert len(written) == 1, f"one request wrote {len(written)} records"
    # The newline survives inside the field — escaped, not structural.
    assert json.loads(written[0])["query"] == "real\n" + forged


def test_control_characters_do_not_break_the_jsonl_contract(feedback_log):
    r = call("POST", "/feedback",
             json={**FEEDBACK_BODY, "comment": "a\r\nb\tc\x00d"}, headers=TOKEN)
    assert r.status_code == 200
    written = lines_of(feedback_log)
    assert len(written) == 1
    assert json.loads(written[0])["comment"] == "a\r\nb\tc\x00d"


def test_every_stored_record_is_parseable_jsonl(feedback_log):
    for i in range(5):
        call("POST", "/feedback", json={**FEEDBACK_BODY, "query": f"q{i}\nx"},
             headers=TOKEN)
    written = lines_of(feedback_log)
    assert len(written) == 5
    for line in written:
        assert isinstance(json.loads(line), dict)


# ═════════════════════════════════════════════════════════════════════════
# AE-3 — what a token holder may read back
# ═════════════════════════════════════════════════════════════════════════

def test_feedback_summary_requires_the_token(feedback_log):
    assert call("GET", "/feedback/summary").status_code == 401
    assert call("GET", "/feedback/summary", headers=DEMO).status_code == 401


def test_feedback_summary_is_gated_before_it_touches_the_log(monkeypatch):
    """An anonymous caller must not even cause the file to be opened."""
    def explode(*a, **k):
        raise AssertionError("the log was read before the token was checked")
    monkeypatch.setattr(main, "summarise_feedback_line", explode)
    monkeypatch.setattr(main, "FEEDBACK_LOG", "/nonexistent/must-not-be-read")
    assert call("GET", "/feedback/summary").status_code == 401


def test_feedback_summary_never_returns_the_client_ip(feedback_log):
    call("POST", "/feedback", json=FEEDBACK_BODY, headers=TOKEN)
    body = call("GET", "/feedback/summary", headers=TOKEN).json()

    assert body["total_feedback"] == 1
    assert len(body["entries"]) == 1
    assert "ip" not in body["entries"][0], "the submitter's IP reached a caller"
    assert "127.0.0.1" not in json.dumps(body)
    # And it is still recorded on disk: the endpoint filters, the log keeps.
    assert "ip" in json.loads(lines_of(feedback_log)[0])


def test_feedback_summary_returns_projected_records_not_raw_lines(feedback_log):
    call("POST", "/feedback", json=FEEDBACK_BODY, headers=TOKEN)
    entries = call("GET", "/feedback/summary", headers=TOKEN).json()["entries"]
    assert isinstance(entries[0], dict), "raw log lines were passed through"
    assert set(entries[0]) == (set(main._SUMMARY_PASSTHROUGH)
                               | set(main._SUMMARY_TRUNCATED))


def test_feedback_summary_truncates_free_text(feedback_log):
    long_q = "P" * (main.SUMMARY_TEXT_CHARS + 500)
    call("POST", "/feedback", json={**FEEDBACK_BODY, "query": long_q},
         headers=TOKEN)
    entry = call("GET", "/feedback/summary", headers=TOKEN).json()["entries"][0]
    assert len(entry["query"]) == main.SUMMARY_TEXT_CHARS


def test_feedback_summary_is_capped_at_its_entry_limit(feedback_log):
    extra = 5
    for i in range(main.SUMMARY_MAX_ENTRIES + extra):
        call("POST", "/feedback", json={**FEEDBACK_BODY, "query": f"q{i}"},
             headers=TOKEN)
    body = call("GET", "/feedback/summary", headers=TOKEN).json()
    assert body["total_feedback"] == main.SUMMARY_MAX_ENTRIES + extra
    assert len(body["entries"]) == main.SUMMARY_MAX_ENTRIES


def test_legacy_dict_repr_lines_are_dropped_not_leaked(feedback_log):
    """Records written before this patch are dict reprs.

    They cannot be parsed, so they cannot be field-filtered either — and a line
    that cannot be filtered must not be passed through with its IP intact.
    """
    with open(feedback_log, "w", encoding="utf-8") as f:
        f.write(str({"timestamp": "old", "ip": "10.0.0.9",
                     "query": "legacy clinical text"}) + "\n")
    body = call("GET", "/feedback/summary", headers=TOKEN).json()
    assert body["total_feedback"] == 1, "the count still reflects the file"
    assert body["entries"] == []
    assert "10.0.0.9" not in json.dumps(body)
    assert "legacy clinical text" not in json.dumps(body)


def test_missing_feedback_log_is_not_an_error(feedback_log):
    assert call("GET", "/feedback/summary", headers=TOKEN).json() == {
        "total_feedback": 0, "entries": []}


# ═════════════════════════════════════════════════════════════════════════
# AE-4 — /query must not own the event loop
# ═════════════════════════════════════════════════════════════════════════

def test_a_slow_query_does_not_stall_health(monkeypatch):
    """The reboot vector, directly.

    /health is answered by the same event loop /query runs on. The assertion is
    ORDER, not elapsed time: a blocked loop cannot even begin /health until the
    query has finished, so the discriminator is whether /health completes first
    — measured against the unpatched code it completed at 1.76s to the query's
    1.51s, and after the offload at 0.26s to the same 1.51s.

    Timing /health alone does not work: with the loop blocked, the timer itself
    cannot start until the query is already done, and the stall reads as 0.00s.
    """
    SLOW = 1.5

    def slow_pipeline(*a, **k):
        time.sleep(SLOW)
        return dict(OK_RESULT)

    monkeypatch.setattr(main, "query_with_rag", slow_pipeline)

    async def scenario():
        done = []
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://testserver") as c:
            start = time.monotonic()

            async def slow_query():
                r = await c.post("/query", json=QUERY_BODY, headers=TOKEN)
                done.append(("query", time.monotonic() - start))
                return r

            async def health_probe():
                await asyncio.sleep(0.25)     # let the pipeline get underway
                r = await c.get("/health")
                done.append(("health", time.monotonic() - start))
                return r

            query_resp, health = await asyncio.gather(slow_query(), health_probe())
            return query_resp, health, done

    query_resp, health, done = asyncio.run(scenario())
    finished = [name for name, _ in done]
    at = dict(done)

    assert query_resp.status_code == 200, "the slow query itself must still work"
    assert health.status_code == 200
    assert finished[0] == "health", (
        f"/health finished at {at['health']:.2f}s, after the {SLOW}s query at "
        f"{at['query']:.2f}s — the pipeline is back on the event loop, and "
        "three of these in a row is a watchdog restart")
    assert at["health"] < SLOW / 2


def test_concurrent_queries_are_not_serialised(monkeypatch):
    """Two callers should not queue behind one another for the whole pipeline."""
    SLOW = 1.0
    monkeypatch.setattr(main, "query_with_rag",
                        lambda *a, **k: (time.sleep(SLOW), dict(OK_RESULT))[1])

    async def scenario():
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://testserver") as c:
            t0 = time.monotonic()
            rs = await asyncio.gather(*[
                c.post("/query", json=QUERY_BODY, headers=TOKEN)
                for _ in range(3)])
            return rs, time.monotonic() - t0

    responses, elapsed = asyncio.run(scenario())
    assert all(r.status_code == 200 for r in responses)
    assert elapsed < SLOW * 2, (
        f"three {SLOW}s queries took {elapsed:.2f}s — they ran serially")


@pytest.mark.parametrize("field,value", [
    ("query", "x" * (main.MAX_QUERY_CHARS + 1)),
    ("device_id", "x" * 201),
    ("timestamp", "x" * 65),
    ("voice_mode", "x" * 33),
    ("model", "x" * 129),
])
def test_an_oversized_query_field_is_refused(field, value):
    r = call("POST", "/query", json={**QUERY_BODY, field: value}, headers=TOKEN)
    assert r.status_code == 422, f"{field} was accepted at {len(value)} chars"


def test_too_many_history_turns_are_refused():
    turns = [{"query": "q", "response": "r"}] * (main.MAX_HISTORY_TURNS + 1)
    r = call("POST", "/query",
             json={**QUERY_BODY, "conversation_history": turns}, headers=TOKEN)
    assert r.status_code == 422


def test_history_inside_the_turn_cap_but_over_the_byte_budget_is_refused():
    """Turn count alone was never the bound.

    Ten turns is unremarkable; ten turns each carrying 40 KB is the same
    amplification with a shorter list, and the context rebuild walks every
    character of it through the vitals and context regexes.
    """
    fat = [{"query": "x" * 40_000, "response": "y"} for _ in range(10)]
    assert len(fat) <= main.MAX_HISTORY_TURNS
    r = call("POST", "/query",
             json={**QUERY_BODY, "conversation_history": fat}, headers=TOKEN)
    assert r.status_code == 422


def test_an_ordinary_session_is_still_accepted(monkeypatch):
    """The caps refuse abuse, not clinical work.

    A long real handover sits well inside them. This is the guard against
    tightening a security limit into a functional outage.
    """
    monkeypatch.setattr(main, "query_with_rag", lambda *a, **k: dict(OK_RESULT))
    turns = [{"query": f"turn {i} about the patient", "response": "answer"}
             for i in range(30)]
    r = call("POST", "/query",
             json={**QUERY_BODY, "conversation_history": turns}, headers=TOKEN)
    assert r.status_code == 200


def test_query_still_requires_the_token():
    assert call("POST", "/query", json=QUERY_BODY).status_code == 401
    assert call("POST", "/query", json=QUERY_BODY, headers=DEMO).status_code == 401


def test_speak_still_requires_the_token():
    """Unchanged by this patch, pinned so the pattern stays uniform."""
    assert call("POST", "/speak", json={"text": "hi"}).status_code == 401


def test_status_stays_unauthenticated():
    """Deliberately public. This patch must not have changed that by accident."""
    assert call("GET", "/status").status_code == 200
