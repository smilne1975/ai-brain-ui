from pathlib import Path

import pytest

from backend.app import ask, scanner
from backend.app.pdf_index import PdfIndex


def test_pdf_index_opt_in_and_page_evidence(tmp_path: Path, monkeypatch):
    project = tmp_path / "Standards"
    project.mkdir()
    file = project / "details.pdf"
    file.write_bytes(b"not actually a PDF")
    monkeypatch.delenv("BRAIN_INDEX_PDF", raising=False)
    before = scanner.signature(tmp_path)
    assert not scanner.build_brain(tmp_path)["files"]

    monkeypatch.setenv("BRAIN_INDEX_PDF", "1")
    monkeypatch.setattr(PdfIndex, "read", lambda *_: (
        [{"page": 2, "text": "General notes. " * 41 + "Check the clearance around risers.", "method": "ocr"}],
        ["Page 1: no readable text found"], 2,
    ))
    monkeypatch.setattr(ask, "complete", lambda *_args, **_kwargs: pytest.fail("PDF Ask must stay local"))
    brain = scanner.build_brain(tmp_path)
    assert scanner.signature(tmp_path) != before
    result = ask.answer(brain, "clearance around risers", None, {"display": "Test provider"})
    assert result["provider"] == "heuristic"
    assert result["evidence"][0]["page"] == 2
    assert "page 2 (OCR)" in result["citations"][0]["label"]
    assert "clearance around risers" in result["answer"]
    assert result["pdf_gaps"][0]["reason"] == "Page 1: no readable text found"
    assert file.read_bytes() == b"not actually a PDF"


def test_offline_ocr_reads_image_only_pdf(tmp_path):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("rapidocr_onnxruntime")
    from PIL import Image, ImageDraw, ImageFont

    path = tmp_path / "scan.pdf"
    image = Image.new("RGB", (900, 260), "white")
    ImageDraw.Draw(image).text((40, 75), "BIM CLEARANCE CHECK", fill="black", font=ImageFont.load_default(size=48))
    image.save(path)
    before = path.read_bytes()
    pages, warnings, total = PdfIndex().read(path)
    assert total == 1 and not warnings
    assert pages[0]["method"] == "ocr"
    assert "CLEARANCE" in pages[0]["text"].upper()
    assert path.read_bytes() == before


def test_damaged_pdf_has_a_read_failure(tmp_path):
    pytest.importorskip("pypdfium2")
    path = tmp_path / "damaged.pdf"
    path.write_bytes(b"not a PDF")
    assert PdfIndex().read(path) == ([], ["Invalid or damaged PDF"], 0)
