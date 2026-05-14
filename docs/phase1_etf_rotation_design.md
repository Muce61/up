# Phase 1 设计文档：A 股 ETF 轮动 MVP

> **状态**：草案，等待用户确认。**不**包含实现代码。
> **strategy_id**：`cn_etf_rot_v1`
> **上游**：`CLAUDE.md`（最高规则）、`docs/backtest_rules.md`、`docs/data_contract.md`、`docs/strategy_archive.md`。
> 任何与 `CLAUDE.md` 冲突的内容，以 `CLAUDE.md` 为准。

---

## 0. 元数据

| 项 | 值 |
|---|---|
| strategy_id | `cn_etf_rot_v1` |
| 阶段 | Phase 1（A 股 ETF/指数轮动） |
| 目录 | `src/strategies/etf_rotation/cn_etf_rot_v1/` |
| 调仓频率 | 周频（默认每周最后一个交易日收盘生成信号） |
| 资金方向 | long-only |
| 杠杆 | 无（默认 1×） |
| 做空 | **禁止** |
| 实盘 | **禁止**（Phase 1 不进入实盘，仅回测；模拟盘待 Phase 1 退出准则通过后另议） |

---

## 1. 策略目标

### 1.1 经济逻辑（策略假设）

A 股 ETF 市场存在**中期动量**：在一段时间内表现强的板块/宽基指数倾向于继续保持相对强势，弱者倾向于继续弱势。原因包括：

- 政策与景气的连续性（同一主线下的资金惯性）；
- 投资者关注度与申赎驱动的正反馈（ETF 申赎机制本身放大趋势）；
- 行业基本面变化具有 6–18 个月的传导周期。

动量并非永远有效，反转期和高波动期是其主要风险。因此本策略不追求"全市场任何时点都赚"，而是追求"在动量友好的环境下吃到主要收益，在不友好环境下控制损失"。

### 1.2 MVP 目标

本策略的 Phase 1 目标**不是**最大化收益，而是：

1. 跑通"数据 → 因子 → 信号 → 组合 → 回测 → 报告"全链路；
2. 满足 `CLAUDE.md §4` 的 12 项交付物；
3. 通过 7 条强制单元测试；
4. 在样本内 / 样本外 / walk-forward 三组中**方向一致**；
5. 击败"等权 ETF 池基准 + 同等成本"。

**任何一项不达成都不允许进入下一阶段，不允许通过调参强行达成。**

---

## 2. 资产池定义

### 2.1 入池准则

候选 ETF 必须**同时**满足：

- 在 A 股交易所（SH/SZ）上市；
- 上市满 **252 个交易日**（约 1 年），消除 IPO 期失真；
- 过去 **60 个交易日 ADV ≥ 5,000 万元**；
- 不处于退市整理期；
- 不在 ETF 黑名单（清算公告、流动性枯竭、跟踪标的争议）。

ETF 类型分组（影响 T+1/T+0、印花税）：

| 类型 | settlement | 印花税 | 数量上限（Phase 1） |
|---|---|---|---|
| 宽基股票 ETF | T+1 | 否 | 8 |
| 行业股票 ETF | T+1 | 否 | 8 |
| 债券 ETF | T+0 | 否 | 2 |
| 黄金 ETF | T+0 | 否 | 1 |
| 跨境 ETF | T+0 | 否 | 2 |
| 货币 ETF（仅作现金替代） | T+0 | 否 | 1 |

合计 ≤ 22 只；Phase 1 实际启用建议 12–15 只。

### 2.2 候选池（**示例 / 配置在 `config/universe/cn_etf.yaml`，不构成推荐**）

以下仅为构造检测用的示例代码池，最终列表在配置文件中维护，且每季度复核一次（剔除流动性退化、加入新满足条件的）。

| 类型 | 示例代码 | 名称 |
|---|---|---|
| 宽基 | 510300.SH / 510500.SH / 159949.SZ / 588000.SH / 510050.SH | 沪深 300 / 中证 500 / 创业板 50 / 科创 50 / 上证 50 |
| 行业 | 512170 / 512760 / 512660 / 515030 / 512000 / 512800 | 医疗 / 半导体 / 军工 / 新能源车 / 券商 / 银行（示例） |
| 债券 | 511010.SH / 511260.SH | 国债 / 十年国债 |
| 黄金 | 518880.SH | 黄金 |
| 跨境 | 513100.SH / 513500.SH | 纳指 / 标普 |
| 货币 | 511880.SH | 银华日利（现金替代） |

> 上述清单仅为字段口径与回测搭骨架使用；正式启用前由人工 review 一次，并写入 ADR。

### 2.3 池外样本

退市 / 停牌的 ETF **必须**保留在历史样本中（防幸存者偏差，`tests/regression/test_delisted_names_survive_history`）。仅在 `is_tradeable` / `is_delisted_at(asof_date)` 判断时被剔除当期决策。

---

## 3. 数据字段定义

字段定义遵循 `docs/data_contract.md`。本策略**消费**的最小字段集：

### 3.1 行情（`prices_daily`）

| 字段 | 类型 | 用途 |
|---|---|---|
| symbol | str | 标识 |
| trade_date | date | 时间索引 |
| open / high / low / close | float | OHLCV |
| adj_factor | float | 复权（前复权计算收益） |
| volume | int | 成交量（容量约束辅助） |
| amount | float | 成交额（ADV、流动性过滤） |
| limit_up | float | 撮合可行性判断 |
| limit_down | float | 撮合可行性判断 |
| is_suspended | bool | 撮合可行性判断 |
| effective_date | date | = trade_date（行情 T 日 ≤ T+0 收盘后可见，按收盘成交假设） |

### 3.2 主数据（`etf_master`）

| 字段 | 类型 | 用途 |
|---|---|---|
| symbol | str | 标识 |
| etf_type | enum | 决定 T+1/T+0、印花税 |
| settlement | enum | T+1 / T+0 |
| stamp_tax_applicable | bool | 默认 false |
| list_date | date | 入池年限校验 |
| delist_date | date \| null | 历史保留 |

### 3.3 交易日历（`trading_calendar`）

提供 `prev_trade_date` / `next_trade_date` 供调仓与 T+1 模拟。

### 3.4 不消费的字段

Phase 1 MVP **不**使用：财务字段、行业分类、公告事件、宏观指标、新闻文本。任何 Phase 2 字段如被本策略 import 即视为越权。

---

## 4. 因子定义

所有因子的函数签名必须为 `f(asof_date, snapshot_path, params) -> DataFrame[symbol, asof_date, effective_date, value]`，违反则 lookahead 测试失败。

### 4.1 动量因子（三个窗口）

| 名称 | 定义 | 默认窗口 |
|---|---|---|
| `mom_20d` | `close_t / close_{t-20} - 1`，用前复权价 | 20 |
| `mom_60d` | `close_t / close_{t-60} - 1` | 60 |
| `mom_120d` | `close_t / close_{t-120} - 1` | 120 |

窗口以**交易日**计，跨越停牌时不补齐（停牌日不计入窗口）。

### 4.2 波动率因子

`vol_20d` = 过去 20 个交易日**对数收益率**的样本标准差，年化（×√252）。

### 4.3 最大回撤因子

`max_dd_60d` = 过去 60 个交易日内 (peak - trough) / peak 的最大值；用前复权净值计算。

### 4.4 流动性 / 容量

`adv_60d` = 过去 60 个交易日成交额平均值；用于：
- 入池准则（≥ 5000 万元）；
- 容量约束（单日交易量上限 = ADV × N，N 默认 5%）。

### 4.5 趋势过滤

`trend_pass(symbol, asof_date)` = `close_t > sma_t(200)`；返回布尔值。
- `sma_t(200)` 用前复权收盘价 200 日简单平均。
- 趋势失败的 ETF 即使排名靠前也**不持有**。

### 4.6 综合得分

```
score = 0.5 × z(mom_120d) + 0.3 × z(mom_60d) + 0.2 × z(mom_20d)
```
其中 `z(·)` 是横截面 z-score（**当期池内**，剔除离群 3σ 后再计算）。

权重 (0.5/0.3/0.2) 是默认值；参数搜索范围见 §11。

---

## 5. 调仓逻辑

### 5.1 调仓时点

- 信号生成：**每周最后一个交易日收盘后**（一般是周五，遇节假日按交易日历）；
- 订单下发：**下一交易日开盘价成交**（保守假设，避免收盘前抢单）；
- 因此股票 ETF 的实际换仓在 **T+1 开盘**完成（满足 T+1 制度）；T+0 品种在 T+1 开盘成交，仍按统一流程，避免引擎逻辑分叉。

### 5.2 决策流程

1. 取最新 `asof_date` = 本周最后一个交易日；
2. 加载 `snapshot[asof_date]`；
3. 应用入池准则 → 当期可交易池 `Universe_t`；
4. 计算 `mom_*`, `vol_20d`, `max_dd_60d`, `trend_pass`；
5. 过滤：`trend_pass == True` 且 `adv_60d ≥ threshold`；
6. 计算 `score`，按降序排序；
7. 选 top `N`（默认 `N = 3`）作为目标持仓；
8. 计算目标权重（§7）；
9. 与当前持仓比较，生成订单（§6）；
10. 经 `execution/tradeability.py` 过滤不可成交订单；
11. 提交回测引擎在 `T+1` 开盘成交。

### 5.3 数据可见性

- 在 `t` 日只允许访问 `effective_date ≤ t` 的数据；
- 任何向 t+1 前瞻的操作 = lookahead bug，由 `tests/lookahead/*` 拦截。

---

## 6. 买入规则

### 6.1 触发条件

ETF 进入目标持仓集合（top N 且通过过滤）但当前未持有：生成**买入订单**。

### 6.2 订单参数

| 项 | 默认 |
|---|---|
| 订单类型 | 限价单（限价 = 下一交易日开盘价 + 滑点上界） |
| 成交假设 | 下一交易日开盘价成交（被涨停拒绝则失败保留为未成交） |
| 金额 | 目标权重 × 组合净值（详见 §7） |

### 6.3 不可成交处理

- **涨停**：买单被拒，记 `unfilled_reason = "limit_up"`，订单**不顺延**，等下一周调仓；
- **停牌**：买单被拒，记 `unfilled_reason = "suspended"`；
- **未达入池准则**：跳过；
- 任何被拒订单都记入 `trades.parquet` 的 `unfilled` 段，供 W11 执行偏差度量。

---

## 7. 卖出规则

### 7.1 触发条件（任一）

1. ETF 跌出 top `N`；
2. ETF 的 `trend_pass == False`（趋势失效，无视排名立即卖出）；
3. 流动性退池：`adv_60d < threshold`；
4. ETF 进入退市整理期或长期停牌；
5. 全组合触发风控停机（§9.3）。

### 7.2 订单参数

| 项 | 默认 |
|---|---|
| 订单类型 | 限价单（限价 = 下一交易日开盘价 - 滑点下界） |
| 成交假设 | 下一交易日开盘价成交（被跌停拒绝则失败保留为未成交） |
| 数量 | 全数清仓（Phase 1 不做部分减仓） |

### 7.3 T+1 约束

- 卖出仅对**至少持仓一日**的 ETF（T+1 股票 ETF），T+0 品种不受此限；
- 当周买入的 T+1 ETF**不**在同周卖出（不发生这种情况，因为调仓节点本就是周末）。

### 7.4 不可成交处理

跌停拒绝、停牌不可成交 → 当周保留持仓，下次再尝试卖出，并在 `trades.parquet` 标记。

---

## 8. 仓位规则

### 8.1 目标权重

默认 **等权**：
```
weight_i = 1 / N         for i in target_holdings
weight_cash = 1 - sum(weight_i)   # 通常 = 0
```

可选 **逆波动率加权**（参数 `weight_method = "inverse_vol"`）：
```
w_i ∝ 1 / vol_20d_i     再归一化，cap @ 单标的上限
```
Phase 1 默认等权；逆波动率作为可选实验，不作 baseline。

### 8.2 单标的上限

`single_weight_cap = 0.40`（默认 N=3 等权 ≈ 0.333，留容差）。

### 8.3 类型权重上限（防止过度集中于单一类型）

| 类型组 | 默认上限 |
|---|---|
| 全部股票 ETF（宽基 + 行业） | 1.00 |
| 单一行业 ETF（如同时持医药 + 半导体） | 总和 ≤ 0.50 |
| 跨境 ETF 总和 | 0.30 |
| 商品 ETF（黄金等）总和 | 0.20 |

### 8.4 现金 / 货币 ETF

当 top N 中通过过滤的 ETF 不足 N 个时：
- 剩余权重 → 货币 ETF（如池中有），否则保留现金；
- 不补足非过滤 ETF。

### 8.5 容量约束

单日交易量上限 = `adv_60d × N_capacity`（默认 `N_capacity = 0.05`）。
超出按比例削权，**不**抬高滑点掩盖容量问题（per `docs/backtest_rules.md §5.5`）。

---

## 9. 风控规则

### 9.1 组合层

| 项 | 默认 | 说明 |
|---|---|---|
| 最大回撤阈值 | 15% | 触发即"减半暴露"（见 9.3） |
| 目标波动率 | 不强制（Phase 1 MVP 简化） | Phase 2 候选 |
| 单标的权重上限 | 40% | §8.2 |
| 类型权重上限 | 见 §8.3 | |
| 最低现金 buffer | 1% | 应对成交不到位 |

### 9.2 单标的层

| 项 | 默认 |
|---|---|
| 跟踪止损 | 无（Phase 1 MVP，由趋势过滤天然替代） |
| 单日跌幅熔断 | 无（避免与趋势过滤双重作用） |
| 黑名单 | 是（人工维护，`config/risk_limits/blacklist.yaml`） |

### 9.3 停机规则

| 触发 | 动作 |
|---|---|
| 组合滚动 60 日最大回撤 > 15% | 持仓 × 0.5（一次性减半，等次周再评估） |
| 组合滚动 12 个月超额 < -5% 且 IS 期没出现过 | 暂停下单，进入审查（写 `review/failure_cases/`） |
| 7 条强制测试任一失败 | **立即**block 任何回测 / 报告产出 |

### 9.4 ETF 类型差异强约束

- 卖出股票 ETF 时**必须**满足 `settlement_lag` 约束（T+1）；
- 跨境 / 黄金 / 债券 ETF 按 T+0；
- 货币 ETF 不计入 risk asset，只作为现金替代。

---

## 10. 回测假设

### 10.1 时间范围

| 阶段 | 起 | 止 |
|---|---|---|
| in-sample | 2016-01-01 | 2022-12-31 |
| out-of-sample | 2023-01-01 | 2025-12-31 |
| walk-forward | 36 月 IS / 12 月 OOS 滚动 | 全期 |

如某 ETF 上市晚于 IS 起点，则其样本从上市后 252 日开始；不强行延伸。

### 10.2 基准

主基准：**沪深 300 全收益指数**。
对照基准：**池内 ETF 等权组合**（同费用、同 T+1）。

### 10.3 资金假设

| 项 | 默认 |
|---|---|
| 初始资金 | 1,000,000 元（名义，非真实） |
| 再投资 | 全额再投 |
| 借贷 | 无 |
| 杠杆 | 无 |

### 10.4 成本假设

| 项 | 默认 | 配置位置 |
|---|---|---|
| 佣金费率 | 0.015%（万 1.5） | `config/fees/default.yaml` |
| 最低佣金 | 5 元 | 同上 |
| 印花税 | ETF 不收 | `etf_master.stamp_tax_applicable` |
| 过户费 | 沪市按规则；深市无 | 同上 |
| 滑点 | 保守模型（ADV 比例 + ATR） | `src/execution/slippage.py` |

### 10.5 撮合假设

- 成交价 = 次日**开盘价** ± 滑点；
- 涨停时买单一律被拒；跌停时卖单一律被拒；
- 停牌不可交易；
- 容量约束按 §8.5；
- 全部经 `execution/tradeability.py`，策略代码不自行判断。

### 10.6 复现性

- 任何回测调用必须传入 `snapshot_version`；
- 同 `(strategy_id, params, snapshot_version)` 两次运行结果 byte-for-byte 一致；
- seed 写入 `manifest.json`。

---

## 11. 参数表

| 参数 | 默认 | 搜索范围（仅 in-sample） | 备注 |
|---|---|---|---|
| `top_n` | 3 | {2, 3, 4, 5} | 持仓个数 |
| `rebalance_freq` | "W-FRI" | {"W-FRI", "W-WED", "M-LAST"} | 调仓时点 |
| `mom_weights` | (0.5, 0.3, 0.2) | 三档（重长 / 均衡 / 重短） | 与 `mom_120/60/20` 一一对应 |
| `vol_window` | 20 | {20, 60} | 波动率窗口 |
| `trend_ma_window` | 200 | {120, 150, 200, 250} | 趋势过滤均线 |
| `adv_window` | 60 | {20, 60} | 流动性窗口 |
| `adv_threshold_yuan` | 5e7 | 三档 | 流动性下限 |
| `single_weight_cap` | 0.40 | {0.33, 0.40, 0.50} | 单标的上限 |
| `n_capacity_pct` | 0.05 | {0.02, 0.05, 0.10} | 容量约束比例 |
| `dd_halt_threshold` | 0.15 | {0.10, 0.15, 0.20} | 减半触发回撤 |
| `weight_method` | "equal" | {"equal", "inverse_vol"} | 权重方法 |

**参数搜索约束**：
- 仅在 in-sample 搜索；
- 用 walk-forward 跨 fold 一致性筛选；
- **禁止**在 OOS 上调参；
- 最终参数写入 `params.yaml` 并 hash 入 manifest。

---

## 12. 不支持的内容（显式排除）

| 不做 | 原因 |
|---|---|
| 个股 | Phase 1 范围外 |
| 高频 / 盘口 / 自动打板 | `CLAUDE.md §1` 严禁 |
| 日内 / 分钟级 | 同上 |
| 美股 | Phase 3 范围 |
| 做空 / 借券 | A 股 ETF 不开放 |
| 杠杆 / 期权 / 期货 | Phase 1 范围外 |
| 风险警示板个股 | 不交易 |
| 自动实盘下单 | `CLAUDE.md §6` 严禁 |
| AI / LLM 直接荐股或解读新闻 | 同上 |
| 主题 / 政策 overlay | `docs/research_questions.md §Q1.3` 未解决 |
| 容量市场冲击模型 | `docs/research_questions.md §Q5.2` 未解决 |
| Kelly 仓位 | `docs/research_questions.md §Q6.2` 未解决 |

---

## 13. 后续扩展点

按优先级递减：

1. **逆波动率加权 / 风险贡献等权**（小改）；
2. **波动率目标层**（在 §9.1 加目标波动率约束）；
3. **回撤分级减仓**（10% → 缩 70%, 15% → 缩 50%, 20% → 全清）；
4. **行业上限分组细化**（区分必选消费 / 周期 / 科技等）；
5. **regime overlay**（用沪深 300 200 日均线判牛熊，熊市切高比例现金/债券 ETF）；
6. **港股 ETF / 跨境 ETF 比例提升**（合规审查后）；
7. → 进入 **Phase 2 行业轮动**（不再属于本策略）。

每一项扩展前需独立 ADR，且 Phase 1 退出准则全部通过。

---

## 14. 必须新增的测试用例

### 14.1 强制单元测试（CLAUDE.md §5 白名单）

| # | 测试 | 位置 | 在本策略中的具体场景 |
|---|---|---|---|
| 1 | `test_limit_up_buy_blocked` | rule_simulation | 假设候选 ETF 次日开盘涨停 → 买单被拒，不顺延 |
| 2 | `test_limit_down_sell_blocked` | rule_simulation | 持仓 ETF 次日开盘跌停 → 卖单被拒，本周持仓不变 |
| 3 | `test_suspended_security_untradeable` | rule_simulation | 调仓日 ETF 停牌 → 不可买入；持仓 ETF 停牌 → 不可卖出 |
| 4 | `test_cn_stock_t_plus_one` | rule_simulation | 股票 ETF 当周买入次周才能卖出；T+0 品种允许同日来回 |
| 5 | `test_fundamental_release_lag_enforced` | lookahead | 本策略不消费基本面字段；测试断言 import 这些字段会失败 |
| 6 | `test_delisted_names_survive_history` | regression | 历史样本包含退市 ETF；回测器仅按 `effective_date` 剔除当期 |
| 7 | `test_no_future_prices_in_signal` | lookahead | 在 `asof_date` 不可访问 `> asof_date` 的任何价格 |

### 14.2 策略级新增测试

| 测试 | 位置 | 验证 |
|---|---|---|
| `test_universe_eligibility_rules` | unit | 入池准则正确（上市时长、ADV、退市状态） |
| `test_universe_type_caps_enforced` | unit | 类型权重上限不被突破 |
| `test_momentum_lookahead_truncation` | lookahead | `mom_*` 截断未来后输出不变 |
| `test_vol_lookahead_truncation` | lookahead | `vol_20d` 同上 |
| `test_max_dd_lookahead_truncation` | lookahead | `max_dd_60d` 同上 |
| `test_trend_filter_blocks_holding` | unit | `trend_pass == False` 时即使排名靠前也不买；持仓中触发即卖 |
| `test_liquidity_filter_excludes_low_adv` | unit | `adv_60d < threshold` 时 ETF 不参与排序 |
| `test_weekly_rebalance_schedule` | unit | 信号在周最后一个交易日生成，订单 T+1 开盘成交 |
| `test_top_n_selection_consistency` | unit | top-N 截断按 score 降序、tie-breaking 稳定 |
| `test_equal_weight_sums_to_one` | unit | 等权权重和为 1（或剩余给现金 / 货币 ETF） |
| `test_capacity_cap_pro_rata_scale` | unit | 超容量按比例削权，不抬滑点 |
| `test_drawdown_halt_triggers_half_exposure` | unit | 回撤 > 15% → 持仓 × 0.5 |
| `test_stamp_tax_zero_for_etf` | unit | ETF 卖出印花税 = 0 |
| `test_t1_etf_intraweek_no_round_trip` | rule_simulation | T+1 股票 ETF 同日不能买入再卖出 |
| `test_t0_etf_allowed_intraday` | rule_simulation | 黄金 / 债券 / 跨境 ETF 允许 T+0（如策略产生此需求） |
| `test_no_bypass_tradeability` | regression | 信号 / 仓位 / 风控模块不直接 import `market_rules_cn` |
| `test_backtest_byte_for_byte_reproducible` | regression | 同 `(params, snapshot_version)` 两次运行结果完全一致 |
| `test_score_formula_with_zscore_outlier_trim` | unit | 3σ 离群裁剪后 z-score 计算正确 |
| `test_phase2_factors_locked` | regression | import `factors.value/quality/...` 即抛 `NotImplementedError` |

### 14.3 报告级（W10 落地）

| 测试 | 验证 |
|---|---|
| `test_metrics_panel_complete` | 必报指标面板字段齐全 |
| `test_manifest_required_fields` | `manifest.json` 所有必填字段存在 |
| `test_walk_forward_directional_consistency` | 各 fold 年化超额同号 |

---

## 15. 与 CLAUDE.md §4 12 项交付物的对照

| # | 项 | 本设计文档对应章节 | 状态 |
|---|---|---|---|
| 1 | 策略假设 | §1.1 | ✅ 设计期 |
| 2 | 适用市场 | §0 + §2 | ✅ |
| 3 | 数据输入 | §3 | ✅ |
| 4 | 因子定义 | §4 | ✅ |
| 5 | 参数表 | §11 | ✅ |
| 6 | 交易规则 | §5–7 | ✅ |
| 7 | 风控规则 | §9 | ✅ |
| 8 | 回测结果 | — | ⬜ 待实现后产出（W10） |
| 9 | 样本外验证 | — | ⬜ 同上 |
| 10 | walk-forward 验证 | — | ⬜ 同上（W9） |
| 11 | 失败案例 | — | ⬜ 在 `review/failure_cases/` 内补 |
| 12 | 是否进入模拟盘 | — | ⬜ Phase 1 退出评审时给出（W12） |

---

## 16. 实现依赖（必须先行的任务）

以下任务在本策略动工**之前**必须完成（来自 `docs/task_queue.md`）：

- `P1-W1-*` 工程环境；
- `P1-W2-*` A 股交易制度建模；
- `P1-W3-*` 撮合可行性与成本；
- `P1-W4-*` 数据底座与点时点快照；
- `P1-W5-*` 因子原语（momentum / low_vol / liquidity）；
- `P1-W6-*` 回测引擎 v0.1。

本策略对应的实现任务：`P1-W7-*` 与 `P1-W8-*`（资产池 + 信号 + 组合层）。

---

## 17. 不确定与待回答的问题

下列细节在实现前可能需要进一步讨论或写入 ADR：

1. `mom_weights` 是否暴露为参数搜索，还是固定 (0.5, 0.3, 0.2)？默认**固定**，搜索是可选实验。
2. 趋势均线窗口 200 是否合适于 A 股节奏？需要 walk-forward 验证。
3. 容量约束 `N_capacity = 5%` 对个人资金量是否过于保守？取决于实盘规模，详 `docs/research_questions.md §Q6.1`。
4. 跨境 ETF 总和 30% 是否过低？取决于个人对汇率与跨境风险的偏好。
5. 货币 ETF 作为"现金替代"在成本计算上的细节（是否计佣金 / 印花税）。

以上问题不阻塞设计稿，但建议在确认前由用户给出方向。

---

## 18. 等待用户确认

按 `CLAUDE.md §6` 边界："Claude 不承担最终交易决策"。本设计稿在用户确认前**不**进入实现。

确认事项：

- [ ] 资产池规模与类型上限（§2.1）
- [ ] 候选池示例是否合适（§2.2）
- [ ] 因子权重默认 (0.5, 0.3, 0.2)（§4.6）
- [ ] 调仓时点：周五收盘 / 周一开盘（§5.1）
- [ ] 回撤减半阈值 15%（§9.3）
- [ ] 时间范围与样本切分（§10.1）
- [ ] 参数搜索范围（§11）
- [ ] §17 的 5 个待回答问题

用户确认后，进入 `P1-W7-*` 任务实现。
