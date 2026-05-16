# ruff: noqa: E402, RUF002
"""回归测试：snapshot 接入 reference layer 后的 PIT 约束。"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.snapshot import build_price_snapshot

REFERENCE_ROOT = REPO_ROOT / "tests" / "fixtures" / "reference"


def _raw_akshare_etf_daily(close_base: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-05-10", "2026-05-11", "2026-05-12", "2026-05-13"],
            "开盘": [close_base, close_base + 0.01, close_base + 0.02, close_base + 0.03],
            "最高": [close_base + 0.02, close_base + 0.03, close_base + 0.04, close_base + 0.05],
            "最低": [close_base - 0.01, close_base, close_base + 0.01, close_base + 0.02],
            "收盘": [close_base + 0.01, close_base + 0.02, close_base + 0.03, close_base + 0.04],
            "成交量": [100000, 110000, 120000, 130000],
            "成交额": [101000.0, 112200.0, 123600.0, 135200.0],
            "涨停": [close_base + 0.10, close_base + 0.11, close_base + 0.12, close_base + 0.13],
            "跌停": [close_base - 0.10, close_base - 0.09, close_base - 0.08, close_base - 0.07],
            "停牌": [False, False, False, False],
            "复权因子": [1.0, 1.0, 1.0, 1.0],
        }
    )


def _write_raw_csvs(raw_root: Path) -> None:
    raw_dir = raw_root / "20260512"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for symbol, base in {
        "510300.SH": 1.00,
        "510999.SH": 0.80,
        "159999.SZ": 1.20,
        "518880.SH": 2.00,
    }.items():
        _raw_akshare_etf_daily(base).to_csv(raw_dir / f"{symbol}.csv", index=False)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_with_reference(tmp_path: Path):
    raw_root = tmp_path / "raw"
    _write_raw_csvs(raw_root)
    return build_price_snapshot(
        raw_root=raw_root,
        snapshot_root=tmp_path / "snapshots",
        reference_root=REFERENCE_ROOT,
        asof_date=date(2026, 5, 12),
    )


def test_snapshot_reference_manifest_fields_exist(tmp_path: Path) -> None:
    result = _build_with_reference(tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest["asof_date"] == "2026-05-12"
    assert manifest["schema_version"] == "prices_daily.v1"
    assert set(manifest["reference_files"]) == {"trading_calendar", "etf_master"}
    assert set(manifest["reference_hashes"]) == {
        "snapshot/trading_calendar.csv",
        "snapshot/etf_master.csv",
    }
    assert manifest["reference_row_counts"] == {"etf_master": 2, "trading_calendar": 3}
    assert manifest["row_counts"]["etf_master"] == 2
    assert manifest["row_counts"]["trading_calendar"] == 3


def test_snapshot_master_excludes_future_effective_and_not_listed_etfs(tmp_path: Path) -> None:
    result = _build_with_reference(tmp_path)
    master = pd.read_csv(result.etf_master_path)

    assert set(master["symbol"]) == {"510300.SH", "510999.SH"}
    assert "159999.SZ" not in set(master["symbol"])
    assert "518880.SH" not in set(master["symbol"])


def test_snapshot_preserves_delisted_history_but_blocks_new_position(tmp_path: Path) -> None:
    result = _build_with_reference(tmp_path)
    prices = pd.read_csv(result.prices_path)
    master = pd.read_csv(result.etf_master_path)

    assert "510999.SH" in set(prices["symbol"])
    delisted = master[master["symbol"] == "510999.SH"].iloc[0]
    assert delisted["delist_date"] == "2026-05-10"
    assert bool(delisted["can_open_new_position"]) is False


def test_snapshot_prices_follow_visible_reference_universe(tmp_path: Path) -> None:
    result = _build_with_reference(tmp_path)
    prices = pd.read_csv(result.prices_path)

    assert set(prices["symbol"]) == {"510300.SH", "510999.SH"}
    assert "159999.SZ" not in set(prices["symbol"])
    assert "518880.SH" not in set(prices["symbol"])
    assert "2026-05-13" not in set(prices["trade_date"])


def test_snapshot_trading_calendar_is_truncated_to_asof(tmp_path: Path) -> None:
    result = _build_with_reference(tmp_path)
    calendar = pd.read_csv(result.trading_calendar_path)

    assert calendar["trade_date"].tolist() == ["2026-05-10", "2026-05-11", "2026-05-12"]
    assert "2026-05-13" not in set(calendar["trade_date"])


def test_snapshot_reference_generation_is_reproducible(tmp_path: Path) -> None:
    first = _build_with_reference(tmp_path / "run_a")
    second = _build_with_reference(tmp_path / "run_b")

    assert first.snapshot_version == second.snapshot_version
    assert _sha256_file(first.prices_path) == _sha256_file(second.prices_path)
    assert _sha256_file(first.etf_master_path) == _sha256_file(second.etf_master_path)
    assert _sha256_file(first.trading_calendar_path) == _sha256_file(second.trading_calendar_path)
    assert _sha256_file(first.manifest_path) == _sha256_file(second.manifest_path)


def test_snapshot_accepts_reference_dataframes(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    _write_raw_csvs(raw_root)
    calendar = pd.read_csv(REFERENCE_ROOT / "trading_calendar.csv")
    master = pd.read_csv(REFERENCE_ROOT / "etf_master.csv")

    result = build_price_snapshot(
        raw_root=raw_root,
        snapshot_root=tmp_path / "snapshots",
        trading_calendar=calendar,
        etf_master=master,
        asof_date=date(2026, 5, 12),
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest["reference_files"] == {
        "etf_master": "<dataframe>",
        "trading_calendar": "<dataframe>",
    }
    assert result.etf_master_path is not None
    assert result.trading_calendar_path is not None
