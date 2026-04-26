"""Market data fetching.

Primary source: yfinance — free, no API key, full OHLCV with volume.
Fallback: Finnhub /quote (free tier) — used only if yfinance fails for a ticker.

Why this matters: the v8 HTML tracker relied on Finnhub /candle, which Finnhub
deprecated on free tier in 2024 (returns 403). yfinance has no such restriction.
"""
from __future__ import annotations
from typing import Any
import requests
import yfinance as yf
import pandas as pd
import streamlit as st

from app.helpers import safe_num, now_iso, today_iso


# ────────────────────────────────────────────────────────────────────
# yfinance — PRIMARY
# ────────────────────────────────────────────────────────────────────

def fetch_yfinance_data(ticker: str) -> dict | None:
    """Fetch quote + 5-day OHLCV via yfinance.

    Returns a dict shaped to match what fetch_live_market_data() expects:
        {
            'price': float, 'prevClose': float | None,
            'weekOHLC': {open, high, low, close, volume, days, fromDate, toDate, source},
            'source': 'yfinance'
        }
    Or None if the ticker is invalid / data unavailable.
    """
    try:
        tk = yf.Ticker(ticker)
        # Fetch last ~10 days to be safe; we slice to 5 trading days
        hist = tk.history(period="10d", interval="1d", auto_adjust=False)
        if hist.empty:
            return None

        # Most recent close = current/last price; the row before = prev close
        last_close = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None

        # Aggregate the last 5 trading days into weekly OHLCV
        last_5 = hist.tail(5)
        if len(last_5) >= 1:
            week_ohlc = {
                "open":   round(float(last_5["Open"].iloc[0]), 4),
                "high":   round(float(last_5["High"].max()), 4),
                "low":    round(float(last_5["Low"].min()), 4),
                "close":  round(last_close, 4),
                "volume": int(last_5["Volume"].sum()),
                "days":   int(len(last_5)),
                "fromDate": last_5.index[0].strftime("%Y-%m-%d"),
                "toDate":   last_5.index[-1].strftime("%Y-%m-%d"),
                "source":   "yfinance",
            }
        else:
            week_ohlc = None

        return {
            "price": last_close,
            "prevClose": prev_close,
            "weekOHLC": week_ohlc,
            "source": "yfinance",
        }
    except Exception as e:
        # Common: invalid ticker, network, yfinance internal parse errors
        return None


# ────────────────────────────────────────────────────────────────────
# Finnhub /quote — FALLBACK
# ────────────────────────────────────────────────────────────────────

def fetch_finnhub_quote(ticker: str, api_key: str) -> dict | None:
    """Fetch current quote from Finnhub /quote endpoint (works on free tier)."""
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": api_key},
            timeout=10,
        )
        r.raise_for_status()
        q = r.json()
        price = safe_num(q.get("c"), 0)
        if price <= 0:
            price = safe_num(q.get("pc"), 0)  # fallback to prev close
        if price <= 0:
            return None
        return {
            "price": price,
            "prevClose": safe_num(q.get("pc")) or None,
            # Today's intraday OHLC from the quote endpoint
            "intraday": {
                "o": safe_num(q.get("o"), price),
                "h": safe_num(q.get("h"), price),
                "l": safe_num(q.get("l"), price),
                "c": price,
            },
            "source": "finnhub-quote",
        }
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────
# WEEKLY OHLCV from accumulated /quote snapshots (Finnhub-only fallback path)
# ────────────────────────────────────────────────────────────────────

def aggregate_week_from_snaps(state: dict, ticker: str,
                                current_price: float | None = None) -> dict | None:
    """Build a weekly OHLC bar from up to 5 daily snapshots in priceSnap.
    Used when yfinance fails AND we're on Finnhub-only fallback. No volume.
    """
    snaps = [s for s in state.get("priceSnap", [])
             if s.get("ohlc") and ticker in s["ohlc"]]
    snaps = snaps[-5:]
    if not snaps:
        return None
    opens  = [safe_num(s["ohlc"][ticker].get("o")) for s in snaps if s["ohlc"][ticker].get("o", 0) > 0]
    highs  = [safe_num(s["ohlc"][ticker].get("h")) for s in snaps if s["ohlc"][ticker].get("h", 0) > 0]
    lows   = [safe_num(s["ohlc"][ticker].get("l")) for s in snaps if s["ohlc"][ticker].get("l", 0) > 0]
    closes = [safe_num(s["ohlc"][ticker].get("c")) for s in snaps if s["ohlc"][ticker].get("c", 0) > 0]
    if not opens or not highs or not lows or not closes:
        return None
    wk_high = max(highs + ([current_price] if current_price else []))
    wk_low  = min(lows  + ([current_price] if current_price else []))
    return {
        "open":   round(opens[0], 4),
        "high":   round(wk_high, 4),
        "low":    round(wk_low, 4),
        "close":  round(current_price or closes[-1], 4),
        "volume": None,  # not available from /quote
        "days":   len(snaps),
        "fromDate": snaps[0]["date"],
        "toDate":   snaps[-1]["date"],
        "source":   "snapshot",
    }


# ────────────────────────────────────────────────────────────────────
# ORCHESTRATION
# ────────────────────────────────────────────────────────────────────

def fetch_live_market_data(state: dict,
                             progress_cb=None) -> tuple[int, list[str], str]:
    """Fetch quotes + weekly OHLCV for every holding.

    Strategy:
      1. Try yfinance first (free, full OHLCV).
      2. If that fails for a ticker, fall back to Finnhub /quote (if key available).
      3. If on Finnhub-only path, capture today's intraday OHLC into priceSnap
         and aggregate the week from accumulated snapshots.

    Returns (success_count, failure_messages, primary_source_used).
    """
    holdings = state.get("holdings", [])
    if not holdings:
        return (0, ["No holdings to fetch"], "n/a")

    tickers = [h["ticker"] for h in holdings]
    failures: list[str] = []
    sources_used: dict[str, int] = {"yfinance": 0, "snapshot": 0, "finnhub-quote": 0}

    # Today's snapshot — populated as we go (used by fallback aggregation)
    today_snap = {"date": today_iso(), "prices": {}, "ohlc": {}}

    finnhub_key = ""
    try:
        finnhub_key = st.secrets.get("FINNHUB_API_KEY", "") if hasattr(st, "secrets") else ""
    except Exception:
        finnhub_key = ""

    for i, ticker in enumerate(tickers):
        if progress_cb:
            progress_cb(i, len(tickers), ticker)

        # 1. Try yfinance
        data = fetch_yfinance_data(ticker)
        used_source = "yfinance" if data else None

        # 2. Fall back to Finnhub quote
        if data is None and finnhub_key:
            data = fetch_finnhub_quote(ticker, finnhub_key)
            used_source = "finnhub-quote" if data else None

        if data is None:
            failures.append(f"{ticker}: no data from any source")
            continue

        sources_used[used_source] = sources_used.get(used_source, 0) + 1

        # Capture today's snapshot for fallback aggregation
        today_snap["prices"][ticker] = data["price"]
        if "intraday" in data:
            today_snap["ohlc"][ticker] = data["intraday"]
        elif data.get("weekOHLC"):
            wk = data["weekOHLC"]
            today_snap["ohlc"][ticker] = {
                "o": wk["open"], "h": wk["high"], "l": wk["low"], "c": wk["close"],
            }

        # Determine weekOHLC: yfinance gives it directly, Finnhub-only needs aggregation
        week_ohlc = data.get("weekOHLC")
        if not week_ohlc:
            # Will be filled in after we save today's snap (below)
            pass

        # Update the holding
        for h in holdings:
            if h["ticker"] != ticker:
                continue
            h["lastPrice"] = data["price"]
            if data.get("prevClose") is not None:
                h["lastClose"] = data["prevClose"]
            if week_ohlc:
                h["weekOHLC"] = week_ohlc
            h["lastFetchAt"] = now_iso()
            h["status"] = "Quote updated"

    # Save today's snapshot (overwrites any prior entry for today)
    if today_snap["prices"]:
        state["priceSnap"] = [s for s in state.get("priceSnap", [])
                                if s.get("date") != today_snap["date"]]
        state["priceSnap"].append(today_snap)
        # Trim to last 90 days
        if len(state["priceSnap"]) > 90:
            state["priceSnap"] = state["priceSnap"][-90:]

    # Backfill weekOHLC from snapshots for any holding that didn't get one from yfinance
    for h in holdings:
        if h.get("weekOHLC") and h["weekOHLC"].get("source") == "yfinance":
            continue
        snap_week = aggregate_week_from_snaps(state, h["ticker"], h.get("lastPrice"))
        if snap_week:
            h["weekOHLC"] = snap_week

    # Mark portfolio (recompute shares + currentValueUSD from new prices)
    refresh_portfolio_mark(state)

    state["lastRefresh"] = now_iso()
    primary = max(sources_used, key=sources_used.get) if any(sources_used.values()) else "n/a"
    return (len(tickers) - len(failures), failures, primary)


def refresh_portfolio_mark(state: dict) -> None:
    """Recompute shares + currentValueUSD for each holding given lastPrice.

    On first quote after seeding, shares is None — derive it from initialUSD/price.
    On subsequent fetches, shares is fixed; just recompute value.
    """
    for h in state.get("holdings", []):
        price = safe_num(h.get("lastPrice"), 0)
        if price <= 0:
            continue
        if h.get("shares") is None:
            seed = safe_num(h.get("initialUSD"), safe_num(h.get("currentValueUSD"), 0))
            h["shares"] = round(seed / price, 6)
        h["currentValueUSD"] = round(safe_num(h["shares"]) * price, 2)
        h["status"] = "Marked to market"


def fetch_single_quote(ticker: str) -> dict | None:
    """Fetch a one-off price for a ticker (used in 'Add new position' flow)."""
    data = fetch_yfinance_data(ticker)
    if data:
        return data
    finnhub_key = ""
    try:
        finnhub_key = st.secrets.get("FINNHUB_API_KEY", "") if hasattr(st, "secrets") else ""
    except Exception:
        pass
    if finnhub_key:
        return fetch_finnhub_quote(ticker, finnhub_key)
    return None
