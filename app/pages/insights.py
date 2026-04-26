"""Insights tab — institutional-grade portfolio analytics.

Sections:
  1. Headline metrics (concentration, # positions, top weight, vs benchmark return)
  2. Top contributors / detractors to portfolio P&L
  3. Sector exposure (donut chart + table)
  4. Geographic exposure (table)
  5. Concentration analysis (HHI, top-N weight, max-weight check)
  6. Rolling beta to SPY (if enough data)

Goal: help the user *understand* their portfolio, not just track it.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import math

from app.state import get_state, get_portfolio_value
from app.helpers import safe_num, to_usd, signed_pct
from app import sectors, benchmarks


# Color palette for charts (consistent with the rest of the app)
PALETTE = ["#FFB800", "#00B8D4", "#A78BFA", "#34D399", "#FB923C",
           "#F472B6", "#60A5FA", "#E879F9", "#FBBF24", "#10B981",
           "#F87171", "#818CF8"]


# ────────────────────────────────────────────────────────────────────
# HEADLINE METRICS STRIP
# ────────────────────────────────────────────────────────────────────

def _headline_metrics(state: dict, classified: list[dict], nav: float) -> None:
    """Top strip — the at-a-glance health check."""
    if not classified:
        return

    # Concentration: HHI = sum of squared weights (×10000 for readability)
    weights = [safe_num(h.get("currentValueUSD"), 0) / nav for h in classified if nav > 0]
    hhi = sum(w * w for w in weights) * 10000
    top_weight_pct = max(weights) * 100 if weights else 0
    top_3_pct = sum(sorted(weights, reverse=True)[:3]) * 100

    # Effective number of positions: 1 / sum(w^2) — interpretable as "how many
    # equally-weighted positions does this concentration equate to"
    n_eff = 1 / sum(w * w for w in weights) if weights else 0

    # Compare to SPY over portfolio life
    val_history = state.get("valuation", [])
    spy_return = None
    pf_return = None
    if len(val_history) >= 2:
        first_nav = safe_num(val_history[0].get("portfolioValueUSD"), nav)
        if first_nav > 0:
            pf_return = (nav - first_nav) / first_nav * 100
        days_alive = max(1, len(val_history))
        spy_return = benchmarks.benchmark_total_return_pct("SPY", days=days_alive)

    cols = st.columns(5)
    cols[0].metric("Positions", str(len(classified)))
    cols[1].metric("Top weight", f"{top_weight_pct:.1f}%",
                    delta=f"of NAV", delta_color="off")
    cols[2].metric("Top-3 weight", f"{top_3_pct:.1f}%",
                    delta="concentration risk" if top_3_pct > 50 else "diversified",
                    delta_color="inverse" if top_3_pct > 50 else "off")
    cols[3].metric("HHI", f"{hhi:.0f}",
                    delta=f"≈{n_eff:.1f} effective", delta_color="off",
                    help="Herfindahl-Hirschman Index. <1500 = competitive, 1500-2500 = moderate, >2500 = highly concentrated.")
    if spy_return is not None and pf_return is not None:
        delta_vs_spy = pf_return - spy_return
        cols[4].metric("vs SPY", f"{signed_pct(delta_vs_spy)}",
                        delta=f"You {signed_pct(pf_return)} · SPY {signed_pct(spy_return)}",
                        delta_color="normal" if delta_vs_spy >= 0 else "inverse")
    else:
        cols[4].metric("vs SPY", "—", delta="needs more data", delta_color="off")


# ────────────────────────────────────────────────────────────────────
# CONTRIBUTORS / DETRACTORS
# ────────────────────────────────────────────────────────────────────

def _contributors(state: dict, classified: list[dict], nav: float) -> None:
    with st.container(border=True):
        st.markdown("### Performance attribution")
        st.caption("How much each position has added to or subtracted from your NAV "
                    "since you bought it. Sorted by dollar P&L.")

        rows = []
        for h in classified:
            initial = safe_num(h.get("initialUSD"), 0)
            current = safe_num(h.get("currentValueUSD"), 0)
            pl_usd = current - initial
            pl_pct = (pl_usd / initial * 100) if initial > 0 else 0
            wt = (current / nav * 100) if nav > 0 else 0
            # Contribution to portfolio return = position $ P/L / portfolio starting $
            start_cap = safe_num(state["settings"].get("startingCapital"), 1000)
            contrib_to_nav = (pl_usd / start_cap * 100) if start_cap > 0 else 0
            rows.append({
                "Ticker":   h["ticker"],
                "Sector":   h.get("sector", "Unknown"),
                "Weight":   f"{wt:.2f}%",
                "Cost":     to_usd(initial),
                "Value":    to_usd(current),
                "$ P/L":    to_usd(pl_usd),
                "% P/L":    signed_pct(pl_pct),
                "Contrib":  signed_pct(contrib_to_nav),
                "_pl_usd":  pl_usd,
            })
        if not rows:
            st.caption("No positions to attribute.")
            return

        rows.sort(key=lambda r: r["_pl_usd"], reverse=True)
        df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
        st.dataframe(df, hide_index=True, use_container_width=True)

        # Top + bottom callouts
        gainers = [r for r in rows if r["_pl_usd"] > 0]
        losers  = [r for r in rows if r["_pl_usd"] < 0]
        c1, c2 = st.columns(2)
        with c1:
            if gainers:
                top = gainers[0]
                st.markdown(
                    f"<div class='insight insight-good'>"
                    f"<div class='label' style='margin-bottom:4px;'>Top contributor</div>"
                    f"<span class='mono' style='font-size:14px;font-weight:600;'>{top['Ticker']}</span>"
                    f" &nbsp;<span class='mono good' style='font-weight:600;'>{top['$ P/L']}</span>"
                    f" &nbsp;<span class='muted-text' style='font-size:11px;'>"
                    f"({top['Contrib']} of NAV · {top['Sector']})</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No winners yet.")
        with c2:
            if losers:
                bot = losers[-1]
                st.markdown(
                    f"<div class='insight' style='border-left-color:var(--bad);'>"
                    f"<div class='label' style='margin-bottom:4px;'>Top detractor</div>"
                    f"<span class='mono' style='font-size:14px;font-weight:600;'>{bot['Ticker']}</span>"
                    f" &nbsp;<span class='mono bad' style='font-weight:600;'>{bot['$ P/L']}</span>"
                    f" &nbsp;<span class='muted-text' style='font-size:11px;'>"
                    f"({bot['Contrib']} of NAV · {bot['Sector']})</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No losers yet.")


# ────────────────────────────────────────────────────────────────────
# SECTOR EXPOSURE — donut chart + table
# ────────────────────────────────────────────────────────────────────

def _sector_exposure(state: dict, classified: list[dict], nav: float) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown("### Sector exposure")
            st.caption("Where your capital is concentrated by sector. "
                        "Look for unintentional bets — if you hold three names "
                        "in the same sector, you're triple-exposed.")
        with c2:
            # Aggregate by sector
            sector_totals: dict[str, float] = {}
            for h in classified:
                sec = h.get("sector", "Unknown")
                sector_totals[sec] = sector_totals.get(sec, 0) + safe_num(h.get("currentValueUSD"), 0)

            # Add cash
            cash = safe_num(state.get("cashUSD"), 0)
            if cash > 0:
                sector_totals["Cash"] = cash

            if not sector_totals:
                st.caption("No data."); return

            # Sort by value descending
            sorted_sectors = sorted(sector_totals.items(), key=lambda x: -x[1])
            labels = [s[0] for s in sorted_sectors]
            values = [s[1] for s in sorted_sectors]
            total = sum(values)

            colors = []
            for label in labels:
                if label == "Cash":
                    colors.append("#444444")  # neutral grey for cash
                elif label == "Unknown":
                    colors.append("#666666")
                else:
                    colors.append(PALETTE[len(colors) % len(PALETTE)])

            fig = go.Figure(data=[go.Pie(
                labels=labels, values=values, hole=0.55,
                marker=dict(colors=colors, line=dict(color="#0a0a0a", width=2)),
                textfont=dict(family="Menlo, Consolas, monospace", size=11, color="#f5f5f5"),
                texttemplate="%{label}<br>%{percent}",
                textposition="outside",
                hovertemplate="<b>%{label}</b><br>$%{value:,.2f}<br>%{percent}<extra></extra>",
                sort=False,
            )])
            fig.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                annotations=[dict(
                    text=f"<b>{to_usd(total)}</b><br><span style='font-size:10px;color:#888;'>TOTAL</span>",
                    x=0.5, y=0.5, font=dict(size=14, color="#f5f5f5",
                                              family="Menlo, Consolas, monospace"),
                    showarrow=False,
                )],
                hoverlabel=dict(bgcolor="#161616", bordercolor="#FFB800",
                                  font=dict(family="Menlo, Consolas, monospace",
                                              size=11, color="#f5f5f5")),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ────────────────────────────────────────────────────────────────────
# GEOGRAPHIC EXPOSURE
# ────────────────────────────────────────────────────────────────────

def _geographic_exposure(state: dict, classified: list[dict], nav: float) -> None:
    with st.container(border=True):
        st.markdown("### Geographic exposure")
        st.caption("Country exposure based on the listing market and ETF mapping. "
                    "ADRs are tagged to their underlying market when known.")

        country_totals: dict[str, float] = {}
        for h in classified:
            c = h.get("country", "Unknown")
            country_totals[c] = country_totals.get(c, 0) + safe_num(h.get("currentValueUSD"), 0)

        if not country_totals:
            st.caption("No data."); return

        rows = []
        for country, value in sorted(country_totals.items(), key=lambda x: -x[1]):
            wt = (value / nav * 100) if nav > 0 else 0
            rows.append({"Country": country, "Value": to_usd(value), "Weight": f"{wt:.2f}%"})
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)


# ────────────────────────────────────────────────────────────────────
# CONCENTRATION CHECK
# ────────────────────────────────────────────────────────────────────

def _concentration_check(state: dict, classified: list[dict], nav: float) -> None:
    with st.container(border=True):
        st.markdown("### Concentration check")

        max_weight_pct = safe_num(state["settings"].get("maxWeightPct"), 20)
        violations = []
        for h in classified:
            wt = safe_num(h.get("currentValueUSD"), 0) / nav * 100 if nav > 0 else 0
            if wt > max_weight_pct:
                violations.append({"Ticker": h["ticker"], "Weight": f"{wt:.2f}%",
                                    "Max": f"{max_weight_pct:.0f}%",
                                    "Excess": f"+{wt - max_weight_pct:.2f}pp"})

        if violations:
            st.markdown(
                f"<div class='insight insight-warn'>"
                f"<strong>{len(violations)} position(s) exceed your max-weight limit "
                f"of {max_weight_pct:.0f}%.</strong>  "
                f"Consider trimming back toward target.</div>",
                unsafe_allow_html=True,
            )
            df = pd.DataFrame(violations)
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.markdown(
                f"<div class='insight insight-good'>"
                f"All positions within max-weight limit of {max_weight_pct:.0f}%.</div>",
                unsafe_allow_html=True,
            )

        # Cash buffer check
        cash = safe_num(state.get("cashUSD"), 0)
        cash_pct = cash / nav * 100 if nav > 0 else 0
        min_cash = safe_num(state["settings"].get("minCashBufferPct"), 5)
        if cash_pct < min_cash:
            st.markdown(
                f"<div class='insight insight-warn' style='margin-top:8px;'>"
                f"<strong>Cash {cash_pct:.1f}%</strong> is below your "
                f"{min_cash:.0f}% buffer target — limited dry powder for new opportunities.</div>",
                unsafe_allow_html=True,
            )


# ────────────────────────────────────────────────────────────────────
# ROLLING BETA TO SPY
# ────────────────────────────────────────────────────────────────────

def _portfolio_beta(state: dict, nav: float) -> None:
    with st.container(border=True):
        st.markdown("### Portfolio beta to SPY")
        st.caption("Daily NAV returns regressed against SPY daily returns. "
                    "β > 1 means more volatile than the market; < 1 means less. "
                    "Negative β means inverse correlation (rare).")

        val_history = state.get("valuation", [])
        if len(val_history) < 8:
            st.info("Need at least 8 daily NAV observations to compute meaningful beta. "
                    "Keep fetching quotes regularly.")
            return

        # Build NAV returns series
        nav_dates = [v["date"] for v in val_history]
        nav_values = [safe_num(v.get("portfolioValueUSD"), 0) for v in val_history]
        spy_history = benchmarks.fetch_benchmark_history("SPY", days=len(nav_dates) + 30)
        if spy_history is None or spy_history.empty:
            st.info("Could not fetch SPY history right now. Try again in a moment.")
            return

        # Align: keep only dates present in both
        spy_map = {row["date"]: row["close"] for _, row in spy_history.iterrows()}
        aligned = []
        for date, val in zip(nav_dates, nav_values):
            if date in spy_map and val > 0:
                aligned.append((date, val, spy_map[date]))
        if len(aligned) < 5:
            st.info("Not enough overlapping NAV/SPY trading days yet.")
            return

        # Daily returns
        nav_rets, spy_rets = [], []
        for i in range(1, len(aligned)):
            nav_ret = (aligned[i][1] - aligned[i-1][1]) / aligned[i-1][1]
            spy_ret = (aligned[i][2] - aligned[i-1][2]) / aligned[i-1][2]
            nav_rets.append(nav_ret); spy_rets.append(spy_ret)

        if len(nav_rets) < 4:
            st.info("Need more daily observations for a beta estimate.")
            return

        # Beta = cov(p, m) / var(m)
        n = len(nav_rets)
        mean_p = sum(nav_rets) / n
        mean_m = sum(spy_rets) / n
        cov = sum((p - mean_p) * (m - mean_m) for p, m in zip(nav_rets, spy_rets)) / n
        var_m = sum((m - mean_m) ** 2 for m in spy_rets) / n
        if var_m <= 0:
            st.info("SPY shows no variance in this window — beta undefined.")
            return
        beta = cov / var_m

        # Pearson correlation for context
        var_p = sum((p - mean_p) ** 2 for p in nav_rets) / n
        denom = math.sqrt(var_p * var_m)
        corr = cov / denom if denom > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Beta (β)", f"{beta:.2f}",
                    delta="more volatile than SPY" if beta > 1.05
                    else ("less volatile than SPY" if beta < 0.95 else "tracks SPY"),
                    delta_color="off")
        c2.metric("Correlation", f"{corr:.2f}",
                    delta="strong" if abs(corr) > 0.7
                    else ("moderate" if abs(corr) > 0.4 else "weak"),
                    delta_color="off")
        c3.metric("Observations", f"{n} days")

        # Quick interpretation
        if beta > 1.3:
            note = "Your portfolio amplifies market moves — gains are bigger in rallies, losses bigger in selloffs."
        elif beta < 0.5:
            note = "Your portfolio is insulated from market moves — bonds/defensives are doing their job."
        elif corr < 0.3:
            note = "Low correlation with SPY — your portfolio is moving on idiosyncratic factors, not market beta."
        else:
            note = "Your portfolio largely tracks SPY with a moderate amplification factor."
        st.caption(note)


# ────────────────────────────────────────────────────────────────────
# DRAWDOWN CHART
# ────────────────────────────────────────────────────────────────────

def _render_drawdown(state: dict) -> None:
    val_history = [v for v in state.get("valuation", [])
                   if safe_num(v.get("portfolioValueUSD"), 0) > 0]
    with st.container(border=True):
        st.markdown("### Drawdown profile")
        st.caption("Distance from your prior peak NAV. Drawdowns are how risk actually feels — "
                    "not standard deviation. Track recovery time and depth.")

        if len(val_history) < 3:
            st.info("Need at least 3 NAV observations to compute drawdowns.")
            return

        # Compute running peak + drawdown at each point
        xs = [v["date"] for v in val_history]
        ys = [safe_num(v["portfolioValueUSD"]) for v in val_history]
        peaks = []
        running_peak = ys[0]
        for v in ys:
            if v > running_peak:
                running_peak = v
            peaks.append(running_peak)
        drawdowns = [(v - p) / p * 100 if p > 0 else 0 for v, p in zip(ys, peaks)]

        max_dd = min(drawdowns)
        max_dd_idx = drawdowns.index(max_dd)
        max_dd_date = xs[max_dd_idx]
        current_dd = drawdowns[-1]

        # Days in drawdown (from last peak to now)
        days_in_dd = 0
        for i in range(len(drawdowns) - 1, -1, -1):
            if drawdowns[i] >= -0.001:  # at peak
                break
            days_in_dd += 1

        cols = st.columns(3)
        cols[0].metric("Max drawdown", f"{max_dd:.2f}%",
                        delta=f"on {max_dd_date}", delta_color="off")
        cols[1].metric("Current drawdown", f"{current_dd:.2f}%",
                        delta="at peak" if current_dd >= -0.001
                        else f"{days_in_dd} day{'s' if days_in_dd != 1 else ''} in",
                        delta_color="off")
        cols[2].metric("Recovery threshold",
                        to_usd(max(peaks)),
                        delta=f"need {((max(peaks) - ys[-1]) / ys[-1] * 100):+.2f}% to break out"
                        if ys[-1] < max(peaks) else "at all-time high",
                        delta_color="off")

        # Drawdown chart — filled red area below 0
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=drawdowns, mode="lines",
            line=dict(color="#FF4757", width=2, shape="spline", smoothing=0.4),
            fill="tozeroy", fillcolor="rgba(255,71,87,0.15)",
            hovertemplate="<b>%{x}</b><br>Drawdown: %{y:+.2f}%<extra></extra>",
            showlegend=False,
        ))
        fig.add_hline(y=0, line=dict(color="#3a3a3a", width=1, dash="dot"),
                       annotation_text="At peak", annotation_position="top right",
                       annotation_font=dict(color="#888", size=10,
                                              family="Menlo, Consolas, monospace"))

        # Y-range: from max drawdown - small padding to slightly above 0
        y_range = [min(drawdowns) - max(2, abs(min(drawdowns)) * 0.15),
                   max(2, abs(min(drawdowns)) * 0.10)]

        fig.update_layout(
            height=240, margin=dict(l=10, r=10, t=20, b=20),
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
            hovermode="x",
            hoverlabel=dict(bgcolor="#161616", bordercolor="#FF4757",
                              font=dict(family="Menlo, Consolas, monospace",
                                          size=11, color="#f5f5f5")),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ────────────────────────────────────────────────────────────────────
# FRAMEWORK REFERENCES — concise, opinionated
# ────────────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────────────
# TREEMAP — sized by weight, colored by P&L
# ────────────────────────────────────────────────────────────────────

def _render_treemap(state: dict, classified: list[dict], nav: float) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Holdings treemap</span>"
            "<span class='muted-text mono' style='font-size:10px;margin-left:auto;'>"
            "size = weight · color = % P&L</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("The whole portfolio in one image. Block size shows position weight, "
                    "color shows whether it's making or losing money. Read concentration "
                    "and pain at a glance.")

        # Build hierarchical labels: Portfolio > Sector > Ticker
        labels, parents, values, colors_pct, hovers = [], [], [], [], []

        # Root
        labels.append("Portfolio")
        parents.append("")
        values.append(nav)
        colors_pct.append(0)
        hovers.append(f"Total NAV<br>{to_usd(nav)}")

        # Sectors
        sector_totals: dict[str, float] = {}
        for h in classified:
            sec = h.get("sector", "Unknown") or "Unknown"
            sector_totals[sec] = sector_totals.get(sec, 0) + safe_num(h.get("currentValueUSD"), 0)
        for sec, total in sector_totals.items():
            labels.append(sec)
            parents.append("Portfolio")
            values.append(total)
            colors_pct.append(0)  # neutral grey for sector aggregator
            hovers.append(f"<b>{sec}</b><br>{to_usd(total)}<br>"
                            f"{(total/nav*100):.1f}% of NAV")

        # Holdings
        for h in classified:
            initial = safe_num(h.get("initialUSD"), 0)
            current = safe_num(h.get("currentValueUSD"), 0)
            pl_pct = ((current - initial) / initial * 100) if initial > 0 else 0
            labels.append(h["ticker"])
            parents.append(h.get("sector", "Unknown") or "Unknown")
            values.append(current)
            colors_pct.append(pl_pct)
            hovers.append(
                f"<b>{h['ticker']}</b> · {h.get('name', '')[:30]}<br>"
                f"Value {to_usd(current)} · {(current/nav*100):.1f}%<br>"
                f"P&L {signed_pct(pl_pct)}"
            )

        # Cash as its own block (no sector)
        cash = safe_num(state.get("cashUSD"), 0)
        if cash > 0:
            labels.append("Cash")
            parents.append("Portfolio")
            values.append(cash)
            colors_pct.append(0)
            hovers.append(f"<b>Cash</b><br>{to_usd(cash)}<br>{(cash/nav*100):.1f}% of NAV")

        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(
                colors=colors_pct,
                colorscale=[
                    [0.0, "#FF4757"],   # very negative (red)
                    [0.40, "#5a2a35"],  # mildly negative (dark red-grey)
                    [0.50, "#222222"],  # zero (neutral dark)
                    [0.60, "#2a4a3e"],  # mildly positive (dark green-grey)
                    [1.0, "#00C896"],   # very positive (green)
                ],
                cmin=-25, cmid=0, cmax=25,
                line=dict(color="#0a0a0a", width=2),
                showscale=False,
            ),
            text=hovers,
            textinfo="label+value",
            texttemplate="<b>%{label}</b><br><span style='font-size:10px;'>%{value:$,.0f}</span>",
            textfont=dict(family="Menlo, Consolas, monospace", size=11, color="#f5f5f5"),
            hovertemplate="%{text}<extra></extra>",
            tiling=dict(packing="squarify", squarifyratio=1.4),
        ))
        fig.update_layout(
            height=440,
            margin=dict(l=4, r=4, t=4, b=4),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hoverlabel=dict(bgcolor="#161616", bordercolor="#FFB800",
                              font=dict(family="Menlo, Consolas, monospace",
                                          size=11, color="#f5f5f5")),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ────────────────────────────────────────────────────────────────────
# CORRELATION MATRIX — pairwise daily returns
# ────────────────────────────────────────────────────────────────────

def _render_correlation_matrix(state: dict, classified: list[dict]) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Correlation matrix</span>"
            "<span class='muted-text mono' style='font-size:10px;margin-left:auto;'>"
            "daily return correlations</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("How positions actually move together. Sector and HHI tell you what you "
                    "*think* you own; correlation tells you what you *really* own. "
                    "Two stocks at +0.95 are functionally one position.")

        snaps = state.get("priceSnap", [])
        if len(snaps) < 5:
            st.info("Need at least 5 price snapshots to compute meaningful correlations. "
                    "Fetch quotes daily for a week.")
            return

        # Tickers we have AND have at least 5 price observations for
        tickers = sorted({h["ticker"] for h in classified})
        ticker_returns: dict[str, list[float]] = {t: [] for t in tickers}

        for i in range(1, len(snaps)):
            prev_prices = snaps[i-1].get("prices", {})
            curr_prices = snaps[i].get("prices", {})
            for t in tickers:
                if t in prev_prices and t in curr_prices:
                    p_prev = safe_num(prev_prices[t], 0)
                    p_curr = safe_num(curr_prices[t], 0)
                    if p_prev > 0 and p_curr > 0:
                        ticker_returns[t].append((p_curr - p_prev) / p_prev)

        # Filter to tickers with enough observations (≥4 returns)
        eligible = [t for t in tickers if len(ticker_returns[t]) >= 4]
        if len(eligible) < 2:
            st.info("Need at least 2 positions with overlapping price history to compute correlations.")
            return

        # Pairwise Pearson correlation, but only on overlapping observations
        n = len(eligible)
        matrix = [[1.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                # Both need same length — use min and slice from latest
                ri = ticker_returns[eligible[i]]
                rj = ticker_returns[eligible[j]]
                k = min(len(ri), len(rj))
                if k < 4:
                    matrix[i][j] = matrix[j][i] = 0.0
                    continue
                ri_w = ri[-k:]; rj_w = rj[-k:]
                mi = sum(ri_w) / k; mj = sum(rj_w) / k
                cov = sum((a - mi) * (b - mj) for a, b in zip(ri_w, rj_w)) / k
                vi = sum((a - mi) ** 2 for a in ri_w) / k
                vj = sum((b - mj) ** 2 for b in rj_w) / k
                denom = math.sqrt(vi * vj)
                corr = cov / denom if denom > 0 else 0.0
                matrix[i][j] = matrix[j][i] = round(corr, 2)

        # Heatmap
        fig = go.Figure(data=go.Heatmap(
            z=matrix,
            x=eligible,
            y=eligible,
            colorscale=[
                [0.0, "#00B8D4"],   # strong negative correlation (cyan/cool)
                [0.5, "#1a1a1a"],   # uncorrelated (dark/neutral)
                [1.0, "#FF4757"],   # strong positive correlation (red/hot)
            ],
            zmin=-1, zmid=0, zmax=1,
            text=[[f"{v:+.2f}" for v in row] for row in matrix],
            texttemplate="%{text}",
            textfont=dict(family="Menlo, Consolas, monospace", size=10, color="#f5f5f5"),
            hovertemplate="<b>%{y} ↔ %{x}</b><br>ρ = %{z:.2f}<extra></extra>",
            colorbar=dict(
                title=dict(text="ρ", font=dict(color="#888", size=10)),
                tickfont=dict(color="#888", family="Menlo, Consolas, monospace", size=9),
                thickness=10, len=0.6,
            ),
        ))
        fig.update_layout(
            height=max(280, 36 * n + 80),
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(side="bottom",
                         tickfont=dict(color="#b8b8b8",
                                          family="Menlo, Consolas, monospace", size=10)),
            yaxis=dict(autorange="reversed",
                         tickfont=dict(color="#b8b8b8",
                                          family="Menlo, Consolas, monospace", size=10)),
            hoverlabel=dict(bgcolor="#161616", bordercolor="#FFB800",
                              font=dict(family="Menlo, Consolas, monospace",
                                          size=11, color="#f5f5f5")),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Find the most-correlated pair and the most-uncorrelated pair to call out
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append((eligible[i], eligible[j], matrix[i][j]))
        if pairs:
            pairs_sorted = sorted(pairs, key=lambda p: abs(p[2]), reverse=True)
            most_corr = pairs_sorted[0]
            most_uncorr = sorted(pairs, key=lambda p: abs(p[2]))[0]
            c1, c2 = st.columns(2)
            with c1:
                cls = "warn" if abs(most_corr[2]) > 0.85 else "cool"
                st.markdown(
                    f"<div class='insight insight-{cls}'>"
                    f"<div class='label' style='margin-bottom:4px;'>Most-correlated pair</div>"
                    f"<span class='mono' style='font-weight:600;color:var(--text);'>"
                    f"{most_corr[0]} ↔ {most_corr[1]}</span> "
                    f"<span class='mono' style='font-weight:600;'>ρ = {most_corr[2]:+.2f}</span>"
                    + (f"<br><span class='muted-text' style='font-size:11px;'>"
                       f"These are functionally one bet — consider trimming the smaller one.</span>"
                       if abs(most_corr[2]) > 0.85 else "")
                    + f"</div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f"<div class='insight insight-good'>"
                    f"<div class='label' style='margin-bottom:4px;'>Best diversifier</div>"
                    f"<span class='mono' style='font-weight:600;color:var(--text);'>"
                    f"{most_uncorr[0]} ↔ {most_uncorr[1]}</span> "
                    f"<span class='mono' style='font-weight:600;'>ρ = {most_uncorr[2]:+.2f}</span>"
                    f"<br><span class='muted-text' style='font-size:11px;'>"
                    f"These genuinely add diversification to each other.</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ────────────────────────────────────────────────────────────────────
# TAG EXPOSURE — cross-cut analysis sectors don't capture
# ────────────────────────────────────────────────────────────────────

def _render_tag_exposure(state: dict, classified: list[dict], nav: float) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Tag exposure</span>"
            "<span class='muted-text mono' style='font-size:10px;margin-left:auto;'>"
            "your themes</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("Cross-cut analysis using your own tags. Sectors are arbitrary buckets — "
                    "your tags express your actual investment themes (e.g. 'AI infrastructure', "
                    "'rate-sensitive', 'EM consumer'). Tag positions in the Trade tab drill-down.")

        # Aggregate by tag — a position can belong to multiple tags
        tag_totals: dict[str, list[dict]] = {}
        for h in classified:
            tags = h.get("tags", []) or []
            for tag in tags:
                tag_totals.setdefault(tag, []).append(h)

        if not tag_totals:
            st.markdown(
                "<div class='empty-state' style='padding:32px;'>"
                "<div class='empty-state-title'>No tags applied yet</div>"
                "<div class='empty-state-hint'>"
                "Open any position on the Trade tab and use the tag editor to add themes "
                "like 'AI', 'defensive', 'EM', or 'yield play'.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        rows = []
        for tag, positions in sorted(tag_totals.items(),
                                       key=lambda x: -sum(safe_num(p.get("currentValueUSD"), 0) for p in x[1])):
            total_val = sum(safe_num(p.get("currentValueUSD"), 0) for p in positions)
            total_pl = sum(safe_num(p.get("currentValueUSD"), 0) - safe_num(p.get("initialUSD"), 0)
                            for p in positions)
            wt = (total_val / nav * 100) if nav > 0 else 0
            tickers = ", ".join(p["ticker"] for p in positions[:6])
            if len(positions) > 6:
                tickers += f" +{len(positions)-6} more"
            rows.append({
                "Tag": tag,
                "Positions": len(positions),
                "Tickers": tickers,
                "Value": to_usd(total_val),
                "Weight": f"{wt:.2f}%",
                "$ P&L": to_usd(total_pl),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Framework references</span>"
            "<span class='muted-text mono' style='font-size:10px;margin-left:auto;'>"
            "interpretive lenses</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("How to read the metrics above through frameworks that matter. "
                    "Brief by design — these are anchors, not full explanations.")

        with st.expander("HHI — Herfindahl-Hirschman Index"):
            st.markdown("""
**Sum of squared weights × 10,000.** Antitrust-style measure of concentration applied to portfolios.

| HHI | Interpretation |
|---|---|
| < 1,500 | Diversified (≥ 7 effective positions) |
| 1,500 – 2,500 | Moderately concentrated |
| > 2,500 | Highly concentrated |

**Effective N = 1 / sum(w²)** — how many *equally-weighted* positions your portfolio is equivalent to. A 10-position portfolio with one 80% bet has effective N ≈ 1.5 — almost a single-name bet in disguise.

**The catch:** HHI doesn't see correlation. Three names in one sector look diversified to HHI but are functionally one bet.
""")

        with st.expander("Beta — Marks's first-level vs second-level thinking"):
            st.markdown("""
**Beta = covariance with market / variance of market.** Measures sensitivity to market moves.

- β = 1.0 → moves with SPY
- β > 1 → amplified (cyclicals, tech, leverage)
- β < 1 → muted (utilities, staples, bonds)
- β < 0 → inverse (rare; gold sometimes, short positions)

**Marks's point** (*The Most Important Thing*): high beta in a bull market makes you look smart. Real skill is generating *alpha* — return uncorrelated to beta. Your beta tells you how much of your return is "borrowed" from the market vs earned from selection.
""")

        with st.expander("Drawdown — what risk actually feels like"):
            st.markdown("""
**Distance from prior peak NAV.** Volatility measures dispersion; drawdown measures pain.

A 30% drawdown requires a **43% gain to recover** — drawdowns are asymmetric. This is why position sizing and tail-risk management matter more than maximizing expected return.

**Rule of thumb (institutional):** investors fire managers at -20%. Retail capitulates at -30%. Knowing your own drawdown tolerance — *before* you're tested — is half of investing.
""")

        with st.expander("Reflexivity — Soros's framework"):
            st.markdown("""
**Markets shape the fundamentals they're supposed to reflect.** A rising stock attracts buyers, expands access to capital, validates the thesis, raises the stock further — until the loop breaks.

**Watch for:** narrative-driven moves where price *causes* the fundamental story (capex booms in hot sectors, IPO windows, momentum factor extremes). The setup is most dangerous when the loop has gone on longest — when "everyone knows" the story.

**Practical use:** ask of every position, "Is this story fundamental, or is it the price action *creating* the story?" Reflexive bets can compound for years; they also unwind violently.
""")

        with st.expander("Diversification — Dalio's holy grail"):
            st.markdown("""
**Adding 15 uncorrelated return streams cuts portfolio risk by ~80% without sacrificing return** (Dalio, *Principles*).

The math: portfolio volatility ≈ σ / √N when assets are uncorrelated. The catch is correlation — most assets correlate ~0.6 in normal times and ~0.95 in crises.

**The actionable test:** would these positions all fall together in a 2008-style event? If yes, you have *one* bet, not many.

**Where bonds, commodities, foreign equity, and uncorrelated alpha sources earn their place** — not for their standalone return but for their portfolio-level risk reduction.
""")

        with st.expander("Cycles — Marks's second-level thinking"):
            st.markdown("""
**Where in the cycle are we?** is the most consequential question.

The cycle: prosperity → optimism → risk-on → leverage → excess → break → fear → de-risking → opportunity → repeat.

**Signs you're late-cycle:** record-low credit spreads, abundant IPOs, "this time is different" framings, retail investor euphoria, multiple expansion outpacing earnings growth.

**Marks's point:** cycle position is more predictive than valuation alone. A "cheap" stock in a late cycle can keep getting cheaper for years. A "expensive" stock in early cycle can compound for a decade.

**Practical use:** before adding risk, ask whether the macro setup rewards or punishes risk-taking right now. Cash is a position.
""")
    state = get_state()
    nav = get_portfolio_value(state)

    # Need holdings + at least one quote fetch to make insights useful
    holdings = state.get("holdings", [])
    if not holdings:
        st.info("Build a portfolio in the Build tab to see insights.")
        return

    priced = [h for h in holdings if safe_num(h.get("lastPrice"), 0) > 0]
    if not priced:
        st.info("Fetch quotes (Trade tab) to enable portfolio analytics.")
        return

    # Classify everything (cached, fast on re-render)
    with st.spinner("Classifying positions…"):
        classified = sectors.classify_holdings(holdings)

    # Render sections
    _headline_metrics(state, classified, nav)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    _render_treemap(state, classified, nav)
    _contributors(state, classified, nav)
    c1, c2 = st.columns([3, 2])
    with c1:
        _sector_exposure(state, classified, nav)
    with c2:
        _geographic_exposure(state, classified, nav)
    _render_tag_exposure(state, classified, nav)
    _concentration_check(state, classified, nav)
    _render_correlation_matrix(state, classified)
    _render_drawdown(state)
    _portfolio_beta(state, nav)
    _render_framework_references()
