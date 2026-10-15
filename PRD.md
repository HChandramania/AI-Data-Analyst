# Product Requirements Document

## Implementation status

Confirmed joins now use unique planner column references to avoid collisions between dataset-local IDs. Three live planning/execution checks against the sales/customer fixtures matched regional totals; browser join acceptance remains to be verified.

SQL/dashboard planning supports bounded Gemini → OpenRouter → Groq fallback when server-side keys are configured; semantic embeddings remain Gemini-only. Mocked-provider verification is recorded separately from live acceptance.
Phases 0–5 implement the foundation, authentication/CSV intake, computed analysis, charts, follow-up intent, IQR anomalies, explicit joins, saved dashboards, offline HTML reports, semantic history search, bounded execution caching, and safe telemetry. Verification and remaining gates are in `docs/VERIFICATION.md`. Phase 5 automated tests use a fake embedding provider; live embedding quality, earlier live follow-up/join, and responsive/manual gates remain open. The requirements below remain the full product target.

## 1. Product and goal
**Working name:** Digital Back Office AI Data Analyst.

Enable a business user to upload CSV files, ask questions in plain language, and receive accurate computed answers, charts, business summaries, and understandable anomaly explanations. Deliver a polished, reviewable internship submission within a two-day implementation window.

The differentiator is trustworthy analysis: every numeric answer can be traced to a dataset version, executed query, and computed result. Visible method explanations describe the calculation and assumptions, rather than exposing private model reasoning.

## 2. Source and scope
Source: `Software Engineer Intern Assignment.pdf`, headed “AI Engineer Assignment,” Digital Back Office Ltd. The assignment leaves the technology stack open.

| Scope | Requirements |
| --- | --- |
| Mandatory | Upload and validate one or more CSVs; natural-language questions; insights and summaries; bar/line/pie/scatter charts; SQL and/or Pandas generation; explained anomalies; response explanations; session conversation context |
| Agreed optional bonuses | Report export, dashboard generation, semantic search, caching, authentication, observability/logging |
| Supporting implementation | Data-quality profiling, structured tool planning, small evaluation suite, explicit multi-file joins |
| Deferred | Forecasting, unrestricted Python execution, autonomous agent crews, scheduled jobs, enterprise roles, external database connectors, real-time streaming |

Multiple CSV uploads are mandatory. Cross-file analysis is listed separately as a bonus in the PDF; this plan supports explicit joins without guessing relationships. SQL satisfies the assignment's SQL and/or Pandas requirement.

## 3. Users and primary journey
The primary user is an analyst or operator exploring sales/customer/product data. The evaluator needs a reproducible application with clear evidence of engineering quality.

1. Sign in using a documented local demo account or register a local account.
2. Upload one or more CSVs; see accepted files, inferred types, row counts, and quality warnings.
3. Select the datasets for a conversation and ask a business question.
4. Receive a computed answer with a table or chart, concise method, SQL, and dataset references.
5. Ask a contextual follow-up such as “Now break that down by month.”
6. Request anomalies or generate a dashboard from the selected data.
7. Search previous analyses by meaning and export selected results as a report.

## 4. Functional requirements and acceptance

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| C01 | CSV intake | Multiple valid CSVs can be uploaded independently; invalid/empty/oversized files fail with actionable errors; headers, types, and row counts are shown. A failed file does not corrupt an accepted file. |
| C02 | Data quality | Show missing values, duplicate-row count, inferred types, and parsing warnings. Do not silently impute, drop, or reinterpret data. |
| C03 | Questions | Highest-revenue region and top-five customers match independently verified sample-data results; unsupported or ambiguous questions produce clarification. |
| C04 | Insights | Summaries reference computed aggregates and identify the datasets used; no invented values or causal claims. |
| C05 | Charts | Valid bar, line, pie, and scatter charts render with titles, units where known, labeled axes/legend, and a supporting result table. Unsupported chart/data combinations give an explanation. |
| C06 | Generated code | Show the validated SQL used for execution and allow copying it. A request to generate SQL returns an explanation of the tables and columns. |
| C07 | Anomalies | Return flagged records/groups with rule, baseline, threshold, sample size, and caveat. Constant or too-small data produces an honest “insufficient evidence” result. |
| C08 | Explainability | Answers identify calculation, filters, grouping, dataset versions, assumptions, and limitations; figures match the query result. |
| C09 | Context | A follow-up inherits the selected dataset and relevant prior analytical intent; dataset changes cannot silently reuse an incompatible plan. |
| C10 | Multiple files | User can select several datasets and confirm join keys; ambiguous joins require clarification; show join type, key uniqueness, and unmatched counts. |
| B01 | Export reports | Download a self-contained HTML report containing selected answers, charts, result tables, SQL, assumptions, dataset versions, and generation time. It opens offline without remote assets. |
| B02 | Dashboard generation | Produce a dashboard of at most six computed cards/charts based on the chosen datasets. Show real empty/error states and allow saving/reopening it. |
| B03 | Semantic search | Meaning-based search retrieves the owner's past successful analyses, with source titles and excerpts. For example, “regional performance” can retrieve an analysis titled “Revenue by territory.” |
| B04 | Caching | Repeated equivalent structured analyses can reuse execution results; responses indicate cache hits. New dataset versions or different owners cannot reuse stale/foreign results. |
| B05 | Authentication | Register/login/logout works; anonymous users cannot access private resources; a second user cannot read/search/export another user's data by guessing IDs. |
| B06 | Observability | Logs include request ID, timings, provider/model identifier, query outcome, and cache state; health endpoints reflect dependency readiness; sensitive content is excluded. |

“Underperforming” needs an explicit comparison such as revenue below a selected baseline. Do not invent a target. Monthly trends require a user-confirmed date column when inference is uncertain. Revenue must come from an existing field or an explicitly explained formula.

## 5. Experience requirements
- Main workspace: dataset sidebar, central conversation, result cards with chart/table tabs, and expandable SQL/method details.
- Clearly distinguish uploading, profiling, planning, querying, and failed analysis states. Preserve the user's question when an operation fails.
- Make the first successful analysis easy: sample data, suggested questions, and a visible dataset selection.
- Provide readable responsive layouts, keyboard-accessible controls, adequate contrast, and meaningful chart labels.
- Dashboard and export should reuse successful analysis artifacts; do not recompute numbers with a separate narrative pipeline.

## 6. Proposed operating limits
XLSX intake also rejects archives exceeding 64 MiB of total uncompressed entries before workbook parsing.
Initial limits: 64 MiB per CSV, 1,100,000 rows per CSV, 50 columns, five datasets per analysis, 500 returned table rows, and six dashboard cards. These are design choices, not assignment requirements. Enforce and document them consistently; adjust only after measurement.

Support UTF-8 and UTF-8 BOM CSVs with comma delimiters initially. Preserve originals and document unsupported formats. Retain uploaded data until owner deletion; deleting a dataset also invalidates related analyses/search/cache as defined in the technical design.

No latency or scale claims without measurements. A successful local sample-data demo and bounded execution are release requirements.

## 7. Two-day delivery plan
| Window | Deliverable and gate |
| --- | --- |
| Day 1, first block | Scaffold, Docker/database, authentication, sample data, CSV validation/profiling; pass upload and owner isolation checks |
| Day 1, middle block | Structured planning, read-only SQL validation/execution, evidence-backed responses; verify known business questions |
| Day 1, final block | Charts, context, insights, anomalies, explicit joins; core end-to-end demo works |
| Day 2, first block | Saved dashboards, report export, semantic search, version-aware caching, logs/health checks |
| Day 2, middle block | Security/failure tests, evaluation fixtures, clean-start checks, UI polish |
| Day 2, final block | README, architecture diagram, screenshots, 10–30 second demo, submission audit; reserve time for defects |

This is an aggressive schedule. Implement small versions of each bonus: local sessions, local embeddings, process-local bounded caching, fixed dashboard layout, HTML export, and structured logs. Avoid adding Redis, Kafka, Kubernetes, or a separate worker service to the initial submission.

## 8. Release and submission checklist
- Complete source code in a GitHub repository with no secrets or private uploaded data.
- README: setup, environment variables, sample questions, stack decisions, limits, assumptions, security model, completed vs deferred scope, and test instructions.
- Architecture diagram committed and shown in README.
- Both screenshots and a short demo video or live app link in README, following the assignment wording.
- A 10–30 second demo video supplied with the repository link; a live link does not replace the separately requested submission video.
- Docker support and checked-in synthetic sample datasets with provenance and expected answers.
- All mandatory flows and six agreed bonuses demonstrated; relevant tests and frontend build pass; measured results reported honestly.

## 9. Main risks
LLM mistakes are mitigated by structured validation and deterministic computation. Arbitrary query execution is mitigated by restricted SQL and process isolation. Ambiguous business language is mitigated by clarification. Provider availability is mitigated by explicit errors and an injectable fake for tests only. Time risk is mitigated by shallow, usable bonuses and an early core demo.

Semantic search applies a 0.60 cosine-similarity floor before returning results. This initial heuristic was checked against synthetic sales paraphrases (top scores 0.65?0.71) and an unrelated leave query (maximum 0.54); it is not a probability or a universal relevance guarantee. Lower-scoring queries can return an empty result, including some relevant paraphrases. Recalibrate if the embedding model changes.

Individual saved analyses can be permanently deleted from Analyze using the confirmation action (`DELETE /api/v1/analyses/{id}`). The endpoint requires the authenticated owner and CSRF protection. Deletion cascades to the search document; direct retrieval, rerun and export of that ID become unavailable. Referencing dashboard cards become unavailable while other cards remain usable. Dataset files, conversation messages, other analyses, and already downloaded reports remain unchanged. This deletes the saved artifact, not the conversation text.

Uploads accept up to 10 files per request, 64 MiB per file and 256 MiB per multipart request. New analyses and dashboard source selection support up to five datasets, with up to four confirmed join relationships. Existing saved analyses and dashboard evidence remain readable, including earlier larger selections. Provider schema context (32,000 characters), SQL/result caps, deadlines, query memory, and concurrency limits remain enforced; large schemas may require selecting fewer or narrower sources.

Join configuration accepts an unordered, connected, directed acyclic tree rooted at one left-side dataset. Every right dataset has exactly one parent; each edge adds a new dataset. The server computes execution order without reversing edge directions or LEFT preservation semantics. Reorient conflicting edges explicitly; ambiguous directions, cycles, parallel edges, disconnected sources and incompatible columns are rejected. Integer/decimal keys are compatible; other types must match. Edges accept `left_dataset_id`, `left_column`, `right_dataset_id`, `right_column`, `join_type` (INNER/LEFT), alongside legacy `left`, `left_key`, `right`, `right_key`, `type`. Stored proposals retain the legacy field names and SQL is checked against the exact ordered graph. No migration is required.

Analyze supports adding/removing relationships and selecting both endpoints. Edits clear join/multiplication consent. Pairwise diagnostics flag source repetition; multiple expanding relationships also show a conservative fanout warning. Explicit multiplication consent is required to execute risky joins. Consent does not establish aggregate correctness: results may count or sum repeated records, and the answer/method disclose this. No automatic pre-aggregation rewrite or final multi-hop cardinality estimate is implemented. Upload limits remain ten files per batch; the five-dataset limit applies to new analysis selections.
