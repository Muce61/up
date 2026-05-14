"""撮合可行性 — 策略 / 因子 / 信号访问交易规则的**唯一访问入口**。

CLAUDE.md §3 强制约定：策略代码不得直接 import backtest.market_rules_cn；
所有判断必须经此处。本模块只做布尔判断，不修改状态。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from backtest import market_rules_cn as rules

TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class TradeabilityResult:
    is_ok: bool
    reason: str | None = None


def is_tradeable(
    *,
    side: TradeSide,
    price: float,
    limit_up: float,
    limit_down: float,
    is_suspended: bool,
    is_delisted: bool,
) -> TradeabilityResult:
    """判断单一标的在某次撮合上是否可成交。

    输入是"撮合时的快照"：价格、当日涨跌停价、停牌状态、退市状态。
    """
    if is_suspended:
        return TradeabilityResult(False, "suspended")
    if is_delisted:
        return TradeabilityResult(False, "delisted")
    if side == "buy" and rules.is_at_limit_up(price, limit_up):
        return TradeabilityResult(False, "limit_up")
    if side == "sell" and rules.is_at_limit_down(price, limit_down):
        return TradeabilityResult(False, "limit_down")
    return TradeabilityResult(True, None)


def settlement_lag(etf_type: str) -> int:
    """对外暴露品类结算滞后（用于 T+1 检查），转发到 market_rules_cn。"""
    return rules.settlement_lag(etf_type)


def is_t1_violation(
    *,
    etf_type: str,
    last_buy_trade_date: date | None,
    current_trade_date: date,
    trading_calendar: list[date],
) -> bool:
    """卖出时 T+1 是否被违反。

    Returns True 则禁止卖出。
    - 若品类 settlement_lag = 0 → 永不违反；
    - 若 last_buy_trade_date 是 None → 永不违反（无买入记录）；
    - 否则要求 current_trade_date 与 last_buy_trade_date 之间隔 ≥ lag 个**交易日**。
    """
    lag = rules.settlement_lag(etf_type)
    if lag <= 0 or last_buy_trade_date is None:
        return False
    if current_trade_date <= last_buy_trade_date:
        return True
    try:
        idx_buy = trading_calendar.index(last_buy_trade_date)
        idx_now = trading_calendar.index(current_trade_date)
    except ValueError:
        return False
    return (idx_now - idx_buy) < lag


def limit_band_for_type(etf_type: str) -> rules.LimitBand:
    """转发涨跌幅档位查询。"""
    return rules.limit_band(etf_type)


def stamp_tax_rate(applicable: bool, side: TradeSide, default_rate: float) -> float:
    """转发印花税规则，费用模型不直接访问 market_rules_cn。"""
    return rules.stamp_tax_rate(applicable, side, default_rate)
