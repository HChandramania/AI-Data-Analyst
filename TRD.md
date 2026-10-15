# Technical Requirements Document

## 1. Status and decisions

Confirmed-join planning uses per-source unique column tokens (`s1_c3`, `s2_c3`) in schema and join-key context. A deterministic AST adapter resolves exact tokens to registered physical columns and table aliases before the existing SQL validation. It does not infer ambiguous bare IDs, repair mismatched source qualifiers, or authorize joins. Query/dashboard plans share the adapter; saved SQL and intent use physical references. Single-source context is unchanged.

Line chart construction also accepts strictly validated ISO text labels at explicitly declared cadence: YYYY-MM for month, YYYY for year, or YYYY-MM-DD. Chart coordinates normalize month/year to their first day with a caveat; source/result tables remain unchanged. Invalid/ambiguous labels are rejected and existing temporal-gap behavior remains enforced.

Planning now supports ordered Gemini → OpenRouter → Groq fallback, skipping blank keys, within a shared provider deadline (maximum 60 seconds). One explicit attempt per configured provider; each receives a remaining-budget share. Existing analysis/dashboard schemas and independent owner/source/SQL enforcement remain authoritative. OpenRouter/Groq JSON object output is locally schema-validated; failures/malformed responses may advance, while successful clarify/unsupported results stop. Keys/models reload from the selected runtime environment file. Embeddings remain Gemini-only. Fixed endpoint URLs and bounded response bodies are enforced; telemetry records only allowlisted provider names/statuses/categories. Live fallback acceptance remains unverified.
This document defines the full implementation target. Phases 0–2 provide the foundation, authentication/intake, Gemini planning, validated SQL, bounded DuckDB execution, saved evidence, and deterministic wording. Phase 3 adds charts, follow-up intent, IQR, and explicit joins. Phase 4 adds saved dashboards and offline HTML reports. Phase 5 adds migration `0005`, semantic history search, execution caching, and safe telemetry. Dashboard live Gemini and offline browser rendering smokes passed earlier; live embeddings, earlier live follow-up/join, and responsive browser gates remain open. See `docs/PHASES.md` and `docs/VERIFICATION.md` for evidence and unverified gates.

Phase 4 contracts: `POST /dashboards` takes title, conversation_id (whose authorized selection defines scope), optional prompt, analysis_ids (reuse), generate flag, join_confirmation and accept_multiplication. One typed DashboardPlan contains up to six titled AnalysisPlans; cards run sequentially through the same analysis service without additional provider calls. At most one dashboard generation runs process-wide; total generation deadline is 90 seconds. Provider timeout remains separately enforced. No retries or background queue. Successful and failed card references are saved automatically. `GET /dashboards` lists latest 50; `GET /dashboards/{id}` reauthorizes every card and returns completeness plus saved generation/source metadata. No recomputation on reopen. Deleted/version-changed sources cause unavailable cards; evidence uses the existing conservative selected-source dependency semantics.

`POST /reports/export` takes title, analysis_ids and/or dashboard_ids. It permits 1–12 distinct selections and at most 12 unique expanded analyses, with an 8 MiB UTF-8 output cap. Whole dashboards must be complete; partial cards can be selected as analysis IDs. Reauthorize evidence before rendering and again in a fresh transaction before response. HTML is generated in memory, escaped, uses safely serialized chart JSON and a vendored Plotly basic runtime, and is returned as a text/html attachment with a restricted ASCII filename. No filesystem path input, retained report copies, remote assets, or PDF. Same-origin proxy forwards only validated report attachment headers; other API responses remain JSON. Static limits are code constants, not additional environment settings.

Phase 3 implementation contracts: chart/anomaly artifacts and join proposals use the existing `Analysis.result_json`; validated intent lives in `plan_json`, so schema revision remains `0003`. `POST /conversations/{id}/joins` accepts user-selected connected relationships and saves bounded diagnostics. Messages may reference that proposal via `join_confirmation`, with `accept_multiplication` when either side repeats records; `anomaly_group_confirmation` confirms a grouping column. Only direct inner/left equality joins with one key per relationship are supported. All source versions and owners are checked again. Diagnostics are pairwise before preceding joins. IQR uses full single-source snapshots and original data-record positions; it is not calculated from capped query output. Gemini context is capped at 32,000 characters including up to 4,000 characters of structured intent and four user/clarification messages of 500 characters each. Nested query stages retain inner filters. No raw result rows are sent. Deterministic wording remains the production narrative path; a second model summary call is not implemented.

Readiness requires the metadata database, current schema, and writable data directory. It does not require provider credentials or an embedding model. The broader capability checks below are future targets. The same-origin proxy exposes health, authentication, and dataset routes with origin/CSRF and cookie handling. Compose adds a one-shot migration service before the API. Phase 1 adds Argon2id, multipart, and Parquet dependencies.

| Area | Decision | Reason |
| --- | --- | --- |
| Frontend | Next.js, TypeScript, Tailwind, Plotly.js | Familiar UI stack; chart specs can be validated and rendered consistently |
| Backend | FastAPI, Pydantic, SQLAlchemy, Alembic | Typed API boundaries and straightforward service separation |
| Application state | SQLite, migrations, persistent Docker volume | Minimal infrastructure for a local assignment; single API process |
| Analytics | DuckDB over immutable normalized Parquet snapshots | SQL analytics on uploaded files without external database setup |
| LLM | Gemini through a provider interface, configurable model | Structured analytical planning and grounded summaries; credentials remain server-side |
| Semantic search | Gemini `gemini-embedding-001` through existing SDK, normalized 768-dimensional vectors in SQLite | Reuses configured provider without a vector service or additional dependency; embedding requests use the configured key |
| Cache | Bounded process-local TTL cache | Small deployment; cache loss on restart is acceptable |
| Exports | Self-contained HTML with embedded Plotly runtime | Offline charts and evidence without PDF/browser infrastructure |
| Deployment | Docker Compose: frontend + backend, persistent backend volume | Reproducible local evaluation |

The embedding model is called through the existing SDK; search needs a configured Gemini key and network access. Readiness checks local storage and schema, while search reports `SEARCH_UNAVAILABLE` for provider failure. No live embedding API call is made by health checks.

## 2. Architecture
```mermaid
flowchart TD
  UI["Next.js workspace"] --> API["FastAPI and owner authorization"]
  API --> State["SQLite metadata and sessions"]
  API --> Files["CSV and Parquet snapshots"]
  API --> Planner["Structured LLM planner"]
  Planner --> Validator["SQL and chart validation"]
  Validator --> Exec["Isolated DuckDB query process"]
  Files --> Exec
  Exec --> Evidence["Computed evidence artifact"]
  Evidence --> Summary["Grounded response formatter"]
  Summary --> UI
  Evidence --> Artifacts["Dashboards and HTML reports"]
  State --> Search["Owner-scoped semantic retrieval"]
  API --> Search
```

Backend owns calculations, authorization, execution, and report generation. Frontend renders typed artifacts; it does not execute generated code or independently calculate displayed business totals. Use a modular monolith and one API process initially; no durable queue or continuous worker.

## 3. Data model
All IDs are server-generated UUIDs, timestamps UTC, and owner IDs derived from the authenticated session rather than request input.

| Entity | Essential fields |
| --- | --- |
| User | id, normalized email (unique), password_hash, created_at |
| Session | id, user_id, token_digest, expires_at, revoked_at |
| Dataset | id, owner_id, display_name, content_hash, version, status, original_path, parquet_path, schema_json, profile_json, row_count, created_at |
| Conversation | id, owner_id, title, selected_dataset_versions_json, created_at, updated_at |
| Message | id, conversation_id, role, content, status, created_at |
| Analysis | id, owner_id, conversation_id, question, plan_json, sql, dataset_versions_json, result_json, chart_specs_json, method_json, status, timings_json, created_at |
| Dashboard | id, owner_id, title, dataset_versions_json, cards_json, created_at |
| SearchDocument | analysis_id (PK/FK), owner_id, model_revision, content_hash, normalized embedding blob, created_at |

Upload is immutable: a replacement creates a new dataset ID/version. Store file locations internally; never return filesystem paths. Analysis evidence contains bounded result rows and aggregate metadata, not an unrestricted raw data copy. Foreign keys and indexes enforce relationships; application services enforce owner scopes. Enable SQLite foreign keys and use WAL with short transactions. Do not run multiple API replicas against this initial design.

Deletion removes files and associated cache/embedding entries. Delete or invalidate dependent analyses and dashboard cards so deleted data cannot be exposed through a saved artifact. Return a clear unavailable-source state. Exports are generated on demand; avoid persistent report copies. State the cascade behavior in the README.

## 4. CSV/XLSX ingestion
XLSX ZIP entries have a total declared uncompressed-size cap of 64 MiB, checked before loading workbook XML/shared strings.
1. Authenticate and enforce upload/concurrency limits before accepting work.
2. Stream to a randomly named temporary file while counting bytes; do not trust Content-Length or file extension.
3. Parse UTF-8/BOM CSV or the first non-empty worksheet of an XLS/XLSX workbook with bounded rows/columns. Reject empty headers, duplicate headers, malformed rows, invalid encoding/workbooks, zero-data files, unsupported extensions, and exceeded limits. Reject NUL/control characters in headers; retain a safe display-name mapping.
4. Normalize table/column identifiers to server-controlled names; preserve original labels for display. Do not interpolate user headers into SQL.
5. Infer types conservatively. Ambiguous dates remain strings until confirmed; preserve leading-zero identifiers. Document numeric null/invalid-value behavior and timezone assumptions.
6. Produce profile statistics and a normalized Parquet snapshot. Record SHA-256 and schema/version. Use atomic file moves and a short metadata transaction; clean up failures.
7. Return per-file accepted/rejected results. File parsing runs off the request event loop and has a deadline.

Limits: 64 MiB/file, 1,100,000 rows/file, 50 columns/file, five selected datasets, 500 result rows, six cards/dashboard. Rate-limit costly operations and cap concurrent query processes at two by default. Store files outside web-served directories.

## 5. Analytical request pipeline
1. Authorize conversation and selected dataset IDs. Resolve their immutable versions and schemas.
2. Build bounded context from recent messages, prior structured intent, profile statistics, and relevant schema descriptions. Raw sample cells are excluded by default; any optional sample disclosure must be explicitly documented and redacted.
3. Request an `AnalysisPlan`: action (`query`, `anomalies`, `dashboard`, `clarify`), selected dataset IDs, SQL where applicable, join assumptions, chart intent, and concise user-facing method.
4. Validate every field. Unknown datasets, invented columns, unconfirmed joins, unsupported actions, or ambiguous definitions become clarification/errors.
5. Validate SQL and execute in a resource-limited child process, or invoke deterministic anomaly/dashboard tools. Never execute arbitrary generated Python.
6. Save evidence: dataset versions, validated SQL, bounded rows, result schema, count/truncation metadata, deterministic chart specs, and method facts.
7. Ask the model for a concise narrative using only bounded evidence. Verify referenced metric IDs/values against evidence; assemble numeric displays server-side. If validation fails, return the computed table and a deterministic method explanation instead of an unsupported narrative.
8. Persist completed analysis and its search document. Failed analyses remain visible with safe errors but are not indexed as successful evidence.

Provider calls have finite timeouts and at most one repair attempt for invalid structured output. Do not repeatedly regenerate SQL after semantic validation failures; ask for clarification when needed. Keep total request budgets explicit: proposed 30-second provider call, 5-second query, 60-second analysis deadline, configurable and measured.

## 6. SQL execution boundary
Parse exactly one statement with a SQL AST parser compatible with DuckDB. Permit SELECT/CTE queries only. Recursively validate CTEs, subqueries, table references, columns, and all function calls against an allowlist. A keyword regex is insufficient.

Reject DDL/DML, COPY, ATTACH, PRAGMA, INSTALL/LOAD, external scans, table-valued/file/network functions, system catalogs, unregistered tables, dynamic SQL, and unsupported constructs. Allow a small documented set of aggregates, arithmetic, date operations, CASE, grouping, ordering, and controlled joins. Disallow recursive CTEs initially.

The parent creates a per-request DuckDB database containing only authorized snapshot tables. The execution child opens it read-only with external access and extension auto-install/load disabled and locked configuration where supported. The child has no provider credentials, no shell access, no outbound network, restricted filesystem visibility, memory/CPU limits, and a hard parent-enforced deadline. AST restrictions and engine configuration supplement process isolation; neither alone is a complete sandbox.

Impose result caps outside the generated query, preserve aggregate semantics, and mark truncation. Limit threads and DuckDB memory. Bound intermediate work through process limits. On timeout/cancellation terminate and reap the child, delete temporary databases, and release concurrency permits in `finally`. Verify these controls in the Linux Docker runtime; document limitations of any unsupported local platform.

Joins require selected datasets and explicit confirmed keys. Profile key uniqueness, nulls, unmatched keys, and potential many-to-many multiplication. Do not silently sum duplicated revenue after a join. Reject an unsafe or ambiguous join pending user clarification.

## 7. Charts, anomalies, dashboards
**Charts:** backend creates a validated `ChartSpec` with type, title, x/y keys, labels, units, series, and analysis ID. No generated JavaScript/HTML. A line chart needs an ordered temporal/numeric x-axis; scatter needs numeric axes; pie needs nonnegative values with positive total and a small category count. Aggregate into “Other” only with disclosed logic. Render Plotly from computed values.

**Anomalies:** initial method is deterministic IQR outliers on a selected numeric measure, optionally by a confirmed group. Use Q1/Q3 and 1.5×IQR bounds, exclude nulls with disclosed counts, require at least 20 valid observations per group, and return no IQR verdict when IQR=0. Include original row reference, value, bounds, group, sample size, and rule version. These are statistical flags, not proof of fraud or error. Time-series deviations may be added only as a separate documented method.

**Dashboards:** planner suggests up to six cards using valid schema fields; each card passes the same query validator/executor. A fixed grid is sufficient. Record per-card evidence and failures; show partial results honestly. Limit dashboard concurrency and total deadline separately. Saved cards reuse persisted artifacts and display source versions.

## 8. Conversation, semantic search, caching
Context stores structured analytical intent as well as messages. Follow-ups reuse filters/groupings only when applicable to the same dataset versions. On selected-data changes, revalidate context and ask for clarification when necessary. Bound recent messages and summarize older context without treating model summaries as computed evidence.

Semantic search indexes the question, grounded answer, conversation title, chart titles, and dataset names for successful analyses. The existing Gemini SDK generates `gemini-embedding-001` vectors with `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY` task types. Vectors are normalized and stored in SQLite with a model/dimension revision and content hash. Owner and source eligibility are checked before and after ranking; retrieval is capped at 500 recent candidates, top-k defaults to five and maxes at ten. A separate bounded index action handles older saved analyses. Deleting a source cascades its documents. Provider failure returns `SEARCH_UNAVAILABLE` for indexed searches; empty indexes return empty results. Search references reopen conversations, not newly computed answers.

Cache only successful, complete validated SQL query tables. Queries with `LIMIT` and queries without an explicit `ORDER BY` or scalar aggregate bypass caching. Key: owner ID, sorted dataset IDs/versions/hashes, snapshot size/mtime, canonical SQL AST, policy version, and result cap. TTL is 15 minutes, at most 128 entries and 64 MiB total; entries over 1 MiB are refused. The process-local cache loses entries on restart. Every request still authorizes sources, validates SQL, checks snapshot identity, builds fresh evidence, and saves a distinct analysis. `cache_hit` and lookup/query timing appear in analysis metadata. Dataset deletion evicts dependent entries. Explicit saved-query reruns skip model planning for single-source queries; ordinary natural-language questions still require planning.

## 9. Authentication and security
Use Argon2id password hashing and opaque random server sessions. Store token digests only; session lifetime defaults to 24 hours. Cookies are HttpOnly, SameSite=Lax, Secure under HTTPS. Use a same-origin frontend proxy for `/api`; state-changing requests require origin validation and a CSRF token. Local HTTP cookie settings must be explicit development configuration. Logout revokes the server session. Return generic login failures and rate-limit login attempts.

Owner-check every resource query, including nested message/analysis/card reads, search, download, deletion, and cached artifacts. Foreign-resource reads return a consistent not-found response. Escape user content in UI and HTML exports. No client-controlled paths, remote image URLs, generated executable HTML, or formula interpretation of CSV values. Keep provider keys server-only. Clearly state that schema/profile metadata is sent to the configured LLM and describe data retention.

## 10. Proposed API contracts
Prefix `/api/v1`; publish typed OpenAPI schemas. These are implementation targets.

| Method / path | Behavior |
| --- | --- |
| POST `/auth/register`, `/auth/login`, `/auth/logout` | Local account/session lifecycle |
| GET `/auth/me` | Current user |
| POST `/datasets` | Multipart uploads; per-file status and validation errors |
| GET `/datasets`, `/datasets/{id}` | Owner-scoped listing/profile |
| DELETE `/datasets/{id}` | Remove dataset and invalidate dependencies |
| POST `/conversations` | Create with selected dataset IDs |
| GET `/conversations/{id}` | Messages and bounded artifacts |
| PATCH `/conversations/{id}` | Update selected dataset IDs with context revalidation |
| POST `/conversations/{id}/messages` | Analyze or clarify a natural-language request |
| GET `/analyses/{id}` | Completed evidence or safe failure status |
| POST `/dashboards`, GET `/dashboards/{id}` | Generate/save and reopen dashboard |
| POST `/search` | Owner-scoped semantic query |
| POST `/search/index` | Index up to 20 missing recent saved analyses, within a 60-second deadline |
| POST `/analyses/{id}/rerun` | Revalidate and rerun a saved single-source query without model planning |
| POST `/reports/export` | Authorized analysis/dashboard IDs → HTML attachment |
| GET `/health/live`, `/health/ready` | Process and local dependency readiness |

Response envelope: `request_id`, `data`, optional `meta`. Error envelope: `request_id`, `error: {code, message, details}`; details must be sanitized. Status codes: 400/422 invalid input, 401 unauthenticated, 404 inaccessible resource, 413 upload too large, 429 limit reached, 502 provider failure, 504 timeout, 503 unavailable dependency. Never return internal paths or stack traces.

Analysis artifact fields: `id`, `status`, `answer`, `method`, `assumptions`, `dataset_versions`, `sql`, `table: {columns, rows, returned_rows, truncated}`, `charts`, `anomalies`, and `meta: {cache_hit, timings_ms}`. A clarification contains a user-facing question and no fabricated executed result.

## 11. Reports and observability
Generate an HTML attachment from authorized saved evidence with escaped text, embedded chart data/runtime, styled tables, query/method details, source versions, and UTC generation time. Limit report size and selected artifact count. HTML export is the committed bonus format; PDF export is optional future work. Test an exported file offline.

JSON operation logs allow only request ID, route template, status, duration, database timing/count, outcome, and cache state. Untrusted values, SQL, parameters, vectors, secrets, and exception messages are excluded. The authenticated `/health/metrics` endpoint exposes process-local operation counters without user labels. Liveness checks the process; readiness checks metadata schema and writable storage. Neither health route makes a paid provider request or claims search availability.

## 12. Testing and evaluation
Use synthetic sales/products/customer CSVs with documented date, quantity, price, revenue, and join semantics. Check in independently calculated expected answers and a deliberately anomalous fixture.

| Layer | Required coverage |
| --- | --- |
| Unit | CSV encoding/header/limit cases; SQL AST allow/deny; chart validity; IQR small/constant/null data; canonical cache keys; owner-scoped search ranking |
| Integration | Upload→query→chart→follow-up; multiple-file join; auth/logout and cross-owner denial; export; dashboard partial failures; deletion invalidation; provider malformed/failure responses |
| Execution safety | File/network scans, nested forbidden SQL, multiple statements, oversized query, timeout and cancellation cleanup, concurrency permit recovery |
| Evaluation | Known region revenue, monthly sales, top customers, defined underperformance, anomalies, clarification, prompt injection, schema hallucination |
| Delivery | Frontend typecheck/build; offline export; Docker clean start and restart persistence; screenshots and 10–30 second demo |

Inject provider fakes only in tests; live smoke tests require credentials and are reported separately. Score numeric correctness, schema-valid plans, supported charts, source-grounded explanations, and safe refusal independently. Require all deterministic sample answers and security checks to pass. Record actual measured timings and provider/model used; do not invent benchmark claims.

## 13. Implementation sequence and release gate
1. Scaffold and lock dependencies; migrations, auth, sample fixtures, Compose, typed client.
2. Upload/profiles and immutable snapshots; owner-scoped reads and failures.
3. Structured plans, SQL policy, isolated execution, evidence artifacts.
4. Chat UI, context, charts, summaries, anomalies, joins; verify core.
5. Dashboard/report/search/cache/logs; verify all six bonuses.
6. Evaluation/security checks, clean setup, README/diagram/screenshots/video.

Expected verification commands once scaffolded: `pytest`, backend lint/type checks as configured, frontend `npm run lint` (if defined), `npm run typecheck`, `npm run build`, and `docker compose up --build`. Do not describe these as having passed before running them.

Release requires passing PRD criteria, reproducible documented setup, honest limitations, no committed secrets/private data, bounded resource cleanup, and complete submission assets. This design targets a single-user-process local evaluation environment, not proven enterprise production scale.

Semantic search applies a 0.60 cosine-similarity floor before returning results. This initial heuristic was checked against synthetic sales paraphrases (top scores 0.65?0.71) and an unrelated leave query (maximum 0.54); it is not a probability or a universal relevance guarantee. Lower-scoring queries can return an empty result, including some relevant paraphrases. Recalibrate if the embedding model changes.

Individual saved analyses can be permanently deleted from Analyze using the confirmation action (`DELETE /api/v1/analyses/{id}`). The endpoint requires the authenticated owner and CSRF protection. Deletion cascades to the search document; direct retrieval, rerun and export of that ID become unavailable. Referencing dashboard cards become unavailable while other cards remain usable. Dataset files, conversation messages, other analyses, and already downloaded reports remain unchanged. This deletes the saved artifact, not the conversation text.

Uploads accept up to 10 files per request, 64 MiB per file and 256 MiB per multipart request. New analyses and dashboard source selection support up to five datasets, with up to four confirmed join relationships. Existing saved analyses and dashboard evidence remain readable, including earlier larger selections. Provider schema context (32,000 characters), SQL/result caps, deadlines, query memory, and concurrency limits remain enforced; large schemas may require selecting fewer or narrower sources.

Upload intake has a 180-second backend deadline and a 210-second proxy upstream deadline. The full checked-in Olist collection (nine CSVs, 120.34 MiB total) passes the CSV parser under these limits, including 1,000,163 geolocation rows. Large uploads use more memory because CSV profiling and proxy buffering are in memory; analytical query memory/time/result limits still apply independently.

Join configuration accepts an unordered, connected, directed acyclic tree rooted at one left-side dataset. Every right dataset has exactly one parent; each edge adds a new dataset. The server computes execution order without reversing edge directions or LEFT preservation semantics. Reorient conflicting edges explicitly; ambiguous directions, cycles, parallel edges, disconnected sources and incompatible columns are rejected. Integer/decimal keys are compatible; other types must match. Edges accept `left_dataset_id`, `left_column`, `right_dataset_id`, `right_column`, `join_type` (INNER/LEFT), alongside legacy `left`, `left_key`, `right`, `right_key`, `type`. Stored proposals retain the legacy field names and SQL is checked against the exact ordered graph. No migration is required.

Analyze supports adding/removing relationships and selecting both endpoints. Edits clear join/multiplication consent. Pairwise diagnostics flag source repetition; multiple expanding relationships also show a conservative fanout warning. Explicit multiplication consent is required to execute risky joins. Consent does not establish aggregate correctness: results may count or sum repeated records, and the answer/method disclose this. No automatic pre-aggregation rewrite or final multi-hop cardinality estimate is implemented. Upload limits remain ten files per batch; the five-dataset limit applies to new analysis selections.
