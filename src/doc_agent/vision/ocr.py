"""Stage 3 — OCR/HTR (BASELINE = pretrained foundation, fine-tuned)"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from ..contracts import Chunk, Region


class Reader:
    """Model set by cfg['ocr']. Baseline: pretrained TrOCR/Donut/Tesseract."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg["ocr"]
        self.paths = cfg.get("paths", {})
        self.last_confidence = 0.0

    def transcribe_region(self, region: Region) -> str:
        """Crop one region and transcribe it through the Tesseract TSV interface."""
        from PIL import Image

        configured_cmd = str(self.cfg.get("tesseract_cmd", "")).strip()
        common_windows = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        if configured_cmd and Path(configured_cmd).exists():
            tesseract_cmd = configured_cmd
        elif shutil.which(configured_cmd or "tesseract"):
            tesseract_cmd = shutil.which(configured_cmd or "tesseract") or "tesseract"
        elif common_windows.exists():
            tesseract_cmd = str(common_windows)
        else:
            raise RuntimeError(
                "Tesseract was not found. Configure ocr.tesseract_cmd or add it to PATH."
            )

        processed_dir = Path(self.paths.get("preprocessed_dir", "data/interim/preprocessed"))
        image_path = processed_dir / f"{region.page_id}.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Preprocessed page does not exist: {image_path}")
        with Image.open(image_path) as source:
            left, top, right, bottom = region.bbox
            crop = source.convert("L").crop((left, top, right, bottom))
            temporary = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temporary_path = Path(temporary.name)
            temporary.close()
            crop.save(temporary_path, format="PNG")

        psm = int(
            self.cfg.get("heading_psm", 7)
            if region.kind == "heading"
            else self.cfg.get("body_psm", 6)
        )
        command = [
            tesseract_cmd,
            str(temporary_path),
            "stdout",
            "-l",
            str(self.cfg.get("lang", "ben+eng")),
            "--oem",
            str(int(self.cfg.get("oem", 1))),
            "--psm",
            str(psm),
            "-c",
            "preserve_interword_spaces=1",
        ]
        tessdata_dir = str(self.cfg.get("tessdata_dir", "")).strip()
        if tessdata_dir:
            command.extend(["--tessdata-dir", tessdata_dir])
        command.append("tsv")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        finally:
            temporary_path.unlink(missing_ok=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Tesseract OCR failed for {region.page_id}: {result.stderr.strip()}"
            )

        lines: dict[tuple[int, int, int], list[tuple[int, str]]] = {}
        confidences: list[float] = []
        for order, row in enumerate(csv.DictReader(io.StringIO(result.stdout), delimiter="\t")):
            text = row.get("text", "").strip()
            if not text:
                continue
            try:
                key = (
                    int(row.get("block_num", "0")),
                    int(row.get("par_num", "0")),
                    int(row.get("line_num", "0")),
                )
                confidence = float(row.get("conf", "-1"))
            except (TypeError, ValueError):
                continue
            lines.setdefault(key, []).append((order, text))
            if confidence >= 0:
                confidences.append(confidence)
        ordered_lines = [
            " ".join(word for _, word in sorted(words)) for _, words in sorted(lines.items())
        ]
        text = "\n".join(line for line in ordered_lines if line.strip())
        text = unicodedata.normalize("NFC", text)
        text = text.replace("\u200b", "").replace("\ufeff", "")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        self.last_confidence = sum(confidences) / (100.0 * len(confidences)) if confidences else 0.0
        return text


def transcribe(regions: list[Region], cfg: dict) -> list[Chunk]:
    """Transcribe ordered regions and cache one OCR Chunk per source page."""
    grouped: dict[str, list[Region]] = {}
    for region in regions:
        grouped.setdefault(region.page_id, []).append(region)
    reader = Reader(cfg)
    processed_dir = Path(cfg.get("paths", {}).get("preprocessed_dir", "data/interim/preprocessed"))
    cache_dir = Path(cfg.get("paths", {}).get("ocr_dir", "data/interim/ocr"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    output: list[Chunk] = []

    for page_id, page_regions in grouped.items():
        page_regions = sorted(page_regions, key=lambda region: (region.bbox[1], region.bbox[0]))
        image_path = processed_dir / f"{page_id}.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Preprocessed page does not exist: {image_path}")
        stat = image_path.stat()
        fingerprint_payload = {
            "image_size": stat.st_size,
            "image_mtime_ns": stat.st_mtime_ns,
            "ocr": cfg.get("ocr", {}),
            "regions": [region.model_dump(mode="json") for region in page_regions],
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        cache_path = cache_dir / f"{page_id}.json"
        cached: dict = {}
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached = {}

        if cached.get("fingerprint") == fingerprint:
            page_text = str(cached.get("text", ""))
        else:
            texts: list[str] = []
            confidences: list[float] = []
            for region in page_regions:
                region_text = reader.transcribe_region(region)
                if region_text:
                    texts.append(region_text)
                    confidences.append(reader.last_confidence)
            page_text = "\n\n".join(texts).strip()
            mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            temporary_path = cache_path.with_suffix(".json.tmp")
            temporary_path.write_text(
                json.dumps(
                    {
                        "page_id": page_id,
                        "fingerprint": fingerprint,
                        "text": page_text,
                        "ocr_confidence": mean_confidence,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary_path.replace(cache_path)

        doc_id = page_id.rsplit("_p", 1)[0] if "_p" in page_id else page_id.split("_", 1)[0]
        output.append(
            Chunk(
                id=f"{page_id}_ocr",
                doc_id=doc_id,
                text=page_text,
                page_ids=[page_id],
            )
        )
    return output
