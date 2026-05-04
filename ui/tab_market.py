"""
STIR Terminal — Tab 1: Market View
Embeds Dashboard A (HTML/JS/Chart.js) as a full-height iframe component,
AND provides a native Streamlit Overlay Mode for Scenario vs Market analysis.
"""

from __future__ import annotations
import os
import re
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from config.fomc_dates import ALL_FOMC_MEETINGS
from ui.styles import bb_section, bb_subsection, render_bloomberg_table


BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


def _read(name: str) -> str:
    path = os.path.join(BASE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _sub(pattern: str, replacement: str, text: str) -> str:
    return re.sub(pattern, lambda _: replacement, text)


@st.cache_data(show_spinner=False)
def _get_latest_market_data() -> list[float]:
    """Parse assets/data.js to extract the latest market premiums (fed1..fed21)."""
    try:
        data = _read("data.js")
        match = re.search(r"const RAW_MEETING_PREMIUMS = (\[.*?\]);", data, re.DOTALL)
        if match:
            arr = json.loads(match.group(1))
            if arr:
                last_row = arr[-1]
                # Extract fed1 to fed21
                premiums = []
                for i in range(1, 22):
                    val = last_row.get(f"fed{i}")
                    premiums.append(val if val is not None else None)
                return premiums
    except Exception:
        pass
    return [None] * 21


def _build_market_html() -> str:
    css    = _read("style.css")
    data   = _read("data.js")
    app    = _read("app.js")
    html   = _read("index.html")
    chart  = _read("chart_umd_min.js")

    # Inline CSS
    html = _sub(
        r'<link[^>]*href=["\']style\.css["\'][^>]*?>',
        f"<style>\n{css}\n</style>",
        html,
    )
    # Inline Chart.js
    html = _sub(
        r'<script\s+src=["\']chart_umd_min\.js["\']></script>',
        f"<script>\n{chart}\n</script>",
        html,
    )
    # Inline data.js
    html = _sub(
        r'<script\s+src=["\']data\.js["\']></script>',
        f"<script>\n{data}\n</script>",
        html,
    )
    # Inline app.js
    html = _sub(
        r'<script\s+src=["\']app\.js["\']></script>',
        f"<script>\n{app}\n</script>",
        html,
    )
    return html


def _render_overlay_section(cm):
    """Render the Plotly overlay chart and data table."""
    bb_section("MEETING PREMIUMS — OVERLAY MODE")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        view_mode = st.radio(
            "View Mode:",
            ["BOTH", "Market Data", "Scenario Cases"],
            horizontal=True,
            key="market_overlay_mode"
        )
    with col2:
        st.markdown(
            "<div style='padding-top:12px;color:#888;font-size:12px;text-align:right;'>"
            "Comparing live Scenario Engine cuts with latest historical Market Data.</div>",
            unsafe_allow_html=True
        )

    # 1. Prepare Data
    meetings = ALL_FOMC_MEETINGS[:21]
    labels   = [m["decision_date"].strftime("%b '%y") for m in meetings]
    
    market_premiums = _get_latest_market_data()
    # Market data might have fewer than 21 valid points; pad with None
    market_premiums = (market_premiums + [None]*21)[:21]

    # Scenario data
    case_lines = {}
    for case in cm.cases:
        # Cumulative cuts per meeting
        cuts = []
        for m in meetings:
            eff = m["effective_date"]
            # get the cut applied at this meeting
            bps = case["meeting_cuts"].get(eff, 0.0)
            cuts.append(bps)
        
        # Scenario "Premium" is cumulative cuts from base rate
        # Wait, meeting premium is actually cumulative!
        cum_cuts = []
        curr = 0.0
        for c in cuts:
            curr += c
            cum_cuts.append(curr)
        case_lines[case["id"]] = cum_cuts

    # 2. Build Plotly Chart
    fig = go.Figure()

    if view_mode in ["BOTH", "Market Data"]:
        fig.add_trace(go.Scatter(
            x=labels, y=market_premiums,
            name="Market Data (Latest)",
            mode="lines+markers",
            line=dict(color="#FF8C00", width=3, dash="dash"),
            marker=dict(size=8, symbol="diamond")
        ))

    if view_mode in ["BOTH", "Scenario Cases"]:
        colors = ["#4f8dff", "#00d4aa", "#f2cd32", "#ff4f8d", "#a78bfa"]
        for i, case in enumerate(cm.cases):
            color = colors[i % len(colors)]
            fig.add_trace(go.Scatter(
                x=labels, y=case_lines[case["id"]],
                name=f"Scenario: {case['name']}",
                mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=6)
            ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=30, b=20),
        height=750,
        xaxis=dict(showgrid=True, gridcolor="#333", tickangle=-45),
        yaxis=dict(showgrid=True, gridcolor="#333", title="Cumulative Cut/Hike (bps)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # 3. Build Per-Meeting Cuts Table
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    st.markdown("<div class='bb-sub-header'>Per-Meeting Cumulative Cuts (bps)</div>", unsafe_allow_html=True)

    # Columns: Meeting | Market | Case 1 | Case 2 ...
    col_labels = ["Meeting", "Market"] + [c["name"][:15] for c in cm.cases]
    data = []
    for i, m in enumerate(meetings):
        row = [labels[i]]
        row.append(market_premiums[i])
        for case in cm.cases:
            row.append(case_lines[case["id"]][i])
        data.append(row)
    
    # We transpose for Bloomberg table (rows=keys, cols=labels, data=lists)
    row_labels = [r[0] for r in data]
    t_data = []
    for j in range(1, len(col_labels)): # skip "Meeting"
        t_row = [r[j] for r in data]
        t_data.append(t_row)

    st.markdown(render_bloomberg_table(row_labels, col_labels[1:], t_data), unsafe_allow_html=True)
    st.markdown("<hr style='border-color:#333;margin:30px 0;'>", unsafe_allow_html=True)


def render_market_tab(base_sofr: float, base_effr: float, n_cases: int, cm):
    """Render the Market View tab."""

    # ── KPI mini-strip ────────────────────────────────────────────────────
    st.markdown(
        f"""<div class="kpi-mini-bar">
            <div class="kpi-mini-item">
                <div class="kpi-mini-label">SOFR (live)</div>
                <div class="kpi-mini-val">{base_sofr:.4f}%</div>
            </div>
            <div class="kpi-mini-item">
                <div class="kpi-mini-label">EFFR (live)</div>
                <div class="kpi-mini-val">{base_effr:.4f}%</div>
            </div>
            <div class="kpi-mini-item">
                <div class="kpi-mini-label">Scenario Cases</div>
                <div class="kpi-mini-val">{n_cases}</div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Native Overlay Section (disabled — embedded dashboard covers this) ──

    # ── Full Historical Dashboard (bidirectional component) ───────────────
    _ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
    _dashboard_component = components.declare_component("stir_dashboard", path=_ASSETS_DIR)
    selected_date = _dashboard_component(key="stir_dash", height=2200, default=None)

    # ── Structures + Trade Notes (driven by dashboard slider) ─────────────
    _render_date_analysis_section(selected_date)


# ── Trade Notes Persistence ──────────────────────────────────────────────────

_NOTES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "trade_notes.json")


def _load_notes() -> dict:
    if os.path.exists(_NOTES_FILE):
        try:
            with open(_NOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_notes(notes: dict):
    os.makedirs(os.path.dirname(_NOTES_FILE), exist_ok=True)
    with open(_NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)


# ── Meeting Premium Structures ───────────────────────────────────────────────

def _compute_premium_structures(premiums: list) -> dict:
    n = len(premiums)
    structures = {"spreads": {}, "flies": {}, "condors": {}, "deflys": {}}
    for i in range(n - 1):
        if premiums[i] is not None and premiums[i + 1] is not None:
            structures["spreads"][f"fed{i+2}-fed{i+1}"] = round(premiums[i + 1] - premiums[i], 2)
    for i in range(n - 2):
        if all(premiums[j] is not None for j in [i, i + 1, i + 2]):
            structures["flies"][f"fed{i+1}/fed{i+2}/fed{i+3}"] = round(
                premiums[i] - 2 * premiums[i + 1] + premiums[i + 2], 2)
    for i in range(n - 3):
        if all(premiums[j] is not None for j in [i, i + 1, i + 2, i + 3]):
            structures["condors"][f"fed{i+1}/fed{i+2}/fed{i+3}/fed{i+4}"] = round(
                premiums[i] - premiums[i + 1] - premiums[i + 2] + premiums[i + 3], 2)
            structures["deflys"][f"fed{i+1}/fed{i+2}/fed{i+3}/fed{i+4}"] = round(
                premiums[i] - 3 * premiums[i + 1] + 3 * premiums[i + 2] - premiums[i + 3], 2)
    return structures


def _get_all_premium_data() -> list:
    try:
        data = _read("data.js")
        match = re.search(r"const RAW_MEETING_PREMIUMS = (\[.*?\]);", data, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except Exception:
        pass
    return []


def _get_sr3_data() -> dict:
    """Parse SR3 data from data.js keyed by date."""
    try:
        data = _read("data.js")
        match = re.search(r"const RAW_SR3_DATA = (\[.*?\]);", data, re.DOTALL)
        if match:
            arr = json.loads(match.group(1))
            return {r["date"]: r for r in arr}
    except Exception:
        pass
    return {}


def _js_to_json(raw_js: str) -> str:
    """Convert JS object literal text to valid JSON."""
    # Strip JS line comments (// ...)
    s = re.sub(r"//[^\n]*", "", raw_js)
    # Replace single quotes with double quotes
    s = s.replace("'", '"')
    # Quote bare JS property names:  word: -> "word":
    s = re.sub(r'(?<=[{,\s])(\w+)\s*:', r'"\1":', s)
    # Remove trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def _get_js_fomc_meetings() -> list:
    """Parse FOMC meetings from data.js (the ground-truth list starting from 2025)."""
    try:
        data = _read("data.js")
        match = re.search(r"const FOMC_MEETINGS = (\[.*?\]);", data, re.DOTALL)
        if match:
            return json.loads(_js_to_json(match.group(1)))
    except Exception:
        pass
    return []


def _get_sr3_contracts() -> list:
    """Parse SR3 contract schedule from data.js."""
    try:
        data = _read("data.js")
        match = re.search(r"const SR3_CONTRACT_SCHEDULE = (\[.*?\]);", data, re.DOTALL)
        if match:
            return json.loads(_js_to_json(match.group(1)))
    except Exception:
        pass
    return []


def _render_date_analysis_section(js_selected_date=None):
    """Structures and trade notes driven by the JS dashboard slider."""

    all_data = _get_all_premium_data()
    if not all_data:
        st.info("No historical premium data available.")
        return

    sr3_data = _get_sr3_data()
    js_fomc = _get_js_fomc_meetings()  # Ground-truth meetings from data.js
    sr3_contracts = _get_sr3_contracts()
    date_to_idx = {row["date"]: i for i, row in enumerate(all_data)}
    available_dates = [row["date"] for row in all_data]
    n = len(available_dates)

    # ── Use date from JS dashboard slider (or default to latest) ──────────
    if js_selected_date and js_selected_date in date_to_idx:
        idx = date_to_idx[js_selected_date]
        selected_date = js_selected_date
    else:
        idx = n - 1
        selected_date = available_dates[-1]

    prev_date = available_dates[idx - 1] if idx > 0 else None

    # ── Determine which 21 meetings apply to selected_date ────────────────
    # "Next 21 meetings from selected_date" — same logic as app.js
    meetings_from_date = [m for m in js_fomc if m["date"] >= selected_date][:21]
    # Fallback to config if data.js parse fails
    if not meetings_from_date:
        meetings_from_date = [{"label": f"FED{i+1}", "isSEP": False} for i in range(21)]

    # ── Date indicator (no slider — driven by dashboard above) ────────────
    bb_section("ANALYSIS")
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;color:#4fc3f7;"
        f"font-size:13px;font-weight:700;margin:4px 0 12px 0;'>"
        f"<span>{available_dates[0]}</span>"
        f"<span style='color:#00B4D8;font-size:16px;'>📅 Selected: {selected_date}</span>"
        f"<span>{available_dates[-1]}</span></div>",
        unsafe_allow_html=True,
    )

    row = all_data[idx]
    premiums = [row.get(f"fed{i}") for i in range(1, 22)]
    prev_row = all_data[idx - 1] if idx > 0 else None
    prev_premiums = [prev_row.get(f"fed{i}") for i in range(1, 22)] if prev_row else [None] * 21

    # ── Helper for meeting labels ─────────────────────────────────────────
    def _meeting_label(i):
        if i < len(meetings_from_date):
            return meetings_from_date[i].get("label", f"FED{i+1}")
        return f"FED{i+1}"

    # ── Premium Values + Trade Notes side by side ─────────────────────────
    next_date = available_dates[idx + 1] if idx < n - 1 else None
    col_prem, col_notes = st.columns([3, 2])

    with col_prem:
        bb_subsection(f"PREMIUM TABLE — {selected_date}")
        table_html = '<div class="bb-table-wrap"><table class="bb-table">'
        table_html += '<thead><tr><th>MEETING</th><th>PREMIUM (bps)</th><th>CHG</th></tr></thead><tbody>'
        for i in range(21):
            if premiums[i] is None:
                continue
            m_lbl = _meeting_label(i)
            sep = " ⭐" if i < len(meetings_from_date) and meetings_from_date[i].get("isSEP") else ""
            val = premiums[i]
            cls = "pos-val" if val > 0 else ("neg-val" if val < 0 else "zero-val")
            # Change from previous day
            chg = ""
            if prev_row:
                prev_val = prev_row.get(f"fed{i+1}")
                if prev_val is not None:
                    d = val - prev_val
                    chg_cls = "pos-val" if d > 0.01 else ("neg-val" if d < -0.01 else "zero-val")
                    chg = f'<td class="{chg_cls}">{d:+.2f}</td>'
                else:
                    chg = '<td class="zero-val">—</td>'
            else:
                chg = '<td class="zero-val">—</td>'
            table_html += (
                f'<tr><td class="bb-row-label">{m_lbl}{sep}</td>'
                f'<td class="{cls}">{val:.2f}</td>{chg}</tr>'
            )
        table_html += "</tbody></table></div>"
        st.markdown(table_html, unsafe_allow_html=True)

    with col_notes:
        bb_subsection("📝 TRADE JOURNAL")
        notes = _load_notes()

        # Show previous day's notes (for review)
        if prev_date and prev_date in notes:
            prev_note = notes[prev_date]
            st.markdown(
                f"<div style='background:#0A0A00;border:1px solid #333;border-left:3px solid #00FF41;"
                f"padding:8px;margin-bottom:8px;font-size:10px;'>"
                f"<div style='color:#00FF41;font-size:9px;letter-spacing:1px;margin-bottom:4px;'>"
                f"📋 PREVIOUS DAY ({prev_date})</div>"
                f"<div style='color:#C0C0C0;white-space:pre-wrap;'>{prev_note.get('notes', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Current day's notes (editable)
        existing_note = notes.get(selected_date, {}).get("notes", "")
        note_text = st.text_area(
            f"Notes for {selected_date}",
            value=existing_note,
            height=150,
            key=f"note_{selected_date}",
            placeholder="Write trade ideas, observations, entries/exits...",
            label_visibility="collapsed",
        )
        if st.button("💾 SAVE NOTE", key="save_note_btn"):
            from datetime import datetime
            notes[selected_date] = {
                "notes": note_text,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            _save_notes(notes)
            st.success("Note saved!")

        # Show next day's notes (if they exist — for forward-looking trades)
        if next_date and next_date in notes:
            next_note = notes[next_date]
            st.markdown(
                f"<div style='background:#0A0A00;border:1px solid #333;border-left:3px solid #FF8C00;"
                f"padding:8px;margin-top:8px;font-size:10px;'>"
                f"<div style='color:#FF8C00;font-size:9px;letter-spacing:1px;margin-bottom:4px;'>"
                f"📌 NEXT DAY ({next_date})</div>"
                f"<div style='color:#C0C0C0;white-space:pre-wrap;'>{next_note.get('notes', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Structures from Meeting Premiums ──────────────────────────────────
    bb_subsection(f"STRUCTURES — {selected_date}")
    structs = _compute_premium_structures(premiums)

    # Also compute previous day structures for comparison
    prev_structs = None
    if prev_row:
        prev_premiums = [prev_row.get(f"fed{i}") for i in range(1, 22)]
        prev_structs = _compute_premium_structures(prev_premiums)

    # Build a mapping from fed-index to month labels (e.g. fed1 -> "Sep25")
    _month_labels = {}
    for i, m in enumerate(meetings_from_date[:21]):
        lbl = m.get("label", "")
        parts = lbl.split()
        if len(parts) >= 2:
            # e.g. "September 2025" -> "Sep25"
            mon = parts[0][:3]
            yr = parts[-1][-2:]  # last 2 digits of year
            _month_labels[f"fed{i+1}"] = f"{mon}{yr}"
        else:
            _month_labels[f"fed{i+1}"] = f"Fed{i+1}"

    def _humanize_structure_key(key: str) -> str:
        """Replace fed1/fed2/fed3 with Sep25/Dec25/Mar26 style labels."""
        parts = key.replace("-", "/").split("/")
        return "/".join(_month_labels.get(p.strip(), p.strip()) for p in parts)

    s1, s2, s3, s4 = st.tabs(["↔ SPREADS", "🦋 FLIES", "🔷 CONDORS", "🌀 DEFLYS"])

    for tab, stype, label in [
        (s1, "spreads", "SPREADS"),
        (s2, "flies", "BUTTERFLIES"),
        (s3, "condors", "CONDORS"),
        (s4, "deflys", "DEFLYS"),
    ]:
        with tab:
            items = structs.get(stype, {})
            if not items:
                st.markdown("<span style='color:#555;'>No data</span>", unsafe_allow_html=True)
                continue
            # Build table: Key | Value | Prev Day | Change
            col_labels = [selected_date]
            if prev_structs:
                col_labels += [f"Prev ({prev_date})", "Chg"]
            raw_keys = list(items.keys())
            row_labels = [_humanize_structure_key(k) for k in raw_keys]
            data = []
            for key in raw_keys:
                r = [items[key]]
                if prev_structs:
                    pv = prev_structs.get(stype, {}).get(key)
                    r.append(pv)
                    if pv is not None:
                        r.append(round(items[key] - pv, 2))
                    else:
                        r.append(None)
                data.append(r)
            st.markdown(
                render_bloomberg_table(row_labels, col_labels, data, fmt="{:.2f}"),
                unsafe_allow_html=True,
            )

    st.markdown("<hr style='border-color:#333;margin:30px 0;'>", unsafe_allow_html=True)

