"""回归测试：fixtures、数据加载器输出、回测引擎入口都必须满足数据契约。

锁住 docs/data_contract.md 与实际代码之间的口径一致性；
真实快照接入前，这是防止字段口径悄悄漂移的护栏。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from data import etf_loader, schema

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.regression
def test_fixtures_prices_satisfy_contract(prices_df) -> None:
    out = schema.validate_prices(prices_df)
    assert "effective_date" in out.columns
    assert len(out) == len(prices_df)


@pytest.mark.regression
def test_fixtures_master_satisfy_contract(master_df) -> None:
    out = schema.validate_master(master_df)
    assert len(out) == len(master_df)


@pytest.mark.regression
def test_fixtures_calendar_satisfy_contract(calendar_df) -> None:
    out = schema.validate_calendar(calendar_df)
    assert len(out) == len(calendar_df)


@pytest.mark.regression
def test_etf_loader_master_output_satisfies_contract() -> None:
    path = REPO_ROOT / "config" / "universe" / "etf_pool.yaml"
    df = etf_loader.load_etf_master(path)
    # load_etf_master 已内置校验；这里独立再校验一次，防回归
    schema.validate_master(df)
    assert len(df) > 0


@pytest.mark.regression
def test_etf_loader_prices_output_satisfies_contract(tmp_path) -> None:
    prices_file = tmp_path / "prices.csv"
    pd.DataFrame(
        {
            "symbol": ["510300.SH", "510300.SH"],
            "trade_date": ["2024-01-02", "2024-01-03"],
            "open": [1.00, 1.01],
            "high": [1.10, 1.12],
            "low": [0.90, 0.95],
            "close": [1.00, 1.05],
            "adj_factor": [1.0, 1.0],
            "volume": [100, 120],
            "amount": [1000.0, 1100.0],
            "limit_up": [1.10, 1.155],
            "limit_down": [0.90, 0.945],
            "is_suspended": [False, False],
        }
    ).to_csv(prices_file, index=False)
    df = etf_loader.load_prices(prices_file)
    # loader 应已补 effective_date，故 normalize=False 也应通过
    schema.validate_prices(df, normalize=False)


@pytest.mark.regression
def test_engine_run_backtest_rejects_bad_prices(
    prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    """run_backtest 入口必须校验输入；坏数据应抛 SchemaError 而不是静默继续。"""
    from backtest import engine
    from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal

    bad_prices = prices_df.drop(columns=["adj_factor"])
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
    )
    with pytest.raises(schema.SchemaError):
        engine.run_backtest(
            config=cfg,
            prices=bad_prices,
            master=master_df,
            calendar=calendar_df,
            signal_fn=generate_signal,
            params=signal_params,
        )


@pytest.mark.regression
def test_engine_run_backtest_accepts_contract_valid_inputs(
    prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    """契约合法的 fixtures 经过 run_backtest 入口校验后应正常完成。"""
    from backtest import engine
    from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal

    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
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
