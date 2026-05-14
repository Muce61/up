# up — Personal Quantitative Stock Research System

> **当前阶段：Phase 1 — A 股 ETF / 指数轮动。**
> 本仓库的最高规则是 [`CLAUDE.md`](./CLAUDE.md)；一切代码、文档、实验都必须服从它。

---

## 一句话

把交易决策固化成可回测、可审计、可复盘的代码与流程。**不**预测明天涨停，**不**做 AI 荐股，**不**做高频。

---

## 快速开始

```bash
# Python 3.11+
python -m venv .venv && source .venv/bin/activate

# 安装（推荐 pip + editable）
pip install -e ".[dev]"

# 或使用 uv
uv sync

# 测试
pytest

# Lint + 类型检查
ruff check .
mypy src
```

---

## 代码组织（src/ 布局）

`pyproject.toml` 把 `src/` 设为包根。磁盘路径与导入路径的对应：

| 磁盘 | 导入 |
|---|---|
| `src/backtest/market_rules_cn.py` | `from backtest.market_rules_cn import ...` |
| `src/factors/momentum.py` | `from factors.momentum import ...` |
| `src/execution/tradeability.py` | `from execution.tradeability import ...` |

> `CLAUDE.md` 中提到的 `backtest/market_rules_cn.py`、`execution/tradeability.py` 等是**模块路径**，实际文件位于 `src/` 下。

---

## 顶层目录

```
.
├─ CLAUDE.md            最高开发规则（项目宪法）
├─ README.md            本文件
├─ pyproject.toml       包定义与工具配置（ruff/mypy/pytest）
├─ requirements.txt     兼容入口（实际依赖在 pyproject.toml）
├─ .python-version      3.11
├─ .gitignore
│
├─ src/                 源码（src 布局，包根）
│  ├─ data/             数据接入、点时点快照、字段口径
│  ├─ factors/          单因子定义（Phase 1 仅启用 momentum/low_vol/liquidity）
│  ├─ strategies/       策略目录根
│  │  └─ etf_rotation/  Phase 1 唯一策略组
│  ├─ backtest/         回测引擎；market_rules_cn.py 是交易制度唯一定义点
│  ├─ execution/        撮合可行性、订单、滑点、费用；tradeability.py 是唯一访问入口
│  ├─ risk/             黑名单、上限、停机规则
│  ├─ portfolio/        组合优化、风险预算、容量约束
│  ├─ reports/          报告生成代码
│  └─ review/           复盘 / 归因 / 失败处理代码
│
├─ data/                数据分层
│  ├─ raw/              原始下载，永不改写
│  ├─ interim/          解析后中间产物
│  ├─ processed/        清洗后的可用数据
│  ├─ feature_store/    点时点因子表
│  ├─ reference/        交易日历、主数据、退市档案
│  └─ snapshots/        点时点快照（回测唯一可用来源）
│
├─ config/              配置（YAML，pydantic 校验）
│  ├─ universe/         资产池
│  ├─ fees/             费率
│  ├─ risk_limits/      风控阈值
│  └─ strategy_params/  策略参数
│
├─ tests/               测试金字塔
│  ├─ unit/
│  ├─ regression/
│  ├─ lookahead/        防未来函数（每因子 ≥ 1 条）
│  ├─ rule_simulation/  交易制度（含 7 条强制白名单）
│  └─ fixtures/         固定测试数据
│
├─ reports/             报告输出（生成产物，不入源码）
│  ├─ daily/
│  ├─ weekly/
│  ├─ backtest/
│  └─ strategy_archive/<strategy_id>/<run_id>/
│
├─ review/              复盘归档（手写文档，入库）
│  ├─ failure_cases/    失败实验记录（CLAUDE.md §6 强制）
│  └─ playbooks/
│
└─ docs/                规则、路线、契约、研究记录
   ├─ deep-research-report.md   研究依据（必读）
   ├─ roadmap.md                12 周路线图
   ├─ task_queue.md             Phase 1 任务队列
   ├─ engineering_rules.md      工程规范
   ├─ backtest_rules.md         回测细则
   ├─ data_contract.md          数据契约
   ├─ strategy_archive.md       策略归档规范
   ├─ error_correction.md       Bug / 偏差记录模板
   ├─ research_questions.md     悬而未决问题
   └─ adr/                      架构决策记录
```

---

## 文档索引

- 项目宪法 → [`CLAUDE.md`](./CLAUDE.md)
- 12 周路线图 → [`docs/roadmap.md`](./docs/roadmap.md)
- 任务队列 → [`docs/task_queue.md`](./docs/task_queue.md)
- 工程规范 → [`docs/engineering_rules.md`](./docs/engineering_rules.md)
- 回测细则 → [`docs/backtest_rules.md`](./docs/backtest_rules.md)
- 数据契约 → [`docs/data_contract.md`](./docs/data_contract.md)
- 策略归档 → [`docs/strategy_archive.md`](./docs/strategy_archive.md)
- 偏差记录模板 → [`docs/error_correction.md`](./docs/error_correction.md)
- 研究问题 → [`docs/research_questions.md`](./docs/research_questions.md)
- 测试规范 → [`tests/README.md`](./tests/README.md)
- 研究依据 → [`docs/deep-research-report.md`](./docs/deep-research-report.md)

---

## 边界提醒

- 严格 **回测 → 模拟盘 ≥ 3 个月 → 小资金实盘**，禁止跳级。
- Phase 1 仅 ETF/指数轮动；其他策略（行业轮动、多因子、事件驱动）需通过 Phase Gate 后启动。
- 任何对接真实券商账户的代码都需要单独 ADR 与人工确认。
