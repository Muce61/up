"""单元测试：volatility 因子。"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from factors import volatility


def _make_series(values, start=date(2024, 1, 2)):
    n = len(values)
    dates = pd.bdate_range(start=start, periods=n).date.tolist()
    return pd.DataFrame(
        {
            "symbol": "TEST.SH",
            "trade_date": dates,
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "adj_factor": 1.0,
            "volume": 100_000,
            "amount": [1e6] * n,
            "limit_up": [v * 1.1 for v in values],
            "limit_down": [v * 0.9 for v in values],
            "is_suspended": [False] * n,
        }
    )


@pytest.mark.unit
def test_realized_vol_positive_on_random_walk() -> None:
    rng = np.random.default_rng(7)
    rets = rng.normal(0, 0.01, 30)
    prices = 100 * np.exp(np.cumsum(rets))
    df = _make_series(prices.tolist())
    out = volatility.realized_vol(df, asof_date=df["trade_date"].iloc[-1], window=20)
    v = float(out["value"].iloc[0])
    assert v > 0
    # 年化 vol ≈ 0.01 × √252 ≈ 0.16，给宽松上下限
    assert 0.05 < v < 0.40


@pytest.mark.unit
def test_realized_vol_zero_on_constant_series() -> None:
    df = _make_series([100.0] * 30)
    out = volatility.realized_vol(df, asof_date=df["trade_date"].iloc[-1], window=20)
    assert float(out["value"].iloc[0]) == 0.0


@pytest.mark.unit
def test_realized_vol_insufficient_history_nan() -> None:
    df = _make_series([100, 101, 102])
    out = volatility.realized_vol(df, asof_date=df["trade_date"].iloc[-1], window=20)
    v = float(out["value"].iloc[0])
    assert v != v  # NaN


@pytest.mark.unit
def test_max_drawdown_positive_value() -> None:
    df = _make_series([100, 105, 95, 90, 92, 100])
    out = volatility.max_drawdown(df, asof_date=df["trade_date"].iloc[-1], window=6)
    v = float(out["value"].iloc[0])
    # peak=105, trough=90 → (105-90)/105 ≈ 0.1428
    assert v == pytest.approx(15 / 105, rel=1e-6)


@pytest.mark.unit
def test_max_drawdown_zero_on_monotone_increase() -> None:
    df = _make_series([100, 101, 102, 103, 104, 105])
    out = volatility.max_drawdown(df, asof_date=df["trade_date"].iloc[-1], window=6)
    assert float(out["value"].iloc[0]) == pytest.approx(0.0)
