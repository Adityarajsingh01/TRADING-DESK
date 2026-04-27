import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.pricing_engine import price_sr1, rate_on_date
from core.date_utils import business_days_in_range, day_weight, month_calendar_days
from datetime import date, timedelta

BASE = 3.64
empty_path = {}

# Check Aug 2026 in detail
year, month = 2026, 8
D = month_calendar_days(year, month)
month_start = date(year, month, 1)
month_end = date(year, month, D)
bdays = business_days_in_range(month_start, month_end, inclusive_end=True)

print(f"Aug 2026: {D} cal days, {len(bdays)} biz days")
print(f"Month: {month_start} to {month_end}")
print()

weighted_sum = 0.0
total_weights = 0
for i, bday in enumerate(bdays):
    next_bday = bdays[i+1] if i+1 < len(bdays) else month_end + timedelta(1)
    d_i = day_weight(bday, next_bday, cap=month_end + timedelta(1))
    r_i = rate_on_date(bday, empty_path, BASE)
    weighted_sum += d_i * r_i
    total_weights += d_i
    dow = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][bday.weekday()]
    print(f"  bday={bday} ({dow})  next={next_bday}  d_i={d_i}  rate={r_i:.4f}  cumw={weighted_sum:.4f}")

print(f"\nTotal weights: {total_weights}  (should = {D})")
print(f"Weighted sum: {weighted_sum:.6f}")
print(f"Avg rate: {weighted_sum / D:.6f}")
print(f"Price: {100 - weighted_sum / D:.4f}")
print(f"Expected: {100 - BASE:.4f}")

# Normal month (Jul 2026)
print(f"\n--- Jul 2026 ---")
price_jul = price_sr1(2026, 7, empty_path, BASE)
print(f"Price: {price_jul}  (expected: {100-BASE:.4f})")

# Sep 2026
print(f"\n--- Sep 2026 ---")
price_sep = price_sr1(2026, 9, empty_path, BASE)
print(f"Price: {price_sep}  (expected: {100-BASE:.4f})")

# Check ALL months
print(f"\n--- All months with 0 cuts ---")
for y in [2026, 2027]:
    for m in range(1, 13):
        if y == 2026 and m < 4: continue
        if y == 2027 and m > 9: continue
        p = price_sr1(y, m, empty_path, BASE)
        diff = (p - (100 - BASE)) * 100
        flag = " *** BUG" if abs(diff) > 0.01 else ""
        print(f"  {y}-{m:02d}  price={p:.4f}  diff={diff:+.2f}bp{flag}")
