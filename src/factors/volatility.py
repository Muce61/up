"""波动率因子（年化实现波动率 + 滚动最大回撤）。

公开函数都强制 PIT 截断；输出统一 schema。
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

FACTOR_COLUMNS = ["symbol", "asof_date", "effective_date", "value"]
TRADING_DAYS_PER_YEAR = 252


def _pit(prices: pd.DataFrame, asof_date: date) -> pd.DataFrame:
    if prices.empty:
        return prices
    return prices[prices["trade_date"] <= asof_date].copy()


def _adj_close(df: pd.DataFrame) -> pd.Series:
    return df["close"].astype(float) * df["adj_factor"].astype(float)


def realized_vol(prices: pd.DataFrame, asof_date: date, window: int = 20) -> pd.DataFrame:
    """对数收益样本标准差，年化（×√252）。"""
    pit = _pit(prices, asof_date)
    if pit.empty:
        return pd.DataFrame(columns=FACTOR_COLUMNS)
    rows = []
    for symbol, grp in pit.groupby("symbol"):
        active = grp[~grp["is_suspended"].astype(bool)].sort_values("trade_date")
        if len(active) < window + 1:
            value: float = float("nan")
        else:
            adj = _adj_close(active).to_numpy()
            recent = adj[-(window + 1):]
            with np.errstate(divide="ignore", invalid="ignore"):
                log_ret = np.log(recent[1:] / recent[:-1])
            log_ret = log_ret[np.isfinite(log_ret)]
            if len(log_ret) < 2:
                value = float("nan")
            else:
                value = float(np.std(log_ret, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
        rows.append({
            "symbol": symbol,
            "asof_date": asof_date,
            "effective_date": asof_date,
            "value": value,
        })
    return pd.DataFrame(rows, columns=FACTOR_COLUMNS)


def max_drawdown(prices: pd.DataFrame, asof_date: date, window: int = 60) -> pd.DataFrame:
    """N 日内最大回撤幅度（正数；越大越糟）。"""
    pit = _pit(prices, asof_date)
    if pit.empty:
        return pd.DataFrame(columns=FACTOR_COLUMNS)
    rows = []
    for symbol, grp in pit.groupby("symbol"):
        active = grp[~grp["is_suspended"].astype(bool)].sort_values("trade_date")
        if len(active) < window:
            value: float = float("nan")
        else:
            adj = _adj_close(active).to_numpy()[-window:]
            peak = np.maximum.accumulate(adj)
            drawdown = (peak - adj) / peak
            value = float(np.max(drawdown))
        rows.append({
            "symbol": symbol,
            "asof_date": asof_date,
            "effective_date": asof_date,
            "value": value,
        })
    return pd.DataFrame(rows, columns=FACTOR_COLUMNS)
