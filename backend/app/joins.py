"""User-provided join relationships and bounded, server-authored diagnostics."""

import json
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.executor import execute
from app.sql_policy import SqlRejected


class JoinKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: UUID = Field(validation_alias=AliasChoices("left", "left_dataset_id"))
    right: UUID = Field(validation_alias=AliasChoices("right", "right_dataset_id"))
    left_key: str = Field(pattern=r"^c[0-9]{1,2}$", validation_alias=AliasChoices("left_key", "left_column"))
    right_key: str = Field(pattern=r"^c[0-9]{1,2}$", validation_alias=AliasChoices("right_key", "right_column"))
    type: Literal["inner", "left"] = Field(validation_alias=AliasChoices("type", "join_type"))

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        return value.lower() if isinstance(value, str) else value


def validate_keys(joins: list[JoinKey], datasets):
    registry = {d.id: {c["id"]: c["type"] for c in json.loads(d.schema_json)} for d in datasets}
    if len(joins) != len(registry) - 1 or not joins:
        raise SqlRejected("Provide exactly one fewer relationships than selected datasets.")
    pairs = set()
    parents = {}
    for j in joins:
        if j.left not in registry or j.right not in registry or j.left == j.right:
            raise SqlRejected("Join sources must be distinct selected datasets.")
        pair = frozenset((j.left, j.right))
        if pair in pairs:
            raise SqlRejected("Duplicate relationships or parallel join paths are not allowed.")
        pairs.add(pair)
        left, right = registry[j.left], registry[j.right]
        if j.left_key not in left or j.right_key not in right:
            raise SqlRejected("Join columns must exist in their selected datasets.")
        types = {left[j.left_key], right[j.right_key]}
        if len(types) > 1 and not types <= {"integer", "decimal"}:
            raise SqlRejected("Join keys must have compatible types.")
        if j.right in parents:
            raise SqlRejected("Ambiguous join paths: each right dataset must have one parent.")
        parents[j.right] = j.left
    roots = set(registry) - set(parents)
    if len(roots) != 1:
        raise SqlRejected("Use a connected acyclic tree with a single left-side root.")
    seen = set(roots)
    pending = list(joins)
    ordered = []
    while pending:
        ready = next((j for j in pending if j.left in seen and j.right not in seen), None)
        if ready is None:
            raise SqlRejected("Disconnected or cyclic relationships; check left/right directions.")
        ordered.append(ready)
        seen.add(ready.right)
        pending.remove(ready)
    if seen != set(registry):
        raise SqlRejected("Join relationships must connect every selected dataset.")
    return ordered


def fanout_warning(facts):
    if sum(bool(f["multiplies_left_rows"]) for f in facts) >= 2:
        return (
            "Multiple expanding relationships can create fanout (for example, order items and payments). "
            "SUM, COUNT and AVG may be inflated. Confirmation accepts this risk; it does not make aggregates correct. "
            "Use a narrower join or independently aggregated data when safe aggregation is unknown."
        )
    return None


async def diagnostics(joins, sources, settings, capacity):
    results = []
    for j in joins:
        left, right = f"dataset_{j.left.hex}", f"dataset_{j.right.hex}"
        # Aggregated key frequencies avoid materializing a multiplied join.
        sql = (
            f"WITH l AS (SELECT {j.left_key} AS k, COUNT(*) AS n FROM {left} GROUP BY {j.left_key}), "
            f"r AS (SELECT {j.right_key} AS k, COUNT(*) AS n FROM {right} GROUP BY {j.right_key}) "
            "SELECT (SELECT COUNT(*) FROM l WHERE n>1 AND k IS NOT NULL) AS left_duplicate_keys, "
            "(SELECT COUNT(*) FROM r WHERE n>1 AND k IS NOT NULL) AS right_duplicate_keys, "
            "(SELECT COALESCE(SUM(n),0) FROM l WHERE k IS NULL) AS left_nulls, "
            "(SELECT COALESCE(SUM(n),0) FROM r WHERE k IS NULL) AS right_nulls, "
            "COALESCE(SUM(CASE WHEN r.k IS NULL THEN l.n ELSE 0 END),0) AS left_unmatched_rows, "
            "COALESCE(SUM(CASE WHEN l.k IS NULL THEN r.n ELSE 0 END),0) AS right_unmatched_rows, "
            "COALESCE(SUM(l.n*r.n),0) AS matched_rows, "
            "COALESCE(MAX(CASE WHEN l.k IS NOT NULL AND r.k IS NOT NULL AND r.n>1 THEN 1 ELSE 0 END),0) "
            "AS multiplies_left_rows, "
            "COALESCE(MAX(CASE WHEN l.k IS NOT NULL AND r.k IS NOT NULL AND l.n>1 THEN 1 ELSE 0 END),0) "
            "AS multiplies_right_rows FROM l FULL OUTER JOIN r ON l.k=r.k"
        )
        result = await execute(sql, sources, settings.query_timeout_seconds, capacity)
        facts = result["rows"][0]
        facts["cardinality"] = (
            ("many" if facts["left_duplicate_keys"] else "one")
            + "-to-"
            + ("many" if facts["right_duplicate_keys"] else "one")
        )
        facts["expected_pair_rows"] = facts["matched_rows"] + (facts["left_unmatched_rows"] if j.type == "left" else 0)
        results.append({"join": j.model_dump(mode="json"), **facts})
    return results
