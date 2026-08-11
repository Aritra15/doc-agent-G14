"""Unit tests for page loading and classical preprocessing."""

from pathlib import Path


def test_ingest_placeholder(tmp_path: Path):
    import numpy as np
    from doc_agent.ingest import loader, preprocess
    from PIL import Image, ImageDraw

    raw = tmp_path / "raw" / "bk1"
    raw.mkdir(parents=True)
    for number in (1, 2):
        image = Image.new("L", (240, 140), 255)
        draw = ImageDraw.Draw(image)
        draw.line((20, 45, 220, 45), fill=0, width=3)
        draw.line((20, 85, 220, 85), fill=0, width=3)
        image.save(raw / f"scan_{number:04d}.png")

    cfg = {
        "paths": {
            "raw_dir": str(tmp_path / "raw"),
            "preprocessed_dir": str(tmp_path / "interim"),
        },
        "preprocess": {
            "median_kernel": 3,
            "max_skew_degrees": 1,
            "skew_step": 1,
            "border_px": 4,
        },
    }
    pages = loader.load_pages(cfg)
    assert [page.id for page in pages] == ["bk1_p001", "bk1_p002"]
    processed = preprocess.run(pages, cfg)
    assert [page.id for page in processed] == [page.id for page in pages]
    output = Path(processed[0].image_path)
    assert output.exists()
    values = set(np.unique(np.asarray(Image.open(output))).tolist())
    assert values <= {0, 255}
    assert output.with_suffix(".json").exists()
