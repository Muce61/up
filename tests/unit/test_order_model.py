"""单元测试：订单模型。"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from execution import order_model


def _bar(**overrides) -> order_model.ExecutionBar:
    data = {
        "symbol": "510300.SH",
        "trade_date": date(2024, 1, 2),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "limit_up": 110.0,
        "limit_down": 90.0,
        "is_suspended": False,
        "is_delisted": False,
    }
    data.update(overrides)
    return order_model.ExecutionBar(**data)


@pytest.mark.unit
def test_market_order_fills_at_open() -> None:
    order = order_model.Order(
        symbol="510300.SH",
        side="buy",
        quantity=100,
        order_type="market",
    )

    execution = order_model.execute_order(order, _bar())

    assert execution.status == "filled"
    assert execution.filled_quantity == 100
    assert execution.fill_price == pytest.approx(100.0)
    assert execution.traded_amount == pytest.approx(10_000.0)
    assert execution.reject_reason is None


@pytest.mark.unit
def test_limit_buy_rejected_when_open_above_limit() -> None:
    order = order_model.Order(
        symbol="510300.SH",
        side="buy",
        quantity=100,
        order_type="limit",
        limit_price=99.5,
    )

    execution = order_model.execute_order(order, _bar(open=100.0))

    assert execution.status == "rejected"
    assert execution.filled_quantity == 0
    assert execution.reject_reason == "limit_price_not_met"


@pytest.mark.unit
def test_limit_sell_rejected_when_open_below_limit() -> None:
    order = order_model.Order(
        symbol="510300.SH",
        side="sell",
        quantity=100,
        order_type="limit",
        limit_price=100.5,
    )

    execution = order_model.execute_order(order, _bar(open=100.0))

    assert execution.status == "rejected"
    assert execution.filled_quantity == 0
    assert execution.reject_reason == "limit_price_not_met"


@pytest.mark.unit
def test_limit_up_buy_rejected_by_tradeability() -> None:
    order = order_model.Order(
        symbol="510300.SH",
        side="buy",
        quantity=100,
        order_type="market",
    )

    execution = order_model.execute_order(order, _bar(open=110.0, limit_up=110.0))

    assert execution.status == "rejected"
    assert execution.reject_reason == "limit_up"


@pytest.mark.unit
def test_suspended_order_rejected_by_tradeability() -> None:
    order = order_model.Order(
        symbol="510300.SH",
        side="sell",
        quantity=100,
        order_type="market",
    )

    execution = order_model.execute_order(order, _bar(is_suspended=True))

    assert execution.status == "rejected"
    assert execution.reject_reason == "suspended"


@pytest.mark.unit
def test_capacity_cap_partially_fills_order() -> None:
    order = order_model.Order(
        symbol="510300.SH",
        side="buy",
        quantity=100,
        order_type="market",
    )

    execution = order_model.execute_order(order, _bar(open=100.0), max_trade_amount=4_500.0)

    assert execution.status == "partial_filled"
    assert execution.filled_quantity == 45
    assert execution.traded_amount == pytest.approx(4_500.0)
    assert execution.reject_reason == "capacity_capped"


@pytest.mark.unit
def test_capacity_too_small_rejects_order() -> None:
    order = order_model.Order(
        symbol="510300.SH",
        side="buy",
        quantity=100,
        order_type="market",
    )

    execution = order_model.execute_order(order, _bar(open=100.0), max_trade_amount=99.0)

    assert execution.status == "rejected"
    assert execution.filled_quantity == 0
    assert execution.reject_reason == "capacity_exceeded"


@pytest.mark.unit
def test_order_model_does_not_import_market_rules_directly() -> None:
    path = Path(order_model.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "backtest.market_rules_cn" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in {"backtest", "backtest.market_rules_cn"}
