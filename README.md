# Netflix Customer Intelligence, Churn Prediction & AI Analytics Copilot

End-to-end analytics project: MySQL database, 37 SQL business questions, EDA, 3 ML models,
a free-LLM analytics copilot and a Streamlit app.

## Setup
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then fill in DB_PASSWORD
```

## Run order
1. `notebooks/01_data_cleaning.ipynb`  -> writes cleaned CSVs to `data/processed/`
2. `mysql -u root -p < database/schema.sql`           (creates database `netflix_ci` + 9 tables)
3. `python database/load_data.py`                      (loads cleaned CSVs through SQLAlchemy)
4. `database/sql_business_questions.sql`               (37 queries)  [next step]
5. Notebooks 02-06, then `streamlit run app/dashboard.py` [later steps]

## Key decisions
- Reference date for "today" = **2026-06-30** (latest date in the data). See `src/utils/config.py`.
- Every cleaning decision is logged in `data/processed/data_quality_log.csv`.
