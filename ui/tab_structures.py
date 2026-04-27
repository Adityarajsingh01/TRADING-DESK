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
    render_base_rates, render_formula_builder, render_case_builder, render_case_list
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

def _case_selector(cm) -> List[dict]:
    if not cm.cases:
        st.info("No cases yet — build them in the input panel above.")
        return []

    opts = [f"{c['id']} | {c['name']}" for c in cm.cases]
    n_cases = len(opts)

    # ── Controls row: Select All / Clear ──────────────────────────────────────
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

    # ── Determine sensible default: last N added (so new cases appear immediately)
    # We always default to ALL cases so users can see them right after adding.
    # For very large sets (>50) default to the last 10 to keep table manageable.
    if sel_key not in st.session_state:
        if n_cases <= 50:
            st.session_state[sel_key] = opts[:]
        else:
            st.session_state[sel_key] = opts[-10:]  # last 10 added

    # Make sure any previously selected cases that still exist stay selected,
    # and newly added cases (not yet in session) are appended automatically.
    current_sel = st.session_state.get(sel_key, [])
    # Prune stale ids (deleted cases), add newly added ones
    valid_opts_set = set(opts)
    existing_valid = [s for s in current_sel if s in valid_opts_set]
    # Find newly added cases not yet in the selection
    existing_set = set(existing_valid)
    newly_added  = [o for o in opts if o not in existing_set]
    # If there are newly added cases, auto-select them so they appear immediately
    if newly_added:
        merged = existing_valid + newly_added
        st.session_state[sel_key] = merged

    sel = st.multiselect(
        "Cases:", opts,
        key=sel_key,
        label_visibility="collapsed",
        placeholder=f"Search & select from {n_cases} cases…",
    )

    ids = [s.split(" | ")[0] for s in sel]
    return [c for c in cm.cases if c["id"] in ids]


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
        render_formula_builder(cm)
        
    st.markdown("<hr style='border-color:#333;margin:20px 0;'>", unsafe_allow_html=True)

    selected = _case_selector(cm)
    if not selected:
        return

    with st.spinner("Computing prices..."):
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


def _render_live_curves(zqc, sr3c, cm):
    """Render live ZQ meeting premium curve and SR3 3M spread curve."""
    import plotly.graph_objects as go
    from core.live_data import get_live_price
    from config.fomc_dates import ALL_FOMC_MEETINGS
    from core.date_utils import month_calendar_days

    col_zq, col_sr3 = st.columns(2)

    # ── ZQ Meeting Premium Curve ──────────────────────────────────────────
    # Uses VWAP from live ZQ calendar spread instruments (ZQ_CAL_*)
    # matching CME FedWatch convention: negative = easing expected
    with col_zq:
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

        per_mtg, labels, spd_detail = [], [], []

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
                # TT sends prices ×100; calendar spreads aren't ÷100 back,
                # so stored VWAP is already in bps scale
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
            lbl = dec.strftime("%b '%y")
            if meeting.get('is_sep'):
                lbl += " *"
            labels.append(lbl)
            spd_detail.append(f"ZQ {fc}-{bc}: {premium:+.4f} bps  ({src})")

        if labels:
            fig = go.Figure()
            # Single bold live line — per-meeting premium
            fig.add_trace(go.Scatter(
                x=labels, y=per_mtg, name="LIVE",
                mode="lines+markers",
                line=dict(color="#00B4D8", width=3),
                marker=dict(size=6, color="#00B4D8"),
            ))
            # Case overlays (dotted)
            colors = ["#4f8dff", "#00d4aa", "#f2cd32", "#ff4f8d", "#a78bfa"]
            for i, case in enumerate(cm.cases):
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
        spd_labels, spd_values = [], []
        for i in range(len(sr3c) - 1):
            front, back = sr3c[i], sr3c[i+1]
            pf, pb = sr3_px.get(front['code']), sr3_px.get(back['code'])
            if pf is not None and pb is not None:
                # front - back: negative in easing (back price > front price)
                spd = round((pf - pb) * 100, 2)
                spd_labels.append(f"{front['code'][3:]}-{back['code'][3:]}")
                spd_values.append(spd)
        if spd_labels:
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
            colors = ["#4f8dff", "#00d4aa", "#f2cd32", "#ff4f8d", "#a78bfa"]
            for ci, case in enumerate(cm.cases):
                cs, cl = [], []
                for i in range(len(sr3c) - 1):
                    f_, b_ = sr3c[i], sr3c[i+1]
                    p = case.get('rate_path', {}).get('sofr', {})
                    from core.pricing_engine import price_sr3
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
    _render_live_curves(zqc, sr3c, cm)

    sec1, sec2, sec3, sec4, sec5, sec6, sec7 = st.tabs([
        "📌 OUTRIGHTS", "↔ SPREADS", "🦋 BUTTERFLIES", "🔷 CONDORS", "🌀 DEFLYS",
        "📊 MEETING RANGE", "🔬 STRUCTURES LIVE"
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
        _render_meeting_range(cm)

    # ─── STRUCTURES LIVE ──────────────────────────────────────────────────────
    with sec7:
        bb_section("STRUCTURES LIVE")
        _render_structures_live(cm, zqc, sr3c)



def _render_meeting_range(cm):
    analysis = cm.meeting_range_analysis()
    if not analysis:
        st.info("No cases to analyze.")
        return

    bb_subsection("ALL MEETINGS — CUT/HIKE RANGE ACROSS CASES")
    # Columns are the names of all cases in the CM
    col_labels = [c["name"][:15] for c in cm.cases]
    row_labels = []
    data = []
    for row in analysis:
        lbl = row["decision_date"].strftime("%Y %b %d")
        if row["is_sep"]:
            lbl += " ⭐"
        row_labels.append(lbl)
        data.append(row["values"])

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


def _render_structures_live(cm, zqc, sr3c):
    """Render live ZQ fly and SR3 spread values vs case projections."""
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

    case_names = [c['name'][:15] for c in cm.cases]

    col1, col2 = st.columns(2)

    # ── ZQ Flies ──────────────────────────────────────────────────────────
    with col1:
        bb_section("ZQ MEETING BUTTERFLIES")
        hdr = "<tr><th style='text-align:left;padding:4px 8px;color:#00B4D8;'>Structure</th>"
        hdr += "<th style='padding:4px 8px;color:#00B4D8;'>LIVE</th>"
        for cn in case_names:
            hdr += f"<th style='padding:4px 8px;color:#a78bfa;'>{cn}</th>"
        hdr += "</tr>"
        rows = ""
        fly_names, fly_vals = [], []
        for name, legs in ZQ_FLIES:
            val = _live_fly(legs)
            fly_names.append(name.replace("ZQ ","").replace(" Fly",""))
            fly_vals.append(val if val is not None else 0)
            rows += f"<tr><td style='padding:3px 8px;color:#C0C0C0;white-space:nowrap;'>{name}</td>"
            rows += f"<td style='padding:3px 8px;text-align:center;'>{_cv(val)}</td>"
            for case in cm.cases:
                cv = _case_zq_fly(case, legs)
                rows += f"<td style='padding:3px 8px;text-align:center;'>{_cv(cv)}</td>"
            rows += "</tr>"
        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:12px;font-family:monospace;'>"
            f"<thead style='border-bottom:1px solid #333;'>{hdr}</thead><tbody>{rows}</tbody></table>",
            unsafe_allow_html=True)

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
        hdr2 = "<tr><th style='text-align:left;padding:4px 8px;color:#00B4D8;'>Structure</th>"
        hdr2 += "<th style='padding:4px 8px;color:#00B4D8;'>LIVE</th>"
        for cn in case_names:
            hdr2 += f"<th style='padding:4px 8px;color:#a78bfa;'>{cn}</th>"
        hdr2 += "</tr>"
        rows2 = ""
        spd_names, spd_vals = [], []
        for name, legs in SR3_SPDS:
            val = _live_spread(legs)
            spd_names.append(name.replace("SR3 ",""))
            spd_vals.append(val if val is not None else 0)
            rows2 += f"<tr><td style='padding:3px 8px;color:#C0C0C0;white-space:nowrap;'>{name}</td>"
            rows2 += f"<td style='padding:3px 8px;text-align:center;'>{_cv(val)}</td>"
            for case in cm.cases:
                cv = _case_sr3_spread(case, legs)
                rows2 += f"<td style='padding:3px 8px;text-align:center;'>{_cv(cv)}</td>"
            rows2 += "</tr>"
        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:12px;font-family:monospace;'>"
            f"<thead style='border-bottom:1px solid #333;'>{hdr2}</thead><tbody>{rows2}</tbody></table>",
            unsafe_allow_html=True)

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
