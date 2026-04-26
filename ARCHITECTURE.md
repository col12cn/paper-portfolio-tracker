# Architecture

Maintainer-facing guide to the codebase. Covers what each file is responsible for, the key data structures, and where to make common edits.

For setup, deployment, and migration from the v8 HTML tracker, see [README.md](./README.md).

---

## Top-level

### `streamlit_app.py` (~50 lines)
Entry point. Sets page config, injects CSS, renders the masthead, creates 5 `st.tabs`, and dispatches each tab to a `render()` function in `app/pages/*`. Streamlit Cloud expects this filename. To add a 6th tab, this is the only top-level file you touch.

### `requirements.txt`
Pinned minimums. `streamlit`, `yfinance`, `plotly`, `pandas`, `requests`. Add deps here; Streamlit Cloud picks them up on next push.

### `.streamlit/config.toml`
Theme (dark, accent `#7aa2ff`, panels `#192349`). Change colours here once instead of hunting through CSS.

### `.streamlit/secrets.toml`
`GEMINI_API_KEY` and optional `FINNHUB_API_KEY`. Read via `st.secrets.get(...)`. Gitignored.

---

## `app/` — core modules

### `helpers.py` (~90 lines)
Pure formatting and type-coercion utilities. `safe_num` (None/NaN-safe float coercion — used everywhere), `to_usd`, `to_pct`, `signed_pct`, `fmt_volume` (12.3M / 4.5K), `fmt_rel_time` (ISO → "2h ago"), `now_iso`, `today_iso`. No Streamlit imports — safe to call from anywhere. Add new formatters here.

### `state.py` (~225 lines)
The data layer. Three things:

1. **Schema definitions** — `DEFAULT_BASKET` (the 8-position seed), `DEFAULT_SETTINGS` (capital, buffer %, max weight, lookback days), `_empty_state()` (shape of a fresh state dict).
2. **Persistence** — `load_state()` reads `state.json`, `save_state(state)` writes it, `_migrate_if_needed(data)` upgrades old schemas (including v8 HTML backups). The migration is forward-compatible: missing keys get backfilled, bad types get reset.
3. **Session wrapper** — `get_state()` is the single entry point pages use. It loads from disk on first session access, caches in `st.session_state["state"]` thereafter. `commit()` writes session state back to disk. Domain ops: `get_portfolio_value()` (NAV calc), `mark_valuation()` (append NAV snapshot, dedup same-day), `initialize_portfolio()` (seed from basket), `full_reset()`.

State is a plain `dict` — not a class — to make JSON round-trip trivial and keep migration loose. To add a new field: add it to `_empty_state()` and `_migrate_if_needed()` (so old backups still load).

### `market.py` (~275 lines)
Price fetching. Two-source strategy:

1. `fetch_yfinance_data(ticker)` — Primary. Pulls 10 days of daily bars, takes last close as price, last 5 days for the weekly OHLCV bar. Returns `None` on failure. Full volume.
2. `fetch_finnhub_quote(ticker, key)` — Fallback. Hits Finnhub `/quote` (free tier, no `/candle` 403 issue). Returns price + today's intraday OHLC, no volume.
3. `aggregate_week_from_snaps(state, ticker, current_price)` — When yfinance fails AND we're on Finnhub-only path, builds a weekly bar by aggregating up to 5 daily snapshots stored in `state["priceSnap"]`. Source tagged `"snapshot"` so the UI can show partial-week warnings.
4. `fetch_live_market_data(state, progress_cb)` — The orchestrator. Loops every holding, tries yfinance, falls back to Finnhub, captures today's snapshot, backfills missing weeks from snapshots, then calls `refresh_portfolio_mark` to recompute `shares` and `currentValueUSD`. Returns `(success_count, failure_messages, primary_source_used)`.
5. `fetch_single_quote(ticker)` — One-off for the "Add new position" flow.

To add a third data source (Polygon, Alpha Vantage), add a `fetch_X_data` function with the same return shape and slot it into the cascade in `fetch_live_market_data`.

### `ai.py` (~310 lines)
Gemini integration. Layered:

1. `_call_gemini(prompt, with_search, temperature, max_tokens)` — Low-level POST to `generativelanguage.googleapis.com`. Handles search grounding via `tools=[{"google_search": {}}]`. Surfaces `MAX_TOKENS` truncation as a visible banner. The choke point for streaming, retry-on-429, or token usage tracking.
2. `build_portfolio_context(state)` — Serialises the portfolio into a structured text block (NAV, cash, per-position lines with target/current weights, P/L, week %, rationale, thesis). Used by all three AI functions for context injection.
3. `generate_portfolio_prompt(state, mode)` — Two modes. `"fresh"` produces a generic hedge-fund-style portfolio brief. `"evolve"` embeds the current portfolio and asks for KEEP/CUT/ADD decisions. Returns the *meta-prompt* for the user to paste into another AI.
4. `ask_gemini(state, question)` — Free-form Q&A with portfolio context + Google Search.
5. `analyse_portfolio(state)` — Two-section RISKS/RECOMMENDATIONS review. 6144 max tokens.
6. `parse_picks_json(raw)` — Tolerant parser for AI responses. Strips fences, accepts `weight` or `targetWeight`, extracts thesis from text before the JSON array. Raises `ValueError` with a clear message if it can't find a usable array.

To swap models (e.g. to Claude), `_call_gemini` is essentially the only function that needs replacing — change the endpoint and request shape, leave the rest alone.

### `styles.py` (~165 lines)
Just a big CSS string and an `inject()` function that calls `st.markdown(CSS, unsafe_allow_html=True)`. CSS variables at the top (`--bg`, `--accent`, `--good`, `--bad`) drive everything else. Edit those to recolour globally. The `.pill`, `.pill-good`, `.pill-bad`, `.pill-warn` classes are referenced from page modules via raw HTML markdown.

---

## `app/pages/` — one file per tab

Each module exports a single `render()` function called from `streamlit_app.py`. They all start with `state = get_state()`. They mutate state directly and call `commit()` to persist.

### `overview.py` (~225 lines)
Read-mostly dashboard.
- `_render_onboarding` — Dismissible 3-step setup card, hidden after dismiss or when steps complete.
- `_render_sparkline` — Compact NAV line over the last N valuation entries with a baseline at starting capital.
- `_render_metrics` — 5-column metric row.
- `_render_ask_gemini` — Free-form Q&A input. Stores the last 10 questions in `state["askHistory"]`. Latest answer always shown, older ones in an expander.
- `_render_active_basket` — Shows current basket + thesis as cards.

### `build.py` (~260 lines)
Portfolio construction.
- `_render_basket_editor` — `st.data_editor` table for tickers/weights/why. Row state cached in `st.session_state.builder_rows` so edits survive reruns.
- `_do_rebalance` — Liquidates everything at NAV, reinvests into the new basket. Trade history, cash log, price history all preserved. Logs to `state["rebalanceLog"]`.
- `_render_ai_workflow` — 3-step flow with mode toggle (fresh/evolve). Step 1 calls `ai.generate_portfolio_prompt`. Step 2 is text instructions. Step 3 takes pasted JSON, parses it via `ai.parse_picks_json`, and pre-fills the basket editor.

### `trade.py` (~510 lines, the biggest)
Holdings management + execution.
- `_drill_down(state, ticker)` — `@st.dialog` modal. Shows price/value/PL/week metrics, weekly OHLCV table, recent trades for the ticker, and the inline Ask Gemini box. Uses keys like `q_{ticker}` and `answer_{ticker}` to namespace per-position state.
- `_render_holdings_table` — Holdings table + a single-position trade controller below it (selectbox + amount + Buy/Sell/→tgt/View buttons). Streamlit's tables don't support per-row buttons cleanly, hence the selector pattern.
- `_execute_trade(state, ticker, action, amt_usd)` — Updates shares, cash, logs trade and cash flow, marks valuation, commits, reruns. The single source of truth for buy/sell.
- `_rebalance_to_target(state, ticker)` — Calculates delta to target USD value, calls `_execute_trade` with the appropriate action.
- `_rebalance_all(state)` — Loops every position with >0.5% deviation, sorts sells before buys to free cash, executes each. Wraps each trade in try/except so one failure doesn't halt the rest.
- `_close_position` — Removes from holdings, returns proceeds to cash.
- `_render_add_new_position` — Adds a new ticker (or tops up existing), fetches a single quote, deducts cash.
- `_render_cash` — Deposit/withdraw forms, recent cash log table.

### `review.py` (~245 lines)
Charts and logs.
- `_render_nav_chart` — Plotly area chart of NAV over time with starting capital baseline.
- `_render_component_chart` — Multi-line chart, each line is a holding's % change from its first observed snapshot.
- `_render_risk_analysis` — Calls `ai.analyse_portfolio`. Result cached in `st.session_state.last_risk_analysis` so it persists across reruns.
- `_render_trade_log` — Last 100 trades as a dataframe.
- `_render_rebalance_log` — Expandable history per rebalance with KEEP/CUT/RESIZE diff chips computed by `_compute_diff` against the previous rebalance.

### `settings.py` (~215 lines)
Configuration + reset.
- `_render_api_status` — Shows whether keys are set, with help text on how to add them locally vs Streamlit Cloud.
- `_render_app_settings` — Form for starting capital, lookback, max weight, min cash buffer.
- `_render_backup` — `st.download_button` with the full state JSON, plus an `st.file_uploader` for restore (with confirm-button gate).
- `_render_cash_override` — Direct cash balance reset, logs the adjustment.
- `_render_diagnostics` — Expander showing state file size, counts, full state JSON. Useful for debugging.
- `_render_danger_zone` — Type-RESET-to-confirm full wipe. Backup-first button right next to it.

---

## Patterns that recur

- **Mutate `state`, then `commit()`** — every page does this. Forget the commit and the change survives the page render but disappears after the next session start.
- **`st.rerun()` after a state change** — re-runs the script top-to-bottom so all derived UI (NAV, weights, charts) reflects the new state. Always after `commit()`.
- **`st.rerun()` inside an `@st.dialog` closes the dialog.** Intended for trade actions where you want to see the updated holdings on the page underneath. Use a session-state flag to keep the dialog open if you ever need that.
- **Session state keys are namespaced by purpose** — `q_{ticker}` for drill-down questions, `answer_{ticker}` for cached answers, `builder_rows` for the data editor, `last_risk_analysis` for the review tab. Give new interactive widgets descriptive keys to avoid collisions.
- **Form inputs avoid the "value + key" warning** by either initialising via `setdefault` or relying on Streamlit's automatic default-from-value behaviour. A few spots use `st.session_state.setdefault(key, default)` then refer to the key — that's the cleanest pattern.
- **Render functions are pure-side-effect** — they read state, render UI, mutate state on user action. No return values. Trivially composable in `streamlit_app.py`.

---

## Common edits, where to make them

| Want to | Edit |
|---|---|
| Add a new metric to Overview | `overview.py::_render_metrics` |
| Change colours globally | `.streamlit/config.toml` (theme) + `app/styles.py` (CSS vars at top) |
| Change AI prompts | `app/ai.py` — each prompt is a multi-line f-string in its own function |
| Add a data source | `app/market.py` — new `fetch_X_data` function, then slot into `fetch_live_market_data` |
| Add a new column to holdings table | `trade.py::_render_holdings_table` (the `rows` list comprehension) |
| Add a new field to state | `state.py::_empty_state()` AND `_migrate_if_needed()` (so old backups load) |
| Change which model | `app/ai.py::_get_gemini_model` (or set `GEMINI_MODEL` in secrets) |
| Add a 6th tab | New file in `app/pages/`, import in `streamlit_app.py`, add to `tab_names` and `tabs[]` |
| Tweak chart styling | `review.py` for the big charts, `overview.py::_render_sparkline` for the small one. Both use Plotly with a shared dark template baked into each `update_layout` call. |
