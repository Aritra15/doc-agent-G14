"""Stage 4 — vector store"""

from __future__ import annotations

import json
from pathlib import Path

from ..contracts import Chunk


def build(chunks, vectors, cfg: dict) -> None:  # type: ignore[no-untyped-def]
    """Build and atomically persist a normalized-vector FAISS Flat index."""
    import faiss
    import numpy as np

    if cfg.get("index", {}).get("type", "faiss:flat") != "faiss:flat":
        raise ValueError("This A2 implementation supports only index.type=faiss:flat")
    array = np.ascontiguousarray(vectors, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("Embedding vectors must be a two-dimensional array")
    if len(chunks) != array.shape[0]:
        raise ValueError("Chunk count and embedding vector count do not match")
    expected_dimension = int(cfg.get("embed", {}).get("dim", 1024))
    if array.shape[1] != expected_dimension:
        raise ValueError(
            f"Embedding dimension {array.shape[1]} does not match configured {expected_dimension}"
        )
    if array.shape[0] == 0:
        raise ValueError("Cannot build an index with no chunks")
    faiss.normalize_L2(array)
    index = faiss.IndexFlatIP(expected_dimension)
    index.add(array)

    index_dir = Path(cfg.get("paths", {}).get("index_dir", "data/interim/index"))
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "index.faiss"
    metadata_path = index_dir / "chunks.json"
    temporary_index = index_dir / "index.faiss.tmp"
    temporary_metadata = index_dir / "chunks.json.tmp"
    faiss.write_index(index, str(temporary_index))
    temporary_metadata.write_text(
        json.dumps(
            {
                "embedding_model": cfg.get("embed", {}).get("model", "BAAI/bge-m3"),
                "dimension": expected_dimension,
                "index_type": "faiss:flat",
                "count": len(chunks),
                "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_index.replace(index_path)
    temporary_metadata.replace(metadata_path)


def load(cfg: dict):  # type: ignore[no-untyped-def]
    """Load and validate the persisted FAISS index and its ordered Chunk metadata."""
    import faiss

    index_dir = Path(cfg.get("paths", {}).get("index_dir", "data/interim/index"))
    index_path = index_dir / "index.faiss"
    metadata_path = index_dir / "chunks.json"
    if not index_path.exists() or not metadata_path.exists():
        raise FileNotFoundError(
            f"Missing persisted index artifacts under {index_dir}; run the index build first"
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid chunk metadata JSON: {metadata_path}") from exc
    expected_model = cfg.get("embed", {}).get("model", "BAAI/bge-m3")
    expected_dimension = int(cfg.get("embed", {}).get("dim", 1024))
    if metadata.get("embedding_model") != expected_model:
        raise ValueError("Persisted embedding model does not match current configuration")
    if int(metadata.get("dimension", -1)) != expected_dimension:
        raise ValueError("Persisted embedding dimension does not match current configuration")
    if metadata.get("index_type") != "faiss:flat":
        raise ValueError("Persisted index type is not faiss:flat")
    chunks = [Chunk.model_validate(item) for item in metadata.get("chunks", [])]
    index = faiss.read_index(str(index_path))
    if index.d != expected_dimension:
        raise ValueError("FAISS index dimension does not match its metadata")
    if index.ntotal != len(chunks) or int(metadata.get("count", -1)) != len(chunks):
        raise ValueError("FAISS index and chunk metadata counts do not match")
    return index, chunks
