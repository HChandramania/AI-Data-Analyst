# Synthetic evaluation fixtures

All records and names are invented; no real personal or business data. UTF-8, comma-delimited, header row. These files are not automatically uploaded.

`no_outliers.csv` contains 24 valid observations with values 1–24 and unique record IDs. With the app's continuous-percentile 1.5×IQR rule, Q1=6.75, Q3=18.25, IQR=11.5, and bounds are −10.5 to 35.5: zero records are flagged. Upload this file alone and ask: “Detect outliers in value using the 1.5 × IQR rule across the entire dataset, without grouping.”

`phase3_anomalies.csv` is a standalone IQR fixture used by Phase 3 API tests and available for manual upload. It contains values 1–24, then 1,000, then one null: 26 records, 25 valid observations, Q1=7, Q3=19, IQR=12, bounds −11 and 37. Exactly record 25 (`R25`, value 1,000) is flagged. The null is disclosed and excluded; this is a synthetic statistical flag, not fraud/error evidence.

`analysis_flat.csv` is the Phase 2 single-table fixture. `python sample_data/build_analysis_flat.py` generates it by explicitly joining sales to customers on `customer_id` and calculating each row's `revenue_usd` with decimal arithmetic. The same bytes are served from `frontend/public/sample_data/analysis_flat.csv` by **Use analysis sample**. This fixture makes regional, monthly, and customer questions available before Phase 3's runtime join workflow.

- `sales.csv`: 24 distinct sale lines, January–March 2026. `sale_id` is unique. Each row is one sale, not a multi-line order. Quantity is a positive integer count; `unit_price_usd` is the transaction price in USD (can vary by transaction).
- `customers.csv`: six unique `customer_id` values; region is the customer's region, not a shipment destination. Names are synthetic business labels.
- `products.csv`: three unique `product_id` values with product category. No catalog price; sales prices are authoritative.
- Explicit joins: `sales.customer_id = customers.customer_id` and `sales.product_id = products.product_id`, both many-to-one, with zero unmatched sale rows. These joins must preserve 24 rows. Joining on names is unsupported.
- Dates are ISO calendar dates, no time of day or timezone conversion. Month means calendar month of `sale_date`.
- Revenue per line = `quantity * unit_price_usd`; gross USD, no tax, discounts, refunds, shipping, or currency conversion. Aggregate with decimal arithmetic.
- `data_quality.csv` is separate from business totals. Blank fields are missing, not zero. Five rows include one duplicate beyond the first occurrence, one missing category and two missing amount cells. Do not silently clean them.

- `empty_header_only.csv` intentionally contains only a header row and no data rows. Uploading it should be rejected with a clear empty-data validation message.
- `oversized_upload.csv` is a valid synthetic CSV of approximately 10.005 MiB (92,840 data rows), created for the former 10 MiB limit. It is below the current 64 MiB limit and should now be accepted; its filename is retained for compatibility.

## Independently worked expected answers

The first 23 sale revenues are $10, $20, …, $230; S24 is $1,000. Total = 10 × (23 × 24 / 2) + 1,000 = $3,760.
January is $10–$80 = $360; February is $90–$160 = $1,000; March is $170–$230 plus $1,000 = $2,400.
Customer totals C01–C06 are respectively $400, $440, $480, $520, $560, $1,360. Regional totals follow the explicit customer join: North $960, South $1,800, East $480, West $520. Category totals equal the month totals by fixture construction.

Representative questions: highest-revenue region; revenue by month; top five customers (revenue descending, ID ascending for ties); revenue by product category; regions below an **explicit $1,000 threshold**, not an inferred target.

Anomaly example: apply 1.5×IQR to the 24 sale revenues, using linear percentile interpolation at `(n−1)*p`. Q1=$67.50, Q3=$182.50, IQR=$115, bounds −$105 and $355. Only S24 ($1,000) is flagged. At least 20 valid observations and nonzero IQR are present. This is an intentional statistical outlier, not evidence of fraud or error. There are no null revenue values.

`expected_answers.json` contains manually worked answers. `python sample_data/verify.py` independently recomputes them using Python's standard library and fails on drift; it does not call an LLM or the application and does not rewrite the oracle. This is fixture verification, not an implemented analysis feature.
