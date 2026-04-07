from __future__ import annotations


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """PDF extraction fallback strategy.

    1) TODO: pypdf extraction
    2) TODO: OCR fallback for scanned docs
    3) current fallback: UTF-8 decode best effort
    """
    return pdf_bytes.decode("utf-8", errors="ignore")
