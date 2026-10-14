"""
Single place where the app / copilot read the analysis tables (CSV based, so the dashboard also works without MySQL).

master()  -> one row per customer: features + churn score + calibrated probability + CLV tier + segment
"""
from __future__ import annotations
from functools import lru_cache
import joblib
import numpy as np
import pandas as pd
from src.utils.config import ROOT, PROCESSED_DIR, REFERENCE_DATE

MODELS_DIR = ROOT / "models"
DATE_COLS = {"customers": ["registration_date"], "subscriptions": ["subscription_start_date", "subscription_end_date", "cancellation_date"],
             "viewing_activity": ["viewing_date"], "payments": ["payment_date"], "support_tickets": ["ticket_date"],
             "customer_feedback": ["feedback_date"], "churn_labels": ["churn_date"]}


@lru_cache(maxsize=16)
def load_table(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / f"{name}.csv", parse_dates=DATE_COLS.get(name, []))


@lru_cache(maxsize=1)
def churn_bundle() -> dict:
    return joblib.load(MODELS_DIR / "churn_model.joblib")


@lru_cache(maxsize=1)
def _calibrator():
    """Platt scaling. The churn model uses class weights, so its raw scores are NOT probabilities (average ~0.5 vs a 24% base rate).
    We map score -> probability with a logistic fit on the same held-out test split used in notebook 04 (random_state 42)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    b = churn_bundle(); snap = pd.read_csv(PROCESSED_DIR / "features_snapshot.csv")
    X, y = snap[b["features"]], snap["churned_next"].values
    _, X_te, _, y_te = train_test_split(X, y, test_size=.2, stratify=y, random_state=42)
    raw = np.clip(b["model"].predict_proba(X_te)[:, 1], 1e-6, 1 - 1e-6)
    lr = LogisticRegression(C=1e6).fit(np.log(raw / (1 - raw)).reshape(-1, 1), y_te)
    return lambda p: lr.predict_proba(np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))).reshape(-1, 1))[:, 1]


@lru_cache(maxsize=1)
def master() -> pd.DataFrame:
    f = pd.read_csv(PROCESSED_DIR / "customer_features.csv", parse_dates=["as_of", "registration_date", "churn_date"])
    m = (f.merge(pd.read_csv(PROCESSED_DIR / "churn_scores.csv"), on="customer_id", how="left")
          .merge(pd.read_csv(PROCESSED_DIR / "clv_scores.csv"), on="customer_id", how="left")
          .merge(pd.read_csv(PROCESSED_DIR / "customer_segments.csv"), on="customer_id", how="left"))
    has = m.churn_risk_score.notna()
    m["churn_prob_est"] = np.nan
    m.loc[has, "churn_prob_est"] = _calibrator()(m.loc[has, "churn_risk_score"].values)
    m["expected_loss_monthly"] = m.churn_prob_est * m.monthly_price            # expected monthly revenue lost = P(churn) x price
    m["age_group"] = pd.cut(m.age, [12, 24, 34, 44, 54, 100], labels=["13-24", "25-34", "35-44", "45-54", "55+"]).astype(str)
    m["active"] = (m.churned == 0)
    return m


def clear_caches():
    load_table.cache_clear(); master.cache_clear(); _calibrator.cache_clear(); churn_bundle.cache_clear()
