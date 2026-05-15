"""回归测试：结构化回测归档完整性与可复现性。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backtest import engine
from reports import backtest_report
from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates):
    cfg = engine.BacktestConfig(
        strategy_id="cn_etf_rot_v1",
        start_date=calendar_dates[150],
        end_date=calendar_dates[-1],
        initial_capital=1_000_000.0,
        snapshot_version="fixtures-mini",
        random_seed=42,
    )
    return engine.run_backtest(
        config=cfg,
        prices=prices_df,
        master=master_df,
        calendar=calendar_df,
        signal_fn=generate_signal,
        params=signal_params,
    )


@pytest.mark.regression
def test_backtest_archive_contains_required_files_and_metrics(
    tmp_path, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    result = _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates)
    out_dir = backtest_report.build_report(result=result, output_root=tmp_path, run_id="fixture-run")

    for filename in backtest_report.REQUIRED_REPORT_FILES:
        assert (out_dir / filename).exists(), f"missing {filename}"

    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    for field in backtest_report.REQUIRED_METRICS:
        assert field in metrics

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "fixture-run"
    assert sorted(manifest["file_hashes"]) == sorted(
        filename for filename in backtest_report.REQUIRED_REPORT_FILES if filename != "manifest.json"
    )


@pytest.mark.regression
def test_backtest_archive_is_field_level_reproducible(
    tmp_path, prices_df, master_df, calendar_df, signal_params, calendar_dates
) -> None:
    first_result = _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates)
    second_result = _run_fixture_backtest(prices_df, master_df, calendar_df, signal_params, calendar_dates)

    first_dir = backtest_report.build_report(
        result=first_result,
        output_root=tmp_path / "first",
        run_id="fixture-run",
    )
    second_dir = backtest_report.build_report(
        result=second_result,
        output_root=tmp_path / "second",
        run_id="fixture-run",
    )

    for filename in backtest_report.REQUIRED_REPORT_FILES:
        assert _sha256_file(first_dir / filename) == _sha256_file(second_dir / filename)
