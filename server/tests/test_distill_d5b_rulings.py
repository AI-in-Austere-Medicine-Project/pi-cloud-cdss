"""D5b rulings (owner, #114 review): the release and hold lists, the fourth
junk signal (a committed clinical vocabulary), and the no-model rebuild.

Offline. The rebuild test writes its own train/valid/review files to tmp_path.
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
vocab_tool = _load("build_clinical_vocabulary", REPO / "tools/distill/build_clinical_vocabulary.py")

VOCAB = json.loads((REPO / "tools/distill/clinical_vocabulary.json").read_text())

JUNK = [
    "Your mother's a whore trabek",
    "You're on feature/local-llm in the live checkout. Move the work to a worktree "
    "(../pi-cloud-cdss-local-llm) and put the live checkout back on main so restarts "
    "never load unreviewed code.",
    "Requirement already satisfied: fsspec>=2023.5.0 in ./.venv/lib/python3.12/site-packages "
    "(from huggingface-hub<2.0) [notice] A new release of pip is available",
    "yesy", "test", "That", "Istg", "what is the weather in Austin today", "tell me a joke",
    "who won the game last night", "how do I fix my car",
]
# The four fragment groups the owner kept out (#114 review), as their seeds read.
FRAGMENTS = ["150lbs", "90 kg male tenio", "he is a normal weight for a 7 year old",
             "Do I give ami for this now?"]


# ── the fourth signal ───────────────────────────────────────────────────────
def test_the_vocabulary_is_generated_and_sourced():
    assert "build_clinical_vocabulary.py" in VOCAB["_note"]
    src = VOCAB["sources"]
    assert src["corpus_pdfs"] > 0 and src["router_terms"] > 0 and src["heading_terms"] > 0
    assert len(VOCAB["terms"]) > 500


def test_generic_words_are_not_in_the_vocabulary():
    terms = set(VOCAB["terms"])
    assert not terms & vocab_tool.GENERIC
    assert not terms & vocab_tool.STOPWORDS
    for w in ("mother", "weight", "code", "release", "weather", "software", "body", "test", "give"):
        assert w not in terms, w


@pytest.mark.parametrize("q", JUNK + FRAGMENTS)
def test_junk_and_fragments_have_no_signal_of_any_kind(q):
    assert bd.clinical_signals(q) == []


@pytest.mark.parametrize("q", [
    "criteria for terminating resuscitation in the field",   # procedure / end of care
    "breech delivery, baby coming feet first",               # obstetrics
    "how do I work out the parkland formula",                # formula
    "when should I burp a chest seal",                       # anatomy / device
    "need to RSI",                                            # the router's slang table
    "burn patient 40% TBSA, how much fluid",                 # D5b's pinned miss, now caught
])
def test_unrouted_clinical_questions_pass_on_the_vocabulary(q):
    sig = bd.clinical_signals(q)
    assert "vocabulary" in sig, sig


def test_router_slang_counts():
    terms = set(VOCAB["terms"])
    assert {"rsi", "cric"} <= terms


# ── release and hold, by hash ───────────────────────────────────────────────
def test_rulings_file_has_hashes_only():
    r = json.loads((REPO / "tools/distill/review_rulings.json").read_text())
    assert r["release_sha256"] and r["hold_sha256"]
    assert not set(r["release_sha256"]) & set(r["hold_sha256"])
    assert all(len(h) == 64 for h in r["release_sha256"] + r["hold_sha256"])


def test_a_released_row_is_kept_without_a_signal_and_a_held_row_stays_in_review():
    rulings = bd.ReviewRulings(release={bd.qhash("yesy")}, hold={bd.qhash("need to RSI")})
    rows = [{"meta": {"query": "yesy"}}, {"meta": {"query": "need to RSI"}},
            {"meta": {"query": "tell me a joke"}}]
    kept, review = bd.partition_junk(rows, rulings)
    assert [r["meta"]["query"] for r in kept] == ["yesy"]
    assert kept[0]["meta"]["ruling"] == "release"
    assert [r["meta"]["query"] for r in review] == ["need to RSI", "tell me a joke"]
    assert review[0]["meta"]["ruling"] == "hold" and review[1]["meta"]["ruling"] is None


def test_the_hold_list_covers_the_four_fragment_seeds():
    hold = bd.ReviewRulings.load(REPO).hold
    for q in FRAGMENTS:
        assert bd.qhash(q) in hold, q


# ── the rebuild: no model call, same split rule, refuse still applies ──────
SYS = "SYSTEM"
SAFE = "BRIEF: needle decompression\nWATCH: SpO2"


def _write(out, name, pairs):
    with open(out / f"{name}.jsonl", "w") as f, open(out / f"{name}.meta.jsonl", "w") as g:
        for row, meta in pairs:
            f.write(json.dumps(row) + "\n")
            g.write(json.dumps(meta) + "\n")


def _pair(q, sid, source="production", answer=SAFE):
    row = bd.to_row(SYS, [{"role": "user", "content": f"Clinical query: {q}"}], answer)
    return row, {"query": q, "scenario_id": sid, "source": source, "synthetic": source != "production",
                 "scenario_type": "unrouted", "snapshot_commit": "abc"}


def _setup(tmp_path, review_answer=SAFE):
    out = tmp_path / "distill"
    out.mkdir()
    _write(out, "train", [_pair("tension pneumo on the left, 80 kg", "p1")])
    _write(out, "valid", [_pair("patient took his wife's metoprolol", "p2")])
    with open(out / "review.jsonl", "w") as f:
        for q, sid in (("yesy", "p3"), ("150lbs", "seed:H-SESS-001"), ("tell me a joke", "p4")):
            row, meta = _pair(q, sid, answer=review_answer)
            f.write(json.dumps({**row, "meta": meta}) + "\n")
    (out / "manifest.json").write_text(json.dumps({"outcomes": {}}))
    return out


def test_rebuild_moves_released_rows_in_and_leaves_held_and_unreleased_in_review(tmp_path):
    out = _setup(tmp_path)
    rulings = bd.ReviewRulings(release={bd.qhash("yesy")}, hold={bd.qhash("150lbs")})
    summary = bd.rebuild(out, rulings, snapshot_commit="abc")
    metas = [json.loads(l) for n in ("train", "valid") for l in open(out / f"{n}.meta.jsonl")]
    assert sorted(m["query"] for m in metas) == sorted(
        ["tension pneumo on the left, 80 kg", "patient took his wife's metoprolol", "yesy"])
    review = [json.loads(l)["meta"]["query"] for l in open(out / "review.jsonl")]
    assert sorted(review) == ["150lbs", "tell me a joke"]
    assert summary["kept"] == 3 and summary["review"] == 2
    # same split rule: by scenario, deterministic
    t = {m["scenario_id"] for m in metas if m["split"] == "train"}
    v = {m["scenario_id"] for m in metas if m["split"] == "valid"}
    assert not t & v and len(v) == 1


def test_rebuild_refuses_a_snapshot_it_did_not_build(tmp_path):
    out = _setup(tmp_path)
    with pytest.raises(bd.RefuseToRun):
        bd.rebuild(out, bd.ReviewRulings(set(), set()), snapshot_commit="def")


def test_rebuild_refuses_an_unsigned_dose_and_writes_nothing(tmp_path):
    out = _setup(tmp_path, review_answer="GIVE: ketamine 400 mg IV for induction")
    before = {p.name: p.read_text() for p in out.iterdir()}
    with pytest.raises(bd.RefuseToRun):
        bd.rebuild(out, bd.ReviewRulings(release={bd.qhash("yesy")}, hold=set()), snapshot_commit="abc")
    assert {p.name: p.read_text() for p in out.iterdir()} == before
