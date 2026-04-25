"""Settings tab: app config, backup/restore, cash override, full reset."""
from __future__ import annotations
import streamlit as st
import json
from datetime import datetime

from app.state import (get_state, commit, full_reset, mark_valuation, save_state, STATE_FILE)
from app.helpers import safe_num, to_usd, now_iso


def _render_api_status(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### API keys")
        st.caption("All API keys are stored in `.streamlit/secrets.toml` (locally) "
                    "or Streamlit Cloud's Secrets UI (deployed). They never appear in the codebase.")

        gemini_set = bool(st.secrets.get("GEMINI_API_KEY", "")) if hasattr(st, "secrets") else False
        finnhub_set = bool(st.secrets.get("FINNHUB_API_KEY", "")) if hasattr(st, "secrets") else False

        c1, c2 = st.columns(2)
        with c1:
            status = "✅ Set" if gemini_set else "❌ Not configured"
            st.markdown(f"**Gemini API key:** {status}")
            st.caption("Required for AI features (prompt generation, ask, risk analysis). "
                        "Get one free at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).")
        with c2:
            status = "✅ Set (fallback)" if finnhub_set else "⚠ Not configured (yfinance is primary)"
            st.markdown(f"**Finnhub API key:** {status}")
            st.caption("Optional. Used as a fallback if yfinance fails for a ticker. "
                        "Free tier at [finnhub.io](https://finnhub.io). Note: `/candle` endpoint requires paid tier.")

        with st.expander("How to add or change keys"):
            st.markdown("""
**Locally:** edit `.streamlit/secrets.toml` and restart the app.

**On Streamlit Cloud:** in your app's dashboard at [share.streamlit.io](https://share.streamlit.io),
click ⋮ → Settings → Secrets, paste:
```toml
GEMINI_API_KEY = "your-key-here"
FINNHUB_API_KEY = "your-key-here-optional"
```
Save. The app restarts automatically.
""")


def _render_app_settings(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### App settings")

        with st.form("settings_form"):
            c1, c2 = st.columns(2)
            with c1:
                starting_capital = st.number_input(
                    "Starting capital (USD)", min_value=100, max_value=10_000_000,
                    value=int(safe_num(state["settings"].get("startingCapital"), 1000)),
                    step=100,
                    help="Reference value for P/L calculation. Doesn't affect existing holdings.",
                )
                lookback = st.number_input(
                    "Price history lookback (days)", min_value=20, max_value=180,
                    value=int(safe_num(state["settings"].get("lookbackDays"), 45)),
                    step=5,
                )
            with c2:
                max_weight = st.number_input(
                    "Max single position weight (%)", min_value=5, max_value=100,
                    value=int(safe_num(state["settings"].get("maxWeightPct"), 20)),
                    step=5,
                )
                min_cash_buffer = st.number_input(
                    "Min cash buffer (%)", min_value=0, max_value=50,
                    value=int(safe_num(state["settings"].get("minCashBufferPct"), 5)),
                    step=1,
                    help="Visual warning threshold; doesn't auto-enforce.",
                )

            if st.form_submit_button("Save settings", type="primary"):
                state["settings"]["startingCapital"] = float(starting_capital)
                state["settings"]["lookbackDays"] = int(lookback)
                state["settings"]["maxWeightPct"] = float(max_weight)
                state["settings"]["minCashBufferPct"] = float(min_cash_buffer)
                commit()
                st.success("✓ Settings saved")


def _render_backup(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### Backup & restore")
        st.caption("Export your full portfolio state as a JSON file. "
                    "**Important on Streamlit Cloud:** the filesystem is ephemeral — "
                    "the JSON state file gets wiped on redeploy. Download a backup regularly.")

        c1, c2 = st.columns(2)
        with c1:
            backup_data = json.dumps(state, indent=2, default=str)
            st.download_button(
                "⇧ Download backup",
                data=backup_data,
                file_name=f"paper-portfolio-{datetime.now().strftime('%Y-%m-%d')}.json",
                mime="application/json",
                use_container_width=True,
                type="primary",
            )

        with c2:
            uploaded = st.file_uploader(
                "Restore from file",
                type=["json"],
                key="restore_uploader",
                label_visibility="collapsed",
            )
            if uploaded is not None:
                try:
                    snap = json.load(uploaded)
                    if st.button(f"⚠ OVERWRITE current state with {uploaded.name}",
                                  type="secondary"):
                        # Perform the restore — completely replace state
                        from app.state import _migrate_if_needed
                        new_state = _migrate_if_needed(snap)
                        state.clear()
                        state.update(new_state)
                        commit()
                        st.success(f"✓ Restored from {uploaded.name}")
                        st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON: {e}")
                except Exception as e:
                    st.error(f"Restore failed: {e}")


def _render_cash_override(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### Cash balance override")
        st.caption("Set the cash balance directly — useful to correct a discrepancy. "
                    "Logs the adjustment to the cash log.")

        c1, c2 = st.columns([1, 2])
        with c1:
            new_cash = st.number_input("Set cash to (USD)", min_value=0.0, step=10.0,
                                          value=safe_num(state.get("cashUSD"), 0))
        with c2:
            note = st.text_input("Reason", placeholder="e.g. Correcting opening balance",
                                   key="reset_cash_note")

        if st.button("Set cash balance", type="secondary"):
            delta = new_cash - safe_num(state.get("cashUSD"), 0)
            state["cashUSD"] = round(new_cash, 2)
            state["cashLog"].insert(0, {
                "timestamp": now_iso(), "type": "RESET",
                "amount": delta, "balance": state["cashUSD"],
                "note": note or "Cash override",
            })
            mark_valuation(state, f"Cash reset: ${new_cash:.2f}")
            commit()
            st.success(f"✓ Cash set to {to_usd(new_cash)}")
            st.rerun()


def _render_danger_zone(state: dict) -> None:
    with st.container(border=True):
        st.markdown("### :red[Danger zone · full reset]")
        st.warning("Wipes all holdings, trades, cash, valuation history, basket, and rebalance log. "
                    "Restarts the portfolio from $1,000 with the default tech basket. "
                    "**This cannot be undone.** Take a backup first.")

        c1, c2 = st.columns([2, 1])
        with c1:
            confirm_text = st.text_input(
                'Type the word **RESET** in capital letters to enable the button',
                key="reset_confirm",
            )
        with c2:
            backup_data = json.dumps(state, indent=2, default=str)
            st.download_button(
                "⇧ Backup first",
                data=backup_data,
                file_name=f"paper-portfolio-pre-reset-{datetime.now().strftime('%Y-%m-%d')}.json",
                mime="application/json",
                use_container_width=True,
            )

        if st.button("I understand, wipe everything", type="primary",
                      disabled=(confirm_text != "RESET"), key="full_reset_btn"):
            full_reset(state)
            commit()
            st.success("Portfolio reset to $1,000 with default basket.")
            st.rerun()


def _render_diagnostics(state: dict) -> None:
    """Tucked-away diagnostic info."""
    with st.expander("Diagnostics & state inspection"):
        st.markdown(f"**State file:** `{STATE_FILE}` "
                     f"(exists: {STATE_FILE.exists()}, "
                     f"size: {STATE_FILE.stat().st_size if STATE_FILE.exists() else 0} bytes)")
        st.markdown(f"**Holdings:** {len(state.get('holdings', []))}")
        st.markdown(f"**Trade log:** {len(state.get('tradeLog', []))} entries")
        st.markdown(f"**Valuation history:** {len(state.get('valuation', []))} entries")
        st.markdown(f"**Price snapshots:** {len(state.get('priceSnap', []))} days")
        st.markdown(f"**Rebalance log:** {len(state.get('rebalanceLog', []))} events")
        st.markdown(f"**Last refresh:** {state.get('lastRefresh', 'never')}")
        st.markdown(f"**App version:** {state.get('_meta', {}).get('version', 'unknown')}")

        if st.checkbox("Show full state JSON"):
            st.json(state)


def render() -> None:
    state = get_state()
    _render_api_status(state)
    _render_app_settings(state)
    _render_backup(state)
    _render_cash_override(state)
    _render_diagnostics(state)
    _render_danger_zone(state)
