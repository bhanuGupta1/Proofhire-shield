"""Deterministic candidate↔job matching (platform Phase 3).

Pure functions, zero external dependencies, works offline — mirrors the security
engine's regex-first philosophy. Two capabilities:

- `score_candidate_for_job`: skill-overlap fit of one candidate against a job's
  required skills.
- `talent_search_score`: free-text query relevance over a candidate's skills,
  headline and name.

A candidate's skills come from the linked scan's stored `match_analysis.skills`
(a category → list-of-skills map produced by the existing analyzer). Manually
added candidates with no scan simply have an empty skill set and score 0 on
skill fit, but can still surface in talent search via name/headline.

Upgrade path (not built until there's a provider): swap the token-overlap
scorers for embedding cosine similarity on pgvector, keeping these as the
offline fallback. The signatures below are provider-agnostic so that swap is
localised.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
# Short/common words that add noise to free-text talent queries.
_STOPWORDS = {
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "with", "or",
    "years", "year", "experience", "strong", "senior", "junior", "mid",
}


def normalize_skill(skill: str) -> str:
    return skill.strip().lower()


def candidate_skills(match_analysis: dict | None) -> set[str]:
    """Flatten the stored match-analysis skill map into a normalized set."""
    if not match_analysis:
        return set()
    skills_map = match_analysis.get("skills") or {}
    out: set[str] = set()
    for values in skills_map.values():
        if isinstance(values, list):
            for v in values:
                if isinstance(v, str) and v.strip():
                    out.add(normalize_skill(v))
    return out


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        t
        for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in _STOPWORDS
    }


def _skill_parts(skill: str) -> set[str]:
    """A skill plus its word parts, so 'react.js' matches a 'react' requirement.

    Splits on dots / slashes / whitespace / commas but NOT on + or #, which are
    meaningful (c++, c#). The full skill string is kept too for exact matches.
    """
    parts = {p for p in re.split(r"[.\s/,]+", skill) if p}
    parts.add(skill)
    return parts


@dataclass
class MatchResult:
    score: float  # 0.0–1.0 fraction of required skills the candidate has
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)


def score_candidate_for_job(
    required_skills: list[str], cand_skills: set[str]
) -> MatchResult:
    """Fraction of the job's required skills the candidate demonstrably has.

    A candidate skill matches a requirement when the requirement token is a
    substring-word of, or equal to, one of the candidate's skills (so 'react'
    matches 'react.js'). No required skills → score 0 with everything missing;
    the caller decides how to present an unscoreable job.
    """
    required_norm = [normalize_skill(s) for s in required_skills if s.strip()]
    if not required_norm:
        return MatchResult(score=0.0, matched_skills=[], missing_skills=[])

    matched: list[str] = []
    missing: list[str] = []
    for req in required_norm:
        if any(req in _skill_parts(cs) for cs in cand_skills):
            matched.append(req)
        else:
            missing.append(req)
    return MatchResult(
        score=len(matched) / len(required_norm),
        matched_skills=matched,
        missing_skills=missing,
    )


def talent_search_score(
    query: str,
    cand_skills: set[str],
    headline: str | None,
    full_name: str | None,
) -> float:
    """Relevance of a candidate to a free-text query, 0.0–1.0.

    Query terms are matched against the union of the candidate's skills and the
    tokens of their headline + name. Score is the fraction of query terms hit,
    so a two-word query fully satisfied scores 1.0.
    """
    terms = _tokens(query)
    if not terms:
        return 0.0
    haystack = set(cand_skills) | _tokens(headline) | _tokens(full_name)
    # Expand skills into their word tokens too, so 'machine learning' as one
    # skill still matches the query term 'learning'.
    for s in list(cand_skills):
        haystack |= _tokens(s)
    hits = sum(1 for t in terms if t in haystack)
    return hits / len(terms)


def _demo() -> None:
    """Self-check: run `python matching.py`."""
    ma = {"skills": {"lang": ["Python", "React.js"], "data": ["PostgreSQL"]}}
    cs = candidate_skills(ma)
    assert cs == {"python", "react.js", "postgresql"}, cs

    r = score_candidate_for_job(["python", "react", "go"], cs)
    assert r.matched_skills == ["python", "react"], r.matched_skills  # react ⊂ react.js
    assert r.missing_skills == ["go"], r.missing_skills
    assert abs(r.score - 2 / 3) < 1e-9, r.score

    assert score_candidate_for_job([], cs).score == 0.0

    # Talent search: 'python engineer' — 'python' is a skill; 'engineer' isn't.
    s = talent_search_score("python engineer", cs, "Backend developer", "Ada")
    assert abs(s - 0.5) < 1e-9, s
    # A query fully covered by headline.
    s2 = talent_search_score("backend developer", cs, "Backend developer", "Ada")
    assert s2 == 1.0, s2
    print("matching self-check OK")


if __name__ == "__main__":
    _demo()
