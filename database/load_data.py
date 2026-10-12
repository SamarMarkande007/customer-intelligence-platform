"""
Load the CLEANED CSVs (data/processed) into MySQL using pandas + SQLAlchemy.

Usage (from project root):
    1. mysql -u root -p < database/schema.sql      # creates DB + tables
    2. python database/load_data.py                # loads data in FK-safe order
Only the columns defined in schema.sql are loaded; audit columns
(*_original, *_flag ...) stay in the processed CSVs.
"""
import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.utils.config import PROCESSED_DIR, db_url

# (table, [schema columns], [date columns]) in foreign-key-safe load order
TABLES = [
    ("customers", ["customer_id","first_name","last_name","age","gender","country","state_or_region","city",
                   "registration_date","acquisition_channel","customer_segment","preferred_language"], ["registration_date"]),
    ("subscription_plans", ["plan_id","plan_name","monthly_price","video_quality","max_devices","advertisements"], []),
    ("subscriptions", ["subscription_id","customer_id","plan_id","subscription_start_date","subscription_end_date",
                       "subscription_status","auto_renew","cancellation_date","cancellation_reason","monthly_price"],
                      ["subscription_start_date","subscription_end_date","cancellation_date"]),
    ("content", ["content_id","title","content_type","genre","release_year","duration_minutes","content_language",
                 "production_country","maturity_rating"], []),
    ("viewing_activity", ["viewing_id","customer_id","content_id","viewing_date","watch_duration_minutes",
                          "completion_percentage","device_type","login_location","session_duration_minutes"], ["viewing_date"]),
    ("payments", ["payment_id","customer_id","subscription_id","payment_date","amount","payment_method",
                  "payment_status","failed_payment_reason"], ["payment_date"]),
    ("support_tickets", ["ticket_id","customer_id","ticket_date","issue_category","issue_subcategory","priority",
                         "ticket_status","resolution_time_hours","customer_satisfaction_score","ticket_description",
                         "support_agent_id"], ["ticket_date"]),
    ("customer_feedback", ["feedback_id","customer_id","feedback_date","rating","feedback_text","sentiment_label"], ["feedback_date"]),
    ("churn_labels", ["customer_id","churned","churn_date","churn_reason"], ["churn_date"]),
]


def main():
    engine = create_engine(db_url())
    for table, cols, date_cols in TABLES:
        df = pd.read_csv(PROCESSED_DIR / f"{table}.csv", usecols=cols, parse_dates=date_cols)[cols]
        for c in df.select_dtypes("bool").columns:
            df[c] = df[c].astype(int)
        df = df.astype(object).where(df.notna(), None)          # NaN/NaT -> NULL
        df.to_sql(table, engine, if_exists="append", index=False, chunksize=5000, method="multi")
        print(f"loaded {table:20s} {len(df):>8,} rows")

    with engine.connect() as conn:
        print("\nRow counts in MySQL:")
        for table, _, _ in TABLES:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  {table:20s} {n:>8,}")


if __name__ == "__main__":
    main()
