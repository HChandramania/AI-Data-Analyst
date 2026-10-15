# Submission readiness — Phase 6C

Source packaging is prepared; final submission acceptance remains open. This checklist follows PRD/TRD's recorded assignment requirements. The original assignment PDF is not present in the project root; a fresh comparison against that authoritative PDF was not performed.

| Deliverable | Status / evidence |
| --- | --- |
| Core and six agreed bonuses | Implemented with deterministic tests; live embedding relevance, live follow-up/join and manual UI gates remain open. |
| Setup | README local/Docker commands, locked dependencies, environment examples and migrations through `0005` included. Current Docker restart gate remains open. |
| Backend verification | Exact final count/command in [VERIFICATION.md](VERIFICATION.md), including XLSX regression. |
| Frontend verification | Historical lint/typecheck/build passed; no frontend changes in Phase 6C. |
| Limits | README documents compressed 64 MiB/file, 256 MiB/request and 64 MiB expanded XLSX cap; workbook parsing is not fully memory-sandboxed. |
| Architecture | [Current diagram](architecture/README.md) covers implemented services and persistence. |
| Sample data | Synthetic data, provenance, expected-answer oracle and independent verifier included. |
| Source package | From root run `backend/.venv/Scripts/python.exe docs/package_submission.py`. ZIP and SHA-256 manifest under ignored `.verification/submission`; excludes credentials, runtime data, dependencies and build outputs. |
| Screenshots | Missing. Capture real dataset profile, answer/chart/SQL and saved dashboard with synthetic data; label test-provider output. Add files and README links after capture. |
| 10–30 second video | Missing. Record the real 25-second sequence below and link it in README. A storyboard does not satisfy this requirement. |
| Repository/live URL | No publication, commit or push performed; no URL supplied. |

## Demo capture sequence (25 seconds)

Use synthetic `analysis_flat.csv` and a prepared authenticated conversation. Obtain explicit permission before any paid provider call; visibly label fixture-provider recordings.

| Time | Screen/action |
| --- | --- |
| 0–5s | Show uploaded sample profile and selected dataset. |
| 5–12s | Show completed regional chart/table (South USD 1,800, total USD 3,760); expand Method/SQL. |
| 12–18s | Show completed contextual monthly follow-up (USD 360 / 1,000 / 2,400). |
| 18–25s | Reopen saved dashboard and initiate offline HTML export. |

## Remaining acceptance

1. Restore Docker; verify production startup/migration `0005`, volume persistence and restart.
2. With paid-call authorization and real credentials, verify embedding relevance and live follow-up/confirmed joins.
3. Complete desktop/mobile semantic search/reopen and remaining UI, keyboard/zoom/reduced-motion and report-print checks.
4. Capture actual screenshots/video, link them in README and repackage.
5. Compare against the original assignment PDF; publish/share only with user authorization.

The archive is a review artifact. Missing media and acceptance gates remain incomplete; owner-exported reports are independent data copies and only synthetic fixtures belong in submission media.
