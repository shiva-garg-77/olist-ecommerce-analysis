"""
Step 6: build a self-contained, interactive HTML dashboard (no server, no CDN,
works offline) that mirrors the 4 pages required by the project brief:

    Page 1  Overview            KPIs + monthly trend + payment mix + satisfaction
    Page 2  Products            category revenue / AOV / Pareto / SKU table
    Page 3  Customers           RFM segments + cohort retention + repeat rate
    Page 4  Geography/Delivery  state performance + delivery promise vs reality

Filters (month range, state, category) recompute pages 1, 2 and 4 live in the
browser from the embedded order-level fact table.

Run:  python -m dashboard.build_dashboard
Out:  dashboard/olist_dashboard.html
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.offline as po

from src.analysis import (
    build_order_fact,
    cohort_analysis,
    compute_rfm,
    load_delivered,
    rfm_summary,
)
from src.config import DASHBOARD_DIR, DATA_PROCESSED, PALETTE

OUT_PATH = DASHBOARD_DIR / "olist_dashboard.html"


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


def primary_category(master: pd.DataFrame) -> pd.Series:
    """An order can span categories; use the one with the highest value."""
    top = (
        master.groupby(["order_id", "category"], as_index=False)["item_total"].sum()
        .sort_values("item_total")
        .drop_duplicates("order_id", keep="last")
    )
    return top.set_index("order_id")["category"]


def build_payload() -> dict:
    master = load_delivered()
    fact = build_order_fact(master)

    # primary category per order + category id lookup
    fact = fact.merge(
        primary_category(master).rename("primary_category"), left_on="order_id",
        right_index=True, how="left",
    )
    fact["primary_category"] = fact["primary_category"].fillna("Unknown")

    cats = sorted(fact["primary_category"].unique().tolist())
    cat_idx = {c: i for i, c in enumerate(cats)}
    states = sorted(fact["customer_state"].dropna().unique().tolist())
    state_idx = {s: i for i, s in enumerate(states)}
    pays = ["credit_card", "boleto", "voucher", "debit_card", "not_defined"]
    pay_idx = {p: i for i, p in enumerate(pays)}

    months = sorted(fact["purchase_month_key"].unique().tolist())
    month_idx = {m: i for i, m in enumerate(months)}
    d0 = pd.Timestamp("2016-01-01")

    fact = fact.sort_values("purchase_date")
    cust_codes, cust_uniq = pd.factorize(fact["customer_unique_id"])

    payload = {
        "states": states,
        "categories": cats,
        "payments": pays,
        "months": months,
        "orders": {
            "d": (fact["purchase_date"] - d0).dt.days.astype(int).tolist(),
            "m": fact["purchase_month_key"].map(month_idx).astype(int).tolist(),
            "s": fact["customer_state"].map(state_idx).fillna(-1).astype(int).tolist(),
            "c": fact["primary_category"].map(cat_idx).astype(int).tolist(),
            "r": fact["payment_value"].fillna(0).round(2).tolist(),
            "it": fact["n_items"].fillna(0).astype(int).tolist(),
            "dd": fact["delivery_days"].round(1).fillna(-1).tolist(),
            "dl": fact["delay_days"].round(1).fillna(-999).tolist(),
            "ed": fact["estimated_days"].round(1).fillna(-1).tolist(),
            "late": fact["is_late"].fillna(0).astype(int).tolist(),
            "rv": fact["review_score"].fillna(-1).astype(int).tolist(),
            "p": fact["payment_type"].map(pay_idx).fillna(4).astype(int).tolist(),
            "cu": cust_codes.tolist(),
        },
        "n_customers": int(len(cust_uniq)),
    }

    # ---- RFM (point-in-time snapshot, not re-computed on filter) ----------
    rfm = compute_rfm(fact)
    summary = rfm_summary(rfm)
    payload["rfm"] = [
        {
            "segment": r["segment"],
            "customers": int(r["customers"]),
            "customer_share": round(float(r["customer_share_pct"]), 2),
            "revenue": round(float(r["revenue"]), 2),
            "revenue_share": round(float(r["revenue_share_pct"]), 2),
            "arpu": round(float(r["revenue_per_customer"]), 2),
            "avg_freq": round(float(r["avg_frequency"]), 2),
            "avg_recency": round(float(r["avg_recency"]), 0),
            "avg_review": round(float(r["avg_review"]), 2),
        }
        for _, r in summary.iterrows()
    ]
    seg_colors = {
        "Champions": "#0B6E99", "Loyal Customers": "#1F9E89", "New Customers": "#4FB3A9",
        "Promising": "#F2A93B", "Need Attention": "#E08D2E", "At Risk": "#D64545",
        "Cannot Lose Them": "#A83232", "Hibernating": "#7A8794", "Lost": "#4A5560",
    }
    payload["segment_colors"] = seg_colors

    # ---- cohort matrix ---------------------------------------------------
    _, matrix = cohort_analysis(fact)
    matrix = matrix.drop(columns=[0], errors="ignore")   # period 0 = 100% by definition
    payload["cohort"] = {
        "cohorts": [str(i) for i in matrix.index],
        "periods": [int(c) for c in matrix.columns],
        "z": [[None if pd.isna(v) else round(float(v), 2) for v in row] for row in matrix.values],
    }

    # ---- Pareto curve (down-sampled) ------------------------------------
    prod = (
        master.groupby("product_id")["item_total"].sum().sort_values(ascending=False)
    )
    cum = prod.cumsum() / prod.sum() * 100
    xp = np.linspace(0, 100, 201)
    step = max(len(cum) // 400, 1)
    payload["pareto"] = {
        "x": (np.arange(1, len(cum) + 1)[::step] / len(cum) * 100).round(2).tolist(),
        "y": cum.values[::step].round(2).tolist(),
        "n_products": int(len(cum)),
        "pct_for_80": round(float((cum <= 80).sum() + 1) / len(cum) * 100, 2),
        "top20_share": round(float(prod.head(int(len(prod) * 0.2)).sum() / prod.sum() * 100), 2),
    }

    # ---- repeat purchase + satisfaction facts ---------------------------
    freq = fact.groupby("customer_unique_id")["order_id"].nunique()
    payload["repeat"] = {
        "one": round(float((freq == 1).mean() * 100), 2),
        "two": round(float((freq == 2).mean() * 100), 2),
        "three": round(float((freq >= 3).mean() * 100), 2),
        "repeat_revenue": round(
            float(fact[fact["customer_unique_id"].isin(freq[freq > 1].index)]["payment_value"].sum()
                  / fact["payment_value"].sum() * 100), 2),
    }
    payload["meta"] = {
        "orders": int(len(fact)),
        "items": int(fact["n_items"].sum()),
        "date_min": str(fact["purchase_date"].min().date()),
        "date_max": str(fact["purchase_date"].max().date()),
        "snapshot": rfm["snapshot_date"].iloc[0],
        "generated": pd.Timestamp.now().strftime("%d %b %Y, %H:%M"),
    }
    return payload


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist E-commerce | Sales &amp; Customer Behaviour Dashboard</title>
<script>__PLOTLY__</script>
<style>
  :root{
    --ink:#1B2733; --muted:#6B7A8A; --line:#E3E8EE; --bg:#F5F7FA; --card:#FFFFFF;
    --primary:#0B6E99; --secondary:#1F9E89; --accent:#F2A93B; --danger:#D64545;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
       font-size:13px;}
  header{background:linear-gradient(120deg,#0B3C56 0%,#0B6E99 60%,#1F9E89 100%);
         color:#fff;padding:18px 26px 14px;}
  header h1{margin:0;font-size:20px;letter-spacing:.2px;font-weight:650}
  header p{margin:4px 0 0;font-size:12px;opacity:.86}
  .wrap{max-width:1440px;margin:0 auto;padding:0 18px 40px}
  /* ---- filter bar ---- */
  .filters{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap;background:var(--card);
           border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-top:16px;
           box-shadow:0 6px 18px rgba(16,42,67,.08);position:sticky;top:8px;z-index:20}
  .fgroup{display:flex;flex-direction:column;gap:4px}
  .fgroup label{font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:600}
  select{border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:12px;
         background:#fff;color:var(--ink);min-width:120px;font-family:inherit}
  select:focus{outline:2px solid #BFE0EE;border-color:var(--primary)}
  #states{min-width:150px;height:66px}
  .btn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 13px;font-size:12px;
       cursor:pointer;color:var(--ink);font-weight:550}
  .btn:hover{background:#F0F6F9;border-color:#BFE0EE}
  .btn.primary{background:var(--primary);color:#fff;border-color:var(--primary)}
  .btn.primary:hover{background:#095B7F}
  .hint{font-size:10px;color:var(--muted)}
  /* ---- KPI cards ---- */
  .kpis{display:grid;grid-template-columns:repeat(8,1fr);gap:10px;margin:16px 0 6px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:11px 13px}
  .kpi .k{font-size:10px;text-transform:uppercase;letter-spacing:.55px;color:var(--muted);font-weight:600}
  .kpi .v{font-size:19px;font-weight:680;margin-top:3px;letter-spacing:-.3px}
  .kpi .s{font-size:10.5px;color:var(--muted);margin-top:2px}
  /* ---- tabs ---- */
  nav.tabs{display:flex;gap:6px;margin:16px 0 12px;flex-wrap:wrap}
  nav.tabs button{border:1px solid var(--line);background:#fff;border-radius:9px 9px 0 0;padding:9px 16px;
                  font-size:12.5px;font-weight:600;color:var(--muted);cursor:pointer;border-bottom:none}
  nav.tabs button.on{background:var(--card);color:var(--primary);box-shadow:0 -2px 0 var(--primary) inset}
  .page{display:none}.page.on{display:block}
  /* ---- grid ---- */
  .grid{display:grid;gap:12px}
  .g2{grid-template-columns:1fr 1fr}
  .g3{grid-template-columns:1fr 1fr 1fr}
  .g21{grid-template-columns:1.45fr 1fr}
  .card{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:8px 10px 4px}
  .card h3{margin:6px 4px 0;font-size:12.5px;font-weight:650}
  .card .sub{margin:2px 4px 4px;font-size:10.5px;color:var(--muted)}
  .insight{background:#FFF8EC;border:1px solid #F5DDB4;border-left:4px solid var(--accent);
           border-radius:9px;padding:10px 14px;font-size:12px;line-height:1.5;margin:12px 0}
  .insight b{color:#8A5A00}
  table{width:100%;border-collapse:collapse;font-size:11.5px}
  th{text-align:left;color:var(--muted);font-weight:600;font-size:10px;text-transform:uppercase;
     letter-spacing:.5px;border-bottom:1px solid var(--line);padding:6px 6px}
  td{padding:6px;border-bottom:1px solid #F0F3F6}
  td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
  tr:hover td{background:#F7FAFC}
  .pill{display:inline-block;padding:2px 7px;border-radius:20px;font-size:10px;font-weight:600;color:#fff}
  footer{color:var(--muted);font-size:10.5px;margin-top:22px;line-height:1.6;text-align:center}
  @media(max-width:1200px){.kpis{grid-template-columns:repeat(4,1fr)}.g3{grid-template-columns:1fr}.g21,.g2{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>Olist Brazilian E-commerce — Sales &amp; Customer Behaviour</h1>
  <p>Problem: how do we grow revenue, and which customers actually drive it? &nbsp;|&nbsp;
     <span id="meta1"></span></p>
</header>

<div class="wrap">
  <div class="filters">
    <div class="fgroup"><label>From month</label><select id="from"></select></div>
    <div class="fgroup"><label>To month</label><select id="to"></select></div>
    <div class="fgroup"><label>State <span class="hint">(all, ctrl+click)</span></label><select id="states" multiple></select></div>
    <div class="fgroup"><label>Category</label><select id="category"></select></div>
    <button class="btn primary" id="reset">Reset filters</button>
    <button class="btn" id="csv">Download filtered CSV</button>
    <span class="hint" id="filterNote" style="margin-left:auto;max-width:340px;text-align:right"></span>
  </div>

  <div class="kpis" id="kpis"></div>

  <nav class="tabs">
    <button data-tab="overview" class="on">1 · Sales overview</button>
    <button data-tab="products">2 · Products &amp; categories</button>
    <button data-tab="customers">3 · Customer segments</button>
    <button data-tab="geo">4 · Geography &amp; delivery</button>
  </nav>

  <!-- ================= PAGE 1 ================= -->
  <div class="page on" id="page-overview">
    <div class="grid g21">
      <div class="card"><h3>Monthly revenue &amp; orders</h3>
        <div class="sub">Revenue = order value collected (delivered orders). Line = 3-month moving average.</div>
        <div id="ch-trend" style="height:330px"></div></div>
      <div class="card"><h3>Payment methods</h3>
        <div class="sub">Share of orders vs revenue</div>
        <div id="ch-pay" style="height:330px"></div></div>
    </div>
    <div class="grid g2" style="margin-top:12px">
      <div class="card"><h3>Does a late delivery hurt the review score?</h3>
        <div class="sub">Average review score by days late vs the promised date</div>
        <div id="ch-delay" style="height:300px"></div></div>
      <div class="card"><h3>Revenue distribution (order value)</h3>
        <div class="sub">Orders up to R$1,000 (a 0.3% tail is left out for readability)</div>
        <div id="ch-value" style="height:300px"></div></div>
    </div>
    <div class="insight" id="insight1"></div>
  </div>

  <!-- ================= PAGE 2 ================= -->
  <div class="page" id="page-products">
    <div class="grid g21">
      <div class="card"><h3>Revenue by category</h3>
        <div class="sub">Top 12 categories in the current filter</div>
        <div id="ch-cat" style="height:390px"></div></div>
      <div class="card"><h3>Revenue vs average order value</h3>
        <div class="sub">Bubble size = orders · hover a bubble for the category name</div>
        <div id="ch-catsct" style="height:390px"></div></div>
    </div>
    <div class="grid g2" style="margin-top:12px">
      <div class="card"><h3>Product Pareto curve (all time)</h3>
        <div class="sub" id="pareto-sub"></div>
        <div id="ch-pareto" style="height:320px"></div></div>
      <div class="card"><h3>Category table</h3>
        <div class="sub">Filtered period</div>
        <div style="height:320px;overflow:auto"><table id="tbl-cat"></table></div></div>
    </div>
    <div class="insight" id="insight2"></div>
  </div>

  <!-- ================= PAGE 3 ================= -->
  <div class="page" id="page-customers">
    <div class="grid g21">
      <div class="card"><h3>RFM segments: who is worth keeping</h3>
        <div class="sub">Point-in-time snapshot (<span id="snap"></span>) · % of customers vs % of revenue ·
          not re-computed by the filters above</div>
        <div id="ch-rfm" style="height:400px"></div></div>
      <div class="card"><h3>Repeat purchase reality</h3>
        <div class="sub">Share of customers by number of orders</div>
        <div id="ch-repeat" style="height:400px"></div></div>
    </div>
    <div class="grid g21" style="margin-top:12px">
      <div class="card"><h3>Monthly cohort retention (%)</h3>
        <div class="sub">Of the customers who first bought in a month, what % ordered again N months later</div>
        <div id="ch-cohort" style="height:400px"></div></div>
      <div class="card"><h3>Segment table</h3>
        <div class="sub">All-time RFM snapshot</div>
        <div style="height:400px;overflow:auto"><table id="tbl-rfm"></table></div></div>
    </div>
    <div class="insight" id="insight3"></div>
  </div>

  <!-- ================= PAGE 4 ================= -->
  <div class="page" id="page-geo">
    <div class="grid g2">
      <div class="card"><h3>Revenue by state</h3>
        <div class="sub">Top 12 states in the current filter</div>
        <div id="ch-state" style="height:370px"></div></div>
      <div class="card"><h3>Delivery promise vs reality</h3>
        <div class="sub">Average promised days vs average actual days by state</div>
        <div id="ch-promise" style="height:370px"></div></div>
    </div>
    <div class="grid g2" style="margin-top:12px">
      <div class="card"><h3>Late deliveries by state (%)</h3>
        <div class="sub">States with 300+ orders in the filter</div>
        <div id="ch-late" style="height:330px"></div></div>
      <div class="card"><h3>State table</h3>
        <div class="sub">Filtered period</div>
        <div style="height:330px;overflow:auto"><table id="tbl-state"></table></div></div>
    </div>
    <div class="insight" id="insight4"></div>
  </div>

  <footer>
    Source: Olist Brazilian E-commerce public dataset (9 tables, 99,441 orders) · cleaned in Python/Pandas,
    analysed in SQL + pandas, dashboard built with Plotly.<br>
    Revenue definition: <b>order revenue = payment_value</b> for KPIs; <b>item revenue = price + freight</b>
    for product/category/state cuts. Cancelled &amp; unavailable orders are excluded.
  </footer>
</div>

<script>
const DATA = __DATA__;
const O = DATA.orders;
const $ = (id) => document.getElementById(id);
const fmtBRL = (v, dp = 0) => "R$ " + v.toLocaleString("en-US", {minimumFractionDigits: dp, maximumFractionDigits: dp});
const fmtK = (v) => v >= 1e6 ? "R$ " + (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? "R$ " + (v / 1e3).toFixed(0) + "k" : "R$ " + v.toFixed(0);
const fmtN = (v) => v.toLocaleString("en-US");
const pct = (v, dp = 1) => v.toFixed(dp) + "%";

const FONT = {family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif', size: 11, color: "#1B2733"};
const LAYOUT = (extra = {}) => Object.assign({
  margin: {l: 54, r: 12, t: 8, b: 40}, font: FONT, paper_bgcolor: "#fff", plot_bgcolor: "#fff",
  hoverlabel: {bgcolor: "#fff", bordercolor: "#DDE3EA", font: {color: "#1B2733", size: 11}},
  xaxis: {gridcolor: "#EEF2F5", zeroline: false, linecolor: "#E3E8EE"},
  yaxis: {gridcolor: "#EEF2F5", zeroline: false, linecolor: "#E3E8EE"},
  showlegend: false, bargap: 0.28
}, extra);
const CONF = {displayModeBar: false, responsive: true};

/* ---------------- filter state ---------------- */
const state = {
  from: 0, to: DATA.months.length - 1,
  states: new Set(DATA.states), cat: "all"
};

function initFilters() {
  const f = $("from"), t = $("to");
  DATA.months.forEach((m, i) => {
    f.insertAdjacentHTML("beforeend", `<option value="${i}">${m}</option>`);
    t.insertAdjacentHTML("beforeend", `<option value="${i}">${m}</option>`);
  });
  f.value = 0; t.value = DATA.months.length - 1;

  const s = $("states");
  DATA.states.forEach(st => s.insertAdjacentHTML("beforeend",
    `<option value="${st}" selected>${st}</option>`));
  const c = $("category");
  c.insertAdjacentHTML("beforeend", `<option value="all">All categories</option>`);
  DATA.categories.forEach((cat, i) => c.insertAdjacentHTML("beforeend",
    `<option value="${i}">${cat}</option>`));

  f.onchange = () => { state.from = +f.value; if (state.to < state.from) { state.to = state.from; t.value = state.to; } render(); };
  t.onchange = () => { state.to = +t.value; if (state.from > state.to) { state.from = state.to; f.value = state.from; } render(); };
  s.onchange = () => { state.states = new Set([...s.selectedOptions].map(o => o.value)); if (!state.states.size) { [...s.options].forEach(o => o.selected = true); state.states = new Set(DATA.states); } render(); };
  c.onchange = () => { state.cat = c.value; render(); };
  $("reset").onclick = () => {
    f.value = 0; t.value = DATA.months.length - 1; c.value = "all";
    [...s.options].forEach(o => o.selected = true);
    state.from = 0; state.to = DATA.months.length - 1; state.cat = "all"; state.states = new Set(DATA.states);
    render();
  };
  $("csv").onclick = () => exportCsv();

  $("meta1").textContent = DATA.meta.date_min + " → " + DATA.meta.date_max + "  ·  " +
    fmtN(DATA.meta.orders) + " delivered orders  ·  " + fmtN(DATA.n_customers) + " unique customers";
}

/* ---------------- aggregation ---------------- */
function sliced() {
  const idx = [];
  const st = state.cat === "all" ? -1 : +state.cat;
  for (let i = 0; i < O.d.length; i++) {
    const m = O.m[i];
    if (m < state.from || m > state.to) continue;
    if (st >= 0 && O.c[i] !== st) continue;
    if (!state.states.has(DATA.states[O.s[i]])) continue;
    idx.push(i);
  }
  return idx;
}

function aggregate(idx) {
  const byMonth = new Map();
  const byCat = new Map();
  const byState = new Map();
  const byPay = new Map();
  const custs = new Set();
  let revenue = 0, items = 0, lateN = 0, ddSum = 0, ddN = 0, rvSum = 0, rvN = 0;
  let promisedSum = 0, promisedN = 0, valueHist = new Array(20).fill(0);

  for (const i of idx) {
    const m = O.m[i], cat = DATA.categories[O.c[i]], st = DATA.states[O.s[i]];
    revenue += O.r[i]; items += O.it[i]; custs.add(O.cu[i]);

    let mo = byMonth.get(m);
    if (!mo) { mo = {revenue: 0, orders: 0, customers: new Set()}; byMonth.set(m, mo); }
    mo.revenue += O.r[i]; mo.orders += 1; mo.customers.add(O.cu[i]);

    let cc = byCat.get(cat);
    if (!cc) { cc = {revenue: 0, orders: 0, items: 0}; byCat.set(cat, cc); }
    cc.revenue += O.r[i]; cc.orders += 1; cc.items += O.it[i];

    let ss = byState.get(st);
    if (!ss) { ss = {revenue: 0, orders: 0, late: 0, dd: 0, ddN: 0, prom: 0, promN: 0, rv: 0, rvN: 0}; byState.set(st, ss); }
    ss.revenue += O.r[i]; ss.orders += 1;

    let pp = byPay.get(DATA.payments[O.p[i]]);
    if (!pp) { pp = {revenue: 0, orders: 0}; byPay.set(DATA.payments[O.p[i]], pp); }
    pp.revenue += O.r[i]; pp.orders += 1;

    if (O.r[i] > 0 && O.r[i] < 1000) valueHist[Math.floor(O.r[i] / 50)] += 1;

    if (O.dd[i] > 0) {
      ddSum += O.dd[i]; ddN += 1; ss.dd += O.dd[i]; ss.ddN += 1;
      if (O.late[i]) { lateN += 1; ss.late += 1; }
    }
    if (O.ed[i] > 0) { promisedSum += O.ed[i]; promisedN += 1; ss.prom += O.ed[i]; ss.promN += 1; }
    if (O.rv[i] > 0) { rvSum += O.rv[i]; rvN += 1; ss.rv += O.rv[i]; ss.rvN += 1; }
  }
  return {revenue, items, orders: idx.length, customers: custs.size, byMonth, byCat, byState, byPay,
          lateN, ddSum, ddN, promisedSum, promisedN, rvSum, rvN, valueHist};
}

/* ---------------- KPI cards ---------------- */
function renderKpis(a) {
  const aov = a.orders ? a.revenue / a.orders : 0;
  const pieces = [
    ["Revenue", fmtK(a.revenue), "net of vouchers"],
    ["Orders", fmtN(a.orders), "delivered"],
    ["Avg order value", fmtBRL(aov), "per order"],
    ["Customers", fmtN(a.customers), "unique buyers"],
    ["Items sold", fmtN(a.items), (a.items / Math.max(a.orders, 1)).toFixed(2) + " per order"],
    ["Avg review", a.rvN ? (a.rvSum / a.rvN).toFixed(2) + " ★" : "–", a.rvN ? fmtN(a.rvN) + " reviews" : ""],
    ["Late deliveries", a.ddN ? pct(a.lateN / a.ddN * 100) : "–", a.ddN ? fmtN(a.lateN) + " orders" : ""],
    ["Avg delivery", a.ddN ? (a.ddSum / a.ddN).toFixed(1) + " d" : "–",
     a.promisedN ? "promised " + (a.promisedSum / a.promisedN).toFixed(1) + " d" : ""]
  ];
  $("kpis").innerHTML = pieces.map(([k, v, s]) =>
    `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");
  $("filterNote").textContent = DATA.months[state.from] + " → " + DATA.months[state.to] +
    " · " + (state.states.size === DATA.states.length ? "all states" : state.states.size + " states") +
    " · " + (state.cat === "all" ? "all categories" : DATA.categories[+state.cat]);
}

/* ---------------- charts ---------------- */
function renderTrend(a) {
  const months = [], rev = [], ord = [], ma = [];
  for (let m = state.from; m <= state.to; m++) {
    const v = a.byMonth.get(m) || {revenue: 0, orders: 0};
    months.push(DATA.months[m]); rev.push(v.revenue); ord.push(v.orders);
  }
  rev.forEach((v, i) => {
    const w = rev.slice(Math.max(0, i - 2), i + 1);
    ma.push(w.reduce((x, y) => x + y, 0) / w.length);
  });
  Plotly.react("ch-trend", [
    {type: "bar", x: months, y: rev, name: "Revenue", marker: {color: "#0B6E99"}, opacity: .9,
     hovertemplate: "%{x}<br>Revenue: R$ %{y:,.0f}<extra></extra>"},
    {type: "scatter", mode: "lines", x: months, y: ma, name: "3M avg", yaxis: "y",
     line: {color: "#F2A93B", width: 2.6}, hoverinfo: "skip"},
    {type: "scatter", mode: "lines+markers", x: months, y: ord, name: "Orders", yaxis: "y2",
     line: {color: "#1F9E89", width: 1.8, dash: "dot"}, marker: {size: 4},
     hovertemplate: "%{x}<br>Orders: %{y:,.0f}<extra></extra>"}
  ], LAYOUT({
    showlegend: true, legend: {orientation: "h", y: 1.12, x: 0, font: {size: 10}},
    xaxis: {tickangle: -55, tickfont: {size: 9}, gridcolor: "#F2F5F8"},
    yaxis: {tickprefix: "R$ ", tickformat: "~s", gridcolor: "#EEF2F5"},
    yaxis2: {overlaying: "y", side: "right", showgrid: false, tickformat: "~s", title: {text: "orders", font: {size: 9}}},
    margin: {l: 58, r: 42, t: 24, b: 56}
  }), CONF);
}

function renderPayment(a) {
  const labels = [], rev = [], ords = [];
  a.byPay.forEach((v, k) => {
    if (v.orders < 1) return;
    labels.push(k.replace("_", " ")); rev.push(v.revenue); ords.push(v.orders);
  });
  const order = rev.map((_, i) => i).sort((x, y) => rev[y] - rev[x]);
  const L = order.map(i => labels[i]), R = order.map(i => rev[i]), Oo = order.map(i => ords[i]);
  Plotly.react("ch-pay", [{
    type: "bar", orientation: "h", y: L, x: R,
    marker: {color: L.map((_, i) => ["#0B6E99", "#1F9E89", "#F2A93B", "#7A8794", "#D64545"][i % 5])},
    text: Oo.map((o, i) => pct(o / a.orders * 100) + " of orders"), textposition: "auto",
    textfont: {size: 10, color: "#fff"}, cliponaxis: false,
    hovertemplate: "%{y}<br>R$ %{x:,.0f}<extra></extra>"
  }], LAYOUT({margin: {l: 92, r: 24, t: 10, b: 34},
    xaxis: {tickprefix: "R$ ", tickformat: "~s"}, yaxis: {autorange: "reversed"}}), CONF);
}

function renderDelay(a, idx) {
  const labels = ["15+ d early", "Early", "On promise", "1-7 d late", "8-15 d late", "15+ d late"];
  const score = labels.map(() => 0), n = labels.map(() => 0), low = labels.map(() => 0);
  // Same buckets as sql/02_analysis_queries.sql (Q7): delay = delivered - promised
  for (const i of idx) {
    if (O.rv[i] < 1 || O.dl[i] < -900) continue;
    const d = O.dl[i];
    let b;
    if (d <= -15) b = 0; else if (d < 0) b = 1; else if (d < 1) b = 2;
    else if (d <= 7) b = 3; else if (d <= 15) b = 4; else b = 5;
    score[b] += O.rv[i]; n[b] += 1;
    if (O.rv[i] <= 2) low[b] += 1;
  }
  const avg = score.map((s, i) => n[i] ? s / n[i] : null);
  Plotly.react("ch-delay", [
    {type: "bar", x: labels, y: avg, marker: {color: "#0B6E99"},
     text: avg.map((v, i) => v === null ? "" : v.toFixed(2) + " ★ (n=" + fmtN(n[i]) + ")"),
     textposition: "outside", textfont: {size: 9.5},
     hovertemplate: "%{x}<br>avg score %{y:.2f}<extra></extra>"},
    {type: "scatter", mode: "lines+markers", x: labels, y: low.map((l, i) => n[i] ? l / n[i] * 100 : null),
     yaxis: "y2", line: {color: "#D64545", width: 2}, marker: {size: 5},
     hovertemplate: "%{x}<br>%{y:.1f}% are 1-2 star<extra></extra>"}
  ], LAYOUT({
    yaxis: {range: [0, 5.4], title: {text: "avg review score", font: {size: 9.5}}},
    yaxis2: {overlaying: "y", side: "right", range: [0, 100], showgrid: false,
             title: {text: "% 1-2 star", font: {size: 9.5}}, tickfont: {color: "#D64545"}},
    margin: {l: 46, r: 46, t: 14, b: 46}, xaxis: {tickfont: {size: 9}}
  }), CONF);
}

function renderValue(a) {
  const x = a.valueHist.map((_, i) => i * 50 + 25);
  Plotly.react("ch-value", [{
    type: "bar", x: x, y: a.valueHist, marker: {color: "#1F9E89"},
    hovertemplate: "R$ %{x}<br>%{y:,} orders<extra></extra>"
  }], LAYOUT({
    xaxis: {tickprefix: "R$ ", title: {text: "order value", font: {size: 9.5}}},
    yaxis: {title: {text: "orders", font: {size: 9.5}}},
    margin: {l: 48, r: 12, t: 10, b: 44}
  }), CONF);
}

function renderCategories(a) {
  const rows = [...a.byCat.entries()].map(([k, v]) => ({cat: k, ...v, aov: v.revenue / v.orders}))
    .sort((x, y) => y.revenue - x.revenue);
  const top = rows.slice(0, 12).reverse();
  Plotly.react("ch-cat", [{
    type: "bar", orientation: "h", y: top.map(r => r.cat), x: top.map(r => r.revenue),
    marker: {color: "#0B6E99"}, customdata: top.map(r => [r.orders, r.aov]),
    text: top.map(r => fmtK(r.revenue)), textposition: "outside", textfont: {size: 9},
    cliponaxis: false,
    hovertemplate: "%{y}<br>Revenue: R$ %{x:,.0f}<br>Orders: %{customdata[0]:,}<br>AOV: R$ %{customdata[1]:,.0f}<extra></extra>"
  }], LAYOUT({margin: {l: 150, r: 96, t: 8, b: 34}, xaxis: {tickprefix: "R$ ", tickformat: "~s"}}), CONF);

  Plotly.react("ch-catsct", [{
    type: "scatter", mode: "markers",
    x: rows.map(r => r.aov), y: rows.map(r => r.revenue),
    text: rows.map((r, i) => i < 7 ? r.cat : ""),
    marker: {size: rows.map(r => Math.max(5, Math.sqrt(r.orders) * 0.5)), color: "#1F9E89", opacity: .55,
             line: {color: "#fff", width: 1}},
    textposition: "top center", textfont: {size: 8.5, color: "#54637A"},
    hovertemplate: "%{text}<br>AOV: R$ %{x:,.0f}<br>Revenue: R$ %{y:,.0f}<extra></extra>"
  }], LAYOUT({
    xaxis: {title: {text: "average order value (R$)", font: {size: 9.5}}},
    yaxis: {title: {text: "revenue", font: {size: 9.5}}, tickprefix: "R$ ", tickformat: "~s"},
    margin: {l: 58, r: 12, t: 10, b: 44}
  }), CONF);

  const t = rows.slice(0, 15);
  $("tbl-cat").innerHTML =
    `<thead><tr><th>Category</th><th class="n">Revenue</th><th class="n">Orders</th>
     <th class="n">AOV</th><th class="n">Share</th></tr></thead><tbody>` +
    t.map(r => `<tr><td>${r.cat}</td><td class="n">${fmtBRL(r.revenue)}</td>
      <td class="n">${fmtN(r.orders)}</td><td class="n">${fmtBRL(r.aov)}</td>
      <td class="n">${pct(r.revenue / a.revenue * 100)}</td></tr>`).join("") + "</tbody>";
}

function renderPareto() {
  const P = DATA.pareto;
  $("pareto-sub").textContent = `${P.pct_for_80}% of the ${fmtN(P.n_products)} SKUs generate 80% of revenue · ` +
    `top 20% of SKUs = ${P.top20_share}% of revenue`;
  Plotly.react("ch-pareto", [{
    type: "scatter", mode: "lines", x: P.x, y: P.y,
    line: {color: "#0B6E99", width: 2.4}, fill: "tozeroy", fillcolor: "rgba(11,110,153,.10)",
    hovertemplate: "%{x:.0f}% of SKUs<br>%{y:.1f}% of revenue<extra></extra>"
  }], LAYOUT({
    shapes: [
      {type: "line", x0: P.pct_for_80, x1: P.pct_for_80, y0: 0, y1: 80, line: {color: "#D64545", dash: "dash", width: 1.4}},
      {type: "line", x0: 0, x1: P.pct_for_80, y0: 80, y1: 80, line: {color: "#D64545", dash: "dash", width: 1.4}}
    ],
    xaxis: {title: {text: "% of products (ranked by revenue)", font: {size: 9.5}}, range: [0, 100]},
    yaxis: {title: {text: "% cumulative revenue", font: {size: 9.5}}, range: [0, 101]},
    margin: {l: 52, r: 14, t: 10, b: 44}
  }), CONF);
}

function renderRfm() {
  const R = DATA.rfm.slice().sort((a, b) => a.revenue - b.revenue);
  var traceCust = {
    type: "bar", orientation: "h", name: "% customers",
    y: R.map(r => r.segment), x: R.map(r => r.customer_share),
    marker: {color: R.map(r => DATA.segment_colors[r.segment] || "#8894A0"), opacity: .45},
    hovertemplate: "%{y}<br>%{x:.1f}% of customers<extra></extra>"
  };
  var traceRev = {
    type: "bar", orientation: "h", name: "% revenue",
    y: R.map(r => r.segment), x: R.map(r => r.revenue_share),
    marker: {color: R.map(r => DATA.segment_colors[r.segment] || "#8894A0")},
    text: R.map(r => r.customers.toLocaleString() + " cust."), textposition: "outside",
    textfont: {size: 8.5, color: "#6B7A8A"},
    hovertemplate: "%{y}<br>%{x:.1f}% of revenue<extra></extra>"
  };
  Plotly.react("ch-rfm", [traceCust, traceRev], LAYOUT({
    barmode: "group", bargap: 0.34, bargroupgap: 0.08,
    showlegend: true, legend: {orientation: "h", y: 1.1, font: {size: 10}},
    xaxis: {title: {text: "% of total", font: {size: 9.5}}, range: [0, 48]},
    margin: {l: 122, r: 70, t: 28, b: 40}
  }), CONF);

  const Rp = DATA.repeat;
  Plotly.react("ch-repeat", [{
    type: "bar", x: ["1 order", "2 orders", "3+ orders"],
    y: [Rp.one, Rp.two, Rp.three],
    marker: {color: ["#0B6E99", "#1F9E89", "#F2A93B"]},
    text: [pct(Rp.one), pct(Rp.two), pct(Rp.three)], textposition: "outside",
    hovertemplate: "%{x}<br>%{y:.2f}% of customers<extra></extra>"
  }], LAYOUT({
    yaxis: {title: {text: "% of customers", font: {size: 9.5}}, range: [0, 108]},
    xaxis: {title: {text: `repeat buyers = 100 − ${Rp.one}% → only ${Rp.repeat_revenue}% of revenue`, font: {size: 9.5}}},
    margin: {l: 52, r: 14, t: 14, b: 52}
  }), CONF);

  $("tbl-rfm").innerHTML =
    `<thead><tr><th>Segment</th><th class="n">Customers</th><th class="n">% cust</th>
      <th class="n">Revenue</th><th class="n">% rev</th><th class="n">R$/cust</th>
      <th class="n">Freq</th></tr></thead><tbody>` +
    DATA.rfm.map(r => `<tr><td><span class="pill" style="background:${DATA.segment_colors[r.segment] || "#8894A0"}">
      ${r.segment}</span></td><td class="n">${fmtN(r.customers)}</td>
      <td class="n">${pct(r.customer_share)}</td><td class="n">${fmtBRL(r.revenue)}</td>
      <td class="n">${pct(r.revenue_share)}</td><td class="n">${fmtBRL(r.arpu)}</td>
      <td class="n">${r.avg_freq.toFixed(2)}</td></tr>`).join("") + "</tbody>";
}

function renderCohort() {
  Plotly.react("ch-cohort", [{
    type: "heatmap", z: DATA.cohort.z, x: DATA.cohort.periods, y: DATA.cohort.cohorts,
    colorscale: [[0, "#F7FAFC"], [0.15, "#D6E9F2"], [0.45, "#7FB6CF"], [1, "#0B3C56"]],
    xgap: 2, ygap: 2, showscale: true,
    colorbar: {thickness: 10, title: {text: "%", font: {size: 9}}, tickfont: {size: 9}},
    hovertemplate: "Cohort %{y}<br>Month %{x}: %{z:.2f}%<extra></extra>"
  }], LAYOUT({
    xaxis: {title: {text: "months since first order", font: {size: 9.5}}, dtick: 1, tickfont: {size: 9}},
    yaxis: {autorange: "reversed", tickfont: {size: 8}, tickmode: "array",
            tickvals: DATA.cohort.cohorts, title: {text: "cohort", font: {size: 9.5}}},
    margin: {l: 64, r: 10, t: 10, b: 44}
  }), CONF);
}

function renderGeo(a) {
  const rows = [...a.byState.entries()].map(([k, v]) => ({
    st: k, ...v, aov: v.revenue / v.orders,
    latePct: v.ddN ? v.late / v.ddN * 100 : 0,
    avgDd: v.ddN ? v.dd / v.ddN : null,
    avgProm: v.promN ? v.prom / v.promN : null
  })).sort((x, y) => y.revenue - x.revenue);
  const top = rows.slice(0, 12).reverse();

  Plotly.react("ch-state", [{
    type: "bar", orientation: "h", y: top.map(r => r.st), x: top.map(r => r.revenue),
    marker: {color: "#0B6E99"}, text: top.map(r => fmtK(r.revenue)), textposition: "outside",
    textfont: {size: 9}, cliponaxis: false,
    hovertemplate: "%{y}<br>Revenue: R$ %{x:,.0f}<extra></extra>"
  }], LAYOUT({margin: {l: 44, r: 86, t: 8, b: 34}, xaxis: {tickprefix: "R$ ", tickformat: "~s"}}), CONF);

  const withPromise = rows.filter(r => r.avgDd !== null).slice(0, 12).reverse();
  Plotly.react("ch-promise", [
    {type: "bar", orientation: "h", y: withPromise.map(r => r.st), x: withPromise.map(r => r.avgProm),
     name: "promised at checkout", marker: {color: "#DCE3EA"},
     hovertemplate: "%{y}<br>promised: %{x:.1f} days<extra></extra>"},
    {type: "bar", orientation: "h", y: withPromise.map(r => r.st), x: withPromise.map(r => r.avgDd),
     name: "actual delivery", marker: {color: "#1F9E89"},
     hovertemplate: "%{y}<br>actual: %{x:.1f} days<extra></extra>"}
  ], LAYOUT({
    barmode: "overlay", showlegend: true, legend: {orientation: "h", y: 1.1, font: {size: 9.5}},
    margin: {l: 44, r: 14, t: 26, b: 34}, xaxis: {title: {text: "days", font: {size: 9.5}}}
  }), CONF);

  const late = rows.filter(r => r.orders >= 300).sort((x, y) => y.latePct - x.latePct).slice(0, 10).reverse();
  Plotly.react("ch-late", [{
    type: "bar", orientation: "h", y: late.map(r => r.st), x: late.map(r => r.latePct),
    marker: {color: "#D64545"}, text: late.map(r => pct(r.latePct)), textposition: "outside",
    textfont: {size: 9}, hovertemplate: "%{y}<br>%{x:.1f}% late<extra></extra>"
  }], LAYOUT({margin: {l: 44, r: 56, t: 8, b: 34}, xaxis: {title: {text: "% late", font: {size: 9.5}}}}), CONF);

  const t = rows.slice(0, 15);
  const maxRev = rows[0].revenue;
  $("tbl-state").innerHTML =
    `<thead><tr><th>State</th><th class="n">Revenue</th><th class="n">Share</th>
      <th class="n">Orders</th><th class="n">AOV</th><th class="n">Avg days</th>
      <th class="n">Late %</th></tr></thead><tbody>` +
    t.map(r => `<tr><td>${r.st}</td><td class="n">${fmtBRL(r.revenue)}</td>
      <td class="n">${pct(r.revenue / a.revenue * 100)}</td><td class="n">${fmtN(r.orders)}</td>
      <td class="n">${fmtBRL(r.aov)}</td><td class="n">${r.avgDd === null ? "–" : r.avgDd.toFixed(1)}</td>
      <td class="n" style="color:${r.latePct > 10 ? "#D64545" : "#1B2733"}">${pct(r.latePct)}</td></tr>`).join("") +
    "</tbody>";
}

/* ---------------- insights ---------------- */
function renderInsights(a, idx) {
  const rows = [...a.byCat.entries()].map(([k, v]) => ({cat: k, ...v})).sort((x, y) => y.revenue - x.revenue);
  const top3 = rows.slice(0, 3);
  const top3Share = top3.reduce((s, r) => s + r.revenue, 0) / (a.revenue || 1) * 100;
  const stRows = [...a.byState.entries()].map(([k, v]) => ({st: k, ...v,
    latePct: v.ddN ? v.late / v.ddN * 100 : 0})).sort((x, y) => y.revenue - x.revenue);

  $("insight1").innerHTML = `<b>What this page says:</b> revenue grew from ~R$0.1M/month in Jan-2017 to a peak of
    R$1.2M in Nov-2017 (Black Friday) and has plateaued around R$1.0–1.1M since. Growth came from
    <b>more orders</b>, not bigger baskets — average order value has stayed flat at ~R$160.
    In the current selection the top 3 categories (${top3.map(r => r.cat).join(", ")}) already carry
    <b>${top3Share.toFixed(1)}%</b> of revenue.`;

  const withOrders = rows.filter(r => r.orders >= 100);
  const aovMax = withOrders.slice().sort((x, y) => y.revenue / y.orders - x.revenue / x.orders)[0];
  const aovMin = withOrders.slice().sort((x, y) => x.revenue / x.orders - y.revenue / y.orders)[0];
  aovMax.aov = aovMax.revenue / aovMax.orders; aovMin.aov = aovMin.revenue / aovMin.orders;
  $("insight2").innerHTML = `<b>What this page says:</b> ${DATA.pareto.pct_for_80}% of SKUs generate 80% of revenue —
    a normal but long tail. The top 20% of products produce <b>${DATA.pareto.top20_share}%</b> of revenue,
    so catalogue pruning (or bundling) should target the bottom half, not the top.
    Note the AOV spread: ${aovMax.cat} ~R$ ${aovMax.aov.toFixed(0)}/order vs ${aovMin.cat} ~R$ ${aovMin.aov.toFixed(0)}/order —
    the same number of orders can mean ${(aovMax.aov / aovMin.aov).toFixed(1)}x different revenue.`;

  $("insight3").innerHTML = `<b>What this page says:</b> only <b>${(100 - DATA.repeat.one).toFixed(1)}%</b> of customers
    buy more than once, so repeat buyers generate just <b>${DATA.repeat.repeat_revenue}%</b> of revenue.
    Champions (repeat + recent + high spend) are only ${DATA.rfm.find(r => r.segment === "Champions").customer_share.toFixed(1)}%
    of customers but spend ${(DATA.rfm.find(r => r.segment === "Champions").arpu /
      (DATA.rfm.reduce((s, r) => s + r.revenue, 0) / DATA.rfm.reduce((s, r) => s + r.customers, 0))).toFixed(1)}x
    the average. The retention heatmap is flat at &lt;1% per month — this is a
    <b>transactional marketplace, not a loyalty business</b>, so the growth lever is acquisition + first-90-day
    conversion, not a classic loyalty programme.`;

  const worst = [...stRows].filter(r => r.orders >= 300).sort((x, y) => y.latePct - x.latePct)[0];
  $("insight4").innerHTML = `<b>What this page says:</b> São Paulo (SP) alone is
    <b>${(stRows[0].revenue / a.revenue * 100).toFixed(1)}%</b> of revenue in this selection and the
    South-East corridor (SP, RJ, MG) is ~${((stRows.filter(r => ["SP", "RJ", "MG"].includes(r.st))
      .reduce((s, r) => s + r.revenue, 0)) / a.revenue * 100).toFixed(0)}% of the total.
    The promise is generous (avg ~24 days) so 92% of orders arrive early — but
    <b>${worst ? worst.st : "–"}</b> still runs at ${worst ? worst.latePct.toFixed(1) : "–"}% late, and late orders
    are the single biggest driver of 1-2 star reviews.`;
}

function exportCsv() {
  const idx = sliced();
  const lines = ["order_index,month,state,category,revenue,items,delivery_days,late,review,payment"];
  for (const i of idx) {
    lines.push([i, DATA.months[O.m[i]], DATA.states[O.s[i]], JSON.stringify(DATA.categories[O.c[i]]),
      O.r[i], O.it[i], O.dd[i], O.late[i], O.rv[i], DATA.payments[O.p[i]]].join(","));
  }
  const blob = new Blob([lines.join("\n")], {type: "text/csv"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "olist_filtered_" + DATA.months[state.from] + "_" + DATA.months[state.to] + ".csv";
  a.click();
}

/* ---------------- boot ---------------- */
function render() {
  const idx = sliced();
  const a = aggregate(idx);
  renderKpis(a);
  renderTrend(a);
  renderPayment(a);
  renderDelay(a, idx);
  renderValue(a);
  renderCategories(a);
  renderGeo(a);
  renderInsights(a, idx);
}

function showTab(name) {
  document.querySelectorAll("nav.tabs button").forEach(x => x.classList.toggle("on", x.dataset.tab === name));
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("on", p.id === "page-" + name));
}

/* shareable links: ?from=2017-01&to=2018-08&state=SP,RJ&cat=Health Beauty */
function applyUrlFilters() {
  const q = new URLSearchParams(location.search);
  if (!q.toString()) return;
  const f = $("from"), t = $("to");
  if (q.get("from") && DATA.months.includes(q.get("from"))) { f.value = DATA.months.indexOf(q.get("from")); state.from = +f.value; }
  if (q.get("to") && DATA.months.includes(q.get("to"))) { t.value = DATA.months.indexOf(q.get("to")); state.to = +t.value; }
  if (state.to < state.from) state.to = state.from;
  const st = q.get("state");
  if (st) {
    const keep = new Set(st.split(",").map(x => x.trim().toUpperCase()));
    state.states = new Set(DATA.states.filter(x => keep.has(x)));
    if (!state.states.size) state.states = new Set(DATA.states);
    const sel = $("states");
    [...sel.options].forEach(o => o.selected = state.states.has(o.value));
  }
  const cat = q.get("cat");
  if (cat) {
    const i = DATA.categories.indexOf(cat);
    if (i >= 0) { state.cat = String(i); $("category").value = String(i); }
  }
}

function initTabs() {
  document.querySelectorAll("nav.tabs button").forEach(b => {
    b.onclick = () => {
      document.querySelectorAll("nav.tabs button").forEach(x => x.classList.remove("on"));
      document.querySelectorAll(".page").forEach(p => p.classList.remove("on"));
      b.classList.add("on");
      $("page-" + b.dataset.tab).classList.add("on");
      history.replaceState(null, "", "#" + b.dataset.tab);
      const pg = $("page-" + b.dataset.tab);
      if (pg) pg.querySelectorAll("[id^='ch-']").forEach(el => Plotly.Plots.resize(el));
    };
  });
}

initFilters();
applyUrlFilters();
initTabs();
$("snap").textContent = DATA.meta.snapshot;
renderPareto();
renderRfm();
renderCohort();
render();

// deep link: olist_dashboard.html#products  (used to capture page screenshots)
const hash = location.hash.replace("#", "");
if (hash && document.getElementById("page-" + hash)) {
  document.querySelectorAll("nav.tabs button").forEach(x => x.classList.toggle("on", x.dataset.tab === hash));
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("on", p.id === "page-" + hash));
  setTimeout(() => document.querySelectorAll("#page-" + hash + " [id^='ch-']")
    .forEach(el => Plotly.Plots.resize(el)), 60);
}
</script>
</body>
</html>
"""


def build() -> Path:
    payload = build_payload()
    html = (
        TEMPLATE.replace("__PLOTLY__", po.get_plotlyjs())
        .replace("__DATA__", json.dumps(payload, separators=(",", ":")))
    )
    OUT_PATH.write_text(html, encoding="utf-8")
    size = OUT_PATH.stat().st_size / 1e6
    print(f"dashboard -> {OUT_PATH}  ({size:.1f} MB, self-contained)")
    return OUT_PATH


if __name__ == "__main__":
    build()
