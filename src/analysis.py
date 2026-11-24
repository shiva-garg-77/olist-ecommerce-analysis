"""
Step 4 (EDA) + Step 5 (advanced analysis) of the project.

Everything here is importable, so the notebook, the dashboard builder and the
report all derive their numbers from the same functions.

Run:  python -m src.analysis
Out:  reports/figures/*.png
      data/processed/{order_fact,rfm,customer_master,cohort_matrix,pareto_products,...}.csv
      data/processed/metrics.json          <- single source of truth for the dashboard
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

from src.config import (
    ANALYSIS_END,
    ANALYSIS_START,
    DATA_PROCESSED,
    PALETTE,
    SEGMENT_COLORS,
    SEGMENT_ORDER,
)
from src.viz import apply_style, brl, fmt_thousands, save

WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Loading & order-grain fact table
# ---------------------------------------------------------------------------


def load_delivered() -> pd.DataFrame:
    """Item-grain master, delivered orders only (the revenue universe)."""
    df = pd.read_parquet(DATA_PROCESSED / "master_delivered.parquet")
    df["purchase_month"] = pd.to_datetime(df["purchase_month"])
    return df


def build_order_fact(master: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse the item-grain master to ONE ROW PER ORDER.

    This matters: an order with 3 items appears 3x in the item table, so
    counting orders or summing payment_value there would triple-count. Every
    order-level KPI in this project comes from this frame.
    """
    items = (
        master.groupby("order_id")
        .agg(
            n_items=("order_item_id", "count"),
            item_revenue=("item_total", "sum"),
            freight_value=("freight_value", "sum"),
            n_products=("product_id", "nunique"),
            n_sellers=("seller_id", "nunique"),
        )
        .reset_index()
    )

    order_cols = [
        "order_id", "customer_unique_id", "customer_state", "customer_city",
        "purchase_date", "purchase_month", "purchase_month_key", "purchase_year",
        "purchase_dow", "purchase_hour", "is_weekend",
        "payment_value", "payment_type", "payment_installments",
        "review_score", "delivery_days", "estimated_days", "delay_days", "is_late",
        "customer_lat", "customer_lng",
    ]
    fact = master.drop_duplicates("order_id")[order_cols].merge(items, on="order_id", how="left")
    fact["items_per_order"] = fact["n_items"]
    return fact


def compute_kpis(order_fact: pd.DataFrame) -> Dict[str, float]:
    cust = order_fact.groupby("customer_unique_id")["order_id"].nunique()
    review = order_fact["review_score"].dropna()
    return {
        "total_revenue": round(float(order_fact["payment_value"].sum()), 2),
        "item_revenue": round(float(order_fact["item_revenue"].sum()), 2),
        "total_orders": int(order_fact["order_id"].nunique()),
        "total_items": int(order_fact["n_items"].sum()),
        "unique_customers": int(order_fact["customer_unique_id"].nunique()),
        "aov": round(float(order_fact["payment_value"].mean()), 2),
        "items_per_order": round(float(order_fact["n_items"].mean()), 2),
        "repeat_customers": int((cust > 1).sum()),
        "repeat_rate_pct": round(float((cust > 1).mean() * 100), 2),
        "avg_review_score": round(float(review.mean()), 2),
        "pct_5_star": round(float((review == 5).mean() * 100), 2),
        "pct_1_2_star": round(float((review <= 2).mean() * 100), 2),
        "avg_delivery_days": round(float(order_fact["delivery_days"].mean()), 1),
        "avg_estimated_days": round(float(order_fact["estimated_days"].mean()), 1),
        "pct_late": round(float(order_fact["is_late"].mean() * 100), 2),
        "freight_pct": round(float(order_fact["freight_value"].sum() / order_fact["item_revenue"].sum() * 100), 2),
        "avg_installments": round(float(order_fact["payment_installments"].mean()), 2),
        "date_min": str(order_fact["purchase_date"].min().date()),
        "date_max": str(order_fact["purchase_date"].max().date()),
        "n_states": int(order_fact["customer_state"].nunique()),
    }


# ---------------------------------------------------------------------------
# Step 4: EDA charts
# ---------------------------------------------------------------------------


def analysis_window(order_fact: pd.DataFrame) -> pd.DataFrame:
    """Drop the two partial edge months so the trend is honest."""
    m = order_fact["purchase_date"]
    return order_fact[(m >= ANALYSIS_START) & (m <= ANALYSIS_END)]


def fig_monthly_trend(order_fact: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        order_fact.groupby("purchase_month_key")
        .agg(orders=("order_id", "nunique"), revenue=("item_revenue", "sum"),
             customers=("customer_unique_id", "nunique"))
        .reset_index()
        .sort_values("purchase_month_key")
    )
    monthly["aov"] = monthly["revenue"] / monthly["orders"]
    monthly["revenue_3m"] = monthly["revenue"].rolling(3, min_periods=1).mean()

    fig, ax = plt.subplots(figsize=(12, 4.6))
    x = np.arange(len(monthly))
    ax.bar(x, monthly["revenue"], color=PALETTE["primary"], alpha=0.85, width=0.68,
           label="Monthly revenue (item grain)")
    ax.plot(x, monthly["revenue_3m"], color=PALETTE["accent"], lw=2.4, label="3-month moving average")
    ax.set_xticks(x)
    ax.set_xticklabels(monthly["purchase_month_key"], rotation=60, ha="right", fontsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: brl(v)))
    ax.set_ylabel("Revenue")
    ax.set_title("Monthly revenue trend — growth is driven by order volume, not basket size")

    ax2 = ax.twinx()
    ax2.plot(x, monthly["orders"], color=PALETTE["secondary"], lw=1.8, ls="--", marker="o",
             ms=3, label="Orders")
    ax2.set_ylabel("Orders")
    ax2.grid(False)

    peak = monthly.loc[monthly["revenue"].idxmax()]
    ax.annotate(
        f"Peak: {peak['purchase_month_key']}\n{brl(peak['revenue'])}",
        xy=(monthly["purchase_month_key"].tolist().index(peak["purchase_month_key"]), peak["revenue"]),
        xytext=(-72, -46), textcoords="offset points", fontsize=8.5, color=PALETTE["ink"],
        arrowprops=dict(arrowstyle="->", color=PALETTE["muted"], lw=0.9),
    )
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8.5)
    save(fig, "01_monthly_revenue_trend")
    plt.close(fig)
    return monthly


def fig_seasonality(win: pd.DataFrame) -> pd.DataFrame:
    """Revenue per calendar day so partial months do not distort the picture."""
    tmp = win.copy()
    tmp["month_name"] = tmp["purchase_date"].dt.month
    tmp["days_in_month"] = tmp["purchase_date"].dt.days_in_month
    # revenue per active day of that month-of-year
    seas = (
        tmp.groupby(["purchase_month_key", "month_name"])
        .agg(revenue=("item_revenue", "sum"), days=("purchase_date", "nunique"))
        .reset_index()
    )
    seas["rev_per_day"] = seas["revenue"] / seas["days"]
    month_avg = seas.groupby("month_name")["rev_per_day"].mean().reindex(range(1, 13))

    hour_dow = (
        tmp.groupby(["purchase_dow", "purchase_hour"])
        .size()
        .unstack(fill_value=0)
        .reindex(WEEKDAY_ORDER)
    )

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.2), gridspec_kw={"width_ratios": [1, 1.5]})
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    colors = [PALETTE["accent"] if v == month_avg.max() else PALETTE["primary"] for v in month_avg]
    axes[0].bar(names, month_avg.values, color=colors)
    axes[0].set_title("Seasonality: average revenue per day, by month")
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda v, p: brl(v)))
    axes[0].tick_params(axis="x", labelsize=8)

    sns.heatmap(hour_dow, cmap="Blues", ax=axes[1], cbar_kws={"label": "orders"}, linewidths=0.3,
                linecolor="white")
    axes[1].set_title("When customers buy: weekday x hour")
    axes[1].set_xlabel("Hour of day")
    axes[1].set_ylabel("")
    save(fig, "02_seasonality")
    plt.close(fig)
    return month_avg.rename("avg_rev_per_day").reset_index()


def fig_payment_mix(order_fact: pd.DataFrame) -> pd.DataFrame:
    pay = (
        order_fact.groupby("payment_type")
        .agg(orders=("order_id", "nunique"), revenue=("payment_value", "sum"),
             aov=("payment_value", "mean"), installments=("payment_installments", "mean"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    pay["order_share"] = pay["orders"] / pay["orders"].sum() * 100
    pay = pay[pay["payment_type"].notna()]

    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    sns.barplot(data=pay, y="payment_type", x="orders", ax=axes[0], color=PALETTE["primary"])
    axes[0].set_title("Orders by payment method")
    axes[0].set_xlabel("Orders")
    axes[0].set_ylabel("")

    sns.barplot(data=pay, y="payment_type", x="aov", ax=axes[1], color=PALETTE["secondary"])
    axes[1].set_title("Average order value by payment method")
    axes[1].set_xlabel("AOV (R$)")
    axes[1].set_ylabel("")
    for ax in axes:
        ax.tick_params(axis="y", labelsize=9)
    save(fig, "03_payment_methods")
    plt.close(fig)
    return pay


def fig_review_vs_delay(order_fact: pd.DataFrame) -> pd.DataFrame:
    df = order_fact.dropna(subset=["review_score", "delay_days"]).copy()
    bins = [-100, -15, -1, 0.99, 7, 15, 1000]
    labels = ["15+ d early", "Early", "On promise day", "1-7 d late", "8-15 d late", "15+ d late"]
    df["delay_bucket"] = pd.cut(df["delay_days"], bins=bins, labels=labels)
    agg = (
        df.groupby("delay_bucket", observed=True)
        .agg(orders=("order_id", "count"), avg_score=("review_score", "mean"),
             pct_low=("review_score", lambda s: (s <= 2).mean() * 100),
             avg_delivery=("delivery_days", "mean"))
        .reset_index()
    )

    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    bars = ax.bar(agg["delay_bucket"], agg["avg_score"], color=PALETTE["primary"], alpha=0.9)
    for b, (_, r) in zip(bars, agg.iterrows()):
        ax.text(b.get_x() + b.get_width() / 2, r["avg_score"] + 0.07, f"{r['avg_score']:.2f}",
                ha="center", fontsize=9, fontweight="bold")
    ax.set_ylim(0, 5.2)
    ax.set_xticks(range(len(agg)))
    ax.set_xticklabels([f"{b}\nn={n:,}" for b, n in zip(agg["delay_bucket"], agg["orders"])],
                       fontsize=8.6)
    ax.set_ylabel("Average review score (1-5)")
    ax.set_title("Late delivery destroys satisfaction — on-time orders average 4.3 stars")

    ax2 = ax.twinx()
    ax2.plot(agg["delay_bucket"], agg["pct_low"], color=PALETTE["danger"], marker="o", lw=1.8,
             label="% 1-2 star reviews")
    ax2.set_ylabel("% of 1-2 star reviews", color=PALETTE["danger"])
    ax2.set_ylim(0, 100)
    ax2.grid(False)
    ax2.legend(loc="upper left", fontsize=8.5)
    save(fig, "04_review_vs_delay")
    plt.close(fig)
    return agg


def fig_delivery_distribution(order_fact: pd.DataFrame) -> pd.DataFrame:
    df = order_fact.dropna(subset=["delivery_days"])
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 3.9))
    sns.histplot(df["delivery_days"].clip(0, 60), bins=40, ax=axes[0], color=PALETTE["primary"])
    axes[0].axvline(df["delivery_days"].median(), color=PALETTE["accent"], ls="--", lw=1.6,
                    label=f"median {df['delivery_days'].median():.0f} days")
    axes[0].set_title("Delivery time distribution (days, clipped at 60)")
    axes[0].set_xlabel("Days from purchase to delivery")
    axes[0].legend(fontsize=8.5)

    sns.histplot(df["delay_days"].clip(-40, 40), bins=50, ax=axes[1], color=PALETTE["secondary"])
    axes[1].axvline(0, color=PALETTE["danger"], ls="--", lw=1.6, label="promised date")
    axes[1].set_title("Delivered vs promised date (negative = early)")
    axes[1].set_xlabel("Days late / early")
    axes[1].legend(fontsize=8.5)
    save(fig, "05_delivery_distribution")
    plt.close(fig)
    return df[["delivery_days", "delay_days", "estimated_days"]].describe().reset_index()


def fig_category_aov(master: pd.DataFrame) -> pd.DataFrame:
    """Category revenue vs average order value for that category."""
    cat = (
        master.groupby("category")
        .agg(revenue=("item_total", "sum"), orders=("order_id", "nunique"),
             units=("order_item_id", "count"))
        .reset_index()
    )
    cat["aov"] = cat["revenue"] / cat["orders"]
    cat["rev_per_unit"] = cat["revenue"] / cat["units"]
    cat = cat[cat["orders"] >= 100].sort_values("revenue", ascending=False)
    top = cat.head(15).sort_values("aov")

    fig, ax = plt.subplots(figsize=(10, 5.4))
    norm = (top["aov"] - top["aov"].min()) / (top["aov"].max() - top["aov"].min() + 1e-9)
    colors = [plt.cm.Blues(0.35 + 0.6 * n) for n in norm]
    ax.barh(top["category"], top["aov"], color=colors)
    for y, (_, r) in enumerate(top.iterrows()):
        ax.text(r["aov"] + 2, y, f"R$ {r['aov']:,.0f}  ({r['orders']:,} orders)",
                va="center", fontsize=8.5)
    ax.set_xlabel("Average order value (R$)")
    ax.set_title("Top 15 categories by revenue — average order value differs ~3x")
    ax.set_xlim(0, top["aov"].max() * 1.35)
    save(fig, "06_category_aov")
    plt.close(fig)
    return cat


def fig_geography(master: pd.DataFrame) -> pd.DataFrame:
    st = (
        master.groupby("customer_state")
        .agg(revenue=("item_total", "sum"), orders=("order_id", "nunique"),
             customers=("customer_unique_id", "nunique"),
             avg_delivery=("delivery_days", "mean"), pct_late=("is_late", "mean"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    st["rev_share"] = st["revenue"] / st["revenue"].sum() * 100
    top = st.head(12).sort_values("revenue")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"width_ratios": [1.1, 1]})
    axes[0].barh(top["customer_state"], top["revenue"], color=PALETTE["primary"])
    for y, (_, r) in enumerate(top.iterrows()):
        axes[0].text(r["revenue"] + r["revenue"] * 0.01, y, f"{r['rev_share']:.1f}%",
                     va="center", fontsize=8)
    axes[0].set_title("Revenue by state (top 12)")
    axes[0].xaxis.set_major_formatter(FuncFormatter(lambda v, p: brl(v)))
    axes[0].set_xlim(0, top["revenue"].max() * 1.15)

    top_late = st[st["orders"] >= 300].sort_values("pct_late").tail(12)
    axes[1].barh(top_late["customer_state"], top_late["pct_late"] * 100, color=PALETTE["danger"])
    axes[1].set_title("Share of late deliveries by state (%)")
    axes[1].set_xlabel("% of delivered orders late")
    save(fig, "07_geography")
    plt.close(fig)
    return st


# ---------------------------------------------------------------------------
# Step 5a: RFM
# ---------------------------------------------------------------------------


def segment_customers(rfm: pd.DataFrame) -> pd.Series:
    """
    Priority ladder on (r_score 1-5, f_score 1-3, m_score 1-5).
    The FIRST matching rule wins, so every customer lands in exactly one segment.
    Mirrors the CASE ladder in sql/02_analysis_queries.sql (Q10).
    """
    r, f, m = rfm["r_score"], rfm["f_score"], rfm["m_score"]
    seg = np.select(
        [
            (f >= 2) & (r >= 4) & (m >= 3),
            (f >= 2) & (r >= 4),
            (f >= 2) & (r <= 2) & (m >= 4),
            (f >= 2) & (r <= 2),
            (f >= 2) & (r == 3),
            (f == 1) & (r >= 4),
            (f == 1) & (r == 3),
            (f == 1) & (r == 2),
        ],
        [
            "Champions",
            "Loyal Customers",
            "Cannot Lose Them",
            "At Risk",
            "Need Attention",
            "New Customers",
            "Promising",
            "Hibernating",
        ],
        default="Lost",
    )
    return pd.Series(seg, index=rfm.index)


def compute_rfm(order_fact: pd.DataFrame) -> pd.DataFrame:
    """
    RFM at customer_unique_id level.

    Olist quirks handled here:
      * customer_id is regenerated for every order, so frequency must be
        computed on customer_unique_id - otherwise every customer looks new.
      * ~97% of customers order once, so quintile-based F scores are useless
        (all customers get the same F). Explicit buckets 1 / 2 / 3+ are used.
      * Monetary uses payment_value at order grain (the money collected).
    """
    snapshot = order_fact["purchase_date"].max() + timedelta(days=1)
    rfm = (
        order_fact.groupby("customer_unique_id")
        .agg(
            last_purchase=("purchase_date", "max"),
            first_purchase=("purchase_date", "min"),
            frequency=("order_id", "nunique"),
            monetary=("payment_value", "sum"),
            items=("n_items", "sum"),
            avg_review=("review_score", "mean"),
            customer_state=("customer_state", "first"),
        )
        .reset_index()
    )
    rfm["recency"] = (snapshot - rfm["last_purchase"]).dt.days

    # Rank-based quintiles avoid qcut failing on duplicate bin edges.
    rfm["r_score"] = pd.qcut(rfm["recency"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["m_score"] = pd.qcut(rfm["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["f_score"] = np.where(rfm["frequency"] >= 3, 3, np.where(rfm["frequency"] == 2, 2, 1))

    rfm["rfm_score"] = rfm["r_score"].astype(str) + rfm["f_score"].astype(str) + rfm["m_score"].astype(str)
    rfm["rfm_sum"] = rfm["r_score"] + rfm["f_score"] + rfm["m_score"]
    rfm["segment"] = segment_customers(rfm)
    rfm["segment"] = pd.Categorical(rfm["segment"], categories=SEGMENT_ORDER, ordered=True)
    rfm["snapshot_date"] = snapshot.date().isoformat()
    return rfm


def rfm_summary(rfm: pd.DataFrame) -> pd.DataFrame:
    s = (
        rfm.groupby("segment", observed=True)
        .agg(
            customers=("customer_unique_id", "count"),
            revenue=("monetary", "sum"),
            avg_monetary=("monetary", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_recency=("recency", "mean"),
            avg_review=("avg_review", "mean"),
        )
        .reset_index()
    )
    s = s[s["customers"] > 0]
    s["customer_share_pct"] = s["customers"] / s["customers"].sum() * 100
    s["revenue_share_pct"] = s["revenue"] / s["revenue"].sum() * 100
    s["revenue_per_customer"] = s["revenue"] / s["customers"]
    return s.sort_values("revenue", ascending=False).reset_index(drop=True)


def fig_rfm(rfm: pd.DataFrame, summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8), gridspec_kw={"width_ratios": [1.25, 1]})

    plot = summary.sort_values("revenue")
    colors = [SEGMENT_COLORS.get(s, PALETTE["muted"]) for s in plot["segment"]]
    y = np.arange(len(plot))
    axes[0].barh(y - 0.2, plot["customer_share_pct"], height=0.4, color=colors, alpha=0.55,
                 label="% of customers")
    axes[0].barh(y + 0.2, plot["revenue_share_pct"], height=0.4, color=colors,
                 label="% of revenue")
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(plot["segment"], fontsize=9)
    for yi, (_, r) in zip(y, plot.iterrows()):
        axes[0].text(max(r["customer_share_pct"], r["revenue_share_pct"]) + 0.7, yi,
                     f"{r['customers']:,} cust. / {r['revenue_share_pct']:.1f}% rev",
                     va="center", fontsize=7.6, color=PALETTE["muted"])
    axes[0].set_xlabel("% of total")
    axes[0].set_title("RFM segments: customer share vs revenue share")
    axes[0].set_xlim(0, 48)
    axes[0].legend(fontsize=8.5, loc="lower right")

    pivot = rfm.pivot_table(index="r_score", columns="m_score", values="monetary",
                            aggfunc="mean", observed=True)
    sns.heatmap(pivot, cmap="YlGnBu", annot=True, fmt=".0f", ax=axes[1],
                cbar_kws={"label": "avg customer spend (R$)"}, linewidths=0.5, linecolor="white")
    axes[1].set_title("Avg customer spend by R x M score")
    axes[1].set_xlabel("Monetary score (5 = highest spend)")
    axes[1].set_ylabel("Recency score (5 = most recent)")
    axes[1].invert_yaxis()
    save(fig, "08_rfm_segments")
    plt.close(fig)

    # Segment value matrix: size vs revenue per customer
    fig, ax = plt.subplots(figsize=(9.5, 5))
    for _, r in summary.iterrows():
        ax.scatter(r["customers"], r["revenue_per_customer"], s=max(r["revenue_share_pct"] * 45, 40),
                   color=SEGMENT_COLORS.get(r["segment"], PALETTE["muted"]),
                   alpha=0.85, edgecolor="white", linewidth=1.4, zorder=3)
        ax.annotate(r["segment"], (r["customers"], r["revenue_per_customer"]),
                    xytext=(9, 6), textcoords="offset points", fontsize=8.5)
    ax.set_xscale("log")
    ax.set_xlabel("Number of customers (log scale)")
    ax.set_ylabel("Revenue per customer (R$)")
    ax.set_title("Where the money is: segment size vs value per customer")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"R$ {v:,.0f}"))
    save(fig, "09_rfm_value_matrix")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Step 5b: Cohort retention
# ---------------------------------------------------------------------------


def cohort_analysis(order_fact: pd.DataFrame, max_periods: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    first = order_fact.groupby("customer_unique_id")["purchase_month_key"].min().rename("cohort_month")
    act = order_fact[["customer_unique_id", "purchase_month_key"]].drop_duplicates()
    act = act.merge(first, on="customer_unique_id")

    def to_idx(k: pd.Series) -> pd.Series:
        return k.str[:4].astype(int) * 12 + k.str[5:7].astype(int)

    act["period"] = to_idx(act["purchase_month_key"]) - to_idx(act["cohort_month"])
    act = act[(act["period"] >= 0) & (act["period"] <= max_periods)]

    sizes = first.value_counts().rename("cohort_size")
    counts = act.groupby(["cohort_month", "period"])["customer_unique_id"].nunique().reset_index()
    counts = counts.merge(sizes, left_on="cohort_month", right_index=True)
    counts["retention_pct"] = counts["customer_unique_id"] / counts["cohort_size"] * 100

    matrix = counts.pivot(index="cohort_month", columns="period", values="retention_pct")
    # keep cohorts with a meaningful base so the heatmap is readable
    matrix = matrix[matrix.index.isin(sizes[sizes >= 300].index)]
    matrix = matrix.sort_index()
    return counts, matrix


def fig_cohort(matrix: pd.DataFrame) -> None:
    # Month 0 is 100% by definition and would flatten the colour scale,
    # so it is shown separately rather than in the heatmap.
    body = matrix.drop(columns=[0], errors="ignore")
    fig, ax = plt.subplots(figsize=(9.8, 5.6))
    sns.heatmap(body, annot=True, fmt=".1f", cmap="Blues", ax=ax, linewidths=0.6,
                linecolor="white", cbar_kws={"label": "% of cohort ordering again"},
                vmin=0, vmax=float(np.nanmax(body.values)) if body.notna().any().any() else 1)
    ax.set_title("Monthly cohort retention (%) after the first purchase "
                 "(month 0 = 100% by definition and is masked)")
    ax.set_xlabel("Months since first order")
    ax.set_ylabel("Cohort (first purchase month)")
    save(fig, "10_cohort_retention")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Step 5c: Pareto
# ---------------------------------------------------------------------------


def pareto_products(master: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, float]]:
    prod = (
        master.groupby(["product_id", "category"])
        .agg(revenue=("item_total", "sum"), units=("order_item_id", "count"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    prod["rank"] = np.arange(1, len(prod) + 1)
    prod["cum_revenue"] = prod["revenue"].cumsum()
    prod["cum_pct_revenue"] = prod["cum_revenue"] / prod["revenue"].sum() * 100
    prod["cum_pct_products"] = prod["rank"] / len(prod) * 100

    n80 = int((prod["cum_pct_revenue"] <= 80).sum()) + 1
    top20_share = float(prod.loc[prod["rank"] <= int(len(prod) * 0.2), "revenue"].sum()
                        / prod["revenue"].sum() * 100)
    stats = {
        "n_products": int(len(prod)),
        "n_products_for_80pct": n80,
        "pct_products_for_80pct": round(n80 / len(prod) * 100, 2),
        "top20pct_products_revenue_share": round(top20_share, 2),
        "top10pct_products_revenue_share": round(
            float(prod.loc[prod["rank"] <= int(len(prod) * 0.1), "revenue"].sum()
                  / prod["revenue"].sum() * 100), 2),
    }
    return prod, stats


def fig_pareto(prod: pd.DataFrame, stats: Dict[str, float]) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.plot(prod["cum_pct_products"], prod["cum_pct_revenue"], color=PALETTE["primary"], lw=2.2)
    ax.fill_between(prod["cum_pct_products"], prod["cum_pct_revenue"], alpha=0.12,
                    color=PALETTE["primary"])
    ax.axhline(80, color=PALETTE["danger"], ls="--", lw=1.3)
    ax.axvline(stats["pct_products_for_80pct"], color=PALETTE["danger"], ls="--", lw=1.3)
    ax.scatter([stats["pct_products_for_80pct"]], [80], color=PALETTE["danger"], zorder=5, s=55)
    ax.annotate(
        f"{stats['pct_products_for_80pct']:.0f}% of SKUs\n= 80% of revenue\n({stats['n_products_for_80pct']:,} products)",
        xy=(stats["pct_products_for_80pct"], 80), xytext=(14, -42), textcoords="offset points",
        fontsize=9, arrowprops=dict(arrowstyle="->", color=PALETTE["muted"]),
    )
    ax.set_xlabel("% of products (ranked by revenue)")
    ax.set_ylabel("% of cumulative revenue")
    ax.set_title("Product Pareto curve — a long tail of low-impact SKUs")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 101)
    save(fig, "11_product_pareto")
    plt.close(fig)


def fig_basket(master: pd.DataFrame, order_fact: pd.DataFrame) -> Dict[str, float]:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 3.9))
    sns.histplot(order_fact["n_items"].clip(1, 6), bins=np.arange(0.5, 6.6, 1), ax=axes[0],
                 color=PALETTE["primary"])
    axes[0].set_title("Items per order")
    axes[0].set_xlabel("Items in the order")
    axes[0].set_xticks(range(1, 7))

    sns.histplot(order_fact["payment_value"].clip(0, 600), bins=45, ax=axes[1],
                 color=PALETTE["secondary"])
    axes[1].set_title("Order value distribution (clipped at R$600)")
    axes[1].set_xlabel("Order value (R$)")
    save(fig, "12_basket_and_value")
    plt.close(fig)
    return {
        "single_item_order_pct": round(float((order_fact["n_items"] == 1).mean() * 100), 2),
        "median_order_value": round(float(order_fact["payment_value"].median()), 2),
        "order_value_p90": round(float(order_fact["payment_value"].quantile(0.9)), 2),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_all(make_plots: bool = True) -> Dict:
    if make_plots:
        apply_style()

    print("Loading item-grain master ...")
    master = load_delivered()
    order_fact = build_order_fact(master)
    print(f"  {len(master):,} item rows -> {len(order_fact):,} orders")

    kpis = compute_kpis(order_fact)
    win = analysis_window(order_fact)

    print("Step 4 | EDA")
    monthly = fig_monthly_trend(win) if make_plots else None
    seasonality = fig_seasonality(win) if make_plots else None
    payments = fig_payment_mix(order_fact) if make_plots else None
    review_delay = fig_review_vs_delay(order_fact) if make_plots else None
    delivery_desc = fig_delivery_distribution(order_fact) if make_plots else None
    categories = fig_category_aov(master) if make_plots else None
    states = fig_geography(master) if make_plots else None

    print("Step 5a | RFM")
    rfm = compute_rfm(order_fact)
    rfm_sum = rfm_summary(rfm)
    if make_plots:
        fig_rfm(rfm, rfm_sum)

    print("Step 5b | Cohort retention")
    cohort_counts, cohort_matrix = cohort_analysis(order_fact)
    if make_plots:
        fig_cohort(cohort_matrix)

    print("Step 5c | Pareto")
    prod_pareto, pareto_stats = pareto_products(master)
    if make_plots:
        fig_pareto(prod_pareto, pareto_stats)

    basket_stats = fig_basket(master, order_fact) if make_plots else {}

    # ---------------- persistence ----------------
    order_fact.to_parquet(DATA_PROCESSED / "order_fact.parquet", index=False)
    rfm.drop(columns=["segment"]).assign(segment=rfm["segment"].astype(str)).to_csv(
        DATA_PROCESSED / "rfm.csv", index=False)
    rfm_sum.to_csv(DATA_PROCESSED / "rfm_summary.csv", index=False)
    cohort_matrix.to_csv(DATA_PROCESSED / "cohort_matrix.csv")
    cohort_counts.to_csv(DATA_PROCESSED / "cohort_detail.csv", index=False)
    prod_pareto.head(1000).to_csv(DATA_PROCESSED / "pareto_products.csv", index=False)

    if monthly is not None:
        monthly.to_csv(DATA_PROCESSED / "monthly_kpis.csv", index=False)
        payments.to_csv(DATA_PROCESSED / "payment_mix.csv", index=False)
        review_delay.to_csv(DATA_PROCESSED / "review_vs_delay.csv", index=False)
        categories.to_csv(DATA_PROCESSED / "category_stats.csv", index=False)
        states.to_csv(DATA_PROCESSED / "state_stats.csv", index=False)

    # daily series for the dashboard date filter
    daily = (
        order_fact.groupby("purchase_date")
        .agg(orders=("order_id", "nunique"), revenue=("item_revenue", "sum"),
             customers=("customer_unique_id", "nunique"))
        .reset_index()
        .sort_values("purchase_date")
    )
    daily["purchase_date"] = daily["purchase_date"].dt.strftime("%Y-%m-%d")
    daily.to_csv(DATA_PROCESSED / "daily_series.csv", index=False)

    metrics = {
        "kpis": kpis,
        "pareto": pareto_stats,
        "basket": basket_stats,
        "rfm": rfm_sum.round(2).to_dict(orient="records"),
        "payment_mix": payments.round(2).to_dict(orient="records") if payments is not None else [],
        "review_vs_delay": review_delay.round(2).to_dict(orient="records") if review_delay is not None else [],
        "delivery_stats": {
            "median_delivery_days": round(float(order_fact["delivery_days"].median()), 1),
            "p90_delivery_days": round(float(order_fact["delivery_days"].quantile(0.9)), 1),
            "pct_early": round(float((order_fact["delay_days"] < 0).mean() * 100), 2),
            "pct_on_time": round(float((order_fact["delay_days"] <= 0).mean() * 100), 2),
        },
        "top_categories": categories.head(15).round(2).to_dict(orient="records") if categories is not None else [],
        "top_states": states.head(12).round(2).to_dict(orient="records") if states is not None else [],
        "monthly": monthly.round(2).to_dict(orient="records") if monthly is not None else [],
        "cohort_matrix": (
            cohort_matrix.reset_index().round(2).to_dict(orient="records") if not cohort_matrix.empty else []
        ),
        "repeat": {},
    }

    # repeat purchase distribution (the single most important behavioural fact)
    freq = order_fact.groupby("customer_unique_id")["order_id"].nunique()
    metrics["repeat"] = {
        "one_order_pct": round(float((freq == 1).mean() * 100), 2),
        "two_order_pct": round(float((freq == 2).mean() * 100), 2),
        "three_plus_pct": round(float((freq >= 3).mean() * 100), 2),
        "revenue_from_repeat_pct": round(
            float(order_fact[order_fact["customer_unique_id"].isin(freq[freq > 1].index)]["payment_value"].sum()
                  / order_fact["payment_value"].sum() * 100), 2),
    }

    with open(DATA_PROCESSED / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)

    print("\nKPIs")
    for k, v in kpis.items():
        print(f"  {k:24s} {v}")
    print("\nRFM segments")
    print(rfm_sum[["segment", "customers", "customer_share_pct", "revenue_share_pct", "revenue_per_customer"]]
          .to_string(index=False))
    print("\nPareto:", pareto_stats)
    print("Repeat:", metrics["repeat"])
    return metrics


if __name__ == "__main__":
    run_all()
