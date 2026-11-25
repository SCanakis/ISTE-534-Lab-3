ALTER DATABASE iste534 CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS iste534.dim_time(
    time_sk BIGINT PRIMARY KEY,
    year INT,
    quarter SMALLINT,
    week INT,
    month INT,
    day INT, 
    full_date DATE,
    fiscal_year INT,
    fiscal_quarter SMALLINT,
    fiscal_month INT
);

INSERT INTO iste534.dim_time (time_sk) VALUES (-1);

CREATE OR REPLACE VIEW iste534.order_time AS
SELECT * FROM iste534.dim_time;

CREATE OR REPLACE VIEW iste534.sale_time AS
SELECT * FROM iste534.dim_time;


CREATE TABLE IF NOT EXISTS  iste534.dim_supplier(
    supplier_sk BIGINT PRIMARY KEY,
    supplier_nk BIGINT,
    supplier_name VARCHAR(50),
    supplier_address1 VARCHAR(50),
    supplier_address2 VARCHAR(50),
    supplier_city VARCHAR(50),
    supplier_state VARCHAR(2),
    supplier_zip VARCHAR(5)
);

INSERT INTO iste534.dim_supplier(supplier_sk, supplier_name) VALUES (-1, 'N/A');

CREATE TABLE IF NOT EXISTS  iste534.dim_customer(
    customer_sk BIGINT PRIMARY KEY,
    customer_nk BIGINT,
    customer_name VARCHAR(50),
    customer_address1 VARCHAR(50),
    customer_address2 VARCHAR(50),
    customer_city VARCHAR(50),
    customer_state VARCHAR(2),
    customer_zip VARCHAR(5),
    customer_type_id CHAR(1),
    customer_type_name VARCHAR(20),
    internal BOOLEAN NOT NULL,
    internal_division VARCHAR(10),
    source_system VARCHAR(10) NOT NULL
);


CREATE TABLE IF NOT EXISTS  iste534.dim_product(
    product_sk BIGINT PRIMARY KEY,
    product_nk BIGINT,
    product_description VARCHAR(50),
    product_price1 decimal(10,2),
    product_price2 decimal(10,2),
    product_unit_cost decimal(10,2),
    prod_type_id INT,
    type_description VARCHAR(25),
    bu_id CHAR(1),
    bu_name VARCHAR(25),
    bu_abbrev VARCHAR(10),
    source_system VARCHAR(10) NOT NULL
);


CREATE TABLE IF NOT EXISTS  iste534.dim_junk(
    junk_sk BIGINT PRIMARY KEY,
    special_shipment VARCHAR(25) NOT NULL,
    order_method VARCHAR(25) NOT NULL,
    payment_method VARCHAR(25) NOT NULL,
    discounted BOOLEAN NOT NULL,
    CONSTRAINT special_shipment_constraint
        CHECK (
            special_shipment IN (
                'train',
                'truck',
                'air',
                'N/A'
            )
        ),
    CONSTRAINT order_method_constraint
        CHECK (
            order_method IN (
                'internet',
                'phone',
                'email',
                'mail',
                'N/A'
            )
        ),
    CONSTRAINT payment_method_constraint
        CHECK (
            payment_method IN (
                'cod',
                'charge',
                'cash',
                'N/A'
            )
        )
);

INSERT INTO iste534.dim_junk VALUES (-1, 'N/A','N/A','N/A',FALSE);
INSERT INTO iste534.dim_junk VALUES (-2, 'N/A','N/A','N/A',TRUE);

CREATE TABLE IF NOT EXISTS iste534.fact_sales(
    order_time_fk BIGINT,
    sale_time_fk BIGINT,
    supplier_fk BIGINT,
    customer_fk BIGINT,
    product_fk BIGINT,
    junk_fk BIGINT,

    invoice_nk BIGINT,
    source_system VARCHAR(10),
    fact_sales_amount DECIMAL(10,2),
    fact_num_products INT,
    fact_cost DECIMAL(10,2),
    shipping_cost DECIMAL(10,2), 
    fulfill_time INT,
    gross_profit DECIMAL(10,2),

    CONSTRAINT order_time_constraint
        FOREIGN KEY (order_time_fk) REFERENCES iste534.dim_time(time_sk),
    CONSTRAINT sale_time_constraint
        FOREIGN KEY (sale_time_fk) REFERENCES iste534.dim_time(time_sk),
    CONSTRAINT supplier_constraint
        FOREIGN KEY (supplier_fk) REFERENCES iste534.dim_supplier(supplier_sk),
    CONSTRAINT customer_constraint
        FOREIGN KEY (customer_fk) REFERENCES iste534.dim_customer(customer_sk),
    CONSTRAINT product_constraint
        FOREIGN KEY (product_fk) REFERENCES iste534.dim_product(product_sk),
    CONSTRAINT junk_constraint
        FOREIGN KEY (junk_fk) REFERENCES iste534.dim_junk(junk_sk),
    CONSTRAINT primary_key_constraint
        PRIMARY KEY (order_time_fk, sale_time_fk, supplier_fk, customer_fk, product_fk, junk_fk, invoice_nk)
);