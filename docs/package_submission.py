"""Package explicit source paths, excluding runtime data and credentials."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
TREES = (
    ".github/workflows",
    "backend/app",
    "backend/migrations",
    "backend/tests",
    "frontend/src",
    "frontend/public",
    "frontend/scripts",
    "docs",
    "sample_data",
)
FILES = (
    "AGENTS.md",
    "PRD.md",
    "TRD.md",
    "README.md",
    "DESIGN.md",
    ".gitignore",
    ".env.example",
    "docker-compose.yml",
    "backend/.dockerignore",
    "backend/.env.example",
    "backend/alembic.ini",
    "backend/Dockerfile",
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/live_dashboard_smoke.py",
    "backend/live_gemini_smoke.py",
    "frontend/.dockerignore",
    "frontend/.env.example",
    "frontend/Dockerfile",
    "frontend/eslint.config.mjs",
    "frontend/next-env.d.ts",
    "frontend/next.config.ts",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/postcss.config.mjs",
    "frontend/tsconfig.json",
)


def main():
    candidates = {ROOT / name for name in FILES}
    for tree in TREES:
        candidates.update(path for path in (ROOT / tree).rglob("*") if path.is_file())
    paths = []
    for path in sorted(candidates):
        relative = path.relative_to(ROOT)
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Unsafe package path: {relative}")
        if any(
            part
            in {
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                "node_modules",
                ".next",
                "data",
                ".verification",
            }
            for part in relative.parts
        ):
            continue
        if (
            path.name.startswith(".env") and path.name != ".env.example"
        ) or path.suffix in {".pyc", ".db", ".sqlite", ".log", ".tsbuildinfo"}:
            continue
        if not path.is_file():
            raise FileNotFoundError(relative)
        paths.append(path)
    output = ROOT / ".verification" / "submission"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "ai-data-analyst-source.zip"
    entries = {}
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        for path in paths:
            data = path.read_bytes()
            name = path.relative_to(ROOT).as_posix()
            package.writestr(name, data)
            entries[name] = hashlib.sha256(data).hexdigest()
    with ZipFile(archive) as package:
        assert package.testzip() is None
        assert set(package.namelist()) == set(entries)
        assert all(
            hashlib.sha256(package.read(name)).hexdigest() == digest
            for name, digest in entries.items()
        )
    manifest = {
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Verified {len(entries)} files; {archive.stat().st_size} bytes; SHA-256 {manifest['archive_sha256']}"
    )


if __name__ == "__main__":
    main()
