"""共享 fixture + sys.path 兜底（在未 pip install -e 时也能 import）。"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 确保 src/ 在 PYTHONPATH 上
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

REPO_ROOT = _PROJECT_ROOT


# ---------------------------------------------------------------------------
# 合成行情 fixture
# ---------------------------------------------------------------------------

def _bdate_range(start: date, n: int) -> list[date]:
    out: list[date] = []
    cur = start
    while len(out) < n:
        if cur.weekday() < 5:  # 周一到周五
            out.append(cur)
        cur = cur + timedelta(days=1)
    return out


def _synth_prices(
    symbol: str,
    dates: list[date],
    base: float = 100.0,
    daily_drift: float = 0.0004,
    daily_vol: float = 0.012,
    seed: int = 42,
    is_suspended_mask: list[bool] | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(dates)
    rets = rng.normal(daily_drift, daily_vol, n)
    rets[0] = 0.0
    closes = base * np.exp(np.cumsum(rets))
    opens = closes * (1.0 + rng.normal(0.0, 0.002, n))
    highs = np.maximum(closes, opens) * (1.0 + np.abs(rng.normal(0.0, 0.003, n)))
    lows = np.minimum(closes, opens) * (1.0 - np.abs(rng.normal(0.0, 0.003, n)))
    prev_close = np.concatenate([[base], closes[:-1]])
    limit_up = prev_close * 1.10
    limit_down = prev_close * 0.90
    amount = closes * rng.integers(1_000_000, 10_000_000, n)
    volume = rng.integers(100_000, 1_000_000, n)
    suspended = is_suspended_mask if is_suspended_mask is not None else [False] * n
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trade_date": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "adj_factor": 1.0,
            "volume": volume,
            "amount": amount,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "is_suspended": suspended,
        }
    )


@pytest.fixture(scope="session")
def calendar_dates() -> list[date]:
    return _bdate_range(date(2022, 1, 3), 500)


@pytest.fixture(scope="session")
def calendar_df(calendar_dates) -> pd.DataFrame:
    n = len(calendar_dates)
    prev = [None] + list(calendar_dates[:-1])
    nxt = list(calendar_dates[1:]) + [None]
    return pd.DataFrame(
        {
            "trade_date": calendar_dates,
            "is_open": [True] * n,
            "prev_trade_date": prev,
            "next_trade_date": nxt,
        }
    )


@pytest.fixture(scope="session")
def master_df() -> pd.DataFrame:
    """5 个 ETF，混合 T+1 / T+0。"""
    return pd.DataFrame(
        [
            {
                "symbol": "ETFA.SH",
                "name": "A 宽基",
                "etf_type": "broad_index",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2018, 1, 2),
                "delist_date": None,
                "exchange": "SH",
            },
            {
                "symbol": "ETFB.SH",
                "name": "B 行业",
                "etf_type": "sector",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2018, 1, 2),
                "delist_date": None,
                "exchange": "SH",
            },
            {
                "symbol": "ETFC.SZ",
                "name": "C 行业",
                "etf_type": "sector",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2018, 1, 2),
                "delist_date": None,
                "exchange": "SZ",
            },
            {
                "symbol": "ETFD.SH",
                "name": "D 黄金",
                "etf_type": "gold",
                "settlement": "T+0",
                "stamp_tax_applicable": False,
                "list_date": date(2018, 1, 2),
                "delist_date": None,
                "exchange": "SH",
            },
            {
                "symbol": "ETFE.SH",
                "name": "E 已退市",
                "etf_type": "broad_index",
                "settlement": "T+1",
                "stamp_tax_applicable": False,
                "list_date": date(2018, 1, 2),
                "delist_date": date(2023, 6, 30),
                "exchange": "SH",
            },
        ]
    )


@pytest.fixture(scope="session")
def prices_df(calendar_dates, master_df) -> pd.DataFrame:
    """每个 symbol 一段合成行情。给不同 ETF 不同 drift 制造横截面差异。"""
    drifts = {
        "ETFA.SH": 0.0010,
        "ETFB.SH": 0.0006,
        "ETFC.SZ": 0.0002,
        "ETFD.SH": 0.0001,
        "ETFE.SH": -0.0003,
    }
    seeds = {sym: 10 + i for i, sym in enumerate(drifts.keys())}
    parts = []
    for _, row in master_df.iterrows():
        sym = row["symbol"]
        # 退市股票只到 delist_date - 1
        dates = list(calendar_dates)
        if row["delist_date"] is not None:
            dates = [d for d in dates if d < row["delist_date"]]
        df = _synth_prices(
            sym,
            dates,
            base=100.0,
            daily_drift=drifts[sym],
            daily_vol=0.012,
            seed=seeds[sym],
        )
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


@pytest.fixture(scope="session")
def signal_params():
    """缩小窗口的策略参数，便于在 500-日 fixtures 内测试。"""
    from strategies.etf_rotation.cn_etf_rot_v1.signal import SignalParams

    return SignalParams(
        top_n=2,
        mom_windows=(5, 10, 20),
        mom_weights=(0.2, 0.3, 0.5),
        vol_window=10,
        trend_ma_window=60,
        adv_window=20,
        adv_threshold_yuan=1e6,
        single_weight_cap=0.6,
        weight_method="equal",
        zscore_clip_sigma=3.0,
        min_history_days=120,
    )
