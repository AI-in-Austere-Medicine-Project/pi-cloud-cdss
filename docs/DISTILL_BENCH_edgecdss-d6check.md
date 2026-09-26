# Distillation bench: `edgecdss-d6check`, 2026-09-26

> Toolchain check on the 50-row dry-run set (ITERS=50). Not a candidate model; this proves the targets, not the model.

Written by `make bench` (tools/distill, D6). A measurement record: nothing was tuned between the arms.

## Setup

| | |
|---|---|
| Commit | `50533991548d6cdcd6d5205608a445e0e91003df` (`git archive` of `server/`, plus the deployed `drug_concentrations.json`) |
| Contract bank | **64 signed entries** of 104 |
| Ollama | ollama version is 0.34.2 |
| Power mode | NV Power Mode: 25W 1 |
| Kernel | 6.8.12-1021-tegra |
| Before | `qwen2.5:3b` (357c53fb659c) |
| After | `edgecdss-d6check` (12c6f6eeb690), same TEMPLATE, SYSTEM and LICENSE as the base |
| 30-scenario set | `/home/andrew/projects/cdss-eval/runs/run-tests-mm3-20260925/scenarios-30.jsonl`, sha256 `76c2bed932b7d2ae…`, `--round all` |
| Isolation | 30-set on :8123 (cdss-eval `run_bank.py`), `run_tests.sh` on a second uvicorn on :8012; no provider keys in the environment; the live service on :8000 and its `.env` untouched |

## Toolchain provenance

| | |
|---|---|
| Adapter | `d6check`: `mlx-community/Qwen2.5-3B-Instruct-4bit`, data `/Users/andrew/edgecdss-train/data-dryrun`, 50 iters, lr 0.0001, batch 2 |
| Train (Mac, mlx_lm.lora) | tok/s mean 987.5 (min 966.8, max 995.1, 5 reports); train loss 1.020 @ 10 -> 0.000 @ 50; val loss 5.045 @ 1 -> 0.000 @ 50 |
| Fused, bf16 (Mac, mlx_lm.generate, probe) | 71.239 tok/s |
| Q4_K_M GGUF | sha256 `e1183f5c8f2a3c8d…` |
| Jetson probe (ollama run --verbose) | 19.89 tok/s |

## Before / after

| Arm | 30-set served / held / sys-err | Model turns | Latency median / p95 (s) † | Generation median (s) | Generation tok/s § | Prefill tok/s § | Prompt tokens |
|---|---|---|---|---|---|---|---|
| before: `qwen2.5:3b` | 26 / 4 / 0 | 25 | 13.3 / 63.7 | 9.7 | 22.6 | 1526.9 | n/a ‡ |
| after: `edgecdss-d6check` | 26 / 4 / 0 | 25 | 49.6 / 53.4 | 33.5 | 21.9 | 1385.8 | n/a ‡ |

† Server processing time over model-reaching turns, excluding system errors.
§ One single-line ketamine probe through the Ollama API on the Jetson, `temperature 0`, `num_predict 128`, after one warm-up call: `eval_count / eval_duration` and `prompt_eval_count / prompt_eval_duration`. Not the served prompt.
‡ The harness does not wrap the local client, so served prompt tokens are not captured (as in benchmark run 3).

Models that generated the model turns: before ['local/qwen2.5:3b'], after ['local/edgecdss-d6check'].

## run_tests.sh against the new tag

**27 / 27**, required 27/27: **holds**.

## Scenarios whose outcome moved

- `H-S2`: SERVE → BLOCK
- `G-DIC-04`: BLOCK → SERVE
- `R2-HYPOTENSION-VASOACTIVE-RISK-MAP-POS`: SERVE → BLOCK
- `R2-DEPRESSED-GCS-ORAL-ROUTE-POS`: BLOCK → SERVE
