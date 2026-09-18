"""
EdgeCDSS — the portal shows the brief first and folds the rest.

Runs the real client script (client_render_harness.js) against payloads built
by the real pipeline, so what is folded and what is not is asserted on cards a
medic is actually served.

The rules pinned here:
  - the brief comes first, and every section of the response is still on the
    page, under a one-tap heading;
  - a hold, CONFIRM VIAL, DON'T, a section the server marks critical, and
    every warning never start folded, whatever the saved preference says;
  - the saved preference opens what the medic opened last time, and storage
    that is missing or throws costs the preference, never the answer;
  - the feedback controls are unchanged.

Requires node; skipped where it is absent, as test_client_render.py is.

    cd server && ./run_unit_tests.sh
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402

HERE = pathlib.Path(__file__).parent
HARNESS = HERE / "client_render_harness.js"
CLIENT = HERE.parent / "static" / "index.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node is not installed; client render harness cannot run")


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def _payload(result):
    return {k: result[k] for k in ("response", "brief", "critical_sections",
                                   "validator_result")}


@pytest.fixture(scope="module")
def payloads():
    rsi = oc._query_with_rag_internal(
        "RSI an 80kg male trauma patient ketamine and rocuronium", _NoRetrieval())
    # The human-review note is appended after a served answer. It is a warning
    # and must never fold with the section it happens to follow.
    rsi = dict(rsi, response=rsi["response"] + oc.HUMAN_REVIEW_BANNER)
    hold = oc._query_with_rag_internal("patient with WPW and SVT give adenosine",
                                       _NoRetrieval())
    prose = oc.attach_brief({"response": (
        "Normal lactate is below 2 mmol/L. Above 4 suggests hypoperfusion. "
        "Trend it. Recheck after resuscitation.\n\n"
        "General reference, not JTS. Confirm against local protocol."
        + oc.HUMAN_REVIEW_BANNER), "validator_result": "NEEDS_HUMAN_REVIEW"})
    return {"rsi": _payload(rsi), "hold": _payload(hold),
            "no_sections": _payload(prose)}


@pytest.fixture(scope="module")
def rendered(payloads):
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "payloads.json"
        path.write_text(json.dumps(payloads))
        proc = subprocess.run(["node", str(HARNESS), str(CLIENT), "brief", str(path)],
                              capture_output=True, text=True, timeout=120)
    assert proc.stdout, f"harness produced no output\n{proc.stderr}"
    out = json.loads(proc.stdout)
    for name, scenario in out.items():
        assert "error" not in scenario, f"{name} render threw: {scenario['error']}"
    return out


def details(bubble, name):
    """The opening <details> tag for a section, or None."""
    m = re.search(r'<details class="sect[^"]*" data-name="' + re.escape(name) + r'"[^>]*>',
                  bubble)
    return m.group(0) if m else None


def is_open(tag):
    return tag is not None and tag.endswith(" open>")


# ── brief first, nothing lost ────────────────────────────────────────────────

def test_the_brief_is_the_first_thing_in_the_answer(rendered, payloads):
    bubble = rendered["rsi"]["bubble"]
    first_line = payloads["rsi"]["brief"].splitlines()[0]
    assert '<div class="brief">' in bubble
    assert bubble.index('<div class="brief">') < bubble.index("<details")
    assert first_line.split(" · ")[0].replace("&", "&amp;") in bubble


def test_every_section_is_still_on_the_page(rendered, payloads):
    bubble = rendered["rsi"]["bubble"]
    for name in ("DO THIS", "GIVE", "POST-INTUBATION SEDATION", "CONFIRM VIAL",
                 "CONTRAINDICATIONS", "CAUTIONS", "WATCH", "DON'T", "TLDR", "SOURCE"):
        assert details(bubble, name) is not None, f"{name} is missing"
    # The clinical text itself, not only its heading.
    assert "Never give paralytic before induction in a patient with a pulse." in bubble
    assert "Pre-oxygenate and prepare suction" in bubble


def test_ordinary_sections_start_folded(rendered):
    bubble = rendered["rsi"]["bubble"]
    for name in ("DO THIS", "GIVE", "WATCH", "SOURCE", "CAUTIONS"):
        assert not is_open(details(bubble, name)), f"{name} should start folded"


def test_the_source_chips_are_folded_too(rendered):
    bubble = rendered["rsi"]["bubble"]
    tag = details(bubble, "SOURCES")
    assert tag is not None and not is_open(tag)
    assert bubble.index(tag) < bubble.index("JTS Airway CPG")


# ── what never starts folded ─────────────────────────────────────────────────

def test_confirm_vial_stays_open(rendered):
    assert is_open(details(rendered["rsi"]["bubble"], "CONFIRM VIAL"))


def test_sections_the_server_marks_critical_stay_open(rendered, payloads):
    bubble = rendered["rsi"]["bubble"]
    assert payloads["rsi"]["critical_sections"], "the RSI card no longer marks anything critical"
    for name in payloads["rsi"]["critical_sections"]:
        tag = details(bubble, name)
        assert is_open(tag), f"{name} is critical and folded"
        assert "critical" in tag


def test_dont_never_folds_even_unmarked_and_saved_closed(rendered):
    """The server marks DON'T critical, but the client does not rely on it."""
    bubble = rendered["dont_unmarked"]["bubble"]
    tag = details(bubble, "DON'T")
    assert is_open(tag), "DON'T folded when the server did not mark it"
    assert "Avoid succinylcholine in burns/crush/hyperkalemia risk" in bubble


def test_the_client_never_folds_every_spelling_brief_py_reads():
    import brief
    html = CLIENT.read_text()
    line = next(l for l in html.splitlines() if l.startswith("const ALWAYS_OPEN"))
    for name in brief.DONT_SECTIONS:
        assert f"'{name}'" in line or f'"{name}"' in line, f"{name} can fold"


def test_a_warning_never_folds(rendered):
    bubble = rendered["rsi"]["bubble"]
    note = bubble.index("CLINICAL SAFETY NOTE")
    assert note > bubble.rindex("</details>"), "the review note is inside a folded section"


def test_a_hold_is_shown_in_full_and_open(rendered, payloads):
    bubble = rendered["hold"]["bubble"]
    assert '<div class="brief hold">' in bubble
    assert "Reassess patient. Use local protocol." in bubble
    for tag in re.findall(r"<details[^>]*>", bubble):
        assert "SOURCES" in tag or is_open(tag), f"a hold folded something: {tag}"


def test_prose_folds_but_its_warning_does_not(rendered):
    bubble = rendered["no_sections"]["bubble"]
    tag = details(bubble, "FULL ANSWER")
    assert tag is not None and not is_open(tag)
    assert bubble.index("CLINICAL SAFETY NOTE") > bubble.rindex("</details>")


# ── the remembered preference ────────────────────────────────────────────────

def test_a_saved_preference_opens_the_section(rendered):
    assert is_open(details(rendered["pref_open"]["bubble"], "DO THIS"))
    assert not is_open(details(rendered["pref_open"]["bubble"], "WATCH"))


def test_a_saved_preference_cannot_fold_a_forced_section(rendered):
    """CONFIRM VIAL was saved closed. It is open anyway."""
    assert is_open(details(rendered["pref_open"]["bubble"], "CONFIRM VIAL"))


def test_storage_that_throws_costs_the_preference_not_the_answer(rendered):
    bubble = rendered["storage_throws"]["bubble"]
    assert "REQUEST FAILED" not in bubble
    assert '<div class="brief">' in bubble
    assert is_open(details(bubble, "CONFIRM VIAL"))


def test_a_toggle_is_remembered_per_section(rendered):
    assert rendered["pref_saved"] == {"WATCH": True}


# ── unchanged ────────────────────────────────────────────────────────────────

def test_the_feedback_controls_are_unchanged(rendered):
    bubble = rendered["rsi"]["bubble"]
    assert '<button class="fbbtn" data-v="appropriate">✓ clinically appropriate</button>' in bubble
    assert '<button class="fbbtn flag" data-v="flagged">⚠ flag issue</button>' in bubble


def test_the_toggles_are_furniture(rendered):
    """Wiring the toggles is decoration: a throw there cannot unrender the answer."""
    html = CLIENT.read_text()
    body = html.split("async function ask(")[1]
    assert "decoration('section toggles'" in body


# ── follow-up chips ──────────────────────────────────────────────────────────

def test_chips_sit_under_the_brief(rendered):
    bubble = rendered["rsi"]["bubble"]
    assert '<div class="chips">' in bubble
    assert bubble.index('<div class="brief">') < bubble.index('<div class="chips">') \
        < bubble.index("<details")
    for label in ("Why?", "Contraindications", "Vial math", "Pediatric",
                  "What to watch", "Full protocol"):
        assert ">" + label + "</button>" in bubble


def test_chip_labels_are_separated_in_the_text_not_only_the_layout(rendered):
    """On a phone the flex gap spaces them (checked in headless Chromium at
    390 px). The pasted output ran them together because the markup had no
    whitespace between buttons, so anything reading text rather than layout
    got "Why?ContraindicationsVial math"."""
    bubble = rendered["rsi"]["bubble"]
    chips = bubble[bubble.index('<div class="chips">'):]
    chips = chips[:chips.index("</div>")]
    text = re.sub(r"<[^>]+>", "", chips)
    assert text == "Why? Contraindications Vial math Pediatric What to watch Full protocol"
    css = CLIENT.read_text()
    assert re.search(r"\.chips\s*\{[^}]*gap:\s*\d+px[^}]*flex-wrap:\s*wrap", css), \
        "the chip row lost its gap or its wrap"


def test_no_chips_under_a_hold(rendered):
    assert '<div class="chips">' not in rendered["hold"]["bubble"]


def test_a_chip_goes_out_through_the_history_path_tagged_chip(rendered):
    bodies = rendered["chip_request"]["bodies"]
    assert len(bodies) == 2
    typed, chip = bodies
    assert typed["input_mode"] == "typed"
    assert chip["input_mode"] == "chip"
    assert chip["query"] == "Why that dose?"
    assert [t["query"] for t in chip["conversation_history"]] == \
        ["RSI an 80kg male trauma patient ketamine and rocuronium"]
    assert chip["model"] == typed["model"] and chip["voice_mode"] == typed["voice_mode"]
