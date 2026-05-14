"""单元测试：fee_model。"""
from __future__ import annotations

import pytest

from execution import fee_model


@pytest.mark.unit
def test_commission_uses_min_when_amount_small() -> None:
    cfg = fee_model.FeeConfig(commission_rate=1e-4, min_commission=5.0)
    cost = fee_model.calculate_cost(
        amount=1000.0, side="buy", stamp_tax_applicable=False, exchange="SH", config=cfg
    )
    assert cost.commission == 5.0


@pytest.mark.unit
def test_commission_uses_rate_when_amount_large() -> None:
    cfg = fee_model.FeeConfig(commission_rate=1e-4, min_commission=5.0)
    cost = fee_model.calculate_cost(
        amount=1_000_000.0,
        side="buy",
        stamp_tax_applicable=False,
        exchange="SH",
        config=cfg,
    )
    assert cost.commission == pytest.approx(100.0)


@pytest.mark.unit
def test_etf_sell_no_stamp_tax() -> None:
    """关键断言：ETF 卖出印花税 = 0（CLAUDE.md §3）。"""
    cfg = fee_model.FeeConfig()
    cost = fee_model.calculate_cost(
        amount=100_000.0,
        side="sell",
        stamp_tax_applicable=False,
        exchange="SH",
        config=cfg,
    )
    assert cost.stamp_tax == 0.0


@pytest.mark.unit
def test_stock_sell_stamp_tax_collected() -> None:
    cfg = fee_model.FeeConfig(stamp_tax_rate=0.0005)
    cost = fee_model.calculate_cost(
        amount=100_000.0,
        side="sell",
        stamp_tax_applicable=True,
        exchange="SH",
        config=cfg,
    )
    assert cost.stamp_tax == pytest.approx(50.0)


@pytest.mark.unit
def test_stock_buy_no_stamp_tax() -> None:
    cfg = fee_model.FeeConfig(stamp_tax_rate=0.0005)
    cost = fee_model.calculate_cost(
        amount=100_000.0,
        side="buy",
        stamp_tax_applicable=True,
        exchange="SH",
        config=cfg,
    )
    assert cost.stamp_tax == 0.0


@pytest.mark.unit
def test_total_is_sum_of_parts() -> None:
    cfg = fee_model.FeeConfig()
    cost = fee_model.calculate_cost(
        amount=200_000.0,
        side="sell",
        stamp_tax_applicable=True,
        exchange="SH",
        config=cfg,
    )
    assert cost.total == pytest.approx(cost.commission + cost.stamp_tax + cost.transfer_fee)
