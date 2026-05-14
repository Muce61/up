"""ETF 数据加载器。

只承担**数据加载与 PIT 截断**：主数据（YAML） + 行情（CSV/Parquet 快照） + 交易日历。
真正的 AKShare 拉取在 W4 实现（`src/data/akshare_adapter.py`）。
本模块不允许判断交易规则；那是 tradeability 的事。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import yaml

MASTER_COLUMNS = [
    "symbol",
    "name",
    "etf_type",
    "settlement",
    "stamp_tax_applicable",
    "list_date",
    "delist_date",
    "exchange",
]
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
CALENDAR_COLUMNS = ["trade_date", "is_open", "prev_trade_date", "next_trade_date"]


def _to_date(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce")
    return out.apply(lambda v: v.date() if pd.notna(v) else None)


def load_etf_master(config_path: str | Path) -> pd.DataFrame:
    """从 `config/universe/etf_pool.yaml` 加载 ETF 主数据。"""
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    rows = config.get("etfs", [])
    df = pd.DataFrame(rows)
    for col in MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df["list_date"] = _to_date(df["list_date"])
    df["delist_date"] = _to_date(df["delist_date"])
    df["stamp_tax_applicable"] = df["stamp_tax_applicable"].fillna(False).astype(bool)
    return df[MASTER_COLUMNS].reset_index(drop=True)


def load_prices(snapshot_path: str | Path, symbols: list[str] | None = None) -> pd.DataFrame:
    """从快照目录或单文件加载行情。支持 CSV 与 Parquet。"""
    path = Path(snapshot_path)
    if path.is_dir():
        candidates = [path / "prices.parquet", path / "prices.csv"]
        prices_file = next((p for p in candidates if p.exists()), None)
        if prices_file is None:
            raise FileNotFoundError(f"未在 {path} 找到 prices.parquet 或 prices.csv")
    else:
        prices_file = path
    if prices_file.suffix == ".csv":
        df = pd.read_csv(prices_file)
    else:
        df = pd.read_parquet(prices_file)
    df["trade_date"] = _to_date(df["trade_date"])
    if "effective_date" not in df.columns:
        df["effective_date"] = df["trade_date"]
    else:
        df["effective_date"] = _to_date(df["effective_date"])
    for col in PRICE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df["is_suspended"] = df["is_suspended"].fillna(False).astype(bool)
    if symbols:
        df = df[df["symbol"].isin(symbols)]
    return df[PRICE_COLUMNS].reset_index(drop=True)


def load_calendar(snapshot_path: str | Path) -> pd.DataFrame:
    """从快照目录或单文件加载交易日历。"""
    path = Path(snapshot_path)
    if path.is_dir():
        cal_file = path / "calendar.csv"
    else:
        cal_file = path
    df = pd.read_csv(cal_file)
    df["trade_date"] = _to_date(df["trade_date"])
    if "is_open" not in df.columns:
        df["is_open"] = True
    df["is_open"] = df["is_open"].fillna(True).astype(bool)
    if "prev_trade_date" in df.columns:
        df["prev_trade_date"] = _to_date(df["prev_trade_date"])
    else:
        df = df.sort_values("trade_date").reset_index(drop=True)
        df["prev_trade_date"] = [None] + df["trade_date"].tolist()[:-1]
    if "next_trade_date" in df.columns:
        df["next_trade_date"] = _to_date(df["next_trade_date"])
    else:
        df["next_trade_date"] = df["trade_date"].tolist()[1:] + [None]
    return df[CALENDAR_COLUMNS].reset_index(drop=True)


def filter_pit(df: pd.DataFrame, asof_date: date, date_col: str = "trade_date") -> pd.DataFrame:
    """对 DataFrame 做 PIT 截断（date_col <= asof_date）。"""
    return df[df[date_col] <= asof_date].copy()
