# STIR Trading Terminal — Comprehensive System & Architecture Guide

This document serves as an institutional-level reference for the STIR (Short-Term Interest Rate) Trading Terminal. It details the underlying financial models, product specifications, system architecture, and integration layers. It is designed to be provided as context for future development, ensuring a deep understanding of the platform's pricing mechanics, scenario generation, and structure conventions.

---

## 1. System Overview

The STIR Trading Terminal is a unified, Bloomberg-style pricing and scenario analysis application built in Python/Streamlit. It bridges real-time market data with an advanced scenario engine to model interest rate paths.

**Core Capabilities:**
- **Market Data Visualizer:** Live VWAP and meeting premium visualization, live structure pricing, historical event analysis.
- **Scenario Engine:** Advanced FOMC-based rate path modeling, allowing users to project custom basis point (bps) cuts/hikes across future meetings via built-in (e.g., Front-Loaded, Back-Loaded) or custom distribution formulas.
- **Trade & Risk Management:** Trade Blotter, Trade Builder, and cross-scenario Profit & Loss (PnL) matrix computation based on DV01 parameters.

---

## 2. Traded Products & Universe

The terminal models three primary STIR futures products across the yield curve:

1. **SR1 (1-Month SOFR Futures)**
   - **Underlying:** Secured Overnight Financing Rate (SOFR)
   - **Tick Value / DV01:** $41.67 per lot
2. **ZQ (30-Day Federal Funds Futures)**
   - **Underlying:** Effective Federal Funds Rate (EFFR)
   - **Tick Value / DV01:** $41.67 per lot
3. **SR3 (3-Month SOFR Futures)**
   - **Underlying:** 3-Month Compounded SOFR
   - **Tick Value / DV01:** $25.00 per lot

### Traded Structures
The system calculates implied prices for various derivative structures using the outright prices:
- **Spreads (Calendar):** Gap intervals: 1M, 2M, 3M, up to 4Q depending on the underlying. Formula: `Front Price - Back Price`.
- **Butterflies:** (+1 / -2 / +1)
- **Condors:** (+1 / -1 / -1 / +1)
- **Deflys (Double Butterflies):** (+1 / -3 / +3 / -1)
- **Inter-Product Spreads:** e.g., SR1/ZQ spread

---

## 3. Core Pricing Mechanics & Math

All futures in this dashboard follow the convention: **Price = 100 - Implied Rate**. 
The scenario engine models the rate as a **step-function**: the rate stays flat between FOMC meetings and shifts on the *effective date* of a new FOMC decision.

### Base Rates vs. Future Adjustments
- **Base SOFR & Base EFFR:** Represent the *current live spot rate*, meaning they already encompass the effects of all *past* FOMC meetings.
- **Rate Path:** The scenario engine only calculates rate shifts for *future* FOMC meetings. Past meetings are zeroed out to prevent double counting. 

### A. SR1 and ZQ Pricing (Arithmetic Average)
SR1 and ZQ contracts settle against the simple arithmetic average of the underlying daily rate (SOFR or EFFR) during the delivery month.

* **Formula:** `Price = 100 - [(1/D) * Σ (d_i * Rate_i)]`
* **Variables:**
  * `D`: Total calendar days in the delivery month.
  * `d_i`: Number of calendar days a specific business day's rate applies (e.g., 1 for Mon-Thu, 3 for Fri to cover the weekend).
  * `Rate_i`: The prevailing spot rate on that day (driven by the step-function rate path).

### B. SR3 Pricing (Compounded Average)
SR3 contracts settle against the compounded daily SOFR over the reference quarter (from the 3rd Wednesday of the contract month to the 3rd Wednesday of the delivery month).

* **Formula:** `Price = 100 - R`
* **Where R:** `[ Π (1 + (d_i/360) * (Rate_i/100)) - 1 ] * (360/D) * 100`
* **Variables:**
  * `D`: Total calendar days in the reference quarter.
  * `d_i`: Calendar days the business day's SOFR applies.
  * `Rate_i`: SOFR rate in % p.a. for that business day.

---

## 4. Scenario Engine & Case Management

The core of the terminal's predictive power lies in `CaseManager` (`core/case_manager.py`). 

- **Rate Path Projection:** Users do not input daily rates. Instead, they define annual or semi-annual (H1/H2) rate cuts/hikes. 
- **Distribution Formulas:** Cuts are distributed across FOMC meetings using weighted formulas (Uniform, Front-Loaded, Back-Loaded, Custom).
- **Meeting Premium Extraction:** The dashboard maps these projected case values against live market expectations. It extracts CME FedWatch-equivalent market expectations from Calendar Spreads VWAP (e.g., `ZQ_CAL_J26K26`) or calculates them dynamically via outrights.

---

## 5. System Architecture & Directory Structure

The project is structured modularly to separate UI rendering from core pricing math and live data ingestion.

```text
stir_terminal/
├── app.py                    # Unified entry point; initializes Streamlit layout and session states.
├── config/
│   ├── constants.py          # DV01s, contract specs, formula weights
│   ├── fomc_dates.py         # FOMC meeting schedules (decision & effective dates)
│   └── ls_config.py          # Lightstreamer server URL, adapters, and TT Instrument ID mappings
├── core/
│   ├── pricing_engine.py     # SR1/ZQ/SR3 math formulas & batch pricing over rate paths
│   ├── case_manager.py       # CRUD operations for scenarios (JSON persistence in /data/)
│   ├── structures.py         # Math for Spreads, Flies, Condors, Deflys
│   ├── date_utils.py         # Business day calendars, IMM dates, day weighting
│   └── live_data.py          # Lightstreamer integration client & callback handlers
└── ui/
    ├── styles.py             # Injects custom Bloomberg-style CSS & table helpers
    ├── input_panel.py        # Sidebar controls (Case list, Formula builder)
    ├── tab_market.py         # Tab 1: Historical Market View
    ├── tab_structures.py     # Tab 2: Case Analyzer (Live curves, outrights, structures)
    └── tab_trade_builder.py  # Tab 3: Trade construction & Scenario PnL tracking
```

---

## 6. Live Data Integration (Lightstreamer)

Market data is supplied by a corporate Lightstreamer server interfacing with Trading Technologies (TT). 

- **Configuration (`config/ls_config.py`):** Maps human-readable contract codes (e.g., `SR3H26`) and spread configurations (e.g., `ZQ_CAL_J26K26`) directly to numeric TT Instrument IDs (e.g., `2264814074172926158`).
- **Subscription Model (`core/live_data.py`):** The app asynchronously subscribes to `TTsdkLSAdapter` using the `HGL1_Adapter` data adapter. 
- **Fields Ingested:** `VWAP`, `Last`, `Bid`, `Ask`, `Volume`. For forward curve meeting premiums, the system actively prefers `VWAP` on Calendar Spread instruments.

## Summary for Claude / Future AI
When working on this repository, strictly adhere to the following rules:
1. **Never alter the mathematical definitions** of SR1/ZQ arithmetic averaging or SR3 compounding without extreme caution.
2. **Respect the base rate step function logic:** Past meetings are baked into the base rate; do not allow the engine to apply historical meeting cuts twice.
3. **Follow the Bloomberg visual aesthetic:** Adhere to the established CSS paradigms defined in `ui/styles.py` (dark background, distinct cyan/orange/green font colors, dense tabular layouts). 
4. **Lightstreamer Integrity:** Maintain the strict TT Instrument ID mapping. Any new products added to the dashboard must be registered in `ls_config.py` with their raw TT IDs.
