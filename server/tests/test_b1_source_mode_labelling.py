"""B1 (owner, work order): a dose served from a JTS-cited signed contract is
JTS-grounded, regardless of retrieval score, and the SOURCE line carries the
contract's citation. Format only: nothing held, served or dosed changes.

The evidence: "80 kg adult, severe pain from a femur fracture, fentanyl IV"
(run_tests.sh B1) retrieves the JTS Analgesia and Sedation PFC guideline
(CPG ID61) as its source chips, but its top score (0.196) is under the 0.35
JTS_GROUNDED line, so it was labelled GENERAL_MEDICAL ("general") and the model
was told to write "General Evidence-Based Medicine (outside retrieved JTS
scope)" — while the only IV fentanyl dose it could serve is the signed adult
fixed dose whose contract cites CPG ID61.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

QUERY = "80 kg adult, severe pain from a femur fracture, fentanyl IV"
GENERAL_SOURCE = "**SOURCE**: General Evidence-Based Medicine (outside retrieved JTS scope)"
# The signed adult IV fixed dose (JTS PFC, CPG ID61): 50 mcg.
ID61_GIVE = "**GIVE**\n- Draw 1 mL of 0.05mg/mL fentanyl IV (0.05mg). Indication: acute pain.\n"
# The IN entry cites NASEMSO only: 1 mcg/kg at 80 kg.
NASEMSO_GIVE = "**GIVE**\n- Draw 1.6 mL of 0.05mg/mL fentanyl IN (0.08mg). Indication: acute pain.\n"
SAFE = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
# gpt-4o-mini's served answer to QUERY, from the live session log of 2026-10-03,
# verbatim: GENERAL_MEDICAL, the ID61-signed 50 mcg in the no-volume form the
# dose block asks for (no fentanyl concentration is declared), no canonical
# "Draw X mL of Y mg/mL" line at all.
LOGGED_ANSWER = """**BRIEF**
- Draw 50 mcg fentanyl IV. Indication: acute pain / analgesia.
- Prepare for slow IV push over 3-5 minutes.
- Watch for hypotension.

**DO THIS**
1. Draw 50 mcg fentanyl IV. Indication: acute pain / analgesia.
2. Administer slowly over 3-5 minutes.
3. Monitor vital signs closely.

**GIVE**
- Fentanyl IV: 50 mcg. NO VOLUME — confirm concentration to compute volume. Indication: acute pain / analgesia.

**WATCH**
- Monitor for respiratory depression.

**DON'T**
- Hypotension.

**TLDR**
- Administer 50 mcg fentanyl IV for severe pain. 

**SOURCE**: General Evidence-Based Medicine"""


class _Id61Chips:
    """What retrieval returned for QUERY: ID61 pages, top score 0.196."""
    def query(self, *a, **k):
        return {"documents": [["PCC text", "ID61 p.10 text", "ID61 p.6 text"]],
                "metadatas": [[{"source": "Prolonged Casualty Care Guidelines", "page": 31},
                               {"source": "Analgesia and Sedation Management during Prolonged Field Care", "page": 10},
                               {"source": "Analgesia and Sedation Management during Prolonged Field Care", "page": 6}]],
                "distances": [[0.804, 0.829, 0.843]]}


def _run(monkeypatch, generator_text):
    def fake_chat(system, messages, *, model, temperature=0.2, max_tokens=700):
        return SAFE if system == oc.VALIDATOR_PROMPT else generator_text
    monkeypatch.setattr(providers, "chat", fake_chat)
    for name in ("CDSS_LLM_PROVIDER", "CDSS_LLM_MODEL", "CDSS_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return oc._query_with_rag_internal(QUERY, _Id61Chips())


def _source_line(response):
    return [l for l in response.splitlines() if l.startswith("**SOURCE**")]


def test_the_contract_is_what_the_evidence_assumes():
    ctx = oc.rebuild_patient_context_from_history(QUERY)
    iv = [d for d in oc.build_allowed_doses(QUERY, ctx) if d.drug == "fentanyl" and d.route == "IV"]
    assert [round(d.dose_mg, 6) for d in iv] == [0.05], iv
    assert "JTS PFC fixed dose" in iv[0].indication


def test_the_retrieval_alone_is_general(monkeypatch):
    # The score is what it was: the stub reproduces GENERAL_MEDICAL.
    assert oc.classify_retrieval(_Id61Chips().query()).source_mode == "GENERAL_MEDICAL"


def test_a_served_id61_dose_is_labelled_jts(monkeypatch):
    r = _run(monkeypatch, ID61_GIVE + "\n" + GENERAL_SOURCE)
    assert r["validator_result"] != "UNSAFE", r["response"]
    assert r["source_mode"] == "JTS_GROUNDED"
    assert oc.knowledge_source(r["source_mode"]) == "jts"


def test_the_logged_answer_is_labelled_jts_and_cites_id61(monkeypatch):
    r = _run(monkeypatch, LOGGED_ANSWER)
    assert r["validator_result"] != "UNSAFE", r["response"]
    assert r["source_mode"] == "JTS_GROUNDED"
    lines = _source_line(r["response"])
    assert len(lines) == 1 and "CPG ID61" in lines[0], lines
    assert "ID61" in r["response"]  # run_tests.sh B1's pass string
    before, after = LOGGED_ANSWER.split("**SOURCE**")[0], r["response"].split("**SOURCE**")[0]
    assert after.endswith(before), "only the SOURCE line may change"


def test_the_logged_answer_with_80_mcg_stays_general(monkeypatch):
    # The same answer at the NASEMSO 1 mcg/kg IN value is not the ID61 dose.
    r = _run(monkeypatch, LOGGED_ANSWER.replace("50 mcg", "80 mcg").replace(" IV", " IN"))
    assert r["source_mode"] == "GENERAL_MEDICAL"


def test_the_source_line_carries_the_contracts_citation(monkeypatch):
    r = _run(monkeypatch, ID61_GIVE + "\n" + GENERAL_SOURCE)
    lines = _source_line(r["response"])
    assert len(lines) == 1, r["response"]
    assert "CPG ID61" in lines[0], lines
    assert "General Evidence-Based Medicine" not in lines[0], lines


def test_only_the_source_line_changes(monkeypatch):
    # The deployment declares no fentanyl concentration, so the volume audit
    # strips the volume either way; everything but the SOURCE line is the same
    # text the NASEMSO-only answer gets, line for line.
    r = _run(monkeypatch, ID61_GIVE + "\n" + GENERAL_SOURCE)
    n = _run(monkeypatch, NASEMSO_GIVE + "\n" + GENERAL_SOURCE)
    body = [l for l in r["response"].splitlines() if not l.startswith("**SOURCE**")]
    other = [l for l in n["response"].splitlines() if not l.startswith("**SOURCE**")]
    assert len(body) == len(other) and "0.05" in "\n".join(body), r["response"]
    assert r["sources"][1]["title"] == "Analgesia and Sedation Management during Prolonged Field Care"


# ── guards: pass before and after ────────────────────────────────────────────

def test_a_nasemso_only_dose_stays_general(monkeypatch):
    r = _run(monkeypatch, NASEMSO_GIVE + "\n" + GENERAL_SOURCE)
    assert r["source_mode"] == "GENERAL_MEDICAL"
    assert _source_line(r["response"]) == [GENERAL_SOURCE]


def test_no_dose_served_stays_general(monkeypatch):
    text = "**DO THIS**\n1. Splint the femur.\n\n" + GENERAL_SOURCE
    r = _run(monkeypatch, text)
    assert r["source_mode"] == "GENERAL_MEDICAL"
    assert _source_line(r["response"]) == [GENERAL_SOURCE]


def test_a_held_answer_is_not_relabelled(monkeypatch):
    # 1 mg is not the signed dose: held. The hold is Python's text, not JTS's.
    held = "**GIVE**\n- Draw 20 mL of 0.05mg/mL fentanyl IV (1mg).\n\n" + GENERAL_SOURCE
    r = _run(monkeypatch, held)
    assert r["validator_result"] == "UNSAFE"
    assert r["source_mode"] == "GENERAL_MEDICAL"
