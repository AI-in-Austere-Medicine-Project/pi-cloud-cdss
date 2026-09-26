# tools/distill: D6 training toolchain

This toolchain trains a LoRA adapter on Qwen2.5-3B-Instruct from the D5 distillation set, turns it into a Q4_K_M GGUF, ships it to the Jetson's Ollama and benchmarks it against the base model. It runs on the Mac in `~/edgecdss-train`, not on the Jetson. The plan of record is `docs/WORK_ORDER.md`, item D6.

## Install

```
python3.12 -m venv ~/edgecdss-train/.venv-fresh
~/edgecdss-train/.venv-fresh/bin/pip install -r tools/distill/requirements.txt
```

Install into a fresh venv with pip install -r requirements.txt; verified on 2026-09-26 with make train ITERS=50 on the dry-run data.

Install only this way. `requirements.txt` pins the full set pip resolves for mlx, mlx-lm, transformers, tokenizers, huggingface_hub (< 2.0) and torch. torch is used only by llama.cpp's converter in `make gguf`. The Makefile uses `~/edgecdss-train/.venv-fresh` by default, and `make train` refuses to run if the venv has drifted from these pins.

## Targets

Run these from `tools/distill/`.

| Target | What it does |
|---|---|
| `make train ADAPTER=name [DATA=dir] [ITERS=600] [LR=1e-4]` | Runs a format preflight, then `mlx_lm.lora` on `mlx-community/Qwen2.5-3B-Instruct-4bit`. `DATA` defaults to `data/distill` (D5's output). The adapter goes to `~/edgecdss-train/adapters/<name>`. |
| `make fuse` | Runs `mlx_lm.fuse --dequantize` against the full-precision `Qwen/Qwen2.5-3B-Instruct`, copies the four tokenizer files from the base snapshot over the fused folder, then runs one probe generation. |
| `make gguf` | Converts to f16 with llama.cpp's `convert_hf_to_gguf.py`, runs `llama-quantize` to Q4_K_M, then deletes the f16, even if a step fails. It checks the GGUF header says Q4_K_M. |
| `make ship TAG=edgecdss-name` | Refuses if the Jetson has under 3 GB free. It refuses any file whose GGUF header is not Q4_K_M, and any file with f16 in its name. It copies the Q4 over with scp, writes the Modelfile and runs `ollama create`, then runs one single-line ketamine probe on the Jetson over ssh. |
| `make bench` | Benches on the Jetson, against a pinned `git archive` of `origin/main`. It runs the 30-scenario local arm for the base and the new tag, then `run_tests.sh` against a second uvicorn serving the new tag. It prints the before/after table and writes `docs/DISTILL_BENCH_<tag>.md`. It fails unless `run_tests.sh` gives 27/27. |

`fuse`, `gguf` and `ship` default to the adapter of the last `train`. `bench` defaults to the tag of the last `ship`. Pass `ADAPTER=` or `TAG=` to override.

### Preflight

`make train` first checks every row of `DATA/train.jsonl` and `DATA/valid.jsonl` against `fixtures/format_example.jsonl`: the same keys, the roles system, user and assistant in that order, and no empty content.

The fixture is a placeholder in the shape of `~/edgecdss-train/data-dryrun/train.jsonl`. It was written by hand for D6, because no D5 row existed on main yet. Replace it with a real D5 row once D5 lands.

### Isolation (bench)

- The 30-scenario set runs through cdss-eval `run_bank.py` on port 8123.
- `run_tests.sh` runs against a uvicorn started from the snapshot on port 8012, with its own logs and corpus copy.
- Neither port is 8000, the live service. The production `.env` is never read, and no provider key is in the environment. Both arms are local.
- Bench refuses to start if another cdss-eval run is active, because the load would distort the latencies.
- The new tag's Modelfile copies TEMPLATE, SYSTEM and LICENSE from `qwen2.5:3b`, so the two arms differ in weights only.

## The three gotchas

1. **Never upgrade the foundation libraries in this venv.** Don't pass pip's upgrade flag, and don't install anything outside `requirements.txt`. mlx, mlx-lm and transformers are pinned to a set that works together today. An upgrade silently changes training, fusing or the tokenizer.
2. **Copy the tokenizer files after fuse.** `mlx_lm.fuse` writes its own tokenizer files. `make fuse` overwrites `tokenizer.json`, `tokenizer_config.json`, `vocab.json` and `merges.txt` with the base snapshot's copies, so the GGUF gets the base model's tokenizer.
3. **Quantize on the Mac, and probe on the Jetson directly.** Never ship an f16 GGUF and quantize it with Ollama on the Jetson. Probe the shipped model with `ollama run` on the Jetson over ssh, with a single-line prompt: a multi-line quoted prompt breaks across ssh.

## Open

- **The bench is not linked from the work order yet.** Each `make bench` writes `docs/DISTILL_BENCH_<tag>.md`. Adding the link to the work order is left to the work order's owner.
