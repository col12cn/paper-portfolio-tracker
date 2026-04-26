"""Review tab: NAV chart, component price chart, logs, AI risk analysis."""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from app.state import get_state, commit, get_portfolio_value
from app.helpers import safe_num, to_usd, signed_pct, fmt_rel_time, now_iso
from app import ai


# ────────────────────────────────────────────────────────────────────
# NAV CHART
# ────────────────────────────────────────────────────────────────────

def _render_nav_chart(state: dict) -> None:
    val_history = [v for v in state.get("valuation", [])
                   if safe_num(v.get("portfolioValueUSD"), 0) > 0]
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.markdown("### Portfolio NAV")
        with c2:
            show_spy = st.toggle("vs SPY", value=True, key="nav_show_spy",
                                    help="Overlay SPY rebased to your starting NAV.")
        with c3:
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

        # Optionally fetch SPY rebased to portfolio's starting capital
        spy_df = None
        if show_spy:
            from app import benchmarks
            try:
                spy_df = benchmarks.benchmark_aligned_to_dates("SPY", xs, baseline=ys[0])
            except Exception:
                spy_df = None

        # Y-range that focuses on actual variation across BOTH series
        all_vals = ys + [start_cap]
        if spy_df is not None and not spy_df.empty:
            all_vals = all_vals + spy_df["value"].tolist()
        y_min, y_max = min(all_vals), max(all_vals)
        spread = max(y_max - y_min, y_max * 0.02)
        y_range = [y_min - spread * 0.20, y_max + spread * 0.20]

        colour = "#00C896" if ys[-1] >= start_cap else "#FF4757"
        rgb = "0,200,150" if ys[-1] >= start_cap else "255,71,87"

        fig = go.Figure()

        # Main NAV trace with subtle fill
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", name="Your NAV",
            line=dict(color=colour, width=2.5, shape="spline", smoothing=0.4),
            fill="tozeroy", fillcolor=f"rgba({rgb},0.10)",
            hovertemplate="<b>%{x}</b><br>NAV: $%{y:,.2f}<extra></extra>",
        ))

        # SPY overlay (no fill, dashed cyan to distinguish)
        if spy_df is not None and not spy_df.empty:
            fig.add_trace(go.Scatter(
                x=spy_df["date"].tolist(), y=spy_df["value"].tolist(),
                mode="lines", name="SPY (rebased)",
                line=dict(color="#00B8D4", width=1.8, dash="dash"),
                hovertemplate="<b>%{x}</b><br>SPY: $%{y:,.2f}<extra></extra>",
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
            showlegend=show_spy and spy_df is not None,
            legend=dict(
                orientation="h", yanchor="top", y=1.10,
                xanchor="right", x=1,
                font=dict(color="#b8b8b8", size=10, family="Menlo, Consolas, monospace"),
                bgcolor="rgba(0,0,0,0)",
            ),
            hovermode="x",
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

    holdings_tickers = {h["ticker"] for h in state.get("holdings", [])}
    historical_tickers = {t["ticker"] for t in trade_log
                           if t.get("ticker") and t["ticker"] != "ALL"}
    all_tickers = sorted(holdings_tickers | historical_tickers)

    # Bloomberg-modern palette for multi-ticker mode
    PALETTE = ["#FFB800", "#00B8D4", "#A78BFA", "#34D399", "#FB923C",
               "#F472B6", "#60A5FA", "#E879F9", "#FBBF24", "#10B981"]

    with st.container(border=True):
        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown("### Component price · % from cost basis")

        if not all_tickers:
            st.info("No positions yet — add one to see its price track.")
            return

        with c2:
            default_tickers = []
            if state.get("holdings"):
                first_held = state["holdings"][0]["ticker"]
                if first_held in all_tickers:
                    default_tickers = [first_held]
            selected = st.multiselect(
                "Tickers", all_tickers,
                default=default_tickers,
                key="component_chart_tickers",
                label_visibility="collapsed",
                placeholder="Select one or more tickers to compare…",
            )

        if not selected:
            st.info("Select one or more tickers above to see their price tracks.")
            return

        if len(snaps) < 2:
            st.info("Need at least 2 price snapshots — fetch quotes a couple of times.")
            return

        is_single = len(selected) == 1

        # ─── Build per-ticker datasets ─────────────────────────────────
        datasets = []
        for i, ticker in enumerate(selected):
            entry_date, entry_price = _get_ticker_basis(state, ticker)
            if not entry_date or not entry_price:
                continue

            xs, ys = [], []
            for s in snaps:
                if s["date"] >= entry_date and ticker in s.get("prices", {}):
                    xs.append(s["date"])
                    ys.append((s["prices"][ticker] - entry_price) / entry_price * 100)
            if len(xs) < 2:
                continue

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
                    entry_meta.append([usd, price, ticker])
                else:
                    exit_xs.append(trade_date); exit_ys.append(pct)
                    exit_meta.append([usd, price, action, ticker])

            datasets.append({
                "ticker": ticker,
                "entry_date": entry_date,
                "entry_price": entry_price,
                "cur_price": entry_price * (1 + ys[-1] / 100),
                "cur_pct": ys[-1],
                "xs": xs, "ys": ys,
                "entry_xs": entry_xs, "entry_ys": entry_ys, "entry_meta": entry_meta,
                "exit_xs": exit_xs, "exit_ys": exit_ys, "exit_meta": exit_meta,
            })

        if not datasets:
            st.info("No usable price history for the selected tickers yet.")
            return

        # Assign colours: semantic green/red for single, palette for multi
        for i, d in enumerate(datasets):
            if is_single:
                d["color"] = "#00C896" if d["cur_pct"] >= 0 else "#FF4757"
                d["rgb"] = "0,200,150" if d["cur_pct"] >= 0 else "255,71,87"
            else:
                d["color"] = PALETTE[i % len(PALETTE)]
                d["rgb"] = None  # no fill in multi mode

        # ─── Summary strip ─────────────────────────────────────────────
        if is_single:
            d = datasets[0]
            cur_class = "good" if d["cur_pct"] >= 0 else "bad"
            st.markdown(
                f"<div style='display:flex;gap:32px;margin:6px 0 12px 0;align-items:baseline;flex-wrap:wrap;'>"
                f"<div><span class='label'>Cost basis</span> "
                f"<span class='mono' style='margin-left:8px;color:var(--text);font-weight:600;'>${d['entry_price']:,.2f}</span> "
                f"<span class='muted-text mono' style='font-size:11px;margin-left:6px;'>· {d['entry_date']}</span></div>"
                f"<div><span class='label'>Latest</span> "
                f"<span class='mono' style='margin-left:8px;color:var(--text);font-weight:600;'>${d['cur_price']:,.2f}</span></div>"
                f"<div><span class='label'>Δ</span> "
                f"<span class='mono {cur_class}' style='margin-left:8px;font-weight:600;font-size:14px;'>"
                f"{'+' if d['cur_pct'] >= 0 else ''}{d['cur_pct']:.2f}%</span></div>"
                f"<div><span class='label'>Trades</span> "
                f"<span class='mono' style='margin-left:8px;color:var(--text-2);'>"
                f"{len(d['entry_xs'])} buy · {len(d['exit_xs'])} sell</span></div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            # Multi-ticker: compact colour-dotted comparison cards
            strip = "<div style='display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 14px 0;'>"
            for d in datasets:
                cls = "good" if d["cur_pct"] >= 0 else "bad"
                sign = "+" if d["cur_pct"] >= 0 else ""
                strip += (
                    f"<div style='display:flex;align-items:center;gap:10px;"
                    f"padding:6px 12px;background:var(--bg-soft);"
                    f"border:1px solid var(--line);border-radius:4px;'>"
                    f"<span style='display:inline-block;width:10px;height:10px;"
                    f"border-radius:50%;background:{d['color']};'></span>"
                    f"<span class='mono' style='color:var(--text);font-weight:600;font-size:13px;'>{d['ticker']}</span>"
                    f"<span class='mono muted-text' style='font-size:11px;'>"
                    f"${d['entry_price']:,.2f} → ${d['cur_price']:,.2f}</span>"
                    f"<span class='mono {cls}' style='font-weight:600;font-size:13px;'>"
                    f"{sign}{d['cur_pct']:.2f}%</span>"
                    f"</div>"
                )
            strip += "</div>"
            st.markdown(strip, unsafe_allow_html=True)

        # ─── Build chart ───────────────────────────────────────────────
        fig = go.Figure()

        # Lines (with subtle fill in single mode only)
        for d in datasets:
            trace_kwargs = dict(
                x=d["xs"], y=d["ys"], mode="lines", name=d["ticker"],
                line=dict(color=d["color"], width=2, shape="spline", smoothing=0.3),
                hovertemplate=f"<b>{d['ticker']}</b><br>%{{x}}<br>%{{y:+.2f}}%<extra></extra>",
                showlegend=not is_single,  # legend = ticker names in multi; hidden in single
            )
            if is_single:
                trace_kwargs["fill"] = "tozeroy"
                trace_kwargs["fillcolor"] = f"rgba({d['rgb']},0.08)"
            fig.add_trace(go.Scatter(**trace_kwargs))

        # Cost basis at 0% (shared reference — each ticker has its own dollar basis,
        # but they all anchor to 0% on this chart)
        cb_label = (f"Cost basis  ${datasets[0]['entry_price']:,.2f}"
                    if is_single else "Cost basis (each ticker)")
        fig.add_hline(
            y=0, line=dict(color="#3a3a3a", width=1, dash="dot"),
            annotation_text=cb_label,
            annotation_position="bottom right",
            annotation_font=dict(color="#888", size=10, family="Menlo, Consolas, monospace"),
        )

        # Portfolio init vertical marker (shared) — split line + annotation
        # to avoid Plotly's mean-of-string-dates bug
        init_date = state["valuation"][0]["date"] if state.get("valuation") else None
        if init_date:
            x_min = min(d["xs"][0] for d in datasets)
            x_max = max(d["xs"][-1] for d in datasets)
            if x_min <= init_date <= x_max:
                init_label = "Portfolio init"
                if is_single and datasets[0]["entry_date"] == init_date:
                    init_label = "Init / entry"
                fig.add_vline(
                    x=init_date,
                    line=dict(color="#FFB800", width=1, dash="dash"),
                )
                fig.add_annotation(
                    x=init_date, y=1, yref="paper",
                    text=init_label, showarrow=False,
                    xanchor="left", yanchor="top",
                    xshift=4, yshift=-2,
                    font=dict(color="#FFB800", size=10,
                                family="Menlo, Consolas, monospace"),
                )

        # Trade markers — semantic green/red triangles in both modes (standard
        # financial-charting convention; ticker identity comes from hover)
        for d in datasets:
            if d["entry_xs"]:
                fig.add_trace(go.Scatter(
                    x=d["entry_xs"], y=d["entry_ys"], customdata=d["entry_meta"],
                    mode="markers", name="Buy",
                    marker=dict(symbol="triangle-up", size=14, color="#00C896",
                                  line=dict(color="#0a0a0a", width=1.5)),
                    hovertemplate=("<b>%{customdata[2]} BUY</b>  $%{customdata[0]:,.2f}<br>"
                                   "%{x}<br>"
                                   "Px $%{customdata[1]:,.2f}<br>"
                                   "%{y:+.2f}% from cost<extra></extra>"),
                    showlegend=is_single,  # avoid N "Buy" entries in multi mode
                ))
            if d["exit_xs"]:
                fig.add_trace(go.Scatter(
                    x=d["exit_xs"], y=d["exit_ys"], customdata=d["exit_meta"],
                    mode="markers", name="Sell",
                    marker=dict(symbol="triangle-down", size=14, color="#FF4757",
                                  line=dict(color="#0a0a0a", width=1.5)),
                    hovertemplate=("<b>%{customdata[3]} %{customdata[2]}</b>  $%{customdata[0]:,.2f}<br>"
                                   "%{x}<br>"
                                   "Px $%{customdata[1]:,.2f}<br>"
                                   "%{y:+.2f}% from cost<extra></extra>"),
                    showlegend=is_single,
                ))

        # ─── Y-axis range — explicit, always includes 0, handles negatives ─
        # Goal: line of sight on actual variation, with 0% (cost basis) always
        # visible and a minimum 5pp window so trivial moves don't look extreme.
        # Asymmetric padding (40% below / 60% above) leaves room for top labels.
        all_ys = [y for d in datasets for y in d["ys"]]
        data_min = min(all_ys + [0])    # always include the cost basis line
        data_max = max(all_ys + [0])
        data_spread = data_max - data_min
        target_spread = max(data_spread * 1.30, 5.0)
        extra = target_spread - data_spread
        y_range = [data_min - extra * 0.40, data_max + extra * 0.60]

        fig.update_layout(
            height=380, margin=dict(l=10, r=10, t=30, b=20),
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
# DECISION JOURNAL — trades + rationale + post-mortem notes
# ────────────────────────────────────────────────────────────────────

def _render_decision_journal(state: dict) -> None:
    """Show trades that have rationale, allow adding post-mortem reflections.

    Closes the learning loop: write thesis at trade time, add reflection later
    once you can see how it played out. Post-mortems stored on the trade itself
    as t['postMortems'] = [{'note': str, 'addedAt': iso}].
    """
    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Decision journal</span>"
            "<span class='muted-text mono' style='font-size:10px;margin-left:auto;'>"
            "thesis → reflection</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("Trades you took with a rationale. Add post-mortem notes weeks later "
                    "to see whether your thesis held up. This is how you learn.")

        # Find trades with non-trivial reasons (skip auto-generated rebalance/init notes)
        rationale_trades = []
        for t in state.get("tradeLog", []):
            if t.get("action") == "INIT":
                continue
            reason = (t.get("reason") or "").strip()
            # Filter out auto-generated minimal reasons
            if not reason or reason in ("Manual buy", "Manual sell"):
                continue
            rationale_trades.append(t)

        if not rationale_trades:
            st.markdown(
                "<div class='empty-state' style='padding:32px;'>"
                "<div class='empty-state-title'>No journaled trades yet</div>"
                "<div class='empty-state-hint'>Add a 'Why?' note when you trade on the Trade tab "
                "and your decisions will appear here.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        # Display newest first
        for i, t in enumerate(rationale_trades[:25]):
            ts = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
            date_str = ts.strftime("%Y-%m-%d")
            rel = fmt_rel_time(t["timestamp"])
            usd = safe_num(t.get("tradeUSD"), 0)
            price = t.get("price")
            action_class = "pill-good" if t["action"] == "BUY" else "pill-bad"

            postmortems = t.get("postMortems", []) or []
            pm_count = len(postmortems)
            header_label = (f"{date_str} · {t['action']} {t['ticker']} · {to_usd(usd)}"
                              + (f"  ({pm_count} reflection{'s' if pm_count != 1 else ''})"
                                 if pm_count else ""))

            with st.expander(header_label, expanded=(i == 0 and pm_count == 0)):
                # Trade card header
                price_str = f"@ ${price:.2f}" if price else "(no price)"
                st.markdown(
                    f"<div style='display:flex;gap:14px;align-items:center;margin-bottom:10px;'>"
                    f"<span class='pill {action_class}'>{t['action']}</span>"
                    f"<span class='mono' style='font-weight:600;color:var(--text);'>{t['ticker']}</span>"
                    f"<span class='mono'>{to_usd(usd)} {price_str}</span>"
                    f"<span class='muted-text mono' style='font-size:11px;margin-left:auto;'>{rel}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Original rationale
                st.markdown(
                    f"<div class='insight insight-cool' style='margin-bottom:12px;'>"
                    f"<div class='label' style='margin-bottom:6px;'>Original thesis</div>"
                    f"{t['reason']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Existing post-mortems
                for pm in postmortems:
                    pm_rel = fmt_rel_time(pm.get("addedAt", ""))
                    st.markdown(
                        f"<div class='insight' style='margin-bottom:8px;border-left-color:var(--warn);'>"
                        f"<div class='label' style='margin-bottom:6px;'>"
                        f"Reflection · <span class='muted-text mono' style='text-transform:none;'>{pm_rel}</span>"
                        f"</div>{pm.get('note','')}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                # Add a new reflection
                pm_key = f"pm_input_{t['timestamp']}"
                new_note = st.text_area(
                    "Add a reflection — how is this position playing out vs your thesis?",
                    key=pm_key, height=70,
                    placeholder="e.g. NVDA earnings beat as expected; raising target. Or: thesis broken — sell.",
                )
                if st.button("Save reflection", key=f"pm_save_{t['timestamp']}"):
                    if new_note.strip():
                        # Find the trade in the live state and append
                        for live_t in state["tradeLog"]:
                            if live_t.get("timestamp") == t.get("timestamp"):
                                live_t.setdefault("postMortems", []).append({
                                    "note": new_note.strip(),
                                    "addedAt": now_iso(),
                                })
                                break
                        commit()
                        st.success("✓ Saved")
                        st.rerun()
                    else:
                        st.error("Write something first.")

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
            "Why": (t.get("reason") or "")[:60],
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
    _render_decision_journal(state)
    c1, c2 = st.columns(2)
    with c1: _render_trade_log(state)
    with c2: _render_rebalance_log(state)
