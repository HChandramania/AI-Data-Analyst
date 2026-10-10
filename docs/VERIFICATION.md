# Verification record

## Phase 1 — 2026-10-10

Windows/PowerShell, Python 3.13, Node 24. Phase 0 results below are historical; current Phase 1 checks are listed here.

| Check | Result |
| --- | --- |
| `uv run --frozen pytest -q --basetemp=.pytest_tmp` (`backend`) | 21 passed; one Starlette/httpx deprecation warning |
| `uv run --frozen ruff check .` and `uv run --frozen ruff format --check .` (`backend`) | Passed |
| `uv run --frozen alembic check` against disposable `.phase1-smoke` storage | No new upgrade operations detected |
| `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build` (`frontend`) | Passed after route regeneration and cleanup of stale generated route type |
| `uv run --frozen python ../docs/smoke_phase1.py` (`backend`) | Passed through live Next.js proxy: anonymous workspace redirect, register, authenticated workspace access, current user, three sample uploads, list/detail/preview, logout, access denied and workspace redirect |
| Integrated browser | Could not connect: browser tool rejected its own sandbox metadata before opening a tab. Visual/mobile interaction gate remains unverified. |

Tests cover session expiry/revocation, cookie flags, origin/CSRF checks, login throttling, anonymous and cross-owner denial, mixed batch results, malformed/invalid CSV, rows/columns/file size, leading-zero text, ambiguous date warnings, nulls, duplicate counts, Parquet integrity, deletion, and recovery after rejected uploads. The proxy smoke also checks that logout forwards two Set-Cookie headers. Upload streaming enforces each file's cap before writing additional bytes to disk.

Docker Engine 29.1.2: disposable `dbo-phase1-check` and final `dbo-phase1-final` Compose builds passed with ports 3101/8101 and `DBO_PUBLIC_ORIGIN=http://localhost:3101`. Migration exited 0; backend/frontend became healthy. The three-file proxy smoke passed against port 3101 on both runs. Dataset metadata and Parquet snapshot counts were 3/3 after backend restart. Both projects were removed with `docker compose -p <test-project> down --volumes`, affecting only their dedicated containers, networks, and volumes. No Phase 2 capability is implemented.

## Phase 0 verification

Verified on 2026-10-09, Windows/PowerShell, Python 3.13.15, uv 0.11.26, Node 24.18.0. Commands below are actual runs, not forecasts.

## Passed

| Working directory | Exact command | Result |
| --- | --- | --- |
| `backend` | `uv lock --cache-dir .uv-cache` | Dependency lock generated |
| `backend` | `uv sync --frozen --cache-dir .uv-cache` | Locked dependencies installed |
| `backend` | `.venv\Scripts\python.exe -m pytest -q` | 9 passed (rerun with access to system temp after sandbox denial) |
| `backend` | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .verification/pytest-envelope` | Final API-envelope version: 9 passed; local temporary directory |
| `backend` | `.venv\Scripts\ruff.exe check .` | Passed |
| `backend` | `.venv\Scripts\ruff.exe format --check .` | Passed on final backend; 9 files formatted |
| `backend` | `.venv\Scripts\python.exe -m alembic upgrade head` | Fresh local metadata migrated |
| `backend` | `.venv\Scripts\python.exe -m alembic check` | No new upgrade operations detected |
| `backend` | `.venv\Scripts\python.exe -m app.serve` | Actual local server started |
| Root | `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/live` | HTTP 200, `alive`, request ID |
| Root | `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready` | HTTP 200, `ready`, request ID |
| Root | `Invoke-RestMethod http://127.0.0.1:3000/api/v1/health/ready` | HTTP 200 through Next.js proxy |
| Root | `(Invoke-WebRequest http://127.0.0.1:3000/analyze -UseBasicParsing).StatusCode` | HTTP 200 |
| Root | `python sample_data/verify.py` | All expected-answer groups match; decimal arithmetic, joins, IQR and data-quality checks |
| Root | `docker compose config --quiet` | Passed; sandbox emitted Docker config-access warnings |
| `frontend` | `npm.cmd audit --omit=dev --cache .npm-cache` | 0 production vulnerabilities |
| `frontend` | `npm.cmd ci --cache .npm-cache` | Clean locked install passed, with documented development audit findings |
| `frontend` | `npm.cmd run lint` | Passed with zero warnings after clean install |
| `frontend` | `npm.cmd run typecheck` | Route generation and TypeScript passed after clean install |
| `frontend` | `npm.cmd run build` | Final production build and standalone static-asset preparation passed |
| `frontend` | `npm.cmd exec -- eslint scripts/start.mjs --max-warnings=0` | Final local launcher passed lint |
| `frontend` | `npm.cmd run start` | Standalone production server started successfully |
| `frontend` | `npm.cmd run dev` | Development server started; Analyze and same-origin readiness both returned HTTP 200 |
| Root | `python docs/smoke_http.py --expect-unavailable` | With backend stopped: Analyze HTML, all referenced static assets, sanitized proxy 503, and unknown-probe 404 passed |
| Root | `python docs/smoke_http.py` | After backend restart: Analyze HTML/assets, real proxy readiness, matching request ID, no-store, and unknown-probe 404 passed |

Tests cover liveness without storage, no implicit migrations, idempotent migration setup, readiness and engine restart, missing schema columns, unwritable storage, missing migration table, invalid settings, unique request IDs, sanitized 404/405/422/500 errors/logs, foreign keys/WAL, persisted User/Session records, cascading deletion, and rejection of non-digest session values. Test endpoints exist only inside tests.

## Docker runtime verification

Verified on 2026-10-09 with Docker Engine 29.1.2 (`linux/amd64`) using the isolated Compose project `dbo-phase0-runtime`, host ports 18000/13000, and a disposable named volume. The project and volume were removed after verification with `docker compose -p dbo-phase0-runtime down --volumes --remove-orphans`.

| Gate | Result |
| --- | --- |
| Clean image build and startup | Passed after regenerating the frontend lockfile in the Linux Node image; all services started with `docker compose up --build -d --wait` |
| Migration ordering | Passed; `migrate` exited 0 before `backend` became healthy, and `backend` depends on `migrate` with `service_completed_successfully` |
| Backend direct readiness | Passed; `http://127.0.0.1:18000/api/v1/health/ready` returned HTTP 200 and phase 0 ready envelope |
| Frontend same-origin proxy | Passed; `http://127.0.0.1:13000/api/v1/health/ready` returned HTTP 200 and phase 0 ready envelope |
| Non-root application processes | Passed; backend container user was `10001:10001`, frontend container user was `node` |
| Required storage write | Passed; backend, running as UID/GID 10001, created `/app/data/phase0-marker` |
| Persistence across recreation | Passed; after `docker compose down` without `--volumes` and a new `up -d --wait`, the marker remained readable |
| Disposable cleanup | Passed; containers, network, and `dbo-phase0-runtime_backend_data` were removed |

The first clean build exposed a confirmed lockfile defect: Linux `npm ci` reported missing `@emnapi/runtime` and `@emnapi/core` entries, and subsequent builds reported omitted platform optional packages. `frontend/package-lock.json` was regenerated inside the same Linux Node image used by the Dockerfile, after which the clean image build passed. No application behavior was changed.

## Browser verification

Verified on 2026-10-09 with the integrated browser against a local backend and Next.js development server:

| View / interaction | Result |
| --- | --- |
| Desktop viewport (1440 px) | Passed; essential content and controls reachable, no page-level horizontal overflow |
| Mobile viewport (390 px) | Passed; single-column layout remains reachable, no page-level horizontal overflow |
| Keyboard navigation | Passed; links and the connection control receive focus with a visible outline; skip link is reachable |
| Loading state | Passed; availability region announces “Checking service availability…” and disables the check control |
| Ready state | Passed; availability region announces “Backend connected · storage ready” |
| Empty state | Passed; the workspace explicitly states that no datasets are loaded and that upload is not available yet |
| Backend unavailable state | Passed; safe “Service unavailable” message and persistent “Try again” action are rendered |
| Retry affordance | Passed as a rendered recovery control; a fresh probe after backend restoration returned to the ready state |

The browser console reported expected Next.js development HMR connection noise when using the local development server; it did not affect page content, health probing, or the layout checks above.

## Blocked / not verified

- Browser verification at 200% zoom, reduced-motion mode, and a physical mobile device remains unverified. The integrated browser covered desktop/mobile viewport layout, keyboard focus, loading, ready, empty, unavailable, and retry affordances as recorded above. HTTP/production-build checks do not substitute for these.
- GitHub Actions is configured but has not been run remotely. The folder currently belongs to a parent Git repository; no separate Git repository was initialized, and no commit/push was made. The workflow will apply when this project is used as the repository root.

## Dependency and environment notes

- Full `npm.cmd audit --json --cache .npm-cache` reported five high-severity development-only findings in `braces` → `micromatch` → `fast-glob` → Next's lint plugin/config. The registry's latest `braces` was 3.0.3, still affected. No arbitrary major downgrade or forced audit fix was applied. Production audit is clean. Recheck the [upstream advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) when updating lint tooling.
- ESLint 9.39.5 is marked unsupported upstream but satisfies the React/import/accessibility lint plugins' current peer ranges. ESLint 10 was evaluated and rejected because those plugins did not declare compatibility. This is a development-tool limitation.
- Starlette emits a deprecation warning for its HTTPX test-client compatibility layer. The tests pass; no provider dependency or fake production response is involved.
- Initial pytest failed on sandbox access to its shared temp directory; a permitted rerun passed. A later explicit local-temp invocation initially missed its parent directory; creating the ignored `.verification` parent resolved that setup error. These were test-environment failures, not silently counted as passes.
- Initial frontend lint detected an anonymous default export; it was fixed. A clean-install dry run exposed a transitive lock inconsistency; the lock was reconciled. Docker runtime verification then exposed omitted Linux optional packages in the lockfile; the lock was regenerated in the Linux Node build environment and the clean Docker build passed. The subsequent frontend lint/typecheck/build passed. `next start` initially warned about standalone output; the documented launcher now uses the built standalone server and copies static assets during build.

Phase 0 is **accepted**. Authentication and every analysis feature remain out of scope and unimplemented.

Local verification servers were stopped after the smoke checks. Next.js's generated agent-rules file was removed and automatic generation disabled (`agentRules: false`); the user's root instructions are preserved.
