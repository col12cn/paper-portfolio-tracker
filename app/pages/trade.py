"""Trade tab: holdings desk + add new + cash management."""
from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime

from app.state import get_state, commit, mark_valuation, get_portfolio_value
from app.helpers import safe_num, to_usd, signed_pct, fmt_volume, fmt_rel_time, now_iso
from app import market


# ────────────────────────────────────────────────────────────────────
# DRILL-DOWN (modal dialog)
# ────────────────────────────────────────────────────────────────────

@st.dialog("Position drill-down", width="large")
def _drill_down(state: dict, ticker: str) -> None:
    h = next((x for x in state["holdings"] if x["ticker"] == ticker), None)
    if not h:
        st.error("Position not found")
        return

    nav = get_portfolio_value(state) or 1
    wt = safe_num(h.get("currentValueUSD"), 0) / nav * 100
    tgt = safe_num(h.get("targetWeight"), 0) * 100
    initial = safe_num(h.get("initialUSD"), 0)
    current = safe_num(h.get("currentValueUSD"), 0)
    pos_return = ((current - initial) / initial * 100) if initial > 0 else None

    wk = h.get("weekOHLC")
    wk_pct = ((wk["close"] - wk["open"]) / wk["open"] * 100) if wk and wk.get("open") else None

    st.markdown(f"## {h['ticker']}  &nbsp; <span style='font-size:14px;color:#a8b4d8;font-weight:400;'>{h['name']}</span>",
                 unsafe_allow_html=True)
    if h.get("why"):
        st.caption(h["why"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"${h['lastPrice']:.2f}" if h.get("lastPrice") else "—",
              delta=f"{fmt_rel_time(h.get('lastFetchAt'))}" if h.get("lastFetchAt") else "never")
    c2.metric("Position value", to_usd(current),
              delta=f"{wt:.2f}% (tgt {tgt:.1f}%)", delta_color="off")
    if pos_return is not None:
        c3.metric("P/L vs cost", to_usd(current - initial),
                  delta=f"{pos_return:+.2f}%",
                  delta_color="normal" if pos_return >= 0 else "inverse")
    else:
        c3.metric("P/L vs cost", "—")
    if wk_pct is not None:
        c4.metric("Week change", f"{wk_pct:+.2f}%",
                  delta=f"{wk['fromDate']} → {wk['toDate']}", delta_color="off")
    else:
        c4.metric("Week change", "—")

    # ─── Tag editor ──────────────────────────────────────────────
    # Cross-cut analysis: tag this position by theme (AI, defensive, etc.)
    h.setdefault("tags", [])
    # Suggest tags from anything that already exists across the portfolio
    all_existing_tags = sorted({t for hh in state.get("holdings", [])
                                  for t in (hh.get("tags") or [])})
    st.markdown("**Tags** &nbsp; <span class='muted-text' style='font-size:11px;'>"
                "for cross-cut analysis on the Insights tab</span>",
                unsafe_allow_html=True)
    selected_tags = st.multiselect(
        "Tags", options=sorted(set(all_existing_tags + h["tags"])),
        default=h["tags"], key=f"tags_{ticker}",
        label_visibility="collapsed",
        placeholder="No tags · pick existing or add new below",
    )
    new_tag_col, save_tag_col = st.columns([3, 1])
    with new_tag_col:
        new_tag = st.text_input("Add new tag", key=f"new_tag_{ticker}",
                                  label_visibility="collapsed",
                                  placeholder="Type a new tag and click Save (e.g. AI infra, defensive, EM)")
    with save_tag_col:
        if st.button("Save tags", key=f"save_tags_{ticker}", use_container_width=True):
            new_tags = list(selected_tags)
            if new_tag.strip():
                t = new_tag.strip()
                if t not in new_tags:
                    new_tags.append(t)
            h["tags"] = sorted(set(new_tags))
            commit()
            st.success(f"✓ Tags saved: {', '.join(h['tags']) if h['tags'] else '(none)'}")
            st.rerun()

    if wk:
        source_pill = (f"<span class='pill pill-good'>SOURCE · YFINANCE</span>"
                       if wk.get("source") == "yfinance"
                       else f"<span class='pill pill-warn'>SNAPSHOT · {wk.get('days', 0)}/5 days</span>")
        st.markdown(f"**Week OHLCV** &nbsp; {source_pill}", unsafe_allow_html=True)
        df = pd.DataFrame([{
            "Open": f"${wk['open']:.2f}",
            "High": f"${wk['high']:.2f}",
            "Low":  f"${wk['low']:.2f}",
            "Close": f"${wk['close']:.2f}",
            "Volume": fmt_volume(wk.get("volume")) if wk.get("volume") else "n/a",
            "% chg": f"{wk_pct:+.2f}%" if wk_pct is not None else "—",
        }])
        st.dataframe(df, hide_index=True, use_container_width=True)

    # Trades for this ticker
    trades = [t for t in state.get("tradeLog", [])
              if t.get("ticker") == ticker and t.get("action") != "INIT"][:20]
    st.markdown(f"**Recent trades · {len(trades)}**")
    if trades:
        df_tr = pd.DataFrame([{
            "When": datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d"),
            "Action": t["action"],
            "USD": to_usd(t.get("tradeUSD")) if isinstance(t.get("tradeUSD"), (int, float)) else "—",
            "Shares": f"{t['shares']:.4f}" if isinstance(t.get("shares"), (int, float)) else "—",
            "Price": f"${t['price']:.2f}" if t.get("price") else "—",
        } for t in trades])
        st.dataframe(df_tr, hide_index=True, use_container_width=True)
    else:
        st.caption("No trades for this ticker yet.")

    # ─── Ask Gemini about this ticker (inline within the dialog) ───
    st.markdown("---")
    st.markdown(f"**✦ Ask Gemini about {ticker}**")

    default_q = (f"Detailed view on {ticker}: current setup, key catalysts in the next "
                 f"90 days, main risks, and whether to add / trim / hold given my full portfolio.")

    # Initialise the question once per dialog open; don't fight value-vs-key warnings
    q_key = f"q_{ticker}"
    st.session_state.setdefault(q_key, default_q)

    question = st.text_area(
        "Edit the question if you like, then Ask",
        key=q_key,
        height=90,
        label_visibility="collapsed",
    )

    c_ask, c_clear = st.columns([1, 1])
    with c_ask:
        ask_clicked = st.button("Ask Gemini", key=f"ask_btn_{ticker}",
                                  type="primary", use_container_width=True)
    with c_clear:
        if st.button("Reset question", key=f"reset_q_{ticker}",
                      use_container_width=True):
            st.session_state[q_key] = default_q
            st.session_state.pop(f"answer_{ticker}", None)
            st.rerun()

    if ask_clicked and question.strip():
        with st.spinner(f"Asking Gemini about {ticker}…"):
            try:
                from app import ai as ai_mod
                answer = ai_mod.ask_gemini(state, question.strip())
                st.session_state[f"answer_{ticker}"] = answer
                # Mirror to global ask history so it shows up on the Overview tab too
                state.setdefault("askHistory", []).insert(0, {
                    "timestamp": now_iso(),
                    "question": question.strip(),
                    "answer": answer,
                })
                state["askHistory"] = state["askHistory"][:10]
                commit()
            except Exception as e:
                st.error(f"Error: {e}")

    # Show the cached answer if we have one
    answer = st.session_state.get(f"answer_{ticker}")
    if answer:
        st.markdown(
            f"<div class='insight' style='margin-top:8px;'>{answer}</div>",
            unsafe_allow_html=True,
        )


# ────────────────────────────────────────────────────────────────────
# HOLDINGS TABLE
# ────────────────────────────────────────────────────────────────────

def _render_holdings_table(state: dict) -> None:
    holdings = state.get("holdings", [])
    if not holdings:
        st.info("No holdings yet. Build one in the Build tab.")
        return

    nav = get_portfolio_value(state) or 1
    rows = []
    for h in holdings:
        cur_pct = safe_num(h.get("currentValueUSD"), 0) / nav * 100
        tgt_pct = safe_num(h.get("targetWeight"), 0) * 100
        diff = cur_pct - tgt_pct
        day_chg = None
        if h.get("lastPrice") and h.get("lastClose"):
            day_chg = (h["lastPrice"] - h["lastClose"]) / h["lastClose"] * 100
        wk = h.get("weekOHLC")
        wk_pct = ((wk["close"] - wk["open"]) / wk["open"] * 100) if wk and wk.get("open") else None
        wk_range = (f"${wk['low']:.2f} → ${wk['high']:.2f}" if wk else "—")
        wk_vol = fmt_volume(wk.get("volume")) if wk and wk.get("volume") is not None else (
            "n/a" if wk else "—"
        )
        days_tag = ""
        if wk and wk.get("source") == "snapshot" and wk.get("days", 5) < 5:
            days_tag = f" ({wk['days']}/5)"
        fresh = ""
        if h.get("lastFetchAt"):
            rel = fmt_rel_time(h["lastFetchAt"])
            fresh = f"⚠ {rel}" if "d ago" in rel and int(rel.split("d")[0]) >= 1 else rel

        tag_str = ", ".join(h.get("tags", [])[:3]) if h.get("tags") else "—"
        if h.get("tags") and len(h["tags"]) > 3:
            tag_str += f" +{len(h['tags']) - 3}"

        rows.append({
            "Ticker": h["ticker"],
            "Name": h["name"][:22],
            "Tags": tag_str,
            "Value": to_usd(h.get("currentValueUSD")),
            "Cur %": f"{cur_pct:.2f}%",
            "Tgt %": f"{tgt_pct:.1f}%" if tgt_pct > 0 else "—",
            "Δ tgt": f"{diff:+.2f}pp" if tgt_pct > 0 else "—",
            "Price": f"${h['lastPrice']:.2f}" if h.get("lastPrice") else "—",
            "Day chg": f"{day_chg:+.2f}%" if day_chg is not None else "—",
            "Wk range": wk_range,
            "Wk %": f"{wk_pct:+.2f}%{days_tag}" if wk_pct is not None else "—",
            "Wk vol": wk_vol,
            "Updated": fresh,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    # Per-position trade controls (one row at a time via selector)
    st.markdown("##### Trade a position")
    cols = st.columns([2, 2, 1, 1, 1, 1])
    with cols[0]:
        ticker_sel = st.selectbox("Ticker",
                                    options=[h["ticker"] for h in holdings],
                                    key="trade_ticker_sel")
    with cols[1]:
        amt = st.number_input("USD amount", min_value=0.0, step=10.0, value=0.0,
                                key="trade_amt_input")
    with cols[2]:
        buy = st.button("Buy", use_container_width=True, key="trade_buy")
    with cols[3]:
        sell = st.button("Sell", type="secondary", use_container_width=True, key="trade_sell")
    with cols[4]:
        rebal = st.button("→ tgt", use_container_width=True, key="trade_rebal",
                           help="Trade toward target weight")
    with cols[5]:
        drill = st.button("View →", use_container_width=True, key="trade_drill")

    # Optional rationale — gets stored on the trade for journaling/learning
    rationale = st.text_input(
        "Why? (optional — gets logged with the trade for future review)",
        key="trade_rationale_input",
        placeholder="e.g. Trim before earnings, or rotate into defensive after Fed decision",
    )

    selected = next(h for h in holdings if h["ticker"] == ticker_sel)

    if buy and amt > 0:
        _execute_trade(state, ticker_sel, "BUY", amt, reason=rationale.strip())
    if sell and amt > 0:
        _execute_trade(state, ticker_sel, "SELL", amt, reason=rationale.strip())
    if rebal:
        _rebalance_to_target(state, ticker_sel, reason=rationale.strip())
    if drill:
        _drill_down(state, ticker_sel)

    # Current position status display for selected ticker
    s_price = safe_num(selected.get("lastPrice"), 0)
    s_val = safe_num(selected.get("currentValueUSD"), 0)
    s_wt = (s_val / nav * 100) if nav > 0 else 0
    s_tgt = safe_num(selected.get("targetWeight"), 0) * 100

    st.caption(
        f"**{ticker_sel}** · price ${s_price:.2f} · value {to_usd(s_val)} · "
        f"weight {s_wt:.2f}% (target {s_tgt:.1f}%) · "
        f"close position with the ✕ option in row controls (drill-down)"
    )


def _execute_trade(state: dict, ticker: str, action: str, amt_usd: float,
                     reason: str = "") -> None:
    """Execute a buy or sell. Optional `reason` gets logged to the trade."""
    h = next((x for x in state["holdings"] if x["ticker"] == ticker), None)
    if not h:
        st.error("Position not found"); return
    price = safe_num(h.get("lastPrice"), 0)
    if price <= 0:
        st.error("No live price — fetch quotes first"); return

    if action == "BUY":
        if safe_num(state.get("cashUSD"), 0) < amt_usd:
            st.error(f"Insufficient cash ({to_usd(state.get('cashUSD'))})"); return
        shares = amt_usd / price
        h["shares"] = round(safe_num(h.get("shares"), 0) + shares, 6)
        h["currentValueUSD"] = round(h["shares"] * price, 2)
        state["cashUSD"] = round(safe_num(state.get("cashUSD"), 0) - amt_usd, 2)
        h["lastTradeAt"] = now_iso(); h["status"] = "Manual buy"
        state["cashLog"].insert(0, {
            "timestamp": now_iso(), "type": "BUY", "amount": -amt_usd,
            "balance": state["cashUSD"],
            "note": f"Bought {ticker} — {shares:.4f} sh @ ${price:.2f}"
                     + (f" · {reason}" if reason else ""),
        })
        state["tradeLog"].insert(0, {
            "timestamp": now_iso(), "action": "BUY", "ticker": ticker,
            "tradeUSD": amt_usd, "shares": round(shares, 6), "price": price,
            "reason": reason or "Manual buy",
        })
        st.success(f"✓ Bought {to_usd(amt_usd)} of {ticker} ({shares:.4f} sh)")
    else:  # SELL
        max_sell = safe_num(h.get("currentValueUSD"), 0)
        if max_sell <= 0:
            st.error("Nothing to sell"); return
        sell_usd = min(amt_usd, max_sell)
        shares = sell_usd / price
        h["shares"] = round(max(0, safe_num(h.get("shares"), 0) - shares), 6)
        h["currentValueUSD"] = round(h["shares"] * price, 2)
        state["cashUSD"] = round(safe_num(state.get("cashUSD"), 0) + sell_usd, 2)
        h["lastTradeAt"] = now_iso(); h["status"] = "Manual sell"
        state["cashLog"].insert(0, {
            "timestamp": now_iso(), "type": "SELL", "amount": sell_usd,
            "balance": state["cashUSD"],
            "note": f"Sold {ticker} — {shares:.4f} sh @ ${price:.2f}"
                     + (f" · {reason}" if reason else ""),
        })
        state["tradeLog"].insert(0, {
            "timestamp": now_iso(), "action": "SELL", "ticker": ticker,
            "tradeUSD": sell_usd, "shares": round(shares, 6), "price": price,
            "reason": reason or "Manual sell",
        })
        st.success(f"✓ Sold {to_usd(sell_usd)} of {ticker}"
                   + (" (full position)" if sell_usd < amt_usd else ""))

    mark_valuation(state, f"Manual {action.lower()}: {ticker}")
    commit()
    st.rerun()


def _rebalance_to_target(state: dict, ticker: str, reason: str = "") -> None:
    """One-click trade toward target weight. Reason passed through."""
    h = next((x for x in state["holdings"] if x["ticker"] == ticker), None)
    if not h: return
    tgt = safe_num(h.get("targetWeight"), 0)
    if tgt <= 0:
        st.error("No target weight set"); return
    price = safe_num(h.get("lastPrice"), 0)
    if price <= 0:
        st.error("No live price — fetch quotes first"); return

    nav = get_portfolio_value(state)
    target_usd = nav * tgt
    delta = target_usd - safe_num(h.get("currentValueUSD"), 0)
    if abs(delta) < 1:
        st.info("✓ Already at target"); return
    action = "BUY" if delta > 0 else "SELL"
    rebal_reason = reason or "Rebalance toward target weight"
    _execute_trade(state, ticker, action, abs(delta), reason=rebal_reason)


def _rebalance_all(state: dict) -> None:
    """Rebalance every position with > 0.5% NAV deviation. Sells first, then buys."""
    nav = get_portfolio_value(state)
    candidates = []
    for h in state["holdings"]:
        tgt = safe_num(h.get("targetWeight"), 0)
        if tgt <= 0 or safe_num(h.get("lastPrice"), 0) <= 0:
            continue
        target_usd = nav * tgt
        delta = abs(target_usd - safe_num(h.get("currentValueUSD"), 0))
        if delta > nav * 0.005:
            candidates.append(h)
    if not candidates:
        st.info("All positions within 0.5% of target.")
        return
    # Sort: sells first to free cash
    actions = []
    for h in candidates:
        tgt = safe_num(h.get("targetWeight"), 0)
        delta = nav * tgt - safe_num(h.get("currentValueUSD"), 0)
        actions.append((h["ticker"], "BUY" if delta > 0 else "SELL", abs(delta)))
    actions.sort(key=lambda a: 0 if a[1] == "SELL" else 1)
    for ticker, action, amt in actions:
        try:
            _execute_trade(state, ticker, action, amt)
        except Exception:
            continue


def _close_position(state: dict, ticker: str) -> None:
    """Close entire position, return proceeds to cash."""
    h = next((x for x in state["holdings"] if x["ticker"] == ticker), None)
    if not h: return
    proceeds = safe_num(h.get("currentValueUSD"), 0)
    if proceeds > 0:
        state["cashUSD"] = round(safe_num(state.get("cashUSD"), 0) + proceeds, 2)
        state["cashLog"].insert(0, {
            "timestamp": now_iso(), "type": "SELL", "amount": proceeds,
            "balance": state["cashUSD"], "note": f"Closed position: {ticker}",
        })
        state["tradeLog"].insert(0, {
            "timestamp": now_iso(), "action": "CLOSE", "ticker": ticker,
            "tradeUSD": proceeds, "shares": safe_num(h.get("shares"), 0),
            "price": safe_num(h.get("lastPrice"), 0) or None,
        })
    state["holdings"] = [x for x in state["holdings"] if x["ticker"] != ticker]
    mark_valuation(state, f"Position closed: {ticker}")
    commit()
    st.success(f"✓ Closed {ticker}")
    st.rerun()


# ────────────────────────────────────────────────────────────────────
# ADD NEW POSITION
# ────────────────────────────────────────────────────────────────────

def _render_add_new_position(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### Add new position")
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        with c1:
            new_ticker = st.text_input("Ticker", key="new_ticker_input").upper().strip()
        with c2:
            new_name = st.text_input("Name (optional)", key="new_name_input")
        with c3:
            new_amt = st.number_input("Amount (USD)", min_value=0.0, step=10.0, value=0.0,
                                        key="new_amt_input")
        with c4:
            st.markdown("&nbsp;", unsafe_allow_html=True)  # spacer
            add_btn = st.button("Add to portfolio", use_container_width=True,
                                  type="primary", key="new_add_btn")

        if add_btn:
            if not new_ticker:
                st.error("Enter a ticker"); return
            if new_amt <= 0:
                st.error("Enter a USD amount"); return
            if safe_num(state.get("cashUSD"), 0) < new_amt:
                st.error(f"Insufficient cash ({to_usd(state.get('cashUSD'))})"); return

            with st.spinner(f"Fetching {new_ticker}..."):
                data = market.fetch_single_quote(new_ticker)
            if not data:
                st.error(f"No price found for {new_ticker}"); return

            price = data["price"]
            shares_delta = new_amt / price
            existing = next((h for h in state["holdings"] if h["ticker"] == new_ticker), None)
            if existing:
                existing["shares"] = round(safe_num(existing.get("shares"), 0) + shares_delta, 6)
                existing["currentValueUSD"] = round(existing["shares"] * price, 2)
                existing["lastPrice"] = price
                existing["lastTradeAt"] = now_iso()
                existing["status"] = "Topped up"
            else:
                state["holdings"].append({
                    "ticker": new_ticker,
                    "name": new_name.strip() or new_ticker,
                    "targetWeight": 0.0,
                    "maxWeightPct": safe_num(state["settings"].get("maxWeightPct"), 20),
                    "initialUSD": new_amt,
                    "shares": round(shares_delta, 6),
                    "lastPrice": price, "lastClose": price,
                    "currentValueUSD": round(shares_delta * price, 2),
                    "weekOHLC": data.get("weekOHLC"),
                    "lastFetchAt": now_iso(),
                    "status": "New position", "why": "", "lastTradeAt": now_iso(),
                })
            state["cashUSD"] = round(safe_num(state.get("cashUSD"), 0) - new_amt, 2)
            state["cashLog"].insert(0, {
                "timestamp": now_iso(), "type": "BUY", "amount": -new_amt,
                "balance": state["cashUSD"],
                "note": f"{'Top-up' if existing else 'New position'}: {new_ticker} @ ${price:.2f}",
            })
            state["tradeLog"].insert(0, {
                "timestamp": now_iso(), "action": "BUY", "ticker": new_ticker,
                "tradeUSD": new_amt, "shares": round(shares_delta, 6), "price": price,
            })
            mark_valuation(state, f"{'Top-up' if existing else 'New position'}: {new_ticker}")
            commit()
            st.success(f"✓ {'Topped up' if existing else 'Opened'} {new_ticker} at ${price:.2f}")
            st.rerun()


# ────────────────────────────────────────────────────────────────────
# CASH MANAGEMENT
# ────────────────────────────────────────────────────────────────────

def _render_cash(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### Cash management")
        nav = get_portfolio_value(state)
        cash = safe_num(state.get("cashUSD"), 0)
        cash_pct = (cash / nav * 100) if nav > 0 else 0
        deposited = sum(safe_num(c.get("amount")) for c in state.get("cashLog", []) if c.get("type") == "DEPOSIT")
        withdrawn = abs(sum(safe_num(c.get("amount")) for c in state.get("cashLog", []) if c.get("type") == "WITHDRAW"))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current cash", to_usd(cash), delta=f"{cash_pct:.1f}% of NAV", delta_color="off")
        c2.metric("Total deposited", to_usd(deposited))
        c3.metric("Total withdrawn", to_usd(withdrawn))
        c4.metric("Net external", to_usd(deposited - withdrawn))

        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**Deposit**")
            dep_amt = st.number_input("Amount", min_value=0.0, step=50.0, value=0.0, key="dep_amt")
            dep_note = st.text_input("Note", key="dep_note", placeholder="e.g. Monthly contribution")
            if st.button("Deposit", use_container_width=True, key="dep_btn"):
                if dep_amt > 0:
                    state["cashUSD"] = round(cash + dep_amt, 2)
                    state["cashLog"].insert(0, {
                        "timestamp": now_iso(), "type": "DEPOSIT",
                        "amount": dep_amt, "balance": state["cashUSD"],
                        "note": dep_note or "Deposit",
                    })
                    mark_valuation(state, f"Deposit: ${dep_amt:.2f}")
                    commit(); st.success(f"✓ Deposited {to_usd(dep_amt)}"); st.rerun()
        with d2:
            st.markdown("**Withdraw**")
            wd_amt = st.number_input("Amount", min_value=0.0, step=50.0, value=0.0, key="wd_amt")
            wd_note = st.text_input("Note", key="wd_note", placeholder="e.g. Profit taking")
            if st.button("Withdraw", use_container_width=True, key="wd_btn"):
                if wd_amt <= 0:
                    st.error("Enter a positive amount")
                elif wd_amt > cash:
                    st.error(f"Insufficient cash ({to_usd(cash)})")
                else:
                    state["cashUSD"] = round(cash - wd_amt, 2)
                    state["cashLog"].insert(0, {
                        "timestamp": now_iso(), "type": "WITHDRAW",
                        "amount": -wd_amt, "balance": state["cashUSD"],
                        "note": wd_note or "Withdrawal",
                    })
                    mark_valuation(state, f"Withdraw: ${wd_amt:.2f}")
                    commit(); st.success(f"✓ Withdrew {to_usd(wd_amt)}"); st.rerun()

        # Recent cash log
        st.markdown("**Recent cash flow**")
        if state.get("cashLog"):
            df = pd.DataFrame([{
                "When": datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M"),
                "Type": c["type"],
                "Amount": to_usd(c["amount"]),
                "Balance after": to_usd(c["balance"]),
                "Note": c.get("note", ""),
            } for c in state["cashLog"][:30]])
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.caption("No cash flow events yet.")


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────

def render() -> None:
    state = get_state()

    # Engine metrics
    nav = get_portfolio_value(state)
    cash = safe_num(state.get("cashUSD"), 0)
    cash_pct = (cash / nav * 100) if nav > 0 else 0
    pnl = nav - safe_num(state["settings"].get("startingCapital"), 1000)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("NAV", to_usd(nav))
    c2.metric("Cash", to_usd(cash))
    c3.metric("Cash weight", f"{cash_pct:.1f}%")
    c4.metric("Positions", str(len(state.get("holdings", []))))
    c5.metric("P/L vs start", to_usd(pnl),
              delta_color="normal" if pnl >= 0 else "inverse")

    # Holdings desk
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.markdown("### Holdings · trade desk")
        with c2:
            if st.button("⟳ Fetch quotes", use_container_width=True, type="primary",
                          key="fetch_quotes_main"):
                progress = st.progress(0.0, text="Starting fetch…")
                def cb(i, total, ticker):
                    progress.progress((i+1)/total, text=f"Fetching {ticker} ({i+1}/{total})")
                ok, fails, source = market.fetch_live_market_data(state, progress_cb=cb)
                progress.empty()
                commit()
                if fails:
                    st.warning(f"Done with issues — {ok} ok, source: {source}\n\n" + "\n".join(fails))
                else:
                    st.success(f"✓ Updated {ok} tickers · source: {source}")
                st.rerun()
        with c3:
            if st.button("⇄ Rebal all → tgt", use_container_width=True,
                          key="rebal_all_btn"):
                _rebalance_all(state)
                commit(); st.rerun()

        st.caption("`→ tgt` auto-trades toward your target weight. "
                   "Use the View button to see trade history, OHLCV breakdown, and ask Gemini.")
        _render_holdings_table(state)

    _render_add_new_position(state)
    _render_cash(state)
