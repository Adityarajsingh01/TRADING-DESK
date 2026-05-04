"""
STIR Dashboard — Case Manager
Handles case creation, storage (JSON), rate path computation, and retrieval.

Case JSON schema:
{
  "id":          "case_001",
  "name":        "War Theme",
  "created_at":  "2026-04-12T18:00:00",
  "base_effr":   4.33,
  "base_sofr":   4.30,
  "year_configs": {
    "2026": {
      "mode":          "annual",   # or "h1h2"
      "annual_cut":    -10.0,      # bps, used if mode=="annual"
      "formula_name":  "Front-Loaded",
      "h1_cut":        null,       # bps, used if mode=="h1h2"
      "h2_cut":        null,
      "h1_formula":    null,
      "h2_formula":    null,
    }, ...
  },
  "rate_path": {
    "sofr": {"2026-03-19": 4.05, ...},
    "effr": {"2026-03-19": 4.08, ...},
  },
  "meeting_cuts": {
    "sofr": {"2026-03-19": -25.0, ...},  # bps applied at each effective date
    "effr": {"2026-03-19": -25.0, ...},
  }
}
"""

from __future__ import annotations
import json
import os
from datetime import date, datetime
from typing import Dict, List, Optional
from copy import deepcopy

from config.constants import BUILTIN_FORMULAS, H1_MEETING_INDICES, H2_MEETING_INDICES
from config.fomc_dates import ALL_FOMC_MEETINGS, FOMC_BY_YEAR

# ── Paths ─────────────────────────────────────────────────────────────────────
_DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
_CASES_FILE = os.path.join(_DATA_DIR, "cases.json")


# ── Date serialisation helpers ────────────────────────────────────────────────
def _date_str(d: date) -> str:
    return d.isoformat()

def _str_date(s: str) -> date:
    return date.fromisoformat(s)

def _serialise_path(path: Dict[date, float]) -> Dict[str, float]:
    return {_date_str(k): v for k, v in path.items()}

def _deserialise_path(path: Dict[str, float]) -> Dict[date, float]:
    return {_str_date(k): v for k, v in path.items()}


# ── Formula Application ───────────────────────────────────────────────────────

def _normalise_weights(weights: List[float], indices: List[int] = None) -> List[float]:
    """Normalise a weight list over the specified indices (or all if None)."""
    if indices is None:
        indices = list(range(len(weights)))
    total = sum(weights[i] for i in indices)
    if total == 0:
        return weights[:]
    result = weights[:]
    for i in indices:
        result[i] = weights[i] / total
    return result


def _get_formula_weights(formula_name: str, custom_weights: List[float] = None) -> List[float]:
    if formula_name == "Custom" and custom_weights:
        return custom_weights[:]
    return BUILTIN_FORMULAS.get(formula_name, BUILTIN_FORMULAS["Uniform"])["weights"][:]


def compute_meeting_cuts_for_year(
    year: int,
    year_config: dict,
) -> Dict[date, float]:
    """
    Given year config, return {effective_date: cut_bps} for each FOMC meeting
    in that year.

    mode == "annual":     distribute annual_cut ONLY across future meetings via formula.
    mode == "h1h2":       distribute h1/h2 cuts ONLY across future H1/H2 meetings.
    mode == "per_meeting": direct bps per meeting {eff_date_str: bps}.

    IMPORTANT: In annual/h1h2 modes, weights are re-normalised to exclude past
    meetings. The FULL specified cut is applied to future meetings only.
    Past meetings always get cut=0 (their effect is already in base_sofr/effr).
    """
    meetings = FOMC_BY_YEAR.get(year, [])
    if not meetings:
        return {}

    today = date.today()
    n = len(meetings)   # typically 8
    cuts = [0.0] * n
    mode = year_config.get("mode", "annual")

    if mode == "per_meeting":
        # Direct per-meeting assignment — {effective_date_str: bps}
        per_meeting_cuts = year_config.get("per_meeting_cuts", {})
        result = {}
        for meeting in meetings:
            eff_str = meeting["effective_date"].isoformat()
            bps = float(per_meeting_cuts.get(eff_str, 0.0))
            result[meeting["effective_date"]] = bps
        return result

    if mode == "annual":
        total        = float(year_config.get("annual_cut", 0.0))
        formula_name = year_config.get("formula_name", "Uniform")
        custom_w     = year_config.get("custom_weights", None)
        weights      = _get_formula_weights(formula_name, custom_w)
        # Pad / trim to n meetings
        weights = (weights + [0.0] * n)[:n]

        # Distribute ONLY across future meetings
        future_mask = [m["effective_date"] > today for m in meetings]
        n_future = sum(future_mask)

        if n_future == 0:
            cuts = [0.0] * n
        else:
            # Zero out past meetings, re-normalise over future meetings
            future_w = [w if future_mask[i] else 0.0 for i, w in enumerate(weights)]
            total_w  = sum(future_w)
            if total_w == 0:
                # Formula gave 0 weight to all future meetings → uniform fallback
                future_w = [1.0 / n_future if future_mask[i] else 0.0 for i in range(n)]
                total_w  = 1.0
            norm_w = [w / total_w for w in future_w]
            cuts   = [round(total * w, 6) for w in norm_w]

    elif mode == "h1h2":
        h1_total   = float(year_config.get("h1_cut", 0.0) or 0.0)
        h2_total   = float(year_config.get("h2_cut", 0.0) or 0.0)
        h1_formula = year_config.get("h1_formula", "Uniform")
        h2_formula = year_config.get("h2_formula", "Uniform")
        h1_custom  = year_config.get("h1_custom_weights", None)
        h2_custom  = year_config.get("h2_custom_weights", None)

        h1_weights = _get_formula_weights(h1_formula, h1_custom)
        h2_weights = _get_formula_weights(h2_formula, h2_custom)

        h1_idx = [i for i in H1_MEETING_INDICES if i < n]
        h2_idx = [i for i in H2_MEETING_INDICES if i < n]

        # Filter to future meetings only within each half
        h1_future = [i for i in h1_idx if meetings[i]["effective_date"] > today]
        h2_future = [i for i in h2_idx if meetings[i]["effective_date"] > today]

        def _apply_half(total_bps, weights_list, all_idx, future_idx):
            if not future_idx:
                return
            sub = [weights_list[j] if j < len(weights_list) else 0.0
                   for j, _ in enumerate(all_idx)]
            future_sub = [sub[all_idx.index(i)] for i in future_idx]
            total_w = sum(future_sub)
            if total_w == 0:
                future_sub = [1.0 / len(future_idx)] * len(future_idx)
                total_w = 1.0
            for j, i in enumerate(future_idx):
                cuts[i] = round(total_bps * (future_sub[j] / total_w), 6)

        _apply_half(h1_total, h1_weights, h1_idx, h1_future)
        _apply_half(h2_total, h2_weights, h2_idx, h2_future)

    # Map cut to each meeting's effective_date
    result = {}
    for i, meeting in enumerate(meetings):
        result[meeting["effective_date"]] = cuts[i]

    return result


def build_rate_path(
    base_sofr: float,
    base_effr: float,
    year_configs: Dict[str, dict],
) -> tuple:
    """
    Compute cumulative SOFR / EFFR rate paths from year configs.

    CRITICAL: base_sofr / base_effr represent TODAY's live rate — they already
    incorporate all past FOMC decisions. Therefore we only include meetings
    whose effective_date is strictly AFTER today in the rate_path.
    Past meetings must NOT be in the path (would cause double-counting).

    Returns: (sofr_path, effr_path, meeting_cuts)
      sofr_path: {effective_date: new_sofr_level}  — only FUTURE meetings
      effr_path: {effective_date: new_effr_level}  — only FUTURE meetings
      meeting_cuts: {effective_date: bps_cut_applied} — ALL meetings (for display)
    """
    sofr_path    = {}
    effr_path    = {}
    meeting_cuts = {}  # ALL cuts (past + future) for analytics/display

    today = date.today()

    current_sofr = base_sofr
    current_effr = base_effr

    # Collect all (effective_date, bps_cut) tuples across all years
    all_cuts: Dict[date, float] = {}

    for year_str, year_cfg in sorted(year_configs.items()):
        year = int(year_str)
        year_cuts = compute_meeting_cuts_for_year(year, year_cfg)
        for eff_date, bps in year_cuts.items():
            all_cuts[eff_date] = bps

    # Build cumulative paths — ONLY for future meetings
    # Past meetings are skipped (their effect is already in base_sofr/base_effr)
    for eff_date in sorted(all_cuts.keys()):
        bps = all_cuts[eff_date]
        # Always record the cut for analytics display
        meeting_cuts[eff_date] = bps

        # Only add to rate_path if the meeting is FUTURE and has a non-zero cut.
        # Zero-cut meetings don't change the rate, so no entry needed.
        if eff_date > today and bps != 0.0:
            current_sofr = round(current_sofr + bps / 100.0, 6)  # bps → %
            current_effr = round(current_effr + bps / 100.0, 6)
            sofr_path[eff_date] = current_sofr
            effr_path[eff_date] = current_effr

    return sofr_path, effr_path, meeting_cuts


# ── Case Manager ──────────────────────────────────────────────────────────────

class CaseManager:
    """Manages the universe of scenario cases with file persistence."""

    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self.cases:    List[dict] = []
        self.formulas: List[dict] = self._default_formulas()
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _default_formulas(self) -> List[dict]:
        result = []
        for name, data in BUILTIN_FORMULAS.items():
            result.append({
                "name":        name,
                "description": data["description"],
                "weights":     data["weights"],
                "is_builtin":  True,
            })
        return result

    def _load(self):
        self.deleted_builtins = []
        if not os.path.exists(_CASES_FILE):
            self._save()
            return
        try:
            with open(_CASES_FILE, "r") as f:
                data = json.load(f)
            
            self.deleted_builtins = data.get("deleted_builtins", [])
            # Filter out deleted built-ins from self.formulas
            self.formulas = [f for f in self.formulas if f["name"] not in self.deleted_builtins]
            
            raw_cases = data.get("cases", [])
            self.cases = []
            for c in raw_cases:
                # Fast path: trust saved rate_path / meeting_cuts. Rebuilding
                # build_rate_path for every case on load made startup ~25 s
                # for 5,000 cases. We only rebuild when the saved data is
                # missing (legacy cases or external edits).
                saved_sofr = c.get("rate_path", {}).get("sofr") or {}
                saved_effr = c.get("rate_path", {}).get("effr") or {}
                saved_cuts = c.get("meeting_cuts") or {}

                if saved_sofr or saved_effr or saved_cuts:
                    c["rate_path"] = {
                        "sofr": _deserialise_path(saved_sofr),
                        "effr": _deserialise_path(saved_effr),
                    }
                    c["meeting_cuts"] = {
                        _str_date(k): v for k, v in saved_cuts.items()
                    }
                else:
                    sofr_path, effr_path, meeting_cuts = build_rate_path(
                        c["base_sofr"], c["base_effr"], c.get("year_configs", {})
                    )
                    c["rate_path"] = {"sofr": sofr_path, "effr": effr_path}
                    c["meeting_cuts"] = meeting_cuts
                self.cases.append(c)
            # Load custom formulas if any
            custom = data.get("custom_formulas", [])
            for cf in custom:
                if not any(f["name"] == cf["name"] for f in self.formulas):
                    self.formulas.append(cf)
        except Exception:
            self.cases = []

    def _save(self):
        serialised_cases = []
        for c in self.cases:
            sc = deepcopy(c)
            sc["rate_path"]["sofr"] = _serialise_path(sc["rate_path"]["sofr"])
            sc["rate_path"]["effr"] = _serialise_path(sc["rate_path"]["effr"])
            sc["meeting_cuts"] = {
                _date_str(k): v for k, v in sc["meeting_cuts"].items()
            }
            serialised_cases.append(sc)

        custom_formulas = [f for f in self.formulas if not f.get("is_builtin", False)]
        with open(_CASES_FILE, "w") as f:
            json.dump({
                "cases":           serialised_cases,
                "custom_formulas": custom_formulas,
                "deleted_builtins": getattr(self, "deleted_builtins", []),
            }, f, indent=2)

    # ── Case CRUD ─────────────────────────────────────────────────────────────

    def _next_id(self) -> str:
        """Generate a unique case ID that won't collide even after deletions."""
        if not self.cases:
            return "case_0001"
        existing_nums = set()
        for c in self.cases:
            try:
                # Extract numeric part from id like "case_0001"
                existing_nums.add(int(c["id"].split("_")[1]))
            except (IndexError, ValueError):
                pass
        n = max(existing_nums) + 1 if existing_nums else 1
        return f"case_{n:04d}"

    def add_case(
        self,
        name:         str,
        base_effr:    float,
        base_sofr:    float,
        year_configs: Dict[str, dict],
    ) -> dict:
        """Build a new case and append to the list."""
        sofr_path, effr_path, meeting_cuts = build_rate_path(
            base_sofr, base_effr, year_configs
        )
        case = {
            "id":           self._next_id(),
            "name":         name,
            "created_at":   datetime.now().isoformat(timespec="seconds"),
            "base_effr":    base_effr,
            "base_sofr":    base_sofr,
            "year_configs": year_configs,
            "rate_path":    {"sofr": sofr_path, "effr": effr_path},
            "meeting_cuts": meeting_cuts,
        }
        self.cases.append(case)
        self._save()
        return case

    def bulk_add_cases(self, specs: List[dict]) -> int:
        """
        Append many cases in a single batch (one disk write).

        specs: list of dicts with keys: name, base_effr, base_sofr, year_configs.
        Names that collide with existing cases are auto-suffixed with " (n)".
        Returns the number of cases added.
        """
        # Seed the id counter from existing cases so we never reuse ids.
        next_num = 0
        for c in self.cases:
            try:
                next_num = max(next_num, int(c["id"].split("_")[1]))
            except (IndexError, ValueError):
                pass

        existing_names = {c["name"] for c in self.cases}
        added = 0

        for spec in specs:
            # Avoid name collisions without dropping cases.
            name = spec["name"]
            if name in existing_names:
                k = 2
                while f"{name} ({k})" in existing_names:
                    k += 1
                name = f"{name} ({k})"
            existing_names.add(name)

            next_num += 1
            sofr_path, effr_path, meeting_cuts = build_rate_path(
                spec["base_sofr"], spec["base_effr"], spec["year_configs"]
            )
            self.cases.append({
                "id":           f"case_{next_num:04d}",
                "name":         name,
                "created_at":   datetime.now().isoformat(timespec="seconds"),
                "base_effr":    spec["base_effr"],
                "base_sofr":    spec["base_sofr"],
                "year_configs": spec["year_configs"],
                "rate_path":    {"sofr": sofr_path, "effr": effr_path},
                "meeting_cuts": meeting_cuts,
            })
            added += 1

        if added:
            self._save()
        return added

    def delete_case(self, case_id: str):
        self.cases = [c for c in self.cases if c["id"] != case_id]
        self._save()

    def delete_all_cases(self):
        self.cases = []
        self._save()

    def duplicate_case(self, case_id: str, new_name: str = None) -> Optional[dict]:
        orig = self.get_case(case_id)
        if not orig:
            return None
        return self.add_case(
            name         = new_name or f"{orig['name']} (copy)",
            base_effr    = orig["base_effr"],
            base_sofr    = orig["base_sofr"],
            year_configs = deepcopy(orig["year_configs"]),
        )

    def get_case(self, case_id: str) -> Optional[dict]:
        for c in self.cases:
            if c["id"] == case_id:
                return c
        return None

    def get_case_names(self) -> List[str]:
        return [f"{c['id']} | {c['name']}" for c in self.cases]

    # ── Formula CRUD ──────────────────────────────────────────────────────────

    def add_formula(self, name: str, weights: List[float], description: str = ""):
        """Add a custom distribution formula."""
        # normalise
        total = sum(weights)
        norm  = [w / total for w in weights] if total else weights
        self.formulas.append({
            "name":        name,
            "description": description,
            "weights":     norm,
            "is_builtin":  False,
        })
        self._save()
        
    def delete_formula(self, name: str):
        """Delete a formula by name. If it's builtin, track it so it doesn't return."""
        to_delete = next((f for f in self.formulas if f["name"] == name), None)
        if to_delete:
            if to_delete.get("is_builtin"):
                if not hasattr(self, "deleted_builtins"):
                    self.deleted_builtins = []
                self.deleted_builtins.append(name)
            self.formulas = [f for f in self.formulas if f["name"] != name]
            self._save()

    def get_formula_names(self) -> List[str]:
        return [f["name"] for f in self.formulas]

    def get_formula_weights(self, name: str) -> List[float]:
        for f in self.formulas:
            if f["name"] == name:
                return f["weights"]
        return [1/8] * 8

    # ── Meeting Range Analysis ────────────────────────────────────────────────

    def meeting_range_analysis(self) -> List[dict]:
        """
        For each FOMC meeting, compute across all cases:
          - min_cut, max_cut, mean_cut, mode_cut, range
        Returns list of dicts ordered by meeting date.
        """
        if not self.cases:
            return []

        meeting_data: Dict[date, List[float]] = {}

        for case in self.cases:
            for eff_date, bps in case["meeting_cuts"].items():
                if eff_date not in meeting_data:
                    meeting_data[eff_date] = []
                meeting_data[eff_date].append(bps)

        # Also add meetings with 0 cut (hold)
        for m in ALL_FOMC_MEETINGS:
            eff = m["effective_date"]
            if eff not in meeting_data:
                # All cases hold at this meeting → fill with zeros
                n_cases = len(self.cases)
                meeting_data[eff] = [0.0] * n_cases

        result = []
        for eff_date in sorted(meeting_data.keys()):
            vals = meeting_data[eff_date]
            # Find matching meeting info
            meeting_info = next(
                (m for m in ALL_FOMC_MEETINGS if m["effective_date"] == eff_date),
                None,
            )
            # mode: most common value
            from collections import Counter
            cnt  = Counter([round(v, 2) for v in vals])
            mode = cnt.most_common(1)[0][0]

            result.append({
                "decision_date":  meeting_info["decision_date"] if meeting_info else eff_date - __import__('datetime').timedelta(1),
                "effective_date": eff_date,
                "is_sep":         meeting_info["is_sep"] if meeting_info else False,
                "is_official":    meeting_info["is_official"] if meeting_info else False,
                "n_cases":        len(vals),
                "min_cut":        round(min(vals), 4),
                "max_cut":        round(max(vals), 4),
                "mean_cut":       round(sum(vals) / len(vals), 4),
                "mode_cut":       mode,
                "range":          round(max(vals) - min(vals), 4),
                "values":         vals,
            })

        return result
