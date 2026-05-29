# ProofHire Shield — Autonomous Session 3 Prompt

Paste into: `claude --dangerously-skip-permissions` inside the Proofhire-shield/ repo.

---

/caveman

Read CLAUDE.md in full. This is Session 3. Sessions 1 and 2 have been completed.

## What exists now (do NOT rebuild)

- Detection engine: prompt injection (7 PR-01 patterns), PII flagging, AI-text heuristic
- Hardening: ZWC stripping, homoglyph normalisation, base64 decode+scan, pdfplumber hidden text, DOCX full surface scan (headers, footers, textboxes, comments, metadata)
- Match analysis: heuristic skill extraction, experience tier, education level, interview probes, key claims
- Frontend: React 18 / TypeScript / Tailwind — Risk tab (traffic light, side-by-side viewer), Match tab (skills, tier, probes, claims), Proof tab (Trust Report PDF export)
- CI: GitHub Actions — Bandit + pytest + tsc + vite build on every push
- 107 tests passing. Bandit: 0 issues.

## Session 3 objectives — in order

### 1. Address REVIEW_02 findings
Read reviews/REVIEW_02_hardened_engine_match_analysis.md in full first.
Fix every HIGH finding. For MEDIUM findings: fix if it takes <30 lines. LOW: add a comment or a test, do not over-engineer.

### 2. Harden ZWC strip list
Add to _ZWC_RE in scanner.py:
  U+034F  combining grapheme joiner
  U+115F  Hangul choseong filler
  U+1160  Hangul jungseong filler
  U+3164  Hangul filler
  U+FFA0  halfwidth Hangul filler
  U+180B-U+180E  Mongolian format chars (180B, 180C, 180D, 180E)
  U+FE00-U+FE0F  variation selectors
Add adversarial tests for each new char. Tests must pass before committing.

### 3. Add URL-safe base64 variant detection
In scanner.py _decode_base64_candidates(): also try base64.urlsafe_b64decode().
Add one adversarial test: a URL-safe base64 encoded injection string.

### 4. DOCX zip bomb protection
In text_extract.py extract_text(): before calling python-docx, check the raw bytes — if the DOCX zip's uncompressed size estimate exceeds 50 MB, raise ValueError("File too large to process safely.").
Use zipfile.ZipFile to inspect the central directory before opening with python-docx.
Add a test that creates a normal DOCX and verifies the check passes for it.

### 5. Match tab — add a "no skills" API test
tests/test_api.py: add a test that POSTs a plain-text CV with no technical skills and asserts match_analysis.total_skills_found == 0 and match_analysis.experience_tier == "Entry".

### 6. Playwright E2E update
e2e/: if a test file exists, add one test that:
  1. Uploads demo-cvs/prompt-injection.pdf
  2. Clicks the Match tab
  3. Asserts that interview_probes are visible (at least one list item present)
If no Playwright file exists yet, create e2e/test_match_tab.spec.ts with this test only.

### 7. Run Semgrep
`semgrep --config=auto backend/ --json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(r['check_id'], r['path'], r['start']['line']) for r in d.get('results',[])]"`
Fix any HIGH severity findings. Low severity: add inline nosemgrep comment with reason.

## COMMIT FORMAT after every step — no exceptions

feat(scope): short title

What was built: [exact description]
Why it matters: [security or product reason]
Files changed: [each file + one line]
Test coverage: [what tests now cover this]
Attack prevented: [what a candidate could no longer do — for security commits]

Never git push. Never squash. Output full commit hash after each commit.
Author: Bhanu Gupta only. No Co-Authored-By.
Never stop to ask unless touching file upload handler or disk write path.

## Start here

git log --oneline -8
