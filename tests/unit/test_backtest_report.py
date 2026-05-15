"""单元测试：backtest_report 结构化归档。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtest import engine
from reports import backtest_report
from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal


def _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates):
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
    )
    return engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )


@pytest.mark.unit
def test_report_persists_required_files(
    tmp_path, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    result = _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates)
    out_dir = backtest_report.build_report(result=result, output_root=tmp_path, run_id="fixed-run")

    for filename in backtest_report.REQUIRED_REPORT_FILES:
        assert (out_dir / filename).exists(), f"missing {filename}"


@pytest.mark.unit
def test_manifest_required_fields(
    tmp_path, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    result = _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates)
    out_dir = backtest_report.build_report(result=result, output_root=tmp_path, run_id="fixed-run")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    for field in [
        "strategy_id",
        "snapshot_version",
        "params_hash",
        "metrics_summary",
        "random_seed",
        "start_date",
        "end_date",
        "initial_capital",
        "run_id",
        "report_schema_version",
        "report_files",
        "file_hashes",
    ]:
        assert field in manifest
    assert manifest["run_id"] == "fixed-run"
    assert manifest["report_files"] == backtest_report.REQUIRED_REPORT_FILES


@pytest.mark.unit
def test_metrics_required_fields(
    tmp_path, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    result = _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates)
    out_dir = backtest_report.build_report(result=result, output_root=tmp_path, run_id="fixed-run")
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))

    for field in backtest_report.REQUIRED_METRICS:
        assert field in metrics
    assert isinstance(metrics["monthly_returns"], dict)
    assert isinstance(metrics["drawdown_duration"], int)


@pytest.mark.unit
def test_report_default_root_is_reports_backtest(
    tmp_path, monkeypatch, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates)

    out_dir = backtest_report.build_report(result=result, run_id="fixed-run")

    assert out_dir == Path("reports/backtest/fixed-run")
    assert (tmp_path / out_dir / "manifest.json").exists()
