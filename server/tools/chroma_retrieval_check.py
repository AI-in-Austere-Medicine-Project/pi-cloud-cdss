"""V3: prove retrieval is unchanged when onnxruntime-gpu is installed.

The replay sets never query Chroma, so they cannot show this on their own.
This runs every query the replay sets hold (unique query texts from
replay-out/{pipe,served,held,gate}_*.json) against a Chroma DB the way the
pipeline does (top k = CDSS_RAG_TOP_K default 10, with the species filter),
and saves the ids and distances.

  chroma_retrieval_check.py dump <tree/server> <chroma_db> <replay-out> <out.json>
  chroma_retrieval_check.py compare <a.json> <b.json>

It also saves each query's vector as Chroma embeds it (collection._embed), the
one thing the provider pin controls. compare prints how many vectors differ
and by how much, how many queries return different ids (order included), the
first rank at which they differ, and the largest distance difference.

Chroma's HNSW search is approximate and not fully repeatable: the same code
and DB run twice can return a different chunk in the last ranks. So identical
vectors are the proof; an ids difference is read against a main-vs-main run.
"""
import json
import os
import sys
import time


def queries(replay_dir):
    qs = set()
    for name in sorted(os.listdir(replay_dir)):
        kind = name.split("_", 1)[0]
        if not name.endswith(".json") or kind not in ("pipe", "served", "held", "gate"):
            continue
        d = json.load(open(os.path.join(replay_dir, name)))
        for key, row in d.items():
            if kind == "pipe":
                qs.add(row.get("query") or "")
            else:
                qs.add(json.loads(key)[1])
    return sorted(q for q in qs if q.strip())


def dump(tree, db, replay_dir, out):
    sys.path.insert(0, tree)
    os.environ["CHROMADB_PATH"] = db
    import onnxruntime as ort
    from embeddings import ChromaDBClient
    from openai_client import retrieval_species_filter
    client = ChromaDBClient()
    qs = queries(replay_dir)
    rows, t0 = {}, time.perf_counter()
    for q in qs:
        r = client.query(q, n_results=10, where=retrieval_species_filter(q))
        vec = client.collection._embed(input=[q], is_query=True)[0]
        rows[q] = {"ids": r["ids"][0], "distances": r["distances"][0],
                   "vector": [float(x) for x in vec]}
    ef = client.collection._embedding_function
    onnx = getattr(ef, "_onnx", None)
    meta = {"ort": ort.__version__, "available": ort.get_available_providers(),
            "session": onnx.model.get_providers() if onnx is not None else "chroma default (per call)",
            "n": len(qs), "seconds": round(time.perf_counter() - t0, 1)}
    json.dump({"meta": meta, "rows": rows}, open(out, "w"))
    print(json.dumps(meta))


def compare(a, b):
    A, B = json.load(open(a)), json.load(open(b))
    print("a:", A["meta"]), print("b:", B["meta"])
    ids_diff, worst, vec_diff, vec_worst, missing = [], 0.0, 0, 0.0, 0
    for q, ra in A["rows"].items():
        rb = B["rows"].get(q)
        if rb is None:
            missing += 1
            continue
        if "vector" in ra and "vector" in rb:
            d = max(abs(x - y) for x, y in zip(ra["vector"], rb["vector"]))
            vec_diff += d > 0
            vec_worst = max(vec_worst, d)
        if ra["ids"] != rb["ids"]:
            first = next(i for i, (x, y) in enumerate(zip(ra["ids"], rb["ids"])) if x != y)
            ids_diff.append((q, first + 1))
        else:
            worst = max([worst] + [abs(x - y) for x, y in zip(ra["distances"], rb["distances"])])
    print(f"queries {len(A['rows'])}  missing {missing}  vectors differ {vec_diff} (max {vec_worst:.3g})  "
          f"ids differ {len(ids_diff)}  max distance diff (same ids) {worst:.3g}")
    for q, rank in ids_diff[:20]:
        print(f"  DIFF from rank {rank}: {q[:80]!r}")
    return 1 if vec_diff or missing else 0


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] == "dump":
        dump(*sys.argv[2:])
    elif len(sys.argv) == 4 and sys.argv[1] == "compare":
        sys.exit(compare(*sys.argv[2:]))
    else:
        print(__doc__)
        sys.exit(2)
