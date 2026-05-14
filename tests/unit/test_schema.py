"""单元测试：data.schema 数据契约校验。

正例 + 反例，确保 validate_prices / validate_master / validate_calendar
按 docs/data_contract.md 强制结构与口径。
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from data import schema


def _valid_prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "ETFA.SH", "trade_date": date(2024, 1, 2),
                "effective_date": date(2024, 1, 2),
                "open": 100.0, "high": 102.0, "low": 98.0, "close": 101.0,
                "adj_factor": 1.0, "volume": 1_000_000, "amount": 1.0e8,
                "limit_up": 110.0, "limit_down": 90.0, "is_suspended": False,
            },
            {
                "symbol": "ETFA.SH", "trade_date": date(2024, 1, 3),
                "effective_date": date(2024, 1, 3),
                "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0,
                "adj_factor": 1.0, "volume": 1_200_000, "amount": 1.1e8,
                "limit_up": 111.1, "limit_down": 90.9, "is_suspended": False,
            },
        ]
    )


def _valid_master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "ETFA.SH", "name": "A 宽基", "etf_type": "broad_index",
                "settlement": "T+1", "stamp_tax_applicable": False,
                "list_date": date(2018, 1, 2), "delist_date": None, "exchange": "SH",
            },
            {
                "symbol": "ETFB.SH", "name": "B 黄金", "etf_type": "gold",
                "settlement": "T+0", "stamp_tax_applicable": False,
                "list_date": date(2018, 1, 2), "delist_date": date(2023, 6, 30),
                "exchange": "SH",
            },
        ]
    )


def _valid_calendar() -> pd.DataFrame:
    d = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    return pd.DataFrame(
        {
            "trade_date": d,
            "is_open": [True, True, True],
            "prev_trade_date": [None, d[0], d[1]],
            "next_trade_date": [d[1], d[2], None],
        }
    )


# --------------------------- prices: 正例 ---------------------------

@pytest.mark.unit
def test_validate_prices_accepts_valid() -> None:
    out = schema.validate_prices(_valid_prices())
    assert len(out) == 2
    assert "effective_date" in out.columns


@pytest.mark.unit
def test_validate_prices_normalizes_missing_effective_date() -> None:
    df = _valid_prices().drop(columns=["effective_date"])
    out = schema.validate_prices(df, normalize=True)
    assert "effective_date" in out.columns
    assert (out["effective_date"] == out["trade_date"]).all()


@pytest.mark.unit
def test_validate_prices_does_not_mutate_input() -> None:
    df = _valid_prices().drop(columns=["effective_date"])
    schema.validate_prices(df, normalize=True)
    assert "effective_date" not in df.columns  # 原对象不被修改


# --------------------------- prices: 反例 ---------------------------

@pytest.mark.unit
def test_validate_prices_strict_rejects_missing_effective_date() -> None:
    df = _valid_prices().drop(columns=["effective_date"])
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df, normalize=False)


@pytest.mark.unit
def test_validate_prices_rejects_missing_required_column() -> None:
    df = _valid_prices().drop(columns=["adj_factor"])
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_empty() -> None:
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(_valid_prices().iloc[0:0])


@pytest.mark.unit
def test_validate_prices_rejects_timestamp_in_date_column() -> None:
    df = _valid_prices()
    df["trade_date"] = pd.to_datetime(df["trade_date"])  # → pd.Timestamp
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_string_date() -> None:
    df = _valid_prices()
    df["trade_date"] = ["2024-01-02", "2024-01-03"]
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_duplicate_symbol_date() -> None:
    df = pd.concat([_valid_prices().iloc[[0]], _valid_prices().iloc[[0]]], ignore_index=True)
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_nonpositive_adj_factor() -> None:
    df = _valid_prices()
    df.loc[0, "adj_factor"] = 0.0
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_nonpositive_close() -> None:
    df = _valid_prices()
    df.loc[0, "close"] = -1.0
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_effective_date_before_trade_date() -> None:
    df = _valid_prices()
    df.loc[0, "effective_date"] = date(2023, 12, 31)
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_high_below_low() -> None:
    df = _valid_prices()
    df.loc[0, "high"] = 1.0  # 低于 low
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_non_bool_is_suspended() -> None:
    df = _valid_prices()
    df["is_suspended"] = ["no", "yes"]
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


@pytest.mark.unit
def test_validate_prices_rejects_null_trade_date() -> None:
    df = _valid_prices()
    df.loc[0, "trade_date"] = None
    with pytest.raises(schema.SchemaError):
        schema.validate_prices(df)


# --------------------------- master ---------------------------

@pytest.mark.unit
def test_validate_master_accepts_valid() -> None:
    out = schema.validate_master(_valid_master())
    assert len(out) == 2


@pytest.mark.unit
def test_validate_master_allows_null_delist_date() -> None:
    out = schema.validate_master(_valid_master())
    val = out.loc[0, "delist_date"]
    assert val is None or pd.isna(val)


@pytest.mark.unit
def test_validate_master_rejects_unknown_etf_type() -> None:
    df = _valid_master()
    df.loc[0, "etf_type"] = "crypto"
    with pytest.raises(schema.SchemaError):
        schema.validate_master(df)


@pytest.mark.unit
def test_validate_master_rejects_unknown_settlement() -> None:
    df = _valid_master()
    df.loc[0, "settlement"] = "T+2"
    with pytest.raises(schema.SchemaError):
        schema.validate_master(df)


@pytest.mark.unit
def test_validate_master_rejects_duplicate_symbol() -> None:
    df = pd.concat([_valid_master().iloc[[0]], _valid_master().iloc[[0]]], ignore_index=True)
    with pytest.raises(schema.SchemaError):
        schema.validate_master(df)


@pytest.mark.unit
def test_validate_master_rejects_null_list_date() -> None:
    df = _valid_master()
    df.loc[0, "list_date"] = None
    with pytest.raises(schema.SchemaError):
        schema.validate_master(df)


@pytest.mark.unit
def test_validate_master_rejects_missing_column() -> None:
    df = _valid_master().drop(columns=["etf_type"])
    with pytest.raises(schema.SchemaError):
        schema.validate_master(df)


# --------------------------- calendar ---------------------------

@pytest.mark.unit
def test_validate_calendar_accepts_valid() -> None:
    out = schema.validate_calendar(_valid_calendar())
    assert len(out) == 3


@pytest.mark.unit
def test_validate_calendar_rejects_duplicate_trade_date() -> None:
    df = _valid_calendar()
    df.loc[2, "trade_date"] = date(2024, 1, 2)
    with pytest.raises(schema.SchemaError):
        schema.validate_calendar(df)


@pytest.mark.unit
def test_validate_calendar_rejects_missing_column() -> None:
    df = _valid_calendar().drop(columns=["is_open"])
    with pytest.raises(schema.SchemaError):
        schema.validate_calendar(df)


@pytest.mark.unit
def test_validate_calendar_rejects_null_trade_date() -> None:
    df = _valid_calendar()
    df.loc[1, "trade_date"] = None
    with pytest.raises(schema.SchemaError):
        schema.validate_calendar(df)


@pytest.mark.unit
def test_validate_calendar_allows_null_prev_next() -> None:
    # 首行 prev、末行 next 为 None 是合法的
    out = schema.validate_calendar(_valid_calendar())
    assert out.loc[0, "prev_trade_date"] is None or pd.isna(out.loc[0, "prev_trade_date"])
