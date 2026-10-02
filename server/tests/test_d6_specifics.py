"""D6 bench: specifics present and answer length (owner, 2026-10-02).

make bench scores both arms' served answers against benchmark run 3's specifics
list, by run 3's method (docs/MULTI_MODEL_BENCHMARK_2026-09-25.md): a specific is
present if its term or one of its match_terms appears verbatim, case-insensitive,
on word boundaries. The headline compares the arms on the same scenarios: the
model-reaching scenarios both arms served that have specifics. The report also
gives each arm's mean served-answer length in tokens, by the base tokenizer.

bench_remote.sh copies the list into the bench dir (specifics.json), so the
report needs nothing from the Jetson but that dir.
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

SPEC = {
    "A": {"specifics": [{"term": "tourniquet", "match_terms": ["TQ"]},
                        {"term": "TXA", "match_terms": ["tranexamic acid"]}]},
    "B": {"specifics": [{"term": "needle decompression", "match_terms": []},
                        {"term": "chest tube", "match_terms": []}]},
    "C": {"specifics": [{"term": "escharotomy", "match_terms": []}]},
    "D": {"specifics": [{"term": "CPR", "match_terms": []}]},
    "E": {"specifics": []},
}

# (scenario, outcome, model-reaching, response)
BASE = [("A", "SERVE", True, "Apply a tourniquet high and tight."),
        ("B", "SERVE", True, "Needle decompression now; then a chest tube."),
        ("C", "BLOCK", True, "Clinical safety hold."),
        ("D", "SERVE", False, "START CPR."),
        ("E", "SERVE", True, "one two three")]
TAG = [("A", "SERVE", True, "Apply a TQ, give tranexamic acid. Not a TQs."),
       ("B", "SERVE", True, "needle decompression"),
       ("C", "SERVE", True, "Escharotomy."),
       ("D", "SERVE", False, "START CPR."),
       ("E", "SERVE", True, "one two three four five")]


def _rows(arm):
    res = [{"request_id": f"{s}#r1", "scenario_id": s, "outcome": o, "response": t,
            "server_processing_ms": 1000} for s, o, m, t in arm]
    inst = [{"request_id": f"{s}#r1", "generator_calls": 1 if m else 0, "generation_ms": 900}
            for s, o, m, t in arm]
    return res, inst


def _bench(tmp_path, with_spec=True):
    b = tmp_path / "bench"
    b.mkdir()
    (b / "meta.json").write_text(json.dumps({
        "commit": "c45b210", "signed": 68, "entries": 108, "ollama": "0.34.2", "power": "25W",
        "kernel": "6.8", "tag": "edgecdss-v1", "base": "qwen2.5:3b", "tag_id": "t", "base_id": "b",
        "scenarios_src": "s", "scenarios_sha256": "0" * 64, "bank_port": 8123, "rt_port": 8012,
        "started": "2026-10-01T18:05:46+00:00"}))
    (b / "tokps.jsonl").write_text("")
    for lab, arm in (("base", BASE), ("tag", TAG)):
        res, inst = _rows(arm)
        (b / f"{lab}.results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in res))
        (b / f"{lab}.instrument.jsonl").write_text("".join(json.dumps(r) + "\n" for r in inst))
    rt = "RESULTS: 28 passed / 29 total\n"
    (b / "run_tests.tag.txt").write_text(rt)
    (b / "run_tests.base.txt").write_text(rt)
    if with_spec:
        (b / "specifics.json").write_text(json.dumps(SPEC))
    return b


def _words(text):
    """A stand-in for the base tokenizer: one token per whitespace-separated word."""
    return len(text.split())


def test_a_specific_is_present_by_term_or_match_term_on_word_boundaries():
    assert d6.specifics_present(SPEC["A"], "Apply a TQ, give tranexamic acid.") == (2, 2)
    assert d6.specifics_present(SPEC["A"], "TQs and TXAs") == (0, 2)        # not on a word boundary
    assert d6.specifics_present(SPEC["A"], "TOURNIQUET") == (1, 2)          # case-insensitive
    assert d6.specifics_present(SPEC["E"], "anything") is None              # no specifics: not scored
    assert d6.specifics_present(None, "anything") is None


def test_same_scenarios_are_model_reaching_and_served_by_both_arms(tmp_path):
    b = _bench(tmp_path)
    s = d6.answer_stats(d6.arm(b, "base"), d6.arm(b, "tag"), SPEC, _words)
    # C is held in the base, D never reaches a model, E has no specifics: only A and B.
    assert s["same_scenarios"] == ["A", "B"]
    assert (s["base"]["same_hit"], s["base"]["same_of"]) == (3, 4)
    assert (s["tag"]["same_hit"], s["tag"]["same_of"]) == (3, 4)
    # Each arm's own served answers with specifics, as in run 3's per-arm column.
    assert (s["base"]["all_hit"], s["base"]["all_of"], s["base"]["all_n"]) == (4, 5, 3)
    assert (s["tag"]["all_hit"], s["tag"]["all_of"], s["tag"]["all_n"]) == (5, 6, 4)


def test_mean_answer_length_is_over_served_model_answers(tmp_path):
    b = _bench(tmp_path)
    s = d6.answer_stats(d6.arm(b, "base"), d6.arm(b, "tag"), SPEC, _words)
    # base: A 6, B 7, E 3 (C held, D deterministic); tag: A 9, B 2, C 1, E 5
    assert s["base"]["len_n"] == 3 and s["base"]["len_mean"] == pytest.approx(16 / 3)
    assert s["tag"]["len_n"] == 4 and s["tag"]["len_mean"] == pytest.approx(17 / 4)


def test_the_report_writes_specifics_and_length(tmp_path):
    tokenizers = pytest.importorskip("tokenizers")
    from tokenizers import models, pre_tokenizers
    tok = tokenizers.Tokenizer(models.WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    tok_file = tmp_path / "tokenizer.json"
    tok.save(str(tok_file))
    b = _bench(tmp_path)
    out = tmp_path / "DISTILL_BENCH_test.md"
    d6.cmd_report(argparse.Namespace(bench=str(b), out=str(out), stages=None, note=None, rt_base=None,
                                     specifics=None, tokenizer=str(tok_file)))
    doc = out.read_text()
    assert "## Specifics present and answer length" in doc
    assert "| before: `qwen2.5:3b` | 3 / 4 (75%) | 4 / 5 (3 scenarios) | 5.3 (n=3) |" in doc
    assert "| after: `edgecdss-v1` | 3 / 4 (75%) | 5 / 6 (4 scenarios) | 4.2 (n=4) |" in doc
    assert "A, B" in doc


def test_the_report_refuses_without_a_specifics_list(tmp_path):
    b = _bench(tmp_path, with_spec=False)
    with pytest.raises(SystemExit):
        d6.cmd_report(argparse.Namespace(bench=str(b), out=str(tmp_path / "x.md"), stages=None, note=None,
                                         rt_base=None, specifics=None, tokenizer="unused"))


def test_an_explicit_specifics_list_scores_an_older_bench_dir(tmp_path):
    b = _bench(tmp_path, with_spec=False)
    spec_file = tmp_path / "specifics_final.json"
    spec_file.write_text(json.dumps(SPEC))
    assert d6.load_specifics(b, str(spec_file)) == SPEC


def test_the_bench_carries_the_specifics_list_and_the_tokenizer():
    sh = (DISTILL / "jetson/bench_remote.sh").read_text()
    assert "specifics_final.json" in sh and '"$W/specifics.json"' in sh
    mk = (DISTILL / "Makefile").read_text()
    assert "--tokenizer" in mk
