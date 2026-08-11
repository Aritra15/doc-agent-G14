"""Stage 1 — deskew / denoise / binarize / augment"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..contracts import Page


def run(pages: list[Page], cfg: dict) -> list[Page]:
    """Create deterministic, OCR-ready binary page images with a reusable cache."""
    import numpy as np
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    settings = cfg.get("preprocess", {})
    output_dir = Path(cfg.get("paths", {}).get("preprocessed_dir", "data/interim/preprocessed"))
    output_dir.mkdir(parents=True, exist_ok=True)
    median_kernel = int(settings.get("median_kernel", 3))
    if median_kernel < 1 or median_kernel % 2 == 0:
        raise ValueError("preprocess.median_kernel must be a positive odd integer")
    max_skew = float(settings.get("max_skew_degrees", 7.0))
    skew_step = float(settings.get("skew_step", 0.5))
    border_px = int(settings.get("border_px", 24))
    if max_skew < 0 or skew_step <= 0 or border_px < 0:
        raise ValueError("Invalid preprocessing skew or border configuration")

    def otsu_threshold(array: np.ndarray) -> int:
        histogram = np.bincount(array.ravel(), minlength=256).astype(np.float64)
        total = float(array.size)
        weighted_total = float(np.dot(np.arange(256), histogram))
        background_weight = 0.0
        background_sum = 0.0
        best_variance = -1.0
        best_threshold = 127
        for value in range(256):
            background_weight += histogram[value]
            if background_weight == 0:
                continue
            foreground_weight = total - background_weight
            if foreground_weight == 0:
                break
            background_sum += value * histogram[value]
            background_mean = background_sum / background_weight
            foreground_mean = (weighted_total - background_sum) / foreground_weight
            variance = (
                background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
            )
            if variance > best_variance:
                best_variance = variance
                best_threshold = value
        return best_threshold

    def projection_score(image: Image.Image) -> float:
        array = np.asarray(image, dtype=np.uint8)
        threshold = otsu_threshold(array)
        ink_per_row = (array < threshold).sum(axis=1, dtype=np.float64)
        return float(np.var(ink_per_row))

    processed: list[Page] = []
    for page in pages:
        source = Path(page.image_path)
        if not source.exists():
            raise FileNotFoundError(f"Page image does not exist: {source}")
        output_path = output_dir / f"{page.id}.png"
        metadata_path = output_dir / f"{page.id}.json"
        stat = source.stat()
        fingerprint_data = {
            "source": str(source.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "settings": settings,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if output_path.exists() and metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("fingerprint") == fingerprint:
                    processed.append(
                        Page(id=page.id, image_path=str(output_path.resolve()), doc_id=page.doc_id)
                    )
                    continue
            except (OSError, json.JSONDecodeError):
                pass

        with Image.open(source) as opened:
            transposed = ImageOps.exif_transpose(opened)
            image = (transposed if transposed is not None else opened).convert("L")
        image = image.filter(ImageFilter.MedianFilter(size=median_kernel))
        image = ImageOps.autocontrast(image)
        image = ImageEnhance.Sharpness(image).enhance(1.35)

        sample = image.copy()
        sample.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        best_angle = 0.0
        best_score = projection_score(sample)
        candidate = -max_skew
        while candidate <= max_skew + 1e-9:
            rotated_sample = sample.rotate(
                candidate, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=255
            )
            score = projection_score(rotated_sample)
            if score > best_score:
                best_score = score
                best_angle = candidate
            candidate += skew_step
        if abs(best_angle) >= 0.05:
            image = image.rotate(
                best_angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=255
            )

        gray = np.asarray(image, dtype=np.uint8)
        threshold = otsu_threshold(gray)
        binary = np.where(gray <= threshold, 0, 255).astype(np.uint8)
        result = Image.fromarray(binary, mode="L")
        if border_px:
            result = ImageOps.expand(result, border=border_px, fill=255)
        result.save(output_path, format="PNG", optimize=True)
        metadata_path.write_text(
            json.dumps(
                {"fingerprint": fingerprint, "deskew_angle": best_angle, "threshold": threshold},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        processed.append(
            Page(id=page.id, image_path=str(output_path.resolve()), doc_id=page.doc_id)
        )
    return processed
