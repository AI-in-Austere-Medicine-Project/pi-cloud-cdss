"""
EdgeCDSS — web client / server contract.

The client is a single static file with no build step and no test runner, so the
places where it duplicates a server-side string are exactly the places that
drift silently. These pin the ones that would fail quietly rather than loudly:
a banner the client no longer recognises is rendered as body text — the label
still there, but reading as part of the clinical answer instead of as a warning
about it.

    cd server && ./run_unit_tests.sh
"""

import os
import pathlib
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import general_reference as gr  # noqa: E402

CLIENT = pathlib.Path(__file__).parent.parent / "static" / "index.html"
HTML = CLIENT.read_text()


def test_client_exists_and_is_one_file():
    assert CLIENT.exists()


def test_client_recognises_the_banner_the_server_emits():
    """Both halves of the marker, verbatim.

    The client splits the banner off the answer to render it as a label. If the
    server's wording changes and the client's pattern does not, the banner is
    silently demoted to body text.
    """
    banner = gr.GENERAL_REFERENCE_BANNER
    assert "GENERAL MEDICAL REFERENCE" in banner
    assert "not from JTS protocols" in banner
    assert "GENERAL MEDICAL REFERENCE" in HTML
    assert "not from JTS protocols" in HTML


def test_client_sends_the_selected_model():
    assert "model: document.getElementById('model').value" in HTML
    assert 'id="model"' in HTML


def test_client_sends_the_source_flag_to_speak():
    """The spoken disclosure is applied server-side from this flag.

    If the client stops sending it, general answers are voiced with no
    indication they did not come from JTS — silently, because the audio still
    plays.
    """
    assert "JSON.stringify({ text, source })" in HTML


def test_client_renders_the_attribution_footer():
    assert "Answered by" in HTML
    assert "source: " in HTML


def test_deterministic_answers_are_not_attributed_to_a_model():
    """`model` is null for a card Python wrote; the footer must not invent one."""
    assert "EdgeCDSS (deterministic)" in HTML


def test_client_reads_provider_detail_when_the_menu_is_empty():
    """An empty dropdown must say why, not just be empty."""
    assert "provider_detail" in HTML


def test_no_key_material_in_the_client():
    """The client is served to every user. Provider keys live server-side only."""
    lowered = HTML.lower()
    for marker in ("sk-ant-", "sk-proj-", "anthropic_api_key", "openai_api_key"):
        assert marker not in lowered, f"{marker} appears in the web client"


def test_client_renders_the_patient_context_strip():
    """S-1 as UI: the medic must be able to see what the system believes.

    The v4.1 fix cleared stale context at a boundary. The strip is the other
    half — showing it the rest of the time, so a wrong value gets corrected
    before it is dosed against rather than after.
    """
    assert 'id="ctx"' in HTML
    assert "renderCtx" in HTML
    assert "patient_context" in HTML


def test_the_strip_clears_when_the_patient_does():
    """Leaving a cleared patient's vitals on screen is S-1 with extra steps."""
    marker = HTML.split("function newPatient()")[1].split("}")[0]
    assert "patientCtx = null" in marker
    assert "renderCtx()" in marker


def test_the_strip_marks_readings_whose_age_is_unknown():
    """A reading whose age cannot be established is the one worth looking at."""
    assert "age ?" in HTML
    assert "stale" in HTML


def test_the_strip_never_splits_a_blood_pressure():
    """Systolic and diastolic are one measurement and are shown as one.

    test_client_render.py asserts the rendered result ("BP <b>90/30 mmHg</b>");
    this pins the source expression so the two fail together rather than one
    quietly stopping to mean anything.
    """
    assert "num(r.value) + '/' + num(v.dbp.value)" in HTML


def test_the_strip_shows_the_map_with_the_pressure():
    """MAP belongs to the pressure it was derived from, and rides in its chip.

    test_client_render.py asserts the rendered result; this pins the source so
    the two fail together rather than one quietly stopping to mean anything.
    """
    assert "mapBadge" in HTML
    assert "'map'" in HTML, "the client no longer reads the vital by name"


def test_the_client_and_the_caution_table_agree_on_the_map_threshold():
    """65 in two places: the colour on the strip and the rule that arms the
    hypotension caution. If they drift, the strip shows green next to a caution
    that says the patient is hypotensive — the strip contradicting the answer
    beside it is worse than either alone."""
    import json

    assert "const MAP_LOW = 65;" in HTML
    rules = json.loads((pathlib.Path(__file__).parent.parent / "vitals_rules.json").read_text())
    armed = [r for r in rules["cautions"] if "map" in (r.get("when") or {})]
    assert armed, "no rule arms on MAP; the strip's threshold now pins nothing"
    assert all(r["when"]["map"] == {"lt": 65} for r in armed), \
        "the caution table and the client disagree about MAP 65"


def test_the_escape_helper_coerces():
    """The v4.3 client bug, pinned.

    esc() is fed straight out of a JSON body, where numbers are numbers:
    confirmed_weight_kg arrives as 75.0 and (75).replace is undefined. The
    TypeError did not stop at the chip it came from — it unwound into ask()'s
    catch and replaced a rendered SEPSIS card with REQUEST FAILED.
    """
    assert "String(s ?? '')" in HTML


def test_the_answer_survives_a_failure_in_the_furniture_around_it():
    """The strip, the listen button and the feedback controls are not the answer.

    They are wired up after the answer is in the DOM, and a throw in any of
    them used to land in the catch that writes REQUEST FAILED over it.
    """
    assert "function decoration(" in HTML
    body = HTML.split("async function ask()")[1]
    for what in ("context strip", "listen button", "feedback controls"):
        assert "decoration('" + what + "'" in body, what + " is not guarded"


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
#
# The other half of the same contract. Above: the client reads what the server
# writes. Here: the server writes what the client reads — every field, on every
# response, whichever pipeline path produced it. A field the client cannot find
# is not a blank space in the UI; before the render path was hardened it was a
# whole clinical answer replaced with REQUEST FAILED.

import ast  # noqa: E402

MAIN = pathlib.Path(__file__).parent.parent / "main.py"

# Read from source rather than imported: importing main constructs a ChromaDB
# client at module scope, which is not a unit test's business.
_MODULE = ast.parse(MAIN.read_text())


def _query_response_fields() -> dict:
    """{field name: has a default} for QueryResponse."""
    for node in _MODULE.body:
        if isinstance(node, ast.ClassDef) and node.name == "QueryResponse":
            return {stmt.target.id: stmt.value is not None
                    for stmt in node.body if isinstance(stmt, ast.AnnAssign)}
    raise AssertionError("QueryResponse is not declared in main.py")


# What the client actually reads off a /query response. Adding a render that
# reads a new field means adding it here.
CLIENT_READS = ("response", "sources", "processing_time_ms", "validator_result",
                "model", "source", "patient_context")


def test_query_response_declares_every_field_the_client_reads():
    fields = _query_response_fields()
    missing = [f for f in CLIENT_READS if f not in fields]
    assert not missing, f"the client renders fields the response does not declare: {missing}"


# Computed by the handler on every path rather than read out of the pipeline
# result, so these cannot go missing and are required on purpose. A response
# with no text is not a response to degrade to.
ALWAYS_COMPUTED = ("response", "processing_time_ms")


def _query_response_kwargs() -> set:
    """The keywords the handler passes when it builds a QueryResponse."""
    for node in ast.walk(_MODULE):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "QueryResponse"):
            return {kw.arg for kw in node.keywords}
    raise AssertionError("main.py never constructs a QueryResponse")


def test_the_fields_the_client_reads_are_never_absent():
    """Defaults, so the key is serialised even on a path that sets nothing.

    Anything pulled out of the pipeline's result dict has to survive a path
    that did not set it. Before the render path was hardened, a field the
    client could not find cost the whole answer.
    """
    fields = _query_response_fields()
    for name in CLIENT_READS:
        if name in ALWAYS_COMPUTED:
            continue
        assert fields[name], f"{name} has no default and can be absent from a response"


def test_the_required_fields_are_the_ones_the_handler_always_supplies():
    """The carve-out above holds only while the handler really does supply them."""
    supplied = _query_response_kwargs()
    for name in ALWAYS_COMPUTED:
        assert name in supplied, f"{name} is required but not always passed"


def test_patient_context_carries_every_key_the_strip_reads():
    """Against the real pipeline, for the query that broke the client."""
    import openai_client as oc

    ctx = oc.rebuild_patient_context_from_history(
        "I have a patient who is hypotensive his blood pressure is 90/30. He has "
        "a fever of 104 and he has a recent infection I need to know general "
        "treatment. I have an IV established and he is 75 kg.",
        conversation_history=[], now_ts="2026-08-21T10:21:54Z")
    d = ctx.to_dict()
    for key in ("confirmed_weight_kg", "age_years", "access_state", "vitals"):
        assert key in d, f"the strip reads {key} and the response does not carry it"
    assert d["confirmed_weight_kg"] == 75.0
    assert d["access_state"] == "CONFIRMED_IV_IO"
    assert set(d["vitals"]) >= {"sbp", "dbp"}


def test_the_numeric_context_fields_are_numbers_on_the_wire():
    """Stated, because the client got this wrong.

    These are floats in JSON, not strings. Anything rendering them has to
    convert; this is the assertion that says so out loud.
    """
    import openai_client as oc

    ctx = oc.rebuild_patient_context_from_history(
        "7 year old, 40 kg, HR 120", conversation_history=[],
        now_ts="2026-08-21T10:21:54Z")
    d = ctx.to_dict()
    assert isinstance(d["confirmed_weight_kg"], float)
    assert isinstance(d["age_years"], float)
    assert isinstance(d["vitals"]["hr"]["value"], float)


def test_every_vital_reading_is_shaped_the_way_the_strip_expects():
    """value / unit / ts on every reading — ts may be None, but the key is there.

    A reading with no `ts` renders "age ?" and is styled stale. A reading with
    no `ts` KEY would have been an undefined into the escape helper.
    """
    import openai_client as oc

    ctx = oc.rebuild_patient_context_from_history(
        "BP 90/30, HR 130, SpO2 91%, RR 28, GCS 14, temp 39.4 C",
        conversation_history=[], now_ts="2026-08-21T10:21:54Z")
    vitals = ctx.to_dict()["vitals"]
    assert vitals, "nothing parsed; the fixture no longer exercises the contract"
    for name, reading in vitals.items():
        assert set(reading) >= {"value", "unit", "ts"}, f"{name}: {reading}"
        assert isinstance(reading["value"], (int, float)), name
        assert isinstance(reading["unit"], str), name
