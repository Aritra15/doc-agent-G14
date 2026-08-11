"""Stage 5 — dense retrieval"""

from __future__ import annotations

from ..contracts import Chunk


class Retriever:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg["retrieve"]
        self.full_cfg = cfg
        from ..index import store

        self.index, self.chunks = store.load(cfg)

    def retrieve(self, query: str, k: int | None = None) -> list[Chunk]:
        """Top-k dense retrieval. Set chunk.score (relevance) on every result so decide() can judge
        whether the evidence is weak. IMPLEMENT."""
        from ..index import embed

        query = query.strip()
        if not query:
            raise ValueError("Retrieval query must not be empty")
        requested_k = int(k if k is not None else self.cfg.get("k", 10))
        if requested_k <= 0:
            raise ValueError("Retrieval k must be positive")
        if not self.chunks:
            return []
        query_chunk = Chunk(id="__query__", doc_id="__query__", text=query, page_ids=[])
        query_vector = embed.encode([query_chunk], self.full_cfg)
        scores, positions = self.index.search(query_vector, min(requested_k, len(self.chunks)))
        results: list[Chunk] = []
        for score, position in zip(scores[0], positions[0], strict=False):
            if position < 0:
                continue
            results.append(self.chunks[int(position)].model_copy(update={"score": float(score)}))
        return results


# --- evidence-strength policy: read by agent.decide() for evidence-gated re-search ---
def top_score(chunks: list[Chunk]) -> float:
    """Strength of the current evidence = best chunk score (0.0 if empty)."""
    return max((c.score for c in chunks), default=0.0)


def is_weak(chunks: list[Chunk], cfg: dict) -> bool:
    """Weak evidence = best score below cfg.retrieve.weak_threshold."""
    return top_score(chunks) < cfg["retrieve"]["weak_threshold"]


def next_k(k: int, cfg: dict) -> int | None:
    """Widen the net: k + k_step, or None once it would exceed k_max (signal to ABSTAIN)."""
    nk = k + cfg["retrieve"]["k_step"]
    return nk if nk <= cfg["retrieve"]["k_max"] else None
