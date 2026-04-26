"""Benchmark data — SPY (and optionally others) for chart overlays and beta calc.

Cached at the Streamlit level (TTL 1h) so chart re-renders don't re-hit yfinance
on every interaction. Falls back gracefully if the network call fails.
"""
from __future__ import annotations
from typing import Optional
import pandas as pd
import yfinance as yf
import streamlit as st


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark_history(ticker: str = "SPY", days: int = 180) -> Optional[pd.DataFrame]:
    """Fetch daily closes for a benchmark ticker.

    Returns a DataFrame with columns [date, close] or None if fetch fails.
    Cached for 1 hour to avoid hammering yfinance during interactive use.
    """
    try:
        # yfinance accepts period='6mo', '1y' etc.; we use a day count for flexibility
        period_map = [(7, "5d"), (32, "1mo"), (95, "3mo"),
                       (190, "6mo"), (370, "1y"), (740, "2y")]
        period = next((p for d, p in period_map if days <= d), "5y")
        hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
        if hist.empty:
            return None
        df = pd.DataFrame({
            "date": [d.strftime("%Y-%m-%d") for d in hist.index],
            "close": hist["Close"].astype(float).values,
        })
        return df
    except Exception:
        return None


def normalize_to_baseline(df: pd.DataFrame, baseline: float,
                            anchor_date: Optional[str] = None) -> pd.DataFrame:
    """Rebase a benchmark price series so it starts at `baseline`.

    If `anchor_date` is given, the value on that date becomes baseline; otherwise
    the first row does. Returns a copy with an added 'value' column.
    """
    df = df.copy()
    if anchor_date:
        anchor_rows = df[df["date"] >= anchor_date]
        anchor_close = float(anchor_rows.iloc[0]["close"]) if not anchor_rows.empty else float(df.iloc[0]["close"])
    else:
        anchor_close = float(df.iloc[0]["close"])
    df["value"] = df["close"].astype(float) / anchor_close * baseline
    return df


def benchmark_aligned_to_dates(ticker: str, dates: list[str],
                                  baseline: float) -> Optional[pd.DataFrame]:
    """Get benchmark series rebased to `baseline` at the first of `dates`.

    Returns DataFrame [date, value] containing only rows whose date is in `dates`
    (or the closest available trading day). None on fetch failure.
    """
    if not dates:
        return None
    history = fetch_benchmark_history(ticker, days=len(dates) + 30)
    if history is None or history.empty:
        return None
    rebased = normalize_to_baseline(history, baseline, anchor_date=dates[0])
    # Filter to only rows whose date is in our portfolio's date set,
    # or at least within the visible window
    visible = rebased[(rebased["date"] >= dates[0]) & (rebased["date"] <= dates[-1])]
    if visible.empty:
        return None
    return visible[["date", "value"]].reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def benchmark_total_return_pct(ticker: str = "SPY", days: int = 7) -> Optional[float]:
    """% change in benchmark over the last `days` calendar days. None on failure."""
    history = fetch_benchmark_history(ticker, days=days + 10)
    if history is None or len(history) < 2:
        return None
    last = float(history.iloc[-1]["close"])
    # Use the close from `days` ago, or the earliest available
    cutoff_idx = max(0, len(history) - days - 1)
    earlier = float(history.iloc[cutoff_idx]["close"])
    if earlier <= 0:
        return None
    return (last - earlier) / earlier * 100
