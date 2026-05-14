# 12 周路线图（Phase 1 — A 股 ETF 轮动）

> 配套阅读：`CLAUDE.md`（宪法）、`docs/task_queue.md`（任务粒度）、`tests/README.md`（测试规范）。
>
> 总体原则：W1–W6 是底座，**任何 W7 之后的策略代码都依赖前 6 周的产物**。任一周的退出准则未通过，禁止跨周推进。

---

## 阶段概览

| 段 | 周 | 主题 | 关键产物 |
|---|---|---|---|
| P1-A | W1 | 工程环境与项目元数据 | pyproject、pre-commit、CI 占位 |
| P1-A | W2 | A 股交易制度建模 | `backtest/market_rules_cn.py` + 7 条强制测试 |
| P1-A | W3 | 撮合可行性与成本模型 | `execution/{tradeability,order_model,slippage,fee_model}.py` |
| P1-A | W4 | 数据底座与点时点快照 | AKShare 适配器、`data/snapshots/` 流水线 |
| P1-A | W5 | 因子与信号原语（ETF 用） | momentum / low_vol / liquidity（仅 ETF 适用子集） |
| P1-A | W6 | 回测引擎 v0.1 | `backtest/engine.py` + smoke test |
| P1-B | W7 | 策略 v0 — 资产池与信号 | `strategies/etf_rotation/cn_etf_rot_v1/signal.py` |
| P1-B | W8 | 策略 v0 — 组合层与风控 | `portfolio/optimizer.py`、风险预算与容量约束 |
| P1-B | W9 | Walk-forward 与参数稳健性 | `backtest/walk_forward.py` + 参数扰动 |
| P1-B | W10 | 报告层 + 因子诊断 | `reports/` 自动生成必报面板 + 因子诊断 |
| P1-C | W11 | 模拟盘接口与执行偏差度量 | paper-trade 接入设计 + 偏差度量框架 |
| P1-C | W12 | 阶段评审与封存 | Phase 1 评审、ADR、`strategy_archive/` 封存 |

---

## W1 — 工程环境与项目元数据

**目标**：让任何一次 `git clone && make setup && make test` 都能稳定复现。

**交付**
- `pyproject.toml`：Python ≥ 3.11；运行依赖与开发依赖分离。
- `ruff`、`mypy --strict`（按工程规范配置）、`pytest`、`pre-commit`。
- `Makefile`：`setup` / `lint` / `type` / `test` / `smoke` 五个目标。
- `.gitignore`、`.editorconfig`。
- `docs/adr/0001-tooling.md`：记录工具链选择。

**退出准则（可测试）**
1. `make lint` 和 `make type` 在空仓库上即返回 0。
2. `make test` 在空仓库上至少跑通一个"hello world"占位用例。
3. `pre-commit run --all-files` 通过。

---

## W2 — A 股交易制度建模

**目标**：把交易规则变成代码与测试，而不是 README 里的注释。

**交付**
- `backtest/market_rules_cn.py`：`limit_band(security, date)`、`is_tradeable(security, date)`、`settlement_lag(security)`、`fee_schedule(...)`。
- 涨跌幅配置：主板 10% / 创业板与科创板 20% / 风险警示 5%（沪市风险警示 2026-07-06 切换开关）。
- T+1 默认；ETF 类型字典区分 T+0 / T+1。
- 停牌、退市整理期、首日不设涨跌幅的特殊撮合。
- 印花税、过户费、佣金、滑点参数化。

**退出准则**
1. `tests/rule_simulation/` 中实现并通过：`test_limit_up_buy_blocked`、`test_limit_down_sell_blocked`、`test_suspended_security_untradeable`、`test_cn_stock_t_plus_one`、`test_delisted_names_survive_history`。
2. `test_fundamental_release_lag_enforced`（占位即可，W4 数据底座到位后才真正生效）。
3. 沪市风险警示 5%/10% 切换通过参数化测试覆盖。

---

## W3 — 撮合可行性与成本模型

**目标**：把"能不能成交"和"成交后实际亏多少手续费 + 滑点"独立建模。

**交付**
- `execution/tradeability.py`：吸收 W2 的规则，作为撮合层唯一入口。
- `execution/order_model.py`：限价单 / 市价单 / 收盘成交假设。
- `execution/slippage.py`：基于 ATR / 成交额的滑点模型（默认保守版本）。
- `execution/fee_model.py`：佣金、印花税、过户费、最小成交额。

**退出准则**
1. `tests/unit/` 内对每个模块至少 3 条边界用例（涨停下买单、跌停下卖单、停牌、最低佣金、成交额上限）。
2. 1000 笔随机订单流的回归测试，输出实际成交占比和总成本 breakdown，结果可复现（固定 seed）。

---

## W4 — 数据底座与点时点快照

**目标**：建立**一次抽取、永不改写**的原始层，和**带 effective_date 的点时点快照**两层数据。

**交付**
- `data/raw/`：AKShare 拉取脚本，按日期分区；不允许覆盖。
- `data/reference/`：交易日历、ETF 主数据、行业分类、退市档案。
- `data/snapshots/YYYYMMDD/`：每次跑研究时冻结的点时点快照；命名带数据版本号。
- `scripts/snapshot.py`：从 raw 生成 snapshots 的工具。
- `docs/data_contracts.md`：字段、口径、复权方式、缺失值策略。

**退出准则**
1. 同一天的快照可用 hash 校验；不同天的快照间能 diff。
2. `test_no_future_prices_in_signal` 启用：任何因子在 t 日只能看到 ≤ t 的快照。
3. AKShare 字段口径与官方接口对齐，由 `tests/regression/test_akshare_contract.py` 验证。

---

## W5 — 因子与信号原语（仅 ETF 适用子集）

**目标**：实现 Phase 1 真正用得到的 3 个因子，**不**实现其他因子。

**交付**
- `factors/momentum.py`：3 / 6 / 12 个月动量；标准化与去极值。
- `factors/low_vol.py`：20 / 60 日实现波动率。
- `factors/liquidity.py`：ADV、成交额、最小流动性阈值。
- 每个因子函数签名都强制接收 `as_of_date`，输出带 `effective_date` 列。

**退出准则**
1. `tests/lookahead/` 对每个因子至少 1 条用例：截断未来数据后输出不变。
2. 3 个因子的产出表与回测引擎的输入 schema 对齐（schema 单元测试）。

> 其他因子（value、quality、growth、dividend、event_features）保留空文件 + Phase 2 占位注释，**禁止**在 Phase 1 实现。

---

## W6 — 回测引擎 v0.1

**目标**：能跑通一个最小可用的、严格服从 W2/W3 规则的事件循环回测。

**交付**
- `backtest/engine.py`：日级事件循环；可配置调仓频率（默认周频）。
- 接口契约：输入 = `(signal_df, universe_config, rules_config)`，输出 = `(equity_curve, trade_log, holdings)`。
- 复权处理在引擎内部完成，因子层与策略层只见点时点价格。
- `scripts/run_backtest.py` CLI。

**退出准则**
1. Smoke test：用固定假数据（fixtures）跑通一次回测，对比快照输出无差。
2. 两次相同输入运行的输出必须 byte-for-byte 一致。
3. 回测引擎所有路径都经过 `execution/tradeability.py`，不能绕过。

---

## W7 — 策略 v0 资产池与信号

**目标**：把 `cn_etf_rot_v1` 的资产池与信号定义清楚，**不**做组合优化。

**交付**
- `config/universe/cn_etf.yaml`：宽基（沪深 300 / 中证 500 / 中证 1000 / 创业板 50 等）+ 行业 ETF 一组，按 T+1 / T+0 / 跨境 / 商品 标注。
- `strategies/etf_rotation/cn_etf_rot_v1/signal.py`：横截面动量 + 趋势过滤；输出标的得分。
- `strategies/.../params.yaml`：参数表 + 经济逻辑说明。
- `strategies/.../README.md`：策略卡片（假设、风险点、适用市场、失效条件、下一步验证）。

**退出准则**
1. 信号代码所有数据访问都通过 `as_of_date`，由 lookahead 测试覆盖。
2. 资产池配置覆盖至少 10 只 ETF；T+1 / T+0 分类在测试中验证。

---

## W8 — 组合层与风控

**目标**：把信号变成组合，叠加风控。

**交付**
- `portfolio/optimizer.py`：按横截面得分构造目标权重；单标的上限、行业上限、目标波动率。
- `portfolio/risk_budget.py`：组合波动率目标 + 回撤阈值减仓。
- `portfolio/capacity.py`：基于 ADV 的容量上限。
- 接入回测引擎，做一次完整 backtest。

**退出准则**
1. 单标的权重约束、波动率目标在 `tests/unit/` 中各有 ≥ 2 条用例。
2. 完整回测在样本内产生非平凡的换手率和持仓集中度统计。

---

## W9 — Walk-Forward 与参数稳健性

**目标**：拒绝"全样本最优"，强制滚动窗口验证。

**交付**
- `backtest/walk_forward.py`：滚动窗口（默认 36 个月 in-sample / 12 个月 out-of-sample）。
- 参数扰动脚本：对动量窗口、波动率目标、调仓频率做 ±20% 扰动。
- 输出参数稳健性热力图或文字摘要。

**退出准则**
1. 样本外结果方向与样本内一致（同号、量级合理）。
2. 参数扰动下年化超额收益无单点尖峰。

---

## W10 — 报告层 + 因子诊断

**目标**：必报指标面板自动化产出；策略可解释。

**交付**
- `reports/strategy_archive/cn_etf_rot_v1/`：年化、回撤、Sharpe、Sortino、Calmar、胜率、盈亏比、换手率、月度分布、回撤持续时间、相对基准、信息比率。
- `reports/factor_diagnostics/`：动量 / 低波 / 流动性的 IC、Rank IC、分层收益。
- 报告生成器入口：`scripts/build_report.py`。

**退出准则**
1. 任何一次回测结果都能自动产出上述完整报告。
2. 报告中必须包含：策略假设 / 风险点 / 失效条件 / 下一步验证计划。

---

## W11 — 模拟盘接口与执行偏差度量

**目标**：为模拟盘做接口设计与偏差度量框架，**暂不**接通真实券商。

**交付**
- `execution/broker_adapters/`：抽象 broker 接口、paper-trade 模拟器（不接真实账户）。
- 执行偏差度量：理论成交 vs 模拟成交差异、滑点分布、未成交单原因归因。
- `docs/paper_trade_plan.md`：模拟盘启动条件、监控指标、停机规则。

**退出准则**
1. paper-trade 模拟器在历史回放数据上输出与回测引擎一致的成交序列（容差 < 0.1%）。
2. 模拟盘启动条件清单全部可被自动检查脚本验证。

---

## W12 — 阶段评审与封存

**目标**：决定是否进入模拟盘观察期；封存 Phase 1 工件。

**交付**
- `review/phase1_review.md`：跨样本表现、参数稳健性、容量与执行偏差、失败案例汇总。
- ADR：`docs/adr/0002-phase1-exit-decision.md`。
- `reports/strategy_archive/cn_etf_rot_v1/`：含 git commit、参数、快照版本、回测时间、结果摘要。

**退出准则（= Phase 1 退出准则）**
1. 7 条强制单元测试全部通过；
2. 样本内 / 样本外 / walk-forward 方向一致；
3. 必报面板齐全；
4. 至少 1 个失败案例归档到 `review/failure_cases/`；
5. ADR 通过；
6. 已具备模拟盘启动条件——但**不**自动启动，要由人按 ADR 决定。

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 数据源字段口径漂移（AKShare） | 高 | W4 的 regression 测试 + 字段版本化 |
| 未来函数潜入 | 高 | `tests/lookahead/` 在 W2 起就跑 |
| 参数过拟合 | 高 | walk-forward + 参数扰动（W9） |
| 涨跌停 / 停牌建模遗漏 | 高 | 撮合层是回测唯一通道（W3） |
| 容量假设过乐观 | 中 | 容量约束在 W8 内置 |
| 沪市风险警示新规切换（2026-07-06） | 中 | W2 内做成开关 + 配置化 |
