"""Bounded, opt-in PDF text extraction and offline OCR."""

from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
from threading import Lock

from backend.app.redact import redact

PAGE_LIMIT = 15
PAGE_CHARS = 4_000
_PDF_LOCK = Lock()  # PDFium calls must not overlap, even on separate documents.


def enabled() -> bool:
    return os.getenv("BRAIN_INDEX_PDF") == "1"


class PdfIndex:
    def __init__(self) -> None:
        self.ocr_remaining = 45
        self._ocr = None
        self._ocr_unavailable = False

    def read(self, path: Path) -> tuple[list[dict], list[str], int]:
        try:
            import pypdfium2 as pdfium
        except ImportError:
            return [], ["Optional PDF dependencies are not installed"], 0

        pages, warnings = [], []
        total = 0
        with _PDF_LOCK:
            try:
                with pdfium.PdfDocument(path) as document:
                    total = len(document)
                    for index in range(min(total, PAGE_LIMIT)):
                        try:
                            with closing(document[index]) as page:
                                with closing(page.get_textpage()) as textpage:
                                    text = textpage.get_text_bounded().strip()
                                method = "text"
                                if not text:
                                    text, problem = self._recognize(page)
                                    if problem:
                                        warnings.append(f"Page {index + 1}: {problem}")
                                        continue
                                    method = "ocr"
                                if len(text) > PAGE_CHARS:
                                    warnings.append(f"Page {index + 1}: text exceeds the index limit")
                                pages.append({"page": index + 1, "text": redact(text)[:PAGE_CHARS], "method": method})
                        except Exception:
                            warnings.append(f"Page {index + 1}: could not read or render page")
            except pdfium.PdfiumError as exc:
                reason = "Password-protected PDF" if exc.err_code == pdfium.raw.FPDF_ERR_PASSWORD else "Invalid or damaged PDF"
                warnings.append(reason)
            except OSError:
                warnings.append("PDF could not be opened")
        if total > PAGE_LIMIT:
            warnings.append(f"Only the first {PAGE_LIMIT} of {total} pages were checked")
        if not total and not warnings:
            warnings.append("PDF contains no pages")
        return pages, warnings, total

    def _recognize(self, page) -> tuple[str, str | None]:
        if self.ocr_remaining <= 0:
            return "", "offline OCR limit reached for this scan"
        if not self._ocr_unavailable and self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                self._ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
            except Exception:
                self._ocr_unavailable = True
        if self._ocr_unavailable:
            return "", "no text layer and offline OCR is unavailable"
        self.ocr_remaining -= 1
        # Limit the size of the rendered image, including unusually large drawings.
        longest_side = max(page.get_size())
        if longest_side <= 0:
            return "", "invalid page size"
        with closing(page.render(scale=min(2.5, 2000 / longest_side), rev_byteorder=True)) as bitmap:
            results, _ = self._ocr(bitmap.to_numpy())
        text = "\n".join(row[1] for row in results or ()).strip()
        return (text, None) if text else ("", "no readable text found by offline OCR")
