"""
Diagnostic: Connect to Lightstreamer, capture a few SR1 outright prices,
then compute what the pricing engine WOULD produce with base_sofr=4.33
and 0 cuts to see if they match.
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.ls_config import (
    SERVER_URL, ADAPTER_SET, DATA_ADAPTER, FIELD_NAMES,
    TT_MAPPING, INV_TT_MAPPING,
)

# Only need a few SR1 outrights for diagnosis
TEST_CODES = ["SR1J26", "SR1K26", "SR1M26", "SR1N26", "SR1Q26", "SR1U26"]
TEST_IDS = {code: TT_MAPPING[code] for code in TEST_CODES if code in TT_MAPPING}

prices = {}

try:
    from lightstreamer.client import LightstreamerClient, Subscription

    def _safe_float(v):
        try:
            return float(str(v).strip().replace(',','')) if v not in (None,'','--','N/A') else None
        except: return None

    def _normalize(v):
        t = str(v or '').strip()
        if t.startswith('TT-'): t = t[3:]
        if t.endswith('.0'): t = t[:-2]
        return t

    class Listener:
        def onItemUpdate(self, update):
            item = update.getItemName()
            iid = str(update.getValue('InstrumentId') or '').strip()
            for cand in (item, iid):
                key = _normalize(cand)
                if key in INV_TT_MAPPING:
                    code = INV_TT_MAPPING[key]
                    if code in TEST_CODES:
                        bid = _safe_float(update.getValue('BestBid'))
                        ask = _safe_float(update.getValue('BestAsk'))
                        last = _safe_float(update.getValue('Last'))
                        settle = _safe_float(update.getValue('Settle'))
                        prev_settle = _safe_float(update.getValue('PrevSettle'))
                        price = _safe_float(update.getValue('Price'))
                        
                        # Mid = (bid+ask)/2 when both available
                        if bid is not None and ask is not None:
                            mid = (bid + ask) / 2.0
                        elif last is not None:
                            mid = last
                        elif price is not None:
                            mid = price
                        elif settle is not None:
                            mid = settle
                        else:
                            mid = None
                        
                        # Divide by 100 for outrights
                        if mid is not None:
                            mid = mid / 100.0
                        if bid is not None:
                            bid = bid / 100.0
                        if ask is not None:
                            ask = ask / 100.0
                        
                        prices[code] = {
                            'bid': bid, 'ask': ask, 'mid': mid,
                            'raw_last': last, 'raw_settle': settle,
                            'raw_prev_settle': prev_settle, 'raw_price': price,
                        }
                    break
        def onSubscription(self): pass
        def onUnsubscription(self): pass
        def onSubscriptionError(self, code, msg): print(f"  Sub error: {code} {msg}")
        def onEndOfSnapshot(self, item, pos): pass
        def onClearSnapshot(self, item, pos): pass
        def onItemLostUpdates(self, item, pos, lost): pass

    print(f"Connecting to {SERVER_URL} ...")
    client = LightstreamerClient(SERVER_URL, ADAPTER_SET)
    client.connect()
    print("Connected. Subscribing to", len(TEST_IDS), "items...")

    sub = Subscription('MERGE', ['TT-'+v for v in TEST_IDS.values()], FIELD_NAMES)
    sub.setDataAdapter(DATA_ADAPTER)
    sub.setRequestedMaxFrequency('1')
    sub.setRequestedSnapshot('yes')
    listener = Listener()
    sub.addListener(listener)
    client.subscribe(sub)

    # Wait for data
    for _ in range(15):
        time.sleep(1)
        if len(prices) >= len(TEST_CODES):
            break
        print(f"  ... received {len(prices)}/{len(TEST_CODES)} prices")

    client.disconnect()
    print(f"\nReceived {len(prices)} prices.\n")

except Exception as e:
    print(f"Lightstreamer error: {e}")
    print("Using fallback: no live data available")

# Now compute scenario prices and compare
from core.pricing_engine import price_sr1
from core.date_utils import generate_sr1_contracts
from datetime import date

sr1c = generate_sr1_contracts(18)

# Try different base rates to find the best match
base_rates = [4.33, 4.30, 3.64, 3.58]
empty_path = {}  # No cuts = flat rate

print("=" * 90)
print(f"{'CODE':12s} {'LIVE MID':>12s} {'IMPLIED RATE':>12s}  |  ", end="")
for br in base_rates:
    print(f"  BASE={br:.2f}", end="")
print()
print("=" * 90)

for c in sr1c:
    code_bare = c["code"].split(" (")[0]  # strip label
    live = prices.get(code_bare, {})
    live_mid = live.get('mid')
    
    row = f"{c['code']:24s} "
    if live_mid is not None:
        row += f"{live_mid:12.4f} {100 - live_mid:12.4f}  |  "
    else:
        row += f"{'—':>12s} {'—':>12s}  |  "
    
    for br in base_rates:
        scenario_price = price_sr1(c["year"], c["month"], empty_path, br)
        diff = ""
        if live_mid is not None:
            d = (scenario_price - live_mid) * 100  # diff in bps
            diff = f" ({d:+.1f}bp)"
        row += f"  {scenario_price:.4f}{diff}"
    
    print(row)

print("\n" + "=" * 90)
print("Diff = (Scenario - Live) × 100 bps")
print("A perfect match means diff ≈ 0.0 bp")
print("The base rate that gives closest match reveals the correct base_sofr setting.")
