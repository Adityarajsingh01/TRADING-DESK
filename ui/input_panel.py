"""
STIR Terminal — Input Panel (Sidebar)
Fixed: H1/H2 uses 2-row layout instead of squeezed 4-column.
"""

from __future__ import annotations
import streamlit as st
from config.fomc_dates import FOMC_BY_YEAR
from ui.styles import bb_section, bb_subsection


def _years() -> list:
    return [2026, 2027, 2028, 2029, 2030]


# ── Base Rates ────────────────────────────────────────────────────────────────

def render_base_rates() -> tuple[float, float]:
    bb_section("BASE RATES")
    st.markdown(
        "<small style='color:#666'>Current live rates — manual entry</small>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        base_sofr = st.number_input(
            "SOFR (%)", min_value=0.0, max_value=20.0,
            value=st.session_state.get("base_sofr", 3.64),
            step=0.0025, format="%.4f", key="base_sofr_input",
        )
    with c2:
        base_effr = st.number_input(
            "EFFR (%)", min_value=0.0, max_value=20.0,
            value=st.session_state.get("base_effr", 3.64),
            step=0.0025, format="%.4f", key="base_effr_input",
        )
    st.session_state["base_sofr"] = base_sofr
    st.session_state["base_effr"] = base_effr

    st.markdown(
        f"""<div style='display:flex;gap:8px;margin-top:5px;'>
            <div style='flex:1;background:#0D0D00;border:1px solid #FF6600;
                        border-radius:2px;padding:5px;text-align:center;'>
                <div style='color:#FF8C00;font-size:8px;letter-spacing:2px;'>SOFR</div>
                <div style='color:#00FF41;font-size:16px;font-weight:700;'>{base_sofr:.4f}%</div>
            </div>
            <div style='flex:1;background:#0D0D00;border:1px solid #FF6600;
                        border-radius:2px;padding:5px;text-align:center;'>
                <div style='color:#FF8C00;font-size:8px;letter-spacing:2px;'>EFFR</div>
                <div style='color:#00FF41;font-size:16px;font-weight:700;'>{base_effr:.4f}%</div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )
    return base_sofr, base_effr


# ── Formula Builder ───────────────────────────────────────────────────────────

def render_formula_builder(cm) -> None:
    with st.expander("🔧 FORMULA BUILDER", expanded=False):
        st.markdown(
            "<small style='color:#666'>Define cut distribution across meetings</small>",
            unsafe_allow_html=True,
        )
        formula_name = st.text_input("Formula Name", placeholder="e.g. Quarterly Cuts", key="fml_name")
        formula_desc = st.text_input("Description", placeholder="Optional", key="fml_desc")

        freq = st.radio("Meeting Frequency:", ["All 8 Meetings", "Quarterly (4 SEP Meetings)"], horizontal=True, key="fml_freq")
        mode = st.radio("Input Method:", ["Direct Weights", "Marginal Cuts (bps)"], horizontal=True, key="fml_input_mode")
        
        is_quarterly = (freq == "Quarterly (4 SEP Meetings)")
        num_inputs   = 4 if is_quarterly else 8
        labels       = ["Q1 (Mar)", "Q2 (Jun)", "Q3 (Sep)", "Q4 (Dec)"] if is_quarterly else [f"M{i+1}" for i in range(8)]
        
        raw_weights = []
        row1 = st.columns(4)
        row2 = st.columns(4) if num_inputs == 8 else None

        if mode == "Direct Weights":
            for i in range(num_inputs):
                col = row1[i] if i < 4 else row2[i - 4]
                with col:
                    w = st.number_input(
                        labels[i], min_value=0.0, max_value=1.0,
                        value=round(1/num_inputs, 4), step=0.01, format="%.3f",
                        key=f"fml_w_{i}",
                    )
                    raw_weights.append(w)
        else:
            st.markdown(
                "<small style='color:#666'>Enter bps cut/hike for each meeting (e.g. -25, 0)</small>",
                unsafe_allow_html=True,
            )
            marginal_cuts = []
            cum = 0.0
            for i in range(num_inputs):
                col = row1[i] if i < 4 else row2[i - 4]
                with col:
                    m = st.number_input(
                        labels[i], value=0.0, step=12.5, format="%.1f",
                        key=f"fml_p_{i}",
                    )
                    marginal_cuts.append(m)
                    cum += m
                    color = "#FF3131" if cum > 0 else ("#00FF41" if cum < 0 else "#888")
                    st.markdown(
                        f"<div style='color:{color};font-size:10px;margin-top:-10px;margin-bottom:10px;'>Cum: {cum:+.1f}</div>",
                        unsafe_allow_html=True
                    )
            
            # Derive weights from absolute marginal cuts
            total_abs = sum(abs(c) for c in marginal_cuts)
            if total_abs == 0:
                raw_weights = [1/num_inputs] * num_inputs
            else:
                raw_weights = [abs(c) / total_abs for c in marginal_cuts]

        # Map to 8-meeting structure
        if is_quarterly:
            final_weights = [0.0] * 8
            # SEP meetings are indices 1 (Mar), 3 (Jun), 5 (Sep), 7 (Dec)
            final_weights[1] = raw_weights[0]
            final_weights[3] = raw_weights[1]
            final_weights[5] = raw_weights[2]
            final_weights[7] = raw_weights[3]
        else:
            final_weights = raw_weights

        total_w = sum(final_weights)
        colour  = "#00FF41" if abs(total_w - 1) < 0.01 else "#FF3131"
        
        if mode == "Direct Weights":
            st.markdown(
                f"<small style='color:{colour};'>∑ = {total_w:.3f} (auto-normalised)</small>",
                unsafe_allow_html=True,
            )
        else:
            w_str = " | ".join(f"{w:.3f}" for w in final_weights)
            st.markdown(
                f"<small style='color:#FFB347'>Auto-calculated 8-meeting weights: <br><b>{w_str}</b></small>",
                unsafe_allow_html=True,
            )

        if st.button("💾 SAVE FORMULA", key="save_formula_btn"):
            if not formula_name.strip():
                st.error("Formula name required")
            elif formula_name in cm.get_formula_names():
                st.error("Name already exists")
            else:
                cm.add_formula(formula_name, final_weights, formula_desc)
                st.success(f"Saved '{formula_name}'!")
                st.rerun()

        st.markdown("---")
        bb_subsection("Saved Formulas")
        for f in cm.formulas:
            tag = "🔒" if f.get("is_builtin") else "📋"
            with st.expander(f"{tag} {f['name']}", expanded=False):
                fc1, fc2 = st.columns([5, 1])
                with fc1:
                    w_str = " | ".join(f"{w:.3f}" for w in f["weights"])
                    st.markdown(
                        f"<small style='color:#666'>{f.get('description','')}</small><br>"
                        f"<span style='color:#FF6600;font-size:9px;'>{w_str}</span>",
                        unsafe_allow_html=True,
                    )
                with fc2:
                    if st.button("✕", key=f"del_fml_{f['name']}", help="Delete"):
                        cm.delete_formula(f["name"])
                        st.rerun()


# ── Year Row ──────────────────────────────────────────────────────────────────

def _render_year_row(year: int, formula_names: list, key_prefix: str) -> dict:
    from datetime import date as dt_date
    today = dt_date.today()

    meetings = FOMC_BY_YEAR.get(year, [])
    official = meetings and meetings[0]["is_official"]
    icon = "✅" if official else "🔮"

    # Count future meetings
    n_future = sum(1 for m in meetings if m["effective_date"] > today)
    n_past   = len(meetings) - n_future

    st.markdown(
        f"<div style='color:#FF8C00;font-size:10px;letter-spacing:1px;"
        f"border-top:1px solid #1A1A1A;padding-top:5px;margin-top:5px;'>"
        f"{icon} <b>{year}</b>"
        f"<span style='color:#555;font-size:9px;margin-left:8px;'>"
        f"{n_past} past · {n_future} future</span></div>",
        unsafe_allow_html=True,
    )

    mode = st.radio(
        "Mode", options=["Annual", "H1 / H2", "Per Meeting"],
        horizontal=True, key=f"{key_prefix}_mode_{year}",
        label_visibility="collapsed",
    )

    if mode == "Annual":
        config = {"mode": "annual"}
        c1, c2 = st.columns([2, 3])
        with c1:
            annual_cut = st.number_input(
                "Total bps", value=0.0, step=0.5, format="%.2f",
                key=f"{key_prefix}_annual_{year}",
                help=f"Full cut/hike applied across {n_future} remaining future meetings",
            )
        with c2:
            formula = st.selectbox(
                "Formula", formula_names, key=f"{key_prefix}_fml_{year}",
            )
        config["annual_cut"]   = annual_cut
        config["formula_name"] = formula

        if annual_cut != 0 and n_past > 0:
            st.markdown(
                f"<small style='color:#FF8C00;'>⚠ {n_past} past meetings excluded — "
                f"full {annual_cut:+.2f}bps distributed across {n_future} future meetings only</small>",
                unsafe_allow_html=True,
            )
        return config

    elif mode == "H1 / H2":
        config = {"mode": "h1h2"}
        # H1 row
        c1, c2 = st.columns(2)
        with c1:
            h1_cut = st.number_input(
                "H1 bps", value=0.0, step=0.5, format="%.2f",
                key=f"{key_prefix}_h1_{year}",
            )
        with c2:
            h1_fml = st.selectbox("H1 Formula", formula_names, key=f"{key_prefix}_h1fml_{year}")
        # H2 row
        c3, c4 = st.columns(2)
        with c3:
            h2_cut = st.number_input(
                "H2 bps", value=0.0, step=0.5, format="%.2f",
                key=f"{key_prefix}_h2_{year}",
            )
        with c4:
            h2_fml = st.selectbox("H2 Formula", formula_names, key=f"{key_prefix}_h2fml_{year}")

        config["h1_cut"]     = h1_cut
        config["h1_formula"] = h1_fml
        config["h2_cut"]     = h2_cut
        config["h2_formula"] = h2_fml
        return config

    else:  # Per Meeting
        config = {"mode": "per_meeting", "per_meeting_cuts": {}}

        if not meetings:
            st.markdown("<small style='color:#555;'>No FOMC meetings for this year.</small>",
                        unsafe_allow_html=True)
            return config

        st.markdown(
            "<small style='color:#666;'>Enter bps directly per meeting. "
            "Past meetings are locked at 0 (already in base rate).</small>",
            unsafe_allow_html=True,
        )

        cumulative = 0.0
        per_meeting_cuts = {}

        for i, m in enumerate(meetings):
            eff_date   = m["effective_date"]
            dec_date   = m["decision_date"]
            is_past    = eff_date <= today
            is_sep     = m.get("is_sep", False)
            sep_marker = " ⭐" if is_sep else ""
            label      = f"{dec_date.strftime('%b %d')}{sep_marker}"
            past_label = " 🔒" if is_past else ""

            col_label, col_input, col_cum = st.columns([3, 2, 2])

            with col_label:
                color = "#555" if is_past else "#C0C0C0"
                st.markdown(
                    f"<div style='color:{color};font-size:10px;padding-top:8px;'>"
                    f"{label}{past_label}</div>",
                    unsafe_allow_html=True,
                )

            with col_input:
                if is_past:
                    st.markdown(
                        "<div style='color:#444;font-size:11px;padding-top:8px;'>0.0</div>",
                        unsafe_allow_html=True,
                    )
                    bps = 0.0
                else:
                    bps = st.number_input(
                        f"bps_{year}_{i}", value=0.0, step=12.5, format="%.1f",
                        key=f"{key_prefix}_pm_{year}_{i}",
                        label_visibility="collapsed",
                    )

            cumulative += bps
            with col_cum:
                cum_color = "#00FF41" if cumulative < 0 else ("#FF3131" if cumulative > 0 else "#555")
                st.markdown(
                    f"<div style='color:{cum_color};font-size:10px;padding-top:8px;'>"
                    f"Σ {cumulative:+.1f}</div>",
                    unsafe_allow_html=True,
                )

            per_meeting_cuts[eff_date.isoformat()] = bps

        # Summary
        future_cuts = [v for k, v in per_meeting_cuts.items()
                       if dt_date.fromisoformat(k) > today]
        total_future = sum(future_cuts)
        total_color = "#00FF41" if total_future < 0 else ("#FF3131" if total_future > 0 else "#888")
        st.markdown(
            f"<div style='color:{total_color};font-size:11px;font-weight:700;"
            f"border-top:1px solid #222;padding-top:4px;margin-top:2px;'>"
            f"Total future cuts: {total_future:+.2f} bps</div>",
            unsafe_allow_html=True,
        )

        config["per_meeting_cuts"] = per_meeting_cuts
        return config




# ── Case Builder ──────────────────────────────────────────────────────────────

def render_case_builder(cm) -> None:
    bb_section("CASE BUILDER")
    formula_names = cm.get_formula_names()

    case_name = st.text_input(
        "Case Name", placeholder="e.g. War Theme 2026", key="case_name_input",
    )

    year_configs = {}
    with st.expander("📅 YEAR-BY-YEAR RATE PATH", expanded=True):
        for y in _years():
            year_configs[str(y)] = _render_year_row(y, formula_names, "cb")

    if st.button("🔍 PREVIEW CUTS", key="preview_btn"):
        from core.case_manager import build_rate_path, compute_meeting_cuts_for_year
        from datetime import date as dt_date
        sofr = st.session_state.get("base_sofr", 3.64)
        effr = st.session_state.get("base_effr", 3.64)
        sofr_path, _, all_cuts = build_rate_path(sofr, effr, year_configs)
        today = dt_date.today()

        if all_cuts:
            lines = []
            current_rate = sofr
            for m in sorted(all_cuts.keys()):
                bps = all_cuts[m]
                is_past = m <= today
                if not is_past and bps != 0:
                    current_rate = round(current_rate + bps / 100.0, 6)
                tag = "[PAST – skipped]" if is_past else f"→ SOFR {current_rate:.4f}%"
                lines.append(f"{m.strftime('%Y-%m-%d')}  {bps:+.2f} bps  {tag}")
            st.code("\n".join(lines), language=None)
        else:
            st.info("No rate changes (all holds)")


    st.markdown("<hr style='border-color:#222;margin:6px 0;'>", unsafe_allow_html=True)

    if st.button("➕ ADD CASE", type="primary", key="add_case_btn"):
        if not case_name.strip():
            st.error("Enter a case name")
        elif case_name in [c["name"] for c in cm.cases]:
            st.error(f"'{case_name}' already exists")
        else:
            sofr = st.session_state.get("base_sofr_input", 3.64)
            effr = st.session_state.get("base_effr_input", 3.64)
            cm.add_case(name=case_name, base_effr=effr, base_sofr=sofr, year_configs=year_configs)
            st.success(f"✅ '{case_name}' added ({len(cm.cases)} total)")
            st.rerun()


# ── Bulk Case Generator ───────────────────────────────────────────────────────

MAX_BULK_CASES = 5000

# ── Correlated Cascade — Historical Spillover Profiles ────────────────────────
# Coefficients are: Y+1, Y+2, Y+3, Y+4.
# Example: if anchor year gets -100bp and coeff for Y+1 = 0.8, then Y+1 gets -80bp.
# Derived from Fed rate cycle analysis 2015-2025.
CASCADE_PROFILES = {
    "Momentum": {
        "description": "Cuts/hikes continue in the same direction, fading gradually. "
                       "Based on 2015-2018 hiking cycle & 2024-2025 easing.",
        "coeffs": [0.80, 0.50, 0.20, 0.00],
        "icon": "🚀",
    },
    "Front-Loaded": {
        "description": "Most of the action is in the anchor year, little follow-through. "
                       "Based on 2019 insurance cuts (quick adjustment, then hold).",
        "coeffs": [0.40, 0.15, 0.00, 0.00],
        "icon": "⚡",
    },
    "Mean-Revert": {
        "description": "Outer years partially reverse the anchor move. "
                       "Based on 2018 peak → 2019 reversal pattern.",
        "coeffs": [0.50, 0.10, -0.20, -0.15],
        "icon": "🔄",
    },
    "Shock + Fade": {
        "description": "Y+1 amplifies the anchor (panic/crisis), then fades & reverses. "
                       "Based on 2020 COVID response (emergency cuts → slow recovery).",
        "coeffs": [1.30, 0.25, -0.10, -0.10],
        "icon": "💥",
    },
    "Gradual Norm.": {
        "description": "Slow, steady continuation that tapers gently. "
                       "Based on 2015-2017 post-GFC normalization.",
        "coeffs": [0.60, 0.40, 0.25, 0.10],
        "icon": "📐",
    },
    "Zig-Zag Cycle": {
        "description": "Anchor year cuts → next year hikes → then cuts again. "
                       "Alternating direction. Based on stop-start tightening cycles.",
        "coeffs": [-0.50, 0.30, -0.20, 0.10],
        "icon": "📈",
    },
    "Overshoot+Correct": {
        "description": "Y+1 overshoots in same direction, then hard reversal in Y+2/Y+3. "
                       "Based on 2020-2022 pattern (deep cuts → aggressive hikes).",
        "coeffs": [1.20, -0.60, -0.30, 0.10],
        "icon": "⚖️",
    },
}


def _bps_range(bmin: float, bmax: float, step: float) -> list[float]:
    """Inclusive bps range, sorted low→high. Returns [bmin] if step <= 0."""
    if step <= 0:
        return [round(bmin, 4)]
    lo, hi = (bmin, bmax) if bmin <= bmax else (bmax, bmin)
    n = int(round((hi - lo) / step)) + 1
    vals = [round(lo + i * step, 4) for i in range(n)]
    return [v for v in vals if v <= hi + 1e-9]


def _formula_short(name: str) -> str:
    """Compact tag for use in case names: 'Front-Loaded' → 'FL'."""
    if not name:
        return "U"
    parts = name.replace("-", " ").replace("_", " ").split()
    short = "".join(p[0].upper() for p in parts)[:3]
    return short or name[:2].upper()


def _year_unique_options(cuts: list[float], formulas: list[str]) -> list[tuple[float, str]]:
    """Cartesian (cut × formula) with 0-cut de-duplicated (formula irrelevant)."""
    opts: list[tuple[float, str]] = []
    seen_zero = False
    for c in cuts:
        if c == 0:
            if not seen_zero and formulas:
                opts.append((0.0, formulas[0]))
                seen_zero = True
        else:
            for f in formulas:
                opts.append((c, f))
    return opts


def _spec_from_year_configs(
    seq: int,
    prefix: str,
    year_configs: dict,
    base_sofr: float,
    base_effr: float,
) -> dict:
    """Build a single case spec dict with a descriptive name."""
    tag_parts = []
    for year_str, cfg in year_configs.items():
        cut = cfg.get("annual_cut", 0.0)
        if cut != 0:
            tag_parts.append(f"{year_str[-2:]}:{int(round(cut)):+d}{_formula_short(cfg.get('formula_name', ''))}")
    suffix = "_".join(tag_parts) if tag_parts else "ALL_HOLD"
    return {
        "name":         f"{prefix}_{seq:04d} [{suffix}]",
        "base_effr":    base_effr,
        "base_sofr":    base_sofr,
        "year_configs": year_configs,
    }


def _build_bulk_specs(
    prefix: str,
    per_year: dict[str, dict],
    base_sofr: float,
    base_effr: float,
    mode: str = "cartesian",
    smart_filter: bool = True,
) -> list[dict]:
    """
    Two generation modes:

    - "cartesian": every combination of (cut × formula) across ALL years.
        Total = N1 × N2 × … × Nk  (multiplicative — explodes fast).

    - "additive":  vary one year at a time; all OTHER years held at 0 cuts.
        Total = N1 + N2 + … + Nk  (one case per year-variant; isolates each
        year's impact from the others). One extra "ALL_HOLD" baseline added.

    Both treat 0-cut as a single option per year (formula irrelevant when cut=0).
    """
    import itertools

    year_opts: list[tuple[str, list[tuple[float, str]]]] = []
    for year_str, cfg in per_year.items():
        opts = _year_unique_options(cfg["cuts"], cfg["formulas"])
        if not opts:
            opts = [(0.0, "Uniform")]
        year_opts.append((year_str, opts))

    specs: list[dict] = []
    seq = 0

    if mode == "additive":
        # One baseline (all years 0) + per-year, per-(cut, formula) variants
        # where the varying year is at the chosen (cut, formula) and every
        # other year is held at 0 (with that year's first formula as a stub).
        baseline = {
            ys: {"mode": "annual", "annual_cut": 0.0,
                 "formula_name": opts[0][1] if opts else "Uniform"}
            for ys, opts in year_opts
        }
        seq += 1
        specs.append(_spec_from_year_configs(seq, prefix, baseline, base_sofr, base_effr))

        for vary_year, vary_opts in year_opts:
            for (cut_bps, fml) in vary_opts:
                if cut_bps == 0:
                    continue  # already covered by baseline
                
                if smart_filter:
                    f_name = fml.lower()
                    if cut_bps < 0 and "hike" in f_name and "cut" not in f_name:
                        continue
                    if cut_bps > 0 and "cut" in f_name and "hike" not in f_name:
                        continue

                year_configs = {
                    ys: dict(baseline[ys])  # copy each year as 0-cut stub
                    for ys, _ in year_opts
                }
                year_configs[vary_year] = {
                    "mode": "annual",
                    "annual_cut": float(cut_bps),
                    "formula_name": fml,
                }
                seq += 1
                specs.append(_spec_from_year_configs(
                    seq, prefix, year_configs, base_sofr, base_effr,
                ))
        return specs

    # ── default: cartesian ───────────────────────────────────────────────
    for combo in itertools.product(*[o for _, o in year_opts]):
        year_configs = {}
        valid_combo = True
        for (year_str, _), (cut_bps, fml) in zip(year_opts, combo):
            if smart_filter:
                f_name = fml.lower()
                if cut_bps < 0 and "hike" in f_name and "cut" not in f_name:
                    valid_combo = False
                    break
                if cut_bps > 0 and "cut" in f_name and "hike" not in f_name:
                    valid_combo = False
                    break

            year_configs[year_str] = {
                "mode":         "annual",
                "annual_cut":   float(cut_bps),
                "formula_name": fml,
            }
        if valid_combo:
            seq += 1
            specs.append(_spec_from_year_configs(seq, prefix, year_configs, base_sofr, base_effr))
    return specs


def _build_cascade_specs(
    prefix: str,
    anchor_year: str,
    anchor_cuts: list[float],
    coeffs: list[float],
    year_formulas: dict[str, list[str]],
    offsets: dict[str, float],
    base_sofr: float,
    base_effr: float,
    smart_filter: bool = True,
) -> list[dict]:
    """
    Correlated Cascade: sweep anchor year from min→max, propagate to other
    years via spillover coefficients.

    coeffs:        [Y+1, Y+2, Y+3, Y+4] — multiplier of anchor cut.
                   Negative = opposite direction (cuts become hikes).
    year_formulas: {year_str: [formula_names]} — per-year formula list.
    offsets:       {year_str: fixed_bps} — added AFTER cascade multiplication.
    """
    from itertools import product as iterproduct

    all_years = sorted(str(y) for y in _years())
    anchor_idx = all_years.index(anchor_year)

    # Map each non-anchor year to its coefficient
    year_coeff_map: dict[str, float] = {}
    for i, ys in enumerate(all_years):
        if ys == anchor_year:
            continue
        distance = abs(i - anchor_idx)
        ci = distance - 1
        year_coeff_map[ys] = coeffs[ci] if ci < len(coeffs) else 0.0

    # Build formula combos: Cartesian product of per-year formula lists
    fml_lists = [year_formulas.get(ys, ["Uniform"]) for ys in all_years]
    fml_combos = list(iterproduct(*fml_lists))

    specs: list[dict] = []
    seq = 0
    for anchor_bps in anchor_cuts:
        for fml_combo in fml_combos:
            year_configs = {}
            valid_combo = True
            for idx, ys in enumerate(all_years):
                if ys == anchor_year:
                    cut = float(anchor_bps)
                else:
                    c = year_coeff_map.get(ys, 0.0)
                    cut = round(float(anchor_bps) * c + offsets.get(ys, 0.0), 2)
                
                if smart_filter:
                    f_name = fml_combo[idx].lower()
                    if cut < 0 and "hike" in f_name and "cut" not in f_name:
                        valid_combo = False
                        break
                    if cut > 0 and "cut" in f_name and "hike" not in f_name:
                        valid_combo = False
                        break

                year_configs[ys] = {
                    "mode": "annual",
                    "annual_cut": cut,
                    "formula_name": fml_combo[idx],
                }
            if valid_combo:
                seq += 1
                specs.append(_spec_from_year_configs(seq, prefix, year_configs, base_sofr, base_effr))
    return specs



def render_bulk_generator(cm) -> None:
    """Bulk case generator with three modes: cartesian, additive, or correlated cascade."""
    with st.expander("🎲 BULK CASE GENERATOR", expanded=False):
        st.markdown(
            "<small style='color:#888'>"
            "<b style='color:#FFB347;'>How it works:</b> for each year you set a "
            "<b>cut range</b> (min/max/step in bps) and pick which "
            "<b>formulas</b> to permute. Pick a mode below — that decides whether "
            "year-variants <b>multiply</b> together or are generated <b>independently</b>."
            "</small>",
            unsafe_allow_html=True,
        )

        prefix = st.text_input(
            "Naming prefix", value="Bulk", key="bulk_prefix",
            help="Cases are named '{prefix}_NNNN [26:-15U_27:-25FL ...]'.",
        )

        mode_label = st.radio(
            "Generation Mode",
            options=[
                "Cartesian (multiply across years)",
                "Additive (one year at a time)",
                "Correlated Cascade (anchor + spillover)",
            ],
            key="bulk_gen_mode",
            horizontal=False,
            help=(
                "Cartesian: every combination of every year.\n"
                "Additive: vary one year, hold others at 0.\n"
                "Cascade: sweep one anchor year, other years follow via "
                "historically-derived spillover coefficients."
            ),
        )
        if mode_label.startswith("Cartesian"):
            gen_mode = "cartesian"
        elif mode_label.startswith("Additive"):
            gen_mode = "additive"
        else:
            gen_mode = "cascade"

        _mode_blurbs = {
            "cartesian": (
                "<small style='color:#FFB347;'>"
                "✱ Cartesian: <b>N₂₀₂₆ × N₂₀₂₇ × N₂₀₂₈ × …</b> — "
                "every combo of every year. Grows fast.</small>"
            ),
            "additive": (
                "<small style='color:#00FF41;'>"
                "✱ Additive: <b>N₂₀₂₆ + N₂₀₂₇ + N₂₀₂₈ + …</b> + 1 baseline — "
                "for each year-variant, all other years are held at 0.</small>"
            ),
            "cascade": (
                "<small style='color:#00B4D8;'>"
                "✱ Cascade: sweep an <b>anchor year</b>'s cuts, other years react "
                "via spillover coefficients derived from <b>10 years of Fed history</b> "
                "(2015-2025). All 5 years move together coherently.</small>"
            ),
        }
        st.markdown(_mode_blurbs[gen_mode], unsafe_allow_html=True)

        formula_names = cm.get_formula_names()
        if not formula_names:
            st.warning("No formulas defined — add some in the Formula Builder first.")
            return

        # ==================================================================
        # CASCADE UI
        # ==================================================================
        if gen_mode == "cascade":
            st.markdown(
                "<div style='color:#FF8C00;font-size:11px;letter-spacing:1px;"
                "margin:10px 0 4px 0;'>CORRELATED CASCADE SETTINGS</div>"
                "<small style='color:#666'>Sweep one anchor year. Other years "
                "follow via spillover coefficients (negative = opposite direction)."
                "</small>",
                unsafe_allow_html=True,
            )
            years_list = _years()
            all_ys = sorted(str(y) for y in years_list)

            if "custom_profiles" not in st.session_state:
                st.session_state.custom_profiles = {}
            if "deleted_profiles" not in st.session_state:
                st.session_state.deleted_profiles = []
                
            combined_profiles = {k: v for k, v in CASCADE_PROFILES.items() if k not in st.session_state.deleted_profiles}
            combined_profiles.update(st.session_state.custom_profiles)

            def _apply_profile():
                prof = st.session_state.casc_profile
                anch = str(st.session_state.casc_anchor)
                all_y = sorted(str(y) for y in _years())
                anch_idx = all_y.index(anch)
                if prof in combined_profiles:
                    cfs = combined_profiles[prof]["coeffs"]
                    for ys in all_y:
                        if ys != anch:
                            ci = abs(all_y.index(ys) - anch_idx) - 1
                            val = float(cfs[ci]) if ci < len(cfs) else 0.0
                            st.session_state[f"casc_c_{ys}"] = val
            
            # Init keys to avoid error on first run
            if "casc_anchor" not in st.session_state:
                st.session_state.casc_anchor = years_list[0]
            if "casc_profile" not in st.session_state:
                st.session_state.casc_profile = "Momentum"
                _apply_profile()

            anchor_year = st.selectbox(
                "Anchor Year", years_list, key="casc_anchor", on_change=_apply_profile
            )
            anchor_str = str(anchor_year)
            anch_i = all_ys.index(anchor_str)

            cr1, cr2, cr3 = st.columns(3)
            with cr1:
                casc_min = st.number_input(
                    "Anchor Min bps", value=-100.0, step=12.5,
                    format="%.1f", key="casc_min",
                )
            with cr2:
                casc_max = st.number_input(
                    "Anchor Max bps", value=25.0, step=12.5,
                    format="%.1f", key="casc_max",
                )
            with cr3:
                casc_step = st.number_input(
                    "Step", value=12.5, step=2.5, format="%.1f",
                    min_value=0.5, key="casc_step",
                )
            anchor_cuts = _bps_range(casc_min, casc_max, casc_step)

            # Profile picker
            st.markdown(
                "<div style='color:#00B4D8;font-size:11px;letter-spacing:1px;"
                "font-weight:700;margin:12px 0 4px 0;'>"
                "📊 SPILLOVER PROFILE</div>",
                unsafe_allow_html=True,
            )
            profile_names = list(combined_profiles.keys()) + ["Custom"]
            
            if "_pending_casc_profile" in st.session_state:
                st.session_state.casc_profile = st.session_state._pending_casc_profile
                del st.session_state._pending_casc_profile
                
            profile_sel = st.selectbox(
                "Profile", profile_names, key="casc_profile", on_change=_apply_profile,
                format_func=lambda n: (
                    f"{combined_profiles[n].get('icon', '📌')} {n}"
                    if n in combined_profiles
                    else "✏️ Custom"
                ),
            )
            if profile_sel != "Custom":
                prof = combined_profiles.get(profile_sel)
                if not prof:
                    prof = {"description": "Profile not found.", "coeffs": [0.0, 0.0, 0.0, 0.0]}
                base_coeffs = prof["coeffs"][:]
                st.markdown(
                    f"<small style='color:#888;'>{prof['description']}</small>",
                    unsafe_allow_html=True,
                )
            else:
                base_coeffs = [0.5, 0.2, 0.0, 0.0]

            # Per-year coefficients with actual year labels
            st.markdown(
                "<div style='color:#FFB347;font-size:10px;letter-spacing:1px;"
                "margin:10px 0 2px 0;'>SPILLOVER COEFFICIENTS PER YEAR "
                "<span style='color:#555;'>(negative = opposite direction)</span></div>",
                unsafe_allow_html=True,
            )
            other_years = [ys for ys in all_ys if ys != anchor_str]
            coeffs = base_coeffs[:]
            coeff_cols = st.columns(len(other_years))
            for ic, ys in enumerate(other_years):
                dist = abs(all_ys.index(ys) - anch_i)
                ci = dist - 1
                default_c = base_coeffs[ci] if ci < len(base_coeffs) else 0.0
                if f"casc_c_{ys}" not in st.session_state:
                    st.session_state[f"casc_c_{ys}"] = float(default_c)

                with coeff_cols[ic]:
                    val = st.number_input(
                        f"{ys}", step=0.05,
                        min_value=-2.0, max_value=2.0, format="%.2f",
                        key=f"casc_c_{ys}",
                    )
                    if ci < len(coeffs):
                        coeffs[ci] = val
            
            with st.expander("💾 Manage Current Profile (Save / Update / Delete)", expanded=False):
                st.markdown("<small style='color:#888;'>Save your current coefficients as a new profile, or manage existing profiles.</small>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    new_prof_name = st.text_input("Profile Name", placeholder="e.g. Bear Flattening", label_visibility="collapsed", key="new_prof_name_input")
                with c2:
                    if st.button("Save as New", use_container_width=True, key="save_prof_btn"):
                        if new_prof_name and new_prof_name not in combined_profiles:
                            st.session_state.custom_profiles[new_prof_name] = {
                                "description": "Custom user profile.",
                                "coeffs": coeffs[:],
                                "icon": "📌"
                            }
                            st.session_state._pending_casc_profile = new_prof_name
                            st.rerun()
                with c3:
                    is_deletable = profile_sel != "Custom"
                    if st.button("Delete Current", use_container_width=True, disabled=not is_deletable, key="del_prof_btn"):
                        if profile_sel in st.session_state.custom_profiles:
                            del st.session_state.custom_profiles[profile_sel]
                        elif profile_sel in CASCADE_PROFILES:
                            st.session_state.deleted_profiles.append(profile_sel)
                        # Calculate fallback profile dynamically
                        valid_builtins = [k for k in CASCADE_PROFILES.keys() if k not in st.session_state.deleted_profiles]
                        if valid_builtins:
                            fallback = valid_builtins[0]
                        elif st.session_state.custom_profiles:
                            fallback = list(st.session_state.custom_profiles.keys())[0]
                        else:
                            fallback = "Custom"
                            
                        st.session_state._pending_casc_profile = fallback
                        st.rerun()
                
                is_custom = profile_sel in st.session_state.custom_profiles
                if is_custom:
                    if st.button(f"Update '{profile_sel}' with current inputs", use_container_width=True):
                        st.session_state.custom_profiles[profile_sel]["coeffs"] = coeffs[:]
                        st.success("Profile updated!")
                        st.rerun()
                elif st.session_state.deleted_profiles:
                    if st.button("🔄 Restore Deleted Built-in Profiles", use_container_width=True):
                        st.session_state.deleted_profiles = []
                        st.rerun()

            with st.expander("📐 Calculate Profile from Sample Rates", expanded=False):
                st.markdown(
                    "<small style='color:#888;'>Enter the absolute bps cuts/hikes you expect for each year. "
                    "The tool will automatically calculate the relative spillover coefficients based on your "
                    f"selected Anchor Year (<b>{anchor_str}</b>).</small>", 
                    unsafe_allow_html=True
                )
                samp_cols = st.columns(len(all_ys))
                samp_vals = {}
                for ic, ys in enumerate(all_ys):
                    with samp_cols[ic]:
                        dist_pre = abs(all_ys.index(ys) - anch_i)
                        ci_pre = dist_pre - 1
                        def_c = -100.0 if ys == anchor_str else round(-100.0 * (coeffs[ci_pre] if ci_pre < len(coeffs) else 0.0), 2)
                        samp_vals[ys] = st.number_input(ys, value=def_c, step=12.5, format="%.1f", key=f"samp_calc_{ys}")
                
                cc1, cc2 = st.columns([3, 1])
                with cc1:
                    calc_name = st.text_input("New Profile Name", placeholder="e.g. Calculated Scenario", label_visibility="collapsed", key="calc_name_input")
                with cc2:
                    if st.button("Calculate & Save", use_container_width=True, key="calc_save_btn"):
                        if calc_name and calc_name not in combined_profiles:
                            anch_val = samp_vals[anchor_str]
                            if anch_val == 0:
                                st.error("Anchor year must be non-zero to calculate spillover ratios.")
                            else:
                                new_cfs = [0.0, 0.0, 0.0, 0.0]
                                counts = [0, 0, 0, 0]
                                for ys in all_ys:
                                    if ys != anchor_str:
                                        dist = abs(all_ys.index(ys) - anch_i)
                                        ci = dist - 1
                                        if ci < len(new_cfs):
                                            coeff = samp_vals[ys] / anch_val
                                            new_cfs[ci] += coeff
                                            counts[ci] += 1
                                
                                for i in range(4):
                                    if counts[i] > 0:
                                        new_cfs[i] = round(new_cfs[i] / counts[i], 2)
                                
                                st.session_state.custom_profiles[calc_name] = {
                                    "description": f"Auto-calculated profile anchored to {anchor_str}.",
                                    "coeffs": new_cfs,
                                    "icon": "📐"
                                }
                                st.session_state._pending_casc_profile = calc_name
                                st.rerun()

            # Per-year formula selection (multi-select)
            st.markdown(
                "<div style='color:#4fc3f7;font-size:10px;letter-spacing:1px;"
                "font-weight:700;margin:10px 0 2px 0;'>"
                "📐 FORMULAS PER YEAR "
                "<span style='color:#555;font-weight:400;'>"
                "(pick multiple — cases multiply)</span></div>",
                unsafe_allow_html=True,
            )
            casc_year_formulas: dict[str, list[str]] = {}
            default_fml = ["Uniform"] if "Uniform" in formula_names else formula_names[:1]
            fml_cols = st.columns(len(all_ys))
            for ic, ys in enumerate(all_ys):
                with fml_cols[ic]:
                    f_sel = st.multiselect(
                        ys, formula_names, default=default_fml,
                        key=f"casc_fml_{ys}",
                    )
                    casc_year_formulas[ys] = f_sel if f_sel else default_fml

            # Per-year offsets
            with st.expander("🔧 Per-year offsets (optional bias)", expanded=False):
                st.markdown(
                    "<small style='color:#666;'>Fixed bps bias added after cascade. "
                    "E.g. +10bp in 2029 for inflation persistence.</small>",
                    unsafe_allow_html=True,
                )
                casc_offsets: dict[str, float] = {}
                off_cols = st.columns(len(years_list))
                for ic, y in enumerate(years_list):
                    with off_cols[ic]:
                        ov = st.number_input(
                            str(y), value=0.0, step=5.0, format="%.1f",
                            key=f"casc_off_{y}",
                        )
                        if ov != 0:
                            casc_offsets[str(y)] = ov

            # Total: anchor steps × formula combos
            fml_combo_count = 1
            for ys in all_ys:
                fml_combo_count *= len(casc_year_formulas.get(ys, ["Uniform"]))
            total = len(anchor_cuts) * fml_combo_count
            if fml_combo_count > 1:
                math_str = f"{len(anchor_cuts)} steps × {fml_combo_count} formula combos = {total:,}"
            else:
                math_str = f"{total} anchor steps"

            # Live Sample Preview
            st.markdown(
                "<div style='color:#00FF41;font-size:11px;letter-spacing:1px;"
                "font-weight:700;margin:16px 0 4px 0;'>LIVE SAMPLES (Based on your Anchor Range)</div>",
                unsafe_allow_html=True,
            )
            sample_anchors = anchor_cuts[:3] if anchor_cuts else [-100.0, -50.0, 0.0]
            for s_anch in sample_anchors:
                sample_cuts = []
                for ys in all_ys:
                    if ys == anchor_str:
                        c = float(s_anch)
                    else:
                        dist = abs(all_ys.index(ys) - anch_i)
                        ci = dist - 1
                        coeff = coeffs[ci] if ci < len(coeffs) else 0.0
                        c = round(float(s_anch) * coeff + casc_offsets.get(ys, 0.0), 2)
                    
                    color = "#00FF41" if c < 0 else ("#FF3131" if c > 0 else "#888")
                    sample_cuts.append(
                        f"<span style='color:#C0C0C0;'>{ys}:</span> "
                        f"<span style='color:{color};font-weight:700;'>{c:+.1f}bp</span>"
                    )
                
                st.markdown(
                    f"<div style='background:#111;border:1px solid #333;padding:4px 8px;border-radius:4px;font-size:12px;margin-bottom:4px;'>"
                    f"<span style='color:#FF8C00;font-size:11px;width:95px;display:inline-block;'>"
                    f"Anchor <b style='color:#fff;'>{s_anch:+.1f}</b></span> │ "
                    f"{' &nbsp;│&nbsp; '.join(sample_cuts)}</div>",
                    unsafe_allow_html=True,
                )

        # ==================================================================
        # CARTESIAN / ADDITIVE UI  (original)
        # ==================================================================
        else:
            st.markdown(
                "<div style='color:#FF8C00;font-size:11px;letter-spacing:1px;"
                "margin:10px 0 4px 0;'>PER-YEAR RANGES &amp; FORMULAS</div>"
                "<small style='color:#666'>Negative bps = cut. Uncheck a year to "
                "hold it at 0.</small>",
                unsafe_allow_html=True,
            )
            per_year: dict[str, dict] = {}
            for y in _years():
                year_str = str(y)
                hc1, hc2 = st.columns([3, 1])
                with hc1:
                    st.markdown(
                        f"<div style='color:#FF8C00;font-size:10px;font-weight:600;"
                        f"border-top:1px solid #1a1a1a;padding-top:6px;margin-top:6px;'>"
                        f"📅 {y}</div>",
                        unsafe_allow_html=True,
                    )
                with hc2:
                    enabled = st.checkbox(
                        "Vary", value=(y in (2026, 2027)),
                        key=f"bulk_enable_{y}",
                    )
                if not enabled:
                    per_year[year_str] = {"cuts": [0.0], "formulas": [formula_names[0]]}
                    st.markdown(
                        "<small style='color:#555;margin-left:6px;'>held at 0 bps</small>",
                        unsafe_allow_html=True,
                    )
                    continue
                r1, r2, r3, r4 = st.columns(4)
                with r1:
                    bmin = st.number_input(
                        "Min bps", value=-30.0, step=2.5, format="%.1f",
                        key=f"bulk_min_{y}",
                    )
                with r2:
                    bmax = st.number_input(
                        "Max bps", value=0.0, step=2.5, format="%.1f",
                        key=f"bulk_max_{y}",
                    )
                with r3:
                    step = st.number_input(
                        "Step", value=5.0, step=0.5, format="%.1f",
                        min_value=0.5, key=f"bulk_step_{y}",
                    )
                with r4:
                    cuts = _bps_range(bmin, bmax, step)
                    st.markdown(
                        f"<div style='color:#FFB347;font-size:11px;padding-top:26px;'>"
                        f"{len(cuts)} cut levels</div>",
                        unsafe_allow_html=True,
                    )
                default_fml = ["Uniform"] if "Uniform" in formula_names else formula_names[:1]
                st.markdown(
                    f"<div style='color:#4fc3f7;font-size:10px;letter-spacing:1px;"
                    f"font-weight:700;margin:6px 0 -4px 0;'>"
                    f"📐 FORMULAS TO PERMUTE FOR {y} "
                    f"<span style='color:#888;font-weight:400;'>"
                    f"({len(formula_names)} available — pick any subset)</span></div>",
                    unsafe_allow_html=True,
                )
                fmls = st.multiselect(
                    f"Formulas to permute · {y}",
                    options=formula_names,
                    default=default_fml,
                    key=f"bulk_fml_{y}",
                    label_visibility="collapsed",
                    placeholder=f"Pick formulas to combine with the cut range for {y}…",
                )
                if not fmls:
                    fmls = default_fml
                n_unique = len(_year_unique_options(cuts, fmls))
                st.markdown(
                    f"<small style='color:#888;'>"
                    f"{len(cuts)} cuts × {len(fmls)} formulas = "
                    f"<b style='color:#FFB347;'>{n_unique}</b> unique year-variants"
                    f"{'  (0-cut de-duplicated)' if 0 in cuts and len(fmls) > 1 else ''}"
                    f"</small>",
                    unsafe_allow_html=True,
                )
                per_year[year_str] = {"cuts": cuts, "formulas": fmls}

            # Total estimate
            per_year_counts = [
                max(1, len(_year_unique_options(cfg["cuts"], cfg["formulas"])))
                for cfg in per_year.values()
            ]
            if gen_mode == "cartesian":
                total = 1
                for n in per_year_counts:
                    total *= n
                math_str = " × ".join(str(n) for n in per_year_counts) + f" = {total:,}"
            else:
                non_zero_per_year = []
                for cfg in per_year.values():
                    opts = _year_unique_options(cfg["cuts"], cfg["formulas"])
                    non_zero_per_year.append(sum(1 for c, _ in opts if c != 0))
                total = sum(non_zero_per_year) + 1
                math_str = " + ".join(str(n) for n in non_zero_per_year) + f" + 1 = {total:,}"

        # ==================================================================
        # SHARED: total display + buttons
        # ==================================================================
        if total > MAX_BULK_CASES:
            color, warn = "#FF3131", f" ⚠ EXCEEDS LIMIT ({MAX_BULK_CASES:,})"
        elif total > 1000:
            color, warn = "#FFB347", " (large batch)"
        else:
            color, warn = "#00FF41", ""

        _sym = {"cartesian": "∏", "additive": "Σ", "cascade": "⟿"}[gen_mode]
        st.markdown(
            f"<div style='color:#888;font-size:11px;margin-top:6px;'>"
            f"<span style='color:#4fc3f7;'>{_sym}</span> "
            f"<span style='font-family:monospace;color:#FFB347;'>{math_str}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<hr style='border-color:#222;margin:10px 0;'>", unsafe_allow_html=True)
        smart_filter = st.checkbox(
            "🧠 Smart Formula Filtering (Recommended)",
            value=True,
            help="Automatically skips combinations where a formula named 'Hike' is applied to a cut, or 'Cut' is applied to a hike."
        )

        st.markdown(
            f"<div style='border-top:1px solid #333;padding-top:8px;margin-top:10px;'>"
            f"<span style='color:#888;font-size:11px;letter-spacing:1px;'>"
            f"ESTIMATED TOTAL CASES (pre-filter): </span>"
            f"<span style='color:{color};font-size:16px;font-weight:700;'>{total:,}</span>"
            f"<span style='color:{color};font-size:10px;'>{warn}</span></div>",
            unsafe_allow_html=True,
        )

        cb1, cb2 = st.columns([1, 1])
        with cb1:
            preview = st.button(
                "👁 PREVIEW SAMPLE", key="bulk_preview_btn",
                help="Show the first 8 case names without creating them.",
            )
        with cb2:
            generate = st.button(
                "🚀 GENERATE CASES", type="primary", key="bulk_generate_btn",
                disabled=(total > MAX_BULK_CASES or total == 0),
            )

        sofr = st.session_state.get("base_sofr", 3.64)
        effr = st.session_state.get("base_effr", 3.64)

        if preview or generate:
            if gen_mode == "cascade":
                specs = _build_cascade_specs(
                    prefix, str(anchor_year), anchor_cuts, coeffs,
                    casc_year_formulas, casc_offsets, sofr, effr,
                    smart_filter=smart_filter,
                )
            else:
                specs = _build_bulk_specs(
                    prefix, per_year, sofr, effr, gen_mode, smart_filter=smart_filter
                )

            if preview:
                sample_n = min(8, len(specs))
                st.code(
                    "\n".join(s["name"] for s in specs[:sample_n]) +
                    (f"\n... ({len(specs) - sample_n} more)" if len(specs) > sample_n else ""),
                    language=None,
                )
            if generate:
                with st.spinner(f"Building {len(specs):,} cases..."):
                    added = cm.bulk_add_cases(specs)
                st.success(f"✅ Generated {added:,} cases (total now: {len(cm.cases):,})")
                st.rerun()


# ── Case List ─────────────────────────────────────────────────────────────────

def render_case_list(cm) -> None:
    bb_section(f"CASES [{len(cm.cases)}]")

    if not cm.cases:
        st.markdown(
            "<div style='color:#444;font-size:11px;padding:8px;'>No cases yet.</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Scrollable HTML table for all cases (fast for 200+) ──────────────────
    rows_html = []
    for case in cm.cases:
        total = sum(case["meeting_cuts"].values())
        color = "#00FF41" if total < 0 else ("#FF3131" if total > 0 else "#888")
        rows_html.append(
            f"<tr>"
            f"<td style='color:#FF8C00;font-size:10px;white-space:nowrap;padding:2px 6px;'>{case['id']}</td>"
            f"<td style='color:#C0C0C0;font-size:10px;padding:2px 6px;max-width:140px;"
            f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' title='{case['name']}'>{case['name']}</td>"
            f"<td style='color:#888;font-size:9px;padding:2px 4px;'>{case['base_sofr']:.2f}%</td>"
            f"<td style='color:{color};font-size:10px;font-weight:700;padding:2px 6px;white-space:nowrap;'>{total:+.1f}bp</td>"
            f"</tr>"
        )

    table_html = (
        "<div style='max-height:280px;overflow-y:auto;border:1px solid #222;"
        "border-radius:2px;margin-bottom:6px;'>"
        "<table style='width:100%;border-collapse:collapse;'>"
        "<thead><tr>"
        "<th style='color:#FF6600;font-size:9px;letter-spacing:1px;padding:4px 6px;"
        "background:#0D0D0D;border-bottom:1px solid #333;text-align:left;position:sticky;top:0;'>ID</th>"
        "<th style='color:#FF6600;font-size:9px;letter-spacing:1px;padding:4px 6px;"
        "background:#0D0D0D;border-bottom:1px solid #333;text-align:left;position:sticky;top:0;'>NAME</th>"
        "<th style='color:#FF6600;font-size:9px;letter-spacing:1px;padding:4px 6px;"
        "background:#0D0D0D;border-bottom:1px solid #333;text-align:left;position:sticky;top:0;'>SOFR</th>"
        "<th style='color:#FF6600;font-size:9px;letter-spacing:1px;padding:4px 6px;"
        "background:#0D0D0D;border-bottom:1px solid #333;text-align:left;position:sticky;top:0;'>ΣCUT</th>"
        "</tr></thead>"
        "<tbody>" + "".join(rows_html) + "</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Per-case actions ──────────────────────────────────────────────────────
    if len(cm.cases) <= 20:
        # Inline delete/dup buttons when list is manageable
        for case in cm.cases:
            c1, c2, c3 = st.columns([5, 1, 1])
            with c1:
                st.markdown(
                    f"<span style='color:#FF8C00;font-size:9px;'>{case['id']}</span>"
                    f"<span style='color:#555;font-size:9px;'> │ {case['name'][:22]}</span>",
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button("⎘", key=f"dup_{case['id']}", help="Duplicate"):
                    cm.duplicate_case(case["id"], f"{case['name']} (copy)")
                    st.rerun()
            with c3:
                if st.button("✕", key=f"del_{case['id']}", help="Delete"):
                    cm.delete_case(case["id"])
                    st.rerun()
    else:
        # For large lists: targeted delete / duplicate by dropdown
        with st.expander("✂️ Delete / Duplicate by ID", expanded=False):
            case_ids = [c["id"] for c in cm.cases]
            pick_id = st.selectbox("Case ID", case_ids, key="case_action_pick")
            ba, bb_ = st.columns(2)
            with ba:
                if st.button("⎘ Duplicate", key="action_dup"):
                    picked = cm.get_case(pick_id)
                    if picked:
                        cm.duplicate_case(pick_id, f"{picked['name']} (copy)")
                        st.rerun()
            with bb_:
                if st.button("✕ Delete", key="action_del", type="primary"):
                    cm.delete_case(pick_id)
                    st.rerun()

    st.markdown("<hr style='border-color:#222;margin:5px 0;'>", unsafe_allow_html=True)
    if st.button("🗑️ CLEAR ALL", key="clear_all_btn"):
        cm.delete_all_cases()
        # Reset the case selector so UI refreshes fully
        if "struct_case_sel" in st.session_state:
            del st.session_state["struct_case_sel"]
        st.rerun()
