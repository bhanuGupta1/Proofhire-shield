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

### Phase 6 — AWS migration (SKIPPED 2026-06-01)
Skipped per Bhanu: no budget for paid infra until there is a revenue signal.
Stack stays HF Spaces (backend) + Cloudflare Pages (frontend) + Neon Postgres.
Original sketch retained below for the day a revenue signal arrives:
- ECS / Fargate (or Lambda if footprint stays small).
- RDS Postgres (Aurora Serverless v2 if usage is spiky).
- Secrets Manager for `ANTHROPIC_API_KEY` and DB URL.
- CloudFront in front of Cloudflare Pages, or move frontend hosting too.

### Phase 7 — Monetisation (Stripe-gated Pro) — re-scoped 2026-06-01
Original Phase 7 ("Production hardening + observability") deferred. The
revenue-first re-scope: three-tier billing model, Stripe Checkout, Stripe
Customer Portal, signature-verified webhook.

Tiers:
- **Anonymous**: unlimited stateless scans, no history, no Assessment. Unchanged
  from today (zero-friction demo path).
- **Free** (signed-in): 10 persisted scans per calendar month UTC, full history
  of those, no Assessment. Hard 402 at the 11th scan with an "Upgrade to Pro"
  message.
- **Pro** (signed-in + active Stripe subscription): unlimited scans, full
  history, Assessment unlocked. $29 / month, per-user (org-level Pro deferred).

Org policy (settled with Bhanu): "view-everything" — if a Pro org member
generated an Assessment, free org-mates see it via the existing
`or_(user_id, org_id)` scope. Pro is a generation gate, not a viewing gate.

Surface:
- Schema: `subscriptions(user_id PK, stripe_customer_id, stripe_subscription_id,
  plan, status, current_period_end, created_at, updated_at)` + migration 0004.
- Helpers: `is_pro(user_id, db)` and `scans_used_this_month(user_id, db)` — both
  computed via existing indexes, no counter table.
- New endpoints: `POST /billing/checkout-session`, `POST /billing/portal`,
  `GET /billing/status`, `POST /billing/webhook` (signature-verified).
- New dep: `stripe` Python SDK. `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
  `STRIPE_PRICE_ID_PRO` env vars. Frontend reads `VITE_STRIPE_PUBLISHABLE_KEY`.
- Backwards compat: if Stripe envs are unset, billing endpoints return 503 and
  the quota gate degrades open (Phase-4/5 behaviour preserved).
- HIGH-RISK path (per CLAUDE.md §3): `/billing/webhook`. Signature verification
  + idempotency on `event.id` are non-negotiable.

Closed 2026-06-01 (7.1–7.7):
- 7.1 (`a3121dc`) `subscriptions` model + `is_pro` / `scans_used_this_month` helpers + migration 0004.
- 7.2 (`df641c7`) `/scan-cv` free-tier 402 gate (the 11th scan in a UTC calendar month).
- 7.3 (`5d239e6`) `/assessment` Pro gate (initial cut — kept anonymous demo path).
- 7.4 (`5115760`) `/billing/checkout-session` + `/billing/portal` + `/billing/status`.
- 7.5 (`20a37ff`) `/billing/webhook` — Stripe signature verification + `webhook_events`
  idempotency ledger + migration 0005.
- 7.6 (`8b3f27b`) Frontend — pricing modal, quota meter, Pro gates, upgrade CTA.
- 7.7 (`6a3f7cb`) End-of-phase Codex P7 adversarial review + hardening. **Round 1**
  HIGH=3 MED=2 LOW=1 — all six closed in `6a3f7cb` (persist param removed from
  `/scan-cv`; `/trust-report` now persists and counts toward the quota;
  `/assessment` requires auth so dropping the Authorization header no longer
  bypasses the gate; new `last_event_at` column + migration 0006 + the webhook
  drops events older than the row's last applied; customer-id collision under
  a different user is refused; webhook commit catches `IntegrityError` and
  returns duplicate 2xx). **Round 2** on the post-fix source: **HIGH=0** MED=1
  LOW=1 — the LOW (oversized webhook body + noisy log) is closed in the same
  commit (256 KB cap on `/billing/webhook`; signature warning no longer carries
  `exc_info`). The MED is documented below as a Phase 8 follow-up.

Deferred to Phase 8 (Codex P7 round-2 MED #1): free-tier scan quota is a
check-then-write read of `COUNT(*)`, so a determined attacker firing
concurrent `/scan-cv` requests at a 9-of-10 quota can race past the cap by
a few scans before the rows commit. Bounded (each rogue scan still writes a
row, so the next request is gated correctly) and not exploitable for
unlimited free use. The proper fix is a `(user_id, utc_month, count)`
counter row with `SELECT FOR UPDATE` or `INSERT ... ON CONFLICT DO UPDATE`,
which belongs with the Phase 8 rate-limit + observability work.

As-built deltas from the plan above: the price-id env var shipped as `STRIPE_PRICE_ID`
(not `STRIPE_PRICE_ID_PRO`); the frontend uses Stripe-hosted Checkout (redirect to the
returned URL), so no `VITE_STRIPE_PUBLISHABLE_KEY` / Stripe.js is needed client-side.
After Phase 7.7, `/assessment` requires Clerk auth — the Phase-7 spec table
("Anonymous: no Assessment") is now actually enforced, so the public demo URL
shows Risk/Match/Proof only; Assessment is the upgrade carrot.

### Phase 8 — Production hardening + observability + Recruiter co-pilot
Promoted from "original Phase 7 + original Phase 8" — once Phase 7 is producing
revenue, observability and the co-pilot follow. Specifics deferred until
Phase 7 close.

## Architecture decisions (provisional)

- **Continue this repo** — don't fork. The security scanner is reusable as the
  ingestion layer; HireIQ-style assessment sits on top.
- **React + FastAPI** stay the stack.
- **LLM default: Claude API** (per Bhanu's HireIQ build).
- **DB**: defer to Phase 3; Postgres-on-Neon to start, Postgres-on-RDS at AWS.
- **Hosting**: HF Spaces + Cloudflare Pages indefinitely (Phase 6 AWS migration
  skipped 2026-06-01). Neon Postgres remains the Phase-3 DB.
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
- Phase 5: SHIPPED — firm/organisation multi-tenancy via Clerk Organizations
  (re-scoped from the original "multi-framework scoring engine" plan per the
  Phase-4 answer #2; the scoring engine is deferred to a later phase). `org_id`
  columns added to scans/assessments with Clerk org-extraction dependencies
  (`get_current_org_optional` reads the `org_id` claim); `/scan-cv`, `/scans`,
  and `/assessment` stamp `org_id` and scope visibility by
  `or_(user_id == caller, org_id == active_org)`, falling back to user-only when
  no org is active; new `GET /scans/{id}` returns one scan's full detail under the
  same user+org scope and 404s (never 403 / existence-leak) on a cross-tenant
  miss. Frontend: `OrganizationSwitcher` in the header with HistoryView refetch
  on org switch, and clicking a saved scan rehydrates every tab
  (Risk/Match/Proof/Assessment) from `GET /scans/{id}` — Proof's PDF re-download
  is disabled for history-loaded scans, which carry no uploaded File. Privacy
  invariant intact: `original_text` is still never persisted; the detail endpoint
  echoes `safe_copy_text`. End-of-phase Codex review (P6) returned
  **HIGH=0 MED=0 LOW=0** — no fix commits needed; reviewer confirmed
  `org_id` derives only from the verified token claim, list + detail + assessment
  paths share the same scoped predicate, and the no-org branch stays narrowed to
  `user_id == current_user`. **243 tests; bandit 0 HIGH/MED (1 pre-existing LOW);
  tsc clean; vite build clean (210 KB JS / 61 KB gzip).** semgrep was not run
  locally (the pipx semgrep on Windows crashes on rule-pack download with
  `UnicodeDecodeError`); CI runs bandit only, which stays the enforced gate.
- Phase 6: **SKIPPED** (2026-06-01) — no budget for paid infra. Stack stays
  HF Spaces + Cloudflare Pages + Neon. Re-evaluate when a revenue signal arrives.
- Phase 7: **COMPLETE + REVIEWED** (2026-06-01) — re-scoped from observability to
  Stripe-gated monetisation. 7.1–7.7 shipped (commits a3121dc, df641c7, 5d239e6,
  5115760, 20a37ff, 8b3f27b, 6a3f7cb). End-of-phase Codex P7 round 1 returned
  HIGH=3 MED=2 LOW=1 — all six closed in `6a3f7cb`. Round 2 on the hardened
  source: **HIGH=0** MED=1 LOW=1; LOW closed in the same commit; MED (concurrent
  quota TOCTOU) deferred to Phase 8 with rationale (see "Deferred" block under
  Phase 7 above). **320 tests; bandit 0 HIGH/MED (1 pre-existing LOW); tsc
  clean; vite build clean.** Tier rules + Bhanu's answers recorded below.
- Phase 8: pending Phase 7 close. Promoted to the original Phase 7 + 8 contents
  (hardening + observability + recruiter co-pilot).

### Phase 7 answers from Bhanu (2026-06-01)
1. **Pro scope** — per-user for v1. Org-level Pro deferred (a candidate Phase 7.5
   or Phase 8 slice).
2. **Price** — $29 / month (single tier).
3. **Org policy** — "view-everything": a Pro-generated Assessment is visible to
   free org-mates via the existing org-scoped `or_(user_id, org_id)` filter. Pro
   gates GENERATION (and direct access for non-org-shared scans), not viewing
   of already-shared content.
4. **Free-tier enforcement** — hard 402 at the 11th scan in a calendar month
   (UTC). No soft nag.
5. **Anonymous behaviour** — unchanged from Phase 5: unlimited stateless scans,
   no history, no Assessment. The zero-friction demo path is preserved.

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
