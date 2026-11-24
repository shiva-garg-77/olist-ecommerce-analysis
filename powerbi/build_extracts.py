"""
Generate the Power BI extracts (star schema) from the cleaned parquet files.

Power BI reads these CSVs from powerbi/data/ — run this once after `python -m src.etl`.
The files are git-ignored because they are derived; regenerate them any time.

Run:  python -m powerbi.build_extracts
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.config import DATA_PROCESSED, ROOT

OUT = ROOT / "powerbi" / "data"
OUT.mkdir(parents=True, exist_ok=True)

MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def main() -> None:
    master = pd.read_parquet(DATA_PROCESSED / "master_delivered.parquet")
    fact = pd.read_parquet(DATA_PROCESSED / "order_fact.parquet")
    rfm = pd.read_csv(DATA_PROCESSED / "rfm.csv")

    # ------------------------------------------------------------------
    # fact_sales  (one row per order — every order-level page uses this)
    # ------------------------------------------------------------------
    primary = (
        master.groupby(["order_id", "category"], as_index=False)["item_total"].sum()
        .sort_values("item_total").drop_duplicates("order_id", keep="last")
        .rename(columns={"category": "primary_category"})[["order_id", "primary_category"]]
    )
    sales = fact.merge(primary, on="order_id", how="left")
    sales["primary_category"] = sales["primary_category"].fillna("Unknown")
    sales["year"] = sales["purchase_date"].dt.year
    sales["month_key"] = sales["purchase_month_key"]
    sales["day_key"] = sales["purchase_date"].dt.strftime("%Y-%m-%d")

    sales = sales[[
        "order_id", "customer_unique_id", "customer_state", "customer_city",
        "day_key", "month_key", "year", "purchase_dow", "purchase_hour",
        "primary_category", "payment_type", "payment_installments", "payment_value",
        "item_revenue", "freight_value", "n_items", "items_per_order",
        "delivery_days", "estimated_days", "delay_days", "is_late", "review_score",
    ]].rename(columns={"payment_value": "order_revenue", "item_revenue": "items_revenue"})
    sales.round(2).to_csv(OUT / "fact_sales.csv", index=False)
    print(f"fact_sales          {sales.shape[0]:>7,} rows")

    # ------------------------------------------------------------------
    # fact_items (item grain — product / seller pages)
    # ------------------------------------------------------------------
    items = master[[
        "order_id", "order_item_id", "product_id", "seller_id", "category",
        "seller_state", "price", "freight_value", "item_total",
        "purchase_month_key", "is_late", "review_score",
    ]].rename(columns={"purchase_month_key": "month_key"})
    items.round(2).to_csv(OUT / "fact_items.csv", index=False)
    print(f"fact_items          {items.shape[0]:>7,} rows")

    # ------------------------------------------------------------------
    # dim_customers (RFM lives here — one row per person)
    # ------------------------------------------------------------------
    cust = rfm[[
        "customer_unique_id", "customer_state", "first_purchase", "last_purchase",
        "frequency", "monetary", "recency", "r_score", "f_score", "m_score",
        "rfm_score", "segment", "avg_review",
    ]].rename(columns={"monetary": "lifetime_revenue"})
    cust.round(2).to_csv(OUT / "dim_customers.csv", index=False)
    print(f"dim_customers       {cust.shape[0]:>7,} rows")

    # ------------------------------------------------------------------
    # dim_products / dim_sellers
    # ------------------------------------------------------------------
    prods = pd.read_parquet(DATA_PROCESSED / "dim_products.parquet")
    prods.round(2).to_csv(OUT / "dim_products.csv", index=False)
    sellers = pd.read_parquet(DATA_PROCESSED / "dim_sellers.parquet")
    sellers.to_csv(OUT / "dim_sellers.csv", index=False)
    print(f"dim_products        {prods.shape[0]:>7,} rows")
    print(f"dim_sellers         {sellers.shape[0]:>7,} rows")

    # ------------------------------------------------------------------
    # dim_date
    # ------------------------------------------------------------------
    dates = pd.DataFrame({"date": pd.date_range("2016-01-01", "2018-12-31", freq="D")})
    dates["year"] = dates["date"].dt.year
    dates["month_key"] = dates["date"].dt.strftime("%Y-%m")
    dates["month_no"] = dates["date"].dt.month
    dates["month_name"] = dates["month_no"].map(MONTH_NAMES)
    dates["quarter"] = "Q" + dates["date"].dt.quarter.astype(str)
    dates["weekday"] = dates["date"].dt.day_name()
    dates["is_weekend"] = dates["date"].dt.dayofweek >= 5
    dates["date"] = dates["date"].dt.strftime("%Y-%m-%d")
    dates.to_csv(OUT / "dim_date.csv", index=False)
    print(f"dim_date            {dates.shape[0]:>7,} rows")

    meta = {
        "orders": int(len(sales)),
        "customers": int(len(cust)),
        "revenue": round(float(sales["order_revenue"].sum()), 2),
        "date_min": str(sales["day_key"].min()),
        "date_max": str(sales["day_key"].max()),
    }
    (OUT / "extract_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("\nPower BI extracts written to", OUT)


if __name__ == "__main__":
    main()
