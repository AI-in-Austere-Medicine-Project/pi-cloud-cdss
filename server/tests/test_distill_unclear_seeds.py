"""D5b follow-up (owner, 2026-10-01): unclear seeds are never paraphrased.

A seed that fails the junk rule (no route, drug, vital or vocabulary word, and
not released by the owner) goes to review itself and generates nothing. The
case that prompted it: "90 kg male tenio", which the teacher paraphrased as
"90 kg male, tension pneumo", a different situation.
"""
import importlib.util
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bd = _load("build_distill_dataset", REPO / "tools/build_distill_dataset.py")
aug = _load("augment_seeds", REPO / "tools/augment_seeds.py")

TENIO = "90 kg male tenio"
CLEAR = "stonefish sting, foot is agonising, what now"
NONE = bd.ReviewRulings(set(), set())


def _exam():
    return bd.ExamSet(texts=bd.run_tests_queries((REPO / "server/run_tests.sh").read_text()), ids=set())


def _seed_file(tmp_path, rows):
    p = tmp_path / "scenarios.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_tenio_is_an_unclear_seed_by_the_rule_alone():
    assert bd.clinical_signals(TENIO) == []
    assert bd.seed_is_clear(TENIO, NONE) is False
    assert bd.seed_is_clear(CLEAR, NONE) is True


def test_the_owner_rulings_decide_over_the_rule():
    assert bd.seed_is_clear(TENIO, bd.ReviewRulings(release={bd.qhash(TENIO)}, hold=set())) is True
    assert bd.seed_is_clear(CLEAR, bd.ReviewRulings(release=set(), hold={bd.qhash(CLEAR)})) is False


def test_an_unclear_seed_generates_nothing(tmp_path):
    p = _seed_file(tmp_path, [{"id": "H-SESS-017", "query": TENIO}, {"id": "K1", "query": CLEAR}])
    todo = aug.seeds_to_augment(p, _exam(), done=set(), rulings=NONE)
    assert [s["seed_id"] for s in todo] == ["K1"]


def test_split_unclear_reports_the_unclear_seeds():
    seeds = [{"seed_id": "H-SESS-017", "query": TENIO}, {"seed_id": "K1", "query": CLEAR}]
    clear, unclear = bd.split_unclear(seeds, NONE)
    assert [s["seed_id"] for s in clear] == ["K1"]
    assert [s["seed_id"] for s in unclear] == ["H-SESS-017"]


def test_paraphrases_already_written_for_an_unclear_seed_are_not_replayed(tmp_path):
    p = tmp_path / "paraphrases.jsonl"
    recs = (aug.records({"seed_id": "H-SESS-017", "query": TENIO},
                        ["90 kg male, tension pneumo — what do I do?", "b two", "c three", "d four",
                         "e five"], model_returned=None)
            + aug.records({"seed_id": "K1", "query": CLEAR},
                          ["stonefish sting on the foot", "stepped on a stonefish", "x y", "z w",
                           "v u"], model_returned=None))
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    items, counts = bd.load_paraphrases(p, _exam(), bd.EvalExclusion.load(REPO),
                                        bd.JunkDrop.load(REPO), unclear={"H-SESS-017"})
    assert all(i["seed_id"] == "K1" for i in items)
    assert counts["unclear_seed"] == 5


def test_the_unclear_seed_itself_goes_to_review():
    rows = [{"meta": {"query": TENIO}}]
    kept, review = bd.partition_junk(rows, NONE)
    assert kept == [] and review == rows
