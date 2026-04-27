"""
STIR Terminal — Trade Engine
Accurate CME PnL calculations, trade dataclass, and blotter persistence.

PnL Formula (verified against CME Group contract specifications):
    PnL = (exit_price - entry_price) × CONTRACT_MULTIPLIER × lots × sign

    sign = +1 for BUY, -1 for SELL

Contract Multipliers:
    SR1 (1-Month SOFR):  $4,167 per index point  → DV01 = $41.67
    ZQ  (30-Day Fed Funds): $4,167 per index point  → DV01 = $41.67
    SR3 (3-Month SOFR):  $2,500 per index point  → DV01 = $25.00
"""

from __future__ import annotations
import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

from config.constants import CONTRACT_MULTIPLIER, CONTRACT_SPECS

# ── Data directory ────────────────────────────────────────────────────────────
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_BLOTTER_FILE = os.path.join(_DATA_DIR, "trade_blotter.json")


# ── PnL Helpers ───────────────────────────────────────────────────────────────

def compute_pnl(
    product: str,
    entry_price: float,
    exit_price: float,
    lots: int,
    side: str,
) -> float:
    """
    Compute PnL in USD for a trade.

    Args:
        product:     "SR1", "ZQ", or "SR3"
        entry_price: Entry price in IMM index points (e.g. 96.3500)
        exit_price:  Exit/current price in IMM index points
        lots:        Number of contracts
        side:        "BUY" or "SELL"

    Returns:
        PnL in USD (positive = profit, negative = loss)
    """
    multiplier = CONTRACT_MULTIPLIER[product]
    sign = 1 if "BUY" in side.upper() else -1
    return round((exit_price - entry_price) * multiplier * lots * sign, 2)


def compute_pnl_bps(entry_price: float, exit_price: float) -> float:
    """Price change in basis points (1 bp = 0.01 price points)."""
    return round((exit_price - entry_price) * 100, 4)


def dv01_per_lot(product: str) -> float:
    """DV01 per lot ($ per basis point move in the structure price)."""
    return CONTRACT_SPECS[product]["dv01"]


def tick_value(product: str, is_front: bool = False) -> float:
    """Tick value in USD."""
    specs = CONTRACT_SPECS[product]
    return specs["tick_value_front"] if is_front else specs["tick_value_back"]


def tick_size(product: str, is_front: bool = False) -> float:
    """Minimum tick size."""
    specs = CONTRACT_SPECS[product]
    return specs["tick_size_front"] if is_front else specs["tick_size_back"]


# ── Structure weight info ─────────────────────────────────────────────────────

STRUCTURE_WEIGHTS = {
    "Outright":        [1],
    "Spread":          [1, 1],           # +1 back, -1 front → 2 legs
    "Butterfly (Fly)": [1, 2, 1],        # +1, -2, +1 → 4 outright lots
    "Condor":          [1, 1, 1, 1],     # +1, -1, -1, +1
    "Defly":           [1, 3, 3, 1],     # +1, -3, +3, -1 → 8 outright lots
}


def structure_leg_count(trade_type: str) -> int:
    return len(STRUCTURE_WEIGHTS.get(trade_type, [1]))


def structure_total_lots(trade_type: str) -> int:
    """Total outright-equivalent lots per 1 structure lot."""
    return sum(STRUCTURE_WEIGHTS.get(trade_type, [1]))


# ── Trade dataclass ───────────────────────────────────────────────────────────

@dataclass
class Trade:
    id: str = ""
    product: str = "SR1"
    trade_type: str = "Outright"
    legs: list = field(default_factory=list)       # e.g. ["SR1K26"] or ["SR1K26","SR1M26"]
    instrument_key: str = ""                        # internal key e.g. "SR1M26-SR1K26"
    display_name: str = ""                           # full label e.g. "[FLY 1M] ZQV26/ZQX26/ZQZ26"
    side: str = "BUY"
    lots: int = 1
    entry_price: float = 0.0
    entry_source: str = "Manual"                    # "Live Mid", "Case: xxx", "Manual"
    notes: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")

    def pnl(self, exit_price: float) -> float:
        return compute_pnl(self.product, self.entry_price, exit_price, self.lots, self.side)

    def pnl_bps(self, exit_price: float) -> float:
        return compute_pnl_bps(self.entry_price, exit_price)

    def dv01(self) -> float:
        return dv01_per_lot(self.product) * self.lots

    def sign(self) -> int:
        return 1 if "BUY" in self.side.upper() else -1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Trade":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Trade Blotter ─────────────────────────────────────────────────────────────

class TradeBlotter:
    """Manages a portfolio of trades with file persistence."""

    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self.trades: List[Trade] = []
        self._load()

    def _load(self):
        if not os.path.exists(_BLOTTER_FILE):
            self._save()
            return
        try:
            with open(_BLOTTER_FILE, "r") as f:
                data = json.load(f)
            self.trades = [Trade.from_dict(t) for t in data.get("trades", [])]
        except Exception:
            self.trades = []

    def _save(self):
        with open(_BLOTTER_FILE, "w") as f:
            json.dump({"trades": [t.to_dict() for t in self.trades]}, f, indent=2)

    def add_trade(self, trade: Trade) -> Trade:
        self.trades.append(trade)
        self._save()
        return trade

    def remove_trade(self, trade_id: str):
        self.trades = [t for t in self.trades if t.id != trade_id]
        self._save()

    def clear_all(self):
        self.trades = []
        self._save()

    def get_trade(self, trade_id: str) -> Optional[Trade]:
        return next((t for t in self.trades if t.id == trade_id), None)

    def portfolio_pnl(self, live_prices: dict) -> float:
        """
        Compute total portfolio PnL using live prices.

        live_prices: {instrument_key: float} — current mid prices
        """
        total = 0.0
        for t in self.trades:
            exit_px = live_prices.get(t.instrument_key)
            if exit_px is not None:
                total += t.pnl(exit_px)
        return round(total, 2)

    def scenario_pnl(self, case_prices: dict) -> Dict[str, float]:
        """
        Compute portfolio PnL for each case.

        case_prices: {case_id: {instrument_key: float}}
        Returns: {case_id: total_pnl}
        """
        result = {}
        for case_id, prices in case_prices.items():
            total = 0.0
            for t in self.trades:
                exit_px = prices.get(t.instrument_key)
                if exit_px is not None:
                    total += t.pnl(exit_px)
            result[case_id] = round(total, 2)
        return result
