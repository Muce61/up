# ruff: noqa: RUF002
"""Reference layer schema 与 PIT 校验。

P1 Step 1 只冻结真实数据链路需要的最小 reference 契约：
- trading_calendar
- etf_master

本模块不联网、不读写真实数据文件、不生成 snapshot、不接回测，
只提供 deterministic 的 DataFrame 校验与 asof_date 过滤。
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

VALID_ETF_TYPES = {
    "broad_index",
    "sector",
    "bond",
    "gold",
    "cross_border",
    "money_market",
}
VALID_SETTLEMENTS = {"T+0", "T+1"}
VALID_EXCHANGES = {"SH", "SZ", "BJ"}
VALID_MARKETS = {"SH", "SZ", "BJ"}
BOOL_TRUTHY = {"true", "1", "yes", "y"}
BOOL_FALSY = {"false", "0", "no", "n", ""}

TRADING_CALENDAR_COLUMNS = [
    "trade_date",
    "is_open",
    "prev_trade_date",
    "next_trade_date",
    "market",
    "effective_date",
]

ETF_MASTER_COLUMNS = [
    "symbol",
    "name",
    "etf_type",
    "settlement",
    "stamp_tax_applicable",
    "list_date",
    "delist_date",
    "exchange",
    "effective_date",
]


def load_trading_calendar(path: str | Path, *, asof_date: date) -> pd.DataFrame:
    """从 CSV 加载 trading_calendar，并按 asof_date 返回 PIT 可见日历。"""
    df = _read_csv(path, table="trading_calendar")
    _convert_date_columns(
        df, ["trade_date", "prev_trade_date", "next_trade_date", "effective_date"]
    )
    _convert_bool_columns(df, ["is_open"])
    return filter_visible_trading_calendar(df, asof_date=asof_date)


def load_etf_master(path: str | Path, *, asof_date: date) -> pd.DataFrame:
    """从 CSV 加载 etf_master，并按 asof_date 返回 PIT 可见主数据。"""
    df = _read_csv(path, table="etf_master")
    _convert_date_columns(df, ["list_date", "delist_date", "effective_date"])
    _convert_bool_columns(df, ["stamp_tax_applicable"])
    return filter_visible_etf_master(df, asof_date=asof_date)


def validate_trading_calendar(df: pd.DataFrame, *, asof_date: date | None = None) -> pd.DataFrame:
    """校验交易日历 reference 契约。"""
    out = df.copy()
    _require_columns(out, TRADING_CALENDAR_COLUMNS, "trading_calendar")
    _require_non_empty(out, "trading_calendar")

    for col, allow_null in [
        ("trade_date", False),
        ("prev_trade_date", True),
        ("next_trade_date", True),
        ("effective_date", False),
    ]:
        _check_date_column(out, col, "trading_calendar", allow_null=allow_null)

    _check_bool_column(out, "is_open", "trading_calendar")
    _check_str_allowed(out, "market", "trading_calendar", VALID_MARKETS)
    _check_unique(out, ["market", "trade_date"], "trading_calendar")

    if asof_date is not None:
        _check_asof_boundary(out, "effective_date", asof_date, "trading_calendar")
        _check_asof_boundary(out, "trade_date", asof_date, "trading_calendar")

    for _idx, row in out.iterrows():
        prev_date = row["prev_trade_date"]
        next_date = row["next_trade_date"]
        trade_date = row["trade_date"]
        if _not_null(prev_date) and not prev_date < trade_date:
            raise ValueError("trading_calendar.prev_trade_date must be < trade_date")
        if _not_null(next_date) and not next_date > trade_date:
            raise ValueError("trading_calendar.next_trade_date must be > trade_date")

    return out.sort_values(["market", "trade_date"]).reset_index(drop=True)


def validate_etf_master(df: pd.DataFrame, *, asof_date: date | None = None) -> pd.DataFrame:
    """校验 ETF 主数据 reference 契约。"""
    out = df.copy()
    _require_columns(out, ETF_MASTER_COLUMNS, "etf_master")
    _require_non_empty(out, "etf_master")

    for col in ["symbol", "name"]:
        _check_str_non_empty(out, col, "etf_master")
    _check_str_allowed(out, "etf_type", "etf_master", VALID_ETF_TYPES)
    _check_str_allowed(out, "settlement", "etf_master", VALID_SETTLEMENTS)
    _check_str_allowed(out, "exchange", "etf_master", VALID_EXCHANGES)
    _check_bool_column(out, "stamp_tax_applicable", "etf_master")

    for col, allow_null in [
        ("list_date", False),
        ("delist_date", True),
        ("effective_date", False),
    ]:
        _check_date_column(out, col, "etf_master", allow_null=allow_null)

    if asof_date is not None:
        _check_asof_boundary(out, "effective_date", asof_date, "etf_master")

    for _, row in out.iterrows():
        if _not_null(row["delist_date"]) and row["delist_date"] < row["list_date"]:
            raise ValueError("etf_master.delist_date must be >= list_date")

    return out.sort_values(["symbol", "effective_date"]).reset_index(drop=True)


def filter_visible_etf_master(df: pd.DataFrame, *, asof_date: date) -> pd.DataFrame:
    """返回 asof_date 当时可见的 ETF 主数据。

    规则：
    - effective_date > asof_date 的记录不可见；
    - list_date > asof_date 的 ETF 不可见；
    - delist_date <= asof_date 的 ETF 保留，但 can_open_new_position=False。
    """
    validated = validate_etf_master(df)
    visible = validated[
        (validated["effective_date"] <= asof_date) & (validated["list_date"] <= asof_date)
    ].copy()

    if visible.empty:
        visible["can_open_new_position"] = pd.Series(dtype=bool)
        return visible.reset_index(drop=True)

    visible = visible.sort_values(["symbol", "effective_date"]).drop_duplicates(
        subset=["symbol"], keep="last"
    )
    visible["can_open_new_position"] = visible["delist_date"].apply(
        lambda value: not (_not_null(value) and value <= asof_date)
    )
    return visible.sort_values("symbol").reset_index(drop=True)


def filter_visible_trading_calendar(df: pd.DataFrame, *, asof_date: date) -> pd.DataFrame:
    """返回 asof_date 当时可见的交易日历。"""
    validated = validate_trading_calendar(df)
    visible = validated[
        (validated["effective_date"] <= asof_date) & (validated["trade_date"] <= asof_date)
    ].copy()
    return visible.sort_values(["market", "trade_date"]).reset_index(drop=True)


def _read_csv(path: str | Path, *, table: str) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"{table} reference file does not exist: {csv_path}")
    return pd.read_csv(csv_path)


def _convert_date_columns(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        df[col] = parsed.apply(lambda value: value.date() if pd.notna(value) else None)


def _convert_bool_columns(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(lambda value, column=col: _parse_bool(value, col=column))


def _parse_bool(value: object, *, col: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if _is_null(value):
        raise ValueError(f"{col} must be bool and must not be null")
    lowered = str(value).strip().lower()
    if lowered in BOOL_TRUTHY:
        return True
    if lowered in BOOL_FALSY:
        return False
    raise ValueError(f"{col} must be bool-compatible, got {value!r}")


def _require_columns(df: pd.DataFrame, required: list[str], table: str) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"{table} missing required columns: {missing}")


def _require_non_empty(df: pd.DataFrame, table: str) -> None:
    if df.empty:
        raise ValueError(f"{table} must not be empty")


def _check_date_column(df: pd.DataFrame, col: str, table: str, *, allow_null: bool) -> None:
    for idx, value in df[col].items():
        if _is_null(value):
            if allow_null:
                continue
            raise ValueError(f"{table}.{col} row {idx} must not be null")
        if isinstance(value, datetime):
            raise ValueError(f"{table}.{col} row {idx} must be datetime.date, not datetime")
        if not isinstance(value, date):
            raise ValueError(f"{table}.{col} row {idx} must be datetime.date")


def _check_bool_column(df: pd.DataFrame, col: str, table: str) -> None:
    for idx, value in df[col].items():
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError(f"{table}.{col} row {idx} must be bool")


def _check_str_non_empty(df: pd.DataFrame, col: str, table: str) -> None:
    for idx, value in df[col].items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{table}.{col} row {idx} must be non-empty str")


def _check_str_allowed(df: pd.DataFrame, col: str, table: str, allowed: set[str]) -> None:
    for idx, value in df[col].items():
        if value not in allowed:
            raise ValueError(f"{table}.{col} row {idx} must be one of {sorted(allowed)}")


def _check_unique(df: pd.DataFrame, cols: list[str], table: str) -> None:
    duplicated = df.duplicated(subset=cols, keep=False)
    if duplicated.any():
        raise ValueError(f"{table} duplicated keys for columns: {cols}")


def _check_asof_boundary(df: pd.DataFrame, col: str, asof_date: date, table: str) -> None:
    future_rows = df[df[col] > asof_date]
    if not future_rows.empty:
        raise ValueError(f"{table}.{col} must be <= asof_date")


def _is_null(value: object) -> bool:
    return value is None or pd.isna(value)


def _not_null(value: object) -> bool:
    return not _is_null(value)
