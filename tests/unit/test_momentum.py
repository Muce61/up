"""单元测试：momentum 因子。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from factors import momentum


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
def test_momentum_simple_increase() -> None:
    prices = _make_series([100, 101, 102, 103, 104, 105, 106])
    out = momentum.momentum(prices, asof_date=prices["trade_date"].iloc[-1], window=5)
    assert len(out) == 1
    # close_t / close_{t-5} - 1 = 106/101 - 1
    assert out["value"].iloc[0] == pytest.approx(106 / 101 - 1)


@pytest.mark.unit
def test_momentum_insufficient_history_returns_nan() -> None:
    prices = _make_series([100, 101])
    out = momentum.momentum(prices, asof_date=prices["trade_date"].iloc[-1], window=10)
    assert out["value"].iloc[0] != out["value"].iloc[0]  # NaN


@pytest.mark.unit
def test_momentum_skips_suspended_days() -> None:
    prices = _make_series([100, 101, 102, 103, 104, 105])
    prices.loc[2, "is_suspended"] = True  # 一天停牌
    out = momentum.momentum(prices, asof_date=prices["trade_date"].iloc[-1], window=3)
    # 排除停牌后剩 5 日：100,101,103,104,105；window=3 → 105/101-1
    assert out["value"].iloc[0] == pytest.approx(105 / 101 - 1)


@pytest.mark.unit
def test_trend_pass_above_ma() -> None:
    # 价格持续上涨，最终高于均线
    prices = _make_series(list(range(100, 200)))
    out = momentum.trend_pass(prices, asof_date=prices["trade_date"].iloc[-1], ma_window=50)
    assert bool(out["value"].iloc[0]) is True


@pytest.mark.unit
def test_trend_pass_below_ma() -> None:
    # 价格持续下跌，最终低于均线
    prices = _make_series(list(range(200, 100, -1)))
    out = momentum.trend_pass(prices, asof_date=prices["trade_date"].iloc[-1], ma_window=50)
    assert bool(out["value"].iloc[0]) is False


@pytest.mark.unit
def test_factor_output_schema() -> None:
    prices = _make_series([100, 101, 102, 103, 104, 105])
    out = momentum.momentum(prices, asof_date=prices["trade_date"].iloc[-1], window=3)
    assert list(out.columns) == ["symbol", "asof_date", "effective_date", "value"]
