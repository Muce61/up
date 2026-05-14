"""烟雾测试：引擎端到端跑通。"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest import engine
from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal


@pytest.mark.unit
def test_run_backtest_end_to_end(
    prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],  # 留出建仓所需历史
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
        random_seed=42,
    )
    result = engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )
    assert len(result.equity_curve) > 0
    assert result.metrics["n_trading_days"] > 0
    assert result.equity_curve["equity"].iloc[0] > 0
    assert "annualized_return" in result.metrics
    assert "max_drawdown" in result.metrics
    assert "sharpe" in result.metrics


@pytest.mark.unit
def test_exec_price_uses_slippage_model(monkeypatch) -> None:
    calls = []

    def fake_execution_price(**kwargs):
        calls.append(kwargs)
        return 123.45

    monkeypatch.setattr(engine.slippage, "execution_price", fake_execution_price)
    bar = pd.Series(
        {
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 101.0,
            "amount": 1_000_000.0,
        }
    )

    out = engine._exec_price(bar, "buy", 5.0, order_amount=10_000.0)

    assert out == pytest.approx(123.45)
    assert calls
    assert calls[0]["side"] == "buy"
    assert calls[0]["base_price"] == pytest.approx(100.0)
    assert calls[0]["order_amount"] == pytest.approx(10_000.0)
    assert calls[0]["adv_amount"] == pytest.approx(1_000_000.0)
