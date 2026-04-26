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
from app.state import get_state, get_portfolio_value
from app.helpers import safe_num, to_usd, signed_pct, fmt_rel_time
from app.pages import (overview, build, watchlist, trade, review,
                        insights, settings as settings_page)

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
st.markdown("<div style='margin-bottom:14px;'></div>", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────
# PERSISTENT TICKER BAR — visible across every tab
# ────────────────────────────────────────────────────────────────────
def _render_ticker_bar() -> None:
    state = get_state()
    nav = get_portfolio_value(state)
    cash = safe_num(state.get("cashUSD"), 0)
    cash_pct = (cash / nav * 100) if nav > 0 else 0
    start_cap = safe_num(state["settings"].get("startingCapital"), 1000)
    pnl_pct = ((nav - start_cap) / start_cap * 100) if start_cap > 0 else 0
    pnl_class = "good" if pnl_pct >= 0 else "bad"

    val = state.get("valuation", [])
    daily = (nav - safe_num(val[-2].get("portfolioValueUSD"), nav)
             if len(val) > 1 else 0)
    daily_class = "good" if daily >= 0 else "bad"
    daily_pct = (daily / safe_num(val[-2].get("portfolioValueUSD"), nav) * 100
                  if len(val) > 1 and safe_num(val[-2].get("portfolioValueUSD"), 0) > 0 else 0)

    last_refresh = state.get("lastRefresh") or "never"
    if last_refresh != "never":
        last_refresh = fmt_rel_time(last_refresh) or "recent"
    is_fresh = "ago" in last_refresh and not last_refresh.startswith(("3d", "4d", "5d", "6d", "7d"))
    live_dot = "<span class='ticker-bar-live'></span>" if is_fresh else ""

    n_pos = len(state.get("holdings", []))

    bar_html = (
        "<div class='ticker-bar'>"
        f"<div class='ticker-bar-item'>"
        f"<span class='ticker-bar-label'>NAV</span>"
        f"<span class='ticker-bar-value'>{to_usd(nav)}</span>"
        f"<span class='ticker-bar-delta {pnl_class}'>{signed_pct(pnl_pct)}</span>"
        f"</div>"
        f"<div class='ticker-bar-divider'></div>"
        f"<div class='ticker-bar-item'>"
        f"<span class='ticker-bar-label'>Day</span>"
        f"<span class='ticker-bar-value {daily_class}'>{to_usd(daily)}</span>"
        f"<span class='ticker-bar-delta {daily_class}'>{signed_pct(daily_pct)}</span>"
        f"</div>"
        f"<div class='ticker-bar-divider'></div>"
        f"<div class='ticker-bar-item'>"
        f"<span class='ticker-bar-label'>Cash</span>"
        f"<span class='ticker-bar-value'>{to_usd(cash)}</span>"
        f"<span class='ticker-bar-delta muted-text'>{cash_pct:.1f}%</span>"
        f"</div>"
        f"<div class='ticker-bar-divider'></div>"
        f"<div class='ticker-bar-item'>"
        f"<span class='ticker-bar-label'>Positions</span>"
        f"<span class='ticker-bar-value'>{n_pos}</span>"
        f"</div>"
        f"<div class='ticker-bar-divider'></div>"
        f"<div class='ticker-bar-item'>"
        f"<span class='ticker-bar-label'>Refreshed</span>"
        f"<span class='ticker-bar-value' style='font-size:13px;'>{live_dot}{last_refresh}</span>"
        f"</div>"
        "</div>"
    )
    st.markdown(bar_html, unsafe_allow_html=True)


_render_ticker_bar()


# ────────────────────────────────────────────────────────────────────
# TABS
# ────────────────────────────────────────────────────────────────────
tab_names = ["Overview", "Build", "Watchlist", "Trade", "Review", "Insights", "Settings"]
tabs = st.tabs(tab_names)

with tabs[0]:
    overview.render()
with tabs[1]:
    build.render()
with tabs[2]:
    watchlist.render()
with tabs[3]:
    trade.render()
with tabs[4]:
    review.render()
with tabs[5]:
    insights.render()
with tabs[6]:
    settings_page.render()
