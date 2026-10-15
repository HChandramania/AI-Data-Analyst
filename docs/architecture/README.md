# Current architecture

```mermaid
flowchart TD
  Browser[Browser: datasets, analysis, dashboards, search, export] -->|Same-origin cookies and CSRF| Next[Next.js proxy]
  Next --> API[FastAPI: one process]
  API --> Auth[Session and owner authorization]
  Auth --> Intake[Bounded CSV/XLS/XLSX intake and profiling]
  Intake --> Files[(Private originals and Parquet snapshots)]
  Auth --> Analysis[Analysis: bounded context and explicit join consent]
  Analysis --> Gemini[Gemini typed planning: schema/context only]
  Gemini --> Policy[Independent read-only SQL AST validation]
  Policy --> Cache[Owner/version/snapshot-bound cache]
  Cache --> Worker[Deadline-bound DuckDB child]
  Files --> Worker
  Worker --> Evidence[Computed tables, charts, IQR, method and SQL]
  Evidence --> DB[(SQLite metadata, evidence, dashboards and search vectors)]
  Evidence --> Embedding[Gemini embedding: bounded history metadata]
  Embedding --> DB
  Auth --> Search[Owner/source-validated semantic retrieval]
  DB --> Search
  Auth --> Dashboard[Bounded sequential dashboard cards]
  Dashboard --> Analysis
  Auth --> Export[Reauthorized evidence to escaped offline HTML]
  DB --> Export
  Migration[Alembic through 0005] --> DB
  API --> Logs[Allowlisted JSON logs and authenticated counters]
```

Ownership and source identity are rechecked for reads, cache hits and exports. Model output and dataset text cannot authorize execution. Only registered snapshots reach DuckDB; generated Python/shell commands never execute. Charts/narratives use computed evidence. Join keys/type require explicit version-bound confirmation.

SQLite enables foreign keys, WAL and bounded busy waits. Session contexts close or roll back; provider calls occur outside long-lived application transactions. Lifespan disposes the engine. Migrations are explicit; Compose waits for migration completion and backend readiness before frontend startup.

Local storage is `backend/data`; Compose uses `backend_data`. Backend runs as UID/GID 10001 and frontend as `node`. One backend process owns concurrency, cache and counters; cache/counters reset while persisted metadata/snapshots survive restart.

Readiness checks writable storage/current schema, without provider calls or semantic-availability claims. Logs exclude arbitrary text, credentials, SQL and result rows. Credentials stay server-side.

Intake caps compressed files at 10 MiB and declared XLSX expansion at 64 MiB. Workbook parsing is not fully memory-sandboxed. DuckDB children enforce memory/thread/deadline limits; Linux adds OS CPU/address-space limits. This local runtime is not a general-purpose hostile-file/code sandbox. See [verification](../VERIFICATION.md) for actual evidence and open gates.
