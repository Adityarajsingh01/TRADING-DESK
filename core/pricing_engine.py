"""
STIR Dashboard — Pricing Engine
Computes outright prices for SR1, ZQ, SR3 given a rate path.

Rate path format:
    {
      "sofr": {date(2026,3,19): 4.05, date(2026,6,18): 3.80, ...},
      "effr": {date(2026,3,19): 4.08, date(2026,6,18): 3.83, ...},
    }
    → Rates are step functions: on each effective_date, the rate
      changes to the new value. Between effective dates the rate is flat.

All prices: 100 - rate  (both SR1/ZQ and SR3 follow this convention).

KEY RULE: The base_sofr / base_effr inputs represent TODAY's live rate
(i.e., after all past FOMC decisions have already taken effect).
Only future FOMC meetings (effective_date > today) should shift the rate.
Past meetings that already occurred are NOT in the rate_path — the base
rate already reflects them.
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, List

from core.date_utils import (
    business_days_in_range,
    day_weight,
    month_calendar_days,
    is_business_day,
)


# ── Rate Path Helpers ─────────────────────────────────────────────────────────

def rate_on_date(d: date, rate_path: Dict[date, float], base_rate: float) -> float:
    """
    Return the applicable rate on calendar date d given a rate path.
    rate_path keys are effective_dates (the rate changes ON that date).
    Walks backwards from d to find the most recent effective_date <= d.
    
    base_rate = today's live rate (already includes all past cuts).
    rate_path = only FUTURE meeting adjustments (incremental from base_rate).
    """
    applicable = base_rate
    for eff_date, rate in sorted(rate_path.items()):
        if eff_date <= d:
            applicable = rate
        else:
            break
    return applicable


def build_daily_rate_series(
    start: date,
    end_inclusive: date,
    rate_path: Dict[date, float],
    base_rate: float,
) -> List[tuple]:
    """
    Returns list of (calendar_date, rate) for every calendar day
    in [start, end_inclusive]. Rate changes take effect on the
    effective_date (rate applies from that day forward).
    """
    series = []
    cur = start
    while cur <= end_inclusive:
        r = rate_on_date(cur, rate_path, base_rate)
        series.append((cur, r))
        cur += timedelta(days=1)
    return series


# ── SR1 Pricing ───────────────────────────────────────────────────────────────

def price_sr1(year: int, month: int,
              rate_path: Dict[date, float], base_sofr: float) -> float:
    """
    SR1 price = 100 - simple arithmetic average of daily SOFR for delivery month.

    The daily SOFR for each calendar day is the rate in effect on that day.
    Weekend/holiday SOFR = the most recent business day's fixing
    (automatically handled by rate_path step function + calendar day weighting).

    Formula:
        AvgSOFR = (1/D) × Σ (d_i × SOFR_i)
        Price   = 100 - AvgSOFR

    where D = total calendar days in month,
          d_i = calendar days business day i's rate applies (1 for Mon-Thu, 3 for Fri).

    NOTE: base_sofr is today's live SOFR. rate_path contains only FUTURE
    meeting changes (effective_date > today). Past meetings are baked into base_sofr.
    """
    D = month_calendar_days(year, month)

    # Build business days in the month
    from datetime import date as dt
    month_start = dt(year, month, 1)
    month_end   = dt(year, month, D)          # last calendar day (inclusive)

    bdays = business_days_in_range(month_start, month_end, inclusive_end=True)

    if not bdays:
        # Fallback: no business days (shouldn't happen)
        r = rate_on_date(month_start, rate_path, base_sofr)
        return round(100 - r, 4)

    weighted_sum = 0.0

    # Handle leading non-business days (month starts on weekend/holiday).
    # These days carry the previous business day's rate (= rate_on_date for day 1).
    if bdays[0] > month_start:
        leading_days = (bdays[0] - month_start).days
        r_leading    = rate_on_date(month_start, rate_path, base_sofr)
        weighted_sum += leading_days * r_leading

    for i, bday in enumerate(bdays):
        next_bday = bdays[i + 1] if i + 1 < len(bdays) else month_end + timedelta(1)
        d_i       = day_weight(bday, next_bday, cap=month_end + timedelta(1))
        r_i       = rate_on_date(bday, rate_path, base_sofr)
        weighted_sum += d_i * r_i

    avg_sofr = weighted_sum / D
    return round(100 - avg_sofr, 4)


# ── ZQ Pricing ────────────────────────────────────────────────────────────────

def price_zq(year: int, month: int,
             rate_path: Dict[date, float], base_effr: float) -> float:
    """
    ZQ price = 100 - simple arithmetic average of daily EFFR for delivery month.
    Identical formula to SR1 but uses EFFR rate path.
    
    NOTE: base_effr is today's live EFFR. rate_path contains only FUTURE
    meeting changes (effective_date > today). Past meetings are baked into base_effr.
    """
    D = month_calendar_days(year, month)
    from datetime import date as dt
    month_start = dt(year, month, 1)
    month_end   = dt(year, month, D)

    bdays = business_days_in_range(month_start, month_end, inclusive_end=True)

    if not bdays:
        r = rate_on_date(month_start, rate_path, base_effr)
        return round(100 - r, 4)

    weighted_sum = 0.0

    # Handle leading non-business days (month starts on weekend/holiday)
    if bdays[0] > month_start:
        leading_days = (bdays[0] - month_start).days
        r_leading    = rate_on_date(month_start, rate_path, base_effr)
        weighted_sum += leading_days * r_leading

    for i, bday in enumerate(bdays):
        next_bday = bdays[i + 1] if i + 1 < len(bdays) else month_end + timedelta(1)
        d_i       = day_weight(bday, next_bday, cap=month_end + timedelta(1))
        r_i       = rate_on_date(bday, rate_path, base_effr)
        weighted_sum += d_i * r_i

    avg_effr = weighted_sum / D
    return round(100 - avg_effr, 4)


# ── SR3 Pricing ───────────────────────────────────────────────────────────────

def price_sr3(ref_start: date, ref_end_excl: date,
              rate_path: Dict[date, float], base_sofr: float) -> float:
    """
    SR3 price = 100 - R

    R = [∏(1 + d_i/360 × r_i/100) - 1] × (360/D) × 100

    where:
      ref_start     : 3rd Wednesday of contract month (inclusive)
      ref_end_excl  : 3rd Wednesday of delivery month (exclusive)
      D             : total calendar days in reference quarter
      d_i           : calendar days business day i's SOFR applies
      r_i           : SOFR rate (% p.a.) for business day i

    NOTE: base_sofr is today's live SOFR. rate_path contains only FUTURE
    meeting changes (effective_date > today). Past meetings are baked into base_sofr.
    """
    D = (ref_end_excl - ref_start).days   # total calendar days in ref quarter

    # Enumerate business days in [ref_start, ref_end_excl)
    bdays = business_days_in_range(ref_start, ref_end_excl, inclusive_end=False)

    if not bdays:
        r = rate_on_date(ref_start, rate_path, base_sofr)
        R = r
        return round(100 - R, 4)

    product = 1.0

    # Handle leading non-business days (ref period starts on holiday)
    if bdays[0] > ref_start:
        leading_days = (bdays[0] - ref_start).days
        r_leading    = rate_on_date(ref_start, rate_path, base_sofr)
        product     *= (1.0 + (leading_days / 360.0) * (r_leading / 100.0))

    for i, bday in enumerate(bdays):
        next_bday = bdays[i + 1] if i + 1 < len(bdays) else ref_end_excl
        d_i       = day_weight(bday, next_bday, cap=ref_end_excl)
        r_i       = rate_on_date(bday, rate_path, base_sofr)
        product  *= (1.0 + (d_i / 360.0) * (r_i / 100.0))

    R = round((product - 1.0) * (360.0 / D) * 100.0, 4)
    return round(100.0 - R, 4)


# ── Batch Pricing ─────────────────────────────────────────────────────────────

def compute_all_prices(
    sr1_contracts: list,
    zq_contracts:  list,
    sr3_contracts: list,
    sofr_path:     Dict[date, float],
    effr_path:     Dict[date, float],
    base_sofr:     float,
    base_effr:     float,
) -> dict:
    """
    Compute all outright prices for one scenario (one rate path).

    Returns:
    {
      "SR1": {"SR1K26": 95.7083, ...},
      "ZQ":  {"ZQK26":  95.7083, ...},
      "SR3": {"SR3M26": 95.6512, ...},
    }
    """
    out = {"SR1": {}, "ZQ": {}, "SR3": {}}

    for c in sr1_contracts:
        out["SR1"][c["code"]] = price_sr1(
            c["year"], c["month"], sofr_path, base_sofr
        )

    for c in zq_contracts:
        out["ZQ"][c["code"]] = price_zq(
            c["year"], c["month"], effr_path, base_effr
        )

    for c in sr3_contracts:
        out["SR3"][c["code"]] = price_sr3(
            c["ref_start"], c["ref_end"], sofr_path, base_sofr
        )

    return out
