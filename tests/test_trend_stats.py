"""Tests for robust trend statistics primitives (Patch 1).

Covers:
- Theil–Sen slope (matches OLS on monotone data, robust to outliers)
- Mann–Kendall test (monotone → significant, random → not, ties safe)
- Bootstrap CI (excludes 0 on monotone, includes 0 on flat)
- _collapse_same_day (median per unique date)
"""
from __future__ import annotations

import datetime as _dt

import numpy as np

from generate_report import (
    _bootstrap_slope_ci,
    _collapse_same_day,
    _mann_kendall,
    _theil_sen_slope,
)


def test_theil_sen_matches_ols_on_monotone():
    x = np.arange(10, dtype=float)
    y = 2.0 * x + 3.0
    ts = _theil_sen_slope(x, y)
    assert abs(ts["slope"] - 2.0) < 1e-9
    assert abs(ts["intercept"] - 3.0) < 1e-9


def test_theil_sen_robust_to_outlier():
    x = np.arange(8, dtype=float)
    y = x.copy()
    # inject one wild outlier that flips OLS slope if extreme enough
    y_out = y.copy()
    y_out[4] = -100.0
    # OLS slope on the outlier series
    ols_slope = np.polyfit(x, y_out, 1)[0]
    ts_slope = _theil_sen_slope(x, y_out)["slope"]
    # OLS should be dragged down noticeably, Theil–Sen should remain ~1
    assert ts_slope > 0.5
    assert ols_slope < ts_slope  # OLS pulled further by outlier


def test_theil_sen_skips_zero_dx():
    # tied x values should not crash or produce inf
    x = np.array([0.0, 0.0, 1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    ts = _theil_sen_slope(x, y)
    assert np.isfinite(ts["slope"])


def test_mann_kendall_monotone_increasing_small_n():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    res = _mann_kendall(y)
    assert res["tau"] == 1.0
    assert res["p_value"] < 0.05


def test_mann_kendall_monotone_decreasing_small_n():
    y = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
    res = _mann_kendall(y)
    assert res["tau"] == -1.0
    assert res["p_value"] < 0.05


def test_mann_kendall_random_no_trend():
    rng = np.random.default_rng(0)
    y = rng.normal(size=20)
    res = _mann_kendall(y)
    assert res["p_value"] > 0.1


def test_mann_kendall_ties_no_crash():
    y = np.array([1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0, 3.0, 4.0])
    res = _mann_kendall(y)
    assert np.isfinite(res["p_value"])
    assert np.isfinite(res["tau"])


def test_mann_kendall_asymptotic_branch():
    # n >= 11 forces asymptotic path
    y = np.arange(15, dtype=float)
    res = _mann_kendall(y)
    assert res["tau"] == 1.0
    assert res["p_value"] < 0.01


def test_bootstrap_ci_excludes_zero_on_monotone():
    x = np.arange(8, dtype=float)
    y = 2.0 * x + 1.0
    lo, hi = _bootstrap_slope_ci(x, y, n_boot=500, seed=1)
    assert lo > 0
    assert hi > 0


def test_bootstrap_ci_includes_zero_on_flat():
    rng = np.random.default_rng(3)
    x = np.arange(12, dtype=float)
    y = rng.normal(size=12)
    lo, hi = _bootstrap_slope_ci(x, y, n_boot=500, seed=3)
    assert lo < 0 < hi


def test_collapse_same_day_medians_duplicates():
    d1 = _dt.date(2024, 1, 1)
    d2 = _dt.date(2024, 1, 5)
    d3 = _dt.date(2024, 1, 10)
    dates = np.array([d1, d1, d2, d3, d3, d3])
    values = np.array([10.0, 20.0, 5.0, 7.0, 9.0, 11.0])
    out_d, out_v = _collapse_same_day(dates, values)
    assert len(out_d) == 3
    assert list(out_d) == [d1, d2, d3]
    # medians: [15, 5, 9]
    assert list(out_v) == [15.0, 5.0, 9.0]


def test_collapse_same_day_preserves_order():
    d = [_dt.date(2024, 1, i) for i in (1, 2, 3, 4)]
    dates = np.array(d)
    values = np.array([1.0, 2.0, 3.0, 4.0])
    out_d, out_v = _collapse_same_day(dates, values)
    assert list(out_d) == d
    assert list(out_v) == [1.0, 2.0, 3.0, 4.0]
