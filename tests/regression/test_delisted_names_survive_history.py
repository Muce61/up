"""强制白名单 #6：退市样本必须保留在历史中，但在 asof_date 之后被剔除决策。"""
from __future__ import annotations

import pytest

from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal


@pytest.mark.regression
def test_delisted_etf_in_history(prices_df, master_df) -> None:
    """ETFE.SH 在 2023-06-30 退市；fixture 中其历史数据应仍存在。"""
    assert "ETFE.SH" in master_df["symbol"].values
    etf_e_master = master_df[master_df["symbol"] == "ETFE.SH"].iloc[0]
    assert etf_e_master["delist_date"] is not None
    # 历史价格应仍存在（直到退市前一日）
    etf_e_prices = prices_df[prices_df["symbol"] == "ETFE.SH"]
    assert len(etf_e_prices) > 0


@pytest.mark.regression
def test_delisted_not_in_signal_after_delist(
    prices_df, master_df, signal_params, calendar_dates
) -> None:
    """退市日之后，ETFE.SH 不能出现在信号目标里。"""
    # fixtures 中 ETFE.SH 在 2023-06-30 退市；calendar_dates[-1] 远晚于此
    asof = calendar_dates[-1]
    out = generate_signal(asof, prices_df, master_df, signal_params)
    if not out.empty:
        assert "ETFE.SH" not in out["symbol"].values
