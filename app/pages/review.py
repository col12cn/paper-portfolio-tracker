"""Review tab: NAV chart, component price chart, logs, AI risk analysis."""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from app.state import get_state, commit, get_portfolio_value
from app.helpers import safe_num, to_usd, signed_pct
from app import ai


# ────────────────────────────────────────────────────────────────────
# NAV CHART
# ────────────────────────────────────────────────────────────────────

def _render_nav_chart(state: dict) -> None:
    val_history = [v for v in state.get("valuation", [])
                   if safe_num(v.get("portfolioValueUSD"), 0) > 0]
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown("### Portfolio NAV")
        with c2:
            if val_history:
                st.markdown(
                    f"<div style='text-align:right;color:#a8b4d8;font-size:12px;'>"
                    f"{val_history[0]['date']} → {val_history[-1]['date']}</div>",
                    unsafe_allow_html=True,
                )

        if len(val_history) < 2:
            st.info("Not enough data — fetch quotes a few times to start tracking NAV.")
            return

        xs = [v["date"] for v in val_history]
        ys = [v["portfolioValueUSD"] for v in val_history]
        start_cap = safe_num(state["settings"].get("startingCapital"), 1000)
        colour = "#27c281" if ys[-1] >= start_cap else "#ff6b6b"
        rgb = "39,194,129" if ys[-1] >= start_cap else "255,107,107"

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color=colour, width=2.5),
            fill="tozeroy", fillcolor=f"rgba({rgb},0.18)",
            hovertemplate="<b>%{x}</b><br>NAV: $%{y:,.2f}<extra></extra>",
            name="NAV",
        ))
        fig.add_hline(y=start_cap, line=dict(color="#7385b8", width=1, dash="dash"),
                       annotation_text=f"Start: {to_usd(start_cap)}",
                       annotation_position="top right")
        fig.update_layout(
            height=320, margin=dict(l=10, r=10, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0f1732",
            xaxis=dict(gridcolor="#1e2d54", tickfont=dict(color="#a8b4d8")),
            yaxis=dict(gridcolor="#1e2d54", tickfont=dict(color="#a8b4d8"),
                        tickformat="$,.0f"),
            showlegend=False, hovermode="x",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ────────────────────────────────────────────────────────────────────
# COMPONENT PRICE CHART (% from base)
# ────────────────────────────────────────────────────────────────────

def _render_component_chart(state: dict) -> None:
    snaps = state.get("priceSnap", [])
    with st.container(border=True):
        st.markdown("### Component prices · % from base")
        st.caption("Each line = a holding's price change vs its first observed snapshot. "
                   "Snapshots accumulate each time you fetch quotes.")

        if len(snaps) < 2:
            st.info("Need at least 2 snapshots — fetch quotes again.")
            return

        # Find all tickers + base prices
        all_tickers = sorted({t for s in snaps for t in s.get("prices", {}).keys()})
        base_prices = {}
        for t in all_tickers:
            for s in snaps:
                if t in s.get("prices", {}):
                    base_prices[t] = s["prices"][t]; break
        if not base_prices:
            st.info("No usable price data yet."); return

        fig = go.Figure()
        palette = ["#7aa2ff", "#27c281", "#f3b74f", "#ff6b6b", "#c587ff",
                   "#5dd4d4", "#ff9966", "#9af36b", "#ff7faa", "#88e0ff"]
        for i, t in enumerate(all_tickers):
            xs, ys = [], []
            base = base_prices[t]
            for s in snaps:
                if t in s.get("prices", {}):
                    xs.append(s["date"])
                    ys.append((s["prices"][t] - base) / base * 100)
            if len(xs) < 2:
                continue
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", name=t,
                line=dict(color=palette[i % len(palette)], width=1.6),
                hovertemplate=f"<b>{t}</b><br>%{{x}}<br>%{{y:+.2f}}%<extra></extra>",
            ))

        fig.add_hline(y=0, line=dict(color="#7385b8", width=1, dash="dot"))
        fig.update_layout(
            height=380, margin=dict(l=10, r=10, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0f1732",
            xaxis=dict(gridcolor="#1e2d54", tickfont=dict(color="#a8b4d8")),
            yaxis=dict(gridcolor="#1e2d54", tickfont=dict(color="#a8b4d8"),
                        ticksuffix="%"),
            legend=dict(orientation="h", yanchor="top", y=-0.12,
                          font=dict(color="#a8b4d8", size=11)),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ────────────────────────────────────────────────────────────────────
# AI RISK ANALYSIS
# ────────────────────────────────────────────────────────────────────

def _render_risk_analysis(state: dict) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown("### Portfolio risk analysis (Gemini)")
        with c2:
            run = st.button("✦ Analyse with Gemini", use_container_width=True, key="risk_btn")
        st.caption("Sends current portfolio + market context to Gemini with Google Search "
                    "grounding. Requires Gemini key (Settings) and live quotes.")

        if run:
            priced = [h for h in state.get("holdings", []) if safe_num(h.get("lastPrice"), 0) > 0]
            if not priced:
                st.error("Fetch quotes first — need live prices to analyse.")
            else:
                with st.spinner("Asking Gemini to analyse against current conditions…"):
                    try:
                        result = ai.analyse_portfolio(state)
                        st.session_state.last_risk_analysis = result
                        st.success("✓ Analysis complete")
                    except Exception as e:
                        st.error(f"Error: {e}")

        if "last_risk_analysis" in st.session_state:
            st.markdown(
                f"<div style='background:#0f1732;border:1px solid #2d3a6b;border-left:3px solid #f3b74f;"
                f"border-radius:10px;padding:14px;white-space:pre-wrap;line-height:1.7;font-size:14px;'>"
                f"{st.session_state.last_risk_analysis}</div>",
                unsafe_allow_html=True,
            )


# ────────────────────────────────────────────────────────────────────
# TRADE LOG
# ────────────────────────────────────────────────────────────────────

def _render_trade_log(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### Trade log")
        trades = [t for t in state.get("tradeLog", []) if t.get("action") != "INIT"][:100]
        if not trades:
            st.caption("No trades yet."); return
        df = pd.DataFrame([{
            "When": datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M"),
            "Action": t["action"],
            "Ticker": t["ticker"],
            "USD": to_usd(t["tradeUSD"]) if isinstance(t.get("tradeUSD"), (int, float)) else "—",
            "Shares": f"{t['shares']:.4f}" if isinstance(t.get("shares"), (int, float)) else "—",
            "Price": f"${t['price']:.2f}" if t.get("price") else "—",
        } for t in trades])
        st.dataframe(df, hide_index=True, use_container_width=True)


# ────────────────────────────────────────────────────────────────────
# REBALANCE LOG with DIFFS
# ────────────────────────────────────────────────────────────────────

def _compute_diff(current: dict, previous: dict | None) -> dict | None:
    """Return added/removed/changed lists between consecutive rebalances."""
    if not previous:
        return None
    prev_map = {p["ticker"]: p["weight"] for p in previous.get("picks", [])}
    cur_map  = {p["ticker"]: p["weight"] for p in current.get("picks", [])}
    added = [{"ticker": t, "weight": w} for t, w in cur_map.items() if t not in prev_map]
    removed = [{"ticker": t, "weight": w} for t, w in prev_map.items() if t not in cur_map]
    changed = [{"ticker": t, "fromWt": prev_map[t], "toWt": w}
               for t, w in cur_map.items()
               if t in prev_map and abs(w - prev_map[t]) > 0.005]
    return {"added": added, "removed": removed, "changed": changed}


def _render_rebalance_log(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### Rebalance log")
        log = state.get("rebalanceLog", [])
        if not log:
            st.caption("No rebalances yet."); return

        for i, r in enumerate(log[:20]):
            diff = _compute_diff(r, log[i+1] if i+1 < len(log) else None)
            date = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            with st.expander(f"{date.strftime('%d %b %Y')} · "
                              f"{r['positionCount']} positions · NAV {to_usd(r['navAtRebalance'])}",
                              expanded=(i == 0)):
                if diff:
                    chips = []
                    for p in diff["added"]:
                        chips.append(f"<span class='pill pill-good'>+ {p['ticker']} {p['weight']*100:.1f}%</span>")
                    for p in diff["removed"]:
                        chips.append(f"<span class='pill pill-bad'>− {p['ticker']} {p['weight']*100:.1f}%</span>")
                    for p in diff["changed"]:
                        chips.append(
                            f"<span class='pill pill-warn'>Δ {p['ticker']} "
                            f"{p['fromWt']*100:.1f}→{p['toWt']*100:.1f}%</span>"
                        )
                    if chips:
                        st.markdown(" ".join(chips), unsafe_allow_html=True)
                    else:
                        st.caption("No structural change vs previous rebalance.")
                else:
                    st.caption("Initial rebalance — no prior to compare.")

                df = pd.DataFrame([{
                    "Ticker": p["ticker"], "Name": p.get("name", ""),
                    "Weight": f"{p['weight']*100:.1f}%",
                    "Why": p.get("why", ""),
                } for p in r.get("picks", [])])
                st.dataframe(df, hide_index=True, use_container_width=True)


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────

def render() -> None:
    state = get_state()
    _render_nav_chart(state)
    _render_component_chart(state)
    _render_risk_analysis(state)
    c1, c2 = st.columns(2)
    with c1: _render_trade_log(state)
    with c2: _render_rebalance_log(state)
