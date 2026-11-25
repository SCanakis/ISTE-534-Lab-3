from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import pandas as pd


SCHEMA = "iste534"
SOURCE = "oltp"


CUSTOMERS_SQL = f"""
SELECT c.customer_id         AS customer_nk,
       c.name                AS customer_name,
       NULLIF(c.addr1, '')   AS customer_address1,
       NULLIF(c.addr2, '')   AS customer_address2,
       c.city                AS customer_city,
       c.state               AS customer_state,
       c.zip                 AS customer_zip,
       c.cust_type_id        AS customer_type_id,
       t.type_name           AS customer_type_name
FROM {SCHEMA}.customer c
LEFT JOIN {SCHEMA}.customer_type t ON c.cust_type_id = t.cust_type_id
"""

PRODUCTS_SQL = f"""
SELECT p.prod_id             AS product_nk,
       p.description         AS product_description,
       p.price1              AS product_price1,
       p.price2              AS product_price2,
       p.unit_cost           AS product_unit_cost,
       p.prod_type_id        AS prod_type_id,
       t.type_description    AS type_description,
       t.bu_id               AS bu_id,
       b.name                AS bu_name,
       TRIM(b.abbrev)        AS bu_abbrev
FROM {SCHEMA}.product p
LEFT JOIN {SCHEMA}.prod_type t     ON p.prod_type_id = t.prod_type_id
LEFT JOIN {SCHEMA}.business_unit b ON t.bu_id = b.bu_id
"""

SUPPLIERS_SQL = f"""
SELECT supplier_id           AS supplier_nk,
       name                  AS supplier_name,
       NULLIF(addr1, '')     AS supplier_address1,
       NULLIF(addr2, '')     AS supplier_address2,
       city                  AS supplier_city,
       state                 AS supplier_state,
       zip                   AS supplier_zip
FROM {SCHEMA}.supplier
"""

SALES_SQL = f"""
SELECT d.invoice_id, h.customer_id, h.sales_date, d.prod_id,
       p.supplier_id, p.unit_cost, d.amt, d.qty, d.discounted
FROM {SCHEMA}.invoice_dtl d
JOIN {SCHEMA}.invoice_hdr h ON d.invoice_id = h.invoice_id
JOIN {SCHEMA}.product p     ON d.prod_id = p.prod_id
"""


def connect():
    load_dotenv()
    password = os.getenv("PASSWORD")
    return create_engine(f"mysql+pymysql://root:{password}@localhost/{SCHEMA}?charset=utf8mb4")


def main():
    pass
