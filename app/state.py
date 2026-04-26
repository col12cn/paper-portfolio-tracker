"""State management: in-memory via st.session_state, persisted to state.json.

The JSON file is the source of truth across browser sessions and app restarts
within a single Streamlit Cloud deployment. Streamlit Cloud's filesystem is
ephemeral on redeploys — use Settings → Backup to download regularly.

State schema mirrors the v8 HTML tracker for easy migration. Existing v8 backups
can be imported directly.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
import streamlit as st

from app.helpers import safe_num, now_iso, today_iso

STATE_FILE = Path(os.environ.get("PP_STATE_FILE", "state.json"))

DEFAULT_BASKET = [
    {"ticker": "NVDA", "name": "NVIDIA",
     "targetWeight": 0.15, "why": "AI accelerator leader and capex beneficiary."},
    {"ticker": "TSM",  "name": "TSMC ADR",
     "targetWeight": 0.15, "why": "Leading-edge foundry backbone for advanced chips."},
    {"ticker": "ASML", "name": "ASML Holding",
     "targetWeight": 0.10, "why": "Critical lithography supplier with AI order leverage."},
    {"ticker": "MELI", "name": "MercadoLibre",
     "targetWeight": 0.10, "why": "LatAm ecommerce and fintech compounder."},
    {"ticker": "IBN",  "name": "ICICI Bank ADR",
     "targetWeight": 0.10, "why": "Indian private-sector bank with structural growth."},
    {"ticker": "EWJ",  "name": "iShares MSCI Japan ETF",
     "targetWeight": 0.10, "why": "Japan governance and reform sleeve."},
    {"ticker": "IEF",  "name": "iShares 7-10yr Treasury ETF",
     "targetWeight": 0.15, "why": "High-quality duration sleeve."},
    {"ticker": "LQD",  "name": "iShares IG Corporate Bond ETF",
     "targetWeight": 0.15, "why": "Investment-grade credit carry sleeve."},
]

DEFAULT_SETTINGS = {
    "startingCapital": 1000.0,
    "initialCashBufferPct": 5.0,
    "minCashBufferPct": 5.0,
    "maxWeightPct": 20.0,
    "lookbackDays": 45,
}


def _empty_state() -> dict:
    """Initial empty state — populated by initialize_portfolio() on first run."""
    return {
        "settings": dict(DEFAULT_SETTINGS),
        "holdings": [],
        "cashUSD": None,
        "tradeLog": [],
        "valuation": [],
        "priceSnap": [],
        "newsState": [],
        "cashLog": [],
        "aiBasket": None,
        "aiThesis": None,
        "rebalanceLog": [],
        "askHistory": [],
        "watchlist": [],
        "aiMode": "fresh",
        "lastRefresh": None,
        "onboardingDismissed": False,
        "_meta": {"version": "py-1.2", "createdAt": now_iso()},
    }


# ────────────────────────────────────────────────────────────────────
# PERSISTENCE
# ────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    """Read state.json from disk. Returns empty state if missing/corrupt."""
    if not STATE_FILE.exists():
        return _empty_state()
    try:
        with STATE_FILE.open("r") as f:
            data = json.load(f)
        return _migrate_if_needed(data)
    except (json.JSONDecodeError, OSError) as e:
        st.warning(f"Could not load state.json ({e}); starting with empty state.")
        return _empty_state()


def save_state(state: dict) -> None:
    """Write state to state.json. Best-effort; failures are warned but not fatal."""
    try:
        with STATE_FILE.open("w") as f:
            json.dump(state, f, indent=2, default=str)
    except OSError as e:
        st.warning(f"Could not save state.json: {e}")


def _migrate_if_needed(data: dict) -> dict:
    """Upgrade older state schemas (incl. v8 HTML backups) to current shape."""
    state = _empty_state()
    state.update(data)

    # If user dropped in a v8 HTML backup, the structure is identical except for
    # the _meta block. Backfill anything missing.
    state.setdefault("settings", dict(DEFAULT_SETTINGS))
    for k, v in DEFAULT_SETTINGS.items():
        state["settings"].setdefault(k, v)

    # Holdings backfill — ensure new fields exist on each
    for h in state.get("holdings", []) or []:
        h.setdefault("weekOHLC", None)
        h.setdefault("lastFetchAt", None)
        h.setdefault("why", "")
        h.setdefault("lastTradeAt", None)
        h.setdefault("maxWeightPct", state["settings"].get("maxWeightPct", 20))

    # Ensure required collections are lists, not None
    for k in ("tradeLog", "valuation", "priceSnap", "newsState",
              "cashLog", "rebalanceLog", "askHistory", "watchlist"):
        if not isinstance(state.get(k), list):
            state[k] = []

    # Backfill tags field on every holding (added in py-1.2)
    for h in state.get("holdings", []):
        if "tags" not in h or not isinstance(h.get("tags"), list):
            h["tags"] = []

    return state


# ────────────────────────────────────────────────────────────────────
# SESSION STATE WRAPPER
# ────────────────────────────────────────────────────────────────────

def get_state() -> dict:
    """Return the live state dict. Loads from disk on first access of session."""
    if "state" not in st.session_state:
        st.session_state.state = load_state()
        if not st.session_state.state.get("holdings"):
            initialize_portfolio(st.session_state.state, force=True)
            save_state(st.session_state.state)
    return st.session_state.state


def commit() -> None:
    """Persist current session state to disk."""
    if "state" in st.session_state:
        save_state(st.session_state.state)


# ────────────────────────────────────────────────────────────────────
# DOMAIN OPS
# ────────────────────────────────────────────────────────────────────

def get_portfolio_value(state: dict) -> float:
    """NAV = sum(holding values) + cash."""
    holdings_val = sum(safe_num(h.get("currentValueUSD", h.get("initialUSD", 0)))
                       for h in state.get("holdings", []))
    return round(holdings_val + safe_num(state.get("cashUSD"), 0), 2)


def mark_valuation(state: dict, note: str) -> None:
    """Append a NAV snapshot to valuation history (collapses same-day same-note)."""
    item = {
        "date": today_iso(),
        "portfolioValueUSD": get_portfolio_value(state),
        "cashUSD": round(safe_num(state.get("cashUSD"), 0), 2),
        "note": note,
    }
    val = state.setdefault("valuation", [])
    if val and val[-1].get("date") == item["date"] and val[-1].get("note") == note:
        val[-1] = item
    else:
        val.append(item)


def initialize_portfolio(state: dict, force: bool = False,
                          override_basket: list | None = None) -> None:
    """Seed an empty portfolio from the active basket (or default)."""
    if state.get("holdings") and state.get("cashUSD") is not None and not force:
        return

    basket = override_basket or state.get("aiBasket") or DEFAULT_BASKET
    capital = safe_num(state["settings"].get("startingCapital"), 1000)
    cash_pct = max(0, safe_num(state["settings"].get("initialCashBufferPct"), 5)) / 100
    cash = round(capital * cash_pct, 2)
    investable = capital - cash

    state["cashUSD"] = cash
    state["holdings"] = [
        {
            "ticker": h["ticker"],
            "name": h["name"],
            "targetWeight": h["targetWeight"],
            "maxWeightPct": safe_num(state["settings"].get("maxWeightPct"), 20),
            "initialUSD": round(investable * h["targetWeight"], 2),
            "shares": None,
            "lastPrice": None,
            "lastClose": None,
            "currentValueUSD": round(investable * h["targetWeight"], 2),
            "weekOHLC": None,
            "lastFetchAt": None,
            "status": "Awaiting first quote fetch",
            "why": h.get("why", ""),
            "lastTradeAt": None,
        }
        for h in basket
    ]
    state["tradeLog"] = [{
        "timestamp": now_iso(), "action": "INIT", "ticker": "ALL",
        "tradeUSD": investable, "shares": "-",
        "reason": f"Initialized with ${capital:.2f} capital, ${cash:.2f} cash reserve.",
    }]
    state["valuation"] = [{
        "date": today_iso(),
        "portfolioValueUSD": round(capital, 2),
        "cashUSD": round(cash, 2),
        "note": "Initial capital",
    }]
    state["priceSnap"] = []
    state["cashLog"] = [{
        "timestamp": now_iso(), "type": "DEPOSIT",
        "amount": capital, "balance": cash,
        "note": f"Portfolio initialised — ${investable:.2f} allocated, ${cash:.2f} cash.",
    }]


def full_reset(state: dict) -> None:
    """Wipe everything, restart from default basket at $1,000."""
    fresh = _empty_state()
    state.clear()
    state.update(fresh)
    initialize_portfolio(state, force=True)
