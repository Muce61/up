"""防未来函数：volatility 因子。"""
from __future__ import annotations

import pytest

from factors import volatility


@pytest.mark.lookahead
def test_realized_vol_unchanged_when_future_truncated(prices_df, calendar_dates) -> None:
    asof = calendar_dates[200]
    full = volatility.realized_vol(prices_df, asof_date=asof, window=20)
    truncated = prices_df[prices_df["trade_date"] <= asof]
    again = volatility.realized_vol(truncated, asof_date=asof, window=20)
    full = full.sort_values("symbol").reset_index(drop=True)
    again = again.sort_values("symbol").reset_index(drop=True)
    for v1, v2 in zip(full["value"], again["value"]):
        if v1 == v1:
            assert v1 == pytest.approx(v2)


@pytest.mark.lookahead
def test_max_dd_unchanged_when_future_truncated(prices_df, calendar_dates) -> None:
    asof = calendar_dates[200]
    full = volatility.max_drawdown(prices_df, asof_date=asof, window=60)
    truncated = prices_df[prices_df["trade_date"] <= asof]
    again = volatility.max_drawdown(truncated, asof_date=asof, window=60)
    full = full.sort_values("symbol").reset_index(drop=True)
    again = again.sort_values("symbol").reset_index(drop=True)
    for v1, v2 in zip(full["value"], again["value"]):
        if v1 == v1:
            assert v1 == pytest.approx(v2)
