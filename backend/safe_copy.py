"""
Safe CV Copy generator.

Two-pass removal strategy:
  Pass 1 — span-based: find ALL injection match spans in the full text,
            mark every line that overlaps any span for removal. This correctly
            handles multi-line injections that a single-line check would miss.
  Pass 2 — line-by-line sweep on the already-cleaned text to catch any
            residual single-line fragments left after pass 1.

PII is annotated (not silently removed) so the recruiter sees what was flagged.
"""
from __future__ import annotations
from models import PromptInjectionFinding, PIIFinding
from scanner import _INJECTION_PATTERNS, _PII_PATTERNS, _strip_zero_width, _apply_homoglyphs

_REMOVED = "[HIDDEN INSTRUCTION REMOVED]"


def generate_safe_copy(
    original: str,
    injection_findings: list[PromptInjectionFinding],
    pii_findings: list[PIIFinding],
) -> str:
    # Preprocess: strip zero-width characters and normalize homoglyphs.
    # The safe copy is the document the recruiter will use — it should be
    # clean ASCII, not Cyrillic lookalikes or invisible Unicode.
    text = _apply_homoglyphs(_strip_zero_width(original))

    # ── Pass 1: span-based multi-line removal ────────────────────────────────
    lines = text.split("\n")

    # Pre-compute the character-offset start of each line in the full string.
    line_starts: list[int] = []
    pos = 0
    for line in lines:
        line_starts.append(pos)
        pos += len(line) + 1  # +1 for the \n separator

    lines_to_remove: set[int] = set()
    for pattern in _INJECTION_PATTERNS:
        for m in pattern.regex.finditer(text):
            ms, me = m.start(), m.end()
            for idx, ls in enumerate(line_starts):
                le = ls + len(lines[idx])
                if ls <= me and le >= ms:          # line overlaps the match span
                    lines_to_remove.add(idx)

    after_pass1: list[str] = []
    for idx, line in enumerate(lines):
        if idx in lines_to_remove:
            after_pass1.append(_REMOVED)
        else:
            after_pass1.append(line)

    # Collapse consecutive removal markers into one.
    deduped: list[str] = []
    for line in after_pass1:
        if line == _REMOVED and deduped and deduped[-1] == _REMOVED:
            continue
        deduped.append(line)

    # ── Pass 2: line-by-line sweep on remaining text ─────────────────────────
    cleaned: list[str] = []
    for line in deduped:
        if line == _REMOVED:
            cleaned.append(line)
            continue
        replaced = False
        for pattern in _INJECTION_PATTERNS:
            if pattern.regex.search(line):
                cleaned.append(_REMOVED)
                replaced = True
                break
        if not replaced:
            cleaned.append(line)

    text = "\n".join(cleaned)

    # ── PII annotation ────────────────────────────────────────────────────────
    for pattern in _PII_PATTERNS:
        text = pattern.regex.sub(
            lambda m, t=pattern.pii_type: f"[PII:{t.upper()}]",
            text,
        )

    return text.strip()
