"""回归测试：reference layer 最小数据契约与 PIT 过滤。"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sys

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.reference import (
    filter_visible_etf_master,
    filter_visible_trading_calendar,
    validate_etf_master,
    validate_trading_calendar,
)


def _trading_calendar() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": [date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13)],
            "is_open": [True, True, True],
            "prev_trade_date": [None, date(2026, 5, 11), date(2026, 5, 12)],
            "next_trade_date": [date(2026, 5, 12), date(2026, 5, 13), None],
            "market": ["SH", "SH", "SH"],
            "effective_date": [date(2026, 5, 10), date(2026, 5, 11), date(2026, 5, 13)],
        }
    )


def _etf_master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "510300.SH",
                "name": "沪深300ETF",
                "etf_type": "broad_index",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2012, 5, 28),
                "delist_date": None,
                "exchange": "SH",
                "effective_date": date(2026, 5, 1),
            },
            {
                "symbol": "159999.SZ",
                "name": "未来上市ETF",
                "etf_type": "sector",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2026, 6, 1),
                "delist_date": None,
                "exchange": "SZ",
                "effective_date": date(2026, 5, 1),
            },
            {
                "symbol": "510999.SH",
                "name": "已退市ETF",
                "etf_type": "broad_index",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2015, 1, 5),
                "delist_date": date(2026, 5, 10),
                "exchange": "SH",
                "effective_date": date(2026, 5, 1),
            },
            {
                "symbol": "518880.SH",
                "name": "黄金ETF未来修订",
                "etf_type": "gold",
                "settlement": "T+0",
                "stamp_tax_applicable": False,
                "list_date": date(2013, 7, 29),
                "delist_date": None,
                "exchange": "SH",
                "effective_date": date(2026, 5, 20),
            },
        ]
    )


@pytest.mark.regression
def test_validate_trading_calendar_rejects_missing_required_field() -> None:
    broken = _trading_calendar().drop(columns=["effective_date"])

    with pytest.raises(ValueError, match="trading_calendar missing required columns"):
        validate_trading_calendar(broken)


@pytest.mark.regression
def test_validate_etf_master_rejects_missing_required_field() -> None:
    broken = _etf_master().drop(columns=["settlement"])

    with pytest.raises(ValueError, match="etf_master missing required columns"):
        validate_etf_master(broken)


@pytest.mark.regression
def test_validate_reference_rejects_future_effective_date() -> None:
    with pytest.raises(ValueError, match="trading_calendar.effective_date must be <= asof_date"):
        validate_trading_calendar(_trading_calendar(), asof_date=date(2026, 5, 12))

    with pytest.raises(ValueError, match="etf_master.effective_date must be <= asof_date"):
        validate_etf_master(_etf_master(), asof_date=date(2026, 5, 12))


@pytest.mark.regression
def test_filter_visible_etf_master_excludes_not_yet_listed_etf() -> None:
    visible = filter_visible_etf_master(_etf_master(), asof_date=date(2026, 5, 12))

    assert "510300.SH" in set(visible["symbol"])
    assert "159999.SZ" not in set(visible["symbol"])


@pytest.mark.regression
def test_filter_visible_etf_master_keeps_delisted_history_but_blocks_new_position() -> None:
    visible = filter_visible_etf_master(_etf_master(), asof_date=date(2026, 5, 12))
    delisted = visible[visible["symbol"] == "510999.SH"].iloc[0]

    assert delisted["delist_date"] == date(2026, 5, 10)
    assert delisted["can_open_new_position"] is False


@pytest.mark.regression
def test_filter_visible_etf_master_excludes_future_effective_reference_row() -> None:
    visible = filter_visible_etf_master(_etf_master(), asof_date=date(2026, 5, 12))

    assert "518880.SH" not in set(visible["symbol"])


@pytest.mark.regression
def test_filter_visible_trading_calendar_applies_trade_and_effective_date_boundaries() -> None:
    visible = filter_visible_trading_calendar(_trading_calendar(), asof_date=date(2026, 5, 12))

    assert visible["trade_date"].tolist() == [date(2026, 5, 11), date(2026, 5, 12)]
    assert (visible["effective_date"] <= date(2026, 5, 12)).all()


@pytest.mark.regression
def test_reference_contract_rejects_string_or_datetime_dates() -> None:
    broken = _etf_master()
    broken.loc[0, "list_date"] = "2012-05-28"

    with pytest.raises(ValueError, match="etf_master.list_date"):
        validate_etf_master(broken)

    broken = _trading_calendar()
    broken.loc[0, "trade_date"] = datetime(2026, 5, 11, 0, 0)

    with pytest.raises(ValueError, match="trading_calendar.trade_date"):
        validate_trading_calendar(broken)


@pytest.mark.regression
def test_reference_contract_rejects_invalid_enums() -> None:
    broken = _etf_master()
    broken.loc[0, "settlement"] = "T+2"

    with pytest.raises(ValueError, match="etf_master.settlement"):
        validate_etf_master(broken)

    broken = _etf_master()
    broken.loc[0, "etf_type"] = "phase2_stock_factor"

    with pytest.raises(ValueError, match="etf_master.etf_type"):
        validate_etf_master(broken)
