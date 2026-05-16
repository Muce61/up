"""Deterministic AKShare-shaped raw sample generator for regression tests.

This module is test infrastructure only. It does not fetch network data, does not create
strategies, and does not tune strategy parameters.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from data.akshare_adapter import REQUIRED_RAW_FIELDS

DEFAULT_SYMBOLS = (
    "510300.SH",
    "510500.SH",
    "510050.SH",
    "159949.SZ",
    "588000.SH",
    "512760.SH",
)
DEFAULT_END_DATE = date(2026, 5, 15)


def build_synthetic_raw(
    raw_root: str | Path,
    *,
    n_days: int = 400,
    seed: int = 20260515,
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS,
    end_date: date = DEFAULT_END_DATE,
) -> date:
    """Write deterministic AKShare-shaped raw CSV files and return the asof date.

    The files are intentionally synthetic and are only used by regression tests that
    validate the engineering data path: raw -> snapshot -> loader -> backtest.
    """
    if n_days <= 0:
        raise ValueError("n_days must be positive")
    if not symbols:
        raise ValueError("symbols must not be empty")

    asof_date = end_date
    trade_dates = [d.date() for d in pd.bdate_range(end=end_date, periods=n_days)]
    raw_dir = Path(raw_root) / asof_date.strftime("%Y%m%d")
    raw_dir.mkdir(parents=True, exist_ok=True)

    for idx, symbol in enumerate(symbols):
        raw = _build_symbol_raw(symbol=symbol, trade_dates=trade_dates, seed=seed + idx)
        raw.loc[:, REQUIRED_RAW_FIELDS].to_csv(
            raw_dir / f"{symbol}.csv",
            index=False,
            lineterminator="\n",
        )

    return asof_date


def _build_symbol_raw(*, symbol: str, trade_dates: list[date], seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(trade_dates)
    symbol_offset = (sum(ord(ch) for ch in symbol) % 17) / 10_000.0
    daily_drift = 0.00015 + symbol_offset
    daily_vol = 0.006 + ((seed % 7) / 10_000.0)

    returns = rng.normal(loc=daily_drift, scale=daily_vol, size=n)
    base_price = 1.0 + ((seed % 13) * 0.08)
    close = base_price * np.exp(np.cumsum(returns))
    open_ = close * (1.0 + rng.normal(loc=0.0, scale=0.0015, size=n))
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.001, 0.006, size=n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.001, 0.006, size=n))

    open_ = np.round(open_, 4)
    close = np.round(close, 4)
    high = np.maximum.reduce([np.round(high, 4), open_, close])
    low = np.minimum.reduce([np.round(low, 4), open_, close])

    prev_close = np.concatenate([[base_price], close[:-1]])
    volume = rng.integers(80_000_000, 160_000_000, size=n)
    amount = close * volume

    return pd.DataFrame(
        {
            "日期": [d.isoformat() for d in trade_dates],
            "开盘": open_,
            "最高": high,
            "最低": low,
            "收盘": close,
            "成交量": volume.astype(int),
            "成交额": np.round(amount, 2),
            "涨停": np.round(prev_close * 1.10, 4),
            "跌停": np.round(prev_close * 0.90, 4),
            "停牌": [False] * n,
            "复权因子": [1.0] * n,
        },
        columns=REQUIRED_RAW_FIELDS,
    )
