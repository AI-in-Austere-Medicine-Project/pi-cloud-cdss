"""D6 v3 (owner, 2026-10-08): re-answer v1's 255 questions under the current prompt.

Two changes to tools/build_distill_dataset.py:

1. The wrapper fix. Capture.rdc stands in for run_deterministic_checks during a
   build; A23 gave that function a `current_query` keyword (the pipeline passes
   it), and the wrapper did not take it: every teacher answer raised TypeError
   inside the pipeline. The wrapper passes it through, and the recorded check
   keeps it, so the whole-set check repeats the pipeline's call exactly.

2. --reanswer-from SRC: every row of SRC (train and valid) is asked once more,
   unchanged, through this tree with the teacher. No instruction is added. Before
   any call, a question that is now in the exam set is excluded and counted.
   The new answer takes the same filters as a build (held, fallback, check,
   unasked drug), then the refuse-to-run check, then the junk rule with the
   owner's rulings. Each kept row keeps its original split. Written to --out,
   never over SRC; the run needs the owner's approved ceiling.

Offline: no teacher, validator or ChromaDB call.
"""
import importlib.util
import json
import pathlib
import types

import pytest

import openai_client as oc
import providers

REPO = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build_distill_dataset", REPO / "tools/build_distill_dataset.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)

MODEL_Q = "80 kg adult, severe pain from a femur fracture, what should I do"
CLEAN = "**DO THIS**\n1. Splint the femur and reassess pain.\n\n**SOURCE**: General Evidence-Based Medicine"
SAFE = '{"result":"SAFE","issues":[],"rationale":"ok"}'


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture(autouse=True)
def _restore_rdc():
    real = oc.run_deterministic_checks
    yield
    oc.run_deterministic_checks = real


# ── 1. the wrapper takes current_query ───────────────────────────────────────
def test_the_wrapper_passes_current_query_through_and_records_it():
    seen = {}

    def spy(query, response_text, patient_ctx, allowed_doses=None, current_query=None):
        seen["current_query"] = current_query
        return types.SimpleNamespace(issues=[])
    fake_oc = types.SimpleNamespace(run_deterministic_checks=spy)
    cap = bd.Capture(fake_oc, types.SimpleNamespace(chat=None), stub=True)
    cap.gen = {"response": "answer"}
    cap.rdc("history + question", "answer", {}, [], current_query="question")
    assert seen["current_query"] == "question"
    assert cap.check[0] == "history + question" and cap.check[-1] == "question"


def test_a_pipeline_run_through_the_wrapper_reaches_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    cap = bd.Capture(oc, providers, stub=True)
    result = cap.run(MODEL_Q, _NoRetrieval(), open(tmp_path / "log", "w"))
    assert cap.gen is not None
    assert cap.check is not None, "the check never ran: the wrapper raised inside the pipeline"
    assert result.get("validator_result") != "ERROR"


def test_the_refuse_to_run_check_repeats_the_recorded_call():
    ctx = oc.rebuild_patient_context_from_history(MODEL_Q)
    row = {"scenario_id": "s", "assistant": CLEAN,
           "check": (MODEL_Q, ctx, oc.build_allowed_doses(MODEL_Q, ctx), MODEL_Q)}
    bd.refuse_unsigned_doses([row])


# ── 2. --reanswer-from ───────────────────────────────────────────────────────
def _src(tmp_path, queries):
    src = tmp_path / "v1"
    src.mkdir()
    pairs = []
    for i, (q, sp) in enumerate(queries):
        row = {"messages": [{"role": "system", "content": "the v1 system prompt"},
                            {"role": "user", "content": f"Clinical query: {q}"},
                            {"role": "assistant", "content": "the v1 answer"}]}
        meta = {"scenario_id": f"s{i}", "query": q, "source": "seed", "synthetic": True,
                "split": sp, "snapshot_commit": "d0b44f4", "seed_id": f"seed{i}"}
        pairs.append((row, meta))
    bd.write_split(src, [p for p in pairs if p[1]["split"] == "train"],
                   [p for p in pairs if p[1]["split"] == "valid"])
    return src


class _Exam:
    def __init__(self, texts=()):
        self.texts = set(texts)

    def exact(self, q):
        return q in self.texts

    def near(self, q):
        return False


class _NoExclusion:
    def excludes(self, q):
        return False


SNAP = {"commit": "0" * 40, "contract_bank": {"signed": 68}, "concentrations_sha256": "c"}


@pytest.fixture
def teacher(monkeypatch, tmp_path):
    calls = {"teacher": 0, "answers": {}}
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)

    def chat(system, messages, *, model, **kw):
        if model == bd.TEACHER:
            calls["teacher"] += 1
            q = messages[-1]["content"]
            return next((a for k, a in calls["answers"].items() if k in q), CLEAN)
        return SAFE
    monkeypatch.setattr(providers, "chat", chat)
    return calls


def _run(tmp_path, src, *, exam=None, approve=30.0, plan=False):
    return bd.reanswer(src, tmp_path / "v3", SNAP, oc, providers, _NoRetrieval(),
                       open(tmp_path / "pipeline.log", "w"), approve_cost=approve, plan=plan,
                       exam=exam or _Exam(), exclusion=_NoExclusion(),
                       rulings=bd.ReviewRulings(set(), set()))


def test_every_row_is_asked_again_unchanged_and_keeps_its_split(tmp_path, teacher):
    src = _src(tmp_path, [(MODEL_Q, "train"), ("70 kg male, partial thickness burns 30% TBSA, what now", "valid")])
    m = _run(tmp_path, src)
    assert teacher["teacher"] == 2
    train, valid = bd._read_pairs(tmp_path / "v3", "train"), bd._read_pairs(tmp_path / "v3", "valid")
    assert [x["scenario_id"] for _r, x in train] == ["s0"] and [x["scenario_id"] for _r, x in valid] == ["s1"]
    row, meta = train[0]
    assert row["messages"][-1]["content"] == CLEAN
    assert row["messages"][1]["content"].endswith(MODEL_Q)          # no instruction added
    assert meta["snapshot_commit"] == SNAP["commit"] and meta["v3"]["source_snapshot_commit"] == "d0b44f4"
    assert m["kept"] == 2 and m["source_rows"] == 2


def test_a_question_now_in_the_exam_is_excluded_before_any_call(tmp_path, teacher):
    src = _src(tmp_path, [(MODEL_Q, "train")])
    m = _run(tmp_path, src, exam=_Exam({MODEL_Q}))
    assert teacher["teacher"] == 0
    assert m["exam_excluded"] == {"exam_text": 1} and m["kept"] == 0


def test_a_held_answer_is_dropped_and_counted_by_filter(tmp_path, teacher):
    teacher["answers"]["femur"] = "**DO THIS**\n1. Give fentanyl 1 mg IV now.\n"
    src = _src(tmp_path, [(MODEL_Q, "train")])
    m = _run(tmp_path, src)
    assert m["kept"] == 0 and sum(m["dropped_by_filter"].values()) == 1


def test_the_junk_rule_sends_a_signal_free_question_to_review(tmp_path, teacher):
    src = _src(tmp_path, [("what should I do now", "train")])
    m = _run(tmp_path, src)
    assert m["junk_review"] == 1 and m["kept"] == 0
    assert (tmp_path / "v3/review.jsonl").read_text().strip()


def test_the_run_needs_the_approved_ceiling_and_plan_calls_nothing(tmp_path, teacher):
    src = _src(tmp_path, [(MODEL_Q, "train")])
    with pytest.raises(bd.RefuseToRun):
        _run(tmp_path, src, approve=None)
    _run(tmp_path, src, plan=True)
    assert teacher["teacher"] == 0 and not (tmp_path / "v3/train.jsonl").exists()


def test_the_output_is_never_the_source(tmp_path, teacher):
    src = _src(tmp_path, [(MODEL_Q, "train")])
    with pytest.raises(bd.RefuseToRun):
        bd.reanswer(src, src, SNAP, oc, providers, _NoRetrieval(), open(tmp_path / "l", "w"),
                    approve_cost=30, plan=False, exam=_Exam(), exclusion=_NoExclusion(),
                    rulings=bd.ReviewRulings(set(), set()))


def test_the_flag_exists():
    assert "reanswer_from" in {a.dest for a in bd.parser()._actions}


# ── the actual cost: read from each API response's usage ─────────────────────
def test_the_meter_prices_usage_at_the_list_rates():
    m = bd.UsageMeter()
    m.add("claude-opus-5", 1_000_000, 100_000)
    m.add("gpt-4o-mini", 1_000_000, 0)
    assert m.usd() == pytest.approx(5.0 + 2.5 + 0.15)
    assert m.tokens["claude-opus-5"] == {"calls": 1, "in": 1_000_000, "out": 100_000}


def test_the_meter_reads_the_sdk_responses():
    from anthropic.resources.messages import Messages
    from openai.resources.chat.completions import Completions
    a_usage = types.SimpleNamespace(input_tokens=1000, output_tokens=500,
                                    cache_creation_input_tokens=None, cache_read_input_tokens=200)
    o_usage = types.SimpleNamespace(prompt_tokens=3000, completion_tokens=100)
    real_a, real_o = Messages.create, Completions.create
    stand_a = lambda self, **kw: types.SimpleNamespace(model=kw["model"], usage=a_usage)
    stand_o = lambda self, **kw: types.SimpleNamespace(model=kw["model"], usage=o_usage)
    Messages.create, Completions.create = stand_a, stand_o
    try:
        with bd.UsageMeter() as m:
            Messages.create(None, model="claude-opus-5")
            Completions.create(None, model="gpt-4o-mini")
        assert m.tokens["claude-opus-5"] == {"calls": 1, "in": 1200, "out": 500}
        assert m.tokens["gpt-4o-mini"] == {"calls": 1, "in": 3000, "out": 100}
        assert Messages.create is stand_a and Completions.create is stand_o    # restored on exit
    finally:
        Messages.create, Completions.create = real_a, real_o


def test_the_run_stops_when_actual_spend_passes_the_ceiling(tmp_path, teacher, monkeypatch):
    monkeypatch.setattr(bd.UsageMeter, "usd", lambda self: 99.0)
    src = _src(tmp_path, [(MODEL_Q, "train"), (MODEL_Q + " again", "train")])
    with pytest.raises(bd.RefuseToRun):
        _run(tmp_path, src)
    assert teacher["teacher"] == 1
