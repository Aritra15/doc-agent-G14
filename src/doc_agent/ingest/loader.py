"""Stage 1 — load scanned page-images"""

from __future__ import annotations

import re
from pathlib import Path

from ..contracts import Page


def load_pages(cfg: dict) -> list[Page]:
    """Read configured page images and return stable, document-scoped Page objects."""
    raw_dir = Path(cfg.get("paths", {}).get("raw_dir", "data/raw"))
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw corpus directory does not exist: {raw_dir}")

    extensions = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
    image_paths = sorted(
        (
            path
            for path in raw_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in extensions
        ),
        key=lambda path: path.relative_to(raw_dir).as_posix().casefold(),
    )
    if not image_paths:
        raise ValueError(f"No scanned page images found under {raw_dir}")

    by_document: dict[str, list[Path]] = {}
    for image_path in image_paths:
        relative = image_path.relative_to(raw_dir)
        doc_id = relative.parts[0] if len(relative.parts) > 1 else image_path.parent.name
        if image_path.parent == raw_dir:
            match = re.match(r"(?P<doc>.+?)[_-]p?\d+$", image_path.stem, flags=re.IGNORECASE)
            doc_id = match.group("doc") if match else "corpus"
        by_document.setdefault(doc_id, []).append(image_path)

    pages: list[Page] = []
    seen_ids: set[str] = set()
    for doc_id in sorted(by_document, key=str.casefold):
        for ordinal, image_path in enumerate(by_document[doc_id], start=1):
            explicit = re.fullmatch(
                rf"{re.escape(doc_id)}[_-]p(\d+)", image_path.stem, flags=re.IGNORECASE
            )
            page_number = int(explicit.group(1)) if explicit else ordinal
            page_id = f"{doc_id}_p{page_number:03d}"
            if page_id in seen_ids:
                raise ValueError(f"Duplicate derived page id {page_id} from {image_path}")
            seen_ids.add(page_id)
            pages.append(Page(id=page_id, image_path=str(image_path.resolve()), doc_id=doc_id))
    return pages
