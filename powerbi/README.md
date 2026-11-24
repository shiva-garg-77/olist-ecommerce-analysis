# Power BI build pack

A `.pbix` file cannot be generated from code, so this folder ships **everything needed to rebuild the
exact dashboard in Power BI Desktop in ~30 minutes**, with the CSVs already modelled as a star schema.

The interactive HTML dashboard in `dashboard/olist_dashboard.html` is the reference implementation —
same KPIs, same four pages, same filters. Use the screenshots in `dashboard/screenshots/` as the
design target.

---

## 0. Generate the extracts

```bash
python -m src.etl              # cleaned tables (once)
python -m src.analysis         # metrics + RFM
python -m powerbi.build_extracts
```

This writes `powerbi/data/`:

| File | Grain | Rows |
|---|---|---|
| `fact_sales.csv` | one row per delivered order | 96,478 |
| `fact_items.csv` | one row per order item | 110,197 |
| `dim_customers.csv` | one row per person (RFM scores + segment) | 93,358 |
| `dim_products.csv` | one row per product | 32,951 |
| `dim_sellers.csv` | one row per seller | 3,095 |
| `dim_date.csv` | one row per calendar day | 1,096 |

## 1. Load

Power BI Desktop → **Get Data → Text/CSV** → load all six files →
**Transform Data** and set these types (critical, otherwise time intelligence breaks):

| Table | Column | Type |
|---|---|---|
| `fact_sales` | `day_key` | Date |
| `dim_date` | `date` | Date |
| `fact_sales` | `order_revenue`, `items_revenue`, `freight_value` | Decimal number |
| `fact_sales` | `is_late`, `n_items`, `review_score` | Whole number |
| `dim_customers` | `first_purchase`, `last_purchase` | Date |
| `fact_items` | `price`, `freight_value`, `item_total` | Decimal number |

Then **Close & Apply**.

## 2. Model (star schema)

In *Model view*, create these relationships (all **one-to-many**, single direction from dimension to fact):

```
dim_date[date]             1 ──*  fact_sales[day_key]
dim_customers[id]          1 ──*  fact_sales[customer_unique_id]
dim_products[product_id]   1 ──*  fact_items[product_id]
dim_sellers[seller_id]     1 ──*  fact_items[seller_id]
fact_sales[order_id]       1 ──*  fact_items[order_id]
```

Mark `dim_date` as a **date table** (Table tools → Mark as date table → `date`).
Hide the raw keys (`day_key`, `customer_unique_id`, `product_id`, `seller_id`) from report view.

> If Power BI complains about duplicate keys, it means the CSV was regenerated while the report was
> open — just refresh.

## 3. Measures

Create a new table `_Measures` (Enter Data → one empty column → rename) and paste the formulas from
**`measures.dax`**. Start with `Total Revenue`, `Total Orders`, `Avg Order Value`, `Total Customers`.

## 4. Pages

### Page 1 — Sales overview
* 4 KPI cards: `Total Revenue`, `Total Orders`, `Avg Order Value`, `Total Customers`
* Line + column combo chart: axis `dim_date[month_key]`, columns `Total Revenue`, line `Total Orders`
  (secondary axis on), plus `Revenue 3M Moving Avg` as a smooth line
* Donut: `fact_sales[payment_type]` by `Total Orders`
* Column chart: `Avg Review Score` by a calculated column bucket of `delay_days`
  (`Delay Bucket = SWITCH(TRUE(), fact_sales[delay_days] <= -15, "15+ d early", fact_sales[delay_days] < 0, "Early", fact_sales[delay_days] < 1, "On promise", fact_sales[delay_days] <= 7, "1-7 d late", fact_sales[delay_days] <= 15, "8-15 d late", "15+ d late")`)
* Slicer: `dim_date[date]` between; `fact_sales[customer_state]`; `dim_products[category]`

### Page 2 — Products & categories
* Bar: `dim_products[category]` by `Item Revenue` (Top N filter = 12), sorted desc
* Scatter: X = `Avg Order Value`, Y = `Item Revenue`, size = `Units Sold`, details = category
* Pareto: line + column, X = `Product Revenue Rank` (bucket it into 100 bins), Y = `Cumulative Product Revenue %`
* Table: category, revenue, orders, AOV, `Category Revenue Share %`

### Page 3 — Customer segments
* Bar: `dim_customers[segment]` by `Customers by Segment` and `Segment Revenue Share %`
* Cards: `Repeat Rate %`, `% Revenue from Repeat`, `Champion Value Index`
* Matrix: `dim_customers[rfm_score]` (R x M) with `Segment Revenue` in values
* Cohort: either a matrix with `cohort_month` (calculated column) × `period` (calculated column), or
  use the exported `data/processed/cohort_matrix.csv` as an additional table (simplest).

### Page 4 — Geography & delivery
* Filled map: `fact_sales[customer_state]` by `Total Revenue` (enable *Map visuals → Shape map* if the
  Bing map is blocked; the state codes are ISO 3166-2:Brazil)
* Bar: state by `Total Revenue`, Top 12
* Bar: state by `% Late Deliveries` (filter orders >= 300)
* Clustered bar: `Avg Promised Days` vs `Avg Delivery Days` by state
* Table: state, revenue, share, orders, AOV, avg days, late %

## 5. Formatting checklist (so it matches the screenshots)

* Theme: custom JSON or manually — primary `#0B6E99`, secondary `#1F9E89`, accent `#F2A93B`,
  danger `#D64545`, ink `#1B2733`, grid `#E3E8EE`
* Font: Segoe UI, 10–11 pt; card labels 9 pt, values 18–20 pt semi-bold
* Turn off axis titles where the card title already says it; keep gridlines light
* Page background `#F5F7FA`, visual background white, 8 px rounded corners, thin border `#E3E8EE`

## 6. Publish

`File → Export → Export to PDF` (or take screenshots) and drop them into
`dashboard/screenshots/` next to the HTML dashboard screenshots. Save the `.pbix` as
`powerbi/olist_dashboard.pbix`.
