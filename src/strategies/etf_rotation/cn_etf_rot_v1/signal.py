"""cn_etf_rot_v1 信号生成。

输入：PIT 行情 + 主数据 + 参数。
输出：当期目标权重表 `DataFrame[symbol, asof_date, target_weight, score, ...]`。

约束（CLAUDE.md §3）：
- 严禁直接 import `backtest.market_rules_cn`；交易规则一律走 `execution.tradeability`；
- 所有数据访问通过 `asof_date`；不得读取未来字段。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from factors import liquidity, momentum, volatility


SIGNAL_COLUMNS = [
    "symbol",
    "asof_date",
    "target_weight",
    "score",
    "mom_20",
    "mom_60",
    "mom_120",
    "vol_20",
    "adv_60",
    "trend_pass",
    "etf_type",
]


@dataclass(frozen=True)
class SignalParams:
    top_n: int = 3
    rebalance_freq: str = "W-FRI"
    mom_windows: tuple[int, int, int] = (20, 60, 120)
    mom_weights: tuple[float, float, float] = (0.2, 0.3, 0.5)
    vol_window: int = 20
    trend_ma_window: int = 200
    adv_window: int = 60
    adv_threshold_yuan: float = 5e7
    single_weight_cap: float = 0.40
    stock_type_cap: float = 1.00
    sector_type_cap: float = 0.50
    cross_border_type_cap: float = 0.30
    commodity_type_cap: float = 0.20
    weight_method: str = "equal"
    zscore_clip_sigma: float = 3.0
    n_capacity_pct: float = 0.05
    dd_halt_threshold: float = 0.15
    min_history_days: int = 252

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SignalParams":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            top_n=int(data.get("top_n", 3)),
            rebalance_freq=str(data.get("rebalance_freq", "W-FRI")),
            mom_windows=tuple(data.get("mom_windows", (20, 60, 120))),  # type: ignore[arg-type]
            mom_weights=tuple(data.get("mom_weights", (0.2, 0.3, 0.5))),  # type: ignore[arg-type]
            vol_window=int(data.get("vol_window", 20)),
            trend_ma_window=int(data.get("trend_ma_window", 200)),
            adv_window=int(data.get("adv_window", 60)),
            adv_threshold_yuan=float(data.get("adv_threshold_yuan", 5e7)),
            single_weight_cap=float(data.get("single_weight_cap", 0.40)),
            stock_type_cap=float(data.get("stock_type_cap", 1.00)),
            sector_type_cap=float(data.get("sector_type_cap", 0.50)),
            cross_border_type_cap=float(data.get("cross_border_type_cap", 0.30)),
            commodity_type_cap=float(data.get("commodity_type_cap", 0.20)),
            weight_method=str(data.get("weight_method", "equal")),
            zscore_clip_sigma=float(data.get("zscore_clip_sigma", 3.0)),
            n_capacity_pct=float(data.get("n_capacity_pct", 0.05)),
            dd_halt_threshold=float(data.get("dd_halt_threshold", 0.15)),
            min_history_days=int(data.get("min_history_days", 252)),
        )


def _filter_universe(
    asof_date: date,
    prices: pd.DataFrame,
    master: pd.DataFrame,
    params: SignalParams,
) -> pd.DataFrame:
    """入池准则：上市满 min_history_days、未退市、master 已收录。"""
    rows = []
    for _, row in master.iterrows():
        if row["list_date"] is None:
            continue
        if row["list_date"] > asof_date:
            continue
        if row["delist_date"] is not None and row["delist_date"] <= asof_date:
            continue
        if row["etf_type"] == "money_market":
            # 货币 ETF 仅作现金替代，不参与排序
            continue
        sym = row["symbol"]
        psub = prices[(prices["symbol"] == sym) & (~prices["is_suspended"].astype(bool))]
        psub = psub[psub["trade_date"] <= asof_date]
        if len(psub) < params.min_history_days:
            continue
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=master.columns)
    return pd.DataFrame(rows).reset_index(drop=True)


def _clip_zscore(s: pd.Series, n_sigma: float) -> pd.Series:
    if s.empty:
        return s
    mu = s.mean()
    sd = s.std(ddof=0)
    if sd == 0 or not np.isfinite(sd):
        return s * 0.0
    clipped = s.clip(mu - n_sigma * sd, mu + n_sigma * sd)
    mu2 = clipped.mean()
    sd2 = clipped.std(ddof=0)
    if sd2 == 0 or not np.isfinite(sd2):
        return clipped * 0.0
    return (clipped - mu2) / sd2


def _apply_weight_caps(top: pd.DataFrame, params: SignalParams) -> pd.DataFrame:
    """应用单标的与类型上限；被裁掉的权重保留为现金。"""
    if top.empty:
        return top

    out = top.copy()
    out["target_weight"] = out["target_weight"].astype(float).clip(
        lower=0.0, upper=params.single_weight_cap
    )

    def _scale(mask: pd.Series, cap: float) -> None:
        total = float(out.loc[mask, "target_weight"].sum())
        if total > cap and total > 0:
            out.loc[mask, "target_weight"] *= cap / total

    _scale(out["etf_type"].isin(["broad_index", "sector"]), params.stock_type_cap)
    _scale(out["etf_type"] == "sector", params.sector_type_cap)
    _scale(out["etf_type"] == "cross_border", params.cross_border_type_cap)
    _scale(out["etf_type"].isin(["gold"]), params.commodity_type_cap)

    return out


def generate_signal(
    asof_date: date,
    prices: pd.DataFrame,
    master: pd.DataFrame,
    params: SignalParams,
) -> pd.DataFrame:
    """生成 asof_date 当期的目标权重。返回为空表示空仓。"""
    # 1. PIT 截断（安全网）
    pit = prices[prices["trade_date"] <= asof_date]
    if pit.empty:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)

    # 2. 入池
    eligible = _filter_universe(asof_date, pit, master, params)
    if eligible.empty:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)
    pit_e = pit[pit["symbol"].isin(eligible["symbol"])]

    # 3. 因子计算（每个因子接 asof_date，严格 PIT）
    w20, w60, w120 = params.mom_windows
    mom20 = momentum.momentum(pit_e, asof_date, w20).rename(columns={"value": "mom_20"})
    mom60 = momentum.momentum(pit_e, asof_date, w60).rename(columns={"value": "mom_60"})
    mom120 = momentum.momentum(pit_e, asof_date, w120).rename(columns={"value": "mom_120"})
    vol20 = volatility.realized_vol(pit_e, asof_date, params.vol_window).rename(
        columns={"value": "vol_20"}
    )
    adv60 = liquidity.adv(pit_e, asof_date, params.adv_window).rename(columns={"value": "adv_60"})
    trend = momentum.trend_pass(pit_e, asof_date, params.trend_ma_window).rename(
        columns={"value": "trend_pass"}
    )

    def _pick(df: pd.DataFrame, col: str) -> pd.DataFrame:
        return df[["symbol", col]]

    merged = (
        eligible[["symbol", "etf_type"]]
        .merge(_pick(mom20, "mom_20"), on="symbol", how="left")
        .merge(_pick(mom60, "mom_60"), on="symbol", how="left")
        .merge(_pick(mom120, "mom_120"), on="symbol", how="left")
        .merge(_pick(vol20, "vol_20"), on="symbol", how="left")
        .merge(_pick(adv60, "adv_60"), on="symbol", how="left")
        .merge(_pick(trend, "trend_pass"), on="symbol", how="left")
    )

    merged = merged.dropna(subset=["mom_20", "mom_60", "mom_120"])
    if merged.empty:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)

    # 4. 趋势 + 流动性过滤
    merged = merged[merged["trend_pass"].astype(bool)]
    merged = merged[merged["adv_60"] >= params.adv_threshold_yuan]
    if merged.empty:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)

    # 5. 综合得分（横截面 z-score，3σ 裁剪）
    z20 = _clip_zscore(merged["mom_20"], params.zscore_clip_sigma)
    z60 = _clip_zscore(merged["mom_60"], params.zscore_clip_sigma)
    z120 = _clip_zscore(merged["mom_120"], params.zscore_clip_sigma)
    ww20, ww60, ww120 = params.mom_weights
    merged = merged.assign(score=(ww20 * z20 + ww60 * z60 + ww120 * z120))

    # 6. Top-N 选择
    merged = merged.sort_values(["score", "symbol"], ascending=[False, True]).reset_index(drop=True)
    top = merged.head(params.top_n).copy()

    # 7. 权重
    if params.weight_method == "inverse_vol" and (top["vol_20"] > 0).all():
        inv = 1.0 / top["vol_20"].clip(lower=1e-9)
        weights = inv / inv.sum()
    else:
        weights = pd.Series([1.0 / len(top)] * len(top), index=top.index)

    top["target_weight"] = weights.values
    top = _apply_weight_caps(top, params)
    top["asof_date"] = asof_date

    return top[SIGNAL_COLUMNS].reset_index(drop=True)
