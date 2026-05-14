# 测试规范

> 本文档说明：本项目必须具备哪些测试、如何组织、如何运行。
> 上游：`CLAUDE.md §六`（强制测试白名单）、`docs/engineering_rules.md §三`（防未来函数）。

测试是宪法生效的具体形式。规则写在 CLAUDE.md 是约束，**必须由测试自动验证**才会变成现实。

---

## 一、测试金字塔

```
tests/
├─ unit/             # 单元测试：函数级、纯逻辑、毫秒级
├─ regression/       # 回归测试：跨模块契约、数据源口径、架构约束
├─ lookahead/        # 防未来函数：截断未来数据后输出不变
├─ rule_simulation/  # 交易制度撮合测试：T+1/涨跌停/停牌/退市/费用
├─ fixtures/         # 共享测试数据（小、固定、可 diff）
└─ README.md         # 本文件
```

### 1.1 各层用途

- **unit**：单函数 / 单类；不依赖网络；不依赖真实数据；用 fixtures 注入；目标 < 50ms / 用例。
- **regression**：跨模块或跨契约；包括数据源字段口径、架构约束（如"不能绕过 tradeability"）、复权一致性。
- **lookahead**：每个因子至少一条；构造"未来数据可见"的反例，断言输出**不应**因此变化。
- **rule_simulation**：撮合层制度测试；覆盖 7 条强制白名单。
- **fixtures**：小而稳定的样例数据；用 parquet / yaml / json；新增前先评估是否能复用。

### 1.2 选择规则

- 优先单元测试；只有用单元测试表达不了的契约才升级到 regression。
- 任何"复现 bug"的测试都先进 `regression/`。

---

## 二、必须存在的强制测试白名单（7 条）

这 7 条测试是 Phase 1 退出准则之一。**任一未通过 = 策略禁止进入报告层与模拟盘**。

| # | 测试函数 | 位置 | 验证 | 创建在 |
|---|---|---|---|---|
| 1 | `test_limit_up_buy_blocked` | rule_simulation | 涨停时买单被拒 | W2 |
| 2 | `test_limit_down_sell_blocked` | rule_simulation | 跌停时卖单被拒 | W2 |
| 3 | `test_suspended_security_untradeable` | rule_simulation | 停牌时双向不可成交 | W2 |
| 4 | `test_cn_stock_t_plus_one` | rule_simulation | A 股股票 / 股票 ETF 当日买入不可当日卖出；T+0 品类允许 | W2 |
| 5 | `test_fundamental_release_lag_enforced` | lookahead | 财务字段按 announcement_date 入模；T 日收盘后公告，T+1 才可见 | W2 占位 / W4 启用 |
| 6 | `test_delisted_names_survive_history` | regression | 历史样本保留 ST/*ST / 退市股票；不允许"清洗后回填" | W4 |
| 7 | `test_no_future_prices_in_signal` | lookahead | 在 t 日访问 t+1 价格的所有路径都失败 | W4 |

每条测试的源码位置由对应周的任务（见 `docs/task_queue.md`）创建；本文件是接口契约。

---

## 三、命名与组织约定

### 3.1 文件命名

- 测试文件以 `test_` 开头。
- 一个被测模块对应一个测试文件：`backtest/market_rules_cn.py` ↔ `tests/unit/test_market_rules_cn.py`。
- 跨模块契约放 `regression/`；不依附具体模块。

### 3.2 用例命名

- 用 `test_<被测函数>_<场景>_<期望>` 三段式：`test_limit_band_chinext_returns_20pct`。
- 反例显式标注：`test_xxx_raises_when_yyy`。

### 3.3 markers

- `pytest.mark.unit`、`pytest.mark.regression`、`pytest.mark.lookahead`、`pytest.mark.rule_simulation`、`pytest.mark.slow`。
- 默认 `pytest` 跑所有非 `slow`；`make smoke` 单跑 unit；CI 全跑。

---

## 四、Fixtures 约定

- 所有 fixtures 放 `tests/fixtures/`；按用途分子目录（`prices/`、`calendar/`、`etf_master/`、`announcements/`）。
- 优先使用 **parquet**；YAML 用于配置类 fixture。
- 大小约束：单个 fixture ≤ 100KB；超过的需 ADR 说明。
- Fixture 必须可 diff：禁止生成时间戳，禁止用 `now()`。
- 同一份 fixture 在不同测试中可复用，但**禁止**测试之间互相依赖。

---

## 五、运行规范

### 5.1 本地

```bash
make test       # 所有非 slow 测试
make smoke      # 仅 unit + smoke
pytest -m lookahead         # 仅防未来函数
pytest -m rule_simulation   # 仅撮合规则
```

### 5.2 提交前

- pre-commit 钩子运行 unit。
- 提交本身必须 lint + type + unit 全绿。

### 5.3 PR 前

- `make lint && make type && make test` 全绿。
- 必要时 `pytest --slow` 跑慢测试。
- 报告需附在 PR 描述里。

### 5.4 失败处理

- **禁止 skip**、**禁止 xfail 掉头**、**禁止注释掉**。
- 测试失败 → 定位根因 → 修复 → 重跑；如修复时间超 30 分钟，先开 issue / ADR。

---

## 六、覆盖率与质量门槛

- 单元测试覆盖率：`backtest/`、`execution/`、`factors/`、`portfolio/` 模块行覆盖 ≥ 85%；分支覆盖 ≥ 70%。
- 防未来函数测试：每个因子文件至少 1 条；每个数据访问入口至少 1 条。
- 制度模拟测试：7 条白名单 + 至少 5 条边界测试（费用、复权、退市整理、容量、最小成交额）。

> 覆盖率不是目标，是底线。覆盖率高但测试都在测 happy path 仍属于失败。

---

## 七、特殊测试主题

### 7.1 浮点对比

- 一律用 `pytest.approx` 或 `numpy.testing.assert_allclose`；禁止 `==` 比较浮点。

### 7.2 时间相关

- 禁止用 `datetime.now()`、`pd.Timestamp.now()`；改用 `freezegun` 或注入 `clock` 依赖。

### 7.3 随机数

- 用 `numpy.random.default_rng(seed=...)`；seed 在测试 fixture 中固定。
- 任何用 hypothesis 做属性测试的，seed 也要固定。

### 7.4 网络与外部 API

- 单元测试**不许**访问网络；用 mock。
- 数据源契约测试（AKShare）用本地缓存的样例 + 定期人工刷新。

---

## 八、本项目"测试是合规层"

下列规则不是"应该"测，是"必须"测；不通过则不允许进入下一阶段：

1. `tests/lookahead/*` 全绿——否则**禁止**策略代码上线（W5 起）。
2. `tests/rule_simulation/*` 全绿——否则**禁止**回测引擎进入策略测试阶段（W2 退出准则）。
3. `tests/regression/test_no_bypass_tradeability.py` 通过——否则**禁止**新增策略目录（W3 起）。
4. `tests/regression/test_phase2_factors_locked.py` 通过——确保 Phase 2 因子在 Phase 1 期间不被误用（W5 起）。

测试失败的处理路径见 `docs/engineering_rules.md §十`。
