"""Newly-released split for the scope rulings (owner, 2026-11-20). Report only.

    CDSS_DRUG_SET=PFC python ruling_split.py <server_dir> <out_dir>

Every stored row goes through <server_dir>'s full pipeline twice, the model
replaced and nothing else:

  today   the generator returns the row's stored model answer; the validator
          returns its stored verdict. Eval runs keep both verbatim
          (instrument.generator_raw / validator_raw). Live rows keep the answer
          (held_response when held, else response) and the gate's verdict and
          issues, so their validator verdict is rebuilt from those
          ("live, approximate").
  ruling  ruling 1: the generator returns code's own GIVE lines for the doses
          that run built (render_give_line, render_range_line); the validator
          returns SAFE (its future is the owner's ruling b3). A row whose run
          builds no dose would, under ruling 2, show guideline text.

Columns (owner, 2026-11-20): a row held today that serves a code-written dose
under ruling 1 is NEWLY RELEASED, split by why it held today:
  (i)  a code check failed on the model's text (det_check issues);
  (ii) the validator's verdict (issues listed verbatim, and flagged when they
       name a patient finding);
  (iii) anything else (expected 0).
A row held today that, under ruling 2, shows guideline text goes in its own
column, "now shows guideline text", and is not counted as released.

Rows with no stored model answer get the ruling run only ("no stored answer").
Retrieval is stubbed, as in the pipe replay. The trace (tools/dose_trace.py)
is run on every served answer: today's as a baseline, ruling 1's must be 0.

Writes <out_dir>/ruling_split_<SET>.json and .md.
"""
import ast
import collections
import glob
import json
import os
import re
import sys

tree, out_dir = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
SET = os.environ.get("CDSS_DRUG_SET", "PFC")
os.makedirs(os.path.join(out_dir, "split_logs"), exist_ok=True)
os.environ.update(OPENAI_API_KEY="offline", CDSS_LOG_DIR=os.path.join(out_dir, "split_logs"),
                  FEEDBACK_LOG=os.path.join(out_dir, "split_logs", "fb.log"))
sys.path.insert(0, tree)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
os.chdir(tree)
import openai_client as oc  # noqa: E402
import providers  # noqa: E402
from dose_trace import untraced  # noqa: E402

EVAL = "/home/andrew/projects/cdss-eval"
LIVE = "/home/andrew/pi-cloud-cdss/server/logs/sessions"
PATIENT_TERMS = re.compile(
    r"hypotens|hypertens|\bbp\b|blood pressure|\bhr\b|heart rate|brady|tachy|spo2|"
    r"allerg|pregnan|contraindicat|weight|\bkg\b|pediatric|paediatric|child|infant|"
    r"\bage\b|elderly|renal|hepatic|head injury|tbi|gcs|sbp|shock|bleed", re.I)

# ── the stubs ────────────────────────────────────────────────────────────────
S = {}


def _is_validator(system):
    return system == oc.VALIDATOR_PROMPT or "Clinical Safety Validator" in (system or "")


def chat(system, messages, **k):
    if _is_validator(system):
        q = S.get("validator") or []
        return q.pop(0) if q else '{"result":"SAFE","issues":[],"rationale":"stub"}'
    S["generator_called"] = True
    if S["mode"] == "ruling":
        return S.get("code_text") or "(no dose built)"
    q = S.get("generator") or []
    return (q.pop(0) if len(q) > 1 else q[0]) if q else "(no stored answer)"


providers.chat = chat
_real_doses, _real_rates, _real_gate = oc.build_allowed_doses, oc.build_allowed_rates, oc.apply_safety_gate


def _doses(*a, **k):
    d = _real_doses(*a, **k)
    S["doses"] = list(d or [])
    S["all_doses"] = list(d or [])
    _code()
    return d


def _rates(*a, **k):
    r = _real_rates(*a, **k)
    S["rates"] = list(r or [])
    _code()
    return r


def _code():
    lines = ([oc.render_give_line(d) for d in S.get("doses") or []]
             + [oc.render_range_line(r) for r in S.get("rates") or []])
    S["code_text"] = ("**GIVE**\n" + "\n".join(lines)) if lines else ""


def _gate(response_text, det_check, llm_result, *a, **k):
    o = _real_gate(response_text, det_check, llm_result, *a, **k)
    S["gate"] = {"det": list(det_check.issues or []), "validator": llm_result.get("result"),
                 "validator_issues": list(llm_result.get("issues") or []),
                 "blocked": bool(o.blocked), "text": response_text}
    return o


_real_checks = oc.run_deterministic_checks


def _checks(query, response_text, patient_ctx, allowed_doses=None, current_query=None):
    # Ruling 1's answer is the doses the checks themselves accept for this
    # question: the list as built carries several indications and the model
    # was told to choose; the checks narrow it (A1b indication_matched, A32
    # stated_indication_matched). The stand-in renders that narrowed list,
    # and the real checks then judge that text.
    if S.get("mode") == "ruling":
        narrowed = oc.indication_matched(query, allowed_doses or [])
        narrowed, _other = oc.stated_indication_matched(query, narrowed, patient_ctx)
        S["doses"] = list(narrowed)
        _code()
        response_text = S["code_text"] or response_text
        S["ruling_text"] = response_text
    return _real_checks(query, response_text, patient_ctx, allowed_doses, current_query=current_query)


def _gate_ruling(response_text, *a, **k):
    if S.get("mode") == "ruling" and S.get("ruling_text"):
        response_text = S["ruling_text"]
    return _gate(response_text, *a, **k)


oc.build_allowed_doses, oc.build_allowed_rates = _doses, _rates
oc.run_deterministic_checks, oc.apply_safety_gate = _checks, _gate_ruling


class _Ret:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                "distances": [[0.2]]}


def run(mode, query, history, generator=None, validator=None):
    S.clear()
    S.update(mode=mode, generator=list(generator or []), validator=list(validator or []))
    r = oc._query_with_rag_internal(query, _Ret(), conversation_history=history)
    g = S.get("gate")
    called = bool(S.get("generator_called"))
    if not called:
        state = "before model"
    elif g and g["blocked"]:
        state = "held"
    else:
        state = "served"
    return {"state": state, "source_mode": r.get("source_mode"), "verdict": r.get("validator_result"),
            "doses": [oc.render_give_line(d) for d in S.get("doses") or []],
            "rates": [oc.render_range_line(x) for x in S.get("rates") or []],
            "gate": g, "response": r.get("response"), "built_any": bool(S.get("all_doses") or S.get("rates")),
            "_doses": S.get("doses") or [], "_rates": S.get("rates") or []}


# ── the rows ─────────────────────────────────────────────────────────────────
def _list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            x = ast.literal_eval(v)
            return x if isinstance(x, list) else [v]
        except (ValueError, SyntaxError):
            return [v]
    return []


hist = {}
for l in open(f"{EVAL}/scenarios/scenarios.jsonl"):
    s = json.loads(l)
    hist[s["id"]] = [h for h in (s.get("history") or []) if isinstance(h, dict)]

rows, seen = [], set()
for f in sorted(glob.glob(f"{EVAL}/runs/*/results.jsonl")):
    for l in open(f):
        r = json.loads(l)
        ins = r.get("instrument") or {}
        gen, val = _list(ins.get("generator_raw")), _list(ins.get("validator_raw"))
        if not gen:
            continue
        key = json.dumps([r["scenario_id"], r["query"], gen[0]])
        if key in seen:
            continue
        seen.add(key)
        rows.append({"origin": "eval", "run": f.split("/")[-2], "scenario": r["scenario_id"],
                     "query": r["query"], "history": hist.get(r["scenario_id"], []),
                     "generator": gen, "validator": val, "recorded": r.get("outcome")})
for f in sorted(glob.glob(f"{LIVE}/*.jsonl")):
    for l in open(f):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if not r.get("query") or str(r.get("synthetic")) == "True":
            continue
        v = r.get("validator_result")
        text = r.get("held_response") if v == "UNSAFE" else r.get("response")
        if not text or v not in ("SAFE", "UNSAFE", "NEEDS_HUMAN_REVIEW"):
            continue
        key = json.dumps(["live", r["query"], text])
        if key in seen:
            continue
        seen.add(key)
        verdict = json.dumps({"result": v, "issues": _list(r.get("validator_issues")),
                              "rationale": "recorded"})
        rows.append({"origin": "live, approximate", "run": os.path.basename(f), "scenario": "live",
                     "query": r["query"], "history": [], "generator": [text], "validator": [verdict],
                     "recorded": v})
pred, pseen = [], {(x["query"], json.dumps(x["history"])) for x in rows}
for l in open(f"{EVAL}/scenarios/scenarios.jsonl"):
    s = json.loads(l)
    k = (s["query"], json.dumps(hist.get(s["id"], [])))
    if k not in pseen:
        pseen.add(k)
        pred.append({"origin": "bank, no stored answer", "scenario": s["id"], "query": s["query"],
                     "history": hist.get(s["id"], [])})
for f in sorted(glob.glob(f"{LIVE}/*.jsonl")):
    for l in open(f):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("query") and str(r.get("synthetic")) != "True" and (r["query"], "[]") not in pseen:
            pseen.add((r["query"], "[]"))
            pred.append({"origin": "live, no stored answer", "scenario": "live", "query": r["query"],
                         "history": []})

# ── classify ─────────────────────────────────────────────────────────────────
out, counts = [], collections.Counter()
trace_today, trace_ruling = collections.Counter(), []


def _strip(x):
    return {k: v for k, v in x.items() if not k.startswith("_")}


_LIMIT = int(os.environ.get("SPLIT_LIMIT", "0")) or None  # smoke runs only
for row in (rows + pred)[:_LIMIT]:
    ruling = run("ruling", row["query"], row["history"])
    today = run("today", row["query"], row["history"], row.get("generator"), row.get("validator")) \
        if row.get("generator") else None
    has_dose = bool(ruling["doses"] or ruling["rates"])
    if ruling["state"] == "served" and has_dose:
        bad = untraced(ruling["gate"]["text"], ruling["_doses"], ruling["_rates"])
        if bad:
            trace_ruling.append({"query": row["query"], "untraced": bad})
    if today and today["state"] == "served" and today["gate"]:
        bad = untraced(today["gate"]["text"], today["_doses"], today["_rates"])
        trace_today["served" if not bad else "served, untraced number"] += 1
    # The ruling's outcome.
    if ruling["state"] == "before model":
        r_out = "before model (unchanged)"
    elif not has_dose and ruling["built_any"]:
        r_out = "no dose for the asked indication (hold or question)"
    elif not has_dose:
        r_out = "guideline text (ruling 2)"
    elif ruling["state"] == "held":
        r_out = "held (code text)"
    else:
        r_out = "code-written dose"
    t_out = "no stored answer" if today is None else today["state"]
    col, why, flagged = None, None, False
    if today is None:
        col = "no stored answer: " + r_out
    elif today["state"] == "before model" or ruling["state"] == "before model":
        col = "before model, unchanged" if today["state"] == ruling["state"] else "before model, differs (check)"
    elif today["state"] == "held" and r_out == "code-written dose":
        g = today["gate"] or {}
        if g.get("det"):
            col, why = "NEWLY RELEASED (i) code check on model text", g["det"]
        elif g.get("validator") == "UNSAFE":
            col, why = "NEWLY RELEASED (ii) validator verdict", g.get("validator_issues")
            flagged = any(PATIENT_TERMS.search(str(i)) for i in (why or []))
        else:
            col, why = "NEWLY RELEASED (iii) anything else", g
    elif today["state"] == "held" and r_out == "guideline text (ruling 2)":
        g = today["gate"] or {}
        col, why = "now shows guideline text", (g.get("det") or g.get("validator_issues"))
    elif today["state"] == "held" and r_out.startswith("no dose for the asked"):
        col = "held both (no dose for the asked indication)"
    elif today["state"] == "held":
        col = "held both"
    elif today["state"] == "served" and r_out == "held (code text)":
        col, why = "NEWLY HELD (code text held)", ruling["gate"]["det"] if ruling["gate"] else None
    elif today["state"] == "served" and r_out.startswith("no dose for the asked"):
        col, why = "NEWLY HELD (no dose for the asked indication)", today["doses"]
    elif today["state"] == "served" and r_out == "code-written dose":
        col = "served both (dose now code-written)"
    elif today["state"] == "served":
        col = "served both (model text now guideline text)"
    else:
        col = "other (check)"
    counts[col] += 1
    out.append({"origin": row["origin"], "run": row.get("run"), "scenario": row.get("scenario"),
                "query": row["query"], "history_turns": len(row["history"]), "column": col,
                "recorded_outcome": row.get("recorded"),
                "today": t_out, "ruling": r_out, "why_held_today": why, "patient_term_flag": flagged,
                "ruling_doses": ruling["doses"] + ruling["rates"],
                "today_detail": _strip(today) if today else None, "ruling_detail": _strip(ruling)})

base = os.path.join(out_dir, f"ruling_split_{SET}")
json.dump({"set": SET, "tree": tree, "counts": counts, "trace_today": trace_today,
           "trace_ruling_untraced": trace_ruling, "rows": out},
          open(base + ".json", "w"), ensure_ascii=False, indent=1, default=str)

md = [f"# Newly-released split, {SET} (report only)", "",
      f"Tree: `{tree}`. Rows: {len(rows)} with a stored model answer, {len(pred)} without.", "",
      "| Column | Rows |", "|---|---|"]
md += [f"| {k} | {v} |" for k, v in sorted(counts.items())]
md += ["", f"Trace, today's served model answers: {dict(trace_today)}.",
       f"Trace, ruling 1's code-written answers: {len(trace_ruling)} with an untraced number.", ""]
for title in sorted(c for c in counts if c.startswith("NEWLY") or c == "now shows guideline text"):
    md += [f"## {title}", ""]
    for o in out:
        if o["column"] != title:
            continue
        md.append(f"- [{o['origin']}] {o['scenario']} — \"{o['query'][:160]}\""
                  + (f" (history {o['history_turns']})" if o["history_turns"] else ""))
        if o["ruling_doses"]:
            md.append(f"  - ruling 1 serves: {' | '.join(d.lstrip('- ') for d in o['ruling_doses'])}")
        if o["why_held_today"]:
            md.append(f"  - held today for: {json.dumps(o['why_held_today'], ensure_ascii=False)[:400]}")
        if o["patient_term_flag"]:
            md.append("  - **flag: the validator's issue names a patient finding**")
    md.append("")
open(base + ".md", "w").write("\n".join(md))
print(SET, len(rows), len(pred), dict(counts))
