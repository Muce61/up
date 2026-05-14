"""防未来函数：截断 asof_date 之后的数据，因子输出不变。"""
from __future__ import annotations

import pytest

from factors import momentum


@pytest.mark.lookahead
def test_momentum_unchanged_when_future_truncated(prices_df, calendar_dates) -> None:
    asof = calendar_dates[200]
    # 全量
    full = momentum.momentum(prices_df, asof_date=asof, window=20)
    # 人为截断 asof 之后的数据后再算
    truncated = prices_df[prices_df["trade_date"] <= asof]
    again = momentum.momentum(truncated, asof_date=asof, window=20)
    full = full.sort_values("symbol").reset_index(drop=True)
    again = again.sort_values("symbol").reset_index(drop=True)
    # value 应完全相同（顺序与值）
    for s_full, v_full, s_again, v_again in zip(
        full["symbol"], full["value"], again["symbol"], again["value"]
    ):
        assert s_full == s_again
        if v_full == v_full:  # not NaN
            assert v_full == pytest.approx(v_again)


@pytest.mark.lookahead
def test_trend_pass_unchanged_when_future_truncated(prices_df, calendar_dates) -> None:
    asof = calendar_dates[200]
    full = momentum.trend_pass(prices_df, asof_date=asof, ma_window=60)
    truncated = prices_df[prices_df["trade_date"] <= asof]
    again = momentum.trend_pass(truncated, asof_date=asof, ma_window=60)
    full = full.sort_values("symbol").reset_index(drop=True)
    again = again.sort_values("symbol").reset_index(drop=True)
    assert (full["value"].astype(bool) == again["value"].astype(bool)).all()
