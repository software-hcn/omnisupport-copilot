# Week 05 · Transform 与语义层：把业务口径做成受控工程接口

> **一句话**：让 BI、Agent、Eval、治理四方共享同一份指标口径——用 dbt 分层 + 证据链 + 本地 registry + 受控查询工具，把"指标 = SQL 结果"升级成"指标 = 可授权、可审计、可迁移的工程接口"。
>
> 讲义：`pdf/doc/week05-Transform 与语义层.pdf`（72 页 / 5 课时）

---

## 0. 本周主干

五节课是一条从"业务口径"到"Agent 可安全调用"的收窄链路，每一节都在给下一节减少自由度：

```
L01 Metrics       指标接口卡 16 字段        「口径是什么」
      ↓
L02 dbt Layers    sources/staging/int/marts  「事实从哪长出来」
      ↓
L03 Evidence      tests + docs + lineage + artifacts  「凭什么信它」
      ↓
L04 Semantics     metric_registry_v1.yml     「runtime 的事实来源」
      ↓
L05 Tool Guard    query_support_kpis_v1       「Agent 只能这样问」
      ↓
                  audit payload → Week06 编排 / Week08 评测 / Week10 治理
```

课程反复回扣的一句口诀，值得单独记住：

**schema 限"形状"，registry 限"语义"，guards 限"权限与成本"，参数化 SQL 限"确定性"，audit 限"可复盘"。**

另一句配套的判断：**grain（一行是什么）比 SQL 写法重要十倍——grain 错了，看着都对，全是错。**

---

## 1. L01 · 指标不是 SQL，是工程接口

### 核心论点

同一个"P1 工单数"，运营按 `created_at` 算、BI 按 `last_status_change_at` 把历史升级也算进来、客服按 `priority_changed_at` 加 SLA tier 过滤——三个 SQL 都跑得通，三个口径都"合理"，没有一个能被多方共识。**根因不是 SQL 写错，是时间字段、grain、filters 从未被约定过。**

LLM 把这件事从"开会吵"升级成"线上事故"：以前同名不同义的代价是运营吵半小时，现在是 Agent 用错口径自信地答了客户、写了报告、决策了退款。

### 把"指标"拆成三个工程对象

中文里都叫"指标"，生产里是三个东西，混掉就栽：

| 对象 | 回答什么 | 例子 | 混了的后果 |
|---|---|---|---|
| **metric**（指标） | 业务要复用、要解释的那个数字 | `p1_ticket_count` | 同名不同义 |
| **business definition**（业务口径） | 怎么算、什么粒度、什么时间窗、reopen 算不算 | `priority in (p1, p1_critical)` 且按 `created_date` | SQL 跑得通但口径漂 |
| **engineering interface**（工程接口） | 谁能查、怎么查、输出什么、如何审计 | `query_support_kpis_v1` + registry + `audit_id` | Agent 越界、不可复盘、不可评测 |

**metric 是名字，definition 是含义，interface 让多方对得齐。**

### 指标接口卡：16 字段最低集

课程的判断是"这张卡可以扩，不能减；删掉的字段就是事故种子"：

| 分组 | 字段 |
|---|---|
| 身份 | `metric_name` / `business_label` / `business_question` |
| 口径 | `business_definition` / `source_model` / `grain` / `measure_expression` / `time_field` |
| 边界 | `allowed_dimensions` / `allowed_filters` / `allowed_roles` |
| 责任与证据 | `owner` / `tests` / `docs_link` / `audit_fields` / `change_policy` |

### 上线前 10 问（任一答不出 = HOLD）

owner / grain / time field / filters / dimensions / tests / docs / lineage / roles / agent gate。**HOLD 一个指标，比修一次事故便宜十倍；HOLD 不是失败，是工程纪律。**

### 四条最常见的误信

| 你大概率信过 | 现实是 |
|---|---|
| 指标就是 SQL | 指标是定义 + 来源 + 粒度 + 测试 + 文档 + 权限 + 接口的合体 |
| Dashboard 显示了就够 | Agent / Eval / 治理 / 复盘要用同一口径 |
| SQL 改了大家同步一下 | 没有 lineage 和 docs，影响范围不可控；旧口径能被消费半年没人发现 |
| Agent 会自己写对 SQL | 它会"高自信地"写出能跑、口径错、越权、不可审计的 SQL |

配套的一条设计判断：`first_resolution_rate` 被故意留成 `experimental_proxy`（"已解决且未升级 / 已解决"），真实生产要接入 reopen 事件后重定义。**能诚实地标"这是代理口径"，比偷偷上线高级一万倍**——这个标记后面直接变成 runtime 的一道闸。

---

## 2. L02 · dbt 分层 = 污染隔离 + 消费边界 + 影响可定位

### 核心论点

分层不是目录命名，是给"变化"画边界。一次上游把 `status` 从 `"In Transit"` 改成 `IN_TRANSIT`，下游 14 处同时挂（BI 看板、cron 报表、stored procedure、Python 脚本、Hive 视图、对账接口），修复全靠 grep——因为没有 sources 声明、没有依赖图、没有枚举测试。dbt 的价值就是让 SQL 拥有代码的属性：依赖、测试、文档、可复现命令。

### dbt is / is not

| 你可能以为 | 其实 | 它真正负责的 |
|---|---|---|
| dbt 是数据库 / BI / 采集工具 | 不存数据、不画图、不负责 EL | SQL transform 的工程框架，承接已加载的数据再加工 |
| dbt 是 SQL 文件夹 | 只堆 SQL 不叫 dbt | 依赖、测试、文档、DAG、artifacts |
| dbt = 语义层 | dbt 本身不暴露指标 API | 语义层定义的事实来源 |

### 四层各自"绝对不该做的事"

这是本节最实用的一张表：

| 层 | 可以做 | 坚决不做 | 本项目物化 |
|---|---|---|---|
| **sources** | 声明物理上游表、挂 `not_null`/`unique`、配 freshness | 不 cast、不 rename、不写 case-when、不让 dashboard 直连 | — |
| **staging** | rename / cast / 枚举标准化、派生纯类型布尔（`is_open`/`is_p1`/`sla_breached`）、PII 打标不删数据 | 不做 group by 聚合、不写 dashboard 专用字段、不做跨表业务 JOIN | view |
| **intermediate** | JOIN ticket + customer + comment，派生业务事实（`first_response_minutes` / `backlog_age_days` / `is_first_resolution_proxy`） | 不直接给 BI / Agent 消费、不做最终聚合 | view |
| **marts** | 对外契约：说清"一行是什么 + 谁消费 + 不能暴露什么" | 不塞越多越好，字段"刚好够下游用" | table（safe view 除外） |

判断标准：**"派生布尔 OK，聚合 KPI 不 OK"是 staging 与 intermediate/marts 的最重要分界。** 最常见的反模式是 staging 里出现 group by——把事故种子种在最深的那一层。

### grain 对照表

| grain | 一行是什么 | 错了会怎样 |
|---|---|---|
| case grain | 一个 support case | 复开率分母混乱；reopen 被重复算 |
| daily activity grain | 某天 × 某类活动 × 某维度组合 | 历史升级重复计；漏掉时区 |
| metric row grain | 某指标 × 某日期 × 某维度组合 | 不同指标混到同一行；列错位 |
| query result grain | 工具返回的结构化结果 | Agent 汇总错维度；图表说谎 |
| snapshot grain | 某时刻的当前状态快照 | 把"已关闭"算成"当前打开" |

### 三个 mart 的分工

| mart | grain | 谁消费 | 不能暴露什么 |
|---|---|---|---|
| `support_case_mart` | 一个 support case | 分析师 / BI 做 case-level 切片 | `contact_email` / `phone` / subject 全文 / comment body |
| `support_kpi_mart` | metric × date × 维度组合 | 11 个指标全走它，本周最核心 mart | 同上 |
| `agent_tool_input_view` | 白名单 metric 的安全行 | Agent 唯一能读的对象 | 物理上不存在 `ticket_id` / `customer_id` / 正文列 |

### 宽表 → 长表的翻转

`support_kpi_mart` 的核心手法是 PostgreSQL 的 `cross join lateral values`，把日粒度宽表翻转成 `metric_name + metric_value` 的长表：

```sql
from daily
cross join lateral (
    values
        ('ticket_count', daily.ticket_count::numeric),
        ('p1_ticket_count', daily.p1_ticket_count::numeric),
        ('sla_breach_rate', daily.sla_breach_rate::numeric)
        -- 11 个指标一次性翻转
) as metrics(metric_name, metric_value)
where metrics.metric_value is not null
```

长表骨架的工程意义：新增指标只是多一行 `values`，白名单、测试、registry 都按 `metric_name` 一个维度扩展，不用改表结构。

### 物化选型

口诀：**staging / intermediate 默认 view（便宜）；marts 默认 table（稳定）；大表才考虑 incremental，不是越大越 incremental**；`ephemeral` 留给只被 1-2 个模型引用的中间步骤，本周两者都不用。

**safe view 必须是 view**：它要实时跟上 mart 的最新构建，做成 table 就有"两份数据"的隐患。

---

## 3. L03 · 能跑 ≠ 能交付：四件证据

### 核心论点

一个"工单数"指标，运营说 +18%、产品说 +6%，差异全在 reopen 算不算。进去问三个问题——owner 是谁、docs 在哪、变更过几次——没人能答，SQL 是离职同事 2017 年写的。**坏点不是 SQL 写错，是没人能解释、没人能追责、没人能复盘。**

**能跑的 mart 不该被消费，除非它带着证据进系统。** 四件凑齐才叫一次交付：

| 证据 | 证明什么 | 内容 |
|---|---|---|
| tests | 明显破坏的事情没发生 | generic + singular + unit + freshness |
| docs | 未来的消费者读得懂 | grain + 字段含义 + 时间语义 + 消费者清单 |
| lineage | 变更影响可定位 | `manifest.json` + DAG |
| artifacts | 交付可验收 | manifest / catalog / run_results / sources |

### dbt 四层测试各保护一类东西

| 类别 | 怎么写 | 保护什么 | 本周示例 |
|---|---|---|---|
| Generic | 在 `schema.yml` 字段下挂 `not_null` / `unique` / `accepted_values` / `relationships` | 主键、关键字段、枚举漂移、外键完整 | `ticket_id` unique；`metric_name` 在 11 个白名单内 |
| Singular | 在 `tests/` 写 SELECT，返回任何一行 = 失败 | 跨字段业务断言、安全边界 | `no_pii_columns_in_agent_tool_input_view` / `ratio_metrics_between_0_and_1` / `metric_values_non_negative` |
| Unit（dbt 1.8+） | `unit_tests` 给输入打桩验证 SQL 逻辑 | 复杂 case-when、升级判定、reopen 规则 | 讲义要求，仓库未落地（见第 7 节） |
| Source Freshness | `sources.yml` 配 `loaded_at_field` | 上游断流在工程层被发现 | 讲义要求，仓库未落地（见第 7 节） |

**真正保护口径的是"业务断言 + 自定义 + unit test"，不是 `not_null` 的数量。** 堆 `not_null` 凑覆盖率是"表演性安全"。

### docs 的第一性问题

`schema.yml` 必写四件事：model description（一行 grain）、字段含义 + 时间语义、边界（不能怎么用）、消费者清单。评审时只问一句：**"如果消费者把这个字段算错了，他能不能从文档里看出来？"** 答不出"能"，docs 就不够。

### lineage 是变更影响入口，不是装饰图

看 DAG 要追问"改了它，谁会因为我而变"。三个样例影响链：

| 你改了什么 | 下游可能受影响 | 必须同步更新的工件 |
|---|---|---|
| `stg_tickets.is_p1` 定义 | 所有用 priority / `p1_ticket_count` 的 mart 与看板 | schema.yml / docs / registry / tool examples |
| `int_support_cases.first_response_minutes` | `avg_first_response_minutes` / SLA 看板 / Agent 工具 | tests / docs / registry / impact note |
| `support_kpi_mart` 加新指标 | safe view / registry / tool contract | safe view 白名单 + `accepted_values` test + registry validator |

### 四份 artifacts

| artifact | 位置 | 记录什么 | 本周怎么用 |
|---|---|---|---|
| `manifest.json` | `analytics/target/` | 所有节点、依赖、tests、元数据 | 抽 lineage 做影响分析；CI 比对前后差异 |
| `catalog.json` | `analytics/target/` | 仓库里真实 schema、列、类型 | 回填 dbt docs 站点；比对模型与仓库 |
| `run_results.json` | `analytics/target/` | 每次 run/build/test 的状态、耗时、错误 | build evidence 的事实来源 |
| `sources.json` | `analytics/target/` | source freshness 检查结果 | 上游断流预警 |

**交付物里不允许只有"build 通过"截图。**

### metric_ready 七道闸

`build pass`（先修模型，不要 patch 测试）→ `tests pass`（修业务逻辑，不要 disable test）→ `docs complete`（补字段 description）→ `lineage clear`（补 impact note）→ `registry entry`（补 registry 条目）→ `safe view available`（修 safe view + 加 no_pii test）→ `audit fields ready`（补输出契约与审计字段）。任一缺失 = HOLD。

### 评审直接拒签的六类反模式

只贴 build 截图；`schema.yml` 只有字段名没有 description；只贴 DAG 图不给影响清单；tests 全是 `not_null`；mart 改了 registry 没同步（Agent 用旧白名单"成功"地拿到错数据）；safe view 没配 PII 测试。

---

## 4. L04 · 语义层现实主义：先立内核，再谈平台

### 核心论点

某客户花 60 万美元/年订阅托管语义层，定义 300 个指标；一年后 BI 实际用 78 个、Agent 用 31 个，剩下 191 个有定义、有 owner、没人用，且半数说不清 grain。**坏点不在平台，在组织还没准备好**——`metric_name` 没统一、grain 没人能讲清，买了 SaaS 也救不了。

判断不是反平台，是反"跳过准备就买票"。**语义层的核心从来不是用哪家，是"你公司里同名指标能不能不变意思"。**

### 语义层五个工程对象

| 术语 | 它是什么 | 它不是什么 | 本项目例子 |
|---|---|---|---|
| semantic model | 实体 + 维度 + 度量的语义结构 | 不是 dashboard，也不是单条 SQL | support_case / ticket_activity |
| entity | 业务里能被连接的对象主键 | 不是所有字段 | `ticket_id` / `customer_id` / `org_id` |
| dimension | 用来切分或过滤的属性 | 不是任意 where 条件 | `product_line` / `priority` / `category` |
| measure | 可聚合的基础值 | 不是最终业务指标 | `ticket_count` / `sla_breach_count` |
| metric | 面向业务消费的最终指标 | 不是 SQL 片段 | `p1_ticket_count` / `sla_breach_rate` |
| semantic graph | 语义对象之间的关系 | 不是漂亮的图 | case — customer — activity |

混了这五个词，就读不懂 MetricFlow / dbt SL / Cube 的文档，也设计不出合格的 registry。

### 核心 vs 外延

必做的是 **Semantic Core**（`metric_name` / grain / dimensions / filters / roles + window）和 **Local Registry**（`metric_registry_v1.yml` + 版本号 + owner + sensitivity）；**Tool Contract** 在 L05 收口。**Semantic Model Draft**（entity / measure 的准 MetricFlow 形态）和 **Managed SL**（dbt SL / Cube / OSI）是迁移目标，不是本周硬要求。核心立住了，迁到任何平台都只是"换前端"。

四方案按五维（本地可跑 / 语义一致性 / 工具边界 / 迁移性 / 运维成本）评：dashboard SQL only 五项皆低；dbt marts only 中等；**local metric registry 前四项全高、运维成本中**；托管语义层语义与边界高，但迁移性看标准、运维成本高。所以本周选 local registry。

### registry 是 runtime contract，每个字段都是决策点

| 字段 | 回答什么 | 缺失后果 |
|---|---|---|
| `metric_name` | 请求哪个指标 | unknown metric 漂移 |
| `owner` | 出问题谁负责 | 事故无人认领 |
| `source_model` / `safe_view` | 从哪个 mart、哪个安全视图查 | 下游猜表 / 越权读 PII |
| `time_dimension` / grain | 时间字段、一行是什么 | 时间错；重复或漏计 |
| `allowed_dimensions` / `allowed_filters` | 能按什么切、按什么过滤 | 维度越权；任意 where |
| `allowed_roles` | 哪些角色能查 | 越权访问 |
| `max_window_days` | 能查多久 | 成本爆 / 滥用 |
| `sensitivity` / `definition_status` | 敏感级、是否实验代理 | 代理口径被静默当生产用 |
| `quality_tests` | 哪些测试在保护它 | 不可验收 |

### v1.1 的升级姿势：加字段，不改字段

指标从 6 个扩到 11 个，registry 每个指标加 `owner`/`unit`/`metric_type`/`formula`/`sensitivity`/`definition_status`/`version`/`quality_tests`，tool contract 加 `trace_id`/`purpose`/`actor_org_ids`/`include_experimental_metrics`，runtime 加 `audit_id`/`policy_applied`/`data_freshness`/组织范围过滤/实验指标确认。**旧调用全兼容——这是版本演进的标准姿势。**

### HOLD 也是工程能力，迁移路径分五步

六种该 HOLD 的情形：关键 tests 未过、维度未授权（如 `assignee_id` 涉及员工绩效）、`max_window_days` 未定怕扫表、safe view 或 no_pii test 没守住、grain 还不稳定、owner 不明确。

迁移路径：local registry → semantic model draft（MetricFlow YAML）→ MetricFlow validate → managed SL 或按 OSI 导出 → BI/Agent/Eval 共享。三条原则：任何阶段不丢五个核心字段（`metric_name` / grain / `allowed_dimensions` / `allowed_filters` / `allowed_roles` + `max_window_days`，这也正是跨厂商标准想统一的最低集合）；过渡期 registry 与 semantic model 双写一段时间；迁移后监控指标级 diff、下游延迟、成本曲线。

---

## 5. L05 · 不让 Agent 裸写 SQL

### 核心论点

某客户 Agent 上线三个月后，数据库 query log 里出现大量 `customer_email = ...` 明文查询——客服把邮箱贴进提示词，Agent 为了"更好回答"把它当过滤条件写进 SQL，DBA 备份系统又把这些查询固化下来。修复花 11 周，其中 8 周是合规审查与客户通知，总成本是整套工具治理预算的 6 倍。

结论：**Agent 永远不能写 SQL。不是它能力不够，是它没法对结果负责。**

受控工具不是"SQL 安全壳"，它从根上换了接口形状——**你直接把 SQL 拿走，只给它一个能传"指标 + 维度 + 时间窗"的入口。**

### 六类风险 → 六道 guard

| 风险 | 具体表现 | 对应 guard |
|---|---|---|
| 口径漂移 | 同名指标 SQL 不同 | metric registry + `accepted_values` |
| 越权访问 | 查到邮箱、评论正文、未授权维度 | role policy + safe view |
| 注入 / 非法过滤 | Agent 接受任意 where | filter whitelist + 参数化 SQL |
| 成本失控 | 365 天大窗口、全表扫、limit 失控 | `max_window_days` + limit cap |
| 审计缺失 | 不知道谁查了什么 | audit payload + `trace_id` + `release_id` |
| 不可复现 | SQL 每次生成不同 | 参数化 SQL + `idempotency_key_fields` |

### 为什么 Structured Outputs strict 还不够

Function Calling 把工具的 JSON Schema 交给模型，strict 模式（`additionalProperties: false` + `required` 全列）能保证输出**形状**合法——`raw_sql` 这种字段彻底进不来。但 strict 不知道指标是否真实存在、角色能不能查、31 天窗口是否太长。**形状合法只是第一道闸，语义与权限必须 runtime 兜底。**

### 工具的"不是什么"

`query_support_kpis_v1` 是 registry-driven（从 `metric_registry_v1.yml` 读真相）、parameterized（只生成参数化 SQL）、structured + audit（返回结构化 rows + 审计字段）、idempotent（相同输入 → 相同结果）。它**不是** NL2SQL、不接受自然语言、不能选任意表任意字段、不接受 `raw_sql` 参数，也不是完整治理——HITL 与配额留给 Week10。

**工具的价值在"拒绝边界"，不在"灵活性"。**

### runtime 六步

`load`（schema + registry）→ `validate shape`（jsonschema strict）→ `check policies`（七道闸）→ `build SQL`（参数化 placeholder，只查 safe view）→ `execute`（asyncpg，失败兜 `DB_UNAVAILABLE`）→ `assemble`（rows + audit + `data_freshness` + `policy_applied`）。

每一步不可绕过；顺序本身就是设计——形状不合法就没必要查 registry，registry 没过就没必要建 SQL。

### 九种 denial_code

拒绝码不是失败，是接口能力——**它让 LLM 知道怎么改**：

| code | 触发条件 | 对 Agent 的提示 |
|---|---|---|
| `SCHEMA_VALIDATION_FAILED` | 输入不符合 JSON Schema | 改 payload 形状 |
| `ROLE_DENIED` | `actor_role` 不在 `allowed_roles` | 换角色或申请权限 |
| `METRIC_DENIED` | 指标未注册或角色不允许 | 换指标 / 申请白名单 |
| `DIMENSION_DENIED` | dimension 不在 `allowed_dimensions` | 改维度选择 |
| `FILTER_DENIED` | filter 字段不在 `allowed_filters` | 改过滤字段 |
| `WINDOW_TOO_LARGE` | 窗口超过 `max_window_days` | 缩小窗口 |
| `ORG_SCOPE_REQUIRED` | `support_ops` 没传 `actor_org_ids` | 补 org scope |
| `EXPERIMENTAL_METRIC_NOT_ACKNOWLEDGED` | 实验指标未确认 | 设 `include_experimental_metrics=true` |
| `DB_UNAVAILABLE` | 底层 DB 不可用 | 稍后重试或降级 |

### audit payload 的六个维度

**Who**（`actor_id` / `actor_role` / `trace_id` / `purpose`）、**What**（`metrics` / `dimensions` / `filters` / 日期区间 / `actor_org_ids`）、**Registry**（`registry_id` / `registry_version` / `safe_view`）、**Data**（`release_id` / `data_release_id` / `generated_at_max`）、**Outcome**（`row_count` / `denial_code` / `query_fingerprint`）、**Policy**（`policy_applied` 列表）。

**没有 audit 的工具调用不应进入生产**——出事后要能回答"谁查了什么、什么版本、走了哪些策略、得到什么结果"。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 分析路径决策记录 | `docs/blueprints/week05/analytics_path_v1.md` | 设计边界、目录映射、mermaid 数据链路 |
| L02 dbt 项目与连接配置 | `analytics/dbt_project.yml`<br>`analytics/profiles.yml`（`profiles.yml.example` 为模板） | 分层默认物化、`tags: ["week05", ...]`、`vars.week05_data_release_id`；连接全走 `env_var`，target schema 固定 `analytics` |
| L02 sources 层 | `analytics/models/sources.yml` | 四张上游表、只挂约束不做变形 |
| L02 staging 层 | `analytics/models/staging/stg_tickets.sql`<br>`stg_customers.sql` / `stg_ticket_comments.sql` / `stg_knowledge_docs.sql` | 枚举 `lower()` 标准化、`created_date` 派生、四个布尔（`is_open`/`is_resolved`/`is_escalated`/`is_p1`）+ `sla_breached`，无一处 group by |
| L02 intermediate 层 | `analytics/models/intermediate/int_support_cases.sql`<br>`int_ticket_activity_daily.sql` | 前者 case grain 派生业务事实，后者才做日粒度聚合 |
| L02 三个 mart | `analytics/models/marts/support_case_mart.sql`<br>`support_kpi_mart.sql` / `agent_tool_input_view.sql` | case mart 对比 `int_support_cases` 看哪些字段被**故意没选**（`customer_id`/`subject`/`error_codes`）；kpi mart 看长表翻转；safe view 看 `materialized='view'` + 11 个 `metric_name` 白名单 |
| L03 docs | `analytics/models/marts/schema.yml`<br>`staging/schema.yml` / `intermediate/schema.yml` | model description、`accepted_values` 的 11 个指标白名单 |
| L03 三个自定义 SQL 测试 | `analytics/tests/no_pii_columns_in_agent_tool_input_view.sql`<br>`ratio_metrics_between_0_and_1.sql` / `metric_values_non_negative.sql` | 分别守 PII 边界（查 `information_schema.columns`）、三个 rate 的 [0,1] 区间、八个 count/avg 的非负 |
| L03 build 证据 | `reports/week05/dbt_build_evidence.md` | 表格式验收记录：39/39、`metric_count=11`、五个正负例的 denial_code |
| L04 metric registry | `analytics/metric_registry_v1.yml`<br>`docs/blueprints/week05/metric_registry_contract_v1.md` | registry 级白名单 + 11 个指标的 v1.1 元数据；blueprint 里有字段作用表和通过标准 |
| L04 registry 校验器 | `analytics/scripts/validate_metric_registry.py` | `--json` 输出 `valid` / `metric_count` / `experimental_metric_count` |
| L05 tool contract | `contracts/tools/tools/query_support_kpis_v1.json`<br>`contracts/tools/tool_contract_schema.json` | `additionalProperties: false`、九个 `failure_codes`、`idempotency_key_fields`、`rate_limit`；后者是所有工具契约的元 schema |
| L05 runtime | `services/tool_api/app/kpi_query.py`<br>`app/metric_registry.py` / `app/routers/kpis.py` | `_validate_request()` 的闸门顺序、`_build_query()` 的参数化与聚合、`_audit()`；路由里 `actor_role` 与 `tenant_id` 由服务端 principal 覆写 |
| L05 测试 | `tests/contract/test_week05_metric_contracts.py`<br>`tests/integration/test_week05_metric_registry.py` / `test_week05_kpi_query_tool.py` | 契约侧断言 `raw_sql` 不在 properties；集成侧四类拒绝 + `"ticket_fact" not in query` + org/tenant scope |
| 实操命令 | `runbooks/week05/README.md`<br>`README.md` "Week05 Analytics Engineering 最小闭环" / `analytics/README.md` | runbook 十节完整命令含 v1.1 正负例 payload；README 给三条最小命令和边界说明 |

### 代码里几个值得单独看、但讲义没展开的细节

**1. safe view 比讲义版本"宽"，而且必须宽。** 讲义 p28 的 `agent_tool_input_view` 只选了 `metric_value` 和维度列，但仓库里的实际视图还额外带了 `ticket_count` / `resolved_ticket_count` / `first_resolution_count` / `first_response_count` / `handle_time_count` 等支撑列。原因在 `kpi_query.py`：跨维度重新聚合时，**预先算好的 rate 和 avg 不能直接 sum 或 avg**，否则得到"平均的平均"、分母权重全丢。所以 runtime 按 registry 的 `numerator`/`denominator`/`weight_column` 现场重算：

```python
if metric.numerator and metric.denominator:
    expression = (f"sum({metric.numerator})::numeric / "
                  f"nullif(sum({metric.denominator})::numeric, 0)")
elif metric.weight_column:
    expression = (f"sum(metric_value * {metric.weight_column})::numeric / "
                  f"nullif(sum({metric.weight_column})::numeric, 0)")
elif metric.aggregation == "sum":
    expression = "sum(metric_value)"
else:
    expression = "avg(metric_value)"
```

这就是 `policy_applied` 里那个讲义没提的 `semantic_aggregation` 标记。它也解释了为什么 registry 强制 ratio 指标必须声明 `numerator` 和 `denominator`——**那不是文档字段，是 runtime 的计算依据。**

**2. 多租户是讲义完全没提的一条数据边界。** `tenant_id` 贯穿 `stg_tickets` → `int_*` → 两个 mart → safe view，并在 tool contract 里被标注为"由产品服务注入，绝不接受浏览器传入"。`routers/kpis.py` 对 `actor_role` 和 `tenant_id` 采用**硬覆盖**——它们是服务端身份解析结果，客户端传什么都会被 principal 覆盖；而 `actor_org_ids` 目前仍来自 payload（课堂版妥协，contract 的 description 里写明生产应服务端派生）。这一层区分讲义没讲，但它是"哪些字段可以信客户端"的实战范例。

**3. 闸门实际顺序与讲义列的不同。** `_validate_request()` 的顺序是 schema → role → metric → **experimental** → dimension → filter → org scope → 日期合法性 → window。讲义 p66 把 experimental 排在最后。实际顺序更合理：指标层面的问题一次报完，再谈维度和窗口。另外 `date_to < date_from` 复用了 `SCHEMA_VALIDATION_FAILED`，没有单独的拒绝码。

**4. 两处硬编码的白名单镜像已经漂了。** `kpi_query.py` 里的 `SAFE_COLUMNS`（含 `tenant_id`）和 `validate_metric_registry.py` 里的 `SAFE_VIEW_COLUMNS`（不含 `tenant_id`）都是对 safe view 列集合的手写镜像，两份都没有真正解析 `agent_tool_input_view.sql`——所以改 safe view 时是**三处**要同步（视图本身 + 两份镜像）。这正是讲义 L03 说的"registry stale"反模式的现实版本，值得当作 impact note 的练习题。

**5. `SAFE_IDENTIFIER` 正则是第二层注入防线。** metric name 与 numerator/denominator/weight 列名会被拼进 SQL 的 `case when` 表达式（不能参数化），所以 `_build_query()` 用 `^[a-z][a-z0-9_]*$` 逐个校验，不合格直接抛 `ValueError`。也就是说：**registry 本身也被当作不完全可信的输入对待。**

**6. `data_release_id` 的兜底策略。** `support_kpi_mart` 写的是 `coalesce(data_release_id, '{{ var("week05_data_release_id") }}')`，var 默认值来自 `env_var('WEEK05_DATA_RELEASE_ID', 'week05-dev-local')`——上游有 release 就继承，没有才落到本地默认值。审计字段宁可有个可识别的假值，也不留 null。

---

## 7. 讲义与仓库对不上的地方

| 讲义写的 | 实际情况 |
|---|---|
| `docs/blueprints/week05/adr-week5-analytics-path.md` | 不存在，实际是 `docs/blueprints/week05/analytics_path_v1.md` |
| `docs/blueprints/week05/metric-interface-principles.md`（L01 交付物，也是指标卡 `docs_link` 示例） | 不存在。最接近的是 `docs/blueprints/week05/metric_registry_contract_v1.md`，但内容是 registry 字段契约，不是"指标接口原则" |
| `reports/week05/query_tool_examples.md` | 不存在 |
| `reports/week05/query_tool_audit_notes.md` | 不存在 |
| `reports/week05/lineage-impact-notes.md`（L03 交付物之一） | 不存在。讲义 p41 给了完整模板，但仓库里没有落地文件；要做这个练习得自己新建 |
| Source Freshness（`sources.yml` 配 `loaded_at_field`，"ticket_fact 24h 内必须有新数据"） | `analytics/models/sources.yml` 里**没有任何 freshness 配置**，所以 `dbt source freshness` 跑不出结果，`target/sources.json` 也不会有内容 |
| dbt Unit Test（`unit_tests`，"reopen 算不算"的 SQL 逻辑回归） | 全仓库没有 `unit_tests` 定义。四层测试实际只落地了 generic + singular 两层 |
| `schema.yml` 字段级 description（p36 示范了 `metric_date` / `metric_name` / `metric_value` / `data_release_id` 的说明文字） | 三份 `schema.yml` 只有 model 级 description，**字段全部只有 tests 没有 description**。按讲义 p42 的标准，这正是它自己点名的"empty docs"反模式 |
| `runbooks/week05/README.md` 里引用的 `docs/assets/week05/analytics-code-structure.png` | 图片不存在，`docs/assets/` 整个目录都没有。runbook 里那张代码结构图渲染不出来 |
| 讲义 p29 的 docker 命令 | 缺 `--env-file infra/env/.env.local`。以 README 和 runbook 的命令为准 |
| 讲义 p65 的 `input_schema` 片段 | 少了实际契约中的 `tenant_id` 属性；`filters` 也有更细的 `additionalProperties` 约束 |
| 讲义 p27 的 KPI mart 片段 | 实际是 `coalesce(data_release_id, var(...))`，不是直接写 var；且实际 mart 还带 `tenant_id` 和一批支撑计数列 |
| 讲义 p66 的 `_build_query` 片段 | 是简化版，省掉了 `tenant_id` 过滤、`SAFE_COLUMNS` 校验和最关键的 ratio/加权聚合表达式（见第 6 节细节 1） |

---

## 8. 动手清单

统一走 Docker devbox。完整版（含 Tool API 端点 curl 和 v1.1 四个 payload）见 `runbooks/week05/README.md`。下面用 `DC` 代替重复的前缀。

```bash
# 0. 准备依赖（首次）
cp infra/env/.env.example infra/env/.env.local
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml \
  up -d --build postgres minio minio_init

# 之后所有命令的前缀
DC="docker compose --profile tools --env-file infra/env/.env.local \
    -f infra/docker-compose.yml run --rm devbox"

# 1. dbt debug —— 看到 "Connection test: OK connection ok" 才往下
$DC bash -lc 'cd analytics && DBT_PROFILES_DIR=. dbt debug'

# 2. build + docs —— 一次出齐 manifest / catalog / run_results
$DC bash -lc 'cd analytics && DBT_PROFILES_DIR=. dbt build --select tag:week05'
$DC bash -lc 'cd analytics && DBT_PROFILES_DIR=. dbt docs generate'

# 3. 校验 registry
$DC python analytics/scripts/validate_metric_registry.py --json

# 4. 受控工具：一正四负
#    --example 可换成 bad_metric / bad_role / bad_experimental / bad_org_scope
$DC bash -lc 'PYTHONPATH=services/tool_api python -m app.kpi_query --example valid'

# 5. 回归
$DC pytest tests/contract/test_week05_metric_contracts.py \
           tests/integration/test_week05_metric_registry.py \
           tests/integration/test_week05_kpi_query_tool.py -q
```

**验收标准不是"跑过了"，而是能回答这六个问题**：

1. `dbt build` 一共构建了多少个节点、多少个 test？失败的是模型还是断言？
2. `support_kpi_mart` 里一行代表什么？`agent_tool_input_view` 比它少了哪些列、为什么少？
3. registry validator 的 `metric_count` / `experimental_metric_count` 是多少？它到底校验了哪几类一致性？
4. 正例返回的 `policy_applied` 里有哪几项？`data_freshness` 三个字段分别从哪来？
5. 四个负例分别命中哪个 denial_code？各自被哪一段代码拦下？
6. 如果只看 `audit` 对象，能不能复原"谁在什么口径版本下查了什么、拿到多少行"？

**加分练习**（每一个都对应第 7 节的一个缺口）：

- 给 `analytics/models/marts/schema.yml` 补齐字段级 description，特别是 `metric_date` 的时间语义（它来自 `created_date`，不是 `updated_at`），然后用讲义的第一性问题自检
- 给 `sources.yml` 的 `ticket_fact` 配 `loaded_at_field` + freshness，跑 `dbt source freshness`，看 `target/sources.json` 长什么样
- 按讲义 p41 模板写一份 `reports/week05/lineage-impact-notes.md`：假设 `first_response_minutes` 改成"只算 `author_role=customer` 的第一条评论"，列出 marts / metrics / dashboards / tools / evals 五类下游影响
- 往 registry 里加一个新 ratio 指标（例如 `reopen_rate`），故意不加 `numerator`/`denominator`，确认 validator 报错；再故意不同步 safe view 白名单，确认 `accepted_values` test 或 validator 拦住它——**这才是"registry stale"反模式的手感**
- 改 safe view 加一列，数一数需要同步修改的地方到底有几处（见第 6 节细节 4）

---

## 9. 易错点与边界

**概念层面**

- 指标 ≠ SQL。metric 是名字，business definition 是含义，engineering interface 才让多方对得齐。
- 分层 ≠ 目录命名。它是污染隔离 + 消费边界 + 影响可定位。
- 派生布尔 ≠ 聚合 KPI。前者属 staging，后者属 intermediate / marts。
- build pass ≠ metric ready。前者证明能跑，后者要七道闸全过。
- lineage ≠ DAG 截图。它必须能回答"改了 X 谁受影响"。
- schema strict ≠ 安全。strict 只保证形状，语义、权限、成本必须 runtime 兜底。
- measure ≠ metric，语义层 ≠ 平台。前者是可聚合基础值 vs 面向业务的最终指标；后者的核心是"同名指标在不同系统里不变意思"。
- `denial_code` ≠ 报错。它是给 LLM 的修正指令，是接口能力的一部分。
- 预聚合的 rate ≠ 可再聚合。跨维度重算必须回到分子分母（见第 6 节细节 1）。

**范围边界（Week05 到底做到哪）**

Week05 交付的是**一份可负责的指标包 v1**：dbt models + tests/docs/lineage + local registry + 受控查询工具 + audit evidence。

刻意不做的事（`runbooks/week05/README.md` 第 0 节写得很明确）：不改 Week01-Week04 主路径；不引入 dbt Cloud / MetricFlow / Snowflake / BigQuery / Spark / Trino；不做 NL2SQL；不要求宿主机装 PostgreSQL / Python / dbt。

留给后面的：incremental 物化与大表成本优化、semantic model draft 与托管语义层迁移、HITL 与配额（Week10 治理）、指标包的评测消费（Week08）、asset 化编排与 backfill（Week06 已在 Week03-05 之上做）。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 三个团队算"P1 工单数"算出三个数，根因是什么？为什么"三个 SQL 都跑得通"反而更危险？把这个故事映射到 metric / business definition / engineering interface 三个对象上，分别是哪一层缺了东西？
2. 为什么 staging 里出现 `group by` 是把事故种子种在最深那一层？派生布尔和聚合 KPI 的分界线在哪？
3. `support_case_mart` / `support_kpi_mart` / `agent_tool_input_view` 的 grain 分别是什么？为什么 safe view 必须是 view 而不是 table？
4. `cross join lateral values` 的长表翻转带来了什么工程好处？如果用宽表，新增一个指标要改哪些地方？
5. build pass 为什么不等于 metric ready？七道闸里哪几道是"文档类"的，为什么它们也能 HOLD 上线？
6. 只堆 `not_null` 为什么叫"表演性安全"？本项目三个自定义 SQL 测试各保护什么？
7. `first_resolution_rate` 为什么是 `experimental_proxy`？runtime 用哪一道闸保证它不被静默消费？
8. 某公司买了 60 万美元/年的托管语义层却只用上三分之一，问题出在平台还是组织？你会怎么判断一家公司"准备好了"？
9. Structured Outputs strict 保证了什么、保证不了什么？举两个 strict 通过但必须被 runtime 拒绝的请求。
10. 九种 denial_code 里，哪几种是"registry 语义问题"、哪几种是"权限与成本问题"？为什么要给 LLM 返回码而不只是报错？
11. 为什么跨维度聚合时不能直接对 `sla_breach_rate` 求平均？registry 的 `numerator` / `denominator` / `weight_column` 在 runtime 里如何被用到？
12. `actor_role` / `tenant_id` 由服务端覆写，`actor_org_ids` 却仍来自 payload——这个差异说明了什么？给 safe view 加一列时，又需要同步修改哪几处？

---

## 11. 一句话收口

Week05 是整门课的**语义控制面**：它把 Week03/Week04 搬进仓的事实，收窄成一份 BI、Agent、Eval、治理都签字认可的指标接口——后面 Week06 的编排、Week08 的评测、Week10 的治理都建立在"同一个数字在四个系统里含义不变"这个前提上，而这个前提只能在这一周立住。
