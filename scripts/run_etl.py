"""Rebuild the shipment analysis outputs from the original CSV."""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "SCMS_Delivery_History_Dataset.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
DATABASE_PATH = OUTPUT_DIR / "vendor_analysis.db"
SQL_EXPORT_DIR = PROJECT_ROOT / "sql"

# Preserve the current SQL filenames while exporting with clean output names.
SQL_REPORTS = {
    "01_vendor_summary.sql": "vendor_summary.csv",
    "02_vendor_spend.sql": "vendor_spend.csv",
    "03_vendor_delivery_perfomance.sql": "vendor_delivery_perfomance.csv",
    "04_monthly_spend": "monthly_spend.csv",
    "05_vendor_spend_concentration.sql": "vendor_spend_concentration.csv",
    "06_firght_status_by_vendor.sql": "freight_status_by_vendor.csv",
}

KEY_COLUMNS = ["ID", "Project Code", "PQ #", "PO / SO #", "ASN/DN #"]
NUMERIC_COLUMNS = [
    "unit of measure (per pack)",
    "line item quantity",
    "line item value",
    "pack price",
    "unit price",
    "line item insurance (usd)",
]
DATE_COLUMNS = [
    "pq first sent to client date",
    "po sent to vendor date",
    "scheduled delivery date",
    "delivered to client date",
    "delivery recorded date",
]


def normalize_column_name(column: str) -> str:
    """Convert source headers to lowercase snake_case for SQL use."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", column.strip().lower())).strip("_")


def add_quality_metric(rows: list[dict], name: str, value: int | float | str, note: str) -> None:
    rows.append({"check_name": name, "value": value, "note": note})


def add_exception(
    records: list[dict],
    clean_df: pd.DataFrame,
    row_index: int,
    field: str,
    raw_value: object,
    issue: str,
) -> None:
    records.append(
        {
            "source_row_index": row_index,
            "id": clean_df.at[row_index, "id"] if "id" in clean_df.columns else "",
            "po_so": clean_df.at[row_index, "po_so"] if "po_so" in clean_df.columns else "",
            "asn_dn": clean_df.at[row_index, "asn_dn"] if "asn_dn" in clean_df.columns else "",
            "field": field,
            "raw_value": raw_value,
            "issue": issue,
        }
    )


def main() -> None:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Raw dataset not found: {RAW_FILE}\n"
            "Place the Kaggle CSV at data/SCMS_Delivery_History_Dataset.csv."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SQL_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / "etl_run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )

    logging.info("Reading raw dataset: %s", RAW_FILE)
    raw_df = pd.read_csv(
        RAW_FILE,
        low_memory=False,
        keep_default_na=False,
        dtype={column: "string" for column in KEY_COLUMNS},
        encoding="utf-8-sig",
    )
    source_rows = len(raw_df)
    exact_duplicate_excess = int(raw_df.duplicated().sum())
    duplicate_rows_involved = int(raw_df.duplicated(keep=False).sum())
    blank_cells = int(
        raw_df.astype("string").apply(lambda values: values.str.strip().eq("")).sum().sum()
    )

    clean_df = raw_df.copy()
    clean_df.insert(0, "source_row_index", range(source_rows))
    clean_df.columns = [normalize_column_name(str(column)) for column in clean_df.columns]
    if clean_df.columns.duplicated().any():
        duplicates = clean_df.columns[clean_df.columns.duplicated()].tolist()
        raise ValueError(f"Header normalization created duplicate columns: {duplicates}")

    quality_rows: list[dict] = []
    exception_records: list[dict] = []
    add_quality_metric(quality_rows, "source_rows", source_rows, "Rows read from the unchanged raw CSV.")
    add_quality_metric(quality_rows, "source_columns", len(raw_df.columns), "Source fields before derived columns.")
    add_quality_metric(quality_rows, "blank_source_cells", blank_cells, "Blank strings in source cells; no rows removed.")
    add_quality_metric(quality_rows, "exact_duplicate_rows_involved", duplicate_rows_involved, "Exact full-row duplicates, including the first copy.")
    add_quality_metric(quality_rows, "exact_duplicate_excess_rows", exact_duplicate_excess, "Extra exact full-row copies beyond the first.")

    # Numeric copies are created alongside raw fields so special source text is retained.
    for field in NUMERIC_COLUMNS:
        column = normalize_column_name(field)
        if column not in clean_df.columns:
            raise KeyError(f"Expected numeric source field is missing: {field}")
        raw_values = clean_df[column].astype("string").str.strip()
        parsed = pd.to_numeric(raw_values.str.replace(",", "", regex=False), errors="coerce")
        clean_df[f"{column}_numeric"] = parsed
        invalid = raw_values.ne("") & parsed.isna()
        add_quality_metric(
            quality_rows,
            f"{column}_non_numeric_nonblank",
            int(invalid.sum()),
            "Nonblank text not converted to a number; flagged, not imputed.",
        )
        for row_index, value in raw_values[invalid].items():
            add_exception(exception_records, clean_df, int(row_index), column, value, "Non-numeric value in numeric field")

    # Weight and freight intentionally mix numeric amounts with operational statuses/references.
    weight_raw = clean_df["weight_kilograms"].astype("string").str.strip()
    weight_numeric = pd.to_numeric(weight_raw.str.replace(",", "", regex=False), errors="coerce")
    clean_df["weight_kg_numeric"] = weight_numeric
    clean_df["weight_status"] = "Review other value"
    clean_df.loc[weight_numeric.notna(), "weight_status"] = "Numeric value"
    clean_df.loc[weight_raw.str.match(r"(?i)^see\b", na=False), "weight_status"] = "See ASN/DN reference"
    clean_df.loc[weight_raw.eq("Weight Captured Separately"), "weight_status"] = "Captured separately"

    freight_raw = clean_df["freight_cost_usd"].astype("string").str.strip()
    freight_numeric = pd.to_numeric(freight_raw.str.replace(",", "", regex=False), errors="coerce")
    clean_df["freight_usd_numeric"] = freight_numeric
    clean_df["freight_status"] = "Review other value"
    clean_df.loc[freight_numeric.notna(), "freight_status"] = "Numeric value"
    clean_df.loc[freight_raw.str.match(r"(?i)^see\b", na=False), "freight_status"] = "See ASN/DN reference"
    clean_df.loc[freight_raw.eq("Freight Included in Commodity Cost"), "freight_status"] = "Included in commodity cost"
    clean_df.loc[freight_raw.eq("Invoiced Separately"), "freight_status"] = "Invoiced separately"

    for field, status_column, raw_values in [
        ("weight_kilograms", "weight_status", weight_raw),
        ("freight_cost_usd", "freight_status", freight_raw),
    ]:
        review_mask = clean_df[status_column].eq("Review other value") & raw_values.ne("")
        add_quality_metric(quality_rows, f"{status_column}_review_other", int(review_mask.sum()), "Unexpected status text; retained and flagged.")
        for row_index, value in raw_values[review_mask].items():
            add_exception(exception_records, clean_df, int(row_index), field, value, "Unrecognized weight/freight status")
        for status, count in clean_df[status_column].value_counts(dropna=False).items():
            add_quality_metric(quality_rows, f"{status_column}:{status}", int(count), "Expected mixed numeric/status source field.")

    date_status_specs = {
        "pq_first_sent_to_client_date": {
            "Pre-PQ Process": "Pre-PQ Process",
            "Date Not Captured": "Date not captured",
        },
        "po_sent_to_vendor_date": {
            "N/A - From RDC": "Not applicable - From RDC",
            "Date Not Captured": "Date not captured",
        },
    }

    for column_name in [normalize_column_name(field) for field in DATE_COLUMNS]:
        if column_name not in clean_df.columns:
            raise KeyError(f"Expected date source field is missing: {column_name}")
        raw_values = clean_df[column_name].astype("string").str.strip()
        parsed = pd.to_datetime(raw_values.where(raw_values.ne("")), errors="coerce")
        clean_df[f"{column_name}_parsed"] = parsed
        invalid = raw_values.ne("") & parsed.isna()

        if column_name in date_status_specs:
            status_column = f"{column_name}_status"
            clean_df[status_column] = "Review other value"
            clean_df.loc[parsed.notna(), status_column] = "Date captured"
            for marker, status in date_status_specs[column_name].items():
                clean_df.loc[raw_values.eq(marker), status_column] = status
            clean_df.loc[raw_values.eq(""), status_column] = "Source blank"
            unexpected = clean_df[status_column].eq("Review other value")
            for row_index, value in raw_values[unexpected].items():
                add_exception(exception_records, clean_df, int(row_index), column_name, value, "Unrecognized date/status value")
            for status, count in clean_df[status_column].value_counts(dropna=False).items():
                add_quality_metric(quality_rows, f"{status_column}:{status}", int(count), "Date captured or documented source status.")
        else:
            for row_index, value in raw_values[invalid].items():
                add_exception(exception_records, clean_df, int(row_index), column_name, value, "Date could not be parsed")
        add_quality_metric(quality_rows, f"{column_name}_unparsed_nonblank", int(invalid.sum()), "Nonblank values not parsed as dates; special status markers are categorized separately where defined.")

    scheduled = clean_df["scheduled_delivery_date_parsed"]
    delivered = clean_df["delivered_to_client_date_parsed"]
    recorded = clean_df["delivery_recorded_date_parsed"]
    clean_df["delivery_variance_days"] = (delivered - scheduled).dt.days
    clean_df["delivery_status"] = "Review date"
    clean_df.loc[clean_df["delivery_variance_days"].lt(0), "delivery_status"] = "Early"
    clean_df.loc[clean_df["delivery_variance_days"].eq(0), "delivery_status"] = "On scheduled date"
    clean_df.loc[clean_df["delivery_variance_days"].gt(0), "delivery_status"] = "Late"
    for status, count in clean_df["delivery_status"].value_counts(dropna=False).items():
        add_quality_metric(quality_rows, f"delivery_status:{status}", int(count), "Line-level delivery variance; negative means early.")

    recorded_before_delivery = recorded.notna() & delivered.notna() & recorded.lt(delivered)
    add_quality_metric(quality_rows, "recorded_before_delivered_date", int(recorded_before_delivery.sum()), "Retained as source-date exceptions; not automatically corrected.")
    for row_index in clean_df.index[recorded_before_delivery]:
        add_exception(
            exception_records,
            clean_df,
            int(row_index),
            "delivery_recorded_date",
            clean_df.at[row_index, "delivery_recorded_date"],
            "Delivery recorded before delivered date",
        )

    clean_df.to_csv(OUTPUT_DIR / "cleaned_shipment_lines.csv", index=False)
    pd.DataFrame(quality_rows).to_csv(OUTPUT_DIR / "data_quality_summary.csv", index=False)
    exception_columns = ["source_row_index", "id", "po_so", "asn_dn", "field", "raw_value", "issue"]
    pd.DataFrame(exception_records, columns=exception_columns).to_csv(
        OUTPUT_DIR / "data_quality_exceptions.csv", index=False
    )

    logging.info("Writing SQLite database: %s", DATABASE_PATH)
    with sqlite3.connect(DATABASE_PATH) as connection:
        clean_df.to_sql("stg_shipments", connection, if_exists="replace", index=False)
        table_check = pd.read_sql_query(
            "SELECT COUNT(*) AS row_count FROM stg_shipments", connection
        )
        loaded_rows = int(table_check.iloc[0]["row_count"])
        if loaded_rows != source_rows:
            raise RuntimeError(f"Row-count mismatch: source={source_rows}, database={loaded_rows}")

        for query_filename, export_filename in SQL_REPORTS.items():
            query_path = PROJECT_ROOT / "sql" / query_filename
            if not query_path.exists():
                raise FileNotFoundError(f"SQL report not found: {query_path}")
            query = query_path.read_text(encoding="utf-8").strip()
            report_df = pd.read_sql_query(query, connection)
            report_df.to_csv(SQL_EXPORT_DIR / export_filename, index=False)
            logging.info("Exported %s rows to %s", len(report_df), SQL_EXPORT_DIR / export_filename)

    logging.info("ETL complete: %s source rows loaded; %s exceptions recorded.", source_rows, len(exception_records))
    logging.info("Processed outputs: %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()
