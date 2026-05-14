# cn_etf_rot_v1 — 策略卡片

> CLAUDE.md §4 强制 12 项交付物。本卡片是入口；详细规则见 `docs/phase1_etf_rotation_design.md`。

| # | 项 | 内容 |
|---|---|---|
| 1 | 策略假设 | A 股 ETF 中期动量（6–18 个月行业景气传导 + 申赎正反馈）。详 `design §1.1`。 |
| 2 | 适用市场 | A 股 ETF（宽基 + 行业 + 债券 + 黄金 + 跨境 + 货币），T+1 / T+0 按品类分组。 |
| 3 | 数据输入 | OHLCV + adj_factor + 成交额 + 涨跌停 + 停牌；字段见 `docs/data_contract.md §3`。 |
| 4 | 因子定义 | mom_{20,60,120} + vol_20 + max_dd_60 + adv_60 + trend_pass(200)。详 `design §4`。 |
| 5 | 参数表 | 见 `params.yaml`；搜索范围见 `design §11`。 |
| 6 | 交易规则 | 周末收盘生成信号，T+1 开盘成交，等权 top-N。详 `design §5–7`。 |
| 7 | 风控规则 | 单标 ≤ 40%；类型上限；回撤 > 15% 持仓 ×0.5。详 `design §9`。 |
| 8 | 回测结果 | 待实现后由 `src/reports/backtest_report.py` 自动生成。 |
| 9 | 样本外验证 | IS 2016–2022 / OOS 2023–2025。结果归档到 `reports/strategy_archive/`。 |
| 10 | walk-forward | 36 IS / 12 OOS 滚动；待 W9。 |
| 11 | 失败案例 | 归档到 `review/failure_cases/`；至少在 W12 评审前补 1 份。 |
| 12 | 是否进入模拟盘 | **否**（Phase 1 MVP，未进入模拟盘审批流程）。 |

## 不做

- 个股 / 高频 / 盘口 / 打板 / 实盘下单 / 做空 / 杠杆 / LLM 信号 / 美股（见 `design §12`）。
