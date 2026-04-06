"""Regression tests for trend_state derivation in analyze_trends (Patch 6).

Exercises the sufficiency gate and robust-trend statistics on synthetic data:
- too-few points → insufficient
- monotone rise → supported_up (robust to one outlier)
- U-shape → no_clear_trend
- method_or_range_change → insufficient
- short span → insufficient
- too few unique dates → insufficient
- same-day duplicates collapse before M-K
"""
from __future__ import annotations

import datetime as _dt

import pandas as pd

from generate_report import analyze_trends


def _make_df(marker_id: str, rows: list[tuple]) -> pd.DataFrame:
    """Build a minimal df with the columns analyze_trends needs.

    rows: list of (date, value, quality_flags, unit) tuples.
    """
    records = []
    for d, v, flags, unit in rows:
        records.append({
            "marker_id": marker_id,
            "marker_label_pl": marker_id,
            "numeric_value": float(v),
            "comparator": "",
            "collected_at": pd.Timestamp(d),
            "unit": unit,
            "quality_flags": flags,
        })
    return pd.DataFrame(records)


def _status_df(marker_id: str, status: str = "OK") -> pd.DataFrame:
    return pd.DataFrame([{"marker_id": marker_id, "status": status}])


def _daily_span(start: str, n: int, step_days: int = 45) -> list[_dt.date]:
    d0 = _dt.date.fromisoformat(start)
    return [d0 + _dt.timedelta(days=i * step_days) for i in range(n)]


def test_n_below_5_is_insufficient():
    for n in (1, 2, 3, 4):
        dates = _daily_span("2022-01-01", n, step_days=90)
        rows = [(d, 10.0 + i, "", "mg/dL") for i, d in enumerate(dates)]
        df = _make_df("m", rows)
        out = analyze_trends(df, _status_df("m"))
        assert out.iloc[0]["trend_state"] == "insufficient", f"n={n}"


def test_n5_monotone_rise_is_supported_up():
    dates = _daily_span("2022-01-01", 5, step_days=90)
    rows = [(d, 10.0 + i * 2, "", "mg/dL") for i, d in enumerate(dates)]
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    assert out.iloc[0]["trend_state"] == "supported_up"
    assert out.iloc[0]["tau"] == 1.0


def test_monotone_rise_with_outlier_still_supported():
    # n=8 rising series with a mild mid-series outlier — Theil–Sen robustness
    dates = _daily_span("2022-01-01", 8, step_days=60)
    vals = [10.0, 12.0, 14.0, 11.0, 18.0, 20.0, 22.0, 24.0]  # index 3 is dip
    rows = [(d, v, "", "mg/dL") for d, v in zip(dates, vals)]
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    assert out.iloc[0]["trend_state"] == "supported_up"
    assert out.iloc[0]["sen_slope_per_year"] > 0


def test_u_shape_is_no_clear_trend():
    dates = _daily_span("2022-01-01", 8, step_days=60)
    vals = [20.0, 15.0, 11.0, 9.0, 10.0, 13.0, 17.0, 21.0]
    rows = [(d, v, "", "mg/dL") for d, v in zip(dates, vals)]
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    assert out.iloc[0]["trend_state"] == "no_clear_trend"


def test_method_change_forces_insufficient():
    dates = _daily_span("2022-01-01", 6, step_days=70)
    rows = [(d, 10.0 + i * 2, "", "mg/dL") for i, d in enumerate(dates)]
    # inject method_or_range_change flag on one row
    rows[2] = (rows[2][0], rows[2][1], "method_or_range_change", "mg/dL")
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    assert out.iloc[0]["trend_state"] == "insufficient"
    assert bool(out.iloc[0]["has_method_change"]) is True


def test_short_span_is_insufficient():
    # n=6 but over ~100 days (< 180)
    dates = _daily_span("2022-01-01", 6, step_days=20)
    rows = [(d, 10.0 + i, "", "mg/dL") for i, d in enumerate(dates)]
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    assert out.iloc[0]["trend_state"] == "insufficient"
    assert out.iloc[0]["span_days"] < 180


def test_few_unique_dates_is_insufficient():
    # 10 records on 3 unique dates over 400 days
    d1 = _dt.date(2022, 1, 1)
    d2 = _dt.date(2022, 7, 1)
    d3 = _dt.date(2023, 2, 5)
    rows = []
    vals = [10.0, 10.2, 10.5, 11.0, 11.3, 11.6, 12.1, 12.4, 12.7, 13.0]
    date_seq = [d1, d1, d1, d1, d2, d2, d2, d3, d3, d3]
    for d, v in zip(date_seq, vals):
        rows.append((d, v, "", "mg/dL"))
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    assert out.iloc[0]["trend_state"] == "insufficient"
    assert out.iloc[0]["n_unique_dates"] == 3


def test_same_day_duplicates_collapse_but_eligible():
    # 10 raw rows on 5 unique dates spanning 400 days — 2 rows per date.
    uniq_dates = _daily_span("2022-01-01", 5, step_days=100)
    rows = []
    per_date_vals = [(8.0, 12.0), (10.0, 14.0), (12.0, 16.0), (14.0, 18.0), (16.0, 20.0)]
    for d, (a, b) in zip(uniq_dates, per_date_vals):
        rows.append((d, a, "", "mg/dL"))
        rows.append((d, b, "", "mg/dL"))
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    row = out.iloc[0]
    # Eligible: n_exact=10, span≈400d, n_unique_dates=5
    assert row["n_exact_measurements"] == 10
    assert row["n_unique_dates"] == 5
    assert row["trend_eligible"]
    # After collapse medians are [10, 12, 14, 16, 18] — strictly increasing
    assert row["trend_state"] == "supported_up"
    assert row["tau"] == 1.0


def test_unit_change_forces_insufficient():
    dates = _daily_span("2022-01-01", 6, step_days=70)
    rows = [(d, 10.0 + i * 2, "", "mg/dL") for i, d in enumerate(dates)]
    rows[3] = (rows[3][0], rows[3][1], "", "g/L")  # unit change mid-series
    df = _make_df("m", rows)
    out = analyze_trends(df, _status_df("m"))
    assert out.iloc[0]["trend_state"] == "insufficient"
    assert bool(out.iloc[0]["has_unit_change"]) is True
