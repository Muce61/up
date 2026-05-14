# Phase 1 任务队列（A 股 ETF 轮动）

> 顺序与依赖严格执行。每个任务的"验收准则"必须由测试或脚本自动验证。
> 进度同步在项目内置 Task 工具中跟踪；本文件是**任务定义的唯一来源**。

ID 命名规则：`P1-<WW>-<NN>`，例如 `P1-W2-01`。

---

## P1-W1 工程环境

### P1-W1-01 初始化 pyproject + 依赖矩阵
- **依赖**：无
- **交付**：`pyproject.toml`（Python ≥ 3.11）；运行依赖（pandas / numpy / pyarrow / duckdb / pydantic / pyyaml / akshare）与开发依赖（pytest / ruff / mypy / pre-commit / hypothesis）分离。
- **验收**：`python -c "import pandas, numpy, pyarrow, duckdb, pydantic, yaml"` 成功；`pip install -e ".[dev]"` 在干净环境通过。
- **估算**：2h

### P1-W1-02 代码规范与 Git Hook
- **依赖**：P1-W1-01
- **交付**：`ruff.toml`（line-length=100, select=E/F/I/B/UP/SIM/RUF）；`mypy` strict 模式；`pre-commit` 含 ruff/mypy/pytest -m unit。
- **验收**：`pre-commit run --all-files` 在空仓库通过；故意提交不合规代码被拦截。
- **估算**：2h

### P1-W1-03 Makefile / 任务入口
- **依赖**：P1-W1-01
- **交付**：`make setup`、`make lint`、`make type`、`make test`、`make smoke`、`make snapshot`。
- **验收**：每个 target 在空仓库下返回 0；`make help` 列出所有 target。
- **估算**：1h

### P1-W1-04 ADR-0001 工具链选择
- **依赖**：P1-W1-01
- **交付**：`docs/adr/0001-tooling.md`，记录为什么选 ruff/mypy/duckdb/akshare 等。
- **验收**：包含决策、备选方案、推翻条件三部分。
- **估算**：1h

---

## P1-W2 A 股交易制度建模

### P1-W2-01 涨跌幅与板块映射
- **依赖**：P1-W1-*
- **交付**：`backtest/market_rules_cn.py` 中实现 `limit_band(security, date) -> (up_pct, down_pct)`；按主板 10% / 创业板 20% / 科创板 20% / 风险警示 5% 配置化；沪市风险警示 2026-07-06 切换为参数。
- **验收**：`tests/rule_simulation/test_limit_band.py` 覆盖以上四类 + 切换日。
- **估算**：3h

### P1-W2-02 T+1 / T+0 分类
- **依赖**：P1-W2-01
- **交付**：`settlement_lag(security_type) -> int`；股票 ETF 默认 T+1，债券 / 黄金 / 跨境 / 货币 ETF T+0；配置在 `config/universe/cn_etf.yaml`。
- **验收**：`test_cn_stock_t_plus_one` 通过。
- **估算**：2h

### P1-W2-03 涨停买不进 / 跌停卖不出 / 停牌不可交易
- **依赖**：P1-W2-01
- **交付**：`is_tradeable(security, date, side) -> bool`；考虑涨停、跌停、停牌、退市整理。
- **验收**：`test_limit_up_buy_blocked`、`test_limit_down_sell_blocked`、`test_suspended_security_untradeable` 通过。
- **估算**：3h

### P1-W2-04 费用模型骨架
- **依赖**：P1-W2-01
- **交付**：`fee_schedule(security_type)` 返回 `{commission, stamp_tax, transfer_fee, min_commission}`。
- **验收**：单元测试覆盖至少 3 个边界（最小佣金、印花税仅卖出收、跨境 ETF 不收印花税）。
- **估算**：2h

---

## P1-W3 撮合可行性与成本模型

### P1-W3-01 tradeability 总入口
- **依赖**：P1-W2-*
- **交付**：`execution/tradeability.py`，回测引擎与策略层访问交易规则的**唯一**接口。
- **验收**：架构测试 `tests/regression/test_no_bypass_tradeability.py` 通过——回测引擎所有调用都经过此模块（用 import 关系扫描）。
- **估算**：2h

### P1-W3-02 订单模型
- **依赖**：P1-W3-01
- **交付**：`execution/order_model.py`：限价单、市价单、收盘价成交假设；订单状态机。
- **验收**：单元测试 ≥ 6 条覆盖正常成交、部分成交、被涨跌停拒绝、被停牌拒绝、超过成交额上限。
- **估算**：4h

### P1-W3-03 滑点模型
- **依赖**：P1-W3-01
- **交付**：`execution/slippage.py`：默认基于 ATR 与成交额的保守模型；参数化。
- **验收**：1000 笔随机订单的回归测试，结果可复现（固定 seed）。
- **估算**：3h

### P1-W3-04 费用模型完整版
- **依赖**：P1-W2-04
- **交付**：`execution/fee_model.py`：佣金 / 印花税 / 过户费 / 最低佣金 / 最小成交额。
- **验收**：单元测试覆盖 ≥ 8 条边界。
- **估算**：3h

---

## P1-W4 数据底座与点时点快照

### P1-W4-01 AKShare 适配器
- **依赖**：P1-W1-*
- **交付**：`scripts/fetch_akshare.py`：按日期拉取 ETF 日线、成份、行业；落到 `data/raw/{date}/`。
- **验收**：连续两次抓取产生相同 hash；网络失败重试 3 次后给出明确错误。
- **估算**：4h

### P1-W4-02 交易日历与主数据
- **依赖**：P1-W4-01
- **交付**：`data/reference/trading_calendar.parquet`、`etf_master.parquet`。
- **验收**：日历跨度覆盖 2010–2026；主数据字段对齐 `docs/data_contracts.md`。
- **估算**：3h

### P1-W4-03 点时点快照流水线
- **依赖**：P1-W4-01
- **交付**：`scripts/snapshot.py`：从 `data/raw/` 生成 `data/snapshots/YYYYMMDD/`，带数据版本号与 manifest。
- **验收**：`test_no_future_prices_in_signal` 启用并通过。
- **估算**：5h

### P1-W4-04 AKShare 字段口径回归测试
- **依赖**：P1-W4-01
- **交付**：`tests/regression/test_akshare_contract.py`：用本地缓存的样例校验字段名、复权方式、缺失值策略。
- **验收**：故意改变上游字段时测试失败。
- **估算**：3h

### P1-W4-05 docs/data_contracts.md
- **依赖**：P1-W4-01
- **交付**：每个字段一行：名称 / 来源 / 复权方式 / 单位 / 缺失值策略 / `effective_date` 处理。
- **验收**：被 P1-W4-04 引用；新增字段必须更新此文件（pre-commit 校验）。
- **估算**：2h

---

## P1-W5 因子原语（ETF 用子集）

### P1-W5-01 动量因子
- **依赖**：P1-W4-03
- **交付**：`factors/momentum.py`：3 / 6 / 12 月动量；函数签名 `momentum(asof_date, window, snapshot_path) -> DataFrame`。
- **验收**：`tests/lookahead/test_momentum_truncation.py`——截断 asof_date 之后的数据后输出不变。
- **估算**：3h

### P1-W5-02 低波因子
- **依赖**：P1-W4-03
- **交付**：`factors/low_vol.py`：20 / 60 日实现波动率。
- **验收**：lookahead 测试通过；与教科书定义对账。
- **估算**：2h

### P1-W5-03 流动性因子
- **依赖**：P1-W4-03
- **交付**：`factors/liquidity.py`：ADV、20 日平均成交额、最小流动性阈值。
- **验收**：lookahead 测试通过；阈值可配置。
- **估算**：2h

### P1-W5-04 因子输出 schema 校验
- **依赖**：P1-W5-01..03
- **交付**：所有因子输出必须含 `[asset, asof_date, effective_date, value]` 四列。
- **验收**：`tests/unit/test_factor_schema.py` 用 pydantic 校验。
- **估算**：1h

### P1-W5-05 Phase 2 因子占位锁
- **依赖**：无
- **交付**：`factors/{value,quality,growth,dividend,event_features}.py` 写入 `raise NotImplementedError("Phase 2+")`。
- **验收**：`tests/regression/test_phase2_factors_locked.py` 验证调用即抛出。
- **估算**：0.5h

---

## P1-W6 回测引擎 v0.1

### P1-W6-01 引擎事件循环
- **依赖**：P1-W3-*、P1-W5-*
- **交付**：`backtest/engine.py`：日级事件循环；周频调仓；所有撮合走 `tradeability`。
- **验收**：固定 fixtures 下输出 byte-for-byte 一致；smoke test 在 `tests/unit/test_engine_smoke.py` 中通过。
- **估算**：6h

### P1-W6-02 回测 CLI
- **依赖**：P1-W6-01
- **交付**：`scripts/run_backtest.py --strategy <id> --from --to --snapshot <ver>`。
- **验收**：CLI 集成测试通过。
- **估算**：2h

### P1-W6-03 复权与价格一致性测试
- **依赖**：P1-W6-01
- **交付**：`tests/regression/test_adjusted_price_consistency.py`：除权日前后净值连续。
- **验收**：通过。
- **估算**：2h

---

## P1-W7 策略 v0 资产池与信号

### P1-W7-01 ETF 资产池配置
- **依赖**：P1-W4-*
- **交付**：`config/universe/cn_etf.yaml`：≥ 10 只 ETF，含宽基、行业、债券、黄金、跨境，每只标 T+1/T+0、上市日期、停牌历史链接。
- **验收**：`tests/unit/test_universe_config.py` 校验 schema + 每只 ETF 有完整字段。
- **估算**：3h

### P1-W7-02 cn_etf_rot_v1 signal
- **依赖**：P1-W5-*、P1-W7-01
- **交付**：`strategies/etf_rotation/cn_etf_rot_v1/signal.py`：横截面动量 + 趋势过滤；输出标的得分。
- **验收**：lookahead 测试通过；输出 schema 一致。
- **估算**：4h

### P1-W7-03 策略卡片
- **依赖**：P1-W7-02
- **交付**：`strategies/.../README.md`（假设 / 风险 / 适用市场 / 失效条件 / 下一步）+ `params.yaml`。
- **验收**：模板齐全；CI 检查必填字段。
- **估算**：1h

---

## P1-W8 组合层与风控

### P1-W8-01 权重优化器
- **依赖**：P1-W7-02
- **交付**：`portfolio/optimizer.py`：按得分 → 目标权重；单标的上限、行业上限、目标波动率。
- **验收**：单元测试 ≥ 4 条覆盖权重和=1、上限不被突破、行业暴露受控。
- **估算**：4h

### P1-W8-02 风险预算与回撤减仓
- **依赖**：P1-W8-01
- **交付**：`portfolio/risk_budget.py`：组合波动率目标 + 回撤阈值减仓。
- **验收**：人造回撤场景下减仓动作触发。
- **估算**：3h

### P1-W8-03 容量约束
- **依赖**：P1-W8-01
- **交付**：`portfolio/capacity.py`：ADV 的 N 倍上限（N 可配，默认保守）。
- **验收**：人造高换手场景下被容量约束削权。
- **估算**：2h

---

## P1-W9 Walk-Forward 与参数稳健性

### P1-W9-01 walk-forward 框架
- **依赖**：P1-W6-01
- **交付**：`backtest/walk_forward.py`：滚动窗口；in-sample 选参，out-of-sample 评估。
- **验收**：单元测试覆盖窗口切分 + 时间序列不泄漏。
- **估算**：4h

### P1-W9-02 参数扰动
- **依赖**：P1-W9-01
- **交付**：`scripts/param_perturbation.py`：对动量窗口、波动率目标、调仓频率 ±20% 扰动；输出热力图数据。
- **验收**：脚本可重入；输出确定性。
- **估算**：3h

---

## P1-W10 报告层 + 因子诊断

### P1-W10-01 必报指标面板
- **依赖**：P1-W6-01
- **交付**：报告生成器；指标列见 `CLAUDE.md §七`。
- **验收**：固定输入下报告 byte-for-byte 一致。
- **估算**：4h

### P1-W10-02 因子诊断
- **依赖**：P1-W5-*
- **交付**：IC / Rank IC、分层收益、相关矩阵。
- **验收**：人工对账一遍；用 fixture 重现。
- **估算**：3h

---

## P1-W11 模拟盘接口与执行偏差度量

### P1-W11-01 broker 适配抽象
- **依赖**：P1-W6-01
- **交付**：`execution/broker_adapters/base.py`、`paper_trade.py`。
- **验收**：paper-trade 在历史回放数据上与回测引擎结果偏差 < 0.1%。
- **估算**：5h

### P1-W11-02 执行偏差度量
- **依赖**：P1-W11-01
- **交付**：偏差度量指标 + 报告。
- **验收**：人造偏差场景被检测出。
- **估算**：3h

### P1-W11-03 模拟盘启动条件清单
- **依赖**：P1-W11-01
- **交付**：`docs/paper_trade_plan.md` + 自动检查脚本。
- **验收**：脚本结论 = 人工核对结论。
- **估算**：2h

---

## P1-W12 阶段评审与封存

### P1-W12-01 Phase 1 评审报告
- **依赖**：P1-W10-*、P1-W11-*
- **交付**：`review/phase1_review.md`：表现 / 稳健性 / 容量 / 偏差 / 失败案例。
- **验收**：覆盖 Phase 1 退出准则的全部 6 项；ADR-0002 通过。
- **估算**：4h

### P1-W12-02 strategy_archive 封存
- **依赖**：P1-W12-01
- **交付**：`reports/strategy_archive/cn_etf_rot_v1/`：git commit、参数、快照版本、回测时间、结果摘要。
- **验收**：归档目录有 `manifest.json`，字段完整。
- **估算**：1h

### P1-W12-03 至少一个失败案例归档
- **依赖**：P1-W7-* 之后
- **交付**：`review/failure_cases/*.md`，按 `docs/templates/bug_record.md` 写。
- **验收**：归档不少于 1 份；包含根因与防御措施。
- **估算**：1h

---

## 全局完成总线

Phase 1 结束 = 上述任务**全部** done，且 `CLAUDE.md §二` Phase 1 退出准则的 5 条同时满足。
