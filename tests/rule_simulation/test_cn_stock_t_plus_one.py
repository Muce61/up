"""强制白名单 #4：A 股股票 / 股票 ETF T+1；T+0 品类允许同日来回。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from execution import tradeability


@pytest.mark.rule_simulation
def test_t1_violation_same_day(calendar_dates) -> None:
    # 当日买入 + 当日卖出 → T+1 违反（broad_index 是 T+1）
    same_day = calendar_dates[10]
    assert tradeability.is_t1_violation(
        etf_type="broad_index",
        last_buy_trade_date=same_day,
        current_trade_date=same_day,
        trading_calendar=calendar_dates,
    )


@pytest.mark.rule_simulation
def test_t1_violation_next_trading_day_ok(calendar_dates) -> None:
    # 当日买入，下一交易日卖出 → 允许
    buy_day = calendar_dates[10]
    sell_day = calendar_dates[11]
    assert not tradeability.is_t1_violation(
        etf_type="broad_index",
        last_buy_trade_date=buy_day,
        current_trade_date=sell_day,
        trading_calendar=calendar_dates,
    )


@pytest.mark.rule_simulation
def test_t0_etf_same_day_ok(calendar_dates) -> None:
    same_day = calendar_dates[10]
    # 黄金 ETF 是 T+0 → 同日来回允许
    assert not tradeability.is_t1_violation(
        etf_type="gold",
        last_buy_trade_date=same_day,
        current_trade_date=same_day,
        trading_calendar=calendar_dates,
    )


@pytest.mark.rule_simulation
def test_no_buy_no_violation(calendar_dates) -> None:
    assert not tradeability.is_t1_violation(
        etf_type="broad_index",
        last_buy_trade_date=None,
        current_trade_date=calendar_dates[10],
        trading_calendar=calendar_dates,
    )
