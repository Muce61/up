# ruff: noqa: RUF002
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
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .akshare_adapter import PRICE_COLUMNS, normalize_etf_daily
from .reference import filter_visible_etf_master, filter_visible_trading_calendar

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
    etf_master_path: Path | None = None
    trading_calendar_path: Path | None = None


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
    reference_root: str | Path | None = None,
    trading_calendar_path: str | Path | None = None,
    trading_calendar: pd.DataFrame | None = None,
    etf_master_path: str | Path | None = None,
    etf_master: pd.DataFrame | None = None,
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
    reference_root:
        可选 reference layer 根目录。若提供，读取 `trading_calendar.csv` 和
        `etf_master.csv`，按 asof_date 做 PIT 过滤后随 snapshot 一起落地。
    trading_calendar_path / etf_master_path:
        可选 reference CSV 单文件路径。优先用于显式传入单表。
    trading_calendar / etf_master:
        可选 reference DataFrame。用于测试或上游已加载数据；仍会按 asof_date
        做 schema 校验与 PIT 过滤。
    """
    raw_root_path = Path(raw_root)
    snapshot_root_path = Path(snapshot_root)
    reference_root_path = Path(reference_root) if reference_root is not None else None

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
        raw_df = _truncate_raw_rows_after_asof(pd.read_csv(raw_file.path), asof_date=asof_date)
        normalized = normalize_etf_daily(
            raw_df,
            symbol=symbol,
            asof_date=asof_date,
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

    reference_options: dict[str, Any] = {}
    if trading_calendar_path is not None:
        reference_options["trading_calendar_path"] = trading_calendar_path
    if trading_calendar is not None:
        reference_options["trading_calendar"] = trading_calendar
    if etf_master_path is not None:
        reference_options["etf_master_path"] = etf_master_path
    if etf_master is not None:
        reference_options["etf_master"] = etf_master

    reference_result = _load_reference_outputs(
        reference_root_path,
        asof_date=asof_date,
        **reference_options,
    )
    reference_outputs, reference_files = _split_reference_outputs(reference_result)
    prices = _apply_reference_universe(prices, reference_outputs.get("etf_master"))
    _validate_snapshot_prices(prices, asof_date=asof_date)

    prices_csv_bytes = _to_deterministic_csv_bytes(prices)
    reference_output_hashes = {
        f"snapshot/{_snapshot_reference_filename(name)}": _sha256_bytes(
            _to_deterministic_csv_bytes(df)
        )
        for name, df in sorted(reference_outputs.items())
    }
    content_digest = _snapshot_content_digest(
        asof_date=asof_date,
        schema_version=schema_version,
        input_file_hashes=input_file_hashes,
        prices_csv_bytes=prices_csv_bytes,
        reference_output_hashes=reference_output_hashes,
    )
    final_snapshot_version = snapshot_version or f"{asof_date:%Y%m%d}-{content_digest[:8]}"

    snapshot_dir = snapshot_root_path / final_snapshot_version
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    prices_path = snapshot_dir / "prices_daily.csv"
    prices_path.write_bytes(prices_csv_bytes)

    snapshot_etf_master_path: Path | None = None
    snapshot_trading_calendar_path: Path | None = None

    created_at_value = created_at or _deterministic_created_at(asof_date)
    output_hashes = {"snapshot/prices_daily.csv": _sha256_bytes(prices_csv_bytes)}
    row_counts = {"prices_daily": len(prices)}
    reference_hashes: dict[str, str] = {}
    reference_row_counts: dict[str, int] = {}

    for name, df in reference_outputs.items():
        csv_bytes = _to_deterministic_csv_bytes(df)
        if name == "etf_master":
            snapshot_etf_master_path = snapshot_dir / "etf_master.csv"
            snapshot_etf_master_path.write_bytes(csv_bytes)
            output_hashes["snapshot/etf_master.csv"] = _sha256_bytes(csv_bytes)
            reference_hashes["snapshot/etf_master.csv"] = _sha256_bytes(csv_bytes)
        elif name == "trading_calendar":
            snapshot_trading_calendar_path = snapshot_dir / "trading_calendar.csv"
            snapshot_trading_calendar_path.write_bytes(csv_bytes)
            output_hashes["snapshot/trading_calendar.csv"] = _sha256_bytes(csv_bytes)
            reference_hashes["snapshot/trading_calendar.csv"] = _sha256_bytes(csv_bytes)
        row_counts[name] = len(df)
        reference_row_counts[name] = len(df)

    file_hashes = {**dict(sorted(input_file_hashes.items())), **output_hashes}

    manifest = {
        "snapshot_version": final_snapshot_version,
        "created_at": created_at_value,
        "asof_date": asof_date.isoformat(),
        "source_raw_dates": sorted(source_raw_dates),
        "input_files": [raw_file.relative_path for raw_file in raw_files],
        "file_hashes": file_hashes,
        "schema_version": schema_version,
        "reference_files": reference_files,
        "reference_hashes": dict(sorted(reference_hashes.items())),
        "reference_row_counts": dict(sorted(reference_row_counts.items())),
        "row_counts": row_counts,
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
        etf_master_path=snapshot_etf_master_path,
        trading_calendar_path=snapshot_trading_calendar_path,
    )
    _convert_bool_columns(calendar, ["is_open"])
    return filter_visible_trading_calendar(calendar, asof_date=asof_date)


def _visible_etf_master_from_frame(df: pd.DataFrame, *, asof_date: date) -> pd.DataFrame:
    master = df.copy()
    _convert_date_columns(master, ["list_date", "delist_date", "effective_date"])
    _convert_bool_columns(master, ["stamp_tax_applicable"])
    return filter_visible_etf_master(master, asof_date=asof_date)


def _apply_reference_universe(
    prices: pd.DataFrame, visible_master: pd.DataFrame | None
) -> pd.DataFrame:
    if visible_master is None:
        return prices.sort_values(["symbol", "trade_date", "effective_date"]).reset_index(drop=True)
    visible_symbols = set(visible_master["symbol"].astype(str).tolist())
    filtered = prices[prices["symbol"].astype(str).isin(visible_symbols)].copy()
    if filtered.empty:
        raise ValueError("reference etf_master removed all prices_daily rows")
    return filtered.sort_values(["symbol", "trade_date", "effective_date"]).reset_index(drop=True)


def _convert_date_columns(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        df[col] = parsed.apply(lambda value: value.date() if pd.notna(value) else None)


def _convert_bool_columns(df: pd.DataFrame, columns: list[str]) -> None:
    truthy = {"true", "1", "yes", "y"}
    falsy = {"false", "0", "no", "n", ""}
    for col in columns:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(
            lambda value, column=col: _parse_bool(value, col=column, truthy=truthy, falsy=falsy)
        )


def _parse_bool(value: object, *, col: str, truthy: set[str], falsy: set[str]) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        raise ValueError(f"{col} must be bool and must not be null")
    lowered = str(value).strip().lower()
    if lowered in truthy:
        return True
    if lowered in falsy:
        return False
    raise ValueError(f"{col} must be bool-compatible, got {value!r}")


def _split_reference_outputs(
    reference_result: object,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Normalize supported reference loader return shapes.

    The canonical return value is ``(outputs, reference_files)``.  This
    defensive normalization also accepts a bare outputs mapping and one level
    of accidentally nested tuple output so a merge-conflict resolution cannot
    make callers treat a tuple as the outputs mapping.
    """
    if isinstance(reference_result, dict):
        return reference_result, {}

    if not isinstance(reference_result, tuple) or len(reference_result) != 2:
        raise TypeError("reference loader must return outputs or (outputs, reference_files)")

    outputs, reference_files = reference_result
    if isinstance(outputs, tuple) and len(outputs) == 2:
        nested_outputs, nested_reference_files = outputs
        outputs = nested_outputs
        if not reference_files and isinstance(nested_reference_files, dict):
            reference_files = nested_reference_files

    if not isinstance(outputs, dict):
        raise TypeError("reference loader outputs must be a dict")
    if not isinstance(reference_files, dict):
        raise TypeError("reference loader reference_files must be a dict")

    return outputs, reference_files


def _snapshot_reference_filename(name: str) -> str:
    if name == "etf_master":
        return "etf_master.csv"
    if name == "trading_calendar":
        return "trading_calendar.csv"
    raise ValueError(f"unsupported reference output: {name}")


def _load_reference_outputs(
    reference_root: Path | None,
    *,
    asof_date: date,
    trading_calendar_path: str | Path | None = None,
    trading_calendar: pd.DataFrame | None = None,
    etf_master_path: str | Path | None = None,
    etf_master: pd.DataFrame | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    if reference_root is not None and not reference_root.exists():
        raise FileNotFoundError(f"reference_root does not exist: {reference_root}")

    if trading_calendar is not None and trading_calendar_path is not None:
        raise ValueError("pass only one of trading_calendar or trading_calendar_path")
    if etf_master is not None and etf_master_path is not None:
        raise ValueError("pass only one of etf_master or etf_master_path")

    calendar_path = Path(trading_calendar_path) if trading_calendar_path is not None else None
    master_path = Path(etf_master_path) if etf_master_path is not None else None
    if reference_root is not None:
        calendar_path = calendar_path or reference_root / "trading_calendar.csv"
        master_path = master_path or reference_root / "etf_master.csv"

    outputs: dict[str, pd.DataFrame] = {}
    reference_files: dict[str, str] = {}

    if trading_calendar is not None:
        visible_calendar = _visible_trading_calendar_from_frame(
            trading_calendar, asof_date=asof_date
        )
        outputs["trading_calendar"] = visible_calendar
        reference_files["trading_calendar"] = "<dataframe>"
    elif calendar_path is not None:
        if not calendar_path.exists():
            msg = f"trading_calendar reference file does not exist: {calendar_path}"
            raise FileNotFoundError(msg)
        calendar = pd.read_csv(calendar_path)
        visible_calendar = _visible_trading_calendar_from_frame(calendar, asof_date=asof_date)
        outputs["trading_calendar"] = visible_calendar
        reference_files["trading_calendar"] = calendar_path.as_posix()

    if etf_master is not None:
        visible_master = _visible_etf_master_from_frame(etf_master, asof_date=asof_date)
        outputs["etf_master"] = visible_master
        reference_files["etf_master"] = "<dataframe>"
    elif master_path is not None:
        if not master_path.exists():
            raise FileNotFoundError(f"etf_master reference file does not exist: {master_path}")
        master = pd.read_csv(master_path)
        visible_master = _visible_etf_master_from_frame(master, asof_date=asof_date)
        outputs["etf_master"] = visible_master
        reference_files["etf_master"] = master_path.as_posix()

    return outputs, dict(sorted(reference_files.items()))


def _visible_trading_calendar_from_frame(df: pd.DataFrame, *, asof_date: date) -> pd.DataFrame:
    calendar = df.copy()
    _convert_date_columns(
        calendar,
        ["trade_date", "prev_trade_date", "next_trade_date", "effective_date"],
    )
    _convert_bool_columns(calendar, ["is_open"])
    return filter_visible_trading_calendar(calendar, asof_date=asof_date)


def _visible_etf_master_from_frame(df: pd.DataFrame, *, asof_date: date) -> pd.DataFrame:
    master = df.copy()
    _convert_date_columns(master, ["list_date", "delist_date", "effective_date"])
    _convert_bool_columns(master, ["stamp_tax_applicable"])
    return filter_visible_etf_master(master, asof_date=asof_date)


def _apply_reference_universe(
    prices: pd.DataFrame, visible_master: pd.DataFrame | None
) -> pd.DataFrame:
    if visible_master is None:
        return prices.sort_values(["symbol", "trade_date", "effective_date"]).reset_index(drop=True)
    visible_symbols = set(visible_master["symbol"].astype(str).tolist())
    filtered = prices[prices["symbol"].astype(str).isin(visible_symbols)].copy()
    if filtered.empty:
        raise ValueError("reference etf_master removed all prices_daily rows")
    return filtered.sort_values(["symbol", "trade_date", "effective_date"]).reset_index(drop=True)


def _convert_date_columns(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        df[col] = parsed.apply(lambda value: value.date() if pd.notna(value) else None)


def _convert_bool_columns(df: pd.DataFrame, columns: list[str]) -> None:
    truthy = {"true", "1", "yes", "y"}
    falsy = {"false", "0", "no", "n", ""}
    for col in columns:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(
            lambda value, column=col: _parse_bool(value, col=column, truthy=truthy, falsy=falsy)
        )


def _parse_bool(value: object, *, col: str, truthy: set[str], falsy: set[str]) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        raise ValueError(f"{col} must be bool and must not be null")
    lowered = str(value).strip().lower()
    if lowered in truthy:
        return True
    if lowered in falsy:
        return False
    raise ValueError(f"{col} must be bool-compatible, got {value!r}")


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


def _truncate_raw_rows_after_asof(raw: pd.DataFrame, *, asof_date: date) -> pd.DataFrame:
    """按 AKShare 原始 `日期` 字段做 PIT 预截断。"""
    if "日期" not in raw.columns:
        return raw
    raw_dates = pd.to_datetime(raw["日期"], errors="coerce")
    visible_mask = raw_dates.apply(lambda value: pd.notna(value) and value.date() <= asof_date)
    return raw.loc[visible_mask].copy()


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
    reference_output_hashes: dict[str, str] | None = None,
) -> str:
    payload = {
        "asof_date": asof_date.isoformat(),
        "schema_version": schema_version,
        "input_file_hashes": dict(sorted(input_file_hashes.items())),
        "prices_daily_hash": _sha256_bytes(prices_csv_bytes),
        "reference_output_hashes": dict(sorted((reference_output_hashes or {}).items())),
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
