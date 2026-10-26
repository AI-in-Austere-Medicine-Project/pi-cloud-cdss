# Local voice, Kokoro-82M: listen-path timing, 2026-10-25 (V2)

**Owner (2026-10-25):** "V2: replace /speak with local Kokoro-82M (kokoro-onnx, CPU, weights and voices on disk, espeak-ng via apt; no network after install). Keep the ElevenLabs path deleted, not optional. Measure text-sent → first-audio → audio-end on the 20 harness answers and the magnesium hold; report median and p90. No change to answer text yet."

## Setup

- **Engine:** kokoro-onnx 0.6.1, `kokoro-v1.0.onnx` (fp32, 325 MB) and `voices-v1.0.bin`, sha256-checked by `server/tools/install_kokoro.sh`. onnxruntime 1.27 on the CPU (6 Cortex-A78AE cores, Jetson). Phonemes come from apt's libespeak-ng 1.51.
- **Voice:** `bm_george`, `en-gb`, speed 0.85. That's the nearest match to the ElevenLabs "George" voice and the 0.85 speed it replaces.
- **Output:** 16-bit mono 24 kHz WAV, the whole utterance per request.
- **No network:** the real-model test runs with every connection refused.
- **Model load:** about 2.2 s once per process, paid by the first `/speak`. The warm-up here took 4.2 s for a 2.5 s clip, and is excluded from the tables.

## Method

- A :8012 server ran from the branch, offline (`CDSS_LLM_PROVIDER=local`, qwen2.5:3b).
- **Items:**
  - the 20 batch 2/3 harness questions (V1's set, since no list of ten is recorded);
  - the magnesium hold.
- **For each item** (`server/tools/tts_latency_run.py`):
  - ask `/query`, untimed;
  - send `/speak` exactly what the listen button sends: the response with `**` and `|` cleaned, the brief, and the source. The server speaks the brief when there is one, with the general-reference disclosure, after `normalize_for_speech`.
- **Timed:**
  - **text sent → first audio:** until the whole WAV has arrived. The portal plays the blob only once it is complete, so first audio cannot start earlier. The browser's own decode-to-play time is not measured (there's no browser on the Jetson);
  - **first audio → audio end:** the WAV's duration.
- **Nearest-rank p90**, n = 21. One pass, sequential. No live traffic reached :8000 during the run.
- Not timed in a browser. The portal's `/speak/timing` record (V1) will give the real figures from the first presses.

## Results

| | n | median | p90 | max |
|---|---|---|---|---|
| Text sent → first audio | 21 | 17.0 s | 34.3 s | 49.1 s |
| First audio → audio end (clip length) | 21 | 22.7 s | 46.0 s | 67.2 s |
| Text sent → audio end | 21 | 39.7 s | 80.3 s | 116.3 s |
| Synthesis on the server (X-Synth-Ms) | 21 | 17.0 s | 34.3 s | 49.1 s |
| Characters sent | 21 | 202 | 571 | 889 |

- **Synthesis runs at about 0.75× real time** (synthesis time over clip length: median 0.75). Because the whole clip is made before any of it plays, first audio is about three-quarters of the clip's length.
- **The time follows the length of what is spoken.** A 60-character vial question gets first audio at 6.3 s. The longest, an 889-character epinephrine hold (B3-1), waits 49 s for first audio and 116 s to the end.
- **Holds are the longest texts.** A hold has no brief, so its full "Clinical safety hold … Issues identified …" text is spoken. All nine items over 300 characters are holds (seven) or the haemorrhagic-shock card (two). No change to answer text was made (owner: "not yet").
- The magnesium hold: 301 characters, first audio 18.0 s, end 42.4 s.

## Every item

| Id | Source mode | Chars | Text sent → first audio | Clip | Text sent → audio end | Spoken (start) |
|---|---|---|---|---|---|---|
| B2-1 | PRE_GATE | 166 | 11.1 s | 14.3 s | 25.4 s | Which indication for cefazolin — penetrating brain or spinal injury (a… |
| B2-2 | GENERAL_MEDICAL | 246 | 17.0 s | 22.7 s | 39.7 s | Transfer to surgical support as soon as feasible / Provide single dose p… |
| B2-3 | GENERAL_MEDICAL | 445 | 29.3 s | 39.5 s | 68.8 s | Clinical safety hold. This response was blocked. / Issues identified: Th… |
| B2-4 | DETERMINISTIC_PRE_GATE | 202 | 14.4 s | 19.3 s | 33.7 s | Fever or pus plus hypotension = sepsis: fluids, antibiotics, urgent ev… |
| B2-5 | GENERAL_MEDICAL | 571 | 34.3 s | 46.0 s | 80.3 s | Clinical safety hold. This response was blocked. / Issues identified: Th… |
| B2-6 | DETERMINISTIC_PRE_GATE | 185 | 13.7 s | 18.3 s | 32.0 s | Intubated sedation: ketamine drip with mg/mL concentration and mL/hr p… |
| B2-7 | PRE_GATE | 60 | 6.4 s | 8.0 s | 14.4 s | Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?… |
| B2-8 | PRE_GATE | 60 | 6.3 s | 8.0 s | 14.3 s | Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?… |
| B2-9 | INSUFFICIENT | 201 | 12.5 s | 16.6 s | 29.1 s | Clinical safety hold. This response was blocked. / Issues identified: Pa… |
| B3-1 | JTS_GROUNDED | 889 | 49.1 s | 67.2 s | 116.3 s | Clinical safety hold. This response was blocked. / Issues identified: gi… |
| B3-2 | FIXED_PREP | 202 | 17.2 s | 23.4 s | 40.5 s | epinephrine IV: 5-20 mcg. / Continuous cardiac monitoring required. Use … |
| B3-3 | DETERMINISTIC_PRE_GATE | 397 | 27.9 s | 37.7 s | 65.6 s | tranexamic acid IV: 2 g. / Control hemorrhage immediately: pressure, tou… |
| B3-4 | DETERMINISTIC_PRE_GATE | 397 | 28.0 s | 37.7 s | 65.7 s | tranexamic acid IV: 2 g. / Control hemorrhage immediately: pressure, tou… |
| B3-5 | GENERAL_MEDICAL | 401 | 28.1 s | 38.2 s | 66.4 s | Clinical safety hold. This response was blocked. / Issues identified: gi… |
| B3-6 | PRE_GATE | 166 | 10.7 s | 14.3 s | 24.9 s | Which indication for cefazolin — penetrating brain or spinal injury (a… |
| B3-7 | JTS_GROUNDED | 132 | 11.8 s | 15.8 s | 27.5 s | ceftriaxone IV: 2000 mg (100 mg/kg × 20 kg). No volume — confirm conce… |
| B3-8 | JTS_GROUNDED | 123 | 11.3 s | 15.1 s | 26.5 s | Draw 1 mL of 0.4mg/mL naloxone IM (0.4 mg). / Administer naloxone IM. / Na… |
| B3-9 | JTS_GROUNDED | 69 | 7.9 s | 10.2 s | 18.1 s | Draw 168 mg of artesunate IV (168 mg). / Monitor for adverse reactions.… |
| B3-10 | GENERAL_MEDICAL | 390 | 27.3 s | 36.7 s | 64.0 s | Clinical safety hold. This response was blocked. / Issues identified: gi… |
| B3-11 | JTS_GROUNDED | 662 | 36.7 s | 50.3 s | 87.0 s | Clinical safety hold. This response was blocked. / Issues identified: Th… |
| MG-A39 | DETERMINISTIC_PRE_GATE | 301 | 18.0 s | 24.4 s | 42.4 s | Clinical safety hold. This response was blocked. / Issues identified: Ma… |

## Not changed

- **Answer text** is unchanged (owner).
- **No streaming and no quantised model.** V2 is the replacement and its measurement, so neither was tried.
- **`client/cdss_client.py`**, the separate desktop client, still calls ElevenLabs directly with its own key. It doesn't go through `/speak` and is not touched here. Owner ruled 2026-10-26: delete; done in its own PR.
