# Voice warm-up, GPU retry, and the V1 table with Kokoro on the GPU (2026-10-27)

**Owner (2026-10-27):** "Live: GPU confirmed, voice works on both models. One PR, two items: 1. Warm-up: load Kokoro and synthesise a short sentence at service start, so first listen after a restart isn't 6 s. Test pins voice_device gpu within 30 s of start. 2. Re-run the V1 latency table on the live service with Kokoro resident on the GPU and compare model-answer median to 12.5 s; report any slowdown."

**Owner, added to the same PR:** "(a) after a GPU fallback, Kokoro retries the GPU on the next call rather than staying on CPU until restart; (b) /status reports the fallback with its reason and time. Record the memory budget in the PR: qwen + Kokoro fits; qwen + edgecdss-v3 + Kokoro is the case that spills."

## 1. Warm-up at service start

- **`tts.warm_up()`** synthesises `WARM_UP_TEXT`, "Reassess in five minutes.". It runs in a thread from a startup hook, so `/health` answers while the model loads.
  - It never raises. A failure leaves the voice to load on the first listen. A GPU synthesis failure ends on the CPU, as in any listen (below).
  - `CDSS_KOKORO_WARMUP=0` turns it off.
- **Tests** (`tests/test_voice_warmup.py`):
  - With a stand-in engine: `voice_device` is `gpu` within 30 s of start; `/health` answers while the model is still loading; a failed GPU warm-up ends on the CPU with the reason; there is no warm-up when voice isn't configured or when it is turned off.
  - On the Jetson (`CDSS_TEST_KOKORO_GPU=1`): a real uvicorn on the real model reports `voice_device: gpu` within 30 s. It passed in 7.4 s, with qwen2.5:3b loaded in Ollama.
- **Measured on the Jetson** (:8012 from this branch, service venv, `onnxruntime-gpu` 1.24.0; two runs each, the same both times). The first listen is "Give fentanyl, fifty micrograms, intravenously. Watch respiratory rate.", streamed:

| | `/health` first answers | First listen, first audio |
|---|---|---|
| Warm-up off | 2.7 s | 3.5 s |
| **Warm-up on** | 5.1 s | **0.69 s** |

- `/health` comes up 2.4 s later: the model load, in its own thread, competes with the server's start for the CPU. The watchdog checks every 3 minutes.
- The live first listen this morning, 6.1 s, was the same cold load as "warm-up off", plus whatever else was running on the box at the time.

## 2. A GPU fallback is per call, retried next time, and reported

- **Before:** one GPU synthesis failure moved Kokoro to the CPU until the service restarted. Live at 17:31 UTC a 139-character listen took 21.6 s: the GPU failed in a Conv node (`/decoder/decoder/generator/resblocks.3/convs1.1/Conv`), then the CPU model loaded and synthesised. The voice stayed on the CPU until the 19:13 restart.
- **Now:**
  - A GPU synthesis failure finishes that sentence on a CPU model. The CPU model is loaded on the first failure and then kept.
  - The GPU model is not discarded, and the next call tries it first.
  - When the GPU works again, the voice is back on it with no reload.
- **`/status voice_device`:**
  - `device`: where the last synthesis ran.
  - `note`: why the CPU, when it is the CPU.
  - `last_fallback`: `{"reason", "at"}`, at in UTC to the second, or `null`.
  - `gpu_fallbacks`: count since start.
- **Cost under steady memory pressure:** every sentence pays the failed GPU attempt before the CPU, when it used to pay it once. The real failure's cost has not been measured on its own. It is part of the live 21.6 s, which also included loading the CPU model.

## 3. The V1 table on the live service, Kokoro resident on the GPU

- **Method:** V1's method and items (EVALUATION_SET_30 `76c2bed9…`, batch 2 and 3, the magnesium hold; one warm-up excluded), sent to the **live service on :8000**. It runs main `25b7233` (#190), `onnxruntime-gpu` 1.24.0, and qwen2.5:3b as generator and validator.
  - Kokoro was loaded on the GPU by one `/speak` before the run and was still on the GPU after it.
  - The run took 19:26:52–19:31:38 UTC, with no other session and no listen in that window.
  - Timings are the session log's, joined by `query_id` (`tools/latency_report.py`).
  - `latency_run.py` now takes `CDSS_LATENCY_BASE` and `CDSS_ACCESS_TOKEN`.

### Model answers (n = 25)

| Stage | V1 (2026-10-25, :8012) median / p90 | **Now, live, Kokoro on GPU** median / p90 |
|---|---|---|
| pre-gate | 66 ms / 117 ms | 85 ms / 164 ms |
| retrieval | 462 ms / 492 ms | **166 ms / 190 ms** |
| doses built | 41 ms / 46 ms | 33 ms / 47 ms |
| LLM to first token | 1.56 s / 2.60 s | 1.56 s / 2.58 s |
| LLM first to last token | 7.07 s / 9.46 s | 6.67 s / 8.47 s |
| validator | 3.28 s / 4.54 s | 2.94 s / 4.51 s |
| checks + finalise + send | 5 ms / 11 ms | 12 ms / 40 ms |
| **total** | **12.54 s / 16.19 s** | **10.52 s / 15.16 s** |

### Deterministic answers (n = 26)

| | V1 median / p90 | Now median / p90 |
|---|---|---|
| total | 62 ms / 89 ms | 91 ms / 124 ms |

- **No slowdown from Kokoro resident on the GPU.** The model-answer median is 10.52 s against 12.5 s. Every model stage is the same or faster.
- **Retrieval is 0.3 s faster.** The pinned CPU embedder keeps one ONNX session. Main before V3 rebuilt Chroma's stock embedder per call (round 3's retrieval check: 0.46 s against 1.67 s per query).
- **Generation and validator are 0.3–0.4 s faster.** This is not attributed: it may be the qwen keep-alive or other runs on the box during V1. Neither run was repeated.
- **Deterministic answers are about 30 ms slower** (pre-gate 66 → 85 ms). That is within the run-to-run noise of a live box. Not chased.
- **What this run does not measure:** a listen synthesising on the GPU *while* qwen generates. No listen ran during the run, so this shows Kokoro resident, not Kokoro working at the same time.

## Memory budget (Orin Nano, 7.5 GB unified memory shared by CPU and GPU, 2 GB swap)

| Resident | Size | Source |
|---|---|---|
| System, desktop, services (Claude Code, cloudflared, tailscale, snapd…) | about 0.9 GB | `free` less the processes below, 2026-10-27 |
| EdgeCDSS server, Kokoro not loaded | about 0.15 GB | live RSS after the 19:13 restart |
| Kokoro on the CPU | about 0.6 GB server RSS | :8012, round 3 |
| **Kokoro on the GPU** | **about 1.0 GB more** than on the CPU (server RSS 1.66 GB; system used +0.86 GB) | :8012, round 3 |
| qwen2.5:3b in Ollama, 8,192 context | 2.4 GB (`ollama ps`); llama-server RSS 3.07 GB | live, 2026-10-27 |
| edgecdss-v3 in Ollama | 1.9 GB on disk, the same as qwen2.5:3b; loaded about 2.4 GB at the same context | estimate. It was not loaded for this, to avoid pushing the live box into swap |

- **qwen + Kokoro on the GPU fits.**
  - About 0.9 + 1.7 + 3.1 = 5.7 GB.
  - Measured live: 5.35 GB used with Kokoro loaded, 5.65 GB after the V1 run. About 1.9 GB available.
- **qwen + edgecdss-v3 + Kokoro on the GPU spills.** That is about 5.7 + 2.4–3.1 = 8.1–8.8 GB, against 7.5 GB.
  - This is the 17:31 failure: an answer from edgecdss-v3, with qwen loaded as the validator.
  - The next GPU synthesis could not get its memory and failed in a Conv node.
- **What spills is the voice, not the answer.** With the retry above, each listen in that state falls to the CPU and says so in `/status`. It is back on the GPU once Ollama unloads a model (keep-alive, about 5 minutes).

## Checks

- **Suite:** 3,707 passed, 0 failed, 44 skipped.
- **Real-GPU tests** (`CDSS_TEST_KOKORO_GPU=1`, the real model): 2 passed.
- **Replay vs main `25b7233`:** 0 changed in all five sets, byte-identical (served 1,738, held 308, gate 1,408, log 4,251, pipe 833). The log set includes today's live turns, this V1 run among them.
