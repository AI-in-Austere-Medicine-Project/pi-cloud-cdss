---
license: other
license_name: qwen-research
license_link: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE
base_model: Qwen/Qwen2.5-3B-Instruct
language:
- en
pipeline_tag: text-generation
tags:
- medical
- research
- not-for-clinical-use
- gguf
---

<!-- DRAFT (2026-10-12) for the owner's review. Not published. Before any
publication: (1) the owner decides whether to publish weights at all;
(2) the training answers were written by claude-opus-5 and checked by
gpt-4o-mini, and whether those providers' terms permit publishing a model
trained on their outputs is not checked here; (3) a published repo must
include a copy of the Qwen RESEARCH LICENSE AGREEMENT and a NOTICE file. -->

# edgecdss-v3 — research artifact, not adopted

**Built with Qwen.**

Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) Alibaba Cloud. All Rights Reserved.

A LoRA distillation of [Qwen2.5-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) trained to write EdgeCDSS field cards. **The teacher was Anthropic's `claude-opus-5`: it wrote every training answer.** OpenAI's `gpt-4o-mini` checked each one as EdgeCDSS's validator. No human-written answers were used.

> ⚠️ **Not for clinical use, and not adopted by the project.** On the project owner's reading of its benchmark answers (2026-10-10), this model **fails**: several answers it served were clinically wrong. The project's offline model remains `qwen2.5:3b`. This card exists so the result is on the record. It is a research artifact about distillation for edge clinical decision support, and nothing more.

**Source:** [EdgeCDSS v5.0.0](https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss/releases/tag/v5.0.0) ([changelog](https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss/blob/v5.0.0/CHANGELOG.md), [safety statement](https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss/blob/v5.0.0/SAFETY.md)). **Bench record:** [`DISTILL_BENCH_edgecdss-v3-d7.md`](https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss/blob/v5.0.0/docs/DISTILL_BENCH_edgecdss-v3-d7.md) (with `qwen2.5:3b` as validator) and [`DISTILL_BENCH_edgecdss-v3.md`](https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss/blob/v5.0.0/docs/DISTILL_BENCH_edgecdss-v3.md) (as its own validator).

## Licence

This model is a derivative of Qwen2.5-3B-Instruct and is distributed under the [Qwen RESEARCH LICENSE AGREEMENT](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE): **non-commercial use (research or evaluation) only**; commercial use needs a licence from Alibaba Cloud. A copy of the agreement and a NOTICE file ship with these weights. The EdgeCDSS repository's own code is MIT; that does not apply to these weights.

## What it is

| | |
|---|---|
| Base | `Qwen/Qwen2.5-3B-Instruct` (trained on `mlx-community/Qwen2.5-3B-Instruct-4bit`) |
| Method | LoRA (`mlx_lm.lora`): rank 8, scale 20, dropout 0, 16 layers; 300 iterations, learning rate 1e-4, batch 1, gradient checkpointing, max sequence length 6656, seed 0 |
| Loss | train 2.071 → 0.366; validation 2.880 → 0.625 (iteration 300) |
| Artifact | fused, then GGUF Q4_K_M (1.93 GB), sha256 `a5a24a6442d076d4e580c4e686a10b375973f2d705f9baf781643246a53bb8c4`; Ollama tag `edgecdss-v3` (93a43d964fff) with the base model's TEMPLATE and SYSTEM |
| Teacher | **`claude-opus-5` (Anthropic)** wrote every training answer, under the EdgeCDSS system prompt; **`gpt-4o-mini` (OpenAI)** validated each one, with EdgeCDSS's deterministic checks |
| Data | 221 rows (205 train / 16 validation) from 255 field questions; 34 dropped (20 named a drug the question did not ask about, 8 changed by the pipeline, 6 held). Every row carries the full live system prompt. Questions overlapping the evaluation set were excluded by hash. **The dataset is not released.** |

## How it was evaluated

The EdgeCDSS distillation bench (`make bench`, `tools/distill`): the project's 29-case endpoint suite (`run_tests.sh`), and a signed 30-scenario evaluation set run through the full pipeline, on an NVIDIA Jetson Orin Nano (Ollama 0.34.2, 25 W).

| | `qwen2.5:3b` (base) | `edgecdss-v3` as its own validator | `edgecdss-v3`, validator `qwen2.5:3b` |
|---|---|---|---|
| `run_tests.sh` | 29 / 29 | 28 / 29 | 29 / 29 |
| 30-set model answers served (of 23) | 15–16 | 0 (19 of 23 validator replies unreadable) | 17 |
| Specifics present, same served scenarios | 4 / 39 | — | 8 / 39 |
| Mean served answer (tokens) | 87 | — | 234 |
| Latency median / p95 (s) | 8.1 / 13.0 | 28.2 / 34.6 | 16.4 / 23.5 |

Full records, as of v5.0.0: [`DISTILL_BENCH_edgecdss-v3-d7.md`](https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss/blob/v5.0.0/docs/DISTILL_BENCH_edgecdss-v3-d7.md) and [`DISTILL_BENCH_edgecdss-v3.md`](https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss/blob/v5.0.0/docs/DISTILL_BENCH_edgecdss-v3.md).

## Why it was not adopted

The counts improved on the base. The answers did not hold up. Read in full, answers the model wrote and the pipeline served included:
- "tourniquet low and loose" and debridement before control, for a fresh arterial bleed;
- "reapply" a tourniquet on loss of distal pulse;
- "Do not re-warm until professional help arrives", for a hypothermic arrest;
- "Treat as a presumed cardiac arrest … chest compressions", for an adult having a seizure;
- repositioning and "secure the tube", with no needle decompression, for a tension pneumothorax.

Other behaviour observed:
- **As a validator it is unusable:** asked for a verdict, it writes a field card instead (19 of 23 calls), sometimes stating unsigned transfusion volumes.
- **It states doses and rules no source gave it:** a "rule of two" ketamine range and a vial concentration in a bare prompt; "Draw 50 mcg of fentanyl IV (50 mg)", a thousandfold unit slip next to the correct dose.

In EdgeCDSS every such dose is held by deterministic checks; procedural advice is not, which is why the project's rule is that **benchmark counts are advisory and a distilled model ships only when every served answer has been read and none is clinically wrong.**

## Intended use

Research on distilling a large model's clinical answers into a small on-device model: what improves (specific terms, format), what does not (clinical correctness), and what the surrounding safety layer must catch.

## Out of scope

Any clinical use, any patient-facing use, any use as a validator, and any commercial use (Qwen licence).
