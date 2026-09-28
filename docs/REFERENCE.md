# EdgeCDSS reference

One line per name. The plan of record is [`WORK_ORDER.md`](WORK_ORDER.md); this page says what each name means and where it stands.

**Maintenance rule.** Any PR that changes an item's status, adds or removes a model tag, changes a Makefile command, or records a finding also updates this file, in the same PR. If this file and `WORK_ORDER.md` disagree, the work order wins.

## 1. The three modes

| Mode | Setting | Model writing the prose | State |
|---|---|---|---|
| **Cloud** | `CDSS_LLM_PROVIDER=openai`, or unset (the default) | The cloud model: `gpt-4o-mini` by default, or the one the medic selects. The validator stays on `gpt-4o-mini`. | The setting the live service ran in every benchmark so far (`LOCAL_LLM_BENCHMARK.md`, run 3). |
| **Hybrid** | The same setting. The fallback is built into it. | The cloud model. If a call can't connect in time, it's sent once to local `qwen2.5:3b`, and the answer is stamped `local-fallback` and bannered above the brief. | Always on under cloud. Default model: 8 s (`CDSS_LLM_CLOUD_TIMEOUT`). A selected model: 60 s (`CDSS_LLM_SELECTED_TIMEOUT`, #88). A provider error (401, 429, 5xx…) is not retried locally. |
| **Offline** | `CDSS_LLM_PROVIDER=local` (Ollama at `CDSS_LLM_BASE_URL`, default `http://localhost:11434/v1`) | The on-device model, `qwen2.5:3b` by default. The validator moves to it too. | Measured in the benchmarks, not the live setting. The client shows a "local model · offline" badge. |

Switching the offline model is one `.env` line: `CDSS_LLM_MODEL=<tag>`.

## 2. Model names

| Name | What it is |
|---|---|
| `qwen2.5:3b` | The Ollama tag on the Jetson (357c53fb659c): Qwen2.5 3B, GGUF Q4_K_M. It is the offline model, the hybrid fallback, and the "before" arm of every distillation bench (`BASE_TAG`). |
| `Qwen2.5-3B-Instruct-4bit` | `mlx-community/Qwen2.5-3B-Instruct-4bit`, the Mac base that `make train` puts the LoRA on (`BASE_4BIT`). `make fuse` uses the full-precision `Qwen/Qwen2.5-3B-Instruct` (`BASE_FULL`). |
| `edgecdss-dryrun` | Base plus a LoRA trained on a handful of hand-written rows before D6 existed. Proof that the Mac → GGUF → Jetson chain works; not a model result. Nothing serves it. An Ollama tag on the Jetson (865f63ecb476). |
| `edgecdss-d6check` | **Removed.** The D6 toolchain proof: 50 iterations on the 50-row dry-run set. Its record is [`DISTILL_BENCH_edgecdss-d6check.md`](DISTILL_BENCH_edgecdss-d6check.md). It is not a candidate model. |
| `edgecdss-v1` | **Does not exist yet.** Its job is to beat `qwen2.5:3b` on the same exam. |
| `edgecdss-v2` and later | Later versions, each with its own dataset or training knobs and its own bench doc. |
| The teacher | `claude-opus-5`: the exact model ID run 3's Opus arm called (`providers.json` id, `anthropic/claude-opus-5`). D5 regenerates the training answers with it. It is never substituted. |
| The eight cloud arms | `gpt-4o-mini` (default, and the validator), `gpt-4o`, `claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-5`, `gemini-3.7-flash`, `gemini-3.1-pro-preview`, `grok-4`. |

A version number names one dataset, plus one set of training knobs, plus one bench doc.

## 3. A items: safety

Every A item finishes before any D item starts, because D5's dataset is built through this code.

| Item | Meaning | Came from | Status |
|---|---|---|---|
| A0 | After "new patient" or "different patient", the previous patient's doses, vitals, weight and history are gone. | Run 3, finding 3 (G-MTN-05) | Done, #90 |
| A1 | Haemorrhage with shock physiology reaches the DCR card, with TXA. | Work order 2026-09-24 (P1) | Done, #82 |
| A1b | The dose check matches the indication, not only the value. A seizing patient gets the seizure entry. | Run 3, finding 2 (H-S3) | Done, #91 |
| A2 | A deterministic severe-TBI card for GCS ≤ 8 with a head injury. | Work order 2026-09-24 | Done, #84 |
| A3 | A patient whose airway is already done never gets the RSI bundle. | Feedback review §1 (4 field reports) | Done, #86 |
| A4 | Anything by mouth holds when consciousness is depressed. A refusal of oral intake doesn't hold. | Work order 2026-09-24; run 3, finding 4 | Done, #95 |
| A5 | A fixed-dose hold never says "no weight confirmed"; it names the real reason. | Work order 2026-09-24; local benchmark run 2, finding 3 | Done, #97 |
| A6 | A design, no code, for a signed table of contraindicated procedures. | Work order 2026-09-24 | Done, #99. P3 and P5 signed (#100); P1 and P2 unsigned |
| A7 | The GCS parser reads "GCS is seven", "3T", "of 6", "G6" and "E4V5M6". | Owner, 2026-09-25; "E4V5M6" added in the #95 review | Done, #101 |
| A8 | "status post" must not match status epilepticus. | Found in #91 | In review, #102 |
| A9 | "actively seizing", "still seizing", "seizing now" and "in status" reach the signed seizure entry. | Found in #91 | Next, after A8 |
| A10 | The CICO card doesn't fire on a cric that is already done. | Found in #86 | After A9 |
| A11 | The free-text dose check reads infusion rates and compares them with signed rate entries; a rate with no signed rate entry holds. | Found in #97; owner, #97 review | After A10 |
| A12 | Succinylcholine leaves ALLOWED_DOSES under a P5 condition (burns, spinal cord injury, hyperkalaemia). | Owner, #98 review | After A11 |
| A13 | Remove the dead `safety_rules.json` path, with a test that nothing depended on it. | Found in #98; owner, #98 review | After A12 |

## 4. D items: data and speed

| Item | Meaning | Machine | Status |
|---|---|---|---|
| D5a | Log the full answer (schema 14), with a disk estimate and log rotation. | Jetson | After A13 |
| D1 | Evaluation hygiene: new `run_tests.sh` cases, reconciling the 30-set, the benchmark protocol. | Jetson | After D5a |
| D5 | Build the distillation dataset from teacher answers (`tools/build_distill_dataset.py`). | Jetson | After D1 |
| D6 | The training toolchain: train, fuse, gguf, ship, bench. | Mac (bench runs on the Jetson over ssh) | Done, #93 |
| D2 | Put the fixed prompt first, so Ollama reuses its cache. | Jetson | After C1 |
| D3 | Pass the model 4 retrieved chunks, not the current top-k. | Jetson | After D2 |
| D4 | Show the deterministic part first; the prose only after the dose check passes. | Jetson | After D3 |

## 5. B and C items: format and feedback

| Item | Meaning | Status |
|---|---|---|
| B1 | A dose served from a JTS-cited signed contract is labelled JTS, with the contract's citation. | After D6 |
| B2 | Brief-mode section headers are normalised to DO THIS, GIVE, WATCH, DON'T, EVAC, TLDR, SOURCE. | After B1 |
| B3 | The vitals caution stops appending "anything by mouth carries an aspiration risk" to an answer that already refuses oral intake. Format only. | After B2 |
| C1 | The feedback instrument: session id, the full context in `/feedback`, a working comment field. | After B3 |

## 6. Training vocabulary

| Word | Meaning | Where |
|---|---|---|
| Distillation | Teaching the small local model to write what the teacher wrote. | D5 builds the data; D6 trains on it |
| Dataset | `data/distill/train.jsonl` and `valid.jsonl`: messages triples (system, user, assistant), split 90/10 by scenario. Untracked. | `tools/build_distill_dataset.py` (D5); format fixture `tools/distill/fixtures/format_example.jsonl`, checked by `make preflight` |
| Base model | The model before training: `Qwen2.5-3B-Instruct`. | `BASE_4BIT`, `BASE_FULL`, `BASE_TAG` in the Makefile |
| LoRA | Training a small add-on to the base, not the whole model. | `make train` (`mlx_lm.lora`) |
| Adapter | The trained add-on. | `make train ADAPTER=name` → `~/edgecdss-train/adapters/<name>` |
| Iterations | Training steps. Default 600. | `ITERS=` |
| Learning rate | Step size. Default 1e-4. Batch size 2. | `LR=`, `BATCH=` |
| Loss | How far the model's text is from the target's. Train loss and val loss are logged. | `adapters/<name>/train.log`, `train-stats.txt`; the bench doc's provenance table |
| Fuse | Merge the adapter into the full-precision base, then copy the base's tokenizer files over. | `make fuse` → `~/edgecdss-train/fused/<adapter>` |
| GGUF | The file format Ollama runs. | `make gguf` (llama.cpp `convert_hf_to_gguf.py`, f16 as a temporary file) |
| Q4_K_M | The 4-bit quantisation shipped; the f16 is deleted. | `make gguf` (`llama-quantize`) → `~/edgecdss-train/gguf/<adapter>-q4km.gguf` |
| Ship | Copy the Q4 file to the Jetson, `ollama create` it, and probe it once. It refuses if the Jetson has under 3 GB free. | `make ship TAG=edgecdss-name`, `tools/distill/jetson/ship_remote.sh` |
| Tag | The Ollama name of a shipped model. It must start with `edgecdss-`; the base and production tags are never overwritten. | `TAG=` |
| Bench | The 30-set local arm, base against the new tag, plus `run_tests.sh`. 27/27 is required. | `make bench`, `tools/distill/jetson/bench_remote.sh` → `docs/DISTILL_BENCH_<tag>.md` |
| Teacher / student | The teacher (`claude-opus-5`) writes the answers; the student (Qwen2.5-3B) learns them. | D5 (a); D6 |

**The three gotchas (dry run).**
1. Never upgrade the foundation libraries in the training venv. Install only with `pip install -r requirements.txt`.
2. Copy the tokenizer files after fuse.
3. Quantize on the Mac, and probe on the Jetson directly, with a single-line prompt.

## 7. Measurements

| Name | Meaning | Current reference value |
|---|---|---|
| `run_tests.sh` | The endpoint suite: 27 queries. None of them reaches a model. | 27/27 on every run-3 arm and on the d6check bench |
| The 30-scenario set | 30 safety-critical scenarios from the cdss-eval bank, `run_bank.py --round all`. 25 reach a model and 5 don't. | Run 3, gpt-4o-mini: 28 served / 2 held (as deployed), 30 / 0 (120 s). qwen2.5:3b: 25/5, 24/6, 26/4 over three passes |
| Served / held | Served: the answer reaches the medic. Held: a check withholds it and a hold message replaces it. | See the 30-set row |
| Specifics present | Owner-reviewed draft specifics found verbatim in served answers. Term matching, not a correctness score. | Run 3, the same 13 scenarios: claude-opus-5 37/48 (77%), gpt-4o-mini 8/48 (17%), qwen 10/44, 10/40, 9/48 |
| Latency | Server processing time on model turns: median / p95. | Run 3: gpt-4o-mini 3.2 / 4.8 s (as deployed); qwen2.5:3b 12.2–13.5 / 38.3–38.6 s |
| Deterministic identity | Answers that never reach a model must be byte-identical across arms and runs. | Run 3: 32 queries, byte-identical across all 11 as-deployed passes |
| Replay | Re-run stored answers through the changed checks, and compare against main. | 537 served answers at the time of the order |
| Newly held / newly released | Replay deltas. Every new hold is read and classified. A new release must be 0, and so must a cloud regression. | Required: 0 newly released |
| Signed entries | Contract doses the owner has signed; the only doses that serve. | 64 of 104 (d6check bench, `5053399`) |
| Fallback | A turn written by local qwen because the cloud call didn't connect in time. Attributed per row by `model_used`. | Run 3 at 8 s: 20 of 25 Opus turns and 24 of 25 gemini-3.1-pro turns were qwen. 60 s for a selected model since #88 |

| Document | Holds |
|---|---|
| [`WORK_ORDER.md`](WORK_ORDER.md) | The order of record: items, rulings, global rules, findings placement |
| `REFERENCE.md` (this page) | One-line meaning and status of every name |
| [`MULTI_MODEL_BENCHMARK_2026-09-25.md`](MULTI_MODEL_BENCHMARK_2026-09-25.md) | Run 3: nine arms, hold lists, specifics, findings 1–8 |
| [`LOCAL_LLM_BENCHMARK.md`](LOCAL_LLM_BENCHMARK.md) | Cloud vs `qwen2.5:3b`: the 2026-09-19 baseline, repeat 1, post-signing run 2. The base model's record; bench results are not appended to it. |
| `DISTILL_BENCH_<tag>.md` | One per `make bench`: before/after against `qwen2.5:3b` |
| [`FEEDBACK_REVIEW_2026-09-03.md`](FEEDBACK_REVIEW_2026-09-03.md) | The field feedback behind A3 and C1 |
| [`A6_CONTRAINDICATED_PROCEDURES_DESIGN.md`](A6_CONTRAINDICATED_PROCEDURES_DESIGN.md) | A6's proposal: the procedure table, matching, false-positive risks, signing |
| [`TESTING_LOCAL.md`](TESTING_LOCAL.md) | Manual checks for the offline and hybrid modes on a second server |
| [`tools/distill/README.md`](../tools/distill/README.md) | The D6 toolchain: install, targets, isolation, the three gotchas |

## 8. Standing rules

- One work item per PR. Stop for the owner's review after each. Never merge.
- A items: the failing test is committed first, on its own, then the fix.
- Never loosen a gate. The dose check stays indication-specific.
- After every safety change, replay the served answers: each newly held answer read and classified, 0 newly released, 0 cloud regressions. D items also need byte-identical deterministic answers.
- Every PR reports the files touched, the suite count, and a live harness against a second uvicorn, never the live service.
- Never restart the live service or touch its `.env`.
- Every benchmark row records the git commit, the signed-entry count, the Ollama version, the power mode and the kernel.
- Format and label changes don't change what is decided, held or dosed.
- Don't merge an unsigned state; re-sign in the same PR. A missing contract holds; never serve an uncited value. Signing is the owner's act.
- Benchmarks: if a key is missing or a model errors, record it and skip. Don't substitute.
- Never ship f16.
- The training venv is pinned: install only from `requirements.txt`, never with the upgrade flag.
- Secrets never go in GitHub: no `.env`, no keys.
- Each machine has one job: the Mac trains and quantizes, and the Jetson serves, probes and benches.

## 9. Found, not yet placed

Mirrors the list of the same name in `WORK_ORDER.md`.

| Finding | Found in |
|---|---|
| The validator holds a correct post-tube sedation answer ("we tubed him"). | #86 |
| A correct signed dose is held when the question names the indication, not the drug (epinephrine 1 mg in asystole). Fixing it releases holds and needs an owner ruling. | #97 |
| A ketamine drip for pain gets the RSI bundle. | #86 |
| A unitless weight ("he is 150") silently skips the RSI card. | #86 |
| "Absent lung sounds" is not read as a tension sign, so a chest GSW in shock with that phrasing gets the DCR card first (A1 ruling 1 says tension first). A live-log query. | #101 |
| gpt-4o hits the organisation's 30,000 TPM limit on a sequential 30-set. | Run 3 (#87) |
| The corpus was ingested from the superseded 2017 ID39; the 2026 edition is now in `jts_protocols`. Re-ingest is a separate decision. | #100 |
| The signed succinylcholine dose contract cites ID39 p.28 for contraindications the page doesn't list; ID40 p.3 does. A re-sign. | #100 |
