# E-commerce Sales & Customer Behaviour Analysis
### Olist Brazilian E-commerce — 96,478 delivered orders · R$ 15.42M revenue · 93,358 customers

> *"Ek online store ke sales, customers aur products ka analysis karke business ko batana ki revenue kaise badha sakte hain aur kaun se customers sabse valuable hain."*
>
> **In English:** how can this store grow revenue, and which customers are actually valuable?

This project answers both questions end-to-end: raw CSV → cleaned warehouse → SQL analysis → Python EDA →
RFM / cohort / Pareto → interactive dashboard → business recommendations.

---

## TL;DR — what the data says

| | |
|---|---|
| **Revenue** | R$ 15.42M from 96,478 delivered orders (Sep 2016 – Aug 2018) |
| **Growth** | R$ 127k/month (Jan-2017) → R$ 1.15M/month (Nov-2017, Black Friday), then **flat** at R$ 1.0–1.1M |
| **Basket** | AOV R$ 159.86 — **unchanged for 20 months**; growth came entirely from order volume |
| **Loyalty** | **97% of customers buy once**; repeat buyers = 5.6% of revenue; monthly cohort retention < 0.7% |
| **Value** | top 1% of customers = 10.3% of revenue · top 5% = 26.8% · top 20% = 53.5% |
| **Delivery** | 12.6 days actual vs 23.7 promised; 8.1% late — and late orders average **2.57 stars vs 4.29** |
| **Catalogue** | 28.1% of the 32,216 SKUs (9,053 products) generate 80% of revenue |

**The one-line answer:** grow by protecting the 1,886 highest-value customers (Champions + Cannot Lose Them,
R$339–358 lifetime value) and by fixing late delivery in the North-East — **not** by building a loyalty
programme for a base that buys once.

> ⚠️ The standard RFM story ("Champions are 15% of customers and 50% of revenue") is **false for this dataset**.
> Champions are 1.2% of customers and 2.5% of revenue. Section 4.3 of the report explains why, and what to do instead.

---

## Repository map

```
.
├── data/
│   ├── raw/                     9 original Olist CSVs (git-ignored, re-downloadable)
│   └── processed/               master tables, RFM, cohorts, SQLite warehouse (generated)
├── notebooks/
│   └── 01_olist_analysis.ipynb  ★ the main notebook (executed, with commentary)
├── sql/
│   ├── 01_schema.sql            star-schema DDL for MySQL / PostgreSQL / SQLite
│   └── 02_analysis_queries.sql  ★ 13 annotated business queries (window functions, CTEs, NTILE)
├── src/
│   ├── config.py                paths, business rules, palette
│   ├── download_data.py         fetch the 9 raw CSVs
│   ├── etl.py                   Step 1–2: load, audit, clean, master table, SQLite
│   ├── sql_analysis.py          Step 3: executes every query, exports results
│   ├── analysis.py              Step 4–5: EDA figures, RFM, cohort, Pareto, metrics.json
│   └── viz.py                   shared chart style
├── dashboard/
│   ├── build_dashboard.py       Step 6: builds the HTML dashboard
│   ├── olist_dashboard.html     ★ interactive dashboard (4 pages, filters, offline)
│   └── screenshots/             4 page screenshots
├── powerbi/
│   ├── README.md                ★ step-by-step Power BI build guide
│   ├── measures.dax             all DAX measures
│   ├── build_extracts.py        writes the star-schema CSVs
│   └── data/                    generated extracts (git-ignored)
├── reports/
│   ├── REPORT.md                ★ written report (7 sections)
│   ├── Olist_Report.docx         same report as a document
│   ├── Olist_Presentation.pptx  ★ 11-slide deck
│   ├── figures/                 12 publication-quality charts
│   └── sql_results/             13 CSV outputs of the SQL analysis
└── scripts/
    ├── build_report.py          regenerates REPORT.md + DOCX
    └── build_pptx.py            regenerates the deck
```

---

## Quickstart (fresh machine / teammate setup)

Requirement: **Python 3.10+** installed ([python.org](https://www.python.org/downloads/) — tick "Add to PATH" during install).

```bash
# 1. clone
git clone https://github.com/shiva-garg-77/olist-ecommerce-analysis.git
cd olist-ecommerce-analysis

# 2. dependencies (2-3 min)
pip install -r requirements.txt

# 3. download the 9 dataset CSVs (~121 MB, verifies row counts automatically)
python -m src.download_data

# 4. run the full pipeline (2 min)
python -m src.etl && python -m src.sql_analysis && python -m src.analysis
python -m dashboard.build_dashboard
```

Windows shortcut after cloning: **double-click `RUN_PIPELINE.bat`** — it runs steps 3→4 in order
and opens the dashboard in the browser when done.

Then open:
* `dashboard/olist_dashboard.html` — the interactive dashboard (works offline, no server)
* `notebooks/01_olist_analysis.ipynb` — the full story, cell by cell
* `reports/Olist_Presentation.pptx` — the deck
* `reports/REPORT.md` — the written report

Runtime: ~4 minutes total on a laptop (geolocation is the only heavy table).


---

## Step-by-step (what was done, and why)

### Step 1 — Load & understand
9 tables, 1.55M rows total. Two traps handled explicitly:

1. **`customer_id` is regenerated for every order** — it is an order key, not a person. Repeat behaviour
   must use `customer_unique_id` (99,441 vs 96,096). Miss this and the repeat rate looks like 0%.
2. **`order_items` is item-grain** — summing `payment_value` there multiplies revenue. All order KPIs use a
   one-row-per-order fact table.

### Step 2 — Cleaning (`src/etl.py`)

| Problem | Fix |
|---|---|
| 8 date columns stored as text | `to_datetime`, impossible timestamps nulled |
| 103,886 payments for 99,441 orders | collapsed to 1 row/order (total, max installments, dominant type) |
| 551 orders with 2+ reviews | kept the latest answer |
| 1,000,163 geolocation rows / 261,831 duplicates | aggregated to 19,015 zip-prefix centroids |
| 610 products without category | labelled `Unknown`, categories translated PT→EN |
| 1,234 cancelled / unavailable orders | excluded from the revenue universe |
| payment value missing on 1 order | filled with 0 |

**Validation:** item revenue (price + freight) and payment revenue agree within **0.02%**
(R$15,419,774 vs R$15,422,462) — proof the joins did not fan out.

### Step 3 — SQL (13 queries)
Monthly revenue/orders with `LAG()` + running total, top-10 categories with cumulative share,
state performance, delivery vs promise, `RANK() OVER (PARTITION BY state)`, review-vs-delay,
Pareto with `ROW_NUMBER()`, seller leaderboard, `NTILE()` RFM, cohort retention, repeat-purchase
distribution. SQLite ships with the project; the same file runs on MySQL 8 / PostgreSQL 12+.

### Step 4 — EDA
Trend, seasonality (Nov peak, weekday × hour demand), payment mix, review vs delay, delivery distribution,
category AOV, geography, basket size.

### Step 5 — Advanced
* **RFM** — R and M in quintiles, **F in explicit 1 / 2 / 3+ buckets** because 97% of customers buy once and
  quintiles would give every customer the same F score. Priority ladder for segments, mirrored in SQL (Q10).
* **Cohort retention** — monthly cohorts, 6 periods, month 0 masked (100% by definition).
* **Pareto** — 80/20 on products.

### Step 6 — Dashboard
A self-contained interactive HTML dashboard (`dashboard/olist_dashboard.html`) with the four required pages:
sales overview · products & categories · customer segments · geography & delivery. Filters: month range,
state (multi), category. Every page recomputes live from the embedded order-level fact table.
A Power BI build pack (`powerbi/`) reproduces the same model with DAX.

### Step 7 — Insights & recommendations
See `reports/REPORT.md` §5. The seven actions are ordered by impact per unit of effort, with expected
revenue attached to each.

---

## Deliverables checklist

| Requirement | Where |
|---|---|
| Jupyter notebook (clean, commented) | `notebooks/01_olist_analysis.ipynb` |
| SQL file | `sql/01_schema.sql`, `sql/02_analysis_queries.sql` |
| Dashboard (.pbix + screenshots) | `dashboard/olist_dashboard.html` + `dashboard/screenshots/` + `powerbi/` build pack |
| README | this file |
| 5–7 page report / PPT | `reports/Olist_Report.docx`, `reports/REPORT.md`, `reports/Olist_Presentation.pptx` |

---

## Method notes worth defending in a viva

1. **Revenue has two definitions, used consistently.** *Order revenue* = `payment_value` (money collected,
   net of vouchers) for KPIs/AOV/RFM. *Item revenue* = `price + freight` for product/category/state cuts.
   They reconcile to 0.02%.
2. **Frequency buckets instead of quintiles.** A textbook RFM on this dataset assigns F=1 to 97% of customers,
   so the score carries no information. Explicit 1 / 2 / 3+ buckets are honest and interpretable.
3. **Order-grain vs item-grain is tested, not assumed.** The reconciliation step exists in both the ETL and the
   notebook.
4. **Cohorts are read by column, not row**, because later cohorts are right-censored — a mistake that makes
   recent cohorts look better than they are.
5. **Primary-category attribution** for multi-category orders (highest-value category) is a documented
   simplification, not a hidden one.

---

## Limitations
No cost/margin data, no marketing spend (so no CAC/ROAS), no returns table, partial months at the edges of the
history, and RFM is a point-in-time snapshot (2018-08-30).

## Data source
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle).
Raw files are git-ignored; `python -m src.download_data` fetches an identical public mirror and verifies row counts.
