# 工程规范

> 配套阅读：`CLAUDE.md`（宪法）、`tests/README.md`（测试规范）。
> 任何与 `CLAUDE.md` 冲突的内容，以 `CLAUDE.md` 为准。

---

## 一、代码规范

### 1.1 语言与版本

- Python ≥ 3.11，启用 `from __future__ import annotations`。
- 所有新代码使用 **type hints**；公开函数参数、返回值必须标注。
- 函数 / 类必须有 docstring；docstring 包含输入契约、输出契约、副作用说明（如有）。

### 1.2 静态检查

- `ruff` 作为 linter + formatter，line-length=100；启用规则集：E, F, I, B, UP, SIM, RUF。
- `mypy --strict`；不允许 `Any`，必要时显式 `cast`。
- `pre-commit` 包含 ruff、mypy、pytest -m unit 三步。

### 1.3 命名

- 模块：snake_case；类：PascalCase；常量：UPPER_SNAKE。
- 时间字段统一：日期 = `date`（`datetime.date`）；时间戳 = `ts`（aware datetime，时区 = Asia/Shanghai 或 America/New_York，**禁止 naive datetime**）。
- 点时点字段统一：`asof_date`（研究"当下"日期）、`effective_date`（数据正式可用日期）、`announcement_date`（公告发布日期）、`report_period`（财报所属期）。

### 1.4 错误处理

- 不允许 `except:` 或 `except Exception:` 静默吞掉；必须显式声明异常类型，并 log。
- 不允许 print；用 `structlog` 或 `logging`，关键路径输出 JSON。
- 不允许"成功路径里的 try"：try 仅包住可能失败的最小块。

### 1.5 配置

- 配置文件统一用 YAML，放 `config/`；用 pydantic 模型加载校验。
- 任何硬编码常量（费率、阈值、时间窗口）都必须迁入配置。
- 配置 schema 变更必须更新 `docs/data_contracts.md` 和对应测试。

### 1.6 依赖

- 运行依赖与开发依赖分离；版本固定到 minor。
- 新增依赖必须在 ADR 中说明理由与备选方案。
- 禁止"only-for-this-feature"的偏门依赖。

---

## 二、回测规范

### 2.1 撮合层是唯一通道

- 所有"是否能成交"判断必须经过 `execution/tradeability.py`。
- 策略代码 / 因子代码 / 信号代码**禁止**自行判断涨跌停、停牌、T+1。
- 用静态检查保证：`tests/regression/test_no_bypass_tradeability.py` 通过 import 关系扫描。

### 2.2 时间戳契约

- 所有 DataFrame 输入输出含 `asof_date`；信号生成函数签名必须接收 `asof_date`。
- 任何"未来字段"必须通过 `effective_date <= asof_date` 才可见。
- 引擎不允许在 `t` 日访问 `t+1` 及之后的任何数据；违反则单元测试 fail。

### 2.3 复权

- 复权处理在引擎内部完成；因子层与策略层只见点时点价格。
- 除权日前后净值必须连续——`test_adjusted_price_consistency` 验证。

### 2.4 可复现

- 任何回测调用必须传入 `snapshot_version`；引擎记录到结果 manifest。
- 同一 `(strategy_id, params, snapshot_version)` 两次运行结果**byte-for-byte 一致**。
- 任何随机性（采样、扰动）都必须固定 seed，seed 写入 manifest。

### 2.5 调仓与成本

- 调仓周期默认周频；变更需在 `params.yaml` 中显式声明。
- 印花税仅卖出收（A 股股票）；ETF 默认不收印花税（按品类配置）。
- 滑点用保守模型作默认；激进模型只在样本外做敏感性分析。

### 2.6 容量

- 单标的单日成交量上限默认 = 该标的 20 日 ADV 的 N 倍（N 在配置中，默认保守）。
- 超过容量时按比例削权，**不**抬高滑点掩盖容量问题。

---

## 三、防未来函数规范（Lookahead Prevention）

### 3.1 数据层

- `data/raw/` 永不改写；每个文件名带日期后缀。
- `data/snapshots/YYYYMMDD/` 是回测唯一可用来源。
- 行业分类、指数成分、ETF 主数据都按 `effective_date` 切片存储。
- 退市股票留在样本中，仅在 `is_delisted_at(asof_date)` 后被剔除。

### 3.2 因子层

- 每个因子函数签名：`f(asof_date, snapshot_path, ...) -> DataFrame[asset, asof_date, effective_date, value]`。
- 因子代码**禁止**从全局变量读取数据；所有数据通过参数注入。
- 财务因子必须按 `announcement_date` 入模；公告在收盘后发布的，T+1 才可见。
- 每个因子必配一条 `tests/lookahead/test_<factor>_truncation.py`：截断未来数据，输出不变。

### 3.3 信号 / 策略层

- 信号函数签名同因子层；不允许直接读 `data/raw/`，只允许读快照。
- 策略 `signal.py` 不许调用 `pandas.DataFrame.shift(-1)` 或任何向未来移位的操作；ruff 自定义规则 + grep CI 拦截。

### 3.4 测试层

- `tests/lookahead/` 是独立目录；每次提交都跑。
- 任意一条 lookahead 测试失败 = block 合并。

---

## 四、目录与单文件规则

### 4.1 一策略一目录

```
strategies/<strategy_id>/
  ├─ signal.py
  ├─ params.yaml
  ├─ README.md       # 策略卡片（假设/风险/适用市场/失效条件/下一步）
  └─ tests/          # 策略级测试（少量集成测试 + 烟雾测试）
```

### 4.2 一因子一文件

- `factors/<name>.py` 只导出一个公开函数；私有 helper 命名前缀 `_`。
- 因子文件**禁止**导入策略代码或回测引擎。

### 4.3 报告归档

```
reports/strategy_archive/<strategy_id>/<YYYYMMDD-HHMM>/
  ├─ manifest.json   # 含 git_commit, params, snapshot_version, runtime
  ├─ equity_curve.parquet
  ├─ trades.parquet
  ├─ metrics.json
  └─ report.html
```

### 4.4 失败案例

- 任何被淘汰的实验都必须在 `review/failure_cases/<YYYYMMDD>-<short>.md` 留档；
- 模板见 `docs/templates/bug_record.md`（W2 内补齐）。

---

## 五、Git 与 ADR

### 5.1 分支与提交

- 主分支：`main`，禁止直接 push；通过 PR 合并。
- 分支命名：`feat/<short>`、`fix/<short>`、`docs/<short>`、`exp/<short>`。
- 提交信息：祈使句开头；72 列以内；正文写"为什么"，不写"做了什么"。

### 5.2 PR 自检表（贴在 PR 描述里）

```
- [ ] CLAUDE.md 所列约束未被破坏
- [ ] 新增 / 修改的因子配有 lookahead 测试
- [ ] tests/{unit,regression,lookahead,rule_simulation} 全绿
- [ ] 回测 smoke test 通过
- [ ] 如改了交易制度，沪市风险警示切换日的参数化测试通过
- [ ] 如改了配置 schema，docs/data_contracts.md 已同步
- [ ] 涉及决策的变更已开 ADR
```

### 5.3 ADR

- 路径：`docs/adr/NNNN-title.md`。
- 模板：背景 → 决策 → 备选方案 → 推翻条件 → 影响范围。
- 触发 ADR 的情形：工具链变更、数据源切换、回测规则修改、策略上线 / 下线 / 失效判定。

### 5.4 标签与发版

- 每完成一周（W1..W12）的退出准则后打 tag：`v0.1-w<NN>`。
- Phase 1 退出后打 `v1.0-phase1`。

---

## 六、研究实验管理

### 6.1 实验 ID

- 实验编号 = `exp-<YYYYMMDD>-<short>`；放在 `notebooks/exp-.../` 或 `scripts/exp-.../`。
- 实验完成后必须**或者**晋升到 `factors/` / `strategies/`，**或者**归档到 `review/failure_cases/`；不允许游离。

### 6.2 笔记本规则

- `notebooks/` 仅用于探索性研究；进入版本控制前必须 strip output。
- 任何写 csv / parquet 的代码不允许写到非 `data/interim/` 之外的位置。

### 6.3 参数搜索

- 参数搜索只允许在 in-sample；out-of-sample 仅供评估。
- 搜索过程日志（每次试验的参数与结果）必须落地到 `reports/factor_diagnostics/<exp_id>/trials.parquet`。
- 最终选定参数前 / 后的 in/out-of-sample 表现都要写入 ADR。

---

## 七、安全与机密

### 7.1 凭证

- 任何 API 密钥（券商、数据源）只通过环境变量或 `.env`（被 `.gitignore` 排除）。
- 严禁把 token 写进代码、配置或测试 fixture。
- pre-commit 加 `detect-secrets` 兜底。

### 7.2 个人数据

- 实盘账户、持仓、资金量级不进入 git；仅放 `~/.quant-private/`，由本地脚本读取。
- 报告中涉及实盘的数字必须脱敏（按百分比，而非绝对金额）。

---

## 八、性能与资源

- 单次回测内存 ≤ 4GB；超过需说明。
- Parquet + DuckDB 是首选；pandas 仅在面向小数据时使用。
- 任何"全量回测"的 wall-clock 时间记录入 manifest；同一 commit 上回归慢 > 30% 需要给出原因。

---

## 九、文档规范

- 任何 ADR、roadmap、task_queue、research_questions 的修改都必须在 PR 中说明动因。
- 每周结束（按 roadmap.md 周次）写一份 `review/weekly/<YYYY-WW>.md`：上周完成、未完成、阻塞、下周计划。
- 必须保持以下文档为最新：`CLAUDE.md`、`docs/roadmap.md`、`docs/task_queue.md`、`docs/data_contracts.md`、`tests/README.md`、`docs/research_questions.md`。

---

## 十、违规处理

- 任何一次违反 §三 防未来函数规范 = 立即回滚相关 commit + 归档到 `review/failure_cases/`。
- 任何一次"在测试集上调参" = 该次研究结果作废，且 ADR 必须记录为反面教材。
- 任何一次跳过失败测试 = 整次 PR 被拒，重做。
