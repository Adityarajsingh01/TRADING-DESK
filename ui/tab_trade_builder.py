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

# ── Structure definitions (same as Structures Live in Case Analyzer) ──────────
_ZQ_FLIES = [
    ("ZQ Jul26 Aug26 Oct26 Fly", ["ZQN26","ZQQ26","ZQV26"]),
    ("ZQ Aug26 Oct26 Nov26 Fly", ["ZQQ26","ZQV26","ZQX26"]),
    ("ZQ Oct26 Nov26 Jan27 Fly", ["ZQV26","ZQX26","ZQF27"]),
    ("ZQ Nov26 Jan27 Feb27 Fly", ["ZQX26","ZQF27","ZQG27"]),
    ("ZQ Jan27 Feb27 Apr27 Fly", ["ZQF27","ZQG27","ZQJ27"]),
    ("ZQ Feb27 Apr27 May27 Fly", ["ZQG27","ZQJ27","ZQK27"]),
    ("ZQ Apr27 May27 Jul27 Fly", ["ZQJ27","ZQK27","ZQN27"]),
]

_SR3_SPDS = [
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
    # Fallback: compute directly from bare leg codes (Structures Live trades)
    from core.live_data import get_live_price
    prices = [get_live_price(l, t.product) for l in t.legs]
    if any(p is None for p in prices):
        return None
    if t.trade_type == "Outright":
        return prices[0]
    elif t.trade_type == "Spread":
        return round(prices[1] - prices[0], 4)  # back - front
    elif t.trade_type == "Butterfly (Fly)":
        return round(prices[0] - 2*prices[1] + prices[2], 4)
    elif t.trade_type == "Condor":
        return round(prices[0] - prices[1] - prices[2] + prices[3], 4)
    elif t.trade_type == "Defly":
        return round(prices[0] - 3*prices[1] + 3*prices[2] - prices[3], 4)
    return None


# ── Structures Live helpers ───────────────────────────────────────────────────

def _sl_get_price(bare_code, zqc, sr3c):
    """Get outright mid for a bare code like ZQN26 or SR3M26."""
    from core.live_data import get_live_price
    # Build code_map on first call
    code_map = {}
    for c in zqc + sr3c:
        b = c['code'].split(' (')[0] if ' (' in c['code'] else c['code']
        code_map[b] = c['code']
    suffixed = code_map.get(bare_code, bare_code)
    return get_live_price(suffixed)

def _sl_live_fly(legs, zqc, sr3c):
    p = [_sl_get_price(l, zqc, sr3c) for l in legs]
    if all(x is not None for x in p):
        return (p[0] - 2*p[1] + p[2]) * 100
    return None

def _sl_live_spread(legs, zqc, sr3c):
    p = [_sl_get_price(l, zqc, sr3c) for l in legs]
    if all(x is not None for x in p):
        return (p[0] - p[1]) * 100
    return None

def _sl_cv(v):
    if v is None: return "<span style='color:#555;'>—</span>"
    c = "#00FF41" if v > 0.01 else "#FF3131" if v < -0.01 else "#C0C0C0"
    return f"<span style='color:{c};font-weight:bold;'>{v:+.3f}</span>"

def _sl_case_zq_fly(case, legs):
    from core.pricing_engine import price_zq
    C2M = {'F':1,'G':2,'H':3,'J':4,'K':5,'M':6,'N':7,'Q':8,'U':9,'V':10,'X':11,'Z':12}
    path = case.get('rate_path', {}).get('effr', {})
    base = case.get('base_effr', 3.64)
    prices = []
    for l in legs:
        suffix = l[2:]  # e.g. "N26"
        yr = 2000 + int(suffix[1:])
        mo = C2M[suffix[0]]
        prices.append(price_zq(yr, mo, path, base))
    return (prices[0] - 2*prices[1] + prices[2]) * 100

def _sl_case_sr3_spread(case, legs, sr3c):
    from core.pricing_engine import price_sr3
    path = case.get('rate_path', {}).get('sofr', {})
    base = case.get('base_sofr', 3.64)
    sr3_map = {}
    for c in sr3c:
        bare = c['code'].split(' (')[0] if ' (' in c['code'] else c['code']
        sr3_map[bare] = c
    prices = []
    for l in legs:
        cinfo = sr3_map.get(l)
        if cinfo is None: return None
        prices.append(price_sr3(cinfo['ref_start'], cinfo['ref_end'], path, base))
    return (prices[0] - prices[1]) * 100


def _render_structures_live_panel(cm, blotter, zqc, sr3c):
    """Render ZQ flies + SR3 spreads with live values, case projections, and quick-trade buttons."""
    bb_section("STRUCTURES LIVE — QUICK TRADE")
    case_names = [c['name'][:15] for c in cm.cases]

    col1, col2 = st.columns(2)

    # ── ZQ Butterflies ────────────────────────────────────────────────────
    with col1:
        bb_subsection("ZQ MEETING BUTTERFLIES")
        hdr = "<tr><th style='text-align:left;white-space:nowrap;min-width:180px;'>Structure</th>"
        hdr += "<th style='white-space:nowrap;min-width:70px;color:#00B4D8;'>LIVE</th>"
        for cn in case_names:
            hdr += f"<th style='white-space:nowrap;min-width:70px;color:#a78bfa;'>{cn}</th>"
        hdr += "</tr>"
        rows = ""
        fly_names, fly_vals = [], []
        for i, (name, legs) in enumerate(_ZQ_FLIES):
            val = _sl_live_fly(legs, zqc, sr3c)
            fly_names.append(name.replace("ZQ ","").replace(" Fly",""))
            fly_vals.append(val if val is not None else 0)
            rows += f"<tr><td class='bb-row-label' style='white-space:nowrap;'>{name}</td>"
            rows += f"<td style='text-align:center;white-space:nowrap;'>{_sl_cv(val)}</td>"
            for case in cm.cases:
                cv = _sl_case_zq_fly(case, legs)
                rows += f"<td style='text-align:center;white-space:nowrap;'>{_sl_cv(cv)}</td>"
            rows += "</tr>"
        st.markdown(
            f"<div class='bb-table-wrap'>"
            f"<table class='bb-table'>"
            f"<thead>{hdr}</thead><tbody>{rows}</tbody></table></div>",
            unsafe_allow_html=True)

        # Quick-trade buttons for ZQ flies
        fly_sel = st.selectbox("Select ZQ Fly to trade", [n for n, _ in _ZQ_FLIES], key="tb_sl_zq_sel")
        qc1, qc2 = st.columns(2)
        with qc1:
            if st.button("BUY this Fly", key="tb_sl_zq_buy", type="primary"):
                _quick_trade_fly(fly_sel, "BUY", blotter, zqc, sr3c)
                st.rerun()
        with qc2:
            if st.button("SELL this Fly", key="tb_sl_zq_sell"):
                _quick_trade_fly(fly_sel, "SELL", blotter, zqc, sr3c)
                st.rerun()

        # Bar chart
        fig = go.Figure()
        fig.add_trace(go.Bar(x=fly_names, y=fly_vals,
            marker_color=["#00FF41" if v>=0 else "#FF3131" for v in fly_vals],
            text=[f"{v:+.2f}" for v in fly_vals], textposition="outside",
            textfont=dict(size=9, color="#C0C0C0")))
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=250, showlegend=False,
            margin=dict(l=40,r=10,t=10,b=60), xaxis=dict(tickangle=-30, tickfont=dict(size=8)),
            yaxis=dict(title="bps", tickformat=".2f", zeroline=True, zerolinecolor="#444"))
        fig.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── SR3 Calendar Spreads ──────────────────────────────────────────────
    with col2:
        bb_subsection("SR3 CALENDAR SPREADS (1Q)")
        hdr2 = "<tr><th style='text-align:left;white-space:nowrap;min-width:180px;'>Structure</th>"
        hdr2 += "<th style='white-space:nowrap;min-width:70px;color:#00B4D8;'>LIVE</th>"
        for cn in case_names:
            hdr2 += f"<th style='white-space:nowrap;min-width:70px;color:#a78bfa;'>{cn}</th>"
        hdr2 += "</tr>"
        rows2 = ""
        spd_names, spd_vals = [], []
        for name, legs in _SR3_SPDS:
            val = _sl_live_spread(legs, zqc, sr3c)
            spd_names.append(name.replace("SR3 ",""))
            spd_vals.append(val if val is not None else 0)
            rows2 += f"<tr><td class='bb-row-label' style='white-space:nowrap;'>{name}</td>"
            rows2 += f"<td style='text-align:center;white-space:nowrap;'>{_sl_cv(val)}</td>"
            for case in cm.cases:
                cv = _sl_case_sr3_spread(case, legs, sr3c)
                rows2 += f"<td style='text-align:center;white-space:nowrap;'>{_sl_cv(cv)}</td>"
            rows2 += "</tr>"
        st.markdown(
            f"<div class='bb-table-wrap'>"
            f"<table class='bb-table'>"
            f"<thead>{hdr2}</thead><tbody>{rows2}</tbody></table></div>",
            unsafe_allow_html=True)

        # Quick-trade buttons for SR3 spreads
        spd_sel = st.selectbox("Select SR3 Spread to trade", [n for n, _ in _SR3_SPDS], key="tb_sl_sr3_sel")
        qc3, qc4 = st.columns(2)
        with qc3:
            if st.button("BUY this Spread", key="tb_sl_sr3_buy", type="primary"):
                _quick_trade_spread(spd_sel, "BUY", blotter, zqc, sr3c)
                st.rerun()
        with qc4:
            if st.button("SELL this Spread", key="tb_sl_sr3_sell"):
                _quick_trade_spread(spd_sel, "SELL", blotter, zqc, sr3c)
                st.rerun()

        # Bar chart
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=spd_names, y=spd_vals,
            marker_color=["#00FF41" if v>=0 else "#FF3131" for v in spd_vals],
            text=[f"{v:+.2f}" for v in spd_vals], textposition="outside",
            textfont=dict(size=8, color="#C0C0C0")))
        fig2.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=250, showlegend=False,
            margin=dict(l=40,r=10,t=10,b=60), xaxis=dict(tickangle=-30, tickfont=dict(size=7)),
            yaxis=dict(title="bps", tickformat=".2f", zeroline=True, zerolinecolor="#444"))
        fig2.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<hr style='border-color:#1a3050;margin:20px 0;'>", unsafe_allow_html=True)


def _quick_trade_fly(name, side, blotter, zqc, sr3c):
    """Add a ZQ fly trade to the blotter at live mid."""
    legs = next((l for n, l in _ZQ_FLIES if n == name), None)
    if not legs: return
    key = "/".join(legs)
    live_val = _sl_live_fly(legs, zqc, sr3c)
    # Entry in price points (same unit as get_live_struct_price)
    entry_px = round(live_val / 100, 4) if live_val is not None else 0.0
    trade = Trade(
        product="ZQ", trade_type="Butterfly (Fly)",
        legs=legs, instrument_key=key,
        display_name=f"[FLY] {name}",
        side=side, lots=1, entry_price=entry_px,
        entry_source="Structures Live",
    )
    blotter.add_trade(trade)
    bps_str = f"{live_val:+.3f} bps" if live_val is not None else "---"
    st.success(f"Added {side} 1x {name} @ {bps_str}")


def _quick_trade_spread(name, side, blotter, zqc, sr3c):
    """Add an SR3 spread trade to the blotter at live mid."""
    legs = next((l for n, l in _SR3_SPDS if n == name), None)
    if not legs: return
    key = f"{legs[1]}-{legs[0]}"  # back-front convention
    live_val = _sl_live_spread(legs, zqc, sr3c)  # front-back in bps
    # Convert to back-front price points (blotter convention: back - front)
    entry_px = round(-live_val / 100, 4) if live_val is not None else 0.0
    trade = Trade(
        product="SR3", trade_type="Spread",
        legs=legs, instrument_key=key,
        display_name=f"[SPD 1Q] {name}",
        side=side, lots=1, entry_price=entry_px,
        entry_source="Structures Live",
    )
    blotter.add_trade(trade)
    bps_str = f"{live_val:+.3f} bps" if live_val is not None else "---"
    st.success(f"Added {side} 1x {name} @ {bps_str}")


# ---- MAIN RENDER ----
def render_trade_builder_tab(cm, sr1c, zqc, sr3c):
    all_cases = cm.cases
    blotter = _get_blotter()
    catalog = _build_instrument_catalog(sr1c, zqc, sr3c)
    st.session_state["tb_catalog"] = catalog

    # ── Structures Live panel at the top ──────────────────────────────────
    _render_structures_live_panel(cm, blotter, zqc, sr3c)

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
        pnl_val = t.pnl(live_px) if live_px is not None else None
        bps_chg = t.pnl_bps(live_px) if live_px is not None else None
        t_dv01 = t.dv01()
        if pnl_val is not None:
            total_live_pnl += pnl_val
        total_dv01_all += t_dv01

        # Display entry & live in bps for structure trades, price points for outrights
        is_struct = t.trade_type != "Outright"
        if is_struct:
            entry_disp = f"{t.entry_price * 100:+.3f}"
            live_disp = f"{live_px * 100:+.3f}" if live_px is not None else "---"
        else:
            entry_disp = f"{t.entry_price:.4f}"
            live_disp = f"{live_px:.4f}" if live_px is not None else "---"

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
            <td style="color:#FFB347;">{entry_disp}</td>
            <td style="color:#00FF41;font-weight:600;">{live_disp}</td>
            <td style="color:{pc};font-weight:700;">{bps_str}</td>
            <td style="color:{pc};font-weight:700;">{pnl_str}</td>
        </tr>"""

    ptc = "#00FF41" if total_live_pnl >= 0 else "#FF3131"
    st.markdown(f"""
    <div class="bb-table-wrap">
    <table class="bb-table">
    <thead><tr>
        <th>ID</th><th>DATE</th><th>SIDE</th><th>LOTS</th><th>PROD</th>
        <th>INSTRUMENT</th><th>ENTRY</th><th>LIVE</th><th>chg bps</th><th>PnL ($)</th>
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
