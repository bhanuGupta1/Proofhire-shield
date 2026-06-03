"""
Match analysis — heuristic skill extraction, experience tier, education level,
and interview probe generation.

Zero LLM dependency. Pure regex + keyword matching. Works offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scanner import scan_text

# ── Skill taxonomy ─────────────────────────────────────────────────────────────

_SKILLS: dict[str, list[str]] = {
    "Languages": [
        "Python", "JavaScript", "TypeScript", "Java", "C#", "C\\+\\+", "Go",
        "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R", "MATLAB",
        "Bash", "Shell", "SQL", "HTML", "CSS",
    ],
    "Frameworks & Libraries": [
        "React", "Angular", "Vue", "Next\\.js", "Node\\.js", "Express",
        "Django", "Flask", "FastAPI", "Spring", "Rails", "Laravel",
        "TensorFlow", "PyTorch", "Scikit-learn",
        "Tailwind", "Bootstrap", "GraphQL", "REST", "gRPC",
    ],
    "Cloud & DevOps": [
        "AWS", "Azure", "GCP", "Google Cloud", "Docker", "Kubernetes",
        "Terraform", "Ansible", "Jenkins", "GitHub Actions", "CircleCI",
        "Helm", "Kafka", "RabbitMQ", "Redis", "Elasticsearch",
        "Prometheus", "Grafana", "Datadog", "Splunk",
    ],
    "Databases": [
        "PostgreSQL", "MySQL", "MongoDB", "SQLite", "DynamoDB",
        "Cassandra", "BigQuery", "Snowflake", "Redshift", "Oracle",
        "MariaDB", "Firestore", "Neo4j",
    ],
    "Tools & Practices": [
        "Git", "GitHub", "GitLab", "Jira", "Confluence", "Figma",
        "Agile", "Scrum", "Kanban", "CI/CD", "TDD", "BDD",
        "Microservices", "Serverless", "Linux", "Unix",
    ],
    "Testing & QA": [
        "pytest", "Jest", "Cypress", "Selenium", "Playwright",
        "JUnit", "Mocha", "Chai", "Postman", "k6",
    ],
    "Data & ML Ops": [
        "Pandas", "NumPy", "Spark", "Airflow", "dbt", "Jupyter",
        "Matplotlib", "Seaborn", "MLflow", "Weights & Biases", "Hugging Face",
    ],
}

# Build compiled regex per skill — word-boundary match, case-insensitive
_SKILL_PATTERNS: dict[str, dict[str, re.Pattern]] = {
    category: {
        skill: re.compile(rf"\b{skill}\b", re.IGNORECASE)
        for skill in skills
    }
    for category, skills in _SKILLS.items()
}


def _extract_skills(text: str) -> dict[str, list[str]]:
    """Return skills grouped by category, preserving canonical capitalisation."""
    found: dict[str, list[str]] = {}
    for category, patterns in _SKILL_PATTERNS.items():
        hits = []
        for canonical, pat in patterns.items():
            if pat.search(text):
                # Use canonical name (strip any regex escapes)
                hits.append(canonical.replace("\\", "").replace("+", "+"))
        if hits:
            found[category] = hits
    return found


# ── Experience tier ────────────────────────────────────────────────────────────

# Matches "5 years", "5+ years", "five years", etc.
_YEARS_RE = re.compile(
    r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|work|exp)?",
    re.IGNORECASE,
)

_SENIORITY_WORDS = {
    "principal": 4,
    "staff": 4,
    "director": 4,
    "vp ": 4,
    "head of": 4,
    "lead": 3,
    "senior": 3,
    r"sr\.": 3,
    "mid": 2,
    "associate": 2,
    "junior": 1,
    r"jr\.": 1,
    "intern": 1,
    "graduate": 1,
    "entry": 1,
    "fresher": 1,
}

_TIER_LABELS = {1: "Entry", 2: "Mid-level", 3: "Senior", 4: "Principal / Lead"}


def _compute_experience_tier(text: str) -> tuple[str, int | None]:
    """Returns (tier_label, max_years_found_or_None)."""
    # Years mentioned in text — ignore implausible values (0, >50) that would
    # otherwise let a candidate inflate the tier with "99 years experience".
    years_hits = [
        y for y in (int(m.group(1)) for m in _YEARS_RE.finditer(text))
        if 0 < y <= 50
    ]
    max_years = max(years_hits) if years_hits else None

    # Score from explicit years
    years_score = 0
    if max_years is not None:
        if max_years >= 10:
            years_score = 4
        elif max_years >= 5:
            years_score = 3
        elif max_years >= 2:
            years_score = 2
        else:
            years_score = 1

    # Score from seniority keywords
    text_lower = text.lower()
    seniority_score = 0
    for word, score in _SENIORITY_WORDS.items():
        if re.search(rf"\b{word}", text_lower):
            seniority_score = max(seniority_score, score)

    final_score = max(years_score, seniority_score)
    tier = _TIER_LABELS.get(final_score, "Entry")

    # Phase 9 — hard floor: a candidate with no detectable years of
    # experience is always Entry, regardless of any seniority keyword that
    # may have leaked in from unrelated text. ("Associate's degree" hits the
    # "associate" seniority keyword and used to inflate to Mid-level; same
    # for "Midwest", "leading the team" used as a verb phrase, etc.)
    if not max_years:
        tier = "Entry"

    return tier, max_years


# ── Education level ────────────────────────────────────────────────────────────

# Phase 9 fix — the bare-two-letter abbreviations `MS`, `BS`, `BE`, `AS`
# matched anywhere by the previous regex (e.g. "MS Office", "be a senior
# engineer", "as a team lead"), which combined with the highest-rank-wins
# resolution silently inflated education levels — a Bachelor's CV listing
# "MS Excel" was being labelled Master's. The first dot is now required on
# every two-letter alternative, so "M.S." and "M.S" still match for an
# academic CV but the bare-word collisions are gone. `MSc` / `BSc` / `BEng`
# / `MBA` / "Bachelor" / "Master" keep working unchanged.
_EDU_PATTERNS = [
    (re.compile(r"\b(ph\.?d|doctor(?:ate)?)\b", re.IGNORECASE), "PhD"),
    (re.compile(r"\b(m\.?sc|m\.s\.?|master(?:s)?(?:\sof)?|mba|meng)\b", re.IGNORECASE), "Master's"),
    (re.compile(r"\b(b\.?sc|b\.s\.?|b\.e\.?|b\.?eng|bachelor(?:s)?(?:\sof)?|b\.a\.?)\b", re.IGNORECASE), "Bachelor's"),
    (re.compile(r"\b(associate(?:s)?(?:\sdegree)?|a\.s\.?|a\.a\.?)\b", re.IGNORECASE), "Associate's"),
    (re.compile(r"\b(high school|secondary school|diploma|ged)\b", re.IGNORECASE), "High School"),
    (re.compile(r"\b(bootcamp|boot camp|self-?taught|online course|certification)\b", re.IGNORECASE), "Certification / Bootcamp"),
]

_EDU_RANK = {
    "PhD": 6,
    "Master's": 5,
    "Bachelor's": 4,
    "Associate's": 3,
    "High School": 2,
    "Certification / Bootcamp": 1,
}

# Short forms used by the recruiter summary card.
_EDU_ABBREV = {
    "PhD": "PhD",
    "Master's": "MSc",
    "Bachelor's": "BSc",
    "Associate's": "Assoc",
    "High School": "HS",
    "Certification / Bootcamp": "Cert",
    "Not specified": "—",
}


# Phase 9 v2 — section-scoped education detection.
#
# Without scoping, a Bachelor's CV that mentions "MSc" anywhere (a project
# description, a course list, a supervisor's title, a research programme) gets
# silently inflated to Master's because the highest-rank-wins resolver doesn't
# care WHERE the keyword lived. Restricting the scan to a clearly-headed
# Education section makes that noise invisible. CVs WITHOUT a clear Education
# header still get the whole-text scan as a fallback.

_EDU_SECTION_HEADER_RE = re.compile(
    r"^\s*(?:education(?:al)?(?:\s+(?:background|history|qualifications?))?|"
    r"academic(?:\s+(?:background|history|qualifications?))?|"
    r"qualifications?)"
    r"\s*[:\-]?\s*$",
    re.IGNORECASE,
)

# Headers that close the Education section if encountered after it.
_NON_EDU_SECTION_HEADER_RE = re.compile(
    r"^\s*(?:experience|work\s+experience|employment(?:\s+history)?|"
    r"professional\s+experience|career(?:\s+history)?|"
    r"skills|technical\s+skills|core\s+competen(?:ce|cies)|"
    r"projects|portfolio|certifications?|publications?|"
    r"awards|honou?rs|references?|languages|hobbies|interests?|"
    r"summary|profile|objective|about(?:\s+me)?|contact|"
    r"achievements?|volunteer(?:ing)?|extra-?curricular)"
    r"\s*[:\-]?\s*$",
    re.IGNORECASE,
)


def _find_education_section(text: str) -> str | None:
    """Return the text of the candidate's Education section, or None if no
    clear heading is detected. Caller falls back to whole-text scanning.

    Strategy: scan line-by-line for a line that's just an Education-style
    heading (optionally with a trailing colon / dash); take subsequent
    lines until the next major non-Education section header (or 60 lines,
    whichever first). 60 is a soft cap so a CV with a permissive
    "Education" heading and no other clear headers doesn't accidentally
    swallow the whole document."""
    lines = text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if _EDU_SECTION_HEADER_RE.match(line.strip()):
            start_idx = i + 1
            break
    if start_idx is None:
        return None
    end_idx = min(start_idx + 60, len(lines))
    for j in range(start_idx, end_idx):
        if _NON_EDU_SECTION_HEADER_RE.match(lines[j].strip()):
            end_idx = j
            break
    section_text = "\n".join(lines[start_idx:end_idx]).strip()
    return section_text or None


def _detect_education(text: str) -> str:
    """Return highest education level found, or 'Not specified'.

    Prefers scanning ONLY the Education section when a clear header
    exists, so a "MSc" mention buried in a project description or
    course list can't inflate a Bachelor's CV to Master's. Falls back
    to whole-CV scan when no Education header is detected (zero
    structure → best we can do with regex)."""
    section_text = _find_education_section(text)
    scan_text = section_text if section_text is not None else text
    best_label = "Not specified"
    best_rank = 0
    for pat, label in _EDU_PATTERNS:
        if pat.search(scan_text):
            if _EDU_RANK[label] > best_rank:
                best_rank = _EDU_RANK[label]
                best_label = label
    return best_label


# ── Interview probes ───────────────────────────────────────────────────────────

# Probe templates keyed by skill keyword (lowercase match)
_PROBE_TEMPLATES: dict[str, list[str]] = {
    "python": [
        "Walk me through how you'd structure a Python service for high throughput.",
        "How do you handle memory leaks in a long-running Python process?",
    ],
    "javascript": [
        "Explain the event loop and how you'd debug an async race condition.",
        "What's your approach to bundle size optimisation in a JS project?",
    ],
    "typescript": [
        "How do you model a discriminated union in TypeScript and when would you reach for one?",
    ],
    "react": [
        "How do you decide between Context, Zustand, and React Query for state?",
        "Walk me through optimising a React component that re-renders too often.",
    ],
    "aws": [
        "Describe a time you reduced AWS spend. What levers did you pull?",
        "How do you design for fault tolerance across AWS availability zones?",
    ],
    "docker": [
        "How do you keep Docker images lean and secure in production?",
    ],
    "kubernetes": [
        "Explain your approach to resource requests/limits and pod autoscaling.",
    ],
    "postgresql": [
        "How do you approach query optimisation on a large PostgreSQL table?",
        "When would you reach for a partial index vs a composite index?",
    ],
    "mongodb": [
        "When would you choose MongoDB over a relational DB and what are the tradeoffs?",
    ],
    "machine learning": [
        "How do you detect and handle data drift in a production ML model?",
    ],
    "tensorflow": [
        "Walk me through your model debugging workflow when validation loss diverges.",
    ],
    "pytorch": [
        "How do you profile GPU memory usage in a PyTorch training loop?",
    ],
    "java": [
        "Explain JVM garbage collection tuning — when have you needed to adjust GC settings?",
    ],
    "go": [
        "How do you manage goroutine lifecycles and avoid goroutine leaks?",
    ],
    "sql": [
        "Write a query to find the second-highest salary without using LIMIT/OFFSET.",
        "What's the difference between a clustered and non-clustered index?",
    ],
    "agile": [
        "Describe a sprint retrospective where you identified and fixed a process problem.",
    ],
    "microservices": [
        "How do you handle distributed transactions across microservices?",
        "What's your approach to inter-service authentication?",
    ],
    "pytest": [
        "How do you structure pytest fixtures for tests that share expensive setup?",
    ],
    "cypress": [
        "What's your approach to flaky end-to-end tests in Cypress?",
    ],
    "selenium": [
        "How do you keep Selenium tests stable across browser and version drift?",
    ],
    "playwright": [
        "When would you reach for Playwright over Cypress, and why?",
    ],
    "airflow": [
        "Walk me through a non-trivial Airflow DAG you debugged in production.",
    ],
    "dbt": [
        "How do you manage incremental models and testing in dbt?",
    ],
    "spark": [
        "How do you debug a Spark job spending too long in shuffles?",
    ],
}

# Generic probes used when no skill-specific probes found
_GENERIC_PROBES = [
    "Tell me about a technical decision you made that you'd make differently now.",
    "Describe your approach to debugging a production incident with no obvious cause.",
    "How do you stay current with the technology in your domain?",
    "Walk me through a project where you had to balance speed with code quality.",
]


def _generate_probes(skills: dict[str, list[str]], tier: str) -> list[str]:
    """Generate up to 5 interview probes based on detected skills and tier."""
    probes: list[str] = []
    seen: set[str] = set()

    # Flatten detected skills to lowercase for lookup
    all_skills_lower = [
        s.lower().replace("\\", "").replace(".", "")
        for skills_list in skills.values()
        for s in skills_list
    ]

    for skill_key, templates in _PROBE_TEMPLATES.items():
        if any(skill_key in s for s in all_skills_lower):
            for probe in templates:
                if probe not in seen and len(probes) < 4:
                    probes.append(probe)
                    seen.add(probe)

    # Add a tier-appropriate generic probe
    if tier in ("Senior", "Principal / Lead"):
        probes.append("How do you approach mentoring junior engineers?")
    elif tier == "Mid-level":
        probes.append("Describe a situation where you had to push back on a product requirement.")
    else:
        probes.append("How do you approach learning an unfamiliar codebase?")

    # Fill to 5 with generics if needed
    for probe in _GENERIC_PROBES:
        if len(probes) >= 5:
            break
        if probe not in seen:
            probes.append(probe)
            seen.add(probe)

    return probes[:5]


# ── Key claims ────────────────────────────────────────────────────────────────

_CLAIM_PATTERNS = [
    re.compile(r"(?:led|managed|built|architected|designed|delivered)\s+[^\n.]{10,60}", re.IGNORECASE),
    re.compile(r"(?:increased|reduced|improved|cut|saved|grew)\s+[^\n.]{10,60}", re.IGNORECASE),
    re.compile(r"\d+[%x]\s+(?:improvement|increase|reduction|faster|growth|uplift)", re.IGNORECASE),
    re.compile(r"(?:team of|managed)\s+\d+", re.IGNORECASE),
]


def _extract_key_claims(text: str) -> list[str]:
    """Extract up to 5 verifiable-looking claims from the CV.

    A claim that itself contains an injection is dropped — otherwise it would be
    shown on the Match tab and could be copied into a recruiter's AI tool.
    """
    seen: set[str] = set()
    claims: list[str] = []
    for pat in _CLAIM_PATTERNS:
        for m in pat.finditer(text):
            claim = m.group(0).strip()
            normalised = claim.lower()
            if normalised in seen or len(claims) >= 5:
                continue
            injection, _, _ = scan_text(claim)
            if injection:
                continue
            claims.append(claim)
            seen.add(normalised)
    return claims


# ── CV completeness ───────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/", re.IGNORECASE)
_GITHUB_RE = re.compile(r"github\.com/[a-zA-Z0-9_-]+", re.IGNORECASE)
_WORK_DATES_RE = re.compile(r"20\d\d[\s\-–—]+(?:20\d\d|present|current)", re.IGNORECASE)
_SKILLS_HEADING_RE = re.compile(r"\b(skills|technologies|stack)\b", re.IGNORECASE)


@dataclass
class CompletenessResult:
    score: int
    breakdown: dict[str, bool]


def score_cv_completeness(text: str) -> CompletenessResult:
    """Score the structural completeness of a CV (0-100) from 9 signals."""
    word_count = len(text.split())
    checks: dict[str, tuple[bool, int]] = {
        "Has email":                    (bool(_EMAIL_RE.search(text)), 10),
        "Has phone":                    (bool(_PHONE_RE.search(text)), 10),
        "Has LinkedIn":                 (bool(_LINKEDIN_RE.search(text)), 10),
        "Has GitHub":                   (bool(_GITHUB_RE.search(text)), 10),
        "Has work-entry dates":         (bool(_WORK_DATES_RE.search(text)), 15),
        "Has measurable achievement":   (any(p.search(text) for p in _CLAIM_PATTERNS), 15),
        "Has skills heading":           (bool(_SKILLS_HEADING_RE.search(text)), 10),
        "Word count >= 300":            (word_count >= 300, 10),
        "Word count >= 600":            (word_count >= 600, 10),
    }
    score = sum(pts for hit, pts in checks.values() if hit)
    breakdown = {label: hit for label, (hit, _) in checks.items()}
    return CompletenessResult(score=score, breakdown=breakdown)


# ── Public API ─────────────────────────────────────────────────────────────────

# ── Candidate summary card ────────────────────────────────────────────────────

def generate_candidate_summary(
    skills: dict[str, list[str]],
    tier: str,
    years: int | None,
    education: str,
    key_claims: list[str],
) -> str:
    """One-line recruiter summary in the style:
    'Senior Python · React · AWS engineer (8y exp) | MSc | 3 verifiable claims'.
    Template-based, no LLM.
    """
    top_skills: list[str] = []
    for _, items in sorted(skills.items(), key=lambda kv: -len(kv[1])):
        for s in items:
            if s not in top_skills:
                top_skills.append(s)
                if len(top_skills) >= 3:
                    break
        if len(top_skills) >= 3:
            break

    tier_label = tier or "Entry"
    if top_skills:
        role = f"{tier_label} {' · '.join(top_skills)} engineer"
    else:
        role = f"{tier_label} candidate"
    if years is not None:
        role += f" ({years}y exp)"

    edu = _EDU_ABBREV.get(education, "—")
    n = len(key_claims)
    claims = f"{n} verifiable claim{'s' if n != 1 else ''}"
    return f"{role} | {edu} | {claims}"


# ── Red flags ────────────────────────────────────────────────────────────────

def detect_red_flags(
    text: str,
    skills: dict[str, list[str]],
    tier: str,
    years: int | None,
) -> list[str]:
    """Heuristic red flags surfaced to recruiters. Not a hiring decision."""
    flags: list[str] = []

    total_skills = sum(len(v) for v in skills.values())

    if total_skills >= 15 and years is not None and years < 3:
        flags.append("Unusually broad tech stack for stated experience.")

    if total_skills == 0 and years is not None and years >= 5:
        flags.append("5+ years claimed but no recognised technical skills detected.")

    distinct_years = {
        y for y in (int(m.group(1)) for m in _YEARS_RE.finditer(text))
        if 0 < y <= 50
    }
    if len(distinct_years) >= 2:
        flags.append("Inconsistent experience claims — verify with candidate.")

    if len(text.split()) < 150:
        flags.append("CV appears very short — may be incomplete or a stub.")

    employers = set(re.findall(r"(?:at|@)\s+([A-Z][a-zA-Z]+)", text))
    if len(employers) > 3 and years is not None and years < 2:
        flags.append("High job frequency relative to stated experience.")

    return flags


@dataclass
class MatchAnalysis:
    skills: dict[str, list[str]]
    experience_tier: str
    years_experience: int | None
    education_level: str
    interview_probes: list[str]
    key_claims: list[str]
    total_skills_found: int
    summary: str
    completeness: CompletenessResult
    red_flags: list[str]
    # Phase 9 v4 — which engine actually produced the education / tier
    # values, so the UI can show a badge and the recruiter knows whether
    # they got the fast deterministic path or the context-aware AI path.
    # "regex" means the LLM was skipped or unavailable; "llm" means an
    # LLM successfully returned and refined the values.
    match_engine: str = "regex"


def _years_to_tier(years: int | None) -> str:
    """Map a years-of-experience integer back to a tier label, using the
    same buckets as _compute_experience_tier's years_score path. Used
    when the LLM gives us a years figure directly and we need a tier
    that matches it without re-running the regex+seniority-keyword
    blend (which is what produced the wrong tier in the first place)."""
    if not years:
        return "Entry"
    if years >= 10:
        return "Principal / Lead"
    if years >= 5:
        return "Senior"
    if years >= 2:
        return "Mid-level"
    return "Entry"


def analyze_match(text: str, *, engine: str = "llm") -> MatchAnalysis:
    """Run all heuristics and return a MatchAnalysis.

    Phase 9 v4 — caller picks the match engine:

    - `engine="regex"` (fast, deterministic, on-device) — runs ONLY the
      regex paths. Microseconds per scan, no LLM call. The trade-off is
      that decorative keyword mentions ("MSc dissertation supervisor",
      "MSc-level coursework", "taught a Bachelor's programme") can land
      in the wrong bucket on unusual CV layouts, because the regex has
      no notion of "the candidate themselves vs someone else".

    - `engine="llm"` (default, context-aware) — runs the regex first,
      then asks an LLM (Groq → Anthropic) to read the CV with context
      and override the education_level + years_experience when it has
      a confident answer. ~600-1500 ms per scan. Failure modes (no API
      key, network error, parse failure, invalid level) silently fall
      back to the regex result, so deployments without an LLM still
      get sensible output and the per-scan latency stays bounded.

    The `MatchAnalysis.match_engine` field on the returned object tells
    the caller which engine ACTUALLY produced the values — `"llm"` only
    when the LLM successfully refined them; `"regex"` for the regex path
    OR for an `engine="llm"` request whose LLM call ended up falling
    back. The recruiter UI uses this to render a "AI / Fast" badge.
    """
    skills = _extract_skills(text)
    tier, years = _compute_experience_tier(text)
    education = _detect_education(text)

    used_engine = "regex"
    if engine == "llm":
        # Best-effort LLM refinement. Returns None when no provider is
        # configured (tests, dev deploys without keys), which silently
        # falls back to the regex result above.
        try:
            from cv_llm_extract import extract_cv_facts

            llm_facts = extract_cv_facts(text)
        except Exception:
            llm_facts = None
        if llm_facts:
            llm_level = llm_facts.get("education_level")
            llm_years = llm_facts.get("years_experience")
            if llm_level:
                education = llm_level
            if llm_years is not None:
                years = llm_years
                # Recompute tier from the refined years figure. Drop the
                # seniority-keyword blend (which inflated "Senior" CVs
                # with no years) — the LLM already saw the same text
                # and gave us the canonical years count.
                tier = _years_to_tier(llm_years)
            used_engine = "llm"

    probes = _generate_probes(skills, tier)
    claims = _extract_key_claims(text)
    total = sum(len(v) for v in skills.values())
    summary = generate_candidate_summary(skills, tier, years, education, claims)
    completeness = score_cv_completeness(text)
    red_flags = detect_red_flags(text, skills, tier, years)

    return MatchAnalysis(
        skills=skills,
        experience_tier=tier,
        years_experience=years,
        education_level=education,
        interview_probes=probes,
        key_claims=claims,
        total_skills_found=total,
        summary=summary,
        completeness=completeness,
        red_flags=red_flags,
        match_engine=used_engine,
    )
