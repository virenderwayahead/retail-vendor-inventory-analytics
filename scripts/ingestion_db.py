import pandas as pd
import os
from sqlalchemy import create_engine
import logging
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.FileHandler(os.path.join(BASE_DIR, "logs", "ingestion_db.log"), mode="a")
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_handler)

engine = create_engine(f'sqlite:///{os.path.join(BASE_DIR, "inventory.db")}')


def ingest_db(df, table_name, engine, if_exists='replace'):
    """Ingest dataframe into database"""
    df.to_sql(table_name, con=engine, if_exists=if_exists, index=False)


INPUT_FILES = [
    "begin_inventory.csv",
    "end_inventory.csv",
    "purchase_prices.csv",
    "purchases.csv",
    "sales.csv",
    "vendor_invoice.csv",
]


def load_raw_data():
    """Load CSVs and ingest into database"""

    start = time.time()

    for file in INPUT_FILES:

        filepath = os.path.join(BASE_DIR, file)

        try:
            if not os.path.exists(filepath):
                logger.error(f"Input file not found: {filepath}")
                raise FileNotFoundError(f"Input file not found: {filepath}")

            logger.info(f"Starting ingestion of {file}...")

            table_name = file[:-4]
            total_rows = 0

            for i, chunk in enumerate(pd.read_csv(filepath, chunksize=50000)):
                # First chunk replaces the table, remaining chunks append
                mode = 'replace' if i == 0 else 'append'
                ingest_db(chunk, table_name, engine, if_exists=mode)
                total_rows += len(chunk)

            logger.info(f"Completed ingestion of {file} ({total_rows} rows)")

        except Exception:
            logger.exception(f"Failed to ingest {file}")
            raise

    end = time.time()

    total_time = (end - start) / 60

    logger.info("---------------- Ingestion Complete ----------------")

    logger.info(f"Total Time Taken: {total_time:.2f} minutes")


if __name__ == "__main__":
    load_raw_data()