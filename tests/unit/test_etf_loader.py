"""单元测试：etf_loader。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from data import etf_loader

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_load_etf_master_required_columns() -> None:
    path = REPO_ROOT / "config" / "universe" / "etf_pool.yaml"
    df = etf_loader.load_etf_master(path)
    assert set(etf_loader.MASTER_COLUMNS).issubset(df.columns)
    assert len(df) > 0
    assert "510300.SH" in df["symbol"].values


@pytest.mark.unit
def test_filter_pit_drops_future() -> None:
    df = pd.DataFrame(
        {
            "trade_date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "value": [1, 2, 3],
        }
    )
    out = etf_loader.filter_pit(df, asof_date=date(2024, 1, 3))
    assert len(out) == 2
    assert date(2024, 1, 4) not in out["trade_date"].values


@pytest.mark.unit
def test_load_prices_adds_effective_date_when_missing(tmp_path) -> None:
    prices_file = tmp_path / "prices.csv"
    pd.DataFrame(
        {
            "symbol": ["510300.SH"],
            "trade_date": ["2024-01-02"],
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.0],
            "adj_factor": [1.0],
            "volume": [100],
            "amount": [1000.0],
            "limit_up": [1.1],
            "limit_down": [0.9],
            "is_suspended": [False],
        }
    ).to_csv(prices_file, index=False)

    out = etf_loader.load_prices(prices_file)

    assert "effective_date" in out.columns
    assert out["trade_date"].iloc[0] == date(2024, 1, 2)
    assert out["effective_date"].iloc[0] == date(2024, 1, 2)


@pytest.mark.unit
def test_load_prices_preserves_explicit_effective_date(tmp_path) -> None:
    prices_file = tmp_path / "prices.csv"
    pd.DataFrame(
        {
            "symbol": ["510300.SH"],
            "trade_date": ["2024-01-02"],
            "effective_date": ["2024-01-03"],
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.0],
            "adj_factor": [1.0],
            "volume": [100],
            "amount": [1000.0],
            "limit_up": [1.1],
            "limit_down": [0.9],
            "is_suspended": [False],
        }
    ).to_csv(prices_file, index=False)

    out = etf_loader.load_prices(prices_file)

    assert out["effective_date"].iloc[0] == date(2024, 1, 3)
