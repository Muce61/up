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

```text
src/strategies/<group>/<strategy_id>/
  ├─ signal.py
  ├─ params.yaml
  ├─ README.md
  └─ tests/
```

归档输出：

```text
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

## 三、策略回测 manifest.json 必填字段

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

退役流程：
1. 写 `review/failure_cases/<YYYYMMDD>-<strategy_id>-retire.md`；
2. 在最新归档的 `manifest.json` 中标 `promotion_decision = "retire"` 并写明原因；
3. **不允许**删除归档目录。

---

## 六、数据快照 manifest.json 必填字段

P1-W4-03 引入 `data/snapshots/<snapshot_version>/manifest.json`。该 manifest 不等同于策略回测 manifest，但会被后续策略归档引用。

```json
{
  "snapshot_version": "20260512-<content_hash>",
  "created_at": "2026-05-12T00:00:00+08:00",
  "asof_date": "2026-05-12",
  "source_raw_dates": ["20260512"],
  "input_files": ["20260512/510300.SH.csv"],
  "file_hashes": {
    "raw/20260512/510300.SH.csv": "<sha256>",
    "snapshot/prices_daily.csv": "<sha256>"
  },
  "schema_version": "prices_daily.v1",
  "row_counts": {"prices_daily": 0},
  "min_date": "2026-05-11",
  "max_date": "2026-05-12"
}
```

要求：
- `snapshot_version` 由 `asof_date + schema_version + input_file_hashes + prices_daily_hash` 确定性生成；
- `prices_daily.csv` 只允许包含 `effective_date <= asof_date` 且 `trade_date <= asof_date` 的行；
- `file_hashes` 同时记录 raw 输入和 snapshot 输出，用于追踪与校验；
- 同一输入连续两次生成的 `snapshot_version`、`prices_daily.csv` hash、`manifest.json` hash 必须一致。

---

## 七、阶段进展记录

### 2026-05-13 — P1-W3-02 订单模型 MVP

- **任务**：`P1-W3-02 订单模型`
- **范围**：实现 `src/execution/order_model.py` 的最小订单状态机与撮合入口。
- **测试结果**：`pytest` 通过，`84 passed in 8.42s`。
- **晋升状态**：`pending`；该进展不构成策略晋升，也不允许进入模拟盘。

### 2026-05-14 — P1-W3-03 滑点模型 MVP

- **任务**：`P1-W3-03 滑点模型`
- **范围**：实现 `src/execution/slippage.py` 的确定性保守滑点模型，并将成交价计算接入回测引擎。
- **测试结果**：聚焦测试通过，`8 passed`。
- **晋升状态**：`pending`；系统仍不可靠，仍不允许进入模拟盘或下一阶段。

### 2026-05-14 — 回测引擎接入订单模型

- **范围**：让 `engine._try_execute` 调用 `order_model.execute_order` 处理订单状态、涨跌停、停牌与退市拒绝。
- **测试结果**：完整 `pytest` 通过，`102 passed in 8.35s`。
- **晋升状态**：`pending`。

### 2026-05-14 — P1-W8-03 容量约束 MVP

- **任务**：`P1-W8-03 容量约束`
- **范围**：实现 `src/portfolio/capacity.py` 的 ADV × N 容量上限，并接入订单执行。
- **测试结果**：完整 `pytest` 通过，`108 passed in 8.67s`。
- **晋升状态**：`pending`。

### 2026-05-14 — P1-W6-03 复权一致性回归

- **任务**：`P1-W6-03 复权与价格一致性测试`
- **范围**：新增复权跳变场景回归测试，并统一估值、目标仓位现值与成交金额口径为 `price × adj_factor`。
- **测试结果**：完整 `pytest` 通过，`110 passed in 8.83s`。
- **晋升状态**：`pending`。

### 2026-05-14 — P1-W4-04 AKShare 字段口径回归测试

- **任务**：`P1-W4-04 AKShare 字段口径回归测试`
- **范围**：新增 AKShare ETF 日线字段契约回归测试，并实现 `src/data/akshare_adapter.py` 的本地标准化函数 `normalize_etf_daily`。
- **测试结果**：完整 `pytest` 通过，`149 passed in 10.70s`。
- **晋升状态**：`pending`；该任务只补齐真实快照前的数据契约底座。

### 2026-05-15 — P1-W4-03 点时点快照流水线

- **任务**：`P1-W4-03 点时点快照流水线`
- **范围**：实现 `src/data/snapshot.py`，从 `data/raw/{date}/` 以及兼容的 `data/raw/{vendor}/{date}/` 读取本地 CSV raw 文件，生成 `data/snapshots/{snapshot_version}/prices_daily.csv` 与 `manifest.json`。
- **新增 / 修改文件**：
  - `src/data/snapshot.py`
  - `scripts/snapshot.py`
  - `tests/regression/test_snapshot_pipeline.py`
  - `docs/strategy_archive.md`
- **当前支持**：
  - 自动发现 raw CSV；
  - 调用 `normalize_etf_daily` 复用 AKShare 字段契约；
  - 按 `asof_date` 对原始 `日期` 字段预截断，禁止未来行情进入 snapshot；
  - 稳定排序与确定性 CSV 输出；
  - 确定性 `snapshot_version`；
  - `manifest.json` 记录 `snapshot_version`、`created_at`、`source_raw_dates`、`input_files`、`file_hashes`、`schema_version`、`row_counts`、`min_date`、`max_date`。
- **新增测试**：`tests/regression/test_snapshot_pipeline.py`
  - `test_snapshot_manifest_exists`
  - `test_snapshot_generation_is_reproducible`
  - `test_snapshot_truncates_rows_after_asof_date`
  - `test_snapshot_rejects_missing_required_raw_field`
  - `test_snapshot_output_columns_match_data_contract`
- **测试结果**：本地最小复现环境执行 `pytest tests/regression/test_snapshot_pipeline.py -q` 通过，`5 passed in 0.45s`。
- **当前不支持**：AKShare 网络拉取、真实 raw 样例缓存、reference 层生成、Parquet 输出、真实供应商复权口径交叉验证。
- **架构约束**：不修改策略逻辑、不修改参数、不触碰 Phase 2；该任务只补齐点时点数据快照底座。
- **晋升状态**：`pending`；该进展不构成策略晋升，也不允许进入模拟盘。
