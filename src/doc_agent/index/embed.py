"""Stage 4 — embed chunks"""

from __future__ import annotations

from ..contracts import Chunk


def encode(chunks: list[Chunk], cfg: dict):  # type: ignore[no-untyped-def]
    """Encode chunks as normalized dense float32 vectors using the configured model."""
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    embed_cfg = cfg.get("embed", {})
    dimension = int(embed_cfg.get("dim", 1024))
    if not chunks:
        return np.empty((0, dimension), dtype=np.float32)
    texts = [chunk.text.strip() for chunk in chunks]
    if any(not text for text in texts):
        raise ValueError("Cannot embed empty chunk text")

    requested_device = str(cfg.get("device", "cpu"))
    device = "cuda" if requested_device.startswith("cuda") and torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(str(embed_cfg.get("model", "BAAI/bge-m3")), device=device)
    model.max_seq_length = int(embed_cfg.get("max_length", 512))
    if device == "cuda" and bool(embed_cfg.get("use_fp16", True)):
        model.half()
    vectors = model.encode(
        texts,
        batch_size=int(embed_cfg.get("batch_size", 4)),
        show_progress_bar=len(texts) > 16,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape != (len(chunks), dimension):
        raise ValueError(
            f"Embedding shape {vectors.shape} does not match ({len(chunks)}, {dimension})"
        )
    return vectors
