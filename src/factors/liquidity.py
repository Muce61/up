"""流动性因子：ADV（平均日成交额，元）。"""
from __future__ import annotations

from datetime import date

import pandas as pd

FACTOR_COLUMNS = ["symbol", "asof_date", "effective_date", "value"]


def _pit(prices: pd.DataFrame, asof_date: date) -> pd.DataFrame:
    if prices.empty:
        return prices
    return prices[prices["trade_date"] <= asof_date].copy()


def adv(prices: pd.DataFrame, asof_date: date, window: int = 60) -> pd.DataFrame:
    """过去 N 个交易日平均日成交额（元）。

    停牌日不计入窗口；不足窗口则使用现有有效样本计算（避免上市初期被全 NaN 拦截）。
    """
    pit = _pit(prices, asof_date)
    if pit.empty:
        return pd.DataFrame(columns=FACTOR_COLUMNS)
    rows = []
    for symbol, grp in pit.groupby("symbol"):
        active = grp[~grp["is_suspended"].astype(bool)].sort_values("trade_date")
        if active.empty:
            value: float = float("nan")
        else:
            sample = active.iloc[-window:]
            value = float(sample["amount"].mean())
        rows.append({
            "symbol": symbol,
            "asof_date": asof_date,
            "effective_date": asof_date,
            "value": value,
        })
    return pd.DataFrame(rows, columns=FACTOR_COLUMNS)
