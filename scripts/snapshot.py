"""CLI wrapper for P1-W4-03 snapshot generation."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from data.snapshot import build_price_snapshot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PIT price snapshot from raw data.")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--snapshot-root", type=Path, default=Path("data/snapshots"))
    parser.add_argument("--asof-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--snapshot-version", default=None)
    parser.add_argument("--reference-root", type=Path, default=None)
    parser.add_argument("--trading-calendar-path", type=Path, default=None)
    parser.add_argument("--etf-master-path", type=Path, default=None)
    parser.add_argument("--schema-version", default="prices_daily.v1")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = build_price_snapshot(
        raw_root=args.raw_root,
        snapshot_root=args.snapshot_root,
        asof_date=date.fromisoformat(args.asof_date),
        snapshot_version=args.snapshot_version,
        schema_version=args.schema_version,
        reference_root=args.reference_root,
        trading_calendar_path=args.trading_calendar_path,
        etf_master_path=args.etf_master_path,
    )
    print(result.snapshot_dir.as_posix())


if __name__ == "__main__":
    main()
