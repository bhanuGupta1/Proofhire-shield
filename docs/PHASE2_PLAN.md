# Phase 2+ Expansion Plan — HireIQ-class capability

> **Authorising directive** (Bhanu, 2026-05-30): bring ProofHire Shield to feature
> and architecture parity with HireIQ — the AI-powered candidate assessment
> platform previously built for a specialist sales recruitment firm.

## What this means concretely

| Capability | Phase 1 (today) | HireIQ target |
|---|---|---|
| LLM-driven assessment | none | Claude API → structured, client-ready report |
| Scoring engine | heuristic risk + match | multi-framework, proprietary, 3 candidate tiers |
| Stack | React + FastAPI, stateless | React + FastAPI on AWS, production-grade |
| Persistence | none | DB (recruiter accounts, saved scans, report history) |
| Auth / multi-tenant | none | recruiter-firm accounts, per-firm scoping |
| Delivery cadence | ad hoc | 8 phases with milestone sign-off |

## Hard guardrails carried forward from CLAUDE.md

- **Authorship**: never add AI tools as author or `Co-Authored-By:` (§1).
- **Local commits only**; Bhanu pushes (§1).
- **Security gates**: bandit + semgrep + Codex pass at the end of each phase.
- **Detection-engine posture stays Phase-1 strict**: every change still gets a test,
  the engine itself remains simple/testable/boring. The expansion adds layers ON
  TOP of the core, it does not loosen the core.
- **Backend rule (§3)** still applies to the new modules: simple, testable, boring,
  no clever abstractions, no premature flexibility.

CLAUDE.md §4's "no DB / no auth / no LLM / zero-cost" Phase-1 constraints are
explicitly SUPERSEDED for the expansion path. CLAUDE.md should be updated to
record this.

## Proposed phase plan (mirrors HireIQ's 8-phase milestone cadence)

### Phase 2 — Assessment report generator (Claude API)
Smallest distinctive HireIQ feature. A completed scan's results feed a Claude prompt
that produces a structured assessment report shown to the recruiter.
- `backend/assessment.py`: `generate_assessment_report(scan_result) -> AssessmentReport`.
- `POST /assessment`: input = scan result (or scan_id once persistence lands); output
  = `AssessmentReportModel`.
- Anthropic SDK as a backend dependency. Prompt caching ON by default. Current model
  (per the claude-api skill) so we never pin a stale ID.
- API key from `ANTHROPIC_API_KEY`; HF Spaces Secret in deploy.
- Frontend: new "Assessment" tab below the existing Risk / Match / Proof tabs,
  visible once a scan completes. Renders the structured report.
- Tests: stub the SDK call (HTTP mock or injected client), assert prompt structure
  + response handling on happy + error paths.
- Codex review pass at end of phase.

### Phase 3 — Persistence (free-tier Postgres)
- Postgres on Neon (free tier, matches AWS Postgres dialect for Phase 6).
- SQLAlchemy + Alembic migrations.
- Tables: `scans`, `assessments`. `recruiter_firms` deferred to Phase 4.
- Backwards-compatible: anonymous scans still work; if `DATABASE_URL` is set,
  scans + assessments persist; otherwise the API behaves as today.

### Phase 4 — Auth + recruiter-firm multi-tenancy
- Clerk (preferred) or Supabase Auth — free tier.
- `recruiter_firms` table; all scans/assessments scoped to firm.
- RBAC: viewer / recruiter / admin.
- Per-firm history view on the frontend.

### Phase 5 — Multi-framework scoring engine (3 tiers)
**BLOCKED until Bhanu shares the proprietary methodology and tier definitions.**
- Pluggable framework registry: each framework declares dimensions and rubric.
- Tier model: configurable; my placeholder is sales-specific
  SDR / AE / Sales Leadership — confirm with Bhanu.
- Calibration tooling (offline notebook) to validate against past HireIQ output.

### Phase 6 — AWS migration
- ECS / Fargate (or Lambda if footprint stays small).
- RDS Postgres (Aurora Serverless v2 if usage is spiky).
- Secrets Manager for `ANTHROPIC_API_KEY` and DB URL.
- CloudFront in front of Cloudflare Pages, or move frontend hosting too.

### Phase 7 — Production hardening + observability
- CloudWatch / OpenTelemetry instrumentation.
- Per-firm rate limiting + quota (especially for Claude calls).
- Per-firm usage metering; Claude spend dashboard.
- Costed alerting (e.g., alert at $X/day per firm).

### Phase 8 — Recruiter co-pilot
- Conversational interface over a candidate's scan + assessment.
- Saved query history per firm.
- Optional: Slack integration for recruiters to chat with a candidate's record.

## Architecture decisions (provisional)

- **Continue this repo** — don't fork. The security scanner is reusable as the
  ingestion layer; HireIQ-style assessment sits on top.
- **React + FastAPI** stay the stack.
- **LLM default: Claude API** (per Bhanu's HireIQ build).
- **DB**: defer to Phase 3; Postgres-on-Neon to start, Postgres-on-RDS at AWS.
- **Hosting**: HF Spaces + Cloudflare Pages through Phase 5; AWS in Phase 6.
- **Phase-2 reversibility**: assessment endpoint stays optional. If Claude API is
  not configured, the endpoint returns 503 with a clear message; the scan
  workflow still ships as Phase 1.

## Open questions for Bhanu (need answers before Phase 2 commits land)

1. **The 3 candidate experience tiers** — what are they exactly? My current Match
   tab uses Entry / Mid-level / Senior / Principal-Lead. HireIQ said "three" —
   are these sales-specific (e.g., SDR / AE / Sales Leadership), or do they map
   to my existing four?
2. **The proprietary scoring methodology** — is it shareable? If yes, share the
   rubric and ideally 2-3 example assessment reports so I can match style + depth.
   If no, I will build a generic sales-screening framework and flag the gap.
3. **Anthropic API key strategy for the build phase** — env var locally and
   HF Spaces Secret on deploy is the simplest. Confirm, or specify AWS Secrets
   Manager now if you'd rather not deal with a key-storage migration in Phase 6.
4. **Phase-2 width** — ship the assessment endpoint alone first, then Phase 3 in a
   separate slice, OR start the DB foundation in parallel with Phase 2? My strong
   recommendation: Phase 2 alone, single reviewable slice.

## Status

- Phase 1: shipped (Session 3 end). 157 tests, 0 HIGH remaining after three Codex
  passes. See `SESSION-HANDOFF.md`.
- Phase 2 backend: SHIPPED + HARDENED — `/assessment` endpoint, ProofHire v1
  framework, Claude API integration. End-of-phase Codex review (P2) found
  HIGH=3 MED=2 LOW=1; all six were closed in the P2-review hardening commit
  (server-derived signals, escaped delimiters in `<signals>`/`<cv>`/`<role>`,
  masked upstream error). Confirm review (P3) returned HIGH=0 MED=0 LOW=1
  (no-API-key disclosure); the LOW closed in 9e4fbc0. **176 tests; bandit 0;
  semgrep 0.**
- Phase 2 frontend: SHIPPED + ALIGNED — Assessment tab below Risk/Match/Proof
  with optional role-context textarea and structured-report view. `api.ts` now
  sends `original_text` to match the server-side re-derive shift.
- Phase 3: SHIPPED + REVIEWED — SQLAlchemy 2.x + Alembic skeleton with optional
  persistence (`DATABASE_URL` unset → Phase-1/2 behaviour unchanged); `/scan-cv`
  persists + returns `scan_id` (UUID); `/assessment` accepts EITHER `cv_text` OR
  `scan_id` (XOR-validated) and persists results with `scan_id` FK + `provider_used`
  audit field. Privacy invariant: `original_text` is never written; only the
  scrubbed `safe_copy_text` is stored, capped at 64 KB per row. Driver:
  psycopg2-binary; tests use SQLite via StaticPool. End-of-phase Codex review (P4)
  returned HIGH=0 MED=2 LOW=2; all four closed in `4a108f2` (DB read txn released
  before LLM call; safe_copy_text/summary capped at 64 KB; `/trust-report` calls
  `scan_cv` with `persist=False`; validator now rejects "both present").
  **198 tests; bandit 0; semgrep 0; tsc clean; vite clean.**
- Phase 4: SHIPPED + REVIEWED — Clerk JWT verification (`backend/auth.py`,
  PyJWKClient + RS256), `user_id` columns added to scans/assessments via
  migration 0002, `/scan-cv` + `/trust-report` + `/assessment` honour the
  authenticated caller (anonymous flow preserved with zero persistence), new
  `GET /scans` per-user history endpoint, frontend ClerkProvider with
  SignedIn/SignedOut UI and a HistoryView panel that fetches /scans for the
  signed-in recruiter. Cross-tenant scoping verified by
  `test_assessment_other_users_scan_id_returns_404` and
  `test_scans_returns_only_caller_own_scans`. End-of-phase Codex review (P5)
  returned HIGH=0 MED=0 LOW=0 — no fix commits needed.
  **223 tests; bandit 0; semgrep 0; tsc clean; vite clean (210 KB JS / 61 KB gzip).**
- Phases 5-8: pending Bhanu sign-off on Phase 4.

### Phase 4 answers from Bhanu (2026-05-31)
1. **Auth provider** — Clerk (faster integration, free tier, better DX than
   Supabase Auth).
2. **Multi-tenancy** — per-user only for now. Firm-level sharing is Phase 5.
3. **scan_id on frontend** — yes, "recent scans" history list landed
   (HistoryView component above the file upload, only visible while signed in).

### Phase 3 answers from Bhanu (2026-05-31)
1. **DATABASE_URL** — Neon free tier; driver choice mine → psycopg2-binary +
   SQLAlchemy 2.x sync sessions (boring; matches existing sync endpoints).
2. **original_text** — never store. safe_copy_text only. Re-upload to re-scan.
3. **scan_id** — UUID, exposed in /scan-cv response. No sequential integers.

### Phase 2 answers from Bhanu (2026-05-30)

1. **Experience tiers** — keep the existing 4 tiers (Entry / Mid-level / Senior /
   Principal-Lead). Don't map to HireIQ's 3. Role detection added later as a
   separate signal, not a tier replacement.
2. **Proprietary scoring** — don't wait; build ProofHire v1 (copying HireIQ's
   rubric carries legal risk). Label the framework explicitly in output as
   "ProofHire v1 — heuristic scoring".
3. **API key strategy** — env var locally + HF Spaces Secret on deploy. AWS
   Secrets Manager deferred to a later phase (no compliance trigger yet).
4. **Phase 2 width** — `/assessment` endpoint alone. DB is its own slice (Phase 3).
