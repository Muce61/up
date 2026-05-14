"""AKShare 行情字段适配器。

本模块只负责把 AKShare 原始 ETF 日线字段标准化为项目内部
`prices_daily` schema；不负责联网拉取、不写快照，也不允许被策略代码直接调用。
"""
from __future__ import annotations

from datetime import date

import pandas as pd


RAW_FIELD_MAP = {
    "日期": "trade_date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
    "涨停": "limit_up",
    "跌停": "limit_down",
    "停牌": "is_suspended",
    "复权因子": "adj_factor",
}

REQUIRED_RAW_FIELDS = tuple(RAW_FIELD_MAP.keys())

PRICE_COLUMNS = [
    "symbol",
    "trade_date",
    "effective_date",
    "open",
    "high",
    "low",
    "close",
    "adj_factor",
    "volume",
    "amount",
    "limit_up",
    "limit_down",
    "is_suspended",
]


def _to_date(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce")
    return out.apply(lambda v: v.date() if pd.notna(v) else None)


def normalize_etf_daily(raw: pd.DataFrame, *, symbol: str, asof_date: date) -> pd.DataFrame:
    """标准化 AKShare ETF 日线数据到项目内部点时点行情 schema。

    `asof_date` 是研究当下日期；标准化结果要求 `effective_date <= asof_date`，
    防止尚不可见的行情进入回测快照。
    """
    missing = sorted(set(REQUIRED_RAW_FIELDS) - set(raw.columns))
    if missing:
        raise ValueError(f"missing required AKShare fields: {missing}")

    df = raw.loc[:, REQUIRED_RAW_FIELDS].rename(columns=RAW_FIELD_MAP).copy()
    df.insert(0, "symbol", symbol)
    df["trade_date"] = _to_date(df["trade_date"])
    df["effective_date"] = df["trade_date"]
    df["is_suspended"] = df["is_suspended"].fillna(False).astype(bool)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "adj_factor",
        "volume",
        "amount",
        "limit_up",
        "limit_down",
    ]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    _validate_price_schema(df, asof_date=asof_date)
    return df[PRICE_COLUMNS].sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def _validate_price_schema(df: pd.DataFrame, *, asof_date: date) -> None:
    if df["trade_date"].isna().any() or df["effective_date"].isna().any():
        raise ValueError("trade_date and effective_date must be valid dates")
    if (df["effective_date"] > asof_date).any():
        raise ValueError("effective_date must be <= asof_date")

    price_cols = ["open", "high", "low", "close", "limit_up", "limit_down"]
    if df[price_cols].isna().any().any() or (df[price_cols] <= 0).any().any():
        raise ValueError("price fields must be positive")
    if (df["high"] < df[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("high must be >= open, low and close")
    if (df["low"] > df[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("low must be <= open, high and close")
    if df["adj_factor"].isna().any() or (df["adj_factor"] <= 0).any():
        raise ValueError("adj_factor must be positive")
    if df["volume"].isna().any() or (df["volume"] < 0).any():
        raise ValueError("volume must be non-negative")
    if df["amount"].isna().any() or (df["amount"] <= 0).any():
        raise ValueError("amount must be positive")
