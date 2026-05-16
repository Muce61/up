# ruff: noqa: E402, RUF002, RUF043
"""回归测试：reference layer CSV 加载、schema 校验与 PIT 可见性。"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.reference import (
    load_etf_master,
    load_trading_calendar,
    validate_etf_master,
    validate_trading_calendar,
)

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "reference"
CALENDAR_CSV = FIXTURE_ROOT / "trading_calendar.csv"
MASTER_CSV = FIXTURE_ROOT / "etf_master.csv"


def test_load_trading_calendar_applies_pit_boundaries() -> None:
    calendar = load_trading_calendar(CALENDAR_CSV, asof_date=date(2026, 5, 12))

    assert calendar["trade_date"].tolist() == [
        date(2026, 5, 10),
        date(2026, 5, 11),
        date(2026, 5, 12),
    ]
    assert (calendar["effective_date"] <= date(2026, 5, 12)).all()
    assert calendar["is_open"].tolist() == [True, True, True]


def test_load_etf_master_applies_pit_universe_rules() -> None:
    master = load_etf_master(MASTER_CSV, asof_date=date(2026, 5, 12))

    assert "510300.SH" in set(master["symbol"])
    assert "159999.SZ" not in set(master["symbol"])
    assert "518880.SH" not in set(master["symbol"])

    delisted = master[master["symbol"] == "510999.SH"].iloc[0]
    assert delisted["delist_date"] == date(2026, 5, 10)
    assert bool(delisted["can_open_new_position"]) is False


def test_validate_trading_calendar_rejects_missing_required_field() -> None:
    broken = pd.read_csv(CALENDAR_CSV).drop(columns=["effective_date"])

    with pytest.raises(ValueError, match="trading_calendar missing required columns"):
        validate_trading_calendar(broken)


def test_validate_etf_master_rejects_missing_required_field() -> None:
    broken = pd.read_csv(MASTER_CSV).drop(columns=["settlement"])

    with pytest.raises(ValueError, match="etf_master missing required columns"):
        validate_etf_master(broken)


def test_validate_trading_calendar_rejects_invalid_prev_next_chain() -> None:
    calendar = load_trading_calendar(CALENDAR_CSV, asof_date=date(2026, 5, 12))
    broken = calendar.copy()
    broken.loc[1, "prev_trade_date"] = broken.loc[1, "trade_date"]

    with pytest.raises(ValueError, match="prev_trade_date must be < trade_date"):
        validate_trading_calendar(broken)

    broken = calendar.copy()
    broken.loc[1, "next_trade_date"] = broken.loc[1, "trade_date"]

    with pytest.raises(ValueError, match="next_trade_date must be > trade_date"):
        validate_trading_calendar(broken)


def test_validate_etf_master_rejects_future_effective_date_when_strict_asof() -> None:
    master = load_etf_master(MASTER_CSV, asof_date=date(2026, 5, 20))

    with pytest.raises(ValueError, match="etf_master.effective_date must be <= asof_date"):
        validate_etf_master(master, asof_date=date(2026, 5, 12))


def test_validate_etf_master_rejects_invalid_settlement() -> None:
    master = load_etf_master(MASTER_CSV, asof_date=date(2026, 5, 12))
    broken = master.copy()
    broken.loc[0, "settlement"] = "T+2"

    with pytest.raises(ValueError, match="etf_master.settlement"):
        validate_etf_master(broken)


def test_validate_etf_master_rejects_invalid_etf_type() -> None:
    master = load_etf_master(MASTER_CSV, asof_date=date(2026, 5, 12))
    broken = master.copy()
    broken.loc[0, "etf_type"] = "phase2_stock_factor"

    with pytest.raises(ValueError, match="etf_master.etf_type"):
        validate_etf_master(broken)
