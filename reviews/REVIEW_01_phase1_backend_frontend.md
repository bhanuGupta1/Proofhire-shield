# REVIEW 01 — Phase 1 Backend + Frontend

**Instructions for Bhanu:** Paste this entire prompt into Codex. Return with any findings.

---

## What was built

Phase 1 of ProofHire Shield — a Safe CV Workflow tool.

**Backend (FastAPI, Python 3.10+):**
- `backend/scanner.py` — PR-01 detection engine: 7 prompt injection pattern families (A–G), 12 PII pattern types, AI-text heuristic (regex buzzword matching). Zero LLM dependency.
- `backend/safe_copy.py` — Safe CV Copy generator: line-level injection removal + PII annotation with `[PII:TYPE]` markers.
- `backend/trust_report.py` — reportlab Trust Report PDF: risk verdict, injection findings, PII table, disclaimer.
- `backend/text_extract.py` — in-memory extraction from PDF (pdfminer.six), DOCX (python-docx), TXT. No temp files written to disk.
- `backend/main.py` — FastAPI app: POST `/scan-cv` (content-type guard, 10 MB cap, filename sanitisation), POST `/trust-report`.
- `backend/models.py` — Pydantic v2 I/O models.
- `tests/` — 30 pytest tests: all 7 injection patterns, PII flagging, AI score, risk scoring for all 5 demo CVs. All passing.

**Frontend (React 18, TypeScript, Tailwind, Vite):**
- Three-tab layout: Risk (live), Match (Phase 2 placeholder), Proof (audit summary + PDF export).
- `FileUpload.tsx` — drag-and-drop + click upload.
- `TrafficLight.tsx` — GREEN/ORANGE/RED traffic light with score.
- `SideBySideViewer.tsx` — original vs safe copy with injection lines highlighted red.
- `ProofTab.tsx` — downloads Trust Report PDF by re-posting the file to `/trust-report`.

---

## Files changed

| File | Description |
|---|---|
| `backend/scanner.py` | Detection engine — patterns, scoring |
| `backend/safe_copy.py` | Safe copy generator |
| `backend/trust_report.py` | PDF export |
| `backend/text_extract.py` | In-memory file parsing |
| `backend/main.py` | FastAPI routes |
| `backend/models.py` | Pydantic models |
| `backend/requirements.txt` | Python deps |
| `tests/test_scanner.py` | Scanner unit tests |
| `tests/test_safe_copy.py` | Safe copy tests |
| `tests/test_risk_scoring.py` | Demo CV traffic light tests |
| `frontend/src/App.tsx` | Root component + tab router |
| `frontend/src/components/*` | UI components |
| `frontend/src/lib/api.ts` | fetch wrapper |
| `frontend/src/lib/types.ts` | TypeScript types |
| `demo-cvs/*.pdf` | 5 synthetic demo CVs |
| `.github/workflows/ci.yml` | CI: bandit + pytest + tsc + vite build |

---

## Questions for Codex

1. **Security bugs in the file upload handler (`main.py`):**
   - Is the content-type check bypassable (e.g. MIME sniffing vs declared type)?
   - Is the filename sanitisation in `_sanitise_filename()` sufficient against path traversal?
   - Is there any risk in passing `raw` bytes directly to pdfminer/python-docx without further validation?

2. **Prompt injection bypass — what patterns does the scanner miss?**
   - Review `scanner.py` PR-01-A through PR-01-G. What real-world injection strings would evade all 7 patterns?
   - Consider: Unicode homoglyphs, base64-encoded instructions, multi-line spread attacks, HTML/XML comment wrappers, JSON-encoded payloads, steganographic whitespace.

3. **Safe copy robustness:**
   - The safe copy works line-by-line. Can an attacker spread an injection across two lines to evade removal?
   - Can PII annotation in `safe_copy.py` be used as a vector (e.g. a crafted string that tricks the PII regex into replacing legitimate content)?

4. **Edge cases the tests don't cover:**
   - Empty PDF (0 bytes of content after extraction)
   - Corrupted PDF (invalid PDF structure)
   - PDF with only images (no extractable text) — what does the scan return?
   - Very large text (e.g. 500-page document pasted as TXT)
   - Non-UTF-8 encoded TXT file
   - CV entirely in a non-Latin script (e.g. Chinese, Arabic)

5. **Architecture risks:**
   - The `/trust-report` endpoint re-scans the file (re-runs the full scan). Is there a risk of double-processing or inconsistency between the UI-displayed result and the PDF?
   - The backend has no rate limiting. What's the risk of a candidate spamming the scan endpoint to probe detection patterns?

6. **Phase 1 scope — is anything out of scope creeping in?**
   - Review all files. Does anything build functionality that belongs to Phase 2 or later?

7. **Demo readiness — 90-second Loom test:**
   - Upload `02_prompt_injection.pdf`. Does the side-by-side viewer clearly show the hidden payload? Would a recruiter understand it in 10 seconds?
   - What is the single most confusing thing a non-technical recruiter would see on first use?

8. **Additional tests to add:**
   - What attack could a determined candidate use that the current 30 tests would not catch?
   - Suggest 3 specific test cases to add to `tests/test_scanner.py`.
