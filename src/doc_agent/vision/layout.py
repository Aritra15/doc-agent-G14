"""Stage 2 — layout detection / segmentation"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
from pathlib import Path
import os
from tqdm import tqdm

from ..contracts import Page, Region


def detect(pages: list[Page], cfg: dict) -> list[Region]:
    """Detect Tesseract text blocks and classify prominent top blocks as headings."""
    from PIL import Image

    ocr_cfg = cfg.get("ocr", {})
    configured_cmd = str(ocr_cfg.get("tesseract_cmd", "")).strip()
    common_windows = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
    env_prefix = Path(os.environ.get("TESSERACT_ENV_PREFIX", Path.home() / ".local" / "share" / "tesseract-env"))
    userspace_candidates = [
        env_prefix / "bin" / "tesseract",
        env_prefix / "Library" / "bin" / "tesseract.exe",
    ]

    if next((p for p in userspace_candidates if p.exists()), None):
        tesseract_cmd = str(next(p for p in userspace_candidates if p.exists()))
    elif configured_cmd and Path(configured_cmd).exists():
        tesseract_cmd = configured_cmd
    elif configured_cmd and shutil.which(configured_cmd):
        tesseract_cmd = shutil.which(configured_cmd) or "tesseract"
    elif shutil.which("tesseract"):
        # Configured path missing (e.g. a Windows path on Linux) — fall back to PATH.
        tesseract_cmd = shutil.which("tesseract") or "tesseract"
    elif common_windows.exists():
        tesseract_cmd = str(common_windows)
    else:
        raise RuntimeError(
            "Tesseract was not found. Configure ocr.tesseract_cmd or add it to PATH."
        )

    language = str(ocr_cfg.get("lang", "ben+eng"))
    oem = int(ocr_cfg.get("oem", 1))
    psm = int(cfg.get("layout", {}).get("psm", 3))
    tessdata_dir = str(ocr_cfg.get("tessdata_dir", "")).strip()
    regions: list[Region] = []

    for page in tqdm(pages, desc="Detecting layout"):
        image_path = Path(page.image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Preprocessed page does not exist: {image_path}")
        with Image.open(image_path) as image:
            page_width, page_height = image.size

        command = [
            tesseract_cmd,
            str(image_path),
            "stdout",
            "-l",
            language,
            "--oem",
            str(oem),
            "--psm",
            str(psm),
        ]
        if tessdata_dir:
            command.extend(["--tessdata-dir", tessdata_dir])
        command.append("tsv")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Tesseract layout failed for {page.id}: {result.stderr.strip()}")

        blocks: dict[int, dict[str, int]] = {}
        block_heights: dict[int, list[int]] = {}
        all_word_heights: list[int] = []
        for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
            try:
                if int(row.get("level", "0")) != 5 or not row.get("text", "").strip():
                    continue
                block_number = int(row["block_num"])
                left = int(row["left"])
                top = int(row["top"])
                width = int(row["width"])
                height = int(row["height"])
            except (KeyError, TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            all_word_heights.append(height)
            block = blocks.setdefault(
                block_number,
                {
                    "left": left,
                    "top": top,
                    "right": left + width,
                    "bottom": top + height,
                    "words": 0,
                },
            )
            block["left"] = min(block["left"], left)
            block["top"] = min(block["top"], top)
            block["right"] = max(block["right"], left + width)
            block["bottom"] = max(block["bottom"], top + height)
            block["words"] += 1
            block_heights.setdefault(block_number, []).append(height)

        if not blocks:
            regions.append(
                Region(page_id=page.id, bbox=(0, 0, page_width, page_height), kind="text")
            )
            continue

        sorted_heights = sorted(all_word_heights)
        median_height = sorted_heights[len(sorted_heights) // 2] if sorted_heights else 1
        page_regions: list[Region] = []
        for block_number, block in blocks.items():
            left = max(0, min(block["left"], page_width))
            top = max(0, min(block["top"], page_height))
            right = max(left + 1, min(block["right"], page_width))
            bottom = max(top + 1, min(block["bottom"], page_height))
            heights = sorted(block_heights.get(block_number, []))
            block_median = heights[len(heights) // 2] if heights else median_height
            block_width = right - left
            centered = abs(((left + right) / 2) - (page_width / 2)) <= page_width * 0.18
            near_top = top <= page_height * 0.22
            short_block = (bottom - top) <= page_height * 0.13
            prominent = block_median >= median_height * 1.12
            few_words = block["words"] <= 16
            kind = (
                "heading"
                if near_top and short_block and few_words and (prominent or centered)
                else "text"
            )
            if block_width >= 3 and bottom - top >= 3:
                page_regions.append(
                    Region(page_id=page.id, bbox=(left, top, right, bottom), kind=kind)
                )
        if not page_regions:
            page_regions.append(
                Region(page_id=page.id, bbox=(0, 0, page_width, page_height), kind="text")
            )
        regions.extend(sorted(page_regions, key=lambda region: (region.bbox[1], region.bbox[0])))
    return regions
