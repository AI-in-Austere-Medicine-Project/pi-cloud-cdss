#!/bin/bash
# Runs ON THE JETSON, called by `make bench`.
# Usage: bench_remote.sh <tag> <base-model> <commit> <stamp> <probe>
#
# Follows benchmark run 3's arm script: the pinned snapshot of <commit>, the
# 30-scenario set through cdss-eval on its own port, and run_tests.sh against a
# second uvicorn. Both arms (base and tag) run on the same snapshot, so the only
# thing that moves between them is the model. Never contacts port 8000, never
# reads the production .env, and runs with no provider key in the environment.
set -euo pipefail
TAG=$1 BASE=$2 SHA=$3 STAMP=$4 PROBE=$5
EVAL=$HOME/projects/cdss-eval
PROD=$HOME/pi-cloud-cdss
PY=$PROD/.venv/bin/python
SCEN=${SCENARIOS:-$EVAL/runs/run-tests-mm3-20260925/scenarios-30.jsonl}
BANK_PORT=${BANK_PORT:-8123}
RT_PORT=${RT_PORT:-8012}
RT_TOKEN=d6-bench-$RT_PORT
W=$HOME/edgecdss-distill-bench/$TAG-$STAMP
die() { echo "bench: $*" >&2; exit 2; }

# ── refuse before touching anything ─────────────────────────────────────────
[ "$BANK_PORT" != 8000 ] && [ "$RT_PORT" != 8000 ] || die "port 8000 is the live service"
for p in "$BANK_PORT" "$RT_PORT"; do
  ss -ltn "sport = :$p" | grep -q LISTEN && die "port $p is in use"
done
pgrep -f 'harness/(serve|run_bank)\.py' >/dev/null \
  && die "another cdss-eval run is active; its load would contaminate the latency figures"
ollama show "$TAG" --template >/dev/null 2>&1 || die "no ollama model $TAG (run make ship first)"
ollama show "$BASE" --template >/dev/null 2>&1 || die "no ollama model $BASE"
git -C "$PROD" cat-file -e "$SHA^{commit}" 2>/dev/null || die "commit $SHA is not in $PROD"
[ -f "$SCEN" ] || die "$SCEN missing"
[ ! -e "$W" ] || die "$W already exists"

# ── pinned snapshot ─────────────────────────────────────────────────────────
mkdir -p "$W/target" "$W/logs" "$W/rt-logs"
git -C "$PROD" archive "$SHA" server | tar -x -C "$W/target" --strip-components=1
cp "$PROD/server/drug_concentrations.json" "$W/target/"
# run_bank.py records the snapshot's commit from this file, in the harness's format.
git -C "$PROD" log -1 --format='%H%n%H %ci %s' "$SHA" > "$W/target/PINNED_SHA"
cp "$SCEN" "$W/scenarios.jsonl"

python3 - "$W" "$SHA" "$TAG" "$BASE" "$SCEN" "$BANK_PORT" "$RT_PORT" <<'EOF'
import hashlib, json, subprocess, sys, datetime
W, sha, tag, base, scen, bp, rp = sys.argv[1:]
sh = lambda c: subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
drugs = json.load(open(f"{W}/target/drug_contracts.json"))["drugs"]
E = [e for d in drugs for e in d.get("dose_entries", [])]
ids = {l.split()[0]: l.split()[1] for l in sh("ollama list").splitlines()[1:]}
json.dump({
    "commit": sha, "signed": sum(e.get("signoff") is True for e in E), "entries": len(E),
    "ollama": sh("ollama --version"), "power": " ".join(sh("nvpmodel -q").split()),
    "kernel": sh("uname -r"), "tag": tag, "base": base,
    "tag_id": ids.get(tag if ":" in tag else f"{tag}:latest"), "base_id": ids.get(base),
    "scenarios_src": scen, "scenarios_sha256": hashlib.sha256(open(scen, "rb").read()).hexdigest(),
    "bank_port": int(bp), "rt_port": int(rp),
    "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
}, open(f"{W}/meta.json", "w"), indent=1)
EOF

# ── local only: no provider key, no production paths ────────────────────────
unset OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY XAI_API_KEY CDSS_LOCAL_API_KEY \
      CDSS_DEFAULT_MODEL CDSS_VALIDATOR_MODEL CDSS_LOG_DIR FEEDBACK_LOG CHROMADB_PATH
export CDSS_LLM_PROVIDER=local

# ── generation tok/s: one single-line probe per model through the API ──────
for pair in "base:$BASE" "tag:$TAG"; do
  python3 - "${pair%%:*}" "${pair#*:}" "$PROBE" >> "$W/tokps.jsonl" <<'EOF'
import json, sys, urllib.request
label, model, probe = sys.argv[1:]
body = json.dumps({"model": model, "prompt": probe, "stream": False,
                   "options": {"temperature": 0, "seed": 0, "num_predict": 128}}).encode()
def call():
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", body,
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=600))
call()  # load and warm
r = call()
print(json.dumps({"label": label, "model": model,
    "eval_count": r["eval_count"], "tok_s": r["eval_count"] / (r["eval_duration"] / 1e9),
    "prompt_eval_count": r.get("prompt_eval_count"),
    "prompt_tok_s": (r["prompt_eval_count"] / (r["prompt_eval_duration"] / 1e9))
                    if r.get("prompt_eval_duration") else None}))
EOF
done
cat "$W/tokps.jsonl"

# ── the 30-scenario set, base then tag ──────────────────────────────────────
run_arm() {
  local label=$1 model=$2 rid="d6-$TAG-$STAMP-$1"
  echo "30-set: $label ($model) -> $EVAL/runs/$rid"
  ( cd "$EVAL" && CDSS_LLM_MODEL=$model "$PY" harness/run_bank.py --provider openai --round all \
      --run-id "$rid" --port "$BANK_PORT" --target "$W/target" --scenarios "$W/scenarios.jsonl" \
      --timeout 300 ) > "$W/logs/bank-$label.stdout" 2>&1 || die "run_bank.py failed for $label: see $W/logs/bank-$label.stdout"
  cp "$EVAL/runs/$rid/results.jsonl" "$W/$label.results.jsonl"
  cp "$EVAL/runs/$rid/instrument.jsonl" "$W/$label.instrument.jsonl"
  cp "$EVAL/runs/$rid/run_meta.json" "$W/$label.run_meta.json"
  ss -ltn "sport = :$BANK_PORT" | grep -q LISTEN && die "the harness left :$BANK_PORT listening"
  return 0
}
run_arm base "$BASE"
run_arm tag "$TAG"

# ── run_tests.sh against a second uvicorn serving the tag ───────────────────
cp -r "$EVAL/corpus/chromadb" "$W/chromadb-rt"
( cd "$W/target" && CDSS_LLM_MODEL=$TAG CDSS_ACCESS_TOKEN=$RT_TOKEN CHROMADB_PATH=$W/chromadb-rt \
    CDSS_LOG_DIR=$W/rt-logs FEEDBACK_LOG=$W/rt-logs/fb.log \
    exec "$PY" -m uvicorn main:app --host 127.0.0.1 --port "$RT_PORT" ) > "$W/logs/uvicorn-rt.log" 2>&1 &
UV=$!
trap 'kill $UV 2>/dev/null || true' EXIT
for _ in $(seq 1 240); do curl -s -m 3 "http://127.0.0.1:$RT_PORT/health" >/dev/null && break; sleep 1; done
curl -s -m 5 "http://127.0.0.1:$RT_PORT/health" >/dev/null || die "uvicorn on :$RT_PORT did not come up"
CDSS_TEST_API=http://127.0.0.1:$RT_PORT/query CDSS_TEST_TOKEN=$RT_TOKEN \
  bash "$W/target/run_tests.sh" > "$W/run_tests.txt" 2>&1 || true
kill $UV; wait $UV 2>/dev/null || true
trap - EXIT
rm -rf "$W/chromadb-rt"
grep RESULTS "$W/run_tests.txt"
echo "bench: done -> $W"
