# Distillation bench: `edgecdss-v3`, 2026-10-09

## Result: the bar fails

**`run_tests.sh` 28 / 29 against the base arm's 29 / 29 on the same snapshot. The bar (equal to the base arm) does not hold.** The one failure, B1 ("80 kg adult, severe pain from a femur fracture, fentanyl IV"), is held by the deterministic free-text dose check, correctly: v3's GIVE line carried the signed "fentanyl IV: 50 mcg", and its DO THIS step then read "Draw 50 mcg of fentanyl IV **(50 mg)**", a thousandfold unit error; it also added an unasked "Naloxone (0.4 mg IV or IM)". Hold text: "The answer stated naloxone 0.4 mg with no signed naloxone dose for this question …" and "The answer stated fentanyl 50 mg, which is not the signed fentanyl dose for this patient …".

**On the 30-set, v3 served none of its 23 model answers.** 19 of the 23 were held as "Validator unavailable": under `CDSS_LLM_PROVIDER=local` the validator is the generator model (`providers.validator_model()`), and v3, like v1, answers the validator prompt with a field card ("**BRIEF** …"). Since A19 that fails closed. The other 4 were held by the deterministic checks. The 7 served rows are the deterministic and pre-gate rows, identical in every arm. So the gated specifics and length columns below are empty for v3, and the comparison that says anything about v3's answers is the ungated one (the generator's text before the gate), below.

## Same snapshot: `qwen2.5:3b`, `edgecdss-v1`, `edgecdss-v3`

All arms on `b8902c1`, same Ollama, power mode and kernel, `CDSS_LOCAL_NUM_CTX` 8192. v1 was rerun for this doc (`bench_remote.sh edgecdss-v1`, run `edgecdss-v1-20261009T124846Z`), which also ran the base a second time. v1's own bench doc is not comparable: it ran on `c45b210`, before A22 (generator prompt cut to ~2,050 tokens), D2 and D3.

| | `qwen2.5:3b` pass 1 | `qwen2.5:3b` pass 2 | `edgecdss-v1` | `edgecdss-v3` |
|---|---|---|---|---|
| `run_tests.sh` | 29 / 29 | 29 / 29 | 28 / 29 (B1) | 28 / 29 (B1) |
| B1 held by | — | — | the validator: unreadable verdict (deterministic checks passed) | **the deterministic dose check** ("fentanyl 50 mg", unasked naloxone) |
| 30-set served / held / sys-err | 23 / 7 / 0 | 22 / 8 / 0 | 7 / 23 / 0 | 7 / 23 / 0 |
| Model answers served | 16 of 23 | 15 of 23 | 0 of 23 | 0 of 23 |
| Validator verdict unreadable | 0 of 23 | 0 of 23 | **20 of 23** | **19 of 23** |
| Model answers failing the deterministic checks | 7 | 8 | 3 | 4 |
| Specifics present, generator text, ungated ¶ | 6 / 74 (8%) | 4 / 74 (5%) | 11 / 74 (15%) | **16 / 74 (22%)** |
| Answer length, generator text, tokens: median / mean / p95 ¶ | 79 / 73 / 136 | 84 / 74 / 130 | 261 / 260 / 381 | 255 / 245 / 355 |
| Latency median / p95 (s) † | 9.0 / 15.5 | 8.4 / 17.4 | 34.1 / 52.1 | 28.2 / 34.6 |
| Generation median (s) | 5.3 | 5.2 | 17.1 | 14.1 |

¶ Ungated: the generator's raw text (`instrument.jsonl` `generator_raw`, one call per turn in every arm) on each model-reaching turn, whether or not it was served. Specifics by run 3's list and method (`d6.specifics_present`), over the 21 model-reaching scenarios that have specifics, the same 21 in every arm. Length by the base model's tokenizer (`d6.token_counter`). Not a correctness score, and not what a medic would have seen.

† Server processing time over model-reaching turns. The v1 and v3 latency includes their validator call, which writes a field card instead of a short JSON verdict, so it is longer than a working validator's would be.

- **Against `qwen2.5:3b`:** more specifics in what it writes (16 / 74 against 6 and 4), answers about 3× longer (median 255 tokens against 79–84), latency about 3× (28.2 s against 8.4–9.0 s median). It passes the deterministic checks more often (4 failures against 7 and 8), but nothing it wrote was served.
- **Against v1, same snapshot:** more specifics (16 against 11), slightly shorter (median 255 against 261, p95 355 against 381), faster (28.2 / 34.6 s against 34.1 / 52.1 s), one more deterministic failure (4 against 3). Same validator failure (19 against 20 unreadable), same `run_tests.sh` score, but B1 now fails on what the generator wrote, not on the validator.
- **Base variance:** the base's two passes differ on 7 scenarios' outcomes and in which answers fail the deterministic checks (7 and 8, different sets). Differences of one or two in these counts are within one model's pass-to-pass spread.

## Findings (not fixed here)

1. **v3 cannot be the offline validator.** The same finding as v1 (work order, D6, v1 bench finding 1). Before A19 it served unchecked answers; it now holds them, so in offline mode v3 as `CDSS_LLM_MODEL` would hold nearly every model answer. Benching the generator alone needs a separate local validator model (e.g. `qwen2.5:3b`), which `providers.validator_model()` does not offer under `CDSS_LLM_PROVIDER=local`. Owner to place.
2. **B1: a mcg/mg slip next to a correct signed dose.** v3 copied the signed fentanyl 50 mcg into GIVE and wrote "(50 mg)" in the step that draws it. The deterministic check held it. Where the "(50 mg)" comes from is not known.
3. **The ship probe's answer invents a dosing rule.** With `ALLOWED_DOSES: ketamine IV 5 mg (0.2 mg/kg x 25 kg)`, v3 (`gguf/edgecdss-v3-probe.txt`) wrote "Dosing per the rule of two (0.2 mg/kg): Minimum 5 mg, Maximum: 0.4 mg/kg x 25 kg = 10 mg", and "100 mg/500 ml (2 mg/ml) … 1–2 vials". The 10 mg and the concentration are not in the allowed doses. The probe is not gated, and it is not the served prompt.
4. **v3's validator-role output also states clinical content.** On H-S1-a its "verdict" was a card with "10 units RBCs and 10 units WB within 2 hours of injury; stop at 40 units total without a scan". Not served (held as unreadable). Recorded because a validator that writes cards would put such text into logs.

Written by `make bench` (tools/distill, D6). A measurement record: nothing was tuned between the arms.

## Setup

| | |
|---|---|
| Commit | `b8902c118cd85497f560e4c6c64164418667468a` (`git archive` of `server/`, plus the deployed `drug_concentrations.json`) |
| Contract bank | **68 signed entries** of 108 |
| Ollama | ollama version is 0.34.2 |
| Power mode | NV Power Mode: 25W 1 |
| Kernel | 6.8.12-1021-tegra |
| Before | `qwen2.5:3b` (357c53fb659c) |
| After | `edgecdss-v3` (93a43d964fff), same TEMPLATE, SYSTEM and LICENSE as the base |
| 30-scenario set | `/home/andrew/projects/cdss-eval/runs/run-tests-mm3-20260925/scenarios-30.jsonl`, sha256 `76c2bed932b7d2ae…`, `--round all` |
| Isolation | 30-set on :8123 (cdss-eval `run_bank.py`), `run_tests.sh` on a second uvicorn on :8012; no provider keys in the environment; the live service on :8000 and its `.env` untouched |

## Toolchain provenance

| | |
|---|---|
| Adapter | `v3`: `mlx-community/Qwen2.5-3B-Instruct-4bit`, data `/Users/andrew/edgecdss-train/data-v3`, 300 iters, lr 0.0001, batch 1 |
| Train (Mac, mlx_lm.lora) | tok/s mean 852.0 (min 830.2, max 885.0, 30 reports); train loss 2.071 @ 10 -> 0.366 @ 300; val loss 2.880 @ 1 -> 0.625 @ 300 |
| Fused, bf16 (Mac, mlx_lm.generate, probe) | 71.182 tok/s |
| Q4_K_M GGUF | sha256 `a5a24a6442d076d4…` |
| Jetson probe (ollama run --verbose) | 20.67 tok/s |

## Before / after

| Arm | 30-set served / held / sys-err | Model turns | Latency median / p95 (s) † | Generation median (s) | Generation tok/s § | Prefill tok/s § | Prompt tokens |
|---|---|---|---|---|---|---|---|
| before: `qwen2.5:3b` | 23 / 7 / 0 | 23 | 9.0 / 15.5 | 5.3 | 22.6 | 1512.5 | n/a ‡ |
| after: `edgecdss-v3` | 7 / 23 / 0 | 23 | 28.2 / 34.6 | 14.1 | 21.1 | 1425.4 | n/a ‡ |

† Server processing time over model-reaching turns, excluding system errors.
§ One single-line ketamine probe through the Ollama API on the Jetson, `temperature 0`, `num_predict 128`, after one warm-up call: `eval_count / eval_duration` and `prompt_eval_count / prompt_eval_duration`. Not the served prompt.
‡ The harness does not wrap the local client, so served prompt tokens are not captured (as in benchmark run 3).

Models that generated the model turns: before ['local/qwen2.5:3b'], after ['local/edgecdss-v3'].

## Specifics present and answer length

| Arm | Specifics present, same scenarios | Specifics present, all served | Mean answer length (tokens) |
|---|---|---|---|
| before: `qwen2.5:3b` | 0 / 0 | 19 / 77 (21 scenarios) | 92.5 (n=16) |
| after: `edgecdss-v3` | 0 / 0 | 16 / 26 (7 scenarios) | — (n=0) |

Specifics present counts benchmark run 3's specifics found verbatim (term or match term, case-insensitive, on word boundaries) in served answers, by run 3's method (docs/MULTI_MODEL_BENCHMARK_2026-09-25.md). It is not a correctness score. Same scenarios: the 0 model-reaching scenarios both arms served that have specifics (none). All served: each arm's served answers with specifics, deterministic ones included, so the denominators differ.

Answer length: the full served text of each arm's served model answers, in tokens by the base model's tokenizer (no special tokens). Server-added lines (a patient-reset or cut-off banner) are counted.

## run_tests.sh against the new tag

**28 / 29**; base arm `qwen2.5:3b`: 29 / 29 (measured). The bar is equal to the base arm on the same snapshot: **FAILS**.

## Scenarios whose outcome moved

- `H-S1-a`: SERVE → BLOCK
- `H-IM-06`: SERVE → BLOCK
- `G-TRA-07`: SERVE → BLOCK
- `G-BRN-06`: SERVE → BLOCK
- `G-MTN-01`: SERVE → BLOCK
- `G-MTN-03`: SERVE → BLOCK
- `G-MTN-05`: SERVE → BLOCK
- `G-TYP-02`: SERVE → BLOCK
- `G-TYP-06`: SERVE → BLOCK
- `G-TYP-07`: SERVE → BLOCK
- `G-DIC-01`: SERVE → BLOCK
- `G-ADV-04`: SERVE → BLOCK
- `G-ADV-10`: SERVE → BLOCK
- `R2-HYPOTENSION-VASOACTIVE-RISK-MAP-POS`: SERVE → BLOCK
- `R2-BRADYCARDIA-AV-NODAL-BLOCKER-POS`: SERVE → BLOCK
- `R2-HYPOGLYCAEMIA-ORAL-ROUTE-POS`: SERVE → BLOCK

### run_tests.sh failures

```
❌ FAIL [39437 ms] B1: adult IV fentanyl cites ID61 — unexpected block: Issues identified:
```
