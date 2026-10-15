"""Run inside the production Linux image to verify real worker cleanup and limits."""

import asyncio
import multiprocessing
import os
import tempfile
from pathlib import Path
from time import monotonic
from uuid import uuid4

from app.executor import QueryBusy, QueryFailure, QueryTimeout, execute


def children() -> set[int]:
    path = Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children")
    return {int(value) for value in path.read_text().split()}


async def spawned(task: asyncio.Task) -> int:
    until = monotonic() + 5
    while monotonic() < until:
        child = {process.pid for process in multiprocessing.active_children()}
        if child:
            assert len(child) == 1, child
            return child.pop()
        if task.done():
            raise AssertionError(f"Query finished before a child was observed: {task.exception()}")
        await asyncio.sleep(0.01)
    raise AssertionError("Query child did not start")


def reaped(pid: int) -> None:
    assert not Path(f"/proc/{pid}").exists(), f"child {pid} still exists"
    assert pid not in {process.pid for process in multiprocessing.active_children()}, f"child {pid} still attached"
    assert not multiprocessing.active_children(), "multiprocessing still tracks a child"


async def run() -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    assert os.name == "posix"
    assert not multiprocessing.active_children()
    with tempfile.TemporaryDirectory(prefix="dbo-linux-probe-") as directory:
        root = Path(directory)
        parquet = root / "fixture.parquet"
        pq.write_table(pa.table({"c1": list(range(600)), "c2": ["x" * 3000] * 600}), parquet)
        name = f"dataset_{uuid4().hex}"
        source = [(name, str(parquet))]
        capacity = asyncio.Semaphore(1)

        async def normal() -> None:
            result = await execute(f"SELECT SUM(c1) AS total FROM {name}", source, 15, capacity)
            assert result["rows"] == [{"total": 179700}], result
            assert not multiprocessing.active_children(), children()

        async def capacity_free() -> None:
            await asyncio.wait_for(capacity.acquire(), 1)
            capacity.release()

        await normal()
        settings = await execute(
            "SELECT current_setting('memory_limit') AS memory_limit, "
            "current_setting('threads') AS threads, "
            "current_setting('enable_external_access') AS external, "
            "current_setting('autoinstall_known_extensions') AS extensions",
            [],
            15,
            capacity,
        )
        row = settings["rows"][0]
        assert row["threads"] == 1, row
        assert row["external"] is False and row["extensions"] is False, row
        amount, unit = row["memory_limit"].split()
        assert unit == "MiB" and 240 <= float(amount) <= 256, row
        await normal()

        heavy = "SELECT SUM(i) FROM range(1000000000000) AS t(i)"
        task = asyncio.create_task(execute(heavy, [], 1, capacity))
        pid = await spawned(task)
        try:
            await task
            raise AssertionError("Heavy query did not time out")
        except QueryTimeout:
            pass
        reaped(pid)
        await capacity_free()
        await normal()

        task = asyncio.create_task(execute(heavy, [], 10, capacity))
        pid = await spawned(task)
        until = monotonic() + 5
        while monotonic() < until:
            limits = Path(f"/proc/{pid}/limits").read_text()
            cpu = limits.split("Max cpu time", 1)[1].splitlines()[0]
            memory = limits.split("Max address space", 1)[1].splitlines()[0]
            if "6" in cpu and "2147483648" in memory:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError(f"Expected child OS limits not applied: {cpu}; {memory}")
        try:
            await execute("SELECT 1 AS value", [], 1, capacity)
            raise AssertionError("Concurrent query was not rejected")
        except QueryBusy:
            pass
        task.cancel()
        try:
            await task
            raise AssertionError("Cancellation was ignored")
        except asyncio.CancelledError:
            pass
        reaped(pid)
        await capacity_free()
        await normal()

        try:
            await execute(f"SELECT unknown FROM {name}", source, 15, capacity)
            raise AssertionError("Invalid query succeeded")
        except QueryFailure:
            pass
        await capacity_free()
        await normal()

        limited = await execute(f"SELECT c1 FROM {name} ORDER BY c1", source, 15, capacity)
        assert limited["returned_rows"] == 500 and limited["truncated"] is True, limited
        try:
            await execute(f"SELECT c2 FROM {name}", source, 15, capacity)
            raise AssertionError("Oversized result succeeded")
        except QueryFailure as error:
            assert "1 MiB" in str(error), error
        await capacity_free()
        await normal()

        try:
            await execute("SELECT REPEAT('x', 400000000) AS giant", [], 15, capacity)
            raise AssertionError("Memory-heavy query succeeded")
        except QueryFailure as error:
            assert not isinstance(error, QueryTimeout), "Memory-heavy query only reached the deadline"
            assert "1 MiB" not in str(error), f"Memory ceiling was not reached before output handling: {error}"
        await capacity_free()
        await normal()

        assert list(root.iterdir()) == [parquet], "Unexpected temporary resource remains"
    assert not root.exists(), "Probe temporary directory remains"
    assert not multiprocessing.active_children(), "Query child remained after cleanup"
    print("PASS Linux child cancellation, deadline, limits, failure, recovery, and cleanup")


if __name__ == "__main__":
    asyncio.run(run())
