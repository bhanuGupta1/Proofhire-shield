"""
Safe CV Copy generator.
Removes prompt injection payloads line-by-line; annotates PII with [PII:TYPE] markers.
Preserves all legitimate content.
"""
from __future__ import annotations
from models import PromptInjectionFinding, PIIFinding
from scanner import _INJECTION_PATTERNS, _PII_PATTERNS


def generate_safe_copy(
    original: str,
    injection_findings: list[PromptInjectionFinding],
    pii_findings: list[PIIFinding],
) -> str:
    # Line-level removal: any line containing an injection pattern is replaced wholesale.
    # This prevents partial-replacement artifacts (e.g. orphaned text after token removal).
    lines = original.split("\n")
    cleaned: list[str] = []
    for line in lines:
        replaced = False
        for pattern in _INJECTION_PATTERNS:
            if pattern.regex.search(line):
                cleaned.append("[HIDDEN INSTRUCTION REMOVED]")
                replaced = True
                break
        if not replaced:
            cleaned.append(line)

    text = "\n".join(cleaned)

    # Annotate PII — mark rather than silently remove so recruiter sees what was flagged
    for pattern in _PII_PATTERNS:
        text = pattern.regex.sub(
            lambda m, t=pattern.pii_type: f"[PII:{t.upper()}]",
            text,
        )

    return text.strip()
