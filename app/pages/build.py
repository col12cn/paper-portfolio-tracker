"""Build tab: portfolio builder + 3-step AI workflow."""
from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime

from app.state import get_state, commit, mark_valuation
from app.helpers import safe_num, to_usd, now_iso
from app import ai


def _render_basket_editor(state: dict) -> None:
    """Editable basket table — st.data_editor."""
    with st.container(border=True):
        st.markdown("### Portfolio builder")
        st.caption("Define your basket manually, paste in JSON from any AI, "
                   "or use the AI workflow below to generate one. "
                   "Weights are auto-normalised to sum to 1.0.")

        # Thesis
        thesis = st.text_area(
            "Investment thesis (optional)",
            value=state.get("aiThesis") or "",
            height=110,
            placeholder="Describe your macro view, sector tilts, and rationale…",
            key="builder_thesis",
        )

        # Initial dataframe — from current basket if it exists, else current holdings
        if "builder_rows" not in st.session_state:
            basket = state.get("aiBasket") or [
                {"ticker": h["ticker"], "name": h["name"],
                 "targetWeight": h["targetWeight"], "why": h.get("why", "")}
                for h in state["holdings"]
            ]
            st.session_state.builder_rows = pd.DataFrame([
                {
                    "Ticker": h["ticker"],
                    "Name": h["name"],
                    "Weight %": round(safe_num(h.get("targetWeight")) * 100, 2),
                    "Why": h.get("why", ""),
                }
                for h in basket
            ])

        edited = st.data_editor(
            st.session_state.builder_rows,
            num_rows="dynamic",
            use_container_width=True,
            key="builder_editor",
            column_config={
                "Ticker": st.column_config.TextColumn(width="small"),
                "Name": st.column_config.TextColumn(width="medium"),
                "Weight %": st.column_config.NumberColumn(min_value=0, max_value=100,
                                                            step=0.1, format="%.2f"),
                "Why": st.column_config.TextColumn(width="large"),
            },
        )

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button("⇄ Rebalance at NAV", type="primary", use_container_width=True):
                _do_rebalance(state, edited, thesis)
        with c2:
            if st.button("Reset form to current basket", use_container_width=True):
                del st.session_state.builder_rows
                st.rerun()

        st.caption("**Rebalance:** liquidates all positions at current NAV and reinvests "
                   "into the new basket. Trade history, cash log, and price history are preserved. "
                   "Full reset is in the Settings tab.")


def _do_rebalance(state: dict, df: pd.DataFrame, thesis: str) -> None:
    """Apply edited basket as a rebalance: liquidate at NAV, reinvest into new picks.

    Captures trade prices so chart markers and cost-basis calcs are accurate:
      - SELL prices come from existing holdings' lastPrice (free, no network).
      - BUY prices: kept-positions reuse their lastPrice; new tickers are quoted
        once via fetch_single_quote so the rebalance lands fully marked.
    """
    # Validate + normalise weights
    picks = []
    for _, row in df.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        wt = safe_num(row.get("Weight %"), 0)
        if not ticker or wt <= 0:
            continue
        picks.append({
            "ticker": ticker,
            "name":   str(row.get("Name") or ticker).strip(),
            "weight": wt,
            "why":    str(row.get("Why") or "").strip(),
        })
    if not picks:
        st.error("Add at least one ticker with a non-zero weight.")
        return

    total = sum(p["weight"] for p in picks)
    for p in picks:
        p["targetWeight"] = round(p["weight"] / total, 4)

    from app.state import get_portfolio_value
    from app import market
    nav = get_portfolio_value(state)
    ts = now_iso()

    # ─── Build price + quote lookups ───────────────────────────────────
    # Snapshot old holdings BEFORE we mutate state["holdings"]
    old_by_ticker = {h["ticker"]: h for h in state["holdings"]}

    price_lookup: dict[str, float] = {}    # ticker → price
    quote_lookup: dict[str, dict] = {}     # ticker → full quote dict (weekOHLC, prevClose)

    # Existing holdings: reuse lastPrice (no network call)
    for h in state["holdings"]:
        if safe_num(h.get("lastPrice"), 0) > 0:
            price_lookup[h["ticker"]] = h["lastPrice"]

    # Tickers entering the portfolio that we don't have a price for yet
    new_tickers_to_fetch = [p["ticker"] for p in picks if p["ticker"] not in price_lookup]
    fetch_failures: list[str] = []

    if new_tickers_to_fetch:
        progress = st.progress(
            0.0,
            text=f"Fetching prices for {len(new_tickers_to_fetch)} new ticker(s)…",
        )
        for i, ticker in enumerate(new_tickers_to_fetch):
            progress.progress(
                (i + 1) / len(new_tickers_to_fetch),
                text=f"Fetching {ticker}  ·  {i+1}/{len(new_tickers_to_fetch)}",
            )
            data = market.fetch_single_quote(ticker)
            if data and safe_num(data.get("price"), 0) > 0:
                price_lookup[ticker] = data["price"]
                quote_lookup[ticker] = data
            else:
                fetch_failures.append(ticker)
        progress.empty()

    # ─── Liquidate ─────────────────────────────────────────────────────
    proceeds = safe_num(state.get("cashUSD"), 0)
    for h in state["holdings"]:
        val = safe_num(h.get("currentValueUSD"), safe_num(h.get("initialUSD"), 0))
        if val > 0:
            proceeds += val
            sell_price = price_lookup.get(h["ticker"])  # may be None if never fetched
            sell_shares = safe_num(h.get("shares"))
            state["tradeLog"].insert(0, {
                "timestamp": ts, "action": "SELL", "ticker": h["ticker"],
                "tradeUSD": val,
                "shares": sell_shares if sell_shares > 0 else None,
                "price": sell_price,
                "reason": "Rebalance — full liquidation",
            })
            state["cashLog"].insert(0, {
                "timestamp": ts, "type": "SELL", "amount": val,
                "balance": proceeds, "note": f"Rebalance liquidation: {h['ticker']}",
            })

    # ─── Save thesis + basket ──────────────────────────────────────────
    state["aiThesis"] = thesis.strip() or None
    state["aiBasket"] = [{"ticker": p["ticker"], "name": p["name"],
                            "targetWeight": p["targetWeight"], "why": p["why"]}
                           for p in picks]

    # ─── Build new holdings (pre-marked when we have prices) ───────────
    state["cashUSD"] = 0.0
    state["holdings"] = []
    for p in picks:
        target_usd = round(nav * p["targetWeight"], 2)
        price = price_lookup.get(p["ticker"])
        quote = quote_lookup.get(p["ticker"])
        old_h = old_by_ticker.get(p["ticker"])

        # Carry forward weekOHLC + lastClose if we don't have fresh data
        last_close = (quote.get("prevClose") if quote
                      else (old_h.get("lastClose") if old_h else None))
        week_ohlc = (quote.get("weekOHLC") if quote
                     else (old_h.get("weekOHLC") if old_h else None))

        state["holdings"].append({
            "ticker": p["ticker"], "name": p["name"],
            "targetWeight": p["targetWeight"],
            "maxWeightPct": safe_num(state["settings"].get("maxWeightPct"), 20),
            "initialUSD": target_usd,
            "shares": round(target_usd / price, 6) if price else None,
            "lastPrice": price,
            "lastClose": last_close,
            "currentValueUSD": target_usd,
            "weekOHLC": week_ohlc,
            "lastFetchAt": now_iso() if price else None,
            "status": "Rebalanced" if price else "Rebalanced — awaiting quote fetch",
            "why": p["why"], "lastTradeAt": ts,
        })

    # ─── BUY trades for the new allocation ─────────────────────────────
    for p in picks:
        amt = round(nav * p["targetWeight"], 2)
        price = price_lookup.get(p["ticker"])
        state["tradeLog"].insert(0, {
            "timestamp": ts, "action": "BUY", "ticker": p["ticker"],
            "tradeUSD": amt,
            "shares": round(amt / price, 6) if price else None,
            "price": price,
            "reason": "Rebalance — new allocation",
        })
        state["cashLog"].insert(0, {
            "timestamp": ts, "type": "BUY", "amount": -amt, "balance": 0,
            "note": f"Rebalance entry: {p['ticker']}",
        })

    mark_valuation(state, "Rebalance")
    state["rebalanceLog"].insert(0, {
        "timestamp": ts,
        "navAtRebalance": nav,
        "positionCount": len(picks),
        "picks": [{"ticker": p["ticker"], "name": p["name"],
                    "weight": p["targetWeight"], "why": p["why"]} for p in picks],
    })

    commit()
    if "builder_rows" in st.session_state:
        del st.session_state.builder_rows

    # ─── Status message ────────────────────────────────────────────────
    fetched = len(new_tickers_to_fetch) - len(fetch_failures)
    msg = f"✓ Rebalanced {len(picks)} positions at NAV {to_usd(nav)}."
    if fetched > 0:
        msg += f"  Fresh quotes captured for {fetched} new ticker(s)."
    if fetch_failures:
        msg += f"  ⚠ Quote fetch failed for: {', '.join(fetch_failures)} — fetch quotes manually on the Trade tab."
    st.success(msg)
    st.rerun()


def _render_ai_workflow(state: dict) -> None:
    """3-step AI workflow with mode toggle."""
    with st.container(border=True):
        cols = st.columns([2, 1])
        with cols[0]:
            st.markdown("### AI workflow")
        with cols[1]:
            mode_label = "Mode: Fresh" if state.get("aiMode", "fresh") == "fresh" else "Mode: Evolve"
            st.markdown(f"<div style='text-align:right;'><span class='pill'>{mode_label}</span></div>",
                        unsafe_allow_html=True)

        st.caption("Three steps. Generate a tailored prompt, paste it into your AI of choice "
                   "(Claude, ChatGPT, Perplexity), then drop the JSON response back here.")

        # Mode toggle
        mode = st.radio(
            "AI mode",
            options=["fresh", "evolve"],
            format_func=lambda m: "Fresh portfolio" if m == "fresh" else "Evolve current portfolio",
            index=0 if state.get("aiMode", "fresh") == "fresh" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="ai_mode_radio",
        )
        if mode != state.get("aiMode"):
            state["aiMode"] = mode
            commit()

        # Step 1
        st.markdown("---")
        st.markdown("**STEP 1 · Generate the prompt**")
        c1, c2 = st.columns([1, 4])
        with c1:
            gen_btn = st.button("✦ Generate prompt", key="gen_prompt_btn", type="primary")
        with c2:
            st.caption("Calls Gemini with the right meta-instructions for the chosen mode.")

        if gen_btn:
            try:
                with st.spinner("Asking Gemini to draft the prompt…"):
                    prompt = ai.generate_portfolio_prompt(state, mode)
                    st.session_state.ai_generated_prompt = prompt
                st.success(f"✓ Prompt ready ({mode} mode)")
            except Exception as e:
                st.error(f"Error: {e}")

        if "ai_generated_prompt" in st.session_state:
            st.text_area("Generated prompt — copy this into your AI",
                          value=st.session_state.ai_generated_prompt,
                          height=240, key="prompt_output")

        # Step 2
        st.markdown("---")
        st.markdown("**STEP 2 · Run it in your AI**")
        st.caption("Paste the prompt into Claude / ChatGPT / Perplexity / Gemini. "
                   "Wait for the JSON response (it will look like `[{\"ticker\":\"NVDA\",...}]`).")

        # Step 3
        st.markdown("---")
        st.markdown("**STEP 3 · Paste the response**")
        json_in = st.text_area(
            "Paste the full JSON array (or the whole AI response — we tolerate surrounding text)",
            height=140, key="json_import_field",
        )
        if st.button("⇩ Import & preview in builder", key="import_btn"):
            if not json_in.strip():
                st.error("Paste the AI response first.")
            else:
                try:
                    picks, thesis = ai.parse_picks_json(json_in)
                    # Replace builder rows
                    st.session_state.builder_rows = pd.DataFrame([
                        {
                            "Ticker": p["ticker"],
                            "Name": p["name"],
                            "Weight %": round(p["weight"] * 100, 2),
                            "Why": p["why"],
                        }
                        for p in picks
                    ])
                    if thesis:
                        # Pre-fill thesis (overwrite session state for the textarea)
                        st.session_state.builder_thesis = thesis
                    st.success(f"✓ Imported {len(picks)} picks. Scroll up to review weights, then click Rebalance.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Parse error: {e}")


def render() -> None:
    state = get_state()
    _render_basket_editor(state)
    _render_ai_workflow(state)
