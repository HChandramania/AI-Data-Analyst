"""Targeted production-image Phase 3 execution probe; no provider or network."""

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4


async def probe(root):
    # Keep the spawn entrypoint light, like app.serve. Heavy fixture/provider imports
    # belong in the parent, not in every execution child before its CPU limit is set.
    import pyarrow as pa
    import pyarrow.parquet as pq

    from app.anomalies import detect
    from app.charts import ChartIntent, build_chart
    from app.executor import QueryFailure, execute
    from app.joins import JoinKey, diagnostics, validate_keys
    from app.planner import AnomalyIntent
    from app.sql_policy import validate_sql

    datasets, sources = [], []
    values = [list(range(1, 25)) + [1000, None], [1, 2, 3]]
    for index, column in enumerate(values):
        dataset_id = uuid4()
        path = root / f"{dataset_id}.parquet"
        pq.write_table(pa.table({"c1": column, "c2": list(range(len(column)))}), path)
        datasets.append(
            SimpleNamespace(
                id=dataset_id,
                row_count=len(column),
                schema_json=json.dumps(
                    [
                        {"id": "c1", "name": "value", "type": "integer"},
                        {"id": "c2", "name": "record", "type": "integer"},
                    ]
                ),
            )
        )
        sources.append((f"dataset_{dataset_id.hex}", str(path)))
    settings = SimpleNamespace(query_timeout_seconds=10)
    capacity = asyncio.Semaphore(1)
    key = JoinKey(left=datasets[0].id, right=datasets[1].id, left_key="c1", right_key="c1", type="inner")
    validate_keys([key], datasets)
    facts = await diagnostics([key], sources, settings, capacity)
    assert facts[0]["matched_rows"] == 3 and facts[0]["left_unmatched_rows"] == 23
    registry = {s[0]: {"c1", "c2"} for s in sources}
    sql = validate_sql(
        f"SELECT a.c1 AS x, b.c2 AS y FROM {sources[0][0]} a INNER JOIN {sources[1][0]} b ON a.c1=b.c1 ORDER BY x",
        registry,
        [key],
    )
    result = await execute(sql, sources, 10, capacity)
    assert result["rows"] == [{"x": 1, "y": 0}, {"x": 2, "y": 1}, {"x": 3, "y": 2}]
    for kind in ("bar", "line", "pie", "scatter"):
        artifact = build_chart(
            ChartIntent(type=kind, title="Probe", x="x", y="y", x_label="Value", y_label="Record"), result
        )
        assert len(artifact["points"]) == 3
    anomaly = await detect(datasets[0], AnomalyIntent(measure="c1"), sources[:1], settings, capacity)
    assert anomaly["flagged_count"] == 1 and anomaly["table"]["rows"][0]["row_reference"] == 25
    assert anomaly["groups"][0]["null_count"] == 1
    try:
        await execute(f"SELECT 1.0/0 AS value FROM {sources[0][0]}", sources[:1], 10, capacity)
    except QueryFailure as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("Non-finite evidence must fail safely")
    assert (await execute(sql, sources, 10, capacity))["rows"] == result["rows"]
    assert capacity._value == 1
    print(
        json.dumps(
            {
                "joined_rows": result["rows"],
                "chart_types": 4,
                "anomaly_flags": anomaly["flagged_count"],
                "capacity_released": True,
                "nonfinite_rejected_and_recovered": True,
            }
        )
    )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        asyncio.run(probe(Path(directory)))
