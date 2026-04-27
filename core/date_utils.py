"""
STIR Dashboard — Date Utilities
Business day calculations, IMM date lookup, contract schedule generation.
"""

from __future__ import annotations
import calendar
from datetime import date, timedelta
from functools import lru_cache
from typing import List, Tuple

import holidays

# ── US Federal Government Securities Market Calendar ─────────────────────────
def _us_holiday_set(year: int) -> set:
    """Return set of US federal holiday dates for a given year (Fed / bond market)."""
    us = holidays.UnitedStates(years=year, observed=True)
    return set(us.keys())


@lru_cache(maxsize=20)
def get_holidays(year: int) -> frozenset:
    return frozenset(_us_holiday_set(year))


def is_business_day(d: date) -> bool:
    """True if d is a US government securities market business day."""
    if d.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    if d in get_holidays(d.year):
        return False
    return True


def next_business_day(d: date) -> date:
    """Next business day strictly after d."""
    nxt = d + timedelta(days=1)
    while not is_business_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def prev_business_day(d: date) -> date:
    """Previous business day strictly before d."""
    prv = d - timedelta(days=1)
    while not is_business_day(prv):
        prv -= timedelta(days=1)
    return prv


def business_days_in_range(start: date, end: date, inclusive_end: bool = False) -> List[date]:
    """
    Return list of business days in [start, end).
    If inclusive_end=True: [start, end].
    """
    result = []
    cur = start
    limit = end if not inclusive_end else end + timedelta(1)
    while cur < limit:
        if is_business_day(cur):
            result.append(cur)
        cur += timedelta(1)
    return result


def day_weight(bday: date, next_bday: date, cap: date | None = None) -> int:
    """
    Calendar days that business day `bday`'s rate applies.
    = days from bday to next_bday (exclusive), capped at `cap` if provided.
    Handles Fri→Mon (d=3) and holiday spans automatically.
    """
    end = min(next_bday, cap) if cap else next_bday
    return (end - bday).days


# ── IMM Date Helpers ──────────────────────────────────────────────────────────
def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    Return the nth occurrence of weekday (0=Mon…6=Sun) in (year, month).
    e.g. nth_weekday_of_month(2026, 3, 2, 3) → 3rd Wednesday of March 2026.
    """
    d = date(year, month, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += timedelta(1)


def third_wednesday(year: int, month: int) -> date:
    """Return the 3rd Wednesday of the given year/month."""
    return nth_weekday_of_month(year, month, 2, 3)  # 2 = Wednesday


# ── SR3 Reference Quarter ─────────────────────────────────────────────────────
def sr3_reference_quarter(contract_year: int, contract_month: int) -> Tuple[date, date]:
    """
    For an SR3 contract with code month (3=Mar, 6=Jun, 9=Sep, 12=Dec):
      Start (inclusive) : 3rd Wednesday of contract_month
      End   (exclusive) : 3rd Wednesday of delivery month (contract_month + 3)

    The last included day = End - 1 calendar day = Tuesday before 3rd Wed.

    Returns: (start_inclusive, end_exclusive)
    """
    start = third_wednesday(contract_year, contract_month)

    # delivery month = contract_month + 3  (rolls year if needed)
    delivery_month = contract_month + 3
    delivery_year  = contract_year
    if delivery_month > 12:
        delivery_month -= 12
        delivery_year  += 1

    end = third_wednesday(delivery_year, delivery_month)
    return start, end


# ── SR1 / ZQ Delivery Month ───────────────────────────────────────────────────
def month_calendar_days(year: int, month: int) -> int:
    """Total calendar days in a given month."""
    return calendar.monthrange(year, month)[1]


# ── Contract List Generators ──────────────────────────────────────────────────
from config.constants import IMM_CODES, SR3_MONTHS


def generate_sr1_contracts(num_months: int = 18) -> List[dict]:
    """
    Generate SR1 (and ZQ) contract schedule from current month+1
    for the next `num_months` months.
    Returns list of dicts with: code, year, month, expiry_label
    """
    today = date.today()
    # start from the current month
    start_year  = today.year
    start_month = today.month

    contracts = []
    y, m = start_year, start_month
    for _ in range(num_months):
        code = f"SR1{IMM_CODES[m]}{str(y)[-2:]} ({calendar.month_abbr[m]})"
        # expiry: last business day of delivery month
        last_day = date(y, m, month_calendar_days(y, m))
        expiry = last_day if is_business_day(last_day) else prev_business_day(last_day)
        contracts.append({
            "product": "SR1",
            "code": code,
            "year": y,
            "month": m,
            "expiry": expiry,
            "label": expiry.strftime("%b %y"),
        })
        m += 1
        if m > 12:
            m = 1
            y += 1
    return contracts


def generate_zq_contracts(num_months: int = 18) -> List[dict]:
    """Same structure as SR1 but product=ZQ."""
    contracts = generate_sr1_contracts(num_months)
    for c in contracts:
        c["product"] = "ZQ"
        c["code"]    = c["code"].replace("SR1", "ZQ")
    return contracts


def generate_sr3_contracts() -> List[dict]:
    """
    Generate SR3 quarterly contracts from SR3M26 → SR3Z30.
    Each has: code, year, month, ref_start, ref_end (exclusive), expiry (= ref_end - 1 day)
    """
    from config.constants import SR3_CODES, IMM_CODES
    contracts = []
    start_year, start_month = 2026, 3   # SR3H26
    end_year,   end_month   = 2030, 12  # SR3Z30

    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        if m in SR3_MONTHS:
            ref_start, ref_end_excl = sr3_reference_quarter(y, m)
            expiry = ref_end_excl - timedelta(days=1)   # Tuesday (inclusive last day)
            code = f"SR3{IMM_CODES[m]}{str(y)[-2:]} ({calendar.month_abbr[m]})"
            contracts.append({
                "product":   "SR3",
                "code":      code,
                "year":      y,
                "month":     m,
                "ref_start": ref_start,
                "ref_end":   ref_end_excl,  # exclusive (3rd Wed of delivery month)
                "expiry":    expiry,         # inclusive last day (Tuesday)
                "label":     ref_start.strftime("%b %y"),
            })
        m += 3
        if m > 12:
            m -= 12
            y += 1
    return contracts
