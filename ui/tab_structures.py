"""
STIR Terminal — Tab 2: Structures
Outrights · Spreads · Butterflies · Condors · Deflys
All rendered from Python pricing engine.
"""

from __future__ import annotations
import streamlit as st
from typing import Dict, List
from datetime import date, timedelta

from ui.styles import bb_section, bb_subsection, render_bloomberg_table
from core.structures import (
    compute_spreads, compute_butterflies, compute_condors, compute_deflys,
)
from ui.input_panel import (
    render_base_rates, render_formula_builder, render_case_builder, render_case_list,
    render_bulk_generator,
)
from config.constants import (
    SR1_SPREAD_GAPS, ZQ_SPREAD_GAPS, SR3_SPREAD_GAPS,
    SR1_FLY_GAPS,    ZQ_FLY_GAPS,    SR3_FLY_GAPS,
)

# Condor/Defly gaps (confirmed by user)
SR1_CONDOR_GAPS = [1]
ZQ_CONDOR_GAPS  = [1]
SR3_CONDOR_GAPS = [1, 2]
SR1_DEFLY_GAPS  = [1]
ZQ_DEFLY_GAPS   = [1]
SR3_DEFLY_GAPS  = [1, 2]


# ── Cached price computation ──────────────────────────────────────────────────

@st.cache_data(ttl=5, show_spinner=False)
def _compute_prices_cached(
    case_id: str,
    base_sofr: float, base_effr: float,
    sofr_path_str: dict, effr_path_str: dict,
    sr1_meta: tuple, zq_meta: tuple, sr3_meta: tuple,
) -> dict:
    from core.pricing_engine import price_sr1, price_zq, price_sr3
    sofr = {date.fromisoformat(k): v for k, v in sofr_path_str.items()}
    effr = {date.fromisoformat(k): v for k, v in effr_path_str.items()}

    sr1_px = {code: price_sr1(yr, mo, sofr, base_sofr) for code, yr, mo in sr1_meta}
    zq_px  = {code: price_zq(yr, mo, effr, base_effr)  for code, yr, mo in zq_meta}
    sr3_px = {
        code: price_sr3(date.fromisoformat(rs), date.fromisoformat(re), sofr, base_sofr)
        for code, rs, re in sr3_meta
    }
    return {"SR1": sr1_px, "ZQ": zq_px, "SR3": sr3_px}


def _prices_for_cases(
    selected: List[dict],
    sr1c: list, zqc: list, sr3c: list,
) -> Dict[str, dict]:
    from core.case_manager import build_rate_path
    sr1_meta = tuple((c["code"], c["year"], c["month"]) for c in sr1c)
    zq_meta  = tuple((c["code"], c["year"], c["month"]) for c in zqc)
    sr3_meta = tuple((c["code"], c["ref_start"].isoformat(), c["ref_end"].isoformat()) for c in sr3c)
    out = {}
    for case in selected:
        # ALWAYS rebuild rate_path live from year_configs.
        # Never use the stored rate_path — it may be stale or built with old logic.
        sofr_path, effr_path, _ = build_rate_path(
            case["base_sofr"], case["base_effr"], case.get("year_configs", {})
        )
        sp = {k.isoformat(): v for k, v in sofr_path.items()}
        ep = {k.isoformat(): v for k, v in effr_path.items()}
        out[case["id"]] = _compute_prices_cached(
            case["id"], case["base_sofr"], case["base_effr"],
            sp, ep, sr1_meta, zq_meta, sr3_meta,
        )
    return out



# ── Case selector ─────────────────────────────────────────────────────────────

MULTISELECT_THRESHOLD = 100  # above this, the multiselect itself is the bottleneck


def _case_selector(cm) -> List[dict]:
    if not cm.cases:
        st.info("No cases yet — build them in the input panel above.")
        return []

    n_cases = len(cm.cases)

    # ── Many cases: skip the multiselect entirely. Streamlit's multiselect
    # widget renders all options into the DOM; with 1000+ items it freezes
    # the browser before the window slider even gets to do its job.
    # Treat ALL cases as selected and let _apply_display_window do the work.
    if n_cases > MULTISELECT_THRESHOLD:
        st.markdown(
            f"<div style='color:#FF8C00;font-size:11px;letter-spacing:1px;"
            f"margin-bottom:4px;'>"
            f"📂 ALL CASES ({n_cases:,}) — multiselect disabled for performance"
            f"</div>"
            f"<small style='color:#888'>"
            f"With {n_cases:,} cases the multiselect dropdown is too slow. "
            f"All cases are treated as selected; use the display window slider "
            f"below to scroll through them in chunks."
            f"</small>",
            unsafe_allow_html=True,
        )
        return list(cm.cases)

    # ── ≤ MULTISELECT_THRESHOLD: keep the rich multiselect ─────────────────
    opts = [f"{c['id']} | {c['name']}" for c in cm.cases]
    sel_key = "struct_case_sel"
    ca, cb, cc = st.columns([2, 1, 1])
    with ca:
        st.markdown(
            f"<span style='color:#FF8C00;font-size:11px;letter-spacing:1px;'>"
            f"SELECT CASES ({n_cases} available)</span>",
            unsafe_allow_html=True,
        )
    with cb:
        if st.button("✅ All", key="case_sel_all", help="Select all cases"):
            st.session_state[sel_key] = opts
    with cc:
        if st.button("✕ Clear", key="case_sel_clear", help="Clear selection"):
            st.session_state[sel_key] = []

    if sel_key not in st.session_state:
        st.session_state[sel_key] = opts[:]

    # Keep previously-selected cases that still exist; auto-select newly added
    # only for small batches (manual builder), not bulk dumps.
    current_sel = st.session_state.get(sel_key, [])
    valid_opts_set = set(opts)
    existing_valid = [s for s in current_sel if s in valid_opts_set]
    existing_set   = set(existing_valid)
    newly_added    = [o for o in opts if o not in existing_set]
    if newly_added and len(newly_added) <= 5:
        st.session_state[sel_key] = existing_valid + newly_added
    else:
        st.session_state[sel_key] = existing_valid

    sel = st.multiselect(
        "Cases:", opts,
        key=sel_key,
        label_visibility="collapsed",
        placeholder=f"Search & select from {n_cases} cases…",
    )

    ids = [s.split(" | ")[0] for s in sel]
    return [c for c in cm.cases if c["id"] in ids]


# ── Display window (caps how many cases are priced/rendered at once) ──────────

MAX_DISPLAY_CASES = 50


def _apply_display_window(selected: List[dict]) -> List[dict]:
    """
    When the user has many cases selected, render only a sliding window of
    MAX_DISPLAY_CASES at a time. Pricing + rendering 1000 columns at once
    freezes the browser; the slider lets the user browse the full set in chunks.
    """
    n = len(selected)
    if n <= MAX_DISPLAY_CASES:
        return selected

    st.markdown(
        f"<div style='background:#0a1628;border-left:3px solid #FFB347;"
        f"padding:6px 12px;margin:8px 0;border-radius:2px;'>"
        f"<span style='color:#FFB347;font-size:10px;letter-spacing:1px;font-weight:700;'>"
        f"⚠ DISPLAY WINDOW</span>"
        f"<span style='color:#888;font-size:10px;'> &nbsp; "
        f"{n:,} cases selected — rendering only {MAX_DISPLAY_CASES} at a time "
        f"to keep the UI responsive. Drag the slider to browse the rest."
        f"</span></div>",
        unsafe_allow_html=True,
    )

    max_start = max(1, n - MAX_DISPLAY_CASES + 1)
    start = st.slider(
        f"Show cases (window of {MAX_DISPLAY_CASES})",
        min_value=1, max_value=max_start,
        value=1, step=1,
        key="case_window_start",
        help=f"Index of first case to show. Window size = {MAX_DISPLAY_CASES}.",
    )
    end = min(n, start + MAX_DISPLAY_CASES - 1)
    st.markdown(
        f"<div style='color:#888;font-size:11px;margin:-6px 0 8px 0;'>"
        f"Showing <b style='color:#00B4D8;'>{start:,}–{end:,}</b> of "
        f"<b style='color:#00B4D8;'>{n:,}</b> selected cases."
        f"</div>",
        unsafe_allow_html=True,
    )
    return selected[start - 1:end]


# ── Generic table for structure dict {key: value per case} ────────────────────

def _struct_table(
    struct_per_case: Dict[str, dict],   # {case_id: {key: value}}
    selected: List[dict],
    gap_label: str,                     # e.g. "1M" or "2Q"
    struct_type: str,                   # e.g. "spread", "fly"
    product: str,                       # e.g. "SR1", "ZQ"
) -> str:
    from core.live_data import get_live_struct_price
    if not selected:
        return ""
    first_id  = selected[0]["id"]
    keys      = list(struct_per_case.get(first_id, {}).get(gap_label, {}).keys())
    if not keys:
        return f"<div style='color:#444;font-size:11px;padding:6px;'>No {gap_label} instruments</div>"
        
    col_labels = ["🔴 LIVE (bps)"] + [f"{c['id']} {c['name'][:10]}" for c in selected]
    data       = []
    for k in keys:
        live_val = get_live_struct_price(k, struct_type, product)
        # ×100: convert price-point difference to basis points
        row = [f"{live_val * 100:.2f}" if live_val is not None else "—"]
        for c in selected:
            raw = struct_per_case.get(c["id"], {}).get(gap_label, {}).get(k)
            row.append(round(raw * 100, 2) if raw is not None else None)
        data.append(row)
    return render_bloomberg_table(keys, col_labels, data, fmt="{:.2f}")


def _outright_table(contracts, selected, all_prices, product):
    from core.live_data import get_live_price
    col_labels = ["🔴 LIVE"] + [f"{c['id']} {c['name'][:10]}" for c in selected]
    row_labels = [c["code"] for c in contracts]
    data = []
    for contract in contracts:
        live_val = get_live_price(contract["code"], product)
        row = [f"{live_val:.4f}" if live_val is not None else "—"]
        for c in selected:
            row.append(all_prices.get(c["id"], {}).get(product, {}).get(contract["code"]))
        data.append(row)
    return render_bloomberg_table(row_labels, col_labels, data)


# ── Main render ───────────────────────────────────────────────────────────────

def render_structures_tab(cm, sr1c, zqc, sr3c):
    """Render Tab 2: full structures panel."""

    # ── Top Pane: Controls ────────────────────────────────────────────────────
    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2])
    with c1:
        render_base_rates()
        st.markdown("<br>", unsafe_allow_html=True)
        render_case_list(cm)
    with c2:
        render_case_builder(cm)
        st.markdown("<br>", unsafe_allow_html=True)
        render_bulk_generator(cm)
        st.markdown("<br>", unsafe_allow_html=True)
        render_formula_builder(cm)
        
    st.markdown("<hr style='border-color:#333;margin:20px 0;'>", unsafe_allow_html=True)

    selected_full = _case_selector(cm)
    if not selected_full:
        return

    # Cap on-screen cases (pricing + rendering 1000+ columns freezes the UI).
    # User browses the rest via the slider in _apply_display_window.
    selected = _apply_display_window(selected_full)

    with st.spinner(f"Computing prices for {len(selected)} cases..."):
        all_prices = _prices_for_cases(selected, sr1c, zqc, sr3c)

    # Store for Tab 3
    st.session_state["_shared_prices"]  = all_prices
    st.session_state["_shared_cases"]   = selected

    # Pre-compute structures for all selected cases
    sr1_spreads  = {c["id"]: compute_spreads(sr1c, all_prices[c["id"]]["SR1"], SR1_SPREAD_GAPS) for c in selected}
    zq_spreads   = {c["id"]: compute_spreads(zqc,  all_prices[c["id"]]["ZQ"],  ZQ_SPREAD_GAPS)  for c in selected}
    sr3_spreads  = {c["id"]: compute_spreads(sr3c, all_prices[c["id"]]["SR3"], SR3_SPREAD_GAPS) for c in selected}

    sr1_flies    = {c["id"]: compute_butterflies(sr1c, all_prices[c["id"]]["SR1"], SR1_FLY_GAPS) for c in selected}
    zq_flies     = {c["id"]: compute_butterflies(zqc,  all_prices[c["id"]]["ZQ"],  ZQ_FLY_GAPS)  for c in selected}
    sr3_flies    = {c["id"]: compute_butterflies(sr3c, all_prices[c["id"]]["SR3"], SR3_FLY_GAPS) for c in selected}

    sr1_condors  = {c["id"]: compute_condors(sr1c, all_prices[c["id"]]["SR1"], SR1_CONDOR_GAPS) for c in selected}
    zq_condors   = {c["id"]: compute_condors(zqc,  all_prices[c["id"]]["ZQ"],  ZQ_CONDOR_GAPS)  for c in selected}
    sr3_condors  = {c["id"]: compute_condors(sr3c, all_prices[c["id"]]["SR3"], SR3_CONDOR_GAPS) for c in selected}

    sr1_deflys   = {c["id"]: compute_deflys(sr1c, all_prices[c["id"]]["SR1"], SR1_DEFLY_GAPS) for c in selected}
    zq_deflys    = {c["id"]: compute_deflys(zqc,  all_prices[c["id"]]["ZQ"],  ZQ_DEFLY_GAPS)  for c in selected}
    sr3_deflys   = {c["id"]: compute_deflys(sr3c, all_prices[c["id"]]["SR3"], SR3_DEFLY_GAPS) for c in selected}

    # ── Section tabs (fragment auto-refreshes live prices every 3 s) ───────────
    _render_live_fragment(
        selected, all_prices, sr1c, zqc, sr3c,
        sr1_spreads, zq_spreads, sr3_spreads,
        sr1_flies, zq_flies, sr3_flies,
        sr1_condors, zq_condors, sr3_condors,
        sr1_deflys, zq_deflys, sr3_deflys,
        cm,
    )


def _render_live_curves(zqc, sr3c, selected_cases):
    """Render live ZQ meeting premium curve and SR3 3M spread curve.

    `selected_cases` is the windowed case list — overlaying 1000 traces per
    second on a live-refreshing chart kills the browser, so we restrict to
    whatever the display window currently contains.
    """
    import plotly.graph_objects as go
    from core.live_data import get_live_price
    from config.fomc_dates import ALL_FOMC_MEETINGS
    from core.date_utils import month_calendar_days

    col_zq, col_sr3 = st.columns(2)

    # ── ZQ Meeting Premium Curve ──────────────────────────────────────────
    # Uses VWAP from live ZQ calendar spread instruments (ZQ_CAL_*)
    # matching CME FedWatch convention: negative = easing expected
    with col_zq:
        # Compute total cuts/hikes from premiums for the title
        # (premiums are computed below, so we use a placeholder and update later)
        bb_subsection("ZQ LIVE MEETING PREMIUMS (bps)")
        from core.live_data import LIVE_PRICES

        # Month number → futures month code
        M2C = {1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',
               7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}

        def _next_ym(ym):
            return (ym[0], ym[1]+1) if ym[1] < 12 else (ym[0]+1, 1)

        # Build ZQ outright price lookup as fallback
        zq_prices = {}
        for c in zqc:
            price = get_live_price(c['code'], 'ZQ')
            if price is not None:
                zq_prices[(c['year'], c['month'])] = price

        per_mtg, labels, spd_detail, per_mtg_meetings = [], [], [], []

        for meeting in ALL_FOMC_MEETINGS:
            dec = meeting['decision_date']
            eff = meeting['effective_date']
            ym = (eff.year, eff.month)
            # CME spread pair:
            #  Late-month (day>20): front=M, back=M+1
            #  Early/mid (day<=20): front=M-1, back=M+1
            if eff.day > 20:
                front_ym = ym
                back_ym = _next_ym(ym)
            else:
                front_ym = (ym[0], ym[1]-1) if ym[1] > 1 else (ym[0]-1, 12)
                back_ym = _next_ym(ym)

            # Build ZQ_CAL key: e.g. ZQ_CAL_J26K26
            fc = M2C[front_ym[1]] + str(front_ym[0])[-2:]
            bc = M2C[back_ym[1]] + str(back_ym[0])[-2:]
            cal_key = f"ZQ_CAL_{fc}{bc}"

            # Try VWAP from calendar spread instrument first
            cal_entry = LIVE_PRICES.get(cal_key, {})
            vwap = cal_entry.get('VWAP')

            if vwap is not None:
                # Calendar spread VWAP is already in bps-equivalent scale
                premium = vwap
                src = f"VWAP={vwap:.6f}"
            else:
                # Fallback: compute from outright prices
                fp = zq_prices.get(front_ym)
                bp = zq_prices.get(back_ym)
                if fp is None or bp is None:
                    continue
                premium = (fp - bp) * 100
                src = f"outrights fp={fp:.4f} bp={bp:.4f}"

            per_mtg.append(premium)
            per_mtg_meetings.append(meeting)
            lbl = dec.strftime("%b '%y")
            if meeting.get('is_sep'):
                lbl += " *"
            labels.append(lbl)
            spd_detail.append(f"ZQ {fc}-{bc}: {premium:+.4f} bps  ({src})")

        if labels:
            # Compute total and per-year cuts for title display
            total_zq = sum(per_mtg)
            # Green = positive (hike), Red = negative (cut)
            color = "#00FF41" if total_zq > 0 else ("#FF3131" if total_zq < 0 else "#888")

            # Per-year breakdown: group premiums by meeting decision year
            yr_totals = {}
            for j, meeting in enumerate(per_mtg_meetings):
                yr = meeting['decision_date'].year
                yr_totals[yr] = yr_totals.get(yr, 0) + per_mtg[j]

            yr_chips = ""
            for yr in sorted(yr_totals.keys()):
                if yr < 2025:
                    continue
                yv = yr_totals[yr]
                yc = "#00FF41" if yv > 0 else ("#FF3131" if yv < 0 else "#888")
                yr_chips += (
                    f"<span style='color:#555;font-size:10px;margin-left:12px;'>│</span>"
                    f"<span style='color:#888;font-size:10px;margin-left:8px;'>{yr}: </span>"
                    f"<span style='color:{yc};font-size:11px;font-weight:600;'>{yv:+.1f} bps</span>"
                )

            st.markdown(
                f"<div style='text-align:right;margin-top:-18px;margin-bottom:4px;'>"
                f"<span style='color:#888;font-size:11px;letter-spacing:1px;'>TOTAL: </span>"
                f"<span style='color:{color};font-size:13px;font-weight:700;'>{total_zq:+.1f} bps</span>"
                f"{yr_chips}</div>",
                unsafe_allow_html=True,
            )
            fig = go.Figure()
            # Single bold live line — per-meeting premium
            fig.add_trace(go.Scatter(
                x=labels, y=per_mtg, name="LIVE",
                mode="lines+markers",
                line=dict(color="#00B4D8", width=3),
                marker=dict(size=6, color="#00B4D8"),
            ))
            # Case overlays (dotted) — only windowed cases (this fragment runs
            # every 1s, so iterating 1000 cases here would freeze the browser).
            colors = ["#4f8dff", "#00d4aa", "#f2cd32", "#ff4f8d", "#a78bfa"]
            for i, case in enumerate(selected_cases):
                case_per_mtg = []
                for m_info in ALL_FOMC_MEETINGS[:len(labels)]:
                    bps = case['meeting_cuts'].get(m_info['effective_date'], 0.0)
                    case_per_mtg.append(round(bps, 2))
                if len(case_per_mtg) == len(labels):
                    fig.add_trace(go.Scatter(
                        x=labels, y=case_per_mtg, name=case['name'][:12],
                        mode="lines", line=dict(color=colors[i%len(colors)], width=1.5, dash="dot"),
                    ))
            all_y = per_mtg
            y_min = min(all_y) if all_y else -5
            y_max = max(all_y) if all_y else 5
            y_pad = max(abs(y_max - y_min) * 0.15, 1)
            fig.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", height=380,
                margin=dict(l=50, r=10, t=10, b=55),
                xaxis=dict(showgrid=True, gridcolor="#222", tickangle=-45, tickfont=dict(size=9)),
                yaxis=dict(showgrid=True, gridcolor="#222", title="bps per meeting", title_font=dict(size=9),
                           range=[y_min - y_pad, y_max + y_pad], tickformat=".3f",
                           zeroline=True, zerolinecolor="#444", zerolinewidth=1, hoverformat=".3f"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=9)),
            )
            fig.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            # Detail expander — verify individual spread values
            with st.expander("📋 ZQ Spread Details", expanded=False):
                for d in spd_detail:
                    st.text(d)
        else:
            st.markdown("<span style='color:#555;font-size:10px;'>Waiting for ZQ data...</span>",
                        unsafe_allow_html=True)

    # ── SR3 3M Calendar Spread Curve ──────────────────────────────────────
    # Convention: (front - back) in bps = rate change, negative = easing
    with col_sr3:
        bb_subsection("SR3 LIVE 3M SPREAD CURVE (1Q)")
        sr3_px = {}
        for c in sr3c:
            price = get_live_price(c['code'], 'SR3')
            if price is not None:
                sr3_px[c['code']] = price
        spd_labels, spd_values, spd_back_codes = [], [], []
        for i in range(len(sr3c) - 1):
            front, back = sr3c[i], sr3c[i+1]
            pf, pb = sr3_px.get(front['code']), sr3_px.get(back['code'])
            if pf is not None and pb is not None:
                # front - back: negative in easing (back price > front price)
                spd = round((pf - pb) * 100, 2)
                spd_labels.append(f"{front['code'][3:]}-{back['code'][3:]}")
                spd_values.append(spd)
                spd_back_codes.append(back['code'])
        if spd_labels:
            # Compute total and per-year for title display
            total_sr3 = sum(spd_values)
            # Green = positive (hike), Red = negative (cut)
            color_sr3 = "#00FF41" if total_sr3 > 0 else ("#FF3131" if total_sr3 < 0 else "#888")

            # Per-year breakdown: assign each spread to the back contract's year
            sr3_yr_totals = {}
            for j in range(len(spd_values)):
                back_code = spd_back_codes[j]
                try:
                    yr = 2000 + int(back_code[-2:])
                except (ValueError, IndexError):
                    continue
                sr3_yr_totals[yr] = sr3_yr_totals.get(yr, 0) + spd_values[j]

            yr_chips_sr3 = ""
            for yr in sorted(sr3_yr_totals.keys()):
                yv = sr3_yr_totals[yr]
                yc = "#00FF41" if yv > 0 else ("#FF3131" if yv < 0 else "#888")
                yr_chips_sr3 += (
                    f"<span style='color:#555;font-size:10px;margin-left:12px;'>│</span>"
                    f"<span style='color:#888;font-size:10px;margin-left:8px;'>{yr}: </span>"
                    f"<span style='color:{yc};font-size:11px;font-weight:600;'>{yv:+.1f} bps</span>"
                )

            st.markdown(
                f"<div style='text-align:right;margin-top:-18px;margin-bottom:4px;'>"
                f"<span style='color:#888;font-size:11px;letter-spacing:1px;'>TOTAL: </span>"
                f"<span style='color:{color_sr3};font-size:13px;font-weight:700;'>{total_sr3:+.1f} bps</span>"
                f"{yr_chips_sr3}</div>",
                unsafe_allow_html=True,
            )
            fig2 = go.Figure()
            bar_colors = ["#00FF41" if v >= 0 else "#FF3131" for v in spd_values]
            fig2.add_trace(go.Bar(
                x=spd_labels, y=spd_values, name="Spread (bps)",
                marker_color=bar_colors, marker_line_color="#1a3050", marker_line_width=0.5,
                text=[f"{v:+.1f}" for v in spd_values], textposition="outside",
                textfont=dict(color="#C0C0C0", size=8),
            ))
            fig2.add_trace(go.Scatter(
                x=spd_labels, y=spd_values, mode="lines+markers",
                line=dict(color="#00B4D8", width=2), marker=dict(size=4, color="#00B4D8"),
                showlegend=False,
            ))
            # Case overlays — windowed cases only (this fragment refreshes
            # every second, so all-cases iteration would freeze the browser).
            colors = ["#4f8dff", "#00d4aa", "#f2cd32", "#ff4f8d", "#a78bfa"]
            from core.pricing_engine import price_sr3
            for ci, case in enumerate(selected_cases):
                cs, cl = [], []
                for i in range(len(sr3c) - 1):
                    f_, b_ = sr3c[i], sr3c[i+1]
                    p = case.get('rate_path', {}).get('sofr', {})
                    pf_c = price_sr3(f_['ref_start'], f_['ref_end'], p, case['base_sofr'])
                    pb_c = price_sr3(b_['ref_start'], b_['ref_end'], p, case['base_sofr'])
                    cs.append(round((pf_c - pb_c) * 100, 2))
                    cl.append(f"{f_['code'][3:]}-{b_['code'][3:]}")
                fig2.add_trace(go.Scatter(
                    x=cl, y=cs, name=case['name'][:12],
                    mode="lines", line=dict(color=colors[ci%len(colors)], width=1.5, dash="dot"),
                ))
            s_min, s_max = min(spd_values), max(spd_values)
            s_pad = max(abs(s_max - s_min) * 0.2, 2)
            fig2.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", height=380,
                margin=dict(l=50, r=10, t=10, b=55),
                xaxis=dict(showgrid=True, gridcolor="#222", tickfont=dict(size=7), tickangle=-45),
                yaxis=dict(showgrid=True, gridcolor="#222", title="bps",
                           title_font=dict(size=9), tickformat=".1f",
                           range=[s_min - s_pad, s_max + s_pad],
                           zeroline=True, zerolinecolor="#444"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=9)),
            )
            fig2.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.markdown("<span style='color:#555;font-size:10px;'>No SR3 prices yet</span>",
                        unsafe_allow_html=True)


@st.fragment(run_every=timedelta(seconds=1))
def _render_live_fragment(
    selected, all_prices, sr1c, zqc, sr3c,
    sr1_spreads, zq_spreads, sr3_spreads,
    sr1_flies, zq_flies, sr3_flies,
    sr1_condors, zq_condors, sr3_condors,
    sr1_deflys, zq_deflys, sr3_deflys,
    cm,
):
    """Auto-refreshing fragment — re-runs every 3 s to pick up new LIVE_PRICES."""
    from core.live_data import LS_STATUS, is_connected
    # ── Live status badge ─────────────────────────────────────────────────────
    if is_connected():
        last = LS_STATUS.get('last_update')
        import time
        age = f"{time.time() - last:.0f}s ago" if last else "?"
        st.markdown(
            f"<span style='color:#00FF41;font-size:11px;'>● LIVE  "
            f"({LS_STATUS.get('items',0)} instruments · last tick {age})</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='color:#FF3131;font-size:11px;'>● CONNECTING…</span>",
            unsafe_allow_html=True,
        )

    # ── Live Forward Curves ──────────────────────────────────────────────────
    _render_live_curves(zqc, sr3c, selected)

    sec1, sec2, sec3, sec4, sec5, sec6, sec7, sec8 = st.tabs([
        "📌 OUTRIGHTS", "↔ SPREADS", "🦋 BUTTERFLIES", "🔷 CONDORS", "🌀 DEFLYS",
        "📊 MEETING RANGE", "🔬 STRUCTURES LIVE", "🎯 RANGE TRADES"
    ])

    # ─── OUTRIGHTS ────────────────────────────────────────────────────────────
    with sec1:
        bb_section("OUTRIGHTS")
        t1, t2, t3 = st.tabs(["SR1 — 1M SOFR", "ZQ — 30D EFFR", "SR3 — 3M SOFR"])
        with t1:
            bb_subsection(f"SR1 Outrights ({len(sr1c)} contracts)")
            st.markdown(_outright_table(sr1c, selected, all_prices, "SR1"), unsafe_allow_html=True)
        with t2:
            bb_subsection(f"ZQ Outrights ({len(zqc)} contracts)")
            st.markdown(_outright_table(zqc, selected, all_prices, "ZQ"), unsafe_allow_html=True)
        with t3:
            bb_subsection(f"SR3 Outrights ({len(sr3c)} contracts)")
            st.markdown(_outright_table(sr3c, selected, all_prices, "SR3"), unsafe_allow_html=True)

    # ─── SPREADS ──────────────────────────────────────────────────────────────
    with sec2:
        bb_section("SPREADS  [back − front]")
        t1, t2, t3 = st.tabs(["SR1 SPREADS", "ZQ SPREADS", "SR3 SPREADS"])
        with t1:
            for g in SR1_SPREAD_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"SR1 {lbl} Spread")
                st.markdown(_struct_table(sr1_spreads, selected, lbl, "spread", "SR1"), unsafe_allow_html=True)
        with t2:
            for g in ZQ_SPREAD_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"ZQ {lbl} Spread")
                st.markdown(_struct_table(zq_spreads, selected, lbl, "spread", "ZQ"), unsafe_allow_html=True)
        with t3:
            labels = ["1Q (3M)", "2Q (6M)", "3Q (9M)", "4Q (1Y)"]
            for i, g in enumerate(SR3_SPREAD_GAPS):
                lbl = f"{g}Q"
                bb_subsection(f"SR3 {labels[i]} Spread")
                st.markdown(_struct_table(sr3_spreads, selected, lbl, "spread", "SR3"), unsafe_allow_html=True)

    # ─── BUTTERFLIES ──────────────────────────────────────────────────────────
    with sec3:
        bb_section("BUTTERFLIES  [+1 / −2 / +1]")
        t1, t2, t3 = st.tabs(["SR1 FLIES", "ZQ FLIES", "SR3 FLIES"])
        with t1:
            for g in SR1_FLY_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"SR1 {lbl} Fly")
                st.markdown(_struct_table(sr1_flies, selected, lbl, "fly", "SR1"), unsafe_allow_html=True)
        with t2:
            for g in ZQ_FLY_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"ZQ {lbl} Fly")
                st.markdown(_struct_table(zq_flies, selected, lbl, "fly", "ZQ"), unsafe_allow_html=True)
        with t3:
            for g in SR3_FLY_GAPS:
                lbl = f"{g}Q"
                bb_subsection(f"SR3 {lbl} Fly")
                st.markdown(_struct_table(sr3_flies, selected, lbl, "fly", "SR3"), unsafe_allow_html=True)

    # ─── CONDORS ──────────────────────────────────────────────────────────────
    with sec4:
        bb_section("CONDORS  [+1 / −1 / −1 / +1]")
        t1, t2, t3 = st.tabs(["SR1 CONDORS", "ZQ CONDORS", "SR3 CONDORS"])
        with t1:
            for g in SR1_CONDOR_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"SR1 {lbl} Condor")
                st.markdown(_struct_table(sr1_condors, selected, lbl, "condor", "SR1"), unsafe_allow_html=True)
        with t2:
            for g in ZQ_CONDOR_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"ZQ {lbl} Condor")
                st.markdown(_struct_table(zq_condors, selected, lbl, "condor", "ZQ"), unsafe_allow_html=True)
        with t3:
            for g in SR3_CONDOR_GAPS:
                lbl = f"{g}Q"
                bb_subsection(f"SR3 {lbl} Condor")
                st.markdown(_struct_table(sr3_condors, selected, lbl, "condor", "SR3"), unsafe_allow_html=True)

    # ─── DEFLYS ───────────────────────────────────────────────────────────────
    with sec5:
        bb_section("DEFLYS  [+1 / −3 / +3 / −1]")
        t1, t2, t3 = st.tabs(["SR1 DEFLYS", "ZQ DEFLYS", "SR3 DEFLYS"])
        with t1:
            for g in SR1_DEFLY_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"SR1 {lbl} Defly")
                st.markdown(_struct_table(sr1_deflys, selected, lbl, "defly", "SR1"), unsafe_allow_html=True)
        with t2:
            for g in ZQ_DEFLY_GAPS:
                lbl = f"{g}M"
                bb_subsection(f"ZQ {lbl} Defly")
                st.markdown(_struct_table(zq_deflys, selected, lbl, "defly", "ZQ"), unsafe_allow_html=True)
        with t3:
            for g in SR3_DEFLY_GAPS:
                lbl = f"{g}Q"
                bb_subsection(f"SR3 {lbl} Defly")
                st.markdown(_struct_table(sr3_deflys, selected, lbl, "defly", "SR3"), unsafe_allow_html=True)

    # ─── MEETING RANGE ────────────────────────────────────────────────────────
    with sec6:
        bb_section("MEETING RANGE ANALYSIS")
        # Pass `selected` (windowed) so per-case columns don't blow up with 1000 cases.
        # Aggregate stats (min/max/mean/mode) still come from the full cm.cases.
        _render_meeting_range(cm, selected)

    # ─── STRUCTURES LIVE ──────────────────────────────────────────────────────
    with sec7:
        bb_section("STRUCTURES LIVE")
        _render_structures_live(selected, zqc, sr3c)

    # ─── RANGE TRADES ─────────────────────────────────────────────────────────
    with sec8:
        bb_section("RANGE TRADE FINDER")
        _render_range_trades(cm, sr1c, zqc, sr3c)



def _render_meeting_range(cm, selected):
    """
    Aggregate stats (min/max/mean/mode) computed across the FULL cm.cases set
    so the chart still shows the true distribution. The per-case-column table
    is restricted to `selected` (windowed) to avoid rendering 1000 columns.
    """
    analysis = cm.meeting_range_analysis()
    if not analysis:
        st.info("No cases to analyze.")
        return

    n_total = len(cm.cases)
    n_shown = len(selected)
    if n_total > n_shown:
        bb_subsection(
            f"ALL MEETINGS — CUT/HIKE RANGE  (stats across {n_total} cases · "
            f"showing {n_shown} columns from window)"
        )
    else:
        bb_subsection("ALL MEETINGS — CUT/HIKE RANGE ACROSS CASES")

    # Restrict per-case columns to the windowed selection.
    selected_ids   = [c["id"] for c in selected]
    case_id_index  = {c["id"]: i for i, c in enumerate(cm.cases)}  # map id → column index in row["values"]
    col_labels     = [c["name"][:15] for c in selected]
    row_labels, data = [], []
    for row in analysis:
        lbl = row["decision_date"].strftime("%Y %b %d")
        if row["is_sep"]:
            lbl += " ⭐"
        row_labels.append(lbl)
        # row["values"] is in cm.cases order — pick out the selected ones
        data.append([
            row["values"][case_id_index[cid]]
            if cid in case_id_index and case_id_index[cid] < len(row["values"])
            else 0.0
            for cid in selected_ids
        ])

    st.markdown(render_bloomberg_table(row_labels, col_labels, data), unsafe_allow_html=True)

    # Chart
    import plotly.graph_objects as go
    bb_subsection("MEETING RANGE CHART")

    x_dates = [r["decision_date"].strftime("%Y-%b-%d") for r in analysis]
    y_min = [r["min_cut"] for r in analysis]
    y_max = [r["max_cut"] for r in analysis]
    y_mean = [r["mean_cut"] for r in analysis]
    y_mode = [r["mode_cut"] for r in analysis]

    fig = go.Figure()
    # Range band
    fig.add_trace(go.Scatter(
        x=x_dates + x_dates[::-1],
        y=y_max + y_min[::-1],
        fill="toself",
        fillcolor="rgba(245, 158, 11, 0.1)",
        line=dict(color="rgba(255,255,255,0)"),
        name="Range Band"
    ))
    fig.add_trace(go.Scatter(x=x_dates, y=y_max, mode="lines+markers", name="Max bps", line=dict(color="#f59e0b", dash="dot")))
    fig.add_trace(go.Scatter(x=x_dates, y=y_min, mode="lines+markers", name="Min bps", line=dict(color="#ef4444", dash="dot")))
    fig.add_trace(go.Scatter(x=x_dates, y=y_mean, mode="lines+markers", name="Mean bps", line=dict(color="#f2cd32")))
    fig.add_trace(go.Scatter(x=x_dates, y=y_mode, mode="markers", name="Mode bps", marker=dict(color="#00FF41", symbol="diamond", size=8)))

    # ── Live meeting premium overlay ──────────────────────────────────────
    from core.live_data import LIVE_PRICES, get_live_price
    M2C = {1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',
           7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}
    def _next_ym(ym):
        return (ym[0], ym[1]+1) if ym[1] < 12 else (ym[0]+1, 1)

    # Build ZQ outright fallback
    from config.constants import SR1_ZQ_HORIZON_MONTHS
    from core.date_utils import generate_zq_contracts
    zqc_local = generate_zq_contracts(SR1_ZQ_HORIZON_MONTHS)
    zq_px = {}
    for c in zqc_local:
        p = get_live_price(c['code'], 'ZQ')
        if p is not None:
            zq_px[(c['year'], c['month'])] = p

    live_x, live_y = [], []
    for i, row in enumerate(analysis):
        dec = row['decision_date']
        from config.fomc_dates import ALL_FOMC_MEETINGS
        mtg = next((m for m in ALL_FOMC_MEETINGS if m['decision_date'] == dec), None)
        if mtg is None:
            continue
        eff = mtg['effective_date']
        ym = (eff.year, eff.month)
        if eff.day > 20:
            front_ym = ym; back_ym = _next_ym(ym)
        else:
            front_ym = (ym[0], ym[1]-1) if ym[1] > 1 else (ym[0]-1, 12)
            back_ym = _next_ym(ym)
        fc = M2C[front_ym[1]] + str(front_ym[0])[-2:]
        bc = M2C[back_ym[1]] + str(back_ym[0])[-2:]
        cal_key = f"ZQ_CAL_{fc}{bc}"
        cal_entry = LIVE_PRICES.get(cal_key, {})
        vwap = cal_entry.get('VWAP')
        if vwap is not None:
            live_x.append(x_dates[i]); live_y.append(vwap)
        else:
            fp = zq_px.get(front_ym); bp = zq_px.get(back_ym)
            if fp is not None and bp is not None:
                live_x.append(x_dates[i]); live_y.append((fp - bp) * 100)

    if live_x:
        fig.add_trace(go.Scatter(
            x=live_x, y=live_y, name="LIVE Premium",
            mode="lines+markers", line=dict(color="#00B4D8", width=3),
            marker=dict(size=7, color="#00B4D8", symbol="circle"),
        ))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=350, margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(tickangle=-45, showgrid=True, gridcolor="#333"),
        yaxis=dict(title="Cut (-) / Hike (+) bps", showgrid=True, gridcolor="#333"),
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99, bgcolor="rgba(0,0,0,0.5)")
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Meeting detail dropdown
    bb_subsection("MEETING DETAIL — DISTRIBUTION")
    sel_meeting = st.selectbox("Select Meeting", row_labels, key="meeting_dist_select")
    if sel_meeting:
        idx = row_labels.index(sel_meeting)
        row = analysis[idx]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("MIN", f"{row['min_cut']:+.2f} bps")
        c2.metric("MAX", f"{row['max_cut']:+.2f} bps")
        c3.metric("MEAN", f"{row['mean_cut']:+.2f} bps")
        c4.metric("RANGE", f"{row['range']:.2f} bps")


def _render_structures_live(selected, zqc, sr3c):
    """Render live ZQ fly and SR3 spread values vs case projections.

    `selected` is the windowed case list (capped at MAX_DISPLAY_CASES) so this
    sub-tab no longer iterates 1000 cases for every row of every table.
    """
    import plotly.graph_objects as go
    from core.live_data import LIVE_PRICES, get_live_price

    # Build lookup: bare code → suffixed code (e.g. "ZQN26" → "ZQN26 (Jul)")
    code_map = {}
    for c in zqc + sr3c:
        bare = c['code'].split(' (')[0] if ' (' in c['code'] else c['code']
        code_map[bare] = c['code']

    ZQ_FLIES = [
        ("ZQ Jul26 Aug26 Oct26 Fly", ["ZQN26","ZQQ26","ZQV26"]),
        ("ZQ Aug26 Oct26 Nov26 Fly", ["ZQQ26","ZQV26","ZQX26"]),
        ("ZQ Oct26 Nov26 Jan27 Fly", ["ZQV26","ZQX26","ZQF27"]),
        ("ZQ Nov26 Jan27 Feb27 Fly", ["ZQX26","ZQF27","ZQG27"]),
        ("ZQ Jan27 Feb27 Apr27 Fly", ["ZQF27","ZQG27","ZQJ27"]),
        ("ZQ Feb27 Apr27 May27 Fly", ["ZQG27","ZQJ27","ZQK27"]),
        ("ZQ Apr27 May27 Jul27 Fly", ["ZQJ27","ZQK27","ZQN27"]),
    ]

    SR3_SPDS = [
        ("SR3 Mar26-Jun26", ["SR3H26","SR3M26"]),
        ("SR3 Jun26-Sep26", ["SR3M26","SR3U26"]),
        ("SR3 Sep26-Dec26", ["SR3U26","SR3Z26"]),
        ("SR3 Dec26-Mar27", ["SR3Z26","SR3H27"]),
        ("SR3 Mar27-Jun27", ["SR3H27","SR3M27"]),
        ("SR3 Jun27-Sep27", ["SR3M27","SR3U27"]),
        ("SR3 Sep27-Dec27", ["SR3U27","SR3Z27"]),
        ("SR3 Dec27-Mar28", ["SR3Z27","SR3H28"]),
        ("SR3 Mar28-Jun28", ["SR3H28","SR3M28"]),
        ("SR3 Jun28-Sep28", ["SR3M28","SR3U28"]),
        ("SR3 Sep28-Dec28", ["SR3U28","SR3Z28"]),
        ("SR3 Dec28-Mar29", ["SR3Z28","SR3H29"]),
        ("SR3 Mar29-Jun29", ["SR3H29","SR3M29"]),
        ("SR3 Jun29-Sep29", ["SR3M29","SR3U29"]),
        ("SR3 Sep29-Dec29", ["SR3U29","SR3Z29"]),
    ]

    def _get_price(bare):
        """Get outright mid using the suffixed code that Lightstreamer uses."""
        suffixed = code_map.get(bare, bare)
        return get_live_price(suffixed)

    def _live_fly(legs):
        p = [_get_price(l) for l in legs]
        if all(x is not None for x in p):
            return (p[0] - 2*p[1] + p[2]) * 100
        return None

    def _live_spread(legs):
        p = [_get_price(l) for l in legs]
        if all(x is not None for x in p):
            return (p[0] - p[1]) * 100
        return None

    def _cv(v):
        if v is None: return "<span style='color:#555;'>—</span>"
        c = "#00FF41" if v > 0.01 else "#FF3131" if v < -0.01 else "#C0C0C0"
        return f"<span style='color:{c};font-weight:bold;'>{v:+.3f}</span>"

    # ── Month code → (month_num, year) parser ────────────────────────────
    C2M = {'F':1,'G':2,'H':3,'J':4,'K':5,'M':6,
           'N':7,'Q':8,'U':9,'V':10,'X':11,'Z':12}

    def _parse_ym(bare_code):
        """Parse 'ZQN26' → (2026, 7) or 'SR3M26' → (2026, 6)."""
        # Strip product prefix: ZQ or SR3
        if bare_code.startswith("SR3"):
            suffix = bare_code[3:]  # e.g. "M26"
        else:
            suffix = bare_code[2:]  # e.g. "N26"
        mc = suffix[0]       # month code letter
        yr = int(suffix[1:])  # 2-digit year
        return (2000 + yr, C2M[mc])

    # ── Case pricing for ZQ outrights ─────────────────────────────────────
    from core.pricing_engine import price_zq, price_sr3

    def _case_zq_fly(case, legs):
        """Compute ZQ fly value for a case using price_zq."""
        path = case.get('rate_path', {}).get('effr', {})
        base = case.get('base_effr', 3.64)
        prices = []
        for l in legs:
            yr, mo = _parse_ym(l)
            p = price_zq(yr, mo, path, base)
            prices.append(p)
        return (prices[0] - 2*prices[1] + prices[2]) * 100  # bps

    def _case_sr3_spread(case, legs):
        """Compute SR3 spread value for a case using price_sr3."""
        path = case.get('rate_path', {}).get('sofr', {})
        base = case.get('base_sofr', 3.64)
        # Build SR3 contract lookup
        sr3_map = {}
        for c in sr3c:
            bare = c['code'].split(' (')[0] if ' (' in c['code'] else c['code']
            sr3_map[bare] = c
        prices = []
        for l in legs:
            cinfo = sr3_map.get(l)
            if cinfo is None:
                return None
            p = price_sr3(cinfo['ref_start'], cinfo['ref_end'], path, base)
            prices.append(p)
        return (prices[0] - prices[1]) * 100  # bps

    case_names = [c['name'][:15] for c in selected]

    col1, col2 = st.columns(2)

    # ── ZQ Flies ──────────────────────────────────────────────────────────
    with col1:
        bb_section("ZQ MEETING BUTTERFLIES")
        # Use render_bloomberg_table → wraps in bb-table-wrap (scroll) and gives
        # each column min-width:80px so case columns can't overlap each other.
        zq_row_labels = []
        zq_data       = []
        fly_names, fly_vals = [], []
        for name, legs in ZQ_FLIES:
            val = _live_fly(legs)
            fly_names.append(name.replace("ZQ ", "").replace(" Fly", ""))
            fly_vals.append(val if val is not None else 0)
            zq_row_labels.append(name)
            zq_data.append([val] + [_case_zq_fly(c, legs) for c in selected])

        st.markdown(
            render_bloomberg_table(
                zq_row_labels,
                ["LIVE"] + case_names,
                zq_data,
                fmt="{:+.3f}",
            ),
            unsafe_allow_html=True,
        )

        # Bar chart
        bb_subsection("ZQ FLY VALUES")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=fly_names, y=fly_vals,
            marker_color=["#00FF41" if v>=0 else "#FF3131" for v in fly_vals],
            text=[f"{v:+.2f}" for v in fly_vals], textposition="outside",
            textfont=dict(size=9, color="#C0C0C0")))
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=280, showlegend=False,
            margin=dict(l=40,r=10,t=10,b=60), xaxis=dict(tickangle=-30, tickfont=dict(size=8)),
            yaxis=dict(title="bps", tickformat=".2f", zeroline=True, zerolinecolor="#444"))
        fig.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── SR3 Spreads ───────────────────────────────────────────────────────
    with col2:
        bb_section("SR3 CALENDAR SPREADS (1Q)")
        sr3_row_labels = []
        sr3_data       = []
        spd_names, spd_vals = [], []
        for name, legs in SR3_SPDS:
            val = _live_spread(legs)
            spd_names.append(name.replace("SR3 ", ""))
            spd_vals.append(val if val is not None else 0)
            sr3_row_labels.append(name)
            sr3_data.append([val] + [_case_sr3_spread(c, legs) for c in selected])

        st.markdown(
            render_bloomberg_table(
                sr3_row_labels,
                ["LIVE"] + case_names,
                sr3_data,
                fmt="{:+.3f}",
            ),
            unsafe_allow_html=True,
        )

        bb_subsection("SR3 SPREAD VALUES")
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=spd_names, y=spd_vals,
            marker_color=["#00FF41" if v>=0 else "#FF3131" for v in spd_vals],
            text=[f"{v:+.2f}" for v in spd_vals], textposition="outside",
            textfont=dict(size=8, color="#C0C0C0")))
        fig2.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=280, showlegend=False,
            margin=dict(l=40,r=10,t=10,b=60), xaxis=dict(tickangle=-30, tickfont=dict(size=7)),
            yaxis=dict(title="bps", tickformat=".2f", zeroline=True, zerolinecolor="#444"))
        fig2.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    # ── Diagnostic ────────────────────────────────────────────────────────
    with st.expander("🔧 PRICE DEBUG", expanded=False):
        for name, legs in ZQ_FLIES[:3]:
            vals = {l: _get_price(l) for l in legs}
            st.text(f"{name}: {vals}")
        for name, legs in SR3_SPDS[:3]:
            vals = {l: _get_price(l) for l in legs}
            st.text(f"{name}: {vals}")


# ── Range Trade Finder ────────────────────────────────────────────────────────

def _render_range_trades(cm, sr1c, zqc, sr3c):
    """
    Range-Bound Trade Finder.

    Idea: each "case" is a different Fed path. For every instrument we know
    its dollar value (= price × contract multiplier) under every case. A
    combo of two legs in some integer-ratio (a, b) is "range-bound" when
        range_across_cases( a · V_primary  +  b · V_hedge )
    is small in dollar terms — meaning whatever case actually plays out, the
    combo's value barely moves. Capture the trade vs. live entry, hold to
    expiry, PnL is bounded by the residual range.

    Three sections:
      1. STRUCTURE RANGE TABLE — every instrument's $ range, with filters.
      2. HEDGE FINDER — pick a primary leg, see the best 1-leg hedges
         ranked by absolute residual $ range. Trivially-flat primaries
         hidden by a min-range gate.
      3. TRADE INSPECTOR — for the chosen trade (or one you override the
         ratio of), shows per-case combo $ value distribution + worst/best
         PnL if you enter at the mean.
    """
    import numpy as np
    import plotly.graph_objects as go
    from core.range_finder import (
        build_instrument_matrix, per_instrument_stats, find_best_hedges,
        MULTIPLIER,
    )

    n_total = len(cm.cases)
    if n_total == 0:
        st.info("No cases yet. Build cases first to find range-bound trades.")
        return
    if n_total < 2:
        st.warning("Need at least 2 cases to find range-bound trades.")
        return

    st.markdown(
        "<small style='color:#888'>"
        "Find leg combinations whose <b>$ value barely moves across all your "
        "cases</b>. Values are in dollars (price × CME multiplier: SR1/ZQ "
        "$4,167 per pt, SR3 $2,500 per pt). Range = max − min across cases. "
        "Lower residual range ⇒ tighter, more range-bound trade."
        "</small>",
        unsafe_allow_html=True,
    )

    # ── Cache state + Compute button ─────────────────────────────────────
    cached_n    = st.session_state.get("_range_n",    0)
    cached_keys = st.session_state.get("_range_keys", None)
    cached_mat  = st.session_state.get("_range_mat",  None)

    state_cols = st.columns([3, 1])
    with state_cols[0]:
        if cached_mat is None:
            status = (
                f"<div style='color:#FFB347;font-size:11px;'>⚠ No analysis yet — "
                f"click → to compute across all {n_total:,} cases.</div>"
            )
        elif cached_n != n_total:
            status = (
                f"<div style='color:#FFB347;font-size:11px;'>⚠ Stale: ran with "
                f"{cached_n:,} cases, you now have {n_total:,}. Click → to refresh.</div>"
            )
        else:
            status = (
                f"<div style='color:#00FF41;font-size:11px;'>✓ Fresh — "
                f"{n_total:,} cases × {cached_mat.shape[1]:,} instruments "
                f"(values in bps).</div>"
            )
        st.markdown(status, unsafe_allow_html=True)
    with state_cols[1]:
        compute = st.button(
            f"🔄 Compute  ({n_total:,} cases)",
            key="range_compute_btn", type="primary",
            use_container_width=True,
        )

    if compute:
        prog_text = st.empty()
        prog_bar  = st.progress(0)
        def _on_progress(done: int, total: int):
            if done == total or done % max(1, total // 50) == 0:
                prog_text.markdown(
                    f"<small style='color:#FFB347;'>Pricing case "
                    f"{done:,} / {total:,}…</small>",
                    unsafe_allow_html=True,
                )
                prog_bar.progress(done / total)

        keys, matrix = build_instrument_matrix(
            cm.cases, sr1c, zqc, sr3c, progress=_on_progress,
        )
        prog_text.empty()
        prog_bar.empty()
        st.session_state["_range_keys"] = keys
        st.session_state["_range_mat"]  = matrix
        st.session_state["_range_n"]    = n_total
        st.rerun()

    if cached_mat is None:
        return

    keys   = cached_keys
    matrix = cached_mat
    stats  = per_instrument_stats(matrix)

    # Parse "PRODUCT·TYPE·GAP·NAME" once for filtering / grouping
    parsed = [k.split("·") for k in keys]
    products_all = sorted({p[0] for p in parsed})
    types_all    = sorted({p[1] for p in parsed})

    # Precompute bps arrays (stored as $ = price_pt × mult; bps = $/mult × 100)
    bps_rng  = np.array([stats["range"][i] / MULTIPLIER.get(parsed[i][0], 1.0) * 100 for i in range(len(keys))])
    bps_min  = np.array([stats["min"][i]   / MULTIPLIER.get(parsed[i][0], 1.0) * 100 for i in range(len(keys))])
    bps_max  = np.array([stats["max"][i]   / MULTIPLIER.get(parsed[i][0], 1.0) * 100 for i in range(len(keys))])
    bps_mean = np.array([stats["mean"][i]  / MULTIPLIER.get(parsed[i][0], 1.0) * 100 for i in range(len(keys))])
    bps_std  = np.array([stats["std"][i]   / MULTIPLIER.get(parsed[i][0], 1.0) * 100 for i in range(len(keys))])

    # ════════════════════════════════════════════════════════════════════
    # SECTION 1 — Structure Range Table  (grouped by product & type, bps)
    # ════════════════════════════════════════════════════════════════════
    bb_subsection("① STRUCTURE RANGE TABLE  —  bps range of every instrument across all cases")

    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        sel_products = st.multiselect(
            "Products", products_all, default=products_all, key="range_filter_prod",
        )
    with f2:
        sel_types = st.multiselect(
            "Types  (OUT=Outright · SPR=Spread · FLY=Fly · CON=Condor · DEF=Defly)",
            types_all, default=types_all, key="range_filter_type",
        )
    with f3:
        sort_dir = st.radio(
            "Sort by Range",
            ["High → Low (most volatile first)", "Low → High (tightest first)"],
            key="range_sort_dir", horizontal=False,
        )

    f4, f5 = st.columns([2, 2])
    with f4:
        min_range_bps = st.number_input(
            "Hide rows with range below (bps)", min_value=0.0, value=0.0, step=0.5,
            key="range_filter_min",
            help="Filter out instruments that barely move across your cases.",
        )
    with f5:
        n_show = st.slider(
            "Show top N rows per group", 5, min(200, len(keys)) if keys else 5,
            min(30, len(keys)) if keys else 5,
            key="range_tight_topn",
        )

    _TYPE_LABELS = {"OUT": "OUTRIGHTS", "SPR": "SPREADS", "FLY": "BUTTERFLIES",
                    "CON": "CONDORS", "DEF": "DEFLYS"}
    _TYPE_ORDER  = ["OUT", "SPR", "FLY", "CON", "DEF"]

    def _bps_table(row_lbs, col_lbs, rows) -> str:
        """Bloomberg-styled table that renders pre-formatted string cells."""
        h = '<div class="bb-table-wrap"><table class="bb-table"><thead><tr>'
        h += '<th>CONTRACT</th>'
        for c in col_lbs:
            h += f'<th>{c}</th>'
        h += '</tr></thead><tbody>'
        for rl, row in zip(row_lbs, rows):
            h += f'<tr><td class="bb-row-label">{rl}</td>'
            for val in row:
                if val is None:
                    h += '<td class="zero-val">—</td>'
                else:
                    try:
                        fval = float(str(val).replace(",", ""))
                        cls  = ("pos-val" if fval > 0.0001 else
                                "neg-val" if fval < -0.0001 else "zero-val")
                        h += f'<td class="{cls}">{val}</td>'
                    except (TypeError, ValueError):
                        h += f'<td class="zero-val">{val}</td>'
            h += '</tr>'
        h += '</tbody></table></div>'
        return h

    grand_total = 0
    for _prod in sorted(sel_products):
        _mult = MULTIPLIER.get(_prod, 1.0)
        prod_match = [
            i for i in range(len(keys))
            if parsed[i][0] == _prod
            and parsed[i][1] in sel_types
            and bps_rng[i] >= min_range_bps
        ]
        if not prod_match:
            continue

        with st.expander(
            f"📊 {_prod}  —  {len(prod_match):,} matching instruments",
            expanded=True,
        ):
            for _ttype in _TYPE_ORDER:
                if _ttype not in sel_types:
                    continue
                grp = [i for i in prod_match if parsed[i][1] == _ttype]
                if not grp:
                    continue

                grp_arr = np.array(grp)
                if sort_dir.startswith("High"):
                    ord_local = np.argsort(-bps_rng[grp_arr])
                else:
                    ord_local = np.argsort(bps_rng[grp_arr])
                top_grp = [grp[j] for j in ord_local[:n_show]]

                st.markdown(
                    f"<div style='color:#FFB347;font-size:10px;letter-spacing:1px;"
                    f"font-weight:700;margin:8px 0 3px 0;'>"
                    f"▸ {_TYPE_LABELS.get(_ttype, _ttype)}"
                    f"<span style='color:#555;font-weight:400;'> ({len(grp)} instruments"
                    f"{', top ' + str(n_show) + ' shown' if len(grp) > n_show else ''})"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )

                _is_out = (_ttype == "OUT")
                _row_lbs = [parsed[i][3] for i in top_grp]

                if _is_out:
                    _col_lbs = ["Range (bps)", "Min (price)", "Max (price)", "Mean (price)", "Std (bps)"]
                    _data = [
                        [
                            f"{bps_rng[i]:.2f}",
                            f"{stats['min'][i]  / _mult:.4f}",
                            f"{stats['max'][i]  / _mult:.4f}",
                            f"{stats['mean'][i] / _mult:.4f}",
                            f"{bps_std[i]:.2f}",
                        ]
                        for i in top_grp
                    ]
                else:
                    _col_lbs = ["Range (bps)", "Min (bps)", "Max (bps)", "Mean (bps)", "Std (bps)"]
                    _data = [
                        [
                            f"{bps_rng[i]:.2f}",
                            f"{bps_min[i]:.2f}",
                            f"{bps_max[i]:.2f}",
                            f"{bps_mean[i]:.2f}",
                            f"{bps_std[i]:.2f}",
                        ]
                        for i in top_grp
                    ]

                st.markdown(_bps_table(_row_lbs, _col_lbs, _data), unsafe_allow_html=True)
                grand_total += len(top_grp)

    if grand_total == 0:
        st.info("No instruments match these filters. Loosen them.")
    else:
        st.markdown(
            f"<small style='color:#666;'>Showing {grand_total:,} rows across all groups "
            f"(total universe: {len(keys):,} instruments).</small>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#222;margin:18px 0;'>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 2 — Hedge Finder
    # ════════════════════════════════════════════════════════════════════
    bb_subsection("② HEDGE FINDER  —  pick a primary leg, find the best hedges")

    st.markdown(
        "<small style='color:#888;'>"
        "<b style='color:#FFB347;'>What it does:</b> for the primary leg you "
        "pick, the finder scans every other instrument and every coprime "
        "integer ratio <code>a:b</code>. The winner per hedge is the ratio "
        "that minimises <code>range(a·primary + b·hedge)</code> in $ across "
        "your cases. Lower residual range = tighter trade."
        "</small>",
        unsafe_allow_html=True,
    )

    # Min-range gate so user can't accidentally pick a flat primary
    g1, g2 = st.columns([2, 2])
    with g1:
        primary_min_range_bps = st.number_input(
            "Hide primary candidates with range below (bps)",
            min_value=0.0, value=1.0, step=0.5,
            key="range_primary_minrng",
            help="Trivially-flat legs make terrible primaries — there's "
                 "nothing to capture. Keep this above 0.",
        )
    with g2:
        primary_prods = st.multiselect(
            "Restrict primary product",
            products_all, default=products_all,
            key="range_primary_prods",
        )

    eligible = [
        keys[i] for i in range(len(keys))
        if bps_rng[i] >= primary_min_range_bps and parsed[i][0] in primary_prods
    ]
    if not eligible:
        st.info("No primary candidates match the min-range filter. Lower it.")
        return

    # Pre-sort eligible by descending bps range (most volatile first)
    eligible_sorted = sorted(
        eligible, key=lambda k: -float(bps_rng[keys.index(k)])
    )
    _p_is_out = {k: parsed[keys.index(k)][1] == "OUT" for k in eligible_sorted}
    label_with_rng = {
        k: (
            f"{k}    [range {bps_rng[keys.index(k)]:.2f} bps · "
            f"price {stats['mean'][keys.index(k)] / MULTIPLIER.get(parsed[keys.index(k)][0], 1.0):.4f}]"
            if _p_is_out[k]
            else f"{k}    [range {bps_rng[keys.index(k)]:.2f} bps]"
        )
        for k in eligible_sorted
    }
    primary_label = st.selectbox(
        f"Primary leg ({len(eligible_sorted):,} eligible · sorted by range, biggest first)",
        eligible_sorted,
        format_func=lambda k: label_with_rng[k],
        key="range_primary_sel",
    )
    if not primary_label:
        return

    primary_idx  = keys.index(primary_label)
    p_prod       = parsed[primary_idx][0]
    p_mult       = MULTIPLIER.get(p_prod, 1.0)
    p_range      = float(stats["range"][primary_idx])
    p_range_bps  = float(bps_rng[primary_idx])
    p_min_bps    = float(bps_min[primary_idx])
    p_max_bps    = float(bps_max[primary_idx])
    p_std_bps    = float(bps_std[primary_idx])
    p_mean_px    = float(stats["mean"][primary_idx]) / p_mult  # price level for display

    _is_out_prim = (parsed[primary_idx][1] == "OUT")
    if _is_out_prim:
        _prim_detail = (
            f"range <b style='color:#FFB347;'>{p_range_bps:.2f} bps</b>  "
            f"(min {p_min_bps:.2f} bps, max {p_max_bps:.2f} bps, σ {p_std_bps:.2f} bps) "
            f"· mean price <b style='color:#00B4D8;'>{p_mean_px:.4f}</b>"
        )
    else:
        _prim_detail = (
            f"range <b style='color:#FFB347;'>{p_range_bps:.2f} bps</b>  "
            f"(min {p_min_bps:.2f} bps, max {p_max_bps:.2f} bps, σ {p_std_bps:.2f} bps)"
        )
    st.markdown(
        f"<div style='color:#888;font-size:11px;margin-bottom:8px;'>"
        f"<b>{primary_label}</b> across {matrix.shape[0]:,} cases: "
        f"{_prim_detail}"
        f"</div>",
        unsafe_allow_html=True,
    )

    cfg_cols = st.columns(2)
    with cfg_cols[0]:
        max_ratio = st.slider(
            "Max integer ratio per leg", 1, 8, 5,
            key="range_max_ratio",
            help="Search a:b in {1..N} × {-N..-1, 1..N}, gcd=1. Bigger N "
                 "finds tighter exotic ratios but the trade gets harder to fill.",
        )
    with cfg_cols[1]:
        top_k = st.slider(
            "Show top K hedges", 5, 100, 30,
            key="range_top_k",
        )

    hedges = find_best_hedges(primary_idx, matrix, max_ratio=max_ratio, top_k=top_k)
    if not hedges:
        st.info("No hedge candidates found.")
        return

    # ── Top trade card ───────────────────────────────────────────────────
    best = hedges[0]
    sign       = "BUY" if best["b"] > 0 else "SELL"
    sign_color = "#00FF41" if best["b"] > 0 else "#FF3131"
    a_lots = "lot" if best["a"] == 1 else "lots"
    b_lots = "lot" if abs(best["b"]) == 1 else "lots"

    st.markdown(
        f"<div style='border:2px solid #00B4D8;border-radius:4px;"
        f"padding:12px 16px;margin:8px 0 14px 0;background:#0a1628;'>"
        f"<div style='color:#FFB347;font-size:11px;letter-spacing:2px;font-weight:700;'>"
        f"⚡ TOP RANGE-BOUND TRADE</div>"
        f"<div style='color:#C0C0C0;font-size:13px;margin-top:8px;line-height:1.7;'>"
        f"&nbsp;<b style='color:#00FF41;'>BUY {best['a']} {a_lots}</b> of "
        f"<code style='color:#FFB347;background:#000;padding:2px 6px;border-radius:2px;'>"
        f"{primary_label}</code><br>"
        f"&nbsp;<b style='color:{sign_color};'>{sign} {abs(best['b'])} {b_lots}</b> of "
        f"<code style='color:#FFB347;background:#000;padding:2px 6px;border-radius:2px;'>"
        f"{keys[best['hedge_idx']]}</code></div>"
        f"<div style='color:#888;font-size:11px;margin-top:8px;'>"
        f"Residual $ range across {matrix.shape[0]:,} cases: "
        f"<b style='color:#00B4D8;'>${best['residual_range']:,.0f}</b> "
        f"(was ${p_range:,.0f}, "
        f"<b style='color:#00FF41;'>{best['reduction_pct']:.1f}% reduction</b>)"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # ── Full hedge table ─────────────────────────────────────────────────
    html = '<div class="bb-table-wrap"><table class="bb-table"><thead><tr>'
    html += '<th>#</th><th>Hedge instrument</th><th>Action</th><th>Ratio (P : H)</th>'
    html += '<th>Residual $ range</th><th>% reduction</th><th>Min $</th><th>Max $</th>'
    html += '</tr></thead><tbody>'
    for rank, h in enumerate(hedges, start=1):
        s_color = "#00FF41" if h["b"] > 0 else "#FF3131"
        s_text  = "BUY" if h["b"] > 0 else "SELL"
        red_class = "pos-val" if h["reduction_pct"] > 0 else "neg-val"
        html += '<tr>'
        html += f'<td style="color:#888;text-align:center;">{rank}</td>'
        html += f'<td class="bb-row-label">{keys[h["hedge_idx"]]}</td>'
        html += f'<td style="color:{s_color};font-weight:700;text-align:center;">{s_text}</td>'
        html += f'<td style="text-align:center;">{h["a"]} : {abs(h["b"])}</td>'
        html += f'<td>${h["residual_range"]:,.0f}</td>'
        html += f'<td class="{red_class}">{h["reduction_pct"]:+.1f}%</td>'
        html += f'<td>${h["residual_min"]:,.0f}</td>'
        html += f'<td>${h["residual_max"]:,.0f}</td>'
        html += '</tr>'
    html += '</tbody></table></div>'
    st.markdown(html, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#222;margin:18px 0;'>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 3 — Trade Inspector
    # ════════════════════════════════════════════════════════════════════
    bb_subsection("③ TRADE INSPECTOR  —  PnL distribution across cases")

    st.markdown(
        "<small style='color:#888;'>"
        "Pick any hedge from the table above (or override the ratio yourself). "
        "Below is the combo's $ value in every case. <b>If you enter at the "
        "mean, your worst-case PnL is <i>min − mean</i>, best-case is "
        "<i>max − mean</i>.</b> The tighter the histogram, the safer the trade."
        "</small>",
        unsafe_allow_html=True,
    )

    insp_cols = st.columns([3, 1, 1])
    with insp_cols[0]:
        # Default to top hedge; user can switch
        hedge_options = [
            (i, f"#{i+1}  {keys[h['hedge_idx']]}  "
                 f"({'BUY' if h['b']>0 else 'SELL'} {h['a']}:{abs(h['b'])} · "
                 f"residual ${h['residual_range']:,.0f})")
            for i, h in enumerate(hedges)
        ]
        sel_idx = st.selectbox(
            "Hedge to inspect (default = #1, the top trade)",
            options=[i for i, _ in hedge_options],
            format_func=lambda i: hedge_options[i][1],
            key="range_inspect_idx",
        )
    chosen = hedges[sel_idx]
    default_a, default_b = chosen["a"], chosen["b"]
    with insp_cols[1]:
        a_user = st.number_input(
            "Override a (primary lots)", value=int(default_a),
            min_value=-20, max_value=20, step=1,
            key="range_a_override",
        )
    with insp_cols[2]:
        b_user = st.number_input(
            "Override b (hedge lots, signed)", value=int(default_b),
            min_value=-20, max_value=20, step=1,
            key="range_b_override",
        )

    if a_user == 0 and b_user == 0:
        st.warning("Both lots are zero — pick non-zero ratios to inspect a trade.")
        return

    p_vec = matrix[:, primary_idx]
    h_vec = matrix[:, chosen["hedge_idx"]]
    combo = a_user * p_vec + b_user * h_vec

    c_min  = float(combo.min())
    c_max  = float(combo.max())
    c_mean = float(combo.mean())
    c_std  = float(combo.std(ddof=0))
    c_rng  = c_max - c_min

    # PnL if entered at mean
    pnl_worst = c_min - c_mean
    pnl_best  = c_max - c_mean

    # Direction summary
    a_dir = "BUY" if a_user > 0 else "SELL"
    b_dir = "BUY" if b_user > 0 else "SELL"

    st.markdown(
        f"<div style='border-left:3px solid #FF8C00;padding:8px 14px;margin:8px 0;background:#0d0a04;'>"
        f"<div style='color:#FFB347;font-size:11px;letter-spacing:1px;'>YOUR TRADE</div>"
        f"<div style='color:#C0C0C0;font-size:12px;margin-top:4px;line-height:1.6;'>"
        f"<b style='color:{'#00FF41' if a_user>0 else '#FF3131'};'>"
        f"{a_dir} {abs(a_user)} {'lot' if abs(a_user)==1 else 'lots'}</b> of "
        f"<code style='color:#FFB347;'>{primary_label}</code><br>"
        f"<b style='color:{'#00FF41' if b_user>0 else '#FF3131'};'>"
        f"{b_dir} {abs(b_user)} {'lot' if abs(b_user)==1 else 'lots'}</b> of "
        f"<code style='color:#FFB347;'>{keys[chosen['hedge_idx']]}</code>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # Stats strip
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("MEAN $",  f"${c_mean:,.0f}")
    m2.metric("STD $",   f"${c_std:,.0f}")
    m3.metric("MIN $",   f"${c_min:,.0f}")
    m4.metric("MAX $",   f"${c_max:,.0f}")
    m5.metric("RANGE $", f"${c_rng:,.0f}")

    # PnL summary
    st.markdown(
        f"<div style='border:1px solid #333;border-radius:3px;padding:10px 14px;"
        f"background:#050505;margin:10px 0;'>"
        f"<div style='color:#FFB347;font-size:11px;letter-spacing:1px;font-weight:700;'>"
        f"📊 PnL IF YOU ENTER AT THE MEAN (${c_mean:,.0f})</div>"
        f"<table style='width:100%;margin-top:6px;font-size:12px;'>"
        f"<tr><td style='color:#888;'>Worst-case PnL across cases:</td>"
        f"<td style='color:#FF3131;font-weight:700;text-align:right;'>${pnl_worst:,.0f}</td></tr>"
        f"<tr><td style='color:#888;'>Best-case PnL across cases:</td>"
        f"<td style='color:#00FF41;font-weight:700;text-align:right;'>${pnl_best:,.0f}</td></tr>"
        f"<tr><td style='color:#888;'>PnL spread (range):</td>"
        f"<td style='color:#00B4D8;font-weight:700;text-align:right;'>${c_rng:,.0f}</td></tr>"
        f"</table>"
        f"<div style='color:#666;font-size:10px;margin-top:6px;'>"
        f"To capture edge, compare live mid of this combo against ${c_mean:,.0f}. "
        f"If live &lt; mean, BUY — expected payoff to mean = (mean − live). "
        f"If live &gt; mean, SELL — expected payoff = (live − mean)."
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # ── Histogram of combo values per case ──────────────────────────────
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=combo,
        nbinsx=min(60, max(10, matrix.shape[0] // 20)),
        marker_color="#00B4D8",
        marker_line_color="#0a1628",
        marker_line_width=1,
        opacity=0.85,
        name="Combo $ value per case",
    ))
    fig.add_vline(
        x=c_mean, line_color="#FFB347", line_dash="dash", line_width=2,
        annotation_text=f"Mean ${c_mean:,.0f}",
        annotation_position="top",
        annotation_font=dict(color="#FFB347", size=10),
    )
    fig.add_vline(x=c_min, line_color="#FF3131", line_width=1)
    fig.add_vline(x=c_max, line_color="#00FF41", line_width=1)
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", height=320,
        margin=dict(l=50, r=20, t=30, b=40),
        xaxis=dict(title="Combo value ($)", showgrid=True, gridcolor="#222",
                   tickformat="$,.0f", title_font=dict(size=10)),
        yaxis=dict(title="# cases", showgrid=True, gridcolor="#222",
                   title_font=dict(size=10)),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Per-case combo value table (optional, capped) ───────────────────
    with st.expander(
        f"📋 Per-case combo values ({matrix.shape[0]:,} cases — sorted)", expanded=False,
    ):
        sort_choice = st.radio(
            "Sort", ["Best PnL → Worst", "Worst PnL → Best", "Case order"],
            horizontal=True, key="range_inspect_sort",
        )
        case_names = [c.get("name", c.get("id", f"case_{i}")) for i, c in enumerate(cm.cases)]
        pnls = combo - c_mean  # PnL if entry at mean
        if sort_choice.startswith("Best"):
            order_p = np.argsort(-pnls)
        elif sort_choice.startswith("Worst"):
            order_p = np.argsort(pnls)
        else:
            order_p = np.arange(len(case_names))

        # Cap at 200 rows for browser sanity
        order_p = order_p[:200]
        rows_html = []
        for rank, i in enumerate(order_p, start=1):
            pnl = float(pnls[i])
            color = "#00FF41" if pnl > 0 else ("#FF3131" if pnl < 0 else "#888")
            rows_html.append(
                f"<tr><td style='color:#666;text-align:right;padding:2px 8px;'>{rank}</td>"
                f"<td style='color:#C0C0C0;padding:2px 8px;'>{case_names[i]}</td>"
                f"<td style='text-align:right;padding:2px 8px;'>${combo[i]:,.0f}</td>"
                f"<td style='color:{color};font-weight:700;text-align:right;padding:2px 8px;'>"
                f"${pnl:+,.0f}</td></tr>"
            )
        st.markdown(
            "<div class='bb-table-wrap'><table class='bb-table'>"
            "<thead><tr><th>#</th><th>Case</th><th>Combo $</th><th>PnL vs mean</th></tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
