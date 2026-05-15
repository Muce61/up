"""单元测试：etf_loader 对接 snapshot 流水线的两处改动。

1. load_prices 能从 snapshot 目录读取 `prices_daily.csv`（data_contract 规范名）。
2. derive_calendar_from_prices 从行情自身派生交易日历（stopgap，详见函数 docstring）。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from data import etf_loader
from data import schema


def _valid_prices_daily() -> pd.DataFrame:
    """一份符合 akshare_adapter.PRICE_COLUMNS 的最小合法行情。"""
    rows = []
    base_dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    for symbol in ("510300.SH", "510500.SH"):
        for i, d in enumerate(base_dates):
            close = 1.0 + 0.01 * i
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": d,
                    "effective_date": d,
                    "open": close,
                    "high": close + 0.02,
                    "low": close - 0.02,
                    "close": close,
                    "adj_factor": 1.0,
                    "volume": 100000,
                    "amount": 100000.0,
                    "limit_up": close * 1.1,
                    "limit_down": close * 0.9,
                    "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.unit
def test_load_prices_reads_prices_daily_csv(tmp_path: Path) -> None:
    snap_dir = tmp_path / "20240104-abc12345"
    snap_dir.mkdir(parents=True)
    _valid_prices_daily().to_csv(snap_dir / "prices_daily.csv", index=False)

    out = etf_loader.load_prices(snap_dir)

    assert len(out) == 6
    assert set(out["symbol"]) == {"510300.SH", "510500.SH"}
    assert out["trade_date"].iloc[0] == date(2024, 1, 2)
    # 仍能通过契约校验
    schema.validate_prices(out)


@pytest.mark.unit
def test_load_prices_still_reads_legacy_prices_csv(tmp_path: Path) -> None:
    """不破坏旧路径：prices.csv 仍可被识别。"""
    snap_dir = tmp_path / "legacy"
    snap_dir.mkdir(parents=True)
    _valid_prices_daily().to_csv(snap_dir / "prices.csv", index=False)

    out = etf_loader.load_prices(snap_dir)
    assert len(out) == 6


@pytest.mark.unit
def test_derive_calendar_basic_shape() -> None:
    prices = _valid_prices_daily()
    cal = etf_loader.derive_calendar_from_prices(prices)

    assert list(cal.columns) == etf_loader.CALENDAR_COLUMNS
    # 3 个唯一交易日（两个 symbol 共享同一日期网格）
    assert list(cal["trade_date"]) == [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    assert cal["is_open"].all()
    # prev / next 链
    assert cal["prev_trade_date"].iloc[0] is None
    assert cal["prev_trade_date"].iloc[1] == date(2024, 1, 2)
    assert cal["next_trade_date"].iloc[1] == date(2024, 1, 4)
    assert cal["next_trade_date"].iloc[-1] is None


@pytest.mark.unit
def test_derive_calendar_passes_schema_validation() -> None:
    prices = _valid_prices_daily()
    cal = etf_loader.derive_calendar_from_prices(prices)
    # 必须能通过 data_contract 的 calendar 契约校验
    schema.validate_calendar(cal)


@pytest.mark.unit
def test_derive_calendar_deduplicates_across_symbols() -> None:
    """不同 symbol 的相同 trade_date 只产生一行日历。"""
    prices = _valid_prices_daily()
    cal = etf_loader.derive_calendar_from_prices(prices)
    assert len(cal) == 3
    assert cal["trade_date"].is_unique


@pytest.mark.unit
def test_derive_calendar_rejects_empty() -> None:
    with pytest.raises((ValueError, schema.SchemaError)):
        etf_loader.derive_calendar_from_prices(pd.DataFrame(columns=["symbol", "trade_date"]))
