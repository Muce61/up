"""单元测试：cn_etf_rot_v1 signal。"""
from __future__ import annotations

import pytest

import pandas as pd

from strategies.etf_rotation.cn_etf_rot_v1.signal import (
    SIGNAL_COLUMNS,
    SignalParams,
    _apply_weight_caps,
    generate_signal,
)


@pytest.mark.unit
def test_signal_returns_top_n_or_fewer(prices_df, master_df, signal_params, calendar_dates) -> None:
    asof = calendar_dates[-1]
    out = generate_signal(asof, prices_df, master_df, signal_params)
    assert len(out) <= signal_params.top_n
    assert set(SIGNAL_COLUMNS).issubset(out.columns)


@pytest.mark.unit
def test_signal_weights_sum_to_one_or_zero(prices_df, master_df, signal_params, calendar_dates) -> None:
    asof = calendar_dates[-1]
    out = generate_signal(asof, prices_df, master_df, signal_params)
    if not out.empty:
        assert out["target_weight"].sum() <= 1.0 + 1e-6


@pytest.mark.unit
def test_signal_only_trend_pass_assets(prices_df, master_df, signal_params, calendar_dates) -> None:
    asof = calendar_dates[-1]
    out = generate_signal(asof, prices_df, master_df, signal_params)
    if not out.empty:
        assert out["trend_pass"].all()


@pytest.mark.unit
def test_signal_only_liquid_assets(prices_df, master_df, signal_params, calendar_dates) -> None:
    asof = calendar_dates[-1]
    out = generate_signal(asof, prices_df, master_df, signal_params)
    if not out.empty:
        assert (out["adv_60"] >= signal_params.adv_threshold_yuan).all()


@pytest.mark.unit
def test_signal_excludes_money_market(prices_df, master_df, signal_params, calendar_dates) -> None:
    """货币 ETF 只作现金替代，不参与排序。fixture 中无货币 ETF，但断言路径存在。"""
    asof = calendar_dates[-1]
    out = generate_signal(asof, prices_df, master_df, signal_params)
    if not out.empty:
        assert (out["etf_type"] != "money_market").all()


@pytest.mark.unit
def test_signal_excludes_delisted_at_asof(prices_df, master_df, signal_params, calendar_dates) -> None:
    """退市 ETFE.SH（2023-06-30）在 asof_date 之后不应进入信号。"""
    asof = calendar_dates[-1]
    out = generate_signal(asof, prices_df, master_df, signal_params)
    if not out.empty:
        assert "ETFE.SH" not in out["symbol"].values


@pytest.mark.unit
def test_single_weight_cap_leaves_cash_when_binding() -> None:
    top = pd.DataFrame(
        {
            "symbol": ["A.SH", "B.SH"],
            "target_weight": [0.5, 0.5],
            "etf_type": ["broad_index", "broad_index"],
        }
    )
    params = SignalParams(top_n=2, single_weight_cap=0.4)

    capped = _apply_weight_caps(top, params)

    assert capped["target_weight"].max() <= 0.4
    assert capped["target_weight"].sum() == pytest.approx(0.8)


@pytest.mark.unit
def test_type_caps_enforced() -> None:
    top = pd.DataFrame(
        {
            "symbol": ["A.SH", "B.SH", "C.SH"],
            "target_weight": [1 / 3, 1 / 3, 1 / 3],
            "etf_type": ["sector", "sector", "gold"],
        }
    )
    params = SignalParams(top_n=3, sector_type_cap=0.5, commodity_type_cap=0.2)

    capped = _apply_weight_caps(top, params)

    sector_weight = capped.loc[capped["etf_type"] == "sector", "target_weight"].sum()
    gold_weight = capped.loc[capped["etf_type"] == "gold", "target_weight"].sum()
    assert sector_weight == pytest.approx(0.5)
    assert gold_weight == pytest.approx(0.2)
    assert capped["target_weight"].sum() == pytest.approx(0.7)
