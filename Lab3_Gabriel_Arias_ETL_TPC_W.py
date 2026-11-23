from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import pandas as pd
import csv


TPCW_DIR = "Lab3_DataFiles/Lab3_DataFiles/TPCW"
SOURCE   = "TPC-W"
SCHEMA   = "iste534"

INTERNAL_DIVISIONS = {
    "The Product Company (East)": "TPC-E",
    "The Product Company (West)": "TPC-W",
}

CUST_TYPE_MAP = {
    "COMM":  "C",
    "COMMM": "C",   # "Commm" is a typo in the source data, still Commercial
    "EDU":   "E",
    "STATE": "S",
    "GOVT":  "F",
}

STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Fl": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "DC": "DC", "District of Columbia": "DC",
}


# Extract

def _read(path, sep=";", header="infer", names=None):
    df = pd.read_csv(
        path,
        sep=sep,
        header=header,
        names=names,
        quoting=csv.QUOTE_NONE,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        on_bad_lines="warn",
    )
    df.columns = df.columns.str.strip('", ')
    df = df.apply(lambda col: col.str.strip('", '))
    return df


def extract_tpcw(tpcw_dir):
    # The product file has no header row. The PDF lists 10 columns but the actual
    # data has an extra "Attn: ..." line before the street address, so we get 11.
    product_cols = [
        "prodid", "prodDescription", "price1", "price2", "unitCost",
        "supplierName", "supplierAttn", "supplierAddress", "supplierCityState",
        "supplierZip", "productTypeID",
    ]

    tpcw_bu = _read(f"{tpcw_dir}/TPCWbusiness_unit.csv")
    tpcw_ct = _read(f"{tpcw_dir}/TPCWcustomer_type.csv")
    tpcw_c  = _read(f"{tpcw_dir}/TPCWcustomer.csv")
    tpcw_pt = _read(f"{tpcw_dir}/TPCWproduct_type.csv")
    tpcw_i  = _read(f"{tpcw_dir}/TPCWinvoice.csv", sep=",")
    tpcw_p  = _read(f"{tpcw_dir}/TPCWproduct.csv", header=None, names=product_cols)

    return tpcw_bu, tpcw_ct, tpcw_c, tpcw_pt, tpcw_i, tpcw_p


# Transform

def transform_tpcw_customer(tpcw_c, tpcw_ct):
    c = tpcw_c.copy()

    c["customer_type_id"] = c["custtype"].str.upper().map(CUST_TYPE_MAP)
    unmapped = c[c["customer_type_id"].isna()]
    if not unmapped.empty:
        print("Unmapped customer types:\n", unmapped[["custID", "custtype"]])

    c = c.merge(tpcw_ct, left_on="customer_type_id", right_on="CUSTTYPEID", how="left")

    c["internal_division"] = c["name"].map(INTERNAL_DIVISIONS)
    c["internal"] = c["internal_division"].notna()

    c["state_abbrev"] = c["state"].map(STATE_ABBREV)
    unmapped_states = c[c["state_abbrev"].isna() & c["state"].notna()]
    if not unmapped_states.empty:
        print("Unmapped states (will use raw value):\n", unmapped_states[["custID", "state"]])
        c["state_abbrev"] = c["state_abbrev"].fillna(c["state"])

    return pd.DataFrame({
        "customer_nk":        c["custID"].astype(int),
        "customer_name":      c["name"],
        "customer_address1":  c["address"],
        "customer_address2":  None,
        "customer_city":      c["city"],
        "customer_state":     c["state_abbrev"],
        "customer_zip":       c["zip"].str.zfill(5),
        "customer_type_id":   c["customer_type_id"],
        "customer_type_name": c["TYPENAME"],
        "internal":           c["internal"],
        "internal_division":  c["internal_division"],
        "source_system":      SOURCE,
    })


def transform_tpcw_product(tpcw_p, tpcw_bu, tpcw_pt):
    p  = tpcw_p.copy()
    pt = tpcw_pt.copy()

    # The product file stores type IDs as plain integers (e.g. 3), but the
    # product_type table uses zero-padded strings (e.g. "0003"), so we align them.
    p["productTypeID"] = p["productTypeID"].astype(int).apply(lambda x: str(x).zfill(4))

    p = (p.merge(pt, left_on="productTypeID", right_on="PRODTYPEID", how="left")
          .merge(tpcw_bu, on="BUID", how="left"))

    return pd.DataFrame({
        "product_nk":          p["prodid"].astype(int),
        "product_description": p["prodDescription"],
        "product_price1":      p["price1"].astype(float),
        "product_price2":      p["price2"].astype(float),
        "product_unit_cost":   p["unitCost"].astype(float),
        "prod_type_id":        p["productTypeID"],
        "type_description":    p["TYPEDESCRIPTION"],
        "bu_id":               p["BUID"],
        "bu_name":             p["NAME"],
        "bu_abbrev":           p["ABBREV"],
        "source_system":       SOURCE,
    })


def build_dim_supplier(tpcw_p):
    names = sorted(tpcw_p["supplierName"].dropna().unique())
    return pd.DataFrame({"supplier_name": names})


def clean_tpcw_invoices(tpcw_i):
    i = tpcw_i.copy()

    # TPC-W sends dates as DD-MM-YY, which is the opposite of what PEC uses (MM/DD/YY).
    i["sale_date"] = pd.to_datetime(i["salesDate"], format="%d-%m-%y", errors="coerce")

    num_cols = ["invoice", "custID", "prodID", "qty", "amt"]
    for c in num_cols:
        i[c] = pd.to_numeric(i[c], errors="coerce")

    bad = i[i[num_cols + ["sale_date"]].isna().any(axis=1)]
    if not bad.empty:
        print(f"Dropping {len(bad)} bad invoice rows:")
        print(bad[["invoice", "custID", "salesDate"]])
    i = i.drop(bad.index)

    int_cols = ["invoice", "custID", "prodID", "qty"]
    i[int_cols] = i[int_cols].astype(int)
    i["discounted"] = i["discounted"] == "1"

    return i


def next_sk(engine, table, col):
    with engine.connect() as conn:
        current = conn.execute(text(f"SELECT MAX({col}) FROM {SCHEMA}.{table}")).scalar()
    return max(current or 0, 0) + 1


def add_sk(df, col, start):
    df = df.copy()
    df.insert(0, col, range(start, start + len(df)))
    return df


def build_fact_table(inv, tpcw_p, dim_customer, dim_product, dim_supplier):
    f = inv.copy()

    # Customer IDs overlap between divisions, so we only look up TPC-W customers
    # to avoid accidentally matching a PEC customer with the same ID.
    cust_lookup = dim_customer[dim_customer["source_system"] == SOURCE][["customer_nk", "customer_sk"]]
    f = f.merge(cust_lookup, left_on="custID", right_on="customer_nk", how="left")

    # Same story for products — IDs are not shared across divisions.
    prod_lookup = dim_product[dim_product["source_system"] == SOURCE][["product_nk", "product_sk", "product_unit_cost"]]
    f = f.merge(prod_lookup, left_on="prodID", right_on="product_nk", how="left")

    # Supplier isn't on the invoice directly, so we pull it from the product file.
    prod_supplier = tpcw_p[["prodid", "supplierName"]].copy()
    prod_supplier["prodid"] = prod_supplier["prodid"].astype(int)
    f = f.merge(prod_supplier, left_on="prodID", right_on="prodid", how="left")
    f = f.merge(dim_supplier, left_on="supplierName", right_on="supplier_name", how="left")
    f["supplier_sk"] = f["supplier_sk"].fillna(-1).astype(int)

    # Some invoice rows reference customer or product IDs that don't exist in the
    # dimension tables (bad data). We drop them since the DB won't accept null FKs.
    missing = f[f[["customer_sk", "product_sk"]].isna().any(axis=1)]
    if not missing.empty:
        print(f"Dropping {len(missing)} fact rows with unresolved customer/product FK:")
        print(missing[["invoice", "custID", "prodID"]].drop_duplicates().head(10).to_string())
    f = f.dropna(subset=["customer_sk", "product_sk"])

    # Pandas turns integer columns into floats whenever a merge introduces NaNs,
    # so we cast back to int after dropping the bad rows.
    f["customer_sk"] = f["customer_sk"].astype(int)
    f["product_sk"]  = f["product_sk"].astype(int)

    sales   = f["amt"] * f["qty"]
    cost    = f["product_unit_cost"] * f["qty"]
    sale_sk = f["sale_date"].dt.strftime("%Y%m%d").astype(int)
    junk_fk = f["discounted"].map({True: -2, False: -1})

    return pd.DataFrame({
        "order_time_fk":     sale_sk,        # TPC-W only has a sale date, so we use it for both
        "sale_time_fk":      sale_sk,
        "supplier_fk":       f["supplier_sk"],
        "customer_fk":       f["customer_sk"],
        "product_fk":        f["product_sk"],
        "junk_fk":           junk_fk,        # -1 = not discounted, -2 = discounted (sentinels in dim_junk)
        "invoice_nk":        f["invoice"],
        "source_system":     SOURCE,
        "fact_sales_amount": sales.round(2),
        "fact_num_products": f["qty"],
        "fact_cost":         cost.round(2),
        "shipping_cost":     None,            # TPC-W doesn't include shipping cost in its feed
        "fulfill_time":      0,               # can't calculate fulfillment without an order date
        "gross_profit":      (sales - cost).round(2),
    })


# Load

def build_dim_time(start="2004-01-01", end="2011-12-31"):
    d = pd.Series(pd.date_range(start, end))
    fiscal_month = (d.dt.month - 5) % 12 + 1
    return pd.DataFrame({
        "time_sk":        d.dt.strftime("%Y%m%d").astype(int),
        "year":           d.dt.year,
        "quarter":        d.dt.quarter,
        "week":           d.dt.isocalendar().week.astype(int).values,
        "month":          d.dt.month,
        "day":            d.dt.day,
        "full_date":      d.dt.date,
        "fiscal_year":    d.dt.year.where(d.dt.month >= 5, d.dt.year - 1),
        "fiscal_quarter": (fiscal_month - 1) // 3 + 1,
        "fiscal_month":   fiscal_month,
    })


def load_tpcw(engine, dim_customer, dim_product, dim_supplier, fact_sales):
    dim_time = build_dim_time()
    with engine.connect() as conn:
        existing = {row[0] for row in conn.execute(text(f"SELECT time_sk FROM {SCHEMA}.dim_time"))}
    dim_time = dim_time[~dim_time["time_sk"].isin(existing)]

    tables = {
        "dim_time":     dim_time,
        "dim_supplier": dim_supplier,
        "dim_customer": dim_customer,
        "dim_product":  dim_product,
        "fact_sales":   fact_sales,
    }

    for name, df in tables.items():
        df.to_sql(name, engine, schema=SCHEMA, if_exists="append", index=False)
        print(f"  Loaded {name:15s}: {len(df)} rows")


# Main

def main():
    load_dotenv()
    password = os.getenv("PASSWORD")
    engine = create_engine(f"mysql+pymysql://root:{password}@localhost/{SCHEMA}?charset=utf8mb4")
    # engine = create_engine(f"mysql+pymysql://aa-coco:{password}@localhost/{SCHEMA}?charset=utf8mb4")  # use this if aa-coco has been granted access

    tpcw_bu, tpcw_ct, tpcw_c, tpcw_pt, tpcw_i, tpcw_p = extract_tpcw(TPCW_DIR)

    dim_customer = transform_tpcw_customer(tpcw_c, tpcw_ct)
    dim_product  = transform_tpcw_product(tpcw_p, tpcw_bu, tpcw_pt)
    dim_supplier = build_dim_supplier(tpcw_p)

    dim_customer = add_sk(dim_customer, "customer_sk", next_sk(engine, "dim_customer", "customer_sk"))
    dim_product  = add_sk(dim_product,  "product_sk",  next_sk(engine, "dim_product",  "product_sk"))
    dim_supplier = add_sk(dim_supplier, "supplier_sk", next_sk(engine, "dim_supplier", "supplier_sk"))

    invoices   = clean_tpcw_invoices(tpcw_i)
    fact_sales = build_fact_table(invoices, tpcw_p, dim_customer, dim_product, dim_supplier)

    load_tpcw(engine, dim_customer, dim_product, dim_supplier, fact_sales)


if __name__ == "__main__":
    main()
