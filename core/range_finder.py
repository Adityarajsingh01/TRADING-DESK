"""
core/range_finder.py
─────────────────────
Range-Bound Trade Finder.

For a universe of scenario cases (each a different Fed path), this module:
  1. Computes every instrument's value (outrights + spreads + flies + condors
     + deflys) under each case → a (n_cases × n_instruments) matrix.
  2. For a chosen primary instrument P, searches integer (a, b) ratios for
     every other instrument H, minimising  range(a·P + b·H)  across cases.

The smallest residual ranges are trades that are approximately PnL-flat across
the user's full case universe — i.e. range-bound: as long as the actual Fed
path falls inside the case set, the trade's value barely moves.

Convention:
  - "Value" of an outright = its price (100 - implied rate)
  - "Value" of a spread/fly/etc. = its computed level (back-front, etc.)
  - 1 "lot" of an instrument means +1 of that combination of legs. Buying a
    fly means +1 front, -2 mid, +1 back → 1 lot of the fly contributes
    1 × (front - 2*mid + back) to the combo's value.
"""
from __future__ import annotations

from math import gcd
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

# CME contract $ multipliers per index point.
# Each leg of a structure inherits its product's multiplier; the matrix is
# stored in dollar units so hedge optimisation respects PnL economics across
# mixed-product combos (e.g. SR1 outright + SR3 fly).
MULTIPLIER = {"SR1": 4167.0, "ZQ": 4167.0, "SR3": 2500.0}


# ── Build (n_cases × n_instruments) matrix ───────────────────────────────────

def build_instrument_matrix(
    cases: list,
    sr1c:  list,
    zqc:   list,
    sr3c:  list,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Tuple[List[str], np.ndarray]:
    """
    Returns (keys, matrix):
      keys   — list of instrument labels
      matrix — float64 array, shape (n_cases, n_instruments)

    Instrument label format: "PRODUCT·TYPE·GAP·NAME"
        SR1·OUT·-·SR1Z26
        SR3·SPR·1Q·SR3M26-SR3H26
        ZQ·FLY·1M·ZQF27/ZQG27/ZQH27

    Only instruments that compute under EVERY case are kept (so the matrix has
    no NaNs). `progress(done, total)` is called once per case if given.
    """
    from core.case_manager   import build_rate_path
    from core.pricing_engine import price_sr1, price_zq, price_sr3
    from core.structures     import compute_all_structures

    n_cases = len(cases)
    if n_cases == 0:
        return [], np.zeros((0, 0))

    type_tag = {"spreads": "SPR", "flies": "FLY", "condors": "CON", "deflys": "DEF"}
    rows: List[Dict[str, float]] = []

    for ci, case in enumerate(cases):
        sofr_path, effr_path, _ = build_rate_path(
            case["base_sofr"], case["base_effr"], case.get("year_configs", {})
        )
        sr1_px = {c["code"]: price_sr1(c["year"], c["month"], sofr_path, case["base_sofr"]) for c in sr1c}
        zq_px  = {c["code"]: price_zq (c["year"], c["month"], effr_path, case["base_effr"])  for c in zqc}
        sr3_px = {c["code"]: price_sr3(c["ref_start"], c["ref_end"], sofr_path, case["base_sofr"]) for c in sr3c}

        struct = compute_all_structures(sr1c, zqc, sr3c, sr1_px, zq_px, sr3_px)

        flat: Dict[str, float] = {}
        # Outrights — scale price by product multiplier ($ per 1 lot)
        for code, px in sr1_px.items(): flat[f"SR1·OUT·-·{code}"] = px * MULTIPLIER["SR1"]
        for code, px in zq_px.items():  flat[f"ZQ·OUT·-·{code}"]  = px * MULTIPLIER["ZQ"]
        for code, px in sr3_px.items(): flat[f"SR3·OUT·-·{code}"] = px * MULTIPLIER["SR3"]
        # Structures — same multiplier applies (all legs are same product)
        for stype, by_prod in struct.items():
            tag = type_tag.get(stype, stype.upper()[:3])
            for prod, by_gap in by_prod.items():
                mult = MULTIPLIER.get(prod, 1.0)
                for gap, by_key in by_gap.items():
                    for k, v in by_key.items():
                        flat[f"{prod}·{tag}·{gap}·{k}"] = v * mult
        rows.append(flat)

        if progress is not None:
            progress(ci + 1, n_cases)

    common: set = set(rows[0].keys())
    for r in rows[1:]:
        common.intersection_update(r.keys())
    keys = sorted(common)

    matrix = np.array(
        [[r[k] for k in keys] for r in rows],
        dtype=np.float64,
    )
    return keys, matrix


# ── Per-instrument stats ─────────────────────────────────────────────────────

def per_instrument_stats(matrix: np.ndarray) -> Dict[str, np.ndarray]:
    """Per-column min / max / range / mean / std."""
    if matrix.size == 0:
        empty = np.array([])
        return {"min": empty, "max": empty, "range": empty, "mean": empty, "std": empty}
    mins = matrix.min(axis=0)
    maxs = matrix.max(axis=0)
    return {
        "min":   mins,
        "max":   maxs,
        "range": maxs - mins,
        "mean":  matrix.mean(axis=0),
        "std":   matrix.std(axis=0, ddof=0),
    }


# ── Hedge search (vectorised) ────────────────────────────────────────────────

def _coprime_ratios(max_ratio: int) -> Tuple[np.ndarray, np.ndarray]:
    """All coprime (a, b) with a in [1, R], b in [-R, R] \\ {0}."""
    aa, bb = [], []
    for a in range(1, max_ratio + 1):
        for b in range(-max_ratio, max_ratio + 1):
            if b == 0:
                continue
            if gcd(a, abs(b)) > 1:
                continue
            aa.append(a)
            bb.append(b)
    return np.array(aa, dtype=np.int32), np.array(bb, dtype=np.int32)


def find_best_hedges(
    primary_idx: int,
    matrix: np.ndarray,
    max_ratio: int = 5,
    top_k:     int = 30,
    chunk:     int = 32,
) -> List[dict]:
    """
    For column j=primary_idx, find the integer ratio (a, b) per OTHER column k
    that minimises  range( a*matrix[:,j] + b*matrix[:,k] )  across cases.

    Returns the top_k hedges sorted by ascending residual_range. Each result:
        {
            "hedge_idx":      int,    # index into original keys[]
            "a":              int,    # lots of primary  (always > 0)
            "b":              int,    # lots of hedge    (signed; sign = direction)
            "residual_range": float,
            "residual_min":   float,
            "residual_max":   float,
            "reduction_pct":  float,  # % shrink vs primary's own range
        }

    Vectorised over hedge candidates in chunks to control peak memory.
    For chunk=32, n_ratios≈40, n_cases=5000: peak ≈ 32·40·5000·8 B ≈ 50 MB.
    """
    n_cases, n_inst = matrix.shape
    if n_cases == 0 or n_inst <= 1:
        return []

    primary = matrix[:, primary_idx]
    primary_range = float(primary.max() - primary.min())
    if primary_range <= 1e-12:
        # Already flat — any non-zero hedge would only widen the range.
        return []

    a_arr, b_arr = _coprime_ratios(max_ratio)
    p_term = primary[:, None] * a_arr[None, :].astype(np.float64)   # (n_cases, n_r)

    out: List[dict] = []
    for start in range(0, n_inst, chunk):
        end = min(start + chunk, n_inst)
        H = matrix[:, start:end]                                    # (n_cases, c)

        # combo[case, ratio, hedge] = a*P + b*H
        combo = (
            p_term[:, :, None] +
            b_arr[None, :, None].astype(np.float64) * H[:, None, :]
        )
        c_min = combo.min(axis=0)                                    # (n_r, c)
        c_max = combo.max(axis=0)
        c_rng = c_max - c_min

        best_r  = c_rng.argmin(axis=0)                               # (c,)
        col_idx = np.arange(c_rng.shape[1])
        best_rng = c_rng[best_r, col_idx]
        best_min = c_min[best_r, col_idx]
        best_max = c_max[best_r, col_idx]

        for j_local, j_glob in enumerate(range(start, end)):
            if j_glob == primary_idx:
                continue
            r = best_r[j_local]
            out.append({
                "hedge_idx":      j_glob,
                "a":              int(a_arr[r]),
                "b":              int(b_arr[r]),
                "residual_range": float(best_rng[j_local]),
                "residual_min":   float(best_min[j_local]),
                "residual_max":   float(best_max[j_local]),
            })

    for r in out:
        r["reduction_pct"] = 100.0 * (1.0 - r["residual_range"] / primary_range)
    out.sort(key=lambda x: x["residual_range"])
    return out[:top_k]
