"""Overview tab — terminal-style dashboard.

Layout:
  ┌─ Persistent header (NAV + sparkline + key metrics + live indicator)
  ├─ This-week digest (4-col strip)
  └─ 2-column grid below:
      LEFT:  Active basket
      RIGHT: Quick-action Ask Gemini  +  Recent activity feed

Tighter information density, designed to be the at-a-glance command centre.
"""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

from app.state import get_state, commit, get_portfolio_value
from app.helpers import safe_num, to_usd, signed_pct, fmt_rel_time
from app import ai


# ────────────────────────────────────────────────────────────────────
# PERSISTENT HEADER STRIP
# ────────────────────────────────────────────────────────────────────

def _render_header_strip(state: dict) -> None:
    """Top NAV strip — sparkline + metrics in a single dense row."""
    val_history = [v for v in state.get("valuation", [])
                   if safe_num(v.get("portfolioValueUSD"), 0) > 0]
    nav = get_portfolio_value(state)
    cash = safe_num(state.get("cashUSD"), 0)
    start_cap = safe_num(state["settings"].get("startingCapital"), 1000)
    pnl_pct = ((nav - start_cap) / start_cap * 100) if start_cap > 0 else 0
    pnl_class = "good" if pnl_pct >= 0 else "bad"

    # Day change
    daily = 0
    if len(val_history) > 1:
        daily = nav - safe_num(val_history[-2].get("portfolioValueUSD"), nav)
    daily_class = "good" if daily >= 0 else "bad"

    last_refresh = state.get("lastRefresh") or "never"
    if last_refresh != "never":
        last_refresh = fmt_rel_time(last_refresh) or "recent"

    # Sparkline (smaller than before to fit the strip)
    cols = st.columns([1.4, 3, 1, 1, 1, 1])
    with cols[0]:
        st.markdown(
            f"<div class='label'>Portfolio NAV</div>"
            f"<div class='value' style='font-size:28px;'>{to_usd(nav)}</div>"
            f"<div class='mono {pnl_class}' style='font-size:12px;font-weight:600;margin-top:2px;'>"
            f"{signed_pct(pnl_pct)} <span class='muted-text' style='font-weight:400;'>since inception</span></div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        if len(val_history) >= 2:
            xs = [v["date"] for v in val_history]
            ys = [v["portfolioValueUSD"] for v in val_history]
            all_vals = ys + [start_cap]
            y_min, y_max = min(all_vals), max(all_vals)
            spread = max(y_max - y_min, y_max * 0.02)
            y_range = [y_min - spread * 0.30, y_max + spread * 0.20]
            colour = "#00C896" if ys[-1] >= start_cap else "#FF4757"
            rgb = "0,200,150" if ys[-1] >= start_cap else "255,71,87"
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines",
                line=dict(color=colour, width=2, shape="spline", smoothing=0.4),
                fill="tozeroy", fillcolor=f"rgba({rgb},0.15)",
                hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
            ))
            fig.add_hline(y=start_cap, line=dict(color="#333", width=1, dash="dash"))
            fig.update_layout(
                height=80, margin=dict(l=0, r=0, t=4, b=4),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(visible=False),
                yaxis=dict(visible=False, range=y_range),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.markdown(
                "<div style='color:var(--muted);font-style:italic;font-size:11px;"
                "text-align:center;padding:24px;font-family:var(--font-mono);'>"
                "Awaiting data</div>",
                unsafe_allow_html=True,
            )
    with cols[2]:
        st.markdown(
            f"<div class='label'>Cash</div>"
            f"<div class='mono' style='font-size:18px;font-weight:600;color:var(--text);margin-top:6px;'>"
            f"{to_usd(cash)}</div>"
            f"<div class='muted-text mono' style='font-size:10px;'>"
            f"{(cash/nav*100 if nav>0 else 0):.1f}% of NAV</div>",
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(
            f"<div class='label'>Day</div>"
            f"<div class='mono {daily_class}' style='font-size:18px;font-weight:600;margin-top:6px;'>"
            f"{to_usd(daily)}</div>"
            f"<div class='muted-text mono' style='font-size:10px;'>last marked</div>",
            unsafe_allow_html=True,
        )
    with cols[4]:
        st.markdown(
            f"<div class='label'>Positions</div>"
            f"<div class='mono' style='font-size:18px;font-weight:600;color:var(--text);margin-top:6px;'>"
            f"{len(state.get('holdings', []))}</div>"
            f"<div class='muted-text mono' style='font-size:10px;'>active</div>",
            unsafe_allow_html=True,
        )
    with cols[5]:
        live_dot = ("<span class='ticker-bar-live'></span>"
                    if "ago" in last_refresh and not last_refresh.startswith(("3d", "4d", "5d")) else "")
        st.markdown(
            f"<div class='label'>Last refresh</div>"
            f"<div class='mono' style='font-size:14px;font-weight:600;color:var(--text);margin-top:6px;'>"
            f"{live_dot}{last_refresh}</div>"
            f"<div class='muted-text mono' style='font-size:10px;'>fetch on Trade tab</div>",
            unsafe_allow_html=True,
        )


# ────────────────────────────────────────────────────────────────────
# THIS-WEEK DIGEST
# ────────────────────────────────────────────────────────────────────

def _render_this_week(state: dict) -> None:
    val = state.get("valuation", [])
    if len(val) < 2:
        return

    today = datetime.now(timezone.utc).date()
    week_ago_iso = (today - timedelta(days=7)).isoformat()
    historical = [v for v in val if v["date"] <= week_ago_iso]
    week_ago_nav = (safe_num(historical[-1]["portfolioValueUSD"])
                     if historical else safe_num(val[0]["portfolioValueUSD"]))
    current_nav = safe_num(val[-1]["portfolioValueUSD"])
    nav_chg = current_nav - week_ago_nav
    nav_chg_pct = (nav_chg / week_ago_nav * 100) if week_ago_nav > 0 else 0

    from app import benchmarks
    try:
        spy_chg_pct = benchmarks.benchmark_total_return_pct("SPY", days=7)
    except Exception:
        spy_chg_pct = None

    week_ago_dt = datetime.now(timezone.utc) - timedelta(days=7)
    recent_trades = [t for t in state.get("tradeLog", [])
                     if t.get("action") in ("BUY", "SELL", "CLOSE")
                     and t.get("timestamp", "") >= week_ago_dt.isoformat()]

    movers = []
    for h in state.get("holdings", []):
        wk = h.get("weekOHLC")
        if wk and wk.get("open"):
            wk_pct = (wk["close"] - wk["open"]) / wk["open"] * 100
            movers.append((h["ticker"], wk_pct))
    movers.sort(key=lambda x: x[1], reverse=True)
    best = movers[0] if movers else None
    worst = movers[-1] if movers and len(movers) > 1 else None

    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>This week</span>"
            "<span class='muted-text mono' style='font-size:10px;margin-left:auto;'>past 7 days</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        cols = st.columns(4)
        nav_class = "good" if nav_chg >= 0 else "bad"
        cols[0].markdown(
            f"<div class='label'>NAV change</div>"
            f"<div class='mono {nav_class}' style='font-size:22px;font-weight:600;'>"
            f"{to_usd(nav_chg)}</div>"
            f"<div class='mono {nav_class}' style='font-size:11px;'>{signed_pct(nav_chg_pct)}</div>",
            unsafe_allow_html=True,
        )
        if spy_chg_pct is not None:
            delta = nav_chg_pct - spy_chg_pct
            cls = "good" if delta >= 0 else "bad"
            cols[1].markdown(
                f"<div class='label'>vs SPY</div>"
                f"<div class='mono {cls}' style='font-size:22px;font-weight:600;'>"
                f"{signed_pct(delta)}</div>"
                f"<div class='mono muted-text' style='font-size:11px;'>SPY {signed_pct(spy_chg_pct)}</div>",
                unsafe_allow_html=True,
            )
        else:
            cols[1].markdown(
                f"<div class='label'>vs SPY</div>"
                f"<div class='mono muted-text' style='font-size:14px;'>n/a</div>",
                unsafe_allow_html=True,
            )
        if best:
            cls = "good" if best[1] >= 0 else "bad"
            cols[2].markdown(
                f"<div class='label'>Top mover</div>"
                f"<div class='mono' style='font-size:20px;font-weight:600;color:var(--text);'>{best[0]}</div>"
                f"<div class='mono {cls}' style='font-size:11px;'>{signed_pct(best[1])} this wk</div>",
                unsafe_allow_html=True,
            )
        else:
            cols[2].markdown(
                f"<div class='label'>Top mover</div>"
                f"<div class='mono muted-text' style='font-size:14px;'>n/a</div>",
                unsafe_allow_html=True,
            )
        cols[3].markdown(
            f"<div class='label'>Trades</div>"
            f"<div class='mono' style='font-size:22px;font-weight:600;color:var(--text);'>{len(recent_trades)}</div>"
            f"<div class='mono muted-text' style='font-size:11px;'>"
            f"{sum(1 for t in recent_trades if t['action'] == 'BUY')} buy · "
            f"{sum(1 for t in recent_trades if t['action'] in ('SELL','CLOSE'))} sell</div>",
            unsafe_allow_html=True,
        )
        if worst and worst[1] < -3:
            st.markdown(
                f"<div style='margin-top:14px;padding-top:10px;border-top:1px solid var(--line);"
                f"font-size:11px;color:var(--muted);'>"
                f"<span class='label' style='color:var(--warn);'>Watch</span> "
                f"<span class='mono' style='color:var(--text);font-weight:600;margin-left:8px;'>{worst[0]}</span> "
                f"<span class='mono bad'>{signed_pct(worst[1])}</span> "
                f"this week — consider reviewing the thesis."
                f"</div>",
                unsafe_allow_html=True,
            )


# ────────────────────────────────────────────────────────────────────
# ASK GEMINI WITH QUICK-ACTION CHIPS
# ────────────────────────────────────────────────────────────────────

QUICK_ACTIONS = [
    ("Brief on top position",
     "Give me a 200-word brief on my single largest position: current setup, key catalyst in the next 60 days, primary risk, and whether to add/trim/hold."),
    ("Where am I most exposed?",
     "Identify my 3 biggest concentration risks (sector, factor, single-stock, or macro) and quantify each in % of NAV terms."),
    ("Diversification gap",
     "What sector, factor, or geographic exposure am I missing relative to a balanced portfolio? Suggest 2-3 specific tickers I should consider for the watchlist."),
    ("Critique my thesis",
     "Pressure-test my current investment thesis. What are the 2-3 most likely ways I'm wrong about this portfolio?"),
    ("Macro factor in focus",
     "Given current market conditions, which macro variable (rates, inflation, credit spreads, USD, oil) most affects my portfolio's beta right now? How much would a 1-sigma move in it shift my NAV?"),
    ("Biggest tail risk",
     "Identify the single biggest tail risk to my portfolio in the next 30 days. Quantify the potential drawdown if it materializes."),
]


def _render_ask_gemini(state: dict) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Ask Gemini</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("Quick actions below or write your own. "
                    "Your full portfolio context is sent automatically.")

        # Quick-action chips — each populates the textarea via session state
        st.markdown("<div class='quick-action-row'>", unsafe_allow_html=True)
        chip_cols = st.columns(3)
        for i, (label, prompt) in enumerate(QUICK_ACTIONS):
            with chip_cols[i % 3]:
                if st.button(label, key=f"qa_{i}", use_container_width=True):
                    st.session_state["ask_input"] = prompt
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        # Question textarea + Ask button
        question = st.text_area(
            "Question",
            placeholder="e.g. What if the Fed cuts 50bps next month? Where am I most exposed?",
            key="ask_input",
            label_visibility="collapsed",
            height=90,
        )

        b1, b2 = st.columns([1, 1])
        with b1:
            ask_btn = st.button("✦ Ask", use_container_width=True, type="primary",
                                  key="ask_btn_main")
        with b2:
            if st.button("Clear history", use_container_width=True, key="clear_ask",
                          help="Wipe past Q&A"):
                state["askHistory"] = []
                commit()
                st.rerun()

        if ask_btn and question.strip():
            with st.spinner("Asking Gemini with full portfolio context…"):
                try:
                    answer = ai.ask_gemini(state, question.strip())
                    state.setdefault("askHistory", []).insert(0, {
                        "timestamp": datetime.now().isoformat(),
                        "question": question.strip(),
                        "answer": answer,
                    })
                    state["askHistory"] = state["askHistory"][:10]
                    commit()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        history = state.get("askHistory", [])
        if not history:
            st.markdown(
                "<div class='empty-state' style='padding:24px;'>"
                "<div class='empty-state-title'>No questions yet</div>"
                "<div class='empty-state-hint'>Pick a quick action or write your own to get started.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            latest = history[0]
            st.markdown(
                f"<div class='insight'>"
                f"<div class='insight-meta'><strong>Q</strong>{latest['question']}"
                f"<span style='margin-left:10px;color:var(--muted-2);'>"
                f"{fmt_rel_time(latest.get('timestamp'))}</span></div>"
                f"<div>{latest['answer']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if len(history) > 1:
                with st.expander(f"Earlier questions · {len(history)-1}"):
                    for h in history[1:]:
                        st.markdown(f"**Q:** {h['question']}")
                        st.markdown(f"<div style='font-size:13px;color:var(--text-2);"
                                    f"line-height:1.6;'>{h['answer']}</div>",
                                    unsafe_allow_html=True)
                        st.markdown("---")


# ────────────────────────────────────────────────────────────────────
# RECENT ACTIVITY FEED
# ────────────────────────────────────────────────────────────────────

def _render_activity_feed(state: dict) -> None:
    """Last ~10 events: trades, asks, rebalances, cash flows."""
    events = []

    for t in state.get("tradeLog", [])[:10]:
        if t.get("action") == "INIT":
            continue
        action = t.get("action", "")
        dot_class = "buy" if action == "BUY" else "sell"
        usd = safe_num(t.get("tradeUSD"), 0)
        events.append({
            "ts": t.get("timestamp", ""),
            "dot": dot_class,
            "text": (f"<b>{action}</b> "
                     f"<span class='mono' style='color:var(--text);font-weight:600;'>{t.get('ticker','')}</span> "
                     f"<span class='mono'>{to_usd(usd)}</span>"
                     + (f"<br><span style='color:var(--muted);font-size:11px;'>"
                        f"{(t.get('reason') or '')[:80]}</span>"
                        if t.get("reason") else "")),
        })

    for r in state.get("rebalanceLog", [])[:3]:
        events.append({
            "ts": r.get("timestamp", ""),
            "dot": "rebal",
            "text": (f"<b>REBALANCE</b> "
                     f"<span class='mono'>{r.get('positionCount', 0)} positions</span> "
                     f"<span class='mono muted-text'>NAV {to_usd(r.get('navAtRebalance'))}</span>"),
        })

    for a in state.get("askHistory", [])[:5]:
        events.append({
            "ts": a.get("timestamp", ""),
            "dot": "ask",
            "text": f"<b>ASK</b> <span style='color:var(--text-2);'>{a.get('question','')[:90]}…</span>",
        })

    for c in state.get("cashLog", [])[:5]:
        if c.get("type") in ("DEPOSIT", "WITHDRAW"):
            events.append({
                "ts": c.get("timestamp", ""),
                "dot": "cash",
                "text": (f"<b>{c['type']}</b> "
                         f"<span class='mono'>{to_usd(abs(safe_num(c.get('amount'))))}</span> "
                         f"<span class='muted-text'>{c.get('note', '')[:60]}</span>"),
            })

    # Sort by timestamp descending, take top 12
    events.sort(key=lambda e: e["ts"], reverse=True)
    events = events[:12]

    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Recent activity</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        if not events:
            st.markdown(
                "<div class='empty-state' style='padding:24px;'>"
                "<div class='empty-state-title'>No activity yet</div>"
                "<div class='empty-state-hint'>Your trades, asks, and rebalances will appear here.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        feed_html = "<div>"
        for e in events:
            feed_html += (
                f"<div class='activity-item'>"
                f"<div class='activity-dot activity-dot-{e['dot']}'></div>"
                f"<div class='activity-text'>{e['text']}</div>"
                f"<div class='activity-time'>{fmt_rel_time(e['ts'])}</div>"
                f"</div>"
            )
        feed_html += "</div>"
        st.markdown(feed_html, unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────
# ACTIVE BASKET (compact)
# ────────────────────────────────────────────────────────────────────

def _render_active_basket(state: dict) -> None:
    with st.container(border=True):
        is_custom = bool(state.get("aiBasket"))
        title = "Active basket" if is_custom else "Default basket"
        st.markdown(
            f"<div class='section-header'>"
            f"<span class='section-header-text'>{title}</span>"
            f"<span class='muted-text mono' style='font-size:10px;margin-left:auto;'>"
            f"edit on Build tab</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if state.get("aiThesis"):
            with st.expander("Thesis", expanded=False):
                st.markdown(
                    f"<div style='font-size:13px;color:var(--text-2);line-height:1.65;"
                    f"white-space:pre-wrap;'>{state['aiThesis']}</div>",
                    unsafe_allow_html=True,
                )

        basket = state.get("aiBasket") or [
            {"ticker": h["ticker"], "name": h["name"], "targetWeight": h["targetWeight"],
             "why": h.get("why", "")}
            for h in state["holdings"]
        ]
        for h in basket:
            st.markdown(
                f"<div class='position-row'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<span class='position-ticker'>{h['ticker']}</span>"
                f"<span class='pill pill-accent'>{safe_num(h.get('targetWeight'))*100:.1f}%</span></div>"
                f"<div class='position-name'>{h['name']}</div>"
                + (f"<div class='position-why'>{h.get('why','')}</div>" if h.get("why") else "")
                + f"</div>",
                unsafe_allow_html=True,
            )


# ────────────────────────────────────────────────────────────────────
# ONBOARDING
# ────────────────────────────────────────────────────────────────────

def _render_onboarding(state: dict) -> None:
    if state.get("onboardingDismissed"):
        return
    gemini_set = bool(st.secrets.get("GEMINI_API_KEY", "")) if hasattr(st, "secrets") else False
    customised = bool(state.get("aiBasket"))
    steps = [
        {"done": gemini_set, "label": "Add a Gemini API key in `.streamlit/secrets.toml`"},
        {"done": customised, "label": "Build your basket in the Build tab — or use the AI workflow"},
        {"done": False, "label": "Click 'Fetch quotes' on the Trade tab to mark to market"},
    ]
    if all(s["done"] for s in steps[:-1]):
        return
    with st.container(border=True):
        st.markdown(
            "<div class='section-header'>"
            "<span class='section-header-text'>Get started</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        for i, s in enumerate(steps, 1):
            check = "✅" if s["done"] else f"**{i}.**"
            st.markdown(f"{check} {s['label']}")
        if st.button("Dismiss", key="dismiss_onboard"):
            state["onboardingDismissed"] = True
            commit()
            st.rerun()


# ────────────────────────────────────────────────────────────────────
# MAIN — DASHBOARD GRID LAYOUT
# ────────────────────────────────────────────────────────────────────

def render() -> None:
    state = get_state()
    _render_onboarding(state)
    _render_header_strip(state)
    _render_this_week(state)

    # Two-column dashboard grid below
    left, right = st.columns([1, 1])
    with left:
        _render_active_basket(state)
    with right:
        _render_ask_gemini(state)
        _render_activity_feed(state)
