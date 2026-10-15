"""Pain severity is the clinician's to declare (owner, #164 review, 2026-10-15).

#164 offers a drugless pain question the signed pain entries. With #163 signed,
acetaminophen ("mild to moderate pain") matched "severe pain" too, because the
rule matched any entry labelled pain and read no severity. The owner's ruling:

- Severity is clinician-declared, never inferred from sparse vitals.
- Undeclared, the system asks mild / moderate / severe as an explicit choice,
  with each one's criteria inline, one line each.
- The choice selects the dose set, and the question says so ("severe → ...").
- When the vitals grossly contradict the choice ("mild" with RR <= 8), a soft
  advisory is shown. It never blocks and never changes the verdict.

Doctrine (docs/DESIGN_PRINCIPLES.md): gates on physiology, advisories on
judgment. Severity is judgment.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402
import vitals as vitals_mod  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
UNDECLARED = "80 kg adult, closed femur fracture, screaming in pain, IV access, what can I give"
MILD_ONLY = {"acetaminophen"}
SEVERE_ONLY = {"ketamine", "fentanyl", "morphine"}


def _ctx(q):
    return oc.rebuild_patient_context_from_history(q)


def _drugs(q, current=None):
    return {d.drug for d in oc.build_allowed_doses(q, _ctx(q), current_query=current)}


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def seen(monkeypatch):
    out = {"allowed": None, "generator": None}
    real = oc.build_allowed_doses

    def build(history, ctx, **kw):
        doses = real(history, ctx, **kw)
        out["allowed"] = doses
        return doses

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        out["generator"] = messages
        give = oc.render_give_line(out["allowed"][0]) if out["allowed"] else ""
        return "**BRIEF**\n- Analgesia.\n\n**GIVE**\n" + give + "\n"

    monkeypatch.setattr(oc, "build_allowed_doses", build)
    monkeypatch.setattr(providers, "chat", chat)
    return out


def run(query, history=()):
    return oc._query_with_rag_internal(query, _JtsHit(), conversation_history=list(history))


# ── undeclared: asked, never inferred ────────────────────────────────────────

def test_an_undeclared_pain_question_is_asked_the_severity(seen):
    r = run(UNDECLARED)
    assert r["source_mode"] == "PRE_GATE", r["response"]
    assert r["response"].startswith(oc.PAIN_SEVERITY_QUESTION_PREFIX)
    assert seen["generator"] is None


def test_the_question_gives_each_severity_its_criteria_on_one_line():
    _a, q = oc.pre_gate(UNDECLARED, _ctx(UNDECLARED))
    lines = q.splitlines()
    for level in ("mild", "moderate", "severe"):
        mine = [l for l in lines if re.match(rf"\W*{level}\b", l, re.I)]
        assert len(mine) == 1, (level, q)
        assert re.search(r"NRS \d+.\d+", mine[0]), mine[0]


def test_the_question_says_what_each_choice_selects():
    _a, q = oc.pre_gate(UNDECLARED, _ctx(UNDECLARED))
    severe = next(l for l in q.splitlines() if re.match(r"\W*severe\b", l, re.I))
    mild = next(l for l in q.splitlines() if re.match(r"\W*mild\b", l, re.I))
    assert "→" in severe and "ketamine" in severe and "acetaminophen" not in severe, severe
    assert "→" in mild and "acetaminophen" in mild and "ketamine" not in mild, mild


def test_the_question_states_no_dose():
    _a, q = oc.pre_gate(UNDECLARED, _ctx(UNDECLARED))
    assert not re.search(r"\d\s*(?:mg|mcg|ml)\b", q, re.I), q


@pytest.mark.parametrize("q", [
    "80 kg adult, femur fracture, in pain, HR 140, BP 160/95, RR 28, what can I give",
    "80 kg adult, femur fracture, in pain, HR 62, BP 118/76, RR 14, what can I give",
])
def test_severity_is_not_inferred_from_vitals(q):
    action, text = oc.pre_gate(q, _ctx(q))
    assert action == "ASK" and text.startswith(oc.PAIN_SEVERITY_QUESTION_PREFIX), text


# ── declared: not asked; the choice selects the set ──────────────────────────

@pytest.mark.parametrize("q", [
    "80 kg adult, severe pain from a closed femur fracture, IV access, what can I give",
    "80 kg adult, femur fracture, pain 8/10, IV access, what can I give",
    "80 kg adult, femur fracture, mild pain, what can I give",
])
def test_a_declared_severity_is_not_asked(q):
    assert oc.pre_gate(q, _ctx(q))[0] == "CONTINUE"


def test_severe_selects_the_moderate_to_severe_set():
    q = "80 kg adult, severe pain from a closed femur fracture, IV access, what can I give"
    got = _drugs(q)
    assert "ketamine" in got and "acetaminophen" not in got, got


def test_mild_selects_the_mild_to_moderate_set():
    got = _drugs("80 kg adult, femur fracture, mild pain, what can I give")
    assert got == MILD_ONLY, got


def test_moderate_selects_both():
    got = _drugs("80 kg adult, femur fracture, moderate pain, what can I give")
    assert "acetaminophen" in got and "ketamine" in got, got


@pytest.mark.parametrize("score,expect", [("2/10", MILD_ONLY), ("9/10", None)])
def test_a_stated_pain_score_is_a_declaration(score, expect):
    got = _drugs(f"80 kg adult, femur fracture, pain {score}, what can I give")
    if expect:
        assert got == expect, got
    else:
        assert "acetaminophen" not in got and "ketamine" in got, got


def test_the_answer_turn_selects_the_set(seen):
    asked = run(UNDECLARED)["response"]
    run("severe", [{"query": UNDECLARED, "response": asked}])
    got = {d.drug for d in seen["allowed"]}
    assert "ketamine" in got and "acetaminophen" not in got, got


def test_a_named_drug_is_not_asked_the_severity():
    q = "80 kg adult, femur fracture, in pain, IV access, how much fentanyl"
    assert oc.pre_gate(q, _ctx(q))[0] == "CONTINUE"


# ── RR: the physiology gate stays; the question shows its reasoning ──────────

def test_at_rr_8_severe_selects_ketamine_and_says_why_the_opioids_are_not_offered():
    q = "80 kg adult, femur fracture, screaming in pain, RR is 8, what analgesia do I give"
    _a, text = oc.pre_gate(q, _ctx(q))
    severe = next(l for l in text.splitlines() if re.match(r"\W*severe\b", l, re.I))
    assert "ketamine" in severe, severe
    assert "fentanyl" not in severe.split("→")[1].split("(")[0], severe
    assert "RR < 10" in text, text


def test_the_rr_caution_states_its_trigger():
    """Owner, #164: RR <= 8 is respiratory depression, inclusive, and the warning
    shows the trigger. The rule stays at RR < 10 (owner, 2026-10-15: moving it
    would loosen the gate at RR 9), and its sentence states that threshold."""
    rule = next(r for r in vitals_mod.CAUTIONS if r["id"] == "respiratory_depressant_low_rr")
    assert rule["when"]["rr"] == {"lt": 10}
    ctx = _ctx("80 kg adult, RR 8")
    out = vitals_mod.conflicts("give fentanyl 50 mcg IV", ctx.vitals)
    assert out and "RR < 10" in out[0], out
    assert "8/min" in out[0], out


def test_rr_8_still_arms_the_caution_inclusively():
    for rr in (8, 9):
        ctx = _ctx(f"80 kg adult, RR {rr}")
        assert vitals_mod.conflicts("give morphine 5 mg IV", ctx.vitals), rr
    assert not vitals_mod.conflicts("give morphine 5 mg IV", _ctx("80 kg adult, RR 10").vitals)


# ── the advisory: soft, never a block ────────────────────────────────────────

def test_mild_with_rr_8_shows_an_advisory_and_changes_nothing_else(seen):
    q = "80 kg adult, femur fracture, mild pain, RR 8, what can I give"
    r = run(q)
    assert oc.SEVERITY_ADVISORY_HEADING.strip() in r["response"], r["response"]
    assert "RR ≤ 8" in r["response"]
    assert "mild" in r["response"].split(oc.SEVERITY_ADVISORY_HEADING.strip())[1]
    assert {d.drug for d in seen["allowed"]} == MILD_ONLY
    assert r["source_mode"] != "PRE_GATE"
    control = run(q.replace("RR 8", "RR 16"))
    assert oc.SEVERITY_ADVISORY_HEADING.strip() not in control["response"]
    assert r["validator_result"] == control["validator_result"], (r["validator_issues"], control["validator_issues"])


# ── replay (2026-10-15): the question must say what will actually be offered ──

def test_with_no_weight_the_question_says_which_drugs_need_one():
    """"Need to know what pain med to give" (H-SESS-043, live) was told
    "severe → ketamine, fentanyl, morphine dosing"; with no weight only the
    fixed doses resolve, so the line must not promise a weight-based one."""
    q = "Need to know what pain med to give"
    _a, text = oc.pre_gate(q, _ctx(q))
    severe = next(l for l in text.splitlines() if re.match(r"\W*severe\b", l, re.I))
    offered = severe.split("→")[1].split("(")[0]
    assert "ketamine" not in offered and "morphine" not in offered, severe
    assert "need a weight" in severe and "ketamine" in severe, severe
    got = {d.drug for d in oc.build_allowed_doses(q + ". Pain severity: severe", _ctx(q))}
    assert got <= set(re.findall(r"[a-z]+", offered)), (got, severe)
