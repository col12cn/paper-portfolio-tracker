"""Overview tab: NAV sparkline, key metrics, ask Gemini, active basket."""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from app.state import get_state, commit, get_portfolio_value
from app.helpers import safe_num, to_usd, signed_pct, fmt_rel_time
from app import ai


def _render_onboarding(state: dict) -> None:
    """First-run guidance — dismissible card with 3 setup steps."""
    if state.get("onboardingDismissed"):
        return
    gemini_set = bool(st.secrets.get("GEMINI_API_KEY", "")) if hasattr(st, "secrets") else False
    customised = bool(state.get("aiBasket"))
    steps = [
        {"done": gemini_set,  "label": "Add a Gemini API key in `.streamlit/secrets.toml`"},
        {"done": customised,  "label": "Build your basket in the Build tab — or use the AI workflow"},
        {"done": False,       "label": "Click 'Fetch quotes' on the Trade tab to mark to market"},
    ]
    if all(s["done"] for s in steps[:-1]):
        return  # all set, hide card

    with st.container(border=True):
        st.markdown("### Get started in 3 steps")
        for i, s in enumerate(steps, 1):
            check = "✅" if s["done"] else f"**{i}.**"
            st.markdown(f"{check} {s['label']}")
        if st.button("Dismiss", key="dismiss_onboard"):
            state["onboardingDismissed"] = True
            commit()
            st.rerun()


def _render_sparkline(state: dict) -> None:
    """Compact NAV sparkline above metrics."""
    val_history = [v for v in state.get("valuation", [])
                   if safe_num(v.get("portfolioValueUSD"), 0) > 0]
    nav = get_portfolio_value(state)
    start_cap = safe_num(state["settings"].get("startingCapital"), 1000)
    pnl_pct = ((nav - start_cap) / start_cap * 100) if start_cap > 0 else 0

    cols = st.columns([1, 4, 1])
    with cols[0]:
        st.markdown(
            f"<div class='label'>Portfolio NAV</div>"
            f"<div class='value'>{to_usd(nav)}</div>",
            unsafe_allow_html=True,
        )

    with cols[1]:
        if len(val_history) < 2:
            st.markdown(
                "<div style='color:var(--muted);font-style:italic;font-size:11px;"
                "text-align:center;padding:24px;font-family:var(--font-mono);'>"
                "Awaiting data — fetch quotes to start tracking</div>",
                unsafe_allow_html=True,
            )
        else:
            xs = [v["date"] for v in val_history]
            ys = [v["portfolioValueUSD"] for v in val_history]

            # Y-range that focuses on actual variation, not 0-to-NAV
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
                fill="tozeroy",
                fillcolor=f"rgba({rgb},0.15)",
                hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
            ))
            fig.add_hline(y=start_cap, line=dict(color="#3a3a3a", width=1, dash="dash"))
            fig.update_layout(
                height=80, margin=dict(l=0, r=0, t=4, b=4),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(visible=False),
                yaxis=dict(visible=False, range=y_range),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with cols[2]:
        cls = "good" if pnl_pct >= 0 else "bad"
        st.markdown(
            f"<div style='text-align:right;font-family:var(--font-mono);"
            f"font-weight:600;font-size:18px;letter-spacing:-0.01em;' class='{cls}'>"
            f"{signed_pct(pnl_pct)}</div>"
            f"<div class='label' style='text-align:right;margin-top:2px;'>Since inception</div>",
            unsafe_allow_html=True,
        )


def _render_metrics(state: dict) -> None:
    nav = get_portfolio_value(state)
    cash = safe_num(state.get("cashUSD"), 0)
    start_cap = safe_num(state["settings"].get("startingCapital"), 1000)
    pnl = nav - start_cap
    val_history = state.get("valuation", [])
    last_val = val_history[-2]["portfolioValueUSD"] if len(val_history) > 1 else nav
    daily = nav - safe_num(last_val, nav)
    last_refresh = state.get("lastRefresh") or "Never"
    if last_refresh != "Never":
        last_refresh = fmt_rel_time(last_refresh) or last_refresh

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("NAV", to_usd(nav))
    c2.metric("Cash", to_usd(cash))
    c3.metric("P/L vs start", to_usd(pnl),
              delta=f"{signed_pct((pnl/start_cap*100) if start_cap else 0)}",
              delta_color="normal" if pnl >= 0 else "inverse")
    c4.metric("Latest move", to_usd(daily),
              delta_color="off")
    c5.metric("Positions", str(len(state.get("holdings", []))),
              delta=f"refreshed {last_refresh}", delta_color="off")


def _render_ask_gemini(state: dict) -> None:
    """Free-form Q&A box."""
    with st.container(border=True):
        st.markdown("### Ask Gemini about your portfolio")
        st.caption("Free-form question. Your current holdings, weights, P/L, cash, and thesis are sent as context.")

        cols = st.columns([5, 1, 1])
        with cols[0]:
            question = st.text_input(
                "question_input",
                label_visibility="collapsed",
                placeholder="e.g. What if the Fed cuts 50bps next month? Where am I most exposed?",
                key="ask_input",
            )
        with cols[1]:
            ask_btn = st.button("Ask", use_container_width=True, key="ask_btn")
        with cols[2]:
            if st.button("Clear", use_container_width=True, key="clear_ask",
                         help="Clear cached Q&A history"):
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
                "<div style='color:var(--muted);font-style:italic;font-size:12px;"
                "padding:8px;font-family:var(--font-mono);'>"
                "Awaiting first question</div>",
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


def _render_active_basket(state: dict) -> None:
    """Show active basket + thesis."""
    with st.container(border=True):
        is_custom = bool(state.get("aiBasket"))
        title = "Active basket" if is_custom else "Default basket"
        st.markdown(f"### {title}")
        if is_custom:
            st.caption("Defined in the Build tab. Fetch quotes (Trade tab) to mark to market.")
        else:
            st.caption("Seeded from default. Build your own in the Build tab.")

        if state.get("aiThesis"):
            st.markdown(
                f"<div class='insight insight-cool' style='margin-bottom:14px;'>"
                f"{state['aiThesis']}</div>",
                unsafe_allow_html=True,
            )

        basket = state.get("aiBasket") or [
            {"ticker": h["ticker"], "name": h["name"], "targetWeight": h["targetWeight"], "why": h.get("why", "")}
            for h in state["holdings"]
        ]
        for h in basket:
            st.markdown(
                f"<div class='position-row'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<span class='position-ticker'>{h['ticker']}</span>"
                f"<span class='pill pill-accent'>Tgt {safe_num(h.get('targetWeight'))*100:.1f}%</span></div>"
                f"<div class='position-name'>{h['name']}</div>"
                f"<div class='position-why'>{h.get('why', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def render() -> None:
    state = get_state()
    _render_onboarding(state)
    _render_sparkline(state)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    _render_metrics(state)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    _render_ask_gemini(state)
    _render_active_basket(state)
