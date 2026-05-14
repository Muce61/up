"""强制白名单 #1：涨停时买单被拒。"""
from __future__ import annotations

import pytest

from execution import tradeability


@pytest.mark.rule_simulation
def test_limit_up_buy_blocked() -> None:
    res = tradeability.is_tradeable(
        side="buy",
        price=110.0,
        limit_up=110.0,
        limit_down=90.0,
        is_suspended=False,
        is_delisted=False,
    )
    assert res.is_ok is False
    assert res.reason == "limit_up"


@pytest.mark.rule_simulation
def test_buy_just_below_limit_up_ok() -> None:
    res = tradeability.is_tradeable(
        side="buy",
        price=109.9,
        limit_up=110.0,
        limit_down=90.0,
        is_suspended=False,
        is_delisted=False,
    )
    assert res.is_ok is True
