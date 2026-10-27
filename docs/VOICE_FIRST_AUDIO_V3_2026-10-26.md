# Voice, first audio sooner: V3, 2026-10-26

**Owner (2026-10-26):** "V3, three commits, measure after each on the same 21 items: 1. Sentence-chunked synthesis … so first audio waits only for the first sentence. 2. Run Kokoro on the GPU …; fall back to CPU if it fails. Report real-time factor both ways. 3. A spoken brief for every answer … Fixed templates, tested, no model wording in the spoken brief. Report first-audio median and p90 after each commit."

## Method

- **Items:** the 21 from V2. That's the 20 batch 2/3 harness questions plus the magnesium hold.
- **Same text for every commit.** `/query` was asked once, on a :8012 server from this branch, offline with qwen2.5:3b. Exactly what the listen button would send was saved (`tts_latency_run.py fetch`).
  - Commits 1 and 2 speak those saved payloads.
  - Commit 3 speaks the spoken brief built from the same saved answers.
  - **Live check:** a second live `/query` pass on commit 3 gave the same response text for 13 of 21. Each of those 13 carried exactly the spoken brief built offline. The other 8 differ because the model answered differently.
- **Baseline:** "whole" is V2's behaviour (one WAV, played once complete), timed on the same saved text, so the commit 1 comparison is like for like. V2's own figures (17.0 / 34.3 s first audio) came from a different model run with different answer text.
- **Timed at the HTTP client** (`tts_latency_run.py time`), one item at a time, after one warm-up:
  - **first audio:** the first sentence's WAV received;
  - **audio end:** when the last sentence ends. Each sentence plays when it has arrived and the one before has ended, plus the portal's 0.15 s breath, so a sentence that arrives late counts as a gap.
  - The browser's decode time is not included.
- **Statistics:** median and p90, with p90 linearly interpolated. No live traffic overlapped any run.
- **Commit 2** was timed from its own tree (`git archive 83cd015`), in a scratch venv that has `onnxruntime-gpu` 1.31 (PyPI, aarch64, CUDA 13) over the shared venv. Commit 3 used the same scratch venv.

## Results

| | First audio median | First audio p90 | Audio end median | Audio end p90 | Chars median / p90 |
|---|---|---|---|---|---|
| Before: whole WAV (V2 behaviour, same text) | 18.8 s | 30.4 s | 44.1 s | 69.9 s | 305 / 445 |
| **1. Sentence by sentence** | **4.2 s** | **9.5 s** | 37.8 s | 56.4 s | 305 / 445 |
| **2. GPU, else CPU** (fell back to the CPU) | **4.0 s** | **7.2 s** | 37.0 s | 55.1 s | 305 / 445 |
| **3. Spoken brief** | **3.7 s** | **7.2 s** | 14.4 s | 25.3 s | 84 / 168 |

### 1. Sentence by sentence

- **First audio:** 18.8 → 4.2 s (median). It now waits for the first sentence only. The magnesium hold starts at 2.0 s instead of 18.4 s; the epinephrine hold (B3-1) at 3.3 s instead of 38.1 s.
- **Gaps:** synthesis is a little faster than real time, but sentence lengths are uneven. A short sentence ("Held.") ends before the next long one is ready. 13 of 21 items had at least one gap: 100.5 s in total, the longest 15.5 s.
- **Audio end** improves less than first audio (44.1 → 37.8 s): playback overlaps synthesis, but the gaps eat into the saving.

### 2. The GPU, and the CPU fallback

- **The GPU could not be used on this Jetson as it stands.** The CUDA provider loads, then `cudaSetDevice` fails with CUDA error 801, "operation not supported". The same error comes from a bare `cuInit` in the CUDA driver, without onnxruntime. So the cause is GPU access for this user, not the onnxruntime build.
- **Probable cause:** the service user (`andrew`) is not in the `render` group, and cannot open `/dev/dri/renderD128` / `renderD129` or `/dev/nvgpu/igpu0/sched`. The `ollama` user is in `render`, and its GPU works (qwen2.5:3b runs 100% GPU). This could not be confirmed without sudo.
- **The fallback worked as built.** onnxruntime retried on the CPU by itself, `tts` read back the session's real providers, and `/status voice_device` said "cpu: the CUDA provider did not start …". The timing matches commit 1 within run-to-run noise.

| Real-time factor (synthesis time ÷ clip length) | CPU | GPU |
|---|---|---|
| Whole clips, 21 items | 0.77 median (0.75–0.87) | not measured: no GPU access (error 801) |
| First sentence, 21 items | 0.81 median (0.73–0.94) | not measured |
| Three fixed sentences, probe | 0.76–0.86 | not measured |

**To measure the GPU (owner):**
1. `sudo usermod -aG render andrew`, then restart `edgecdss`.
2. In the service venv, replace `onnxruntime` with `onnxruntime-gpu==1.31.0`. This is the same `onnxruntime` module that Chroma's embedder uses, so retrieval would move to the GPU too. That needs its own replay before it ships, or Chroma pinned to the CPU.
3. Run `tools/tts_latency_run.py time` again.

The code needs no change for this.

### 3. The spoken brief

- **First audio** changes little (4.0 → 3.7 s median, p90 unchanged at 7.2 s). First audio is the first sentence, and a card's first sentence is still a full sentence. The two cefazolin indication questions (B2-1, B3-6) are one 165-character sentence each: first audio 11.3 s, the slowest of the 21.
- **Audio end** drops from 37.0 to 14.4 s (median) and from 55.1 to 25.3 s (p90): 84 characters spoken instead of 305. Gaps fall to 15.2 s in total, the longest 3.0 s. That gap is the TXA card's WATCH line, a long sentence after a short GIVE line.
- **A hold is spoken in about 10 s.** The magnesium hold: first audio 1.2 s, end 10.3 s, against 18.4 s and 42.8 s before (whole WAV, same text). The epinephrine hold: 1.1 s and 11.9 s, against 38.1 s and 88.4 s.

## The spoken brief (`server/spoken.py`)

| Answer | What is spoken |
|---|---|
| Hold, no signed entry (A39) | "Held. No signed dose for magnesium sulfate. Use local protocol." |
| Hold from the dose check | "Held. The cefazolin dose in the answer is not the signed dose. Use local protocol." |
| Any other hold (validator, volume, indication) | "Held. The reason is on the screen. Use local protocol." |
| A dose | "Give naloxone, zero point four milligrams, intramuscularly. Draw one millilitre of naloxone, zero point four milligrams per millilitre." |
| A dose with no volume | "Give artesunate, one hundred and sixty-eight milligrams, intravenously. Confirm the concentration before drawing it up." |
| A card | Its GIVE line(s), then "Watch:" and its first WATCH line. TXA: "Give tranexamic acid, two grams, intravenously. Watch: mental status, radial pulse, blood pressure trend, …" |
| One drug twice on a card | Each dose is led by its signed indication: "For vasodilatory or haemorrhagic shock infusion, give norepinephrine, …". |
| One drug twice in a model answer | "There are two doses of ketamine. Read them on the screen." |
| A gate question, a card with no dose | Its own line, written out: "Which ketamine do you have, five hundred milligrams in ten millilitres vial, fifty milligrams per millilitre?" |
| A model answer with no dose | "No dose in this answer. The answer is on the screen." |

- **No model wording.** A model answer is heard only through the templates: the drug name comes from the recognised-drug index, and the numbers, units and routes come from the code-made dose line. Its WATCH line, indication and prose are never spoken. A test checks that every word a model answer can make the voice say is in the templates' vocabulary.
- **Never abbreviations.** Numbers are written out ("zero point one eight"), units in full with British spelling ("millilitres", "micrograms per kilogram per minute"), "q5min" as "every five minutes", and routes as "intravenously" and so on. A card line that still contains anything sayable only as letters or symbols is not spoken.
- **Corpus check:** over the 831 pipeline-replay answers, no spoken brief has a digit, a unit abbreviation or an unexpanded abbreviation. 5 deterministic answers fall back to a fixed sentence: 4 holds and 1 card.
- **The screen is unchanged.** `/query` adds `spoken_brief`; the portal speaks it, and an older server's brief is spoken as before. The session log does not record the spoken brief: it is a pure function of the logged response and model, and is recomputable.

## Found, not changed (owner to rule)

Ruled by the owner on 2026-10-26; see the next section.

- ~~The general-reference disclosure is spoken with "JTS", and before a hold.~~ Ruling 2.
- ~~"magnesium sulfate", not "magnesium".~~ Ruling 3: kept.
- ~~First audio is bounded by the first sentence.~~ Ruling 5.

## Owner rulings, round 2 (2026-10-26)

**Owner:** "1. Pin Chroma to the CPU explicitly before installing onnxruntime-gpu==1.31.0 into the service venv, so retrieval doesn't change; then run replay to prove it (0 changed), then re-time Kokoro on the GPU. 2. Disclosure: never spoken before a hold. For a served general-reference answer the spoken form is "General reference, not guideline." No "JTS" in speech. 3. Keep "magnesium sulfate". 4. Commits without failing-test-first are accepted for V3; templates aren't gates. 5. First chunk may split at a comma, colon or semicolon if the first sentence exceeds 80 characters. And the which-indication question gets its own spoken template: "<Drug>. Which indication: <list>?" with the list of names only."

### 1. Chroma on the CPU, and the GPU

- **The pin** (`embeddings.CpuDefaultEmbeddingFunction`): the same all-MiniLM ONNX model, with the provider list fixed to `CPUExecutionProvider`. It is named "default", so it matches the collection's stored config.
  - It is deliberately not a `DefaultEmbeddingFunction` subclass. Chroma ignores any instance of that class and rebuilds the stock default from the stored config. The first version of the pin was such a subclass, and it pinned nothing. A test now queries a pre-existing collection and fails if the stock embedder runs.
- **Retrieval check** (`tools/chroma_retrieval_check.py`): the replay sets never query Chroma, so a replay cannot show retrieval is unchanged.
  - **Method:** every unique query in the replay sets (607) runs against a copy of the live DB, with top 10 and the species filter, as the pipeline does. It saves each query's vector as Chroma embeds it, plus ids and distances.

| Run (against main, CPU wheel) | Vectors differ | Ids differ |
|---|---|---|
| main again, CPU wheel | 0 | 8 |
| pinned, CPU wheel | 0 | 4 |
| pinned, `onnxruntime-gpu` 1.31.0 | 0 | 4 |
| **main (not pinned), `onnxruntime-gpu` 1.31.0** | **every query fails** | |

  - **Vectors:** bit-identical in every pinned run.
  - **Ids:** the differences are Chroma's own. Its HNSW search is approximate and not fully repeatable: main run twice, same code, same DB, returns a different chunk from rank 4 to 10 on 8 of 607 queries. The 4 pinned differences are among those 8.
- **Without the pin, the GPU wheel breaks retrieval.** Chroma's stock embedder takes every available provider. It starts on CUDA, and every query fails: `cudaErrorNoKernelImageForDevice` in `/embeddings/position_embeddings/Gather`.
- **Kokoro cannot run on this GPU with that wheel.** The session opens on CUDA, and the first synthesis fails the same way (`/decoder/Slice/GatherSliceToSplitFusion`). `tts` moves to the CPU and says so in `/status`.
  - **Cost:** the first `/speak` after a restart takes 7.2 s (GPU load, failure, CPU load). After that, timing is the CPU's: 21 items 1.5 / 4.8 s on the GPU wheel against 1.6 / 4.8 s on the CPU wheel.
  - **Cause:** the wheel's CUDA kernels are built for sm_89, sm_90a, sm_120a and sm_121a only, with no PTX (`cuobjdump`). The Orin Nano is sm_87.
- **Real-time factor:** CPU 0.77, as before. GPU: not measurable with the approved wheel.
- **A wheel with sm_87 exists:** NVIDIA's Jetson AI Lab index has `onnxruntime-gpu` 1.24.0, cp312, built for CUDA 13.0 (`sbsa/cu130`); the sha256 matches the index. It was downloaded and inspected only, and is not installed. It is not the wheel the owner named, and installing third-party code is the owner's decision.
- **The service venv was not changed.** The live `edgecdss` service runs main, without the pin, from that venv, and the watchdog can restart it at any time. With the GPU wheel installed, a restart before this PR merges would leave retrieval failing on every query (above). The measurements used a scratch overlay venv with the same 1.31.0 wheel.

### 2–5. Speech

- **Disclosure** (`general_reference.for_speech`): "General reference, not guideline." It is its own sentence, so it is streamed as the first chunk. A hold carries no disclosure: a text starting "Held." or the hold opener is spoken as is. No "JTS" is spoken.
- **"magnesium sulfate"** is kept.
- **First chunk** (`tts.speech_chunks`): a first sentence over 80 characters splits once, at the last comma, colon or semicolon within 80 characters, else the first one after. The mark must be followed by white space, so "2,000" does not split.
- **Which indication** (`spoken.WHICH_INDICATION`): "Cefazolin. Which indication: penetrating brain or spinal injury, ventriculostomy in place or open fracture or wound infection prophylaxis?"
  - The options are matched against `INDICATION_CLASSES` and must rebuild the question word for word, else the brief is built as before. A name drops its bracketed qualifier. Tested on the question the pipeline writes for all 9 multi-indication drugs.

### Timing (same 21 saved answers, spoken briefs rebuilt with this code)

The commit 3 payloads (`payloads_c3.json`), with each brief rebuilt by this branch's `spoken.build`. 19 of the 21 are unchanged; the two cefazolin questions take the new template. Each wheel ran on a fresh :8012 server.

| | First audio median / p90 | Audio end median / p90 |
|---|---|---|
| V3 commit 3 | 3.7 / 7.2 s | 14.4 / 25.3 s |
| **Rulings, CPU** | **1.6 / 4.8 s** | 13.5 / 20.9 s |
| Rulings, GPU wheel (Kokoro falls back to the CPU) | 1.5 / 4.8 s | 13.3 / 20.7 s |

| Item | First audio | Audio end |
|---|---|---|
| Cefazolin which-indication (B2-1) | 11.3 → 1.7 s | 25.3 → 21.0 s |
| Ketamine which-vial (B2-7, split at "vial,") | 6.7 → 4.8 s | 14.6 → 13.5 s |
| General-source cefazolin hold (B2-3, no disclosure) | 3.3 → 1.1 s | 14.0 → 12.0 s |
| Epinephrine general-reference dose (B3-2) | 6.3 → 2.7 s | 21.0 → 18.7 s |
| Magnesium hold | 1.2 → 1.1 s | 10.3 → 10.5 s |

- **Gaps rose from 15.2 s to 52.5 s in total.** The wait moved; it did not grow: audio end fell (14.4 → 13.5 s median). A short first chunk plays before the next sentence is ready.
  - **General-source holds** opened with "From general reference, not JTS: Held." (3.7 s of audio), which covered the next sentence's synthesis. "Held." alone is 0.9 s, followed by about 3 s of silence.

### Found, not changed (owner to rule)

- **Names only drops "(already intubated)".** Ketamine's question is spoken "agitation, rapid sequence intubation, sedation, seizure or pain". The screen says "sedation (already intubated)", the distinction behind the 2026-10-15 incident (post-intubation sedation served to a patient who was not intubated).
- **"/" read as "or" inside a name runs into the list's own "or".** "ventriculostomy in place or open fracture or wound infection prophylaxis" can't be told apart by ear from four options. Atropine has the same problem: "bradycardia or nerve agent or organophosphate poisoning".
- **The gap moved behind the first chunk.** The cefazolin question starts at 1.6 s with "Cefazolin.", then 7.2 s of silence while the 130-character list synthesises, the longest gap in the 21. The list could split at its commas if the 80-character rule applied to every sentence, not only the first.
- **Split point:** the last mark within 80 characters gives the longer, more natural first chunk (B2-7: 4.8 s). The earliest mark would start sooner but leave a gap after it.
- **Chroma's top-10 is not repeatable run to run** (8 of 607 queries, from rank 4). This was here before V3. Not chased.

## Owner rulings, round 3 (2026-10-26)

**Owner:** "1. GPU wheel: yes, try NVIDIA's Jetson AI Lab onnxruntime-gpu 1.24.0 in the scratch venv first and time Kokoro. If it works, pin Chroma to CPU, install it in the service venv, replay (0 changed), re-time. If it doesn't work, stay on CPU and close the item; 1.6 s is acceptable. 2. Spoken options keep their qualifiers: "sedation, already intubated", never plain "sedation". 3. Lists: up to four options are spoken, each separated by a pause (semicolon), with "/" spoken as "or" only inside an option. Five or more: "Several indications are on screen. Say one." 4. Every sentence over 80 characters splits at commas, not only the first, so no silence over 2 s. Report first-audio and longest-silence after. PR, do not merge."

### 1. The Jetson wheel: Kokoro runs on the GPU

- **Wheel:** `onnxruntime_gpu-1.24.0-cp312-cp312-linux_aarch64.whl` from the Jetson AI Lab index (`sbsa/cu130`), sha256 `012c10be…22f6`, matching the index. Installed with `--no-deps` into a scratch overlay venv over the service venv's packages, so everything else is the same. Providers: TensorRT, CUDA, CPU.
- **Kokoro on CUDA works.** Same three texts as round 2, warm session:

| | 55 chars | 80 chars | 213 chars | Real-time factor |
|---|---|---|---|---|
| CUDA | 0.58 s | 0.72 s | 1.45 s | **0.09–0.12** |
| CPU | 4.32 s | 5.70 s | 13.02 s | 0.80–0.88 |

- **Audio:** the same length to the sample. The envelope correlates 0.9997 with the CPU's, and the log spectrogram 0.986. It is not bit-identical (CPU against CPU is exactly 1): GPU float arithmetic in the vocoder. Samples: `replay-out/v3tts/sample_CUDA0.wav`, `sample_CPUE1.wav`, for the owner to listen to.
- **Memory:** the server with Kokoro on CUDA uses about 1 GB more than on the CPU (RSS 1,658 MB against 620 MB; system used +860 MB). This is unified memory, shared with Ollama when a local model is loaded.
- **The first `/speak` after a start:** 3.3 s on CUDA (4.4 s on the CPU), for the warm-up sentence.
- `tts` needed no change: it already asks for `[CUDA, CPU]` and reports the device in `/status` (`voice_device: gpu`).

### Retrieval on the Jetson wheel

`tools/chroma_retrieval_check.py`, the same 607 queries against main on the CPU wheel (1.27.0):

| Run | Vectors differ | Ids differ |
|---|---|---|
| main again, CPU wheel 1.27.0 | 0 | 8 |
| **pinned, Jetson wheel 1.24.0** (run 1 / run 2) | **607, max 3.3e-7** | 3 / 4 |
| pinned, Jetson wheel, run 1 against run 2 | 0 | 3 |
| **main (not pinned), Jetson wheel 1.24.0** | **607, max 1.8e-4** | **17** |

- **Pinned, retrieval is the same within Chroma's own noise, but not bit-identical.** The pin keeps the embedder on the CPU, but it is 1.24.0's CPU code, not 1.27.0's. Every vector differs in the seventh significant digit (max 3.3e-7), and distances differ by at most 1.2e-6.
  - Every changed id in run 2 is on a query where main also differs from itself.
  - Run 1 had one more ("he's tanking, BP is 78/44 now and he's grey", a chunk missing from rank 4, with no near tie). It came back in run 2, so it was the HNSW search, not the vectors.
- **Not pinned, the Jetson wheel changes retrieval and slows it about 20-fold.** Chroma's stock embedder takes every provider and starts on TensorRT, building an engine on each query. The run took 12,493 s for 607 queries, about 20 s per query, against about 1.7 s per query in main's own run (1,013.7 s). 17 queries return different chunks, one from rank 1 ("leishmaniasis skin lesion, what treatment").

### The service venv: not changed

- **The ruling's condition is not met on the live service.** #188 merged into the V3 branch (#187), not main, and #187 is still open. So the live `edgecdss` service runs main without the pin, from `/home/andrew/pi-cloud-cdss/.venv`, and the watchdog can restart it at any time.
- With the Jetson wheel in that venv, the next restart would put live retrieval on TensorRT: about 20 s per query, and 17 of 607 queries changed (above).
- The service process is already in the render group (993), so the GPU is reachable once the wheel is in.
- **To install, once #187 is merged and deployed:** `pip uninstall -y onnxruntime`, then `pip install --no-deps` the wheel, then restart. Both packages provide the `onnxruntime` module, so the CPU one must go first.

### Replay (round-3 tree, both wheels)

0 changed in all five sets, against main, on the CPU wheel and on the Jetson wheel. Served 1,738, held 308, gate 1,408, log 3,945, pipe 831. Every output is byte-identical to main's.
- The log set is 58 rows larger than round 2's because the live session logs have grown, so main was replayed again on the same logs.
- The replays do not query Chroma or synthesise speech, so they show the answers unchanged and nothing more.

### 2–4. Speech

- **Qualifiers kept** (`spoken.indication_name`): "sedation, already intubated"; "penetrating brain or spinal injury, antibiotic prophylaxis".
- **Lists** (`spoken.WHICH_INDICATION`, `INDICATION_LIST_MAX = 4`, `MANY_INDICATIONS`): options are joined by "; ", with no list "or". A "/" inside an option is "or".
  - "Cefazolin. Which indication: penetrating brain or spinal injury, antibiotic prophylaxis; ventriculostomy in place; open fracture or wound infection prophylaxis?"
  - "Midazolam. Which indication: agitation; pacing or cardioversion; sedation, already intubated; seizure?"
  - "Atropine. Which indication: bradycardia; nerve agent or organophosphate poisoning?"
  - Ketamine has five options (agitation, RSI, sedation (already intubated), seizure, pain): "Ketamine. Several indications are on screen. Say one." (`spoken.MANY_INDICATIONS`; the drug name added on the owner's 2026-10-27 ruling). It is the only drug today past four.
- **Every long sentence splits** (`tts.speech_chunks`, `CHUNK_MAX = 80`): each sentence over 80 characters is cut repeatedly, at the last comma, colon or semicolon within 80, else the first after, until every piece fits or no mark is left. A semicolon between options is a mark, so the cefazolin list streams as "Which indication: penetrating brain or spinal injury, antibiotic prophylaxis;" then "ventriculostomy in place; open fracture or wound infection prophylaxis?".
- `tools/tts_latency_run.py` now records `longest_silence_ms` per item: the wait from one chunk ending to the next starting, the portal's 0.15 s breath included.

### Timing (same 21 saved answers; briefs rebuilt with this code, only the two cefazolin questions change)

Each run used a fresh :8012 server.

| | First audio median / p90 | Audio end median / p90 | Longest silence median / p90 / max | Items with a silence over 2 s |
|---|---|---|---|---|
| Round 2 (#188), CPU wheel | 1.6 / 4.8 s | 13.5 / 20.9 s | (not recorded) / max 7.3 s | 13 |
| #188, Jetson wheel, GPU | 0.31 / 0.64 s | 9.1 / 14.2 s | 0.15 / 0.15 / 0.15 s | 0 |
| **Round 3, Jetson wheel, GPU** | **0.30 / 0.64 s** | **9.1 / 14.9 s** | **0.15 / 0.15 / 0.15 s** | **0** |
| Round 3, CPU wheel (if the GPU fails) | 1.5 / 4.6 s | 13.2 / 19.7 s | 2.1 / 3.8 / 3.8 s | 11 |

- **On the GPU, no item has a gap beyond the 0.15 s breath.** Every chunk is ready before the one before it ends.
- **On the CPU, ruling 4 cannot hold the 2 s.** The silences left come after "Held." (0.9 s of audio, then about 2.9 s while a sentence under 80 characters synthesises) and after "Cefazolin." (3.8 s). Splitting at commas does not reach them: the sentence after is already under 80 characters, or splits only once. The longest silence on the CPU fell from 7.3 to 3.8 s.

| Item | Round 2, CPU | Round 3, GPU |
|---|---|---|
| Cefazolin which-indication (B2-1) | 1.7 s first audio, 7.2 s silence | 0.35 s, no silence |
| Ketamine which-vial (B2-7) | 4.8 s | 0.66 s |
| Cefazolin hold (B2-3) | 1.1 s, 2.9 s silence after "Held." | 0.27 s, no silence |
| Ketamine drip (B2-6, longest audio) | 2.1 s, audio end 25.1 s | 0.36 s, audio end 19.8 s |
| Magnesium hold | 1.1 s | 0.26 s |

### Found, not changed (ruled 2026-10-27, below)

- **Install the Jetson wheel in the service venv only after #187 is deployed** (above). The owner installs it.
- **About 1 GB more memory with Kokoro on the GPU**, shared with Ollama's model.

### Owner rulings on #189 (2026-10-27)

**Owner rulings on #189 (2026-10-27):** "(1) "unchanged within Chroma's own noise, 0 changed on all five replays" is acceptable; record it in the PR as the criterion. (2) The five-option sentence names the drug: "Ketamine. Several indications are on screen. Say one." (3) The CPU fallback's 3 s silence is accepted and documented; GPU is primary. Add commit 2, then stop; I'll merge and install the wheel myself."

- **The retrieval criterion for the Jetson wheel** is "unchanged within Chroma's own noise, 0 changed on all five replays", not bit-identical vectors. Pinned on 1.24.0: vectors within 3.3e-7, ids differing only on queries where main differs from itself, and 0 changed on all five replays. It meets the criterion.
- **The five-option sentence names the drug:** "Ketamine. Several indications are on screen. Say one."
- **The CPU fallback's silences of about 3 s are accepted.** The GPU is primary; on the CPU the longest silence is 3.8 s (after "Cefazolin.") and about 2.9 s after "Held.".
- **The owner merges #189 and installs the wheel.** This branch does not change the service venv.

## Every item, commit 3

| Id | Source mode | Chars | First audio | Audio end | Spoken |
|---|---|---|---|---|---|
| B2-1 | PRE_GATE | 165 | 11.3 s | 25.3 s | Which indication for cefazolin, penetrating brain or spinal injury, antibiotic prophylaxis, ventriculostomy in place or open fracture or wound infection prophylaxis? |
| B2-2 | GENERAL_MEDICAL | 84 | 3.4 s | 14.4 s | Held. The ceftriaxone dose in the answer is not the signed dose. Use local protocol. |
| B2-3 | GENERAL_MEDICAL | 82 | 3.3 s | 14.0 s | Held. The cefazolin dose in the answer is not the signed dose. Use local protocol. |
| B2-4 | DETERMINISTIC_PRE_GATE | 83 | 6.4 s | 14.4 s | Fever or pus plus hypotension means sepsis: fluids, antibiotics, urgent evacuation. |
| B2-5 | GENERAL_MEDICAL | 84 | 3.3 s | 14.3 s | Held. The ceftriaxone dose in the answer is not the signed dose. Use local protocol. |
| B2-6 | DETERMINISTIC_PRE_GATE | 228 | 7.2 s | 25.9 s | Ketamine infusion: document concentration in milligrams per millilitre and pump rate in millilitres per hour. Watch: blood pressure, heart rate, oxygen saturation, end-tidal carbon dioxide if available, and ventilator synchrony. |
| B2-7 | PRE_GATE | 109 | 6.7 s | 14.6 s | Which ketamine do you have, five hundred milligrams in ten millilitres vial, fifty milligrams per millilitre? |
| B2-8 | PRE_GATE | 109 | 6.7 s | 14.7 s | Which ketamine do you have, five hundred milligrams in ten millilitres vial, fifty milligrams per millilitre? |
| B2-9 | INSUFFICIENT | 54 | 1.1 s | 8.1 s | Held. The reason is on the screen. Use local protocol. |
| B3-1 | JTS_GROUNDED | 84 | 1.1 s | 11.9 s | Held. The epinephrine dose in the answer is not the signed dose. Use local protocol. |
| B3-2 | FIXED_PREP | 136 | 6.3 s | 21.0 s | Give epinephrine, five to twenty micrograms, intravenously. Watch: continuous cardiac monitoring required. Use only with local protocol. |
| B3-3 | DETERMINISTIC_PRE_GATE | 168 | 3.7 s | 20.3 s | Give tranexamic acid, two grams, intravenously. Watch: mental status, radial pulse, blood pressure trend, ongoing bleeding, hypothermia, and response to blood products. |
| B3-4 | DETERMINISTIC_PRE_GATE | 168 | 3.7 s | 20.4 s | Give tranexamic acid, two grams, intravenously. Watch: mental status, radial pulse, blood pressure trend, ongoing bleeding, hypothermia, and response to blood products. |
| B3-5 | GENERAL_MEDICAL | 82 | 3.3 s | 14.2 s | Held. The cefazolin dose in the answer is not the signed dose. Use local protocol. |
| B3-6 | PRE_GATE | 165 | 11.3 s | 25.3 s | Which indication for cefazolin, penetrating brain or spinal injury, antibiotic prophylaxis, ventriculostomy in place or open fracture or wound infection prophylaxis? |
| B3-7 | GENERAL_MEDICAL | 84 | 3.4 s | 14.4 s | Held. The ceftriaxone dose in the answer is not the signed dose. Use local protocol. |
| B3-8 | JTS_GROUNDED | 135 | 4.2 s | 15.3 s | Give naloxone, zero point four milligrams, intramuscularly. Draw one millilitre of naloxone, zero point four milligrams per millilitre. |
| B3-9 | JTS_GROUNDED | 119 | 4.6 s | 14.0 s | Give artesunate, one hundred and sixty-eight milligrams, intravenously. Confirm the concentration before drawing it up. |
| B3-10 | GENERAL_MEDICAL | 82 | 3.3 s | 14.0 s | Held. The midazolam dose in the answer is not the signed dose. Use local protocol. |
| B3-11 | JTS_GROUNDED | 54 | 1.2 s | 8.2 s | Held. The reason is on the screen. Use local protocol. |
| MG-A39 | DETERMINISTIC_PRE_GATE | 63 | 1.2 s | 10.3 s | Held. No signed dose for magnesium sulfate. Use local protocol. |
