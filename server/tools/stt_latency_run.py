"""S1: time speech in, release to transcript, on a :8012 server.

  stt_latency_run.py make <dir>
      Speak the 20 batch 2/3 harness questions with Kokoro (bm_george, the
      service's voice) and save each as the portal would send it: averaged
      down to 16 kHz, 16-bit mono WAV (the portal's downsampleTo16k). A
      synthetic speaker, not a medic: the same 20 recordings every run.

  stt_latency_run.py time <dir> <out.json>
      POST each WAV to /transcribe, one at a time, after one warm-up, and time
      from the request leaving to the transcript arriving. That is release to
      transcript less the portal's own downsample and encode (a few ms in the
      browser, not measured here). Saves each transcript verbatim beside the
      text that was spoken, with a word error rate on lower-cased words with
      punctuation stripped (numbers are compared as written, so "80" against
      "eighty" counts as an error).

  stt_latency_run.py report <out.json>
      Median and p90 over the 20.
"""
import io
import json
import os
import re
import statistics
import sys
import time
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from latency_run import B2, B3  # noqa: E402

BASE = os.getenv("CDSS_LATENCY_BASE", "http://127.0.0.1:8012").rstrip("/")
TOKEN = os.getenv("CDSS_ACCESS_TOKEN", "edgecdss-demo-2026")
ITEMS = [(f"B2-{i+1}", q) for i, q in enumerate(B2)] + [(f"B3-{i+1}", q) for i, q in enumerate(B3)]
RATE = 16000


def downsample_to_16k(samples, rate):
    """index.html downsampleTo16k: each output sample is the mean of its window."""
    import numpy as np
    x = np.asarray(samples, dtype=np.float32)
    if rate == RATE:
        return x
    ratio = rate / RATE
    n = int(len(x) // ratio)
    out = np.empty(n, dtype=np.float32)
    for i in range(n):
        a, b = int(i * ratio), min(len(x), int((i + 1) * ratio))
        out[i] = x[a:b].mean() if b > a else 0.0
    return out


def wav16k(samples) -> bytes:
    import numpy as np
    pcm = np.clip(samples, -1, 1)
    pcm = np.where(pcm < 0, pcm * 32768, pcm * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def make(out_dir):
    import tts
    os.makedirs(out_dir, exist_ok=True)
    eng = tts._engine()
    manifest = []
    for ident, text in ITEMS:
        samples, sr = eng.create(text, voice=tts.DEFAULT_VOICE, speed=tts.DEFAULT_SPEED, lang=tts.DEFAULT_LANG)
        body = wav16k(downsample_to_16k(samples, sr))
        path = os.path.join(out_dir, f"{ident}.wav")
        open(path, "wb").write(body)
        manifest.append({"id": ident, "text": text, "wav": path, "audio_s": round(len(samples) / sr, 2)})
        print(ident, manifest[-1]["audio_s"], flush=True)
    json.dump(manifest, open(os.path.join(out_dir, "manifest.json"), "w"), indent=1)


def words(s):
    return re.sub(r"[^\w\s/.]", " ", s.lower()).replace(".", " ").split()


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return round(d[len(h)] / max(1, len(r)), 3)


def post(body):
    req = urllib.request.Request(BASE + "/transcribe", body,
                                 {"Content-Type": "audio/wav", "X-Access-Token": TOKEN})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    return d, round((time.perf_counter() - t0) * 1000, 1)


def time_all(in_dir, out_path):
    manifest = json.load(open(os.path.join(in_dir, "manifest.json")))
    post(open(manifest[0]["wav"], "rb").read())                     # warm-up
    out = []
    for m in manifest:
        d, ms = post(open(m["wav"], "rb").read())
        row = {"id": m["id"], "audio_s": m["audio_s"], "release_to_transcript_ms": ms,
               "transcribe_ms": d.get("transcribe_ms"), "device": d.get("device"),
               "spoken": m["text"], "transcript": d.get("text", ""), "wer": wer(m["text"], d.get("text", ""))}
        out.append(row)
        print(row["id"], ms, row["device"], row["wer"], repr(row["transcript"]), flush=True)
    json.dump(out, open(out_path, "w"), indent=1)


def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def report(path):
    rows = json.load(open(path))
    for f in ("release_to_transcript_ms", "transcribe_ms", "audio_s", "wer"):
        xs = [r[f] for r in rows]
        print(f"{f}: median {statistics.median(xs):.3g}  p90 {pct(xs, 0.9):.3g}  max {max(xs):.3g}")
    print("devices:", sorted({r["device"] for r in rows}), "exact transcripts:",
          sum(1 for r in rows if r["wer"] == 0), "of", len(rows))


if __name__ == "__main__":
    a = sys.argv
    if len(a) == 3 and a[1] == "make":
        make(a[2])
    elif len(a) == 4 and a[1] == "time":
        time_all(a[2], a[3])
    elif len(a) == 3 and a[1] == "report":
        report(a[2])
    else:
        print(__doc__)
        sys.exit(2)
