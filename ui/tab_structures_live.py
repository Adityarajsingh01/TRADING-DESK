"""
ui/tab_structures_live.py
─────────────────────────
Structures Live tab — shows live ZQ butterfly and SR3 calendar spread values
alongside case-based projections for direct comparison.
"""

import streamlit as st
from ui.styles import bb_section, bb_subsection
from core.live_data import LIVE_PRICES, get_live_price

# ── Structure definitions ──────────────────────────────────────────────────────
ZQ_FLIES = [
    {"code": "ZQ_FLY_N26Q26V26", "name": "ZQ Jul26 Aug26 Oct26 Fly",
     "legs": ["ZQN26", "ZQQ26", "ZQV26"]},
    {"code": "ZQ_FLY_Q26V26X26", "name": "ZQ Aug26 Oct26 Nov26 Fly",
     "legs": ["ZQQ26", "ZQV26", "ZQX26"]},
    {"code": "ZQ_FLY_V26X26F27", "name": "ZQ Oct26 Nov26 Jan27 Fly",
     "legs": ["ZQV26", "ZQX26", "ZQF27"]},
    {"code": "ZQ_FLY_X26F27G27", "name": "ZQ Nov26 Jan27 Feb27 Fly",
     "legs": ["ZQX26", "ZQF27", "ZQG27"]},
    {"code": "ZQ_FLY_F27G27J27", "name": "ZQ Jan27 Feb27 Apr27 Fly",
     "legs": ["ZQF27", "ZQG27", "ZQJ27"]},
    {"code": "ZQ_FLY_G27J27K27", "name": "ZQ Feb27 Apr27 May27 Fly",
     "legs": ["ZQG27", "ZQJ27", "ZQK27"]},
    {"code": "ZQ_FLY_J27K27N27", "name": "ZQ Apr27 May27 Jul27 Fly",
     "legs": ["ZQJ27", "ZQK27", "ZQN27"]},
]

SR3_SPREADS = [
    {"code": "SR3_CAL_H26M26", "name": "SR3 Mar26-Jun26", "legs": ["SR3H26", "SR3M26"]},
    {"code": "SR3_CAL_M26U26", "name": "SR3 Jun26-Sep26", "legs": ["SR3M26", "SR3U26"]},
    {"code": "SR3_CAL_U26Z26", "name": "SR3 Sep26-Dec26", "legs": ["SR3U26", "SR3Z26"]},
    {"code": "SR3_CAL_Z26H27", "name": "SR3 Dec26-Mar27", "legs": ["SR3Z26", "SR3H27"]},
    {"code": "SR3_CAL_H27M27", "name": "SR3 Mar27-Jun27", "legs": ["SR3H27", "SR3M27"]},
    {"code": "SR3_CAL_M27U27", "name": "SR3 Jun27-Sep27", "legs": ["SR3M27", "SR3U27"]},
    {"code": "SR3_CAL_U27Z27", "name": "SR3 Sep27-Dec27", "legs": ["SR3U27", "SR3Z27"]},
    {"code": "SR3_CAL_Z27H28", "name": "SR3 Dec27-Mar28", "legs": ["SR3Z27", "SR3H28"]},
    {"code": "SR3_CAL_H28M28", "name": "SR3 Mar28-Jun28", "legs": ["SR3H28", "SR3M28"]},
    {"code": "SR3_CAL_M28U28", "name": "SR3 Jun28-Sep28", "legs": ["SR3M28", "SR3U28"]},
    {"code": "SR3_CAL_U28Z28", "name": "SR3 Sep28-Dec28", "legs": ["SR3U28", "SR3Z28"]},
    {"code": "SR3_CAL_Z28H29", "name": "SR3 Dec28-Mar29", "legs": ["SR3Z28", "SR3H29"]},
    {"code": "SR3_CAL_H29M29", "name": "SR3 Mar29-Jun29", "legs": ["SR3H29", "SR3M29"]},
    {"code": "SR3_CAL_M29U29", "name": "SR3 Jun29-Sep29", "legs": ["SR3M29", "SR3U29"]},
    {"code": "SR3_CAL_U29Z29", "name": "SR3 Sep29-Dec29", "legs": ["SR3U29", "SR3Z29"]},
    {"code": "SR3_CAL_Z29H30", "name": "SR3 Dec29-Mar30", "legs": ["SR3Z29", "SR3H30"]},
    {"code": "SR3_CAL_H30M30", "name": "SR3 Mar30-Jun30", "legs": ["SR3H30", "SR3M30"]},
    {"code": "SR3_CAL_M30U30", "name": "SR3 Jun30-Sep30", "legs": ["SR3M30", "SR3U30"]},
    {"code": "SR3_CAL_U30Z30", "name": "SR3 Sep30-Dec30", "legs": ["SR3U30", "SR3Z30"]},
]


def _get_live_struct(code, legs, struct_type="fly"):
    """Get live value: VWAP/Mid from direct subscription, or compute from outrights."""

    # 1. Try VWAP from direct calendar spread / fly subscription
    entry = LIVE_PRICES.get(code, {})
    vwap = entry.get('VWAP')
    if vwap is not None:
        return vwap, "VWAP"

    # 2. Try Mid from direct subscription
    mid = entry.get('Mid')
    if mid is not None:
        return mid, "Mid"

    # 3. Fallback: compute from outright leg prices
    #    LIVE_PRICES stores outrights with month suffix e.g. "ZQN26 (Jul)"
    #    so we need to find the matching key
    def _find_price(bare_code):
        # Direct lookup first
        e = LIVE_PRICES.get(bare_code, {})
        if e.get('Mid') is not None:
            return e['Mid']
        # Search for key starting with bare_code + " ("
        for k, v in LIVE_PRICES.items():
            if k.startswith(bare_code + " (") and v.get('Mid') is not None:
                return v['Mid']
        return None

    prices = [_find_price(l) for l in legs]
    if any(p is None for p in prices):
        return None, ""

    if struct_type == "fly" and len(prices) == 3:
        val = (prices[0] - 2 * prices[1] + prices[2]) * 100  # bps
        return val, "Calc"
    elif struct_type == "spread" and len(prices) == 2:
        val = (prices[0] - prices[1]) * 100  # bps
        return val, "Calc"

    return None, ""


def _case_struct_value(case, legs, struct_type="fly"):
    """Compute structure value from case rate path."""
    from core.pricing_engine import price_sr3
    product = "ZQ" if legs[0].startswith("ZQ") else "SR3"

    if product == "ZQ":
        # For ZQ, use EFFR rate path
        path = case.get('rate_path', {}).get('effr', {})
        base = case.get('base_effr', 3.64)
        # ZQ price = 100 - avg_effr_for_month
        # We'd need month dates to compute this — skip for now and return None
        # This requires more infrastructure; show "—" for ZQ case values
        return None
    else:
        # SR3 — use pricing engine
        path = case.get('rate_path', {}).get('sofr', {})
        base = case.get('base_sofr', 3.64)
        from core.date_utils import generate_sr3_contracts
        all_sr3 = generate_sr3_contracts()
        sr3_map = {c['code'].split(' ')[0]: c for c in all_sr3}

        prices = []
        for leg in legs:
            clean = leg.split(' ')[0]
            cinfo = sr3_map.get(clean)
            if cinfo is None:
                return None
            p = price_sr3(cinfo['ref_start'], cinfo['ref_end'], path, base)
            prices.append(p)

        if struct_type == "fly" and len(prices) == 3:
            return (prices[0] - 2 * prices[1] + prices[2]) * 100
        elif struct_type == "spread" and len(prices) == 2:
            return (prices[0] - prices[1]) * 100
    return None


def _color_val(v):
    """Color a value: green positive, red negative, white zero."""
    if v is None:
        return "<span style='color:#555;'>—</span>"
    color = "#00FF41" if v > 0.01 else "#FF3131" if v < -0.01 else "#C0C0C0"
    return f"<span style='color:{color};font-weight:bold;'>{v:+.3f}</span>"


def render_structures_live_tab(cm, sr3c):
    """Render the Structures Live tab."""
    import plotly.graph_objects as go

    col1, col2 = st.columns(2)

    # ── ZQ Butterflies ────────────────────────────────────────────────────
    with col1:
        bb_section("ZQ MEETING BUTTERFLIES")

        # Build table
        case_names = [c['name'][:15] for c in cm.cases]
        hdr = "<tr><th style='text-align:left;padding:4px 8px;color:#00B4D8;'>Structure</th>"
        hdr += "<th style='padding:4px 8px;color:#00B4D8;'>LIVE</th>"
        hdr += "<th style='padding:4px 8px;color:#555;font-size:9px;'>Src</th>"
        for cn in case_names:
            hdr += f"<th style='padding:4px 8px;color:#a78bfa;'>{cn}</th>"
        hdr += "</tr>"

        rows = ""
        for fly in ZQ_FLIES:
            val, src = _get_live_struct(fly['code'], fly['legs'], "fly")
            rows += "<tr>"
            rows += f"<td style='padding:3px 8px;color:#C0C0C0;white-space:nowrap;'>{fly['name']}</td>"
            rows += f"<td style='padding:3px 8px;text-align:center;'>{_color_val(val)}</td>"
            rows += f"<td style='padding:3px 8px;text-align:center;color:#555;font-size:9px;'>{src}</td>"
            for case in cm.cases:
                cv = _case_struct_value(case, fly['legs'], "fly")
                rows += f"<td style='padding:3px 8px;text-align:center;'>{_color_val(cv)}</td>"
            rows += "</tr>"

        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:12px;font-family:monospace;'>"
            f"<thead style='border-bottom:1px solid #333;'>{hdr}</thead>"
            f"<tbody>{rows}</tbody></table>",
            unsafe_allow_html=True,
        )

        # ── ZQ Fly Chart ─────────────────────────────────────────────────
        bb_subsection("ZQ FLY VALUES")
        fly_names = [f['name'].replace('ZQ ', '').replace(' Butterfly', '') for f in ZQ_FLIES]
        fly_vals = []
        for f in ZQ_FLIES:
            v, _ = _get_live_struct(f['code'], f['legs'], "fly")
            fly_vals.append(v if v is not None else 0)

        fig = go.Figure()
        bar_colors = ["#00FF41" if v >= 0 else "#FF3131" for v in fly_vals]
        fig.add_trace(go.Bar(
            x=fly_names, y=fly_vals, marker_color=bar_colors,
            text=[f"{v:+.2f}" for v in fly_vals], textposition="outside",
            textfont=dict(size=9, color="#C0C0C0"),
        ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=280,
            margin=dict(l=40, r=10, t=10, b=60),
            xaxis=dict(tickangle=-30, tickfont=dict(size=8)),
            yaxis=dict(title="bps", tickformat=".2f", zeroline=True, zerolinecolor="#444"),
            showlegend=False,
        )
        fig.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── SR3 Calendar Spreads ──────────────────────────────────────────────
    with col2:
        bb_section("SR3 CALENDAR SPREADS (1Q)")

        hdr2 = "<tr><th style='text-align:left;padding:4px 8px;color:#00B4D8;'>Structure</th>"
        hdr2 += "<th style='padding:4px 8px;color:#00B4D8;'>LIVE</th>"
        hdr2 += "<th style='padding:4px 8px;color:#555;font-size:9px;'>Src</th>"
        for cn in case_names:
            hdr2 += f"<th style='padding:4px 8px;color:#a78bfa;'>{cn}</th>"
        hdr2 += "</tr>"

        rows2 = ""
        for spd in SR3_SPREADS:
            val, src = _get_live_struct(spd['code'], spd['legs'], "spread")
            rows2 += "<tr>"
            rows2 += f"<td style='padding:3px 8px;color:#C0C0C0;white-space:nowrap;'>{spd['name']}</td>"
            rows2 += f"<td style='padding:3px 8px;text-align:center;'>{_color_val(val)}</td>"
            rows2 += f"<td style='padding:3px 8px;text-align:center;color:#555;font-size:9px;'>{src}</td>"
            for case in cm.cases:
                cv = _case_struct_value(case, spd['legs'], "spread")
                rows2 += f"<td style='padding:3px 8px;text-align:center;'>{_color_val(cv)}</td>"
            rows2 += "</tr>"

        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:12px;font-family:monospace;'>"
            f"<thead style='border-bottom:1px solid #333;'>{hdr2}</thead>"
            f"<tbody>{rows2}</tbody></table>",
            unsafe_allow_html=True,
        )

        # ── SR3 Spread Chart ─────────────────────────────────────────────
        bb_subsection("SR3 SPREAD VALUES")
        spd_names = [s['name'].replace('SR3 ', '') for s in SR3_SPREADS]
        spd_vals = []
        for s in SR3_SPREADS:
            v, _ = _get_live_struct(s['code'], s['legs'], "spread")
            spd_vals.append(v if v is not None else 0)

        fig2 = go.Figure()
        bar_colors2 = ["#00FF41" if v >= 0 else "#FF3131" for v in spd_vals]
        fig2.add_trace(go.Bar(
            x=spd_names, y=spd_vals, marker_color=bar_colors2,
            text=[f"{v:+.2f}" for v in spd_vals], textposition="outside",
            textfont=dict(size=8, color="#C0C0C0"),
        ))

        # Case overlays
        colors = ["#4f8dff", "#00d4aa", "#f2cd32", "#ff4f8d", "#a78bfa"]
        for ci, case in enumerate(cm.cases):
            case_vals = []
            for s in SR3_SPREADS:
                cv = _case_struct_value(case, s['legs'], "spread")
                case_vals.append(cv if cv is not None else 0)
            fig2.add_trace(go.Scatter(
                x=spd_names, y=case_vals, name=case['name'][:12],
                mode="lines+markers", line=dict(color=colors[ci % len(colors)], width=1.5, dash="dot"),
                marker=dict(size=4),
            ))

        fig2.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=280,
            margin=dict(l=40, r=10, t=10, b=60),
            xaxis=dict(tickangle=-30, tickfont=dict(size=7)),
            yaxis=dict(title="bps", tickformat=".2f", zeroline=True, zerolinecolor="#444"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=8)),
        )
        fig2.add_hline(y=0, line_color="#444", line_width=1, line_dash="dot")
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    # ── Debug: Raw data diagnostic ────────────────────────────────────────
    with st.expander("🔧 LIVE DATA DIAGNOSTIC", expanded=False):
        st.markdown("**ZQ Fly Instruments**")
        for f in ZQ_FLIES:
            raw = LIVE_PRICES.get(f['code'], {})
            st.text(f"{f['code']}: {raw if raw else '❌ NO DATA'}")

        st.markdown("**SR3 Calendar Spread Instruments**")
        for s in SR3_SPREADS[:5]:  # show first 5
            raw = LIVE_PRICES.get(s['code'], {})
            st.text(f"{s['code']}: {raw if raw else '❌ NO DATA'}")

        st.markdown("**ZQ Outright Samples (for reference)**")
        for code in ['ZQN26', 'ZQQ26', 'ZQV26', 'ZQX26']:
            raw = LIVE_PRICES.get(code, {})
            st.text(f"{code}: {raw if raw else '❌ NO DATA'}")

        st.markdown("**SR3 Outright Samples**")
        for code in ['SR3H26', 'SR3M26', 'SR3U26', 'SR3Z26']:
            raw = LIVE_PRICES.get(code, {})
            st.text(f"{code}: {raw if raw else '❌ NO DATA'}")

        st.markdown(f"**Total LIVE_PRICES keys: {len(LIVE_PRICES)}**")
        st.text("All keys with data: " + ", ".join(sorted(k for k, v in LIVE_PRICES.items() if v)))
