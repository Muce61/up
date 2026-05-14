"""ADV × N 容量约束（超出按比例削权）。

单一职责：只计算成交额容量上限与削减结果，不判断交易可行性、不计算费用。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapacityResult:
    requested_amount: float
    max_amount: float
    allowed_amount: float
    scale: float
    is_capped: bool
    reason: str | None = None


def max_trade_amount(*, adv_amount: float, capacity_pct: float) -> float:
    """单标的单日最大成交额 = ADV × capacity_pct。"""
    if capacity_pct < 0:
        raise ValueError("capacity_pct must be non-negative")
    if adv_amount <= 0:
        return 0.0
    return float(adv_amount) * float(capacity_pct)


def cap_order_amount(
    *,
    requested_amount: float,
    adv_amount: float,
    capacity_pct: float,
) -> CapacityResult:
    """按 ADV 容量上限削减订单金额。"""
    if requested_amount < 0:
        raise ValueError("requested_amount must be non-negative")
    limit = max_trade_amount(adv_amount=adv_amount, capacity_pct=capacity_pct)
    if requested_amount == 0:
        return CapacityResult(
            requested_amount=0.0,
            max_amount=limit,
            allowed_amount=0.0,
            scale=0.0,
            is_capped=False,
            reason=None,
        )
    if limit <= 0:
        return CapacityResult(
            requested_amount=float(requested_amount),
            max_amount=limit,
            allowed_amount=0.0,
            scale=0.0,
            is_capped=True,
            reason="capacity_unavailable",
        )
    if requested_amount <= limit:
        return CapacityResult(
            requested_amount=float(requested_amount),
            max_amount=limit,
            allowed_amount=float(requested_amount),
            scale=1.0,
            is_capped=False,
            reason=None,
        )
    return CapacityResult(
        requested_amount=float(requested_amount),
        max_amount=limit,
        allowed_amount=limit,
        scale=limit / float(requested_amount),
        is_capped=True,
        reason="capacity_capped",
    )
