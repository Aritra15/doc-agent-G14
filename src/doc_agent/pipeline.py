"""FIXED end-to-end order (Stages 0-9) + cross-cutting seams.
Do not reorder stages or remove hooks.run()/register_all() calls."""
from __future__ import annotations
from . import config, hooks, wiring  # noqa: F401
from .ingest import loader, preprocess, enhance
from .vision import layout, ocr
from .index import chunk, embed, store
from .retrieval import retriever
from .agent import agent
import time

def build_knowledge_base(cfg: dict) -> None:
    # print time duration for each stage
    t0 = time.time()

    wiring.register_all(cfg)                        # wire cross-cutting features
    print("starting loading pages...")
    pages = loader.load_pages(cfg)
    t1 = time.time()
    print(f"loaded {len(pages)} pages from {cfg.get('paths', {}).get('raw_dir', 'data/raw')} in {t1 - t0:.2f} seconds")

    print("starting preprocessing pages...")
    pages = preprocess.run(pages, cfg)
    t2 = time.time()
    print(f"preprocessed {len(pages)} pages into {cfg.get('paths', {}).get('preprocessed_dir', 'data/interim/preprocessed')} in {t2 - t1:.2f} seconds")

    print("starting enhancement...")
    pages = enhance.run(pages, cfg)                 # Stage 1 - enhancement (VAE/diffusion)
    t3 = time.time()
    print(f"enhanced {len(pages)} pages in {t3 - t2:.2f} seconds")
    hooks.run(hooks.AFTER_INGEST, {"pages": pages})

    print("starting layout detection...")
    regions = layout.detect(pages, cfg)             # Stage 2
    t4 = time.time()
    print(f"detected {len(regions)} regions across {len(pages)} pages in {t4 - t3:.2f} seconds  ")

    print("starting OCR...")
    text = ocr.transcribe(regions, cfg)             # Stage 3
    t5 = time.time()
    print(f"transcribed {len(text)} OCR chunks across {len(regions)} regions in {t5 - t4:.2f} seconds")
    hooks.run(hooks.AFTER_OCR, {"chunks": text})    # e.g. PII redaction on extracted text

    print("starting chunking...")
    chunks = chunk.split(text, cfg)                 # Stage 4
    t6 = time.time()
    print(f"split {len(text)} OCR chunks into {len(chunks)} indexable chunks in {t6 - t5:.2f} seconds")
    hooks.run(hooks.BEFORE_INDEX, {"chunks": chunks})

    print("starting embedding...")
    vectors = embed.encode(chunks, cfg)
    t7 = time.time()
    print(f"encoded {len(chunks)} indexable chunks into {len(vectors)} vectors in {t7 - t6:.2f} seconds")

    print("starting storage...")
    store.build(chunks, vectors, cfg)
    t8 = time.time()
    print(f"storage built successfully in {t8 - t7:.2f} seconds")

def answer(query_text: str, cfg: dict):
    wiring.register_all(cfg)
    r = retriever.Retriever(cfg)                    # Stage 5
    return agent.Agent(cfg, r).run(query_text)      # Stage 6 (seams run inside the loop)
