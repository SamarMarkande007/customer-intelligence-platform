# Netflix Customer Intelligence, Churn Prediction & AI Analytics Copilot
 
End-to-end analytics project: cleaned data, MySQL database, 37 SQL business questions, EDA (32 charts),
ML models, a free-LLM analytics copilot and a Streamlit app.
 
## Setup
```bash
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
.env           #  -> then set DB_PASSWORD
```
 
## Run order
| Step | Command / file | Output |
|---|---|---|
| 1 | `notebooks/01_data_cleaning.ipynb` | cleaned CSVs + `data_quality_log.csv` in `data/processed/` |
| 2 | `mysql -u root -p < database/schema.sql` | database `netflix_ci`, 9 tables |
| 3 | `python database/load_data.py` | loads cleaned CSVs through SQLAlchemy |
| 4 | `database/sql_business_questions.sql` (open in MySQL Workbench) | answers to all 37 questions |
| 4b | `python database/run_queries.py` | runs all queries, saves results to `reports/sql_results/` |
| 5 | `notebooks/02_exploratory_analysis.ipynb` | 32 charts in `reports/figures/` |
| 6+ | feature engineering, ML, copilot, Streamlit | coming next |
 
## Key decisions
- "Today" = **2026-06-30** (latest date in the data). Payments stop on 2026-05-31, so payment windows use `MAX(payment_date)`.
- "Active customer" = `churn_labels.churned = 0`. "Current plan" = latest `subscriptions` row.
- Every cleaning decision is logged in `data/processed/data_quality_log.csv`.
## Data quirks worth knowing
- Churn dates only exist from **2025-10-03** onward, so monthly churn is 0 for Jul-Sep 2025 and old cohorts show 100% early retention.
- Within a customer, `subscriptions.monthly_price` never changes (the old row carries the new plan's price). "Price change" in Q29 therefore means a plan switch with a different list price.
- 305 of 875 plan changes are same-plan to same-plan; Q34 labels them "Same plan".
- Viewing history covers only 2025-07-01 .. 2026-06-30.
