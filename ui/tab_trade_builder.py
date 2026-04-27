"""
STIR Terminal — Tab 2: Trade Builder (Pro-Trader Edition)
Full instrument picker, live PnL, trade blotter, scenario matrix.
CME-accurate PnL: PnL = (exit - entry) x Multiplier x lots x sign
"""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
from typing import Dict, List, Optional
from datetime import date, timedelta

from ui.styles import bb_section, bb_subsection, render_bloomberg_table
from config.constants import CONTRACT_SPECS, CONTRACT_MULTIPLIER
from core.trade_engine import (
    Trade, TradeBlotter, compute_pnl, compute_pnl_bps,
    dv01_per_lot, STRUCTURE_WEIGHTS, structure_leg_count, structure_total_lots,
)

TRADE_TYPES = ["Outright", "Spread", "Butterfly (Fly)", "Condor", "Defly"]

def _contract_codes(contracts: list) -> List[str]:
    return [c["code"] for c in contracts]

def _get_blotter() -> TradeBlotter:
    if "trade_blotter" not in st.session_state:
        st.session_state["trade_blotter"] = TradeBlotter()
    return st.session_state["trade_blotter"]

def _build_instrument_catalog(sr1c, zqc, sr3c) -> Dict[str, dict]:
    from core.live_data import get_live_price, get_live_struct_price
    from config.constants import (
        SR1_SPREAD_GAPS, ZQ_SPREAD_GAPS, SR3_SPREAD_GAPS,
        SR1_FLY_GAPS, ZQ_FLY_GAPS, SR3_FLY_GAPS,
    )
    catalog = {}
    for product, contracts in [("SR1", sr1c), ("ZQ", zqc), ("SR3", sr3c)]:
        for c in contracts:
            code = c["code"]
            live = get_live_price(code, product)
            catalog[code] = {
                "key": code, "product": product, "type": "Outright",
                "legs": [code], "label": f"[OUT] {code}",
                "live_mid": live, "struct_type": "outright",
            }
    for product, contracts, gaps in [
        ("SR1", sr1c, SR1_SPREAD_GAPS), ("ZQ", zqc, ZQ_SPREAD_GAPS), ("SR3", sr3c, SR3_SPREAD_GAPS)
    ]:
        for gap in gaps:
            unit = "Q" if product == "SR3" else "M"
            for i in range(len(contracts) - gap):
                front, back = contracts[i], contracts[i + gap]
                key = f"{back['code']}-{front['code']}"
                live = get_live_struct_price(key, "spread", product)
                catalog[key] = {
                    "key": key, "product": product, "type": "Spread",
                    "legs": [front["code"], back["code"]],
                    "label": f"[SPD {gap}{unit}] {key}",
                    "live_mid": live, "struct_type": "spread",
                }
    for product, contracts, gaps in [
        ("SR1", sr1c, SR1_FLY_GAPS), ("ZQ", zqc, ZQ_FLY_GAPS), ("SR3", sr3c, SR3_FLY_GAPS)
    ]:
        for gap in gaps:
            unit = "Q" if product == "SR3" else "M"
            for i in range(len(contracts) - 2 * gap):
                f_, m_, b_ = contracts[i], contracts[i+gap], contracts[i+2*gap]
                key = f"{f_['code']}/{m_['code']}/{b_['code']}"
                live = get_live_struct_price(key, "fly", product)
                catalog[key] = {
                    "key": key, "product": product, "type": "Butterfly (Fly)",
                    "legs": [f_["code"], m_["code"], b_["code"]],
                    "label": f"[FLY {gap}{unit}] {key}",
                    "live_mid": live, "struct_type": "fly",
                }
    condor_gaps = {"SR1": [1], "ZQ": [1], "SR3": [1, 2]}
    for product, contracts in [("SR1", sr1c), ("ZQ", zqc), ("SR3", sr3c)]:
        for gap in condor_gaps[product]:
            unit = "Q" if product == "SR3" else "M"
            for i in range(len(contracts) - 3 * gap):
                c0, c1 = contracts[i], contracts[i+gap]
                c2, c3 = contracts[i+2*gap], contracts[i+3*gap]
                key = f"{c0['code']}/{c1['code']}/{c2['code']}/{c3['code']}"
                live_c = get_live_struct_price(key, "condor", product)
                catalog[f"CDR:{key}"] = {
                    "key": key, "product": product, "type": "Condor",
                    "legs": [c0["code"], c1["code"], c2["code"], c3["code"]],
                    "label": f"[CDR {gap}{unit}] {key}",
                    "live_mid": live_c, "struct_type": "condor",
                }
                live_d = get_live_struct_price(key, "defly", product)
                catalog[f"DFL:{key}"] = {
                    "key": key, "product": product, "type": "Defly",
                    "legs": [c0["code"], c1["code"], c2["code"], c3["code"]],
                    "label": f"[DFL {gap}{unit}] {key}",
                    "live_mid": live_d, "struct_type": "defly",
                }
    return catalog

def _get_case_structure_price(trade_type, product, legs, case_prices):
    px = case_prices.get(product, {})
    prices = [px.get(leg) for leg in legs]
    if any(p is None for p in prices):
        return None
    if trade_type == "Outright":
        return prices[0]
    elif trade_type == "Spread":
        return round(prices[1] - prices[0], 4)
    elif trade_type == "Butterfly (Fly)":
        return round(prices[0] - 2 * prices[1] + prices[2], 4)
    elif trade_type == "Condor":
        return round(prices[0] - prices[1] - prices[2] + prices[3], 4)
    elif trade_type == "Defly":
        return round(prices[0] - 3*prices[1] + 3*prices[2] - prices[3], 4)
    return None

def _live_price_for_instrument(inst):
    from core.live_data import get_live_price, get_live_struct_price
    if inst["type"] == "Outright":
        return get_live_price(inst["legs"][0], inst["product"])
    return get_live_struct_price(inst["key"], inst["struct_type"], inst["product"])

def _live_price_for_trade(t, catalog):
    inst = catalog.get(t.instrument_key) or catalog.get(f"CDR:{t.instrument_key}") or catalog.get(f"DFL:{t.instrument_key}")
    if inst:
        return _live_price_for_instrument(inst)
    return None

# ---- MAIN RENDER ----
def render_trade_builder_tab(cm, sr1c, zqc, sr3c):
    all_cases = cm.cases
    blotter = _get_blotter()
    catalog = _build_instrument_catalog(sr1c, zqc, sr3c)
    st.session_state["tb_catalog"] = catalog

    bb_section("NEW TRADE ENTRY")
    col_prod, col_type = st.columns([1, 1])
    with col_prod:
        product_filter = st.selectbox("Product", ["SR1", "ZQ", "SR3"], key="tb_prod_filter")
    with col_type:
        type_filter = st.selectbox("Structure", TRADE_TYPES, key="tb_type_filter")

    filtered = {k: v for k, v in catalog.items() if v["product"] == product_filter and v["type"] == type_filter}
    if not filtered:
        st.warning("No instruments available for this product/structure combination.")
        return

    inst_options = {v["label"]: k for k, v in filtered.items()}
    inst_labels = list(inst_options.keys())
    selected_label = st.selectbox("Instrument", inst_labels, key="tb_instrument_sel",
                                   help="All instruments from your dashboard")
    catalog_key = inst_options[selected_label]
    inst = filtered[catalog_key]
    live_mid = _live_price_for_instrument(inst)
    live_str = f"{live_mid:.4f}" if live_mid is not None else "---"
    legs_str = " / ".join(inst["legs"])

    st.markdown(
        f"""<div style="display:flex;gap:16px;flex-wrap:wrap;margin:6px 0;">
            <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:6px 14px;text-align:center;">
                <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">LEGS</div>
                <div style="color:#90caf9;font-size:12px;font-weight:600;">{legs_str}</div>
            </div>
            <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:6px 14px;text-align:center;">
                <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">LIVE MID</div>
                <div style="color:#00FF41;font-size:14px;font-weight:700;">{live_str}</div>
            </div>
            <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:6px 14px;text-align:center;">
                <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">DV01/LOT</div>
                <div style="color:#FFB347;font-size:14px;font-weight:700;">${dv01_per_lot(product_filter):.2f}</div>
            </div>
            <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:6px 14px;text-align:center;">
                <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">MULTIPLIER</div>
                <div style="color:#FFB347;font-size:14px;font-weight:700;">${CONTRACT_MULTIPLIER[product_filter]:,}</div>
            </div>
        </div>""", unsafe_allow_html=True)

    col_side, col_lots, col_entry = st.columns([1, 1, 2])
    with col_side:
        side = st.radio("Side", ["BUY", "SELL"], horizontal=True, key="tb_side")
    with col_lots:
        lots = st.number_input("Lots", min_value=1, max_value=10000, value=1, step=1, key="tb_lots")

    # Entry price source
    with col_entry:
        entry_sources = ["Manual"]
        if live_mid is not None:
            entry_sources.insert(0, f"Live Mid ({live_mid:.4f})")
        if all_cases:
            for c in all_cases[:5]:
                entry_sources.append(f"Case: {c['id']}|{c['name'][:12]}")
        source = st.selectbox("Entry Price Source", entry_sources, key="tb_entry_source")

    # FIX #1: Force-sync entry price when source changes
    prev_source = st.session_state.get("_tb_prev_source", "")
    if source.startswith("Live Mid"):
        resolved = live_mid if live_mid else 0.0
    elif source.startswith("Case:"):
        cid = source.split(":")[1].split("|")[0].strip()
        ap = st.session_state.get("_shared_prices", {})
        cpx = ap.get(cid)
        resolved = _get_case_structure_price(type_filter, product_filter, inst["legs"], cpx) if cpx else 0.0
        if resolved is None:
            resolved = 0.0
    else:
        resolved = st.session_state.get("tb_entry_price", 0.0)

    if source != prev_source:
        st.session_state["tb_entry_price"] = float(round(resolved, 4))
        st.session_state["_tb_prev_source"] = source

    entry_price = st.number_input("Entry Price", value=float(round(resolved, 4)),
                                   step=0.0025, format="%.4f", key="tb_entry_price")

    sign_val = 1 if side == "BUY" else -1
    total_dv01 = dv01_per_lot(product_filter) * lots
    pnl_per_bp = total_dv01 * sign_val
    pnl_color = '#00FF41' if pnl_per_bp > 0 else '#FF3131'

    st.markdown(
        f"""<div style="display:flex;gap:16px;margin:6px 0;flex-wrap:wrap;">
            <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:6px 14px;text-align:center;">
                <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">TOTAL DV01</div>
                <div style="color:#FFB347;font-size:14px;font-weight:700;">${total_dv01:,.2f}</div>
            </div>
            <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:6px 14px;text-align:center;">
                <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">PnL / bp</div>
                <div style="color:{pnl_color};font-size:14px;font-weight:700;">${pnl_per_bp:,.2f}</div>
            </div>
            <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:6px 14px;text-align:center;">
                <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">OUTRIGHT EQUIV</div>
                <div style="color:#C0C0C0;font-size:14px;font-weight:700;">{structure_total_lots(type_filter)}x per lot</div>
            </div>
        </div>""", unsafe_allow_html=True)

    notes = st.text_input("Notes (optional)", key="tb_notes", placeholder="e.g. Jun FOMC play")

    if st.button("ADD TO BLOTTER", key="tb_add_trade", type="primary"):
        if entry_price <= 0 and type_filter == "Outright":
            st.error("Enter a valid entry price.")
        else:
            trade = Trade(
                product=product_filter, trade_type=type_filter,
                legs=inst["legs"], instrument_key=inst["key"],
                display_name=selected_label,
                side=side, lots=lots, entry_price=entry_price,
                entry_source=source.split("(")[0].strip(), notes=notes,
            )
            blotter.add_trade(trade)
            st.success(f"Added {side} {lots}x {selected_label} @ {entry_price:.4f}")
            st.rerun()

    # ---- BLOTTER ----
    st.markdown("<hr style='border-color:#1a3050;margin:20px 0;'>", unsafe_allow_html=True)
    bb_section(f"TRADE BLOTTER ({len(blotter.trades)} trades)")
    if not blotter.trades:
        st.info("No trades in blotter. Add trades above.")
    else:
        _render_live_blotter(blotter, catalog, all_cases, sr1c, zqc, sr3c)


@st.fragment(run_every=timedelta(seconds=2))
def _render_live_blotter(blotter, catalog, all_cases, sr1c, zqc, sr3c):
    bb_subsection("POSITIONS & LIVE PnL")
    total_live_pnl = 0.0
    total_dv01_all = 0.0
    rows_html = ""

    for t in blotter.trades:
        live_px = _live_price_for_trade(t, catalog)
        live_str = f"{live_px:.4f}" if live_px is not None else "---"
        pnl_val = t.pnl(live_px) if live_px is not None else None
        bps_chg = t.pnl_bps(live_px) if live_px is not None else None
        t_dv01 = t.dv01()
        if pnl_val is not None:
            total_live_pnl += pnl_val
        total_dv01_all += t_dv01

        pnl_str = f"${pnl_val:,.2f}" if pnl_val is not None else "---"
        bps_str = f"{bps_chg:+.2f}" if bps_chg is not None else "---"
        pc = "#00FF41" if (pnl_val or 0) >= 0 else "#FF3131"
        sc = "#00FF41" if t.side == "BUY" else "#FF3131"
        si = "B" if t.side == "BUY" else "S"
        # FIX #2: Full display name
        dn = getattr(t, 'display_name', '') or t.instrument_key
        # FIX #3: Show date/time
        ts = t.created_at[5:16].replace('T', ' ') if t.created_at else "---"

        rows_html += f"""<tr>
            <td class="bb-row-label" style="min-width:55px;">{t.id}</td>
            <td style="color:#666;font-size:10px;white-space:nowrap;">{ts}</td>
            <td style="color:{sc};font-weight:700;">{si} {t.side}</td>
            <td style="color:#FFB347;">{t.lots}</td>
            <td style="color:#90caf9;">{t.product}</td>
            <td style="color:#C0C0C0;text-align:left;white-space:nowrap;">{dn}</td>
            <td style="color:#FFB347;">{t.entry_price:.4f}</td>
            <td style="color:#00FF41;font-weight:600;">{live_str}</td>
            <td style="color:{pc};font-weight:700;">{bps_str}</td>
            <td style="color:{pc};font-weight:700;">{pnl_str}</td>
        </tr>"""

    ptc = "#00FF41" if total_live_pnl >= 0 else "#FF3131"
    st.markdown(f"""
    <div class="bb-table-wrap">
    <table class="bb-table">
    <thead><tr>
        <th>ID</th><th>DATE</th><th>SIDE</th><th>LOTS</th><th>PROD</th>
        <th>INSTRUMENT</th><th>ENTRY</th><th>LIVE</th><th>bps</th><th>PnL ($)</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="display:flex;gap:20px;margin:10px 0;flex-wrap:wrap;">
        <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:8px 18px;text-align:center;">
            <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">PORTFOLIO PnL</div>
            <div style="color:{ptc};font-size:18px;font-weight:700;">${total_live_pnl:,.2f}</div>
        </div>
        <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:8px 18px;text-align:center;">
            <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">TOTAL DV01</div>
            <div style="color:#FFB347;font-size:18px;font-weight:700;">${total_dv01_all:,.2f}</div>
        </div>
        <div style="background:#0a1628;border:1px solid #1a3050;border-radius:2px;padding:8px 18px;text-align:center;">
            <div style="color:#4fc3f7;font-size:9px;letter-spacing:1px;">TRADES</div>
            <div style="color:#C0C0C0;font-size:18px;font-weight:700;">{len(blotter.trades)}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Delete controls
    bb_subsection("MANAGE BLOTTER")
    dc = st.columns([3, 1, 1])
    with dc[0]:
        tids = [f"{t.id} | {t.side} {t.lots}x {getattr(t,'display_name','') or t.instrument_key}" for t in blotter.trades]
        ds = st.selectbox("Select trade to remove", tids, key="tb_del_sel")
    with dc[1]:
        if st.button("Remove", key="tb_del_btn"):
            blotter.remove_trade(ds.split(" | ")[0])
            st.rerun()
    with dc[2]:
        if st.button("Clear All", key="tb_clear_btn"):
            blotter.clear_all()
            st.rerun()

    # ---- SCENARIO PnL ----
    if all_cases and blotter.trades:
        st.markdown("<hr style='border-color:#1a3050;margin:20px 0;'>", unsafe_allow_html=True)
        bb_section("SCENARIO PnL - ALL CASES")
        _render_scenario_matrix(blotter, all_cases, sr1c, zqc, sr3c)


def _render_scenario_matrix(blotter, all_cases, sr1c, zqc, sr3c):
    all_prices = st.session_state.get("_shared_prices", {})
    if not all_prices:
        from ui.tab_structures import _prices_for_cases
        with st.spinner("Computing scenario prices..."):
            all_prices = _prices_for_cases(all_cases, sr1c, zqc, sr3c)
            st.session_state["_shared_prices"] = all_prices

    col_labels = [f"{c['id']} {c['name'][:10]}" for c in all_cases]
    case_totals = [0.0] * len(all_cases)

    # FIX #4: Per-trade scenario PnL (separate table per trade)
    for t in blotter.trades:
        dn = getattr(t, 'display_name', '') or t.instrument_key
        si = "BUY" if t.side == "BUY" else "SELL"
        bb_subsection(f"{si} {t.lots}x {dn}  |  Entry: {t.entry_price:.4f}")

        r_price, r_bps, r_pnl = [], [], []
        for ci, case in enumerate(all_cases):
            cpx = all_prices.get(case["id"], {})
            epx = _get_case_structure_price(t.trade_type, t.product, t.legs, cpx)
            if epx is not None:
                pnl = t.pnl(epx)
                bps = t.pnl_bps(epx)
                r_price.append(round(epx, 4))
                r_bps.append(round(bps, 2))
                r_pnl.append(round(pnl, 2))
                case_totals[ci] += pnl
            else:
                r_price.append(None)
                r_bps.append(None)
                r_pnl.append(None)

        st.markdown(render_bloomberg_table(
            ["Case Price", "Delta bps", "PnL ($)"], col_labels,
            [r_price, r_bps, r_pnl], fmt="{:.2f}"
        ), unsafe_allow_html=True)

    # Portfolio total row
    bb_subsection("PORTFOLIO TOTAL PnL")
    st.markdown(render_bloomberg_table(
        ["TOTAL PnL ($)"], col_labels,
        [[round(v, 2) for v in case_totals]], fmt="${:,.2f}"
    ), unsafe_allow_html=True)

    # Bar chart
    case_names = [c["name"][:15] for c in all_cases]
    colours = ["#00FF41" if v >= 0 else "#FF3131" for v in case_totals]
    fig = go.Figure(go.Bar(
        x=case_names, y=case_totals, marker_color=colours,
        marker_line_color="#1a3050", marker_line_width=0.5,
        text=[f"${v:,.0f}" for v in case_totals], textposition="outside",
        textfont=dict(color="#C0C0C0", size=9),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, Courier New", color="#C0C0C0", size=10),
        title=dict(text=f"Portfolio Scenario PnL", font=dict(color="#00B4D8", size=11), x=0),
        xaxis=dict(tickfont=dict(color="#4fc3f7", size=9), gridcolor="#1a2a40", tickangle=-30),
        yaxis=dict(tickfont=dict(color="#4fc3f7", size=9), gridcolor="#1a2a40",
                   title=dict(text="P&L ($)", font=dict(color="#00B4D8")),
                   zeroline=True, zerolinecolor="#333"),
        margin=dict(l=60, r=20, t=50, b=80), height=350, showlegend=False,
    )
    fig.add_hline(y=0, line_color="#333", line_width=1)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if case_totals:
        bb_subsection("PORTFOLIO SCENARIO SUMMARY")
        bi = case_totals.index(max(case_totals))
        wi = case_totals.index(min(case_totals))
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("Best Case", f"${max(case_totals):,.0f}", delta=case_names[bi])
        with m2: st.metric("Worst Case", f"${min(case_totals):,.0f}", delta=case_names[wi])
        with m3: st.metric("Mean PnL", f"${sum(case_totals)/len(case_totals):,.0f}")
        with m4: st.metric("Positive", f"{sum(1 for v in case_totals if v>0)}/{len(case_totals)}")
