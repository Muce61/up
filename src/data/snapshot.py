"""点时点快照生成器（data/raw → data/snapshots/{snapshot_version}/）。

P1-W4-03 只负责把已落地的 raw 层行情文件转换为可复现、可追踪、
可校验的 snapshot；不拉取网络数据、不计算策略信号、不修改策略参数。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .akshare_adapter import PRICE_COLUMNS, normalize_etf_daily

SUPPORTED_RAW_SUFFIXES = {".csv"}
DEFAULT_SCHEMA_VERSION = "prices_daily.v1"
SNAPSHOT_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class SnapshotBuildResult:
    """一次 snapshot 构建的关键输出路径。"""

    snapshot_version: str
    snapshot_dir: Path
    prices_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class _RawInputFile:
    path: Path
    relative_path: str
    source_raw_date: date


def build_price_snapshot(
    *,
    raw_root: str | Path,
    snapshot_root: str | Path,
    asof_date: date,
    snapshot_version: str | None = None,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    created_at: str | None = None,
) -> SnapshotBuildResult:
    """从 raw 层生成 `prices_daily` 点时点快照。

    Parameters
    ----------
    raw_root:
        raw 层根目录。支持 `data/raw/{date}/*.csv`，并兼容
        `data/raw/{vendor}/{date}/*.csv`。
    snapshot_root:
        snapshot 输出根目录。
    asof_date:
        研究当下日期。所有输出行情都必须满足 `effective_date <= asof_date`。
    snapshot_version:
        可选快照版本。不传时根据输入内容和标准化输出确定性生成。
    schema_version:
        manifest 中记录的 schema 版本。
    created_at:
        manifest 中记录的创建时间。默认使用 `asof_date` 当天 Asia/Shanghai
        零点，保证同一输入重复生成 manifest hash 一致。
    """
    raw_root_path = Path(raw_root)
    snapshot_root_path = Path(snapshot_root)

    raw_files = _discover_raw_files(raw_root_path, asof_date=asof_date)
    if not raw_files:
        raise ValueError(f"no raw files found at or before asof_date={asof_date.isoformat()}")

    frames: list[pd.DataFrame] = []
    input_file_hashes: dict[str, str] = {}
    source_raw_dates: set[str] = set()

    for raw_file in raw_files:
        input_file_hashes[f"raw/{raw_file.relative_path}"] = _sha256_file(raw_file.path)
        source_raw_dates.add(raw_file.source_raw_date.strftime("%Y%m%d"))

        symbol = _infer_symbol(raw_file.path)
        raw_df = pd.read_csv(raw_file.path)
        normalized = normalize_etf_daily(
            raw_df,
            symbol=symbol,
            asof_date=asof_date,
            truncate_after_asof=True,
        )
        if not normalized.empty:
            frames.append(normalized)

    if not frames:
        raise ValueError(f"all raw rows are after asof_date={asof_date.isoformat()}")

    prices = (
        pd.concat(frames, ignore_index=True)
        .loc[:, PRICE_COLUMNS]
        .sort_values(["symbol", "trade_date", "effective_date"])
        .reset_index(drop=True)
    )
    _validate_snapshot_prices(prices, asof_date=asof_date)

    prices_csv_bytes = _to_deterministic_csv_bytes(prices)
    content_digest = _snapshot_content_digest(
        asof_date=asof_date,
        schema_version=schema_version,
        input_file_hashes=input_file_hashes,
        prices_csv_bytes=prices_csv_bytes,
    )
    final_snapshot_version = snapshot_version or f"{asof_date:%Y%m%d}-{content_digest[:8]}"

    snapshot_dir = snapshot_root_path / final_snapshot_version
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    prices_path = snapshot_dir / "prices_daily.csv"
    prices_path.write_bytes(prices_csv_bytes)

    created_at_value = created_at or _deterministic_created_at(asof_date)
    output_hashes = {"snapshot/prices_daily.csv": _sha256_bytes(prices_csv_bytes)}
    file_hashes = {**dict(sorted(input_file_hashes.items())), **output_hashes}

    manifest = {
        "snapshot_version": final_snapshot_version,
        "created_at": created_at_value,
        "asof_date": asof_date.isoformat(),
        "source_raw_dates": sorted(source_raw_dates),
        "input_files": [raw_file.relative_path for raw_file in raw_files],
        "file_hashes": file_hashes,
        "schema_version": schema_version,
        "row_counts": {"prices_daily": int(len(prices))},
        "min_date": _date_to_iso(prices["trade_date"].min()),
        "max_date": _date_to_iso(prices["trade_date"].max()),
    }

    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return SnapshotBuildResult(
        snapshot_version=final_snapshot_version,
        snapshot_dir=snapshot_dir,
        prices_path=prices_path,
        manifest_path=manifest_path,
    )


def _discover_raw_files(raw_root: Path, *, asof_date: date) -> list[_RawInputFile]:
    if not raw_root.exists():
        raise FileNotFoundError(f"raw_root does not exist: {raw_root}")

    discovered: list[_RawInputFile] = []
    for path in sorted(raw_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_RAW_SUFFIXES:
            continue

        relative_path = path.relative_to(raw_root).as_posix()
        source_raw_date = _find_source_raw_date(path.relative_to(raw_root))
        if source_raw_date is None:
            raise ValueError(f"raw file path must include a date folder: {relative_path}")
        if source_raw_date > asof_date:
            continue

        discovered.append(
            _RawInputFile(
                path=path,
                relative_path=relative_path,
                source_raw_date=source_raw_date,
            )
        )

    return sorted(discovered, key=lambda item: item.relative_path)


def _find_source_raw_date(relative_path: Path) -> date | None:
    for part in relative_path.parts[:-1]:
        parsed = _parse_date_part(part)
        if parsed is not None:
            return parsed
    return None


def _parse_date_part(value: str) -> date | None:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _infer_symbol(path: Path) -> str:
    return path.stem


def _validate_snapshot_prices(prices: pd.DataFrame, *, asof_date: date) -> None:
    missing = sorted(set(PRICE_COLUMNS) - set(prices.columns))
    if missing:
        raise ValueError(f"snapshot prices_daily missing columns: {missing}")

    if (prices["effective_date"] > asof_date).any():
        raise ValueError("snapshot contains rows with effective_date after asof_date")
    if (prices["trade_date"] > asof_date).any():
        raise ValueError("snapshot contains rows with trade_date after asof_date")

    duplicate_key = prices.duplicated(subset=["symbol", "trade_date"], keep=False)
    if duplicate_key.any():
        raise ValueError("snapshot contains duplicate symbol/trade_date rows")


def _snapshot_content_digest(
    *,
    asof_date: date,
    schema_version: str,
    input_file_hashes: dict[str, str],
    prices_csv_bytes: bytes,
) -> str:
    payload = {
        "asof_date": asof_date.isoformat(),
        "schema_version": schema_version,
        "input_file_hashes": dict(sorted(input_file_hashes.items())),
        "prices_daily_hash": _sha256_bytes(prices_csv_bytes),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return _sha256_bytes(encoded)


def _to_deterministic_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _deterministic_created_at(asof_date: date) -> str:
    dt = datetime.combine(asof_date, time.min, tzinfo=SNAPSHOT_TIMEZONE)
    return dt.isoformat()


def _date_to_iso(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return str(value)
