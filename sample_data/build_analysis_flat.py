"""Rebuild the explicit single-table Phase 2 fixture from checked-in synthetic sources."""

import csv
from decimal import Decimal
from pathlib import Path

root = Path(__file__).parent
with (root / "customers.csv").open(newline="", encoding="utf-8") as file:
    customers = {row["customer_id"]: row for row in csv.DictReader(file)}
with (root / "sales.csv").open(newline="", encoding="utf-8") as file:
    sales = list(csv.DictReader(file))
rows = []
for sale in sales:
    customer = customers[sale["customer_id"]]
    rows.append({"sale_id": sale["sale_id"], "sale_date": sale["sale_date"],
                 "customer_id": sale["customer_id"], "customer_name": customer["customer_name"],
                 "region": customer["region"], "quantity": sale["quantity"],
                 "unit_price_usd": sale["unit_price_usd"],
                 "revenue_usd": str(Decimal(sale["quantity"]) * Decimal(sale["unit_price_usd"]))})
assert len(rows) == len(sales) == 24
with (root / "analysis_flat.csv").open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
