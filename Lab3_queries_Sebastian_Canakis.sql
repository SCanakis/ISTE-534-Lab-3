-- Indexes:
CREATE INDEX idx_fact_sale_customer
    ON iste534.fact_sales (
        sale_time_fk,
        customer_fk,
        fact_sales_amount,
        fact_cost, 
        gross_profit
);


CREATE INDEX idx_fact_source_invoice
    ON iste534.fact_sales (
        source_system,
        invoice_nk,
        fulfill_time
    );

CREATE INDEX idx_customer_internal
    ON iste534.dim_customer (
        internal,
        internal_division
    );


-- Query 1: sales, cost and gross profit by customer type, per quarter
SELECT st.year, st.quarter, c.customer_type_name,
       SUM(f.fact_sales_amount) AS sales,
       SUM(f.fact_cost)         AS cost,
       SUM(f.gross_profit)      AS gross_profit
FROM iste534.fact_sales f
JOIN iste534.dim_time st   ON f.sale_time_fk = st.time_sk
JOIN iste534.dim_customer c ON f.customer_fk  = c.customer_sk
GROUP BY st.year, st.quarter, c.customer_type_name
ORDER BY st.year, st.quarter, c.customer_type_name;


-- Query 2: PEC average days to fulfill an order, and orders over 10 days
SELECT AVG(days)       AS avg_days_to_fulfill,
       SUM(days > 10)  AS orders_over_10_days,
       COUNT(*)        AS total_orders
FROM (
    SELECT invoice_nk, MAX(fulfill_time) AS days
    FROM iste534.fact_sales
    WHERE source_system = 'PEC'
    GROUP BY invoice_nk
) AS orders;


-- Query 3: sales from one division to another
SELECT f.source_system       AS seller,
       c.internal_division   AS buyer,
       SUM(f.fact_sales_amount) AS sales,
       SUM(f.gross_profit)      AS gross_profit
FROM iste534.fact_sales f
JOIN iste534.dim_customer c ON f.customer_fk = c.customer_sk
WHERE c.internal = TRUE
GROUP BY f.source_system, c.internal_division;