from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import pandas as pd


SOURCE_SCHEMA = "oltp"
TARGET_SCHEMA = "iste534"
SOURCE = "TPC-E"

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
    sales = pd.read_sql(SALES_SQL, engine)

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

    fact = build_fact(sales, customers, products, suppliers)

    days = build_dim_time("2017-01-01", "2023-12-31")
    existing = pd.read_sql(f"SELECT time_sk FROM {TARGET_SCHEMA}.dim_time", engine)
    days = days[~days["time_sk"].isin(existing["time_sk"])]

    load(engine, "dim_time", days)
    load(engine, "dim_supplier", suppliers)
    load(engine, "dim_customer", customers)
    load(engine, "dim_product", products)
    load(engine, "fact_sales", fact)

    
def new_keys(engine, table, key_column, how_many):

    highest = pd.read_sql(f"SELECT COALESCE(MAX({key_column}), 0) AS highest FROM {TARGET_SCHEMA}.{table}", engine)
    start = max(int(highest["highest"][0]), 0) + 1
    return range(start, start + how_many)



def build_fact(sales, customers, products, suppliers):
    # Lookup tables: TPC-E ID -> data mart key
    customer_key = dict(zip(customers["customer_nk"], customers["customer_sk"]))
    product_key = dict(zip(products["product_nk"], products["product_sk"]))
    supplier_key = dict(zip(suppliers["supplier_nk"], suppliers["supplier_sk"]))

    sale_date = pd.to_datetime(sales["sales_date"])

    fact = pd.DataFrame({
        "order_time_fk": -1,
        "sale_time_fk": sale_date.dt.strftime("%Y%m%d").astype(int),
        "supplier_fk": sales["supplier_id"].map(supplier_key),
        "customer_fk": sales["customer_id"].map(customer_key),
        "product_fk": sales["prod_id"].map(product_key),
        "junk_fk": sales["discounted"].map({0: -1, 1: -2}),
        "invoice_nk": sales["invoice_id"],
        "source_system": SOURCE,
        "fact_sales_amount": sales["amt"],
        "fact_num_products": sales["qty"],
        "fact_cost": (sales["unit_cost"] * sales["qty"]).round(2),
        "shipping_cost": None,
        "fulfill_time": None,
    })
    fact["gross_profit"] = (fact["fact_sales_amount"] - fact["fact_cost"]).round(2)
    return fact


def build_dim_time(start, end):
    """One row per day. Fiscal year starts May 1."""
    d = pd.Series(pd.date_range(start, end))
    fiscal_month = (d.dt.month - 5) % 12 + 1
    return pd.DataFrame({
        "time_sk": d.dt.strftime("%Y%m%d").astype(int),
        "year": d.dt.year,
        "quarter": d.dt.quarter,
        "week": d.dt.isocalendar().week.astype(int).values,
        "month": d.dt.month,
        "day": d.dt.day,
        "full_date": d.dt.date,
        "fiscal_year": d.dt.year.where(d.dt.month >= 5, d.dt.year - 1),
        "fiscal_quarter": (fiscal_month - 1) // 3 + 1,
        "fiscal_month": fiscal_month,
    })


def load(engine, table, df):
    df.to_sql(table, engine, schema=TARGET_SCHEMA, if_exists="append", index=False)
    print(f"Loaded {len(df):>6} rows into {table}")


if __name__ == "__main__":
    main()