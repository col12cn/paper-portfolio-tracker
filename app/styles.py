"""Custom CSS — Bloomberg-inspired modern aesthetic.

Color philosophy:
- Near-black (#0a0a0a) base for terminal density without harsh pure black
- Bloomberg amber (#FFB800) as the distinctive primary accent
- Cyan (#00B8D4) for interactive/secondary emphasis
- Modern vibrant P/L colors (#00C896 / #FF4757) over soft pastels
- Inter for UI, JetBrains Mono for all numeric/financial data

Type hierarchy via weight + size, not visual containers.
4-6px corner radii — sharp without being brutal.
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  /* Surfaces */
  --bg:           #0a0a0a;
  --bg-soft:      #0f0f0f;
  --panel:        #161616;
  --panel-2:      #1f1f1f;
  --panel-input:  #0d0d0d;
  --line:         #2a2a2a;
  --line-strong:  #3a3a3a;

  /* Text */
  --text:         #f5f5f5;
  --text-2:       #b8b8b8;
  --muted:        #888888;
  --muted-2:      #555555;

  /* Accents */
  --accent:       #FFB800;
  --accent-bold:  #FFA000;
  --accent-soft:  rgba(255, 184, 0, 0.10);
  --cool:         #00B8D4;
  --cool-soft:    rgba(0, 184, 212, 0.10);

  /* P/L */
  --good:         #00C896;
  --good-soft:    rgba(0, 200, 150, 0.10);
  --bad:          #FF4757;
  --bad-soft:     rgba(255, 71, 87, 0.10);
  --warn:         #FFA726;
  --warn-soft:    rgba(255, 167, 38, 0.10);

  /* Type */
  --font-sans:    'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono:    'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
}

/* ───────────────────────────── App-level ──────────────────────────────── */
.stApp {
  background: var(--bg);
  font-family: var(--font-sans);
  color: var(--text);
}

.main .block-container {
  padding-top: 1.5rem;
  padding-bottom: 4rem;
  max-width: 1400px;
}

.stMetric, .stNumberInput, [data-testid="stDataFrame"] {
  font-feature-settings: "tnum" 1;
}

/* ───────────────────────────── Masthead ───────────────────────────────── */
h1 {
  font-family: var(--font-sans);
  font-weight: 700 !important;
  letter-spacing: -0.02em !important;
  color: var(--text);
}

.paper-badge {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.18em;
  padding: 4px 10px;
  border: 1px solid var(--accent);
  color: var(--accent);
  border-radius: 3px;
  background: var(--accent-soft);
  margin-left: 12px;
  vertical-align: middle;
  text-transform: uppercase;
}

/* ──────────────────────────── Tabs (terminal-style underline) ─────────── */
.stTabs [data-baseweb="tab-list"] {
  gap: 0;
  background: transparent;
  border-bottom: 1px solid var(--line);
}

.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  padding: 10px 20px !important;
  margin: 0 4px 0 0 !important;
  color: var(--muted) !important;
  font-family: var(--font-sans) !important;
  font-weight: 500 !important;
  font-size: 12px !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  transition: all 0.12s ease;
}

.stTabs [data-baseweb="tab"]:hover {
  color: var(--text-2) !important;
}

.stTabs [aria-selected="true"] {
  color: var(--accent) !important;
  border-bottom-color: var(--accent) !important;
  background: transparent !important;
  font-weight: 600 !important;
}

/* ──────────────────────────── Metrics ─────────────────────────────────── */
[data-testid="stMetric"] {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px 16px;
  transition: border-color 0.12s ease;
}

[data-testid="stMetric"]:hover {
  border-color: var(--line-strong);
}

[data-testid="stMetricLabel"] {
  color: var(--muted) !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

[data-testid="stMetricValue"] {
  font-family: var(--font-mono) !important;
  font-feature-settings: "tnum" 1;
  font-size: 24px !important;
  font-weight: 600 !important;
  color: var(--text) !important;
  letter-spacing: -0.01em;
  margin-top: 4px;
}

[data-testid="stMetricDelta"] {
  font-family: var(--font-mono) !important;
  font-size: 11px !important;
  font-weight: 500 !important;
}

/* ──────────────────────────── Inputs ──────────────────────────────────── */
.stTextInput input, .stNumberInput input, .stTextArea textarea {
  background: var(--panel-input) !important;
  border: 1px solid var(--line) !important;
  border-radius: 4px !important;
  color: var(--text) !important;
  font-family: var(--font-sans) !important;
  font-size: 13px !important;
  padding: 8px 12px !important;
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}

.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent) !important;
  outline: none !important;
}

.stSelectbox > div > div, [data-baseweb="select"] > div {
  background: var(--panel-input) !important;
  border: 1px solid var(--line) !important;
  border-radius: 4px !important;
  color: var(--text) !important;
  font-family: var(--font-sans) !important;
  font-size: 13px !important;
}

label, [data-testid="stWidgetLabel"] {
  color: var(--text-2) !important;
  font-size: 11px !important;
  font-weight: 500 !important;
  letter-spacing: 0.04em !important;
  text-transform: uppercase;
}

/* ──────────────────────────── Buttons ─────────────────────────────────── */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {
  background: var(--accent) !important;
  color: #0a0a0a !important;
  border: none !important;
  border-radius: 4px !important;
  padding: 8px 16px !important;
  font-family: var(--font-sans) !important;
  font-weight: 600 !important;
  font-size: 11px !important;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  transition: all 0.12s ease;
  box-shadow: none !important;
}

.stButton button:hover, .stDownloadButton button:hover, .stFormSubmitButton button:hover {
  background: var(--accent-bold) !important;
  color: #0a0a0a !important;
  transform: translateY(-1px);
}

.stButton button:disabled {
  background: var(--panel-2) !important;
  color: var(--muted-2) !important;
  cursor: not-allowed;
  transform: none !important;
}

.stButton button[kind="secondary"] {
  background: var(--panel-2) !important;
  color: var(--text) !important;
  border: 1px solid var(--line) !important;
}

.stButton button[kind="secondary"]:hover {
  background: var(--panel) !important;
  border-color: var(--accent) !important;
  color: var(--accent) !important;
}

/* ──────────────────────────── Containers ──────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: 6px !important;
  padding: 8px !important;
}

/* ──────────────────────────── Headers in containers ───────────────────── */
h2, h3, h4, h5 {
  font-family: var(--font-sans);
  font-weight: 600 !important;
  color: var(--text);
  letter-spacing: -0.01em;
}

h3 {
  font-size: 15px !important;
  margin-top: 4px !important;
  margin-bottom: 6px !important;
  text-transform: uppercase;
  letter-spacing: 0.04em !important;
  color: var(--text) !important;
}

h4 {
  font-size: 13px !important;
  text-transform: uppercase;
  letter-spacing: 0.04em !important;
  color: var(--muted) !important;
  font-weight: 600 !important;
}

/* ──────────────────────────── DataFrames ──────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--line) !important;
  border-radius: 6px;
  overflow: hidden;
}

[data-testid="stDataFrame"] [role="grid"] {
  font-family: var(--font-mono) !important;
  font-size: 12px !important;
}

[data-testid="stDataFrame"] [role="columnheader"] {
  background: var(--panel-2) !important;
  color: var(--muted) !important;
  font-family: var(--font-sans) !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase;
  border-bottom: 1px solid var(--line) !important;
}

[data-testid="stDataFrame"] [role="cell"] {
  font-feature-settings: "tnum" 1;
  border-bottom: 1px solid var(--line) !important;
  color: var(--text) !important;
}

/* ──────────────────────────── Captions ────────────────────────────────── */
[data-testid="stCaptionContainer"], small {
  color: var(--muted) !important;
  font-size: 11px !important;
  line-height: 1.5;
}

/* ──────────────────────────── Helper classes ──────────────────────────── */
.mono { font-family: var(--font-mono); font-feature-settings: "tnum" 1; }

.label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.value {
  font-family: var(--font-mono);
  font-size: 26px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.02em;
  font-feature-settings: "tnum" 1;
}

.good { color: var(--good); }
.bad { color: var(--bad); }
.warn { color: var(--warn); }
.muted-text { color: var(--muted); }
.accent { color: var(--accent); }
.cool { color: var(--cool); }

/* ──────────────────────────── Pills / badges ──────────────────────────── */
.pill {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--text-2);
  text-transform: uppercase;
  vertical-align: middle;
}

.pill-good { background: var(--good-soft); color: var(--good); border-color: rgba(0, 200, 150, 0.3); }
.pill-bad  { background: var(--bad-soft);  color: var(--bad);  border-color: rgba(255, 71, 87, 0.3); }
.pill-warn { background: var(--warn-soft); color: var(--warn); border-color: rgba(255, 167, 38, 0.3); }
.pill-accent { background: var(--accent-soft); color: var(--accent); border-color: rgba(255, 184, 0, 0.3); }
.pill-cool { background: var(--cool-soft); color: var(--cool); border-color: rgba(0, 184, 212, 0.3); }

/* ──────────────────────────── Section divider ─────────────────────────── */
.divider {
  border-top: 1px solid var(--line);
  margin: 16px 0;
}

/* ──────────────────────────── Onboarding card ─────────────────────────── */
.onboard {
  background: linear-gradient(135deg, var(--accent-soft), transparent);
  border: 1px solid var(--accent);
  border-radius: 6px;
  padding: 18px;
  margin-bottom: 12px;
}

/* ──────────────────────────── Insight panels ──────────────────────────── */
.insight {
  background: var(--bg-soft);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  padding: 14px 16px;
  white-space: pre-wrap;
  line-height: 1.65;
  font-size: 13px;
  color: var(--text);
}

.insight-cool { border-left-color: var(--cool); }
.insight-warn { border-left-color: var(--warn); }
.insight-good { border-left-color: var(--good); }

.insight-meta {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 8px;
  font-family: var(--font-mono);
}

.insight-meta strong {
  color: var(--accent);
  font-weight: 600;
  margin-right: 6px;
}

/* ──────────────────────────── Position card (basket display) ──────────── */
.position-row {
  border-top: 1px solid var(--line);
  padding: 12px 0;
}

.position-row:first-child {
  border-top: none;
}

.position-ticker {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 14px;
  color: var(--text);
  letter-spacing: 0.02em;
}

.position-name {
  color: var(--text-2);
  font-size: 12px;
  margin-top: 2px;
}

.position-why {
  color: var(--muted);
  font-size: 11px;
  margin-top: 6px;
  line-height: 1.5;
}

/* ──────────────────────────── Plotly tweaks ───────────────────────────── */
.js-plotly-plot .modebar { background: transparent !important; }

/* ──────────────────────────── Streamlit chrome ────────────────────────── */
[data-testid="stHeader"] { background: transparent; }
footer { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

/* ──────────────────────────── Expander ────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid var(--line) !important;
  border-radius: 6px !important;
  background: var(--panel) !important;
}

[data-testid="stExpander"] summary {
  font-family: var(--font-sans) !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  color: var(--text-2) !important;
  padding: 10px 14px !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

[data-testid="stExpander"] summary:hover {
  color: var(--accent) !important;
}

/* ──────────────────────────── Dialog / modal ──────────────────────────── */
[role="dialog"] {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: 8px !important;
}

/* ──────────────────────────── Progress bar ────────────────────────────── */
.stProgress > div > div {
  background-color: var(--accent) !important;
}

/* ──────────────────────────── Alerts ──────────────────────────────────── */
.stAlert {
  border-radius: 4px !important;
  font-size: 12px !important;
  font-family: var(--font-sans) !important;
}

[data-testid="stAlertContentSuccess"] { border-left: 3px solid var(--good) !important; }
[data-testid="stAlertContentWarning"] { border-left: 3px solid var(--warn) !important; }
[data-testid="stAlertContentError"]   { border-left: 3px solid var(--bad)  !important; }
[data-testid="stAlertContentInfo"]    { border-left: 3px solid var(--cool) !important; }

/* ──────────────────────────── Radio / toggle ──────────────────────────── */
.stRadio [role="radiogroup"] label {
  font-family: var(--font-sans) !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  color: var(--text-2) !important;
  text-transform: none !important;
  letter-spacing: normal !important;
}
</style>
"""


def inject():
    """Inject the CSS into the Streamlit app."""
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
