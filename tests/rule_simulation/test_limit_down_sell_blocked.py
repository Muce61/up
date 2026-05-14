"""强制白名单 #2：跌停时卖单被拒。"""
from __future__ import annotations

import pytest

from execution import tradeability


@pytest.mark.rule_simulation
def test_limit_down_sell_blocked() -> None:
    res = tradeability.is_tradeable(
        side="sell",
        price=90.0,
        limit_up=110.0,
        limit_down=90.0,
        is_suspended=False,
        is_delisted=False,
    )
    assert res.is_ok is False
    assert res.reason == "limit_down"


@pytest.mark.rule_simulation
def test_sell_just_above_limit_down_ok() -> None:
    res = tradeability.is_tradeable(
        side="sell",
        price=90.1,
        limit_up=110.0,
        limit_down=90.0,
        is_suspended=False,
        is_delisted=False,
    )
    assert res.is_ok is True
