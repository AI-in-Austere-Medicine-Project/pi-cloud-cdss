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

- **The general-reference disclosure is still spoken with an abbreviation:** "From general reference, not JTS:". `/speak` adds it (`general_reference.for_speech`) before any `source=general` answer, holds included: "From general reference, not JTS: Held. …". Its wording is not the spoken brief's to change.
- **"magnesium sulfate", not "magnesium".** The hold says the drug's name from the index. The owner's example said "magnesium".
- **First audio is now bounded by the first sentence.** A long first sentence (the cefazolin indication question, 11.3 s) is the slowest item. Splitting a sentence at commas would cut it, but the owner's instruction was sentence boundaries.

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
