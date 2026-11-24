# Vendor and Shipment Performance Analysis

This project analyzes the public USAID Supply Chain Shipment Pricing dataset using Python, SQLite, SQL, Excel, and Power BI.

## Run the ETL pipeline

Keep the source CSV at `data/SCMS_Delivery_History_Dataset.csv`. From the project root, activate the Python environment used by the notebook and run:

```bash
python scripts/run_etl.py
```

The script leaves the raw CSV unchanged. It normalizes field names, creates parsed numeric/date companions and status fields, records review exceptions, loads `stg_shipments` into SQLite, and runs the SQL reports.

Generated processed data is written under `data/processed/`. SQL report CSVs are refreshed in `sql/` using the existing filenames so the Excel workbook can refresh from those files:

- `vendor_analysis.db` — SQLite database with the `stg_shipments` table
- `cleaned_shipment_lines.csv` — line-level data with raw and derived fields
- `data_quality_summary.csv` and `data_quality_exceptions.csv` — quality checks and review flags
- `etl_run.log` — run log

The six SQL report CSVs are `vendor_summary.csv`, `vendor_spend.csv`, `vendor_delivery_perfomance.csv`, `monthly_spend.csv`, `vendor_spend_concentration.csv`, and `freight_status_by_vendor.csv` in `sql/`.

Install the script dependency in that environment with `python -m pip install -r requirements.txt` if pandas is missing.

## Important interpretation notes

- The data is public historical shipment data, not UAE company or FM contract data.
- Delivery performance compares actual delivery with scheduled delivery; it is not an FM SLA measure.
- Several weight, freight, and date fields contain meaningful status text or references. The pipeline retains those source values and adds separate parsed/status columns.
- Delivery status is line-level in `stg_shipments`; use the shipment-level SQL report when counting shipments.
