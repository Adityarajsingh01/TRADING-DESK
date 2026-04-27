# STIR Trading Terminal

A unified **Bloomberg-style STIR trading dashboard** combining:
- **Market Data Visualizer** — Meeting premiums, SR3 curve, ZQ/EFFR, Events Calendar, Trade Blotter (static 2024–2025 data)
- **Scenario Engine** — Full SR1/ZQ/SR3 pricing engine with FOMC-based rate path modeling and case management

## Features

| Feature | Status |
|---|---|
| Meeting Premium Curve (historical) | ✅ |
| SR3 Curve & ZQ/EFFR Charts | ✅ |
| Events Calendar & Trade Blotter | ✅ |
| Outright Pricing (SR1/ZQ/SR3) | ✅ |
| Spreads (1M/2M SR1/ZQ · 1Q–4Q SR3) | ✅ |
| Butterflies (1M SR1/ZQ · 1Q/2Q SR3) | ✅ |
| Condors (1M SR1/ZQ · 1Q/2Q SR3) | ✅ |
| Deflys (1M SR1/ZQ · 1Q/2Q SR3) | ✅ |
| Trade Builder + DV01 | ✅ |
| Scenario PnL across all cases | ✅ |
| Case Manager (up to 1000 cases) | ✅ |
| Annual + H1/H2 rate path modes | ✅ |
| Custom formula builder | ✅ |

## Layout

```
┌─ Sidebar ──────────┬─ Main Panel (3 Tabs) ──────────────────────┐
│ Base Rates          │ [📊 Market View] [📈 Structures] [🧾 Trade] │
│ Formula Builder     │                                              │
│ Case Builder        │  Tab 1: Full Dashboard A (historical data)  │
│ Case List           │  Tab 2: Outrights/Spreads/Flies/Condors     │
│                     │  Tab 3: Trade Builder + Scenario PnL        │
└─────────────────────┴──────────────────────────────────────────────┘
```

## Running Locally

```bash
pip install streamlit plotly pandas holidays
streamlit run app.py
```

## Deploying to Streamlit Cloud

1. Push this folder to a GitHub repo (include all files)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect the repo, set **Main file path** to `app.py`
4. Deploy

> **Note:** The `data/` folder (case storage) is ephemeral on Streamlit Cloud — cases reset on each deploy. For persistence, connect to a database or use `st.secrets`.

## Project Structure

```
stir_terminal/
├── app.py                    # Unified entry point
├── requirements.txt
├── .streamlit/config.toml    # Streamlit Cloud config
├── assets/                   # Dashboard A static files (HTML/JS/CSS)
│   ├── index.html
│   ├── app.js
│   ├── data.js               # Precomputed market data (2024–2025)
│   ├── style.css
│   └── chart_umd_min.js
├── config/
│   ├── constants.py          # DV01s, contract specs, formula weights
│   └── fomc_dates.py         # FOMC meeting dates 2026–2030
├── core/
│   ├── pricing_engine.py     # SR1/ZQ/SR3 pricing formulas
│   ├── case_manager.py       # Scenario case CRUD + rate path builder
│   ├── structures.py         # Spreads/Flies/Condors/Deflys
│   └── date_utils.py         # Business days, IMM dates, contract schedules
└── ui/
    ├── styles.py             # Bloomberg CSS + table helpers
    ├── input_panel.py        # Sidebar controls
    ├── tab_market.py         # Tab 1: Market View (Dashboard A iframe)
    ├── tab_structures.py     # Tab 2: All structure types
    └── tab_trade_builder.py  # Tab 3: Trade entry + scenario PnL

```

## Pricing Formulas

| Product | Formula |
|---|---|
| SR1 | `100 − simple_avg(daily SOFR over delivery month)` |
| ZQ  | `100 − simple_avg(daily EFFR over delivery month)` |
| SR3 | `100 − compounded_3M_SOFR` (3rd Wed to 3rd Wed) |

## DV01

| Product | DV01/lot |
|---|---|
| SR1 | $41.67 |
| ZQ  | $41.67 |
| SR3 | $25.00 |
