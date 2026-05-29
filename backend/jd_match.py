"""
JD Match — compare a CV's extracted skills against a job description.

Returns: match_score (0-100), matched_skills, missing_skills, bonus_skills.
Zero LLM. Reuses the same skill taxonomy as match_analysis.py (pure keyword overlap).
"""
from __future__ import annotations

from dataclasses import dataclass

from match_analysis import _extract_skills

# Category weights for the match score. Categories not listed fall back to the
# default so the score still works if the taxonomy grows.
_CATEGORY_WEIGHTS: dict[str, int] = {
    "Languages": 25,
    "Frameworks & Libraries": 25,
    "Cloud & DevOps": 20,
    "Databases": 15,
    "Tools & Practices": 15,
}
_DEFAULT_WEIGHT = 15


@dataclass
class JDMatchResult:
    match_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    bonus_skills: list[str]


def extract_jd_keywords(jd_text: str) -> dict[str, list[str]]:
    """Skills the JD asks for, grouped by category (same taxonomy as the CV)."""
    return _extract_skills(jd_text)


def _flat(skills_by_cat: dict[str, list[str]]) -> set[str]:
    return {skill for skills in skills_by_cat.values() for skill in skills}


def score_match(
    cv_skills: dict[str, list[str]],
    jd_skills: dict[str, list[str]],
) -> JDMatchResult:
    """Weighted keyword-overlap score between a CV's skills and a JD's skills."""
    cv_flat = _flat(cv_skills)
    jd_flat = _flat(jd_skills)

    matched = sorted(cv_flat & jd_flat)
    missing = sorted(jd_flat - cv_flat)
    bonus = sorted(cv_flat - jd_flat)

    # For each category the JD requires, score the fraction of its skills the CV
    # has, weighted by category importance, then normalise by the weights in play.
    total_weight = 0.0
    earned = 0.0
    for category, jd_list in jd_skills.items():
        if not jd_list:
            continue
        weight = _CATEGORY_WEIGHTS.get(category, _DEFAULT_WEIGHT)
        total_weight += weight
        cv_set = set(cv_skills.get(category, []))
        hits = len(set(jd_list) & cv_set)
        earned += weight * (hits / len(jd_list))

    score = int(round(100 * earned / total_weight)) if total_weight else 0

    return JDMatchResult(
        match_score=score,
        matched_skills=matched,
        missing_skills=missing,
        bonus_skills=bonus,
    )


def match_cv_to_jd(cv_text: str, jd_text: str) -> JDMatchResult:
    return score_match(_extract_skills(cv_text), extract_jd_keywords(jd_text))
