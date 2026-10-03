"""D6 v2 (owner, 2026-10-03): one change to the dataset, answer length.

tools/build_distill_dataset.py gains two modes:

  --shorten-from SRC  On the tree the rows were built on (d0b44f4 for v1): every
                      row whose answer is over 320 tokens is re-run once through
                      the teacher, with one instruction added to the teacher's
                      generator call only. The new answer takes the same replay
                      and filters. Still over 320, or excluded, means dropped and
                      counted. Every other row is copied unchanged. Each row keeps
                      its original split. Written to --out, never over SRC.
  --recheck DIR       On today's tree, no model call: every row is checked by
                      today's deterministic checks and unasked-drug filter; a row
                      that holds is dropped and reported ("the dataset must pass
                      today's checks, whatever snapshot generated it").

Offline: no teacher, validator or ChromaDB call. A one-token-per-word counter
stands in for the base tokenizer.
"""
import importlib.util
import json
import pathlib

import pytest

import openai_client as oc

REPO = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build_distill_dataset", REPO / "tools/build_distill_dataset.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)

words = lambda text: len(text.split())
SNAP = "d0b44f406a4e75703aaa3dee993a6b9fbfb1d456"


def _pair(sid, answer, split="train", query="80kg male, burn, what do I do", snap=SNAP):
    row = {"messages": [{"role": "system", "content": "the live system prompt"},
                        {"role": "user", "content": f"Clinical query: {query}"},
                        {"role": "assistant", "content": answer}]}
    meta = {"scenario_id": sid, "query": query, "source": "production", "split": split,
            "snapshot_commit": snap}
    return row, meta


# ── the rule ─────────────────────────────────────────────────────────────────
def test_the_instruction_and_the_limit_are_the_owners():
    assert bd.SHORTEN_INSTRUCTION == ("answer in under 300 tokens; keep every signed dose "
                                      "and every specific; drop narrative")
    assert bd.SHORTEN_LIMIT == 320


def test_only_answers_over_320_tokens_are_re_run():
    short, at, over = (_pair("a", "w " * 100), _pair("b", "w " * 320), _pair("c", "w " * 321))
    keep, rerun = bd.shorten_targets([short, at, over], words)
    assert [m["scenario_id"] for _r, m in keep] == ["a", "b"]
    assert [m["scenario_id"] for _r, m in rerun] == ["c"]


@pytest.mark.parametrize("why,tokens,outcome", [
    (None, 300, "shortened"),
    (None, 320, "shortened"),
    (None, 321, "still_over"),          # one retry only: dropped and counted
    ("held", 100, "held"),              # a filter excluded it: dropped, reported by reason
    ("unasked_drug", 100, "unasked_drug"),
])
def test_rerun_outcome(why, tokens, outcome):
    assert bd.rerun_outcome(why, tokens) == outcome


# ── the instruction reaches the teacher, never the stored row ────────────────
class _Providers:
    def __init__(self):
        self.sent = []

    def validator_model(self):
        return "gpt-4o-mini"

    def chat(self, system, messages, *, model, **kw):
        self.sent.append((model, json.loads(json.dumps(messages))))
        return "SHORT ANSWER"


def test_the_instruction_goes_on_the_generator_call_only_and_the_row_keeps_the_original():
    p = _Providers()
    cap = bd.Capture(oc, p, stub=False, instruction=bd.SHORTEN_INSTRUCTION)
    original = [{"role": "user", "content": "Clinical query: burn 70kg"}]
    out = cap.chat("the live system prompt", original, model=bd.TEACHER)
    assert out == "SHORT ANSWER"
    sent = p.sent[0][1]
    assert sent[-1]["content"].startswith("Clinical query: burn 70kg")
    assert sent[-1]["content"].endswith(bd.SHORTEN_INSTRUCTION)
    # what the training row is built from: the original prompt
    assert cap.gen["messages"] == original
    assert bd.to_row(cap.gen["system"], cap.gen["messages"], out)["messages"][1]["content"] == \
        "Clinical query: burn 70kg"
    # the validator sees the original question too
    cap.chat("validator prompt", [{"role": "user", "content": "x"}], model="gpt-4o-mini")
    assert bd.SHORTEN_INSTRUCTION not in json.dumps(p.sent[1][1])


def test_without_an_instruction_the_teacher_call_is_unchanged():
    p = _Providers()
    cap = bd.Capture(oc, p, stub=False)
    cap.chat("s", [{"role": "user", "content": "q"}], model=bd.TEACHER)
    assert p.sent[0][1] == [{"role": "user", "content": "q"}]


# ── same scenarios, same split, never over the source ────────────────────────
def test_each_row_keeps_its_original_split():
    rows = [_pair("a", "x", "valid"), _pair("b", "y", "train"), _pair("c", "z", "valid")]
    train, valid = bd.by_original_split(rows)
    assert [m["scenario_id"] for _r, m in train] == ["b"]
    assert [m["scenario_id"] for _r, m in valid] == ["a", "c"]
    assert all(m["split"] == "valid" for _r, m in valid)


def test_the_re_run_refuses_a_tree_that_is_not_the_rows_snapshot():
    pairs = [_pair("a", "x")]
    bd.check_shorten_snapshot(pairs, SNAP)
    with pytest.raises(bd.RefuseToRun):
        bd.check_shorten_snapshot(pairs, "510dc56" + "0" * 33)


def test_the_output_is_never_the_source(tmp_path):
    with pytest.raises(bd.RefuseToRun):
        bd.check_out_dir(tmp_path, tmp_path)
    bd.check_out_dir(tmp_path / "v1", tmp_path / "v2")


@pytest.mark.parametrize("ceiling,approved,ok", [(14.94, 15, True), (15.01, 15, False), (3.0, None, False)])
def test_the_re_run_needs_an_approved_ceiling(ceiling, approved, ok):
    if ok:
        bd.check_approved(ceiling, approved)
    else:
        with pytest.raises(bd.RefuseToRun):
            bd.check_approved(ceiling, approved)


# ── the recheck: today's checks, no model call ───────────────────────────────
def test_the_recheck_drops_a_row_todays_check_holds_and_keeps_a_clean_one():
    txa = _pair("t", "**DO THIS**\n- If 1 g already given and <3 hours from injury: give 1 g more, not 2 g.\n",
                query="hx: DVT + thrombosis. TXA still ok in his case?")
    clean = _pair("c", "**DO THIS**\n1. Cool the burn with clean water.\n2. Cover with a dry dressing.\n")
    passed, dropped = bd.recheck([txa, clean])
    assert [m["scenario_id"] for _r, m in passed] == ["c"]
    assert [(sid, why) for sid, why, _i in dropped] == [("t", "deterministic_check")]


def test_the_recheck_applies_the_unasked_drug_filter_too():
    row = _pair("u", "**DO THIS**\n1. Cool the burn.\n2. Consider ketamine for the dressing change.\n")
    passed, dropped = bd.recheck([row])
    assert not passed and dropped[0][1] == "unasked_drug"


def test_the_recheck_calls_no_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a model was called")
    monkeypatch.setattr(oc.providers, "chat", boom)
    bd.recheck([_pair("c", "**DO THIS**\n1. Cool the burn with clean water.\n")])


def test_the_new_flags_exist():
    flags = {a.dest for a in bd.parser()._actions}
    assert {"shorten_from", "recheck", "tokenizer", "env"} <= flags
