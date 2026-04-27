"""Test if the adapter accepts symbolic contract names."""
import sys, time
sys.path.insert(0, '.')
from lightstreamer.client import LightstreamerClient, Subscription

SERVER_URL   = 'https://ls-md.corp.hertshtengroup.com/'
ADAPTER_SET  = 'TTsdkLSAdapter'
DATA_ADAPTER = 'HGL1_Adapter'
FIELDS = ['command', 'Contract', 'Product', 'InstrumentId', 'Last', 'BestBid', 'BestAsk']

hits = {}

class CL:
    def onStatusChange(self, s):
        if 'CONNECTED' in s: print('Connected:', s)
    def onServerError(self, c, m): print('ERR', c, m)
    def onPropertyChange(self, p): pass

class SL:
    def onItemUpdate(self, u):
        name = u.getItemName()
        contract = u.getValue('Contract') or ''
        bid  = u.getValue('BestBid') or ''
        ask  = u.getValue('BestAsk') or ''
        iid  = u.getValue('InstrumentId') or ''
        hits[name] = {'contract': contract, 'bid': bid, 'ask': ask, 'iid': iid}
        print('HIT: %-25s contract=%s bid=%s ask=%s iid=%s' % (name, contract, bid, ask, iid))
    def onSubscription(self): print('[SUB] OK')
    def onSubscriptionError(self, c, m): print('[SERR]', c, m)
    def onEndOfSnapshot(self, n, p): pass
    def onUnsubscription(self): pass
    def onClearSnapshot(self, n, p): pass
    def onItemLostUpdates(self, n, p, l): pass

# Only valid item names (no spaces)
test_items = [
    'SR1K26', 'SR1M26', 'SR1N26', 'SR1U26', 'SR1V26',
    'ZQK26', 'ZQM26', 'ZQN26', 'ZQU26',
    'SR3M26', 'SR3U26', 'SR3Z26',
    'CME/SR1K26', 'CME_SR1K26',
    'CBOT/ZQK26', 'CBOT_ZQK26',
    'SR1_K26', 'ZQ_K26',
    'FRONT_SR1', 'FRONT_ZQ',
    'SR1_FRONT', 'ZQ_FRONT',
]

c = LightstreamerClient(SERVER_URL, ADAPTER_SET)
c.addListener(CL())
c.connect()
time.sleep(2)

sub = Subscription('MERGE', test_items, FIELDS)
sub.setDataAdapter(DATA_ADAPTER)
sub.setRequestedSnapshot('yes')
sub.addListener(SL())
c.subscribe(sub)

print('Listening 12s...')
time.sleep(12)
c.disconnect()

print()
print('Items that returned data:', list(hits.keys()) if hits else 'NONE - numeric IDs required')
