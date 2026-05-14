"""单元测试：backtest_report 归档。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtest import engine
from reports import backtest_report
from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal


@pytest.mark.unit
def test_report_persists_required_files(
    tmp_path, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
    )
    result = engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )
    out_dir = backtest_report.build_report(result=result, output_root=tmp_path)
    for f in [
        "manifest.json",
        "metrics.json",
        "equity_curve.csv",
        "trades.csv",
        "holdings.csv",
        "summary.md",
    ]:
        assert (out_dir / f).exists(), f"missing {f}"


@pytest.mark.unit
def test_manifest_required_fields(
    tmp_path, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
    )
    result = engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )
    out_dir = backtest_report.build_report(result=result, output_root=tmp_path)
    manifest = json.loads((out_dir / "manifest.json").read_text())
    for f in [
        "strategy_id",
        "snapshot_version",
        "params_hash",
        "metrics_summary",
        "random_seed",
        "start_date",
        "end_date",
        "initial_capital",
    ]:
        assert f in manifest


@pytest.mark.unit
def test_report_default_root_is_reports_backtest(
    tmp_path, monkeypatch, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
    )
    result = engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )

    out_dir = backtest_report.build_report(result=result, run_id="fixed-run")

    assert out_dir == Path("reports/backtest/cn_etf_rot_v1/fixed-run")
    assert (tmp_path / out_dir / "manifest.json").exists()
