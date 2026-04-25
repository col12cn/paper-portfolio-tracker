"""Custom CSS injection to recreate the dark Bloomberg-ish aesthetic of v8.

Streamlit's native theming covers basics; this layers on the specific look
(monospace numbers, thin borders, accent dots, paper badge, etc.).
"""

CSS = """
<style>
:root {
  --bg: #0b1020; --panel: #121933; --panel-2: #192349; --panel-3: #0f1732;
  --text: #ecf1ff; --muted: #a8b4d8; --muted-2: #7385b8;
  --line: #2d3a6b;
  --good: #27c281; --bad: #ff6b6b; --warn: #f3b74f;
  --accent: #7aa2ff;
  --paper-flag: #c9a96e;
}

/* App-level */
.stApp { background: linear-gradient(180deg, #0b1020 0%, #101834 100%); }

/* Tighten container spacing */
.main .block-container { padding-top: 1.4rem; padding-bottom: 4rem; max-width: 1400px; }

/* Masthead pieces */
.paper-badge {
  display: inline-block;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px;
  letter-spacing: 0.18em; padding: 4px 10px;
  border: 1px solid var(--paper-flag); color: var(--paper-flag);
  border-radius: 999px; background: rgba(201, 169, 110, 0.07);
  margin-left: 12px; vertical-align: middle;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  gap: 6px;
  background: transparent;
}
.stTabs [data-baseweb="tab"] {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: 12px !important;
  padding: 8px 18px !important;
  color: var(--text) !important;
  font-weight: 500 !important;
}
.stTabs [aria-selected="true"] {
  background: var(--accent) !important;
  color: #08112b !important;
  border-color: var(--accent) !important;
  font-weight: 700 !important;
}

/* Metrics — tighter than default */
[data-testid="stMetric"] {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
}
[data-testid="stMetricLabel"] {
  color: var(--muted) !important;
  font-size: 11px !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
[data-testid="stMetricValue"] {
  font-feature-settings: "tnum" 1;
  font-size: 22px !important;
  font-weight: 700 !important;
}

/* Inputs */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox > div {
  background: var(--panel-3) !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
  color: var(--text) !important;
}

/* Buttons */
.stButton button {
  background: var(--accent);
  color: #08112b;
  border: none;
  border-radius: 10px;
  padding: 8px 16px;
  font-weight: 700;
  transition: all 0.15s ease;
}
.stButton button:hover {
  background: #5a82e0;
  color: #08112b;
  transform: translateY(-1px);
}
/* Secondary button styling via kind=secondary */
.stButton button[kind="secondary"] {
  background: #334372;
  color: var(--text);
}

/* Dataframes */
[data-testid="stDataFrame"] {
  border: 1px solid var(--line);
  border-radius: 12px;
}

/* Cards (using st.container with border=True) */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(18, 25, 51, 0.92);
  border: 1px solid var(--line) !important;
  border-radius: 16px !important;
  padding: 6px;
}

/* Mono helper */
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-feature-settings: "tnum" 1; }

/* Pills/badges */
.pill {
  display: inline-block;
  padding: 4px 10px; border-radius: 999px;
  font-size: 11px; font-weight: 700;
  background: #1f2b55; border: 1px solid var(--line);
  color: #dce5ff; letter-spacing: 0.02em;
}
.pill-good { background: rgba(39, 194, 129, 0.15); color: #57df9f; border-color: var(--good); }
.pill-bad  { background: rgba(255, 107, 107, 0.15); color: #ff9090; border-color: var(--bad); }
.pill-warn { background: rgba(243, 183, 79, 0.15); color: #ffd27d; border-color: var(--warn); }

/* Color helpers */
.good { color: var(--good); }
.bad  { color: var(--bad); }
.muted-text { color: var(--muted); }
.warn-text  { color: var(--warn); }

/* Section dividers */
.divider { border-top: 1px solid var(--line); margin: 16px 0; }

/* Onboarding card */
.onboard {
  background: linear-gradient(135deg, rgba(122, 162, 255, 0.10), rgba(122, 162, 255, 0.02));
  border: 1px solid var(--accent);
  border-radius: 16px; padding: 18px; margin-bottom: 12px;
}

/* Week range bar */
.week-range-bar {
  position: relative; height: 4px; background: var(--line); border-radius: 2px;
}
.week-range-marker {
  position: absolute; top: -2px; width: 2px; height: 8px;
  background: var(--accent); border-radius: 1px;
}
</style>
"""


def inject():
    """Inject the CSS into the Streamlit app."""
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
