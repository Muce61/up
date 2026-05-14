"""强制白名单 #5：基本面字段必须按 announcement_date 入模；Phase 1 不消费财务字段，
故策略不应能加载 Phase 2 因子（已加 Phase 2 锁）。
"""
from __future__ import annotations

import pytest


@pytest.mark.lookahead
def test_phase2_value_factor_locked() -> None:
    with pytest.raises((ImportError, NotImplementedError)):
        from factors import value  # noqa: F401


@pytest.mark.lookahead
def test_phase2_quality_factor_locked() -> None:
    with pytest.raises((ImportError, NotImplementedError)):
        from factors import quality  # noqa: F401


@pytest.mark.lookahead
def test_phase2_event_features_locked() -> None:
    with pytest.raises((ImportError, NotImplementedError)):
        from factors import event_features  # noqa: F401


@pytest.mark.lookahead
def test_phase2_growth_locked() -> None:
    with pytest.raises((ImportError, NotImplementedError)):
        from factors import growth  # noqa: F401


@pytest.mark.lookahead
def test_phase2_dividend_locked() -> None:
    with pytest.raises((ImportError, NotImplementedError)):
        from factors import dividend  # noqa: F401
