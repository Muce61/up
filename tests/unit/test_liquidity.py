"""单元测试：liquidity 因子。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from factors import liquidity


@pytest.mark.unit
def test_adv_simple_average() -> None:
    dates = pd.bdate_range(start=date(2024, 1, 2), periods=10).date.tolist()
    df = pd.DataFrame(
        {
            "symbol": "TEST.SH",
            "trade_date": dates,
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "adj_factor": 1.0,
            "volume": 1_000_000,
            "amount": [1e7] * 10,
            "limit_up": 110.0,
            "limit_down": 90.0,
            "is_suspended": False,
        }
    )
    out = liquidity.adv(df, asof_date=dates[-1], window=10)
    assert float(out["value"].iloc[0]) == pytest.approx(1e7)


@pytest.mark.unit
def test_adv_excludes_suspended() -> None:
    dates = pd.bdate_range(start=date(2024, 1, 2), periods=5).date.tolist()
    df = pd.DataFrame(
        {
            "symbol": "TEST.SH",
            "trade_date": dates,
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "adj_factor": 1.0,
            "volume": 1_000_000,
            "amount": [1e7, 2e7, 0.0, 2e7, 1e7],
            "limit_up": 110.0,
            "limit_down": 90.0,
            "is_suspended": [False, False, True, False, False],
        }
    )
    out = liquidity.adv(df, asof_date=dates[-1], window=5)
    # 排除 1 个停牌日，剩 4 条：1e7 + 2e7 + 2e7 + 1e7 = 6e7 / 4 = 1.5e7
    assert float(out["value"].iloc[0]) == pytest.approx(1.5e7)
