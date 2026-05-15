"""结构化回测报告归档。

P1-W10-01：把一次 BacktestResult 写成可复现、可读取、可审计的
`reports/backtest/{run_id}/` 目录。本模块只做报告与指标归档，
不新增策略、不修改参数、不改变信号逻辑。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
DEFAULT_OUTPUT_ROOT = Path("reports/backtest")

REQUIRED_REPORT_FILES = [
    "manifest.json",
    "metrics.json",
    "equity_curve.csv",
    "trades.csv",
    "holdings.csv",
    "orders.csv",
    "report.md",
]

REQUIRED_METRICS = [
    "total_return",
    "annualized_return",
    "max_drawdown",
    "sharpe",
    "sortino",
    "calmar",
    "win_rate",
    "profit_loss_ratio",
    "turnover",
    "trade_count",
    "monthly_returns",
    "drawdown_duration",
    "benchmark_return",
    "excess_return",
]


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run_id(manifest: dict[str, Any]) -> str:
    """根据回测身份与参数生成确定性 run_id。"""
    payload = {
        "strategy_id": manifest.get("strategy_id"),
        "snapshot_version": manifest.get("snapshot_version"),
        "params_hash": manifest.get("params_hash"),
        "start_date": manifest.get("start_date"),
        "end_date": manifest.get("end_date"),
        "initial_capital": manifest.get("initial_capital"),
        "random_seed": manifest.get("random_seed"),
    }
    digest = _sha256_bytes(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))[:10]
    return f"{manifest.get('strategy_id', 'unknown')}-{manifest.get('start_date')}-{digest}"


def _total_return(equity: pd.Series) -> float:
    if equity.empty or float(equity.iloc[0]) <= 0:
        return 0.0
    return float(float(equity.iloc[-1]) / float(equity.iloc[0]) - 1.0)


def _annualized_return(equity: pd.Series) -> float:
    if equity.empty or float(equity.iloc[0]) <= 0:
        return 0.0
    years = max(len(equity) / TRADING_DAYS_PER_YEAR, 1e-9)
    return float((float(equity.iloc[-1]) / float(equity.iloc[0])) ** (1.0 / years) - 1.0)


def _daily_returns(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    return equity.astype(float).pct_change().fillna(0.0)


def _sharpe(returns: pd.Series) -> float:
    if len(returns) <= 1:
        return 0.0
    std = float(returns.std(ddof=1))
    if std <= 0:
        return 0.0
    return float(float(returns.mean()) / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def _sortino(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    if len(downside) <= 1:
        return 0.0
    std = float(downside.std(ddof=1))
    if std <= 0:
        return 0.0
    return float(float(returns.mean()) / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def _win_rate(returns: pd.Series) -> float:
    non_zero = returns[returns != 0]
    if non_zero.empty:
        return 0.0
    return float((non_zero > 0).mean())


def _profit_loss_ratio(returns: pd.Series) -> float:
    gains = returns[returns > 0]
    losses = returns[returns < 0]
    if gains.empty or losses.empty:
        return 0.0
    return float(gains.mean() / abs(losses.mean()))


def _monthly_returns(equity_df: pd.DataFrame) -> dict[str, float]:
    if equity_df.empty:
        return {}
    df = equity_df[["trade_date", "equity"]].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    month_end = df.groupby(df["trade_date"].dt.to_period("M"))["equity"].last()
    monthly = month_end.pct_change().dropna()
    return {str(period): float(value) for period, value in monthly.items()}


def _drawdown_duration(drawdown: pd.Series) -> int:
    max_duration = 0
    current = 0
    for value in drawdown.astype(float).tolist():
        if value < 0:
            current += 1
            max_duration = max(max_duration, current)
        else:
            current = 0
    return int(max_duration)


def _turnover(equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> float:
    if equity_df.empty or trades_df.empty:
        return 0.0
    filled = trades_df[trades_df["status"].isin(["filled", "partial_filled"])]
    if filled.empty:
        return 0.0
    avg_equity = float(equity_df["equity"].mean())
    if avg_equity <= 0:
        return 0.0
    years = max(len(equity_df) / TRADING_DAYS_PER_YEAR, 1e-9)
    return float(float(filled["amount"].sum()) / avg_equity / years)


def compute_required_metrics(
    *,
    equity_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    benchmark_return: float = 0.0,
) -> dict[str, Any]:
    """计算 P1-W10-01 必报指标面板。"""
    if equity_df.empty:
        metrics: dict[str, Any] = {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "turnover": 0.0,
            "trade_count": 0,
            "monthly_returns": {},
            "drawdown_duration": 0,
            "benchmark_return": float(benchmark_return),
            "excess_return": -float(benchmark_return),
        }
        return metrics

    equity = equity_df["equity"].astype(float)
    returns = _daily_returns(equity)
    total_return = _total_return(equity)
    annualized_return = _annualized_return(equity)
    max_drawdown = float(equity_df["drawdown"].astype(float).min())
    calmar = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
    filled = trades_df[trades_df["status"].isin(["filled", "partial_filled"])] if not trades_df.empty else trades_df

    metrics = {
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "max_drawdown": float(max_drawdown),
        "sharpe": _sharpe(returns),
        "sortino": _sortino(returns),
        "calmar": float(calmar),
        "win_rate": _win_rate(returns),
        "profit_loss_ratio": _profit_loss_ratio(returns),
        "turnover": _turnover(equity_df, trades_df),
        "trade_count": int(len(filled)),
        "monthly_returns": _monthly_returns(equity_df),
        "drawdown_duration": _drawdown_duration(equity_df["drawdown"]),
        "benchmark_return": float(benchmark_return),
        "excess_return": float(total_return - benchmark_return),
    }
    return metrics


def _report_md(manifest: dict[str, Any], metrics: dict[str, Any]) -> str:
    lines = [
        f"# Backtest Report — {manifest.get('strategy_id', '?')}",
        "",
        "## 运行信息",
        "",
        f"- run_id: `{manifest.get('run_id')}`",
        f"- snapshot_version: `{manifest.get('snapshot_version')}`",
        f"- params_hash: `{manifest.get('params_hash')}`",
        f"- range: {manifest.get('start_date')} → {manifest.get('end_date')}",
        f"- initial_capital: {manifest.get('initial_capital')}",
        "",
        "## 必报指标",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
    ]
    for key in REQUIRED_METRICS:
        value = metrics.get(key)
        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## 归档文件",
            "",
            *[f"- `{name}`" for name in REQUIRED_REPORT_FILES],
            "",
            "> 本报告由 `src/reports/backtest_report.py` 自动生成。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, lineterminator="\n")


def build_report(
    *,
    result,
    output_root: str | Path | None = None,
    run_id: str | None = None,
    benchmark_return: float = 0.0,
) -> Path:
    """把 BacktestResult 持久化到 `reports/backtest/{run_id}/`。"""
    base_manifest = dict(result.manifest)
    full_metrics = compute_required_metrics(
        equity_df=result.equity_curve,
        trades_df=result.trades,
        benchmark_return=benchmark_return,
    )
    rid = run_id or _run_id(base_manifest)
    out = (Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT) / rid
    out.mkdir(parents=True, exist_ok=True)

    orders_df = getattr(result, "orders", result.trades)
    _write_csv(result.equity_curve, out / "equity_curve.csv")
    _write_csv(result.trades, out / "trades.csv")
    _write_csv(result.holdings, out / "holdings.csv")
    _write_csv(orders_df, out / "orders.csv")

    manifest = {
        **base_manifest,
        "run_id": rid,
        "report_schema_version": "backtest_report.v1",
        "report_files": REQUIRED_REPORT_FILES,
    }
    report_body = _report_md(manifest, full_metrics)
    (out / "report.md").write_text(report_body, encoding="utf-8")
    (out / "metrics.json").write_text(_json_dumps(full_metrics), encoding="utf-8")

    file_hashes = {
        name: _sha256_file(out / name)
        for name in [
            "metrics.json",
            "equity_curve.csv",
            "trades.csv",
            "holdings.csv",
            "orders.csv",
            "report.md",
        ]
    }
    manifest["file_hashes"] = file_hashes
    (out / "manifest.json").write_text(_json_dumps(manifest), encoding="utf-8")
    return out
