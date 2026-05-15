# Phase 1 当前阶段总结

生成日期：2026-05-15  
范围：`docs/roadmap.md`、`docs/task_queue.md`、`docs/strategy_archive.md`、`reports/backtest/`、`tests/`。  
结论先行：**当前系统仍不可靠，不能进入模拟盘，不能进入 Phase 2，也不能把当前回测结果当成策略有效性证据。**

说明：本次总结以仓库当前 `master` 文件为准，并结合用户反馈“全量 pytest 已通过”。当前无法确认仓库中已经提交真实 `reports/backtest/{run_id}/` 运行目录；已确认的是报告生成器与归档完整性测试存在。

---

## 1. 当前已经完成什么

### 1.1 工程与测试骨架

- 已建立 `tests/unit`、`tests/regression`、`tests/lookahead`、`tests/rule_simulation` 测试分层。
- `tests/README.md` 已明确 7 条强制白名单、测试金字塔、fixture 约束、失败处理方式和覆盖率底线。
- 用户反馈当前全量 `pytest` 已通过；但没有覆盖率报告，不能等价为“系统可靠”。
- 已有基础可复现回归测试，包括回测结果、报告归档、snapshot、滑点随机订单流、walk-forward 窗口切分等。

### 1.2 A 股交易制度与执行基础

- `src/backtest/market_rules_cn.py` 已作为 A 股交易制度定义点。
- `src/execution/tradeability.py` 已作为交易规则访问入口。
- 已覆盖并测试的基础交易制度包括：
  - 涨停买入拒绝；
  - 跌停卖出拒绝；
  - 停牌不可交易；
  - 退市不可交易；
  - ETF T+1 / T+0 分类；
  - 印花税方向；
  - 佣金、最低佣金、过户费基础计算。
- `src/execution/order_model.py` 已实现最小订单模型：市价单、限价单、开盘撮合、拒单、部分成交、容量上限削减。
- `src/execution/slippage.py` 已实现保守滑点模型：基础 bps、ATR 百分比、订单金额占 ADV 比例、max_bps 封顶。
- 已新增固定 seed 的 1000 笔随机订单流滑点回归测试，覆盖 buy/sell、不同订单金额、ADV None/0/正数、ATR None/0/正数、max_bps 封顶。

### 1.3 容量约束与回测引擎 MVP

- `src/portfolio/capacity.py` 已实现 ADV × capacity_pct 的容量上限。
- 已新增容量边界测试，覆盖：
  - `requested_amount = 0`；
  - `adv_amount <= 0`；
  - `capacity_pct = 0`；
  - `requested_amount <= limit`；
  - `requested_amount > limit`；
  - `capacity_pct < 0` 报错。
- `src/backtest/engine.py` 已能跑 fixtures 下的日级事件循环回测。
- 回测执行路径已接入订单模型、费用模型、滑点模型、容量约束。
- 回测估值、目标仓位现值和成交金额已统一到 `price × adj_factor`，并已有复权一致性回归测试。

### 1.4 数据契约与点时点快照底座

- `src/data/akshare_adapter.py` 已实现 AKShare ETF 日线字段标准化。
- `tests/regression/test_akshare_contract.py` 已锁定本地 AKShare 样例字段契约。
- `src/data/snapshot.py` 已实现从本地 raw CSV 生成 snapshot 的 MVP：
  - 支持 `data/raw/{date}/`；
  - 兼容 `data/raw/{vendor}/{date}/`；
  - 输出 `data/snapshots/{snapshot_version}/prices_daily.csv`；
  - 输出 `manifest.json`；
  - 按 `asof_date` 截断，禁止未来行情进入 snapshot；
  - 记录输入文件、文件 hash、schema version、行数、日期范围。
- `tests/regression/test_snapshot_pipeline.py` 已覆盖 manifest 存在、连续生成 hash 一致、PIT 截断、缺字段报错、输出字段符合数据契约。

### 1.5 因子、信号与 Phase 2 锁定

- Phase 1 ETF 轮动相关因子已存在：动量、波动率 / 低波、流动性。
- 已有 ETF 轮动策略信号 `cn_etf_rot_v1`，并有相关 lookahead / signal 测试。
- Phase 2 因子仍处于锁定状态，不应在当前阶段实现或使用。
- 当前策略参数没有因为测试或收益表现被优化，这一点是正确的。

### 1.6 Walk-forward 框架的第一层已完成

- `src/backtest/walk_forward.py` 已实现：
  - `WalkForwardWindow`；
  - `generate_walk_forward_windows()`；
  - `validate_no_overlap()`；
  - `validate_train_before_test()`。
- `tests/unit/test_walk_forward.py` 已覆盖：
  - 训练区间早于测试区间；
  - 测试区间按 step 滚动；
  - 测试区间不重叠；
  - 月末边界日期；
  - train/test 泄漏检测；
  - 无效参数报错；
  - 不完整最终测试窗口丢弃。
- 这只是窗口切分与防泄漏校验，不是完整 walk-forward 回测。

### 1.7 报告归档能力已补齐第一版

- `src/reports/backtest_report.py` 已能生成结构化回测归档目录：

```text
reports/backtest/{run_id}/
  ├─ manifest.json
  ├─ metrics.json
  ├─ equity_curve.csv
  ├─ trades.csv
  ├─ holdings.csv
  ├─ orders.csv
  └─ report.md
```

- `metrics.json` 已包含必报指标：
  - `total_return`
  - `annualized_return`
  - `max_drawdown`
  - `sharpe`
  - `sortino`
  - `calmar`
  - `win_rate`
  - `profit_loss_ratio`
  - `turnover`
  - `trade_count`
  - `monthly_returns`
  - `drawdown_duration`
  - `benchmark_return`
  - `excess_return`
- `tests/regression/test_backtest_report_archive.py` 已覆盖报告文件完整性、metrics 字段完整性、manifest 文件 hash 与固定 fixture 下归档可复现。
- 当前 `orders.csv` 复用 trades 输出，因为引擎还没有独立订单生命周期对象；这是 MVP，不是完整订单审计系统。

---

## 2. 当前系统还不能做什么

当前系统仍不能被视为可靠量化研究系统。

明确不能做的事：

1. **不能进入模拟盘。** 还没有 W11 的 paper-trade broker、执行偏差度量、模拟盘启动检查脚本。
2. **不能进入 Phase 2。** 行业轮动、多因子选股、事件驱动仍必须暂缓。
3. **不能做正式真实市场结论。** 当前主链路仍主要依赖 fixtures 和本地样例测试，不是经过真实 A 股 ETF 全量点时点数据验证的结果。
4. **不能声称 walk-forward 已完成。** 当前只完成窗口切分和防泄漏校验，没有实际执行每个 fold 的训练、测试、汇总和一致性判断。
5. **不能声称参数稳健。** P1-W9-02 参数扰动尚未完成，也没有 ±20% 参数扰动矩阵。
6. **不能声称报告层完整到 Phase 1 退出标准。** P1-W10-01 的结构化归档已经有了，但 P1-W10-02 因子诊断没有完成，IC / Rank IC / 分层收益 / 因子相关矩阵仍缺失。
7. **不能保证真实数据源可靠。** AKShare 适配器和 snapshot 流水线是本地文件级 MVP，不等于 AKShare 网络拉取、真实样例缓存、字段漂移监控、供应商复权口径交叉验证已经完成。
8. **不能做正式基准比较。** `benchmark_return` 当前在报告生成器中默认是 `0.0`，还没有真实 benchmark 曲线接入。
9. **不能完整审计订单生命周期。** `orders.csv` 当前复用 `trades`，没有独立记录 signal → target → order → execution → reject / fill 的完整生命周期。
10. **不能处理更真实的交易细节。** 例如最小交易单位细节、涨跌停价内成交价封顶、跨 bar 顺延、单日跨订单共享容量、组合层预削权等仍未完善。

---

## 3. 当前最大技术债是什么

最大技术债：**系统已经能产出看起来完整的回测与报告，但真实数据、真实执行、真实 walk-forward 还没有闭环。**

具体拆开看：

1. **真实数据链路没有闭环。**
   - 已有 AKShare adapter 和 snapshot MVP；
   - 但缺少 AKShare 网络拉取脚本、真实 raw 样例缓存、reference 层、真实交易日历、真实 ETF master、真实快照生成记录。

2. **真实执行模型仍是 MVP。**
   - 订单、滑点、费用、容量都已经有基础模块；
   - 但没有真实快照下的成交端到端回归；
   - 没有跨订单共享容量；
   - 没有组合层容量预削权；
   - 没有更完整的订单生命周期。

3. **Walk-forward 只有窗口，没有回测编排。**
   - 当前能生成 train/test 窗口并防泄漏；
   - 但还不能自动对每个 fold 跑回测；
   - 还没有 fold 级 manifest、metrics 汇总、方向一致性检查。

4. **报告归档和策略归档仍未完全统一。**
   - `reports/backtest/{run_id}/` 已有结构化目录；
   - `docs/strategy_archive.md` 仍描述 `reports/strategy_archive/<strategy_id>/<run_id>/`；
   - 后续需要明确：backtest run 归档与策略晋升归档的关系。

5. **依赖与工程入口仍存在债务。**
   - roadmap / task_queue 要求 `Makefile`、pre-commit、工具链与依赖矩阵；
   - 当前是否完全满足这些 W1 退出准则，还没有在本总结中看到确定证据。

这不是小修小补问题，而是“工程回测系统”和“可相信的研究系统”之间的差距。

---

## 4. 当前最大策略风险是什么

最大策略风险：**把 fixtures 或本地样例下能跑通的 ETF 轮动链路，误认为已经有策略有效性。**

当前策略链路的风险点：

1. **没有真实点时点数据验证。** fixtures 只能验证工程行为，不能证明市场有效性。
2. **没有真实 benchmark 曲线。** `benchmark_return = 0.0` 只能作为占位，不能证明超额收益。
3. **没有完整 walk-forward。** 没有样本内选参、样本外验证、跨 fold 方向一致性。
4. **没有参数扰动。** 不知道策略是否对窗口、权重、调仓频率、风险阈值敏感。
5. **没有因子诊断。** 动量、低波、流动性是否真的有 IC / Rank IC，不清楚。
6. **没有失败案例归档。** Phase 1 退出要求至少一个失败案例归档；当前仍不应跳过这一步。
7. **报告现在更像正式成果。** 结构化报告越完整，越容易造成“已经可靠”的错觉；这反而提高了错误决策风险。

结论：当前策略最多只能算工程样例链路，不能用于投资判断。

---

## 5. 当前测试覆盖是否足够

结论：**不够。当前测试覆盖比之前明显更强，但仍不足以证明系统可靠。**

已经比较好的部分：

- 交易制度基础测试：涨跌停、停牌、T+1 / T+0、退市不可交易。
- 费用模型基础测试：佣金、最低佣金、印花税方向、成本合计。
- 滑点模型测试：单元测试 + 固定 seed 1000 笔随机订单流回归。
- 容量约束测试：基础单元测试 + 边界测试。
- AKShare 字段契约测试：本地样例字段、日期、价格、成交额、复权因子、PIT 边界。
- Snapshot 测试：manifest、hash 可复现、asof 截断、缺字段报错、字段契约。
- Walk-forward 测试：窗口切分、防泄漏、测试窗口重叠、无效参数。
- 报告归档测试：必需文件、必报指标、文件 hash、固定 fixture 可复现。
- Phase 2 锁定测试：避免 Phase 2 因子误用。

仍不足的部分：

1. **没有覆盖率报告。** 无法确认 `backtest/`、`execution/`、`factors/`、`portfolio/` 是否达到测试规范里的行覆盖 ≥ 85%、分支覆盖 ≥ 70%。
2. **没有真实网络数据契约测试。** 当前 AKShare 只测本地样例，不测真实响应字段漂移。
3. **没有真实 raw/reference/snapshot 端到端样例。** 还没看到真实 `data/raw` → `data/snapshots` → 回测的完整 fixtures。
4. **没有真实 benchmark 测试。** 相对收益、超额收益和信息比率相关测试不足。
5. **没有 walk-forward 回测测试。** 只有窗口，不跑 fold。
6. **没有参数扰动测试。** P1-W9-02 未完成。
7. **没有因子诊断测试。** P1-W10-02 未完成。
8. **没有 paper-trade / 执行偏差测试。** W11 未开始。
9. **没有完整订单生命周期测试。** 当前 orders 与 trades 没有分离。
10. **没有真实市场极端情形测试。** 连续涨跌停、长期停牌、流动性枯竭、退市整理期、复权异常、成交额缺失等仍需要更强测试。

所以：全量测试通过只能说明“当前断言下没有失败”，不能说明“研究结论可信”。

---

## 6. 是否可以进入下一阶段

结论：**不可以进入 Phase 2，不可以进入模拟盘，不可以进入 Phase 1 退出评审。**

可以继续推进的，只是 Phase 1 内部的未完成工程任务。

不能进入下一阶段的原因：

1. W4 仍未完整完成：AKShare 网络拉取、真实 raw 落地、reference 层、真实快照样例仍缺。
2. W8 仍未完整完成：组合优化器、风险预算、组合层容量预削权仍缺。
3. W9 只完成了 W9-01 的窗口切分，W9-02 参数扰动和真实 walk-forward 回测编排未完成。
4. W10 只完成了 W10-01 的结构化报告归档，W10-02 因子诊断未完成。
5. W11 完全不能启动：paper-trade、broker adapter、执行偏差度量都未完成。
6. W12 完全不能启动：没有 Phase 1 评审报告、没有 ADR-0002、没有策略封存、没有失败案例归档闭环。

当前状态：**Phase 1 中段工程骨架增强版**。还不是可晋升系统。

---

## 7. 下一阶段建议做什么

下一步不要开发新策略，不要改参数，不要做收益优化。建议按以下顺序补齐底座：

### 7.1 优先补真实数据链路

- 完成 `scripts/fetch_akshare.py` 或等价 raw 拉取入口。
- 固定一小段真实 ETF raw 样例，入 `tests/fixtures` 或受控缓存。
- 完成 reference 层：交易日历、ETF master、退市档案。
- 用真实 raw 样例跑一次 `data/raw` → `data/snapshots` → 回测的端到端测试。

### 7.2 补 walk-forward 回测编排，但不做自由调参

- 在 `generate_walk_forward_windows()` 之上增加 fold runner。
- 每个 fold 输出独立 metrics。
- 检查 train/test 时间边界。
- 先用固定参数跑，不做自动选参。
- 后续再做 P1-W9-02 参数扰动。

### 7.3 补真实 benchmark 与报告指标

- 增加 benchmark 曲线输入。
- 计算 `benchmark_return`、`excess_return`、信息比率。
- 报告中明确 benchmark 名称、来源、snapshot_version。
- 不要继续使用默认 `benchmark_return = 0.0` 作为正式报告。

### 7.4 补因子诊断

- 实现 P1-W10-02：IC、Rank IC、分层收益、相关矩阵。
- 用 fixture 做可复现测试。
- 先验证因子是否有方向，再谈策略晋升。

### 7.5 补订单生命周期与执行偏差前置能力

- 区分 signal、target、order、trade。
- `orders.csv` 不应长期复用 `trades.csv`。
- 加入订单未成交原因聚合。
- 为 W11 paper-trade 做数据结构准备。

---

## 8. 哪些任务必须暂缓

必须暂缓：

- **任何新策略开发**：包括新 ETF 策略、行业轮动、多因子选股、事件驱动。
- **任何参数优化**：不能因为 fixtures 或小样本结果不好看就改窗口、权重、阈值。
- **任何 Phase 2 因子实现**：value、quality、growth、dividend、event_features 继续锁定。
- **任何模拟盘代码**：W11 前置条件远未满足。
- **任何实盘下单代码**：当前严禁。
- **任何策略晋升结论**：当前没有完整真实数据、walk-forward、参数扰动、因子诊断，不允许谈晋升。
- **任何“收益美化”工作**：例如调参、换 benchmark、删失败窗口、隐藏回撤。
- **报告页面美化优先事项**：在真实数据链路和稳健性验证完成前，继续美化页面价值很低。
- **Phase 1 退出评审**：W10-02、W11、W12 缺失，不能启动退出评审。

---

## 最终判断

当前项目已经从“能跑的 ETF 轮动骨架”进化到“有较多工程护栏的研究系统雏形”。

但它仍然不可靠。核心原因不是测试没过，而是：

- 真实数据链路没有闭环；
- walk-forward 没有真正跑起来；
- benchmark 与因子诊断缺失；
- 订单与执行模型仍是 MVP；
- 没有模拟盘和执行偏差验证。

下一步正确方向是继续补底座，而不是扩策略、调参数、讲收益。
