"""AKShare raw 拉取与本地缓存入口。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .akshare_adapter import REQUIRED_RAW_FIELDS, write_raw_etf_daily_csv

RAW_MANIFEST_NAME = "raw_manifest.json"
RAW_CACHE_TIMEZONE = ZoneInfo("Asia/Shanghai")
FetchFn = Callable[[str, date], pd.DataFrame]


@dataclass(frozen=True)
class RawCacheResult:
    """一次 AKShare raw 缓存写入结果。"""

    raw_dir: Path
    manifest_path: Path
    output_files: list[str]
    file_hashes: dict[str, str]


def fetch_akshare_raw_cache(
    *,
    symbols: list[str],
    asof_date: date,
    raw_root: str | Path,
    vendor: str = "akshare",
    overwrite: bool = False,
    fetch_fn: FetchFn | None = None,
    source: str = "akshare.fund_etf_hist_em",
    created_at: str | None = None,
) -> RawCacheResult:
    """Fetch AKShare-shaped ETF daily raw data and cache it under raw_root.

    Tests should pass a deterministic `fetch_fn`; the default fetcher is only for real
    CLI usage and performs an AKShare network/vendor call.
    """
    clean_symbols = _normalize_symbols(symbols)
    root = Path(raw_root)
    raw_dir = root / vendor / asof_date.strftime("%Y%m%d")
    manifest_path = raw_dir / RAW_MANIFEST_NAME
    if manifest_path.exists() and not overwrite:
        msg = f"raw manifest already exists and must not be overwritten: {manifest_path}"
        raise FileExistsError(msg)
    existing_raw = [
        raw_dir / f"{symbol}.csv"
        for symbol in clean_symbols
        if (raw_dir / f"{symbol}.csv").exists()
    ]
    if existing_raw and not overwrite:
        paths = [path.as_posix() for path in existing_raw]
        raise FileExistsError(f"raw files already exist and must not be overwritten: {paths}")
    if overwrite and manifest_path.exists():
        manifest_path.unlink()

    fetch = fetch_fn or fetch_akshare_etf_daily
    output_files: list[str] = []
    file_hashes: dict[str, str] = {}

    for symbol in clean_symbols:
        raw = _fetch_symbol(fetch, symbol=symbol, asof_date=asof_date, source=source)
        missing = sorted(set(REQUIRED_RAW_FIELDS) - set(raw.columns))
        if missing:
            raise ValueError(f"AKShare raw for {symbol} missing required fields: {missing}")

        raw_path = raw_dir / f"{symbol}.csv"
        if overwrite and raw_path.exists():
            raw_path.unlink()
        written = write_raw_etf_daily_csv(
            raw,
            raw_root=root,
            symbol=symbol,
            asof_date=asof_date,
            vendor=vendor,
        )
        relative = written.path.relative_to(root).as_posix()
        output_files.append(relative)
        file_hashes[relative] = written.sha256

    manifest = {
        "vendor": vendor,
        "asof_date": asof_date.isoformat(),
        "symbols": clean_symbols,
        "input": {"source": source},
        "source": source,
        "output_files": output_files,
        "file_hashes": dict(sorted(file_hashes.items())),
        "created_at": created_at or _deterministic_created_at(asof_date),
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(_json_dumps(manifest), encoding="utf-8")
    manifest_hash_key = manifest_path.relative_to(root).as_posix()
    file_hashes[manifest_hash_key] = _sha256_file(manifest_path)

    return RawCacheResult(
        raw_dir=raw_dir,
        manifest_path=manifest_path,
        output_files=output_files,
        file_hashes=dict(sorted(file_hashes.items())),
    )


def fetch_akshare_etf_daily(symbol: str, asof_date: date) -> pd.DataFrame:
    """Fetch one ETF daily raw table from AKShare.

    The returned table must satisfy the raw field contract before it is cached.
    """
    if importlib.util.find_spec("akshare") is None:
        raise RuntimeError("akshare package is not installed; cannot fetch AKShare raw data")
    import akshare as ak

    compact_symbol = symbol.split(".", maxsplit=1)[0]
    end_date = asof_date.strftime("%Y%m%d")
    try:
        return ak.fund_etf_hist_em(
            symbol=compact_symbol,
            period="daily",
            start_date="19900101",
            end_date=end_date,
            adjust="",
        )
    except Exception as exc:
        msg = f"AKShare fetch failed for symbol={symbol}, asof_date={asof_date.isoformat()}"
        raise RuntimeError(msg) from exc


def _fetch_symbol(fetch: FetchFn, *, symbol: str, asof_date: date, source: str) -> pd.DataFrame:
    try:
        raw = fetch(symbol, asof_date)
    except Exception as exc:
        msg = (
            f"raw fetch failed for source={source}, symbol={symbol}, "
            f"asof_date={asof_date.isoformat()}: {exc}"
        )
        raise RuntimeError(msg) from exc
    if not isinstance(raw, pd.DataFrame):
        raise TypeError(f"raw fetch for {symbol} must return pandas.DataFrame")
    return raw


def _normalize_symbols(symbols: list[str]) -> list[str]:
    cleaned = [symbol.strip() for symbol in symbols if symbol and symbol.strip()]
    if not cleaned:
        raise ValueError("symbols must not be empty")
    duplicate = sorted({symbol for symbol in cleaned if cleaned.count(symbol) > 1})
    if duplicate:
        raise ValueError(f"symbols must be unique, duplicated: {duplicate}")
    return cleaned


def _deterministic_created_at(asof_date: date) -> str:
    return datetime.combine(asof_date, time.min, tzinfo=RAW_CACHE_TIMEZONE).isoformat()


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
