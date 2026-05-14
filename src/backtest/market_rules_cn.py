"""A 股交易制度的**唯一定义点**（CLAUDE.md §3）。

本模块定义 T+1、涨跌幅、停牌、退市整理、印花税、佣金等规则。
策略 / 因子 / 信号代码**禁止**直接 import 本模块；必须经由
`src/execution/tradeability.py` 唯一访问入口。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TOLERANCE = 1e-6
TRADING_DAYS_PER_YEAR = 252

TradeSide = Literal["buy", "sell"]


# ---------------------------------------------------------------------------
# 结算与品类
# ---------------------------------------------------------------------------

_SETTLEMENT_LAG_BY_TYPE: dict[str, int] = {
    "broad_index": 1,
    "sector": 1,
    "bond": 0,
    "gold": 0,
    "cross_border": 0,
    "money_market": 0,
}


def settlement_lag(etf_type: str) -> int:
    """返回 ETF 类型对应的 T+N 滞后（0 或 1）。未知类型默认 T+1（保守）。"""
    return _SETTLEMENT_LAG_BY_TYPE.get(etf_type, 1)


# ---------------------------------------------------------------------------
# 涨跌幅档位
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LimitBand:
    up_pct: float
    down_pct: float


_LIMIT_BAND_BY_TYPE: dict[str, tuple[float, float]] = {
    "broad_index": (0.10, 0.10),
    "sector": (0.10, 0.10),
    "bond": (0.10, 0.10),
    "gold": (0.10, 0.10),
    "cross_border": (0.10, 0.10),
    "money_market": (0.0, 0.0),
}


def limit_band(etf_type: str) -> LimitBand:
    """返回 ETF 类型的默认涨跌幅档位。"""
    up, down = _LIMIT_BAND_BY_TYPE.get(etf_type, (0.10, 0.10))
    return LimitBand(up_pct=up, down_pct=down)


def is_at_limit_up(price: float, limit_up: float) -> bool:
    return price >= limit_up - TOLERANCE


def is_at_limit_down(price: float, limit_down: float) -> bool:
    return price <= limit_down + TOLERANCE


# ---------------------------------------------------------------------------
# 费用规则（仅返回率；金额计算在 execution/fee_model.py）
# ---------------------------------------------------------------------------

def stamp_tax_rate(applicable: bool, side: TradeSide, default_rate: float = 0.0005) -> float:
    """A 股印花税：股票卖出收 0.05%；ETF 默认不收（applicable=False）。"""
    if not applicable:
        return 0.0
    return default_rate if side == "sell" else 0.0
