"""
PR-01 detection engine — prompt injection, PII, and AI-text heuristic.
Zero LLM dependency. Pure regex + heuristics. Works offline.

Preprocessing pipeline applied before pattern matching:
  1. Strip zero-width characters (U+200B, U+200C, U+200D, ZWNBSP, etc.)
  2. Normalize Unicode homoglyphs to ASCII (Cyrillic/Greek lookalikes)
  3. Decode base64 candidate strings and scan the decoded content
"""
from __future__ import annotations
import base64
import re
import unicodedata
from dataclasses import dataclass
from models import PromptInjectionFinding, PIIFinding


# ── Zero-width character stripping (Technique 4) ─────────────────────────────

_ZWC_RE = re.compile(
    r"[­"          # soft hyphen
    r"​-‏"    # ZWS, ZWNJ, ZWJ, LRM, RLM
    r"⁠"           # word joiner
    r"﻿"           # BOM / ZWNBSP
    r"  ]"    # line/paragraph separator
)


def _strip_zero_width(text: str) -> str:
    return _ZWC_RE.sub("", text)


# ── Homoglyph normalization (Technique 3) ─────────────────────────────────────
# Maps visually identical non-ASCII code points to their Latin ASCII equivalents.
# Applied to the scan copy only; the original text returned to the UI is unchanged.

_HOMOGLYPH_TABLE = str.maketrans({
    # Cyrillic → Latin (most common real-world homoglyph attack vector)
    "А": "A", "а": "a",   # А а
    "В": "B",                   # В
    "С": "C", "с": "c",   # С с
    "Е": "E", "е": "e",   # Е е
    "Н": "H",                   # Н
    "І": "I", "і": "i",   # І і (Ukrainian I)
    "Ј": "J",                   # Ј
    "К": "K",                   # К
    "М": "M",                   # М
    "О": "O", "о": "o",   # О о
    "Р": "P", "р": "p",   # Р р
    "Т": "T",                   # Т
    "Х": "X", "х": "x",   # Х х
    "у": "y",                   # у (looks like y)
    "Ѕ": "S", "ѕ": "s",   # Ѕ ѕ
    # Greek → Latin
    "Α": "A", "α": "a",   # Α α
    "Β": "B",                   # Β
    "Ε": "E", "ε": "e",   # Ε ε
    "Η": "H",                   # Η
    "Ι": "I", "ι": "i",   # Ι ι
    "Κ": "K", "κ": "k",   # Κ κ
    "Μ": "M",                   # Μ
    "Ν": "N",                   # Ν
    "Ο": "O", "ο": "o",   # Ο ο
    "Ρ": "P", "ρ": "r",   # Ρ ρ
    "Τ": "T", "τ": "t",   # Τ τ
    "Υ": "Y", "υ": "u",   # Υ υ
    "Χ": "X", "χ": "x",   # Χ χ
    # Full-width Latin (used in CJK-context attacks)
    "Ａ": "A", "ａ": "a",   # Ａ ａ
    "Ｂ": "B", "ｂ": "b",
    "Ｃ": "C", "ｃ": "c",
    "Ｅ": "E", "ｅ": "e",
    "Ｇ": "G", "ｇ": "g",
    "Ｉ": "I", "ｉ": "i",
    "Ｎ": "N", "ｎ": "n",
    "Ｏ": "O", "ｏ": "o",
    "Ｒ": "R", "ｒ": "r",
    "Ｓ": "S", "ｓ": "s",
    "Ｔ": "T", "ｔ": "t",
    "Ｕ": "U", "ｕ": "u",
    "Ｗ": "W", "ｗ": "w",
})


def _apply_homoglyphs(text: str) -> str:
    # NFKC maps full-width Latin (Ａ→A), ligatures (ﬁ→fi), superscripts, etc.
    text = unicodedata.normalize("NFKC", text)
    # Manual table maps Cyrillic and Greek lookalikes that NFKC leaves as-is.
    return text.translate(_HOMOGLYPH_TABLE)


# ── Base64 candidate detection (Technique 2) ──────────────────────────────────
# Matches strings long enough to encode a meaningful instruction (≥20 chars base64
# = ≥14 plaintext bytes) and surrounded by non-base64 characters.

_B64_RE = re.compile(
    r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/=])"
)


def _decode_b64_candidates(text: str) -> list[str]:
    results: list[str] = []
    for m in _B64_RE.finditer(text):
        b64 = m.group(0)
        padded = b64 + "=" * ((-len(b64)) % 4)
        try:
            decoded = base64.b64decode(padded, validate=True).decode("utf-8", errors="ignore")
            if len(decoded) >= 8 and decoded.isprintable():
                results.append(decoded)
        except Exception:
            pass
    return results


# ── Prompt Injection Patterns (PR-01) ────────────────────────────────────────

@dataclass
class _InjectionPattern:
    pattern_id: str
    regex: re.Pattern[str]


_INJECTION_PATTERNS: list[_InjectionPattern] = [
    # PR-01-A: Direct override imperatives
    # Allows optional parenthetical or em-dash aside between verb and object.
    _InjectionPattern(
        "PR-01-A",
        re.compile(
            r"(ignore|disregard|forget|override|bypass|overrule)\s+"
            r"(?:\([^)]{0,60}\)\s*)?"           # optional (parenthetical)
            r"(?:[-—–]{1,3}[^.!?\n]{0,50}[-—–]{1,3}\s*)?"  # optional —aside—
            r"(all\s+|your\s+|any\s+)?"
            r"(previous|prior|above|earlier|original|your)\s+"
            r"(instructions?|prompts?|context|guidelines?|directives?|rules?|constraints?|criteria)",
            re.IGNORECASE,
        ),
    ),
    # PR-01-B: Role/persona hijack
    _InjectionPattern(
        "PR-01-B",
        re.compile(
            r"you\s+(are\s+now|will\s+now|must\s+now|should\s+now)\s+"
            r"(a[n]?\s+)?"
            r"(act\s+as\b|be\b|become\b|pretend|play\s+the|unconditional|hiring|evaluation|approval|screening)",
            re.IGNORECASE,
        ),
    ),
    # PR-01-C: System/special tokens (LLM chat templates)
    _InjectionPattern(
        "PR-01-C",
        re.compile(
            r"(<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|<s>|</s>"
            r"|<<SYS>>|<</SYS>>|\[SYSTEM\]|###\s*Instruction|###\s*System)",
            re.IGNORECASE,
        ),
    ),
    # PR-01-D: Explicit rating/hiring manipulation
    _InjectionPattern(
        "PR-01-D",
        re.compile(
            r"(rate|score|rank|evaluate|assess)\s+(this\s+)?(candidate|applicant|cv|resume)\s+"
            r".{0,40}(10(/10)?|perfect|maximum|highest|top)",
            re.IGNORECASE,
        ),
    ),
    # PR-01-E: New directive injection
    _InjectionPattern(
        "PR-01-E",
        re.compile(
            r"(new\s+directive|new\s+instruction|new\s+command|system\s*:)\s*"
            r".{0,80}(approve|pass|hire|accept|recommend)",
            re.IGNORECASE,
        ),
    ),
    # PR-01-F: Unconditional approval commands
    _InjectionPattern(
        "PR-01-F",
        re.compile(
            r"(approve|hire|accept|recommend)\s+(this\s+)?(candidate|applicant)?\s*"
            r"(unconditionally|immediately|automatically|without\s+(question|review|hesitation))",
            re.IGNORECASE,
        ),
    ),
    # PR-01-G: Evaluation mode / override mode declarations
    _InjectionPattern(
        "PR-01-G",
        re.compile(
            r"(evaluation|override|screening|bypass|debug)\s+mode",
            re.IGNORECASE,
        ),
    ),
    # PR-01-H: Loose override catch-all — same verb + object within one sentence,
    # tolerates up to 60 chars of intervening content (parentheticals, asides, etc.)
    _InjectionPattern(
        "PR-01-H",
        re.compile(
            r"(ignore|disregard|forget|override|bypass|overrule)"
            r"[^.!?\n]{0,60}"
            r"(all\s+)?(previous|prior|earlier|original)\s+"
            r"(instructions?|guidelines?|directives?|rules?|criteria|constraints?)",
            re.IGNORECASE,
        ),
    ),
]


# ── PII Patterns ─────────────────────────────────────────────────────────────

@dataclass
class _PIIPattern:
    pii_type: str
    regex: re.Pattern[str]


_PII_PATTERNS: list[_PIIPattern] = [
    _PIIPattern("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    _PIIPattern("nz_bank_account", re.compile(r"\b\d{2}-\d{4}-\d{7}-\d{2,3}\b")),
    # NZ IRD before phone_generic — otherwise the phone pattern swallows it
    _PIIPattern("nz_ird", re.compile(r"\b\d{2,3}[\s\-]\d{3}[\s\-]\d{3}\b")),
    _PIIPattern("nz_passport", re.compile(r"\b[A-Z]{2}\d{6,7}\b")),
    _PIIPattern("nz_drivers_licence", re.compile(r"\b[A-Z]{2}\d{6}\b")),
    _PIIPattern("phone_nz", re.compile(r"\b(\+64|0)[\s\-]?[2-9]\d[\s\-]?\d{3}[\s\-]?\d{4}\b")),
    _PIIPattern("phone_generic", re.compile(r"\b\+?\d[\d\s\-().]{8,}\d\b")),
    _PIIPattern("dob", re.compile(
        r"\b(DOB|Date\s+of\s+Birth|Born)\s*:?\s*\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b",
        re.IGNORECASE,
    )),
    _PIIPattern("street_address", re.compile(
        r"\b\d+\s+[A-Za-z][A-Za-z\s]+\s+(Rd|Road|St|Street|Ave|Avenue|Dr|Drive|Ln|Lane|Pl|Place|Cres|Crescent)\b",
        re.IGNORECASE,
    )),
    _PIIPattern("visa_status", re.compile(
        r"\b(visa|work\s+permit|residency|citizen|PR)\s*:?\s*(expires?|valid|until|status)?\s*\d{4}",
        re.IGNORECASE,
    )),
    _PIIPattern("medical_info", re.compile(
        r"\b(health|medical|gp|doctor|non[\s\-]smoker|smoker|disability|chronic)\b",
        re.IGNORECASE,
    )),
    _PIIPattern("marital_status", re.compile(
        r"\b(married|single|divorced|widowed|civil\s+union|de\s+facto|spouse|husband|wife)\b",
        re.IGNORECASE,
    )),
]


# ── AI-Text Heuristic ─────────────────────────────────────────────────────────

_AI_BUZZWORDS = [
    r"results[\s\-]driven",
    r"proven track record",
    r"leverag(e|ing)\s+\w+\s+(to|for)",
    r"synerg(y|ies|istic)",
    r"cross[\s\-]functional",
    r"fast[\s\-]paced.*dynamic",
    r"dynamic.*fast[\s\-]paced",
    r"thought leadership",
    r"paradigm[\s\-]shift",
    r"laser focus",
    r"unlock(ing)?\s+(unprecedented|exceptional|significant)\s+value",
    r"transformational\s+change",
    r"cutting[\s\-]edge\s+technolog",
    r"spearheaded",
    r"orchestrated\s+(seamless|cross)",
    r"fostered\s+(collaborative|innovation)",
    r"catalys(e|ed|ing)\s+\w*\s*(transformation|growth|change)",
    r"holistic\s+(approach|strateg|go[\s\-]to[\s\-]market)",
    r"unprecedented\s+(growth|value|outcome)",
    r"data[\s\-]driven\s+(decision|insight|approach)",
]

_AI_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _AI_BUZZWORDS]


# ── Core scanning functions ───────────────────────────────────────────────────

def _context_snippet(text: str, match: re.Match, window: int = 60) -> str:
    start = max(0, match.start() - window // 2)
    end = min(len(text), match.end() + window // 2)
    return f"...{text[start:end].replace(chr(10), ' ')}..."


def scan_text(text: str) -> tuple[
    list[PromptInjectionFinding],
    list[PIIFinding],
    float,
]:
    """
    Returns (injection_findings, pii_findings, ai_score).

    Preprocessing pipeline:
      - ZWC stripped (Technique 4)
      - Homoglyphs normalized to ASCII (Technique 3)
      - Base64 segments decoded and scanned separately (Technique 2)

    PII and AI-text heuristic run on the ZWC-stripped text (not homoglyph-
    normalized) so that legitimate Unicode content isn't mangled.
    """
    # Step 1: strip zero-width characters — used for all subsequent steps
    text_stripped = _strip_zero_width(text)

    # Step 2: normalize homoglyphs — injection scan only
    text_normalized = _apply_homoglyphs(text_stripped)

    # Step 3: injection detection on the normalized text
    injection_findings: list[PromptInjectionFinding] = []
    for pattern in _INJECTION_PATTERNS:
        for m in pattern.regex.finditer(text_normalized):
            injection_findings.append(PromptInjectionFinding(
                pattern_id=pattern.pattern_id,
                matched_text=m.group(0),
                context=_context_snippet(text_normalized, m),
            ))

    # Step 4: decode base64 candidates and scan the decoded strings
    for decoded in _decode_b64_candidates(text_stripped):
        decoded_norm = _apply_homoglyphs(decoded)
        for pattern in _INJECTION_PATTERNS:
            for m in pattern.regex.finditer(decoded_norm):
                injection_findings.append(PromptInjectionFinding(
                    pattern_id=pattern.pattern_id,
                    matched_text=f"[base64] {m.group(0)}",
                    context=f"Decoded from base64: {decoded[:80]}",
                ))

    # Step 5: PII on ZWC-stripped text (exact char matching, no homoglyph mapping)
    pii_findings: list[PIIFinding] = []
    seen_spans: list[tuple[int, int]] = []
    for pattern in _PII_PATTERNS:
        for m in pattern.regex.finditer(text_stripped):
            overlap = any(s <= m.start() < e or s < m.end() <= e for s, e in seen_spans)
            if not overlap:
                pii_findings.append(PIIFinding(
                    pii_type=pattern.pii_type,
                    matched_text=m.group(0),
                ))
                seen_spans.append((m.start(), m.end()))

    # Step 6: AI-text heuristic on ZWC-stripped text
    words = len(text_stripped.split())
    hit_count = sum(1 for p in _AI_PATTERNS if p.search(text_stripped))
    ai_score = min(1.0, hit_count / 10.0) if words > 50 else 0.0

    return injection_findings, pii_findings, ai_score


def compute_risk(
    injection_findings: list[PromptInjectionFinding],
    pii_findings: list[PIIFinding],
    ai_score: float,
) -> tuple[str, int]:
    """Returns (risk_level, risk_score 0-100)."""
    score = 0

    if injection_findings:
        score += 60 + min(20, len(injection_findings) * 5)

    sensitive_pii = {"nz_ird", "nz_passport", "nz_drivers_licence", "dob",
                     "nz_bank_account", "visa_status", "medical_info", "marital_status"}
    sensitive_count = sum(1 for f in pii_findings if f.pii_type in sensitive_pii)
    normal_count = len(pii_findings) - sensitive_count
    score += min(40, sensitive_count * 8 + normal_count * 2)

    if ai_score >= 0.6:
        score += 10
    elif ai_score >= 0.3:
        score += 5

    score = min(100, score)

    if injection_findings or score >= 70:
        level = "RED"
    elif score >= 30:
        level = "ORANGE"
    else:
        level = "GREEN"

    return level, score
