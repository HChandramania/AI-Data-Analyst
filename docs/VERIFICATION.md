# Configurable join trees (2026-10-15)

New analysis selections support five datasets/four edges. Uploads still allow ten files. `JoinKey` accepts explicit dataset/column/type names plus legacy fields; saved proposals keep legacy serialization. `validate_keys` derives a directed rooted execution order from unordered edges and rejects unknown/self sources, duplicate/parallel edges, cycles, disconnected graphs, multiple parents, and missing/incompatible columns. Integer/decimal equality is compatible. Edge orientation is preserved, including LEFT joins; conflicting directions require user correction. Existing saved analyses and dashboard artifacts need no migration; the planner schema retains its earlier larger-source capacity for saved workflows.

Analyze reuses the existing editor/review styling with add/remove controls, both endpoint selectors, summaries and local errors. Edits revoke prior confirmation. Backend-authorized datasets are rechecked, validated ordered edges are passed to planning, and SQL must match the exact ordered source/key/type tree. Two or more expanding edges trigger a conservative fanout warning. Existing multiplication consent gates execution; results and method explicitly warn that consent does not correct inflated aggregates. No automatic aggregation rewrite or final multi-hop cardinality estimate is provided.

Targeted: `pytest tests/test_join_graph.py -q --tb=short --basetemp=.verification/join-graph-targeted-20261015` ? 11 passed. Regression: `pytest tests/test_join_graph.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_planner_columns.py -q --tb=short --basetemp=.verification/join-graph-regression-20261015` ? 107 passed. Both runs reported one existing Starlette/httpx deprecation warning. Cases cover chains, branches, execution order, aliases/legacy saved proposals, invalid mappings/types, unauthorized/unselected sources, duplicate/parallel edges, disconnection/cycles, unsupported joins, fanout consent and five-source Olist-style SQL enforcement. Synthetic orders/items/payments produce four joined rows and a repeated item sum of 60 versus the original item total of 30; this deliberately demonstrates fanout, not corrected aggregation. A saved dashboard using a legacy-format proposal reopens successfully.

Backend lint, targeted frontend lint, frontend typecheck and production build passed. Browser interaction and live LLM generation for the five-source graph remain unverified. Tests use explicit provider doubles and small synthetic fixtures, not the full Olist data. No user analyses were deleted or rewritten.

# Olist upload capacity (2026-10-15)

Raised upload limits to 64 MiB/file, 1,100,000 rows/file, 256 MiB/request; retained ten files and 50 columns. Updated backend receiver/middleware, frontend proxy/body buffering, displayed limits and documentation. Upload backend deadline is 180 seconds; frontend upstream deadline is 210 seconds. XLSX expansion remains capped at 64 MiB.

Read-only validation of all nine actual `olist-data` CSVs through `inspect_csv` passed in 14.64 seconds total; geolocation contained 1,000,163 rows and took 9.04 seconds locally. No real dataset records or credentials were logged. This validates CSV parsing, not browser batch transfer or large-query performance. Intake tests passed 16/16; oversized-file/row rejection is exercised with reduced thresholds to avoid large synthetic allocations. Lint passed. Large-file profiling and proxy request buffering increase memory use; full-size concurrent stress testing remains unverified.

# Ten-file upload and ten-dataset analysis limits (2026-10-15)

Updated upload file counts, multipart caps, frontend proxy/body buffering, analysis/dashboard selection, plan schemas, join relationship limits, and semantic-search source eligibility. Ten files retain 10 MiB each with a 102 MiB request cap. Resource/deadline and 32,000-character schema-context caps remain enforced.

Verification: `pytest tests/test_phase1.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_provider_fallback.py tests/test_planner_columns.py -q --tb=short --basetemp=.verification/ten-dataset-limit-20261015` passed 112 tests (one existing dependency deprecation warning). Added ten-file upload and eleven-file rejection/cleanup coverage; extended confirmed multi-source execution to ten datasets with expected total 121, search indexing/retrieval, and rejection of eleven selected datasets. Backend lint, targeted frontend lint, typecheck and production build passed. Full-size ten-file stress testing, live-model ten-source planning and browser acceptance remain unverified.

# Verification record

## Formatted monthly line chart fix — 2026-10-13

Latest completed local evidence confirmed `month: VARCHAR`, numeric revenue, explicit `chart.period: month` and chart error "Line requires a temporal or numeric x-axis." Computation succeeded; formatting SQL returned text rather than a DATE/TIMESTAMP. Added strict ISO-text line support with declared cadence: YYYY-MM/month and YYYY/year normalize chart coordinates to first day, or accept valid YYYY-MM-DD. Visible caveat discloses normalization; table/source values stay unchanged. Ambiguous labels, invalid dates, missing cadence and duplicate coordinates are rejected; missing periods remain gaps. Shared planning guidance also prefers typed DATE_TRUNC output for lines. No SQL-policy relaxation, new provider call or frontend change.

From `backend`: `.venv/Scripts/python.exe -m pytest -q tests/test_phase3.py tests/test_phase4.py -p no:cacheprovider --basetemp ../.verification/iso-line-chart`: **70 passed**, one existing warning, **51.03s**. Tests include authenticated formatted-month query-to-chart with exact 360/1000/2400 evidence, table preservation, gaps, ISO year/day handling, invalid/ambiguous dates, plus existing chart/join/dashboard/export regressions. Ruff check/format passed after wrapping a test SQL string. README/TRD document chart normalization. Existing saved chart errors remain stored snapshots: restart backend and rerun the saved query or submit a new analysis to build the corrected chart. Actual browser rendering of this live result is not claimed.

## Live fallback rejection follow-up — 2026-10-13

Targeted verification from `backend`: `.venv/Scripts/python.exe -m pytest -q tests/test_provider_fallback.py tests/test_phase2.py::test_month_query_allows_safe_duckdb_date_formatting tests/test_env_reload.py -p no:cacheprovider --basetemp ../.verification/fallback-date-guidance`: **13 passed**, one existing warning, **5.97s**. Ruff check/format passed for changed Python files.

User-provided logs for request `ac10afd7-a7fa-47ee-a96b-ca1dbaaebc3a` show Gemini HTTP **503**, OpenRouter planning success, then API **422**. The latest local failed saved plan confirmed SQL rejection: provider used display column names (`sale_date`, `revenue_usd`) rather than registered internal IDs, and SQLite-style reversed STRFTIME arguments. SQLGlot consequently represented the formatting argument as a column identifier; the validator rejected it as unsupported formatting. No query executed. Inspected only failed plan/schema metadata; no result rows or credentials were printed.

Strengthened the shared prompt for Gemini/OpenRouter/Groq: map display names to `columns[].id`; prefer monthly DATE_TRUNC with explicit DATE cast; specify DuckDB date-first STRFTIME and existing permitted formats. SQL policy unchanged. Mocked routing checks assert both fallback endpoints receive this guidance. This is a planning-guidance correction, not evidence that a new live monthly request succeeds. No paid request was made; runtime acceptance remains open until a user retry produces correct computed results.

## Planning-provider fallback — 2026-10-13

Implemented configured Gemini → OpenRouter → Groq routing for analysis and dashboard planning, skipping empty keys. Keeps existing GeminiProvider entry points and API contracts. Each provider gets a share of remaining time within the same 1–60 second provider deadline; at most three explicit application attempts, one per configured provider. Success (including clarification/unsupported) stops routing. Provider failure/timeout/malformed output may advance; SQL/authorization failures after planning never cause fallback. Gemini-only embeddings are unchanged.

Root/backend examples now include active empty fallback keys and configurable models (`openai/gpt-4o-mini`, `openai/gpt-oss-120b`). Keys are SecretStr, reload with provider models/timeouts, and disappear from active configuration when removed from the file. Verified both existing root keys are nonempty through boolean-only checks; credential values were not printed/edited. Fixed HTTPS endpoints, no redirects, JSON object mode with local Pydantic validation, 128 KiB streamed response cap, existing 16k/64k plan limits and finally/context-managed cleanup. Query children also strip new provider-key environment variables. Provider-name telemetry uses a fixed allowlist; API body/messages remain redacted.

Commands from `backend`:

- `.venv/Scripts/python.exe -m pytest -q tests/test_provider_fallback.py tests/test_provider_diagnostics.py tests/test_env_reload.py tests/test_phase2.py tests/test_phase4.py tests/test_phase5.py -p no:cacheprovider --basetemp ../.verification/provider-fallback-final`: **61 passed**, one existing Starlette/httpx warning, **33.52s**.
- Added explicit embedding-no-fallback regression afterward; `.venv/Scripts/python.exe -m pytest -q tests/test_provider_fallback.py::test_embeddings_do_not_switch_providers -p no:cacheprovider --basetemp ../.verification/provider-fallback-embedding`: **1 passed**, one existing warning, **3.50s**.
- Changed Python files passed Ruff check/format. Earlier initial run was **20 passed/1 failed** due to stacking two mock HTTP client factories; corrected test setup, then the 61-test run above passed.

Mocks verified both plan schemas, Gemini/router/Groq ordering, stop-on-success, malformed fallback, shared timeout, cancellation, client closure, secret redaction, key removal/model reload, response cap, real authenticated fallback-plan-to-query revenue **3760.00**, and rejection of external file-scan SQL. No live/paid provider calls were made. Live credentials/model access, output quality, follow-up/join quality, browser and Docker gates remain open. Total deadline/cost tradeoff: with three keys a 60-second budget initially gives Gemini about 20 seconds; failure may incur calls to both fallback providers. No dependency, frontend, migration or architecture rewrite.

Protocol/model references: [OpenRouter JSON response parameters](https://github.com/OpenRouterTeam/docs/blob/main/api_reference/parameters.mdx), [OpenRouter model](https://openrouter.ai/openai/gpt-4o-mini), [Groq models](https://console.groq.com/docs/models), [Groq structured output versus JSON mode](https://console.groq.com/docs/structured-outputs). JSON mode does not guarantee our schema; local validation remains mandatory. Source ZIP regenerated after documentation changes. The old full-suite count is historical; this slice received targeted verification only.

## Provider failure diagnostics — 2026-10-13

User's monthly-trend request returned `PROVIDER_FAILED` (502) after 30,298.77 ms; increasing the runtime provider deadline to 60 seconds did not resolve the reported failure. This duration suggests, but does not establish, a provider timeout. The root cause remains unconfirmed; no live call was made by Codex.

Added allowlisted provider failure telemetry: numeric SDK HTTP status when present, fixed API/transport-timeout/deadline/unexpected categories, duration and request ID. SDK bodies/messages, keys, URLs and prompts are never logged. HTTPX transport timeouts and provider HTTP 504 now map to the existing `ProviderTimeout` path instead of generic failure. Planning/embedding clients still close in finally blocks. Restart the running backend to load these code changes; its next user-triggered failure will provide diagnostic evidence.

From `backend`, `.venv/Scripts/python.exe -m pytest -q tests/test_provider_diagnostics.py tests/test_env_reload.py tests/test_phase2.py::test_provider_failures_are_saved_safely tests/test_phase5.py::test_safe_logs_request_ids_and_health -p no:cacheprovider --basetemp ../.verification/provider-diagnostics`: **16 passed**, one existing warning, **10.20s**. SDK doubles cover 400/429/504, transport and unexpected errors, redaction and client closure without network. Ruff check/fix and format ran on the three changed Python files. The earlier 113-test full run predates these diagnostics; no new full-suite pass is claimed.

## Phase 6C — final verification and source packaging — 2026-10-13

Ran the full backend suite exactly once after the Phase 6B XLSX guard. From `backend`: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp ../.verification/phase6c-final`: **113 passed**, **one existing Starlette/httpx deprecation warning**, **63.36 seconds**. This supersedes Phase 6A's 112-test count for the current source. The 64 MiB XLSX expansion fix is preserved; no application/frontend files changed in Phase 6C.

README explicitly documents **10 MiB per compressed file**, **32 MiB upload request**, **64 MiB XLSX total declared expanded contents**, and that workbook parsing is **not fully memory-sandboxed**. Corrected stale schema guidance to `0005`, replaced the Phase 0 architecture description with the implemented pipeline, and added `docs/SUBMISSION.md` with evidence links, missing artifacts and a 25-second recording sequence. The sequence is not a completed demo video. Phase status updated accordingly.

Additional final checks from root: `backend/.venv/Scripts/python.exe sample_data/verify.py`: **all 12 expected-answer groups passed**. `backend/.venv/Scripts/ruff.exe format docs/package_submission.py` formatted the new standalone packaging script; `... check docs/package_submission.py`: **passed**. Packaging uses explicit source paths, excludes runtime data/credentials/dependencies/build outputs, and verifies ZIP CRC, membership and every included file's SHA-256 against its manifest. Output is under ignored `.verification/submission`; no publication/commit/push.

No Phase 6A/6B audit or repeated backend suite; no paid Gemini calls. Frontend unchanged, so historical static-check results are retained without claiming a new run. Docker `0005` restart, current browser interactions and live embeddings/follow-up/joins remain unverified. Screenshots and the 10–30 second video are absent; no real browser capture is claimed. The authoritative assignment PDF is absent from the project root, so the submission matrix is based on its requirements already recorded in PRD/TRD, not a new PDF audit.

Packaging command from root: `backend/.venv/Scripts/python.exe docs/package_submission.py`: **passed**, **115 source files**; CRC, archive membership and per-file hashes verified. ZIP and `manifest.json` are in `.verification/submission`; the manifest records the exact final archive SHA-256. Regenerated after this verification entry so packaged documentation includes the result.

**Readiness:** verified source and packaging documentation are prepared. Final submission remains incomplete until actual screenshots/video, original-PDF comparison, repository URL/publication authorization and the outstanding Docker/browser/live-provider gates are resolved. See `docs/SUBMISSION.md` for the concrete remaining actions.

## Phase 6B — targeted hardening — 2026-10-13

Inspected only authentication/CSRF, owner-scoped dataset/analysis/dashboard/search reads, cache authorization, SQL AST policy and child execution, upload parsers, report escaping, provider cleanup/timeouts, telemetry and health paths. Existing unrelated changes were preserved. No paid provider calls or new dependencies.

**Confirmed high-impact issue and fix:** XLSX's 10 MiB compressed upload cap did not bound expanded workbook input before openpyxl parsing, exposing memory/CPU exhaustion through compressed XML/shared strings. A regression fixture compressed 65 MiB below the upload cap and proved it reached the parser. Added a 64 MiB total declared ZIP-entry expansion cap before workbook parsing; API/frontend contracts are preserved, with an additional per-file validation rejection. README/PRD/TRD document the cap. This bounds archive expansion, not total parser memory or all malformed-workbook CPU costs.

Commands below ran from `backend`.

| Check | Exact command / result |
| --- | --- |
| Existing targeted security/reliability tests | `.venv/Scripts/python.exe -m pytest -q tests/test_phase1.py tests/test_phase2.py tests/test_phase4.py tests/test_phase5.py tests/test_foundation.py -p no:cacheprovider --basetemp ../.verification/phase6b-targeted`: **63 passed**, one existing Starlette/httpx warning, **40.77s**. Collected before adding the regression. |
| Reproduction before fix | `.venv/Scripts/python.exe -m pytest -q tests/test_phase1.py::test_xlsx_rejects_expanded_archive_before_workbook_parsing -p no:cacheprovider --basetemp ../.verification/phase6b-repro`: **1 failed**, explicitly because oversized expanded input reached the workbook parser. |
| Upload/auth regressions after fix | `.venv/Scripts/python.exe -m pytest -q tests/test_phase1.py -p no:cacheprovider --basetemp ../.verification/phase6b-upload-fixed`: **15 passed**, one existing warning, **8.45s**, including valid XLSX and oversized archive rejection. |
| Changed Python lint/format | `.venv/Scripts/ruff.exe check app/datasets.py tests/test_phase1.py` and `... format --check app/datasets.py tests/test_phase1.py`: passed; two files already formatted. |

Security tests covered guessed foreign IDs, anonymous/logout access, stale/deleted sources, cache owner/version keys, external scans/unauthorized SQL/DML/multiple statements, malicious report HTML/script serialization, export reauthorization and sensitive-log suppression. Dataset labels/questions/model plans remain untrusted: only validated registered-source SQL executes; no generated Python/shell execution. Report text/attributes are escaped and chart JSON neutralizes script termination; Plotly label strings are escaped in frontend and reports. Keys remain server-side SecretStr configuration, worker key environment variables are removed, provider errors are sanitized, and operation logs use allowlisted fields. Intended owner-selected data may appear in exports; exported content is not anonymized.

Reliability tests covered provider failures, query deadline/capacity recovery, result caps, partial dashboard persistence/deadline/concurrency, export failures/source revalidation, embedding failure without evidence corruption, cache expiry/invalidation and dependency health failures. Session/database contexts close or roll back on exit; provider clients and query processes close in finally blocks. No additional connection-leak claim beyond these reviewed cleanup paths and passing tests.

Limits reviewed in code: 10 MiB/file, 32 MiB/upload request, three files, 100,000 rows/50 columns, two intake requests, 60-second intake deadline; 12,000-character SQL, 500 rows/1 MiB query results, two query workers, 256 MB DuckDB memory/one thread, configured query/provider deadlines; six dashboard cards/90 seconds/one generation; 500 search candidates, ten results, two embedding calls, 35-second embedding call timeout and 60-second legacy indexing; 15-minute cache/128 entries/64 MiB with 1 MiB entry cap; report 12 selections/8 MiB final output. These are configured/enforced caps, not load benchmarks. No speculative optimization was applied.

**Remaining risks/limits:** embedding semaphore waits are not separately deadline-bounded; archive caps do not make workbook parsing a hostile-file sandbox; Windows lacks Linux OS CPU/address-space limits; process-local capacity/cache/metrics and single backend process remain intentional constraints. No browser injection/rendering check, live Gemini quality/timeout check, new Linux execution probe or Docker restart ran here. Phase 6A's Docker/provider/browser blockers remain open. Full backend suite was not repeated for this isolated parser guard; Phase 6A's 112-test full pass remains historical. Frontend unchanged, so static checks not repeated.

**Phase 6C readiness:** ready to proceed with remaining acceptance/submission work; final release remains conditional on the outstanding live-provider, browser and Docker gates. No other critical/high issue was reproduced in the targeted review.

## Phase 6A — integration verification — 2026-10-13

Preserved existing local changes. Reviewed AGENTS, PRD/TRD, README, prior verification, migration `0005`, search/cache authorization, follow-up/join paths, Analyze API calls and the Next.js proxy. No critical application failure or obvious runtime API contract mismatch was reproduced. No application/frontend code changed; no regression fix was required.

Commands ran from `backend` unless noted.

| Check | Exact command / outcome |
| --- | --- |
| Targeted integration | `.venv/Scripts/python.exe -m pytest -q tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py -p no:cacheprovider --basetemp ../.verification/phase6a-targeted`: **100 passed**, one existing Starlette/httpx warning, **61.76s**. Covers authentication, ingestion, analysis, contextual follow-ups, nested filters, explicit joins, charts, dashboards, exports, search, cache and observability with deterministic providers. |
| Migrations | Set `$env:DBO_DATA_DIR='../.verification/phase6a-migration'`; `.venv/Scripts/python.exe -m alembic upgrade 0004`, `... -m alembic upgrade head`, `... -m alembic current`, `... -m alembic check`: each exited **0**, **0005 (head)**, **No new upgrade operations detected**. Disposable storage. |
| Persisted search after local application restart | `.venv/Scripts/python.exe ../.verification/phase6a_restart_probe.py`: **passed** using existing test helpers/fake embeddings. Closed the application/TestClient/engine and created a new application against the same storage. Session, readiness, original search hit and saved evidence survived. Cache started empty, then produced miss/hit. With warmed cache, anonymous rerun returned **401**, foreign-owner rerun **404**, foreign search **[]**. Application/engine restart only; no OS-process or Docker-volume restart claim. |
| Cache/source boundaries | Targeted tests passed for dataset version rejection, source deletion/eviction, owner-dependent keys, snapshot identity and TTL; restart probe independently exercised anonymous/foreign reruns against warmed cache. |
| Full backend suite, once | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp ../.verification/phase6a-full`: **112 passed**, one existing warning, **61.23s**. |
| Compose configuration (root) | `docker compose config --quiet`: exited **0**, sandbox Docker-config access warnings. |
| Docker availability (root) | `docker version --format '{{.Server.Version}}'`: sandbox failed; approved outside-sandbox retry exited **1**, Docker Desktop Linux engine pipe missing. Startup/build/container migration/volume persistence/restart could not execute. |
| Frontend integration review | Reviewed search/index/rerun/join payloads, response fields, auth/CSRF forwarding, proxy routes and report attachment handling; no obvious runtime mismatch. No browser pass claimed. Frontend static checks not rerun because frontend files did not change. |

The disposable restart harness initially failed on its import path and then Windows multiprocessing's missing main guard. Corrected those harness issues and reran against fresh storage; they were not product bugs. Harness/storage remain under ignored `.verification`; no user data was reset.

**Confirmed fixes:** none. **Not executed/manual gates:** desktop/mobile semantic search/indexing, loading/error/empty states and result reopening; earlier responsive/keyboard/zoom/reduced-motion and report print checks. Live Gemini embedding quality and contextual follow-up/confirmed cross-file joins require credentials/network and explicit paid-call permission; no Gemini API call was made.

**Remaining blockers:** unavailable Docker daemon for Compose restart with `0005`; live-provider authorization and outstanding browser acceptance. **Phase 6B:** automated integration is ready for packaging, conditional on those unresolved gates. Final submission readiness is not established.

## Phase 5 — semantic search, execution cache, observability — 2026-10-11

Implemented owner-scoped SQLite search documents with `0005`, Gemini `gemini-embedding-001` 768-dimensional retrieval vectors, explicit bounded legacy indexing, and an Analyze history search/reopen UI. A failed embedding call leaves completed evidence intact. No live embedding quality or paid API call was verified. Search checks owner and source eligibility in database queries and before returning references; deleted source documents cascade away.

Validated SQL tables use a 15-minute, 128-entry, 64 MiB process-local cache keyed by owner, canonical SQL, policy version, dataset IDs/versions/hashes, and snapshot stat. Unsafe ordering/`LIMIT`, truncation, failures, and oversized tables bypass storage. Cached hits still validate SQL and authorization and save separate evidence. A saved single-source rerun skips model planning. JSON telemetry records safe request/operation fields, timings and database query counts; authenticated `/health/metrics` exposes fixed operation counters. Liveness and readiness retain their distinct semantics, with readiness now checking schema `0005`.

| Check | Result |
| --- | --- |
| New Phase 5 targeted tests | `backend/.venv/Scripts/python.exe -m pytest -q tests/test_phase5.py -p no:cacheprovider --basetemp ../.verification/phase5-new-final2`: **6 passed**, one existing Starlette/httpx warning. |
| Affected Phase 2/4 regressions | `backend/.venv/Scripts/python.exe -m pytest -q tests/test_phase2.py tests/test_phase4.py -p no:cacheprovider --basetemp ../.verification/phase5-affected`: **33 passed**, one existing warning. |
| Final full backend run | `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp ../.verification/phase5-full-release`: **110 passed**, one existing Starlette/httpx warning in 131.13 seconds. A later one-line cache-deletion telemetry addition passed its two affected tests (**2 passed**) and Ruff checks; the full suite was not repeated for that log-only change. |
| Backend lint/format | `.venv/Scripts/ruff.exe check .` and `.venv/Scripts/ruff.exe format --check .`: passed; 39 Python files formatted. |
| Fresh migration | With `DBO_DATA_DIR=../.verification/phase5-migration`, `.venv/Scripts/python.exe -m alembic upgrade head` then `... -m alembic check`: passed, no new operations. |
| Frontend | `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build`: all passed after the final UI edit. |

Provider-dependent live search, actual semantic relevance, manual desktop/mobile history search, and full Docker restart with migration `0005` remain unverified. Existing live contextual-follow-up/confirmed-join and visual gates remain open. Phase 6 submission packaging has not started. No commit or push was made.

## Continuation verification — 2026-10-11

The existing Phase 4 implementation was revalidated without resetting the working tree. Targeted Phase 4 tests passed **15/15**; the complete backend suite passed **103 tests** with one pre-existing Starlette/httpx deprecation warning. Ruff check/format, frontend lint, TypeScript typecheck, and production build passed. A clean migration data directory passed `alembic upgrade head` and `alembic check`.

The disposable Compose stack was rebuilt and started with `docker compose ... up --build -d --wait`. `docs/smoke_phase4.py` passed in create mode, then the backend was explicitly restarted and the smoke passed again with `--reopen`: both persisted cards remained complete, the saved revenue evidence remained **3,760.00**, the saved chart data matched, and the report remained **1,204,827 bytes** with the expected attachment headers.

The generated report was opened as a local `file:///` document in the integrated browser. The chart rendered to SVG, the supporting table showed the matching regional values, and browser resource timing contained no external requests. This closes the local-file rendering check for the fixture report; a browser-wide network-disabled toggle was not available, while the report CSP also declares `connect-src 'none'`. Responsive/mobile, keyboard/zoom/reduced-motion, print review, and the earlier live contextual-follow-up/confirmed-join Gemini gates remain open.

## Phase 4 — Dashboards and report export — 2026-10-11

Implemented owner-scoped generation/list/save/reopen with migration `0004`, at most six cards, one typed provider plan, sequential card execution through the existing SQL/evidence pipeline, one concurrent dashboard generation, and a 90-second generation deadline. Explicit version-bound join confirmation and multiplication consent remain mandatory. Partial/failed dashboards are saved, and card reads reauthorize sources/evidence. Deletion makes dependent cards unavailable. Reopening never recomputes. UI adds a two-column/one-column responsive grid, generation dialog, evidence disclosures and export selection.

Reports are on-demand HTML attachments from saved evidence, limited to 12 selections/expanded analyses and 8 MiB. Text is escaped, chart JSON neutralizes closing script tags, Plotly basic 4.1.2 is embedded locally, and CSP blocks networking. Ownership/source validity is checked again after rendering. Light theme, print CSS, supporting tables, SQL, assumptions, anomalies, join diagnostics and limitations are included. The proxy forwards restricted attachment filenames/content type; the UI says “Download started” and retains selections on failure.

| Check | Exact command / result |
| --- | --- |
| Existing baseline suite after initial implementation | `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp .verification/phase4-initial`: **88 passed**, one existing Starlette/httpx warning. The historical Phase 3 85-test result and later 88-test follow-up below remain unchanged. |
| Final backend suite (run in `backend`) | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp .verification/phase4-full-final`: **102 passed**, one existing Starlette/httpx warning, 100.58 seconds. |
| Backend lint/format | `.venv/Scripts/ruff.exe check .` and `.venv/Scripts/ruff.exe format --check .`: passed, 34 Python files formatted. |
| Migration upgrade/check | With `DBO_DATA_DIR=.verification/phase4-migration`, `.venv/Scripts/python.exe -m alembic upgrade head` and `... -m alembic check`: passed; no new upgrade operations. |
| Frontend (run in `frontend`) | `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build`: all passed on final UI; `/dashboards` and `/dashboards/[id]` included. |
| Disposable Docker clean build/start and final image recreation | `docker compose -p dbo-phase4-check -f docker-compose.yml -f docs/compose.phase4.yml up --build -d --wait`, with `FRONTEND_PORT=3104`, `BACKEND_PORT=8104`, `DBO_PUBLIC_ORIGIN=http://localhost:3104`: passed; migration exited successfully and both app services became healthy. Only the override injects the explicitly labeled test provider. |
| Persistence after final image recreation | `.venv/Scripts/python.exe ../docs/smoke_phase4.py --base-url http://localhost:3104 --reopen`: passed. Two cards, revenue 3,760.00, saved chart values unchanged, authenticated saved-dashboard page returned 200. |
| Proxy report and programmatic offline assets | Same smoke verified `text/html; charset=utf-8`, restricted `Content-Disposition`, `nosniff`, `no-store`, logout denial, exact saved chart JSON, two supporting tables, three inline script blocks, no external asset attributes, and network-blocking CSP. Report: **1,204,827 bytes**. `node --check .verification/phase4/script-0.js` and `script-1.js` passed for the embedded runtime and chart bootstrap. This does **not** establish browser rendering. |
| Authenticated live Gemini dashboard (separate from fixtures) | `.venv/Scripts/python.exe live_dashboard_smoke.py`: **passed**, provider Gemini, model `gemini-3.8-flash`. One dashboard request, two complete scalar cards: actual **3,760.00 / 1,800.00**, independently computed expected **3,760.00 / 1,800.00** from synthetic `analysis_flat.csv`. Disposable metadata; credentials were not printed or edited. |
| Integrated browser / actual offline rendering | The generated local report opened successfully. The chart rendered to SVG, the supporting table contained matching values, and `performance.getEntriesByType('resource')` returned no external resources. The report CSP blocks network connections; a browser-wide network-disabled mode was unavailable. Responsive/mobile interactions, print appearance, and earlier visual gates remain **unverified**. |

New tests cover known figures and exported chart equality, saving/reopening without a provider call, saved-analysis reuse, six-card plan/input limits, malformed plans, SQL failures with preserved successful cards, generation deadline/cancellation and capacity release, concurrent generation rejection, sanitized provider failure, missing join consent and multiplication consent, anonymous/cross-owner access, nested card reauthorization, deleted/stale sources, post-render source revalidation, direct and expanded selection limits, final report-size limit, safe attachment filenames, and malicious HTML/closing-script-tag serialization. The Docker smoke exercises the real Next.js attachment proxy; fixture responses are not represented as live-provider results.

Initial verification issues were corrected rather than counted as passes: reopen exposed SQLite timezone loss (dashboard/evidence responses now explicitly use UTC); the first test run had 11 passing tests and that timestamp failure. A Docker build was stopped before startup to correct the test-fixture bind mount and disable host-path creation. The smoke's first logout assertion used a revoked CSRF cookie (403); it now obtains a fresh token and verifies anonymous denial (401). One reopen attempt hit the container recreation window before readiness and was rerun after `up --wait` completed. Existing npm development audit findings remain recorded below; no unrelated dependency audit or Phase 2/3 Linux safety audit was repeated.

### Remaining manual acceptance checklist

1. Generate from `analysis_flat.csv`, name/save/reopen, inspect metric shape, Chart/Table tabs, sources, Method/SQL, empty/partial/failed states, and unavailable cards after source deletion. Verify dialogs and the fixed grid at 1440 px and 390 px, keyboard focus, 200% zoom, and reduced motion.
2. In Analyze, explicitly confirm join keys/type and multiplication consent, then generate. Missing/stale confirmation must produce clarification/rejection, never guessed joins. Earlier live contextual-follow-up and confirmed-join smokes remain open; the Phase 4 scalar smoke does not close them.
3. Select completed answers/cards in **Export report**; unavailable selections must explain why. Simulate a failed request and confirm selections persist. Successful initiation must say **Download started**.
4. Download the HTML, stop application services, disable browser networking, then open the local file. **Fixture rendering passed**: the chart visibly rendered, values agreed with supporting tables (fixture total 3,760.00), and no external resources were recorded. Labels containing `<`, `&`, and closing script tags, plus print preview, still need manual inspection.

Phase 4 implementation is ready for review and conditional Phase 5 planning; acceptance remains open for the manual gates above. Phase 5 has not started. Semantic search, execution caching, expanded observability, PDF, and submission packaging were explicitly out of scope. All earlier open gates and historical results below are preserved. No commit or push was made.

## Runtime env reload and live-provider follow-up — 2026-10-11

The root Compose `.env` now mounts read-only into the backend. Gemini key/model and provider/query timeouts are parsed and validated for each new analysis or join diagnostic request; startup-only settings remain restart-bound. The test provider confirms key/model/timeout edits, removed keys, invalid values, and successful prior evidence preservation through the real analysis API. The SQL policy now allows the pure `LOWER` expression after a real Gemini plan used it for a regional filter. Gemini uses `response_json_schema` because the SDK's `response_schema` encoding of Pydantic `extra="forbid"` produced an HTTP 400 (`additional_properties` unsupported in that request form). [Google's SDK documentation](https://github.com/googleapis/python-genai#json-schema-support) documents the JSON Schema form.

| Check | Result |
| --- | --- |
| `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp .verification/pytest-final-autoload` | 88 passed, 1 Starlette/httpx deprecation warning. |
| `backend/.venv/Scripts/ruff.exe check .` and `ruff.exe format --check .` | Passed; 27 Python files formatted. |
| `docker compose config --quiet` | Passed. |
| Disposable production backend image and synthetic read-only `.env` bind mount | Passed. Final image rebuilt. In one running Linux container, an in-place host edit changed the visible model and query timeout from `fixture-model`/5 to `fixture-model-edited`/9 without restart. A second container also saw `before-rename` change to `after-rename` after an atomic host file replacement. No user credential file was edited; both probe containers were removed. |
| Authenticated live Gemini smoke against synthetic data | Partial, **not a pass**. One single-source South revenue answer matched independent USD 1,800 expectation. The first follow-up attempt was stopped by the SQL allowlist on `LOWER`; that safe expression is now admitted and tested. Later live retries returned `PROVIDER_FAILED` on the first call; a separate time-bounded structured-output diagnostic received provider HTTP 504 `DEADLINE_EXCEEDED`. Contextual follow-up and confirmed cross-file live figures remain unverified. The reusable script is `backend/live_gemini_smoke.py`. |

No frontend code or migration changed in this follow-up. Phase 1–3 visual/browser verification remains open. This runtime-config work does not close the earlier Phase 2/3 acceptance gates.

## Phase 3 — 2026-10-10–11

Implemented through the existing authenticated pipeline: validated bar/line/pie/scatter artifacts, Chart/Table views, bounded structured follow-up intent (including nested filters), full-snapshot IQR evidence, and explicit inner/left joins across up to five sources. Chart values come from executed evidence. Invalid chart requests retain successful tables. Confirmation is a separate user action, never a provider instruction. Failed follow-ups preserve prior successful evidence. Deleted sources invalidate historical dependencies even after selection changes.

| Check | Actual result |
| --- | --- |
| Backend full suite: `uv run --frozen pytest -q -p no:cacheprovider --basetemp=.phase3-tests-final` | 85 passed; one existing Starlette/httpx deprecation warning. |
| `uv run --frozen ruff check .`; `uv run --frozen ruff format --check .` | Passed. |
| `DBO_DATA_DIR=.verification/phase3-migrations`, `uv run --frozen alembic upgrade head`, then `uv run --frozen alembic check` | Passed; no new upgrade operations. Phase 3 uses existing JSON columns; schema remains `0003`. |
| Frontend `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build` | Passed, including Plotly dynamic import, Chart/Table controls, join workflow, anomaly tables, and mobile-visible sign-out. These checks do not establish visual correctness. |
| Frontend `npm.cmd ci --dry-run --ignore-scripts` | Passed lock consistency check. Existing platform-specific dependency entries were preserved; Plotly runtime/types were added. No full clean Linux frontend build was repeated. |
| `docker build -t dbo-phase3-check-backend -f backend/Dockerfile backend` | Passed; disposable production backend image. |
| Targeted Linux probe, `backend/tests/linux_phase3_probe.py`, mounted read-only at `/app/probe.py`; `docker run --rm --network none … dbo-phase3-check-backend python /app/probe.py` | Passed: exact joined rows `(1,0),(2,1),(3,2)`, all four chart artifacts, one expected IQR flag at record 25, null count 1, non-finite query output rejected, and a later query succeeded with its permit released. Container and temporary fixtures removed automatically. |
| Live Gemini | Not run. `backend/.env` absent, root `DBO_GEMINI_API_KEY` empty, and no `DBO_GEMINI_API_KEY` environment variable configured. No production fake was substituted. |
| Integrated browser | Connection failed before opening a tab: tool sandbox metadata lacked `sandboxPolicy`. Phase 1–3 desktop/mobile visual acceptance remains open. |

The new tests cover result-column/type validation, negative/zero/null/truncated pies, category caps, ordered temporal gaps, all four chart types through the API, chart-only failure, filtered and nested follow-up inheritance, ambiguous references, changed versions, previous-evidence preservation, IQR null/constant/small/all-null groups, explicitly confirmed grouping, and full-population counts beyond the display cap. Join fixtures cover many-to-one and many-to-many risk, unmatched/null keys, five connected sources, missing/ambiguous relationships, changed keys/types, stale/tampered/cross-conversation confirmations, foreign owners, and deletion invalidation. Existing SQL, timeout, capacity, result-cap, authentication, intake, and owner-isolation tests remain in the full suite.

Independent numeric expectations: filtered South revenue 1,800; its monthly breakdown sums to 1,800; left-join fixture total 150; repeated-key fixture total 180 only after multiplication acknowledgement; five-source fixture total 66. IQR fixture `sample_data/phase3_anomalies.csv` has Q1=7, Q3=19, one null and one flag (record 25, value 1,000). A separate 3,600-record fixture flags 600 records while showing only 500. IQR quartiles are checked against Python standard-library inclusive quantiles. These are deterministic test-provider results, not live Gemini results.

Initial-check issues were not counted as passes: the existing uv/npm caches and Docker daemon required sandbox escalation; reuse of the old `.pytest_tmp` directory failed on Windows permissions, so new disposable directories were used. Lint findings were fixed before passing checks. The first Linux probe exceeded the existing CPU cap with heavy fixture/provider imports in its spawn entrypoint; moving those test-only imports into the parent produced the passing probe without changing CPU, memory, timeout, or concurrency limits. Windows npm installation pruned unrelated optional lock entries; the prior entries were preserved rather than accepting that regression. Previously recorded npm development-only audit findings remain unresolved.

### Open manual/browser and live-provider gates

Use a configured local Gemini instance and synthetic data; test desktop (~1440 px), mobile (~390 px), keyboard, 200% zoom, and reduced motion:

1. Register/sign in, upload valid/invalid CSVs, inspect profiles and nulls, and verify logout/session expiry clears private content. Confirm sign-out stays reachable on mobile.
2. Select `analysis_flat.csv`; ask total revenue (3,760), then “Now break that down by month” (360/1,000/2,400). Inspect sources, method/stages, and copied SQL; reopen the conversation.
3. Request bar, line, pie, and scatter charts with suitable fields. Switch Chart/Table using keyboard arrows, inspect labels/units and temporal gaps, and verify narrow-screen scrolling. Invalid charts must retain the computed table; truncated results must retain their warning.
4. Upload `phase3_anomalies.csv`; ask for unusual `value` observations. Inspect Q1/Q3, bounds, sample/null counts, the record-25 flag, and statistical caveats. Test a small/constant group separately and confirm its verdict is insufficient evidence.
5. Select sales + customers; explicitly choose customer-ID keys/type, review uniqueness/unmatched/repetition diagnostics, acknowledge multiplication, and confirm. Ask revenue by region using quantity × unit price; South must be 1,800 and total revenue 3,760. Changed keys or sources must require a new confirmation.
6. Exercise clarification, provider failure, retry, empty results, and source deletion. Questions and earlier successful evidence must survive failed follow-ups; deleting either join source must make dependent evidence unavailable.

The required live smoke consists of steps 2 and 5 (one authenticated single-source answer, one contextual follow-up, one explicitly confirmed cross-file answer). Record provider/model, actual figures, and independent comparisons separately from test-provider results. It has not run. Browser interaction, label escaping in the rendered Plotly DOM, and responsive/visual behavior are also not claimed verified.

Phase 3 implementation supports Phase 4 planning, but full core acceptance remains conditional on these gates. No dashboards, exports, semantic search, execution caching, commits, pushes, or Phase 4 work were added. Phase 2's prior Linux execution-safety evidence was not re-audited.

## Phase 2 — 2026-10-10

The single-table analysis path is implemented with a test-only deterministic provider. The fixture is `sample_data/analysis_flat.csv`, derived from the checked-in synthetic sales/customers files by `sample_data/build_analysis_flat.py`. It permits questions about regional revenue, monthly totals, and top customers without an implicit runtime join.

| Check | Result |
| --- | --- |
| Backend Phase 2 tests (`uv run --frozen pytest -q --basetemp=.pytest_tmp tests/test_phase2.py`) | 18 passed; one Starlette/httpx deprecation warning. |
| Backend full suite (`uv run --frozen pytest -q --basetemp=.pytest_tmp`) | 39 passed; same warning. |
| `uv run --frozen ruff check .` and `uv run --frozen ruff format --check .` | Passed. |
| `uv run --frozen alembic upgrade head` then `alembic check` in disposable `.phase2-migration-check` data directory | Passed; no new upgrade operations. |
| Frontend `npm.cmd run lint`, `typecheck`, and `build` | Passed. |
| Disposable Docker build/start/migrate, project `dbo-phase2-check` | Passed; both app services healthy. |
| Proxy smoke `uv run --frozen python ../docs/smoke_phase2.py --base-url http://localhost:3102` | Passed: account, upload, conversation, honest missing-provider error, and persisted failure. |
| Linux child execution | Passed: validated query over uploaded Parquet returned revenue `3760.00` in a child DuckDB process. |
| Restart persistence | Passed: after backend restart, 1 dataset, 1 conversation, 1 failed analysis, and 1 Parquet snapshot remained. Disposable project and volume then removed. |
| Live Gemini smoke | Not run: no `DBO_GEMINI_API_KEY` was configured in the checked environment. No synthetic response is used in production. |
| Integrated browser | Connection failed before opening a tab due to browser-tool sandbox metadata. Phase 1 desktop/mobile and Phase 2 visual interaction remain unverified. |

### Linux execution safety follow-up — 2026-10-10

The production backend image was built as the disposable `dbo-phase2-safety-backend` tag. `backend/tests/linux_execution_probe.py` ran in a disposable Linux container with no network. The probe created a temporary Parquet fixture and inspected real `/proc` child PIDs and limits; the container and fixture were removed afterward.

| Scenario | Observed result |
| --- | --- |
| Cancellation and one-query capacity | A running child was observed; a second query returned `QueryBusy`. Cancellation terminated and reaped that PID, released the permit, and a normal query succeeded. |
| Deadline | A deliberately long query exceeded its one-second deadline; its child PID disappeared, the permit was available, and a normal query succeeded. |
| Worker limits | DuckDB reported one thread, a 244.1 MiB effective memory cap for the configured 256 MB limit, external access off, and extension auto-install off. The child `/proc` limits showed six seconds of CPU and 2 GiB address space. |
| Failure and output caps | Invalid SQL, a memory-heavy query, and output over 1 MiB failed safely. A 600-row query returned 500 rows with `truncated=true`. Capacity was released and a normal query succeeded after each failure. |
| Cleanup | No query child remained in multiprocessing's live-child set or `/proc` after cancellation/deadline; no temporary file remained after the probe. |

The first probe runs exposed test-harness issues (a resource-tracker process counted as a query child, a cold-start-sensitive five-second probe allowance, and DuckDB's MB-to-MiB display). A later run exposed intermittent child exit code `-11` (segmentation fault) on a normal query under the 1 GiB address-space cap. The address-space cap was raised to 2 GiB while retaining DuckDB's 256 MB allocation limit; the complete Linux probe then passed twice. Unexpected worker exits now include the exit code in the internal exception, while the API continues to return a sanitized error. The live-provider and browser checks remain unverified, so Phase 2 functional acceptance is still open.

Known-answer assertions use South regional revenue of 1800.00, monthly totals 360.00/1000.00/2400.00, and top customer IDs C06/C05/C04/C03/C02. SQL rejection cases include external scan, foreign table/column, multiple statements, DML in CTEs, unsafe functions, joins, and nested unauthorized sources. API tests cover persistence, clarification, provider errors, owner isolation, cascade invalidation, and source deletion during execution. Windows tests verify query timeout, capacity recovery, 500-row truncation, and the 1 MiB result cap. The Linux follow-up above subsequently verified cancellation/resource-limit behavior. Live Gemini and browser interaction remain unverified, so the complete Phase 2 functional gate remains open.

Manual browser check: register/login; upload the analysis sample and inspect its profile/preview; select it in Analyze; with a configured key, ask a question and inspect answer/table/source/Method/SQL; verify an error preserves the question and retry works; reopen the conversation; delete the dataset and confirm dependent evidence is unavailable; sign out. Check keyboard focus and layout at desktop and mobile widths. The integrated browser connection failed again during this follow-up before a tab opened; no visual result is claimed.

Gemini structured JSON with a Pydantic response schema and the selected model were checked against [Google structured output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) and the [Gemini models list](https://ai.google.dev/gemini-api/docs/generate-content/latest-model). Documentation verification is separate from a live API call.

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
# Regional bar-chart planner regression (2026-10-14)

Two saved failed regional bar requests used display names as source SQL columns (`region` / `revenue_usd`) instead of registered IDs (`c5` / `c8`). The SQL validator correctly rejected them. Planner guidance now illustrates source IDs versus output aliases; validation remains unchanged.

Verification: `pytest tests/test_phase2.py tests/test_phase3.py tests/test_provider_fallback.py -q --tb=short` passed all 84 tests, including a mocked-provider upload-to-bar regression asserting South 1800, North 960, West 520, East 480 and continued rejection of both invalid query forms. Ruff passed for the modified Python files. Initial sandbox run hit pytest temporary-directory permissions; the approved rerun passed with cache-permission and dependency-deprecation warnings.

One live configured-provider call for the exact reported question returned SQL accepted by the validator and a bar-chart intent. This was a planning check, not browser rendering verification; restart the backend to load the updated prompt and repeat the UI request. Model output remains nondeterministic.

# Confirmed regional join planner regression (2026-10-14)

The saved failing sales/customers plan used unqualified `ON c3=c1` and unqualified projections. The confirmed relationship was present; the validator correctly rejected ambiguous join keys. Planner guidance now includes a qualified sales/customer aggregation example, explains that internal IDs are local to each source, and preserves the exact confirmed join order/type/keys.

Verification: `pytest tests/test_phase3.py tests/test_provider_fallback.py -q --tb=short --basetemp=.verification/join-qualified-20261014` passed 66 tests (one dependency deprecation warning). A new mocked-provider API test verifies confirmed joins, regional table/chart totals, and rejection of unqualified keys. One live configured-provider call for the reported question produced validated SQL; execution against checked-in sales/customer fixtures matched North 960, South 1800, East 480, West 520. This does not verify browser rendering or guarantee every future model response. Restart the backend before UI retesting.

# Unique join-column references (2026-10-14)

Prompt-only qualification guidance still produced a saved failing plan with a qualified ON clause but ambiguous bare c3 in SELECT/GROUP BY. Confirmed-join schema and key context now use distinct per-source tokens, translated by `planner_columns.py` to qualified physical SQL before the unchanged execution validator. Ambiguous bare references and wrong-source qualifiers are not guessed or repaired.

Verification: `pytest tests/test_planner_columns.py tests/test_phase3.py tests/test_provider_fallback.py -q --tb=short --basetemp=.verification/join-tokens-20261014` passed 69 tests (one dependency deprecation warning). Ruff passed. Tests cover context copying, projection-name preservation, wrong-source references, multiple statements, mocked-provider API execution, and altered join-key rejection. Three consecutive live configured-provider calls for the reported question produced validated SQL and matched all four regional totals when executed against the checked-in fixtures. Browser rendering and the restarted production process remain unverified; these successes do not guarantee all model output.

