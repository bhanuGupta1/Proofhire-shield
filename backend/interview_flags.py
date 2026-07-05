"""Interview notes → red/green flag summary (platform Phase 10).

A lightweight, offline heuristic for ad-hoc interview notes: split into
sentences, classify each by positive/negative signal words, and derive a
recommended next step from the balance. Zero LLM dependency so it's instant and
testable; the LLM upgrade (richer extraction in the recruiter's voice) is a
localised swap that falls back to this. Never a hiring decision — a human aid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_GREEN_WORDS = {
    "strong", "excellent", "confident", "clear", "clearly", "impressive",
    "knowledgeable", "articulate", "experienced", "great", "good", "solid",
    "thoughtful", "prepared", "enthusiastic", "positive", "standout", "fit",
    "collaborative", "proactive",
}
_RED_WORDS = {
    "concern", "concerning", "weak", "unclear", "struggled", "lacked", "lack",
    "unsure", "hesitant", "gap", "vague", "unable", "poor", "red", "flag",
    "difficult", "defensive", "inconsistent", "limited", "missed", "confused",
    "disorganised", "disorganized",
}

_SENTENCE_RE = re.compile(r"[.!?\n]+")
_WORD_RE = re.compile(r"[a-z']+")


@dataclass
class FlagSummary:
    green_flags: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    recommended_step: str = ""


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _signal(sentence: str) -> int:
    words = set(_WORD_RE.findall(sentence.lower()))
    green = len(words & _GREEN_WORDS)
    red = len(words & _RED_WORDS)
    if green > red:
        return 1
    if red > green:
        return -1
    return 0


def summarize_notes(notes: str, max_flags: int = 8) -> FlagSummary:
    """Classify each sentence and recommend a next step from the balance."""
    green: list[str] = []
    red: list[str] = []
    for sentence in _sentences(notes):
        sig = _signal(sentence)
        if sig > 0 and len(green) < max_flags:
            green.append(sentence)
        elif sig < 0 and len(red) < max_flags:
            red.append(sentence)

    if not green and not red:
        step = "Notes are neutral — a structured follow-up interview is recommended."
    elif len(green) > len(red) * 2 and red == []:
        step = "Strong signals, no concerns — advance to the next round."
    elif len(green) > len(red):
        step = "Net positive — advance, but probe the noted concerns next round."
    elif len(red) > len(green):
        step = "Concerns outweigh strengths — do not advance without resolving them."
    else:
        step = "Mixed signals — a follow-up interview to resolve the concerns."
    return FlagSummary(green_flags=green, red_flags=red, recommended_step=step)


def _demo() -> None:
    notes = (
        "Candidate was very confident and articulate about system design. "
        "Strong grasp of distributed systems. "
        "However, struggled to explain their testing approach. "
        "Answers on team conflict were vague."
    )
    s = summarize_notes(notes)
    assert len(s.green_flags) == 2, s.green_flags
    assert len(s.red_flags) == 2, s.red_flags
    assert "follow-up" in s.recommended_step.lower() or "resolve" in s.recommended_step.lower()

    allgood = summarize_notes("Excellent, clear, and impressive throughout.")
    assert allgood.red_flags == []
    assert "advance" in allgood.recommended_step.lower()

    assert summarize_notes("").recommended_step  # non-empty guidance on empty input
    print("interview_flags self-check OK")


if __name__ == "__main__":
    _demo()
