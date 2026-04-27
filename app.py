"""
STIR Trading Terminal — Unified Entry Point
Merges Dashboard A (market data visualizer) + Dashboard B (scenario engine).

Usage:
    streamlit run app.py

Deploy:
    Push to GitHub → connect Streamlit Cloud → set main file = app.py
"""

import streamlit as st
from datetime import datetime

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="STIR Trading Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get help":     None,
        "Report a bug": None,
        "About":        "STIR Trading Terminal — Market Data + Scenario Engine",
    },
)

# ── Imports after page config ─────────────────────────────────────────────────
from ui.styles       import inject_bloomberg_css, bb_header, status_bar
from ui.tab_market        import render_market_tab
from ui.tab_structures    import render_structures_tab
from ui.tab_trade_builder import render_trade_builder_tab

from core.case_manager import CaseManager
from core.date_utils   import generate_sr1_contracts, generate_zq_contracts, \
                               generate_sr3_contracts
from core.live_data    import start_live_data
from config.constants  import SR1_ZQ_HORIZON_MONTHS

# ── CSS ───────────────────────────────────────────────────────────────────────
inject_bloomberg_css()

# ── Session state: CaseManager (persists across reruns) ───────────────────────
if "case_manager" not in st.session_state:
    st.session_state["case_manager"] = CaseManager()
cm = st.session_state["case_manager"]

# ── Contracts ─────────────────────────────────────────────────────────────────
def load_contracts():
    sr1 = generate_sr1_contracts(SR1_ZQ_HORIZON_MONTHS)
    zq  = generate_zq_contracts(SR1_ZQ_HORIZON_MONTHS)
    sr3 = generate_sr3_contracts()
    return sr1, zq, sr3

sr1c, zqc, sr3c = load_contracts()

# Start live data stream
start_live_data(sr1c, zqc, sr3c)


# ── Header ────────────────────────────────────────────────────────────────────
bb_header(
    title    = "STIR TRADING TERMINAL",
    subtitle = (
        f"SR1({len(sr1c)}) · ZQ({len(zqc)}) · SR3({len(sr3c)}) · CASES({len(cm.cases)})"
        f" | Market Data + Scenario Engine"
    ),
)

# Read base rates directly from session state for status bar and tab 1
base_sofr = st.session_state.get("base_sofr", 3.64)
base_effr = st.session_state.get("base_effr", 3.64)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN PANEL — 3 Tabs
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs([
    "📈  CASE ANALYZER",
    "🧾  TRADE BUILDER",
    "📊  HISTORICAL",
])

with tab1:
    render_structures_tab(cm, sr1c, zqc, sr3c)

with tab2:
    render_trade_builder_tab(cm, sr1c, zqc, sr3c)

with tab3:
    render_market_tab(base_sofr, base_effr, len(cm.cases), cm)

# ── Status bar ────────────────────────────────────────────────────────────────
status_bar(len(cm.cases), base_sofr, base_effr)
