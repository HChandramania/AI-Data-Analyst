"""Server-authored IQR queries evaluate full snapshots, not truncated result tables."""

import json

from app.executor import execute
from app.sql_policy import SqlRejected


async def detect(dataset, intent, sources, settings, capacity):
    columns = {c["id"]: c for c in json.loads(dataset.schema_json)}
    if intent.measure not in columns:
        raise SqlRejected("Unknown anomaly measure.")
    empty_measure = columns[intent.measure].get("missing_count") == dataset.row_count
    if not empty_measure and columns[intent.measure]["type"] not in {"integer", "decimal"}:
        raise SqlRejected("Anomalies require a registered numeric measure.")
    if intent.group and intent.group not in columns:
        raise SqlRejected("Unknown anomaly group.")
    # Identifiers come exclusively from the authorized schema; no model SQL is used here.
    measure = intent.measure
    value_expression = "CAST(NULL AS DOUBLE)" if empty_measure else measure
    group = intent.group or "NULL"
    table = f"dataset_{dataset.id.hex}"
    base = (
        f"WITH observations AS (SELECT ROW_NUMBER() OVER () AS row_reference, {value_expression} AS value, "
        f"{group} AS group_value FROM {table}), stats AS (SELECT group_value, COUNT(value) AS sample_size, "
        "COUNT(*)-COUNT(value) AS null_count, QUANTILE_CONT(value, 0.25) AS q1, "
        "QUANTILE_CONT(value, 0.75) AS q3 FROM observations GROUP BY group_value), "
        "bounds AS (SELECT *, q1-1.5*(q3-q1) AS lower_bound, q3+1.5*(q3-q1) AS upper_bound FROM stats), "
        "evaluated AS (SELECT o.*, b.sample_size, b.null_count, b.q1, b.q3, b.lower_bound, b.upper_bound, "
        "(b.sample_size>=20 AND b.q3>b.q1 AND (o.value<b.lower_bound OR o.value>b.upper_bound)) AS flagged "
        "FROM observations o JOIN bounds b ON o.group_value IS NOT DISTINCT FROM b.group_value) "
    )
    summary_sql = base + (
        "SELECT group_value, sample_size, null_count, q1, q3, lower_bound, upper_bound, "
        "COUNT(*) FILTER (WHERE flagged) AS flagged_count FROM evaluated "
        "GROUP BY group_value, sample_size, null_count, q1, q3, lower_bound, upper_bound ORDER BY group_value"
    )
    summary = await execute(summary_sql, sources, settings.query_timeout_seconds, capacity)
    if summary["truncated"]:
        raise SqlRejected("Too many anomaly groups; choose a smaller grouping.")
    for row in summary["rows"]:
        row["status"] = (
            "insufficient_evidence"
            if row["sample_size"] < 20 or row["q1"] == row["q3"]
            else "flagged"
            if row["flagged_count"]
            else "no_values_flagged"
        )
    flags_sql = base + "SELECT * EXCLUDE (flagged) FROM evaluated WHERE flagged ORDER BY row_reference"
    flags = await execute(flags_sql, sources, settings.query_timeout_seconds, capacity)
    return {
        "rule": "IQR v1: Q1/Q3 continuous quantiles; bounds Q1 - 1.5×IQR and Q3 + 1.5×IQR",
        "measure": columns[measure]["name"],
        "group": columns[intent.group]["name"] if intent.group else None,
        "groups": summary["rows"],
        "flagged_count": sum(r["flagged_count"] for r in summary["rows"]),
        "caveats": [
            "Nulls excluded; at least 20 valid observations per group required. Zero IQR has no verdict.",
            "Statistical flags are not proof of fraud, error, or causation.",
            "Row references are 1-based data-record positions in the immutable snapshot (header excluded).",
        ],
        "table": flags,
        "sql": summary_sql + ";\n" + flags_sql,
    }
