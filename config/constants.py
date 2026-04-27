"""
STIR Dashboard — Contract Constants
All contract specs, tick sizes, DV01s, and IMM month codes.
To add a new contract type: add its SPECS dict and update CONTRACT_SPECS.
"""

# ── IMM Month Codes ──────────────────────────────────────────────────────────
IMM_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K",  6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
IMM_CODES_INV = {v: k for k, v in IMM_CODES.items()}  # reverse lookup

# SR3 only uses quarterly months
SR3_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}
SR3_MONTHS = [3, 6, 9, 12]  # Mar, Jun, Sep, Dec

# ── Contract Specifications ───────────────────────────────────────────────────
SR1_SPECS = {
    "name": "1-Month SOFR",
    "product": "SR1",
    "exchange": "CME",
    "notional": 4_167_000,       # Approximate: $4,167 × IMM Index
    "dv01": 41.67,               # $ per basis point per annum
    "tick_size_back": 0.005,     # deferred months
    "tick_value_back": 20.835,
    "tick_size_front": 0.0025,   # front month conditional
    "tick_value_front": 10.4175,
    "settlement": "Cash",
    "underlying": "SOFR",
    "day_count": 360,
    "rate_type": "simple_avg",   # simple arithmetic average
}

ZQ_SPECS = {
    "name": "30-Day Fed Funds",
    "product": "ZQ",
    "exchange": "CBOT",
    "notional": 5_000_000,
    "dv01": 41.67,               # $ per basis point per annum
    "tick_size_back": 0.005,
    "tick_value_back": 20.835,
    "tick_size_front": 0.0025,
    "tick_value_front": 10.4175,
    "settlement": "Cash",
    "underlying": "EFFR",
    "day_count": 360,
    "rate_type": "simple_avg",
}

SR3_SPECS = {
    "name": "3-Month SOFR",
    "product": "SR3",
    "exchange": "CME",
    "notional": 2_500_000,       # $2,500 × IMM Index
    "dv01": 25.00,               # $ per basis point per annum
    "tick_size_back": 0.005,     # all months except front
    "tick_value_back": 12.50,
    "tick_size_front": 0.0025,   # front month only
    "tick_value_front": 6.25,
    "settlement": "Cash",
    "underlying": "SOFR",
    "day_count": 360,
    "rate_type": "compounded",   # business-day compounded SOFR
}

CONTRACT_SPECS = {
    "SR1": SR1_SPECS,
    "ZQ":  ZQ_SPECS,
    "SR3": SR3_SPECS,
}

# ── CME Contract Multipliers (price point → USD) ────────────────────────────
# PnL = (exit_price - entry_price) × MULTIPLIER × lots × sign
# SR1/ZQ: $4,167 per full index point  (DV01 = $41.67 per 0.01)
# SR3:    $2,500 per full index point  (DV01 = $25.00 per 0.01)
CONTRACT_MULTIPLIER = {"SR1": 4167, "ZQ": 4167, "SR3": 2500}

# ── Output Horizon ────────────────────────────────────────────────────────────
SR1_ZQ_HORIZON_MONTHS = 18   # ~1.5 years forward
SR3_START_YEAR        = 2026
SR3_START_MONTH       = 6    # June 2026 (SR3M26)
SR3_END_YEAR          = 2030
SR3_END_MONTH         = 12   # December 2030 (SR3Z30)

# ── Spread Definitions ───────────────────────────────────────────────────────
# (gap = number of months between legs for SR1/ZQ, quarters for SR3)
SR1_SPREAD_GAPS = [1, 2]          # 1-month and 2-month spreads
ZQ_SPREAD_GAPS  = [1, 2]
SR3_SPREAD_GAPS = [1, 2, 3, 4]   # 3M, 6M, 9M, 1Y (in quarters)

# ── Butterfly Definitions ────────────────────────────────────────────────────
SR1_FLY_GAPS = [1]   # 1-month butterflies
ZQ_FLY_GAPS  = [1]
SR3_FLY_GAPS = [1, 2]  # 3-month and 6-month butterflies (in quarters)

# ── Price Display Format ──────────────────────────────────────────────────────
PRICE_DECIMALS   = 4   # e.g. 95.6250
SPREAD_DECIMALS  = 4   # e.g. -0.1250 (in price points, = bps)
FLY_DECIMALS     = 4

# ── Built-in Distribution Formulas ───────────────────────────────────────────
# weights[i] = fraction of total annual cut/hike allocated to meeting i+1
# weights must be normalised (sum=1) before application
BUILTIN_FORMULAS = {
    "Uniform": {
        "description": "Equal weight across all 8 meetings",
        "weights": [1/8] * 8,
    },
    "Front-Loaded": {
        "description": "70% in first 4 meetings, 30% in last 4",
        "weights": [0.20, 0.20, 0.17, 0.13, 0.10, 0.10, 0.05, 0.05],
    },
    "Back-Loaded": {
        "description": "30% in first 4 meetings, 70% in last 4",
        "weights": [0.05, 0.05, 0.10, 0.10, 0.13, 0.17, 0.20, 0.20],
    },
    "Skip-Jan": {
        "description": "Jan meeting always held, rest uniform",
        "weights": [0.0, 1/7, 1/7, 1/7, 1/7, 1/7, 1/7, 1/7],
    },
    "SEP-Only": {
        "description": "Only SEP meetings get cuts (Mar, Jun, Sep, Dec)",
        "weights": [0.0, 0.25, 0.0, 0.25, 0.0, 0.25, 0.0, 0.25],
    },
    "H1-Only": {
        "description": "All cuts in first half (Jan–Jun)",
        "weights": [0.15, 0.25, 0.25, 0.35, 0.0, 0.0, 0.0, 0.0],
    },
    "H2-Only": {
        "description": "All cuts in second half (Jul–Dec)",
        "weights": [0.0, 0.0, 0.0, 0.0, 0.15, 0.35, 0.25, 0.25],
    },
}

# H1 meetings = indices 0-3 (Jan, Mar, Apr/May, Jun)
# H2 meetings = indices 4-7 (Jul, Sep, Oct, Dec)
H1_MEETING_INDICES = [0, 1, 2, 3]
H2_MEETING_INDICES = [4, 5, 6, 7]

# ── Colour Constants (Bloomberg palette) ─────────────────────────────────────
COLOUR_BG          = "#000000"
COLOUR_HEADER      = "#FF8C00"
COLOUR_PRIMARY     = "#FF6600"
COLOUR_POSITIVE    = "#00FF41"
COLOUR_NEGATIVE    = "#FF3131"
COLOUR_NEUTRAL     = "#C0C0C0"
COLOUR_BORDER      = "#333333"
COLOUR_ROW_ALT     = "#0D0D0D"
COLOUR_HIGHLIGHT   = "#1A0D00"
COLOUR_ACCENT      = "#FFB347"
