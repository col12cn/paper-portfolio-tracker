"""Watchlist tab — idea pipeline before positions become live.

Track tickers you're considering. Live prices fetched on demand. Set an alert
target so you can see at a glance how close each idea is to your trigger.
One-click promotion to a real position via the Trade tab's add-position flow.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd

from app.state import get_state, commit
from app.helpers import safe_num, to_usd, signed_pct, now_iso
from app import market


def _add_to_watchlist(state: dict, ticker: str, name: str,
                       alert_price: float, notes: str) -> tuple[bool, str]:
    """Try to add a ticker. Returns (success, message)."""
    ticker = ticker.upper().strip()
    if not ticker:
        return False, "Ticker required."

    # Avoid duplicates
    existing = next((w for w in state["watchlist"] if w["ticker"] == ticker), None)
    if existing:
        return False, f"{ticker} is already on your watchlist."

    # Live quote fetch to validate + populate current price
    data = market.fetch_single_quote(ticker)
    if not data or safe_num(data.get("price"), 0) <= 0:
        return False, f"Could not fetch a price for {ticker}. Check the symbol."

    state["watchlist"].append({
        "ticker": ticker,
        "name": (name or ticker).strip(),
        "addedAt": now_iso(),
        "addedPrice": float(data["price"]),
        "alertPrice": float(alert_price) if alert_price > 0 else None,
        "lastPrice": float(data["price"]),
        "lastFetchAt": now_iso(),
        "notes": (notes or "").strip(),
    })
    return True, f"Added {ticker} at ${data['price']:.2f}."


def _refresh_watchlist_quotes(state: dict) -> tuple[int, list[str]]:
    """Re-quote every watchlist item. Returns (count_ok, failures)."""
    fails = []
    ok = 0
    for w in state["watchlist"]:
        data = market.fetch_single_quote(w["ticker"])
        if data and safe_num(data.get("price"), 0) > 0:
            w["lastPrice"] = float(data["price"])
            w["lastFetchAt"] = now_iso()
            ok += 1
        else:
            fails.append(w["ticker"])
    return ok, fails


def _promote_to_portfolio(state: dict, ticker: str, amt_usd: float) -> tuple[bool, str]:
    """Add a watchlist ticker as a portfolio position (uses cash). Returns (ok, msg)."""
    if amt_usd <= 0:
        return False, "Amount must be positive."
    if safe_num(state.get("cashUSD"), 0) < amt_usd:
        return False, f"Insufficient cash ({to_usd(state.get('cashUSD'))})."

    w = next((x for x in state["watchlist"] if x["ticker"] == ticker), None)
    if not w:
        return False, "Watchlist item not found."

    data = market.fetch_single_quote(ticker)
    if not data or safe_num(data.get("price"), 0) <= 0:
        return False, f"Quote fetch failed for {ticker}."

    price = float(data["price"])
    shares = amt_usd / price

    # Check if already in holdings (top-up) or new position
    existing = next((h for h in state["holdings"] if h["ticker"] == ticker), None)
    if existing:
        existing["shares"] = round(safe_num(existing.get("shares"), 0) + shares, 6)
        existing["currentValueUSD"] = round(existing["shares"] * price, 2)
        existing["lastPrice"] = price
        existing["lastTradeAt"] = now_iso()
        existing["status"] = "Topped up from watchlist"
    else:
        state["holdings"].append({
            "ticker": ticker,
            "name": w.get("name", ticker),
            "targetWeight": 0.0,
            "maxWeightPct": safe_num(state["settings"].get("maxWeightPct"), 20),
            "initialUSD": amt_usd,
            "shares": round(shares, 6),
            "lastPrice": price, "lastClose": data.get("prevClose"),
            "currentValueUSD": round(shares * price, 2),
            "weekOHLC": data.get("weekOHLC"),
            "lastFetchAt": now_iso(),
            "status": "Promoted from watchlist",
            "why": w.get("notes", ""),
            "lastTradeAt": now_iso(),
        })

    state["cashUSD"] = round(safe_num(state.get("cashUSD"), 0) - amt_usd, 2)
    state["cashLog"].insert(0, {
        "timestamp": now_iso(), "type": "BUY", "amount": -amt_usd,
        "balance": state["cashUSD"],
        "note": f"{'Top-up' if existing else 'New position'} from watchlist: {ticker} @ ${price:.2f}",
    })
    state["tradeLog"].insert(0, {
        "timestamp": now_iso(), "action": "BUY", "ticker": ticker,
        "tradeUSD": amt_usd, "shares": round(shares, 6), "price": price,
        "reason": f"Promoted from watchlist · {w.get('notes', '')[:80]}",
    })

    # Remove from watchlist
    state["watchlist"] = [x for x in state["watchlist"] if x["ticker"] != ticker]
    return True, f"Opened {ticker} at ${price:.2f}, removed from watchlist."


def _watchlist_table(state: dict) -> None:
    wl = state.get("watchlist", [])
    if not wl:
        st.markdown(
            "<div style='text-align:center;padding:36px;color:var(--muted);"
            "font-style:italic;border:1px dashed var(--line);border-radius:6px;'>"
            "No tickers on your watchlist yet. Add one below to start tracking ideas.</div>",
            unsafe_allow_html=True,
        )
        return

    rows = []
    for w in wl:
        cur = safe_num(w.get("lastPrice"), 0)
        added = safe_num(w.get("addedPrice"), 0)
        alert = safe_num(w.get("alertPrice"), 0)

        chg_since_added = ((cur - added) / added * 100) if added > 0 else None
        gap_to_alert = ((alert - cur) / cur * 100) if (alert > 0 and cur > 0) else None
        triggered = "🎯" if (alert > 0 and (
            (alert >= added and cur >= alert) or (alert < added and cur <= alert)
        )) else ""

        rows.append({
            "Ticker": w["ticker"] + (" " + triggered if triggered else ""),
            "Name": w.get("name", "")[:24],
            "Added at": f"${added:.2f}",
            "Current": f"${cur:.2f}" if cur > 0 else "—",
            "Δ since added": signed_pct(chg_since_added) if chg_since_added is not None else "—",
            "Alert": f"${alert:.2f}" if alert > 0 else "—",
            "Gap to alert": signed_pct(gap_to_alert) if gap_to_alert is not None else "—",
            "Notes": (w.get("notes", "") or "")[:48],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    # Per-row controls (single-row selector pattern)
    st.markdown("##### Action on a watchlist item")
    cols = st.columns([2, 2, 1, 1])
    with cols[0]:
        sel_ticker = st.selectbox("Ticker", [w["ticker"] for w in wl],
                                    key="wl_action_ticker", label_visibility="collapsed")
    with cols[1]:
        promote_amt = st.number_input("USD to invest", min_value=0.0, step=10.0, value=0.0,
                                          key="wl_promote_amt", label_visibility="collapsed",
                                          placeholder="USD to invest")
    with cols[2]:
        if st.button("→ Open position", use_container_width=True, key="wl_promote_btn"):
            if promote_amt <= 0:
                st.error("Enter a positive amount.")
            else:
                ok, msg = _promote_to_portfolio(state, sel_ticker, promote_amt)
                if ok:
                    commit(); st.success(msg); st.rerun()
                else:
                    st.error(msg)
    with cols[3]:
        if st.button("✕ Remove", type="secondary", use_container_width=True, key="wl_remove_btn"):
            state["watchlist"] = [w for w in wl if w["ticker"] != sel_ticker]
            commit(); st.success(f"Removed {sel_ticker}"); st.rerun()


def _add_form(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### Add to watchlist")
        with st.form("add_to_watchlist", clear_on_submit=True):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                ticker = st.text_input("Ticker", placeholder="NVDA")
            with c2:
                name = st.text_input("Name (optional)", placeholder="NVIDIA Corporation")
            with c3:
                alert = st.number_input("Alert price (optional)", min_value=0.0,
                                          step=1.0, value=0.0,
                                          help="Get a 🎯 indicator when current price crosses this level.")
            notes = st.text_area("Notes / thesis (optional)",
                                    placeholder="Why this could be interesting…",
                                    height=80)
            submitted = st.form_submit_button("Add to watchlist", type="primary")

        if submitted:
            if not ticker.strip():
                st.error("Ticker required.")
            else:
                with st.spinner(f"Fetching {ticker.upper().strip()}…"):
                    ok, msg = _add_to_watchlist(state, ticker, name, alert, notes)
                if ok:
                    commit(); st.success(msg); st.rerun()
                else:
                    st.error(msg)


def render() -> None:
    state = get_state()
    state.setdefault("watchlist", [])

    cols = st.columns([3, 1])
    with cols[0]:
        st.markdown("### Watchlist · idea pipeline")
        st.caption("Track ideas before they become positions. Set an alert price to "
                    "get a 🎯 indicator when a ticker crosses your trigger.")
    with cols[1]:
        if state["watchlist"]:
            if st.button("⟳ Refresh prices", use_container_width=True, type="primary"):
                with st.spinner("Refreshing watchlist quotes…"):
                    ok, fails = _refresh_watchlist_quotes(state)
                commit()
                if fails:
                    st.warning(f"Refreshed {ok} · failed: {', '.join(fails)}")
                else:
                    st.success(f"Refreshed {ok} ticker(s).")
                st.rerun()

    _watchlist_table(state)
    _add_form(state)
