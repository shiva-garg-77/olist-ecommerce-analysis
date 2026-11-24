-- ============================================================================
--  Olist Brazilian E-commerce  |  Step 3: SQL Analysis
--  File   : sql/01_schema.sql
--  Purpose: DDL + data-loading notes for MySQL / PostgreSQL / SQLite
--
--  The project ships a SQLite copy of the cleaned data (data/processed/olist.db)
--  so every query in 02_analysis_queries.sql can be executed as-is:
--
--      sqlite3 data/processed/olist.db < sql/02_analysis_queries.sql
--      # or: python -m src.sql_analysis
--
--  Only portable SQL is used (CTEs, window functions, CASE, SUBSTR) so the same
--  file runs on MySQL 8+ and PostgreSQL 12+ after the DDL below.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. STAR SCHEMA (PostgreSQL flavour - it also runs on SQLite unchanged
--    except for DOUBLE PRECISION, which is REAL in SQLite)
-- ----------------------------------------------------------------------------

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS category_translation;

CREATE TABLE customers (
    customer_id              VARCHAR(64) PRIMARY KEY,
    customer_unique_id       VARCHAR(64) NOT NULL,
    customer_zip_code_prefix INTEGER,
    customer_city            VARCHAR(64),
    customer_state           VARCHAR(4)
);

CREATE TABLE orders (
    order_id                        VARCHAR(64) PRIMARY KEY,
    customer_id                     VARCHAR(64) REFERENCES customers(customer_id),
    order_status                    VARCHAR(20),
    order_purchase_timestamp        TIMESTAMP,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP,
    purchase_month_key              VARCHAR(7),        -- 'YYYY-MM', portable grouping key
    delivery_days                   REAL,              -- purchase -> delivered
    estimated_days                  REAL,              -- purchase -> promised
    delay_days                      REAL,              -- delivered - promised  (>0 = late)
    is_late                         INTEGER,
    is_cancelled                    INTEGER,
    is_revenue_order                INTEGER
);

CREATE TABLE order_items (
    order_id           VARCHAR(64) REFERENCES orders(order_id),
    order_item_id      INTEGER,
    product_id         VARCHAR(64) REFERENCES products(product_id),
    seller_id          VARCHAR(64) REFERENCES sellers(seller_id),
    shipping_limit_date TIMESTAMP,
    price              REAL,
    freight_value      REAL,
    item_total         REAL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE payments (
    order_id             VARCHAR(64) REFERENCES orders(order_id),
    payment_value        REAL,
    payment_installments INTEGER,
    n_payment_records    INTEGER,
    payment_type         VARCHAR(30)
);

CREATE TABLE reviews (
    order_id            VARCHAR(64) REFERENCES orders(order_id),
    review_id           VARCHAR(64),
    review_score        INTEGER,
    has_comment         INTEGER,
    review_creation_date TIMESTAMP
);

CREATE TABLE products (
    product_id              VARCHAR(64) PRIMARY KEY,
    product_category_name   VARCHAR(80),
    category                VARCHAR(80),   -- English, title-cased
    product_weight_g        REAL,
    product_volume_cm3      REAL,
    product_photos_qty      INTEGER,
    product_name_length     INTEGER,
    product_description_length INTEGER
);

CREATE TABLE sellers (
    seller_id              VARCHAR(64) PRIMARY KEY,
    seller_zip_code_prefix INTEGER,
    seller_city            VARCHAR(64),
    seller_state           VARCHAR(4)
);

CREATE TABLE category_translation (
    product_category_name         VARCHAR(80) PRIMARY KEY,
    product_category_name_english VARCHAR(80)
);

CREATE INDEX idx_orders_purchase_month ON orders(purchase_month_key);
CREATE INDEX idx_orders_status         ON orders(order_status);
CREATE INDEX idx_items_order           ON order_items(order_id);
CREATE INDEX idx_items_product         ON order_items(product_id);
CREATE INDEX idx_orders_customer       ON orders(customer_id);

-- ----------------------------------------------------------------------------
-- 2. MySQL 8 equivalent (notable differences only)
-- ----------------------------------------------------------------------------
--   * VARCHAR(7) -> CHAR(7),  INTEGER ok
--   * Load with LOAD DATA LOCAL INFILE ...  (see below)
--   * Window functions & CTEs are supported from MySQL 8.0
--
--   LOAD DATA LOCAL INFILE 'data/processed/fact_orders.csv' INTO TABLE orders
--     FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n'
--     IGNORE 1 ROWS;
--
--   (repeat for each table; loading order matters because of the FKs:
--    customers -> sellers -> products -> orders -> order_items -> payments
--    -> reviews)

-- ----------------------------------------------------------------------------
-- 3. Load the CSVs that  src/etl.py  writes to data/processed/
-- ----------------------------------------------------------------------------
--  PostgreSQL:
--    \copy customers FROM 'data/processed/dim_customers.csv' CSV HEADER;
--    \copy products  FROM 'data/processed/dim_products.csv'  CSV HEADER;
--    \copy sellers   FROM 'data/processed/dim_sellers.csv'   CSV HEADER;
--    \copy orders    FROM 'data/processed/fact_orders.csv'   CSV HEADER;
--    \copy payments  FROM 'data/processed/fact_payments.csv' CSV HEADER;
--    \copy reviews   FROM 'data/processed/fact_reviews.csv'  CSV HEADER;
--
--  order_items is not exported on its own; it is rebuilt by the pipeline into
--  data/processed/master.csv (one row per order item). If you only have the
--  raw Kaggle CSVs, load olist_order_items_dataset.csv into order_items and
--  compute item_total = price + freight_value.
