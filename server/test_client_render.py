"""
EdgeCDSS — web client render regression.

test_client_contract.py greps the client for strings. That catches drift; it
cannot catch a render that throws, and on 2026-08-21 a render that threw took a
delivered clinical answer off the screen:

    patient_context.confirmed_weight_kg arrives as a JSON number (75.0). The
    context strip passed it to esc(), which called .replace on it. The
    TypeError unwound out of renderCtx(), out of ask()'s try, and into the
    catch that writes REQUEST FAILED — over a SEPSIS card that had already
    been written to the DOM. Every grep assertion still passed.

So these run the client instead of reading it: client_render_harness.js loads
the real <script> out of static/index.html into a stubbed DOM and drives ask()
against canned /query payloads, including the one the server actually served
for that query (server/logs/sessions/cdss_session_2026-08-21.jsonl).

The rule being pinned: a missing or unreadable field costs its own element and
nothing else. It never costs the answer. A request that genuinely failed still
says so.

Requires node. Skipped, not failed, where node is absent — this is a check on
the JS, and a python environment without node still has a suite to run.

    cd server && ./run_unit_tests.sh
"""

import json
import pathlib
import shutil
import subprocess

import pytest

HERE = pathlib.Path(__file__).parent
HARNESS = HERE / "client_render_harness.js"
CLIENT = HERE / "static" / "index.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node is not installed; client render harness cannot run")


@pytest.fixture(scope="module")
def rendered():
    """Every scenario the harness drives, as {name: {bubble, ctx}}.

    A scenario that throws reports {"error": ...} rather than taking the rest
    of the report down with it, so one broken path fails one assertion.
    """
    proc = subprocess.run(["node", str(HARNESS), str(CLIENT)],
                          capture_output=True, text=True, timeout=120)
    assert proc.stdout, f"harness produced no output\n{proc.stderr}"
    out = json.loads(proc.stdout)
    assert "harness_error" not in out, out.get("harness_error")
    return out


def _ok(scenario):
    assert "error" not in scenario, f"render threw: {scenario['error']}"
    return scenario


# ── the escape helper ────────────────────────────────────────────────────────

def test_esc_coerces_instead_of_throwing(rendered):
    """The hardening. Values come out of a JSON body; they are not all strings."""
    esc = _ok(rendered["esc"])
    assert esc["num"] == "75", "a JSON number must escape, not throw"
    assert esc["float"] == "101.2"
    assert esc["undef"] == ""
    assert esc["nul"] == ""


def test_esc_still_escapes(rendered):
    """Coercing must not have cost the escaping — this is injected as innerHTML."""
    esc = _ok(rendered["esc"])
    assert esc["amp"] == "a &amp; b"
    assert esc["lt"] == "&lt;script&gt;"
    assert esc["str"] == "plain"


def test_num_does_not_invent_a_zero(rendered):
    """Number(null) is 0. An absent weight must not render as a weight of 0."""
    num = _ok(rendered["num"])
    assert num["float"] == "75", "75.0 reads as 75, not 75.0"
    assert num["decimal"] == "101.2"
    assert num["nul"] == ""
    assert num["undef"] == ""
    assert num["empty"] == ""
    assert num["text"] == ""
    assert num["zero"] == "0", "a real zero is a real reading"


# ── the regression itself ────────────────────────────────────────────────────

def test_the_served_sepsis_answer_renders(rendered):
    """The exact payload the server served for the query that broke the client."""
    real = _ok(rendered["real"])
    assert "REQUEST FAILED" not in real["bubble"]
    assert "SEPSIS" in real["bubble"]
    assert "VALIDATOR: SAFE" in real["bubble"]


def test_the_strip_renders_the_numeric_context_fields(rendered):
    """confirmed_weight_kg is a float on the wire and must reach the strip."""
    real = _ok(rendered["real"])
    assert "WT <b>75 kg</b>" in real["ctx"]
    assert "ACCESS <b>CONFIRMED IV IO</b>" in real["ctx"]


def test_the_strip_shows_a_pressure_as_one_measurement(rendered):
    """Systolic and diastolic are one reading; 90/30, never 90 and never 30."""
    real = _ok(rendered["real"])
    assert "BP <b>90/30 mmHg</b>" in real["ctx"]


# ── degradation ──────────────────────────────────────────────────────────────

def test_a_missing_field_costs_its_element_and_nothing_else(rendered):
    """Weight gone, access gone, one vital with no value, one vital renamed."""
    deg = _ok(rendered["degraded"])
    assert "REQUEST FAILED" not in deg["bubble"], "a missing field must not fail the request"
    assert "SEPSIS" in deg["bubble"]
    assert "undefined" not in deg["ctx"], "an unreadable reading is omitted, not printed"
    assert "NaN" not in deg["ctx"]
    assert "WT" not in deg["ctx"]
    assert "Temp <b>40 C</b>" in deg["ctx"], "the readable vitals still render"


def test_an_absent_patient_context_renders_an_empty_strip(rendered):
    """An older server, or a rollback, sends no patient_context at all."""
    noctx = _ok(rendered["no_context"])
    assert "REQUEST FAILED" not in noctx["bubble"]
    assert "SEPSIS" in noctx["bubble"]
    assert noctx["ctx"] == ""


def test_a_throwing_strip_cannot_unrender_the_answer(rendered):
    """The structural half of the fix.

    esc() coercing stops this particular throw. The guard around the strip is
    what stops the next one: once the answer is in the DOM, the decoration
    around it degrades to absent instead of unwinding into the failure path.
    """
    thrown = _ok(rendered["strip_throws"])
    assert "REQUEST FAILED" not in thrown["bubble"]
    assert "SEPSIS" in thrown["bubble"]


def test_a_real_failure_still_fails_loudly(rendered):
    """Hardening must not turn a genuine error into a blank screen."""
    err = _ok(rendered["http_error"])
    assert "REQUEST FAILED" in err["bubble"]
    assert "HTTP 500" in err["bubble"]
