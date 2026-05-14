"""单元测试：ADV 容量约束。"""
from __future__ import annotations

import pytest

from portfolio import capacity


@pytest.mark.unit
def test_max_trade_amount_is_adv_times_capacity_pct() -> None:
    out = capacity.max_trade_amount(adv_amount=1_000_000.0, capacity_pct=0.05)

    assert out == pytest.approx(50_000.0)


@pytest.mark.unit
def test_cap_order_amount_leaves_small_order_unchanged() -> None:
    result = capacity.cap_order_amount(
        requested_amount=40_000.0,
        adv_amount=1_000_000.0,
        capacity_pct=0.05,
    )

    assert result.allowed_amount == pytest.approx(40_000.0)
    assert result.max_amount == pytest.approx(50_000.0)
    assert result.scale == pytest.approx(1.0)
    assert result.is_capped is False
    assert result.reason is None


@pytest.mark.unit
def test_cap_order_amount_caps_large_order() -> None:
    result = capacity.cap_order_amount(
        requested_amount=100_000.0,
        adv_amount=1_000_000.0,
        capacity_pct=0.05,
    )

    assert result.allowed_amount == pytest.approx(50_000.0)
    assert result.max_amount == pytest.approx(50_000.0)
    assert result.scale == pytest.approx(0.5)
    assert result.is_capped is True
    assert result.reason == "capacity_capped"


@pytest.mark.unit
def test_cap_order_amount_zero_adv_rejects_conservatively() -> None:
    result = capacity.cap_order_amount(
        requested_amount=100_000.0,
        adv_amount=0.0,
        capacity_pct=0.05,
    )

    assert result.allowed_amount == 0.0
    assert result.scale == 0.0
    assert result.is_capped is True
    assert result.reason == "capacity_unavailable"


@pytest.mark.unit
def test_cap_order_amount_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        capacity.cap_order_amount(
            requested_amount=-1.0,
            adv_amount=1_000_000.0,
            capacity_pct=0.05,
        )
    with pytest.raises(ValueError):
        capacity.cap_order_amount(
            requested_amount=1.0,
            adv_amount=1_000_000.0,
            capacity_pct=-0.01,
        )
