"""
Central configuration for the Olist E-commerce Analysis project.

Keeping every path / business rule in one place means the notebook, the SQL
loader, the dashboard and the report all agree on the numbers.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
DASHBOARD_DIR = ROOT / "dashboard"

DB_PATH = DATA_PROCESSED / "olist.db"

for _d in (DATA_PROCESSED, REPORTS_DIR, FIGURES_DIR, DASHBOARD_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Raw file names (Olist Brazilian E-commerce public dataset - 9 tables)
# --------------------------------------------------------------------------
RAW_FILES = {
    "orders": "olist_orders_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

# Columns that must become real timestamps (Step 2: wrong data types)
DATE_COLUMNS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "reviews": ["review_creation_date", "review_answer_timestamp"],
}

# --------------------------------------------------------------------------
# Business rules
# --------------------------------------------------------------------------
# Statuses whose revenue we DO count. "delivered" is the only status that
# represents money actually earned on a fulfilled order.
REVENUE_STATUSES = ("delivered",)

# Cancelled / unavailable orders are dropped from the analysis universe.
# We keep them in a separate frame so we can report their share.
EXCLUDED_STATUSES = ("canceled", "unavailable")

# Olist's history is only dense between these months; the edges are partial
# months caused by the source extract, so trends are plotted inside the window.
ANALYSIS_START = "2017-01-01"
ANALYSIS_END = "2018-08-31"

# Monetary brackets used for the RFM "Frequency" score. Quintile scoring does
# not work here: ~97% of Olist customers buy exactly once, so every customer
# would land in the same frequency bin. Explicit buckets are honest and useful.
FREQUENCY_BUCKETS = [(1, 1), (2, 2), (3, 99)]  # (min, max) -> score 1..3

# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------
PALETTE = {
    "primary": "#0B6E99",
    "secondary": "#1F9E89",
    "accent": "#F2A93B",
    "danger": "#D64545",
    "muted": "#8894A0",
    "ink": "#1B2733",
    "grid": "#E3E8EE",
    "bg": "#FFFFFF",
}

SEGMENT_ORDER = [
    "Champions",
    "Loyal Customers",
    "New Customers",
    "Promising",
    "Need Attention",
    "At Risk",
    "Cannot Lose Them",
    "Hibernating",
    "Lost",
]

SEGMENT_COLORS = {
    "Champions": "#0B6E99",
    "Loyal Customers": "#1F9E89",
    "New Customers": "#4FB3A9",
    "Promising": "#F2A93B",
    "Need Attention": "#E08D2E",
    "At Risk": "#D64545",
    "Cannot Lose Them": "#A83232",
    "Hibernating": "#7A8794",
    "Lost": "#4A5560",
}
