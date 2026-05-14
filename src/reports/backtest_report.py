"""回测报告生成器。

输入：BacktestResult。输出：写入 `reports/backtest/<strategy_id>/<run_id>/` 的归档。
单一职责：只**生成**报告，不做计算（指标已由 engine.compute_metrics 给出）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPORT_FILES = [
    "manifest.json",
    "metrics.json",
    "equity_curve.csv",
    "trades.csv",
    "holdings.csv",
    "summary.md",
]
DEFAULT_OUTPUT_ROOT = Path("reports/backtest")


def _run_id(manifest: dict[str, Any]) -> str:
    """run_id 由 manifest 内容哈希 + 时间戳前缀生成。

    时间戳精确到秒，写入文件路径但**不**写入 manifest.json 内容，
    以保持同输入 byte-for-byte 一致。
    """
    body = json.dumps(
        {k: v for k, v in manifest.items() if k != "built_at_utc"}, sort_keys=True, default=str
    )
    short = hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{short}"


def _summary_md(manifest: dict[str, Any], metrics: dict[str, Any]) -> str:
    lines = [
        f"# Backtest Summary — {manifest.get('strategy_id', '?')}",
        "",
        f"- snapshot_version: `{manifest.get('snapshot_version')}`",
        f"- params_hash: `{manifest.get('params_hash')}`",
        f"- range: {manifest.get('start_date')} → {manifest.get('end_date')}",
        f"- initial_capital: {manifest.get('initial_capital')}",
        "",
        "## 必报指标",
        "",
        "| 指标 | 值 |",
        "|---|---|",
    ]
    for k in [
        "annualized_return",
        "max_drawdown",
        "sharpe",
        "sortino",
        "calmar",
        "turnover",
        "trade_count",
        "final_equity",
        "n_trading_days",
    ]:
        v = metrics.get(k)
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("> 本报告由 `src/reports/backtest_report.py` 自动生成。")
    return "\n".join(lines)


def build_report(
    *,
    result,  # BacktestResult
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> Path:
    """把 BacktestResult 持久化到 reports/backtest/<strategy_id>/<run_id>/。

    Returns 实际写入的目录路径。
    """
    manifest = dict(result.manifest)
    metrics = dict(result.metrics)
    strategy_id = manifest.get("strategy_id", "unknown")
    rid = run_id or _run_id(manifest)
    out = (Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT) / strategy_id / rid
    out.mkdir(parents=True, exist_ok=True)

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    result.equity_curve.to_csv(out / "equity_curve.csv", index=False)
    result.trades.to_csv(out / "trades.csv", index=False)
    result.holdings.to_csv(out / "holdings.csv", index=False)
    (out / "summary.md").write_text(_summary_md(manifest, metrics))
    return out
