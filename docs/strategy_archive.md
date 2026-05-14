# 策略归档规范

> 上游：`CLAUDE.md §4 策略开发流程`。
> 任何策略迭代完成后必须归档；失败迭代也必须归档（到 `review/failure_cases/`，模板见 `docs/error_correction.md`）。

---

## 一、命名

`strategy_id` 格式：`<market>_<asset>_<style>_v<N>`。

| 示例 | 含义 | 阶段 |
|---|---|---|
| `cn_etf_rot_v1` | A 股 ETF 轮动 v1 | Phase 1 |
| `cn_etf_sector_v1` | A 股行业 ETF 轮动 v1 | Phase 2 候选 |
| `cn_stk_qvm_v1` | A 股个股 QVM v1 | Phase 2 候选 |
| `cn_event_pead_v1` | A 股公告事件 v1 | Phase 2 候选 |

---

## 二、目录结构

源码：

```
src/strategies/<group>/<strategy_id>/
  ├─ signal.py
  ├─ params.yaml          # 参数表 + 经济逻辑说明
  ├─ README.md            # 策略卡片（CLAUDE.md §4 的 12 项）
  └─ tests/               # 策略级集成 + 烟雾测试
```

归档输出：

```
reports/strategy_archive/<strategy_id>/<run_id>/
  ├─ manifest.json
  ├─ equity_curve.parquet
  ├─ trades.parquet
  ├─ holdings.parquet
  ├─ metrics.json
  ├─ ic_diagnostics.parquet
  └─ report.html
```

`run_id` 格式：`<YYYYMMDD-HHMM>-<short_hash>`。

---

## 三、manifest.json 必填字段

```json
{
  "strategy_id": "cn_etf_rot_v1",
  "run_id": "20260512-1430-a1b2c3",
  "git_commit": "<full sha>",
  "params_file": "src/strategies/etf_rotation/cn_etf_rot_v1/params.yaml",
  "params_hash": "<sha256>",
  "snapshot_version": "20260511-d4e5f6",
  "universe_config": "config/universe/cn_etf.yaml",
  "fees_config": "config/fees/default.yaml",
  "risk_config": "config/risk_limits/default.yaml",
  "run_started_at": "2026-05-12T14:30:00+08:00",
  "run_finished_at": "2026-05-12T14:35:21+08:00",
  "wall_clock_seconds": 321,
  "random_seed": 42,
  "metrics_summary": {
    "annualized_return": 0.0,
    "max_drawdown": 0.0,
    "sharpe": 0.0,
    "sortino": 0.0,
    "calmar": 0.0,
    "win_rate": 0.0,
    "turnover": 0.0,
    "trade_count": 0,
    "ic_mean": null,
    "rank_ic_mean": null
  },
  "promotion_decision": "pending | promote_to_paper | rework | retire",
  "promotion_reasoning": "<text>"
}
```

任何字段缺失 = 归档不完整 = 策略**不允许**进入模拟盘。

---

## 四、晋升门禁（Promotion Gate）

执行顺序硬约束：**回测 → 模拟盘 ≥ 3 个月 → 小资金实盘**。

| 门槛 | 进入条件 |
|---|---|
| 回测完成 | `CLAUDE.md §4` 的 12 项交付物齐备；7 条强制测试全绿；样本内 / 样本外 / walk-forward 方向一致 |
| 模拟盘开启 | 上述 + ADR `docs/adr/NNNN-promote-<strategy_id>-to-paper.md` 通过 |
| 模拟盘退出 | 至少 3 个月运行；执行偏差报告归档；偏差 < 阈值（阈值在 W11 确定） |
| 小资金实盘 | 上述 + ADR + 个人金额边界（见 `docs/research_questions.md §Q6.1`） |

晋升决策必须写入 `manifest.json` 的 `promotion_decision` 与 `promotion_reasoning` 字段。

---

## 五、退役（Retire）

策略失效判定（任一触发即停机审查，**不**加倍下注）：

- 滚动 12 个月超额显著为负；
- IC / Rank IC 连续多期翻负；
- 换手与滑点突然飙升；
- 容量显著下降；
- 核心逻辑依赖的制度或市场结构发生变化（例：沪市风险警示档位切换、印花税调整）。

具体阈值见 `docs/research_questions.md §Q5.3`。

退役流程：
1. 写 `review/failure_cases/<YYYYMMDD>-<strategy_id>-retire.md`；
2. 在最新归档的 `manifest.json` 中标 `promotion_decision = "retire"` 并写明原因；
3. **不允许**删除归档目录。

---

## 六、阶段进展记录

### 2026-05-13 — P1-W3-02 订单模型 MVP

- **任务**：`P1-W3-02 订单模型`
- **范围**：实现 `src/execution/order_model.py` 的最小订单状态机与撮合入口。
- **新增测试**：`tests/unit/test_order_model.py`
- **测试结果**：`pytest` 通过，`84 passed in 8.42s`。
- **当前支持**：市价单、限价单、开盘价撮合、涨停买入拒绝、停牌拒绝、容量上限导致的部分成交或拒绝。
- **当前不支持**：盘中逐笔撮合、订单排队、跨 bar 顺延、最小交易单位、费用计算、滑点模型；这些仍由后续 W3/W6/W8 任务接入。
- **架构约束**：订单模型不直接访问 `backtest/market_rules_cn.py`，交易制度判断通过 `execution/tradeability.py`。
- **晋升状态**：`pending`；该进展不构成策略晋升，也不允许进入模拟盘。

### 2026-05-14 — P1-W3-03 滑点模型 MVP

- **任务**：`P1-W3-03 滑点模型`
- **范围**：实现 `src/execution/slippage.py` 的确定性保守滑点模型，并将 `src/backtest/engine.py` 的成交价计算接入该模型。
- **新增 / 修改测试**：`tests/unit/test_slippage.py`、`tests/unit/test_engine_smoke.py`
- **测试结果**：聚焦测试 `pytest tests/unit/test_slippage.py tests/unit/test_engine_smoke.py -q` 通过，`8 passed`。
- **当前支持**：基础 bps、ATR 百分比、订单金额占 ADV 比例三部分滑点估算；买入上浮、卖出下浮；结果确定性；回测引擎成交价路径已调用 `execution.slippage`。
- **当前不支持**：真实滚动 ATR 预计算、容量削权、订单模型统一接入回测引擎、涨跌停价内成交价封顶、真实快照下的滑点回归校验。
- **架构约束**：滑点模型只估算价格冲击，不判断交易可行性、不计算费用、不修改策略参数。
- **晋升状态**：`pending`；系统仍不可靠，仍不允许进入模拟盘或下一阶段。

### 2026-05-14 — 回测引擎接入订单模型

- **任务**：降低 `src/backtest/engine.py` 与 `src/execution/order_model.py` 并行成交路径造成的架构债。
- **范围**：扩展 `order_model.ExecutionBar` 支持外部滑点成交价，并让 `engine._try_execute` 调用 `order_model.execute_order` 处理订单状态、涨跌停、停牌与退市拒绝。
- **新增 / 修改测试**：`tests/unit/test_engine_execution.py`、`tests/unit/test_engine_smoke.py`、`tests/regression/test_backtest_reproducible.py`
- **测试结果**：完整 `pytest` 通过，`102 passed in 8.35s`。
- **当前支持**：引擎成交路径已调用 `order_model.execute_order`；涨停买入、跌停卖出、停牌、T+1、费用、滑点和可复现性均有测试覆盖。
- **当前不支持**：容量约束仍未接入；订单模型尚未处理最小交易单位、涨跌停价内成交价封顶、跨 bar 顺延和真实快照下的成交回归。
- **架构约束**：交易可行性仍由 `execution/tradeability.py` 间接负责，费用仍由 `execution/fee_model.py` 负责，滑点仍由 `execution/slippage.py` 负责。
- **晋升状态**：`pending`；系统仍不可靠，仍不允许进入模拟盘或下一阶段。

### 2026-05-14 — P1-W8-03 容量约束 MVP

- **任务**：`P1-W8-03 容量约束`
- **范围**：实现 `src/portfolio/capacity.py` 的 ADV × N 容量上限，并将 `src/backtest/engine.py` 的订单执行接入 `max_trade_amount`，超限订单由 `order_model.execute_order` 产生 `partial_filled` 或容量拒绝。
- **新增 / 修改测试**：`tests/unit/test_capacity.py`、`tests/unit/test_engine_execution.py`、`tests/regression/test_backtest_reproducible.py`
- **测试结果**：完整 `pytest` 通过，`108 passed in 8.67s`。
- **当前支持**：根据历史成交额计算滚动 ADV；按 `ADV × n_capacity_pct` 限制单标的单日成交金额；超出容量时按比例部分成交；费用按实际成交金额计入；回测结果仍可复现。
- **当前不支持**：真实快照字段校验、组合层容量预削权、跨订单共享单日容量、涨跌停价内成交价封顶、最小交易单位在订单模型内统一处理。
- **架构约束**：容量模块只计算容量上限和削减结果，不判断交易可行性、不计算费用、不修改策略参数。
- **晋升状态**：`pending`；系统仍不可靠，仍不允许进入模拟盘或下一阶段。

### 2026-05-14 — P1-W6-03 复权一致性回归

- **任务**：`P1-W6-03 复权与价格一致性测试`
- **范围**：新增复权跳变场景回归测试，并将 `src/backtest/engine.py` 的估值、目标仓位现值与成交金额口径统一为 `price × adj_factor`；交易可行性仍使用原始开盘价与涨跌停价。
- **新增 / 修改测试**：`tests/regression/test_adjusted_price_consistency.py`、`tests/regression/test_backtest_reproducible.py`
- **测试结果**：完整 `pytest` 通过，`110 passed in 8.83s`。
- **当前支持**：动量因子使用复权收盘价；回测持仓估值在复权事件前后保持连续；回测成交金额和持仓现值使用同一复权口径。
- **当前不支持**：真实供应商复权因子口径校验、复权事件真实快照回归、成交数量与真实份额变动的更精细建模。
- **架构约束**：本次不修改策略参数、不优化收益、不新增策略；交易可行性、费用、滑点、容量仍分别由既有模块负责。
- **晋升状态**：`pending`；系统仍不可靠，仍不允许进入模拟盘或下一阶段。

### 2026-05-14 — P1-W4-04 AKShare 字段口径回归测试

- **任务**：`P1-W4-04 AKShare 字段口径回归测试`
- **范围**：新增 AKShare ETF 日线字段契约回归测试，并实现 `src/data/akshare_adapter.py` 的本地标准化函数 `normalize_etf_daily`；本次不联网、不拉取真实数据、不生成 snapshot。
- **新增 / 修改测试**：`tests/regression/test_akshare_contract.py`
- **测试结果**：完整 `pytest` 通过，`149 passed in 10.70s`。
- **当前支持**：将本地 AKShare 样例字段 `日期/开盘/最高/最低/收盘/成交量/成交额/涨停/跌停/停牌/复权因子` 标准化为项目 `prices_daily` schema；校验必填字段、日期、PIT 边界、OHLC 合法性、正复权因子、非负成交量与正成交额。
- **当前不支持**：AKShare 网络拉取、raw 层落地、reference 层生成、snapshot 版本化、真实供应商复权口径交叉验证、ATR 字段生产。
- **架构约束**：数据适配器只负责字段标准化和校验，不判断交易规则、不计算因子、不修改策略参数、不参与收益优化。
- **晋升状态**：`pending`；该任务只补齐真实快照前的数据契约底座，系统仍不可靠，仍不允许进入模拟盘或下一阶段。
