"""V3: Chroma's embedder stays on the CPU when onnxruntime-gpu is installed.

Chroma's default embedder uses every provider onnxruntime reports. With the
GPU wheel that list includes CUDA, so retrieval would move to the GPU. The
pin keeps the provider list to the CPU whatever onnxruntime reports.
"""
import importlib.util
import pathlib

import onnxruntime as ort
import pytest

# Loaded from the file under its own name: other tests put a stub
# "embeddings" in sys.modules so the pipeline imports without Chroma.
_spec = importlib.util.spec_from_file_location(
    "embeddings_real", pathlib.Path(__file__).resolve().parent.parent / "embeddings.py")
embeddings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(embeddings)


def test_pin_is_cpu_only():
    assert embeddings.CHROMA_PROVIDERS == ["CPUExecutionProvider"]


def test_embedder_keeps_the_default_name():
    # The collection's stored config names "default"; another name would conflict.
    assert embeddings.CpuDefaultEmbeddingFunction.name() == "default"


def test_session_asks_for_cpu_even_when_cuda_is_reported(monkeypatch):
    asked = {}

    class FakeSession:
        def __init__(self, path, providers=None, sess_options=None, **kw):
            asked["providers"] = list(providers)

    monkeypatch.setattr(ort, "get_available_providers",
                        lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setattr(ort, "InferenceSession", FakeSession)
    ef = embeddings.CpuDefaultEmbeddingFunction()
    assert ef._onnx is None  # nothing loads until the first query
    try:
        ef._engine().model  # builds the session through ort.InferenceSession
    except FileNotFoundError as e:
        pytest.skip(f"MiniLM model not cached here: {e}")
    assert asked["providers"] == ["CPUExecutionProvider"]


def test_client_collection_uses_the_pinned_embedder(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMADB_PATH", str(tmp_path))
    c = embeddings.ChromaDBClient()
    assert isinstance(c.collection._embedding_function, embeddings.CpuDefaultEmbeddingFunction)


def test_existing_collection_queries_through_the_pin(tmp_path, monkeypatch):
    # The live DB already exists with the stored "default" config. Chroma
    # ignores a DefaultEmbeddingFunction instance and rebuilds its own, so check
    # the pinned embedder is what actually embeds the query.
    import chromadb
    from chromadb.api.types import DefaultEmbeddingFunction
    db = str(tmp_path)
    chromadb.PersistentClient(path=db).get_or_create_collection(
        "jts_protocols", embedding_function=None).add(
        ids=["a", "b"], embeddings=[[0.0] * 384, [1.0] * 384], documents=["x", "y"])
    calls = []
    monkeypatch.setattr(embeddings.CpuDefaultEmbeddingFunction, "_engine",
                        lambda self: (lambda input: calls.append(list(input)) or [[1.0] * 384]))
    monkeypatch.setattr(DefaultEmbeddingFunction, "__call__",
                        lambda self, input: pytest.fail("stock default embedder used"))
    monkeypatch.setenv("CHROMADB_PATH", db)
    r = embeddings.ChromaDBClient().query("tourniquet", n_results=1)
    assert calls == [["tourniquet"]]
    assert r["ids"] == [["b"]]
