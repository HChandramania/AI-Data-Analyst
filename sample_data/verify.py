"""Independent stdlib-only fixture oracle; never overwrites expected answers."""
import csv
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(name):
    with (ROOT / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def money(value):
    return format(value, ".2f")


def compute():
    sales, customers, products, quality = [rows(n) for n in
                                          ("sales", "customers", "products", "data_quality")]
    for data, key in [(sales, "sale_id"), (customers, "customer_id"), (products, "product_id")]:
        assert len({r[key] for r in data}) == len(data), f"Duplicate {key}"
    customer_map = {r["customer_id"]: r for r in customers}
    product_map = {r["product_id"]: r for r in products}
    region, month, customer, category = [defaultdict(Decimal) for _ in range(4)]
    values = []
    unmatched_customer = unmatched_product = 0
    for row in sales:
        value = Decimal(row["quantity"]) * Decimal(row["unit_price_usd"])
        values.append(value)
        period = date.fromisoformat(row["sale_date"]).strftime("%Y-%m")
        month[period] += value
        customer[row["customer_id"]] += value
        if row["customer_id"] in customer_map:
            region[customer_map[row["customer_id"]]["region"]] += value
        else:
            unmatched_customer += 1
        if row["product_id"] in product_map:
            category[product_map[row["product_id"]]["category"]] += value
        else:
            unmatched_product += 1
    ordered = sorted(values)

    def percentile(p):
        position = Decimal(len(ordered) - 1) * p
        lower = int(position)
        return ordered[lower] + (ordered[lower + 1] - ordered[lower]) * (position - lower)

    q1, q3 = percentile(Decimal("0.25")), percentile(Decimal("0.75"))
    low, high = q1 - Decimal("1.5") * (q3 - q1), q3 + Decimal("1.5") * (q3 - q1)
    return {
        "row_count": len(sales), "total_revenue_usd": money(sum(values)),
        "regional_revenue_usd": {k: money(v) for k, v in region.items()},
        "highest_revenue_region": max(region, key=region.get),
        "monthly_revenue_usd": {k: money(v) for k, v in month.items()},
        "top_five_customers": [{"customer_id": k, "revenue_usd": money(v)} for k, v in
                               sorted(customer.items(), key=lambda pair: (-pair[1], pair[0]))[:5]],
        "category_revenue_usd": {k: money(v) for k, v in category.items()},
        "unmatched_customer_rows": unmatched_customer, "unmatched_product_rows": unmatched_product,
        "regions_below_1000_usd": sorted(k for k, v in region.items() if v < 1000),
        "anomaly": {"rule": "IQR 1.5; linear percentile (n-1)*p", "sample_size": len(values),
                    "q1_usd": money(q1), "q3_usd": money(q3), "lower_usd": money(low),
                    "upper_usd": money(high),
                    "sale_ids": [r["sale_id"] for r, v in zip(sales, values) if v < low or v > high]},
        "quality": {"rows": len(quality),
                    "duplicate_rows": len(quality) - len({tuple(r.values()) for r in quality}),
                    "missing_cells": {k: sum(r[k] == "" for r in quality) for k in quality[0]}},
    }


if __name__ == "__main__":
    expected = json.loads((ROOT / "expected_answers.json").read_text(encoding="utf-8"))
    actual = compute()
    if actual != expected:
        raise SystemExit("Fixture verification failed:\n" + json.dumps(actual, indent=2))
    print(f"PASS: all {len(expected)} expected-answer groups match the synthetic CSVs.")
