"""Paper Portfolio Tracker — Streamlit entry point.

Run locally:
    streamlit run streamlit_app.py

Deploys to Streamlit Community Cloud with this filename as the entry.
"""
import streamlit as st

# Page config MUST be the very first st.* call
st.set_page_config(
    page_title="Paper Portfolio Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from app import styles
from app.pages import overview, build, trade, review, settings as settings_page

# Inject custom CSS (dark Bloomberg aesthetic)
styles.inject()

# ────────────────────────────────────────────────────────────────────
# MASTHEAD
# ────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='display:inline-block; margin:0; font-size:24px;'>Paper Portfolio Tracker</h1>"
    "<span class='paper-badge'>PAPER · SIMULATED · NO REAL CAPITAL</span>",
    unsafe_allow_html=True,
)
st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────
# TABS
# ────────────────────────────────────────────────────────────────────
tab_names = ["Overview", "Build", "Trade", "Review", "Settings"]
tabs = st.tabs(tab_names)

with tabs[0]:
    overview.render()
with tabs[1]:
    build.render()
with tabs[2]:
    trade.render()
with tabs[3]:
    review.render()
with tabs[4]:
    settings_page.render()
