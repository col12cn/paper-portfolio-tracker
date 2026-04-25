# Paper Portfolio Tracker

A Streamlit-based paper portfolio tracker with AI decision support. Python port of the original single-file HTML tracker.

**Features:**
- Track a paper portfolio (no real capital)
- Live quotes + weekly OHLCV via `yfinance` (free, no API key)
- AI workflow with two modes: generate fresh portfolio prompts, or evolve current portfolio
- Free-form "Ask Gemini" with full portfolio context
- Per-position drill-down (trades, news, OHLCV, ask AI)
- Trade preview before execute, one-click rebalance to target
- NAV chart, component price chart, sortable holdings, mobile-friendly
- Full state export/import as JSON for backup

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

Opens at `http://localhost:8501`. State persists in `state.json` in the working directory.

## Deploy to Streamlit Community Cloud

1. **Push to GitHub.** Create a public repo (Streamlit Cloud free tier requires public — paid allows private).
2. **Sign in to [share.streamlit.io](https://share.streamlit.io)** with your GitHub account.
3. **New app** → select your repo, branch `main`, main file `streamlit_app.py`.
4. **Advanced settings** → set **Python version 3.11** → paste secrets:
   ```toml
   GEMINI_API_KEY = "your-google-ai-studio-key"
   ```
5. **Deploy.** ~3 minutes for first build.

### Important: Streamlit Cloud filesystem is ephemeral

State is stored in `state.json` which **does not persist across redeploys or app restarts**. Two safety nets are built in:

- **Auto-export to download** — the Settings tab has a one-click "Download backup" button.
- **Restore from file** — drop a backup JSON back in to restore everything.

Make a habit of downloading a backup after meaningful changes (trades, rebalances, deposits). For real persistence on Streamlit Cloud, the next step would be wiring this to a free tier of Supabase, Turso, or similar — see "Future" section below.

### Single-user deployment

This app stores one shared portfolio per deployment. If you make your Streamlit Cloud app URL public, anyone visiting can see and modify your portfolio. Either:
- Keep your URL private, or
- Set the app to private in Streamlit Cloud (paid tier), or
- Add Streamlit's built-in authentication (`st.experimental_user`)

## Get a Gemini API key (free)

Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey), sign in with Google, click "Create API key". Free tier: ~60 requests/minute on `gemini-2.5-flash`. More than enough for this app.

## Folder structure

```
paper-portfolio-tracker/
├── streamlit_app.py        # Entry point (Streamlit Cloud expects this name)
├── requirements.txt
├── README.md
├── .gitignore
├── state.json              # Persistent state (created at first run, gitignored)
├── .streamlit/
│   ├── config.toml         # Theme settings
│   └── secrets.toml.example
└── app/
    ├── state.py            # State + persistence
    ├── helpers.py          # Utility functions
    ├── market.py           # yfinance + Finnhub data fetching
    ├── ai.py               # Gemini integration
    ├── styles.py           # Custom CSS
    └── pages/
        ├── overview.py
        ├── build.py
        ├── trade.py
        ├── review.py
        └── settings.py
```

## Migrating from the v8 HTML tracker

If you have history in the HTML version:
1. In the HTML app, go to Settings → Backup → Download backup
2. In this app, go to Settings → Restore → upload the JSON
3. The migrator will adapt the schema; small format differences are handled.

## Future improvements

- **Persistent storage on Cloud:** swap `state.json` for Supabase / Turso / SQLite-on-LiteFS. ~50 lines of changes.
- **Multi-portfolio:** namespace state by user (`st.experimental_user`) to support multiple portfolios in one deployment.
- **Backtesting:** add a `backtest.py` script using `vectorbt` or `bt` against historical data.
- **Risk analytics:** factor exposures, drawdown, Sharpe/Sortino — pandas + statsmodels.
- **Scheduled jobs:** GitHub Actions to fetch quotes nightly and commit `priceSnap` updates.

## Tech stack

- Streamlit 1.40+
- yfinance for market data (primary)
- Finnhub for market data (optional fallback)
- Plotly for charts
- Google Gemini for AI

## License

Personal project. Use as you like.
