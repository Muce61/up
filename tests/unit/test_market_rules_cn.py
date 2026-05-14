"""单元测试：market_rules_cn 是唯一定义点。"""
from __future__ import annotations

import pytest

from backtest import market_rules_cn as rules


@pytest.mark.unit
def test_settlement_lag_broad_index_is_t_plus_one() -> None:
    assert rules.settlement_lag("broad_index") == 1


@pytest.mark.unit
def test_settlement_lag_sector_is_t_plus_one() -> None:
    assert rules.settlement_lag("sector") == 1


@pytest.mark.unit
def test_settlement_lag_bond_is_t_plus_zero() -> None:
    assert rules.settlement_lag("bond") == 0


@pytest.mark.unit
def test_settlement_lag_gold_is_t_plus_zero() -> None:
    assert rules.settlement_lag("gold") == 0


@pytest.mark.unit
def test_settlement_lag_cross_border_is_t_plus_zero() -> None:
    assert rules.settlement_lag("cross_border") == 0


@pytest.mark.unit
def test_settlement_lag_unknown_defaults_to_conservative_t1() -> None:
    assert rules.settlement_lag("unknown_type") == 1


@pytest.mark.unit
def test_close_at_limit_up_detected() -> None:
    assert rules.is_at_limit_up(110.0, 110.0)


@pytest.mark.unit
def test_close_just_below_limit_up_not_detected() -> None:
    assert not rules.is_at_limit_up(109.9, 110.0)


@pytest.mark.unit
def test_close_at_limit_down_detected() -> None:
    assert rules.is_at_limit_down(90.0, 90.0)


@pytest.mark.unit
def test_close_just_above_limit_down_not_detected() -> None:
    assert not rules.is_at_limit_down(90.1, 90.0)


@pytest.mark.unit
def test_stamp_tax_etf_not_applicable_returns_zero() -> None:
    assert rules.stamp_tax_rate(applicable=False, side="sell") == 0.0
    assert rules.stamp_tax_rate(applicable=False, side="buy") == 0.0


@pytest.mark.unit
def test_stamp_tax_stock_sell_collects() -> None:
    assert rules.stamp_tax_rate(applicable=True, side="sell") == pytest.approx(0.0005)


@pytest.mark.unit
def test_stamp_tax_stock_buy_no_stamp() -> None:
    assert rules.stamp_tax_rate(applicable=True, side="buy") == 0.0
