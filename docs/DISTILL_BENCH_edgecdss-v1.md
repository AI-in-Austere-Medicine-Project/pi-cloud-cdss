# Distillation bench: `edgecdss-v1`, 2026-10-01

> Regenerated on the Jetson by d6.py report from bench run edgecdss-v1-20261001T180545Z (the run on c45b210), after the run_tests.sh bar was changed to equal the base arm's score (owner, 2026-10-01). The base arm's run_tests.sh was measured afterwards on the same pinned snapshot and Ollama build, by the same procedure bench_remote.sh now uses. The toolchain-provenance section (stages.json) is written on the Mac and is not in this copy. Read with the findings in the work order (D6): in the after arm the validator was edgecdss-v1 itself and returned invalid output on 23 of 24 calls. Specifics present and answer length were added on 2026-10-02 by scoring these same run folders (cdss-eval runs/d6-edgecdss-v1-20261001T180545Z-base and -tag) against benchmark run 3's specifics_final.json (sha256 6795aab906a7f6bb…), tokenizer Qwen/Qwen2.5-3B-Instruct tokenizer.json; nothing was rerun.

Written by `make bench` (tools/distill, D6). A measurement record: nothing was tuned between the arms.

## Setup

| | |
|---|---|
| Commit | `c45b2101a01d394df73d6b5fe4a179798a9d9659` (`git archive` of `server/`, plus the deployed `drug_concentrations.json`) |
| Contract bank | **68 signed entries** of 108 |
| Ollama | ollama version is 0.34.2 |
| Power mode | NV Power Mode: 25W 1 |
| Kernel | 6.8.12-1021-tegra |
| Before | `qwen2.5:3b` (357c53fb659c) |
| After | `edgecdss-v1` (c72306bcc72d), same TEMPLATE, SYSTEM and LICENSE as the base |
| 30-scenario set | `/home/andrew/projects/cdss-eval/runs/run-tests-mm3-20260925/scenarios-30.jsonl`, sha256 `76c2bed932b7d2ae…`, `--round all` |
| Isolation | 30-set on :8123 (cdss-eval `run_bank.py`), `run_tests.sh` on a second uvicorn on :8012; no provider keys in the environment; the live service on :8000 and its `.env` untouched |

## Before / after

| Arm | 30-set served / held / sys-err | Model turns | Latency median / p95 (s) † | Generation median (s) | Generation tok/s § | Prefill tok/s § | Prompt tokens |
|---|---|---|---|---|---|---|---|
| before: `qwen2.5:3b` | 28 / 2 / 0 | 24 | 13.1 / 41.6 | 8.1 | 22.6 | 1510.5 | n/a ‡ |
| after: `edgecdss-v1` | 29 / 1 / 0 | 24 | 30.7 / 53.5 | 16.8 | 21.0 | 1421.7 | n/a ‡ |

† Server processing time over model-reaching turns, excluding system errors.
§ One single-line ketamine probe through the Ollama API on the Jetson, `temperature 0`, `num_predict 128`, after one warm-up call: `eval_count / eval_duration` and `prompt_eval_count / prompt_eval_duration`. Not the served prompt.
‡ The harness does not wrap the local client, so served prompt tokens are not captured (as in benchmark run 3).

Models that generated the model turns: before ['local/qwen2.5:3b'], after ['local/edgecdss-v1'].

## Specifics present and answer length

| Arm | Specifics present, same scenarios | Specifics present, all served | Mean answer length (tokens) |
|---|---|---|---|
| before: `qwen2.5:3b` | 20 / 71 (28%) | 32 / 93 (26 scenarios) | 301.0 (n=22) |
| after: `edgecdss-v1` | 24 / 71 (34%) | 37 / 97 (27 scenarios) | 416.7 (n=23) |

Specifics present counts benchmark run 3's specifics found verbatim (term or match term, case-insensitive, on word boundaries) in served answers, by run 3's method (docs/MULTI_MODEL_BENCHMARK_2026-09-25.md). It is not a correctness score. Same scenarios: the 20 model-reaching scenarios both arms served that have specifics (G-ADV-04, G-BRN-06, G-DIC-01, G-MTN-01, G-MTN-03, G-MTN-04, G-MTN-05, G-TRA-07, G-TYP-02, G-TYP-06, G-TYP-07, H-IM-05, H-S1-a, H-S1-b, H-S2, R2-BRADYCARDIA-AV-NODAL-BLOCKER-POS, R2-DEPRESSED-GCS-ORAL-ROUTE-POS, R2-HYPOGLYCAEMIA-ORAL-ROUTE-POS, R2-HYPOGLYCAEMIA-ORAL-ROUTE-UNLABELLED, R2-HYPOTENSION-VASOACTIVE-RISK-MAP-POS). All served: each arm's served answers with specifics, deterministic ones included, so the denominators differ.

Answer length: the full served text of each arm's served model answers, in tokens by the base model's tokenizer (no special tokens). Server-added lines (a patient-reset or cut-off banner) are counted.

## run_tests.sh against the new tag

**28 / 29**; base arm `qwen2.5:3b`: 28 / 29 (measured). The bar is equal to the base arm on the same snapshot: **holds**.

## Scenarios whose outcome moved

- `G-DIC-04`: BLOCK → SERVE

### run_tests.sh failures

```
❌ FAIL [40903 ms] B1: adult IV fentanyl cites ID61 — unexpected block: Issues identified:
```
