"""
Text extraction from PDF, DOCX, and plain text.
All parsing happens on in-memory bytes — no temp files written to disk.
"""
from __future__ import annotations
import io


def extract_text(raw: bytes, filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(raw)
    if lower.endswith(".docx"):
        return _extract_docx(raw)
    # Plain text — decode leniently
    return raw.decode("utf-8", errors="replace")


def _extract_pdf(raw: bytes) -> str:
    from pdfminer.high_level import extract_text_to_fp
    from pdfminer.layout import LAParams
    buf_in = io.BytesIO(raw)
    buf_out = io.StringIO()
    extract_text_to_fp(buf_in, buf_out, laparams=LAParams(), output_type="text", codec="utf-8")
    return buf_out.getvalue()


def _extract_docx(raw: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(raw))
    return "\n".join(p.text for p in doc.paragraphs)
