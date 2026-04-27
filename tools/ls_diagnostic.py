"""
tools/ls_diagnostic.py
----------------------
Standalone connectivity test using the official lightstreamer.client SDK.
Matches colleague's confirmed working code pattern exactly.

Run from project root:
    python tools/ls_diagnostic.py
    python tools/ls_diagnostic.py --timeout 60
    python tools/ls_diagnostic.py --all-spreads
"""
from __future__ import annotations

import sys
import os
import time
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ls_diag")

from config.ls_config import (
    SERVER_URL, ADAPTER_SET, DATA_ADAPTER, FIELD_NAMES,
    TT_MAPPING, INV_TT_MAPPING,
)

try:
    from lightstreamer.client import LightstreamerClient, Subscription
except ImportError:
    print("ERROR: lightstreamer-client-lib not installed.")
    print("  Run:  pip install lightstreamer-client-lib")
    sys.exit(1)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=int, default=30,
                   help="Seconds to listen (default 30)")
    p.add_argument("--all-spreads", action="store_true",
                   help="Include spread/calendar IDs too")
    return p.parse_args()


class DiagListener:
    def __init__(self, label_map):
        self._label_map = label_map
        self.count = 0
        self.seen = set()

    def onItemUpdate(self, update):
        self.count += 1
        item  = update.getItemName()
        label = self._label_map.get(item, item)
        self.seen.add(label)

        non_null = {}
        for f in FIELD_NAMES:
            v = update.getValue(f)
            if v not in (None, "", "#", "$"):
                non_null[f] = v

        out = "  [%4d]  %-20s  %s" % (self.count, label, non_null)
        print(out.encode("ascii", errors="replace").decode("ascii"))

    def onSubscription(self):             pass
    def onUnsubscription(self):           pass
    def onEndOfSnapshot(self, n, p):
        print("  -- Snapshot done: %s" % n)
    def onClearSnapshot(self, n, p):      pass
    def onItemLostUpdates(self, n, p, l):
        print("  !! Lost %d updates: %s" % (l, n))
    def onSubscriptionError(self, code, msg):
        print("  !! SubError %s: %s" % (code, msg))


def main():
    args = parse_args()

    candidates = [
        (code, tid) for code, tid in TT_MAPPING.items()
        if tid and tid.strip()
    ]

    if not args.all_spreads:
        candidates = [
            (c, t) for c, t in candidates
            if not any(x in c for x in ("_CAL_", "SR1ZQ", "ZQ_"))
        ]

    if not candidates:
        print("No IDs in TT_MAPPING. Edit config/ls_config.py.")
        sys.exit(1)

    item_ids  = [tid for _, tid in candidates]
    label_map = {"TT-" + tid: code for code, tid in candidates}

    sep = "=" * 65
    print(sep)
    print("  Lightstreamer Diagnostic")
    print("  Server      : " + SERVER_URL)
    print("  Adapter set : " + repr(ADAPTER_SET))
    print("  Data adapter: " + DATA_ADAPTER)
    print("  Items       : %d" % len(item_ids))
    print("  Timeout     : %ds" % args.timeout)
    print(sep)

    print("\nConnecting ...")
    client = LightstreamerClient(SERVER_URL, ADAPTER_SET)
    try:
        client.connect()
    except Exception as e:
        print("CONNECT FAILED: " + str(e))
        sys.exit(1)
    print("Connected OK\n")

    sub = Subscription("MERGE", ["TT-" + i for i in item_ids], FIELD_NAMES)
    sub.setDataAdapter(DATA_ADAPTER)
    sub.setRequestedMaxFrequency("0.5")
    sub.setRequestedSnapshot("yes")

    listener = DiagListener(label_map)
    sub.addListener(listener)
    client.subscribe(sub)

    print("Listening for %ds ...\n" % args.timeout)
    time.sleep(args.timeout)

    print()
    print(sep)
    print("  Updates received : %d" % listener.count)
    print("  Codes with data  : %d" % len(listener.seen))
    if listener.seen:
        print("  Codes: " + str(sorted(listener.seen)))
    if listener.count == 0:
        print()
        print("  WARNING: No updates. Check:")
        print("    - Item IDs in TT_MAPPING")
        print("    - DATA_ADAPTER = " + repr(DATA_ADAPTER))
        print("    - Market may be closed")
    print(sep + "\n")

    client.disconnect()


if __name__ == "__main__":
    main()
