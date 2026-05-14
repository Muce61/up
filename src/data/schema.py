"""数据契约 schema 校验（强制 docs/data_contract.md）。

prices / master / calendar 三类 DataFrame 进入回测引擎或数据加载器出口前，
必须先通过这里。本模块**只校验结构与口径**：

- 不判断交易规则（那是 execution/tradeability.py 的事）；
- 不计算费用 / 滑点 / 容量；
- 不修改业务数值（normalize 仅补齐契约要求的派生列，如 prices 的 effective_date）。

任何违约都抛 SchemaError，且消息必须包含具体字段名与行号，便于定位。
"""
from __future__ import annotations

import datetime as _dt
from typing import Iterable

import numpy as np
import pandas as pd

_EPS = 1e-9


class SchemaError(ValueError):
    """数据契约被违反时抛出。"""


# ---------------------------------------------------------------------------
# 列定义（对齐 docs/data_contract.md §三）
# ---------------------------------------------------------------------------

PRICE_REQUIRED_COLUMNS = [
    "symbol",
    "trade_date",
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
MASTER_REQUIRED_COLUMNS = [
    "symbol",
    "name",
    "etf_type",
    "settlement",
    "stamp_tax_applicable",
    "list_date",
    "delist_date",
    "exchange",
]
CALENDAR_REQUIRED_COLUMNS = [
    "trade_date",
    "is_open",
    "prev_trade_date",
    "next_trade_date",
]

VALID_ETF_TYPES = {
    "broad_index",
    "sector",
    "bond",
    "gold",
    "cross_border",
    "money_market",
}
VALID_SETTLEMENTS = {"T+1", "T+0"}
VALID_EXCHANGES = {"SH", "SZ", "BJ"}


# ---------------------------------------------------------------------------
# 通用校验原语
# ---------------------------------------------------------------------------

def _is_null(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (ValueError, TypeError):
        return False


def _require_columns(df: pd.DataFrame, required: Iterable[str], table: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(f"{table}: 缺少必需列 {missing}")


def _require_non_empty(df: pd.DataFrame, table: str) -> None:
    if df is None or len(df) == 0:
        raise SchemaError(f"{table}: DataFrame 为空，契约要求至少一行")


def _check_pure_date_column(df: pd.DataFrame, col: str, table: str, *, allow_null: bool) -> None:
    """该列每个非空值必须是 datetime.date，且不能是 datetime.datetime / pd.Timestamp / str。

    契约（data_contract.md §五）：日期统一用 date；禁止字符串日期混用、禁止 naive datetime。
    """
    series = df[col]
    for idx, value in series.items():
        if _is_null(value):
            if allow_null:
                continue
            raise SchemaError(f"{table}.{col}: 第 {idx} 行为空，但该列不允许空值")
        # pd.Timestamp 是 datetime.datetime 的子类，这里一并拒绝
        if isinstance(value, _dt.datetime):
            raise SchemaError(
                f"{table}.{col}: 第 {idx} 行是 {type(value).__name__}，"
                f"契约要求纯 datetime.date（禁止 datetime / Timestamp / naive datetime）"
            )
        if not isinstance(value, _dt.date):
            raise SchemaError(
                f"{table}.{col}: 第 {idx} 行类型为 {type(value).__name__}，契约要求 datetime.date"
            )


def _check_numeric_column(
    df: pd.DataFrame,
    col: str,
    table: str,
    *,
    min_value: float | None = None,
    strict_min: bool = False,
) -> pd.Series:
    """校验列为数值、非 NaN、有限；可选下界。返回转为 float 的 Series。"""
    raw = df[col]
    num = pd.to_numeric(raw, errors="coerce")
    coerce_failed = num.isna() & ~raw.apply(_is_null)
    if coerce_failed.any():
        bad_rows = df.index[coerce_failed].tolist()
        raise SchemaError(f"{table}.{col}: 行 {bad_rows} 不是数值")
    if num.isna().any():
        bad_rows = df.index[num.isna()].tolist()
        raise SchemaError(f"{table}.{col}: 行 {bad_rows} 为空/NaN，该列不允许缺失")
    arr = num.to_numpy(dtype=float)
    if not np.isfinite(arr).all():
        bad_rows = df.index[~np.isfinite(arr)].tolist()
        raise SchemaError(f"{table}.{col}: 行 {bad_rows} 含 inf")
    if min_value is not None:
        if strict_min:
            violating = num[num <= min_value]
            op = ">"
        else:
            violating = num[num < min_value - _EPS]
            op = ">="
        if not violating.empty:
            raise SchemaError(
                f"{table}.{col}: 行 {violating.index.tolist()} 违反约束 {op} {min_value}"
            )
    return num


def _check_bool_column(df: pd.DataFrame, col: str, table: str) -> None:
    series = df[col]
    for idx, value in series.items():
        if not isinstance(value, (bool, np.bool_)):
            raise SchemaError(
                f"{table}.{col}: 第 {idx} 行类型为 {type(value).__name__}，契约要求 bool"
            )


def _check_str_column(
    df: pd.DataFrame,
    col: str,
    table: str,
    *,
    allowed: set[str] | None = None,
    non_empty: bool = True,
) -> None:
    series = df[col]
    for idx, value in series.items():
        if not isinstance(value, str):
            raise SchemaError(
                f"{table}.{col}: 第 {idx} 行类型为 {type(value).__name__}，契约要求 str"
            )
        if non_empty and value.strip() == "":
            raise SchemaError(f"{table}.{col}: 第 {idx} 行为空字符串")
        if allowed is not None and value not in allowed:
            raise SchemaError(
                f"{table}.{col}: 第 {idx} 行值 '{value}' 不在允许集合 {sorted(allowed)}"
            )


def _check_unique(df: pd.DataFrame, cols: list[str], table: str) -> None:
    dup_mask = df.duplicated(subset=cols, keep=False)
    if dup_mask.any():
        bad_rows = df.index[dup_mask].tolist()
        raise SchemaError(f"{table}: 列 {cols} 出现重复，行 {bad_rows}")


# ---------------------------------------------------------------------------
# prices
# ---------------------------------------------------------------------------

def validate_prices(df: pd.DataFrame, *, normalize: bool = True) -> pd.DataFrame:
    """校验行情表 schema，返回校验通过的副本（不修改入参）。

    normalize=True：当缺少 effective_date 时补齐为 trade_date（契约 §3.3：一般 = trade_date）。
    normalize=False：严格模式，effective_date 必须由上游显式提供。
    """
    table = "prices"
    _require_non_empty(df, table)
    _require_columns(df, PRICE_REQUIRED_COLUMNS, table)

    out = df.copy()
    if "effective_date" not in out.columns:
        if not normalize:
            raise SchemaError(
                f"{table}: 缺少 effective_date 列（normalize=False 时必须由上游显式提供）"
            )
        out["effective_date"] = out["trade_date"]

    # 日期列
    _check_pure_date_column(out, "trade_date", table, allow_null=False)
    _check_pure_date_column(out, "effective_date", table, allow_null=False)

    # symbol
    _check_str_column(out, "symbol", table)

    # 数值列
    for col in ("open", "high", "low", "close", "limit_up", "limit_down", "adj_factor"):
        _check_numeric_column(out, col, table, min_value=0.0, strict_min=True)
    for col in ("volume", "amount"):
        _check_numeric_column(out, col, table, min_value=0.0, strict_min=False)

    # OHLC 一致性
    high = pd.to_numeric(out["high"])
    low = pd.to_numeric(out["low"])
    open_ = pd.to_numeric(out["open"])
    close = pd.to_numeric(out["close"])
    bad_hl = out.index[high < low - _EPS].tolist()
    if bad_hl:
        raise SchemaError(f"{table}: 行 {bad_hl} 出现 high < low")
    bad_ho = out.index[(high < open_ - _EPS) | (high < close - _EPS)].tolist()
    if bad_ho:
        raise SchemaError(f"{table}: 行 {bad_ho} 出现 high < open/close")
    bad_lo = out.index[(low > open_ + _EPS) | (low > close + _EPS)].tolist()
    if bad_lo:
        raise SchemaError(f"{table}: 行 {bad_lo} 出现 low > open/close")

    # is_suspended
    _check_bool_column(out, "is_suspended", table)

    # 唯一性
    _check_unique(out, ["symbol", "trade_date"], table)

    # effective_date >= trade_date（行情在交易日当天或之后才可用，不能早于交易日）
    eff_before = out.index[
        out["effective_date"].astype("object") < out["trade_date"].astype("object")
    ].tolist()
    if eff_before:
        raise SchemaError(
            f"{table}: 行 {eff_before} 的 effective_date 早于 trade_date（违反点时点口径）"
        )

    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# master
# ---------------------------------------------------------------------------

def validate_master(df: pd.DataFrame) -> pd.DataFrame:
    """校验 ETF 主数据 schema，返回校验通过的副本。"""
    table = "master"
    _require_non_empty(df, table)
    _require_columns(df, MASTER_REQUIRED_COLUMNS, table)

    out = df.copy()

    _check_str_column(out, "symbol", table)
    _check_str_column(out, "name", table, non_empty=False)
    _check_str_column(out, "etf_type", table, allowed=VALID_ETF_TYPES)
    _check_str_column(out, "settlement", table, allowed=VALID_SETTLEMENTS)
    _check_str_column(out, "exchange", table, allowed=VALID_EXCHANGES)
    _check_bool_column(out, "stamp_tax_applicable", table)
    _check_pure_date_column(out, "list_date", table, allow_null=False)
    _check_pure_date_column(out, "delist_date", table, allow_null=True)
    _check_unique(out, ["symbol"], table)

    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# calendar
# ---------------------------------------------------------------------------

def validate_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """校验交易日历 schema，返回校验通过的副本。"""
    table = "calendar"
    _require_non_empty(df, table)
    _require_columns(df, CALENDAR_REQUIRED_COLUMNS, table)

    out = df.copy()

    _check_pure_date_column(out, "trade_date", table, allow_null=False)
    _check_pure_date_column(out, "prev_trade_date", table, allow_null=True)
    _check_pure_date_column(out, "next_trade_date", table, allow_null=True)
    _check_bool_column(out, "is_open", table)
    _check_unique(out, ["trade_date"], table)

    return out.reset_index(drop=True)
