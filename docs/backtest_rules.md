# 回测细则

> 上游：`CLAUDE.md §3 回测硬约束（A 股）`。本文件是对 §3 的实现级展开。
> 与 `CLAUDE.md` 冲突时，**以 `CLAUDE.md` 为准**。

---

## 一、唯一定义点 / 唯一访问入口

- **唯一定义点**：`src/backtest/market_rules_cn.py` 定义所有 A 股交易制度。
- **唯一访问入口**：`src/execution/tradeability.py` 是策略 / 因子 / 信号代码访问交易规则的**唯一**接口。
- 策略 / 因子 / 信号代码**禁止**自行判断 T+1、涨跌停、停牌；违反由 `tests/regression/test_no_bypass_tradeability.py` 拦截。

---

## 二、T+1 与品类差异

- 默认：A 股股票、股票 ETF = T+1。
- T+0 品类：债券 ETF、黄金 ETF、跨境 ETF、货币 ETF（按 `config/universe/cn_etf.yaml` 配置）。
- 实现：`settlement_lag(symbol) -> int`，返回 0 或 1。

---

## 三、涨跌幅档位

| 板块 | 默认涨跌幅 | 备注 |
|---|---|---|
| 沪深主板（非风险警示） | ±10% | |
| 创业板、科创板 | ±20% | |
| 风险警示（ST/*ST） | ±5% | 沪市拟 2026-07-06 切换为 ±10%；做成参数开关 |
| 退市整理期 | 首日不设涨跌幅；后续按板块 | 通常 15 个交易日 |

实现：`limit_band(symbol, trade_date) -> (up_pct, down_pct)`。

---

## 四、撮合可行性

`is_tradeable(symbol, trade_date, side) -> bool` 返回 false 的情形：

1. 标的停牌；
2. 退市整理期不接受新开仓（按业务规则）；
3. **买单**且收盘价 ≥ 涨停价（涨停**买不进**）；
4. **卖单**且收盘价 ≤ 跌停价（跌停**卖不出**）；
5. T+1 状态下当日新建多头仓位不可当日平仓。

---

## 五、成本模型

### 5.1 佣金
- 默认：成交金额 × `commission_rate`，最低 `min_commission` 元。
- 配置：`config/fees/commission.yaml`。

### 5.2 印花税
- A 股股票卖出收（现行 0.05%，可调）；
- ETF 默认**不**收，按品类配置在 `etf_master.stamp_tax_applicable`。

### 5.3 过户费
- 沪市按规则计入；其他按交易所规定；
- 配置：`config/fees/transfer_fee.yaml`。

### 5.4 滑点
- 默认保守模型：基于成交金额或 ATR；
- 公式见 `src/execution/slippage.py`；
- 激进模型仅在样本外做敏感性分析，**不**作为基线。

### 5.5 容量约束
- 单标的单日成交量上限 = `ADV(20) × N`，N 在 `config/risk_limits/capacity.yaml`；
- 超出按比例削权；**不**抬高滑点掩盖容量问题。

---

## 六、可复现

- 任何回测调用必须传入 `snapshot_version`；引擎在 manifest 记录。
- 同一 `(strategy_id, params, snapshot_version)` 两次运行 **byte-for-byte 一致**。
- 任何随机性（采样、扰动）固定 seed，seed 写入 manifest。

---

## 七、强制测试

7 条强制白名单（位置见 `tests/README.md §二`）必须全部通过，策略才允许进入报告层与模拟盘。

---

## 八、Walk-Forward 默认配置

- 滚动窗口：in-sample = 36 个月，out-of-sample = 12 个月；
- in-sample 调参，out-of-sample 评估，**绝不**在 OOS 上调参；
- 跨 fold 方向必须一致；不一致按"过拟合嫌疑"处理。

---

## 九、ETF 类型差异（必须分别测试）

| 类型 | 结算 | 印花税 | 流动性约束 | 测试覆盖 |
|---|---|---|---|---|
| 宽基股票 ETF | T+1 | 否（默认） | 中高 | 必须 |
| 行业 ETF | T+1 | 否 | 中 | 必须 |
| 债券 ETF | T+0 | 否 | 中 | 必须 |
| 黄金 ETF | T+0 | 否 | 中 | 必须 |
| 跨境 ETF | T+0 | 否 | 中低 | 必须 |
| 货币 ETF | T+0 | 否 | 高 | 选做 |

每类至少 1 条单元测试覆盖其结算行为与费用行为。

---

## 十、失效与停机

详见 `docs/strategy_archive.md §五 退役`。
