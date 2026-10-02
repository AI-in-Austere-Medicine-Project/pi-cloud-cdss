"""D6 bench bar (owner, 2026-10-01): run_tests.sh against the new tag must equal
the base arm's score on the same snapshot. The fixed 27/27 went stale when D1
added two cases (28/29 today; 29/29 once B1 lands).

bench_remote.sh runs run_tests.sh against both arms (run_tests.base.txt,
run_tests.tag.txt); d6.py report compares them. A bench dir from before this
change has no base file: --rt-base N/M states it, and the doc says so.
"""
import argparse
import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DISTILL = REPO / "tools/distill"
spec = importlib.util.spec_from_file_location("d6", DISTILL / "d6.py")
d6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d6)


@pytest.fixture(autouse=True)
def _words_for_tokens(monkeypatch):
    # The answer length needs a tokenizer; the bar doesn't. One token per word.
    monkeypatch.setattr(d6, "token_counter", lambda path: lambda text: len(text.split()))


def _rt(passed, total):
    return f"...\n================================================\nRESULTS: {passed} passed / {total} total\n"


def _bench(tmp_path, tag_rt, base_rt=None, legacy=False):
    b = tmp_path / "bench"
    b.mkdir()
    (b / "meta.json").write_text(json.dumps({
        "commit": "c45b210", "signed": 68, "entries": 108, "ollama": "0.34.2", "power": "25W",
        "kernel": "6.8", "tag": "edgecdss-v1", "base": "qwen2.5:3b", "tag_id": "t", "base_id": "b",
        "scenarios_src": "s", "scenarios_sha256": "0" * 64, "bank_port": 8123, "rt_port": 8012,
        "started": "2026-10-01T18:05:46+00:00"}))
    (b / "tokps.jsonl").write_text("")
    for lab in ("base", "tag"):
        (b / f"{lab}.results.jsonl").write_text(json.dumps(
            {"request_id": "X#r1", "scenario_id": "X", "outcome": "SERVE", "response": "answer",
             "server_processing_ms": 1000}) + "\n")
        (b / f"{lab}.instrument.jsonl").write_text(json.dumps(
            {"request_id": "X#r1", "generator_calls": 1, "generation_ms": 900}) + "\n")
    (b / "specifics.json").write_text(json.dumps({"X": {"specifics": [{"term": "answer"}]}}))
    (b / ("run_tests.txt" if legacy else "run_tests.tag.txt")).write_text(_rt(*tag_rt))
    if base_rt:
        (b / "run_tests.base.txt").write_text(_rt(*base_rt))
    return b


def _report(b, tmp_path, rt_base=None):
    out = tmp_path / "DISTILL_BENCH_test.md"
    d6.cmd_report(argparse.Namespace(bench=str(b), out=str(out), stages=None, note=None, rt_base=rt_base,
                                     specifics=None, tokenizer="unused"))
    return out.read_text()


def test_equal_to_the_base_arm_holds(tmp_path):
    doc = _report(_bench(tmp_path, (28, 29), (28, 29)), tmp_path)
    assert "**28 / 29**" in doc and "base arm `qwen2.5:3b`: 28 / 29 (measured)" in doc
    assert "**holds**" in doc


@pytest.mark.parametrize("tag,base", [((27, 29), (28, 29)),   # below the base arm
                                      ((28, 29), (28, 28)),   # different suite
                                      ((29, 29), (28, 29))])  # not equal: the bar is equality
def test_anything_but_equal_fails_after_writing_the_doc(tmp_path, tag, base):
    b = _bench(tmp_path, tag, base)
    with pytest.raises(SystemExit):
        _report(b, tmp_path)
    assert "**FAILS**" in (tmp_path / "DISTILL_BENCH_test.md").read_text()


def test_no_base_score_cannot_be_judged(tmp_path):
    with pytest.raises(SystemExit):
        _report(_bench(tmp_path, (28, 29)), tmp_path)


def test_a_stated_base_score_is_used_and_labelled(tmp_path):
    doc = _report(_bench(tmp_path, (28, 29), legacy=True), tmp_path, rt_base="28/29")
    assert "28 / 29 (stated, not measured)" in doc and "**holds**" in doc


def test_a_measured_base_score_wins_over_a_stated_one(tmp_path):
    doc = _report(_bench(tmp_path, (28, 29), (28, 29)), tmp_path, rt_base="29/29")
    assert "(measured)" in doc and "**holds**" in doc


def test_the_fixed_27_is_gone():
    mk = (DISTILL / "Makefile").read_text()
    assert "RT_EXPECT" not in mk and "--rt-expect" not in mk
    assert "27/27" not in (DISTILL / "README.md").read_text()
    assert "rt_expect" not in (DISTILL / "d6.py").read_text()


def test_the_bench_runs_run_tests_against_both_arms():
    sh = (DISTILL / "jetson/bench_remote.sh").read_text()
    assert "run_tests.base.txt" in sh.replace("$label", "base") or 'run_rt base "$BASE"' in sh
    assert 'run_rt base "$BASE"' in sh and 'run_rt tag "$TAG"' in sh
