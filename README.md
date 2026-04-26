# Paper Portfolio Tracker

A Streamlit-based paper portfolio tracker designed around three pillars: **build with AI**, **capitalise on trends**, **review and learn**.

## Features

**Build · Trade · Track**
- Live quotes + weekly OHLCV via `yfinance` (free, no API key)
- AI workflow with two modes: generate fresh portfolio prompts, or evolve current portfolio
- Watchlist for ideas before they become positions, with alert prices and one-click promotion
- Per-position trade controls with optional rationale capture (saves your thesis to the journal)
- Rebalance with auto-quote capture on new tickers
- Free-form "Ask Gemini" with full portfolio context

**Review · Learn**
- NAV chart with **SPY benchmark overlay** — answer "am I beating the market?"
- Component price chart, multi-select for ticker comparison, with entry/exit trade markers
- Per-position drill-down (trades, OHLCV, ask AI about this ticker)
- "This week" digest on Overview — best/worst movers, NAV vs SPY, trade count
- Trade log with rationale column — see your past thinking

**Insights** (institutional-grade analytics)
- **Performance attribution** — which positions drove your returns
- **Sector exposure** — donut chart + table, with cash break-out
- **Geographic exposure** — country mix incl. ETF mapping
- **Concentration check** — HHI, top-N weights, max-weight violations
- **Portfolio beta to SPY** — daily-return regression with interpretation
- **Headline metrics** — top-3 weight, effective N, vs SPY return

**Backup & Persistence**
- Full state export/import as JSON
- Persistent cash log, trade log, rebalance log
- v8 HTML backup migration supported

## Quick start (local)

```bash
git clone <your-repo-url>
cd paper-portfolio-tracker
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Add your Gemini key to .streamlit/secrets.toml
# (copy from .streamlit/secrets.toml.example)

streamlit run streamlit_app.py
```

## Deploy to Streamlit Community Cloud

1. **Push to GitHub.** Public repo (free tier) or private (paid).
2. **Sign in to [share.streamlit.io](https://share.streamlit.io)** with GitHub.
3. **New app** → select repo, branch `main`, main file `streamlit_app.py`.
4. **Advanced settings** → Python **3.11** → secrets:
   ```toml
   GEMINI_API_KEY = "your-google-ai-studio-key"
   ```
5. **Deploy.** ~3 minutes for first build.

## Get a Gemini API key (free)

[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → Create API key. Free tier: ~60 req/min on `gemini-2.5-flash`.

## Structure

```
paper-portfolio-tracker/
├── streamlit_app.py        # Entry point
├── requirements.txt
├── README.md
├── ARCHITECTURE.md         # Maintainer guide
├── .gitignore
├── state.json              # Persistent state (gitignored)
├── .streamlit/
│   ├── config.toml         # Theme
│   └── secrets.toml.example
└── app/
    ├── state.py            # Persistence + migrations
    ├── helpers.py          # Format utils
    ├── market.py           # yfinance + Finnhub fetch
    ├── ai.py               # Gemini integration
    ├── benchmarks.py       # SPY / index data with caching
    ├── sectors.py          # Ticker classification (sector/country)
    ├── styles.py           # Custom CSS
    └── pages/
        ├── overview.py     # NAV sparkline + this-week digest + Ask Gemini
        ├── build.py        # Basket builder + AI workflow
        ├── watchlist.py    # Idea pipeline
        ├── trade.py        # Holdings desk + drill-down + cash mgmt
        ├── review.py       # Charts + logs + AI risk analysis
        ├── insights.py     # Sector / contributors / concentration / beta
        └── settings.py     # Config + backup + reset
```

## Important: Streamlit Cloud filesystem is ephemeral

State stored in `state.json` does not persist across redeploys/restarts. The Settings tab has one-click backup/restore. Make a habit of downloading after meaningful changes.

## Migrating from the v8 HTML tracker

1. v8 HTML app: Settings → Backup → Download
2. This app: Settings → Restore → upload the JSON

The migrator handles schema differences automatically.

## Tech stack

- Streamlit 1.40+
- yfinance for quotes (primary) + Finnhub fallback
- Plotly for all charts
- Google Gemini for AI

## License

Personal project.
