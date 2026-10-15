"""Bounded DuckDB execution in a child process with no generated code execution."""

import asyncio
import json
import math
import multiprocessing
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

RESULT_ROWS = 500
RESULT_BYTES = 1024 * 1024


class QueryFailure(Exception):
    pass


class QueryBusy(QueryFailure):
    pass


class QueryTimeout(QueryFailure):
    pass


def _json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise QueryFailure("Query returned non-finite values. Refine the calculation.")
    if isinstance(value, (Decimal, date, datetime)):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _worker(conn, sql: str, sources: list[tuple[str, str]]):
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "DBO_GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "DBO_OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "DBO_GROQ_API_KEY",
    ):
        os.environ.pop(key, None)
    try:
        if os.name != "nt":
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (6, 7))
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        import duckdb

        db = duckdb.connect(
            database=":memory:",
            config={
                "memory_limit": "256MB",
                "threads": "1",
                "autoinstall_known_extensions": "false",
                "autoload_known_extensions": "false",
            },
        )
        try:
            for table, path in sources:
                if not re.fullmatch(r"dataset_[0-9a-f]{32}", table):
                    raise QueryFailure("Invalid registered table.")
                db.execute(f"CREATE TABLE {table} AS SELECT * FROM read_parquet(?)", [path])
            db.execute("SET enable_external_access = false")
            cursor = db.execute(f"SELECT * FROM ({sql}) AS bounded_result LIMIT {RESULT_ROWS + 1}")
            names = [column[0] for column in cursor.description]
            if len(names) != len(set(names)) or len(names) > 50:
                raise QueryFailure("Result columns are ambiguous or exceed limit.")
            rows = []
            used = 0
            while len(rows) <= RESULT_ROWS:
                batch = cursor.fetchmany(min(50, RESULT_ROWS + 1 - len(rows)))
                if not batch:
                    break
                for values in batch:
                    row = dict(zip(names, (_json_value(value) for value in values), strict=True))
                    used += len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
                    if used > RESULT_BYTES:
                        raise QueryFailure("Result exceeds 1 MiB. Narrow the question.")
                    rows.append(row)
            conn.send(
                {
                    "ok": True,
                    "columns": names,
                    "types": {column[0]: str(column[1]) for column in cursor.description},
                    "rows": rows[:RESULT_ROWS],
                    "returned_rows": min(len(rows), RESULT_ROWS),
                    "truncated": len(rows) > RESULT_ROWS,
                }
            )
        finally:
            db.close()
    except QueryFailure as exc:
        conn.send({"ok": False, "message": str(exc)})
    except Exception:
        conn.send({"ok": False, "message": "Query could not be completed safely."})
    finally:
        conn.close()


def source_paths(data_dir: Path, datasets) -> list[tuple[str, str]]:
    root = data_dir.resolve()
    sources = []
    for dataset in datasets:
        path = (root / dataset.parquet_path).resolve()
        if not path.is_relative_to(root / "datasets") or not path.is_file():
            raise QueryFailure("Selected dataset snapshot is unavailable.")
        sources.append((f"dataset_{dataset.id.hex}", str(path)))
    return sources


async def execute(sql: str, sources: list[tuple[str, str]], timeout: int, capacity: asyncio.Semaphore) -> dict:
    try:
        await asyncio.wait_for(capacity.acquire(), timeout=0.1)
    except TimeoutError:
        raise QueryBusy("Query capacity reached.") from None
    process = None
    parent = None
    try:
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_worker, args=(child, sql, sources), daemon=True)
        process.start()
        child.close()
        if not await asyncio.to_thread(parent.poll, timeout):
            raise QueryTimeout("Query timed out.")
        try:
            result = parent.recv()
        except EOFError:
            await asyncio.to_thread(process.join, 0.1)
            raise QueryFailure(f"Query process stopped unexpectedly (exit code {process.exitcode}).") from None
        if not result.get("ok"):
            raise QueryFailure(result.get("message", "Query failed."))
        return result
    finally:
        if process is not None:
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 2)
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 2)
            process.close()
        if parent is not None:
            parent.close()
        capacity.release()
