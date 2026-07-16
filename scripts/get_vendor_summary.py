import sqlite3
import os
import numpy as np
import pandas as pd
import logging
import time
from ingestion_db import ingest_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.FileHandler(os.path.join(BASE_DIR, "logs", "get_vendor_summary.log"), mode="a")
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_handler)


def create_vendor_summary(conn):
    """This function will merge the different tables to get the overall vendor summary and add new columns to the resultant data."""

    vendor_sales_summary = pd.read_sql_query("""
WITH FreightSummary AS (
    SELECT
        VendorNumber,
        SUM(Freight) AS FreightCost
    FROM vendor_invoice
    GROUP BY VendorNumber
),

PurchaseSummary AS (
    SELECT
        p.VendorNumber,
        p.VendorName,
        p.Brand,
        p.Description,
        p.PurchasePrice,
        pp.Price AS ActualPrice,
        pp.Volume,
        SUM(p.Quantity) AS TotalPurchaseQuantity,
        SUM(p.Dollars) AS TotalPurchaseDollars
    FROM purchases p
    JOIN purchase_prices pp
        ON p.Brand = pp.Brand
    WHERE p.PurchasePrice > 0
    GROUP BY
        p.VendorNumber,
        p.VendorName,
        p.Brand,
        p.Description,
        p.PurchasePrice,
        pp.Price,
        pp.Volume
),

SalesSummary AS (
    SELECT
        VendorNo,
        Brand,
        SUM(SalesQuantity) AS TotalSalesQuantity,
        SUM(SalesDollars) AS TotalSalesDollars,
        SUM(SalesPrice) AS TotalSalesPrice,
        SUM(ExciseTax) AS TotalExciseTax
    FROM sales
    GROUP BY VendorNo, Brand
)

SELECT
    ps.VendorNumber,
    ps.VendorName,
    ps.Brand,
    ps.Description,
    ps.PurchasePrice,
    ps.ActualPrice,
    ps.Volume,
    ps.TotalPurchaseQuantity,
    ps.TotalPurchaseDollars,
    ss.TotalSalesQuantity,
    ss.TotalSalesDollars,
    ss.TotalSalesPrice,
    ss.TotalExciseTax,
    fs.FreightCost
FROM PurchaseSummary ps
LEFT JOIN SalesSummary ss
    ON ps.VendorNumber = ss.VendorNo
    AND ps.Brand = ss.Brand
LEFT JOIN FreightSummary fs
    ON ps.VendorNumber = fs.VendorNumber
ORDER BY ps.TotalPurchaseDollars DESC
""", conn)

    return vendor_sales_summary


def clean_data(df):
    """This function will clean the data"""

    # changing datatype to float
    df['Volume'] = df['Volume'].astype('float')

    # filling missing values with 0 for numeric columns only
    numeric_cols = df.select_dtypes(include='number').columns
    df[numeric_cols] = df[numeric_cols].fillna(0)

    # removing spaces from categorical columns
    df['VendorName'] = df['VendorName'].str.strip()
    df['Description'] = df['Description'].str.strip()

    # creating new columns for better analysis
    df['GrossProfit'] = df['TotalSalesDollars'] - df['TotalPurchaseDollars']

    df['ProfitMargin'] = (
        df['GrossProfit'] / df['TotalSalesDollars']
    ) * 100

    df['StockTurnover'] = (
        df['TotalSalesQuantity'] / df['TotalPurchaseQuantity']
    )

    df['SalesToPurchaseRatio'] = (
        df['TotalSalesDollars'] / df['TotalPurchaseDollars']
    )

    # replacing inf/-inf with 0 for clean reporting in Power BI
    df.replace([np.inf, -np.inf], 0, inplace=True)

    return df


if __name__ == '__main__':

    # Start timer
    start_time = time.time()

    conn = None
    report_conn = None

    try:
        # creating database connection
        conn = sqlite3.connect(os.path.join(BASE_DIR, 'inventory.db'))

        logger.info('Creating Vendor Summary Table.....')
        summary_df = create_vendor_summary(conn)
        logger.info(f'Vendor Summary created: {summary_df.shape[0]} rows, {summary_df.shape[1]} columns')

        logger.info('Cleaning Data.....')
        clean_df = clean_data(summary_df)
        logger.info(f'Data cleaned: {clean_df.shape[0]} rows, {clean_df.shape[1]} columns')

        logger.info('Ingesting data.....')
        ingest_db(clean_df, 'vendor_sales_summary', conn)

        # Create / Update Reporting Database
        report_conn = sqlite3.connect(os.path.join(BASE_DIR, 'vendor_summary.db'))

        clean_df.to_sql(
            'vendor_sales_summary',
            report_conn,
            if_exists='replace',
            index=False
        )

        logger.info('Reporting database (vendor_summary.db) updated successfully.')

    except Exception:
        logger.exception('ETL pipeline failed.')
        raise

    finally:
        if report_conn:
            report_conn.close()
        if conn:
            conn.close()

    # End timer
    end_time = time.time()
    total_time = end_time - start_time

    logger.info(f'Total Execution Time: {total_time:.2f} seconds')

    print(f"\nExecution completed in {total_time:.2f} seconds.")