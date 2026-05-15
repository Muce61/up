"""端到端回归：合成 raw 样例 → snapshot → 加载 → 派生日历 → 回测 → 报告。

本测试只验证**数据流水线管道是否打通且可复现**。
所用行情是合成数据（见 scripts/synthetic_raw_sample.py），
**不是真实市场数据，任何指标都不构成策略有效性证据。**
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backtest import engine
from data import etf_loader
from data.snapshot import build_price_snapshot
from reports import backtest_report
from scripts.synthetic_raw_sample import build_synthetic_raw
from strategies.etf_rotation.cn_etf_rot_v1.signal import SignalParams, generate_signal

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_CFG = REPO_ROOT / "config" / "universe" / "etf_pool.yaml"
PARAMS_CFG = REPO_ROOT / "config" / "strategy_params" / "cn_etf_rot_v1.yaml"


def _run_full_chain(workdir: Path):
    """执行完整链路，返回 (snapshot_result, backtest_result, report_dir)。"""
    raw_root = workdir / "raw"
    snap_root = workdir / "snapshots"
    asof = build_synthetic_raw(raw_root, n_days=400, seed=20260515)

    snap = build_price_snapshot(raw_root=raw_root, snapshot_root=snap_root, asof_date=asof)

    prices = etf_loader.load_prices(snap.snapshot_dir)
    calendar = etf_loader.derive_calendar_from_prices(prices)
    master = etf_loader.load_etf_master(UNIVERSE_CFG)
    master = master[master["symbol"].isin(prices["symbol"].unique())].reset_index(drop=True)

    params = SignalParams.from_yaml(PARAMS_CFG)
    cal_dates = sorted(calendar["trade_date"])
    warmup = int(getattr(params, "min_history_days", 252))
    start_idx = min(warmup + 10, len(cal_dates) // 2)

    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=cal_dates[start_idx],
        end_date=cal_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version=snap.snapshot_version,
    )
    result = engine.run_backtest(
        config=cfg,
        prices=prices,
        master=master,
        calendar=calendar,
        signal_fn=generate_signal,
        params=params,
    )
    report_dir = backtest_report.build_report(
        result=result, output_root=workdir / "reports", run_id="e2e-fixed"
    )
    return snap, result, report_dir


@pytest.mark.regression
def test_snapshot_artifacts_generated(tmp_path: Path) -> None:
    snap, _result, _report_dir = _run_full_chain(tmp_path)
    assert snap.prices_path.exists()
    assert snap.manifest_path.exists()
    assert snap.snapshot_version  # 非空版本号


@pytest.mark.regression
def test_engine_consumes_snapshot_and_produces_equity_curve(tmp_path: Path) -> None:
    _snap, result, _report_dir = _run_full_chain(tmp_path)
    assert len(result.equity_curve) > 0
    assert result.equity_curve["equity"].iloc[0] > 0
    assert result.metrics["n_trading_days"] > 0


@pytest.mark.regression
def test_report_artifacts_complete(tmp_path: Path) -> None:
    _snap, _result, report_dir = _run_full_chain(tmp_path)
    for filename in backtest_report.REQUIRED_REPORT_FILES:
        assert (report_dir / filename).exists(), f"missing {filename}"


@pytest.mark.regression
def test_full_chain_is_reproducible(tmp_path: Path) -> None:
    """同一合成输入，两次完整链路 → snapshot_version 与关键指标 byte-for-byte 一致。"""
    snap_a, result_a, _ = _run_full_chain(tmp_path / "run_a")
    snap_b, result_b, _ = _run_full_chain(tmp_path / "run_b")

    assert snap_a.snapshot_version == snap_b.snapshot_version
    for key in ("annualized_return", "max_drawdown", "sharpe", "turnover", "final_equity"):
        assert result_a.metrics[key] == result_b.metrics[key], f"metric drift: {key}"
    assert result_a.equity_curve.equals(result_b.equity_curve)
