#!/usr/bin/env python3
"""
generate_report.py — Blood test analysis and HTML report generator.

Phase 1: Data ingestion and normalization.
Phase 2: Deduplication and consolidation.
Phase 3: Marker catalog completion and status assessment.
Phase 4: Trend analysis.
Phase 5: Recommendations engine.
Phase 6: HTML report with Plotly charts.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

from marker_catalog import (
    GROUPS, GROUP_SPECIALIST, MARKER_SPECIALIST, MARKERS, resolve_marker_id,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

def _load_config() -> dict:
    """Load config.json if present, otherwise use defaults."""
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"WARNING: config.json is malformed, using defaults: {e}")
    return {}

_CFG = _load_config()
DATA_DIR = Path(_CFG.get("data_dir", _SCRIPT_DIR / "wynki_diag"))
PDF_DIR = Path(_CFG.get("pdf_dir", _SCRIPT_DIR / "wyniki_pdf"))
OUTPUT_PATH = Path(_CFG.get("output_path", "raport_zdrowotny.html"))
if not OUTPUT_PATH.is_absolute():
    OUTPUT_PATH = _SCRIPT_DIR / OUTPUT_PATH

for _label, _dir in [("data_dir", DATA_DIR), ("pdf_dir", PDF_DIR)]:
    if not _dir.is_dir():
        sys.exit(f"ERROR: {_label} directory does not exist: {_dir}")

LOG = logging.getLogger("smartdoc")

# Expected CSV columns
EXPECTED_COLS = {"Badanie", "Parametr", "Kod zlecenia", "Data", "Wynik",
                 "Zakres referencyjny", "Opis"}

# Regex for parsing Wynik: optional comparator, number, unit
# Examples: "2.1 mg/l", "<0.3 mg/l", ">60 ml/min/1,73m2", "0.79 mmol/l"
_RE_WYNIK = re.compile(
    r'^([<>≤≥]?)\s*'          # optional comparator
    r'(\d+(?:[.,]\d+)?)'      # numeric value (comma or dot decimal)
    r'(?:\s+(.+))?$'          # optional: space + unit (rest of string)
)

# Regex for parsing reference ranges: "low - high" or "< value" or "> value"
_RE_RANGE_PAIR = re.compile(
    r'^(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)$'
)
_RE_RANGE_SINGLE = re.compile(
    r'^([<>≤≥])\s*(\d+(?:[.,]\d+)?)$'
)

# Opis patterns that indicate method or reference range changes
_RE_METHOD_CHANGE = re.compile(
    r'zmiana\s+(metody|wartości\s+referencyjnych|zakresów\s+referencyjnych)',
    re.IGNORECASE
)


def _parse_decimal(s: str) -> float | None:
    """Parse a decimal string that may use comma as decimal separator."""
    if not s:
        return None
    return float(s.replace(",", "."))


# ---------------------------------------------------------------------------
# Phase 1a: Raw data loading
# ---------------------------------------------------------------------------

def load_raw_data(directory: Path = DATA_DIR) -> pd.DataFrame:
    """Read all CSV files from directory into a single DataFrame.

    Each row gets a `source_file` column with the originating filename.
    Validates that every file has the expected column schema.

    Returns
    -------
    DataFrame with columns:
        Badanie, Parametr, Kod zlecenia, Data, Wynik,
        Zakres referencyjny, Opis, source_file
    """
    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {directory}")

    frames: list[pd.DataFrame] = []
    skipped = 0

    for path in csv_files:
        try:
            df = pd.read_csv(
                path,
                sep=";",
                encoding="utf-8",
                dtype=str,         # keep everything as string for now
                quotechar='"',
                on_bad_lines="warn",
            )
        except Exception as exc:
            LOG.warning("Failed to read %s: %s", path.name, exc)
            skipped += 1
            continue

        # Strip whitespace from column names
        df.columns = df.columns.str.strip()

        # Validate schema
        missing = EXPECTED_COLS - set(df.columns)
        if missing:
            LOG.warning("File %s missing columns %s — skipping", path.name, missing)
            skipped += 1
            continue

        df["source_file"] = path.name
        frames.append(df)

    LOG.info("Loaded %d files (%d skipped)", len(frames), skipped)

    raw = pd.concat(frames, ignore_index=True)

    # Strip quoting artefacts from string columns
    str_cols = ["Badanie", "Parametr", "Wynik", "Zakres referencyjny", "Opis"]
    for col in str_cols:
        raw[col] = raw[col].fillna("").str.strip().str.strip('"')

    # Parse datetime
    raw["collected_at"] = pd.to_datetime(
        raw["Data"].str.strip(),
        format="%d-%m-%Y %H:%M:%S",
        errors="coerce",
    )
    raw["collected_date"] = raw["collected_at"].dt.date

    bad_dates = raw["collected_at"].isna().sum()
    if bad_dates:
        LOG.warning("%d rows with unparseable dates", bad_dates)

    # Rename for consistency
    raw = raw.rename(columns={
        "Kod zlecenia": "source_order_id",
        "Badanie": "source_badanie",
        "Opis": "source_notes",
    })

    raw["source_origin"] = "csv"

    return raw


def load_all_data() -> pd.DataFrame:
    """Load CSV data and, if available, PDF data; return combined DataFrame."""
    csv_df = load_raw_data()
    if PDF_DIR.exists():
        from pdf_parser import load_pdf_data
        pdf_df = load_pdf_data(PDF_DIR)
        if not pdf_df.empty:
            LOG.info("PDF data: %d rows from %d files",
                     len(pdf_df), pdf_df["source_file"].nunique())
            combined = pd.concat([csv_df, pdf_df], ignore_index=True)
            return combined
        else:
            LOG.info("PDF directory exists but yielded no data")
    return csv_df


# ---------------------------------------------------------------------------
# Phase 1b: Normalization
# ---------------------------------------------------------------------------

def _parse_wynik(wynik: str) -> tuple[str, float | None, str]:
    """Parse the Wynik field into (comparator, numeric_value, unit).

    Returns ("", None, "") if parsing fails.
    """
    wynik = wynik.strip()
    m = _RE_WYNIK.match(wynik)
    if not m:
        return ("", None, "")

    comparator = m.group(1)
    numeric = _parse_decimal(m.group(2))
    unit = (m.group(3) or "").strip()
    return (comparator, numeric, unit)


def _parse_lab_range(range_str: str) -> tuple[float | None, float | None]:
    """Parse 'Zakres referencyjny' into (lab_low, lab_high).

    Handles:
      "0.27 - 4.2"  → (0.27, 4.2)
      "< 150"       → (None, 150.0)
      "> 40"        → (40.0, None)
      "0 - 5"       → (0.0, 5.0)
      ""            → (None, None)
    """
    s = range_str.strip()
    if not s:
        return (None, None)

    # Try pair: "low - high"
    m = _RE_RANGE_PAIR.match(s)
    if m:
        low = _parse_decimal(m.group(1))
        high = _parse_decimal(m.group(2))
        return (low, high)

    # Try single: "< value" or "> value"
    m = _RE_RANGE_SINGLE.match(s)
    if m:
        op = m.group(1)
        val = _parse_decimal(m.group(2))
        if op in ("<", "≤"):
            return (None, val)
        if op in (">", "≥"):
            return (val, None)

    return (None, None)


def _detect_quality_flags(notes: str) -> list[str]:
    """Scan source_notes for data-quality signals."""
    flags = []
    if _RE_METHOD_CHANGE.search(notes):
        flags.append("method_or_range_change")
    return flags


def normalize_records(raw: pd.DataFrame) -> pd.DataFrame:
    """Transform raw CSV rows into normalized measurement records.

    Adds columns:
        marker_id, marker_label_pl, group, expression_type,
        raw_value, numeric_value, comparator, unit,
        lab_range_raw, lab_low, lab_high,
        quality_flags
    """
    records = []

    for _, row in raw.iterrows():
        parametr = row["Parametr"]
        wynik = row["Wynik"]
        range_raw = row["Zakres referencyjny"]
        notes = row["source_notes"]

        # Parse value
        comparator, numeric_value, unit = _parse_wynik(wynik)

        # Resolve marker
        marker_id = resolve_marker_id(parametr, unit)

        # Parse lab range
        lab_low, lab_high = _parse_lab_range(range_raw)

        # Quality flags
        quality_flags = _detect_quality_flags(notes)
        if comparator:
            quality_flags.append("threshold_value")

        # Look up marker metadata
        meta = MARKERS.get(marker_id, {})

        records.append({
            "marker_id":        marker_id,
            "marker_label_pl":  meta.get("label_pl", parametr),
            "group":            meta.get("group", "nieznana"),
            "expression_type":  meta.get("expression_type", "unknown"),
            "unit":             unit or meta.get("unit", ""),
            "collected_at":     row["collected_at"],
            "collected_date":   row["collected_date"],
            "raw_value":        wynik,
            "numeric_value":    numeric_value,
            "comparator":       comparator,
            "lab_range_raw":    range_raw,
            "lab_low":          lab_low,
            "lab_high":         lab_high,
            "source_file":      row["source_file"],
            "source_order_id":  row["source_order_id"],
            "source_badanie":   row["source_badanie"],
            "source_notes":     notes,
            "source_origin":    row.get("source_origin", "csv"),
            "quality_flags":    ";".join(quality_flags) if quality_flags else "",
        })

    df = pd.DataFrame(records)

    # Sort by date for reliable "latest" lookups
    df = df.sort_values("collected_at").reset_index(drop=True)

    # Report unmapped markers
    unmapped = df[df["marker_id"].isna()]["raw_value"].unique()
    if len(unmapped):
        unmapped_params = df[df["marker_id"].isna()]["marker_label_pl"].unique()
        LOG.warning("Unmapped markers (%d rows): %s", df["marker_id"].isna().sum(),
                    ", ".join(unmapped_params))

    return df


# ---------------------------------------------------------------------------
# Phase 2: Deduplication & consolidation
# ---------------------------------------------------------------------------

def _add_quality_flag(flags_str: str, new_flag: str) -> str:
    """Append a flag to a semicolon-separated quality_flags string."""
    if not flags_str:
        return new_flag
    existing = flags_str.split(";")
    if new_flag not in existing:
        existing.append(new_flag)
    return ";".join(existing)


def consolidate_measurements(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Deduplicate and consolidate normalized records.

    Three-step process per PLAN_ANALIZY.md dedup policy:
      1. Exact duplicates — same marker_id, collected_at, raw_value,
         source_order_id → keep first (removes (1)/(2) file copies).
      2. Same-day repeats — multiple measurements of same marker on same day
         with identical numeric_value → keep record with latest timestamp.
      3. Same-day conflicts — multiple measurements with different values
         on same day → keep latest timestamp, flag "same_day_conflict".

    Returns
    -------
    (consolidated_df, stats_dict)
    """
    n_input = len(df)

    # --- Step 1: Exact duplicates -------------------------------------------
    dedup_cols = ["marker_id", "collected_at", "raw_value", "source_order_id"]
    df = df.drop_duplicates(subset=dedup_cols, keep="first").reset_index(drop=True)
    n_after_exact = len(df)
    n_exact_removed = n_input - n_after_exact

    # --- Step 1b: CSV-preference for cross-source overlaps ------------------
    n_before_source_pref = len(df)
    if "source_origin" in df.columns:
        has_origin = ~df["marker_id"].isna() & ~df["collected_date"].isna()
        origin_groups = df[has_origin].groupby(["marker_id", "collected_date"], sort=False)
        drop_indices = []
        for (_mid, _dt), grp in origin_groups:
            origins = grp["source_origin"].unique()
            if len(origins) > 1 and "csv" in origins:
                # Keep only CSV rows when both CSV and PDF exist for same marker+day
                pdf_rows = grp[grp["source_origin"] == "pdf"].index
                drop_indices.extend(pdf_rows)
        if drop_indices:
            df = df.drop(index=drop_indices).reset_index(drop=True)
    n_source_pref_removed = n_before_source_pref - len(df)
    if n_source_pref_removed:
        LOG.info("CSV-preference dedup: removed %d PDF overlap rows", n_source_pref_removed)

    # --- Step 2 & 3: Same-day consolidation ---------------------------------
    keep_indices = []
    same_day_repeat_removed = 0
    same_day_conflict_removed = 0
    conflict_details: list[dict] = []

    # Pass through rows with NaN marker_id or collected_date (unmapped/bad date)
    na_mask = df["marker_id"].isna() | df["collected_date"].isna()
    keep_indices.extend(df[na_mask].index.tolist())

    grouped = df[~na_mask].groupby(["marker_id", "collected_date"], sort=False)

    for (marker_id, date), group in grouped:
        if len(group) == 1:
            keep_indices.append(group.index[0])
            continue

        # Multiple records for this marker on this day
        values = group["numeric_value"].dropna().unique()
        latest_idx = group["collected_at"].idxmax()
        keep_indices.append(latest_idx)
        n_extra = len(group) - 1

        if len(values) <= 1:
            # Same-day repeat: all values identical (or all NaN)
            same_day_repeat_removed += n_extra
        else:
            # Same-day conflict: different numeric values
            same_day_conflict_removed += n_extra
            conflict_details.append({
                "marker_id": marker_id,
                "date": date,
                "values": list(group["numeric_value"]),
                "kept_value": df.loc[latest_idx, "numeric_value"],
                "n_records": len(group),
            })

    df = df.loc[sorted(keep_indices)].reset_index(drop=True)

    # Flag conflict records in quality_flags
    for detail in conflict_details:
        mask = (
            (df["marker_id"] == detail["marker_id"])
            & (df["collected_date"] == detail["date"])
        )
        for idx in df[mask].index:
            df.at[idx, "quality_flags"] = _add_quality_flag(
                df.at[idx, "quality_flags"], "same_day_conflict"
            )

    n_output = len(df)

    stats = {
        "n_input": n_input,
        "n_exact_removed": n_exact_removed,
        "n_source_pref_removed": n_source_pref_removed,
        "n_after_exact": n_after_exact,
        "n_same_day_repeat_removed": same_day_repeat_removed,
        "n_same_day_conflict_removed": same_day_conflict_removed,
        "n_output": n_output,
        "conflict_details": conflict_details,
    }

    LOG.info("Consolidation: %d → %d records (-%d exact, -%d source_pref, -%d repeat, -%d conflict)",
             n_input, n_output, n_exact_removed, n_source_pref_removed,
             same_day_repeat_removed, same_day_conflict_removed)

    return df, stats


def print_phase2_summary(df: pd.DataFrame, stats: dict) -> None:
    """Print deduplication and consolidation summary."""
    print("\n" + "=" * 72)
    print("PHASE 2 — DEDUPLICATION & CONSOLIDATION SUMMARY")
    print("=" * 72)

    print(f"\nInput records:              {stats['n_input']}")
    print(f"Exact duplicates removed:   {stats['n_exact_removed']}")
    print(f"After exact dedup:          {stats['n_after_exact']}")
    print(f"Same-day repeats removed:   {stats['n_same_day_repeat_removed']}")
    print(f"Same-day conflicts resolved:{stats['n_same_day_conflict_removed']}")
    print(f"Output records:             {stats['n_output']}")

    # Conflict details
    conflicts = stats["conflict_details"]
    if conflicts:
        print(f"\n--- Same-day conflicts ({len(conflicts)}) ---")
        for c in conflicts:
            label = MARKERS.get(c["marker_id"], {}).get("label_pl", c["marker_id"])
            vals = ", ".join(f"{v}" for v in c["values"])
            print(f"  {label} on {c['date']}: [{vals}] → kept {c['kept_value']}")

    # Per-marker final counts
    print(f"\n--- Consolidated marker counts ---")
    counts = (
        df[df["marker_id"].notna()]
        .groupby(["group", "marker_id"])
        .agg(
            n=("marker_id", "size"),
            first_date=("collected_date", "min"),
            last_date=("collected_date", "max"),
            latest_value=("numeric_value", "last"),
        )
        .sort_values(["group", "marker_id"])
    )
    current_group = None
    for (group, mid), row in counts.iterrows():
        if group != current_group:
            current_group = group
            print(f"\n  [{group}]")
        label = MARKERS.get(mid, {}).get("label_pl", mid)
        print(f"    {label:40s}  n={row['n']:3d}  "
              f"{row['first_date']} → {row['last_date']}  "
              f"latest={row['latest_value']}")

    # Quality flags summary
    flagged = df[df["quality_flags"] != ""]
    if len(flagged):
        print(f"\n--- Quality flags ({len(flagged)} records) ---")
        all_flags: dict[str, int] = {}
        for flags_str in flagged["quality_flags"]:
            for f in flags_str.split(";"):
                all_flags[f] = all_flags.get(f, 0) + 1
        for flag, count in sorted(all_flags.items()):
            print(f"  {flag}: {count}")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Phase 3: Status assessment
# ---------------------------------------------------------------------------

# Margin for "GRANICA OPT" detection: value just outside the optimal range
# but within this fraction of the boundary is borderline rather than a clear
# deviation.  1% matches plan's hand-assigned status for Selen (99.62 vs 100).
# Values inside the optimal range are always OK — GRANICA only applies outside.
_GRANICA_MARGIN = 0.01


def assess_status(
    numeric_value: float | None,
    comparator: str,
    lab_low: float | None,
    lab_high: float | None,
    optimal_low: float | None,
    optimal_high: float | None,
) -> dict:
    """Compare a measurement against lab norms and optimal range.

    Returns
    -------
    dict with keys:
        status   — "OK", "POWYŻEJ NORMY", "PONIŻEJ NORMY",
                    "POWYŻEJ OPT", "PONIŻEJ OPT", "GRANICA OPT",
                    "BRAK DANYCH", "WARTOŚĆ PROGOWA"
        severity — "none", "low", "moderate", "high", "unknown"
        basis    — "lab", "optimal", "data_quality", "threshold"
        detail   — optional clarification string
    """
    # No numeric value at all
    if numeric_value is None:
        return {"status": "BRAK DANYCH", "severity": "unknown",
                "basis": "data_quality", "detail": ""}

    # --- Threshold values (<, >) — best-effort assessment ---
    if comparator in ("<", "≤"):
        # Actual value is below numeric_value.  If that's already under the
        # optimal ceiling (or optimal not defined), we can infer OK.
        effective_high = optimal_high if optimal_high is not None else lab_high
        if effective_high is not None and numeric_value <= effective_high:
            return {"status": "OK", "severity": "none",
                    "basis": "threshold", "detail": f"wartość {comparator}{numeric_value}"}
        return {"status": "WARTOŚĆ PROGOWA", "severity": "unknown",
                "basis": "threshold",
                "detail": f"wartość {comparator}{numeric_value}; nie można ocenić"}

    if comparator in (">", "≥"):
        effective_low = optimal_low if optimal_low is not None else lab_low
        if effective_low is not None and numeric_value >= effective_low:
            return {"status": "OK", "severity": "none",
                    "basis": "threshold", "detail": f"wartość {comparator}{numeric_value}"}
        return {"status": "WARTOŚĆ PROGOWA", "severity": "unknown",
                "basis": "threshold",
                "detail": f"wartość {comparator}{numeric_value}; nie można ocenić"}

    # --- Lab range check (takes priority — outside lab = most severe) ---
    if lab_low is not None and numeric_value < lab_low:
        return {"status": "PONIŻEJ NORMY", "severity": "high",
                "basis": "lab", "detail": ""}
    if lab_high is not None and numeric_value > lab_high:
        return {"status": "POWYŻEJ NORMY", "severity": "high",
                "basis": "lab", "detail": ""}

    # --- Optimal range check ---
    has_optimal = optimal_low is not None or optimal_high is not None
    if not has_optimal:
        # No optimal range defined — within lab range is the best we can say
        return {"status": "OK", "severity": "none",
                "basis": "lab", "detail": "brak zakresu optymalnego"}

    below_opt = optimal_low is not None and numeric_value < optimal_low
    above_opt = optimal_high is not None and numeric_value > optimal_high

    if below_opt:
        if _is_near_boundary(numeric_value, optimal_low):
            return {"status": "GRANICA OPT", "severity": "low",
                    "basis": "optimal", "detail": "blisko dolnej granicy"}
        return {"status": "PONIŻEJ OPT", "severity": "moderate",
                "basis": "optimal", "detail": ""}

    if above_opt:
        if _is_near_boundary(numeric_value, optimal_high):
            return {"status": "GRANICA OPT", "severity": "low",
                    "basis": "optimal", "detail": "blisko górnej granicy"}
        return {"status": "POWYŻEJ OPT", "severity": "moderate",
                "basis": "optimal", "detail": ""}

    # Within optimal range → OK (no inside-range GRANICA)
    return {"status": "OK", "severity": "none",
            "basis": "optimal", "detail": ""}


def _is_near_boundary(value: float, boundary: float) -> bool:
    """Check if value is within _GRANICA_MARGIN of boundary."""
    if boundary == 0:
        return False
    return abs(value - boundary) / abs(boundary) <= _GRANICA_MARGIN


def assess_all_statuses(df: pd.DataFrame) -> pd.DataFrame:
    """Get latest measurement per marker and assess status.

    Returns a DataFrame with one row per marker_id, including:
        all columns from the latest measurement row,
        plus: status, severity, basis, detail, optimal_low, optimal_high,
              source_type, source_label, evidence_level
    """
    # df is sorted by collected_at — .last() per group gives latest row.
    # Note: pandas .last() skips NaN for numeric columns, so lab_low/lab_high
    # may come from an earlier record if the latest has empty lab range.
    # This is acceptable — lab ranges are stable per marker and the carry-
    # forward gives better coverage than using only the latest record's range.
    latest = (
        df[df["marker_id"].notna()]
        .groupby("marker_id")
        .last()
        .reset_index()
    )

    statuses = []
    for _, row in latest.iterrows():
        mid = row["marker_id"]
        meta = MARKERS.get(mid, {})

        opt_low = meta.get("optimal_low")
        opt_high = meta.get("optimal_high")

        result = assess_status(
            numeric_value=row["numeric_value"],
            comparator=row["comparator"],
            lab_low=row["lab_low"],
            lab_high=row["lab_high"],
            optimal_low=opt_low,
            optimal_high=opt_high,
        )

        statuses.append({
            "marker_id": mid,
            "marker_label_pl": row["marker_label_pl"],
            "group": row["group"],
            "numeric_value": row["numeric_value"],
            "comparator": row["comparator"],
            "unit": row["unit"],
            "collected_date": row["collected_date"],
            "lab_low": row["lab_low"],
            "lab_high": row["lab_high"],
            "optimal_low": opt_low,
            "optimal_high": opt_high,
            "status": result["status"],
            "severity": result["severity"],
            "basis": result["basis"],
            "detail": result["detail"],
            "source_type": meta.get("source_type", ""),
            "source_label": meta.get("source_label", ""),
            "evidence_level": meta.get("evidence_level", ""),
        })

    return pd.DataFrame(statuses)


def _format_range(low, high) -> str:
    """Format a range as a human-readable string."""
    low_ok = low is not None and not (isinstance(low, float) and pd.isna(low))
    high_ok = high is not None and not (isinstance(high, float) and pd.isna(high))
    if low_ok and high_ok:
        return f"{low}-{high}"
    if low_ok:
        return f">{low}"
    if high_ok:
        return f"<{high}"
    return "—"


def print_phase3_summary(status_df: pd.DataFrame) -> None:
    """Print status assessment summary grouped by marker group."""
    print("\n" + "=" * 72)
    print("PHASE 3 — STATUS ASSESSMENT SUMMARY")
    print("=" * 72)

    # Group order from GROUPS keys
    group_order = list(GROUPS.keys())
    status_df = status_df.copy()
    status_df["_group_order"] = status_df["group"].map(
        {g: i for i, g in enumerate(group_order)}
    ).fillna(99)
    status_df = status_df.sort_values(["_group_order", "marker_id"])

    current_group = None
    counts = {"OK": 0, "GRANICA OPT": 0, "POWYŻEJ OPT": 0, "PONIŻEJ OPT": 0,
              "POWYŻEJ NORMY": 0, "PONIŻEJ NORMY": 0, "BRAK DANYCH": 0,
              "WARTOŚĆ PROGOWA": 0}

    for _, row in status_df.iterrows():
        group = row["group"]
        if group != current_group:
            current_group = group
            group_label = GROUPS.get(group, group)
            print(f"\n  [{group_label}]")

        label = row["marker_label_pl"]
        val = row["numeric_value"]
        comp = row["comparator"]
        unit = row["unit"]
        status = row["status"]
        basis = row["basis"]
        opt_range = _format_range(row["optimal_low"], row["optimal_high"])
        lab_range = _format_range(row["lab_low"], row["lab_high"])

        val_str = f"{comp}{val}" if comp else (f"{val}" if val is not None else "—")
        basis_tag = f"[{basis}]" if basis != "optimal" else ""

        print(f"    {label:35s}  {val_str:>10s} {unit:12s}  "
              f"lab:{lab_range:>12s}  opt:{opt_range:>12s}  "
              f"→ {status:16s} {basis_tag}")

        counts[status] = counts.get(status, 0) + 1

    # Summary counts
    print(f"\n--- Status distribution ---")
    for status, n in counts.items():
        if n > 0:
            print(f"  {status:20s}: {n}")
    print(f"  {'TOTAL':20s}: {len(status_df)}")

    # Highlight items requiring attention
    attention = status_df[status_df["severity"].isin(["high", "moderate"])]
    if len(attention):
        print(f"\n--- Requiring attention ({len(attention)}) ---")
        for _, row in attention.iterrows():
            sev = "⚠" if row["severity"] == "high" else "●"
            src = row["source_type"] if pd.notna(row["source_type"]) and row["source_type"] else "lab"
            print(f"  {sev} {row['marker_label_pl']:35s}  "
                  f"{row['status']:16s}  ({src})")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Phase 4: Trend analysis
# ---------------------------------------------------------------------------

# Minimum absolute delta% to consider a trend non-stable.
_STABLE_DELTA_PCT = 5.0

# Confidence thresholds
_HIGH_CONFIDENCE_N = 5
_HIGH_CONFIDENCE_R2 = 0.3
_HIGH_CONFIDENCE_SPAN_DAYS = 365


def _linear_regression(x: np.ndarray, y: np.ndarray) -> dict:
    """Fit y = slope*x + intercept via numpy.  Returns slope, intercept, r2."""
    coeffs = np.polyfit(x, y, 1)
    slope, intercept = coeffs[0], coeffs[1]
    y_pred = np.polyval(coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"slope": slope, "intercept": intercept, "r2": r2}


def _trend_confidence(n: int, r2: float, span_days: int) -> str:
    """Assign confidence level based on data quality signals."""
    if n < 2:
        return "none"
    if n < 3:
        return "low"
    if (n >= _HIGH_CONFIDENCE_N
            and r2 >= _HIGH_CONFIDENCE_R2
            and span_days >= _HIGH_CONFIDENCE_SPAN_DAYS):
        return "high"
    return "moderate"


def _interpret_direction(
    delta_pct: float,
    status: str,
) -> str:
    """Classify a trend as poprawa / pogorszenie / stabilny.

    Uses the current status to determine which direction is beneficial:
    - PONIŻEJ (NORMY or OPT): rising is improvement
    - POWYŻEJ (NORMY or OPT): falling is improvement
    - OK / GRANICA OPT / other: stable or moving toward optimal = poprawa
    """
    if abs(delta_pct) < _STABLE_DELTA_PCT:
        return "stabilny"

    rising = delta_pct > 0

    if "PONIŻEJ" in status:
        return "poprawa" if rising else "pogorszenie"
    if "POWYŻEJ" in status:
        return "poprawa" if not rising else "pogorszenie"

    # OK or GRANICA OPT — any significant movement away from OK could be
    # worsening, but we can't be sure without knowing which bound matters.
    # Report raw direction instead of a clinical judgment.
    return "wzrost" if rising else "spadek"


def analyze_trends(df: pd.DataFrame, status_df: pd.DataFrame) -> pd.DataFrame:
    """Compute trend statistics for each marker.

    Parameters
    ----------
    df : consolidated measurement DataFrame (all records, sorted by date)
    status_df : Phase 3 status DataFrame (one row per marker, latest status)

    Returns
    -------
    DataFrame with one row per marker_id:
        marker_id, marker_label_pl, group, n_measurements, first_date,
        last_date, span_days, first_value, last_value, delta_abs, delta_pct,
        slope_per_year, r2, confidence, direction, status
    """
    status_map = dict(zip(status_df["marker_id"], status_df["status"]))

    all_numeric = df[(df["marker_id"].notna()) & (df["numeric_value"].notna())].copy()
    # Count total observations (including thresholds) per marker — used for
    # recommendation wording so threshold-heavy markers like eGFR are not
    # described as "single measurement".
    total_obs_counts = all_numeric.groupby("marker_id").size()

    # Exclude threshold values — their numeric_value is a bound, not exact
    valid = all_numeric[all_numeric["comparator"] == ""].copy()

    results = []
    for marker_id, grp in valid.groupby("marker_id"):
        grp = grp.sort_values("collected_at")
        meta = MARKERS.get(marker_id, {})
        label = meta.get("label_pl", marker_id)
        group = meta.get("group", "nieznana")

        values = grp["numeric_value"].values
        dates = grp["collected_at"]
        n = len(values)

        first_date = dates.iloc[0].date() if hasattr(dates.iloc[0], "date") else dates.iloc[0]
        last_date = dates.iloc[-1].date() if hasattr(dates.iloc[-1], "date") else dates.iloc[-1]
        span_days = (dates.iloc[-1] - dates.iloc[0]).days

        first_val = values[0]
        last_val = values[-1]
        delta_abs = last_val - first_val
        if first_val != 0:
            delta_pct = delta_abs / abs(first_val) * 100
        elif last_val != 0:
            delta_pct = 100.0 if last_val > 0 else -100.0
        else:
            delta_pct = 0.0

        # Linear regression on days-since-first as x
        if n >= 2:
            x_days = np.array([(d - dates.iloc[0]).total_seconds() / 86400
                               for d in dates])
            reg = _linear_regression(x_days, values)
            slope_per_year = reg["slope"] * 365.25
            r2 = reg["r2"]
        else:
            slope_per_year = 0.0
            r2 = 0.0

        confidence = _trend_confidence(n, r2, span_days)
        status = status_map.get(marker_id, "")
        direction = _interpret_direction(delta_pct, status)

        results.append({
            "marker_id": marker_id,
            "marker_label_pl": label,
            "group": group,
            "n_measurements": n,
            "total_observations": int(total_obs_counts.get(marker_id, n)),
            "first_date": first_date,
            "last_date": last_date,
            "span_days": span_days,
            "first_value": first_val,
            "last_value": last_val,
            "delta_abs": round(delta_abs, 3),
            "delta_pct": round(delta_pct, 1),
            "slope_per_year": round(slope_per_year, 4),
            "r2": round(r2, 3),
            "confidence": confidence,
            "direction": direction,
            "status": status,
        })

    return pd.DataFrame(results)


def print_phase4_summary(trend_df: pd.DataFrame) -> None:
    """Print trend analysis summary."""
    print("\n" + "=" * 72)
    print("PHASE 4 — TREND ANALYSIS SUMMARY")
    print("=" * 72)

    # Confidence distribution
    conf_counts = trend_df["confidence"].value_counts()
    print(f"\n--- Confidence distribution ({len(trend_df)} markers with data) ---")
    for level in ["high", "moderate", "low", "none"]:
        if level in conf_counts.index:
            print(f"  {level:12s}: {conf_counts[level]}")

    # Group by direction
    dir_counts = trend_df["direction"].value_counts()
    print(f"\n--- Direction distribution ---")
    for d in ["poprawa", "pogorszenie", "stabilny", "wzrost", "spadek"]:
        if d in dir_counts.index:
            print(f"  {d:14s}: {dir_counts[d]}")

    # Detailed table by group
    group_order = list(GROUPS.keys())
    trend_df = trend_df.copy()
    trend_df["_group_order"] = trend_df["group"].map(
        {g: i for i, g in enumerate(group_order)}
    ).fillna(99)
    trend_df = trend_df.sort_values(["_group_order", "marker_id"])

    current_group = None
    for _, row in trend_df.iterrows():
        group = row["group"]
        if group != current_group:
            current_group = group
            group_label = GROUPS.get(group, group)
            print(f"\n  [{group_label}]")

        delta = row["delta_pct"]
        arrow_dir = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        quality = {"poprawa": "✓", "pogorszenie": "✗"}.get(row["direction"], "")
        arrow = f"{arrow_dir}{quality}" if quality else arrow_dir
        conf_tag = f"[{row['confidence']}]" if row["confidence"] != "high" else ""

        print(f"    {row['marker_label_pl']:35s}  n={row['n_measurements']:2d}  "
              f"{row['first_value']:>8.2f} → {row['last_value']:>8.2f}  "
              f"Δ={row['delta_pct']:+6.1f}%  R²={row['r2']:.2f}  "
              f"{arrow} {row['direction']:14s} {conf_tag}")

    # Highlight concerning trends (pogorszenie with moderate+ confidence)
    concerning = trend_df[
        (trend_df["direction"] == "pogorszenie")
        & (trend_df["confidence"].isin(["moderate", "high"]))
    ]
    if len(concerning):
        print(f"\n--- Concerning trends ({len(concerning)}) ---")
        for _, row in concerning.iterrows():
            a = "↑✗" if row["delta_pct"] > 0 else "↓✗"
            print(f"  {a} {row['marker_label_pl']:35s}  "
                  f"Δ={row['delta_pct']:+.1f}%  "
                  f"slope/yr={row['slope_per_year']:+.2f}  "
                  f"[{row['confidence']}]  status: {row['status']}")

    # Highlight improvements
    improving = trend_df[
        (trend_df["direction"] == "poprawa")
        & (trend_df["confidence"].isin(["moderate", "high"]))
    ]
    if len(improving):
        print(f"\n--- Improving trends ({len(improving)}) ---")
        for _, row in improving.iterrows():
            a = "↑✓" if row["delta_pct"] > 0 else "↓✓"
            print(f"  {a} {row['marker_label_pl']:35s}  "
                  f"Δ={row['delta_pct']:+.1f}%  "
                  f"slope/yr={row['slope_per_year']:+.2f}  "
                  f"[{row['confidence']}]  status: {row['status']}")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Phase 5: Recommendations engine
# ---------------------------------------------------------------------------

# Patient profile — used to contextualize recommendations.
PATIENT_PROFILE: dict = {
    "sex": "M",
    "age": 42,
    "activity": "1-2h dziennie",
    "supplements": ["D3+K2", "magnez", "omega-3", "kurkumina", "probiotyki"],
    "known_conditions": [],
}

# Recommendation categories (matches HTML report structure).
_CAT_MEDICAL = "medical"        # Pilne — konsultacja lekarska
_CAT_SUPPLEMENT = "supplement"  # Suplementacja
_CAT_DIET = "diet"              # Dieta
_CAT_LIFESTYLE = "lifestyle"    # Styl życia
_CAT_RETEST = "retest"          # Badania kontrolne

_PRIORITY_HIGH = "high"
_PRIORITY_MODERATE = "moderate"
_PRIORITY_LOW = "low"

_CATEGORY_LABELS_PL: dict[str, str] = {
    _CAT_MEDICAL: "Konsultacja lekarska",
    _CAT_SUPPLEMENT: "Suplementacja",
    _CAT_DIET: "Dieta",
    _CAT_LIFESTYLE: "Styl życia",
    _CAT_RETEST: "Badania kontrolne",
}


def _rec(
    category: str,
    priority: str,
    marker_ids: list[str],
    text_pl: str,
    rationale_pl: str,
    evidence: str = "",
    medical_escalation: bool = False,
    confidence: str = "moderate",
    specialist_pl: str = "",
    additional_tests_pl: list[str] | None = None,
    specialist_bucket_id: str = "",
    source_group: str = "",
) -> dict:
    """Build a recommendation dict."""
    return {
        "category": category,
        "priority": priority,
        "marker_ids": marker_ids,
        "text_pl": text_pl,
        "rationale_pl": rationale_pl,
        "evidence": evidence,
        "confidence": confidence,
        "medical_escalation": medical_escalation,
        "specialist_pl": specialist_pl,
        "additional_tests_pl": additional_tests_pl or [],
        "specialist_bucket_id": specialist_bucket_id,
        "source_group": source_group,
    }


def _norm_label(s: str) -> str:
    """Normalize a label for exact matching: lowercase + trim + collapse whitespace."""
    return " ".join(s.strip().lower().split())


def _filter_tests(
    tests: list[dict],
    tested_ids: set[str],
    tested_labels_norm: set[str],
) -> list[str]:
    """Filter additional tests against already-tested markers.

    Returns display labels of tests that should still be recommended.
    """
    result = []
    for t in tests:
        mid = t.get("marker_id")
        if mid and mid in tested_ids:
            continue
        aliases = t.get("filter_aliases") or []
        if any(_norm_label(alias) in tested_labels_norm for alias in aliases):
            continue
        result.append(t["label_pl"])
    return result


def _resolve_specialist_recs(
    group: str,
    markers: list[str],
    tested_marker_ids: set[str],
    tested_labels_norm: set[str],
) -> list[tuple[str, list[str], list[str]]]:
    """Return list of (specialist_pl, marker_subset, filtered_test_labels).

    One entry per distinct specialist. Splits markers in mixed-specialist groups.
    Delegates to _resolve_marker_specialist() for routing each marker.
    """
    specialist_buckets: dict[str, tuple[list[str], list[str]]] = {}

    for mid in markers:
        resolved = _resolve_marker_specialist(
            group, mid, tested_marker_ids, tested_labels_norm,
        )
        spec = resolved["specialist_pl"]
        if spec not in specialist_buckets:
            specialist_buckets[spec] = ([], resolved["additional_tests_pl"])
        specialist_buckets[spec][0].append(mid)

    return [
        (spec, spec_markers, filtered_tests)
        for spec, (spec_markers, filtered_tests) in specialist_buckets.items()
    ]


def _slugify_specialist_label(label: str) -> str:
    """Convert a Polish specialist display label to a filesystem-safe ASCII slug.

    Example: "diabetolog / endokrynolog" → "diabetolog_endokrynolog"
    """
    if not label:
        return ""
    import unicodedata
    # Transliterate Polish chars, strip accents
    nfkd = unicodedata.normalize("NFKD", label)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    # Replace separators and whitespace with underscores
    ascii_str = re.sub(r"[/\s]+", "_", ascii_str)
    # Remove anything that isn't alphanumeric or underscore
    ascii_str = re.sub(r"[^a-zA-Z0-9_]", "", ascii_str)
    # Collapse multiple underscores, strip leading/trailing
    ascii_str = re.sub(r"_+", "_", ascii_str).strip("_")
    return ascii_str.lower()


def _specialist_bucket_id(label: str) -> str:
    """Return a stable canonical ID for a specialist routing bucket.

    Uses _slugify_specialist_label under the hood. Empty label → empty string.
    """
    return _slugify_specialist_label(label)


def _resolve_marker_specialist(
    group: str,
    marker_id: str,
    tested_marker_ids: set[str],
    tested_labels_norm: set[str],
) -> dict:
    """Resolve the specialist routing for a single marker.

    Returns a dict with specialist_bucket_id, specialist_pl, marker_id, group,
    and additional_tests_pl (filtered against already-tested markers).
    """
    override = MARKER_SPECIALIST.get(marker_id)
    if override:
        spec = override["specialist_pl"]
        tests_raw = override.get("additional_tests", [])
    else:
        grp_info = GROUP_SPECIALIST.get(group, {})
        spec = grp_info.get("specialist_pl", "")
        tests_raw = grp_info.get("additional_tests", [])

    filtered_tests = _filter_tests(tests_raw, tested_marker_ids, tested_labels_norm)

    return {
        "specialist_bucket_id": _specialist_bucket_id(spec),
        "specialist_pl": spec,
        "marker_id": marker_id,
        "group": group,
        "additional_tests_pl": filtered_tests,
    }


def generate_recommendations(
    status_df: pd.DataFrame,
    trend_df: pd.DataFrame,
    profile: dict | None = None,
) -> pd.DataFrame:
    """Generate prioritized health recommendations.

    Rules are grouped by category.  Each rule inspects status_df / trend_df
    and emits zero or more recommendation dicts.  The engine never diagnoses —
    all out-of-lab-range findings are flagged for physician review.

    Returns DataFrame with columns: category, priority, marker_ids, text_pl,
    rationale_pl, evidence, confidence, medical_escalation.
    """
    if profile is None:
        profile = PATIENT_PROFILE

    recs: list[dict] = []

    # --- helpers ---
    def _status(mid: str) -> str:
        rows = status_df[status_df["marker_id"] == mid]
        return rows.iloc[0]["status"] if len(rows) else ""

    def _trend(mid: str) -> pd.Series | None:
        rows = trend_df[trend_df["marker_id"] == mid]
        return rows.iloc[0] if len(rows) else None

    def _latest(mid: str) -> float | None:
        rows = status_df[status_df["marker_id"] == mid]
        if len(rows) and pd.notna(rows.iloc[0]["numeric_value"]):
            return float(rows.iloc[0]["numeric_value"])
        return None

    def _status_of(mid: str) -> str:
        rows = status_df[status_df["marker_id"] == mid]
        return rows.iloc[0]["status"] if len(rows) else ""

    def _label(mid: str) -> str:
        meta = MARKERS.get(mid, {})
        label = meta.get("label_pl", mid)
        # Disambiguate abs/pct variants that share the same label_pl
        # (e.g., Neutrofile abs vs Neutrofile %)
        expr = meta.get("expression_type", "")
        if expr in ("abs", "pct"):
            unit = meta.get("unit", "")
            if unit:
                label = f"{label} [{unit}]"
        return label

    supplements = {s.lower() for s in profile.get("supplements", [])}

    # ===================================================================
    # MEDICAL — all markers outside lab range → consult doctor
    # ===================================================================

    # Pre-compute CBC declining pattern for deduplication
    cbc_declining = ["leukocyty__abs", "limfocyty__abs", "neutrofile__abs"]
    cbc_bad = [
        m for m in cbc_declining
        if (_status(m) == "PONIŻEJ NORMY"
            and _trend(m) is not None
            and _trend(m)["direction"] == "pogorszenie"
            and _trend(m)["confidence"] in ("moderate", "high"))
    ]
    suppressed_generic_markers = set(cbc_bad) if len(cbc_bad) >= 2 else set()

    # Build sets for additional-test filtering
    tested_marker_ids = set(status_df["marker_id"])
    tested_labels_norm = {
        _norm_label(MARKERS[mid].get("label_pl", ""))
        for mid in tested_marker_ids
        if mid in MARKERS and MARKERS[mid].get("label_pl")
    }

    out_of_lab = status_df[
        status_df["status"].isin(["PONIŻEJ NORMY", "POWYŻEJ NORMY"])
    ]
    if len(out_of_lab):
        for group, grp_rows in out_of_lab.groupby("group"):
            markers = list(grp_rows["marker_id"])

            # Suppress markers handled by the CBC escalation rec
            markers = [m for m in markers if m not in suppressed_generic_markers]
            if not markers:
                continue

            # Resolve specialist routing (may split into multiple recs)
            spec_recs = _resolve_specialist_recs(
                group, markers, tested_marker_ids, tested_labels_norm,
            )

            for specialist_pl, spec_markers, extra_tests in spec_recs:
                spec_labels = [_label(m) for m in spec_markers]
                spec_statuses = [
                    grp_rows[grp_rows["marker_id"] == m].iloc[0]["status"]
                    for m in spec_markers
                ]
                details = ", ".join(
                    f"{lab} ({st.lower()})"
                    for lab, st in zip(spec_labels, spec_statuses)
                )

                trend_cache = {m: _trend(m) for m in spec_markers}
                worsening = [
                    m for m in spec_markers
                    if (trend_cache[m] is not None
                        and trend_cache[m]["direction"] == "pogorszenie"
                        and trend_cache[m]["confidence"] in ("moderate", "high"))
                ]

                priority = _PRIORITY_HIGH if worsening else _PRIORITY_MODERATE
                trend_note = ""
                if worsening:
                    trend_note = (
                        " Trend pogorszenia potwierdzony dla: "
                        + ", ".join(_label(m) for m in worsening)
                        + "."
                    )

                nuance = ""
                if ("testosteron__direct" in spec_markers
                        and "testosteron__direct" in worsening):
                    nuance += (
                        " Uwaga: wysoki testosteron u aktywnego mężczyzny "
                        "42 lat może być fizjologicznie prawidłowy — "
                        "ocenić klinicznie."
                    )
                if ("cholesterol_calkowity__direct" in spec_markers
                        and len(spec_markers) == 1):
                    ch_val = _latest("cholesterol_calkowity__direct")
                    ch_rows = status_df[
                        status_df["marker_id"] == "cholesterol_calkowity__direct"
                    ]
                    if ch_val is not None and len(ch_rows):
                        ch_high = ch_rows.iloc[0]["lab_high"]
                        _ok_statuses = {"OK", "GRANICA OPT"}
                        ldl_status = _status_of("cholesterol_ldl__direct")
                        apob_status = _status_of("apo_b__direct")
                        ldl_ok = ldl_status in _ok_statuses
                        apob_ok = apob_status in _ok_statuses
                        if ch_high and ch_val < ch_high * 1.02:
                            if ldl_ok and apob_ok:
                                nuance += (
                                    " Wartość minimalnie powyżej górnej "
                                    "granicy normy — klinicznie mało istotne "
                                    "przy prawidłowym LDL i Apo B."
                                )
                                priority = _PRIORITY_LOW
                            else:
                                nuance += (
                                    " Wartość minimalnie powyżej górnej "
                                    "granicy normy, jednak LDL i/lub Apo B "
                                    "powyżej optimum — ocenić łącznie profil "
                                    "lipidowy."
                                )

                group_label = GROUPS.get(group, group)
                if specialist_pl:
                    text = (
                        f"Konsultacja — {specialist_pl}: wyniki spoza normy "
                        f"laboratoryjnej ({group_label}): "
                        f"{details}.{trend_note}{nuance}"
                    )
                else:
                    text = (
                        f"Omówić z lekarzem wyniki spoza normy laboratoryjnej "
                        f"({group_label}): {details}.{trend_note}{nuance}"
                    )

                recs.append(_rec(
                    category=_CAT_MEDICAL,
                    priority=priority,
                    marker_ids=spec_markers,
                    text_pl=text,
                    rationale_pl=(
                        "Wartości poza zakresem referencyjnym laboratorium "
                        "wymagają oceny klinicznej."
                    ),
                    evidence="Norma laboratoryjna",
                    medical_escalation=True,
                    confidence="high",
                    specialist_pl=specialist_pl,
                    additional_tests_pl=extra_tests,
                    specialist_bucket_id=_specialist_bucket_id(specialist_pl),
                    source_group=group,
                ))

    # --- CBC declining pattern — extra emphasis ---
    if len(cbc_bad) >= 2:
        cbc_extra_tests = _filter_tests(
            GROUP_SPECIALIST.get("morfologia", {}).get("additional_tests", []),
            tested_marker_ids,
            tested_labels_norm,
        )
        recs.append(_rec(
            category=_CAT_MEDICAL,
            priority=_PRIORITY_HIGH,
            marker_ids=cbc_bad,
            text_pl=(
                "Priorytetowa konsultacja hematologiczna: "
                "jednoczesny spadek leukocytów, limfocytów i/lub neutrofili "
                "poniżej normy z potwierdzonym trendem spadkowym. "
                "Wskazana pełna diagnostyka przyczyn leukopenii."
            ),
            rationale_pl=(
                "Współistniejąca leukopenia, limfopenia i neutropenia "
                "z trendem pogorszenia mogą wskazywać na przyczynę wymagającą "
                "dalszej diagnostyki (np. wirusową, autoimmunologiczną, "
                "szpikową)."
            ),
            evidence="Kliniczna ocena morfologii",
            medical_escalation=True,
            confidence="high",
            specialist_pl="hematolog",
            additional_tests_pl=cbc_extra_tests,
            specialist_bucket_id=_specialist_bucket_id("hematolog"),
            source_group="morfologia",
        ))

    # ===================================================================
    # SUPPLEMENT — actionable supplementation advice
    # ===================================================================

    # Homocysteine above optimal → B-vitamins
    if "POWYŻEJ" in _status("homocysteina__direct"):
        val = _latest("homocysteina__direct")
        val_str = f" ({val:.1f} µmol/l)" if val else ""
        recs.append(_rec(
            category=_CAT_SUPPLEMENT,
            priority=_PRIORITY_MODERATE,
            marker_ids=["homocysteina__direct"],
            text_pl=(
                f"Rozważyć suplementację witamin B6, B12 (metylokobalamina) "
                f"i kwasu foliowego (metylofolian) w celu obniżenia "
                f"homocysteiny{val_str}."
            ),
            rationale_pl=(
                "Podwyższona homocysteina jest markerem ryzyka "
                "sercowo-naczyniowego i często odpowiada na suplementację "
                "witamin z grupy B."
            ),
            evidence="Medycyna prewencyjna; meta-analizy B-witamin i Hcy",
            confidence="moderate",
        ))

    # Magnesium suboptimal despite supplementation
    if "PONIŻEJ" in _status("magnez__direct") and "magnez" in supplements:
        val = _latest("magnez__direct")
        val_str = f" ({val:.2f} mmol/l)" if val else ""
        recs.append(_rec(
            category=_CAT_SUPPLEMENT,
            priority=_PRIORITY_MODERATE,
            marker_ids=["magnez__direct"],
            text_pl=(
                f"Magnez{val_str} poniżej optimum mimo suplementacji. "
                f"Rozważyć zmianę formy (np. glicynian, taurynian magnezu) "
                f"lub zwiększenie dawki. Optymalnie 0.85-1.0 mmol/l."
            ),
            rationale_pl=(
                "Magnez w surowicy nie zawsze odzwierciedla zapasy "
                "wewnątrzkomórkowe, ale wartość poniżej optimum mimo "
                "suplementacji sugeruje niewystarczającą dawkę lub formę."
            ),
            evidence="Medycyna prewencyjna",
            confidence="moderate",
        ))

    # Zinc below optimal
    if "PONIŻEJ" in _status("cynk__direct"):
        val = _latest("cynk__direct")
        val_str = f" ({val:.0f} µg/dl)" if val else ""
        recs.append(_rec(
            category=_CAT_SUPPLEMENT,
            priority=_PRIORITY_LOW,
            marker_ids=["cynk__direct"],
            text_pl=(
                f"Cynk{val_str} poniżej optimum (80-120 µg/dl). "
                f"Rozważyć suplementację cynku (15-30 mg/d, np. pikolinian "
                f"lub bis-glicynian), najlepiej z miedzią w proporcji 15:1."
            ),
            rationale_pl=(
                "Niedobór cynku wpływa na odporność, funkcje hormonalne "
                "i regenerację. Suplementacja cynku bez miedzi może "
                "zaburzać równowagę Cu/Zn."
            ),
            evidence="Medycyna prewencyjna",
            confidence="moderate",
        ))

    # Vitamin D — positive reinforcement if OK
    if _status("witamina_d3__direct") == "OK":
        recs.append(_rec(
            category=_CAT_SUPPLEMENT,
            priority=_PRIORITY_LOW,
            marker_ids=["witamina_d3__direct"],
            text_pl=(
                "Witamina D3 w zakresie optymalnym — kontynuować "
                "obecną suplementację D3+K2."
            ),
            rationale_pl="Suplementacja skuteczna, poziom optymalny.",
            evidence="Endocrine Society 2024",
            confidence="high",
        ))

    # Selenium borderline
    if "GRANICA" in _status("selen__direct") or "PONIŻEJ" in _status("selen__direct"):
        val = _latest("selen__direct")
        val_str = f" ({val:.0f} µg/l)" if val else ""
        recs.append(_rec(
            category=_CAT_SUPPLEMENT,
            priority=_PRIORITY_LOW,
            marker_ids=["selen__direct"],
            text_pl=(
                f"Selen{val_str} na granicy lub poniżej optimum "
                f"(100-140 µg/l). Rozważyć suplementację selenometioniny "
                f"100-200 µg/d lub zwiększenie spożycia orzechów brazylijskich."
            ),
            rationale_pl=(
                "Selen wspiera funkcję tarczycy i odporność. "
                "Przy TSH powyżej optimum szczególnie istotny."
            ),
            evidence="Medycyna prewencyjna",
            confidence="low",
        ))

    # ===================================================================
    # DIET — dietary recommendations
    # ===================================================================

    # Lipid profile: LDL / ApoB / nie-HDL above optimal
    lipid_above = [
        m for m in ("cholesterol_ldl__direct", "apo_b__direct",
                     "cholesterol_nie_hdl__direct")
        if "POWYŻEJ" in _status(m)
    ]
    if lipid_above:
        labels = ", ".join(_label(m) for m in lipid_above)
        recs.append(_rec(
            category=_CAT_DIET,
            priority=_PRIORITY_MODERATE,
            marker_ids=lipid_above,
            text_pl=(
                f"Optymalizacja profilu lipidowego ({labels}): "
                f"zwiększyć spożycie błonnika rozpuszczalnego "
                f"(owies, nasiona lnu, babka płesznik), steroli roślinnych, "
                f"orzechów i ryb tłustych. Ograniczyć tłuszcze nasycone. "
                f"Obecna suplementacja omega-3 wspiera profil lipidowy."
            ),
            rationale_pl=(
                "LDL, Apo B i nie-HDL powyżej zakresów optymalnych "
                "zwiększają ryzyko sercowo-naczyniowe. Dieta to pierwszy "
                "krok interwencji."
            ),
            evidence="ESC/EAS 2021",
            confidence="high",
        ))

    # HbA1c above optimal — glycemic management
    if "POWYŻEJ" in _status("hba1c__direct"):
        val = _latest("hba1c__direct")
        val_str = f" ({val:.1f}%)" if val else ""
        recs.append(_rec(
            category=_CAT_DIET,
            priority=_PRIORITY_MODERATE,
            marker_ids=["hba1c__direct"],
            text_pl=(
                f"HbA1c{val_str} powyżej optimum (<5.4%). "
                f"Ograniczyć rafinowane węglowodany i cukry proste. "
                f"Priorytetyzować posiłki z niskim indeksem glikemicznym, "
                f"białkiem i tłuszczem. Rozważyć monitoring CGM."
            ),
            rationale_pl=(
                "HbA1c 5.7% to próg prediabetes wg ADA. Interwencja "
                "dietetyczna i ruchowa jest najskuteczniejsza na tym etapie."
            ),
            evidence="ADA Standards of Care; medycyna prewencyjna",
            confidence="moderate",
        ))

    # Potassium above optimal — dietary note
    if "POWYŻEJ" in _status("potas__direct"):
        trend = _trend("potas__direct")
        if trend is not None and trend["direction"] == "pogorszenie":
            recs.append(_rec(
                category=_CAT_DIET,
                priority=_PRIORITY_LOW,
                marker_ids=["potas__direct"],
                text_pl=(
                    "Potas z trendem wzrostowym powyżej optimum. "
                    "Monitorować spożycie potasu w diecie (banany, "
                    "ziemniaki, pomidory). Omówić z lekarzem przy "
                    "kolejnej wizycie."
                ),
                rationale_pl=(
                    "Potas powyżej optimum z trendem wzrostowym wymaga "
                    "uwagi, choć wartość w normie lab nie jest alarmująca."
                ),
                evidence="Medycyna prewencyjna",
                confidence="low",
            ))

    # ===================================================================
    # LIFESTYLE — lifestyle recommendations
    # ===================================================================

    # TSH above optimal — thyroid support
    if "POWYŻEJ" in _status("tsh__direct"):
        tsh_val = _latest("tsh__direct")
        tsh_trend = _trend("tsh__direct")
        trend_note = ""
        rationale_detail = ""
        if tsh_trend is not None and tsh_trend["direction"] == "pogorszenie":
            trend_note = " Trend wzrostowy potwierdza dryfowanie w górę."
            rationale_detail = (
                f"TSH {tsh_val:.2f} z trendem wzrostowym "
                f"(R²={tsh_trend['r2']:.2f})"
            ) if tsh_val else "TSH z trendem wzrostowym"
        else:
            rationale_detail = (
                f"TSH {tsh_val:.2f}" if tsh_val else "TSH"
            )
        recs.append(_rec(
            category=_CAT_LIFESTYLE,
            priority=_PRIORITY_MODERATE,
            marker_ids=["tsh__direct", "ft4__direct"],
            text_pl=(
                f"TSH powyżej optimum (0.5-2.0).{trend_note} "
                f"Zadbać o odpowiedni selen, jod i cynk w diecie. "
                f"Unikać nadmiernego stresu i niedoboru snu, które "
                f"mogą pogarszać funkcję tarczycy. Kontrola FT3 "
                f"przy następnym badaniu."
            ),
            rationale_pl=(
                f"{rationale_detail} może wskazywać na subkliniczną "
                f"niedoczynność tarczycy wymagającą obserwacji."
            ),
            evidence="Medycyna prewencyjna / ATA 2017",
            confidence="moderate",
        ))

    # HbA1c — exercise emphasis (complements diet recommendation)
    if "POWYŻEJ" in _status("hba1c__direct"):
        recs.append(_rec(
            category=_CAT_LIFESTYLE,
            priority=_PRIORITY_LOW,
            marker_ids=["hba1c__direct", "glukoza__direct"],
            text_pl=(
                "Obecna aktywność fizyczna (1-2h/dzień) jest doskonała "
                "i kluczowa dla kontroli glikemii. Rozważyć dodanie "
                "krótkich spacerów po posiłkach (10-15 min) dla "
                "wygładzenia skoków glukozy poposiłkowej."
            ),
            rationale_pl=(
                "Aktywność fizyczna po posiłkach obniża glikemię "
                "poposiłkową nawet o 30%."
            ),
            evidence="Diabetologia 2022; medycyna prewencyjna",
            confidence="moderate",
        ))

    # eGFR below optimal — hydration and context
    if "PONIŻEJ" in _status("egfr__calculated"):
        egfr_val = _latest("egfr__calculated")
        egfr_str = f" ({egfr_val:.0f})" if egfr_val else ""
        recs.append(_rec(
            category=_CAT_LIFESTYLE,
            priority=_PRIORITY_LOW,
            marker_ids=["egfr__calculated", "kreatynina__direct"],
            text_pl=(
                f"eGFR{egfr_str} poniżej optimum (>90 ml/min/1,73m²). "
                f"Zadbać o odpowiednie nawodnienie (min. 2-2.5l wody/dzień). "
                f"U osób z dużą masą mięśniową eGFR może być zaniżone "
                f"przez wyższą kreatynynę — interpretować w kontekście."
            ),
            rationale_pl=(
                "eGFR 60-90 to stadium G2 wg KDIGO, często bez znaczenia "
                "klinicznego u aktywnych fizycznie mężczyzn z wyższą masą "
                "mięśniową. Nawodnienie wpływa na kreatynynę i eGFR."
            ),
            evidence="KDIGO 2024",
            confidence="moderate",
        ))

    # Iron declining — monitoring note (relevant to CBC pattern)
    fe_trend = _trend("zelazo__direct")
    if (fe_trend is not None
            and fe_trend["direction"] == "spadek"
            and fe_trend["confidence"] in ("moderate", "high")
            and abs(fe_trend["delta_pct"]) >= 10):
        fe_val = _latest("zelazo__direct")
        fe_str = f" ({fe_val:.0f} µg/dl)" if fe_val else ""
        recs.append(_rec(
            category=_CAT_LIFESTYLE,
            priority=_PRIORITY_LOW,
            marker_ids=["zelazo__direct", "erytrocyty__abs",
                         "hemoglobina__direct"],
            text_pl=(
                f"Żelazo{fe_str} z trendem spadkowym "
                f"({fe_trend['delta_pct']:+.0f}%). Mimo wartości "
                f"w normie, spadek żelaza w kontekście obniżonych "
                f"erytrocytów zasługuje na uwagę. Rozważyć dietę "
                f"bogatą w żelazo hemowe (czerwone mięso, wątróbka) "
                f"i witaminę C wspomagającą wchłanianie."
            ),
            rationale_pl=(
                "Spadek żelaza w połączeniu z erytrocytami poniżej normy "
                "może sugerować początkowy niedobór żelaza. Warto "
                "monitorować ferrytynę i TIBC przy następnym badaniu."
            ),
            evidence="Medycyna prewencyjna",
            confidence="low",
        ))

    # SHBG high — lifestyle note
    if _status("shbg__direct") == "POWYŻEJ NORMY":
        recs.append(_rec(
            category=_CAT_LIFESTYLE,
            priority=_PRIORITY_LOW,
            marker_ids=["shbg__direct", "testosteron_wolny__direct"],
            text_pl=(
                "SHBG powyżej normy — może obniżać biodostępność "
                "testosteronu. Rozważyć ocenę statusu wątrobowego "
                "(SHBG produkowane w wątrobie) i poziomu estrogenów. "
                "Utrzymywać odpowiedni poziom tkanki tłuszczowej "
                "i unikać nadmiernych restrykcji kalorycznych."
            ),
            rationale_pl=(
                "Wysokie SHBG wiąże testosteron, obniżając frakcję "
                "wolną. Przy testosteronie całkowitym 894 ng/dl "
                "klinicznie może nie stanowić problemu, ale warto "
                "monitorować."
            ),
            evidence="Medycyna prewencyjna",
            confidence="low",
        ))

    # ===================================================================
    # RETEST — markers worth retesting
    # ===================================================================

    # Worsening trends with low/moderate confidence → retest
    retest_worsening = trend_df[
        (trend_df["direction"] == "pogorszenie")
        & (trend_df["confidence"].isin(["low", "moderate"]))
    ]
    if len(retest_worsening):
        markers = list(retest_worsening["marker_id"])
        labels = ", ".join(_label(m) for m in markers)
        recs.append(_rec(
            category=_CAT_RETEST,
            priority=_PRIORITY_MODERATE,
            marker_ids=markers,
            text_pl=(
                f"Powtórzyć badania z trendem pogorszenia i umiarkowaną "
                f"pewnością, aby potwierdzić lub wykluczyć trend: {labels}."
            ),
            rationale_pl=(
                "Trendy oparte na mniejszej liczbie pomiarów wymagają "
                "potwierdzenia kolejnym badaniem."
            ),
            evidence="Metodologia analizy trendów",
            confidence="moderate",
        ))

    # Single-measurement markers with abnormal status → retest
    # Use total_observations (includes thresholds) so markers like eGFR with
    # many threshold readings are not falsely described as "single measurement".
    total_obs_col = "total_observations" if "total_observations" in trend_df.columns else "n_measurements"
    single_abnormal = trend_df[
        (trend_df[total_obs_col] == 1)
        & (trend_df["status"].str.contains("PONIŻEJ|POWYŻEJ", na=False))
    ]
    if len(single_abnormal):
        markers = list(single_abnormal["marker_id"])
        labels = ", ".join(_label(m) for m in markers)
        recs.append(_rec(
            category=_CAT_RETEST,
            priority=_PRIORITY_MODERATE,
            marker_ids=markers,
            text_pl=(
                f"Powtórzyć badania z pojedynczym pomiarem i statusem "
                f"nieprawidłowym: {labels}. Pojedynczy wynik nie pozwala "
                f"ocenić, czy odchylenie jest trwałe."
            ),
            rationale_pl=(
                "Przy jednorazowym pomiarze nie można wykluczyć "
                "czynników przejściowych (nawodnienie, pora dnia, stres)."
            ),
            evidence="Metodologia analizy trendów",
            confidence="moderate",
        ))

    # CBC retest if concerning
    cbc_retest = [
        m for m in ("leukocyty__abs", "limfocyty__abs", "neutrofile__abs",
                     "erytrocyty__abs")
        if "PONIŻEJ NORMY" == _status(m)
    ]
    if cbc_retest:
        recs.append(_rec(
            category=_CAT_RETEST,
            priority=_PRIORITY_HIGH,
            marker_ids=cbc_retest,
            text_pl=(
                "Kontrolna morfologia za 4-6 tygodni w celu potwierdzenia "
                "utrzymujących się cytopenii i oceny dynamiki zmian."
            ),
            rationale_pl=(
                "Markery poniżej normy z trendem spadkowym wymagają "
                "powtórzenia w krótkim odstępie."
            ),
            evidence="Praktyka kliniczna",
            medical_escalation=True,
            confidence="high",
        ))

    # Thyroid panel — if TSH drifting, add FT3
    if "POWYŻEJ" in _status("tsh__direct"):
        recs.append(_rec(
            category=_CAT_RETEST,
            priority=_PRIORITY_LOW,
            marker_ids=["tsh__direct", "ft4__direct"],
            text_pl=(
                "Przy kolejnym badaniu tarczycy uwzględnić FT3 "
                "i anty-TPO/anty-TG, aby wykluczyć autoimmunologiczną "
                "chorobę tarczycy (Hashimoto)."
            ),
            rationale_pl=(
                "TSH powyżej optimum z trendem wzrostowym wymaga "
                "poszerzenia diagnostyki tarczycowej."
            ),
            evidence="ATA 2017",
            confidence="moderate",
        ))

    # --- Sort by priority and category ---
    priority_order = {_PRIORITY_HIGH: 0, _PRIORITY_MODERATE: 1, _PRIORITY_LOW: 2}
    category_order = {
        _CAT_MEDICAL: 0, _CAT_DIET: 1, _CAT_SUPPLEMENT: 2,
        _CAT_LIFESTYLE: 3, _CAT_RETEST: 4,
    }
    recs.sort(key=lambda r: (
        priority_order.get(r["priority"], 9),
        category_order.get(r["category"], 9),
    ))

    return pd.DataFrame(recs) if recs else pd.DataFrame(
        columns=["category", "priority", "marker_ids", "text_pl",
                 "rationale_pl", "evidence", "confidence",
                 "medical_escalation", "specialist_pl",
                 "additional_tests_pl", "specialist_bucket_id",
                 "source_group"]
    )


def print_phase5_summary(rec_df: pd.DataFrame) -> None:
    """Print recommendation summary."""
    print("\n" + "=" * 72)
    print("PHASE 5 — RECOMMENDATIONS SUMMARY")
    print("=" * 72)

    if rec_df.empty:
        print("\n  No recommendations generated.")
        print("\n" + "=" * 72)
        return

    print(f"\nTotal recommendations: {len(rec_df)}")
    print(f"  Medical escalation: "
          f"{rec_df['medical_escalation'].sum()}")

    # By priority
    print(f"\n--- By priority ---")
    for p in [_PRIORITY_HIGH, _PRIORITY_MODERATE, _PRIORITY_LOW]:
        n = (rec_df["priority"] == p).sum()
        if n:
            print(f"  {p:12s}: {n}")

    # Print all, grouped by category
    for cat in [_CAT_MEDICAL, _CAT_DIET, _CAT_SUPPLEMENT,
                _CAT_LIFESTYLE, _CAT_RETEST]:
        cat_recs = rec_df[rec_df["category"] == cat]
        if cat_recs.empty:
            continue
        cat_label = _CATEGORY_LABELS_PL.get(cat, cat)
        print(f"\n{'━' * 60}")
        print(f"  {cat_label.upper()}")
        print(f"{'━' * 60}")

        for idx, (_, row) in enumerate(cat_recs.iterrows(), 1):
            esc = " 🏥" if row["medical_escalation"] else ""
            pri = {"high": "❗", "moderate": "●", "low": "○"}.get(
                row["priority"], " ")
            print(f"\n  {pri} [{row['priority']}]{esc}")
            print(f"    {row['text_pl']}")
            print(f"    ➤ {row['rationale_pl']}")
            if row["evidence"]:
                print(f"    📎 {row['evidence']}")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Specialist report generation
# ---------------------------------------------------------------------------

def build_specialist_report_specs(
    rec_df: pd.DataFrame,
    status_df: pd.DataFrame,
) -> list[dict]:
    """Build specialist report specifications from triggered medical recommendations.

    Walks all tested markers and routes each through the specialist resolution
    helper. Includes a marker in a report only if its resolved bucket matches
    a triggered consultation bucket.

    Returns a list of spec dicts sorted by specialist_bucket_id.
    """
    if rec_df.empty:
        return []

    # Step 1: Find triggered specialist buckets from medical recommendations
    medical = rec_df[
        (rec_df["category"] == _CAT_MEDICAL)
        & (rec_df["specialist_bucket_id"].astype(str).str.len() > 0)
    ]
    if medical.empty:
        return []

    # Collect trigger info per bucket
    bucket_triggers: dict[str, dict] = {}
    for _, row in medical.iterrows():
        bid = row["specialist_bucket_id"]
        if bid not in bucket_triggers:
            bucket_triggers[bid] = {
                "specialist_bucket_id": bid,
                "specialist_pl": row["specialist_pl"],
                "trigger_marker_ids": [],
                "additional_tests_pl": [],
                "source_groups": [],
            }
        bucket_triggers[bid]["trigger_marker_ids"].extend(row["marker_ids"])
        bucket_triggers[bid]["additional_tests_pl"].extend(row["additional_tests_pl"])
        if row["source_group"] and row["source_group"] not in bucket_triggers[bid]["source_groups"]:
            bucket_triggers[bid]["source_groups"].append(row["source_group"])

    triggered_bucket_ids = set(bucket_triggers.keys())

    # Step 2: Build sets for additional-test filtering
    tested_marker_ids = set(status_df["marker_id"])
    tested_labels_norm = {
        _norm_label(MARKERS[mid].get("label_pl", ""))
        for mid in tested_marker_ids
        if mid in MARKERS and MARKERS[mid].get("label_pl")
    }

    # Step 3: Route every tested marker and assign to buckets
    bucket_markers: dict[str, list[str]] = {bid: [] for bid in triggered_bucket_ids}
    bucket_groups: dict[str, list[str]] = {bid: [] for bid in triggered_bucket_ids}

    for _, srow in status_df.iterrows():
        mid = srow["marker_id"]
        group = srow["group"]
        resolved = _resolve_marker_specialist(
            group, mid, tested_marker_ids, tested_labels_norm,
        )
        bid = resolved["specialist_bucket_id"]
        if bid in triggered_bucket_ids:
            if mid not in bucket_markers[bid]:
                bucket_markers[bid].append(mid)
            if group not in bucket_groups[bid]:
                bucket_groups[bid].append(group)

    # Step 4: Assemble specs
    group_order = {g: i for i, g in enumerate(GROUPS.keys())}
    specs = []
    for bid in sorted(triggered_bucket_ids):
        report_marker_ids = bucket_markers[bid]
        if not report_marker_ids:
            continue

        trigger_info = bucket_triggers[bid]
        # Deduplicate trigger_marker_ids preserving order
        seen = set()
        dedup_triggers = []
        for m in trigger_info["trigger_marker_ids"]:
            if m not in seen:
                seen.add(m)
                dedup_triggers.append(m)

        # Deduplicate additional_tests_pl preserving first-seen order
        seen_tests: set[str] = set()
        dedup_tests: list[str] = []
        for t in trigger_info["additional_tests_pl"]:
            if t not in seen_tests:
                seen_tests.add(t)
                dedup_tests.append(t)

        # Merge source_groups from triggers + routed markers, sorted by GROUPS order
        all_groups = list(trigger_info["source_groups"])
        for g in bucket_groups[bid]:
            if g not in all_groups:
                all_groups.append(g)
        all_groups.sort(key=lambda g: group_order.get(g, 999))

        specs.append({
            "specialist_bucket_id": bid,
            "specialist_pl": trigger_info["specialist_pl"],
            "trigger_marker_ids": dedup_triggers,
            "report_marker_ids": report_marker_ids,
            "source_groups": all_groups,
            "additional_tests_pl": dedup_tests,
        })

    return specs


def build_specialist_context(
    spec: dict,
    df: pd.DataFrame,
    status_df: pd.DataFrame,
    trend_df: pd.DataFrame,
) -> dict:
    """Build template context for a single specialist report.

    Reuses the same status/trend/chart logic as the main report.
    """
    marker_set = set(spec["report_marker_ids"])
    trigger_set = set(spec["trigger_marker_ids"])

    # Filter status_df to report markers only
    spec_status = status_df[status_df["marker_id"].isin(marker_set)].copy()

    # Build marker sections grouped by source group
    group_order = list(GROUPS.keys())
    sections = []

    for group_key in group_order:
        if group_key not in spec["source_groups"]:
            continue
        grp_status = spec_status[spec_status["group"] == group_key]
        if grp_status.empty:
            continue

        markers_data = []
        for _, srow in grp_status.iterrows():
            mid = srow["marker_id"]
            trend_rows = trend_df[trend_df["marker_id"] == mid]
            trend_row = trend_rows.iloc[0] if len(trend_rows) else None

            chart_html = generate_plotly_chart(df, mid, srow)

            val = srow["numeric_value"]
            comp = srow["comparator"]
            val_str = (
                f"{comp}{val}" if comp
                else (f"{val}" if val is not None and pd.notna(val) else "—")
            )

            markers_data.append({
                "marker_id": mid,
                "label": srow["marker_label_pl"],
                "value_str": val_str,
                "unit": srow["unit"],
                "lab_range": _format_range(srow["lab_low"], srow["lab_high"]),
                "opt_range": _format_range(
                    srow.get("optimal_low"), srow.get("optimal_high"),
                ),
                "status": srow["status"],
                "status_color": _STATUS_COLORS.get(srow["status"], "#94a3b8"),
                "status_icon": _STATUS_ICONS.get(srow["status"], ""),
                "severity": srow["severity"],
                "is_trigger": mid in trigger_set,
                "n_measurements": (
                    int(trend_row.get("total_observations",
                                      trend_row["n_measurements"]))
                    if trend_row is not None else 1
                ),
                "direction": (
                    trend_row["direction"] if trend_row is not None else ""
                ),
                "direction_arrow": (
                    "" if trend_row is not None and trend_row["direction"] == "stabilny"
                    else _DIRECTION_ARROWS.get(trend_row["direction"], "")
                    if trend_row is not None else ""
                ),
                "direction_color": (
                    _DIRECTION_COLORS.get(trend_row["direction"], "#64748b")
                    if trend_row is not None else "#64748b"
                ),
                "math_arrow": (
                    "↑" if trend_row is not None and trend_row["delta_pct"] > 0
                    else "↓" if trend_row is not None and trend_row["delta_pct"] < 0
                    else "→" if trend_row is not None
                    else ""
                ),
                "delta_pct": (
                    f"{trend_row['delta_pct']:+.1f}%"
                    if trend_row is not None else ""
                ),
                "confidence": (
                    trend_row["confidence"] if trend_row is not None else "none"
                ),
                "chart_html": chart_html,
                "collected_date": str(srow["collected_date"]),
            })

        sections.append({
            "group_key": group_key,
            "group_label": GROUPS[group_key],
            "markers": markers_data,
        })

    # Build trigger marker labels for the rationale section
    trigger_markers = []
    for mid in spec["trigger_marker_ids"]:
        meta = MARKERS.get(mid, {})
        label = meta.get("label_pl", mid)
        rows = status_df[status_df["marker_id"] == mid]
        status = rows.iloc[0]["status"] if len(rows) else ""
        trigger_markers.append({"label": label, "status": status})

    return {
        "report_date": date.today().isoformat(),
        "specialist_bucket_id": spec["specialist_bucket_id"],
        "specialist_pl": spec["specialist_pl"],
        "trigger_markers": trigger_markers,
        "source_groups": [
            {"key": g, "label": GROUPS.get(g, g)}
            for g in spec["source_groups"]
        ],
        "marker_sections": sections,
        "additional_tests": spec["additional_tests_pl"],
        "total_markers": sum(len(s["markers"]) for s in sections),
    }


# ---------------------------------------------------------------------------
# Phase 6: HTML report with Plotly charts
# ---------------------------------------------------------------------------

# Status → CSS class / display colour
_STATUS_COLORS: dict[str, str] = {
    "OK": "#22c55e",
    "GRANICA OPT": "#eab308",
    "POWYŻEJ OPT": "#f97316",
    "PONIŻEJ OPT": "#f97316",
    "POWYŻEJ NORMY": "#ef4444",
    "PONIŻEJ NORMY": "#ef4444",
    "BRAK DANYCH": "#94a3b8",
    "WARTOŚĆ PROGOWA": "#94a3b8",
}

_STATUS_ICONS: dict[str, str] = {
    "OK": "✓",
    "GRANICA OPT": "~",
    "POWYŻEJ OPT": "↑",
    "PONIŻEJ OPT": "↓",
    "POWYŻEJ NORMY": "⬆",
    "PONIŻEJ NORMY": "⬇",
    "BRAK DANYCH": "?",
    "WARTOŚĆ PROGOWA": "~",
}

_DIRECTION_ARROWS: dict[str, str] = {
    "poprawa": "✓",
    "pogorszenie": "✗",
    "stabilny": "→",
    "wzrost": "",
    "spadek": "",
}

_DIRECTION_COLORS: dict[str, str] = {
    "poprawa": "#22c55e",
    "pogorszenie": "#ef4444",
    "stabilny": "#64748b",
    "wzrost": "#64748b",
    "spadek": "#64748b",
}

_PRIORITY_LABELS_PL: dict[str, str] = {
    "high": "Pilne",
    "moderate": "Umiarkowane",
    "low": "Niskie",
}


def generate_plotly_chart(
    df: pd.DataFrame,
    marker_id: str,
    status_row: pd.Series | None = None,
) -> str:
    """Generate an interactive Plotly line chart for a single marker.

    Shows measurement points connected by lines, with horizontal bands for
    lab range (light red) and optimal range (light green).

    Parameters
    ----------
    df : consolidated measurement DataFrame (all records)
    marker_id : which marker to chart
    status_row : optional Phase 3 status row for range info

    Returns
    -------
    HTML div string (Plotly's to_html with include_plotlyjs=False).
    """
    mdf = df[(df["marker_id"] == marker_id) & (df["numeric_value"].notna())].copy()
    if mdf.empty:
        return ""

    mdf = mdf.sort_values("collected_at")
    meta = MARKERS.get(marker_id, {})
    label = meta.get("label_pl", marker_id)
    unit = meta.get("unit", "")

    # Separate exact and threshold measurements
    exact = mdf[mdf["comparator"] == ""]
    threshold = mdf[mdf["comparator"] != ""]

    fig = go.Figure()

    # --- Range bands ---
    dates_all = mdf["collected_at"]
    x_min = dates_all.min()
    x_max = dates_all.max()
    lab_low = status_row["lab_low"] if status_row is not None else None
    lab_high = status_row["lab_high"] if status_row is not None else None
    opt_low = status_row.get("optimal_low") if status_row is not None else None
    opt_high = status_row.get("optimal_high") if status_row is not None else None

    # Determine y-axis range for bands
    all_vals = mdf["numeric_value"].tolist()
    range_vals = [v for v in [lab_low, lab_high, opt_low, opt_high]
                  if v is not None and pd.notna(v)]
    all_for_range = all_vals + range_vals
    y_min_data = min(all_for_range)
    y_max_data = max(all_for_range)
    y_margin = (y_max_data - y_min_data) * 0.15 if y_max_data != y_min_data else 1
    y_lo = y_min_data - y_margin
    y_hi = y_max_data + y_margin

    def _notna(v):
        return v is not None and pd.notna(v)

    # Lab range band (light red, semi-transparent, outside only)
    if _notna(lab_low) and _notna(lab_high):
        # Draw as two bands: below lab_low and above lab_high
        fig.add_hrect(y0=y_lo, y1=lab_low, fillcolor="#fecaca",
                      opacity=0.3, line_width=0,
                      annotation_text="poniżej normy", annotation_position="bottom left")
        fig.add_hrect(y0=lab_high, y1=y_hi, fillcolor="#fecaca",
                      opacity=0.3, line_width=0,
                      annotation_text="powyżej normy", annotation_position="top left")
    elif _notna(lab_high):
        fig.add_hrect(y0=lab_high, y1=y_hi, fillcolor="#fecaca",
                      opacity=0.3, line_width=0)
    elif _notna(lab_low):
        fig.add_hrect(y0=y_lo, y1=lab_low, fillcolor="#fecaca",
                      opacity=0.3, line_width=0)

    # Optimal range band (light green)
    if _notna(opt_low) and _notna(opt_high):
        fig.add_hrect(y0=opt_low, y1=opt_high, fillcolor="#bbf7d0",
                      opacity=0.3, line_width=0)
    elif _notna(opt_high) and _notna(lab_low):
        fig.add_hrect(y0=lab_low, y1=opt_high, fillcolor="#bbf7d0",
                      opacity=0.3, line_width=0)
    elif _notna(opt_low) and _notna(lab_high):
        fig.add_hrect(y0=opt_low, y1=lab_high, fillcolor="#bbf7d0",
                      opacity=0.3, line_width=0)

    # Lab range boundary lines
    if _notna(lab_low):
        fig.add_hline(y=lab_low, line_dash="dash", line_color="#ef4444",
                      line_width=1, opacity=0.6)
    if _notna(lab_high):
        fig.add_hline(y=lab_high, line_dash="dash", line_color="#ef4444",
                      line_width=1, opacity=0.6)
    # Optimal boundary lines
    if _notna(opt_low):
        fig.add_hline(y=opt_low, line_dash="dot", line_color="#22c55e",
                      line_width=1, opacity=0.6)
    if _notna(opt_high):
        fig.add_hline(y=opt_high, line_dash="dot", line_color="#22c55e",
                      line_width=1, opacity=0.6)

    # --- Data traces ---
    if not exact.empty:
        fig.add_trace(go.Scatter(
            x=exact["collected_at"],
            y=exact["numeric_value"],
            mode="lines+markers",
            name=label,
            line=dict(color="#2563eb", width=2),
            marker=dict(size=7, color="#2563eb"),
            hovertemplate=f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:.2f}} {unit}<extra></extra>",
        ))

    if not threshold.empty:
        fig.add_trace(go.Scatter(
            x=threshold["collected_at"],
            y=threshold["numeric_value"],
            mode="markers",
            name=f"{label} (próg)",
            marker=dict(size=7, color="#94a3b8", symbol="diamond-open"),
            hovertemplate=(
                f"%{{x|%Y-%m-%d}}<br>{label}: "
                + "%{text}<extra>(wartość progowa)</extra>"
            ),
            text=[f"{row['comparator']}{row['numeric_value']}" for _, row in threshold.iterrows()],
        ))

    fig.update_layout(
        title=None,
        xaxis_title=None,
        yaxis_title=unit if unit else None,
        height=220,
        margin=dict(l=50, r=20, t=10, b=30),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        xaxis=dict(gridcolor="#f1f5f9"),
        yaxis=dict(gridcolor="#f1f5f9", range=[y_lo, y_hi]),
        font=dict(size=11),
    )

    return fig.to_html(include_plotlyjs=False, full_html=False, div_id=f"chart-{marker_id}")


def _build_group_sections(
    df: pd.DataFrame,
    status_df: pd.DataFrame,
    trend_df: pd.DataFrame,
) -> list[dict]:
    """Build per-group section data for the template."""
    group_order = list(GROUPS.keys())
    sections = []

    for group_key in group_order:
        group_label = GROUPS[group_key]
        grp_status = status_df[status_df["group"] == group_key].copy()
        if grp_status.empty:
            continue

        markers_data = []
        for _, srow in grp_status.iterrows():
            mid = srow["marker_id"]
            trend_rows = trend_df[trend_df["marker_id"] == mid]
            trend_row = trend_rows.iloc[0] if len(trend_rows) else None

            chart_html = generate_plotly_chart(df, mid, srow)

            val = srow["numeric_value"]
            comp = srow["comparator"]
            val_str = f"{comp}{val}" if comp else (f"{val}" if val is not None and pd.notna(val) else "—")

            markers_data.append({
                "marker_id": mid,
                "label": srow["marker_label_pl"],
                "value_str": val_str,
                "unit": srow["unit"],
                "lab_range": _format_range(srow["lab_low"], srow["lab_high"]),
                "opt_range": _format_range(srow.get("optimal_low"), srow.get("optimal_high")),
                "status": srow["status"],
                "status_color": _STATUS_COLORS.get(srow["status"], "#94a3b8"),
                "status_icon": _STATUS_ICONS.get(srow["status"], ""),
                "severity": srow["severity"],
                "n_measurements": int(trend_row.get("total_observations", trend_row["n_measurements"])) if trend_row is not None else 1,
                "direction": trend_row["direction"] if trend_row is not None else "",
                "direction_arrow": (
                    "" if trend_row["direction"] == "stabilny"
                    else _DIRECTION_ARROWS.get(trend_row["direction"], "")
                ) if trend_row is not None else "",
                "direction_color": _DIRECTION_COLORS.get(
                    trend_row["direction"], "#64748b") if trend_row is not None else "#64748b",
                "math_arrow": (
                    "↑" if trend_row["delta_pct"] > 0
                    else "↓" if trend_row["delta_pct"] < 0
                    else "→"
                ) if trend_row is not None else "",
                "delta_pct": f"{trend_row['delta_pct']:+.1f}%" if trend_row is not None else "",
                "confidence": trend_row["confidence"] if trend_row is not None else "none",
                "chart_html": chart_html,
                "collected_date": str(srow["collected_date"]),
            })

        # Group summary stats
        n_ok = sum(1 for m in markers_data if m["status"] == "OK")
        n_attention = sum(1 for m in markers_data if m["severity"] in ("high", "moderate"))

        sections.append({
            "group_key": group_key,
            "group_label": group_label,
            "markers": markers_data,
            "n_markers": len(markers_data),
            "n_ok": n_ok,
            "n_attention": n_attention,
        })

    return sections


def _build_dashboard(status_df: pd.DataFrame, trend_df: pd.DataFrame) -> dict:
    """Build dashboard summary statistics."""
    total = len(status_df)
    ok = (status_df["status"] == "OK").sum()
    borderline = (status_df["status"] == "GRANICA OPT").sum()
    above_opt = status_df["status"].isin(["POWYŻEJ OPT", "PONIŻEJ OPT"]).sum()
    out_of_lab = status_df["status"].isin(["POWYŻEJ NORMY", "PONIŻEJ NORMY"]).sum()

    worsening = trend_df[
        (trend_df["direction"] == "pogorszenie")
        & (trend_df["confidence"].isin(["moderate", "high"]))
    ]
    improving = trend_df[
        (trend_df["direction"] == "poprawa")
        & (trend_df["confidence"].isin(["moderate", "high"]))
    ]

    return {
        "total_markers": total,
        "ok_count": int(ok),
        "borderline_count": int(borderline),
        "suboptimal_count": int(above_opt),
        "out_of_lab_count": int(out_of_lab),
        "ok_pct": round(ok / total * 100) if total else 0,
        "worsening_count": len(worsening),
        "improving_count": len(improving),
    }


def _build_recommendations_context(rec_df: pd.DataFrame) -> dict:
    """Structure recommendations for the template."""
    if rec_df.empty:
        return {"categories": [], "total": 0, "escalation_count": 0}

    categories = []
    for cat in [_CAT_MEDICAL, _CAT_DIET, _CAT_SUPPLEMENT,
                _CAT_LIFESTYLE, _CAT_RETEST]:
        cat_recs = rec_df[rec_df["category"] == cat]
        if cat_recs.empty:
            continue
        items = []
        for _, row in cat_recs.iterrows():
            item = {
                "priority": row["priority"],
                "priority_label": _PRIORITY_LABELS_PL.get(row["priority"], row["priority"]),
                "text": row["text_pl"],
                "rationale": row["rationale_pl"],
                "evidence": row["evidence"],
                "medical_escalation": bool(row["medical_escalation"]),
                "confidence": row["confidence"],
                "specialist": row.get("specialist_pl", ""),
                "additional_tests": row.get("additional_tests_pl", []),
            }
            items.append(item)
        categories.append({
            "key": cat,
            "label": _CATEGORY_LABELS_PL.get(cat, cat),
            "items": items,
        })

    return {
        "categories": categories,
        "total": len(rec_df),
        "escalation_count": int(rec_df["medical_escalation"].sum()),
    }


def _build_quality_context(df: pd.DataFrame) -> dict:
    """Build data quality section info."""
    flagged = df[df["quality_flags"] != ""]
    flag_counts: dict[str, int] = {}
    for flags_str in flagged["quality_flags"]:
        for f in flags_str.split(";"):
            flag_counts[f] = flag_counts.get(f, 0) + 1

    threshold_markers = df[df["comparator"] != ""]["marker_id"].nunique()

    return {
        "total_records": len(df),
        "flagged_records": len(flagged),
        "flag_counts": flag_counts,
        "threshold_markers": threshold_markers,
        "date_min": str(df["collected_date"].min()),
        "date_max": str(df["collected_date"].max()),
        "n_files": df["source_file"].nunique(),
    }


def _build_trends_summary(trend_df: pd.DataFrame) -> dict:
    """Build trend summary for dedicated trends section."""
    worsening = trend_df[
        (trend_df["direction"] == "pogorszenie")
        & (trend_df["confidence"].isin(["moderate", "high"]))
    ].copy()
    improving = trend_df[
        (trend_df["direction"] == "poprawa")
        & (trend_df["confidence"].isin(["moderate", "high"]))
    ].copy()
    stable = trend_df[trend_df["direction"] == "stabilny"].copy()

    def _rows_to_list(sub):
        items = []
        for _, r in sub.iterrows():
            dp = r["delta_pct"]
            items.append({
                "label": r["marker_label_pl"],
                "delta_pct": f"{dp:+.1f}%",
                "confidence": r["confidence"],
                "status": r["status"],
                "direction_arrow": "" if r["direction"] == "stabilny" else _DIRECTION_ARROWS.get(r["direction"], ""),
                "math_arrow": "↑" if dp > 0 else "↓" if dp < 0 else "→",
            })
        return items

    return {
        "worsening": _rows_to_list(worsening),
        "improving": _rows_to_list(improving),
        "stable_count": len(stable),
    }


def render_html(
    df: pd.DataFrame,
    status_df: pd.DataFrame,
    trend_df: pd.DataFrame,
    rec_df: pd.DataFrame,
) -> str:
    """Render the full HTML report.

    Returns the complete HTML string ready to be saved to a file.
    """
    template_dir = Path(__file__).parent
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
    )
    template = env.get_template("report_template.html")

    context = {
        "report_date": date.today().isoformat(),
        "patient": PATIENT_PROFILE,
        "dashboard": _build_dashboard(status_df, trend_df),
        "sections": _build_group_sections(df, status_df, trend_df),
        "trends": _build_trends_summary(trend_df),
        "recommendations": _build_recommendations_context(rec_df),
        "quality": _build_quality_context(df),
        "groups": GROUPS,
    }

    return template.render(**context)


def render_specialist_html(
    spec: dict,
    df: pd.DataFrame,
    status_df: pd.DataFrame,
    trend_df: pd.DataFrame,
) -> str:
    """Render a single specialist consultation report as HTML."""
    context = build_specialist_context(spec, df, status_df, trend_df)

    template_dir = Path(__file__).parent
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
    )
    template = env.get_template("report_specialist_template.html")
    return template.render(**context)


def generate_specialist_reports(
    rec_df: pd.DataFrame,
    df: pd.DataFrame,
    status_df: pd.DataFrame,
    trend_df: pd.DataFrame,
) -> list[Path]:
    """Generate specialist consultation reports for all triggered buckets.

    Returns list of written file paths.
    """
    specs = build_specialist_report_specs(rec_df, status_df)
    if not specs:
        return []

    output_dir = OUTPUT_PATH.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    report_date = date.today().isoformat()

    written: list[Path] = []
    for spec in specs:
        html = render_specialist_html(spec, df, status_df, trend_df)
        filename = f"raport_konsultacja_{spec['specialist_bucket_id']}_{report_date}.html"
        path = output_dir / filename
        path.write_text(html, encoding="utf-8")
        written.append(path)

    return written


# ---------------------------------------------------------------------------
# Diagnostics / Phase 1 entry point
# ---------------------------------------------------------------------------

def print_phase1_summary(df: pd.DataFrame) -> None:
    """Print a summary of the normalized dataset for validation."""
    print("=" * 72)
    print("PHASE 1 — DATA INGESTION & NORMALIZATION SUMMARY")
    print("=" * 72)

    total = len(df)
    mapped = df["marker_id"].notna().sum()
    unmapped = total - mapped
    unique_markers = df["marker_id"].dropna().nunique()
    unique_files = df["source_file"].nunique()
    date_min = df["collected_date"].min()
    date_max = df["collected_date"].max()

    print(f"\nTotal records:        {total}")
    print(f"Mapped records:       {mapped}")
    print(f"Unmapped records:     {unmapped}")
    print(f"Unique marker_ids:    {unique_markers}")
    print(f"Source files:         {unique_files}")
    print(f"Date range:           {date_min} → {date_max}")

    # Threshold values
    thresholds = df[df["comparator"] != ""]
    print(f"\nThreshold values (</>): {len(thresholds)}")

    # Quality flags
    flagged = df[df["quality_flags"] != ""]
    print(f"Rows with quality flags: {len(flagged)}")

    # Unmapped detail
    if unmapped:
        print(f"\n--- Unmapped markers ---")
        unmapped_df = df[df["marker_id"].isna()]
        for param in unmapped_df["marker_label_pl"].unique():
            n = (unmapped_df["marker_label_pl"] == param).sum()
            print(f"  {param}: {n} rows")

    # Per-marker summary
    print(f"\n--- Marker counts ---")
    counts = (
        df[df["marker_id"].notna()]
        .groupby(["group", "marker_id"])
        .agg(
            n=("marker_id", "size"),
            first_date=("collected_date", "min"),
            last_date=("collected_date", "max"),
            latest_value=("numeric_value", "last"),
        )
        .sort_values(["group", "marker_id"])
    )
    current_group = None
    for (group, mid), row in counts.iterrows():
        if group != current_group:
            current_group = group
            print(f"\n  [{group}]")
        label = MARKERS.get(mid, {}).get("label_pl", mid)
        print(f"    {label:40s}  n={row['n']:3d}  "
              f"{row['first_date']} → {row['last_date']}  "
              f"latest={row['latest_value']}")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

_PDF_CHART_PREP_JS = r"""
async () => {
  const graphDivs = Array.from(document.querySelectorAll('.plotly-graph-div'));
  document.querySelectorAll('.chart-container').forEach(c => c.classList.add('open'));

  const settle = () => new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });

  await settle();

  for (const gd of graphDivs) {
    if (gd._fullLayout) {
      Plotly.Plots.resize(gd);
    }
  }

  await settle();

  for (const gd of graphDivs) {
    const n = (gd.data || []).length;
    if (n > 0) {
      const idx = Array.from({ length: n }, (_, i) => i);
      await Plotly.restyle(gd, {
        'line.color': '#000000',
        'line.dash': 'solid',
        'marker.color': '#000000',
        'marker.line.color': '#000000',
      }, idx);
    }

    const keptShapes = ((gd.layout && gd.layout.shapes) || [])
      .filter(s => s.type === 'line' && s.line && s.line.dash === 'dash')
      .map(s => ({
        ...s,
        line: { ...(s.line || {}), color: '#000000', width: 1 },
        opacity: 1,
      }));

    await Plotly.relayout(gd, {
      shapes: keptShapes,
      annotations: [],
      'xaxis.gridcolor': '#e5e7eb',
      'yaxis.gridcolor': '#e5e7eb',
    });
  }

  await settle();

  for (const gd of graphDivs) {
    const rect = gd.getBoundingClientRect();
    const width = Math.max(300, Math.round(rect.width || 700));
    const height = Math.max(150, Math.round(rect.height || 220));
    const url = await Plotly.toImage(gd, {
      format: 'png',
      width,
      height,
      scale: 2,
    });

    const img = document.createElement('img');
    img.src = url;
    img.style.width = '100%';
    img.style.maxWidth = width + 'px';
    img.style.height = 'auto';
    img.style.display = 'block';
    gd.replaceWith(img);
  }
}
"""

_PLOTLY_READY_JS = r"""
() => {
  const els = document.querySelectorAll('.plotly-graph-div');
  return els.length === 0 || Array.from(els).every(e => e._fullLayout);
}
"""


def html_to_pdf(context, html_path: Path, pdf_path: Path) -> None:
    """Render a single HTML file to PDF using an existing Playwright browser context."""
    page = context.new_page()
    try:
        file_url = f"file://{html_path.resolve()}"
        page.goto(file_url, wait_until="networkidle")
        page.emulate_media(media="print")

        plotly_available = page.evaluate("() => typeof window.Plotly !== 'undefined'")
        if plotly_available:
            page.wait_for_function(_PLOTLY_READY_JS, timeout=30000)
            page.evaluate(_PDF_CHART_PREP_JS)
        else:
            LOG.warning(
                "Plotly not loaded for %s (CDN unreachable?). "
                "PDF written without chart freezing.",
                html_path.name,
            )

        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "15mm", "right": "12mm", "bottom": "15mm", "left": "12mm"},
        )
    finally:
        page.close()


def generate_pdfs(html_paths: list[Path]) -> tuple[list[Path], int]:
    """Render a batch of HTML files to PDFs, one per file. Returns (written, failed_count)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        LOG.warning(
            "PDF export skipped: playwright not installed. "
            "Run: pip install playwright && playwright install chromium"
        )
        return [], 0

    written: list[Path] = []
    failed = 0

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:
            LOG.warning(
                "PDF export skipped: Chromium unavailable. "
                "Run: playwright install chromium (%s)",
                exc,
            )
            return [], 0

        try:
            context = browser.new_context()
            try:
                for html_path in html_paths:
                    pdf_path = html_path.with_suffix(".pdf")
                    try:
                        html_to_pdf(context, html_path, pdf_path)
                        written.append(pdf_path)
                    except Exception as exc:
                        failed += 1
                        LOG.warning("PDF render failed for %s: %s", html_path.name, exc)
            finally:
                context.close()
        finally:
            browser.close()

    return written, failed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Phase 1: Ingest & normalize
    LOG.info("Loading raw data from %s (+ %s)", DATA_DIR, PDF_DIR)
    raw = load_all_data()
    LOG.info("Raw rows: %d from %d files", len(raw), raw["source_file"].nunique())

    LOG.info("Normalizing records...")
    df = normalize_records(raw)
    print_phase1_summary(df)

    # Phase 2: Deduplication & consolidation
    LOG.info("Consolidating measurements...")
    df, dedup_stats = consolidate_measurements(df)
    print_phase2_summary(df, dedup_stats)

    # Phase 3: Status assessment
    LOG.info("Assessing marker statuses...")
    status_df = assess_all_statuses(df)
    print_phase3_summary(status_df)

    # Phase 4: Trend analysis
    LOG.info("Analyzing trends...")
    trend_df = analyze_trends(df, status_df)
    print_phase4_summary(trend_df)

    # Phase 5: Recommendations
    LOG.info("Generating recommendations...")
    rec_df = generate_recommendations(status_df, trend_df)
    print_phase5_summary(rec_df)

    # Phase 6: HTML report
    LOG.info("Rendering HTML report...")
    html = render_html(df, status_df, trend_df, rec_df)
    output_path = OUTPUT_PATH
    output_path.write_text(html, encoding="utf-8")
    LOG.info("Report saved to %s (%d KB)", output_path.name, len(html) // 1024)

    # Specialist consultation reports
    LOG.info("Generating specialist consultation reports...")
    specialist_paths = generate_specialist_reports(rec_df, df, status_df, trend_df)
    if specialist_paths:
        LOG.info(
            "Specialist reports: %d written (%s)",
            len(specialist_paths),
            ", ".join(p.name for p in specialist_paths),
        )
    else:
        LOG.info("No specialist consultation reports needed.")

    # PDF export
    LOG.info("Exporting PDFs...")
    html_paths = [output_path, *specialist_paths]
    written, failed = generate_pdfs(html_paths)
    if written:
        LOG.info(
            "PDFs written: %d (%s)",
            len(written),
            ", ".join(p.name for p in written),
        )
    if failed:
        LOG.warning("PDF export: %d file(s) failed — see warnings above.", failed)

    return df, status_df, trend_df, rec_df


if __name__ == "__main__":
    main()
