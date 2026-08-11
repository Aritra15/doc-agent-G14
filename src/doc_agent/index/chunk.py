"""Stage 4 — chunk text"""

from __future__ import annotations

import re
import unicodedata

from ..contracts import Chunk


def split(chunks: list[Chunk], cfg: dict) -> list[Chunk]:
    """Normalize OCR text, prefer remedy-entry boundaries, then apply token windows."""
    from transformers import AutoTokenizer

    max_tokens = int(cfg.get("index", {}).get("chunk_tokens", 512))
    overlap = int(cfg.get("index", {}).get("overlap", 64))
    if max_tokens <= 0 or overlap < 0 or overlap >= max_tokens:
        raise ValueError("index chunk_tokens must be positive and overlap must be smaller")
    model_name = str(cfg.get("embed", {}).get("model", "BAAI/bge-m3"))
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    aliases = cfg.get("normalization", {}).get("remedy_aliases", {})

    def normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFC", text)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\u200b", "").replace("\ufeff", "")
        normalized = "".join(
            character
            for character in normalized
            if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
        )
        normalized = "\n".join(
            re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()
        )
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
        for remedy_id, variants in aliases.items():
            marker = f"[remedy:{remedy_id}]"
            for variant in sorted((str(value) for value in variants), key=len, reverse=True):
                if not variant:
                    continue
                pattern = re.compile(re.escape(variant), flags=re.IGNORECASE)

                def add_marker(
                    match: re.Match[str],
                    source_text: str = normalized,
                    expected_marker: str = marker,
                ) -> str:
                    following = source_text[match.end() : match.end() + len(expected_marker) + 1]
                    return (
                        match.group(0)
                        if expected_marker in following
                        else f"{match.group(0)} {expected_marker}"
                    )

                normalized = pattern.sub(add_marker, normalized)
        return normalized

    output: list[Chunk] = []
    for source in chunks:
        normalized = normalize_text(source.text)
        if not normalized:
            continue
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        if not paragraphs:
            paragraphs = [normalized]

        entries: list[str] = []
        current: list[str] = []
        for paragraph in paragraphs:
            starts_entry = "[remedy:" in paragraph
            if starts_entry and current:
                entries.append("\n\n".join(current))
                current = []
            current.append(paragraph)
        if current:
            entries.append("\n\n".join(current))

        pieces: list[str] = []
        for entry in entries:
            token_ids = tokenizer.encode(entry, add_special_tokens=False)
            if len(token_ids) <= max_tokens:
                pieces.append(entry)
                continue
            start = 0
            while start < len(token_ids):
                window = token_ids[start : start + max_tokens]
                decoded = tokenizer.decode(
                    window, skip_special_tokens=True, clean_up_tokenization_spaces=False
                ).strip()
                if decoded:
                    pieces.append(decoded)
                if start + max_tokens >= len(token_ids):
                    break
                start += max_tokens - overlap

        base_page_id = source.page_ids[0] if source.page_ids else source.id.removesuffix("_ocr")
        for position, text in enumerate(pieces, start=1):
            output.append(
                Chunk(
                    id=f"{base_page_id}_c{position:03d}",
                    doc_id=source.doc_id,
                    text=text,
                    page_ids=list(source.page_ids),
                )
            )
    return output
