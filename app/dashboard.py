"""
Netflix Customer Intelligence: Streamlit app entry point.
Run from the project root:   streamlit run app/dashboard.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st
from app import ui

ui.setup("Home")
ui.brand()

pages = {
    "Analytics": [
        st.Page("pages/1_Executive_Overview.py", title="Executive Overview", icon="📊", default=True),
        st.Page("pages/2_Customer_Analytics.py", title="Customer Analytics", icon="👥"),
        st.Page("pages/3_Churn_Risk.py", title="Churn Risk", icon="⚠️"),
        st.Page("pages/4_Segmentation.py", title="Segmentation", icon="🧩"),
    ],
    "Customers & AI": [
        st.Page("pages/5_Customer_360.py", title="Customer 360", icon="🔎"),
        st.Page("pages/6_AI_Copilot.py", title="AI Copilot", icon="🤖"),
        st.Page("pages/7_Reports_and_Models.py", title="Reports & Models", icon="📑"),
    ],
}
st.navigation(pages).run()
