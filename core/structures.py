"""
STIR Dashboard — Derivative Structures Calculator
Computes spreads, butterflies, condors, deflys from outright prices.

Convention:
  Spread  : back - front         (+1 back, -1 front)
  Fly     : front - 2×mid + back (+1, -2, +1)
  Condor  : front - mid1 - mid2 + back  (+1, -1, -1, +1)
  Defly   : front - 3×m1 + 3×m2 - back (+1, -3, +3, -1)

For SR1/ZQ: gap is in months.
For SR3   : gap is in quarters.
"""

from __future__ import annotations
from typing import Dict, List, Optional
import pandas as pd


def _get_price(prices: Dict[str, float], code: str) -> Optional[float]:
    return prices.get(code, None)


# ── Spreads ───────────────────────────────────────────────────────────────────

def compute_spreads(
    contracts: List[dict],
    prices:    Dict[str, float],
    gaps:      List[int],
) -> Dict[str, Dict[str, float]]:
    result = {}
    for gap in gaps:
        label   = f"{gap}{'Q' if contracts[0]['product'] == 'SR3' else 'M'}"
        spreads = {}
        for i in range(len(contracts) - gap):
            front = contracts[i]
            back  = contracts[i + gap]
            pf    = _get_price(prices, front["code"])
            pb    = _get_price(prices, back["code"])
            if pf is not None and pb is not None:
                key = f"{back['code']}-{front['code']}"
                spreads[key] = round(pb - pf, 4)
        result[label] = spreads
    return result


# ── Butterflies ───────────────────────────────────────────────────────────────

def compute_butterflies(
    contracts: List[dict],
    prices:    Dict[str, float],
    gaps:      List[int],
) -> Dict[str, Dict[str, float]]:
    result = {}
    for gap in gaps:
        label = f"{gap}{'Q' if contracts[0]['product'] == 'SR3' else 'M'}"
        flies = {}
        for i in range(len(contracts) - 2 * gap):
            front = contracts[i]
            mid   = contracts[i + gap]
            back  = contracts[i + 2 * gap]
            pf    = _get_price(prices, front["code"])
            pm    = _get_price(prices, mid["code"])
            pb    = _get_price(prices, back["code"])
            if pf is not None and pm is not None and pb is not None:
                key  = f"{front['code']}/{mid['code']}/{back['code']}"
                val  = round(pf - 2 * pm + pb, 4)
                flies[key] = val
        result[label] = flies
    return result


# ── Condors ───────────────────────────────────────────────────────────────────

def compute_condors(
    contracts: List[dict],
    prices:    Dict[str, float],
    gaps:      List[int],
) -> Dict[str, Dict[str, float]]:
    """
    Condor = front - mid1 - mid2 + back  (+1, -1, -1, +1)
    Each leg is spaced `gap` apart.
    """
    result = {}
    for gap in gaps:
        label   = f"{gap}{'Q' if contracts[0]['product'] == 'SR3' else 'M'}"
        condors = {}
        for i in range(len(contracts) - 3 * gap):
            c0 = contracts[i]
            c1 = contracts[i + gap]
            c2 = contracts[i + 2 * gap]
            c3 = contracts[i + 3 * gap]
            p0 = _get_price(prices, c0["code"])
            p1 = _get_price(prices, c1["code"])
            p2 = _get_price(prices, c2["code"])
            p3 = _get_price(prices, c3["code"])
            if all(p is not None for p in [p0, p1, p2, p3]):
                key = f"{c0['code']}/{c1['code']}/{c2['code']}/{c3['code']}"
                condors[key] = round(p0 - p1 - p2 + p3, 4)
        result[label] = condors
    return result


# ── Deflys ────────────────────────────────────────────────────────────────────

def compute_deflys(
    contracts: List[dict],
    prices:    Dict[str, float],
    gaps:      List[int],
) -> Dict[str, Dict[str, float]]:
    """
    Defly = front - 3×m1 + 3×m2 - back  (+1, -3, +3, -1)
    """
    result = {}
    for gap in gaps:
        label  = f"{gap}{'Q' if contracts[0]['product'] == 'SR3' else 'M'}"
        deflys = {}
        for i in range(len(contracts) - 3 * gap):
            c0 = contracts[i]
            c1 = contracts[i + gap]
            c2 = contracts[i + 2 * gap]
            c3 = contracts[i + 3 * gap]
            p0 = _get_price(prices, c0["code"])
            p1 = _get_price(prices, c1["code"])
            p2 = _get_price(prices, c2["code"])
            p3 = _get_price(prices, c3["code"])
            if all(p is not None for p in [p0, p1, p2, p3]):
                key = f"{c0['code']}/{c1['code']}/{c2['code']}/{c3['code']}"
                deflys[key] = round(p0 - 3*p1 + 3*p2 - p3, 4)
        result[label] = deflys
    return result


# ── Full structure compute for one case ───────────────────────────────────────

def compute_all_structures(
    sr1_contracts: list,
    zq_contracts:  list,
    sr3_contracts: list,
    sr1_prices:    Dict[str, float],
    zq_prices:     Dict[str, float],
    sr3_prices:    Dict[str, float],
) -> dict:
    """
    Compute spreads, flies, condors, deflys for SR1, ZQ, SR3.

    Returns:
    {
      "spreads": { "SR1": {"1M":{...},"2M":{...}}, "ZQ": {...}, "SR3": {...} },
      "flies":   { "SR1": {"1M":{...}}, "ZQ": {...}, "SR3": {...} },
      "condors": { "SR1": {"1M":{...}}, "ZQ": {...}, "SR3": {...} },
      "deflys":  { "SR1": {"1M":{...}}, "ZQ": {...}, "SR3": {...} },
    }
    """
    from config.constants import (
        SR1_SPREAD_GAPS, ZQ_SPREAD_GAPS, SR3_SPREAD_GAPS,
        SR1_FLY_GAPS,    ZQ_FLY_GAPS,    SR3_FLY_GAPS,
    )

    # Condor/defly gaps: same as fly gaps (gap=1 for SR1/ZQ, [1,2] for SR3)
    SR1_CONDOR_GAPS = [1]
    ZQ_CONDOR_GAPS  = [1]
    SR3_CONDOR_GAPS = [1, 2]
    SR1_DEFLY_GAPS  = [1]
    ZQ_DEFLY_GAPS   = [1]
    SR3_DEFLY_GAPS  = [1, 2]

    return {
        "spreads": {
            "SR1": compute_spreads(sr1_contracts, sr1_prices, SR1_SPREAD_GAPS),
            "ZQ":  compute_spreads(zq_contracts,  zq_prices,  ZQ_SPREAD_GAPS),
            "SR3": compute_spreads(sr3_contracts, sr3_prices, SR3_SPREAD_GAPS),
        },
        "flies": {
            "SR1": compute_butterflies(sr1_contracts, sr1_prices, SR1_FLY_GAPS),
            "ZQ":  compute_butterflies(zq_contracts,  zq_prices,  ZQ_FLY_GAPS),
            "SR3": compute_butterflies(sr3_contracts, sr3_prices, SR3_FLY_GAPS),
        },
        "condors": {
            "SR1": compute_condors(sr1_contracts, sr1_prices, SR1_CONDOR_GAPS),
            "ZQ":  compute_condors(zq_contracts,  zq_prices,  ZQ_CONDOR_GAPS),
            "SR3": compute_condors(sr3_contracts, sr3_prices, SR3_CONDOR_GAPS),
        },
        "deflys": {
            "SR1": compute_deflys(sr1_contracts, sr1_prices, SR1_DEFLY_GAPS),
            "ZQ":  compute_deflys(zq_contracts,  zq_prices,  ZQ_DEFLY_GAPS),
            "SR3": compute_deflys(sr3_contracts, sr3_prices, SR3_DEFLY_GAPS),
        },
    }
