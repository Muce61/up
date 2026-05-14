# CLAUDE.md — 项目最高开发规则

本文件是本项目的**最高开发规则**。任何代码、文档、研究计划、实验归档都必须服从于此。
本文件与其他文档冲突时，**以本文件为准**。
本文件依据 `docs/deep-research-report.md` 生成；任何修改必须经过显式 ADR（`docs/adr/`）。

---

## 1. 项目定位

本项目是一个**个人股票量化研究系统**。

- **第一阶段**：仅聚焦 **A 股 ETF / 指数轮动**，周频为主，月频备选。
- **后续阶段**（按顺序推进，每次只启动一个，禁止跳级）：
  1. 行业轮动（以 ETF 实现）
  2. A 股 long-only 多因子选股
  3. 公告型事件驱动
- **绝对禁止方向**：
  - 不做高频、盘口、自动打板。
  - **禁止 AI 直接荐股**——任何"挑出某只票"的输出都不被允许。
  - **禁止自动实盘下单**——实盘下单代码只能在我明确要求且为 paper trading 时存在。
  - 不接受忽略真实交易制度的回测。
  - 不接受单一参数、单一市场状态下的"高 Sharpe 神话"。

研究上游：`docs/deep-research-report.md`。

---

## 2. 研发硬约束

任何代码、研究计划、数据落地操作都必须满足以下条款：

1. **所有数据必须有时间戳**——至少含 `asof_date`、`effective_date`、`announcement_date` 三类中的相关一项；禁止 naive datetime；时区显式声明。
2. **所有基本面 / 公告数据必须使用 point-in-time 逻辑**——以 `announcement_date` 生效，**不得**用 `report_period`（财报所属期）直接回填历史；公告在交易日收盘后发布的，最早只能在**下一交易日**使用。
3. **禁止未来函数**——任何在 `t` 日访问 `t+1` 及之后数据的代码路径，一经发现立即回滚 commit；新增因子必须配套 `tests/lookahead/` 用例。
4. **禁止幸存者偏差**——禁止用退市后清洗过的证券池重跑历史；ST/*ST、退市样本必须保留在样本中；禁止用最终行业分类与最终成分股名单回填历史。
5. **禁止在测试集上调参**——所有参数搜索必须限制在 in-sample；out-of-sample 仅供评估；最终参数由 walk-forward 决定。
6. **禁止忽略交易费用、滑点、涨跌停、停牌、T+1**——这些是回测引擎的最低门槛，任何"先回测看看效果再补"的写法都不被允许。

---

## 3. 回测硬约束（A 股）

A 股回测引擎必须显式模拟以下规则：

- **T+1**：股票 ETF 默认 T+1；债券 / 黄金 / 跨境 / 货币 ETF 等支持 T+0 的品类按品类配置（`config/universe/cn_etf.yaml`）。
- **涨停买不进**：涨停价时买单一律被拒。
- **跌停卖不出**：跌停价时卖单一律被拒。
- **停牌不可交易**：双向都不可成交。
- **手续费**：佣金（含最低佣金）。
- **印花税**：A 股股票卖出收；ETF 默认不收，按品类配置。
- **过户费**：按规则计入。
- **滑点**：默认基于成交额 / ATR 的保守模型；激进模型只在样本外做敏感性分析。
- **成交额容量约束**：单标的单日成交量上限 = ADV × N（保守 N，可配置）；超出按比例削权，**不**抬高滑点掩盖容量问题。
- **ETF 类型差异**：宽基 / 行业 / 债券 / 黄金 / 跨境 / 货币 各自的交易制度（T+1 vs T+0、印花税、流动性）按配置生效。
- **涨跌幅档位**：主板 10% / 创业板与科创板 20% / 风险警示 5%（沪市风险警示新规拟 2026-07-06 起改为 10%，必须做成参数化开关）。
- **退市整理期**：通常 15 个交易日，首日不设涨跌幅。

上述全部规则的**唯一定义点**：`backtest/market_rules_cn.py`。
策略代码、因子代码、信号代码**禁止**自行判断这些规则，必须通过**唯一访问入口** `execution/tradeability.py`。

---

## 4. 策略开发流程

每个策略以单独目录 `strategies/<strategy_id>/` 维护（`strategy_id` 命名格式 `<market>_<asset>_<style>_<v>`，例 `cn_etf_rot_v1`）。

每个策略必须完整交付以下 **12 项**，缺一不可：

1. **策略假设** — 经济逻辑、为什么这条 alpha 应该存在。
2. **适用市场** — 市场范围、资产类别、限制条件。
3. **数据输入** — 字段、频率、来源、对应的 `data/snapshots/` 版本。
4. **因子定义** — 每个因子的数学定义、口径、时间窗口。
5. **参数表** — 可调参数、默认值、搜索范围、最终选定值（必须由 in-sample 得出）。
6. **交易规则** — 调仓周期、加减仓逻辑、止损止盈。
7. **风控规则** — 单标的上限、行业上限、目标波动率、回撤减仓、容量约束。
8. **回测结果** — 完整必报指标面板（年化、最大回撤、Sharpe、Sortino、Calmar、胜率、盈亏比、换手率、单笔与月度收益分布、回撤持续时间、相对基准超额、信息比率）。
9. **样本外验证** — 留出的 out-of-sample 段独立评估，方向与样本内一致。
10. **walk-forward 验证** — 滚动窗口（默认 36 月 IS / 12 月 OOS），方向一致。
11. **失败案例** — 迭代过程中被淘汰的版本、原因，归档到 `review/failure_cases/`。
12. **是否允许进入模拟盘** — 明确结论 + 理由；进入模拟盘前 7 条强制测试必须全绿。

策略目录结构：

```
strategies/<strategy_id>/
  ├─ signal.py
  ├─ params.yaml
  ├─ README.md      # 上述 12 项交付物的策略卡片
  └─ tests/         # 策略级集成测试与烟雾测试
```

执行顺序硬约束：**回测 → 模拟盘 ≥ 3 个月 → 小资金实盘**；禁止跳级，禁止合并。

---

## 5. 测试要求

任何代码修改后必须运行下列测试，**不允许跳过**：

1. **pytest** — 覆盖 `tests/unit/`、`tests/regression/`、`tests/lookahead/`、`tests/rule_simulation/`。
2. **回测 smoke test** — 用固定 fixtures 跑一次回测，与快照输出对比 byte-for-byte 一致。
3. **防未来函数测试**（`tests/lookahead/`）— 每个因子至少 1 条；任一失败即 block 合并。
4. **交易规则测试**（`tests/rule_simulation/`）— 必须包含以下 7 条强制白名单：
   - `test_limit_up_buy_blocked`
   - `test_limit_down_sell_blocked`
   - `test_suspended_security_untradeable`
   - `test_cn_stock_t_plus_one`
   - `test_fundamental_release_lag_enforced`
   - `test_delisted_names_survive_history`
   - `test_no_future_prices_in_signal`
5. **回归测试**（`tests/regression/`）— 含 AKShare 字段口径、复权一致性、撮合层不可绕过等架构约束。

测试失败 = block 合并；不允许 skip、xfail 掉头、注释掉、"先合后修"。详见 `tests/README.md`。

---

## 6. Claude Code 行为限制

Claude 的角色：研发助手 / 测试执行者 / 文档生成器 / 代码审查员 / 流程守门人。

Claude **不得**做以下事情：

1. **不得直接推荐具体股票** — 任何输出都不允许出现"建议买入 X"或"X 是好标的"的语义。
2. **不得为了提高收益随意调参** — 任何参数变更必须有明确理由（in-sample 信号 / walk-forward 结果 / 数据修复）；不允许基于回测曲线"主观微调"。
3. **不得跳过失败测试** — 测试失败必须定位根因再修复，不允许 skip / xfail / 注释。
4. **不得删除失败实验记录** — 所有失败实验必须归档到 `review/failure_cases/`；归档是义务，不是选项。
5. **不得生成实盘下单代码** — 除非我**明确要求**且**仅限 paper trading**；任何对接真实券商账户的代码都需要单独 ADR 与人工确认。

附加边界：

- Claude **不**承担最终交易决策。
- Claude 修改本文件必须通过显式 ADR（`docs/adr/NNNN-claude-md-change.md`），不允许"顺便改一下"。
- Claude 主动发现的灰色地带问题，必须先写入 `docs/research_questions.md`，再讨论是否落地。

---

## 配套文档

- `docs/roadmap.md` — 12 周路线图。
- `docs/task_queue.md` — Phase 1 任务队列（含可测试验收准则）。
- `docs/engineering_rules.md` — 工程与测试细节规范。
- `docs/research_questions.md` — 不适合工程落地的悬而未决问题。
- `tests/README.md` — 测试规范与 7 条强制白名单。
- `docs/deep-research-report.md` — 研究依据。
