"""D5b: the junk rule, the seeds, the paraphrases (owner, #113 review).

Offline: no teacher call. Seed and paraphrase files are written to tmp_path;
the exam set comes from run_tests.sh (always in the repo) plus what a test
adds, so nothing depends on the cdss-eval bank being on this machine.
"""
import importlib.util
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bd = _load("build_distill_dataset", REPO / "tools/build_distill_dataset.py")
aug = _load("augment_seeds", REPO / "tools/augment_seeds.py")

ABUSIVE = "Your mother's a whore trabek"
GIT = ("You're on feature/local-llm in the live checkout. Move the work to a worktree "
       "(../pi-cloud-cdss-local-llm) and put the live checkout back on main so restarts "
       "never load unreviewed code.")
PIP = (".4->tokenizers>=0.13.2->chromadb>=0.5.0->-r requirements-server.txt (line 18)) (3.31.0)\n"
       "Requirement already satisfied: fsspec>=2023.5.0 in ./.venv/lib/python3.12/site-packages "
       "(from huggingface-hub<2.0,>=0.16.4->tokenizers>=0.13.2->chromadb>=0.5.0->-r "
       "requirements-server.txt (line 18)) (2026.6.0)\n"
       "Requirement already satisfied: uvloop>=0.15.1 in ./.venv/lib/python3.12/site-packages "
       "(from uvicorn[standard]>=0.30.0->-r requirements-server.txt (line 4)) (0.22.1)\n\n"
       "[notice] A new release of pip is available: 26.1.2 -> 26.2.1\n\n"
       "\"version\":\"4.3.0\"\n\nandrew@edgecdss:~/pi-cloud-cdss$")
# The eight junk rows of the first D5 run (#113). The pip paste above is an
# excerpt; the full paste is pinned by hash only.
EIGHT_SHORT = ["yesy", "test", "How do I pronounce my mother law?", ABUSIVE, "That", "Istg", GIT]


# ── 1. the junk rule ────────────────────────────────────────────────────────
@pytest.mark.parametrize("q", [ABUSIVE, PIP, GIT])
def test_junk_has_no_clinical_signal(q):
    assert bd.clinical_signals(q) == []


@pytest.mark.parametrize("q,signal", [
    ("COPD patient after several nebs, SpO2 84%, RR 32, getting tired", "vital"),
    ("patient took a bottle of his wife's metoprolol", "drug"),
])
def test_an_unrouted_clinical_question_passes(q, signal):
    assert bd.scenario_type(bd._oc(), q) == "unrouted"
    assert signal in bd.clinical_signals(q)


def test_a_routed_question_passes_on_routing_alone():
    assert "routed" in bd.clinical_signals("burn patient 40% TBSA, how much fluid")


def test_rows_failing_all_three_go_to_review_not_train():
    rows = [{"meta": {"query": ABUSIVE}}, {"meta": {"query": "patient took his wife's metoprolol"}}]
    kept, review = bd.partition_junk(rows)
    assert [r["meta"]["query"] for r in kept] == ["patient took his wife's metoprolol"]
    assert [r["meta"]["query"] for r in review] == [ABUSIVE]
    assert review[0]["meta"]["clinical_signals"] == []


def test_the_eight_are_dropped_by_hash(tmp_path):
    pin = json.loads((REPO / "tools/distill/junk_exclusions.json").read_text())
    assert len(pin["query_sha256"]) == 8
    junk = bd.JunkDrop.load(REPO)
    for q in EIGHT_SHORT:
        assert junk.drops(q), q
    log = tmp_path / "cdss_session_2026-09-01.jsonl"
    log.write_text("".join(json.dumps({"query": q, "history_turns": 0}) + "\n"
                           for q in EIGHT_SHORT + ["burn patient 40% TBSA fluids"]))
    src, counts = bd.load_source_queries(tmp_path, bd.EvalExclusion.load(REPO), junk)
    assert [s["query"] for s in src] == ["burn patient 40% TBSA fluids"]
    assert counts["junk_dropped"] == 7
    assert src[0]["source"] == "production" and src[0]["synthetic"] is False


# ── 2. seeds ────────────────────────────────────────────────────────────────
def _exam():
    return bd.ExamSet(texts=bd.run_tests_queries((REPO / "server/run_tests.sh").read_text()),
                      ids={"H-S7"})


@pytest.mark.parametrize("a,b,near", [
    ("patient having active seizure", "patient having active seizure", True),
    ("patint having an activ seizur", "patient having active seizure", True),
    ("septik patient fever and pus hypotensive should i give txa",
     "septic patient with fever and pus give TXA", True),                 # 0.47 in the bank
    ("wat r the vent setings for a 70 kg male with blast lung",
     "ventilator settings for 75 kg male in dka ph 7.1", False),         # 0.51 in the bank
    ("burn patient 40% TBSA fluids", "patient having active seizure", False),
])
def test_near_is_normalised_edit_distance_at_most_half(a, b, near):
    assert bd.ExamSet(texts={b}, ids=set()).near(a) is near


def _seed_file(tmp_path, rows):
    p = tmp_path / "scenarios.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_seeds_exclude_the_exam_history_near_misses_production_and_junk(tmp_path):
    p = _seed_file(tmp_path, [
        {"id": "H-S7", "query": "a question only the 30-set id marks"},       # 30-set id
        {"id": "X1", "query": "patient having active seizure"},               # exam text
        {"id": "X2", "query": "patint having an activ seizur"},               # near exam
        {"id": "X3", "query": "second turn", "history": [{"query": "a", "response": "b"}]},
        {"id": "X4", "query": "Burn patient 40% TBSA fluids."},               # = production
        {"id": "X5", "query": "yesy"},                                         # junk hash
        {"id": "K1", "query": "stonefish sting, foot is agonising, what now"},
        {"id": "K2", "query": "stonefish sting foot is agonising what now"},   # dup of K1
    ])
    seeds, counts = bd.load_seeds(p, _exam(), bd.EvalExclusion.load(REPO), bd.JunkDrop.load(REPO),
                                  production=[{"query": "burn patient 40% TBSA fluids"}])
    assert [s["seed_id"] for s in seeds] == ["K1"]
    s = seeds[0]
    assert s["scenario_id"] == "seed:K1" and s["source"] == "seed" and s["synthetic"] is True
    assert counts == {"exam_30_set": 1, "exam_text": 1, "exam_near": 1, "had_history": 1,
                      "duplicates_production": 1, "junk_dropped": 1, "duplicate": 1}


def test_exam_set_refuses_a_changed_30_set(tmp_path):
    p = tmp_path / "scenarios-30.jsonl"
    p.write_text('{"id": "Z", "query": "q"}\n')
    with pytest.raises(bd.RefuseToRun):
        bd.ExamSet.load(REPO, p)


# ── 3. augmentation ─────────────────────────────────────────────────────────
def test_exam_seeds_are_never_paraphrased_by_construction(tmp_path):
    p = _seed_file(tmp_path, [{"id": "X1", "query": "patient having active seizure"},
                              {"id": "X2", "query": "patint having an activ seizur"},
                              {"id": "K1", "query": "stonefish sting, foot is agonising"}])
    todo = aug.seeds_to_augment(p, _exam(), done=set())
    assert [s["seed_id"] for s in todo] == ["K1"]


def test_augment_skips_seeds_already_done(tmp_path):
    p = _seed_file(tmp_path, [{"id": "K1", "query": "stonefish sting"},
                              {"id": "K2", "query": "lionfish sting"}])
    assert [s["seed_id"] for s in aug.seeds_to_augment(p, _exam(), done={"K1"})] == ["K2"]


def test_the_prompt_is_fixed_and_asks_for_five_with_the_situation_unchanged():
    assert aug.N_PARAPHRASES == 5
    for words in ("wording", "weight", "vital", "same situation", "JSON"):
        assert words.lower() in aug.PROMPT.lower()
    assert len(aug.prompt_sha256()) == 64


@pytest.mark.parametrize("raw,ok", [
    ('{"paraphrases": ["a b", "c d", "e f", "g h", "i j"]}', True),
    ('```json\n{"paraphrases": ["a b", "c d", "e f", "g h", "i j"]}\n```', True),
    ('{"paraphrases": ["a b", "c d", "e f", "g h"]}', False),               # four
    ('{"paraphrases": ["a b", "a b", "e f", "g h", "i j"]}', False),        # duplicate
    ('{"paraphrases": ["a b", "", "e f", "g h", "i j"]}', False),           # empty
    ("here you go: a b; c d", False),
])
def test_parse_paraphrases(raw, ok):
    if ok:
        assert aug.parse_paraphrases(raw) == ["a b", "c d", "e f", "g h", "i j"]
    else:
        with pytest.raises(ValueError):
            aug.parse_paraphrases(raw)


def test_paraphrase_records_carry_source_seed_id_and_synthetic():
    seed = {"seed_id": "K1", "query": "stonefish sting", "source": "seed"}
    recs = aug.records(seed, ["a", "b", "c", "d", "e"], model_returned="claude-opus-5-x")
    assert len(recs) == 5
    r = recs[0]
    assert r["seed_id"] == "K1" and r["synthetic"] is True and r["teacher"] == bd.TEACHER
    assert r["source"] == "cdss-eval/scenarios.jsonl" and r["prompt_sha256"] == aug.prompt_sha256()
    assert r["paraphrase_id"] == "K1/p1"


# ── 4. paraphrases go through the same path as production rows ─────────────
def test_paraphrases_share_the_seed_scenario_and_near_exam_ones_are_dropped(tmp_path):
    p = tmp_path / "paraphrases.jsonl"
    recs = aug.records({"seed_id": "K1", "query": "stonefish sting"},
                       ["stonefish sting on the foot", "patient having active seizure",
                        "stepped on a stonefish", "patint having an activ seizur", "yesy"],
                       model_returned=None)
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))
    items, counts = bd.load_paraphrases(p, _exam(), bd.EvalExclusion.load(REPO), bd.JunkDrop.load(REPO))
    assert [i["query"] for i in items] == ["stonefish sting on the foot", "stepped on a stonefish"]
    assert all(i["scenario_id"] == "seed:K1" and i["source"] == "paraphrase"
               and i["synthetic"] is True for i in items)
    assert counts == {"exam_text": 1, "exam_near": 1, "junk_dropped": 1}


def test_a_seed_and_its_paraphrases_never_straddle_the_split():
    rows = [{"scenario_id": f"seed:S{i}"} for i in range(30) for _ in range(6)]
    rows += [{"scenario_id": f"p{i}"} for i in range(20)]
    train, valid = bd.split(rows)
    assert not {r["scenario_id"] for r in train} & {r["scenario_id"] for r in valid}


# ── 5. the $60 ceiling ──────────────────────────────────────────────────────
def test_the_owner_ceiling_for_this_run_is_60():
    bd.check_budget(59.0, approved=60.0)
    with pytest.raises(bd.RefuseToRun):
        bd.check_budget(61.0, approved=60.0)
