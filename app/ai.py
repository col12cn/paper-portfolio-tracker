"""Gemini AI integration.

Three workflows:
  1. generate_portfolio_prompt() — Two modes: 'fresh' (new portfolio) or
     'evolve' (KEEP/CUT/ADD vs current). Produces a prompt the user copies
     into any AI (Claude, ChatGPT, etc.).
  2. ask_gemini() — Free-form Q&A with full portfolio context.
  3. analyse_portfolio() — Risk + recommendations review of current positions.
"""
from __future__ import annotations
import requests
import streamlit as st
from datetime import datetime

from app.helpers import safe_num, to_usd, now_iso
from app.state import get_portfolio_value


def _get_gemini_key() -> str:
    """Read Gemini API key from Streamlit secrets."""
    try:
        return st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    except Exception:
        return ""


def _get_gemini_model() -> str:
    """Default to 2.5-flash; allow override via secrets."""
    try:
        return st.secrets.get("GEMINI_MODEL", "gemini-2.5-flash") if hasattr(st, "secrets") else "gemini-2.5-flash"
    except Exception:
        return "gemini-2.5-flash"


def _gemini_endpoint(model: str, key: str) -> str:
    return (f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}")


def _call_gemini(prompt: str, with_search: bool = False,
                  temperature: float = 0.4, max_tokens: int = 2048) -> str:
    """Low-level Gemini call. Raises on error, returns text on success.

    If the response hits max_tokens, the partial text is returned with a
    visible truncation banner appended — caller does not need to handle this.
    """
    key = _get_gemini_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in secrets")

    body: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if with_search:
        body["tools"] = [{"google_search": {}}]

    r = requests.post(_gemini_endpoint(_get_gemini_model(), key),
                       json=body, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:200]}")

    data = r.json()
    candidate = (data.get("candidates") or [{}])[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    finish_reason = candidate.get("finishReason", "")

    if not text:
        raise RuntimeError(
            f"Empty response from Gemini (finishReason={finish_reason or 'unknown'})"
        )

    # Surface truncation rather than silently returning a partial response
    if finish_reason == "MAX_TOKENS":
        text += (
            f"\n\n⚠ Response truncated at the {max_tokens}-token limit. "
            f"Re-run for a fresh attempt, or ask a more focused follow-up question."
        )

    return text


# ────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER
# ────────────────────────────────────────────────────────────────────

def build_portfolio_context(state: dict) -> dict:
    """Build a structured snapshot of the portfolio for AI prompts."""
    nav = get_portfolio_value(state)
    cash = safe_num(state.get("cashUSD"), 0)
    cash_pct = (cash / nav * 100) if nav > 0 else 0
    start_cap = safe_num(state["settings"].get("startingCapital"), 1000)
    total_return = ((nav - start_cap) / start_cap * 100) if start_cap > 0 else 0

    lines = []
    for h in state.get("holdings", []):
        wt = (safe_num(h.get("currentValueUSD"), 0) / nav * 100) if nav > 0 else 0
        initial = safe_num(h.get("initialUSD"), 0)
        current = safe_num(h.get("currentValueUSD"), 0)
        pos_return = ((current - initial) / initial * 100) if initial > 0 else 0
        tgt = safe_num(h.get("targetWeight"), 0) * 100
        px = f"${h['lastPrice']:.2f}" if h.get("lastPrice") else "no quote"
        wk = h.get("weekOHLC")
        wk_str = ""
        if wk and wk.get("open"):
            wk_pct = (wk["close"] - wk["open"]) / wk["open"] * 100
            wk_str = f", week {'+' if wk_pct >= 0 else ''}{wk_pct:.2f}%"
        why = f" — {h['why']}" if h.get("why") else ""
        lines.append(
            f"  - {h['ticker']} ({h['name']}): current {wt:.2f}% / target {tgt:.1f}%, "
            f"value {to_usd(current)}, P/L {pos_return:+.2f}%, price {px}{wk_str}{why}"
        )

    return {
        "nav": nav, "cash": cash, "cashPct": cash_pct,
        "totalReturn": total_return,
        "positionLines": "\n".join(lines),
        "holdingsCount": len(state.get("holdings", [])),
        "thesis": state.get("aiThesis") or "(none set)",
    }


# ────────────────────────────────────────────────────────────────────
# 1. PROMPT GENERATOR — fresh / evolve modes
# ────────────────────────────────────────────────────────────────────

def generate_portfolio_prompt(state: dict, mode: str = "fresh") -> str:
    """Generate a self-contained prompt the user pastes into any AI.

    mode='fresh' — generic hedge-fund-style portfolio brief.
    mode='evolve' — embeds current portfolio, asks for KEEP/CUT/ADD decisions.
    """
    today = datetime.now().strftime("%B %d, %Y")

    if mode == "evolve" and state.get("holdings"):
        ctx = build_portfolio_context(state)
        meta = f"""Today is {today}.

You are an expert prompt engineer specialising in financial analysis instructions for large language models.

Write a single, self-contained prompt that a user can paste directly into any AI assistant (Claude, ChatGPT, Perplexity, Gemini, etc.) to receive an EVOLVED hedge-fund-style US equity portfolio.

The user already holds the portfolio below. They want recommendations to evolve it — keep what's working, cut what isn't, add what fills gaps — given current market conditions.

CURRENT PORTFOLIO (NAV: {to_usd(ctx['nav'])}, return since inception: {ctx['totalReturn']:+.2f}%):
{ctx['positionLines']}
Cash: {to_usd(ctx['cash'])} ({ctx['cashPct']:.1f}% of NAV)

Existing thesis: {ctx['thesis']}

The prompt you write must instruct the AI to:
1. Use current market conditions, macro backdrop, sector momentum, earnings trends, and valuation as of today's date.
2. Explicitly KEEP, CUT, or ADD positions relative to the current portfolio above. Justify each decision.
3. Write an updated investment thesis (~300 words) that explains the pivot, what changed in the macro view, and the risk/reward tilt of the new portfolio relative to the old.
4. Select 6-10 US-listed equity tickers (common stock or ADR only — no ETFs, no bonds, no crypto). May include some current positions.
5. Long-only. Weights must sum to 1.0. Max single position 0.25. Higher conviction = higher weight.
6. Return output in this EXACT format — thesis first, then a raw JSON array:

INVESTMENT THESIS:
[~300 word thesis explaining the evolution from current portfolio]

PICKS:
[{{"ticker":"NVDA","name":"NVIDIA Corporation","weight":0.22,"why":"One sentence catalyst including whether this is KEEP/ADD/RESIZE."}},...]

The JSON array must use exactly these four keys: ticker, name, weight, why. Each "why" should briefly note whether the position is KEEP, ADD, or RESIZE relative to the current portfolio. No other keys. No trailing text after the array.

Embed the current portfolio context (positions, weights, P/L, cash, existing thesis) directly inside the prompt you write so the receiving AI has full context.

Write only the prompt text itself — no preamble, no explanation, no meta-commentary."""
    else:
        meta = f"""Today is {today}.

You are an expert prompt engineer specialising in financial analysis instructions for large language models.

Write a single, self-contained prompt that a user can paste directly into any AI assistant (Claude, ChatGPT, Perplexity, Gemini, etc.) to receive a high-quality, hedge-fund-style US equity portfolio.

The prompt you write must instruct the AI to:
1. Use current market conditions, macro backdrop, sector momentum, earnings trends, and valuation as of today's date.
2. Write an investment thesis of approximately 300 words covering: macro view, key drivers, sector tilts, risk factors, and overall portfolio strategy.
3. Select 6-10 US-listed equity tickers (common stock or ADR only — no ETFs, no bonds, no crypto).
4. Long-only. Weights must sum to 1.0. Max single position 0.25. Higher conviction = higher weight.
5. Return output in this EXACT format — thesis first, then a raw JSON array with no markdown fences, no wrapper object:

INVESTMENT THESIS:
[~300 word thesis here]

PICKS:
[{{"ticker":"NVDA","name":"NVIDIA Corporation","weight":0.22,"why":"One sentence catalyst."}},...]

The JSON array must use exactly these four keys: ticker, name, weight, why. No other keys. No trailing text after the array.

Write only the prompt text itself — no preamble, no explanation, no meta-commentary."""

    return _call_gemini(meta, with_search=False, temperature=0.5, max_tokens=4096)


# ────────────────────────────────────────────────────────────────────
# 2. ASK GEMINI (free-form Q&A)
# ────────────────────────────────────────────────────────────────────

def ask_gemini(state: dict, question: str) -> str:
    """Free-form Q&A with full portfolio context + Google Search grounding."""
    ctx = build_portfolio_context(state)
    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""Today is {today}. You are a senior portfolio strategist. Answer the user's question using the portfolio context below and current market conditions.

PORTFOLIO CONTEXT (NAV: {to_usd(ctx['nav'])}, total return: {ctx['totalReturn']:+.2f}%):
{ctx['positionLines']}
Cash: {to_usd(ctx['cash'])} ({ctx['cashPct']:.1f}% of NAV)

Existing thesis: {ctx['thesis']}

USER QUESTION:
{question}

Answer directly and specifically. Reference actual position tickers from the portfolio above. Use 200-400 words. No generic disclaimers."""

    return _call_gemini(prompt, with_search=True, temperature=0.4, max_tokens=4096)


# ────────────────────────────────────────────────────────────────────
# 3. PORTFOLIO ANALYSIS (risk + recommendations)
# ────────────────────────────────────────────────────────────────────

def analyse_portfolio(state: dict) -> str:
    """Risk-and-recommendation review of current portfolio."""
    ctx = build_portfolio_context(state)
    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""Today is {today}. You are a senior risk analyst at a hedge fund reviewing a paper portfolio.

CURRENT PORTFOLIO (NAV: {to_usd(ctx['nav'])}, total return: {ctx['totalReturn']:+.2f}%):
{ctx['positionLines']}
Cash: {to_usd(ctx['cash'])} ({ctx['cashPct']:.1f}% of NAV)

Existing thesis: {ctx['thesis']}

Using current market conditions, recent macro developments, sector trends, and earnings newsflow, provide:

1. KEY RISKS (3-5 bullets): The most material risks to this specific portfolio right now — macro, sector, single-stock, concentration, liquidity. Be specific to the positions held.

2. RECOMMENDATIONS (3-5 bullets): Actionable suggestions to improve risk-adjusted returns or reduce tail risk — sizing, hedges, rotation, cash deployment. Reference specific tickers.

Format:
RISKS:
• [risk 1]
• [risk 2]
...

RECOMMENDATIONS:
• [rec 1]
• [rec 2]
...

Be direct and specific. No generic disclaimers."""

    return _call_gemini(prompt, with_search=True, temperature=0.3, max_tokens=6144)


# ────────────────────────────────────────────────────────────────────
# JSON IMPORT (parse AI response back into picks)
# ────────────────────────────────────────────────────────────────────

def parse_picks_json(raw: str) -> tuple[list[dict], str]:
    """Tolerant JSON parser for AI responses.

    The AI may return:
      - INVESTMENT THESIS: ... PICKS: [json array]
      - Just a JSON array
      - Surrounded by markdown fences

    Returns (picks_list, extracted_thesis_or_empty).
    Raises ValueError if no array found or zero valid picks.
    """
    import json as json_lib
    raw = raw.strip()
    arr_start = raw.find("[")
    arr_end = raw.rfind("]")
    if arr_start < 0 or arr_end <= arr_start:
        raise ValueError("No JSON array found in the response.")

    # Extract thesis (text before the array)
    thesis = ""
    if arr_start > 0:
        thesis = raw[:arr_start]
        thesis = thesis.replace("INVESTMENT THESIS:", "").replace("PICKS:", "").strip()
        if len(thesis) < 50:
            thesis = ""

    # Clean and parse the array
    json_str = raw[arr_start:arr_end + 1]
    # Strip control chars and normalise whitespace
    import re
    json_str = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", json_str)
    json_str = re.sub(r"\s+", " ", json_str)
    picks_raw = json_lib.loads(json_str)
    if not isinstance(picks_raw, list) or not picks_raw:
        raise ValueError("JSON array is empty.")

    # Normalise — accept 'weight' or 'targetWeight'
    normalised = []
    for p in picks_raw:
        ticker = str(p.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        weight = safe_num(p.get("weight", p.get("targetWeight")), 0)
        if weight <= 0:
            continue
        normalised.append({
            "ticker": ticker,
            "name":   str(p.get("name") or ticker).strip(),
            "weight": weight,
            "why":    str(p.get("why") or p.get("reason") or "").strip(),
        })

    if not normalised:
        raise ValueError("No valid picks found (need ticker + weight > 0).")

    return normalised, thesis
