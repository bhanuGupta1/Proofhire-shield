"""Tests for jd_match — JD <-> CV skill matching (C1)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from jd_match import match_cv_to_jd, score_match, extract_jd_keywords


def test_exact_match():
    r = match_cv_to_jd("Skilled in Python.", "We need Python.")
    assert "Python" in r.matched_skills
    assert r.match_score >= 70  # single shared category fully covered


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
