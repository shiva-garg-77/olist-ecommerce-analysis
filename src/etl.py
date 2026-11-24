"""
Step 1 + Step 2 of the project: load the 9 Olist tables, understand them,
clean them, and materialise a single analysis-ready master table.

Run:  python -m src.etl
Out:  data/processed/*.parquet, data/processed/master.csv, data/processed/olist.db
"""

from __future__ import annotations

import json
import sqlite3
from typing import Dict

import numpy as np
import pandas as pd

from src.config import (
    DATA_PROCESSED,
    DATA_RAW,
    DB_PATH,
    RAW_FILES,
    REVENUE_STATUSES,
    EXCLUDED_STATUSES,
)

# --------------------------------------------------------------------------
# Step 1: Load
# --------------------------------------------------------------------------


def load_raw() -> Dict[str, pd.DataFrame]:
    """Load every CSV into a dictionary of DataFrames."""
    tables: Dict[str, pd.DataFrame] = {}
    for name, filename in RAW_FILES.items():
        tables[name] = pd.read_csv(DATA_RAW / filename, low_memory=False)
        print(f"  loaded {name:20s} {tables[name].shape[0]:>8,} rows x {tables[name].shape[1]} cols")
    return tables


def audit_tables(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Profile every table: size, duplicates, missing cells, key nulls."""
    rows = []
    key_map = {
        "orders": ["order_id", "customer_id"],
        "customers": ["customer_id", "customer_unique_id"],
        "order_items": ["order_id", "product_id"],
        "payments": ["order_id"],
        "reviews": ["order_id"],
        "products": ["product_id"],
        "sellers": ["seller_id"],
        "geolocation": ["geolocation_zip_code_prefix"],
        "category_translation": ["product_category_name"],
    }
    for name, df in tables.items():
        keys = key_map.get(name, [])
        rows.append(
            {
                "table": name,
                "rows": len(df),
                "columns": df.shape[1],
                "missing_cells_%": round(df.isna().sum().sum() / df.size * 100, 2),
                "duplicate_rows": int(df.duplicated().sum()),
                "unique_" + keys[0] if keys else "unique_key": df[keys[0]].nunique() if keys else np.nan,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Step 2: Clean, table by table
# --------------------------------------------------------------------------


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["customer_zip_code_prefix"] = df["customer_zip_code_prefix"].astype(int)
    df["customer_city"] = df["customer_city"].str.strip().str.title()
    df["customer_state"] = df["customer_state"].str.strip().str.upper()
    return df.drop_duplicates(subset=["customer_id"])


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Fix dtypes, engineer delivery metrics, flag cancellations."""
    df = df.copy()
    date_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for c in date_cols:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    # Orders without a purchase timestamp are unusable (there are 0 here, but
    # the guard keeps the pipeline robust if the extract changes).
    df = df.dropna(subset=["order_purchase_timestamp"])

    df["purchase_date"] = df["order_purchase_timestamp"].dt.normalize()
    df["purchase_month"] = df["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    # 'YYYY-MM' text key: grouping that behaves identically in SQLite, MySQL and Postgres
    df["purchase_month_key"] = df["order_purchase_timestamp"].dt.strftime("%Y-%m")
    df["purchase_year"] = df["order_purchase_timestamp"].dt.year
    df["purchase_dow"] = df["order_purchase_timestamp"].dt.day_name()
    df["purchase_hour"] = df["order_purchase_timestamp"].dt.hour

    # Delivery performance vs. the promise made at checkout
    df["delivery_days"] = (
        df["order_delivered_customer_date"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    df["estimated_days"] = (
        df["order_estimated_delivery_date"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    df["delay_days"] = (
        df["order_delivered_customer_date"] - df["order_estimated_delivery_date"]
    ).dt.total_seconds() / 86400
    df["is_late"] = (df["delay_days"] > 0).astype("Int64")
    df["approval_hours"] = (
        df["order_approved_at"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 3600
    df["carrier_days"] = (
        df["order_delivered_carrier_date"] - df["order_approved_at"]
    ).dt.total_seconds() / 86400
    df["last_mile_days"] = (
        df["order_delivered_customer_date"] - df["order_delivered_carrier_date"]
    ).dt.total_seconds() / 86400

    # Data-quality guards: a handful of timestamps sit before the purchase.
    for c in ["delivery_days", "carrier_days", "last_mile_days", "approval_hours"]:
        df.loc[df[c] < 0, c] = np.nan

    df["is_cancelled"] = df["order_status"].isin(EXCLUDED_STATUSES)
    df["is_revenue_order"] = df["order_status"].isin(REVENUE_STATUSES)
    return df.drop_duplicates(subset=["order_id"])


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors="coerce")
    for c in ["price", "freight_value"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["order_id", "product_id", "price"])
    df = df[df["price"] > 0]
    df["item_total"] = df["price"] + df["freight_value"].fillna(0)
    return df.drop_duplicates(subset=["order_id", "order_item_id"])


def clean_payments(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse to one row per order (an order can be paid in several ways)."""
    df = df.copy()
    df["payment_value"] = pd.to_numeric(df["payment_value"], errors="coerce").fillna(0)

    agg = (
        df.groupby("order_id")
        .agg(
            payment_value=("payment_value", "sum"),
            payment_installments=("payment_installments", "max"),
            n_payment_records=("payment_sequential", "count"),
        )
        .reset_index()
    )

    # Dominant payment type = the type that carried the most money.
    by_type = df.groupby(["order_id", "payment_type"], as_index=False)["payment_value"].sum()
    dominant = by_type.sort_values("payment_value").drop_duplicates("order_id", keep="last")
    dominant = dominant.rename(columns={"payment_type": "payment_type"})[["order_id", "payment_type"]]

    return agg.merge(dominant, on="order_id", how="left")


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate: some orders carry more than one review. Keep the latest."""
    df = df.copy()
    df["review_creation_date"] = pd.to_datetime(df["review_creation_date"], errors="coerce")
    df["review_answer_timestamp"] = pd.to_datetime(df["review_answer_timestamp"], errors="coerce")
    df["review_score"] = pd.to_numeric(df["review_score"], errors="coerce")
    df["has_comment"] = df["review_comment_message"].notna().astype(int)
    df = df.sort_values("review_answer_timestamp")
    df = df.drop_duplicates(subset=["order_id"], keep="last")
    return df[["order_id", "review_id", "review_score", "has_comment", "review_creation_date"]]


def clean_products(products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    df = products.copy()
    df = df.merge(translation, on="product_category_name", how="left")

    # 610 products have no category -> label them instead of dropping revenue.
    df["product_category_name"] = df["product_category_name"].fillna("sem_categoria")
    df["category"] = (
        df["product_category_name_english"]
        .fillna(df["product_category_name"])
        .str.replace("_", " ", regex=False)
        .str.title()
    )
    df["category"] = df["category"].fillna("Unknown")

    # Fix Olist's misspelled column names
    rename = {
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    }
    df = df.rename(columns=rename)

    num_cols = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
        "product_photos_qty",
        "product_name_length",
        "product_description_length",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df[c] = df[c].fillna(df[c].median())

    df["product_volume_cm3"] = (
        df["product_length_cm"] * df["product_height_cm"] * df["product_width_cm"]
    )
    return df[
        [
            "product_id",
            "product_category_name",
            "category",
            "product_weight_g",
            "product_volume_cm3",
            "product_photos_qty",
            "product_name_length",
            "product_description_length",
        ]
    ].drop_duplicates(subset=["product_id"])


def clean_sellers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["seller_zip_code_prefix"] = df["seller_zip_code_prefix"].astype(int)
    df["seller_state"] = df["seller_state"].str.strip().str.upper()
    df["seller_city"] = df["seller_city"].str.strip().str.title()
    return df.drop_duplicates(subset=["seller_id"])


def build_geo(geo: pd.DataFrame) -> pd.DataFrame:
    """
    1,000,163 raw geolocation rows collapse to ~19k zip-prefix centroids.
    Median lat/lng + most frequent city/state avoids the duplicate explosion
    you get from a naive join on zip prefix.
    """
    geo = geo.copy()
    base = (
        geo.groupby("geolocation_zip_code_prefix")
        .agg(
            lat=("geolocation_lat", "median"),
            lng=("geolocation_lng", "median"),
            n_points=("geolocation_lat", "size"),
        )
        .reset_index()
        .rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"})
    )
    city_mode = (
        geo.groupby(["geolocation_zip_code_prefix", "geolocation_city"])
        .size()
        .reset_index(name="n")
        .sort_values("n")
        .drop_duplicates("geolocation_zip_code_prefix", keep="last")
        .rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"})
    )
    city_mode["geolocation_city"] = city_mode["geolocation_city"].str.title()
    out = base.merge(
        city_mode[["zip_code_prefix", "geolocation_city"]], on="zip_code_prefix", how="left"
    )
    return out


# --------------------------------------------------------------------------
# Master table
# --------------------------------------------------------------------------


def build_master(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Grain: one row per order item.
    Every join is a left join from the revenue-bearing fact (order_items), so
    item revenue is never multiplied.
    """
    orders = tables["_orders_clean"]
    items = tables["_items_clean"]
    customers = tables["_customers_clean"]
    products = tables["_products_clean"]
    sellers = tables["_sellers_clean"]
    payments = tables["_payments_clean"]
    reviews = tables["_reviews_clean"]
    geo = tables["_geo"]

    master = (
        items.merge(orders, on="order_id", how="inner")
        .merge(customers, on="customer_id", how="left")
        .merge(products, on="product_id", how="left")
        .merge(sellers, on="seller_id", how="left")
        .merge(payments, on="order_id", how="left")
        .merge(reviews, on="order_id", how="left")
    )

    geo_c = geo.rename(
        columns={
            "zip_code_prefix": "customer_zip_code_prefix",
            "lat": "customer_lat",
            "lng": "customer_lng",
        }
    )[["customer_zip_code_prefix", "customer_lat", "customer_lng"]]
    master = master.merge(geo_c, on="customer_zip_code_prefix", how="left")

    master["is_weekend"] = master["purchase_dow"].isin(["Saturday", "Sunday"])
    master["freight_share"] = master["freight_value"] / master["item_total"].replace(0, np.nan)

    keep = [
        "order_id", "order_item_id", "customer_id", "customer_unique_id", "order_status",
        "order_purchase_timestamp", "purchase_date", "purchase_month", "purchase_month_key",
        "purchase_year",
        "purchase_dow", "purchase_hour", "is_weekend",
        "order_delivered_customer_date", "order_estimated_delivery_date",
        "delivery_days", "estimated_days", "delay_days", "is_late", "is_cancelled",
        "is_revenue_order", "approval_hours", "carrier_days", "last_mile_days",
        "product_id", "category", "product_category_name", "seller_id", "seller_state",
        "customer_state", "customer_city", "customer_zip_code_prefix", "customer_lat", "customer_lng",
        "price", "freight_value", "item_total", "freight_share",
        "payment_value", "payment_type", "payment_installments", "n_payment_records",
        "review_score", "has_comment", "product_weight_g", "product_volume_cm3",
        "product_photos_qty",
    ]
    return master[keep]


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def to_sqlite(master: pd.DataFrame, tables: Dict[str, pd.DataFrame]) -> None:
    """Load a clean star-ish schema into SQLite so the SQL layer runs for real."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)

    master.to_sql("master", con, index=False)

    orders = tables["_orders_clean"].copy()
    items = tables["_items_clean"].copy()
    customers = tables["_customers_clean"].copy()
    products = tables["_products_clean"].copy()
    sellers = tables["_sellers_clean"].copy()
    payments = tables["_payments_clean"].copy()
    reviews = tables["_reviews_clean"].copy()

    # SQLite cannot store tz-aware / Period objects - serialise as text.
    for df in (orders, items, reviews):
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")

    orders.to_sql("orders", con, index=False)
    items.to_sql("order_items", con, index=False)
    customers.to_sql("customers", con, index=False)
    products.to_sql("products", con, index=False)
    sellers.to_sql("sellers", con, index=False)
    payments.to_sql("payments", con, index=False)
    reviews.to_sql("reviews", con, index=False)

    cur = con.cursor()
    for ddl in [
        "CREATE INDEX idx_master_order ON master(order_id)",
        "CREATE INDEX idx_master_cust ON master(customer_unique_id)",
        "CREATE INDEX idx_master_month ON master(purchase_month)",
        "CREATE INDEX idx_orders_status ON orders(order_status)",
        "CREATE INDEX idx_items_order ON order_items(order_id)",
    ]:
        cur.execute(ddl)
    con.commit()
    con.close()
    print(f"  sqlite -> {DB_PATH}")


def main() -> dict:
    print("Step 1 | Loading raw tables")
    raw = load_raw()

    print("\nStep 1 | Data audit (raw)")
    audit = audit_tables(raw)
    print(audit.to_string(index=False))
    audit.to_csv(DATA_PROCESSED / "audit_raw.csv", index=False)

    print("\nStep 2 | Cleaning")
    tables: Dict[str, pd.DataFrame] = {
        "_customers_clean": clean_customers(raw["customers"]),
        "_orders_clean": clean_orders(raw["orders"]),
        "_items_clean": clean_order_items(raw["order_items"]),
        "_payments_clean": clean_payments(raw["payments"]),
        "_reviews_clean": clean_reviews(raw["reviews"]),
        "_products_clean": clean_products(raw["products"], raw["category_translation"]),
        "_sellers_clean": clean_sellers(raw["sellers"]),
        "_geo": build_geo(raw["geolocation"]),
    }

    print("\nStep 2 | Building master table")
    master = build_master(tables)
    print(f"  master: {len(master):,} item rows | {master['order_id'].nunique():,} orders | "
          f"{master['customer_unique_id'].nunique():,} customers")

    # ---- Persist -------------------------------------------------------
    # parquet only: the CSV copies of these frames are ~130 MB of duplication
    master.to_parquet(DATA_PROCESSED / "master.parquet", index=False)

    revenue = master[master["is_revenue_order"]]
    revenue.to_parquet(DATA_PROCESSED / "master_delivered.parquet", index=False)

    for name, key in [
        ("dim_customers", "_customers_clean"),
        ("dim_products", "_products_clean"),
        ("dim_sellers", "_sellers_clean"),
        ("fact_orders", "_orders_clean"),
        ("fact_payments", "_payments_clean"),
        ("fact_reviews", "_reviews_clean"),
    ]:
        tables[key].to_parquet(DATA_PROCESSED / f"{name}.parquet", index=False)

    to_sqlite(master, tables)

    # ---- Summary for the notebook / README -----------------------------
    status_counts = raw["orders"]["order_status"].value_counts().to_dict()
    summary = {
        "raw_rows": {k: int(len(v)) for k, v in raw.items()},
        "master_rows": int(len(master)),
        "master_orders": int(master["order_id"].nunique()),
        "unique_customers": int(master["customer_unique_id"].nunique()),
        "delivered_orders": int(orders_clean_count(master)),
        "cancelled_orders": int(
            tables["_orders_clean"]["is_cancelled"].sum()
        ),
        "cancelled_share_%": round(
            tables["_orders_clean"]["is_cancelled"].mean() * 100, 2
        ),
        "order_status_mix": status_counts,
        "date_range": [
            str(master["order_purchase_timestamp"].min()),
            str(master["order_purchase_timestamp"].max()),
        ],
        "total_revenue_item_grain": round(float(revenue["item_total"].sum()), 2),
        "total_payment_value": round(float(revenue.drop_duplicates("order_id")["payment_value"].sum()), 2),
        "missing_category_products": int((raw["products"]["product_category_name"].isna()).sum()),
        "orders_missing_delivery_date": int(tables["_orders_clean"]["order_delivered_customer_date"].isna().sum()),
        "duplicate_review_orders_removed": int(raw["reviews"]["order_id"].duplicated().sum()),
    }
    with open(DATA_PROCESSED / "etl_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("\nStep 2 | ETL summary")
    for k, v in summary.items():
        if k != "order_status_mix":
            print(f"  {k:36s} {v}")
    return summary


def orders_clean_count(master: pd.DataFrame) -> int:
    return int(master.loc[master["is_revenue_order"], "order_id"].nunique())


if __name__ == "__main__":
    main()
