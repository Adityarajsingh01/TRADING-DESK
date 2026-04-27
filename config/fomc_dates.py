"""
STIR Dashboard — FOMC Meeting Dates
Official: 2026–2027 (from Federal Reserve website)
Projected: 2028–2030 (rule-based analysis — see README)

Structure per meeting:
  decision_date  : date of FOMC statement (2nd day of the 2-day meeting)
  effective_date : next business day — when rate change takes effect
  is_sep         : True if Summary of Economic Projections published (Mar/Jun/Sep/Dec)
  is_official    : True = Fed-published | False = projected

To update when Fed publishes new dates: change is_official=True and update the dates.
"""

from datetime import date

# ── Helper ────────────────────────────────────────────────────────────────────
def _m(decision: date, is_sep: bool, is_official: bool) -> dict:
    """Build a meeting record given the decision date."""
    from core.date_utils import next_business_day
    return {
        "decision_date":  decision,
        "effective_date": next_business_day(decision),
        "is_sep":         is_sep,
        "is_official":    is_official,
    }


# ── 2026 ─────────────────────────────────────────────────────────────────────
FOMC_2026 = [
    _m(date(2026,  1, 28), is_sep=False, is_official=True),
    _m(date(2026,  3, 18), is_sep=True,  is_official=True),
    _m(date(2026,  4, 29), is_sep=False, is_official=True),
    _m(date(2026,  6, 17), is_sep=True,  is_official=True),
    _m(date(2026,  7, 29), is_sep=False, is_official=True),
    _m(date(2026,  9, 16), is_sep=True,  is_official=True),
    _m(date(2026, 10, 28), is_sep=False, is_official=True),
    _m(date(2026, 12,  9), is_sep=True,  is_official=True),
]

# ── 2027 (Official — published by Fed) ───────────────────────────────────────
FOMC_2027 = [
    _m(date(2027,  1, 27), is_sep=False, is_official=True),
    _m(date(2027,  3, 17), is_sep=True,  is_official=True),
    _m(date(2027,  4, 28), is_sep=False, is_official=True),
    _m(date(2027,  6,  9), is_sep=True,  is_official=True),
    _m(date(2027,  7, 28), is_sep=False, is_official=True),
    _m(date(2027,  9, 15), is_sep=True,  is_official=True),
    _m(date(2027, 10, 27), is_sep=False, is_official=True),
    _m(date(2027, 12,  8), is_sep=True,  is_official=True),
]

# ── 2028 (Projected) ─────────────────────────────────────────────────────────
FOMC_2028 = [
    _m(date(2028,  1, 26), is_sep=False, is_official=False),
    _m(date(2028,  3, 15), is_sep=True,  is_official=False),
    _m(date(2028,  4, 26), is_sep=False, is_official=False),
    _m(date(2028,  6, 14), is_sep=True,  is_official=False),
    _m(date(2028,  7, 26), is_sep=False, is_official=False),
    _m(date(2028,  9, 20), is_sep=True,  is_official=False),
    _m(date(2028, 10, 25), is_sep=False, is_official=False),
    _m(date(2028, 12, 13), is_sep=True,  is_official=False),
]

# ── 2029 (Projected) ─────────────────────────────────────────────────────────
FOMC_2029 = [
    _m(date(2029,  1, 31), is_sep=False, is_official=False),
    _m(date(2029,  3, 21), is_sep=True,  is_official=False),
    _m(date(2029,  5,  9), is_sep=False, is_official=False),
    _m(date(2029,  6, 20), is_sep=True,  is_official=False),
    _m(date(2029,  7, 25), is_sep=False, is_official=False),
    _m(date(2029,  9, 19), is_sep=True,  is_official=False),
    _m(date(2029, 10, 31), is_sep=False, is_official=False),
    _m(date(2029, 12, 12), is_sep=True,  is_official=False),
]

# ── 2030 (Projected) ─────────────────────────────────────────────────────────
FOMC_2030 = [
    _m(date(2030,  1, 30), is_sep=False, is_official=False),
    _m(date(2030,  3, 20), is_sep=True,  is_official=False),
    _m(date(2030,  5,  1), is_sep=False, is_official=False),
    _m(date(2030,  6, 19), is_sep=True,  is_official=False),
    _m(date(2030,  7, 31), is_sep=False, is_official=False),
    _m(date(2030,  9, 18), is_sep=True,  is_official=False),
    _m(date(2030, 10, 30), is_sep=False, is_official=False),
    _m(date(2030, 12, 11), is_sep=True,  is_official=False),
]

# ── Master list (all years) ───────────────────────────────────────────────────
ALL_FOMC_MEETINGS = (
    FOMC_2026 + FOMC_2027 + FOMC_2028 + FOMC_2029 + FOMC_2030
)

# Indexed by year for fast lookup
FOMC_BY_YEAR = {
    2026: FOMC_2026,
    2027: FOMC_2027,
    2028: FOMC_2028,
    2029: FOMC_2029,
    2030: FOMC_2030,
}

def get_meetings_in_range(start_date: date, end_date: date) -> list:
    """Return all FOMC meetings whose effective_date falls in [start_date, end_date]."""
    return [
        m for m in ALL_FOMC_MEETINGS
        if start_date <= m["effective_date"] <= end_date
    ]

def get_all_effective_dates() -> list:
    """Sorted list of all FOMC effective dates."""
    return sorted(m["effective_date"] for m in ALL_FOMC_MEETINGS)
