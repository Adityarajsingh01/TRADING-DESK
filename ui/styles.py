"""
STIR Terminal — Bloomberg Terminal CSS & Styling
Fixed: no overflow:hidden, responsive sidebar, proper spacing.
"""

import streamlit as st

BLOOMBERG_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&display=swap');

/* ── Reset & Base ─────────────────────────────────────────────────── */
*, *::before, *::after {
    box-sizing: border-box;
}
html, body, [data-testid="stAppViewContainer"],
[data-testid="stApp"], .main {
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
    background-color: #0d1117 !important;
    color: #C0C0C0 !important;
}

/* Remove Streamlit default padding — allow natural scroll */
[data-testid="block-container"],
.block-container {
    padding: 0.5rem 1rem 2rem 1rem !important;
    max-width: 100% !important;
}

/* ── Scrollbar ────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #000; }
::-webkit-scrollbar-thumb { background: #00B4D8; border-radius: 3px; }

/* ── Bloomberg Header Bar ─────────────────────────────────────────── */
.bb-header {
    background: linear-gradient(90deg, #0a1628 0%, #0d1117 100%);
    border-bottom: 2px solid #00B4D8;
    padding: 8px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
    flex-wrap: wrap;
    gap: 4px;
}
.bb-header-title {
    color: #00B4D8;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}
.bb-header-sub {
    color: #4fc3f7;
    font-size: 10px;
    letter-spacing: 1px;
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}
.bb-header-time {
    color: #90caf9;
    font-size: 10px;
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}

/* ── Section Labels ───────────────────────────────────────────────── */
.bb-section {
    background: #0a1628;
    border-left: 3px solid #00B4D8;
    border-bottom: 1px solid #1a3050;
    padding: 4px 10px;
    color: #00B4D8;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin: 8px 0 4px 0;
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}
.bb-subsection {
    color: #4fc3f7;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    border-bottom: 1px solid #1a2a40;
    padding: 3px 0;
    margin: 6px 0 3px 0;
    text-transform: uppercase;
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}

/* ── Rate Display ─────────────────────────────────────────────────── */
.bb-rate-box {
    background: #0a1628;
    border: 1px solid #1a3050;
    border-radius: 2px;
    padding: 6px 10px;
    text-align: center;
    margin: 3px 0;
}
.bb-rate-label {
    color: #4fc3f7;
    font-size: 9px;
    letter-spacing: 2px;
    text-transform: uppercase;
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}
.bb-rate-value {
    color: #00FF41;
    font-size: 18px;
    font-weight: 700;
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}

/* ── Inputs ───────────────────────────────────────────────────────── */
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] select,
div[role="listbox"],
input[type="text"],
input[type="number"],
textarea {
    background-color: #0a1628 !important;
    color: #4fc3f7 !important;
    -webkit-text-fill-color: #4fc3f7 !important;
    caret-color: #4fc3f7 !important;
    border: 1px solid #1a3050 !important;
    border-radius: 2px !important;
    font-size: 12px !important;
    font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
    font-weight: 600 !important;
}
[data-testid="stTextInput"] input::placeholder {
    color: #555555 !important;
    -webkit-text-fill-color: #555555 !important;
    font-weight: 400 !important;
}
[data-testid="stSelectbox"] > div > div {
    background-color: #0a1628 !important;
    border: 1px solid #1a3050 !important;
    color: #4fc3f7 !important;
}

/* ── Buttons ──────────────────────────────────────────────────────── */
.stButton > button {
    background-color: #0d1117 !important;
    color: #00B4D8 !important;
    border: 1px solid #00B4D8 !important;
    border-radius: 2px !important;
    font-size: 11px !important;
    letter-spacing: 1px !important;
    font-weight: 700 !important;
    padding: 5px 14px !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background-color: #0a1628 !important;
    border-color: #4fc3f7 !important;
    color: #4fc3f7 !important;
    box-shadow: 0 0 8px rgba(0,180,216,0.4) !important;
}
.stButton > button[kind="primary"] {
    background-color: #00B4D8 !important;
    color: #000000 !important;
    border: 1px solid #00B4D8 !important;
    font-weight: 700 !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: #4fc3f7 !important;
    box-shadow: 0 0 12px rgba(0,180,216,0.6) !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    gap: 0 !important;
    border-bottom: 2px solid #1a3050 !important;
    background: #0d1117 !important;
}
[data-testid="stTabs"] button[role="tab"] {
    background: #0d1117 !important;
    color: #C0C0C0 !important;
    border: 1px solid #1a3050 !important;
    border-bottom: none !important;
    padding: 6px 18px !important;
    font-size: 11px !important;
    letter-spacing: 1px !important;
    font-weight: 600 !important;
    border-radius: 0 !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: #0a1628 !important;
    color: #00B4D8 !important;
    border-color: #00B4D8 !important;
    border-bottom: 2px solid #0a1628 !important;
}
[data-testid="stTabs"] button[role="tab"]:hover {
    background: #0a1628 !important;
    color: #4fc3f7 !important;
}

/* ── Multiselect ──────────────────────────────────────────────────── */
[data-testid="stMultiSelect"] > div > div {
    background-color: #0A0A00 !important;
    border: 1px solid #FF6600 !important;
}
span[data-baseweb="tag"] {
    background-color: #1A0D00 !important;
    border: 1px solid #FF6600 !important;
    color: #FF6600 !important;
    font-size: 10px !important;
}

/* ── Labels & Markdown ────────────────────────────────────────────── */
label, .stMarkdown p {
    color: #C0C0C0 !important;
    font-size: 11px !important;
}
h1 { color: #FF8C00 !important; font-size: 15px !important; letter-spacing: 3px !important; }
h2 { color: #FF6600 !important; font-size: 12px !important; letter-spacing: 2px !important; }
h3 { color: #FFB347 !important; font-size: 11px !important; letter-spacing: 1px !important; }

/* ── Expander ─────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #222 !important;
    background-color: #050505 !important;
}
[data-testid="stExpander"] summary {
    color: #FF6600 !important;
    font-size: 11px !important;
    letter-spacing: 1px !important;
}

/* ── Metric ───────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #0D0D00;
    border: 1px solid #333;
    padding: 6px !important;
    border-radius: 2px;
}
[data-testid="metric-container"] label {
    color: #FF8C00 !important;
    font-size: 9px !important;
    letter-spacing: 1px !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #00FF41 !important;
    font-size: 16px !important;
}

/* ── Checkbox & Radio ─────────────────────────────────────────────── */
[data-testid="stCheckbox"] label, [data-testid="stRadio"] label {
    color: #C0C0C0 !important;
    font-size: 11px !important;
}

/* ── Bloomberg Table ──────────────────────────────────────────────── */
.bb-table-wrap {
    overflow-x: auto;
    overflow-y: visible;
    width: 100%;
    max-width: 100%;
    border: 1px solid #333;
    margin-bottom: 10px;
    background: #000;
    /* Force a clearly visible horizontal scrollbar — overrides the global
       5px webkit rule above. Tables can be 1000s of px wide with many cases. */
    scrollbar-color: #FF6600 #0a1628;
    scrollbar-width: auto;
}
.bb-table-wrap::-webkit-scrollbar {
    height: 12px !important;
    width: 10px !important;
}
.bb-table-wrap::-webkit-scrollbar-track {
    background: #0a1628 !important;
    border-top: 1px solid #1a3050;
}
.bb-table-wrap::-webkit-scrollbar-thumb {
    background: #FF6600 !important;
    border-radius: 6px;
    border: 2px solid #0a1628;
}
.bb-table-wrap::-webkit-scrollbar-thumb:hover {
    background: #FFB347 !important;
}
table.bb-table {
    /* Was width:100% — that forced the table to shrink-fit the wrap, so the
       wrap's overflow-x:auto never kicked in. min-content + min-width:100%
       lets the table grow as wide as its columns need (triggering the
       horizontal scrollbar) while still filling the wrap when narrow. */
    width: max-content;
    min-width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    table-layout: auto;
    background: #000;
}
table.bb-table thead {
    position: sticky;
    top: 0;
    z-index: 10;
    background: #0a1628;
}
table.bb-table th {
    background: #0a1628;
    color: #4fc3f7;
    border: 1px solid #1a3050;
    padding: 4px 8px;
    text-align: center;
    font-size: 10px;
    letter-spacing: 1px;
    font-weight: 700;
    white-space: nowrap;
    min-width: 80px;
}
table.bb-table td {
    border: 1px solid #0d1b2a;
    padding: 3px 8px;
    text-align: right;
    color: #C0C0C0;
    white-space: nowrap;
    font-size: 11px;
}
table.bb-table td.bb-row-label {
    text-align: left;
    color: #90caf9;
    font-weight: 600;
    position: sticky;
    left: 0;
    background: #0d1117;
    border-right: 1px solid #1a3050;
    padding-left: 8px;
    min-width: 160px;
    white-space: nowrap;
}
table.bb-table tr:nth-child(even) td { background: #0a1220; }
table.bb-table tr:hover td { background: #0a1628 !important; color: #e0e0e0 !important; }
table.bb-table td.pos-val { color: #00FF41 !important; font-weight: 600; }
table.bb-table td.neg-val { color: #FF3131 !important; font-weight: 600; }
table.bb-table td.zero-val { color: #666 !important; }

/* ── Case List ────────────────────────────────────────────────────── */
.bb-case-item {
    background: #0A0A00;
    border: 1px solid #222;
    border-left: 3px solid #FF6600;
    padding: 4px 8px;
    margin: 2px 0;
    font-size: 10px;
}
.bb-case-id   { color: #555; font-size: 9px; }
.bb-case-name { color: #FF6600; font-weight: 600; }
.bb-case-info { color: #777; font-size: 9px; }

/* ── Status bar ───────────────────────────────────────────────────── */
.bb-status {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #0D0800;
    border-top: 1px solid #FF6600;
    padding: 3px 14px;
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    font-size: 10px;
    color: #FF6600;
    z-index: 9999;
}

/* ── Trade builder card ───────────────────────────────────────────── */
.tb-card {
    background: #080800;
    border: 1px solid #333;
    border-left: 3px solid #FF8C00;
    padding: 12px 16px;
    margin-bottom: 12px;
    border-radius: 2px;
}
.tb-card-title {
    color: #FF8C00;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 10px;
    text-transform: uppercase;
}

/* ── KPI mini bar ────────────────────────────────────────────────── */
.kpi-mini-bar {
    display: flex;
    gap: 16px;
    background: #080800;
    border-bottom: 1px solid #333;
    padding: 5px 14px;
    flex-wrap: wrap;
    align-items: center;
}
.kpi-mini-item {
    display: flex;
    flex-direction: column;
    align-items: center;
}
.kpi-mini-label { color: #888; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; }
.kpi-mini-val   { color: #FF8C00; font-size: 13px; font-weight: 700; }
.kpi-mini-val.pos { color: #00FF41; }
.kpi-mini-val.neg { color: #FF3131; }

/* ── Hide Streamlit branding ──────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden !important; }
[data-testid="stToolbar"] { display: none !important; }
</style>
"""

def inject_bloomberg_css():
    st.markdown(BLOOMBERG_CSS, unsafe_allow_html=True)


def bb_header(title: str, subtitle: str = "SR1 | ZQ | SR3 | SPREADS | FLIES"):
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    st.markdown(f"""
    <div class="bb-header">
        <div>
            <div class="bb-header-title">⬛ {title}</div>
            <div class="bb-header-sub">{subtitle}</div>
        </div>
        <div class="bb-header-time">🕐 {now}</div>
    </div>
    """, unsafe_allow_html=True)


def bb_section(label: str):
    st.markdown(f'<div class="bb-section">{label}</div>', unsafe_allow_html=True)


def bb_subsection(label: str):
    st.markdown(f'<div class="bb-subsection">▸ {label}</div>', unsafe_allow_html=True)


def render_bloomberg_table(
    row_labels: list,
    col_labels: list,
    data: list,
    title: str = "",
    fmt: str = "{:.4f}",
) -> str:
    html = '<div class="bb-table-wrap">'
    if title:
        html += f'<div class="bb-subsection">▸ {title}</div>'
    html += '<table class="bb-table"><thead><tr>'
    html += '<th>CONTRACT</th>'
    for col in col_labels:
        short = col.replace('\n', ' ')
        html += f'<th>{short}</th>'
    html += '</tr></thead><tbody>'

    for row_lbl, row in zip(row_labels, data):
        html += '<tr>'
        html += f'<td class="bb-row-label">{row_lbl}</td>'
        for val in row:
            if val is None or (isinstance(val, float) and val != val):
                html += '<td class="zero-val">—</td>'
            else:
                try:
                    fval = float(val)
                    cls  = "pos-val" if fval > 0.0001 else ("neg-val" if fval < -0.0001 else "zero-val")
                    html += f'<td class="{cls}">{fmt.format(fval)}</td>'
                except (TypeError, ValueError):
                    html += f'<td class="zero-val">{val}</td>'
        html += '</tr>'

    html += '</tbody></table></div>'
    return html


def status_bar(n_cases: int, base_sofr: float, base_effr: float):
    st.markdown(f"""
    <div class="bb-status">
        <span>STIR TRADING TERMINAL</span>
        <span>SOFR: <b>{base_sofr:.4f}%</b> &nbsp;|&nbsp; EFFR: <b>{base_effr:.4f}%</b></span>
        <span>CASES LOADED: <b>{n_cases}</b></span>
    </div>
    """, unsafe_allow_html=True)
