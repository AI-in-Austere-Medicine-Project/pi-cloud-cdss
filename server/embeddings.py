"""
EdgeCDSS — ChromaDB client wrapper
Faithful to the original cdss-hybrid embeddings.py (arcaneone deployment):
  - Chroma DEFAULT embedding function (all-MiniLM, runs locally on-device — offline, no API cost)
  - collection: jts_protocols
  - DB path: CHROMADB_PATH env var, default ./cache/chromadb (relative to working dir)
A ChromaDB rescued from arcaneone was built with exactly these settings.

The embedder is pinned to the CPU. Chroma's default asks onnxruntime for every
available provider, so installing onnxruntime-gpu (for Kokoro, V3) would move
retrieval onto the GPU without a code change. Pinned, it cannot: same model,
same provider, same vectors as before.
"""

import chromadb
import os
from typing import List, Dict

from chromadb.api.types import EmbeddingFunction

CHROMA_PROVIDERS = ["CPUExecutionProvider"]


class CpuDefaultEmbeddingFunction(EmbeddingFunction):
    """Chroma's default embedder (all-MiniLM-L6-v2, ONNX) on the CPU only.

    Named "default" to match the collection's stored config. Deliberately not a
    DefaultEmbeddingFunction subclass: Chroma ignores any instance of that class
    and rebuilds the stock default (all providers) from the stored config."""

    def __init__(self) -> None:
        self._onnx = None

    def _engine(self):
        if self._onnx is None:
            from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
            self._onnx = ONNXMiniLM_L6_V2(preferred_providers=list(CHROMA_PROVIDERS))
        return self._onnx

    def __call__(self, input):
        return self._engine()(input)

    @staticmethod
    def name() -> str:
        return "default"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return CpuDefaultEmbeddingFunction()

    @staticmethod
    def validate_config(config) -> None:
        return

    def max_tokens(self) -> int:
        return 256


class ChromaDBClient:
    def __init__(self):
        db_path = os.getenv("CHROMADB_PATH", "./cache/chromadb")
        self.client = chromadb.PersistentClient(path=db_path)

        # Create or get collection for JTS protocols
        self.collection = self.client.get_or_create_collection(
            name="jts_protocols",
            metadata={"description": "Joint Trauma System Clinical Practice Guidelines"},
            embedding_function=CpuDefaultEmbeddingFunction(),
        )
        print(f"📦 ChromaDB: jts_protocols at {os.path.abspath(db_path)} "
              f"({self.collection.count()} chunks)")

    def add_documents(self, documents: List[str], metadatas: List[Dict], ids: List[str]):
        """Add documents to the vector database"""
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

    def query(self, query_text: str, n_results: int = 5, where: Dict = None) -> Dict:
        """Query the vector database. `where` is a Chroma metadata filter; the
        pipeline passes one to keep canine documents out of human queries."""
        kwargs = {"query_texts": [query_text], "n_results": n_results}
        if where:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    def get_collection_count(self) -> int:
        """Get number of documents in collection"""
        return self.collection.count()
