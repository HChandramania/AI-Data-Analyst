# Digital Back Office AI Data Analyst

Phase 1 provides local accounts and owner-scoped CSV intake. Analysis, generated SQL, charts, anomalies, dashboards, reports, search, and caching remain planned for later phases. See [delivery phases](docs/PHASES.md), [verification](docs/VERIFICATION.md), [requirements](prd.md), and [technical design](trd.md).

## Local run

Prerequisites: Python 3.13, uv, Node.js 24, npm. In separate terminals from this repository:

```powershell
cd backend
Copy-Item .env.example .env
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen python -m app.serve
```

```powershell
cd frontend
Copy-Item .env.example .env.local
npm.cmd ci
npm.cmd run dev
```

Open `http://localhost:3000/register`, create an account, then open Datasets. Upload CSV files or use the checked-in synthetic sales, customers, and products through **Use sample data**. Inspect profiles and previews, open Analyze to select up to five datasets, and sign out. Analysis questions remain unavailable until Phase 2. On macOS/Linux replace `Copy-Item` with `cp` and `npm.cmd` with `npm`.

`DBO_PUBLIC_ORIGIN` must equal the browser origin. `DBO_ALLOW_INSECURE_COOKIES=true` is explicit for local HTTP only. Set it to `false` when serving HTTPS. Session cookies are HttpOnly and SameSite=Lax; the readable CSRF cookie is paired with an `X-CSRF-Token` header and an exact origin check. The backend stores only SHA-256 session token digests, revokes them on logout, and expires them after 24 hours. Passwords use Argon2id. Do not expose this local setup as a public service.

## CSV behavior and limits

Upload up to **three files per request**, **10 MiB per file**, **32 MiB per request**, **100,000 data rows per file**, and **50 columns per file**. Two intake requests can run concurrently in one API process. Only UTF-8/UTF-8 BOM comma-delimited CSV with a nonblank unique header and at least one valid data row is accepted. The receiver caps each part while streaming, including when `Content-Length` is absent. Files in a batch receive independent accepted/rejected results. A rejected file leaves no dataset.

Snapshots are immutable Parquet files under the private backend data directory, beside preserved CSV originals. A new upload always gets a new ID and version 1. Identifiers and date-like values remain text. Entire columns of unambiguous integers, decimals (up to six fractional places), or boolean literals are inferred as typed values; mixed or uncertain columns remain text. Only empty fields become null. No rows are dropped or imputed. Previews show at most 50 rows and explicit truncation. Profiles show types, missing counts/rates, duplicate row count, and warnings. Deleting a dataset removes its stored files and metadata; dependent analysis artifacts do not exist yet.

The browser uses a same-origin Next.js API proxy. Uploaded files are not publicly served. Metadata, sessions, originals, and snapshots persist in `backend/data` locally or the Compose `backend_data` volume. Do not use `docker compose down --volumes` on data you want to retain. One backend process is supported.

## Docker

```powershell
Copy-Item .env.example .env
docker compose up --build -d --wait
```

Open `http://localhost:3000/register`. The migration service runs before the backend. The Compose HTTP setup explicitly enables insecure cookies on the loopback host; use HTTPS and disable that setting for any nonlocal deployment.

## Checks

From `backend/`: `uv run --frozen pytest -q`, `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`, `uv run --frozen alembic check`.

From `frontend/`: `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build`.

See [verification](docs/VERIFICATION.md) for actual results and unverified gates. No provider credentials are needed for Phase 1. The synthetic fixtures are documented in [sample_data/README.md](sample_data/README.md).
