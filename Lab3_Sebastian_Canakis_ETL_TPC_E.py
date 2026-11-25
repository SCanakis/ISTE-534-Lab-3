from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import pandas as pd


SOURCE_SCHEMA = "oltp"
SOURCE = "TPC-E"
TARGET_SCHEMA = "iste534"

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
FROM {SOURCE_SCHEMA}.customer c
LEFT JOIN {SOURCE_SCHEMA}.customer_type t ON c.cust_type_id = t.cust_type_id
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
FROM {SOURCE_SCHEMA}.product p
LEFT JOIN {SOURCE_SCHEMA}.prod_type t     ON p.prod_type_id = t.prod_type_id
LEFT JOIN {SOURCE_SCHEMA}.business_unit b ON t.bu_id = b.bu_id
"""

SUPPLIERS_SQL = f"""
SELECT supplier_id           AS supplier_nk,
       name                  AS supplier_name,
       NULLIF(addr1, '')     AS supplier_address1,
       NULLIF(addr2, '')     AS supplier_address2,
       city                  AS supplier_city,
       state                 AS supplier_state,
       zip                   AS supplier_zip
FROM {SOURCE_SCHEMA}.supplier
"""

SALES_SQL = f"""
SELECT d.invoice_id, h.customer_id, h.sales_date, d.prod_id,
       p.supplier_id, p.unit_cost, d.amt, d.qty, d.discounted
FROM {SOURCE_SCHEMA}.invoice_dtl d
JOIN {SOURCE_SCHEMA}.invoice_hdr h ON d.invoice_id = h.invoice_id
JOIN {SOURCE_SCHEMA}.product p     ON d.prod_id = p.prod_id
"""


def connect():
    load_dotenv()
    password = os.getenv("PASSWORD")
    return create_engine(f"mysql+pymysql://root:{password}@localhost/{SOURCE_SCHEMA}?charset=utf8mb4")


def main():
    engine = connect()

    customers = pd.read_sql(CUSTOMERS_SQL, engine)
    products = pd.read_sql(PRODUCTS_SQL, engine)
    suppliers = pd.read_sql(SUPPLIERS_SQL, engine)
    customers = pd.read_sql(SALES_SQL, engine)

    # Extra Columns
    # "Processing Equipment Corporation" is PEC buying from TPC-E
    
    customers["internal_division"] = customers["customer_name"].map({"Processing Equipment Corporation": "PEC"})
    customers["internal"] = customers["internal_division"].notna()
    customers["source_system"] = SOURCE
    products["source_system"] = SOURCE


    customers.insert(
        0,
        "customer_sk",
        new_keys(
            engine,
            "dim_customer",
            "customer_sk",
            len(customers)
        )
    )

    products.insert(
        0,
        "product_sk",
        new_keys(
            engine,
            "dim_product",
            "product_sk",
            len(products)
        )
    )

    suppliers.insert(
        0,
        "supplier_sk", 
        new_keys(
            engine,
            "dim_supplier",
            "supplier_sk",
            len(suppliers)
        )
    )

    
def new_keys(engine, table, key_column, how_many):

    highest = pd.read_sql(f"SELECT COALESCE(MAX({key_column}), 0) AS highest FROM {TARGET_SCHEMA}.{table}", engine)
    start = max(int(highest["highest"][0]), 0) + 1
    return range(start, start + how_many)

