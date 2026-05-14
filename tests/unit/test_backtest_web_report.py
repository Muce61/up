"""单元测试：本地回测网页报告生成。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "build_backtest_web_report.py"
    spec = importlib.util.spec_from_file_location("build_backtest_web_report", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_review(report_root: Path) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "etf_rotation_review.md").write_text(
        """# ETF 轮动策略严格回测审查

证据口径：以下数值来自 `tests/conftest.py` 的合成 fixtures，仅用于工程审查。

## 0. 总体结论

结论：**需要继续修正**。

## 1. 数据完整性

| 检查项 | 结果 |
|---|---:|
| 缺失 symbol-date 行 | 0 |

## 4. 结果指标

| 指标 | 数值 |
|---|---:|
| 年化收益 | `-36.76%` |
| 最大回撤 | `-52.85%` |
| Sharpe | `-0.6745` |
| Sortino | `-0.4807` |
| Calmar | `-0.6956` |
| 胜率 | `53.85%` |
| 盈亏比 | `1.2681` |
| 换手率 | `26.0371` |
| 交易次数 | `108` |

## 6. 阻断问题清单

1. **容量约束未接入回测引擎**。

## 8. 下一步建议

1. 优先实现滑点模型。
""",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_backtest_web_report_html_file_can_be_generated(tmp_path) -> None:
    module = _load_module()
    report_root = tmp_path / "reports" / "backtest"
    _write_review(report_root)

    output = module.build_web_report(report_root=report_root)

    assert output == report_root / "index.html"
    assert output.exists()
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")


@pytest.mark.unit
def test_backtest_web_report_contains_key_metric_fields(tmp_path) -> None:
    module = _load_module()
    report_root = tmp_path / "reports" / "backtest"
    _write_review(report_root)

    html = module.build_web_report(report_root=report_root).read_text(encoding="utf-8")

    for field in ["年化收益", "最大回撤", "Sharpe", "Sortino", "Calmar", "胜率", "盈亏比", "换手率", "交易次数"]:
        assert field in html


@pytest.mark.unit
def test_backtest_web_report_contains_review_conclusion(tmp_path) -> None:
    module = _load_module()
    report_root = tmp_path / "reports" / "backtest"
    _write_review(report_root)

    html = module.build_web_report(report_root=report_root).read_text(encoding="utf-8")

    assert "审查结论" in html
    assert "需要继续修正" in html
    assert "fixtures" in html


@pytest.mark.unit
def test_backtest_web_report_default_output_path_is_reports_backtest(tmp_path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.chdir(tmp_path)
    report_root = tmp_path / "reports" / "backtest"
    _write_review(report_root)

    output = module.build_web_report()

    assert output == Path("reports/backtest/index.html")
    assert (tmp_path / output).exists()
