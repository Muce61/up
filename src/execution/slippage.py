"""默认基于成交额 / ATR 的保守滑点模型。

单一职责：只估算滑点并把它应用到成交价；不判断交易可行性、不计算费用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class SlippageConfig:
    """保守滑点参数。

    - `base_bps`：最低单边滑点；
    - `atr_multiplier`：把 ATR 百分比转换为 bps 后的乘数；
    - `participation_bps_per_1pct_adv`：订单金额每占 ADV 1% 增加的 bps；
    - `max_bps`：极端输入下的滑点上限，避免异常数据放大结果。
    """

    base_bps: float = 5.0
    atr_multiplier: float = 0.10
    participation_bps_per_1pct_adv: float = 1.0
    max_bps: float = 100.0


def estimate_slippage_bps(
    *,
    order_amount: float,
    adv_amount: float | None = None,
    atr_pct: float | None = None,
    config: SlippageConfig | None = None,
) -> float:
    """估算单边滑点 bps。

    缺少 ADV 或 ATR 时只使用可用部分，保证 fixtures 和早期快照也能确定性运行。
    """
    cfg = config or SlippageConfig()
    if order_amount < 0:
        raise ValueError("order_amount must be non-negative")

    bps = float(cfg.base_bps)

    if atr_pct is not None and atr_pct > 0:
        bps += float(atr_pct) * 10_000.0 * float(cfg.atr_multiplier)

    if adv_amount is not None and adv_amount > 0 and order_amount > 0:
        participation_pct = float(order_amount) / float(adv_amount) * 100.0
        bps += participation_pct * float(cfg.participation_bps_per_1pct_adv)

    return float(max(0.0, min(bps, float(cfg.max_bps))))


def apply_slippage(side: TradeSide, *, base_price: float, slippage_bps: float) -> float:
    """把滑点应用到基础成交价。买入上浮，卖出下浮。"""
    if base_price <= 0:
        raise ValueError("base_price must be positive")
    if slippage_bps < 0:
        raise ValueError("slippage_bps must be non-negative")

    ratio = float(slippage_bps) / 10_000.0
    if side == "buy":
        return float(base_price) * (1.0 + ratio)
    if side == "sell":
        return float(base_price) * (1.0 - ratio)
    raise ValueError(f"unsupported side: {side}")


def execution_price(
    *,
    side: TradeSide,
    base_price: float,
    order_amount: float,
    adv_amount: float | None = None,
    atr_pct: float | None = None,
    config: SlippageConfig | None = None,
) -> float:
    """估算含滑点成交价。"""
    bps = estimate_slippage_bps(
        order_amount=order_amount,
        adv_amount=adv_amount,
        atr_pct=atr_pct,
        config=config,
    )
    return apply_slippage(side, base_price=base_price, slippage_bps=bps)
