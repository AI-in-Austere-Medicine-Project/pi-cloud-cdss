"""D3 (owner, work order): pass the model 4 retrieved chunks, not the top-k (10).

The cheaper of a reranker and a score cut on the Jetson is neither model: the
retrieval already ranks by similarity, so the 4 best by that score go to the
model, at no cost. Retrieval still fetches CDSS_RAG_TOP_K (10): the source
mode (JTS-grounded / general / insufficient) is decided on the best score of
all of them, and the chips the medic sees are unchanged. The canine filter
(retrieval_species_filter) is applied at retrieval, as before.
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _results(n, start=0.20, step=0.05):
    """n chunks, best first, as Chroma returns them (distance = 1 - score)."""
    docs = [f"CHUNK-{i} text" for i in range(n)]
    metas = [{"source": f"CPG {i}", "page": i} for i in range(n)]
    dists = [round(start + i * step, 3) for i in range(n)]
    return {"documents": [docs], "metadatas": [metas], "distances": [dists]}


def test_the_model_gets_the_four_best_chunks():
    a = oc.classify_retrieval(_results(10))
    assert [c for c in ("CHUNK-0", "CHUNK-1", "CHUNK-2", "CHUNK-3") if c in a.context_text] == \
        ["CHUNK-0", "CHUNK-1", "CHUNK-2", "CHUNK-3"]
    assert not any(f"CHUNK-{i} " in a.context_text for i in range(4, 10))


def test_the_four_are_the_best_by_score_whatever_the_order():
    r = _results(10)
    order = [7, 2, 9, 0, 5, 1, 8, 3, 6, 4]           # shuffled
    r = {k: [[v[0][i] for i in order]] for k, v in r.items()}
    a = oc.classify_retrieval(r)
    kept = [f"CHUNK-{i}" for i in range(10) if f"CHUNK-{i} " in a.context_text]
    assert kept == ["CHUNK-0", "CHUNK-1", "CHUNK-2", "CHUNK-3"]
    assert a.context_text.index("CHUNK-0") < a.context_text.index("CHUNK-3")   # best first


def test_the_source_mode_and_the_chips_are_unchanged():
    a = oc.classify_retrieval(_results(10))
    assert a.top_score == 0.8 and a.source_mode == "JTS_GROUNDED"
    assert len(a.sources) == 10                     # the client shows the top 3 of these


def test_fewer_than_four_are_all_kept():
    a = oc.classify_retrieval(_results(2))
    assert "CHUNK-0" in a.context_text and "CHUNK-1" in a.context_text


def test_the_number_is_configurable(monkeypatch):
    monkeypatch.setenv("CDSS_RAG_CONTEXT_K", "6")
    a = oc.classify_retrieval(_results(10))
    assert sum(f"CHUNK-{i} " in a.context_text for i in range(10)) == 6


def test_retrieval_still_fetches_the_top_k_with_the_species_filter():
    seen = {}

    class _Spy:
        def query(self, q, n_results=None, where=None):
            seen.update(n_results=n_results, where=where)
            return _results(10)
    oc._query_with_rag_internal("80 kg adult, severe pain from a femur fracture, what do I do", _Spy())
    assert seen["n_results"] == 10
    assert seen["where"] == oc.retrieval_species_filter("80 kg adult, severe pain from a femur fracture, what do I do")
