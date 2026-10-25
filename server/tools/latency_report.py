"""V1: join the run's rows to their session-log timings and report per-stage
median and p90 (nearest rank), deterministic answers vs model answers, and the
three slowest turns. Usage: latency_report.py <run.json> <log_dir> <out.md>"""
import json, math, pathlib, sys
run = json.load(open(sys.argv[1]))
logs = {}
for f in pathlib.Path(sys.argv[2]).glob("cdss_session_*.jsonl"):
    for l in f.read_text().splitlines():
        e = json.loads(l); logs[e.get("query_id")] = e
STAGES = ["request_received", "pre_gate_done", "retrieval_done", "doses_built",
          "llm_first_token", "llm_last_token", "validator_done", "response_sent"]
SEGMENTS = [("pre-gate", "request_received", "pre_gate_done"),
            ("retrieval", "pre_gate_done", "retrieval_done"),
            ("doses built", "retrieval_done", "doses_built"),
            ("LLM to first token", "doses_built", "llm_first_token"),
            ("LLM first to last token", "llm_first_token", "llm_last_token"),
            ("validator", "llm_last_token", "validator_done"),
            ("checks + finalise + send", "validator_done", "response_sent"),
            ("card finalise + send", "pre_gate_done", "response_sent"),
            ("total (request to response sent)", "request_received", "response_sent")]
def pct(xs, p):
    xs = sorted(xs)
    return xs[max(0, math.ceil(p / 100 * len(xs)) - 1)] if xs else None
rows = []
for r in run:
    e = logs.get(r["query_id"])
    if e is None or r["set"] == "warmup":
        continue
    t = e["timings"]
    r = dict(r, timings=t, kind="model" if t.get("llm_last_token") is not None else "deterministic",
             first_token_source=t.get("llm_first_token_source"), log_schema=e["log_schema"])
    rows.append(r)
warm = [dict(r, timings=logs[r["query_id"]]["timings"]) for r in run if r["set"] == "warmup" and r["query_id"] in logs]
def seg(t, a, b):
    return None if t.get(a) is None or t.get(b) is None else round(t[b] - t[a], 1)
def fmt(v):
    return "–" if v is None else (f"{v/1000:.2f} s" if v >= 1000 else f"{v:.0f} ms")
out = []
P = out.append
P(f"Items timed: {len(rows)} (warm-up excluded): " + ", ".join(
    f"{s} {sum(1 for r in rows if r['set']==s)}" for s in ("eval30", "batch2", "batch3", "magnesium")))
P(f"Deterministic answers: {sum(r['kind']=='deterministic' for r in rows)}; model answers: {sum(r['kind']=='model' for r in rows)}")
P(f"First-token source on model answers: {sorted({r['first_token_source'] for r in rows if r['kind']=='model'}, key=str)}")
P("")
for kind in ("deterministic", "model"):
    sub = [r for r in rows if r["kind"] == kind]
    P(f"### {kind.capitalize()} answers (n = {len(sub)})")
    P("")
    P("| Stage | n | median | p90 | max |")
    P("|---|---|---|---|---|")
    for name, a, b in SEGMENTS:
        if kind == "deterministic" and name not in ("pre-gate", "card finalise + send", "total (request to response sent)"):
            continue
        if kind == "model" and name == "card finalise + send":
            continue
        xs = [v for v in (seg(r["timings"], a, b) for r in sub) if v is not None]
        if xs:
            P(f"| {name} | {len(xs)} | {fmt(pct(xs,50))} | {fmt(pct(xs,90))} | {fmt(max(xs))} |")
    P("")
P("### The three slowest turns")
P("")
for r in sorted(rows, key=lambda r: -(r["timings"].get("response_sent") or 0))[:3]:
    t = r["timings"]
    P(f"**{r['id']}** ({r['set']}, {r['kind']}, {r['source_mode']}, {r['validator']}, history {r['history_turns']}): \"{r['query']}\"")
    P("")
    P("| Stage | ms from request | segment |")
    P("|---|---|---|")
    prev = None
    for s in STAGES:
        v = t.get(s)
        P(f"| {s} | {fmt(v) if v is not None else '–'} | {fmt(round(v - prev, 1)) if v is not None and prev is not None else ''} |")
        if v is not None:
            prev = v
    P("")
P("### Every turn")
P("")
P("| Id | Kind | Source mode | pre-gate | retrieval | doses | to 1st token | 1st→last | validator | send | total |")
P("|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    t = r["timings"]
    cells = [seg(t, a, b) for _, a, b in SEGMENTS[:7]]
    if r["kind"] == "deterministic":
        cells[6] = seg(t, "pre_gate_done", "response_sent")
    P(f"| {r['id']} | {r['kind']} | {r['source_mode']} | " + " | ".join(fmt(c) for c in cells) + f" | {fmt(t.get('response_sent'))} |")
P("")
if warm:
    P(f"Warm-up (excluded): total {fmt(warm[0]['timings'].get('response_sent'))}, to first token {fmt(seg(warm[0]['timings'],'doses_built','llm_first_token'))}.")
pathlib.Path(sys.argv[3]).write_text("\n".join(out) + "\n")
json.dump(rows, open(pathlib.Path(sys.argv[3]).with_suffix(".rows.json"), "w"), indent=1)
print("\n".join(out[:40]))
