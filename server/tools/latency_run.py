"""V1 latency baseline (docs/VOICE_LATENCY_BASELINE_2026-10-25.md): post every item to the :8012 worktree server (offline,
qwen2.5:3b) and save each response's query_id, so the session log's timings
can be joined. Usage: latency_run.py <out.json>  (a server on :8012, CDSS_LLM_PROVIDER=local)"""
import json, sys, time, urllib.request
API = "http://127.0.0.1:8012/query"
B2 = ["80 kg adult, open femur fracture, IV access, cefazolin dose",
      "80 kg adult, open tib-fib fracture, IV access, what antibiotic do I give",
      "20 kg child, 6 years old, open forearm fracture, IV access, cefazolin dose",
      "80 kg adult, septic, BP 88/50, IV access, ceftriaxone dose",
      "20 kg child, 6 years old, septic, IV access, ceftriaxone dose",
      "80 kg adult, intubated, IV access, ketamine drip for sedation, what rate",
      "80 kg adult, femur fracture, IV access, ketamine drip for pain, what rate",
      "80 kg adult, reducing a dislocated shoulder with ketamine procedural sedation, IV access, how much midazolam do I add",
      "80 kg adult, intubated with rocuronium 40 minutes ago, moving, redose rocuronium how much"]
B3 = ["80 kg adult, BP 70/40 after 2 L of fluid, still in shock, epinephrine infusion rate",
      "80 kg adult trauma, BP 78/40, push dose epinephrine for hypotension",
      "80 kg adult, hemorrhagic shock, 4 units of whole blood in, calcium dose",
      "80 kg adult, hemorrhagic shock, 4 units of whole blood in, calcium chloride dose",
      "80 kg adult, penetrating brain injury, cefazolin dose",
      "80 kg adult, cefazolin dose",
      "20 kg child, 6 years old, penetrating head injury, ceftriaxone dose",
      "adult, opioid overdose, RR 6, no IV access, intranasal naloxone dose",
      "70 kg adult, severe malaria, confused, artesunate dose",
      "80 kg adult, symptomatic bradycardia, about to pace, midazolam for sedation",
      "80 kg adult, intubated, propofol infusion rate for sedation"]
def main(out_path):
    items = [{"set": "warmup", "id": "warmup", "query": "how do I reassess a splinted forearm fracture", "history": []}]
    for l in open("/home/andrew/projects/cdss-eval/runs/run-tests-mm3-20260925/scenarios-30.jsonl"):
        s = json.loads(l)
        items.append({"set": "eval30", "id": s["id"], "query": s["query"],
                      "history": [h for h in (s.get("history") or []) if isinstance(h, dict)]})
    items += [{"set": "batch2", "id": f"B2-{i+1}", "query": q, "history": []} for i, q in enumerate(B2)]
    items += [{"set": "batch3", "id": f"B3-{i+1}", "query": q, "history": []} for i, q in enumerate(B3)]
    items.append({"set": "magnesium", "id": "MG-A39", "query": "don't want ketamine, I need magnesium, 75 kg", "history": []})
    out = []
    for it in items:
        body = json.dumps({"query": it["query"], "device_id": "v1-latency", "timestamp": "2026-10-25T00:00:00",
                           "voice_mode": "brief", "conversation_history": it["history"],
                           "session_id": "v1-latency"}).encode()
        req = urllib.request.Request(API, body, {"Content-Type": "application/json",
                                                 "X-Access-Token": "edgecdss-demo-2026", "X-Test-Run": "1"})
        t = time.perf_counter()
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.load(r)
        wall = round((time.perf_counter() - t) * 1000, 1)
        out.append({**{k: it[k] for k in ("set", "id", "query")}, "history_turns": len(it["history"]),
                    "query_id": d.get("query_id"), "source_mode": d.get("source_mode"),
                    "validator": d.get("validator_result"), "model": d.get("model"),
                    "client_wall_ms": wall, "processing_time_ms": d.get("processing_time_ms"),
                    "response": d.get("response", "")[:400]})
        print(it["id"], d.get("source_mode"), wall, flush=True)
    json.dump(out, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
