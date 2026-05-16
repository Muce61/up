"""CLI for fetching and caching AKShare raw ETF daily data."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from data.akshare_fetcher import fetch_akshare_raw_cache


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch AKShare ETF raw CSV cache.")
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated symbols, e.g. 510300.SH,510500.SH",
    )
    parser.add_argument("--asof-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--vendor", default="akshare")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    result = fetch_akshare_raw_cache(
        symbols=symbols,
        asof_date=date.fromisoformat(args.asof_date),
        raw_root=args.raw_root,
        vendor=args.vendor,
        overwrite=bool(args.overwrite),
    )
    print(result.manifest_path.as_posix())


if __name__ == "__main__":
    main()
