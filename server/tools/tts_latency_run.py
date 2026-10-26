"""V2: time the listen path with local Kokoro on a :8012 server.

For each item: ask /query (not timed), then send /speak exactly what the
portal's listen button sends (the response with ** and | cleaned, the brief,
the source) and time:
  text sent  -> response received (the whole WAV: the portal plays the blob
                only once it is complete, so this is when first audio can
                start; the browser's own decode-to-play is not measured);
  first audio -> audio end: the WAV's own duration.
Usage: tts_latency_run.py <out.json>"""
import io, json, sys, time, urllib.request, wave
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from latency_run import B2, B3  # the 20 batch 2/3 harness questions (V1)

BASE = "http://127.0.0.1:8012"
HDR = {"Content-Type": "application/json", "X-Access-Token": "edgecdss-demo-2026", "X-Test-Run": "1"}


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), HDR)
    return urllib.request.urlopen(req, timeout=900)


items = ([("warmup", "Reassess in five minutes.")]
         + [(f"B2-{i+1}", q) for i, q in enumerate(B2)]
         + [(f"B3-{i+1}", q) for i, q in enumerate(B3)]
         + [("MG-A39", "don't want ketamine, I need magnesium, 75 kg")])
out = []
for ident, q in items:
    if ident == "warmup":
        speak = {"text": q, "source": "", "brief": ""}
        d = {}
    else:
        with post("/query", {"query": q, "device_id": "v2-tts", "timestamp": "2026-10-25T00:00:00",
                             "voice_mode": "brief", "conversation_history": []}) as r:
            d = json.load(r)
        speak = {"text": d.get("response", "").replace("**", "").replace("|", ". "),
                 "source": d.get("source", ""), "brief": d.get("brief") or ""}
    t0 = time.perf_counter()
    with post("/speak", speak) as r:
        audio = r.read()
        synth = r.headers.get("X-Synth-Ms")
    t_first = (time.perf_counter() - t0) * 1000
    with wave.open(io.BytesIO(audio)) as w:
        dur = w.getnframes() / w.getframerate() * 1000
    spoken = speak["brief"] or speak["text"]
    row = {"id": ident, "query": q, "source_mode": d.get("source_mode"), "chars_sent": len(spoken),
           "synth_ms": float(synth) if synth else None, "first_audio_ms": round(t_first, 1),
           "audio_ms": round(dur, 1), "audio_end_ms": round(t_first + dur, 1), "spoken": spoken[:300]}
    out.append(row)
    print(ident, row["chars_sent"], row["first_audio_ms"], row["audio_end_ms"], flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1)
