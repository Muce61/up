"""强制白名单 #3：停牌时双向均不可成交。"""
from __future__ import annotations

import pytest

from execution import tradeability


@pytest.mark.rule_simulation
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_suspended_security_untradeable(side: str) -> None:
    res = tradeability.is_tradeable(
        side=side,  # type: ignore[arg-type]
        price=100.0,
        limit_up=110.0,
        limit_down=90.0,
        is_suspended=True,
        is_delisted=False,
    )
    assert res.is_ok is False
    assert res.reason == "suspended"


@pytest.mark.rule_simulation
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_delisted_security_untradeable(side: str) -> None:
    res = tradeability.is_tradeable(
        side=side,  # type: ignore[arg-type]
        price=100.0,
        limit_up=110.0,
        limit_down=90.0,
        is_suspended=False,
        is_delisted=True,
    )
    assert res.is_ok is False
    assert res.reason == "delisted"
