"""Shared look & feel: dark Netflix-style theme, KPI cards, section headers, Plotly styling. Import in every page: `from app import ui`."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import plotly.graph_objects as go
import streamlit as st

RED, DARK_RED, GREEN, AMBER, BLUE, GREY = "#E50914", "#B20710", "#2FBF71", "#F5A524", "#4C8DFF", "#8C8C99"
TEXT, MUTED, CARD, BORDER, BG = "#F5F5F1", "#9A9AAA", "#14141B", "#262633", "#0B0B0F"
RISK_COLORS = {"High": RED, "Medium": AMBER, "Low": GREEN}
PALETTE = [RED, BLUE, AMBER, GREEN, "#B06CFF", "#2CC4C4", "#F5F5F1", GREY]
PLAN_COLORS = {"Basic": GREY, "Standard": BLUE, "Premium": RED}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; }
.stApp { background: radial-gradient(1200px 500px at 85% -10%, rgba(229,9,20,.10), transparent 60%), #0B0B0F; }
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"], .stDeployButton { display:none !important; }
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapseButton"] { display:flex !important; visibility:visible !important; opacity:1 !important; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1480px; }
h1,h2,h3,h4 { letter-spacing: -0.02em; }
[data-testid="stSidebar"] { background: #0F0F15; border-right: 1px solid #1d1d28; }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
[data-testid="stSidebarNav"] a, [data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] { border-radius: 10px; margin: 2px 0; }
[data-testid="stVerticalBlockBorderWrapper"] { background: #14141B; border: 1px solid #262633 !important; border-radius: 16px; box-shadow: 0 8px 28px rgba(0,0,0,.28); }
.brand { display:flex; align-items:center; gap:10px; padding: 6px 4px 14px 4px; }
.brand .logo { width:34px; height:34px; border-radius:9px; background: linear-gradient(135deg,#E50914,#7a0309); display:flex; align-items:center; justify-content:center; font-weight:800; color:#fff; box-shadow:0 6px 18px rgba(229,9,20,.45); }
.brand .t1 { font-weight:800; font-size:15px; line-height:1.1; color:#fff; } .brand .t2 { font-size:11px; color:#9A9AAA; letter-spacing:.06em; text-transform:uppercase; }
.ph { margin: 0 0 1.1rem 0; padding-bottom: .9rem; border-bottom: 1px solid #1f1f2b; }
.ph h1 { font-size: 1.85rem; font-weight: 800; margin: 0; color:#fff; } .ph p { margin: .25rem 0 0 0; color:#9A9AAA; font-size: .95rem; }
.ph .tag { display:inline-block; font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#E50914; margin-bottom:.35rem; }
.kpi { background: linear-gradient(160deg,#171720 0%,#12121a 100%); border:1px solid #262633; border-radius:16px; padding:16px 18px 14px 18px; position:relative; overflow:hidden; height:100%; }
.kpi:before { content:''; position:absolute; left:0; top:0; height:100%; width:3px; background:#2a2a38; }
.kpi.accent:before { background: linear-gradient(180deg,#E50914,#7a0309); } .kpi.good:before { background:#2FBF71; } .kpi.warn:before { background:#F5A524; }
.kpi-label { font-size:11.5px; font-weight:600; color:#9A9AAA; letter-spacing:.07em; text-transform:uppercase; }
.kpi-value { font-size:29px; font-weight:800; color:#fff; margin-top:4px; letter-spacing:-0.02em; line-height:1.15; }
.kpi-sub { font-size:12.5px; color:#9A9AAA; margin-top:6px; display:flex; align-items:center; gap:7px; flex-wrap:wrap; }
.chip { font-size:11.5px; font-weight:700; padding:2px 8px; border-radius:20px; } .chip.up { background:rgba(47,191,113,.14); color:#2FBF71; } .chip.down { background:rgba(229,9,20,.16); color:#ff5a63; } .chip.flat { background:#232330; color:#b8b8c6; }
.sec { display:flex; align-items:baseline; gap:10px; margin: 1.3rem 0 .6rem 0; }
.sec .bar { width:4px; height:18px; border-radius:2px; background:#E50914; align-self:center; } .sec h3 { margin:0; font-size:1.08rem; font-weight:700; color:#fff; } .sec span { color:#8a8a99; font-size:.86rem; }
.callout { border:1px solid #2a2a38; border-left:4px solid #E50914; background:#13131a; border-radius:12px; padding:12px 16px; margin:.5rem 0; color:#dcdce4; font-size:.93rem; }
.callout.info { border-left-color:#4C8DFF; } .callout.good { border-left-color:#2FBF71; } .callout.warn { border-left-color:#F5A524; }
.badge { display:inline-block; padding:3px 11px; border-radius:20px; font-size:12px; font-weight:700; letter-spacing:.03em; }
.seg-card { background:linear-gradient(165deg,#181822,#12121a); border:1px solid #262633; border-radius:16px; padding:18px; height:100%; }
.seg-card h4 { margin:0 0 4px 0; font-size:1.02rem; color:#fff; } .seg-card .d { color:#9A9AAA; font-size:.84rem; min-height:92px; margin-top:6px; }
.seg-stat { display:flex; justify-content:space-between; font-size:.86rem; color:#c9c9d4; padding:5px 0; border-top:1px solid #20202b; } .seg-stat b { color:#fff; }
.msg-meta { font-size:11.5px; color:#9A9AAA; margin-bottom:4px; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom:1px solid #20202b; } .stTabs [data-baseweb="tab"] { height:40px; padding:0 14px; border-radius:10px 10px 0 0; color:#9A9AAA; font-weight:600; }
.stTabs [aria-selected="true"] { color:#fff !important; }
div[data-testid="stMetric"] { background:#14141B; border:1px solid #262633; border-radius:14px; padding:12px 16px; }
.stButton>button { border-radius:10px; border:1px solid #2d2d3b; background:#181822; color:#eee; font-weight:600; } .stButton>button:hover { border-color:#E50914; color:#fff; }
.stButton>button[kind="primary"] { background:linear-gradient(135deg,#E50914,#a30710); border:none; color:#fff; }
</style>
"""


def setup(title: str = "Customer Intelligence"):
    try:
        st.set_page_config(page_title=f"{title} · Netflix Customer Intelligence", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")
    except Exception:
        pass                                               # already set by the entry page
    st.markdown(CSS, unsafe_allow_html=True)


def brand():
    st.sidebar.markdown('<div class="brand"><div class="logo">N</div><div><div class="t1">Customer Intelligence</div><div class="t2">Churn · CLV · Copilot</div></div></div>', unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", tag: str = ""):
    t = f'<div class="tag">{tag}</div>' if tag else ""
    st.markdown(f'<div class="ph">{t}<h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def section(title: str, caption: str = ""):
    st.markdown(f'<div class="sec"><div class="bar"></div><h3>{title}</h3><span>{caption}</span></div>', unsafe_allow_html=True)


def kpi_html(label: str, value: str, sub: str = "", delta: float | None = None, delta_fmt: str = "{:.1f}%", good_when_up: bool = True, tone: str = "") -> str:
    chip = ""
    if delta is not None:
        cls = "flat" if abs(delta) < 1e-9 else ("up" if (delta > 0) == good_when_up else "down")
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "■"
        chip = f'<span class="chip {cls}">{arrow} {delta_fmt.format(abs(delta))}</span>'
    return f'<div class="kpi {tone}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div class="kpi-sub">{chip}<span>{sub}</span></div></div>'


def kpi_row(items: list[dict]):
    cols = st.columns(len(items))
    for c, it in zip(cols, items):
        c.markdown(kpi_html(**it), unsafe_allow_html=True)


def callout(text: str, kind: str = ""):
    st.markdown(f'<div class="callout {kind}">{text}</div>', unsafe_allow_html=True)


def badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background:{color}22;color:{color};border:1px solid {color}55">{text}</span>'


def style_fig(fig: go.Figure, height: int = 340, legend: bool = True, margin=(10, 10, 10, 10)) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=margin[0], r=margin[1], t=margin[2], b=margin[3]), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, sans-serif", color="#C9C9D4", size=12), colorway=PALETTE, showlegend=legend,
                      legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
                      hoverlabel=dict(bgcolor="#1c1c27", bordercolor="#333346", font=dict(family="Inter", color="#fff")))
    fig.update_xaxes(gridcolor="#20202c", zerolinecolor="#2a2a38", linecolor="#2a2a38", tickfont=dict(size=11))
    fig.update_yaxes(gridcolor="#20202c", zerolinecolor="#2a2a38", linecolor="#2a2a38", tickfont=dict(size=11))
    return fig


def plot(fig: go.Figure, key: str | None = None):
    try:
        st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False})
    except TypeError:                                      # older Streamlit
        st.plotly_chart(fig, use_container_width=True, key=key, config={"displayModeBar": False})


def table(df, **kw):
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)


def money(v: float, dec: int = 0) -> str:
    return f"${v:,.{dec}f}"


def card():
    return st.container(border=True)
