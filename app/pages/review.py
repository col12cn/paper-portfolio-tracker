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
                    f"<div style='text-align:right;color:var(--muted);"
                    f"font-family:var(--font-mono);font-size:11px;letter-spacing:0.04em;'>"
                    f"{val_history[0]['date']} → {val_history[-1]['date']}</div>",
                    unsafe_allow_html=True,
                )

        if len(val_history) < 2:
            st.info("Not enough data — fetch quotes a few times to start tracking NAV.")
            return

        xs = [v["date"] for v in val_history]
        ys = [v["portfolioValueUSD"] for v in val_history]
        start_cap = safe_num(state["settings"].get("startingCapital"), 1000)

        # Y-range that focuses on actual variation (not 0-to-NAV)
        all_vals = ys + [start_cap]
        y_min, y_max = min(all_vals), max(all_vals)
        spread = max(y_max - y_min, y_max * 0.02)
        y_range = [y_min - spread * 0.20, y_max + spread * 0.20]

        colour = "#00C896" if ys[-1] >= start_cap else "#FF4757"
        rgb = "0,200,150" if ys[-1] >= start_cap else "255,71,87"

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color=colour, width=2.5, shape="spline", smoothing=0.4),
            fill="tozeroy", fillcolor=f"rgba({rgb},0.12)",
            hovertemplate="<b>%{x}</b><br>NAV: $%{y:,.2f}<extra></extra>",
            name="NAV",
        ))
        fig.add_hline(
            y=start_cap, line=dict(color="#3a3a3a", width=1, dash="dash"),
            annotation_text=f"Start  {to_usd(start_cap)}",
            annotation_position="top right",
            annotation_font=dict(color="#888", size=10, family="Menlo, Consolas, monospace"),
        )
        fig.update_layout(
            height=320, margin=dict(l=10, r=10, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                gridcolor="#1a1a1a",
                tickfont=dict(color="#888", family="Menlo, Consolas, monospace", size=10),
                showline=False, zeroline=False,
            ),
            yaxis=dict(
                range=y_range,
                gridcolor="#1a1a1a",
                tickfont=dict(color="#888", family="Menlo, Consolas, monospace", size=10),
                tickformat="$,.0f",
                showline=False, zeroline=False,
            ),
            showlegend=False, hovermode="x",
            hoverlabel=dict(
                bgcolor="#161616", bordercolor="#FFB800",
                font=dict(family="Menlo, Consolas, monospace", size=11, color="#f5f5f5"),
            ),
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
        # Bloomberg-modern palette: amber + cyan as anchors, then varied hues
        palette = ["#FFB800", "#00B8D4", "#00C896", "#FF4757", "#A78BFA",
                   "#F472B6", "#34D399", "#60A5FA", "#FB923C", "#E879F9"]
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
                line=dict(color=palette[i % len(palette)], width=1.5,
                           shape="spline", smoothing=0.3),
                hovertemplate=f"<b>{t}</b><br>%{{x}}<br>%{{y:+.2f}}%<extra></extra>",
            ))

        fig.add_hline(y=0, line=dict(color="#3a3a3a", width=1, dash="dot"))
        fig.update_layout(
            height=380, margin=dict(l=10, r=10, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                gridcolor="#1a1a1a",
                tickfont=dict(color="#888", family="Menlo, Consolas, monospace", size=10),
                showline=False, zeroline=False,
            ),
            yaxis=dict(
                gridcolor="#1a1a1a",
                tickfont=dict(color="#888", family="Menlo, Consolas, monospace", size=10),
                ticksuffix="%",
                showline=False, zeroline=False,
            ),
            legend=dict(
                orientation="h", yanchor="top", y=-0.12,
                font=dict(color="#b8b8b8", size=10, family="Menlo, Consolas, monospace"),
            ),
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor="#161616", bordercolor="#FFB800",
                font=dict(family="Menlo, Consolas, monospace", size=11, color="#f5f5f5"),
            ),
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
                f"<div class='insight insight-warn' style='margin-top:8px;'>"
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
