# ruff: noqa: RUF002
"""端到端回归：realistic raw/reference → snapshot → backtest → report。

本测试使用 tests/fixtures/realistic_raw 下的小型真实形态样例：
AKShare 形态 raw CSV + reference CSV。为避免短样例被正式轮动策略的
min_history_days 过滤为空，本文件内使用测试专用固定 signal_fn；它只用于验证
数据链路和回测撮合规则，不是新策略，也不会进入 src/strategies。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backtest import engine
from data import etf_loader
from data.snapshot import build_price_snapshot
from reports import backtest_report

REPO_ROOT = Path(__file__).resolve().parents[2]
REALISTIC_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "realistic_raw"
RAW_ROOT = REALISTIC_FIXTURE_ROOT / "raw"
REFERENCE_ROOT = REALISTIC_FIXTURE_ROOT / "reference"
ASOF_DATE = date(2026, 5, 15)
RUN_ID = "realistic-snapshot-e2e"


@dataclass(frozen=True)
class _FixedSignalParams:
    """测试专用参数对象，仅供 engine manifest hash 使用。"""

    n_capacity_pct: float = 0.05


def _fixed_fixture_signal(
    asof_date: date,
    prices: pd.DataFrame,
    master: pd.DataFrame,
    params: _FixedSignalParams,
) -> pd.DataFrame:
    """短样例专用固定信号，不是新策略。

    2026-05-08 是样例窗口第一周最后一个交易日；引擎会在下一交易日
    2026-05-11 执行订单，从而同时覆盖：正常成交、退市拒单、停牌拒单。
    """
    del prices, params
    if asof_date != date(2026, 5, 8):
        return pd.DataFrame(columns=["symbol", "target_weight"])

    target_symbols = ["510300.SH", "510999.SH", "518880.SH"]
    visible_symbols = set(master["symbol"].astype(str))
    rows = [
        {"symbol": symbol, "target_weight": weight}
        for symbol, weight in zip(target_symbols, [0.30, 0.20, 0.20])
        if symbol in visible_symbols
    ]
    return pd.DataFrame(rows, columns=["symbol", "target_weight"])


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_chain(workdir: Path):
    snapshot = build_price_snapshot(
        raw_root=RAW_ROOT,
        snapshot_root=workdir / "snapshots",
        reference_root=REFERENCE_ROOT,
        asof_date=ASOF_DATE,
    )
    prices = etf_loader.load_prices(snapshot.snapshot_dir)
    master = etf_loader.load_etf_master(snapshot.snapshot_dir)
    calendar = etf_loader.load_calendar(snapshot.snapshot_dir)

    cfg = engine.BacktestConfig(
        strategy_id="test_fixed_signal_snapshot_e2e",
        start_date=date(2026, 5, 4),
        end_date=ASOF_DATE,
        initial_capital=1_000_000.0,
        snapshot_version=snapshot.snapshot_version,
        random_seed=42,
    )
    result = engine.run_backtest(
        config=cfg,
        prices=prices,
        master=master,
        calendar=calendar,
        signal_fn=_fixed_fixture_signal,
        params=_FixedSignalParams(),
    )
    report_dir = backtest_report.build_report(
        result=result,
        output_root=workdir / "reports" / "backtest",
        run_id=RUN_ID,
    )
    return snapshot, prices, master, calendar, result, report_dir


@pytest.mark.regression
def test_realistic_raw_reference_snapshot_to_backtest_e2e(tmp_path: Path) -> None:
    snapshot, prices, master, calendar, result, report_dir = _run_chain(tmp_path / "run_a")

    snapshot_manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    report_manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))

    assert snapshot_manifest["snapshot_version"] == snapshot.snapshot_version
    assert report_manifest["snapshot_version"] == snapshot.snapshot_version
    assert report_dir == tmp_path / "run_a" / "reports" / "backtest" / RUN_ID

    assert max(prices["trade_date"]) <= ASOF_DATE
    assert "2026-05-18" not in set(pd.read_csv(snapshot.prices_path)["trade_date"])
    assert max(calendar["trade_date"]) <= ASOF_DATE

    assert "159999.SZ" not in set(master["symbol"])
    assert "159999.SZ" not in set(prices["symbol"])

    delisted = master[master["symbol"] == "510999.SH"].iloc[0]
    assert delisted["delist_date"] == date(2026, 5, 8)
    delisted_orders = result.trades[result.trades["symbol"] == "510999.SH"]
    assert delisted_orders["reject_reason"].tolist() == ["delisted"]

    suspended_bar = prices[
        (prices["symbol"] == "518880.SH") & (prices["trade_date"] == date(2026, 5, 11))
    ].iloc[0]
    assert bool(suspended_bar["is_suspended"]) is True
    suspended_orders = result.trades[result.trades["symbol"] == "518880.SH"]
    assert suspended_orders["reject_reason"].tolist() == ["suspended"]

    filled = result.trades[result.trades["status"].isin(["filled", "partial_filled"])]
    assert not result.equity_curve.empty
    assert not result.trades.empty
    assert not result.holdings.empty
    assert set(filled["symbol"]) == {"510300.SH"}
    assert result.metrics["n_trading_days"] == len(calendar)

    for filename in backtest_report.REQUIRED_REPORT_FILES:
        assert (report_dir / filename).exists(), f"missing {filename}"


def test_realistic_snapshot_to_backtest_chain_is_reproducible(tmp_path: Path) -> None:
    first = _run_chain(tmp_path / "first")
    second = _run_chain(tmp_path / "second")

    first_snapshot, _prices_a, _master_a, _calendar_a, first_result, first_report = first
    second_snapshot, _prices_b, _master_b, _calendar_b, second_result, second_report = second

    assert first_snapshot.snapshot_version == second_snapshot.snapshot_version
    assert _sha256_file(first_snapshot.prices_path) == _sha256_file(second_snapshot.prices_path)
    assert _sha256_file(first_snapshot.manifest_path) == _sha256_file(second_snapshot.manifest_path)
    assert first_result.equity_curve.equals(second_result.equity_curve)
    assert first_result.trades.equals(second_result.trades)
    assert first_result.holdings.equals(second_result.holdings)
    assert first_result.metrics == second_result.metrics

    for filename in backtest_report.REQUIRED_REPORT_FILES:
        assert _sha256_file(first_report / filename) == _sha256_file(second_report / filename)
