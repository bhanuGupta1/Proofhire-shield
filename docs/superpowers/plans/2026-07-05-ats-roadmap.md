# ProofHire Shield — Platform Roadmap

> **Goal:** Evolve ProofHire Shield from a single-CV scanner into a full
> candidate-intelligence recruiting platform, while keeping its unique
> security layer (hidden-instruction detection, PII flagging, Safe CV Copy,
> Trust Report) as the foundation every candidate record is built on.

**Positioning:** Every other recruiting tool trusts the CV. ProofHire treats
each CV as untrusted input first — scans it, produces a defensible audit
record — *then* turns it into a candidate you can pipeline, match, and report
on. Security is not a feature bolted on; it is the front door.

## Current state (start of this roadmap)

- **Backend:** FastAPI single-file `main.py`, SQLAlchemy 2 + Alembic, pytest
  (SQLite fixtures). Entities: `Scan`, `Assessment`, billing tables. Clerk
  `user_id` / `org_id` scoping already present on every row.
- **Frontend:** React 18 + TS + Vite + Tailwind + Clerk. Single tabbed page
  (Risk / Match / Proof / Assessment) around one uploaded file. **No router.**
- **Security engine:** regex-based, zero-LLM, offline. `scanner.py`,
  `safe_copy.py`, `trust_report.py`, `match_analysis.py`, `assessment.py`.

## Architectural principles for the platform build

1. **Scan-anchored.** A candidate is created *from* a scan. The scan id is the
   audit anchor; the candidate row references it. We never lose the security
   provenance of how a candidate entered the system.
2. **Modularise as we grow.** `main.py` is 52 KB. New surface areas go in their
   own routers (`routers/candidates.py`, `routers/jobs.py`, …) mounted on the
   app, not appended to `main.py`. Existing endpoints stay put until touched.
3. **Every row is tenant-scoped.** `user_id` + `org_id` on every new table,
   same nullable pattern as `Scan`. Org members share; solo users are private.
4. **TDD, small commits.** Every model, endpoint, and component lands with a
   failing test first, then the minimal implementation, then a commit. One
   logical change per commit.
5. **Reuse the security spine.** Match, assessment, reports all build on the
   existing scan/assessment engines — no parallel re-implementation.

## Tech decisions locked for the platform

- **Routing (frontend):** add `react-router-dom` v6. Multi-page is certain, not
  speculative — a state-machine nav would be re-torn-out within one phase.
- **App shell:** sidebar + topbar replace the single-page header. The current
  scan tabs become the Candidate Detail view.
- **Semantic matching (Phase 3):** `pgvector` on Postgres for candidate↔job
  similarity, with a deterministic fallback (existing regex match) when no
  embedding provider is configured — mirrors the AI/Fast toggle already in
  match analysis.
- **No new heavyweight deps** without a clear need. `sentence-transformers` or a
  hosted embedding API decided at Phase 3, not before.

---

## Phases (dependency order)

### Phase 1 — Candidate & Job foundation  ← **detailed plan below**
The backbone. Persist scans as candidates; add jobs/reqs; multi-page app shell.
- **DB:** `candidates`, `jobs`. `candidates.scan_id` → `scans.id`.
- **API:** candidate CRUD + "promote scan to candidate"; job CRUD.
- **UI:** `react-router-dom`, AppShell (sidebar/topbar), Candidates list,
  Candidate detail (existing scan tabs embedded), Jobs list, Job detail.
- **Ships:** you can scan a CV, save it as a candidate, list candidates, create
  jobs — a real ATS spine.

### Phase 2 — Pipeline & Shortlists
Move candidates through hiring stages; shortlist candidates per job.
- **DB:** `pipeline_stages` (per job, ordered), `candidate_stage`
  (candidate↔job placement + stage), `shortlists`.
- **API:** create/reorder stages, move candidate to stage, add/remove from
  shortlist, list a job's pipeline board.
- **UI:** Pipeline board (columns = stages, cards = candidates, drag to move),
  Shortlist panel on Job detail.
- **Ships:** a working Kanban hiring funnel.

### Phase 3 — Matching engine upgrade (semantic)
Auto-match candidates to jobs and free-text talent search.
- **DB:** `candidate_embeddings`, `job_embeddings` (pgvector; nullable, built
  on demand). Deterministic fallback when no embedding provider configured.
- **API:** `POST /jobs/{id}/auto-match` (rank candidates), `POST /talent/search`
  (NL query → ranked candidates), embedding backfill job.
- **UI:** "Top candidates" panel on Job detail, Talent Search page.
- **Ships:** "find me candidates like this job" and "search my talent pool."

### Phase 4 — Dashboard, Today & Reports
Recruiter home + client/ROI reporting on top of existing scan/assessment data.
- **DB:** `outcomes` (hire/reject/withdrawn per candidate↔job), `reports`.
- **API:** `/dashboard` metrics (funnel, throughput, risk stats), `/today`
  (actionable queue), `/reports` generate + PDF (reuse `trust_report` PDF stack).
- **UI:** Dashboard (charts), Today view, Report builder + export.
- **Ships:** metrics leadership trusts + exportable client reports.

### Phase 5 — Clients & sharing
Client records and shareable candidate views.
- **DB:** `clients`, `client_shares` (scoped, expiring links).
- **API:** client CRUD, create share link, public read-only share endpoint.
- **UI:** Clients page, Share dialog on Candidate/Shortlist.
- **Ships:** send a client a shortlist without giving them a login.

### Phase 6 — Comms & Notifications
Follow-up and in-app notifications.
- **DB:** `notifications`, `outreach_messages`.
- **API:** notification list/mark-read, generate follow-up draft (LLM, reuse
  assessment provider plumbing), log outreach.
- **UI:** Notification bell + panel, Follow-up composer on Candidate detail.
- **Ships:** never lose track of who needs a reply.

### Phase 7 — Platform polish
Command palette, settings, admin, audit log, consent.
- **DB:** `audit_log` (append-only), `settings`.
- **API:** settings CRUD, audit query, admin (org/user management).
- **UI:** Command palette (Cmd-K), Settings hub, Admin panel, Consent banner,
  Breadcrumbs.
- **Ships:** the product feels complete and governable.

### Phase 8 — External ATS import
Generic import so candidates/jobs can arrive from an external system.
- **DB:** `import_sources`, `import_runs`.
- **API:** generic CSV/JSON candidate + job import with dedupe; pluggable
  connector interface (no vendor lock-in in the core).
- **UI:** Import wizard, mapping UI, run history.
- **Ships:** onboard an existing book of candidates.

---

## Cross-cutting requirements (every phase)

- **Copy/branding:** product is **ProofHire Shield**. No other product names in
  code, comments, docs, commits, seed data, or fixtures.
- **Security provenance preserved:** any candidate created from a CV carries its
  `scan_id`; the Risk tab is always reachable from the candidate.
- **Tenant isolation:** every query filters by `user_id`/`org_id`; add a test
  proving cross-tenant reads are blocked for each new list/detail endpoint.
- **Tests prove behavior:** each endpoint gets happy-path + auth/tenant + one
  edge case. Frontend gets at least a render/interaction test where a testing
  setup exists.
- **Migrations:** every schema change is an Alembic migration with a downgrade.

---

## Phase 1 — detailed task plan

**Goal:** Persist scans as candidates, add jobs, and turn the single-page tool
into a multi-page app shell.

**Architecture:** New Alembic models `Candidate` and `Job`. New FastAPI routers
`routers/candidates.py` and `routers/jobs.py` mounted in `main.py`. Frontend
gains `react-router-dom`, an `AppShell`, and pages for Candidates and Jobs; the
existing scan tabs become the Candidate Detail body.

### Global constraints
- Python 3.11, FastAPI, SQLAlchemy 2, Alembic, pytest (SQLite test fixtures).
- Frontend React 18 + TS + Vite + Tailwind + Clerk; add `react-router-dom@^6`.
- Every new table has `id` (UUID), `user_id` (String(64), nullable, indexed),
  `org_id` (String(64), nullable, indexed), `created_at`, `updated_at`.
- Auth: reuse existing Clerk JWT dependency from `auth.py`
  (`get_current_user` / whatever `main.py` uses). Tenant filter on every query.
- No product name other than "ProofHire Shield" anywhere.

### Task 1 — `Candidate` + `Job` models
- **Files:** `backend/db_models.py` (add classes), `backend/migrations/versions/`
  (new migration), `tests/test_db.py` (extend).
- `Candidate`: `id`, `user_id`, `org_id`, `scan_id` (FK→scans.id, nullable,
  SET NULL on delete — a candidate outlives a deleted scan but records it),
  `full_name`, `email`, `phone`, `headline`, `location`, `source` (String(32),
  default 'scan'), `status` (String(24), default 'new'), `notes` (Text, nullable),
  `tags` (JSON, default list), `created_at`, `updated_at`.
- `Job`: `id`, `user_id`, `org_id`, `title`, `client_name` (nullable),
  `location`, `employment_type` (nullable), `seniority` (nullable),
  `description` (Text), `required_skills` (JSON, default list),
  `status` (String(24), default 'open'), `created_at`, `updated_at`.
- **TDD:** test that both tables create, insert, and round-trip JSON columns on
  SQLite; test `scan_id` SET NULL behavior.

### Task 2 — Candidates router (CRUD + promote-from-scan)
- **Files:** `backend/routers/__init__.py`, `backend/routers/candidates.py`,
  mount in `backend/main.py`, `tests/test_candidates.py`.
- Endpoints (all tenant-scoped, auth required):
  - `POST /candidates` — create from body **or** from `scan_id` (promotes a
    scan: copies name/email/phone the match analysis already extracted).
  - `GET /candidates` — list current tenant's candidates (paginated, filter by
    `status`, `q` name search).
  - `GET /candidates/{id}` — detail incl. linked scan summary if present.
  - `PATCH /candidates/{id}` — update editable fields.
  - `DELETE /candidates/{id}`.
- **TDD:** happy path each; cross-tenant read returns 404; promote-from-scan
  copies extracted fields; unauth returns 401.

### Task 3 — Jobs router (CRUD)
- **Files:** `backend/routers/jobs.py`, mount in `main.py`, `tests/test_jobs.py`.
- Endpoints mirror candidates: `POST/GET/GET{id}/PATCH/DELETE /jobs`.
- **TDD:** happy path, cross-tenant isolation, unauth.

### Task 4 — Frontend routing + AppShell
- **Files:** add `react-router-dom`; `frontend/src/components/AppShell.tsx`,
  `frontend/src/App.tsx` (convert to router), `frontend/src/lib/api.ts`
  (add candidate/job fns + types).
- AppShell: left sidebar (Scan, Candidates, Jobs, [later: Pipeline, Talent,
  Dashboard]), topbar with Clerk user button + quota. Routes:
  - `/` → Scan (existing upload + tabs, now "New Scan")
  - `/candidates`, `/candidates/:id`
  - `/jobs`, `/jobs/:id`
- Keep existing scan/tab components; Candidate Detail reuses Risk/Match/Proof/
  Assessment tabs pointed at the candidate's linked scan.

### Task 5 — Candidates pages
- **Files:** `frontend/src/pages/CandidatesList.tsx`,
  `frontend/src/pages/CandidateDetail.tsx`.
- List: table (name, headline, status, risk badge from linked scan, created),
  search box, status filter, row → detail. Empty state.
- Detail: header (name/contact/status editable), "Save to pipeline" placeholder
  (Phase 2), tabbed scan body reused from existing tabs.
- "Save as candidate" button added to the Scan result view (calls
  `POST /candidates` with `scan_id`).

### Task 6 — Jobs pages
- **Files:** `frontend/src/pages/JobsList.tsx`, `frontend/src/pages/JobDetail.tsx`,
  `frontend/src/pages/JobForm.tsx` (create/edit).
- List: table (title, client, location, status, created), "New job" button.
- Detail: job fields, required skills chips, [Phase 2 pipeline / Phase 3
  matches placeholders].

### Phase 1 done =
Scan a CV → "Save as candidate" → it appears in Candidates → create a Job →
navigate the whole thing through a real sidebar. All tenant-scoped, all tested.

---

## After Phase 8
Re-plan from real usage: bulk actions, interview scheduling, calendar sync,
analytics deep-dives, mobile. Written when we get there, from evidence.
