# ProofHire Shield — Autonomous Session 3
# Paste this into: claude --dangerously-skip-permissions
# Inside the Proofhire-shield/ repo directory

---

/caveman

Read CLAUDE.md and SESSION-HANDOFF.md in full before writing a single line of code.
SESSION-HANDOFF.md has the complete project state. Do not rebuild anything listed there.

---

## Session 3 — Codex adversarial review loop + hardening

This session uses Codex CLI for adversarial security review. The workflow:

1. Run Codex on the codebase with the adversarial prompt below
2. Fix every HIGH finding — run tests after each fix, commit each fix separately
3. Run Codex again on the fixed code
4. Loop until Codex returns no HIGH findings
5. Then address MEDIUM findings one by one

This is Bhanu's perfectionist review loop. Do not skip the re-review step.

---

## Step 1 — Run Codex adversarial review (do this first)

```bash
codex "You are a security researcher hired to break ProofHire Shield before it ships to recruiters. The app scans CVs for prompt injection, PII, and AI-generated text. Motivated candidates WILL try to manipulate the AI tools recruiters use on their CVs.

Read these files carefully:
- backend/scanner.py
- backend/text_extract.py
- backend/main.py
- backend/match_analysis.py
- backend/safe_copy.py

Find and report:
1. Prompt injection bypass techniques the scanner would miss (e.g. encoding tricks, split-word attacks, metadata-only injection, unicode tricks not yet handled)
2. File upload security bugs (content-type bypass, path traversal, zip bomb, memory exhaustion)
3. API inputs that crash the server (empty file, corrupted PDF, encrypted DOCX, non-UTF8 text, gigantic base64 field)
4. Ways a candidate could manipulate their Match tab score (skill stuffing, fake experience claims the heuristic would believe)
5. Any code that runs user-controlled data without sufficient sanitisation

For every finding: severity (HIGH / MEDIUM / LOW), file + line number, exact issue, concrete fix in Python. Flag anything a real candidate could exploit in a live hiring process as HIGH."
```

After Codex responds:
- Fix every HIGH finding immediately
- Run: python -m pytest tests/ -q
- Fix any test failures
- Commit each fix separately using the mandatory commit format
- Then run Codex again with: "Review the same files. I fixed: [list what you fixed]. Are there still HIGH severity issues?"
- Loop until Codex confirms no HIGH findings remain

---

## Step 2 — Harden ZWC strip list

Add to _ZWC_RE in scanner.py (use Unicode escapes — NO literal bidi chars):
  "\u034f"           # combining grapheme joiner
  "\u115f\u1160"    # Hangul choseong/jungseong filler
  "\u3164"           # Hangul filler
  "\uffa0"           # halfwidth Hangul filler
  "\u180b-\u180e"   # Mongolian format chars
  "\ufe00-\ufe0f"   # variation selectors

Write adversarial tests first — one per char family — then make them pass.
Commit: fix(scanner): expand ZWC strip list — 10 additional evasion chars

---

## Step 3 — URL-safe base64

In scanner.py _decode_base64_candidates():
  Also try base64.urlsafe_b64decode() on each candidate string.
Write test: URL-safe base64 encoded "Ignore previous instructions" is detected.
Commit: fix(scanner): detect URL-safe base64 encoded injection strings

---

## Step 4 — DOCX zip bomb protection

In text_extract.py, before python-docx opens a DOCX file:
  import zipfile
  with zipfile.ZipFile(io.BytesIO(raw)) as zf:
      if sum(i.file_size for i in zf.infolist()) > 50 * 1024 * 1024:
          raise ValueError("DOCX uncompressed size exceeds 50 MB limit.")
Write test: normal DOCX passes check. (Cannot test actual bomb in CI — just verify normal path.)
Commit: fix(upload): DOCX zip bomb protection — cap uncompressed size at 50 MB

---

## Step 5 — No-skills API test

In tests/test_api.py, add:
  def test_match_analysis_no_skills():
      cv_text = "I enjoy problem solving and working in teams. References available on request."
      ... POST as text/plain ...
      assert result["match_analysis"]["total_skills_found"] == 0
      assert result["match_analysis"]["experience_tier"] == "Entry"
Commit: test(api): assert match_analysis for CV with no technical skills

---

## Step 6 — Semgrep

Run:
  semgrep --config=auto backend/ --json | python3 -c "import json,sys; d=json.load(sys.stdin); findings=d.get('results',[]); [print(f['check_id'], f['path'], f['start']['line'], f['extra']['severity']) for f in findings]"

For HIGH findings: fix the code.
For MEDIUM/LOW: add # nosemgrep: <rule-id> -- <reason> inline comment.
Commit if any changes made: fix(semgrep): address static analysis findings

---

## COMMIT FORMAT — mandatory for every commit

feat(scope): short title

What was built: [exact description]
Why it matters: [security or product reason]
Files changed: [each file + one line]
Test coverage: [what tests now cover this]
Attack prevented: [what a candidate can no longer do]

Never push. Never squash. Always show commit hash.

---

## After all steps complete

Run full test suite: python -m pytest tests/ -q
Run Bandit: bandit -r backend/ -ll -x __pycache__
Run tsc: cd frontend && npx tsc --noEmit

All must pass clean before session ends.

Then update SESSION-HANDOFF.md with what was done in this session.
SESSION-HANDOFF.md is gitignored — never commit it.

---

## Start here

git log --oneline -8
