"""Unit tests for page-level OCR assembly and caching."""

from pathlib import Path


def test_ocr_placeholder(tmp_path: Path, monkeypatch):
    from doc_agent.contracts import Region
    from doc_agent.vision import ocr
    from PIL import Image

    processed = tmp_path / "preprocessed"
    processed.mkdir()
    Image.new("L", (200, 200), 255).save(processed / "bk1_p001.png")
    cfg = {
        "paths": {"preprocessed_dir": str(processed), "ocr_dir": str(tmp_path / "ocr")},
        "ocr": {"lang": "ben+eng", "body_psm": 6, "heading_psm": 7},
    }

    def fake_transcribe(self, region):
        self.last_confidence = 0.9
        return "শিরোনাম" if region.kind == "heading" else "আর্সেনিক ৩০"

    monkeypatch.setattr(ocr.Reader, "transcribe_region", fake_transcribe)
    regions = [
        Region(page_id="bk1_p001", bbox=(0, 0, 200, 40), kind="heading"),
        Region(page_id="bk1_p001", bbox=(0, 40, 200, 200), kind="text"),
    ]
    chunks = ocr.transcribe(regions, cfg)
    assert len(chunks) == 1
    assert chunks[0].id == "bk1_p001_ocr"
    assert chunks[0].page_ids == ["bk1_p001"]
    assert chunks[0].text == "শিরোনাম\n\nআর্সেনিক ৩০"
    assert (tmp_path / "ocr" / "bk1_p001.json").exists()


def test_layout_falls_back_to_full_page(tmp_path: Path, monkeypatch):
    import subprocess
    import sys

    from doc_agent.contracts import Page
    from doc_agent.vision import layout
    from PIL import Image

    image_path = tmp_path / "bk1_p001.png"
    Image.new("L", (120, 80), 255).save(image_path)
    cfg = {
        "ocr": {"tesseract_cmd": sys.executable, "lang": "ben+eng", "oem": 1},
        "layout": {"psm": 3},
    }
    empty_tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
        "width\theight\tconf\ttext\n"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, empty_tsv, ""),
    )
    regions = layout.detect([Page(id="bk1_p001", image_path=str(image_path), doc_id="bk1")], cfg)
    assert len(regions) == 1
    assert regions[0].bbox == (0, 0, 120, 80)
    assert regions[0].kind == "text"
