"""Unit tests for normalization/chunking and embedding behavior."""

import sys
import types


def test_eval_placeholder(monkeypatch):
    import numpy as np
    import transformers
    from doc_agent.contracts import Chunk
    from doc_agent.index import chunk, embed

    class FakeTokenizer:
        def encode(self, text, add_special_tokens=False):
            return text.split()

        def decode(self, tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False):
            return " ".join(tokens)

    monkeypatch.setattr(
        transformers.AutoTokenizer, "from_pretrained", lambda model_name: FakeTokenizer()
    )
    cfg = {
        "device": "cpu",
        "index": {"chunk_tokens": 8, "overlap": 2},
        "embed": {"model": "fake-model", "dim": 3, "batch_size": 2, "max_length": 8},
        "normalization": {"remedy_aliases": {"veratrum_album": ["ভিরেট্রাম"]}},
    }
    source = Chunk(
        id="bk1_p001_ocr",
        doc_id="bk1",
        text="ভিরেট্রাম ৩০\n\nএক দুই তিন চার পাঁচ ছয় সাত আট নয়",
        page_ids=["bk1_p001"],
    )
    pieces = chunk.split([source], cfg)
    assert pieces[0].id == "bk1_p001_c001"
    assert "ভিরেট্রাম [remedy:veratrum_album]" in pieces[0].text
    assert "৩০" in pieces[0].text
    assert all(piece.page_ids == ["bk1_p001"] for piece in pieces)

    fake_module = types.ModuleType("sentence_transformers")

    class FakeSentenceTransformer:
        def __init__(self, model_name, device):
            self.max_seq_length = 0

        def encode(self, texts, **kwargs):
            return np.asarray([[3.0, 4.0, 0.0] for _ in texts], dtype=np.float32)

    fake_module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    vectors = embed.encode(pieces[:1], cfg)
    assert vectors.shape == (1, 3)
    assert vectors.dtype == np.float32
