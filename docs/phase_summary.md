# Phase 1 当前阶段总结

生成日期：2026-05-14  
范围：`docs/roadmap.md`、`docs/task_queue.md`、`docs/strategy_archive.md`、`reports/backtest/`、`tests/`。  
结论先行：**当前系统不可靠，不能进入下一阶段，不能进入模拟盘。**

---

## 1. 当前已经完成什么

### 1.1 工程与测试骨架

- 已有 `pyproject.toml`、`requirements.txt`、`scripts/run_tests.py`。
- 已建立 `tests/unit`、`tests/regression`、`tests/lookahead`、`tests/rule_simulation` 四类测试目录。
- 当前 `tests/` 下有 29 个 Python 测试文件。
- 当前完整测试通过：`149 passed in 10.70s`。
- 7 条强制白名单相关测试存在并通过：
  - `test_limit_up_buy_blocked`
  - `test_limit_down_sell_blocked`
  - `test_suspended_security_untradeable`
  - `test_cn_stock_t_plus_one`
  - `test_fundamental_release_lag_enforced`
  - `test_delisted_names_survive_history`
  - `test_no_future_prices_in_signal`

### 1.2 A 股交易规则与执行基础

- `src/backtest/market_rules_cn.py` 已作为交易制度定义点。
- `src/execution/tradeability.py` 已作为交易规则访问入口。
- 已有基础规则测试覆盖涨停买入拒绝、跌停卖出拒绝、停牌不可交易、退市不可交易、T+1 / T+0 分类。
- `src/execution/fee_model.py` 已实现佣金、最低佣金、印花税、过户费计算。
- `src/execution/order_model.py` 已实现最小订单模型：市价、限价、开盘撮合、部分成交、容量上限拒绝/削减。
- `src/execution/slippage.py` 已实现滑点 MVP：基础 bps、ATR 百分比、订单金额占 ADV 比例三部分估算，并已接入 `src/backtest/engine.py` 的成交价计算。
- `src/backtest/engine.py` 的成交执行路径已接入 `src/execution/order_model.py`，不再由引擎独立完成涨跌停、停牌、退市等订单状态判断。
- `src/portfolio/capacity.py` 已实现 ADV × N 容量约束 MVP，并已接入 `src/backtest/engine.py` 的订单执行路径。
- `src/backtest/engine.py` 已将持仓估值、目标仓位现值与成交金额口径统一到 `price × adj_factor`，并新增复权跳变回归测试。
- `src/data/akshare_adapter.py` 已实现 AKShare ETF 日线字段本地标准化与基础合法性校验，并新增 `tests/regression/test_akshare_contract.py` 锁定字段口径。

### 1.3 ETF 轮动 MVP 主链路

- 已有 ETF master 配置：`config/universe/etf_pool.yaml`。
- 已有数据加载器：`src/data/etf_loader.py`，支持 master、行情、日历加载与 PIT 截断。
- 已有 ETF 因子：
  - `src/factors/momentum.py`
  - `src/factors/volatility.py`
  - `src/factors/liquidity.py`
- Phase 2 因子仍为锁定状态，导入即抛 `NotImplementedError`。
- 已有策略信号：`src/strategies/etf_rotation/cn_etf_rot_v1/signal.py`。
- 已有参数文件：`src/strategies/etf_rotation/cn_etf_rot_v1/params.yaml` 与 `config/strategy_params/cn_etf_rot_v1.yaml`。
- 已有策略卡片：`src/strategies/etf_rotation/cn_etf_rot_v1/README.md`。
- 已有最小事件循环回测引擎：`src/backtest/engine.py`。
- 已有报告生成器：`src/reports/backtest_report.py`。

### 1.4 已有审查与展示产物

- 已生成严格回测审查：`reports/backtest/etf_rotation_review.md`。
- 已生成本地网页报告：`reports/backtest/index.html`。
- `docs/strategy_archive.md` 已记录 `P1-W3-02 订单模型 MVP`、`P1-W3-03 滑点模型 MVP`、回测引擎接入订单模型、`P1-W8-03 容量约束 MVP` 与 `P1-W6-03 复权一致性回归` 阶段进展。

---

## 2. 当前系统还不能做什么

当前系统不能被视为可用于真实研究结论，更不能用于模拟盘或实盘。

明确不能做的事：

- 不能基于真实 A 股 ETF 快照做正式回测，因为 `data/snapshots/<snapshot_version>/` 流水线尚未落地。
- 不能保证真实数据字段口径完整正确；AKShare ETF 日线字段契约已有本地回归测试，但 AKShare 网络拉取、raw/reference/snapshot 流水线和真实样例缓存尚未完成。
- 不能输出 Phase 1 合格的完整策略报告，因为报告层还缺少正式归档的 `metrics.json`、`equity_curve`、`trades`、`holdings` 与因子诊断。
- 不能做正式样本内 / 样本外 / walk-forward 结论，因为 `src/backtest/walk_forward.py` 仍是 stub。
- 不能声称已满足真实交易制度，因为容量约束仍只是 MVP，尚未做真实快照字段校验、跨订单共享单日容量、组合层预削权；滑点模型也未用真实滚动 ATR / 真实 ADV 快照验证，且订单模型仍未处理涨跌停价内成交价封顶和跨 bar 顺延。
- 不能进入模拟盘，因为 Phase 1 晋升门禁远未满足。
- 不能开启 Phase 2 行业轮动、多因子选股或事件驱动。
- 不能为了提高结果修改策略参数；当前参数没有经过正式 in-sample 与 walk-forward 决策。

---

## 3. 当前最大技术债是什么

最大技术债：**回测引擎仍不是一个可信的 A 股 ETF 回测引擎**。

具体表现：

1. 数据快照流水线 `src/data/snapshot.py` 仍是 stub；AKShare 适配器已有本地字段标准化，但尚未联网拉取、raw 落地或生成 snapshot。
2. 真实供应商复权因子口径尚未交叉校验；虽然合成复权跳变已被回归测试锁住，AKShare 原始 `复权因子` 字段也已有契约测试，但仍缺真实快照样例与供应商口径验证。
3. `src/portfolio/capacity.py` 虽已不再是 stub，但仍只是 MVP：当前按历史成交额估算滚动 ADV，尚未验证真实快照字段、跨订单共享单日容量和组合层预削权。
4. `src/execution/slippage.py` 虽已不再是 stub，但仍只是 MVP：ATR 由当日 high/low/close 近似或直接字段读取，未建立真实滚动 ATR 特征，也没有真实快照下的滑点回归测试。
5. `src/execution/order_model.py` 已接入引擎，但仍未处理最小交易单位、涨跌停价内成交价封顶、跨 bar 顺延和真实快照下的成交回归。

这不是“细节未完善”，而是核心可信度缺口。只要这些问题存在，任何收益率都不能作为策略有效证据。

---

## 4. 当前最大策略风险是什么

最大策略风险：**策略尚未经过真实、点时点、全交易制度约束下的稳健性验证，但已经能产出看起来完整的回测页面和指标**。

这很危险，因为容易让人误以为系统已经可靠。

来自 `reports/backtest/etf_rotation_review.md` 的现有 fixtures 审查结果本身也不合格：

- 年化收益：`-36.76%`
- 最大回撤：`-52.85%`
- Sharpe：`-0.6745`
- 相对等权基准总收益：`-69.39%`
- 样本内与样本外方向均为负
- walk-forward 未实现

这些结果来自合成 fixtures，不代表真实市场表现。但即便在 fixtures 上，当前策略链路也暴露了高回撤、尾部月份损失和相对基准显著落后的问题。

---

## 5. 当前测试覆盖是否足够

结论：**不够。当前测试数量不少，但覆盖不足以证明系统可靠。**

已经覆盖的部分：

- 基础交易规则：涨跌停、停牌、T+1 / T+0、退市不可交易。
- 基础费用模型：最低佣金、印花税方向、成本合计。
- 基础滑点模型：基础 bps、ATR 百分比、ADV 参与率、买卖方向、确定性输出。
- 基础容量约束：ADV × N 上限、超限部分成交、0 ADV 保守拒绝、引擎成交金额削减。
- 复权一致性：动量因子使用复权收盘价；回测估值和成交金额使用 `price × adj_factor`；合成复权跳变下权益不再断崖。
- 引擎成交路径：调用 `order_model.execute_order`、涨停买入拒绝、跌停卖出拒绝、停牌拒绝、T+1、费用、滑点和可复现性。
- 因子防未来函数：动量、趋势、波动率、最大回撤。
- 信号防未来函数：污染未来价格后信号不变。
- 回测可复现：fixtures 下关键输出一致。
- 报告生成：Markdown / HTML 报告文件可生成。
- Phase 2 因子锁定：部分 lookahead 测试覆盖。

不足的部分：

- 已新增 AKShare ETF 日线字段口径回归测试，但只覆盖本地样例，不覆盖真实网络响应和快照版本化。
- 复权一致性已有合成跳变回归测试，AKShare `复权因子` 必填和正值契约已覆盖；仍没有真实供应商复权口径交叉验证。
- 容量约束已有单元和引擎接入测试，但没有真实快照字段回归、跨订单共享容量测试、组合层预削权测试。
- 滑点测试仍限于单元测试和引擎调用路径，没有 1000 笔随机订单流回归测试，也没有真实快照下校验。
- 订单模型接入引擎已有单元级覆盖，但没有真实快照下的成交端到端回归。
- 没有 walk-forward 切分和防泄漏测试。
- 没有正式基准收益与相对收益测试。
- 没有报告完整性覆盖所有 `CLAUDE.md §4` 必报指标。
- 测试没有覆盖率报告；无法确认 `backtest/`、`execution/`、`factors/`、`portfolio/` 行覆盖是否达到 `tests/README.md` 要求的 85%。

所以，`110 passed` 只能说明“当前已有断言通过”，不能说明“系统已经可信”。

---

## 6. 是否可以进入下一阶段

结论：**不可以。**

不能进入下一阶段的原因：

1. W3 未完成：滑点模型已有 MVP，但尚未满足任务队列要求的 1000 笔随机订单流回归测试；费用模型也未达到任务队列要求的完整边界测试数量；订单模型虽然已接入回测引擎，但尚未覆盖真实快照成交回归。
2. W4 未完成：AKShare 适配器、原始层、reference 层、snapshot 流水线都未完成。
3. W6 只能算 MVP：引擎可跑 fixtures，复权跳变已有合成回归，但仍未满足真实快照、完整订单/滑点/容量回归。
4. W8 未完成：容量约束已有 MVP，但组合优化、风险预算、组合层预削权仍未完成。
5. W9 未完成：walk-forward 仍是 stub。
6. W10 未完成：报告层不是完整必报指标面板，因子诊断未实现。
7. W11 / W12 完全不能启动：模拟盘接口、执行偏差度量、Phase 1 评审与封存条件都未满足。

当前最多处于：**Phase 1 早期 MVP 骨架阶段**。不能进入模拟盘，不能进入 Phase 2，也不能把当前回测当作策略有效性证明。

---

## 7. 下一阶段建议做什么

下一阶段不应做新策略，而应补齐回测可信度底座。

优先级建议：

1. **补齐真实快照前的数据契约与字段测试**
   - 推进 AKShare 字段口径回归测试。
   - 明确行情字段、复权字段、ADV / ATR 字段来源。

2. **补齐滑点、订单和容量回归测试**
   - 对 `src/execution/slippage.py` 增加固定 seed 的 1000 笔随机订单流回归测试。
   - 增加跨订单共享容量、真实 ADV / ATR 字段校验、`order_model` 成交路径回归。

3. **推进 W4 数据底座**
   - 完成 AKShare 适配器、raw/reference/snapshot 结构。
   - 生成第一个可追踪 `snapshot_version`。
   - 增加字段口径回归测试。

4. **扩展报告指标**
   - 在报告层内置胜率、盈亏比、月度收益、回撤持续时间、相对基准收益、信息比率。
   - 不要依赖临时审查脚本手算指标。

---

## 8. 哪些任务必须暂缓

必须暂缓的任务：

- **任何新策略开发**：包括新 ETF 策略、行业轮动、多因子选股、事件驱动。
- **任何参数优化**：当前不能因为 fixtures 上某个参数更好而改参数。
- **任何模拟盘相关代码**：W11 只能在 W1-W10 基础合格后再讨论。
- **任何实盘下单代码**：当前严禁。
- **Phase 2 因子实现**：`value`、`quality`、`growth`、`dividend`、`event_features` 必须继续锁定。
- **基于当前 fixtures 的策略晋升讨论**：fixtures 只能用于工程测试，不能用于投资研究结论。
- **报告美化优先事项**：在数据、滑点、容量、walk-forward 未完成前，继续美化页面没有研究价值。
- **W12 阶段评审与封存**：当前不具备 Phase 1 退出评审条件。

---

## 最终判断

当前项目已经有一个能跑通的 ETF 轮动研究骨架，但它还不是可靠的量化研究系统。

系统当前最大的价值是：规则边界、测试框架、信号链路和报告链路已经初步搭起来。

系统当前最大的限制是：真实点时点数据、真实交易制度关键约束、稳健性验证和完整报告指标都没有完成。

因此，当前阶段的正确动作不是扩张策略，而是补齐底座；否则后续任何收益曲线都可能是工程假象。
