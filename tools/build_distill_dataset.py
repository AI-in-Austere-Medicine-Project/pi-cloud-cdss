#!/usr/bin/env python3
"""D5: build the distillation dataset from teacher answers.

  python3 tools/build_distill_dataset.py --plan     select, count and cost; no teacher call
  python3 tools/build_distill_dataset.py            the run (stops over $40 unless approved)
  python3 tools/build_distill_dataset.py --shorten-from SRC --out DIR --tokenizer T --approve-cost N
                                                     D6 v2: re-run long answers once, shorter
  python3 tools/build_distill_dataset.py --recheck DIR  today's checks over DIR; no model call

Source (owner, 2026-09-26, option a): the stored production queries that are
single patient, no history and model-reaching on this snapshot, each replayed
through the live pipeline (`_query_with_rag_internal`, the function the server
calls) with `claude-opus-5` as the generator, the deployed gpt-4o-mini
validator and the deployed checks. The prompt in each row is the one the live
code handed to providers.chat, captured at the call, not re-rendered.

Kept: served, not held; no fallback; the teacher's text reaches the medic
unaltered (Python may add a notice around it, never change it); no issue from
run_deterministic_checks, which applies A1b's indication matcher; no drug the
question didn't ask about that has no signed entry for it. Then the whole set
is checked again and the run refuses, writing nothing, if any row states a
dose that is not the signed value for its drug and indication.

Excluded before any call: the evaluation set, i.e. every query in run_tests.sh
(current turn and history) and in the 30-scenario bank, pinned by hash in
tools/distill/eval_exclusions.json because this repository is public.

Output (untracked): data/distill/{train,valid}.jsonl, messages triples in the
shape of tools/distill/fixtures/format_example.jsonl, split 90/10 by scenario.
Each row's metadata (teacher, snapshot commit, contract bank version, ...) is
on the same line of {train,valid}.meta.jsonl: a key on the row itself would
fail the D6 preflight, which compares the row's keys with the fixture's.

D5b (owner, #113 review):
- Junk rule: a kept row's question must route to a protocol, name a lexicon
  drug, or contain a parsed vital. A row with none of the three goes to
  data/distill/review.jsonl for the owner, not into train or valid. The eight
  junk queries of the first run are dropped at the source by hash
  (tools/distill/junk_exclusions.json).
- Seeds: cdss-eval/scenarios/scenarios.jsonl, minus the 30-set, minus any
  seed whose normalised text is within edit distance NEAR_EXAM_RATIO of an
  exam query (the 30-set and run_tests.sh, current turn and history), minus
  seeds with history.
- Paraphrases: data/distill/seeds/paraphrases.jsonl, written by
  tools/augment_seeds.py. They share their seed's scenario id, so a seed and
  its paraphrases never straddle the split, and they are checked against the
  exam set again. Every paraphrase takes the same replay and filters as a
  production row. Metadata: source (production, seed, paraphrase) and
  synthetic (false only for production).
"""
import argparse
import collections
import contextlib
import copy
import datetime
import hashlib
import importlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
import unicodedata

REPO = pathlib.Path(__file__).resolve().parent.parent

# The teacher is the model run 3 measured (providers.json id, passed unchanged
# as `model` by the Anthropic adapter). Not a flag: it is never substituted.
TEACHER = "claude-opus-5"
TEACHER_TIMEOUT_S = 120
VALID_FRACTION = 0.1
BUDGET_USD = 40.0
COVERAGE_MIN = 20

# List rates, $ per 1M tokens (in, out): docs/MULTI_MODEL_BENCHMARK_2026-09-25.md.
RATES = {"claude-opus-5": (5.0, 25.0), "gpt-4o-mini": (0.15, 0.60)}
CHARS_PER_TOKEN = 4          # run 3's estimate for the validator share
TEACHER_OUT_EXPECTED = 698   # run 3, Opus at 120 s: output tokens per model turn
VALIDATOR_OUT = 200
VALIDATOR_ANSWER_CHARS = 2361  # D5a: p95 served answer, bytes

EVAL = pathlib.Path("/home/andrew/projects/cdss-eval")
SCENARIOS_30 = EVAL / "runs/run-tests-mm3-20260925/scenarios-30.jsonl"
SEEDS = EVAL / "scenarios/scenarios.jsonl"
# A seed within this normalised edit distance (distance / longer length) of an
# exam query is the exam question. Measured on the bank: the misspelled exam
# questions sit at 0.46-0.48 ("septik patient ... txa", "anafalaxis ..."), the
# nearest different situation at 0.51 (blast-lung vent vs DKA vent).
NEAR_EXAM_RATIO = 0.5


class RefuseToRun(Exception):
    pass


# ── D6 v2 (owner, 2026-10-03): one change to the dataset, answer length ─────
# Every row whose answer is over SHORTEN_LIMIT tokens (base tokenizer, answer
# only) is re-run once through the teacher, on the snapshot the rows were built
# on, with SHORTEN_INSTRUCTION added to the teacher's generator call only: the
# pipeline, the validator and the stored row keep the original question. The
# new answer takes the same replay and filters. Still over the limit after that
# one retry, or excluded by a filter: dropped and counted. Every other row is
# copied unchanged, and every row keeps its original split. Then --recheck runs
# today's checks over the result with no model call: "the dataset must pass
# today's checks, whatever snapshot generated it."
SHORTEN_INSTRUCTION = ("answer in under 300 tokens; keep every signed dose and every specific; "
                       "drop narrative")
SHORTEN_LIMIT = 320
SHORTEN_OUT_EXPECTED = 320


def answer_of(row: dict) -> str:
    return row["messages"][-1]["content"]


def shorten_targets(pairs: list, count):
    """(kept unchanged, to re-run): over SHORTEN_LIMIT answer tokens is re-run."""
    keep, rerun = [], []
    for row, meta in pairs:
        (rerun if count(answer_of(row)) > SHORTEN_LIMIT else keep).append((row, meta))
    return keep, rerun


def rerun_outcome(why, tokens: int) -> str:
    """'shortened' (kept), 'still_over' (dropped), or the filter that excluded it."""
    if why:
        return why
    return "shortened" if tokens <= SHORTEN_LIMIT else "still_over"


def by_original_split(pairs: list):
    """Same split as the source: each row keeps the split it had."""
    return ([p for p in pairs if p[1]["split"] == "train"],
            [p for p in pairs if p[1]["split"] == "valid"])


def check_shorten_snapshot(pairs: list, commit: str):
    built = {m.get("snapshot_commit") for _r, m in pairs}
    if built != {commit}:
        raise RefuseToRun(f"the rows were built on {sorted(built)}, this tree is {commit}: "
                          "re-run them on the tree they were built on, so length is the only change")


def check_out_dir(src, out):
    if pathlib.Path(src).resolve() == pathlib.Path(out).resolve():
        raise RefuseToRun("--out is the source: the source dataset is never written over")


def check_approved(ceiling: float, approved):
    if approved is None or ceiling > approved:
        raise RefuseToRun(f"the ceiling estimate is ${ceiling:.2f}; the approved ceiling is "
                          f"{'not given' if approved is None else f'${approved:.2f}'}: stop for the owner")


def recheck(pairs: list):
    """Today's deterministic checks and unasked-drug filter over every row, each
    row's patient context and signed doses rebuilt by the pipeline; no model
    call. ([(row, meta)] passed, [(scenario_id, reason, issues)] dropped)."""
    oc = _oc()
    check = getattr(oc, "_distill_real_rdc", oc.run_deterministic_checks)
    passed, dropped = [], []
    for row, meta in pairs:
        q, answer = meta["query"], answer_of(row)
        ctx = oc.rebuild_patient_context_from_history(q)
        doses = oc.build_allowed_doses(q, ctx)
        issues = check(q, answer, ctx, doses).issues
        if issues:
            dropped.append((meta["scenario_id"], "deterministic_check", issues))
            continue
        extra = unasked_drugs(q, answer, {d.drug for d in oc.indication_matched(q, doses)})
        if extra:
            dropped.append((meta["scenario_id"], "unasked_drug", sorted(extra)))
            continue
        passed.append((row, meta))
    return passed, dropped


# ── the evaluation set: (b) is out ──────────────────────────────────────────
def normalize(q: str) -> str:
    """Case, punctuation, spacing and "80kg"/"80 kg" folded; words kept."""
    q = unicodedata.normalize("NFKC", q or "").casefold()
    q = re.sub(r"(?<=\d)(?=[^\W\d_])|(?<=[^\W\d_])(?=\d)", " ", q)
    return " ".join(re.sub(r"[\W_]+", " ", q).split())


def qhash(q: str) -> str:
    return hashlib.sha256(normalize(q).encode()).hexdigest()


def parse_run_tests(text: str) -> list:
    """[(name, query, history)] for every `run_test "..."` line."""
    cases = []
    for line in text.splitlines():
        if not line.startswith('run_test "'):
            continue
        args = shlex.split(line, comments=True)
        hist = json.loads(args[3]) if len(args) > 3 and args[3].strip() else []
        cases.append((args[1], args[2], hist))
    return cases


def run_tests_queries(text: str) -> set:
    out = set()
    for _name, query, hist in parse_run_tests(text):
        out.add(query)
        out.update(h["query"] for h in hist if isinstance(h, dict) and h.get("query"))
    return out


class EvalExclusion:
    """Every query in run_tests.sh and in the 30-set, current turn and history."""

    def __init__(self, hashes: set):
        self.hashes = hashes

    @classmethod
    def load(cls, repo: pathlib.Path = REPO) -> "EvalExclusion":
        pin = json.loads((repo / "tools/distill/eval_exclusions.json").read_text())
        rt = run_tests_queries((repo / "server/run_tests.sh").read_text())
        if not rt or not pin.get("query_sha256"):
            raise RefuseToRun("the evaluation set could not be read; nothing is excluded without it")
        return cls(set(pin["query_sha256"]) | {qhash(q) for q in rt})

    def excludes(self, q: str) -> bool:
        return qhash(q) in self.hashes


def _bag_distance(a: str, b: str) -> int:
    """A lower bound on the edit distance, from character counts alone."""
    ca, cb = collections.Counter(a), collections.Counter(b)
    return max(sum((ca - cb).values()), sum((cb - ca).values()))


def edit_distance_within(a: str, b: str, k: int) -> bool:
    """Levenshtein(a, b) <= k."""
    if abs(len(a) - len(b)) > k or _bag_distance(a, b) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > k:
            return False
        prev = cur
    return prev[-1] <= k


class ExamSet:
    """The exam's text, for the edit-distance check: the 30-set and run_tests.sh."""

    def __init__(self, texts, ids):
        self.norms = {normalize(t) for t in texts if normalize(t)}
        self.ids = set(ids)

    @classmethod
    def load(cls, repo: pathlib.Path = REPO, scenarios_30: pathlib.Path = SCENARIOS_30) -> "ExamSet":
        pin = json.loads((repo / "tools/distill/eval_exclusions.json").read_text())
        try:
            raw = pathlib.Path(scenarios_30).read_bytes()
        except OSError as e:
            raise RefuseToRun(f"the 30-set is needed for the edit-distance check: {e}")
        if hashlib.sha256(raw).hexdigest() != pin["scenarios_30_sha256"]:
            raise RefuseToRun(f"{scenarios_30} is not the pinned 30-set")
        texts, ids = set(run_tests_queries((repo / "server/run_tests.sh").read_text())), set()
        for line in raw.decode().splitlines():
            s = json.loads(line)
            ids.add(s["id"])
            texts.add(s["query"])
            texts.update(h["query"] for h in s.get("history") or []
                         if isinstance(h, dict) and h.get("query"))
        return cls(texts, ids)

    def exact(self, q: str) -> bool:
        return normalize(q) in self.norms

    def near(self, q: str) -> bool:
        n = normalize(q)
        return any(edit_distance_within(n, e, int(NEAR_EXAM_RATIO * max(len(n), len(e))))
                   for e in self.norms)


class JunkDrop:
    """The first run's eight junk queries (owner, #113 review), by hash."""

    def __init__(self, hashes: set):
        self.hashes = hashes

    @classmethod
    def load(cls, repo: pathlib.Path = REPO) -> "JunkDrop":
        pin = json.loads((repo / "tools/distill/junk_exclusions.json").read_text())
        return cls(set(pin["query_sha256"]))

    def drops(self, q: str) -> bool:
        return qhash(q) in self.hashes


# ── the source: single-turn production queries ─────────────────────────────
def load_source_queries(log_dir, exclusion: EvalExclusion, junk: "JunkDrop | None" = None):
    """Distinct (by normalize) single-turn, non-synthetic queries, first spelling kept."""
    counts = collections.Counter()
    seen = {}
    for f in sorted(pathlib.Path(log_dir).glob("*.jsonl")):
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                counts["unreadable"] += 1
                continue
            q = (r.get("query") or "").strip()
            if not q:
                counts["empty"] += 1
            elif r.get("synthetic"):
                counts["synthetic"] += 1
            elif r.get("history_turns"):
                counts["had_history"] += 1
            elif exclusion.excludes(q):
                counts["evaluation_set"] += 1
            elif junk is not None and junk.drops(q):
                counts["junk_dropped"] += 1
            else:
                k = normalize(q)
                if k in seen:
                    seen[k]["occurrences"] += 1
                else:
                    seen[k] = {"query": q, "scenario_id": qhash(q)[:12],
                               "first_ts": r.get("ts"), "occurrences": 1,
                               "source": "production", "synthetic": False}
                continue
    return list(seen.values()), counts


def _exam_reason(q: str, exam: ExamSet, exclusion: EvalExclusion) -> "str | None":
    if exclusion.excludes(q) or exam.exact(q):
        return "exam_text"
    if exam.near(q):
        return "exam_near"
    return None


def load_seeds(path, exam: ExamSet, exclusion: EvalExclusion, junk: JunkDrop, production=()):
    """The cdss-eval bank minus the exam, its near misses, history, junk and repeats."""
    counts = collections.Counter()
    taken = {normalize(p["query"]) for p in production}
    seen, seeds = set(), []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        s = json.loads(line)
        q = (s.get("query") or "").strip()
        if s["id"] in exam.ids:
            counts["exam_30_set"] += 1
        elif s.get("history"):
            counts["had_history"] += 1
        elif _exam_reason(q, exam, exclusion):
            counts[_exam_reason(q, exam, exclusion)] += 1
        elif junk.drops(q):
            counts["junk_dropped"] += 1
        elif normalize(q) in taken:
            counts["duplicates_production"] += 1
        elif normalize(q) in seen:
            counts["duplicate"] += 1
        else:
            seen.add(normalize(q))
            seeds.append({"query": q, "seed_id": s["id"], "scenario_id": f"seed:{s['id']}",
                          "first_ts": None, "occurrences": 1,
                          "source": "seed", "synthetic": True})
    return seeds, dict(counts)


def load_paraphrases(path, exam: ExamSet, exclusion: EvalExclusion, junk: JunkDrop,
                     unclear=frozenset()):
    """augment_seeds.py's output, checked against the exam again; seed's scenario id.
    Paraphrases of an unclear seed (`unclear`, seed ids) are never replayed."""
    counts = collections.Counter()
    seen, items = set(), []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        q = (r.get("query") or "").strip()
        if r["seed_id"] in unclear:
            counts["unclear_seed"] += 1
            continue
        why = _exam_reason(q, exam, exclusion) or ("junk_dropped" if junk.drops(q) else None)
        if why is None and normalize(q) in seen:
            why = "duplicate"
        if why:
            counts[why] += 1
            continue
        seen.add(normalize(q))
        items.append({"query": q, "seed_id": r["seed_id"], "paraphrase_id": r["paraphrase_id"],
                      "scenario_id": f"seed:{r['seed_id']}", "first_ts": None, "occurrences": 1,
                      "source": "paraphrase", "synthetic": True})
    return items, dict(counts)


# ── what is kept ────────────────────────────────────────────────────────────
def exclusion_reason(result: dict, gen) -> "str | None":
    """Why this answer is not a training row, or None to keep it."""
    if gen is None:
        return "deterministic"
    if result.get("validator_result") == "ERROR":
        return "error"
    if result.get("fallbacks"):
        return "fallback"
    if result.get("validator_result") == "UNSAFE" or result.get("held_response"):
        return "held"
    if result.get("generation_truncated"):
        return "truncated"
    if gen["response"] not in (result.get("response") or ""):
        return "changed_by_pipeline"
    return None


def _oc():
    return importlib.import_module("openai_client")


def drugs_in(text: str) -> set:
    return {g for _s, _e, g in _oc()._drug_spans(text or "")}


def unasked_drugs(query: str, answer: str, signed) -> set:
    """Drugs the answer names that the question didn't ask for and nothing signed covers."""
    covered = drugs_in(query)
    for name in signed:
        covered |= drugs_in(name) or {name.lower()}
    return drugs_in(answer) - covered


_VOCABULARY = None


def vocabulary() -> frozenset:
    """tools/distill/clinical_vocabulary.json (build_clinical_vocabulary.py)."""
    global _VOCABULARY
    if _VOCABULARY is None:
        _VOCABULARY = frozenset(json.loads(
            (REPO / "tools/distill/clinical_vocabulary.json").read_text())["terms"])
    return _VOCABULARY


def vocabulary_words(query: str) -> set:
    v = vocabulary()
    return {w for w in normalize(query).split() if w in v or (w.endswith("s") and w[:-1] in v)}


def clinical_signals(query: str) -> list:
    """The owner's junk rule, read from the question: routed, drug, vital, and
    (#114 review) a word of the committed clinical vocabulary."""
    oc = _oc()
    readings, _rejected = importlib.import_module("vitals").parse_vitals(query or "")
    return [name for name, hit in (("routed", scenario_type(oc, query) != "unrouted"),
                                   ("drug", bool(drugs_in(query))),
                                   ("vital", bool(readings)),
                                   ("vocabulary", bool(vocabulary_words(query)))) if hit]


class ReviewRulings:
    """The owner's rulings on review rows, by query hash (tools/distill/review_rulings.json):
    a released row is kept without a signal; a held row stays in review with one."""

    def __init__(self, release: set, hold: set):
        self.release, self.hold = set(release), set(hold)

    @classmethod
    def load(cls, repo: pathlib.Path = REPO) -> "ReviewRulings":
        r = json.loads((repo / "tools/distill/review_rulings.json").read_text())
        return cls(set(r["release_sha256"]), set(r["hold_sha256"]))


def partition_junk(rows: list, rulings: "ReviewRulings | None" = None):
    """(kept, review): a row whose question has no signal is for the owner, unless released."""
    rulings = ReviewRulings.load(REPO) if rulings is None else rulings
    kept, review = [], []
    for r in rows:
        m = r["meta"]
        h = qhash(m["query"])
        m["clinical_signals"] = clinical_signals(m["query"])
        m["ruling"] = "hold" if h in rulings.hold else "release" if h in rulings.release else None
        keep = m["ruling"] == "release" or (m["ruling"] is None and bool(m["clinical_signals"]))
        (kept if keep else review).append(r)
    return kept, review


def seed_is_clear(query: str, rulings: ReviewRulings) -> bool:
    """Owner, 2026-10-01: a seed is paraphrased only if it passes the junk rule
    (or the owner released it), and never if the owner held it. An unclear
    seed's paraphrases drift: "90 kg male tenio" came back as "tension pneumo"."""
    h = qhash(query)
    if h in rulings.hold:
        return False
    return h in rulings.release or bool(clinical_signals(query))


def split_unclear(seeds: list, rulings: ReviewRulings):
    """(clear, unclear). An unclear seed is still a row (it goes to review
    itself through the junk rule); it generates nothing."""
    clear, unclear = [], []
    for s in seeds:
        (clear if seed_is_clear(s["query"], rulings) else unclear).append(s)
    return clear, unclear


def _read_pairs(out: pathlib.Path, name: str) -> list:
    rows = [json.loads(l) for l in open(out / f"{name}.jsonl", encoding="utf-8") if l.strip()]
    metas = [json.loads(l) for l in open(out / f"{name}.meta.jsonl", encoding="utf-8") if l.strip()]
    if len(rows) != len(metas):
        raise RefuseToRun(f"{name}.jsonl and {name}.meta.jsonl are not line for line")
    return list(zip(rows, metas))


def rebuild(out, rulings: ReviewRulings, snapshot_commit: str) -> dict:
    """Re-partition and re-split the rows already built, with no model call.

    Every row (train, valid and review) is checked again by the refuse-to-run
    check, its patient context and signed doses rebuilt by the pipeline's own
    functions. Then the junk rule with the rulings, then the same split rule.
    Nothing is written if anything refuses."""
    oc = _oc()
    out = pathlib.Path(out)
    pairs = _read_pairs(out, "train") + _read_pairs(out, "valid")
    for line in open(out / "review.jsonl", encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            pairs.append(({"messages": r["messages"]}, r["meta"]))
    items = []
    for row, meta in pairs:
        if meta.get("snapshot_commit") != snapshot_commit:
            raise RefuseToRun(f"a row was built on {meta.get('snapshot_commit')}, not {snapshot_commit}")
        meta = {k: v for k, v in meta.items() if k != "split"}
        q = meta["query"]
        ctx = oc.rebuild_patient_context_from_history(q)
        items.append({"scenario_id": meta["scenario_id"], "assistant": row["messages"][-1]["content"],
                      "check": (q, ctx, oc.build_allowed_doses(q, ctx)), "row": row, "meta": meta})
    refuse_unsigned_doses(items)
    kept, review = partition_junk(items, rulings)
    train, valid = split(kept)
    write_split(out, [(r["row"], {**r["meta"], "split": "train"}) for r in train],
                [(r["row"], {**r["meta"], "split": "valid"}) for r in valid])
    with open(out / "review.jsonl", "w", encoding="utf-8") as f:
        for r in review:
            f.write(json.dumps({**r["row"], "meta": r["meta"]}, ensure_ascii=False) + "\n")
    by_source = collections.defaultdict(collections.Counter)
    for name, rows in (("train", train), ("valid", valid), ("review", review)):
        for r in rows:
            by_source[r["meta"]["source"]][name] += 1
    released = sum(r["meta"]["ruling"] == "release" for r in kept)
    return {"kept": len(kept), "train": len(train), "valid": len(valid),
            "valid_scenarios": len({r["scenario_id"] for r in valid}), "review": len(review),
            "released": released,
            "held": sum(r["meta"]["ruling"] == "hold" for r in review),
            "kept_on_vocabulary_only": sum(r["meta"]["clinical_signals"] == ["vocabulary"]
                                           and r["meta"]["ruling"] is None for r in kept),
            "by_source": {s: dict(c) for s, c in by_source.items()},
            "scenario_types": dict(collections.Counter(r["meta"]["scenario_type"] for r in kept)),
            "scenario_types_by_source": {s: dict(collections.Counter(
                r["meta"]["scenario_type"] for r in kept if r["meta"]["source"] == s))
                for s in ("production", "seed", "paraphrase")}}


def refuse_unsigned_doses(rows: list):
    """The owner's refuse-to-run: any row with a dose that isn't the signed value."""
    oc = _oc()
    check = getattr(oc, "_distill_real_rdc", oc.run_deterministic_checks)
    bad = []
    for r in rows:
        q, ctx, doses, *current = r["check"]
        issues = check(q, r["assistant"], ctx, doses, *current).issues
        if issues:
            bad.append((r["scenario_id"], issues))
    if bad:
        raise RefuseToRun("rows state doses that are not signed for their drug and indication:\n"
                          + "\n".join(f"  {s}: {i}" for s, i in bad))


# ── format, split, write ───────────────────────────────────────────────────
def to_row(system: str, messages: list, assistant: str) -> dict:
    if len(messages) != 1 or messages[0].get("role") != "user":
        raise RefuseToRun("a training row is one turn, one patient: the prompt carried history")
    return {"messages": [{"role": "system", "content": system},
                         {"role": "user", "content": messages[0]["content"]},
                         {"role": "assistant", "content": assistant}]}


def split(rows: list):
    """90/10 by scenario id, never by row; the valid scenarios are chosen by hash."""
    ids = sorted({r["scenario_id"] for r in rows},
                 key=lambda s: hashlib.sha256(s.encode()).hexdigest())
    n_valid = max(1, round(VALID_FRACTION * len(ids))) if len(ids) > 1 else 0
    valid_ids = set(ids[:n_valid])
    return ([r for r in rows if r["scenario_id"] not in valid_ids],
            [r for r in rows if r["scenario_id"] in valid_ids])


def write_split(out_dir, train: list, valid: list):
    """[(row, meta)] each; rows and metadata line for line, written atomically."""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, pairs in (("train", train), ("valid", valid)):
        for suffix, idx in ((".jsonl", 0), (".meta.jsonl", 1)):
            path = out_dir / f"{name}{suffix}"
            fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=f".{name}")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for p in pairs:
                    f.write(json.dumps(p[idx], ensure_ascii=False) + "\n")
            os.replace(tmp, path)


def check_budget(estimate: float, approved):
    if estimate > BUDGET_USD and (approved is None or approved < estimate):
        raise RefuseToRun(f"the ceiling estimate is ${estimate:.2f}, over ${BUDGET_USD:.0f}: "
                          f"stop for the owner's approval (then --approve-cost {estimate:.0f})")


# ── the pipeline, once per query ────────────────────────────────────────────
class Capture:
    """Wraps providers.chat and run_deterministic_checks for one pipeline run."""

    def __init__(self, oc, providers, stub: bool, instruction: "str | None" = None):
        self.oc, self.providers, self.stub = oc, providers, stub
        self.instruction = instruction
        self.real_chat = providers.chat
        oc._distill_real_rdc = getattr(oc, "_distill_real_rdc", oc.run_deterministic_checks)
        self.real_rdc = oc._distill_real_rdc
        self.gen = self.check = self.validator_chars = None

    def chat(self, system, messages, *, model, **kw):
        is_validator = model == self.providers.validator_model() and self.gen is not None
        if is_validator:
            self.validator_chars = len(system or "") + sum(len(m.get("content") or "") for m in messages)
            if self.stub:
                return '{"result":"SAFE","issues":[],"rationale":"plan stub"}'
            return self.real_chat(system, messages, model=model, **kw)
        if model != TEACHER:
            raise RefuseToRun(f"the generator was called with {model!r}, not the teacher")
        sent = messages
        if self.instruction:
            # D6 v2: the instruction rides on the teacher's call only. The row
            # is built from the original messages, recorded below.
            sent = copy.deepcopy(messages)
            sent[-1]["content"] = f"{sent[-1]['content']}\n\n{self.instruction}"
        out = "PLAN STUB" if self.stub else self.real_chat(system, sent, model=model, **kw)
        self.gen = {"system": system, "messages": copy.deepcopy(messages), "response": out}
        return out

    def rdc(self, query, response_text, patient_ctx, allowed_doses=None, current_query=None):
        # current_query (A23): the pipeline passes it; the recorded check keeps
        # it, so the whole-set check repeats the pipeline's call exactly.
        if self.gen is not None and response_text == self.gen["response"] and self.check is None:
            self.check = (query, copy.deepcopy(patient_ctx), list(allowed_doses or []), current_query)
        return self.real_rdc(query, response_text, patient_ctx, allowed_doses, current_query=current_query)

    def run(self, query, chroma, log):
        self.gen = self.check = self.validator_chars = None
        self.providers.chat, self.oc.run_deterministic_checks = self.chat, self.rdc
        try:
            with contextlib.redirect_stdout(log):
                return self.oc._query_with_rag_internal(query, chroma, model=TEACHER)
        finally:
            self.providers.chat, self.oc.run_deterministic_checks = self.real_chat, self.real_rdc


def scenario_type(oc, query: str) -> str:
    try:
        r = oc._router.route(query, None, query)
        if r.matched_protocol and r.confidence in ("HIGH", "MEDIUM"):
            return r.matched_protocol
    except Exception:
        pass
    return "unrouted"


def snapshot(server: pathlib.Path) -> dict:
    git = lambda *a: subprocess.run(["git", "-C", str(server), *a], capture_output=True,
                                    text=True, check=True).stdout.strip()
    if git("status", "--porcelain", "--untracked-files=no"):
        raise RefuseToRun(f"{server} has uncommitted changes: the snapshot commit would not describe it")
    raw = (server / "drug_contracts.json").read_bytes()
    bank = json.loads(raw)
    entries = [e for d in bank.get("drugs", []) for e in d.get("dose_entries", [])]
    kit = server / "drug_concentrations.json"
    return {"commit": git("rev-parse", "HEAD"),
            "contract_bank": {"sha256": hashlib.sha256(raw).hexdigest(),
                              "schema_version": bank.get("schema_version"),
                              "signed": sum(e.get("signoff") is True for e in entries),
                              "entries": len(entries)},
            "concentrations_sha256": hashlib.sha256(kit.read_bytes()).hexdigest() if kit.exists() else None}


def estimate(plans: list) -> dict:
    t_in, t_out = RATES[TEACHER]
    v_in, v_out = RATES["gpt-4o-mini"]
    tin = sum(p["prompt_chars"] for p in plans) / CHARS_PER_TOKEN
    vin = sum((p["validator_chars"] or 0) + VALIDATOR_ANSWER_CHARS for p in plans) / CHARS_PER_TOKEN
    n = len(plans)
    ceiling_out = n * (700 + 3000)  # max_tokens + claude-opus-5 reserve_tokens
    val = vin * v_in / 1e6 + n * VALIDATOR_OUT * v_out / 1e6
    return {"calls": n, "teacher_in_tokens": round(tin),
            "expected_usd": round(tin * t_in / 1e6 + n * TEACHER_OUT_EXPECTED * t_out / 1e6 + val, 2),
            "ceiling_usd": round(tin * t_in / 1e6 + ceiling_out * t_out / 1e6 + val, 2)}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--server", default=str(REPO / "server"),
                   help="the deployed server tree the dataset is replayed through")
    p.add_argument("--logs", help="session log dir (default: CDSS_LOG_DIR from that tree's .env)")
    p.add_argument("--seeds", default=str(SEEDS), help="the cdss-eval bank the seeds come from")
    p.add_argument("--scenarios-30", default=str(SCENARIOS_30), help="the exam; must match the pin")
    p.add_argument("--out", default=str(REPO / "data/distill"))
    p.add_argument("--plan", action="store_true", help="select, count and cost; call no model")
    p.add_argument("--approve-cost", type=float, help="the owner's approved ceiling, in USD, over $40")
    p.add_argument("--shorten-from", help="D6 v2: the source dataset dir; rows over 320 answer "
                   "tokens are re-run once, shorter, on the tree they were built on (--server)")
    p.add_argument("--recheck", help="D6 v2: a dataset dir to check with today's checks (--server); "
                   "no model call")
    p.add_argument("--tokenizer", help="the base model's tokenizer.json, for answer length")
    p.add_argument("--env", help="a .env to read provider keys from, read only (the tree "
                   "--server names may have none); variables already set win")
    p.add_argument("--rebuild", action="store_true",
                   help="re-partition and re-split the rows in --out with the rulings; call no model")
    return p


def _augment_module():
    spec = importlib.util.spec_from_file_location("augment_seeds", REPO / "tools/augment_seeds.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_distill_dataset", sys.modules[__name__])
    spec.loader.exec_module(mod)
    return mod


def _by_source(items, key=lambda i: i["source"]) -> dict:
    return dict(collections.Counter(key(i) for i in items))


def main(argv=None):
    a = parser().parse_args(argv)
    server = pathlib.Path(a.server).resolve()
    snap = snapshot(server)
    scratch = tempfile.mkdtemp(prefix="d5-")
    # The builder never writes the production session log, and the teacher is
    # waited for as run 3 waited for it.
    os.environ["CDSS_LOG_DIR"] = scratch
    os.environ["FEEDBACK_LOG"] = os.path.join(scratch, "feedback.log")
    os.environ["CDSS_LLM_SELECTED_TIMEOUT"] = str(TEACHER_TIMEOUT_S)
    logs = a.logs
    if logs is None:
        from dotenv import dotenv_values
        logs = dotenv_values(server / ".env").get("CDSS_LOG_DIR") or str(server / "logs/sessions")
    out = pathlib.Path(a.out).resolve()
    # Resolved now: main() changes into the server tree below.
    for k in ("shorten_from", "recheck", "tokenizer", "env"):
        if getattr(a, k):
            setattr(a, k, str(pathlib.Path(getattr(a, k)).resolve()))
    if a.env:
        from dotenv import load_dotenv
        load_dotenv(a.env, override=False)
    exclusion, junk = EvalExclusion.load(REPO), JunkDrop.load(REPO)
    exam = ExamSet.load(REPO, pathlib.Path(a.scenarios_30))
    os.chdir(server)
    sys.path.insert(0, str(server))
    import openai_client as oc
    import providers
    from embeddings import ChromaDBClient
    if providers.generator_timeout_s(TEACHER) != TEACHER_TIMEOUT_S:
        raise RefuseToRun("the teacher would not be waited for 120 s")
    if a.recheck:
        return run_recheck(pathlib.Path(a.recheck).resolve(), snap)
    if a.shorten_from:
        return run_shorten(a, pathlib.Path(a.shorten_from).resolve(), out, snap, oc, providers,
                           ChromaDBClient, scratch)
    if a.rebuild:
        summary = rebuild(out, ReviewRulings.load(REPO), snap["commit"])
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        manifest["rebuild"] = {**summary, "built": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(f"rebuild (no model called): kept {summary['kept']} = train {summary['train']} + "
              f"valid {summary['valid']} ({summary['valid_scenarios']} scenarios); review {summary['review']}")
        print(f"  released by hash {summary['released']}, held by hash {summary['held']}, "
              f"kept on the vocabulary alone {summary['kept_on_vocabulary_only']}")
        print("counts by source:")
        for src in ("production", "seed", "paraphrase"):
            print(f"  {src:10s} {summary['by_source'].get(src, {})}")
        print("scenario types:")
        for t, n in collections.Counter(summary["scenario_types"]).most_common():
            print(f"  {n:4d}  {t}" + (f"   WARNING: fewer than {COVERAGE_MIN} rows" if n < COVERAGE_MIN else ""))
        return 0
    pipeline_log = open(os.path.join(scratch, "pipeline.log"), "w")
    chroma = ChromaDBClient()
    aug = _augment_module()

    production, src_counts = load_source_queries(logs, exclusion, junk)
    seeds, seed_counts = load_seeds(a.seeds, exam, exclusion, junk, production)
    clear_seeds, unclear_seeds = split_unclear(seeds, ReviewRulings.load(REPO))
    unclear_ids = {s["seed_id"] for s in unclear_seeds}
    para_path = out / "seeds/paraphrases.jsonl"
    paraphrases, para_counts = (load_paraphrases(para_path, exam, exclusion, junk, unclear_ids)
                                if para_path.exists() else ([], {}))
    augmented = {p["seed_id"] for p in paraphrases} | set(aug.done_seed_ids(para_path))
    to_augment = [s for s in clear_seeds if s["seed_id"] not in augmented]
    print(f"production: {logs}")
    print(f"  distinct single-turn production queries: {len(production)}  "
          f"(entries left out: {dict(src_counts)})")
    print(f"seeds: {a.seeds}")
    print(f"  seeds: {len(seeds)}  (left out: {seed_counts}); unclear, never paraphrased: "
          f"{len(unclear_seeds)} {sorted(unclear_ids)}")
    print(f"paraphrases: {len(paraphrases)} in {para_path}  (left out: {para_counts}); "
          f"seeds still to paraphrase: {len(to_augment)}")

    sources = production + seeds + paraphrases
    plan_cap = Capture(oc, providers, stub=True)
    plans, deterministic = [], []
    for s in sources:
        plan_cap.run(s["query"], chroma, pipeline_log)
        if plan_cap.gen is None:
            deterministic.append(s)
            continue
        g = plan_cap.gen
        plans.append({**s, "prompt_chars": len(g["system"]) + sum(len(m["content"]) for m in g["messages"]),
                      "validator_chars": plan_cap.validator_chars})
    # Paraphrases not written yet: every one is assumed to reach the teacher,
    # with the mean prompt of the rows planned above.
    n_proj = aug.N_PARAPHRASES * len(to_augment)
    mean = lambda k: sum(p[k] or 0 for p in plans) / max(1, len(plans))
    projected = [{"prompt_chars": mean("prompt_chars"), "validator_chars": mean("validator_chars")}] * n_proj
    replay = estimate(plans + projected)
    augment_est = aug.estimate(to_augment)
    total = {k: round(replay[k] + augment_est[k], 2) for k in ("expected_usd", "ceiling_usd")}
    print(f"  model-reaching on {snap['commit'][:7]}: {_by_source(plans)}  "
          f"(deterministic-only: {_by_source(deterministic)})")
    print(f"  teacher {TEACHER}, {TEACHER_TIMEOUT_S} s; validator {providers.validator_model()}")
    print(f"  cost, replay: {len(plans)} calls + {n_proj} projected paraphrase calls: "
          f"expected ${replay['expected_usd']:.2f}, ceiling ${replay['ceiling_usd']:.2f}")
    print(f"  cost, paraphrasing {len(to_augment)} seeds: expected ${augment_est['expected_usd']:.2f}, "
          f"ceiling ${augment_est['ceiling_usd']:.2f}")
    print(f"  cost, total: expected ${total['expected_usd']:.2f}, ceiling ${total['ceiling_usd']:.2f}")
    check_budget(total["ceiling_usd"], a.approve_cost)
    if a.plan:
        print("plan only: no model was called and nothing was written.")
        return 0
    if to_augment:
        raise RefuseToRun(f"{len(to_augment)} seeds have no paraphrases yet: run tools/augment_seeds.py first")

    cap = Capture(oc, providers, stub=False)
    kept, outcomes, unasked_seen = [], collections.Counter(), collections.Counter()
    for s in deterministic:
        outcomes[(s["source"], "deterministic")] += 1
    for i, s in enumerate(plans, 1):
        result = cap.run(s["query"], chroma, pipeline_log)
        why = exclusion_reason(result, cap.gen)
        if why is None and (cap.check is None
                            or cap.real_rdc(cap.check[0], cap.gen["response"], *cap.check[1:]).issues):
            why = "deterministic_check"
        if why is None:
            signed = {d.drug for d in oc.indication_matched(cap.check[0], cap.check[2])}
            extra = unasked_drugs(s["query"], cap.gen["response"], signed)
            if extra:
                why = "unasked_drug"
                unasked_seen.update(extra)
        outcomes[(s["source"], why or "passed")] += 1
        print(f"  [{i}/{len(plans)}] {s['source']:10s} {why or 'passed':20s} {s['query'][:60]!r}", flush=True)
        if why:
            continue
        kept.append({"scenario_id": s["scenario_id"], "assistant": cap.gen["response"],
                     "check": cap.check, "row": to_row(cap.gen["system"], cap.gen["messages"],
                                                       cap.gen["response"]),
                     "meta": {"scenario_id": s["scenario_id"],
                              "scenario_type": scenario_type(oc, s["query"]),
                              "query": s["query"], "source": s["source"], "synthetic": s["synthetic"],
                              "seed_id": s.get("seed_id"), "paraphrase_id": s.get("paraphrase_id"),
                              "occurrences": s["occurrences"],
                              "first_seen": s["first_ts"], "teacher": TEACHER,
                              "model_returned": result.get("model_returned"),
                              "validator_result": result.get("validator_result"),
                              "source_mode": result.get("source_mode"),
                              "snapshot_commit": snap["commit"],
                              "contract_bank": snap["contract_bank"],
                              "concentrations_sha256": snap["concentrations_sha256"],
                              "built": datetime.datetime.now(datetime.timezone.utc).isoformat()}})

    refuse_unsigned_doses(kept)
    kept, review = partition_junk(kept)
    for r in review:
        outcomes[(r["meta"]["source"], "passed")] -= 1
        outcomes[(r["meta"]["source"], "review")] += 1
    for r in kept:
        outcomes[(r["meta"]["source"], "passed")] -= 1
        outcomes[(r["meta"]["source"], "kept")] += 1
    train, valid = split(kept)
    write_split(out, [(r["row"], {**r["meta"], "split": "train"}) for r in train],
                [(r["row"], {**r["meta"], "split": "valid"}) for r in valid])
    with open(out / "review.jsonl", "w", encoding="utf-8") as f:
        for r in review:
            f.write(json.dumps({**r["row"], "meta": r["meta"]}, ensure_ascii=False) + "\n")

    print(f"\nkept {len(kept)}: train {len(train)}, valid {len(valid)} "
          f"({len({r['scenario_id'] for r in valid})} scenarios); review {len(review)}  -> {out}")
    table = collections.defaultdict(dict)
    for (src, what), n in outcomes.items():
        if n:
            table[src][what] = n
    print("counts by source:")
    for src in ("production", "seed", "paraphrase"):
        split_n = {sp: sum(r["meta"]["source"] == src for r in rows)
                   for sp, rows in (("train", train), ("valid", valid))}
        print(f"  {src:10s} {dict(table.get(src, {}))}  {split_n}")
    print(f"unasked drugs: {dict(unasked_seen)}")
    types = collections.Counter(r["meta"]["scenario_type"] for r in kept)
    print("scenario types (top 10):")
    for t, n in types.most_common(10):
        print(f"  {n:4d}  {t}" + (f"   WARNING: fewer than {COVERAGE_MIN} rows" if n < COVERAGE_MIN else ""))
    drugs = collections.Counter(d for r in kept for d in drugs_in(r["assistant"]))
    print("drugs named in the answers:")
    for d, n in drugs.most_common():
        print(f"  {n:4d}  {d}")
    manifest = {"snapshot": snap, "teacher": TEACHER, "teacher_timeout_s": TEACHER_TIMEOUT_S,
                "validator": providers.validator_model(), "estimate": {"replay": replay, "total": total},
                "production_entries_left_out": dict(src_counts), "seeds_left_out": seed_counts,
                "paraphrases_left_out": para_counts,
                "outcomes": {src: d for src, d in table.items()},
                "unasked_drugs": dict(unasked_seen), "train": len(train), "valid": len(valid),
                "review": len(review), "scenario_types": dict(types), "drugs": dict(drugs),
                "pipeline_log": pipeline_log.name}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return 0


def _token_counter(path):
    if not path:
        raise RefuseToRun("--tokenizer (the base model's tokenizer.json) is required")
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(path))
    return lambda text: len(tok.encode(text, add_special_tokens=False).ids)


def run_shorten(a, src, out, snap, oc, providers, ChromaDBClient, scratch) -> int:
    check_out_dir(src, out)
    count = _token_counter(a.tokenizer)
    pairs = _read_pairs(src, "train") + _read_pairs(src, "valid")
    check_shorten_snapshot(pairs, snap["commit"])
    if {m.get("concentrations_sha256") for _r, m in pairs} != {snap["concentrations_sha256"]}:
        raise RefuseToRun("this tree's drug_concentrations.json is not the one the rows were built with")
    keep, rerun = shorten_targets(pairs, count)
    print(f"source {src}: {len(pairs)} rows; {len(keep)} at or under {SHORTEN_LIMIT} answer tokens kept "
          f"unchanged; {len(rerun)} to re-run on {snap['commit'][:7]}")
    log = open(os.path.join(scratch, "pipeline.log"), "w")
    chroma = ChromaDBClient()
    plan_cap = Capture(oc, providers, stub=True, instruction=SHORTEN_INSTRUCTION)
    plans = []
    for _row, meta in rerun:
        plan_cap.run(meta["query"], chroma, log)
        if plan_cap.gen is None:
            raise RefuseToRun(f"{meta['scenario_id']} no longer reaches the teacher on this tree")
        g = plan_cap.gen
        plans.append({"prompt_chars": len(g["system"]) + sum(len(m["content"]) for m in g["messages"])
                      + len(SHORTEN_INSTRUCTION) + 2, "validator_chars": plan_cap.validator_chars})
    est = estimate(plans)
    t_out = RATES[TEACHER][1]
    est["expected_usd"] = round(est["expected_usd"] - len(plans) * (TEACHER_OUT_EXPECTED - SHORTEN_OUT_EXPECTED)
                                * t_out / 1e6, 2)
    print(f"cost: {est['calls']} teacher calls, ~{est['teacher_in_tokens']:,} input tokens: "
          f"expected ${est['expected_usd']:.2f}, ceiling ${est['ceiling_usd']:.2f}")
    check_approved(est["ceiling_usd"], a.approve_cost)
    if a.plan:
        print("plan only: no model was called and nothing was written.")
        return 0

    cap = Capture(oc, providers, stub=False, instruction=SHORTEN_INSTRUCTION)
    outcomes, new_pairs, report = collections.Counter(), [], []
    for i, (row, meta) in enumerate(rerun, 1):
        result = cap.run(meta["query"], chroma, log)
        why = exclusion_reason(result, cap.gen)
        if why is None and (cap.check is None
                            or cap.real_rdc(cap.check[0], cap.gen["response"], *cap.check[1:]).issues):
            why = "deterministic_check"
        if why is None:
            signed = {d.drug for d in oc.indication_matched(cap.check[0], cap.check[2])}
            if unasked_drugs(meta["query"], cap.gen["response"], signed):
                why = "unasked_drug"
        before = count(answer_of(row))
        after = count(cap.gen["response"]) if cap.gen else None
        outcome = rerun_outcome(why, after or 0)
        outcomes[outcome] += 1
        report.append({"scenario_id": meta["scenario_id"], "split": meta["split"], "outcome": outcome,
                       "tokens_before": before, "tokens_after": after})
        print(f"  [{i}/{len(rerun)}] {meta['split']:5s} {before:4d} -> {after if after is not None else '-':>4} "
              f"{outcome:20s} {meta['query'][:50]!r}", flush=True)
        if outcome != "shortened":
            continue
        new_pairs.append((to_row(cap.gen["system"], cap.gen["messages"], cap.gen["response"]),
                          {**meta, "model_returned": result.get("model_returned"),
                           "validator_result": result.get("validator_result"),
                           "source_mode": result.get("source_mode"),
                           "v2": {"rerun": True, "instruction": SHORTEN_INSTRUCTION,
                                  "answer_tokens_before": before, "answer_tokens_after": after,
                                  "built": datetime.datetime.now(datetime.timezone.utc).isoformat()}}))
        refuse_unsigned_doses([{"scenario_id": meta["scenario_id"], "assistant": cap.gen["response"],
                                "check": cap.check}])
    train, valid = by_original_split(keep + new_pairs)
    write_split(out, train, valid)
    manifest = {"source": str(src), "snapshot": snap, "teacher": TEACHER, "instruction": SHORTEN_INSTRUCTION,
                "limit_tokens": SHORTEN_LIMIT, "tokenizer": str(a.tokenizer), "estimate": est,
                "kept_unchanged": len(keep), "rerun": len(rerun), "outcomes": dict(outcomes),
                "train": len(train), "valid": len(valid), "rows": report, "pipeline_log": log.name}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nkept unchanged {len(keep)}; re-run {len(rerun)}: {dict(outcomes)}")
    print(f"written: train {len(train)}, valid {len(valid)} -> {out}")
    return 0


def run_recheck(d, snap) -> int:
    pairs = _read_pairs(d, "train") + _read_pairs(d, "valid")
    passed, dropped = recheck(pairs)
    train, valid = by_original_split(passed)
    write_split(d, train, valid)
    manifest_path = d / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest["recheck"] = {"commit": snap["commit"], "contract_bank": snap["contract_bank"],
                           "checked": len(pairs), "dropped": len(dropped),
                           "dropped_rows": [{"scenario_id": s, "reason": w, "detail": i} for s, w, i in dropped],
                           "train": len(train), "valid": len(valid),
                           "built": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"recheck on {snap['commit'][:7]} (no model called): {len(pairs)} rows, {len(dropped)} dropped")
    for s, w, i in dropped:
        print(f"  {s}: {w}: {i}")
    print(f"written: train {len(train)}, valid {len(valid)} -> {d}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RefuseToRun as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
