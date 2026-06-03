"""Tests for jd_match — JD <-> CV skill matching (C1)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from jd_match import match_cv_to_jd, score_match, extract_jd_keywords


def test_exact_match_single_skill_jd_is_capped():
    """Phase 9 — a one-skill JD is sparse, score capped at 60 even on full
    overlap. The match itself is still detected; only the headline number
    is bounded."""
    r = match_cv_to_jd("Skilled in Python.", "We need Python.")
    assert "Python" in r.matched_skills
    assert r.match_score <= 60
    assert r.coverage_note  # explains the cap


def test_missing_skill_detected():
    r = match_cv_to_jd("I use Python.", "Need Python and AWS.")
    assert "AWS" in r.missing_skills
    assert "AWS" not in r.matched_skills


def test_bonus_skill_detected():
    r = match_cv_to_jd("Python and Docker expert.", "Need Python.")
    assert "Docker" in r.bonus_skills


def test_score_zero_for_no_overlap():
    r = match_cv_to_jd("I write Python.", "Need Java only.")
    assert r.match_score == 0
    assert r.matched_skills == []


def test_score_full_for_full_overlap():
    text = "Python, React, AWS, PostgreSQL, Docker."
    r = match_cv_to_jd(text, text)
    assert r.match_score >= 95
    assert r.missing_skills == []


def test_case_insensitive():
    r = match_cv_to_jd("python developer", "PYTHON required")
    assert "Python" in r.matched_skills


def test_empty_jd_scores_zero_no_crash():
    r = match_cv_to_jd("Python, AWS, Docker.", "")
    assert r.match_score == 0
    assert r.matched_skills == []
    # everything in the CV is a bonus relative to an empty JD
    assert "Python" in r.bonus_skills


def test_multi_category_weighting():
    # JD needs a Language (weight 25) + a Database (weight 15). The CV has only the
    # Language, so the score reflects the higher Language weight: 25/(25+15) ~= 62.
    cv = {"Languages": ["Python"]}
    jd = {"Languages": ["Python"], "Databases": ["PostgreSQL"]}
    r = score_match(cv, jd)
    assert 60 <= r.match_score <= 65
    assert "PostgreSQL" in r.missing_skills


def test_extract_jd_keywords_groups_by_category():
    jd = extract_jd_keywords("Looking for Python and PostgreSQL skills.")
    assert "Python" in jd.get("Languages", [])
    assert "PostgreSQL" in jd.get("Databases", [])


# Phase 9 — sparse-JD score cap so a one-skill JD that happens to overlap
# with the CV cannot return 100/100.

def test_single_skill_jd_full_overlap_score_capped_at_60():
    """1 JD skill, 100% overlap → would be 100/100 without the cap.
    With the Phase-9 sparse safeguard it sits at the 60 cap with a note."""
    cv = {"Languages": ["Python"]}
    jd = {"Languages": ["Python"]}
    r = score_match(cv, jd)
    assert r.match_score <= 60
    assert r.coverage_note  # non-empty explanation
    assert "1" in r.coverage_note  # mentions the skill count


def test_two_skill_jd_still_capped():
    """Two-skill JD is still below the 3-skill threshold."""
    cv = {"Languages": ["Python"], "Databases": ["PostgreSQL"]}
    jd = {"Languages": ["Python"], "Databases": ["PostgreSQL"]}
    r = score_match(cv, jd)
    assert r.match_score <= 60
    assert r.coverage_note


def test_three_skill_jd_full_overlap_uncapped():
    """At three JD skills the score is statistically informative; no cap,
    no note."""
    cv = {
        "Languages": ["Python"],
        "Databases": ["PostgreSQL"],
        "Cloud & DevOps": ["AWS"],
    }
    jd = {
        "Languages": ["Python"],
        "Databases": ["PostgreSQL"],
        "Cloud & DevOps": ["AWS"],
    }
    r = score_match(cv, jd)
    assert r.match_score > 60
    assert r.coverage_note == ""


def test_sparse_jd_no_overlap_still_low_no_inflated_floor():
    """The cap is an UPPER bound, not a lower one — a 0% overlap stays 0."""
    cv = {"Languages": ["Python"]}
    jd = {"Languages": ["Ruby"]}
    r = score_match(cv, jd)
    assert r.match_score == 0
    assert r.coverage_note  # still annotate sparse JDs
