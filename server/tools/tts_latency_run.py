"""V2/V3: time the listen path with local Kokoro on a :8012 server.

Two steps, so every V3 commit is timed on the same text:

  tts_latency_run.py fetch <payloads.json>
      Ask /query for the 20 batch 2/3 harness questions and the magnesium hold
      (not timed), and save each response and exactly what the portal's
      listen button sends /speak for it (the response with ** and | cleaned,
      the brief, the source, and the spoken brief when the server sends one).

  tts_latency_run.py time <payloads.json> <out.json> [--stream]
      Send each payload to /speak, one at a time, after one warm-up, and time
      from text sent:
        whole  (V2): the WAV is complete when the response is; the portal
                     plays it from then. first audio = response received.
        stream (V3): one WAV per sentence. first audio = the first frame
                     received; each later sentence plays when it has arrived
                     and the one before has ended (plus the portal's 0.15 s
                     breath), so a sentence that arrives late is a gap.
      audio end = when the last sentence ends. The browser's own decode is not
      measured.

  tts_latency_run.py report <out.json> [<out.json> ...]
      Median and p90 per run, over the 21 items.
"""
import io
import json
import statistics
import struct
import sys
import time
import urllib.request
import wave

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from latency_run import B2, B3  # the 20 batch 2/3 harness questions (V1)

BASE = "http://127.0.0.1:8012"
HDR = {"Content-Type": "application/json", "X-Access-Token": "edgecdss-demo-2026", "X-Test-Run": "1"}
GAP_S = 0.15          # index.html SENTENCE_GAP_S
ITEMS = ([(f"B2-{i+1}", q) for i, q in enumerate(B2)]
         + [(f"B3-{i+1}", q) for i, q in enumerate(B3)]
         + [("MG-A39", "don't want ketamine, I need magnesium, 75 kg")])


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), HDR)
    return urllib.request.urlopen(req, timeout=900)


def wav_seconds(b):
    with wave.open(io.BytesIO(b)) as w:
        return w.getnframes() / w.getframerate()


def fetch(path):
    out = []
    for ident, q in ITEMS:
        with post("/query", {"query": q, "device_id": "v3-tts", "timestamp": "2026-10-26T00:00:00",
                             "voice_mode": "brief", "conversation_history": []}) as r:
            d = json.load(r)
        speak = {"text": d.get("response", "").replace("**", "").replace("|", ". "),
                 "source": d.get("source", ""), "brief": d.get("spoken_brief") or d.get("brief") or ""}
        out.append({"id": ident, "query": q, "response": d, "speak": speak})
        print(ident, d.get("source_mode"), len(speak["brief"] or speak["text"]), flush=True)
    json.dump(out, open(path, "w"), indent=1)


def time_one(speak, stream):
    t0 = time.perf_counter()
    body = dict(speak, stream=True) if stream else speak
    arrivals = []                                    # (ms from text sent, audio s)
    with post("/speak", body) as r:
        synth = r.headers.get("X-Synth-Ms")
        if not stream:
            audio = r.read()
            arrivals.append(((time.perf_counter() - t0) * 1000, wav_seconds(audio)))
        else:
            buf = b""
            while True:
                piece = r.read1(65536)
                if not piece:
                    break
                buf += piece
                while len(buf) >= 5:
                    (n,) = struct.unpack(">I", buf[1:5])
                    if len(buf) < 5 + n:
                        break
                    kind, payload, buf = buf[:1], buf[5:5 + n], buf[5 + n:]
                    if kind != b"A":
                        raise RuntimeError(payload.decode())
                    arrivals.append(((time.perf_counter() - t0) * 1000, wav_seconds(payload)))
    end, gaps = None, 0.0
    for at, dur in arrivals:
        start = at if end is None else max(at, end + GAP_S * 1000)
        if end is not None:
            gaps += max(0.0, at - (end + GAP_S * 1000))
        end = start + dur * 1000
    return {"synth_ms": float(synth) if synth else None, "sentences": len(arrivals),
            "first_audio_ms": round(arrivals[0][0], 1),
            "audio_ms": round(sum(d for _, d in arrivals) * 1000, 1),
            "audio_end_ms": round(end, 1), "underrun_ms": round(gaps, 1),
            "frames": [[round(at, 1), round(dur, 3)] for at, dur in arrivals]}


def run(payloads, path, stream):
    items = json.load(open(payloads))
    time_one({"text": "Reassess in five minutes.", "source": "", "brief": ""}, stream)  # warm-up
    out = []
    for it in items:
        row = {"id": it["id"], "source_mode": it["response"].get("source_mode"),
               "chars_sent": len(it["speak"]["brief"] or it["speak"]["text"]),
               "spoken": it["speak"]["brief"] or it["speak"]["text"],
               **time_one(it["speak"], stream)}
        out.append(row)
        print(row["id"], row["chars_sent"], row["sentences"], row["first_audio_ms"],
              row["audio_end_ms"], row["underrun_ms"], flush=True)
    json.dump(out, open(path, "w"), indent=1)


def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def report(paths):
    for p in paths:
        rows = json.load(open(p))
        line = [p.rsplit("/", 1)[-1], f"n={len(rows)}"]
        for f in ("first_audio_ms", "audio_ms", "audio_end_ms", "chars_sent"):
            xs = [r[f] for r in rows]
            line.append(f"{f} {statistics.median(xs):.0f}/{pct(xs, 0.9):.0f}")
        print("  ".join(line))


def main(argv):
    if len(argv) >= 3 and argv[1] == "fetch":
        fetch(argv[2])
    elif len(argv) >= 4 and argv[1] == "time":
        run(argv[2], argv[3], "--stream" in argv)
    elif len(argv) >= 3 and argv[1] == "report":
        report(argv[2:])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
