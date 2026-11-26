from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import pandas as pd
import glob 
import csv



SCHEMA = "iste534"
SOURCE = "PEC"


CUST_TYPE_MAP = {
    "COMMERCIAL": "C",
    "COMERCIAL": "C",
    "EDUCATION": "E",
    "STATELOCALGOVT": "S",
    "USGOVT": "F",
}

INTERNAL_DIVISIONS = {
    "The Product Company (East)": "TPC-E",
    "The Product Company (West)": "TPC-W",
}

SEPARATORS = {
    "PECinvoice.csv": ",",
    "PECmanufacturingCosts.csv": "|",
}

def extract_PEC(PEC_dir: str):
    files = glob.glob(f"{PEC_dir}/*.csv")

    pec_bu = pec_ct = pec_c = pec_i = pec_m = pec_pt = pec_p = None

    for file in files:
        base_name = os.path.basename(file)
        sep = SEPARATORS.get(base_name, ";")

        df = pd.read_csv(file, sep=sep, quoting=csv.QUOTE_NONE, dtype=str,
                         keep_default_na=False, na_values=[""], on_bad_lines="warn")
        df.columns = df.columns.str.strip('",')
        df = df.apply(lambda col: col.str.strip('",').str.strip())

        match base_name:
            case "PECbusiness_unit.csv":
                pec_bu = df
            case "PECcustomer_type.csv":
                pec_ct = df
            case "PECcustomer.csv":
                pec_c = df
            case "PECinvoice.csv":
                pec_i = df
            case "PECmanufacturingCosts.csv":
                pec_m = df
            case "PECproduct_type.csv":
                pec_pt = df
            case "PECproduct.csv":
                pec_p = df
            case _:
                print(f"Unexpected file: {base_name}")

    return pec_bu, pec_ct, pec_c, pec_i, pec_m, pec_pt, pec_p


def transform_PEC(pec_bu, pec_ct, pec_c, pec_i, pec_m, pec_pt, pec_p, engine):
    # Need merging:
    #   pec_bu -> Business Unit seems correct at a glance
    #   pec_p -> fine at a galnce
    #   pec_bu -> fine at a glance


    # pec_i -> fact table, junk_table, and time_table: 
    #

    # Need merging:
    #   pec_ct-> Customer type seems correct at a glance
    #   pec_c-> Customer has an issue with ",," at the end of it 
    customer = transform_pec_customer(pec_c=pec_c, pec_ct=pec_ct)
    product = transform_pec_product(pec_p=pec_p, pec_bu=pec_bu, pec_pt=pec_pt, pec_i=pec_i, pec_m=pec_m)
    invoices = clean_pec_invoices(pec_i=pec_i)

    customer = add_sk(customer, "customer_sk", next_sk(engine, "dim_customer", "customer_sk"))
    product = add_sk(product, "product_sk", next_sk(engine, "dim_product", "product_sk"))
    supplier = build_dim_supplier(pec_p=pec_p, start_sk=next_sk(engine, "dim_supplier", "supplier_sk"))

    junk = build_dim_junk(inv=invoices, start_sk=next_sk(engine, "dim_junk", "junk_sk"))
    time = build_dim_time()

    fact = build_fact_table(invoices, pec_p, customer, product, supplier, junk)

    return {
        "dim_time": time,
        "dim_supplier": supplier,
        "dim_customer": customer,
        "dim_product": product,
        "dim_junk": junk,
        "fact_sales": fact,
    }


def build_fact_table(inv, pec_p, dim_customer, dim_product, dim_supplier, dim_junk):
    f = inv.copy()

    f = f.merge(
        dim_customer[["customer_nk", "customer_sk"]],
        left_on="custID",
        right_on="customer_nk",
        how="left"
    )

    f = f.merge(
        dim_product[["product_nk", "product_sk", "product_unit_cost"]],
        left_on="prodid",
        right_on="product_nk",
        how="left"
    )

    prod_supplier = pec_p.assign(
        prodid=pec_p["prodid"].astype(int)
    )[["prodid", "supplierName"]]

    f = f.merge(prod_supplier, on="prodid", how="left")

    f = f.merge(
        dim_supplier,
        left_on="supplierName",
        right_on="supplier_name",
        how="left"
    )

    f["supplier_sk"] = f["supplier_sk"].fillna(-1).astype(int)

    f = f.merge(
        dim_junk,
        left_on=["shipMethod", "orderMethod", "paymentMethod", "discounted"],
        right_on=["special_shipment", "order_method", "payment_method", "discounted"],
        how="left")

    sales = f["amt"] * f["qty"]
    cost = f["product_unit_cost"] * f["qty"]

    fact = pd.DataFrame({
        "order_time_fk": f["order_date"].dt.strftime("%Y%m%d").astype(int),
        "sale_time_fk": f["sale_date"].dt.strftime("%Y%m%d").astype(int),
        "supplier_fk": f["supplier_sk"],
        "customer_fk": f["customer_sk"],
        "product_fk": f["product_sk"],
        "junk_fk": f["junk_sk"],
        "invoice_nk": f["Invoice"],
        "source_system": SOURCE,
        "fact_sales_amount": sales.round(2),
        "fact_num_products": f["qty"],
        "fact_cost": cost.round(2),
        "shipping_cost": f["shipCost"],
        "fulfill_time": f["fulfill_time"],
        "gross_profit": (sales - cost).round(2),
    })

    missing = fact[fact[["customer_fk", "product_fk", "junk_fk"]].isna().any(axis=1)]
    if not missing.empty:
        print(f"Warning: {len(missing)} fact rows have no matching customer/product/junk")
    return fact


def build_dim_time(start="2004-01-01", end="2011-12-31"):
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

def next_sk(engine, table, col):
    with engine.connect() as conn:
        current = conn.execute(text(f"SELECT MAX({col}) FROM {SCHEMA}.{table}")).scalar()
    return max(current or 0, 0) + 1


def add_sk(df, col, start):
    df = df.copy()
    df.insert(0, col, range(start, start + len(df)))
    return df


def build_dim_supplier(pec_p, start_sk=1):
    names = sorted(pec_p["supplierName"].dropna().unique())
    return add_sk(pd.DataFrame({"supplier_name": names}), "supplier_sk", start_sk)

def build_dim_junk(inv, start_sk=1):

    junk = (inv[["shipMethod", "orderMethod", "paymentMethod", "discounted"]]
            .drop_duplicates()
            .sort_values(["shipMethod", "orderMethod", "paymentMethod", "discounted"])
            .reset_index(drop=True))
    
    junk = junk.rename(columns={
        "shipMethod": "special_shipment",
        "orderMethod": "order_method",
        "paymentMethod": "payment_method",
    })

    return add_sk(junk, "junk_sk", start_sk)



SHIP_FIX = {
    "n/a": "N/A",
    "trran": "train", "trrain": "train", "trainn": "train",
    "trick": "truck", "tuck": "truck", "truckk": "truck",
    "aiir": "air",
}


def clean_pec_invoices(pec_i):
    i = pec_i.copy()

    i["shipMethod"] = i["shipMethod"].replace(SHIP_FIX)

    i["sale_date"] = pd.to_datetime(i["salesDate"], format="%m/%d/%y", errors="coerce")
    i["order_date"] = pd.to_datetime(i["orderDate"], format="%m/%d/%y", errors="coerce")

    num_cols = ["Invoice", "custID", "prodid", "qty", "amt", "shipCost"]
    for c in num_cols:
        i[c] = pd.to_numeric(i[c], errors="coerce")

    bad = i[i[num_cols + ["sale_date", "order_date"]].isna().any(axis=1)]
    if not bad.empty:
        print(f"Dropping {len(bad)} bad invoice rows:")
        print(bad[["Invoice", "custID", "salesDate", "orderDate"]])
    i = i.drop(bad.index)

    int_cols = ["Invoice", "custID", "prodid", "qty"]
    i[int_cols] = i[int_cols].astype(int)
    i["discounted"] = i["discounted"] == "1"
    i["fulfill_time"] = (i["sale_date"] - i["order_date"]).dt.days
    return i




def transform_pec_customer(pec_c, pec_ct):
    c = pec_c.copy()

    c["customer_type_id"] = c["custtype"].str.upper().map(CUST_TYPE_MAP)
    unmapped = c[c["customer_type_id"].isna()]
    if not unmapped.empty:
        print("Unmapped customer types:\n", unmapped[["custID", "custtype"]])

    c = c.merge(pec_ct, left_on="customer_type_id", right_on="CUSTTYPEID", how="left")

    c["internal_division"] = c["name"].map(INTERNAL_DIVISIONS)
    c["internal"] = c["internal_division"].notna()

    return pd.DataFrame({
        "customer_nk": c["custID"].astype(int),
        "customer_name": c["name"],
        "customer_address1": c["address"],
        "customer_address2": None,
        "customer_city": c["city"],
        "customer_state": c["state"],
        "customer_zip": c["zip"].str.zfill(5),
        "customer_type_id": c["customer_type_id"],
        "customer_type_name": c["TYPENAME"],
        "internal": c["internal"],
        "internal_division": c["internal_division"],
        "source_system": "PEC",
    })

def transform_pec_product(pec_p, pec_bu, pec_pt, pec_i, pec_m):
    p = pec_p.copy()
    pt = pec_pt.copy()

    p["productTypeID"] = p["productTypeID"].astype(int)
    pt["PRODTYPEID"] = pt["PRODTYPEID"].astype(int)

    p = (p.merge(pt, left_on="productTypeID", right_on="PRODTYPEID", how="left")
          .merge(pec_bu, on="BUID", how="left"))

    unit_cost = p["unitCost"].astype(float).fillna(p["prodid"].map(pec_unit_costs(pec_i, pec_m)))


    return pd.DataFrame({
        "product_nk": p["prodid"].astype(int),
        "product_description": p["prodDescription"],
        "product_price1": p["price1"].astype(float),
        "product_price2": p["price2"].astype(float),
        "product_unit_cost": p["unitCost"].astype(float),
        "prod_type_id": p["productTypeID"],
        "type_description": p["TYPEDESCRIPTION"],
        "product_unit_cost": unit_cost,
        "bu_id": p["BUID"],
        "bu_name": p["NAME"],
        "bu_abbrev": p["ABBREV"],
        "source_system": "PEC",
    })


def pec_unit_costs(pec_i, pec_m):
    pec_i = pec_i.copy()
    pec_m = pec_m.copy()

    # 1: give both tables a month column
    pec_i["month"] = pd.to_datetime(pec_i["salesDate"], format="%m/%d/%y", errors="coerce").dt.strftime("%Y-%m")
    pec_m["month"] = "20" + pec_m["Year"].str.zfill(2) + "-" + pec_m["Month"].str.zfill(2)

    # 2: how many of each product were sold each month
    pec_i["qty"] = pd.to_numeric(pec_i["qty"], errors="coerce")
    sold = pec_i.groupby(["prodid", "month"], as_index=False)["qty"].sum()

    # 3: put each month's cost next to that month's quantity
    table = pec_m.merge(sold, left_on=["prodID", "month"], right_on=["prodid", "month"])

    # 4: unit cost = cost / quantity
    table["unit_cost"] = table["manufacturingCost"].astype(float) / table["qty"]

    # 5: one number per product 
    return table.groupby("prodID")["unit_cost"].median().round(2)
    

def load_PEC(engine, tables):
    with engine.connect() as conn:
        existing = {row[0] for row in conn.execute(text(f"SELECT time_sk FROM {SCHEMA}.dim_time"))}
    tables["dim_time"] = tables["dim_time"][~tables["dim_time"]["time_sk"].isin(existing)]

    for name in ["dim_time", "dim_supplier", "dim_customer", "dim_product", "dim_junk", "fact_sales"]:
        df = tables[name]
        df.to_sql(
            name,
            engine, 
            schema=SCHEMA,
            if_exists="append",
            index=False,
        )

def main():
    load_dotenv()
    password = os.getenv("PASSWORD")
    engine = create_engine(f"mysql+pymysql://root:{password}@localhost/{SCHEMA}?charset=utf8mb4")
    # engine = create_engine(f"mysql+pymysql://aa-coco:{password}@localhost/{SCHEMA}?charset=utf8mb4")

    PEC_dir = "Lab3_DataFiles/PEC"

    pec_bu, pec_ct, pec_c, pec_i, pec_m, pec_pt, pec_p = extract_PEC(PEC_dir=PEC_dir)
    tables = transform_PEC(pec_bu, pec_ct, pec_c, pec_i, pec_m, pec_pt, pec_p, engine)
    load_PEC(engine, tables)





if __name__ == "__main__":
    main()