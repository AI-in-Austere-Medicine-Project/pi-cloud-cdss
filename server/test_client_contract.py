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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import general_reference as gr  # noqa: E402

CLIENT = pathlib.Path(__file__).parent / "static" / "index.html"
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
    """Systolic and diastolic are one measurement and are shown as one."""
    assert "r.value + '/' + v.dbp.value" in HTML
