#!/usr/bin/env python3
"""D5: build the distillation dataset from teacher answers.

  python3 tools/build_distill_dataset.py --plan     select, count and cost; no teacher call
  python3 tools/build_distill_dataset.py            the run (stops over $40 unless approved)

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
"""
import argparse
import collections
import contextlib
import copy
import datetime
import hashlib
import importlib
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


class RefuseToRun(Exception):
    pass


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


# ── the source: single-turn production queries ─────────────────────────────
def load_source_queries(log_dir, exclusion: EvalExclusion):
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
            else:
                k = normalize(q)
                if k in seen:
                    seen[k]["occurrences"] += 1
                else:
                    seen[k] = {"query": q, "scenario_id": qhash(q)[:12],
                               "first_ts": r.get("ts"), "occurrences": 1}
                continue
    return list(seen.values()), counts


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


def refuse_unsigned_doses(rows: list):
    """The owner's refuse-to-run: any row with a dose that isn't the signed value."""
    oc = _oc()
    check = getattr(oc, "_distill_real_rdc", oc.run_deterministic_checks)
    bad = []
    for r in rows:
        q, ctx, doses = r["check"]
        issues = check(q, r["assistant"], ctx, doses).issues
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

    def __init__(self, oc, providers, stub: bool):
        self.oc, self.providers, self.stub = oc, providers, stub
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
        out = "PLAN STUB" if self.stub else self.real_chat(system, messages, model=model, **kw)
        self.gen = {"system": system, "messages": copy.deepcopy(messages), "response": out}
        return out

    def rdc(self, query, response_text, patient_ctx, allowed_doses=None):
        if self.gen is not None and response_text == self.gen["response"] and self.check is None:
            self.check = (query, copy.deepcopy(patient_ctx), list(allowed_doses or []))
        return self.real_rdc(query, response_text, patient_ctx, allowed_doses)

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
    p.add_argument("--out", default=str(REPO / "data/distill"))
    p.add_argument("--plan", action="store_true", help="select, count and cost; call no model")
    p.add_argument("--approve-cost", type=float, help="the owner's approved ceiling, in USD, over $40")
    return p


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
    os.chdir(server)
    sys.path.insert(0, str(server))
    import openai_client as oc
    import providers
    from embeddings import ChromaDBClient
    if providers.generator_timeout_s(TEACHER) != TEACHER_TIMEOUT_S:
        raise RefuseToRun("the teacher would not be waited for 120 s")
    pipeline_log = open(os.path.join(scratch, "pipeline.log"), "w")
    chroma = ChromaDBClient()

    sources, src_counts = load_source_queries(logs, EvalExclusion.load(REPO))
    print(f"source: {logs}")
    print(f"  distinct single-turn production queries: {len(sources)}  "
          f"(entries left out: {dict(src_counts)})")

    plan_cap = Capture(oc, providers, stub=True)
    plans, deterministic = [], 0
    for s in sources:
        plan_cap.run(s["query"], chroma, pipeline_log)
        if plan_cap.gen is None:
            deterministic += 1
            continue
        g = plan_cap.gen
        plans.append({**s, "prompt_chars": len(g["system"]) + sum(len(m["content"]) for m in g["messages"]),
                      "validator_chars": plan_cap.validator_chars})
    est = estimate(plans)
    print(f"  model-reaching on {snap['commit'][:7]}: {len(plans)}  (deterministic-only: {deterministic})")
    print(f"  teacher {TEACHER}, {TEACHER_TIMEOUT_S} s; validator {providers.validator_model()}")
    print(f"  cost: expected ${est['expected_usd']:.2f}, ceiling ${est['ceiling_usd']:.2f} "
          f"({est['calls']} teacher calls, ~{est['teacher_in_tokens']:,} prompt tokens)")
    check_budget(est["ceiling_usd"], a.approve_cost)
    if a.plan:
        print("plan only: no model was called and nothing was written.")
        return 0

    cap = Capture(oc, providers, stub=False)
    kept, reasons, unasked_seen = [], collections.Counter(), collections.Counter()
    reasons["deterministic"] = deterministic
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
        reasons[why or "kept"] += 1
        print(f"  [{i}/{len(plans)}] {why or 'kept':20s} {s['query'][:70]}", flush=True)
        if why:
            continue
        kept.append({"scenario_id": s["scenario_id"], "assistant": cap.gen["response"],
                     "check": cap.check, "row": to_row(cap.gen["system"], cap.gen["messages"],
                                                       cap.gen["response"]),
                     "meta": {"scenario_id": s["scenario_id"],
                              "scenario_type": scenario_type(oc, s["query"]),
                              "query": s["query"], "occurrences": s["occurrences"],
                              "first_seen": s["first_ts"], "teacher": TEACHER,
                              "model_returned": result.get("model_returned"),
                              "validator_result": result.get("validator_result"),
                              "source_mode": result.get("source_mode"),
                              "snapshot_commit": snap["commit"],
                              "contract_bank": snap["contract_bank"],
                              "concentrations_sha256": snap["concentrations_sha256"],
                              "built": datetime.datetime.utcnow().isoformat() + "Z"}})

    refuse_unsigned_doses(kept)
    train, valid = split(kept)
    write_split(a.out, [(r["row"], {**r["meta"], "split": "train"}) for r in train],
                [(r["row"], {**r["meta"], "split": "valid"}) for r in valid])

    print(f"\nkept {len(kept)}: train {len(train)}, valid {len(valid)} "
          f"({len({r['scenario_id'] for r in valid})} scenarios)  -> {a.out}")
    print("excluded:", {k: v for k, v in reasons.items() if k != "kept"})
    print(f"unasked drugs removed {reasons['unasked_drug']} rows: {dict(unasked_seen)}")
    types = collections.Counter(r["meta"]["scenario_type"] for r in kept)
    print("scenario types (top 10):")
    for t, n in types.most_common(10):
        print(f"  {n:4d}  {t}" + (f"   WARNING: fewer than {COVERAGE_MIN} rows" if n < COVERAGE_MIN else ""))
    drugs = collections.Counter(d for r in kept for d in drugs_in(r["assistant"]))
    print("drugs named in the answers:")
    for d, n in drugs.most_common():
        print(f"  {n:4d}  {d}")
    manifest = {"snapshot": snap, "teacher": TEACHER, "teacher_timeout_s": TEACHER_TIMEOUT_S,
                "validator": providers.validator_model(), "estimate": est,
                "source_entries_left_out": dict(src_counts), "excluded": dict(reasons),
                "unasked_drugs": dict(unasked_seen), "train": len(train), "valid": len(valid),
                "scenario_types": dict(types), "drugs": dict(drugs), "pipeline_log": pipeline_log.name}
    (pathlib.Path(a.out) / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RefuseToRun as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
