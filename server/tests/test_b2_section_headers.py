"""B2 (owner, work order; rulings 2026-10-04): generator section headers.

Headers drift: the generator writes TREAT, WATCH FOR, EVAC IF, a condition
title ("SEVERE HEAD INJURY", "CONDITION", "NEXT HOUR OF CARE") or a qualified
heading ("GIVE — IF PAIN NOT RELIEVED AT 15 MIN"), and the portal showed both
the answer's SOURCE and its own SOURCES fold for the retrieval chips.

The owner's rulings:
  - normalise by rewriting the served generator answer's header lines, after
    the gate, to DO THIS, GIVE, WATCH, DON'T, EVAC, TLDR, SOURCE; a hold and a
    deterministic card are not touched;
  - BRIEF, GATE QUESTION, DRIP, VENT and POST-INTUBATION SEDATION stay as
    they are;
  - an unknown header folds into the following canonical section, and the
    brief never takes a "What it is:" / "Why it matters:" line as its next
    action.
Format only: no word under a header changes, and nothing held, served or dosed
changes. A qualifier on a header is clinical text and is kept beside the
canonical name; a folded title is kept as a plain line.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import brief  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402

# Captured generator outputs, verbatim (cdss-eval runs).
# local-llm-cloud-30-r1-20260924, H-IM-04, gpt-4o-mini, served.
H_IM_04 = '**BRIEF**\n- Assess for signs of herniation.\n- Prepare for possible intubation.\n- Monitor vital signs closely.\n\n**SEVERE HEAD INJURY**\n- What it is: A severe head injury with a GCS of 7 and a blown pupil indicates potential brain herniation.\n- Why it matters: Immediate intervention is critical to prevent further neurological damage.\n\n**TREAT**\n1. Pre-oxygenate the patient.\n2. Prepare for intubation if indicated.\n3. Establish IV access and consider fluid resuscitation.\n\n**WATCH FOR**\n- Changes in vital signs or neurological status.\n\n**EVAC IF**\n- Signs of herniation or deterioration in GCS.\n\n**TLDR**\n- Pre-oxygenate and prepare for intubation. \n\n**SOURCE**: General Evidence-Based Medicine'
# d1-gpt-4o-mini-p1, G-ADV-04, gpt-4o-mini, served.
G_ADV_04 = '**BRIEF**\n- Monitor vital signs closely.\n- Assess for any new injuries or changes in condition.\n- Ensure safety and readiness for evacuation if needed.\n\n**NEXT HOUR OF CARE**\n1. Perform a thorough secondary survey for injuries.\n2. Maintain IV access and administer fluids as needed.\n3. Reassess vital signs every 15 minutes and document changes.\n\n**WATCH FOR**\n- Signs of internal bleeding or shock.\n\n**TLDR**\n- Conduct a secondary survey and monitor vitals closely. \n\n**SOURCE**: General Evidence-Based Medicine (outside retrieved JTS scope)'
# mm3-claude-haiku-4.5-p1, G-MTN-03, claude-haiku-4-5 (held there; the text is the fixture).
G_MTN_03 = "**BRIEF**\n- Ketamine 40 mg IM given for arm fracture pain.\n- Reassess pain in 15 minutes. If breakthrough pain, repeat dose.\n- Position arm comfortably; splint or sling if available.\n\n**DO THIS**\n1. Reassess pain at 15 minutes using age-appropriate pain scale (faces, numbers, or behavioral cues).\n2. Splint or immobilize the arm to prevent movement and further injury.\n3. Keep child calm; provide comfort measures (positioning, reassurance).\n\n**WATCH**\n- Respiratory rate stays ≥10/min. Nystagmus (eyes rolling) is normal with ketamine.\n- Watch for dissociation — child may seem distant or unresponsive but is safe.\n\n**GIVE — IF PAIN NOT RELIEVED AT 15 MIN**\n- Draw 0.4 mL of 100mg/mL ketamine IM (40 mg). Indication: breakthrough pain.\n- May repeat every 15 minutes until pain controlled or nystagmus occurs.\n\n**DON'T**\n- Do not overseduce. Stop dosing if RR falls below 10 or child cannot protect airway.\n\n**EVAC IF**\n- Neurovascular compromise (pale, pulseless, cold limb), open fracture with bleeding, or altered mental status beyond expected dissociation.\n\n**TLDR**\n- Ketamine 40 mg IM; recheck pain at 15 min.\n\n**SOURCE**: JTS Pain, Anxiety and Delirium CPG (2021)"

CANONICAL = {"DO THIS", "GIVE", "WATCH", "DON'T", "EVAC", "TLDR", "SOURCE"}
KEPT = {"BRIEF", "GATE QUESTION", "DRIP", "VENT", "POST-INTUBATION SEDATION"}


def _headers(text):
    return [name for name, _ in brief.parse_sections(text)[1] if name]


def _words(text):
    """Every word, header markup aside: what format-only must preserve."""
    return sorted(re.findall(r"[\w'’≥<>/.%-]+", text.replace("**", " ")))


def _content_words(text):
    return sorted(w for w in _words(text) if w not in {"TREAT", "FOR", "IF", "WATCH", "EVAC"})


@pytest.mark.parametrize("raw, expected", [
    (H_IM_04, ["BRIEF", "DO THIS", "WATCH", "EVAC", "TLDR", "SOURCE"]),
    (G_ADV_04, ["BRIEF", "WATCH", "TLDR", "SOURCE"]),
    (G_MTN_03, ["BRIEF", "DO THIS", "WATCH", "GIVE", "DON'T", "EVAC", "TLDR", "SOURCE"]),
])
def test_three_captured_outputs_get_the_canonical_headers(raw, expected):
    assert _headers(brief.normalise_headers(raw)) == expected


@pytest.mark.parametrize("raw", [H_IM_04, G_ADV_04, G_MTN_03])
def test_no_content_is_lost(raw):
    # Only header words may go (TREAT, WATCH FOR -> WATCH, EVAC IF -> EVAC).
    out = brief.normalise_headers(raw)
    assert _content_words(out) == _content_words(raw)
    assert all(line in out for line in raw.splitlines()
               if line.strip() and not line.startswith("**"))


def test_a_qualifier_on_a_header_is_kept():
    out = brief.normalise_headers(G_MTN_03)
    assert "**GIVE**: IF PAIN NOT RELIEVED AT 15 MIN" in out


def test_a_folded_condition_explainer_follows_the_steps():
    out = brief.normalise_headers(H_IM_04)
    do_this = dict(brief.parse_sections(out)[1])["DO THIS"]
    items = [l for l in do_this if l.strip()]
    assert items[0] == "1. Pre-oxygenate the patient."
    assert "SEVERE HEAD INJURY" in items
    assert items.index("SEVERE HEAD INJURY") > items.index(
        "3. Establish IV access and consider fluid resuscitation.")


def test_the_brief_never_takes_an_explainer_as_its_next_action():
    text = ("**BRIEF**\n- Control the bleeding.\n\n**DO THIS**\n"
            "- What it is: Severe blood loss.\n- Why it matters: Shock.\n"
            "1. Apply direct pressure.\n\n**SOURCE**: General Evidence-Based Medicine")
    out = brief.build_brief(text)["brief"]
    assert "What it is" not in out and "Why it matters" not in out


@pytest.mark.parametrize("text", [
    "**BRIEF**\n- x.\n\n**GATE QUESTION**\n- What is the weight?\n\n**DRIP**\n- y.\n\n"
    "**VENT**\n- z.\n\n**POST-INTUBATION SEDATION**\n- w.",
])
def test_structural_headers_stay(text):
    assert brief.normalise_headers(text) == text


def test_canonical_text_is_unchanged():
    text = "**DO THIS**\n1. A.\n\n**GIVE**\n- B.\n\n**WATCH**\n- C.\n\n**DON'T**\n- D.\n\n" \
           "**EVAC**\n- E.\n\n**TLDR**\n- F.\n\n**SOURCE**: G"
    assert brief.normalise_headers(text) == text


@pytest.mark.parametrize("variant, canon", [
    ("SOURCES", "SOURCE"), ("SOURCE:", "SOURCE"), ("DO NOT", "DON'T"), ("DONT", "DON'T"),
    ("TREAT", "DO THIS"), ("DO NOW", "DO THIS"), ("WATCH FOR", "WATCH"), ("EVAC IF", "EVAC"),
])
def test_synonyms(variant, canon):
    out = brief.normalise_headers(f"**{variant}**\n- line.")
    assert _headers(out) == [canon], out


# ── the pipeline: served generator answers only ──────────────────────────────

class _Hit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                "distances": [[0.5]]}


def _run(monkeypatch, query, generator_text, verdict='{"result":"SAFE","issues":[],"rationale":"ok"}'):
    monkeypatch.setattr(providers, "chat", lambda system, messages, **k:
                        verdict if system == oc.VALIDATOR_PROMPT else generator_text)
    for name in ("CDSS_LLM_PROVIDER", "CDSS_LLM_MODEL", "CDSS_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return oc._query_with_rag_internal(query, _Hit())


def test_a_served_generator_answer_is_normalised(monkeypatch):
    q = "patient is unaltered and following commands, roadmap for the next hour of care after a blast"
    r = _run(monkeypatch, q, G_ADV_04)  # G-ADV-04's own query and served answer
    assert r["source_mode"] not in ("DETERMINISTIC_PRE_GATE",), r["source_mode"]
    assert r["validator_result"] != "UNSAFE", r["response"]
    names = _headers(r["response"])
    assert "WATCH FOR" not in names and "NEXT HOUR OF CARE" not in names, names
    assert "WATCH" in names


def test_a_deterministic_card_is_not_touched(monkeypatch):
    r = _run(monkeypatch, "severe TBI patient GCS 6 BP 90/60 needs management", "unused")
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "**SEVERE TBI**" in r["response"] and "**CAUTIONS**" in r["response"]


# ── the portal: one SOURCE section, chips inside it ──────────────────────────

HERE = pathlib.Path(__file__).parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_portal_shows_one_source_section_with_the_chips():
    def payload(text, verdict="SAFE"):
        return oc.attach_brief({"response": text, "validator_result": verdict})
    payloads = {k: {f: v[f] for f in ("response", "brief", "critical_sections", "validator_result")}
                for k, v in {"rsi": payload(brief.normalise_headers(H_IM_04)),
                             "hold": payload(H_IM_04, "UNSAFE"),
                             "no_sections": payload("Plain prose.")}.items()}
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "p.json"
        path.write_text(json.dumps(payloads))
        proc = subprocess.run(["node", str(HERE / "client_render_harness.js"),
                               str(HERE.parent / "static" / "index.html"), "brief", str(path)],
                              capture_output=True, text=True, timeout=120)
    bubble = json.loads(proc.stdout)["rsi"]["bubble"]
    assert 'data-name="SOURCES"' not in bubble
    source = re.search(r'<details class="sect[^"]*" data-name="SOURCE".*?</details>', bubble, re.S)
    assert source, bubble
    assert "General Evidence-Based Medicine" in source.group(0)
    assert "JTS Airway CPG" in source.group(0)  # the harness's retrieval chip
