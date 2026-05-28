"""
PR-01 detection engine — prompt injection, PII, and AI-text heuristic.
Zero LLM dependency. Pure regex + heuristics. Works offline.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from models import PromptInjectionFinding, PIIFinding


# ── Prompt Injection Patterns (PR-01) ────────────────────────────────────────

@dataclass
class _InjectionPattern:
    pattern_id: str
    regex: re.Pattern[str]


_INJECTION_PATTERNS: list[_InjectionPattern] = [
    # PR-01-A: Direct override imperatives
    _InjectionPattern(
        "PR-01-A",
        re.compile(
            r"(ignore|disregard|forget|override|bypass|overrule)\s+"
            r"(all\s+|your\s+|any\s+)?(previous|prior|above|earlier|original|your)\s+"
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
]


# ── PII Patterns ─────────────────────────────────────────────────────────────

@dataclass
class _PIIPattern:
    pii_type: str
    regex: re.Pattern[str]


_PII_PATTERNS: list[_PIIPattern] = [
    _PIIPattern("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    _PIIPattern("nz_bank_account", re.compile(r"\b\d{2}-\d{4}-\d{7}-\d{2,3}\b")),
    # NZ IRD must come before phone_generic to avoid span overlap swallowing it
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
    _PIIPattern("nz_bank_account", re.compile(r"\b\d{2}-\d{4}-\d{7}-\d{2,3}\b")),
]


# ── AI-Text Heuristic ─────────────────────────────────────────────────────────

# Phrases strongly associated with LLM-generated professional text
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


def _context_snippet(text: str, match: re.Match, window: int = 60) -> str:
    start = max(0, match.start() - window // 2)
    end = min(len(text), match.end() + window // 2)
    snippet = text[start:end].replace("\n", " ")
    return f"...{snippet}..."


def scan_text(text: str) -> tuple[
    list[PromptInjectionFinding],
    list[PIIFinding],
    float,
]:
    """
    Returns (injection_findings, pii_findings, ai_score).
    ai_score is 0.0–1.0; ≥0.6 = LIKELY, 0.3–0.6 = POSSIBLE, <0.3 = UNLIKELY.
    """
    injection_findings: list[PromptInjectionFinding] = []
    for pattern in _INJECTION_PATTERNS:
        for m in pattern.regex.finditer(text):
            injection_findings.append(PromptInjectionFinding(
                pattern_id=pattern.pattern_id,
                matched_text=m.group(0),
                context=_context_snippet(text, m),
            ))

    pii_findings: list[PIIFinding] = []
    seen_spans: list[tuple[int, int]] = []
    for pattern in _PII_PATTERNS:
        for m in pattern.regex.finditer(text):
            # skip if this span is already covered by a more specific match
            overlap = any(s <= m.start() < e or s < m.end() <= e for s, e in seen_spans)
            if not overlap:
                pii_findings.append(PIIFinding(
                    pii_type=pattern.pii_type,
                    matched_text=m.group(0),
                ))
                seen_spans.append((m.start(), m.end()))

    words = len(text.split())
    hit_count = sum(1 for p in _AI_PATTERNS if p.search(text))
    # normalise: 10+ hits in a typical CV → score 1.0
    ai_score = min(1.0, hit_count / 10.0) if words > 50 else 0.0

    return injection_findings, pii_findings, ai_score


def compute_risk(
    injection_findings: list[PromptInjectionFinding],
    pii_findings: list[PIIFinding],
    ai_score: float,
) -> tuple[str, int]:
    """Returns (risk_level, risk_score 0-100)."""
    score = 0

    # Injection is always RED if found
    if injection_findings:
        score += 60 + min(20, len(injection_findings) * 5)

    # PII: each finding adds weight, cap generous enough that 4+ sensitive items → ORANGE
    sensitive_pii = {"nz_ird", "nz_passport", "nz_drivers_licence", "dob",
                     "nz_bank_account", "visa_status", "medical_info", "marital_status"}
    sensitive_count = sum(1 for f in pii_findings if f.pii_type in sensitive_pii)
    normal_count = len(pii_findings) - sensitive_count
    score += min(40, sensitive_count * 8 + normal_count * 2)

    # AI text
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
