# Synthetic evaluation fixtures

All records and names are invented; no real personal or business data. UTF-8, comma-delimited, header row. These files are not automatically uploaded or analyzed by Phase 0.

- `sales.csv`: 24 distinct sale lines, January–March 2026. `sale_id` is unique. Each row is one sale, not a multi-line order. Quantity is a positive integer count; `unit_price_usd` is the transaction price in USD (can vary by transaction).
- `customers.csv`: six unique `customer_id` values; region is the customer's region, not a shipment destination. Names are synthetic business labels.
- `products.csv`: three unique `product_id` values with product category. No catalog price; sales prices are authoritative.
- Explicit joins: `sales.customer_id = customers.customer_id` and `sales.product_id = products.product_id`, both many-to-one, with zero unmatched sale rows. These joins must preserve 24 rows. Joining on names is unsupported.
- Dates are ISO calendar dates, no time of day or timezone conversion. Month means calendar month of `sale_date`.
- Revenue per line = `quantity * unit_price_usd`; gross USD, no tax, discounts, refunds, shipping, or currency conversion. Aggregate with decimal arithmetic.
- `data_quality.csv` is separate from business totals. Blank fields are missing, not zero. Five rows include one duplicate beyond the first occurrence, one missing category and two missing amount cells. Do not silently clean them.

## Independently worked expected answers

The first 23 sale revenues are $10, $20, …, $230; S24 is $1,000. Total = 10 × (23 × 24 / 2) + 1,000 = $3,760.
January is $10–$80 = $360; February is $90–$160 = $1,000; March is $170–$230 plus $1,000 = $2,400.
Customer totals C01–C06 are respectively $400, $440, $480, $520, $560, $1,360. Regional totals follow the explicit customer join: North $960, South $1,800, East $480, West $520. Category totals equal the month totals by fixture construction.

Representative questions: highest-revenue region; revenue by month; top five customers (revenue descending, ID ascending for ties); revenue by product category; regions below an **explicit $1,000 threshold**, not an inferred target.

Anomaly example: apply 1.5×IQR to the 24 sale revenues, using linear percentile interpolation at `(n−1)*p`. Q1=$67.50, Q3=$182.50, IQR=$115, bounds −$105 and $355. Only S24 ($1,000) is flagged. At least 20 valid observations and nonzero IQR are present. This is an intentional statistical outlier, not evidence of fraud or error. There are no null revenue values.

`expected_answers.json` contains manually worked answers. `python sample_data/verify.py` independently recomputes them using Python's standard library and fails on drift; it does not call an LLM or the application and does not rewrite the oracle. This is fixture verification, not an implemented analysis feature.
