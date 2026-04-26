"""Sector / industry / country classification for portfolio analytics.

Pulls from yfinance.Ticker.info, which is rate-limited and occasionally flaky.
Cached per-ticker with TTL to make the Insights tab snappy on re-renders.

Static fallback maps cover common ETFs that don't have sector data in yfinance.
"""
from __future__ import annotations
from typing import Optional
import yfinance as yf
import streamlit as st


# Common ETFs and their broad classifications — yfinance often returns
# 'Financial Services' or empty for these, so we override
ETF_OVERRIDES: dict[str, dict] = {
    # Bonds
    "IEF":  {"sector": "Bonds", "industry": "US Treasuries 7-10y", "country": "United States"},
    "TLT":  {"sector": "Bonds", "industry": "US Treasuries 20+y",  "country": "United States"},
    "SHY":  {"sector": "Bonds", "industry": "US Treasuries 1-3y",  "country": "United States"},
    "LQD":  {"sector": "Bonds", "industry": "Investment Grade Corp", "country": "United States"},
    "HYG":  {"sector": "Bonds", "industry": "High Yield Corp",     "country": "United States"},
    "AGG":  {"sector": "Bonds", "industry": "US Aggregate Bond",   "country": "United States"},
    "BND":  {"sector": "Bonds", "industry": "US Aggregate Bond",   "country": "United States"},
    "TIP":  {"sector": "Bonds", "industry": "US TIPS",             "country": "United States"},
    # Country / region equity ETFs
    "EWJ":  {"sector": "Equity ETF", "industry": "Japan",           "country": "Japan"},
    "EWG":  {"sector": "Equity ETF", "industry": "Germany",         "country": "Germany"},
    "EWU":  {"sector": "Equity ETF", "industry": "United Kingdom",  "country": "United Kingdom"},
    "INDA": {"sector": "Equity ETF", "industry": "India",           "country": "India"},
    "MCHI": {"sector": "Equity ETF", "industry": "China",           "country": "China"},
    "EWZ":  {"sector": "Equity ETF", "industry": "Brazil",          "country": "Brazil"},
    "EWY":  {"sector": "Equity ETF", "industry": "South Korea",     "country": "South Korea"},
    "EWT":  {"sector": "Equity ETF", "industry": "Taiwan",          "country": "Taiwan"},
    "EEM":  {"sector": "Equity ETF", "industry": "Emerging Markets","country": "Multiple (EM)"},
    "EFA":  {"sector": "Equity ETF", "industry": "Developed ex-US", "country": "Multiple (DM)"},
    "VWO":  {"sector": "Equity ETF", "industry": "Emerging Markets","country": "Multiple (EM)"},
    "VEA":  {"sector": "Equity ETF", "industry": "Developed ex-US", "country": "Multiple (DM)"},
    # Broad US
    "SPY":  {"sector": "Equity ETF", "industry": "US Large Cap",    "country": "United States"},
    "VOO":  {"sector": "Equity ETF", "industry": "US Large Cap",    "country": "United States"},
    "QQQ":  {"sector": "Equity ETF", "industry": "US Tech 100",     "country": "United States"},
    "IWM":  {"sector": "Equity ETF", "industry": "US Small Cap",    "country": "United States"},
    "VTI":  {"sector": "Equity ETF", "industry": "US Total Market", "country": "United States"},
    # Sector ETFs
    "XLK":  {"sector": "Technology",   "industry": "Tech ETF",      "country": "United States"},
    "XLF":  {"sector": "Financial Services", "industry": "Financials ETF", "country": "United States"},
    "XLE":  {"sector": "Energy",       "industry": "Energy ETF",    "country": "United States"},
    "XLV":  {"sector": "Healthcare",   "industry": "Healthcare ETF","country": "United States"},
    "XLI":  {"sector": "Industrials",  "industry": "Industrials ETF","country": "United States"},
    # Commodities
    "GLD":  {"sector": "Commodities", "industry": "Gold",            "country": "Global"},
    "SLV":  {"sector": "Commodities", "industry": "Silver",          "country": "Global"},
    "USO":  {"sector": "Commodities", "industry": "Oil",             "country": "Global"},
}


@st.cache_data(ttl=86400, show_spinner=False)
def get_classification(ticker: str) -> dict:
    """Return {sector, industry, country, marketCap} for a ticker.

    Cached for 24h since this changes rarely. Falls back to static map for
    common ETFs and to "Unknown" labels if yfinance returns nothing.
    """
    t = ticker.upper().strip()

    # Static override for ETFs
    if t in ETF_OVERRIDES:
        result = dict(ETF_OVERRIDES[t])
        result.setdefault("marketCap", None)
        return result

    # yfinance fetch
    try:
        info = yf.Ticker(t).info or {}
        return {
            "sector":    info.get("sector") or "Unknown",
            "industry":  info.get("industry") or "Unknown",
            "country":   info.get("country") or "Unknown",
            "marketCap": info.get("marketCap"),
        }
    except Exception:
        return {"sector": "Unknown", "industry": "Unknown",
                "country": "Unknown", "marketCap": None}


def classify_holdings(holdings: list[dict]) -> list[dict]:
    """Add sector/industry/country/marketCap to each holding dict (in-place safe).

    Returns a new list of enriched dicts.
    """
    out = []
    for h in holdings:
        info = get_classification(h["ticker"])
        out.append({**h, **info})
    return out
