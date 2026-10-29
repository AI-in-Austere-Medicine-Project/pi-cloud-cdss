# P1: hold to talk shows every failure; the MODE control is gone (2026-10-29)

**Owner (live, 2026-10-29):** "Live, two portal findings, one PR: 1. Hold-to-talk does nothing from the owner's Mac. Make every failure visible: a recording indicator while held, the transcript appearing word by word, and an on-screen message for each failure case (microphone permission denied, insecure origin so no microphone, no audio captured, /transcribe error with status). Tell me which case it was from the browser console if you can reproduce it; if the portal is reached over http by IP, say so and document that voice-in needs https or localhost. 2. Remove the Mode brief/detailed control from the portal; it does nothing. Config and tests. PR, do not merge."

"P1" is a number assigned here; the owner confirms it.

## 1. Which case it was

The live service's access log is not readable from this account (the journal needs the `adm` group), so the Mac's request could not be seen. Headless Chromium against the live portal (main, v5.1.0), holding HOLD TO TALK for 1.5 s with a fake microphone:

| Reached as | `isSecureContext` | `navigator.mediaDevices` | What the press did |
|---|---|---|---|
| `http://192.168.1.126:8000` (LAN IP) | false | `undefined` | The button never turned red. One 11 px grey line under the box: "No microphone: Cannot read properties of undefined (reading 'getUserMedia'). Type the question instead." No `/transcribe` call. |
| `http://localhost:8000` | true | object | Recorded; `/transcribe` 200 |
| `https://cdss.arcanekg.com` (the tunnel) | true | object | Recorded; `/transcribe` 200 |

The device is also reachable over plain http at its Tailscale address (`http://100.87.238.76:8000`), which is the same case as the LAN IP. **Over http by IP the browser gives the page no microphone at all**: a page gets `navigator.mediaDevices` only in a secure context, https or localhost. That is the only way found to make the press "do nothing" that can be seen: the button stays grey, and the message is easy to miss. `/status speech_in` on live is available.

A second silent case was in the code: the first press on a site, when the browser asks for the microphone. The medic lets go to answer the prompt, the recording is dropped, and nothing is said.

Which of the two happened on the Mac can be read from its browser console with this branch: each failure logs one line, `[talk] <case>`.

**Voice in needs https or localhost.** Use the tunnel address (`https://cdss.arcanekg.com`) from another machine, or `http://localhost:8000` on the device. Typed questions work from any address.

## 2. Hold to talk

Every failure is a red message under the box (13 px, `role="status"`, `aria-live`) and one console line:

| `[talk]` case | When | On screen |
|---|---|---|
| `insecure-origin` | not a secure context, or no `getUserMedia` | "Voice needs https or localhost. This page is http://…, and over plain http the browser gives it no microphone. Open the portal's https address, or localhost on the device. Or type the question." |
| `permission-denied` | `NotAllowedError` / `SecurityError` | "Microphone permission denied. Allow the microphone for this site (…), then hold again. Or type the question." |
| `no-microphone` | `NotFoundError` / `OverconstrainedError` | "No microphone found. Connect one, then hold again. …" |
| `microphone-busy` | `NotReadableError` / `AbortError` | "The microphone could not start (…). It may be in use by another app. …" |
| `microphone-error` | any other `getUserMedia` error | "The microphone did not open (…). …" |
| `released-before-microphone` | let go before the microphone opened (was silent) | "The microphone is on now. Hold the button again and speak; let go when you finish." |
| `too-short` | held under 0.3 s | "Hold the button while you speak." |
| `no-audio` | no audio arrived, or only zeros | "No audio captured from the microphone (no sound arrived / only silence). Check the input device and its level, then hold again. …" |
| `transcribe-unreachable` | the fetch failed | "Speech in failed: could not reach /transcribe (…). …" |
| `transcribe-error <status>` | `/transcribe` not 2xx | "Speech in failed: /transcribe 503: <detail>. …" |
| `empty-transcript` | whisper heard no words | "Nothing was heard. Hold the button and speak, or type." |

- **While held:** the button is red, "● RECORDING". The note under it says "● Recording · waiting for the microphone (allow it if the browser asks)" until audio arrives, then "● Recording 1.2 s · level ▮▮▮▯▯▯▯▯ · let go to transcribe", updated with each audio block. A level that stays empty is visible before letting go.
- **Word by word:** the transcript goes into the box one word every 60 ms, after anything typed. whisper returns the clip's words together, so the pacing is the portal's, after `/transcribe` answers; it is not live transcription while held. The box is read-only and SEND waits until the last word is in.
- **Safari:** the AudioContext is made after the microphone opens, outside the press, and Safari can start it suspended, which delivers no audio. It is resumed. If it still delivers nothing, the press ends in `no-audio`, not silence.
- Unchanged: nothing is sent until the medic presses SEND; the microphone is open only while held; WAV 16 kHz mono 16-bit.

## 3. MODE

`voice_mode` went from the portal's MODE radios to `/query`, to `query_with_rag`, `_query_with_rag_internal` and `_run_pipeline`, and was never read. `/query` echoed it back and nothing read that either. Removed:

- the portal's MODE brief/detailed radios, and `voice_mode` from its `/query` body;
- `voice_mode` from `QueryRequest` and `QueryResponse`, and from the three pipeline signatures (no caller passed it by position);
- `voice_mode` from `run_tests.sh`, `tools/latency_run.py`, `tools/tts_latency_run.py` and `client/cdss_client.py`.

A client that still sends `voice_mode` is answered as before: an unknown field is ignored, not refused. Its 32-character cap went with the field; an unknown field has never had one.

No `.env` setting or config file named the mode, so there was no other config to change.

## 4. Tests

Failing tests first (`46fb8fd`), in `tests/test_p1_portal_voice_and_mode.py`, running the portal's script in `tests/stt_ptt_harness.js` with new scenarios: `insecure`, `nomic`, `early`, `silent`, `noaudio`, `neterr` and `empty`; `denied` now raises a `NotAllowedError`. The harness's `setTimeout` runs on the next microtask, so a chained reveal records each step.

- One test per case above: the message, red, and exactly one `[talk]` case in the console.
- The recording note while held, and the box after each word, typed text first.
- No MODE control, no `voice_mode` in the portal's body, the request and response models, the pipeline signatures, or any client.
- A client that still sends `voice_mode` is answered (`test_security_patch.py`; the field's 33-character refusal case is gone).
- `test_portal_brief.py`: a chip and a typed query both carry no `voice_mode`.

A test fix (`e2dec3a`): the stub DOM starts every label empty, so the insecure case now asserts the button was never put into recording, not its label.

## 5. Checked

- **Suite:** 3,829 passed, 45 skipped, 3 xfailed.
- **Harness:** 29/29 against the branch on :8013.
- **Chromium against the branch on :8013:**
  - `localhost` with a recorded question (S1's B2-7) as the microphone: "● Recording 0.4 s · level …" while held; the box filled in 14 steps, "80", "80 kg", "80 kg adult," … ; "Check the words, then press SEND."
  - `http://lan.test:8013` (resolved to 127.0.0.1, not a secure context): the insecure-origin message in red; console `[talk] insecure-origin`.
  - Microphone denied: the permission message in red; console `[talk] permission-denied NotAllowedError`.
  - No MODE control on the page.
- **Replay** vs main f9119c3 (live kit): all five sets byte-identical (served 1,738, held 308, gate 1,408, log 4,511, pipe 840 rows): 0 changed, 0 newly held, 0 newly released, 0 newly dosing.
