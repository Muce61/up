from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.akshare_adapter import normalize_etf_daily


REQUIRED_COLUMNS = {
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
}


def _raw_akshare_etf_daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-05-11", "2026-05-12"],
            "开盘": [1.001, 1.012],
            "最高": [1.018, 1.025],
            "最低": [0.998, 1.010],
            "收盘": [1.015, 1.020],
            "成交量": [100_000, 120_000],
            "成交额": [101_500.0, 122_400.0],
            "涨停": [1.102, 1.117],
            "跌停": [0.902, 0.914],
            "停牌": [False, False],
            "复权因子": [1.0, 1.0],
        }
    )


def test_normalize_etf_daily_outputs_project_price_schema() -> None:
    normalized = normalize_etf_daily(
        _raw_akshare_etf_daily(),
        symbol="510300.SH",
        asof_date=date(2026, 5, 12),
    )

    assert REQUIRED_COLUMNS.issubset(normalized.columns)
    assert normalized["symbol"].tolist() == ["510300.SH", "510300.SH"]
    assert normalized["trade_date"].tolist() == [date(2026, 5, 11), date(2026, 5, 12)]
    assert normalized["effective_date"].tolist() == [
        date(2026, 5, 11),
        date(2026, 5, 12),
    ]
    assert normalized["is_suspended"].tolist() == [False, False]


def test_normalize_etf_daily_enforces_basic_field_legality() -> None:
    normalized = normalize_etf_daily(
        _raw_akshare_etf_daily(),
        symbol="510300.SH",
        asof_date=date(2026, 5, 12),
    )

    assert (normalized[["open", "high", "low", "close"]] > 0).all().all()
    assert (normalized["high"] >= normalized[["open", "close", "low"]].max(axis=1)).all()
    assert (normalized["low"] <= normalized[["open", "close", "high"]].min(axis=1)).all()
    assert (normalized["adj_factor"] > 0).all()
    assert (normalized["volume"] >= 0).all()
    assert (normalized["amount"] > 0).all()


def test_normalize_etf_daily_rejects_missing_required_raw_field() -> None:
    raw = _raw_akshare_etf_daily().drop(columns=["成交额"])

    with pytest.raises(ValueError, match="missing required AKShare fields"):
        normalize_etf_daily(raw, symbol="510300.SH", asof_date=date(2026, 5, 12))


def test_normalize_etf_daily_rejects_invalid_prices_and_amount() -> None:
    raw = _raw_akshare_etf_daily()
    raw.loc[0, "收盘"] = 0

    with pytest.raises(ValueError, match="price fields must be positive"):
        normalize_etf_daily(raw, symbol="510300.SH", asof_date=date(2026, 5, 12))

    raw = _raw_akshare_etf_daily()
    raw.loc[0, "成交额"] = 0

    with pytest.raises(ValueError, match="amount must be positive"):
        normalize_etf_daily(raw, symbol="510300.SH", asof_date=date(2026, 5, 12))


def test_normalize_etf_daily_enforces_pit_asof_boundary() -> None:
    raw = _raw_akshare_etf_daily()

    with pytest.raises(ValueError, match="effective_date must be <= asof_date"):
        normalize_etf_daily(raw, symbol="510300.SH", asof_date=date(2026, 5, 11))
