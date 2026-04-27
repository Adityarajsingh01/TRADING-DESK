"""
core/live_data.py
─────────────────
Connects to the Hertshten/TT Lightstreamer server and maintains a live
price cache (LIVE_PRICES) keyed by internal contract code.

Library : lightstreamer-client-lib  (official Lightstreamer Python SDK)
  pip install lightstreamer-client-lib
  from lightstreamer.client import LightstreamerClient, Subscription

Connection pattern confirmed from colleague's working code:
  LightstreamerClient(SERVER_URL, ADAPTER_SET='')
  Subscription('MERGE', ['TT-' + id, ...], FIELD_NAMES)
  sub.setDataAdapter('HGL1_Adapter')
  Listener class with  onItemUpdate(self, update)
"""
from __future__ import annotations

import threading
import time
import logging
import traceback
from typing import Any

from config.ls_config import (
    SERVER_URL, ADAPTER_SET, DATA_ADAPTER, FIELD_NAMES,
    TT_MAPPING, INV_TT_MAPPING,
)

# ── Library import ─────────────────────────────────────────────────────────────
try:
    from lightstreamer.client import LightstreamerClient, Subscription
    HAS_LS = True
except ImportError:
    HAS_LS = False

log = logging.getLogger("LiveData")

# ── Live price cache ──────────────────────────────────────────────────────────
# Format: {"SR3M26": {"Bid": 95.355, "Ask": 95.360, "Mid": 95.3575}, ...}
LIVE_PRICES: dict[str, dict[str, float | None]] = {}

# Connection status for the UI status bar
LS_STATUS: dict[str, Any] = {
    "connected": False,
    "items":     0,
    "last_update": None,
    "error":     None,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(value: Any) -> float | None:
    if value in (None, ''):
        return None
    try:
        if isinstance(value, str):
            text = value.strip().replace(',', '')
            if text in ('', '-', '--', 'N/A', 'n/a', 'null', 'None'):
                return None
            return float(text)
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_id(value: Any) -> str:
    """Strip 'TT-' prefix and trailing '.0' from an item/instrument ID."""
    text = str(value or '').strip()
    if text.startswith('TT-'):
        text = text[3:]
    if text.endswith('.0'):
        text = text[:-2]
    return text


def _resolve_app_code(item_name: str, update) -> str:
    """
    Try multiple strategies to map an update to an internal app code
    (e.g. "SR3M26").  Mirrors the colleague's resolution logic exactly.
    """
    instrument_id = str(update.getValue('InstrumentId') or '').strip()

    for candidate in (item_name, instrument_id):
        key = _normalize_id(candidate)
        if key in INV_TT_MAPPING:
            return INV_TT_MAPPING[key]

    # Last resort: match the 'Contract' field name
    raw_contract = str(update.getValue('Contract') or item_name)
    return INV_TT_MAPPING.get(raw_contract, '')


# ── Subscription listener ─────────────────────────────────────────────────────

class _SubListener:
    """Lightstreamer listener — receives onItemUpdate calls from the SDK."""

    def __init__(self) -> None:
        self._last_price: dict[str, float] = {}

    def onItemUpdate(self, update) -> None:       # noqa: N802  (SDK naming)
        item_name = update.getItemName()
        app_code  = _resolve_app_code(item_name, update)
        if not app_code:
            log.debug("Unresolved item: %s", item_name)
            return

        bid = _safe_float(update.getValue('BestBid'))
        ask = _safe_float(update.getValue('BestAsk'))

        # ── Mid-price priority: ALWAYS use (BestBid + BestAsk) / 2 when both
        #    are available.  Only fall back to Last/Settle/etc. when bid or ask
        #    is missing.  This ensures the LIVE column shows the true live mid.
        if bid is not None and ask is not None:
            price = (bid + ask) / 2.0
        else:
            # Fallback chain when bid/ask incomplete
            price_candidates = [
                _safe_float(update.getValue('Last')),
                _safe_float(update.getValue('Price')),
                _safe_float(update.getValue('Close')),
                _safe_float(update.getValue('Settle')),
                _safe_float(update.getValue('PrevSettle')),
                _safe_float(update.getValue('IndSettle')),
                _safe_float(update.getValue('AdminPrice')),
            ]
            price = next((p for p in price_candidates if p is not None), None)
            if price is None and bid is not None:
                price = bid
            if price is None and ask is not None:
                price = ask

        if price is None:
            price = self._last_price.get(app_code)
        if price is None:
            return

        # TT sends outright prices × 100 (e.g. 9635.5 for 96.355).
        # Outrights have no '_' in their app_code; spreads/calendars do.
        is_outright = '_' not in app_code
        if is_outright:
            price = price / 100.0
            if bid is not None: bid = bid / 100.0
            if ask is not None: ask = ask / 100.0

        self._last_price[app_code] = float(price)

        vwap = _safe_float(update.getValue('VWAP'))
        if is_outright and vwap is not None:
            vwap = vwap / 100.0

        entry = LIVE_PRICES.setdefault(app_code, {})
        if bid   is not None: entry['Bid'] = bid
        if ask   is not None: entry['Ask'] = ask
        if vwap  is not None: entry['VWAP'] = vwap
        entry['Mid'] = price

        LS_STATUS['last_update'] = time.time()
        log.debug("Tick  %-12s  bid=%-10s  ask=%-10s  mid=%s",
                  app_code, bid, ask, price)

    # ── Additional SDK callbacks (no-ops, required by interface) ──────────────

    def onSubscription(self):          pass  # noqa: N802
    def onUnsubscription(self):        pass  # noqa: N802
    def onSubscriptionError(self, code, message):                         # noqa: N802
        log.error("Subscription error %s: %s", code, message)
    def onEndOfSnapshot(self, item_name, item_pos):                       # noqa: N802
        log.debug("Snapshot complete for %s", item_name)
    def onClearSnapshot(self, item_name, item_pos):   pass               # noqa: N802
    def onItemLostUpdates(self, item_name, item_pos, lost):              # noqa: N802
        log.warning("Lost %d updates for %s", lost, item_name)


# ── Connection loop ───────────────────────────────────────────────────────────

def _build_subscription(item_ids: list[str]) -> Subscription:
    """Build the Subscription object exactly as the colleague's code does."""
    sub = Subscription(
        'MERGE',
        ['TT-' + iid for iid in item_ids],   # TT- prefix confirmed working
        FIELD_NAMES,
    )
    sub.setDataAdapter(DATA_ADAPTER)
    sub.setRequestedMaxFrequency('1')       # 1 update per second
    sub.setRequestedSnapshot('yes')
    return sub


def _run_client() -> None:
    if not HAS_LS:
        log.error(
            "lightstreamer.client not importable. "
            "Run:  pip install lightstreamer-client-lib"
        )
        LS_STATUS['error'] = 'lightstreamer-client-lib not installed'
        return

    # Only subscribe to items that have a real ID
    items_to_sub = [
        (app_code, tt_id)
        for app_code, tt_id in TT_MAPPING.items()
        if tt_id and tt_id.strip()
    ]

    if not items_to_sub:
        log.warning("TT_MAPPING has no IDs. Edit config/ls_config.py.")
        LS_STATUS['error'] = 'No instrument IDs configured'
        return

    item_ids  = [tt_id for _, tt_id in items_to_sub]
    retry_sec = 5

    while True:
        try:
            log.info("Connecting to %s  (adapter='%s', data='%s') …",
                     SERVER_URL, ADAPTER_SET or '<empty>', DATA_ADAPTER)

            client = LightstreamerClient(SERVER_URL, ADAPTER_SET)
            client.connect()

            LS_STATUS.update(connected=True, items=len(item_ids), error=None)
            log.info("Connected ✓  subscribing %d items …", len(item_ids))

            sub      = _build_subscription(item_ids)
            listener = _SubListener()
            sub.addListener(listener)
            client.subscribe(sub)

            retry_sec = 5   # reset back-off on success

            # Keep alive — the SDK dispatches callbacks on its own thread
            while True:
                time.sleep(1)

        except Exception as exc:
            LS_STATUS.update(connected=False, error=str(exc))
            log.error("LiveData error: %s — retry in %ds", exc, retry_sec)
            log.debug(traceback.format_exc())
            time.sleep(retry_sec)
            retry_sec = min(retry_sec * 2, 120)   # exponential back-off, cap 2 min


# ── Public API ────────────────────────────────────────────────────────────────

_ls_thread: threading.Thread | None = None


def start_live_data(sr1_contracts, zq_contracts, sr3_contracts) -> None:
    """
    Start the Lightstreamer background thread (idempotent — safe to call on
    every Streamlit rerun).  Pre-populates LIVE_PRICES so the UI renders
    immediately with None values instead of missing rows.
    """
    global _ls_thread

    # Pre-populate placeholders
    all_codes = [c['code'] for c in sr1_contracts + zq_contracts + sr3_contracts]
    for code in all_codes:
        LIVE_PRICES.setdefault(code, {'Bid': None, 'Ask': None, 'Mid': None})

    if _ls_thread is not None and _ls_thread.is_alive():
        return   # already running

    _ls_thread = threading.Thread(
        target=_run_client, name='LightstreamerThread', daemon=True
    )
    _ls_thread.start()
    log.info("Lightstreamer thread started.")


def _strip_label(code: str) -> str:
    """Strip the ' (Mon)' suffix: 'SR1J26 (Apr)' → 'SR1J26'."""
    if ' (' in code:
        return code.split(' (')[0]
    return code


def get_live_price(contract_code: str, product: str = '') -> float | None:
    """Return the live mid-price for an internal contract code, or None."""
    key = _strip_label(contract_code)
    return LIVE_PRICES.get(key, {}).get('Mid')


def get_live_bid_ask(contract_code: str) -> tuple[float | None, float | None]:
    """Return (bid, ask) for a contract code."""
    entry = LIVE_PRICES.get(_strip_label(contract_code), {})
    return entry.get('Bid'), entry.get('Ask')


def get_live_struct_price(key: str, struct_type: str, product: str = '') -> float | None:
    """
    Compute a derived live price for a spread / fly / condor / defly.

    key formats:
        spread : "SR3M26-SR3U26"
        fly    : "SR3M26/SR3U26/SR3Z26"
        condor : "SR3M26/SR3U26/SR3Z26/SR3H27"
        defly  : same as condor
    """
    try:
        if struct_type == 'spread':
            b, f = key.split('-', 1)
            pb, pf = get_live_price(b), get_live_price(f)
            if pb is not None and pf is not None:
                return round(pb - pf, 4)

        elif struct_type == 'fly':
            legs = key.split('/')
            if len(legs) == 3:
                prices = [get_live_price(l) for l in legs]
                if all(p is not None for p in prices):
                    return round(prices[0] - 2 * prices[1] + prices[2], 4)

        elif struct_type in ('condor', 'defly'):
            legs = key.split('/')
            if len(legs) == 4:
                prices = [get_live_price(l) for l in legs]
                if all(p is not None for p in prices):
                    if struct_type == 'condor':
                        return round(prices[0] - prices[1] - prices[2] + prices[3], 4)
                    else:
                        return round(prices[0] - 3*prices[1] + 3*prices[2] - prices[3], 4)

    except Exception:
        log.debug("get_live_struct_price failed for %s (%s)", key, struct_type, exc_info=True)

    return None


def is_connected() -> bool:
    return bool(LS_STATUS.get('connected'))


def get_status() -> dict:
    return dict(LS_STATUS)
