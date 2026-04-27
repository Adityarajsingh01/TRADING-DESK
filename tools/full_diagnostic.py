"""
Full diagnostic: capture ALL live prices, compare with pricing engine,
and test the case builder flow end-to-end.
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PYTHONIOENCODING"] = "utf-8"

from config.ls_config import (
    SERVER_URL, ADAPTER_SET, DATA_ADAPTER, FIELD_NAMES,
    TT_MAPPING, INV_TT_MAPPING,
)

# Collect ALL outright IDs (no _ in key = outright)
OUTRIGHT_CODES = [k for k in TT_MAPPING if '_' not in k and TT_MAPPING[k]]
prices = {}

try:
    from lightstreamer.client import LightstreamerClient, Subscription

    def _sf(v):
        try: return float(str(v).strip().replace(',','')) if v not in (None,'','--','N/A') else None
        except: return None

    def _norm(v):
        t = str(v or '').strip()
        if t.startswith('TT-'): t = t[3:]
        if t.endswith('.0'): t = t[:-2]
        return t

    class L:
        def onItemUpdate(self, u):
            item = u.getItemName()
            iid = str(u.getValue('InstrumentId') or '').strip()
            for cand in (item, iid):
                key = _norm(cand)
                if key in INV_TT_MAPPING:
                    code = INV_TT_MAPPING[key]
                    if '_' in code: break  # skip spreads
                    bid = _sf(u.getValue('BestBid'))
                    ask = _sf(u.getValue('BestAsk'))
                    if bid is not None and ask is not None:
                        mid = (bid + ask) / 2.0
                    else:
                        for f in ['Last','Price','Settle','PrevSettle','IndSettle']:
                            mid = _sf(u.getValue(f))
                            if mid is not None: break
                    if mid is not None:
                        mid = mid / 100.0
                        if bid is not None: bid = bid / 100.0
                        if ask is not None: ask = ask / 100.0
                        prices[code] = {'bid': bid, 'ask': ask, 'mid': mid}
                    break
        def onSubscription(self): pass
        def onUnsubscription(self): pass
        def onSubscriptionError(self, c, m): print(f"  Sub err: {c} {m}")
        def onEndOfSnapshot(self, i, p): pass
        def onClearSnapshot(self, i, p): pass
        def onItemLostUpdates(self, i, p, l): pass

    print(f"Connecting to Lightstreamer...")
    client = LightstreamerClient(SERVER_URL, ADAPTER_SET)
    client.connect()
    ids = [TT_MAPPING[c] for c in OUTRIGHT_CODES]
    sub = Subscription('MERGE', ['TT-'+i for i in ids], FIELD_NAMES)
    sub.setDataAdapter(DATA_ADAPTER)
    sub.setRequestedMaxFrequency('1')
    sub.setRequestedSnapshot('yes')
    listener = L()
    sub.addListener(listener)
    client.subscribe(sub)

    for _ in range(20):
        time.sleep(1)
        if len(prices) >= len(OUTRIGHT_CODES) * 0.8:
            break
        print(f"  ... {len(prices)}/{len(OUTRIGHT_CODES)} prices")

    client.disconnect()
    print(f"Got {len(prices)} outright prices.\n")

except Exception as e:
    print(f"LS error: {e}")

# Now compare
from core.pricing_engine import price_sr1, price_zq, price_sr3
from core.date_utils import generate_sr1_contracts, generate_zq_contracts, generate_sr3_contracts
from core.case_manager import build_rate_path, compute_meeting_cuts_for_year
from config.fomc_dates import FOMC_BY_YEAR
from datetime import date

sr1c = generate_sr1_contracts(18)
zqc  = generate_zq_contracts(18)
sr3c = generate_sr3_contracts()

BASE_SOFR = 3.64
BASE_EFFR = 3.64
empty_path = {}

def strip_label(code):
    return code.split(' (')[0] if ' (' in code else code

print("=" * 80)
print("PART 1: OUTRIGHTS - Pricing Engine (0 cuts) vs Live")
print("=" * 80)

# --- SR1 ---
print(f"\n--- SR1 (base_sofr={BASE_SOFR}%) ---")
print(f"{'Code':24s} {'Live':>10s} {'Engine':>10s} {'Diff(bp)':>10s} {'ImplRate':>10s}")
for c in sr1c:
    bare = strip_label(c['code'])
    live = prices.get(bare, {}).get('mid')
    eng = price_sr1(c['year'], c['month'], empty_path, BASE_SOFR)
    if live is not None:
        diff = (eng - live) * 100
        rate = 100 - live
        print(f"{c['code']:24s} {live:10.4f} {eng:10.4f} {diff:+10.2f} {rate:10.4f}")
    else:
        print(f"{c['code']:24s} {'--':>10s} {eng:10.4f} {'--':>10s}")

# --- ZQ ---
print(f"\n--- ZQ (base_effr={BASE_EFFR}%) ---")
print(f"{'Code':24s} {'Live':>10s} {'Engine':>10s} {'Diff(bp)':>10s} {'ImplRate':>10s}")
for c in zqc:
    bare = strip_label(c['code'])
    live = prices.get(bare, {}).get('mid')
    eng = price_zq(c['year'], c['month'], empty_path, BASE_EFFR)
    if live is not None:
        diff = (eng - live) * 100
        rate = 100 - live
        print(f"{c['code']:24s} {live:10.4f} {eng:10.4f} {diff:+10.2f} {rate:10.4f}")
    else:
        print(f"{c['code']:24s} {'--':>10s} {eng:10.4f} {'--':>10s}")

# --- SR3 ---
print(f"\n--- SR3 (base_sofr={BASE_SOFR}%) ---")
print(f"{'Code':24s} {'Live':>10s} {'Engine':>10s} {'Diff(bp)':>10s} {'ImplRate':>10s}")
for c in sr3c[:12]:  # first 12
    bare = strip_label(c['code'])
    live = prices.get(bare, {}).get('mid')
    eng = price_sr3(c['ref_start'], c['ref_end'], empty_path, BASE_SOFR)
    if live is not None:
        diff = (eng - live) * 100
        rate = 100 - live
        print(f"{c['code']:24s} {live:10.4f} {eng:10.4f} {diff:+10.2f} {rate:10.4f}")
    else:
        print(f"{c['code']:24s} {'--':>10s} {eng:10.4f} {'--':>10s}")

# PART 2: Test the case builder with per-meeting cuts
print("\n" + "=" * 80)
print("PART 2: CASE BUILDER TEST - Per Meeting mode")
print("=" * 80)

# Use the first live SR1 to back-calculate what rate the market implies
# and see if we can match it with the right base rate
today = date.today()
print(f"\nToday: {today}")
print(f"Base SOFR: {BASE_SOFR}%")

# Show all 2026 FOMC meetings and their effective dates
meetings_2026 = FOMC_BY_YEAR.get(2026, [])
print(f"\n2026 FOMC meetings:")
for i, m in enumerate(meetings_2026):
    is_past = m['effective_date'] <= today
    status = "PAST" if is_past else "FUTURE"
    print(f"  [{i}] Decision: {m['decision_date']}  Effective: {m['effective_date']}  "
          f"SEP: {m['is_sep']}  {status}")

# Test: Create a case with -25bp at Jun meeting (index 3)
print(f"\n--- Test Case: -25bp at Jun 2026 meeting ---")
year_config = {
    "mode": "per_meeting",
    "per_meeting_cuts": {}
}
for m in meetings_2026:
    eff_str = m['effective_date'].isoformat()
    # Put -25bp at Jun (decision 2026-06-17, effective 2026-06-18)
    if m['decision_date'] == date(2026, 6, 17):
        year_config["per_meeting_cuts"][eff_str] = -25.0
    else:
        year_config["per_meeting_cuts"][eff_str] = 0.0

year_configs = {"2026": year_config}
sofr_path, effr_path, meeting_cuts = build_rate_path(BASE_SOFR, BASE_EFFR, year_configs)

print(f"\nRate path (SOFR):")
for d, r in sorted(sofr_path.items()):
    print(f"  {d}: {r:.4f}%")

print(f"\nSR1 prices with -25bp Jun cut:")
print(f"{'Code':24s} {'Live':>10s} {'NoCut':>10s} {'Cut25':>10s} {'Shift(bp)':>10s}")
for c in sr1c:
    bare = strip_label(c['code'])
    live = prices.get(bare, {}).get('mid')
    no_cut = price_sr1(c['year'], c['month'], empty_path, BASE_SOFR)
    w_cut  = price_sr1(c['year'], c['month'], sofr_path, BASE_SOFR)
    shift = (w_cut - no_cut) * 100
    live_str = f"{live:.4f}" if live else "--"
    print(f"{c['code']:24s} {live_str:>10s} {no_cut:10.4f} {w_cut:10.4f} {shift:+10.2f}")

print("\n" + "=" * 80)
print("PART 3: What base_sofr gives EXACT match for SR1J26 (current month)?")
print("=" * 80)

# SR1J26 = April 2026 = current month
# With 0 cuts, price = 100 - base_sofr (approximately, adjusted for business days)
sr1j26_live = prices.get('SR1J26', {}).get('mid')
if sr1j26_live:
    implied_rate = 100 - sr1j26_live
    print(f"SR1J26 live mid: {sr1j26_live:.4f}")
    print(f"Implied avg SOFR for Apr 2026: {implied_rate:.4f}%")
    
    # The current month is partially elapsed - some days already fixed at today's rate
    # Try to find the exact base_sofr that matches
    from core.date_utils import business_days_in_range, day_weight, month_calendar_days
    D = month_calendar_days(2026, 4)
    month_start = date(2026, 4, 1)
    month_end = date(2026, 4, D)
    bdays = business_days_in_range(month_start, month_end, inclusive_end=True)
    
    elapsed_days = 0
    future_days = 0
    for i, bday in enumerate(bdays):
        from datetime import timedelta
        next_bday = bdays[i+1] if i+1 < len(bdays) else month_end + timedelta(1)
        d_i = day_weight(bday, next_bday, cap=month_end + timedelta(1))
        if bday <= today:
            elapsed_days += d_i
        else:
            future_days += d_i
    
    print(f"\nApr 2026: {D} total cal days, {elapsed_days} elapsed, {future_days} future")
    print(f"Since ALL days use base_sofr (no cuts), price = 100 - base_sofr")
    print(f"=> To match live, set base_sofr = {implied_rate:.4f}%")
else:
    print("SR1J26 live price not available")

print("\nDone.")
