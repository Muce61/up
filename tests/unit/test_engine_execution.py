"""单元测试：回测引擎成交路径。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtest import engine
from execution import fee_model, order_model


def _prices(**overrides) -> pd.DataFrame:
    row = {
        "symbol": "ETFA.SH",
        "trade_date": date(2024, 1, 3),
        "open": 100.0,
        "high": 102.0,
        "low": 98.0,
        "close": 101.0,
        "adj_factor": 1.0,
        "volume": 1_000_000,
        "amount": 10_000_000.0,
        "limit_up": 110.0,
        "limit_down": 90.0,
        "is_suspended": False,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _prices_with_adv_history(
    *,
    prior_amount: float,
    exec_amount: float = 10_000_000.0,
    exec_open: float = 100.0,
) -> pd.DataFrame:
    rows = []
    for day in [date(2024, 1, 1), date(2024, 1, 2)]:
        rows.append(
            {
                "symbol": "ETFA.SH",
                "trade_date": day,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "adj_factor": 1.0,
                "volume": 1_000_000,
                "amount": prior_amount,
                "limit_up": 110.0,
                "limit_down": 90.0,
                "is_suspended": False,
            }
        )
    rows.append(
        {
            "symbol": "ETFA.SH",
            "trade_date": date(2024, 1, 3),
            "open": exec_open,
            "high": 102.0,
            "low": 98.0,
            "close": 101.0,
            "adj_factor": 1.0,
            "volume": 1_000_000,
            "amount": exec_amount,
            "limit_up": 110.0,
            "limit_down": 90.0,
            "is_suspended": False,
        }
    )
    return pd.DataFrame(rows)


def _master(**overrides) -> pd.Series:
    row = {
        "symbol": "ETFA.SH",
        "name": "A 宽基",
        "etf_type": "broad_index",
        "settlement": "T+1",
        "stamp_tax_applicable": False,
        "list_date": date(2018, 1, 2),
        "delist_date": None,
        "exchange": "SH",
    }
    row.update(overrides)
    return pd.Series(row)


def _config(slippage_bps: float = 5.0) -> engine.BacktestConfig:
    return engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        initial_capital=1_000_000.0,
        fee_config=fee_model.FeeConfig(slippage_bps=slippage_bps),
    )


@pytest.mark.unit
def test_try_execute_calls_order_model(monkeypatch) -> None:
    calls = []

    def fake_execute_order(order, bar, *, max_trade_amount=None):
        calls.append((order, bar, max_trade_amount))
        return order_model.OrderExecution(
            symbol=order.symbol,
            trade_date=bar.trade_date,
            side=order.side,
            requested_quantity=order.quantity,
            filled_quantity=order.quantity,
            fill_price=101.0,
            traded_amount=order.quantity * 101.0,
            status="filled",
            reject_reason=None,
        )

    monkeypatch.setattr(engine.order_model, "execute_order", fake_execute_order)

    record, cash_flow = engine._try_execute(
        "ETFA.SH",
        "buy",
        100,
        date(2024, 1, 3),
        _prices(),
        _master(),
        _config(),
        {},
        [date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert calls
    assert calls[0][0].symbol == "ETFA.SH"
    assert calls[0][0].side == "buy"
    assert calls[0][1].symbol == "ETFA.SH"
    assert record["status"] == "filled"
    assert cash_flow < 0


@pytest.mark.unit
def test_try_execute_limit_up_buy_rejected() -> None:
    record, cash_flow = engine._try_execute(
        "ETFA.SH",
        "buy",
        100,
        date(2024, 1, 3),
        _prices(open=110.0, limit_up=110.0),
        _master(),
        _config(),
        {},
        [date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert record["status"] == "rejected"
    assert record["reject_reason"] == "limit_up"
    assert cash_flow == 0.0


@pytest.mark.unit
def test_try_execute_limit_down_sell_rejected() -> None:
    holdings = {"ETFA.SH": {"quantity": 100, "last_buy_date": date(2024, 1, 2)}}

    record, cash_flow = engine._try_execute(
        "ETFA.SH",
        "sell",
        100,
        date(2024, 1, 3),
        _prices(open=90.0, limit_down=90.0),
        _master(),
        _config(),
        holdings,
        [date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert record["status"] == "rejected"
    assert record["reject_reason"] == "limit_down"
    assert cash_flow == 0.0


@pytest.mark.unit
def test_try_execute_suspended_rejected() -> None:
    record, cash_flow = engine._try_execute(
        "ETFA.SH",
        "buy",
        100,
        date(2024, 1, 3),
        _prices(is_suspended=True),
        _master(),
        _config(),
        {},
        [date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert record["status"] == "rejected"
    assert record["reject_reason"] == "suspended"
    assert cash_flow == 0.0


@pytest.mark.unit
def test_try_execute_t1_violation_still_rejected() -> None:
    holdings = {"ETFA.SH": {"quantity": 100, "last_buy_date": date(2024, 1, 3)}}

    record, cash_flow = engine._try_execute(
        "ETFA.SH",
        "sell",
        100,
        date(2024, 1, 3),
        _prices(),
        _master(),
        _config(),
        holdings,
        [date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert record["status"] == "rejected"
    assert record["reject_reason"] == "t1_violation"
    assert cash_flow == 0.0


@pytest.mark.unit
def test_try_execute_fees_are_charged_on_fill() -> None:
    record, cash_flow = engine._try_execute(
        "ETFA.SH",
        "buy",
        100,
        date(2024, 1, 3),
        _prices(),
        _master(),
        _config(),
        {},
        [date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert record["status"] == "filled"
    assert record["commission"] > 0
    assert record["total_cost"] >= record["commission"]
    assert cash_flow == pytest.approx(-(record["amount"] + record["total_cost"]))


@pytest.mark.unit
def test_try_execute_slippage_price_is_used_on_fill() -> None:
    record, _ = engine._try_execute(
        "ETFA.SH",
        "buy",
        100,
        date(2024, 1, 3),
        _prices(open=100.0),
        _master(),
        _config(slippage_bps=10.0),
        {},
        [date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert record["status"] == "filled"
    assert record["price"] > 100.0
    assert record["amount"] == pytest.approx(record["quantity"] * record["price"])


@pytest.mark.unit
def test_try_execute_capacity_cap_partially_fills_order() -> None:
    record, cash_flow = engine._try_execute(
        "ETFA.SH",
        "buy",
        1_000,
        date(2024, 1, 3),
        _prices_with_adv_history(prior_amount=100_000.0),
        _master(),
        _config(slippage_bps=0.0),
        {},
        [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
    )

    assert record["status"] == "partial_filled"
    assert record["reject_reason"] == "capacity_capped"
    assert record["amount"] <= 5_000.0 + 1e-9
    assert 0 < record["quantity"] < 1_000
    assert cash_flow == pytest.approx(-(record["amount"] + record["total_cost"]))
