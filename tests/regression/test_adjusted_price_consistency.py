"""回归测试：复权价格口径一致性。"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest import engine
from factors import momentum


def _prices_with_adjustment() -> pd.DataFrame:
    rows = [
        {
            "symbol": "ETFADJ.SH",
            "trade_date": date(2024, 1, 5),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "adj_factor": 1.0,
            "volume": 1_000_000,
            "amount": 20_000_000.0,
            "limit_up": 110.0,
            "limit_down": 90.0,
            "is_suspended": False,
        },
        {
            "symbol": "ETFADJ.SH",
            "trade_date": date(2024, 1, 8),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "adj_factor": 1.0,
            "volume": 1_000_000,
            "amount": 20_000_000.0,
            "limit_up": 110.0,
            "limit_down": 90.0,
            "is_suspended": False,
        },
        {
            "symbol": "ETFADJ.SH",
            "trade_date": date(2024, 1, 9),
            "open": 50.0,
            "high": 50.5,
            "low": 49.5,
            "close": 50.0,
            "adj_factor": 2.0,
            "volume": 2_000_000,
            "amount": 20_000_000.0,
            "limit_up": 55.0,
            "limit_down": 45.0,
            "is_suspended": False,
        },
    ]
    return pd.DataFrame(rows)


def _master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "ETFADJ.SH",
                "name": "复权测试 ETF",
                "etf_type": "broad_index",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2020, 1, 1),
                "delist_date": None,
                "exchange": "SH",
            }
        ]
    )


def _calendar() -> pd.DataFrame:
    dates = [date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)]
    return pd.DataFrame(
        {
            "trade_date": dates,
            "is_open": [True, True, True],
            "prev_trade_date": [None, dates[0], dates[1]],
            "next_trade_date": [dates[1], dates[2], None],
        }
    )


def _always_hold_signal(asof_date, prices, master, params) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["ETFADJ.SH"],
            "asof_date": [asof_date],
            "target_weight": [1.0],
            "score": [1.0],
            "mom_20": [0.0],
            "mom_60": [0.0],
            "mom_120": [0.0],
            "vol_20": [0.0],
            "adv_60": [20_000_000.0],
            "trend_pass": [True],
            "etf_type": ["broad_index"],
        }
    )


@pytest.mark.regression
def test_momentum_uses_adjusted_close_across_price_adjustment() -> None:
    prices = _prices_with_adjustment().iloc[[1, 2]].reset_index(drop=True)

    out = momentum.momentum(prices, asof_date=date(2024, 1, 9), window=1)

    assert float(out["value"].iloc[0]) == pytest.approx(0.0)


@pytest.mark.regression
def test_backtest_equity_does_not_gap_down_on_adjusted_price_event() -> None:
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=date(2024, 1, 5),
        end_date=date(2024, 1, 9),
        initial_capital=1_000_000.0,
        fee_config=engine.fee_model.FeeConfig(slippage_bps=0.0),
        lot_size=1,
        n_capacity_pct=1.0,
    )

    result = engine.run_backtest(
        config=cfg,
        prices=_prices_with_adjustment(),
        master=_master(),
        calendar=_calendar(),
        signal_fn=_always_hold_signal,
        params=SimpleNamespace(),
    )

    equity_on_adjustment = float(
        result.equity_curve.loc[
            result.equity_curve["trade_date"] == date(2024, 1, 9),
            "equity",
        ].iloc[0]
    )

    assert equity_on_adjustment > 990_000.0
