"""限价 / 市价订单模型与订单状态机。

本模块只负责把一笔订单与一根撮合 bar 转成成交结果；
涨跌停、停牌、退市等交易制度判断统一通过 `execution.tradeability`。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from execution import tradeability

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["filled", "partial_filled", "rejected"]


@dataclass(frozen=True)
class Order:
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: float | None = None


@dataclass(frozen=True)
class ExecutionBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    limit_up: float
    limit_down: float
    is_suspended: bool
    is_delisted: bool = False
    execution_price: float | None = None


@dataclass(frozen=True)
class OrderExecution:
    symbol: str
    trade_date: date
    side: OrderSide
    requested_quantity: int
    filled_quantity: int
    fill_price: float
    traded_amount: float
    status: OrderStatus
    reject_reason: str | None = None


def execute_order(
    order: Order,
    bar: ExecutionBar,
    *,
    max_trade_amount: float | None = None,
) -> OrderExecution:
    """按次日开盘价撮合单笔订单。

    `max_trade_amount` 表示单笔订单允许占用的最大成交额；超出时按金额上限削减数量。
    """
    if order.symbol != bar.symbol:
        return _rejected(order, bar, "symbol_mismatch")
    if order.quantity <= 0:
        return _rejected(order, bar, "invalid_quantity")
    if order.order_type == "limit" and order.limit_price is None:
        return _rejected(order, bar, "missing_limit_price")

    tradeable = tradeability.is_tradeable(
        side=order.side,
        price=float(bar.open),
        limit_up=float(bar.limit_up),
        limit_down=float(bar.limit_down),
        is_suspended=bool(bar.is_suspended),
        is_delisted=bool(bar.is_delisted),
    )
    if not tradeable.is_ok:
        return _rejected(order, bar, tradeable.reason or "not_tradeable")

    if not _limit_price_met(order, float(bar.open)):
        return _rejected(order, bar, "limit_price_not_met")

    fill_price = float(bar.execution_price if bar.execution_price is not None else bar.open)
    if fill_price <= 0:
        return _rejected(order, bar, "invalid_execution_price")
    filled_quantity = int(order.quantity)
    reject_reason: str | None = None
    status: OrderStatus = "filled"

    if max_trade_amount is not None:
        if max_trade_amount < fill_price:
            return _rejected(order, bar, "capacity_exceeded")
        capped_quantity = int(max_trade_amount // fill_price)
        if capped_quantity < filled_quantity:
            filled_quantity = capped_quantity
            status = "partial_filled"
            reject_reason = "capacity_capped"

    traded_amount = filled_quantity * fill_price
    return OrderExecution(
        symbol=order.symbol,
        trade_date=bar.trade_date,
        side=order.side,
        requested_quantity=int(order.quantity),
        filled_quantity=int(filled_quantity),
        fill_price=fill_price,
        traded_amount=float(traded_amount),
        status=status,
        reject_reason=reject_reason,
    )


def _limit_price_met(order: Order, open_price: float) -> bool:
    if order.order_type == "market":
        return True
    assert order.limit_price is not None
    if order.side == "buy":
        return open_price <= float(order.limit_price)
    return open_price >= float(order.limit_price)


def _rejected(order: Order, bar: ExecutionBar, reason: str) -> OrderExecution:
    return OrderExecution(
        symbol=order.symbol,
        trade_date=bar.trade_date,
        side=order.side,
        requested_quantity=int(order.quantity),
        filled_quantity=0,
        fill_price=0.0,
        traded_amount=0.0,
        status="rejected",
        reject_reason=reason,
    )
