"""Unit tests for persistent FAISS storage and dense retrieval."""

from pathlib import Path


def test_retrieval_placeholder(tmp_path: Path, monkeypatch):
    import numpy as np
    import pytest

    pytest.importorskip("faiss")
    from doc_agent.contracts import Chunk
    from doc_agent.index import embed, store
    from doc_agent.retrieval.retriever import Retriever

    cfg = {
        "device": "cpu",
        "paths": {"index_dir": str(tmp_path / "index")},
        "embed": {"model": "test-model", "dim": 3},
        "index": {"type": "faiss:flat"},
        "retrieve": {"k": 1},
    }
    chunks = [
        Chunk(id="c1", doc_id="bk1", text="কলেরা", page_ids=["bk1_p001"]),
        Chunk(id="c2", doc_id="bk1", text="জ্বর", page_ids=["bk1_p002"]),
    ]
    vectors = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    store.build(chunks, vectors, cfg)
    loaded_index, loaded_chunks = store.load(cfg)
    assert loaded_index.ntotal == 2
    assert [chunk.id for chunk in loaded_chunks] == ["c1", "c2"]

    monkeypatch.setattr(
        embed,
        "encode",
        lambda query_chunks, query_cfg: np.asarray([[0.0, 1.0, 0.0]], dtype=np.float32),
    )
    results = Retriever(cfg).retrieve("জ্বর", k=1)
    assert results[0].id == "c2"
    assert results[0].score == pytest.approx(1.0)
