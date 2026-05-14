"""架构回归：交易制度只能经 execution.tradeability 访问。"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

CHECKED_FILES = [
    REPO_ROOT / "src" / "backtest" / "engine.py",
    REPO_ROOT / "src" / "execution" / "fee_model.py",
    REPO_ROOT / "src" / "strategies" / "etf_rotation" / "cn_etf_rot_v1" / "signal.py",
]


def _imports_market_rules(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "backtest.market_rules_cn":
                    return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "backtest" and any(alias.name == "market_rules_cn" for alias in node.names):
                return True
            if module == "backtest.market_rules_cn":
                return True
    return False


@pytest.mark.regression
@pytest.mark.parametrize("path", CHECKED_FILES)
def test_core_modules_do_not_import_market_rules_directly(path: Path) -> None:
    assert not _imports_market_rules(path), f"{path} must use execution.tradeability"
