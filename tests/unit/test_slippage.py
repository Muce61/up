"""单元测试：保守滑点模型。"""
from __future__ import annotations

import pytest

from execution import slippage


@pytest.mark.unit
def test_estimate_slippage_uses_base_bps_when_no_market_inputs() -> None:
    cfg = slippage.SlippageConfig(base_bps=5.0)

    out = slippage.estimate_slippage_bps(order_amount=10_000.0, config=cfg)

    assert out == pytest.approx(5.0)


@pytest.mark.unit
def test_apply_slippage_moves_buy_price_up_and_sell_price_down() -> None:
    assert slippage.apply_slippage("buy", base_price=100.0, slippage_bps=10.0) == pytest.approx(
        100.10
    )
    assert slippage.apply_slippage(
        "sell", base_price=100.0, slippage_bps=10.0
    ) == pytest.approx(99.90)


@pytest.mark.unit
def test_estimate_slippage_increases_with_atr_pct() -> None:
    cfg = slippage.SlippageConfig(base_bps=5.0, atr_multiplier=0.10)

    calm = slippage.estimate_slippage_bps(order_amount=10_000.0, atr_pct=0.01, config=cfg)
    volatile = slippage.estimate_slippage_bps(order_amount=10_000.0, atr_pct=0.03, config=cfg)

    assert volatile > calm
    assert calm == pytest.approx(15.0)
    assert volatile == pytest.approx(35.0)


@pytest.mark.unit
def test_estimate_slippage_increases_with_adv_participation() -> None:
    cfg = slippage.SlippageConfig(base_bps=5.0, participation_bps_per_1pct_adv=1.0)

    small = slippage.estimate_slippage_bps(
        order_amount=10_000.0, adv_amount=1_000_000.0, config=cfg
    )
    large = slippage.estimate_slippage_bps(
        order_amount=50_000.0, adv_amount=1_000_000.0, config=cfg
    )

    assert large > small
    assert small == pytest.approx(6.0)
    assert large == pytest.approx(10.0)


@pytest.mark.unit
def test_estimate_slippage_is_capped() -> None:
    cfg = slippage.SlippageConfig(base_bps=5.0, max_bps=25.0)

    out = slippage.estimate_slippage_bps(
        order_amount=1_000_000.0,
        adv_amount=10_000.0,
        atr_pct=0.20,
        config=cfg,
    )

    assert out == pytest.approx(25.0)


@pytest.mark.unit
def test_execution_price_is_deterministic() -> None:
    cfg = slippage.SlippageConfig(base_bps=5.0)

    p1 = slippage.execution_price(
        side="buy",
        base_price=100.0,
        order_amount=10_000.0,
        adv_amount=1_000_000.0,
        atr_pct=0.02,
        config=cfg,
    )
    p2 = slippage.execution_price(
        side="buy",
        base_price=100.0,
        order_amount=10_000.0,
        adv_amount=1_000_000.0,
        atr_pct=0.02,
        config=cfg,
    )

    assert p1 == pytest.approx(p2)
