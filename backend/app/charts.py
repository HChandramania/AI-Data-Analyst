"""Chart intents carry no values; artifacts are built only from executed rows."""

import math
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChartIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["bar", "line", "pie", "scatter"]
    x: str = Field(max_length=64)
    y: str = Field(max_length=64)
    title: str = Field(min_length=1, max_length=160)
    x_label: str = Field(min_length=1, max_length=100)
    y_label: str = Field(min_length=1, max_length=100)
    period: Literal["day", "month", "year"] | None = None


def numeric(kind: str) -> bool:
    return kind.upper().split("(")[0] in {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UBIGINT",
        "DOUBLE",
        "FLOAT",
        "DECIMAL",
    }


def build_chart(intent: ChartIntent, table: dict) -> dict:
    if intent.x == intent.y or not {intent.x, intent.y}.issubset(table["columns"]):
        raise ValueError("Chart requires two distinct result columns.")
    types = table.get("types", {})
    if not numeric(types.get(intent.y, "")):
        raise ValueError("Chart values must be a numeric result column.")
    rows = table["rows"]
    if not rows:
        raise ValueError("No result rows to chart.")
    if any(r[intent.x] is None for r in rows):
        raise ValueError("Chart labels contain nulls; choose an explicit grouping.")
    points = [{"x": r[intent.x], "y": r[intent.y]} for r in rows]
    if all(p["y"] is None for p in points):
        raise ValueError("No non-null numeric observations to chart.")
    if any(p["y"] is not None and not math.isfinite(float(p["y"])) for p in points):
        raise ValueError("Chart values must be finite.")
    if intent.type in {"bar", "pie"}:
        limit = 8 if intent.type == "pie" else 50
        if len(points) > limit or len({str(p["x"]) for p in points}) != len(points):
            raise ValueError(f"Chart needs unique categories, at most {limit}; aggregate first.")
    if intent.type == "pie":
        if table["truncated"] or any(p["y"] is None or float(p["y"]) < 0 for p in points):
            raise ValueError("Pie requires complete, nonnegative, non-null parts.")
        if sum(float(p["y"]) for p in points) <= 0:
            raise ValueError("Pie requires a positive total.")
    if intent.type == "scatter":
        if not numeric(types.get(intent.x, "")) or any(p["y"] is None for p in points):
            raise ValueError("Scatter requires two non-null numeric columns.")
        if any(not math.isfinite(float(p["x"])) for p in points):
            raise ValueError("Scatter values must be finite.")
    caveats = ["Only returned rows are plotted; query filters and limits still apply."]
    if intent.type == "line":
        temporal = types.get(intent.x, "").startswith(("DATE", "TIMESTAMP"))
        if not temporal and types.get(intent.x, "") == "VARCHAR" and intent.period:
            # Formatting SQL may produce ISO text. Accept only unambiguous labels
            # with explicit cadence; do not infer dates from arbitrary categories.
            for point in points:
                value = str(point["x"])
                if intent.period == "month" and re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
                    value += "-01"
                elif intent.period == "year" and re.fullmatch(r"[0-9]{4}", value):
                    value += "-01-01"
                elif not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                    raise ValueError("Line date labels must be ISO dates matching the declared cadence.")
                try:
                    datetime.fromisoformat(value)
                except ValueError:
                    raise ValueError("Line date labels contain an invalid calendar date.") from None
                point["x"] = value
            temporal = True
            caveats.append(
                "ISO text labels use the declared cadence; month/year labels are plotted at their first day. "
                "Supporting table values are unchanged."
            )
        if not temporal and not numeric(types.get(intent.x, "")):
            raise ValueError("Line requires a temporal or numeric x-axis.")
        if len({str(p["x"]) for p in points}) != len(points):
            raise ValueError("Line requires unique ordered x values; aggregate first.")
        points.sort(key=lambda p: datetime.fromisoformat(str(p["x"])) if temporal else float(p["x"]))
        if temporal:
            if not intent.period:
                raise ValueError("Specify day, month, or year cadence to expose missing periods.")

            def ordinal(value):
                d = datetime.fromisoformat(str(value))
                return (
                    d.toordinal()
                    if intent.period == "day"
                    else d.year * 12 + d.month
                    if intent.period == "month"
                    else d.year
                )

            expanded = []
            for point in points:
                if expanded and ordinal(point["x"]) - ordinal(expanded[-1]["x"]) > 1:
                    expanded.append({"x": point["x"], "y": None})
                expanded.append(point)
            points = expanded
            caveats.append("Missing periods are gaps, never zero-filled or interpolated.")
    if table["truncated"]:
        caveats.append("Result truncated at 500 rows; omitted values/categories are not plotted.")
    return {**intent.model_dump(), "points": points, "caveats": caveats}
