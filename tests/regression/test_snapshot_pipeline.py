from __future__ import annotations

from datetime import date
from pathlib import Path
import json
import hashlib
import sys

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.akshare_adapter import PRICE_COLUMNS
from src.data.snapshot import build_price_snapshot


def _raw_akshare_etf_daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-05-11", "2026-05-12", "2026-05-13"],
            "开盘": [1.001, 1.012, 1.021],
            "最高": [1.018, 1.025, 1.030],
            "最低": [0.998, 1.010, 1.018],
            "收盘": [1.015, 1.020, 1.027],
            "成交量": [100000, 120000, 130000],
            "成交额": [101500.0, 122400.0, 133510.0],
            "涨停": [1.102, 1.117, 1.122],
            "跌停": [0.902, 0.914, 0.921],
            "停牌": [False, False, False],
            "复权因子": [1.0, 1.0, 1.0],
        }
    )


def _write_raw_csv(raw_root: Path) -> Path:
    raw_dir = raw_root / "20260512"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "510300.SH.csv"
    _raw_akshare_etf_daily().to_csv(raw_path, index=False)
    return raw_path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_manifest_exists(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    snapshot_root = tmp_path / "data" / "snapshots"
    _write_raw_csv(raw_root)

    result = build_price_snapshot(raw_root=raw_root, snapshot_root=snapshot_root, asof_date=date(2026, 5, 12))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.manifest_path.exists()
    assert manifest["snapshot_version"] == result.snapshot_version
    assert manifest["source_raw_dates"] == ["20260512"]
    assert manifest["input_files"] == ["20260512/510300.SH.csv"]
    assert manifest["row_counts"] == {"prices_daily": 2}
    assert manifest["min_date"] == "2026-05-11"
    assert manifest["max_date"] == "2026-05-12"
    assert "raw/20260512/510300.SH.csv" in manifest["file_hashes"]
    assert "snapshot/prices_daily.csv" in manifest["file_hashes"]


def test_snapshot_generation_is_reproducible(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    _write_raw_csv(raw_root)

    first = build_price_snapshot(raw_root=raw_root, snapshot_root=tmp_path / "snapshots_a", asof_date=date(2026, 5, 12))
    second = build_price_snapshot(raw_root=raw_root, snapshot_root=tmp_path / "snapshots_b", asof_date=date(2026, 5, 12))

    assert first.snapshot_version == second.snapshot_version
    assert _sha256_file(first.prices_path) == _sha256_file(second.prices_path)
    assert _sha256_file(first.manifest_path) == _sha256_file(second.manifest_path)


def test_snapshot_truncates_rows_after_asof_date(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    _write_raw_csv(raw_root)

    result = build_price_snapshot(raw_root=raw_root, snapshot_root=tmp_path / "data" / "snapshots", asof_date=date(2026, 5, 12))
    prices = pd.read_csv(result.prices_path)

    assert prices["trade_date"].tolist() == ["2026-05-11", "2026-05-12"]
    assert "2026-05-13" not in set(prices["trade_date"])


def test_snapshot_rejects_missing_required_raw_field(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    raw_path = _write_raw_csv(raw_root)
    broken = pd.read_csv(raw_path).drop(columns=["成交额"])
    broken.to_csv(raw_path, index=False)

    with pytest.raises(ValueError, match="missing required AKShare fields"):
        build_price_snapshot(raw_root=raw_root, snapshot_root=tmp_path / "data" / "snapshots", asof_date=date(2026, 5, 12))


def test_snapshot_output_columns_match_data_contract(tmp_path: Path) -> None:
    raw_root = tmp_path / "data" / "raw"
    _write_raw_csv(raw_root)

    result = build_price_snapshot(raw_root=raw_root, snapshot_root=tmp_path / "data" / "snapshots", asof_date=date(2026, 5, 12))
    prices = pd.read_csv(result.prices_path)

    assert prices.columns.tolist() == PRICE_COLUMNS
