"""单元测试：容量约束边界场景。"""
from __future__ import annotations

import pytest

from portfolio import capacity


@pytest.mark.unit
def test_requested_amount_zero_is_not_capped() -> None:
    result = capacity.cap_order_amount(
        requested_amount=0.0,
        adv_amount=1_000_000.0,
        capacity_pct=0.05,
    )

    assert result.requested_amount == 0.0
    assert result.max_amount == pytest.approx(50_000.0)
    assert result.allowed_amount == 0.0
    assert result.scale == 0.0
    assert result.is_capped is False
    assert result.reason is None


@pytest.mark.unit
@pytest.mark.parametrize("adv_amount", [0.0, -1.0])
def test_adv_amount_non_positive_makes_capacity_unavailable(adv_amount: float) -> None:
    result = capacity.cap_order_amount(
        requested_amount=10_000.0,
        adv_amount=adv_amount,
        capacity_pct=0.05,
    )

    assert result.max_amount == 0.0
    assert result.allowed_amount == 0.0
    assert result.scale == 0.0
    assert result.is_capped is True
    assert result.reason == "capacity_unavailable"


@pytest.mark.unit
def test_capacity_pct_zero_makes_capacity_unavailable() -> None:
    result = capacity.cap_order_amount(
        requested_amount=10_000.0,
        adv_amount=1_000_000.0,
        capacity_pct=0.0,
    )

    assert result.max_amount == 0.0
    assert result.allowed_amount == 0.0
    assert result.scale == 0.0
    assert result.is_capped is True
    assert result.reason == "capacity_unavailable"


@pytest.mark.unit
def test_requested_amount_equal_to_limit_is_allowed() -> None:
    result = capacity.cap_order_amount(
        requested_amount=50_000.0,
        adv_amount=1_000_000.0,
        capacity_pct=0.05,
    )

    assert result.max_amount == pytest.approx(50_000.0)
    assert result.allowed_amount == pytest.approx(50_000.0)
    assert result.scale == pytest.approx(1.0)
    assert result.is_capped is False
    assert result.reason is None


@pytest.mark.unit
def test_requested_amount_below_limit_is_allowed() -> None:
    result = capacity.cap_order_amount(
        requested_amount=49_999.0,
        adv_amount=1_000_000.0,
        capacity_pct=0.05,
    )

    assert result.max_amount == pytest.approx(50_000.0)
    assert result.allowed_amount == pytest.approx(49_999.0)
    assert result.scale == pytest.approx(1.0)
    assert result.is_capped is False
    assert result.reason is None


@pytest.mark.unit
def test_requested_amount_above_limit_is_capped() -> None:
    result = capacity.cap_order_amount(
        requested_amount=80_000.0,
        adv_amount=1_000_000.0,
        capacity_pct=0.05,
    )

    assert result.max_amount == pytest.approx(50_000.0)
    assert result.allowed_amount == pytest.approx(50_000.0)
    assert result.scale == pytest.approx(0.625)
    assert result.is_capped is True
    assert result.reason == "capacity_capped"


@pytest.mark.unit
def test_capacity_pct_negative_raises() -> None:
    with pytest.raises(ValueError, match="capacity_pct must be non-negative"):
        capacity.cap_order_amount(
            requested_amount=10_000.0,
            adv_amount=1_000_000.0,
            capacity_pct=-0.01,
        )
