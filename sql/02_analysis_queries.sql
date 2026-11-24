-- ============================================================================
--  Olist Brazilian E-commerce  |  Step 3: Business Analysis Queries
--  File   : sql/02_analysis_queries.sql
--  Engine : SQLite (shipped) - portable to MySQL 8+/PostgreSQL 12+
--
--  Run with:  python -m src.sql_analysis
--  Every query below is executed and its result is written to
--  reports/sql_results/<query_name>.csv
--
--  ---------------------------------------------------------------------------
--  REVENUE DEFINITIONS (used consistently everywhere in this project)
--  ---------------------------------------------------------------------------
--   item_revenue = price + freight_value   -> category / product / state /
--                                             seller level analysis
--   order_revenue = payment_value          -> KPI totals (nets vouchers and
--                                             discounts, so it is the money
--                                             the store actually collected)
--   Both are restricted to order_status = 'delivered' (is_revenue_order = 1),
--   because cancelled and unavailable orders never earn revenue.
--  ---------------------------------------------------------------------------
-- ============================================================================


-- ============================================================================
-- Q1 | Monthly revenue & order trend  +  MoM growth  +  running total
--      Business question: is the business growing, and where are the peaks?
--      Window functions: LAG() for month-over-month growth, SUM() OVER for
--      the cumulative revenue curve.
-- ============================================================================
-- @name: q1_monthly_revenue_trend
WITH item_level AS (
    SELECT
        o.purchase_month_key           AS month,
        COUNT(DISTINCT o.order_id)     AS orders,
        SUM(oi.item_total)             AS item_revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.is_revenue_order = 1
    GROUP BY o.purchase_month_key
),
order_level AS (
    -- one row per order (payments are already collapsed to order grain)
    SELECT
        o.purchase_month_key           AS month,
        SUM(p.payment_value)           AS payment_revenue
    FROM orders o
    LEFT JOIN payments p ON p.order_id = o.order_id
    WHERE o.is_revenue_order = 1
    GROUP BY o.purchase_month_key
),
monthly AS (
    SELECT
        i.month,
        i.orders,
        i.item_revenue,
        COALESCE(d.payment_revenue, 0) AS payment_revenue,
        ROUND(i.item_revenue / i.orders, 2) AS aov
    FROM item_level i
    JOIN order_level d ON d.month = i.month
)
SELECT
    month,
    orders,
    ROUND(item_revenue, 2)                                   AS item_revenue,
    ROUND(payment_revenue, 2)                                AS payment_revenue,
    aov,
    ROUND(SUM(item_revenue) OVER (ORDER BY month), 2)         AS running_total_revenue,
    LAG(item_revenue) OVER (ORDER BY month)                  AS prev_month_revenue,
    ROUND(
        100.0 * (item_revenue - LAG(item_revenue) OVER (ORDER BY month))
              / LAG(item_revenue) OVER (ORDER BY month), 2
    )                                                        AS mom_growth_pct,
    ROUND(AVG(item_revenue) OVER (
        ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS revenue_3m_ma
FROM monthly
ORDER BY month;


-- ============================================================================
-- Q2 | Top 10 product categories by revenue (+ share and cumulative share)
--      Business question: which categories actually carry the business?
-- ============================================================================
-- @name: q2_top10_categories
WITH cat AS (
    SELECT
        p.category                    AS category,
        COUNT(DISTINCT o.order_id)    AS orders,
        SUM(oi.order_item_id)         AS units,
        SUM(oi.item_total)            AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id   = o.order_id
    JOIN products    p  ON p.product_id  = oi.product_id
    WHERE o.is_revenue_order = 1
    GROUP BY p.category
)
SELECT
    category,
    orders,
    units,
    ROUND(revenue, 2)                                        AS revenue,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 2)          AS revenue_share_pct,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC
             ROWS UNBOUNDED PRECEDING) / SUM(revenue) OVER (), 2) AS cumulative_share_pct,
    RANK() OVER (ORDER BY revenue DESC)                       AS revenue_rank
FROM cat
ORDER BY revenue DESC
LIMIT 10;


-- ============================================================================
-- Q3 | State-wise sales performance
--      Business question: where are the customers and where is the money?
--      Note the gap between order share and revenue share -> pricing /
--      freight / product-mix differences between regions.
-- ============================================================================
-- @name: q3_state_performance
WITH st AS (
    SELECT
        c.customer_state              AS state,
        COUNT(DISTINCT o.order_id)    AS orders,
        COUNT(DISTINCT c.customer_unique_id) AS customers,
        SUM(oi.item_total)            AS revenue,
        SUM(oi.freight_value)         AS freight,
        ROUND(AVG(o.delivery_days), 1) AS avg_delivery_days,
        ROUND(100.0 * AVG(o.is_late), 2) AS pct_late
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    JOIN customers   c  ON c.customer_id = o.customer_id
    WHERE o.is_revenue_order = 1
    GROUP BY c.customer_state
)
SELECT
    state,
    orders,
    customers,
    ROUND(revenue, 2)                                          AS revenue,
    ROUND(revenue / orders, 2)                                 AS revenue_per_order,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 2)            AS revenue_share_pct,
    ROUND(100.0 * freight / revenue, 2)                         AS freight_pct_of_revenue,
    avg_delivery_days,
    pct_late,
    RANK() OVER (ORDER BY revenue DESC)                         AS revenue_rank
FROM st
ORDER BY revenue DESC;


-- ============================================================================
-- Q4 | Average delivery time vs. promised time
--      Business question: do we keep our delivery promise - and where not?
--      delivery_days     = purchase -> customer received
--      estimated_days    = purchase -> promise shown at checkout
--      delay_days        = delivered - promised   (positive = late)
-- ============================================================================
-- @name: q4_delivery_vs_promise
WITH base AS (
    SELECT
        c.customer_state,
        o.delivery_days,
        o.estimated_days,
        o.delay_days,
        o.is_late
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.is_revenue_order = 1
      AND o.delivery_days IS NOT NULL
)
SELECT
    customer_state                                       AS state,
    COUNT(*)                                             AS delivered_orders,
    ROUND(AVG(estimated_days), 1)                        AS avg_promised_days,
    ROUND(AVG(delivery_days), 1)                         AS avg_actual_days,
    ROUND(AVG(delay_days), 1)                            AS avg_delay_days,
    ROUND(100.0 * AVG(CASE WHEN delay_days <= 0 THEN 1 ELSE 0 END), 2) AS pct_on_or_before_promise,
    ROUND(MAX(delay_days), 1)                            AS worst_delay_days,
    ROUND(100.0 * AVG(is_late), 2)                       AS pct_late,
    RANK() OVER (ORDER BY AVG(delivery_days) DESC)       AS slowest_rank
FROM base
GROUP BY customer_state
HAVING COUNT(*) >= 100        -- ignore states with too few orders to be reliable
ORDER BY avg_actual_days DESC;

-- @name: q4b_delivery_overall
SELECT
    COUNT(*)                                             AS delivered_orders,
    ROUND(AVG(estimated_days), 1)                        AS avg_promised_days,
    ROUND(AVG(delivery_days), 1)                         AS avg_actual_days,
    ROUND(AVG(delay_days), 1)                            AS avg_delay_days,
    ROUND(100.0 * AVG(is_late), 2)                       AS pct_late,
    ROUND(100.0 * AVG(CASE WHEN delivery_days <= estimated_days THEN 1 ELSE 0 END), 2) AS pct_on_time,
    ROUND(AVG(CASE WHEN is_late = 1 THEN delay_days END), 1) AS avg_delay_when_late
FROM orders
WHERE is_revenue_order = 1 AND delivery_days IS NOT NULL;


-- ============================================================================
-- Q5 | Window-function ranking: top 3 categories inside each state
--      Business question: which categories should we push in each region?
--      Demonstrates RANK() OVER (PARTITION BY ...) and a derived-table filter.
-- ============================================================================
-- @name: q5_category_rank_by_state
WITH st_cat AS (
    SELECT
        c.customer_state                AS state,
        p.category                      AS category,
        SUM(oi.item_total)              AS revenue,
        COUNT(DISTINCT o.order_id)      AS orders
    FROM orders o
    JOIN order_items oi ON oi.order_id  = o.order_id
    JOIN products    p  ON p.product_id = oi.product_id
    JOIN customers   c  ON c.customer_id = o.customer_id
    WHERE o.is_revenue_order = 1
    GROUP BY c.customer_state, p.category
),
ranked AS (
    SELECT
        state, category, orders, revenue,
        RANK() OVER (PARTITION BY state ORDER BY revenue DESC) AS rnk,
        ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY state), 2) AS share_in_state_pct
    FROM st_cat
)
SELECT state, rnk, category, orders,
       ROUND(revenue, 2) AS revenue,
       share_in_state_pct
FROM ranked
WHERE rnk <= 3
ORDER BY state, rnk;


-- ============================================================================
-- Q6 | Payment method distribution
--      Business question: how do customers pay, and does the payment method
--      change the basket size? (installments = the Brazilian credit culture)
-- ============================================================================
-- @name: q6_payment_methods
SELECT
    p.payment_type                                          AS payment_type,
    COUNT(DISTINCT p.order_id)                              AS orders,
    ROUND(SUM(p.payment_value), 2)                          AS revenue,
    ROUND(AVG(p.payment_value), 2)                          AS avg_order_value,
    ROUND(AVG(p.payment_installments), 2)                   AS avg_installments,
    ROUND(100.0 * COUNT(DISTINCT p.order_id)
          / SUM(COUNT(DISTINCT p.order_id)) OVER (), 2)     AS order_share_pct,
    ROUND(100.0 * SUM(p.payment_value)
          / SUM(SUM(p.payment_value)) OVER (), 2)           AS revenue_share_pct
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE o.is_revenue_order = 1
  AND p.payment_type IS NOT NULL
GROUP BY p.payment_type
ORDER BY revenue DESC;


-- ============================================================================
-- Q7 | Review score vs. delivery delay
--      Business question: does a late delivery really destroy satisfaction?
--      delay_bucket makes the relationship readable (and is a classic CASE
--      bucketing + conditional aggregation exercise).
-- ============================================================================
-- @name: q7_reviews_vs_delay
WITH r AS (
    SELECT
        rv.review_score,
        o.delay_days,
        o.delivery_days,
        CASE
            WHEN o.delay_days IS NULL        THEN '0 - not delivered'
            WHEN o.delay_days <= -15         THEN '1 - 15+ days early'
            WHEN o.delay_days <    0         THEN '2 - early'
            WHEN o.delay_days <    1         THEN '3 - on the promised day'
            WHEN o.delay_days <=   7         THEN '4 - 1-7 days late'
            WHEN o.delay_days <=  15         THEN '5 - 8-15 days late'
            ELSE                                  '6 - 15+ days late'
        END AS delay_bucket
    FROM reviews rv
    JOIN orders  o ON o.order_id = rv.order_id
    WHERE o.is_revenue_order = 1
      AND rv.review_score IS NOT NULL
)
SELECT
    delay_bucket,
    COUNT(*)                                     AS reviews,
    ROUND(AVG(review_score), 2)                  AS avg_review_score,
    ROUND(100.0 * SUM(CASE WHEN review_score >= 4 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_4_or_5_star,
    ROUND(100.0 * SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_1_or_2_star,
    ROUND(AVG(delivery_days), 1)                 AS avg_delivery_days
FROM r
GROUP BY delay_bucket
ORDER BY delay_bucket;


-- ============================================================================
-- Q8 | Pareto / 80-20 on products
--      Business question: how concentrated is revenue in a few SKUs?
--      Uses SUM() OVER (ORDER BY ...) to build the cumulative revenue curve
--      and then finds the smallest product count that reaches 80% of revenue.
-- ============================================================================
-- @name: q8_product_pareto
WITH prod AS (
    SELECT
        oi.product_id,
        p.category,
        SUM(oi.item_total)              AS revenue,
        SUM(oi.order_item_id)           AS units
    FROM orders o
    JOIN order_items oi ON oi.order_id  = o.order_id
    JOIN products    p  ON p.product_id = oi.product_id
    WHERE o.is_revenue_order = 1
    GROUP BY oi.product_id, p.category
),
ranked AS (
    SELECT
        product_id, category, units, revenue,
        ROW_NUMBER() OVER (ORDER BY revenue DESC)                    AS revenue_rank,
        SUM(revenue) OVER (ORDER BY revenue DESC
            ROWS UNBOUNDED PRECEDING)                                AS cumulative_revenue,
        ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC
            ROWS UNBOUNDED PRECEDING) / SUM(revenue) OVER (), 2)     AS cumulative_pct
    FROM prod
)
SELECT
    COUNT(*)                                                    AS total_products,
    SUM(CASE WHEN cumulative_pct <= 80 THEN 1 ELSE 0 END)        AS products_for_80pct_revenue,
    ROUND(100.0 * SUM(CASE WHEN cumulative_pct <= 80 THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                                AS pct_products_for_80pct_revenue
FROM ranked;


-- ============================================================================
-- Q9 | Seller leaderboard with running revenue share (long-tail check)
--      Business question: are we dependent on a handful of sellers?
-- ============================================================================
-- @name: q9_seller_leaderboard
WITH s AS (
    SELECT
        oi.seller_id,
        s2.seller_state,
        COUNT(DISTINCT o.order_id)     AS orders,
        SUM(oi.item_total)             AS revenue,
        ROUND(AVG(o.delivery_days), 1) AS avg_delivery_days,
        ROUND(AVG(rv.review_score), 2) AS avg_review_score
    FROM orders o
    JOIN order_items oi ON oi.order_id   = o.order_id
    JOIN sellers     s2 ON s2.seller_id  = oi.seller_id
    LEFT JOIN reviews rv ON rv.order_id  = o.order_id
    WHERE o.is_revenue_order = 1
    GROUP BY oi.seller_id, s2.seller_state
)
SELECT
    seller_id, seller_state, orders,
    ROUND(revenue, 2)                                            AS revenue,
    avg_delivery_days, avg_review_score,
    RANK() OVER (ORDER BY revenue DESC)                           AS revenue_rank,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC
        ROWS UNBOUNDED PRECEDING) / SUM(revenue) OVER (), 2)      AS cumulative_revenue_pct
FROM s
ORDER BY revenue DESC
LIMIT 25;


-- ============================================================================
-- Q10 | RFM segmentation in pure SQL
--       Recency  = days between the customer's last order and the snapshot date
--       Frequency= number of distinct orders (customer_unique_id, not customer_id
--                  - Olist issues a new customer_id per order!)
--       Monetary = total payment value
--       Scores   = NTILE() quintiles for R and M, explicit buckets for F
--                  (97% of customers buy once, so quintiles are useless for F).
-- ============================================================================
-- @name: q10_rfm_segments
WITH snapshot AS (
    SELECT julianday(MAX(order_purchase_timestamp)) + 1 AS snapshot_day
    FROM orders
),
cust AS (
    SELECT
        c.customer_unique_id,
        MAX(o.order_purchase_timestamp)          AS last_purchase,
        COUNT(DISTINCT o.order_id)               AS frequency,
        ROUND(SUM(p.payment_value), 2)           AS monetary,
        ROUND(AVG(rv.review_score), 2)           AS avg_review_score
    FROM orders o
    JOIN customers c   ON c.customer_id = o.customer_id
    LEFT JOIN payments p  ON p.order_id = o.order_id
    LEFT JOIN reviews  rv ON rv.order_id = o.order_id
    WHERE o.is_revenue_order = 1
    GROUP BY c.customer_unique_id
),
scored AS (
    SELECT
        customer_unique_id, last_purchase, frequency, monetary, avg_review_score,
        (SELECT snapshot_day FROM snapshot) - julianday(last_purchase) AS recency_days,
        -- NTILE ascending on the purchase timestamp => the most recent buyers
        -- get the highest r_score (5). Ordering DESC would invert the score.
        NTILE(5) OVER (ORDER BY julianday(last_purchase))               AS r_score,
        CASE WHEN frequency = 1 THEN 1
             WHEN frequency = 2 THEN 2
             ELSE 3 END                                                AS f_score,
        NTILE(5) OVER (ORDER BY monetary)                              AS m_score
    FROM cust
),
seg AS (
    SELECT
        *,
        -- Priority ladder, identical to segment_customers() in src/analysis.py.
        -- Order matters: the first matching rule wins.
        CASE
            WHEN f_score >= 3 AND r_score >= 4 AND m_score >= 3 THEN 'Champions'
            WHEN f_score >= 2 AND r_score >= 4 AND m_score >= 3 THEN 'Loyal Customers'
            WHEN f_score >= 2 AND r_score <= 2 AND m_score >= 4 THEN 'Cannot Lose Them'
            WHEN f_score >= 2 AND r_score <= 2                 THEN 'At Risk'
            WHEN f_score >= 2 AND r_score >= 4                 THEN 'Potential Loyalist'
            WHEN f_score >= 2                                  THEN 'Need Attention'
            WHEN r_score >= 4                                  THEN 'New Customers'
            WHEN r_score =  3                                  THEN 'Promising'
            WHEN r_score =  2                                  THEN 'Hibernating'
            ELSE 'Lost'
        END AS segment
    FROM scored
)
SELECT
    segment,
    COUNT(*)                                              AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)      AS customer_share_pct,
    ROUND(SUM(monetary), 2)                                 AS revenue,
    ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 2) AS revenue_share_pct,
    ROUND(AVG(monetary), 2)                                 AS avg_monetary,
    ROUND(AVG(frequency), 2)                               AS avg_frequency,
    ROUND(AVG(recency_days), 0)                            AS avg_recency_days,
    ROUND(AVG(avg_review_score), 2)                        AS avg_review_score
FROM seg
GROUP BY segment
ORDER BY revenue DESC;


-- ============================================================================
-- Q11 | Monthly cohort retention
--       cohort_month = month of the customer's FIRST order
--       period_number = how many months later they ordered again (0 = first month)
--       Retention % = active / cohort size. This is the standard cohort triangle.
-- ============================================================================
-- @name: q11_cohort_retention
WITH first_order AS (
    SELECT
        c.customer_unique_id,
        MIN(o.purchase_month_key) AS cohort_month
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.is_revenue_order = 1
    GROUP BY c.customer_unique_id
),
activity AS (
    SELECT DISTINCT
        c.customer_unique_id,
        o.purchase_month_key AS activity_month
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.is_revenue_order = 1
),
cohort AS (
    SELECT
        f.cohort_month,
        f.customer_unique_id,
        (CAST(SUBSTR(a.activity_month, 1, 4) AS INTEGER) * 12
         + CAST(SUBSTR(a.activity_month, 6, 2) AS INTEGER))
      - (CAST(SUBSTR(f.cohort_month,    1, 4) AS INTEGER) * 12
         + CAST(SUBSTR(f.cohort_month,    6, 2) AS INTEGER)) AS period_number
    FROM first_order f
    JOIN activity    a ON a.customer_unique_id = f.customer_unique_id
),
sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM first_order
    GROUP BY cohort_month
)
SELECT
    c.cohort_month,
    s.cohort_size,
    c.period_number,
    COUNT(DISTINCT c.customer_unique_id)                                   AS active_customers,
    ROUND(100.0 * COUNT(DISTINCT c.customer_unique_id) / s.cohort_size, 2) AS retention_pct
FROM cohort c
JOIN sizes  s ON s.cohort_month = c.cohort_month
WHERE c.period_number BETWEEN 0 AND 6
GROUP BY c.cohort_month, s.cohort_size, c.period_number
ORDER BY c.cohort_month, c.period_number;


-- ============================================================================
-- Q12 | Repeat-purchase distribution (the core "are customers coming back?"
--       question for this dataset) + revenue contribution by order count
-- ============================================================================
-- @name: q12_repeat_purchase
WITH cust AS (
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT o.order_id)  AS orders,
        SUM(p.payment_value)        AS revenue
    FROM orders o
    JOIN customers c  ON c.customer_id = o.customer_id
    LEFT JOIN payments p ON p.order_id = o.order_id
    WHERE o.is_revenue_order = 1
    GROUP BY c.customer_unique_id
)
SELECT
    orders                                                   AS orders_per_customer,
    COUNT(*)                                                 AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)        AS customer_share_pct,
    ROUND(SUM(revenue), 2)                                   AS revenue,
    ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2) AS revenue_share_pct,
    ROUND(AVG(revenue), 2)                                   AS avg_ltv
FROM cust
GROUP BY orders
ORDER BY orders;
