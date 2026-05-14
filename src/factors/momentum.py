"""动量与趋势因子。

所有公开函数必须接收 `asof_date` 并强制 PIT 截断；
输出含 `effective_date` 列，便于 lookahead 测试。
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

FACTOR_COLUMNS = ["symbol", "asof_date", "effective_date", "value"]


def _pit(prices: pd.DataFrame, asof_date: date) -> pd.DataFrame:
    """Point-in-time 截断：drop rows where trade_date > asof_date."""
    if prices.empty:
        return prices
    return prices[prices["trade_date"] <= asof_date].copy()


def _adj_close(df: pd.DataFrame) -> pd.Series:
    """前复权收盘价。"""
    return df["close"].astype(float) * df["adj_factor"].astype(float)


def momentum(prices: pd.DataFrame, asof_date: date, window: int) -> pd.DataFrame:
    """N 日动量：close_t / close_{t-N} - 1。

    停牌日不计入窗口；史料不足时返回 NaN。
    """
    pit = _pit(prices, asof_date)
    if pit.empty:
        return pd.DataFrame(columns=FACTOR_COLUMNS)
    rows = []
    for symbol, grp in pit.groupby("symbol"):
        active = grp[~grp["is_suspended"].astype(bool)].sort_values("trade_date")
        if len(active) < window + 1:
            value: float = float("nan")
        else:
            adj = _adj_close(active)
            recent = adj.iloc[-(window + 1):].to_numpy()
            value = float(recent[-1] / recent[0] - 1.0) if recent[0] > 0 else float("nan")
        rows.append({
            "symbol": symbol,
            "asof_date": asof_date,
            "effective_date": asof_date,
            "value": value,
        })
    return pd.DataFrame(rows, columns=FACTOR_COLUMNS)


def sma(prices: pd.DataFrame, asof_date: date, window: int) -> pd.DataFrame:
    """简单移动均线。"""
    pit = _pit(prices, asof_date)
    if pit.empty:
        return pd.DataFrame(columns=FACTOR_COLUMNS)
    rows = []
    for symbol, grp in pit.groupby("symbol"):
        active = grp[~grp["is_suspended"].astype(bool)].sort_values("trade_date")
        if len(active) < window:
            value: float = float("nan")
        else:
            adj = _adj_close(active)
            value = float(adj.iloc[-window:].mean())
        rows.append({
            "symbol": symbol,
            "asof_date": asof_date,
            "effective_date": asof_date,
            "value": value,
        })
    return pd.DataFrame(rows, columns=FACTOR_COLUMNS)


def trend_pass(prices: pd.DataFrame, asof_date: date, ma_window: int = 200) -> pd.DataFrame:
    """趋势过滤：close_t > sma_t(ma_window)。布尔。"""
    pit = _pit(prices, asof_date)
    if pit.empty:
        return pd.DataFrame(columns=FACTOR_COLUMNS)
    rows = []
    for symbol, grp in pit.groupby("symbol"):
        active = grp[~grp["is_suspended"].astype(bool)].sort_values("trade_date")
        if len(active) < ma_window:
            value: bool = False
        else:
            adj = _adj_close(active)
            ma = float(adj.iloc[-ma_window:].mean())
            value = bool(float(adj.iloc[-1]) > ma)
        rows.append({
            "symbol": symbol,
            "asof_date": asof_date,
            "effective_date": asof_date,
            "value": value,
        })
    return pd.DataFrame(rows, columns=FACTOR_COLUMNS)
