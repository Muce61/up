# ruff: noqa: E402
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.akshare_fetcher import fetch_akshare_raw_cache

FIXTURE_RAW = REPO_ROOT / "tests" / "fixtures" / "akshare" / "510300.SH.raw.csv"


def _fixture_fetch(_symbol: str, _asof_date: date) -> pd.DataFrame:
    return pd.read_csv(FIXTURE_RAW)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_akshare_raw_cache_manifest_fields_complete(tmp_path: Path) -> None:
    result = fetch_akshare_raw_cache(
        symbols=["510300.SH"],
        asof_date=date(2026, 5, 12),
        raw_root=tmp_path / "data" / "raw",
        fetch_fn=_fixture_fetch,
        source="fixture:tests/fixtures/akshare/510300.SH.raw.csv",
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.manifest_path.name == "raw_manifest.json"
    assert manifest["vendor"] == "akshare"
    assert manifest["asof_date"] == "2026-05-12"
    assert manifest["symbols"] == ["510300.SH"]
    assert manifest["input"] == {"source": "fixture:tests/fixtures/akshare/510300.SH.raw.csv"}
    assert manifest["source"] == "fixture:tests/fixtures/akshare/510300.SH.raw.csv"
    assert manifest["output_files"] == ["akshare/20260512/510300.SH.csv"]
    assert "akshare/20260512/510300.SH.csv" in manifest["file_hashes"]
    assert manifest["created_at"] == "2026-05-12T00:00:00+08:00"


def test_akshare_raw_cache_hash_is_reproducible_for_same_fixture(tmp_path: Path) -> None:
    first = fetch_akshare_raw_cache(
        symbols=["510300.SH"],
        asof_date=date(2026, 5, 12),
        raw_root=tmp_path / "run_a" / "raw",
        fetch_fn=_fixture_fetch,
        source="fixture",
    )
    second = fetch_akshare_raw_cache(
        symbols=["510300.SH"],
        asof_date=date(2026, 5, 12),
        raw_root=tmp_path / "run_b" / "raw",
        fetch_fn=_fixture_fetch,
        source="fixture",
    )

    first_raw = first.raw_dir / "510300.SH.csv"
    second_raw = second.raw_dir / "510300.SH.csv"
    assert _sha256_file(first_raw) == _sha256_file(second_raw)

    first_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
    assert first_manifest == second_manifest


def test_akshare_raw_cache_rejects_missing_required_field(tmp_path: Path) -> None:
    def broken_fetch(_symbol: str, _asof_date: date) -> pd.DataFrame:
        return pd.read_csv(FIXTURE_RAW).drop(columns=["成交额"])

    with pytest.raises(ValueError, match="missing required fields"):
        fetch_akshare_raw_cache(
            symbols=["510300.SH"],
            asof_date=date(2026, 5, 12),
            raw_root=tmp_path / "raw",
            fetch_fn=broken_fetch,
            source="broken-fixture",
        )


def test_akshare_raw_cache_does_not_overwrite_by_default(tmp_path: Path) -> None:
    kwargs = {
        "symbols": ["510300.SH"],
        "asof_date": date(2026, 5, 12),
        "raw_root": tmp_path / "raw",
        "fetch_fn": _fixture_fetch,
        "source": "fixture",
    }
    fetch_akshare_raw_cache(**kwargs)

    with pytest.raises(FileExistsError, match="raw manifest already exists"):
        fetch_akshare_raw_cache(**kwargs)


def test_akshare_raw_cache_overwrite_requires_explicit_flag(tmp_path: Path) -> None:
    kwargs = {
        "symbols": ["510300.SH"],
        "asof_date": date(2026, 5, 12),
        "raw_root": tmp_path / "raw",
        "fetch_fn": _fixture_fetch,
        "source": "fixture",
    }
    first = fetch_akshare_raw_cache(**kwargs)
    second = fetch_akshare_raw_cache(**kwargs, overwrite=True)

    assert _sha256_file(first.raw_dir / "510300.SH.csv") == _sha256_file(
        second.raw_dir / "510300.SH.csv"
    )


def test_akshare_raw_cache_rejects_existing_raw_without_manifest(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    existing_dir = raw_root / "akshare" / "20260512"
    existing_dir.mkdir(parents=True)
    (existing_dir / "510300.SH.csv").write_text("already exists\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="raw files already exist"):
        fetch_akshare_raw_cache(
            symbols=["510300.SH"],
            asof_date=date(2026, 5, 12),
            raw_root=raw_root,
            fetch_fn=_fixture_fetch,
            source="fixture",
        )


def test_akshare_raw_cache_wraps_fetch_failure_with_context(tmp_path: Path) -> None:
    def failing_fetch(_symbol: str, _asof_date: date) -> pd.DataFrame:
        raise TimeoutError("network timeout")

    with pytest.raises(RuntimeError, match=r"raw fetch failed.*510300.SH.*2026-05-12"):
        fetch_akshare_raw_cache(
            symbols=["510300.SH"],
            asof_date=date(2026, 5, 12),
            raw_root=tmp_path / "raw",
            fetch_fn=failing_fetch,
            source="mock-akshare",
        )
