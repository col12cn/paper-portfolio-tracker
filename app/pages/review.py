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
# COMPONENT PRICE CHART (single ticker via selector, with trade markers)
# ────────────────────────────────────────────────────────────────────

def _get_ticker_basis(state: dict, ticker: str) -> tuple:
    """Find cost-basis date and price for a ticker.

    Lookup priority:
      1. First BUY trade with explicit price → use that
      2. First BUY trade without price → first snapshot at/after trade date
      3. No BUY trade (initial-basket position) → portfolio init date + first snapshot
      4. Last resort → first observed snapshot

    Returns (date_str, price) or (None, None) if no usable data.
    """
    snaps = state.get("priceSnap", [])
    trade_log = state.get("tradeLog", [])
    init_date = state["valuation"][0]["date"] if state.get("valuation") else None

    buys = sorted(
        [t for t in trade_log if t.get("ticker") == ticker and t.get("action") == "BUY"],
        key=lambda t: t.get("timestamp", ""),
    )

    if buys:
        first_buy_date = buys[0]["timestamp"][:10]
        price = safe_num(buys[0].get("price"), 0)
        if price <= 0:
            for s in snaps:
                if s["date"] >= first_buy_date and ticker in s.get("prices", {}):
                    price = s["prices"][ticker]; break
        if price > 0:
            return first_buy_date, price

    if init_date:
        for s in snaps:
            if ticker in s.get("prices", {}) and s["date"] >= init_date:
                return init_date, s["prices"][ticker]

    for s in snaps:
        if ticker in s.get("prices", {}):
            return s["date"], s["prices"][ticker]

    return None, None


def _trade_marker_pct(state: dict, ticker: str, trade: dict,
                       entry_price: float) -> tuple:
    """Return (pct_change_from_entry, price_at_trade) for one trade marker.

    Prefers the trade's recorded price; falls back to nearest snapshot.
    Returns (None, None) if no usable price available.
    """
    price = safe_num(trade.get("price"), 0)
    if price <= 0:
        trade_date = trade["timestamp"][:10]
        for s in state.get("priceSnap", []):
            if s["date"] >= trade_date and ticker in s.get("prices", {}):
                price = s["prices"][ticker]; break
    if price > 0 and entry_price > 0:
        return ((price - entry_price) / entry_price) * 100, price
    return None, None


def _render_component_chart(state: dict) -> None:
    snaps = state.get("priceSnap", [])
    trade_log = state.get("tradeLog", [])

    # Tickers ever held (current holdings ∪ tickers in trade log, including closed positions)
    holdings_tickers = {h["ticker"] for h in state.get("holdings", [])}
    historical_tickers = {t["ticker"] for t in trade_log
                           if t.get("ticker") and t["ticker"] != "ALL"}
    all_tickers = sorted(holdings_tickers | historical_tickers)

    with st.container(border=True):
        c1, c2 = st.columns([2, 2])
        with c1:
            st.markdown("### Component price · % from cost basis")

        if not all_tickers:
            st.info("No positions yet — add one to see its price track.")
            return

        with c2:
            # Default selection: first current holding, else first ticker overall
            default_idx = 0
            if state.get("holdings"):
                first_held = state["holdings"][0]["ticker"]
                if first_held in all_tickers:
                    default_idx = all_tickers.index(first_held)
            ticker = st.selectbox("Ticker", all_tickers,
                                    index=default_idx,
                                    key="component_chart_ticker",
                                    label_visibility="collapsed")

        if len(snaps) < 2:
            st.info("Need at least 2 price snapshots — fetch quotes a couple of times to start the chart.")
            return

        # Cost basis
        entry_date, entry_price = _get_ticker_basis(state, ticker)
        if not entry_date or not entry_price:
            st.info(f"No cost basis available for {ticker} — fetch quotes after adding it.")
            return

        # Build the price line: snapshots from entry forward
        xs, ys = [], []
        for s in snaps:
            if s["date"] >= entry_date and ticker in s.get("prices", {}):
                xs.append(s["date"])
                ys.append((s["prices"][ticker] - entry_price) / entry_price * 100)
        if len(xs) < 2:
            st.info(f"Not enough price data for {ticker} since {entry_date}. Fetch quotes again.")
            return

        # Trade markers
        ticker_trades = sorted(
            [t for t in trade_log if t.get("ticker") == ticker],
            key=lambda t: t.get("timestamp", ""),
        )
        entry_xs, entry_ys, entry_meta = [], [], []
        exit_xs, exit_ys, exit_meta = [], [], []
        for t in ticker_trades:
            action = t.get("action")
            if action not in ("BUY", "SELL", "CLOSE"):
                continue
            pct, price = _trade_marker_pct(state, ticker, t, entry_price)
            if pct is None:
                continue
            trade_date = t["timestamp"][:10]
            usd = safe_num(t.get("tradeUSD"), 0)
            if action == "BUY":
                entry_xs.append(trade_date); entry_ys.append(pct)
                entry_meta.append([usd, price])
            else:
                exit_xs.append(trade_date); exit_ys.append(pct)
                exit_meta.append([usd, price, action])

        # Portfolio init date
        init_date = state["valuation"][0]["date"] if state.get("valuation") else None

        # Position summary strip above the chart
        cur_pct = ys[-1]
        cur_price = entry_price * (1 + cur_pct / 100)
        cur_class = "good" if cur_pct >= 0 else "bad"
        st.markdown(
            f"<div style='display:flex;gap:32px;margin:6px 0 12px 0;align-items:baseline;'>"
            f"<div><span class='label'>Cost basis</span> "
            f"<span class='mono' style='margin-left:8px;color:var(--text);font-weight:600;'>${entry_price:,.2f}</span> "
            f"<span class='muted-text mono' style='font-size:11px;margin-left:6px;'>· {entry_date}</span></div>"
            f"<div><span class='label'>Latest</span> "
            f"<span class='mono' style='margin-left:8px;color:var(--text);font-weight:600;'>${cur_price:,.2f}</span></div>"
            f"<div><span class='label'>Δ</span> "
            f"<span class='mono {cur_class}' style='margin-left:8px;font-weight:600;font-size:14px;'>"
            f"{'+' if cur_pct >= 0 else ''}{cur_pct:.2f}%</span></div>"
            f"<div><span class='label'>Trades</span> "
            f"<span class='mono' style='margin-left:8px;color:var(--text-2);'>"
            f"{len(entry_xs)} buy · {len(exit_xs)} sell</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Build the chart
        line_color = "#00C896" if cur_pct >= 0 else "#FF4757"
        rgb = "0,200,150" if cur_pct >= 0 else "255,71,87"

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", name=ticker,
            line=dict(color=line_color, width=2, shape="spline", smoothing=0.3),
            fill="tozeroy", fillcolor=f"rgba({rgb},0.08)",
            hovertemplate=f"<b>{ticker}</b><br>%{{x}}<br>%{{y:+.2f}}%<extra></extra>",
            showlegend=False,
        ))

        # Cost basis at 0%
        fig.add_hline(
            y=0, line=dict(color="#3a3a3a", width=1, dash="dot"),
            annotation_text=f"Cost basis  ${entry_price:,.2f}",
            annotation_position="bottom right",
            annotation_font=dict(color="#888", size=10, family="Menlo, Consolas, monospace"),
        )

        # Portfolio init vertical marker
        if init_date and xs[0] <= init_date <= xs[-1]:
            init_label = "Portfolio init" if init_date != entry_date else "Init / entry"
            fig.add_vline(
                x=init_date, line=dict(color="#FFB800", width=1, dash="dash"),
                annotation_text=init_label, annotation_position="top right",
                annotation_font=dict(color="#FFB800", size=10, family="Menlo, Consolas, monospace"),
            )

        # Entry markers
        if entry_xs:
            fig.add_trace(go.Scatter(
                x=entry_xs, y=entry_ys, customdata=entry_meta,
                mode="markers", name="Buy",
                marker=dict(symbol="triangle-up", size=14, color="#00C896",
                              line=dict(color="#0a0a0a", width=1.5)),
                hovertemplate=("<b>BUY</b>  $%{customdata[0]:,.2f}<br>"
                               "%{x}<br>"
                               "Px $%{customdata[1]:,.2f}<br>"
                               "%{y:+.2f}% from cost<extra></extra>"),
            ))

        # Exit markers
        if exit_xs:
            fig.add_trace(go.Scatter(
                x=exit_xs, y=exit_ys, customdata=exit_meta,
                mode="markers", name="Sell",
                marker=dict(symbol="triangle-down", size=14, color="#FF4757",
                              line=dict(color="#0a0a0a", width=1.5)),
                hovertemplate=("<b>%{customdata[2]}</b>  $%{customdata[0]:,.2f}<br>"
                               "%{x}<br>"
                               "Px $%{customdata[1]:,.2f}<br>"
                               "%{y:+.2f}% from cost<extra></extra>"),
            ))

        fig.update_layout(
            height=380, margin=dict(l=10, r=10, t=30, b=20),
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
                orientation="h", yanchor="top", y=1.10,
                xanchor="right", x=1,
                font=dict(color="#b8b8b8", size=10, family="Menlo, Consolas, monospace"),
                bgcolor="rgba(0,0,0,0)",
            ),
            hovermode="closest",
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
