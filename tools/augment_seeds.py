#!/usr/bin/env python3
"""D5b: the teacher writes five paraphrases of each seed (owner, #113 review).

  python3 tools/augment_seeds.py --plan     count the seeds and price the calls
  python3 tools/augment_seeds.py            write data/distill/seeds/paraphrases.jsonl

The seeds are build_distill_dataset.load_seeds(): the cdss-eval bank minus the
30-set, minus anything within edit distance of an exam query, minus history.
The exam is removed BEFORE this step, so no exam scenario is ever paraphrased;
the builder checks every paraphrase against the exam again anyway.

One call per seed to the teacher (claude-opus-5, 120 s) with the fixed PROMPT
below. A fallback, an error or a reply that is not five distinct paraphrases
is recorded in errors.jsonl and skipped, never substituted. Resumable: seeds
already in paraphrases.jsonl are not called again. Each record carries its
source, seed id, the prompt's sha256 and synthetic: true.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_distill_dataset as bd  # noqa: E402

N_PARAPHRASES = 5
MAX_TOKENS = 800
SOURCE = "cdss-eval/scenarios.jsonl"
EXPECTED_OUT_TOKENS = 300

PROMPT = """You write training questions for a battlefield clinical decision support tool.

You are given ONE question a combat medic typed. Rewrite it as exactly 5 paraphrases.

Keep the same situation in every paraphrase:
- the same patient (adult or child, sex if stated), the same injury or illness, the same severity;
- the same request (what the medic is asking for);
- stated vital signs stay in the same clinical band (hypotensive stays hypotensive, a normal value stays normal).

Vary, across the 5:
- the wording and register: terse field shorthand, full sentences, slang, abbreviations, an occasional typo;
- the weight, if one is stated: within about 15%, in kg or lb;
- each vital sign, if stated: a different value within the same band.

Never:
- add a drug, a dose, a weight, a vital sign, an age or a finding the original does not state;
- add prior conversation, a second patient, or an answer;
- drop the request.

Reply with JSON only, no prose and no code fence:
{"paraphrases": ["...", "...", "...", "...", "..."]}"""


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT.encode()).hexdigest()


def parse_paraphrases(raw: str) -> list:
    """Exactly N_PARAPHRASES distinct non-empty strings, or ValueError."""
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw or "")
    try:
        paras = json.loads(text)["paraphrases"]
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"not the JSON asked for: {e}")
    if (not isinstance(paras, list) or len(paras) != N_PARAPHRASES
            or not all(isinstance(p, str) and p.strip() for p in paras)):
        raise ValueError(f"expected {N_PARAPHRASES} non-empty strings")
    paras = [p.strip() for p in paras]
    if len({bd.normalize(p) for p in paras}) != N_PARAPHRASES:
        raise ValueError("paraphrases repeat")
    return paras


def records(seed: dict, paras: list, model_returned) -> list:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return [{"paraphrase_id": f"{seed['seed_id']}/p{i}", "seed_id": seed["seed_id"],
             "source": SOURCE, "seed_query": seed["query"], "query": p,
             "teacher": bd.TEACHER, "model_returned": model_returned,
             "prompt_sha256": prompt_sha256(), "synthetic": True, "created": now}
            for i, p in enumerate(paras, 1)]


def done_seed_ids(path) -> set:
    path = pathlib.Path(path)
    if not path.exists():
        return set()
    return {json.loads(l)["seed_id"] for l in open(path, encoding="utf-8") if l.strip()}


def seeds_to_augment(seeds_path, exam: "bd.ExamSet", done: set, production=()) -> list:
    seeds, _counts = bd.load_seeds(seeds_path, exam, bd.EvalExclusion.load(bd.REPO),
                                   bd.JunkDrop.load(bd.REPO), production)
    return [s for s in seeds if s["seed_id"] not in done]


def estimate(seeds: list) -> dict:
    t_in, t_out = bd.RATES[bd.TEACHER]
    tin = sum(len(PROMPT) + len(s["query"]) for s in seeds) / bd.CHARS_PER_TOKEN
    n = len(seeds)
    return {"calls": n,
            "expected_usd": round((tin * t_in + n * EXPECTED_OUT_TOKENS * t_out) / 1e6, 2),
            "ceiling_usd": round((tin * t_in + n * (MAX_TOKENS + 3000) * t_out) / 1e6, 2)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--server", default=str(bd.REPO / "server"))
    p.add_argument("--logs", help="session log dir, to leave out seeds that repeat a production query")
    p.add_argument("--seeds", default=str(bd.SEEDS))
    p.add_argument("--scenarios-30", default=str(bd.SCENARIOS_30))
    p.add_argument("--out", default=str(bd.REPO / "data/distill/seeds"))
    p.add_argument("--plan", action="store_true")
    p.add_argument("--approve-cost", type=float)
    a = p.parse_args(argv)
    server, out = pathlib.Path(a.server).resolve(), pathlib.Path(a.out).resolve()
    exam = bd.ExamSet.load(bd.REPO, pathlib.Path(a.scenarios_30))
    logs = a.logs
    if logs is None:
        from dotenv import dotenv_values
        logs = dotenv_values(server / ".env").get("CDSS_LOG_DIR") or str(server / "logs/sessions")
    production, _ = bd.load_source_queries(logs, bd.EvalExclusion.load(bd.REPO), bd.JunkDrop.load(bd.REPO))
    para_path, err_path = out / "paraphrases.jsonl", out / "errors.jsonl"
    todo = seeds_to_augment(a.seeds, exam, done_seed_ids(para_path), production)
    est = estimate(todo)
    print(f"seeds to paraphrase: {len(todo)} ({N_PARAPHRASES} each, prompt {prompt_sha256()[:12]})")
    print(f"cost: expected ${est['expected_usd']:.2f}, ceiling ${est['ceiling_usd']:.2f}")
    bd.check_budget(est["ceiling_usd"], a.approve_cost)
    if a.plan:
        print("plan only: no model was called and nothing was written.")
        return 0

    scratch = tempfile.mkdtemp(prefix="d5b-aug-")
    os.environ["CDSS_LOG_DIR"] = scratch
    os.environ["FEEDBACK_LOG"] = os.path.join(scratch, "feedback.log")
    os.chdir(server)
    sys.path.insert(0, str(server))
    import providers
    out.mkdir(parents=True, exist_ok=True)
    ok = failed = 0
    for i, s in enumerate(todo, 1):
        try:
            with providers.cloud_timeout_for(bd.TEACHER_TIMEOUT_S):
                raw = providers.chat(PROMPT, [{"role": "user", "content": s["query"]}],
                                     model=bd.TEACHER, max_tokens=MAX_TOKENS)
            if providers.last_chat_fallback():
                raise ValueError(f"fell back: {providers.last_chat_fallback()}")
            recs = records(s, parse_paraphrases(raw), providers.last_chat_returned_model())
        except Exception as e:  # recorded and skipped, never substituted
            failed += 1
            with open(err_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"seed_id": s["seed_id"], "error": f"{type(e).__name__}: {e}",
                                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()}) + "\n")
            print(f"  [{i}/{len(todo)}] {s['seed_id']}: ERROR {e}", flush=True)
            continue
        ok += 1
        with open(para_path, "a", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  [{i}/{len(todo)}] {s['seed_id']}: {N_PARAPHRASES} paraphrases", flush=True)
    print(f"done: {ok} seeds paraphrased, {failed} errors  -> {para_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except bd.RefuseToRun as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
