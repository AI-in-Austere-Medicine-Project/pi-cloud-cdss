#!/usr/bin/env python3
"""Checks and reports for the D6 Makefile. Stdlib only, except `gguf-type`,
which reads the GGUF header with llama.cpp's own gguf-py.

  d6.py format FIXTURE DATA_DIR      every row of train/valid has the fixture's keys and roles
  d6.py pins REQUIREMENTS            the venv matches requirements.txt exactly
  d6.py gguf-type FILE LLAMA_CPP     refuse unless FILE is Q4_K_M (never f16)
  d6.py train-stats LOG              tok/s and losses from an mlx_lm.lora log
  d6.py stages WORK ADAPTER TAG       provenance of train, fuse, gguf and ship, as JSON
  d6.py report BENCH_DIR ...         the before/after table and docs/DISTILL_BENCH_<tag>.md
"""
import argparse, json, os, re, statistics, sys
from pathlib import Path


def die(msg):
    print(f"d6: {msg}", file=sys.stderr)
    sys.exit(2)


# ── format ───────────────────────────────────────────────────────────────────
def shape(row):
    """(top-level keys, [(message keys, role), ...]) — content is not compared."""
    msgs = row.get("messages")
    if not isinstance(msgs, list):
        return (tuple(sorted(row)), None)
    return (tuple(sorted(row)), [(tuple(sorted(m)), m.get("role")) for m in msgs])


def cmd_format(a):
    ref_rows = [json.loads(l) for l in open(a.fixture) if l.strip()]
    if not ref_rows:
        die(f"{a.fixture} is empty")
    ref = shape(ref_rows[0])
    bad = 0
    for split in ("train", "valid"):
        path = Path(a.data) / f"{split}.jsonl"
        if not path.exists():
            die(f"{path} missing: mlx_lm.lora needs train.jsonl and valid.jsonl")
        n = 0
        for i, line in enumerate(open(path), 1):
            if not line.strip():
                continue
            n += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  {path.name}:{i}: not JSON ({e})")
                bad += 1
                continue
            if shape(row) != ref:
                print(f"  {path.name}:{i}: shape {shape(row)} != fixture {ref}")
                bad += 1
                continue
            empty = [m["role"] for m in row["messages"]
                     if not isinstance(m.get("content"), str) or not m["content"].strip()]
            if empty:
                print(f"  {path.name}:{i}: empty content for {empty}")
                bad += 1
        print(f"format: {path} {n} rows")
    if bad:
        die(f"{bad} rows do not match {a.fixture}")
    print(f"format: every row matches {Path(a.fixture).name} "
          f"(keys {list(ref[0])}, roles {[r for _, r in ref[1]]})")


# ── pins ─────────────────────────────────────────────────────────────────────
def cmd_pins(a):
    from importlib.metadata import version, PackageNotFoundError
    drift = []
    for line in open(a.requirements):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, want = line.split("==")
        try:
            have = version(name)
        except PackageNotFoundError:
            have = None
        if have != want:
            drift.append(f"{name}: requirements {want}, venv {have}")
    if drift:
        die("venv does not match requirements.txt:\n  " + "\n  ".join(drift))
    print(f"pins: venv matches {a.requirements}")


# ── gguf-type ────────────────────────────────────────────────────────────────
def cmd_gguf_type(a):
    sys.path.insert(0, str(Path(a.llama_cpp) / "gguf-py"))
    import gguf
    r = gguf.GGUFReader(a.file)
    f = r.fields.get("general.file_type")
    if f is None:
        die(f"{a.file}: no general.file_type in the header")
    ftype = gguf.LlamaFileType(int(f.parts[f.data[0]][0]))
    if ftype != gguf.LlamaFileType.MOSTLY_Q4_K_M:
        die(f"{a.file} is {ftype.name}, not MOSTLY_Q4_K_M: refusing")
    print(f"gguf: {a.file} is {ftype.name} ({os.path.getsize(a.file) / 1e9:.2f} GB)")


# ── train-stats ──────────────────────────────────────────────────────────────
ITER_RE = re.compile(r"Iter (\d+): Train loss ([\d.]+).*?It/sec ([\d.]+), Tokens/sec ([\d.]+)")
VAL_RE = re.compile(r"Iter (\d+): Val loss ([\d.]+)")


def cmd_train_stats(a):
    text = open(a.log).read()
    it = [(int(i), float(l), float(s), float(t)) for i, l, s, t in ITER_RE.findall(text)]
    val = [(int(i), float(l)) for i, l in VAL_RE.findall(text)]
    if not it:
        die(f"no training reports in {a.log}")
    toks = [t for *_, t in it]
    print(f"train: tok/s mean {statistics.mean(toks):.1f} (min {min(toks):.1f}, max {max(toks):.1f}, "
          f"{len(toks)} reports); train loss {it[0][1]:.3f} @ {it[0][0]} -> {it[-1][1]:.3f} @ {it[-1][0]}"
          + (f"; val loss {val[0][1]:.3f} @ {val[0][0]} -> {val[-1][1]:.3f} @ {val[-1][0]}" if val else ""))


# ── stages ───────────────────────────────────────────────────────────────────
def grab(path, pattern):
    try:
        m = re.search(pattern, open(path).read())
    except FileNotFoundError:
        return None
    return m.group(1) if m else None


def cmd_stages(a):
    w, ad, tag = Path(a.work), a.adapter, a.tag
    cfg = json.load(open(w / "adapters" / ad / "adapter_config.json"))
    q4 = w / "gguf" / f"{ad}-q4km.gguf"
    out = {
        "Adapter": f"`{ad}`: `{cfg['model']}`, data `{cfg['data']}`, {cfg['iters']} iters, "
                   f"lr {cfg['learning_rate']}, batch {cfg['batch_size']}",
        "Train (Mac, mlx_lm.lora)": (grab(w / "adapters" / ad / "train-stats.txt", r"train: (.*)") or "—"),
        "Fused, bf16 (Mac, mlx_lm.generate, probe)":
            f"{grab(w / 'fused' / ad / 'd6-probe.txt', r'Generation: .*?([\d.]+) tokens-per-sec') or '—'} tok/s",
        "Q4_K_M GGUF": f"sha256 `{(grab(str(q4) + '.sha256', r'^([0-9a-f]{64})') or '—')[:16]}…`",
        "Jetson probe (ollama run --verbose)":
            f"{grab(w / 'gguf' / f'{tag}-probe.txt', r'(?m)^eval rate:\s+([\d.]+) tokens/s') or '—'} tok/s",
    }
    print(json.dumps(out, indent=1))


# ── report ───────────────────────────────────────────────────────────────────
def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def arm(bench, label):
    rows = load(bench / f"{label}.results.jsonl")
    inst = {r["request_id"]: r for r in load(bench / f"{label}.instrument.jsonl")}
    model_rows = [r for r in rows if (inst.get(r["request_id"]) or {}).get("generator_calls")]
    lat = [r["server_processing_ms"] / 1000 for r in model_rows
           if r["outcome"] != "SYSTEM_ERROR" and r.get("server_processing_ms") is not None]
    gen = [inst[r["request_id"]]["generation_ms"] / 1000 for r in model_rows
           if inst[r["request_id"]].get("generation_ms") is not None]
    oc = {k: sum(1 for r in rows if r["outcome"] == k) for k in ("SERVE", "BLOCK", "SYSTEM_ERROR")}
    return {"rows": rows, "n": len(rows), "oc": oc, "model_turns": len(model_rows),
            "models_used": sorted({r.get("model_used") or "" for r in model_rows}),
            "lat_med": pct(lat, .5), "lat_p95": pct(lat, .95), "gen_med": pct(gen, .5)}


def fmt(x, d=1):
    return "—" if x is None else f"{x:.{d}f}"


def cmd_report(a):
    bench = Path(a.bench)
    meta = json.load(open(bench / "meta.json"))
    tokps = {t["label"]: t for t in load(bench / "tokps.jsonl")}
    before, after = arm(bench, "base"), arm(bench, "tag")
    rt = open(bench / "run_tests.txt").read()
    m = re.search(r"RESULTS: (\d+) passed / (\d+) total", rt)
    rt_pass, rt_total = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    rt_ok = rt_pass is not None and rt_pass == rt_total == a.rt_expect
    stages = json.load(open(a.stages)) if a.stages and os.path.exists(a.stages) else {}

    moved = []
    by_sid = {r["scenario_id"]: r for r in before["rows"]}
    for r in after["rows"]:
        b = by_sid.get(r["scenario_id"])
        if b and b["outcome"] != r["outcome"]:
            moved.append((r["scenario_id"], b["outcome"], r["outcome"]))

    def row(name, lab, x):
        t = tokps.get(lab, {})
        return (f"| {name} | {x['oc']['SERVE']} / {x['oc']['BLOCK']} / {x['oc']['SYSTEM_ERROR']} | "
                f"{x['model_turns']} | {fmt(x['lat_med'])} / {fmt(x['lat_p95'])} | {fmt(x['gen_med'])} | "
                f"{fmt(t.get('tok_s'))} | {fmt(t.get('prompt_tok_s'))} | n/a ‡ |")

    table = [
        "| Arm | 30-set served / held / sys-err | Model turns | Latency median / p95 (s) † | Generation median (s) | Generation tok/s § | Prefill tok/s § | Prompt tokens |",
        "|---|---|---|---|---|---|---|---|",
        row(f"before: `{meta['base']}`", "base", before),
        row(f"after: `{meta['tag']}`", "tag", after),
    ]
    L = [f"# Distillation bench: `{meta['tag']}`, {meta['started'][:10]}", ""]
    if a.note:
        L += [f"> {a.note}", ""]
    L += ["Written by `make bench` (tools/distill, D6). A measurement record: nothing was tuned between the arms.",
          "", "## Setup", "", "| | |", "|---|---|",
          f"| Commit | `{meta['commit']}` (`git archive` of `server/`, plus the deployed `drug_concentrations.json`) |",
          f"| Contract bank | **{meta['signed']} signed entries** of {meta['entries']} |",
          f"| Ollama | {meta['ollama']} |",
          f"| Power mode | {meta['power']} |",
          f"| Kernel | {meta['kernel']} |",
          f"| Before | `{meta['base']}` ({meta['base_id']}) |",
          f"| After | `{meta['tag']}` ({meta['tag_id']}), same TEMPLATE, SYSTEM and LICENSE as the base |",
          f"| 30-scenario set | `{meta['scenarios_src']}`, sha256 `{meta['scenarios_sha256'][:16]}…`, `--round all` |",
          f"| Isolation | 30-set on :{meta['bank_port']} (cdss-eval `run_bank.py`), `run_tests.sh` on a second uvicorn on :{meta['rt_port']}; "
          "no provider keys in the environment; the live service on :8000 and its `.env` untouched |"]
    if stages:
        L += ["", "## Toolchain provenance", "", "| | |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in stages.items()]
    L += ["", "## Before / after", "", *table, "",
          "† Server processing time over model-reaching turns, excluding system errors.",
          "§ One single-line ketamine probe through the Ollama API on the Jetson, `temperature 0`, "
          "`num_predict 128`, after one warm-up call: `eval_count / eval_duration` and "
          "`prompt_eval_count / prompt_eval_duration`. Not the served prompt.",
          "‡ The harness does not wrap the local client, so served prompt tokens are not captured "
          "(as in benchmark run 3).", "",
          f"Models that generated the model turns: before {before['models_used']}, after {after['models_used']}.", "",
          "## run_tests.sh against the new tag", "",
          f"**{rt_pass} / {rt_total}**, required {a.rt_expect}/{a.rt_expect}: **{'holds' if rt_ok else 'FAILS'}**.", "",
          "## Scenarios whose outcome moved", ""]
    L += ([f"- `{s}`: {b} → {t}" for s, b, t in moved] or ["- None."])
    fails = [l for l in rt.splitlines() if l.startswith("❌")]
    if fails:
        L += ["", "### run_tests.sh failures", "", "```", *fails, "```"]
    doc = "\n".join(L) + "\n"

    print("\n".join(table))
    print(f"run_tests.sh: {rt_pass}/{rt_total} ({'holds' if rt_ok else 'FAILS'}, need {a.rt_expect}/{a.rt_expect})")
    print("moved:", moved or "none")
    Path(a.out).write_text(doc)
    print(f"wrote {a.out}")
    if not rt_ok:
        die(f"run_tests.sh {rt_pass}/{rt_total}: the {a.rt_expect}/{a.rt_expect} bar does not hold")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("format"); p.add_argument("fixture"); p.add_argument("data"); p.set_defaults(f=cmd_format)
    p = sp.add_parser("pins"); p.add_argument("requirements"); p.set_defaults(f=cmd_pins)
    p = sp.add_parser("gguf-type"); p.add_argument("file"); p.add_argument("llama_cpp"); p.set_defaults(f=cmd_gguf_type)
    p = sp.add_parser("train-stats"); p.add_argument("log"); p.set_defaults(f=cmd_train_stats)
    p = sp.add_parser("stages"); p.add_argument("work"); p.add_argument("adapter"); p.add_argument("tag")
    p.set_defaults(f=cmd_stages)
    p = sp.add_parser("report")
    p.add_argument("bench"); p.add_argument("--out", required=True)
    p.add_argument("--rt-expect", type=int, default=27)
    p.add_argument("--stages"); p.add_argument("--note")
    p.set_defaults(f=cmd_report)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
