# D6: distillation training toolchain. Runs on the Mac, in ~/edgecdss-train.
#
#   make train ADAPTER=name [DATA=dir] [ITERS=600] [LR=1e-4]
#   make fuse   [ADAPTER=name]            (defaults to the last trained adapter)
#   make gguf   [ADAPTER=name]
#   make ship   TAG=edgecdss-name [ADAPTER=name]
#   make bench  [TAG=edgecdss-name]       (defaults to the last shipped tag)
#
# See README.md for the rules and the three gotchas.

# macOS ships GNU Make 3.81, which has no .ONESHELL or .SHELLFLAGS. So each
# recipe below is one shell command (joined with `; \`) that starts with $(STRICT).
SHELL := /bin/bash
STRICT := set -euo pipefail;
.SILENT:

HERE      := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO      := $(abspath $(HERE)/../..)
WORK      ?= $(HOME)/edgecdss-train
VENV      ?= $(WORK)/.venv
PY        := $(VENV)/bin/python
LLAMA_CPP ?= $(HOME)/llama.cpp
JETSON    ?= jetson

BASE_4BIT ?= mlx-community/Qwen2.5-3B-Instruct-4bit
BASE_FULL ?= Qwen/Qwen2.5-3B-Instruct
BASE_TAG  ?= qwen2.5:3b

ITERS ?= 600
LR    ?= 1e-4
BATCH ?= 2
DATA  ?= $(REPO)/data/distill
# A ~ typed on the make command line reaches make unexpanded under zsh.
DATA_DIR := $(patsubst ~/%,$(HOME)/%,$(DATA))

FIXTURE := $(HERE)/fixtures/format_example.jsonl
TOKENIZER_FILES := tokenizer.json tokenizer_config.json vocab.json merges.txt
MIN_FREE_BYTES := 3000000000
RT_EXPECT ?= 27

# Strips Ollama's spinner frames and ANSI codes from captured output.
DESPIN := perl -CS -pe 's/[\x{2800}-\x{28FF}] ?//g; s/\e\[[0-9;?]*[a-zA-Z]//g'

# One line, no quotes: it is passed to `ollama run` over ssh. `ssh -n` everywhere:
# with stdin open, `ollama run` reads stdin into the prompt and blocks forever.
PROBE_TIMEOUT ?= 300
PROBE_SYSTEM := You write EdgeCDSS field cards. Use only the dose in ALLOWED_DOSES.
PROBE := ALLOWED_DOSES: ketamine IV 5 mg (0.2 mg/kg x 25 kg). Question: 25 kg child, femur fracture, ketamine IV for pain

# fuse, gguf, ship and bench default to the adapter and tag of the last train and ship.
STATE := $(WORK)/.d6-state
ADAPTER ?= $(shell cat $(STATE)/adapter 2>/dev/null)
TAG     ?= $(shell cat $(STATE)/tag 2>/dev/null)

ADAPTER_DIR := $(WORK)/adapters/$(ADAPTER)
FUSED_DIR   := $(WORK)/fused/$(ADAPTER)
Q4          := $(WORK)/gguf/$(ADAPTER)-q4km.gguf
F16         := $(WORK)/gguf/$(ADAPTER)-f16.tmp.gguf
BENCH_DIR   := $(WORK)/bench

.PHONY: preflight train fuse gguf ship bench

need-adapter = test -n "$(ADAPTER)" || { echo "ADAPTER is not set and no adapter has been trained yet" >&2; exit 2; }
need-tag = case "$(TAG)" in edgecdss-*) ;; *) echo "TAG must start with edgecdss- (got '$(TAG)'); the base and production tags are never overwritten" >&2; exit 2;; esac

preflight:
	$(STRICT) if grep -n -e '[-]U' $(HERE)/Makefile $(HERE)/README.md; then echo "preflight: the upgrade flag appears above; remove it" >&2; exit 2; fi; \
	$(PY) $(HERE)/d6.py pins $(HERE)/requirements.txt; \
	$(PY) $(HERE)/d6.py format $(FIXTURE) $(DATA_DIR)

train: preflight
	$(STRICT) $(need-adapter); \
	if [ -e "$(ADAPTER_DIR)/adapters.safetensors" ] && [ -z "$(FORCE)" ]; then echo "train: $(ADAPTER_DIR) already holds a trained adapter; pick a new ADAPTER or pass FORCE=1" >&2; exit 2; fi; \
	mkdir -p "$(ADAPTER_DIR)" "$(STATE)"; \
	echo "train: $(ADAPTER) on $(DATA_DIR), $(ITERS) iters, lr $(LR), batch $(BATCH), base $(BASE_4BIT)"; \
	$(VENV)/bin/mlx_lm.lora --model $(BASE_4BIT) --train --data "$(DATA_DIR)" \
	    --iters $(ITERS) --learning-rate $(LR) --batch-size $(BATCH) \
	    --adapter-path "$(ADAPTER_DIR)" 2>&1 | tee "$(ADAPTER_DIR)/train.log"; \
	$(PY) $(HERE)/d6.py train-stats "$(ADAPTER_DIR)/train.log" | tee "$(ADAPTER_DIR)/train-stats.txt"; \
	echo "$(ADAPTER)" > "$(STATE)/adapter"

fuse:
	$(STRICT) $(need-adapter); \
	test -f "$(ADAPTER_DIR)/adapters.safetensors" || { echo "fuse: no adapter at $(ADAPTER_DIR)" >&2; exit 2; }; \
	rm -rf "$(FUSED_DIR)"; \
	$(VENV)/bin/mlx_lm.fuse --model $(BASE_FULL) --adapter-path "$(ADAPTER_DIR)" \
	    --save-path "$(FUSED_DIR)" --dequantize; \
	snap=$$($(PY) -c "from huggingface_hub import snapshot_download as s; print(s('$(BASE_FULL)', local_files_only=True))"); \
	for f in $(TOKENIZER_FILES); do cp "$$snap/$$f" "$(FUSED_DIR)/$$f"; done; \
	echo "fuse: $(FUSED_DIR), tokenizer files copied from $$snap"; \
	$(VENV)/bin/mlx_lm.generate --model "$(FUSED_DIR)" --max-tokens 64 \
	    --system-prompt "$(PROBE_SYSTEM)" --prompt "$(PROBE)" 2>&1 | tee "$(FUSED_DIR)/d6-probe.txt"

gguf:
	$(STRICT) $(need-adapter); \
	test -f "$(FUSED_DIR)/config.json" || { echo "gguf: no fused model at $(FUSED_DIR); run make fuse" >&2; exit 2; }; \
	mkdir -p "$(WORK)/gguf"; \
	trap 'rm -f "$(F16)"' EXIT; \
	$(PY) $(LLAMA_CPP)/convert_hf_to_gguf.py "$(FUSED_DIR)" --outfile "$(F16)" --outtype f16; \
	$(LLAMA_CPP)/build/bin/llama-quantize "$(F16)" "$(Q4)" Q4_K_M; \
	rm -f "$(F16)"; \
	$(PY) $(HERE)/d6.py gguf-type "$(Q4)" $(LLAMA_CPP); \
	shasum -a 256 "$(Q4)" | tee "$(Q4).sha256"

ship:
	$(STRICT) $(need-adapter); \
	$(need-tag); \
	case "$(Q4)" in *[fF]16*) echo "ship: refusing a file named f16" >&2; exit 2;; esac; \
	$(PY) $(HERE)/d6.py gguf-type "$(Q4)" $(LLAMA_CPP); \
	free=$$(ssh -n $(JETSON) 'df -B1 --output=avail "$$HOME" /usr/share/ollama | tail -n +2 | sort -n | head -1'); \
	echo "ship: Jetson has $$free bytes free (need $(MIN_FREE_BYTES))"; \
	if [ "$$free" -lt $(MIN_FREE_BYTES) ]; then echo "ship: refusing, the Jetson has under 3 GB free" >&2; exit 2; fi; \
	ssh -n $(JETSON) 'mkdir -p edgecdss-models'; \
	scp "$(Q4)" $(JETSON):edgecdss-models/$(TAG)-q4km.gguf; \
	scp $(HERE)/jetson/ship_remote.sh $(JETSON):edgecdss-models/ship_remote.sh; \
	ssh -n $(JETSON) 'bash edgecdss-models/ship_remote.sh $(TAG) $(BASE_TAG)'; \
	mkdir -p "$(STATE)"; \
	echo "$(TAG)" > "$(STATE)/tag"; \
	echo "$(ADAPTER)" > "$(STATE)/tag-adapter"; \
	echo "ship: probe on the Jetson"; \
	ssh -n $(JETSON) "timeout $(PROBE_TIMEOUT) ollama run $(TAG) --verbose --nowordwrap '$(PROBE)'" 2>&1 | $(DESPIN) | tee "$(WORK)/gguf/$(TAG)-probe.txt" \
	    || { echo "ship: the probe failed or ran past $(PROBE_TIMEOUT) s" >&2; exit 2; }

bench:
	$(STRICT) $(need-tag); \
	adapter=$$(cat "$(STATE)/tag-adapter" 2>/dev/null || echo "$(ADAPTER)"); \
	out="$(REPO)/docs/DISTILL_BENCH_$(TAG).md"; \
	if [ -e "$$out" ] && [ -z "$(FORCE)" ]; then echo "bench: $$out exists; pass FORCE=1 to replace it" >&2; exit 2; fi; \
	sha=$$(git -C "$(REPO)" rev-parse origin/main); \
	stamp=$$(date -u +%Y%m%dT%H%M%SZ); \
	echo "bench: $(TAG) vs $(BASE_TAG) at $$sha"; \
	scp $(HERE)/jetson/bench_remote.sh $(JETSON):edgecdss-models/bench_remote.sh; \
	ssh -n $(JETSON) "bash edgecdss-models/bench_remote.sh $(TAG) $(BASE_TAG) $$sha $$stamp '$(PROBE)'"; \
	mkdir -p "$(BENCH_DIR)"; \
	scp -rq $(JETSON):edgecdss-distill-bench/$(TAG)-$$stamp "$(BENCH_DIR)/"; \
	$(PY) $(HERE)/d6.py stages "$(WORK)" "$$adapter" "$(TAG)" > "$(BENCH_DIR)/$(TAG)-$$stamp/stages.json"; \
	$(PY) $(HERE)/d6.py report "$(BENCH_DIR)/$(TAG)-$$stamp" --out "$$out" --rt-expect $(RT_EXPECT) \
	    --stages "$(BENCH_DIR)/$(TAG)-$$stamp/stages.json" $(if $(NOTE),--note "$(NOTE)")
