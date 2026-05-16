# 数据契约

> 本文档定义本项目所有数据字段的来源、单位、口径、时间戳处理。
> 上游：`CLAUDE.md §2`（研发硬约束）、`docs/engineering_rules.md`。
> **任何新增字段或更改口径必须先更新本文件并通过 regression 测试。**

---

## 一、时间字段标准

Step 1 冻结范围内，所有业务日期字段在 Python 代码中必须使用 `datetime.date`；落地 CSV 时使用 ISO `YYYY-MM-DD` 字符串，加载后必须还原为 `datetime.date` 再进入 schema 校验。所有时间戳字段必须显式声明时区，**禁止 naive datetime**。Phase 1 A 股数据统一按 `Asia/Shanghai` 解释。

| 字段 | 类型 | 含义 | 时区 |
|---|---|---|---|
| `asof_date` | date | 研究"当下"日期，决定哪些数据可见 | Asia/Shanghai |
| `effective_date` | date | 数据正式可用日期；`effective_date ≤ asof_date` 才可访问 | Asia/Shanghai |
| `announcement_date` | date | 公告发布日期（财务/事件类数据生效日） | Asia/Shanghai |
| `report_period` | date | 财报所属期；**禁止**用此字段直接回填历史 | Asia/Shanghai |
| `trade_date` | date | 交易日 | Asia/Shanghai |

**收盘后公告规则**：交易日 T 收盘后发布的公告，最早可用日为 `effective_date = next_trade_date(T)`。

---

## 二、数据分层与路径

| 层 | 路径 | 写入策略 | 用途 |
|---|---|---|---|
| raw | `data/raw/{vendor}/{YYYYMMDD}/...` | 一次写入，**永不改写** | 上游原始落地；不得被回测直接读取 |
| interim | `data/interim/...` | 可改写 | 解析后中间产物 |
| processed | `data/processed/...` | 可改写 | 清洗后的可用数据 |
| feature_store | `data/feature_store/...` | 可改写 | 点时点因子表 |
| reference | `data/reference/...` | 入库 | 交易日历、主数据、退市档案；必须支持 `asof_date` 点时点过滤 |
| snapshots | `data/snapshots/{snapshot_version}/...` | 入库 | **回测唯一可用来源** |

`snapshot_version` 命名：`{YYYYMMDD}-{short_hash}`（如 `20260511-d4e5f6`）。

reference layer MVP 读取入口：

- `load_trading_calendar(path, asof_date)`：从 `trading_calendar.csv` 读取并按 `trade_date <= asof_date`、`effective_date <= asof_date` 返回可见交易日历。
- `load_etf_master(path, asof_date)`：从 `etf_master.csv` 读取并按 `effective_date <= asof_date`、`list_date <= asof_date` 返回可见 ETF 主数据，同时派生 `can_open_new_position`。
- reference CSV 只作为构建 snapshot 的输入；回测仍只能读取 snapshot。

---

## 三、核心表 schema（Phase 1 最小契约）

### 3.1 交易日历 `trading_calendar`

`trading_calendar` 属于 reference layer，必须能按 `asof_date` 做点时点过滤。

| 字段 | 类型 | 说明 |
|---|---|---|
| trade_date | date | 交易日 |
| is_open | bool | 是否开盘 |
| prev_trade_date | date \| null | 上一交易日；首行可为空 |
| next_trade_date | date \| null | 下一交易日；末行可为空 |
| market | str | `SH` / `SZ` / `BJ` |
| effective_date | date | 该交易日历记录正式可用日期；必须满足 `effective_date <= asof_date` 才可进入 snapshot |

约束：

- `trade_date <= asof_date` 才允许进入 snapshot。
- `effective_date <= asof_date` 才允许进入 snapshot；否则 schema 校验必须报错。
- `prev_trade_date < trade_date < next_trade_date`，首尾缺失时允许为空。
- `prev_trade_date` / `next_trade_date` 允许缺失值仅表示边界未知；禁止用 `1970-01-01`、空字符串或 `0` 占位。
- 日期字段在 DataFrame 中必须是 `datetime.date`，禁止字符串日期、naive datetime、`pd.Timestamp` 混用。
- 缺少任一必需字段时必须报出包含表名和字段名的明确错误。

### 3.2 ETF 主数据 `etf_master`

`etf_master` 属于 reference layer，是构建当时可见 universe 的最小依据。

| 字段 | 类型 | 说明 |
|---|---|---|
| symbol | str | 标准化代码（如 `510300.SH`） |
| name | str | 名称 |
| etf_type | str | `broad_index` / `sector` / `bond` / `gold` / `cross_border` / `money_market` |
| settlement | str | `T+1` / `T+0` |
| stamp_tax_applicable | bool | 印花税是否适用（默认 false） |
| list_date | date | 上市日期 |
| delist_date | date \| null | 退市日期；保留退市样本 |
| exchange | str | `SH` / `SZ` / `BJ` |
| effective_date | date | 该主数据记录正式可用日期；必须满足 `effective_date <= asof_date` 才可进入 snapshot |

约束：

- `effective_date <= asof_date` 的主数据记录才可见；传入 `asof_date` 做 schema 校验时，`effective_date > asof_date` 必须报错。
- 同一 `symbol` 存在多条主数据修订时，只允许使用 `effective_date <= asof_date` 中最新的一条。
- `list_date <= asof_date` 的 ETF 才允许进入当时可见 universe；`list_date > asof_date` 的 ETF 不得出现在可见 universe 中。
- `delist_date <= asof_date` 的 ETF **必须保留历史记录**，但不得作为新开仓标的。
- `filter_visible_etf_master(..., asof_date)` 的输出必须派生 `can_open_new_position`：
  - 未退市或 `delist_date > asof_date`：`true`；
  - 已退市，即 `delist_date <= asof_date`：`false`。
- 不允许用最新 ETF 主数据回填历史 universe。
- `delist_date` 允许为 null；其他必需字段不允许缺失，不允许用空字符串或 `0` 占位。
- 日期字段必须是 `datetime.date`，禁止字符串日期、naive datetime、`pd.Timestamp` 混用。

### 3.3 行情 `prices_daily`（点时点）

| 字段 | 类型 | 说明 |
|---|---|---|
| symbol | str | 标准化代码 |
| trade_date | date | 交易日 |
| open / high / low / close | float | 不复权价格 |
| adj_factor | float | 复权因子 |
| volume | int | 成交量 |
| amount | float | 成交额（元） |
| limit_up | float | 当日涨停价 |
| limit_down | float | 当日跌停价 |
| is_suspended | bool | 是否停牌 |
| effective_date | date | 数据正式可用日（一般 = trade_date） |

约束：

- `trade_date <= asof_date` 才允许进入 snapshot。
- `effective_date <= asof_date` 才允许进入 snapshot。
- `symbol` 必须能在同一 snapshot 的 `etf_master` 中找到当时可见记录。

#### 3.3.1 AKShare ETF 日线输入契约

`src/data/akshare_adapter.py` 只做本地字段标准化与校验，不联网、不写入快照、不被策略代码直接调用。

| AKShare 原始字段 | 标准字段 | 约束 |
|---|---|---|
| 日期 | `trade_date` | 可解析为 Asia/Shanghai 交易日期 |
| 开盘 | `open` | 正数，单位元 |
| 最高 | `high` | 正数，且不低于 `open/low/close` |
| 最低 | `low` | 正数，且不高于 `open/high/close` |
| 收盘 | `close` | 正数，单位元 |
| 成交量 | `volume` | 非负，单位份 |
| 成交额 | `amount` | 正数，单位元；容量约束与 ADV 计算使用该字段 |
| 涨停 | `limit_up` | 正数，单位元 |
| 跌停 | `limit_down` | 正数，单位元 |
| 停牌 | `is_suspended` | bool |
| 复权因子 | `adj_factor` | 正数；项目内复权价统一为 `price × adj_factor` |

标准化后自动补充：

- `symbol`：由调用方显式传入标准代码，例如 `510300.SH`。
- `effective_date`：ETF 日线行情默认等于 `trade_date`，且必须满足 `effective_date <= asof_date`。

输入与缺失值规则：

- AKShare raw 日期列可为 `YYYY-MM-DD` 字符串或可解析日期值，但进入标准化输出后必须为 `datetime.date`。
- 价格、成交额、复权因子不允许缺失、不允许为 0 或负数；成交量不允许缺失且必须非负。
- `停牌` 缺失时可按 `False` 处理；其他必需 raw 字段缺失必须报错。
- `最高` 必须不低于 `开盘/最低/收盘`，`最低` 必须不高于 `开盘/最高/收盘`。

raw 落地规则：

- AKShare ETF 日线 raw 必须写入 `data/raw/akshare/{YYYYMMDD}/{symbol}.csv`。
- raw 文件一旦写入即为审计输入，默认禁止覆盖；只有显式运维动作（例如 CLI `--overwrite`）才允许重建同一路径缓存，并必须重新生成 manifest/hash。
- raw 落地必须返回 SHA-256 hash 与行数，用于真实样例的复现、diff 与 manifest 校验。
- 同一 `{vendor}/{YYYYMMDD}` raw 目录必须生成 `raw_manifest.json`，至少包含：`vendor`、`asof_date`、`symbols`、`input.source`、`source`、`output_files`、`file_hashes`、`created_at`。
- `created_at` 在可复现测试中应可固定；默认按 `asof_date` 当天 `Asia/Shanghai` 零点生成，避免同一输入重复构建产生 manifest 漂移。

字段契约由 `tests/regression/test_akshare_contract.py` 与 `tests/regression/test_akshare_raw_cache.py` 锁定。缺失关键原始字段、非法价格、非法成交额、非法复权因子、违反 PIT 边界或默认覆盖 raw 时必须失败。

### 3.4 Snapshot 最小依赖

Phase 1 的 snapshot 是回测唯一可用来源。Step 1 冻结后，进入真实链路闭环的 snapshot 至少必须包含：

| 文件 | 说明 |
|---|---|
| `prices_daily.csv` | 点时点行情 |
| `trading_calendar.csv` | 点时点交易日历 |
| `etf_master.csv` | 点时点 ETF 主数据，包含 `can_open_new_position` |
| `manifest.json` | 输入文件、reference 文件、hash、schema version、行数、日期范围 |

约束：

- 回测不得直接访问 raw、interim、processed；snapshot 是回测唯一可用来源。
- snapshot 中所有带 `effective_date` 的表必须满足 `effective_date <= asof_date`。
- snapshot 中所有行情必须满足 `trade_date <= asof_date`。
- snapshot 中 `etf_master` 不得包含 `list_date > asof_date` 的 ETF。
- snapshot 必须保留已退市 ETF 的历史主数据，但 `can_open_new_position` 必须为 `false`。
- `manifest.json` 必须记录 `snapshot_version`、`asof_date`、输入 raw/reference 文件、SHA-256、schema version、行数、行情日期范围。
- reference 相关 manifest 字段必须包含 `reference_files`、`reference_hashes`、`reference_row_counts`；未提供 reference 输入时这些字段为空对象。
- snapshot 输出必须稳定排序、稳定列顺序，保证同一输入可复现、可 diff、可 hash 校验。

### 3.5 行业分类 `industry_mapping`

按 `effective_date` 切片存储。**禁止**用最新版本回填历史。

| 字段 | 类型 | 说明 |
|---|---|---|
| symbol | str | 代码 |
| industry_l1 | str | 一级行业 |
| industry_l2 | str | 二级行业 |
| effective_date | date | 此映射的生效日 |
| classification_version | str | 分类版本（如 `sw_2021`） |

### 3.6 退市档案 `delist_history`

| 字段 | 类型 | 说明 |
|---|---|---|
| symbol | str | 代码 |
| list_date | date | 上市日期 |
| delist_date | date | 退市日期 |
| reason | str | 退市原因 |
| delist_warning_dates | list[date] | 退市风险警示发布日列表 |

---

## 四、复权处理

- 引擎内部使用前复权计算收益；展示用按需切换。
- 除权日前后净值必须连续——`tests/regression/test_adjusted_price_consistency.py` 验证。
- 复权因子来源：交易所 / vendor 官方；**不允许**自行计算。

---

## 五、字段口径约束

| 主题 | 约束 |
|---|---|
| 价格 | 全部"元"为单位，浮点 |
| 成交量 | 整数"股"或"份"，不允许除权后强制对齐 |
| 成交额 | "元"，与 `volume × close` 在容差内一致；不一致需在 `data/interim/` 记录差异 |
| 财务数据 | 一律用 `announcement_date` 入模；`report_period` 仅展示 |
| 缺失值 | 不允许 `0` 占位；用 `null`/`NaN` |
| 类型 | 日期用 `datetime.date`；时间戳用 `pd.Timestamp(tz=...)`；禁止字符串日期混用；禁止 naive datetime |

---

## 六、变更流程

新增字段或更改口径：
1. 先在本文件 PR；
2. 同步更新 `tests/regression/test_*_contract.py`；
3. 受影响快照重新生成并打新版本号；
4. 写入 ADR `docs/adr/NNNN-data-contract-change.md`。
