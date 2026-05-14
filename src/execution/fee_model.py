"""费用模型：佣金、印花税、过户费。

实现单一职责：只**计算成本**，不判断是否能成交（那是 tradeability 的事）。
配置来源见 config/fees/default.yaml。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from execution import tradeability

TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class FeeConfig:
    commission_rate: float = 0.00015
    min_commission: float = 5.0
    stamp_tax_rate: float = 0.0005
    transfer_fee_rate_sh: float = 0.0
    transfer_fee_rate_sz: float = 0.0
    slippage_bps: float = 5.0

    @classmethod
    def from_yaml(cls, path: str | Path) -> "FeeConfig":
        data = yaml.safe_load(Path(path).read_text())
        return cls(
            commission_rate=float(data.get("commission_rate", 0.00015)),
            min_commission=float(data.get("min_commission", 5.0)),
            stamp_tax_rate=float(data.get("stamp_tax_rate", 0.0005)),
            transfer_fee_rate_sh=float(data.get("transfer_fee_rate_sh", 0.0)),
            transfer_fee_rate_sz=float(data.get("transfer_fee_rate_sz", 0.0)),
            slippage_bps=float(data.get("slippage_bps", 5.0)),
        )


@dataclass(frozen=True)
class CostBreakdown:
    commission: float
    stamp_tax: float
    transfer_fee: float
    total: float


def calculate_cost(
    *,
    amount: float,
    side: TradeSide,
    stamp_tax_applicable: bool,
    exchange: str,
    config: FeeConfig,
) -> CostBreakdown:
    """计算一次成交的总费用。

    Parameters
    ----------
    amount : 成交金额（元）。
    side : 买 or 卖。
    stamp_tax_applicable : 该品类是否适用印花税（ETF 默认 False，股票 True）。
    exchange : "SH" 或 "SZ"。
    config : 费用配置。
    """
    commission = max(amount * config.commission_rate, config.min_commission)
    stamp_rate = tradeability.stamp_tax_rate(stamp_tax_applicable, side, config.stamp_tax_rate)
    stamp_tax = amount * stamp_rate
    transfer = config.transfer_fee_rate_sh if exchange == "SH" else config.transfer_fee_rate_sz
    transfer_fee = amount * transfer
    total = commission + stamp_tax + transfer_fee
    return CostBreakdown(
        commission=commission,
        stamp_tax=stamp_tax,
        transfer_fee=transfer_fee,
        total=total,
    )
