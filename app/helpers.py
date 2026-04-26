"""Utility helpers — formatting, time, type-safe numerics."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import math


def safe_num(x: Any, default: float = 0.0) -> float:
    """Coerce to float, return default for None/NaN/non-numeric."""
    try:
        n = float(x)
        if math.isnan(n) or math.isinf(n):
            return default
        return n
    except (TypeError, ValueError):
        return default


def to_usd(x: Any) -> str:
    """Format as $X.XX with 2 decimals."""
    return f"${safe_num(x):,.2f}"


def to_pct(x: Any, decimals: int = 2) -> str:
    """Format as X.XX%, dash for invalid."""
    n = safe_num(x, default=float("nan"))
    if math.isnan(n):
        return "—"
    return f"{n:.{decimals}f}%"


def fmt_volume(v: Any) -> str:
    """Format share volume as 12.3M / 4.5K etc."""
    n = safe_num(v, default=0)
    if n <= 0:
        return "—"
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.2f}M"
    if n >= 1e3:
        return f"{n/1e3:.1f}K"
    return f"{int(n)}"


def fmt_rel_time(iso_str: str | None) -> str:
    """Convert an ISO timestamp to relative ('2h ago', '3d ago')."""
    if not iso_str:
        return ""
    try:
        ts = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        seconds = delta.total_seconds()
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{int(seconds/60)}m ago"
        if seconds < 86400:
            return f"{int(seconds/3600)}h ago"
        return f"{int(seconds/86400)}d ago"
    except Exception:
        return ""


def now_iso() -> str:
    """Current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_iso() -> str:
    """Today's date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).date().isoformat()


def colour_for_change(value: float | None) -> str:
    """Return CSS class for positive/negative value display."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if value > 0:
        return "good"
    if value < 0:
        return "bad"
    return ""


def signed_pct(v: float | None, decimals: int = 2) -> str:
    """Format with explicit sign: +1.23% or -0.45%."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{'+' if v >= 0 else ''}{v:.{decimals}f}%"
