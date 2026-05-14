"""可复现性：同 (params, snapshot_version) 两次运行得到完全相同的指标与曲线。"""
from __future__ import annotations

import pytest

from backtest import engine
from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal


@pytest.mark.regression
def test_backtest_byte_for_byte_reproducible(
    prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
        random_seed=42,
    )
    r1 = engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )
    r2 = engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )
    # 关键指标必须完全一致
    for k in ["annualized_return", "max_drawdown", "sharpe", "turnover", "final_equity"]:
        assert r1.metrics[k] == r2.metrics[k]
    # equity_curve 也应完全一致
    assert r1.equity_curve.equals(r2.equity_curve)
    assert r1.manifest["params_hash"] == r2.manifest["params_hash"]
