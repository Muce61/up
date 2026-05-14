"""强制白名单 #7：test_no_future_prices_in_signal。

构造一份"未来价格被人为污染"的副本：把 asof 之后所有价格改成极端值。
信号在 asof_date 上的输出应**不**受影响。
"""
from __future__ import annotations

import pytest

from strategies.etf_rotation.cn_etf_rot_v1.signal import generate_signal


@pytest.mark.lookahead
def test_no_future_prices_in_signal(prices_df, master_df, signal_params, calendar_dates) -> None:
    asof = calendar_dates[200]
    out_clean = generate_signal(asof, prices_df, master_df, signal_params)

    # 污染未来：把 asof 之后所有 close 改成 1e9（信号若偷看就会大幅倾斜）
    polluted = prices_df.copy()
    mask = polluted["trade_date"] > asof
    polluted.loc[mask, "close"] = 1e9
    polluted.loc[mask, "open"] = 1e9
    polluted.loc[mask, "amount"] = 1e15
    out_polluted = generate_signal(asof, polluted, master_df, signal_params)

    out_clean = out_clean.sort_values("symbol").reset_index(drop=True)
    out_polluted = out_polluted.sort_values("symbol").reset_index(drop=True)
    assert list(out_clean["symbol"]) == list(out_polluted["symbol"])
    for v1, v2 in zip(out_clean["target_weight"], out_polluted["target_weight"]):
        assert v1 == pytest.approx(v2)
