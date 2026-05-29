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
        "TensorFlow", "PyTorch", "Pandas", "NumPy", "Scikit-learn",
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
    # Years mentioned in text
    years_hits = [int(m.group(1)) for m in _YEARS_RE.finditer(text)]
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
    return tier, max_years


# ── Education level ────────────────────────────────────────────────────────────

_EDU_PATTERNS = [
    (re.compile(r"\b(ph\.?d|doctor(?:ate)?)\b", re.IGNORECASE), "PhD"),
    (re.compile(r"\b(m\.?sc|m\.?s\.?|master(?:s)?(?:\sof)?|mba|meng)\b", re.IGNORECASE), "Master's"),
    (re.compile(r"\b(b\.?sc|b\.?s\.?|b\.?e\.?|b\.?eng|bachelor(?:s)?(?:\sof)?|b\.a\.?)\b", re.IGNORECASE), "Bachelor's"),
    (re.compile(r"\b(associate(?:s)?(?:\sdegree)?|a\.?s\.?|a\.?a\.?)\b", re.IGNORECASE), "Associate's"),
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


def _detect_education(text: str) -> str:
    """Return highest education level found, or 'Not specified'."""
    best_label = "Not specified"
    best_rank = 0
    for pat, label in _EDU_PATTERNS:
        if pat.search(text):
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


# ── Public API ─────────────────────────────────────────────────────────────────

@dataclass
class MatchAnalysis:
    skills: dict[str, list[str]]
    experience_tier: str
    years_experience: int | None
    education_level: str
    interview_probes: list[str]
    key_claims: list[str]
    total_skills_found: int


def analyze_match(text: str) -> MatchAnalysis:
    """Run all heuristics and return a MatchAnalysis."""
    skills = _extract_skills(text)
    tier, years = _compute_experience_tier(text)
    education = _detect_education(text)
    probes = _generate_probes(skills, tier)
    claims = _extract_key_claims(text)
    total = sum(len(v) for v in skills.values())

    return MatchAnalysis(
        skills=skills,
        experience_tier=tier,
        years_experience=years,
        education_level=education,
        interview_probes=probes,
        key_claims=claims,
        total_skills_found=total,
    )
