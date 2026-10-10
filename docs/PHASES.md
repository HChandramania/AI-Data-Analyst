# Delivery phases

The PRD/TRD sequence is grouped here as Phases 0–6. The supplied documents do not contain a separately numbered seven-phase plan; this mapping retains every agreed feature and isolates the requested foundation from authentication.

| Phase | Scope and gate | Status |
| --- | --- | --- |
| 0 — Repository foundation | Locked dependencies, SQLite migrations, health/logging, application shell/proxy, synthetic fixtures, local/Docker setup and CI. All foundation acceptance gates must pass. | Accepted. Browser viewport, keyboard, loading, empty, ready, unavailable, and retry checks passed. Docker clean build/start, migration ordering, direct/proxied readiness, non-root storage write, recreation persistence, and disposable cleanup passed; see VERIFICATION.md. |
| 1 — Identity and datasets | Registration/login/logout, ownership, bounded CSV intake, profiles, immutable snapshots; authentication/upload/isolation checks. | Implemented and API/Docker verified; visual/mobile browser gate unverified, so Phase 2 gate remains open. See VERIFICATION.md. |
| 2 — Computed answers | Provider boundary, validated structured plans, SQL policy, isolated execution, persisted evidence; known numeric answers and execution security. | Not started |
| 3 — Core analyst experience | Conversation context, charts, grounded summaries, anomalies, explicit joins and clarifications; core end-to-end journey. | Not started |
| 4 — Agreed bonuses | Saved dashboards, offline HTML export, local semantic search, version-aware caching, expanded observability; owner isolation and all six bonuses including Phase 1 authentication. | Not started |
| 5 — Hardening and evaluation | Security/failure fixtures, numeric/chart/narrative/refusal evaluation, limits, cleanup, responsive/accessibility checks, clean setup. | Not started |
| 6 — Submission | Final README/architecture, screenshots, 10–30 second demo, assignment audit; only verified feature claims. | Not started |

Phase 1 adds Argon2id, multipart intake, and Parquet tooling. Analysis and the remaining bonuses are planned, not delivered.
