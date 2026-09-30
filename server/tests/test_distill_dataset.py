"""D5: the distillation dataset builder (tools/build_distill_dataset.py).

Offline: no teacher call, no validator call, no ChromaDB. The builder's
filters, the evaluation-set exclusion, the split, the format and the
refuse-to-run check are pure functions of what the pipeline returned; these
tests drive them with the live checks (openai_client) and hand-made results.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib

import pytest

import openai_client as oc
import providers

REPO = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tools/distill/fixtures/format_example.jsonl"
SCENARIOS_30 = pathlib.Path(
    "/home/andrew/projects/cdss-eval/runs/run-tests-mm3-20260925/scenarios-30.jsonl")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bd = _load("build_distill_dataset", REPO / "tools/build_distill_dataset.py")
d6 = _load("d6", REPO / "tools/distill/d6.py")


# ── the teacher ─────────────────────────────────────────────────────────────
def test_teacher_is_the_run3_opus_arm_and_cannot_be_substituted():
    assert bd.TEACHER == "claude-opus-5"
    assert providers.MODELS[bd.TEACHER].provider == "anthropic"
    assert bd.TEACHER_TIMEOUT_S == 120
    flags = {a.dest for a in bd.parser()._actions}
    assert not any("teacher" in f or f == "model" for f in flags)


# ── (b) is out: the evaluation set never reaches train or valid ─────────────
def test_run_tests_parser_reads_every_case_current_and_history():
    text = (REPO / "server/run_tests.sh").read_text()
    cases = bd.parse_run_tests(text)
    assert len(cases) == text.count('\nrun_test "')
    queries = bd.run_tests_queries(text)
    assert "80 kg adult, severe pain from a femur fracture, fentanyl IV" in queries
    # history turns count too: this one only appears inside a history array
    assert "need ketamine for a 6yo arm fx" in queries


def test_the_30_set_is_pinned_by_hash():
    pin = json.loads((REPO / "tools/distill/eval_exclusions.json").read_text())
    assert pin["scenarios_30_sha256"].startswith("76c2bed932b7d2ae")
    assert pin["scenario_ids"] == 30
    assert len(pin["query_sha256"]) >= 30
    # text is never committed: the repo is public
    assert all(len(h) == 64 for h in pin["query_sha256"])


@pytest.mark.skipif(not SCENARIOS_30.exists(), reason="cdss-eval bank not on this machine")
def test_the_pin_covers_every_query_in_the_30_set():
    raw = SCENARIOS_30.read_bytes()
    pin = json.loads((REPO / "tools/distill/eval_exclusions.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == pin["scenarios_30_sha256"]
    ex = bd.EvalExclusion.load(REPO)
    for line in raw.decode().splitlines():
        s = json.loads(line)
        assert ex.excludes(s["query"]), s["id"]
        for h in s.get("history") or []:
            if isinstance(h, dict) and h.get("query"):
                assert ex.excludes(h["query"]), s["id"]


def test_an_eval_query_in_the_logs_is_excluded_in_any_spelling():
    ex = bd.EvalExclusion.load(REPO)
    assert ex.excludes("80 kg adult, severe pain from a femur fracture, fentanyl IV")
    assert ex.excludes("80kg adult severe pain from a femur fracture fentanyl iv")
    assert ex.excludes("  80 KG ADULT, severe pain from a femur fracture — fentanyl IV. ")
    assert not ex.excludes("80 kg adult, severe pain from a tibia fracture, fentanyl IV")


def test_excluded_queries_are_never_sent_to_the_teacher(tmp_path):
    log = tmp_path / "cdss_session_2026-09-01.jsonl"
    rows = [{"query": "patient having active seizure", "history_turns": 0},
            {"query": "burn patient 30% TBSA 70kg fluids", "history_turns": 0}]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    src, counts = bd.load_source_queries(tmp_path, bd.EvalExclusion.load(REPO))
    assert [s["query"] for s in src] == ["burn patient 30% TBSA 70kg fluids"]
    assert counts["evaluation_set"] == 1


# ── single patient, no history; production only ────────────────────────────
def test_source_is_single_turn_production_queries_deduplicated(tmp_path):
    log = tmp_path / "cdss_session_2026-09-01.jsonl"
    rows = [
        {"query": "tension pneumo on the left, 80kg", "history_turns": 0},
        {"query": "Tension pneumo on the left, 80 kg.", "history_turns": 0},  # same scenario
        {"query": "and now he is hypotensive", "history_turns": 3},           # had history
        {"query": "harness row", "history_turns": 0, "synthetic": True},      # X-Test-Run
        {"query": "", "history_turns": 0},
    ]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n")
    src, counts = bd.load_source_queries(tmp_path, bd.EvalExclusion.load(REPO))
    assert [s["query"] for s in src] == ["tension pneumo on the left, 80kg"]
    assert src[0]["occurrences"] == 2
    assert counts["had_history"] == 1 and counts["synthetic"] == 1


# ── what is kept ────────────────────────────────────────────────────────────
RAW = "BRIEF: tension pneumothorax\nGIVE: needle decompression, 5th ICS AAL\nWATCH: SpO2\nDON'T: delay"


def _result(**kw):
    r = {"response": RAW, "held_response": None, "fallbacks": [], "validator_result": "SAFE",
         "generation_truncated": None, "source_mode": "JTS_GROUNDED"}
    r.update(kw)
    return r


def _gen(raw=RAW):
    return {"system": "sys", "messages": [{"role": "user", "content": "Clinical query: q"}],
            "response": raw}


@pytest.mark.parametrize("result,gen,reason", [
    (_result(source_mode="DETERMINISTIC"), None, "deterministic"),
    (_result(fallbacks=[{"role": "generator", "requested": "claude-opus-5"}]), _gen(), "fallback"),
    (_result(fallbacks=[{"role": "validator", "requested": "gpt-4o-mini"}]), _gen(), "fallback"),
    (_result(validator_result="UNSAFE", held_response=RAW, response="HOLD"), _gen(), "held"),
    (_result(held_response=RAW), _gen(), "held"),
    (_result(generation_truncated=True), _gen(), "truncated"),
    (_result(response="⚠️ volume removed\n" + RAW.replace("5th", "4th")), _gen(), "changed_by_pipeline"),
    (_result(), _gen(), None),
    (_result(response="⚠️ reset notice\n\n" + RAW), _gen(), None),  # Python added, removed nothing
    (_result(validator_result="NEEDS_HUMAN_REVIEW"), _gen(), None),  # served
])
def test_exclusion_reason(result, gen, reason):
    assert bd.exclusion_reason(result, gen) == reason


def test_the_assistant_turn_is_the_teachers_own_text_not_the_served_wrapper():
    row = bd.to_row(_gen()["system"], _gen()["messages"], RAW)
    assert row["messages"][-1] == {"role": "assistant", "content": RAW}


# ── unasked drugs (owner, 2026-09-29; the D1 air-gap B1 answers) ───────────
B1 = "80 kg adult, severe pain from a femur fracture, fentanyl IV"


def test_unasked_drug_without_a_signed_entry_is_found():
    ans = ("GIVE: fentanyl 50 mcg IV\nWATCH: respiratory depression; naloxone 0.4 mg if RR < 8\n"
           "Alternative: ketamine 0.3 mg/kg")
    assert bd.unasked_drugs(B1, ans, signed={"fentanyl"}) == {"naloxone", "ketamine"}


def test_asked_or_signed_drugs_are_not_unasked():
    assert bd.unasked_drugs(B1, "GIVE: fentanyl 50 mcg IV", signed={"fentanyl"}) == set()
    # signed for this question though not named in it
    assert bd.unasked_drugs("RSI an 80kg male", "ketamine then rocuronium",
                            signed={"ketamine", "rocuronium"}) == set()
    # a synonym in the answer is the same drug
    assert bd.unasked_drugs("give TXA for bleeding", "tranexamic acid 2 g IV",
                            signed=set()) == set()


# ── refuse to run: a dose that is not the signed value ──────────────────────
def _ctx_and_doses(q):
    ctx = oc.extract_patient_context(q)
    return ctx, oc.build_allowed_doses(q, ctx)


def test_refuse_to_run_on_an_unsigned_dose():
    q = "80kg male RSI ketamine rocuronium"
    ctx, doses = _ctx_and_doses(q)
    assert doses, "the RSI contract should build doses for an 80 kg adult"
    bad = "GIVE: ketamine 400 mg IV for induction, then rocuronium 80 mg IV"
    rows = [{"check": (q, ctx, doses), "assistant": bad, "scenario_id": "s1"}]
    with pytest.raises(bd.RefuseToRun):
        bd.refuse_unsigned_doses(rows)


def test_a_signed_dose_passes_the_refuse_check():
    q = "80kg male RSI ketamine rocuronium"
    ctx, doses = _ctx_and_doses(q)
    rows = [{"check": (q, ctx, doses), "assistant": "BRIEF: RSI\nWATCH: SpO2", "scenario_id": "s1"}]
    bd.refuse_unsigned_doses(rows)  # no raise


# ── split and format ────────────────────────────────────────────────────────
def test_split_is_90_10_by_scenario_and_no_scenario_is_in_both():
    ids = [f"s{i}" for i in range(57)]
    rows = [{"scenario_id": s} for s in ids] + [{"scenario_id": "s3"}]  # a scenario with 2 rows
    train, valid = bd.split(rows)
    t, v = {r["scenario_id"] for r in train}, {r["scenario_id"] for r in valid}
    assert not t & v and t | v == set(ids)
    assert len(v) == round(0.1 * len(ids))
    assert bd.split(rows) == (train, valid)  # deterministic


def test_split_keeps_one_valid_scenario_when_there_are_few():
    train, valid = bd.split([{"scenario_id": "a"}, {"scenario_id": "b"}, {"scenario_id": "c"}])
    assert len(valid) == 1 and len(train) == 2


def test_written_files_pass_the_d6_preflight_format_check(tmp_path, capsys):
    row = bd.to_row("SYSTEM PROMPT", [{"role": "user", "content": "Clinical query: q"}], RAW)
    meta = {"scenario_id": "s1", "teacher": "claude-opus-5"}
    bd.write_split(tmp_path, [(row, meta)] * 3, [(row, meta)])
    d6.cmd_format(argparse.Namespace(fixture=str(FIXTURE), data=str(tmp_path)))
    assert "every row matches" in capsys.readouterr().out
    # metadata sits beside the rows, line for line, so the rows keep the fixture's shape
    metas = [json.loads(l) for l in (tmp_path / "train.meta.jsonl").read_text().splitlines()]
    assert len(metas) == 3 and metas[0]["teacher"] == "claude-opus-5"


def test_the_row_is_the_live_prompt_verbatim():
    msgs = [{"role": "user", "content": "Clinical query: burn 70kg"}]
    row = bd.to_row("the live system prompt", msgs, RAW)
    assert row == {"messages": [{"role": "system", "content": "the live system prompt"},
                                {"role": "user", "content": "Clinical query: burn 70kg"},
                                {"role": "assistant", "content": RAW}]}


def test_a_multi_turn_prompt_is_refused_by_construction():
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
            {"role": "user", "content": "Clinical query: c"}]
    with pytest.raises(bd.RefuseToRun):
        bd.to_row("sys", msgs, RAW)


# ── cost ────────────────────────────────────────────────────────────────────
def test_over_40_dollars_stops_for_approval():
    with pytest.raises(bd.RefuseToRun):
        bd.check_budget(40.01, approved=None)
    with pytest.raises(bd.RefuseToRun):
        bd.check_budget(55.0, approved=50.0)
    bd.check_budget(39.99, approved=None)
    bd.check_budget(55.0, approved=60.0)
