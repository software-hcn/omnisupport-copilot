# Week 06 · 资产化数据工厂：编排、回填与可追溯

> **一句话**：把数据从"脚本跑出来的输出"升级成"可寻址、可版本、可责任、可观测的工程资产"——用 asset / partition / backfill / lineage / runbook 五件事，让"这份数据现在是哪一版、坏了怎么修、改了谁受影响"变成能在 30 秒内回答的问题。
>
> 讲义：`pdf/doc/week06-资产化数据工厂·编排回填与可追溯.pdf`（52 页 / 5 课时）

---

## 0. 本周主干

五节课是一条从"抽象换挡"到"团队肌肉"的下沉链：

```
L01 Asset      范式转换    Task → Software-Defined Asset：「我跑了什么」→「我交付了什么」
      ↓
L02 Partition  原子单位    资产在时间/维度上可寻址；没有分区，补数不精准、血缘停在表级
      ↓
L03 Backfill   工程化补数  4 阶段 + 3 层幂等 + 成本账；补数 = 时间旅行，不是 rerun
      ↓
L04 Lineage    运行时血缘  编排引擎自动发事件；影响分析 / 故障定位 / bad case 复现
      ↓
L05 Runbook    应急+协作   5 要素 + Game Day + Postmortem
      ↓
                          → Week07 非结构化数据的稳定上游
```

本周最值得背的是 L01 的**资产化四条军规**，后面四节都在给它补实现：

| 军规 | 一句话 | 由谁落地 |
|---|---|---|
| **Addressability** 可寻址 | 不是"那个表"，是 `support_ops.silver.ticket_fact@snap_042` | L01 命名 + L02 分区 |
| **Versioning** 可版本 | 每次物化产生不可变 snapshot，回退是切指针 | L02 分区 + Lakehouse snapshot |
| **Ownership** 可责任 | 告警不是群里 @everyone，是 routing 到 owner team | L05 协作约定 |
| **Observability** 可观测 | 物化历史 / 血缘 / 质量 / 变更全可查 | L04 血缘 + evidence |

另一句值得原样记住的判断：**不是 Airflow 不好，是它的核心抽象错位了——"Task"服务不了"我要拿到第 42 版的 silver"这种诉求。**

---

## 1. L01 · 从任务流到资产流

### 核心论点

调度器只关心"这个 DAG 跑没跑"，而下游 RAG / Agent 问的完全是另一组问题：我拿到的 `customer_dim` 是哪一版？上次更新几点？谁负责？回退要多久？前者是脚本视角，后者是产品视角。**资产化就是把数据当产品管理。**

### 三种范式对照

| 维度 | 脚本式 ETL | 任务流（Airflow） | 资产流（Dagster/dbt） |
|---|---|---|---|
| 核心单位 | Python 脚本 | Task / Operator | Software-Defined Asset |
| 首要关心 | 脚本跑没跑 | DAG 跑通没跑通 | 资产现在是什么状态 |
| 故障定位 | 看日志、人肉排查 | 看 DAG 重试记录 | 看物化历史 + 血缘 |
| 影响分析 | 人肉评估，容易漏 | 看上下游 Task，粒度粗 | Asset Graph 一键渲染 |
| 补数 | 写专用脚本 | 有 backfill 但要人肉判断 | 声明式 partition 自动补 |
| 给 AI 的承诺 | 没有 | 弱（只到 Task 层） | 强（每个分区有 snapshot） |

### 任务流的三个隐藏代价（上线半年才爆）

**补数成本**：一次补数 ≈ 半周协调，人肉评估影响 → 写专用脚本 → 通知 N 个下游各自补 → 补完还要互相校对。根因是影响范围不可计算，解药是声明式 partition + 自动血缘。**协作冲突**：一次冲突 ≈ 一天扯皮，PR 合到主分支才发现两个团队改了同一张表；根因是 dev / prod 共用一套连接，改一处全炸，解药是 L05 的 Branch Deployments + slim CI。**信任流失**："这表是新的吗？""应该是吧。"没人能给确定答案，后果是 AI 团队开始自己抓数据、数据团队被绕过、治理彻底崩塌。

这三个代价在 BI 时代"可以忍"，在 AI 时代忍不住——AI 系统对"数据这一刻是什么样"的精度要求，和 BI 不在一个量级。

### 团队自检五题（超过 3 个答"不"就还在脚本时代）

| 问题 | 答"不"意味着 |
|---|---|
| 30 秒内能否回答"`customer_dim` 当前哪一版、上次更新几点"？ | 没有 Observability（答"要登服务器看日志"） |
| 改核心字段前，能否先看到"下游哪 23 张表 + 哪 4 个 RAG 索引受影响"？ | 没有自动血缘（答"开会评估"） |
| 上游昨天补了数，能否让用过那批数据的下游**立刻知道**？ | 没有 asset 级事件传播（答"群里发通知"） |
| 凌晨 3 点告警，值班同事能否照 Runbook 在 30 分钟内压下 P1？ | Runbook 是摆设（答"先打电话叫人"） |
| 过去 90 天，能否给出"每次补数花了多少钱、改了几个分区、被谁审过"？ | 没有补数 audit trail |

### 迁移路径（渐进式）

`S1 共存`（Airflow 留着，Dagster 新起仓库只接 1-2 个新数据产品域，并行 4-8 周）→ `S2 反向桥接`（用 `ExternalAssetDefinitions` 把 Airflow DAG 当外部资产抽进图，血缘先统一）→ `S3 收编核心`（核心域 silver/gold 搬家，原 DAG 退化为数据源 sensor，必须配审批 + 灰度）→ `S4 退役旧的`（只留跑得稳、无资产化诉求的 edge 任务）。

节奏是 30-60-90 天一个域。**不要一次性把 200 个 DAG 迁过来，95% 的团队会失败。**

> 行业信号（讲义 p11）可压成一句：2024 年之后新项目几乎不再从 Airflow 起步；Dagster/dbt + OpenLineage 是开源默认路径，Snowflake Dynamic Tables 与 Databricks Lakeflow 在追但平台耦合重，Airflow 3.0 虽引入 Asset 感知，Task 在核心 API 仍是一等公民。

---

## 2. L02 · 分区是资产化的原子单位

### 核心论点

分区常被当查询优化，这只对一半。在资产化数据工厂里，分区真正的作用是**时间与维度上的可寻址性**：能精确指着说"就重跑 2026-05-15 这一格"，能只补 `tenant_A` 不动 `tenant_B`，下游问"你用的哪一版"你能给出 `(date, tenant, snapshot_id)`。**没有分区，资产化是一片连续的湖；有了分区，资产化是一张精细的网**——每一格独立物化、独立回滚、独立验证。

一个检验问题：2026-05-15 那天的 `customer_dim` 出问题，你能不能只重跑那一天？答不出来的团队，资产化只做了一半。

### 三种分区类型

| 类型 | 定义方式 | 解决什么 | 关键约束 |
|---|---|---|---|
| **TIME** 时间分区 | `DailyPartitionsDefinition` / `HourlyPartitions` | 补数 / 回放 / 增量，90% 的默认选择 | 必须用 `event_time`，不要用 wall-clock；迟到数据会让两者错位 |
| **DIMENSION** 维度分区 | `StaticPartitionsDefinition` | 多租户隔离 / 灰度 | 维度值必须稳定，加新值会让所有下游重建分区元数据 |
| **COMPOSITE** 复合分区 | `MultiPartitionsDefinition` | 精细化运营 + 定向补数 | 组合数别爆炸：5 tenant × 365 天 = 1825 可以；再乘 24 小时 = 43800，元数据查询会拖慢 |

顺序是"先有需求再上"：维度分区是业务隔离需求的产物，复合分区是精细化运营的产物。

### 时间分区最常踩的四个坑

| 坑 | 工程师为什么会犯 | 后果 | 正确做法 |
|---|---|---|---|
| 用 wall-clock 当分区键 | 本能、改起来快 | 时区错乱 / 时钟漂移 / 数据漏掉 | 永远用 `event_time` + watermark |
| 粒度太粗（按月） | 想少建几个分区 | 一次补数重跑整月，资源浪费 | 默认按天，必要时按小时 |
| 粒度太细（按分钟） | 想做实时 | 分区数爆炸、元数据查询慢 | 高频用流处理，分区按小时 |
| 没设 grace period | 不知道上游会迟到 | 迟到数据漏掉，下游算错 | 声明 `watermark_lateness` 缓冲 |

### 粒度权衡（先问"下游要什么"，再选粒度）

| 粒度 | 适用场景 | 补数代价 | 元数据量 | 推荐 SLO |
|---|---|---|---|---|
| 小时 | 高频更新的 ticket / event | 小（1 小时） | 高（8760/年） | P1 · 30 分新鲜度 |
| 天 | 90% 默认 | 中（1 天） | 中（365/年） | P1 · 4-12 小时 |
| 周 | 聚合宽表 / 周报 | 高（7 天） | 低 | P2 · 24-48 小时 |
| 月 | 财务月结 / 历史归档 | 极高（1 个月） | 极低 | P3 · 周度 |

默认从天分区起步，只在两类情况偏离：高频需求往小走，归档需求往大走。

### 分区演进的硬规则

**分区键一旦定下，永远不要原地改。** 演进只有三条合法路径：**加维度**（单租户变多租户 → 新建 `MultiPartitionsDefinition`，老数据全归 `default` tenant，老分区一行不动）；**变细**（天 → 小时 → 新表 `*_hourly` 双写 4 周，确认稳定后下游切换，老表保留只读）；**变粗**（小时 → 天 → 不要 truncate，起一个新的 daily summary 资产去聚合 hourly，老 hourly 当 raw 留着）。

改键永远要走"新表 + 历史回填 + 切换"三步，Iceberg V3 的 partition transform 演进只能减痛，不能免除。演进成本一半在工程，一半在协作。

### 每个分区必须带的元数据（资产化的黑匣子）

| 字段 | 作用 | 不带的后果 |
|---|---|---|
| `partition_key` | 唯一标识这一格 | 无法定位补数对象 |
| `materialized_at` | 本次物化时间戳 | 不知道用的是哪次物化结果 |
| `source_snapshot_id` | 上游所用 snapshot | 上游变了下游不知道，bad case 复现不了 |
| `row_count` / `size_bytes` | 数据规模 | 补数前评估资源不准 |
| `status` | success / failed / quarantine | 下游不知道这一格能不能消费 |
| `contract_ref` | 所用契约版本 | 语义漂移无法回溯到契约源头 |

> Lakehouse 分区现状（讲义 p18）压成选型口诀：云原生且预算够 → Databricks + Delta（Liquid Clustering）；开源 + 多云 → Iceberg V3（Hidden Partitioning + Row Lineage）；教学/PoC → DuckLake；Hudi 留给已经在用 Hudi 的团队。

---

## 3. L03 · 回填与幂等重试

### 核心论点

**补数的本质是时间旅行，不是"再跑一次"。** "再跑一次"用的是今天的代码 + 今天的上游 + 今天的依赖，而你要补的是两周前的数据——硬补一次，等于用今天的逻辑改写两周前的事实，问题更大。

正确的补数 = 回到那个历史时刻，用**那时的代码版本 + 那时的上游 snapshot** 重新物化。这就叫可重建（reproducibility）。

最危险的一句话是"我直接 rerun 一下就好"：没问场景、没看快照、没通知下游，80% 的事故是这样酿出来的。

### 四种补数场景（处理逻辑完全不同）

| 场景 | 触发原因 | 关键判断 | 回退策略 |
|---|---|---|---|
| 事故补数 | 上游故障 / 数据错乱 | 原数据是否还可信？ | 隔离原区 + 全量重跑 |
| 字段新增补数 | 新增计算列 | 是否影响历史含义？ | 只增量补新字段 |
| 业务变更补数 | KPI 口径调整 | 需不需要追溯历史？ | 协调下游 + 双版本并行 |
| 上游修复补数 | 上游补完通知 | 当时下游用的是错的吗？ | 精确补 + 通知所有消费方 |

补数前必须先问"这是哪种场景"。回答错了，补数会制造更大的问题。

### 幂等性的三层（少一层就会炸）

| 层 | 要求 | 手段 | 漏掉的后果 |
|---|---|---|---|
| **WRITE** 写入层 | 同分区多次写入结果一致 | `INSERT` 改 `MERGE`/`UPSERT`；`partition_key + business_key`；Iceberg snapshot 天然幂等；dbt incremental + `unique_key` | 补数 = 制造重复 |
| **SIDE-EFFECT** 副作用层 | 外部操作幂等 | `idempotency_key` 头；at-least-once + 去重表 | 同一封"账单已到账"邮件发 7 次 |
| **DOWNSTREAM** 下游层 | 消费方能感知 | Watermark Event；Asset Reconciliation Sensor；消费方锁 `snapshot_id` | 下游继续用旧数据生产新错 |

**99% 的补数事故不是写入层的错，是副作用层或下游层没考虑。**

### 幂等 ID 的三种策略

| 策略 | 做法 | 优点 | 缺点 | 适合 |
|---|---|---|---|---|
| S1 自然主键 | 业务字段做主键（`ticket_id` / `order_no`） | 天然幂等 | 上游改键就崩、跨域易冲突 | 源头明确、业务键稳定 |
| S2 合成主键 | UUID v4 / ULID 现场生成 | 永不冲突 | **每次重跑 ID 都不同，完全不幂等** | 仅 append-only 事件流 |
| S3 确定性合成主键 | `hash(partition_key + business_key + version)` | 幂等 + 防冲突 | 实现稍复杂，改 schema 时 hash 要版本化 | 大多数生产场景的标配 |

看到表 ID 是 `uuid_v4()` 要先警惕：除非是纯事件流，否则补数一定会重复。直接问设计者"你们怎么去重"，答不上来就是隐患。

### 迟到数据（90% 补数事故的根源）

上游 5 月 18 日的数据 5 月 22 日才到，如果 18 日那天的分区已经物化了，这批数据算今天还是算 18 日？四件事必须一起做：**声明 watermark**（`watermark_lateness = 7d` 表示"event_time 在 7 天内的迟到数据归入它原本所属的分区"，超过 7 天进 quarantine）；**落分区靠回填**（迟到数据到达 → 触发那一天的分区**重物化 overwrite，不是新建**）；**阈值报警**（迟到占当日总量 > 5% 就报警，说明上游有系统性延迟，要从根上修）；**对外沟通**（下游所有 SLO 公式都要把这 7 天延迟算进去）。

### 一次合格补数的四个阶段（每阶段都必须有产物）

`ASSESS 评估`（回答下面的评估单 5 问 → 产物是补数评估单 PR）→ `APPROVE 审批`（主负责人 + 受影响下游 owner 共同点头 → 产物是 PR approve + 通知群周知）→ `EXECUTE 执行`（声明式 backfill，自动按分区并行、失败隔离 + 重试 → 产物是 `backfill_run_id` + 物化历史）→ `VERIFY 验证`（资产质量检查 + 下游消费方对账 → 产物是验证报告 + Watermark Event）。

最容易被跳过的是评估和验证，而这两步出问题的代价远大于补数本身。

### 补数评估单五问（直接当 PR 模板用）

| 评估项 | 具体问题 | 不评估的后果 |
|---|---|---|
| 范围 | 哪些分区？哪些 tenant？多大批？ | 补漏了 / 补多了 / 影响别的租户 |
| 资源 | 需要多少 CPU / GPU / 时间？ | 挤占在线服务资源，引发二次事故 |
| 影响 | 哪些下游已经消费过这批旧数据？ | 下游继续用错数据生产新错 |
| 策略 | reject + replay 还是增量修补？ | 选错策略 = 修不好，反复返工 |
| 回滚 | 失败了怎么回到补数前的状态？ | 数据卡在半成品状态 |

reviewer 看不到这张表就直接 close PR。补数命令上的 `--tags` 也是同一逻辑：`reason` / `ticket` / `approver` 必填，少一个 tag 审计就追不到人；`source_snapshot_at` 是"时间旅行"的关键，它告诉系统按那个时刻的上游 snapshot 跑。

### 一次真实事故的三个深坑（讲义 p30，3 小时闭环）

时间线：T+0 上游 schema 漂移，contract check 报警，17 个分区进 quarantine → T+30m 评估出影响 7 天 × 3 tenant = 21 个 cell、14 个下游、5 份已发报表 → T+1h 审批 → T+1h30 起 9 路并发 reject + replay → T+2h45 全部 SUCCESS，下游 KPI 偏差 < 0.3% → T+3h 发 Watermark Event，RAG 索引自动重建。

三个差点搞砸的坑，全都不在写入层：**副作用没幂等**（"账单已修复"邮件给同一客户发了 5 次 → 补数前用 toggle 关掉所有外发副作用）、**RAG 索引滞后**（索引还在用旧 chunk，客服回答仍然错 → 发 Watermark Event 触发自动 reindex）、**下游报表对齐**（5 月报表已出，补数后差 0.3% → 出补丁报表 + 通知接收方）。

### 补数的成本账

一次"3 小时小补"（3 tenant × 7 天 = 21 cell）实际约 ¥8,200：compute ~¥2,400、上游 API 重拉 ~¥800、快照膨胀 ~¥300、下游 RAG 重索引 ~¥1,500、工程人时 ~¥3,200。约等于一个工程师一周薪资。

压账的四招：评估单上必须写"**能不能不补**"（大量"补数"其实只需要重新声明 contract + 加 reject 规则）；用 reject + replay 而不是 truncate + reload；下游索引走增量 reindex，RAG 成本能砍 70%；高频 backfill 集中到夜间低价时段。

---

## 4. L04 · 全链路血缘

### 核心论点

**血缘不是文档，是运行时自动生成的拓扑——文档会撒谎，血缘不会。** 过去 20 年"数据字典""血缘文档"90% 都失败了，因为人工维护永远赶不上代码变化。

心智转换很具体：不要再问"我们的血缘文档谁维护"，正确的问题是"**我们的血缘事件流从哪个 emitter 发的？数据存到哪个 backend？**"

### 血缘的三个粒度

| 粒度 | 形态 | 解决什么 | 工具 | 局限 |
|---|---|---|---|---|
| **TABLE** 表级 | A.table → B.table | 粗粒度影响分析 | dbt-docs / DataHub | 改一个字段说不清哪些下游受影响；BI 时代够用，AI 时代不够 |
| **COLUMN** 字段级 | A.col1 → B.col2 | 精细影响分析 | OpenLineage SQL Facet / sqllineage / Marquez | 复杂 SQL（window / UDF）解析仍是难题 |
| **ROW** 行级 | 某一行的源头 | bad case 追溯 | Iceberg V3 Row Lineage | 全量开销过大，通常只在抽样 + 关键域做 |

2026 年的及格线：**表级 100% + 字段级覆盖核心域 + 行级只做在关键 AI 输出链路上**。

### 血缘的五大场景（每一个都直接压 MTTR）

**U1 影响分析**：改 schema 前先渲染哪些 asset / dashboard / RAG 索引受影响，开会评估 → 按一下按钮。**U2 故障定位**：下游 KPI 异常，沿血缘逆向追到第一个坏的资产分区，3 小时 → 5 分钟。**U3 合规审计**："这个客户字段在哪 7 个系统用过"——GDPR / CCPA / AI Act 全靠它。**U4 查询优化**：看哪些下游都在消费同一张巨表，精准物化中间层，是给 FinOps 的礼物。**U5 Bad case 复现**：血缘 + snapshot ID 让你回到那一刻，复现整个推理过程——这是 AI 治理的根。

### OpenLineage 的四个核心对象

| 对象 | 含义 | 主要字段 | 什么时候产生 |
|---|---|---|---|
| **Job** | 一段可重复执行的代码 | `name` / `namespace` / `source` | 代码定义时声明 |
| **Run** | 一次具体执行 | `run_id` / `start` / `end` / `state` | 每次运行时生成 |
| **Dataset** | 一份数据集（表/文件/流） | `name` / `namespace` / `schema` | 输入或输出时声明 |
| **Facet** | 附加元数据扩展 | 任意结构化扩展 | 按需挂到上面三类对象 |

四个对象一组合，就能描述"某个时刻、某段代码用了哪些数据、产生了哪些数据"——这就是血缘的全部。事件里最关键的两块是 `inputs[].facets.version.datasetVersion`（上游用的哪个 snapshot）和 `outputs[].facets.columnLineage`。**它是机器产生的，所以不会过期。**

### AI 时代血缘的边界被推远了

过去血缘 = 表 → 表 → 表。AI 时代必须一路管到答案：

```
Bronze Source → Silver/Gold → Doc Chunks → Vector Store → Prompt Template → AI Answer
   业务库/日志     fact/dim+契约   chunk_id+来源    向量+version+index   版本化+variables   推理记录+决策依据
```

四个工程动作：每个 chunk 带 `source_asset_id` + `source_snapshot_id`（bad case 复现的根）；vector store 的 collection 视为资产纳入 Asset Graph，每次重建都发 OpenLineage 事件；prompt template 走 Git + `version_tag`，推理时记入 trace，血缘里能看到"这次回答用的是 prompt v17"；eval set 也是资产，血缘里能看到"v17 prompt 在 eval_set_v3 上跑分多少"。

### 字段级血缘的四个现实坑

| 坑 | 为什么断 | Workaround |
|---|---|---|
| Window function | `ROW_NUMBER() OVER(...)` / `LAG` / `LEAD` 里静态解析器几乎都丢字段 | 核心域改用 dbt model 显式声明 columns，血缘下沉到 model 元数据 |
| UDF | Python / Spark UDF 内部 SQL parser 看不到 | UDF 显式声明 inputs/outputs，用 `ExtractionFacet` 补 |
| JSON / 半结构化 | `json_extract(payload, "$.user.id")` 只能解到 `payload` | 先 structify 拍平到独立列 |
| 跨引擎 | SQL → Spark → ML 三个引擎事件标准不一致 | 统一 OpenLineage emitter，这是 2026 新项目的硬要求 |

接受现实：**字段级血缘不可能 100% 自动，90% 自动 + 10% 关键域手工补是当前最佳实践。**

> 后端选型（讲义 p40）压成一句：新项目默认 OpenLineage + DataHub；小团队/PoC 用 Marquez；需要治理协作用 OpenMetadata；深度押 Databricks 就用 Unity Catalog。

---

## 5. L05 · Runbook 与协作规范

### 核心论点

**Runbook 不是文档，是"事故压力下也能稳定执行的脚本"。** 最差的 Runbook 写"检查上游数据是否正常"——什么叫正常？查哪些字段？阈值多少？凌晨两点没人看得懂。好的 Runbook 写"执行 `dagster job status ticket_silver_job --partition 2026-05-15`；如果 status 是 FAILED，跳到第 3 步"。

判断一个团队是否真有运维能力：**看不到具体命令的 Runbook，等于没有。**

### 六大反模式

| 反模式 | 表现 | 后果 | 正确做法 |
|---|---|---|---|
| 抽象描述 | "检查上游是否正常" | 凌晨两点没人看得懂 | 给具体命令 + 期望输出 |
| 口口相传 | "问老 X 就行" | 老 X 离职就完蛋 | 强制每个故障写 Runbook |
| 只在事故后写 | 复盘时补 | 凭记忆不准、有遗漏 | 事前演练 + 事后修订 |
| 没人测试 | 写完没人跑过 | 真用时命令早废了 | 每季度 Game Day |
| 没有验证步骤 | 操作完不知道好没好 | 修了还在出问题 | 每个动作配验证命令 |
| 不连接监控 | 看不到当前状态 | 凭感觉判断 | 第一步就看 Grafana |

**Runbook 不是写出来的，是"演练 + 反复修订"出来的——第一版永远是错的。**

### 合格 Runbook 的五要素

| 要素 | 必须包含 |
|---|---|
| **R1 Symptoms** 症状 | 怎么发现是这类故障？告警长什么样？给可观察的判定特征——截图 + 阈值，不是文字描述 |
| **R2 Diagnosis** 排查 | 症状到根因的**决策树**：哪条分支查什么、跑哪个命令、期望输出是什么 |
| **R3 Action** 操作 | 每一行都能复制粘贴。不写"重启服务"，写 `systemctl restart dagster-daemon` |
| **R4 Verification** 验证 | 查哪些指标、跑哪些命令、期望多久恢复。**没有验证 = 修了等于没修** |
| **R5 Postmortem** 复盘 | 发生了什么 / 影响范围 / 根因 / 改进项 / 是否升级 Runbook。每次事故必须产出 |

三档成熟度不要跳级：**L1 Manual**（Markdown，每步明确命令）→ **L2 Semi-Auto**（关键步骤变 CLI / Dagster Job，人工触发，失败回退人介入）→ **L3 Fully-Auto**（Skill Pack / self-healing，检测+决策+执行闭环，只看结果）。

### 协作约定：命名 / Ownership / SLO

命名四条铁律：命名空间统一 `{domain}.{layer}.{name}`（`support_ops.silver.ticket_fact`，不是 `silver_ticket` / `ticket_v2_final`）；layer 仅四档 `bronze / silver / gold / serving`，不造新词（没有 platinum）；名词单数 + 蛇形（`ticket_fact`，不是 `tickets_facts` / `TicketFact`）；**永远不要把版本写在 name 里**，版本走 `snapshot_id`。

Ownership + SLO 四条硬规则：每个资产 ≥ 1 个 owner 且必须是 **team-level 不是个人**（`owners=["team:support-platform"]`）；每个 P1 资产必须声明 `FreshnessPolicy`，告警自动 routing 到 owner team；`criticality` 强制三档（P1 → 30 分新鲜度 + 立刻响应，P2 → 4-12 小时 + 工作时间响应，P3 → 周度 + 尽力而为）；**任何"无主资产"不准上 prod**，靠 CI 检查 asset 没声明 owner 就 fail。

### 变更隔离

90% 的"我改完上线发现你也改了"事故，根因是没做变更隔离。解药是把数据栈当代码栈管——每个 PR 起一个独立的数据沙盒，合到 main 才生效：

- **Dagster Branch Deployments**：开 PR 自动起隔离部署，同一份代码跑在沙盒 schema 上，沙盒里能跑 backfill / asset check / 看血缘；merge 自动 promote 到 prod，关 PR 自动回收资源。价值是两个团队改同一张表互不踩、reviewer 直接在沙盒看效果、出问题 retract PR 而 prod 一行不动。
- **dbt slim CI**：`--select state:modified+` 只跑被改的 model + 下游，`--defer --state ./prod-state` 让上游引用直接指 prod state。CI 从 30 分钟压到 3 分钟，迭代节奏 5×，资源消耗骤降。

### Game Day

Runbook 写完不演练，跟健身办卡不去一样。一年至少 4 次，四步：**选场景**（从历史事故 + 风险清单里随机抽：schema 漂移 / 某 tenant 数据漏 / metadata corrupt / 主备同时挂）→ **选演员**（on-call 名单随机抽 1 主力 + 1 观察员，**抽到 senior 也照样跑，不能换人**）→ **真实演**（观察员只记录不提示，主力照 Runbook 一行行执行，**卡住的地方就是 Runbook 的 bug**，立刻记 issue）→ **复盘升级**（当晚 1 小时复盘，当晚提 PR，3 天内合并）。

Google 叫 Wheel of Misfortune，Netflix 叫 Chaos Monkey，本质是同一件事：**让事故在可控时刻发生，Runbook 才不会撒谎。**

### Postmortem 八节

①摘要（3 句话，让没参与的人 30 秒读懂）②影响范围（带数字，不写"少量"）③事件时间线（每行写"谁做了什么、看到了什么"）④根因分析（5 Why，不停在"网络抖了"，继续问到组织/设计问题）⑤做得好的地方（固化下来）⑥做得不好的地方（Blameless，只对事不对人）⑦**改进项（责任人 + DDL + 是否完成——这是 Postmortem 唯一的产出）**⑧Runbook 升级建议。

### Runbook → Skill Pack（Week09 预告）

Runbook 是"人执行"的单个 Markdown：人收告警手动打开、人复制命令逐步执行、人看结果判断、靠人理解上下文。Skill Pack 是"人 + Agent 都能执行"的目录（`SKILL.md` + `scripts/` + `assets/`）：`description` 字段供 Agent 自动匹配、脚本可被参数化调用、scripts 内置验证并输出结构化结果、YAML frontmatter 声明输入/输出/风险边界、完整目录纳入 release manifest。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。**注意：仓库把 Week06 全部实现收在 `pipelines/data_factory/` 一个包里，与讲义 p52 交付物清单写的目录结构不一致**（对照见第 7 节）。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 资产定义 / 分区元数据 | `pipelines/data_factory/assets.py` | 9 个 asset 的 `key` / `group_name` / `tags` / `ins`；每个 asset 都返回 `Output(payload, metadata=...)`，`MetadataValue.text/int/json/bool/path` 就是分区黑匣子的落地 |
| L01 稳定 ID / Addressability | `pipelines/data_factory/asset_keys.py` | `AssetKey(["week06", "<layer>", "<name>"])` 三段命名，`asset_key_to_str()` 拍平成 `week06/ops/...` |
| L01 Asset Graph 依赖关系 | `docs/blueprints/week06/week06-asset-graph.md` | 九节点依赖图 + 每个 asset 的 source of truth 表 |
| L01 Dagster 注册 / Job | `pipelines/definitions.py`<br>`pipelines/data_factory/jobs.py` | `load_assets_from_modules` / `load_asset_checks_from_modules`；`define_asset_job` + `AssetSelection.assets(*WEEK06_ASSET_KEYS)` |
| L02 时间分区 | `pipelines/data_factory/partitions.py` | `DailyPartitionsDefinition(start_date=...)`，start_date 和 default partition 都来自 env |
| L02 分区字段与时区 | `docs/blueprints/week06/week06-partition-backfill-strategy.md` | 分区字段是 ticket `created_at`，时区 UTC，demo partition `2026-04-17`，safety rules 说明为什么只做 dry-run |
| L03 补数评估单 + CLI | `pipelines/data_factory/backfill_plan.py` | `BackfillPlan` 的 12 个字段 = 评估单的代码化；`partition_window()` 把日期展开成 UTC `time.min → time.max`；`main()` 的 `--partition` / `--mode` / `--operator` |
| L03 幂等 | `pipelines/data_factory/checks.py` | `check_duplicate_idempotency()` 按 `ticket_id` 查重，对应 L03 的 S1 自然主键策略 |
| L04 血缘的落地替身 | `contracts/run_evidence/week06_run_evidence.schema.json` | `source_snapshot_id` / `output_snapshot_id` / `lakehouse_snapshot_id` / `dbt_invocation_id` / `trace_id` / `git_sha` |
| L04 run evidence 生成 | `pipelines/data_factory/evidence.py` | `RunEvidence` dataclass、`validate_run_evidence()`、`build_downstream_decision()` |
| L04 evidence 字段语义 | `docs/blueprints/week06/week06-run-evidence-spec.md` | required / optional 字段划分 + status 与 downstream_decision 语义表 |
| L05 Runbook | `runbooks/week06-data-factory.md` | Scope / UI Path / CLI Path / Checks Acceptance / **Recovery Decision Tree**（对应 R2 决策树）/ Known Limitations |
| L05 Postmortem 模板 | `postmortems/template.md` | 7 节结构，与讲义 8 节不完全对应（见第 7 节） |
| L05 边界与 scope | `docs/blueprints/week06/week06-data-factory-blueprint.md` | Student Core Pack 清单 + Out of scope 清单 + Evidence Policy |
| 契约测试 | `tests/contract/test_week06_run_evidence_schema.py` | 四个用例：schema 自身合法、success 载荷、`not_available` 载荷、非 week06 asset_key 被拒 |
| 集成测试 | `tests/integration/test_week06_definitions_loadable.py`<br>`test_week06_asset_graph_smoke.py`<br>`test_week06_asset_checks.py`<br>`test_week06_backfill_plan.py`<br>`test_week06_run_evidence_generation.py` | smoke 测试用 `materialize(WEEK06_ASSETS, partition_key="2026-04-17")` 跑通全图并断言 evidence JSON 落盘；每个测试都靠 `monkeypatch.setenv` 隔离 report 目录 |
| 运行时配置 / 资源 | `pipelines/resources/config.py`<br>`pipelines/data_factory/resources.py` | `DataFactorySettings.from_env()` 的 16 个字段和默认值；三个 resource `week06_postgres` / `week06_minio` / `week06_reports` |
| 课堂产物 / 种子数据 | `reports/week06/week06_delivery_summary.md`<br>`reports/week06/course_site_sync_notes.md`<br>`data/canonization/tickets/tickets-seed-001.jsonl` | `reports/week06/.gitignore` 决定哪些 runtime evidence 不进 Git；种子 `created_at` 决定哪些分区非空 |

### 代码里值得单独看、讲义没展开的细节

**1. 分区键有一个静默 fallback。** `assets.py` 里每个 asset 都走同一个 `_partition_key(context, settings)`：`context.has_partition_key` 为真就用 `context.partition_key`，否则落到 `default_partition_key(settings)`（即 `WEEK06_DEFAULT_PARTITION`，默认 `2026-04-17`）。所以不带分区调用也不会报错。教学上方便，工程上是个坑——讲义 L02 强调"分区键必须显式"，这里恰好是反例。

**2. `downstream_decision` 是硬编码的四分支优先级**（`evidence.py`）：

```python
if status == "failed":                                   return "hold_downstream"
if dry_run or "dry_run_no_db_write" in reason_codes:     return "dry_run_only"
if status == "warning":                                  return "manual_review_required"
return "proceed_to_week07"
```

注意 `dry_run` 的判断在 `warning` 之前——所以**默认课堂模式下永远不可能得到 `manual_review_required`**，一律是 `dry_run_only`。想看到别的分支必须显式设 `WEEK06_INGEST_DRY_RUN=false`。

**3. 五个 check 的严重性不统一，而 `passed` 的判定很宽松。** `checks.py` 里只有 `check_partition_completeness` 失败时返回 `warning`，其余四个直接 `failed`；但 `CheckOutcome.passed` 把 `passed / warning / skipped` 全算通过。`run_evidence` 里 status 的推导顺序是：有 failed → `failed`；上游 skipped → `skipped`；有 warning → `warning`；否则 `success`。这就是 Week02 的 accept/warn/quarantine/reject 四类动作在 Week06 的对应物。

**4. `row_count_output_count` 这个 asset check 在 Dagster UI 里是空跑的。** 它的 `@asset_check` 包装直接返回 `skipped`，reason 是 `requires_materialization_context`——真正的行数检查只在 `run_week06_asset_checks()` 被 `run_evidence` asset 调用时才执行。UI 上看到它绿灯，不等于行数被校验过。

**5. `manifest_gate` 的准入判断只有一条，schema 却用正则强制了命名空间。** gate 只检查"有 `modality == "structured"` 的 manifest 且 `assets` 非空"，reason code 只有 `structured_manifest_missing_or_empty` 一个——Week02 的五层 contract gate 在 Week06 不重新执行，复用的是 Week02 的准入结论。另一头，evidence schema 的 `asset_key` 带 `"pattern": "^week06/"`，Week05 的 evidence 塞不进来（`test_week06_run_evidence_rejects_non_week06_asset_key` 专测这点），`additionalProperties: false` 保证不能偷偷加字段。

**6. Week04/Week05 是纯观察依赖，读的是文件不是数据库。** `week06_lakehouse_state` 读 `reports/week04/materialization_report.json` 里 `tables["silver.ticket_fact"].snapshot_id`；`week06_support_kpi_mart` 读 `analytics/target/run_results.json` 里 `metadata.invocation_id`。文件不存在就写 `not_available` + reason code，绝不伪造成 passed。

**7. backfill plan 的 `current_output_count` 恒为 0。** `build_backfill_plan()` 签名里默认 0，asset 调用时也没传值，所以只要源表这一格有行，`gap_reason` 必然是 `output_lag`。Blueprint 明确写了 "current output count is observation-only unless a DB query path is explicitly enabled later"——这是刻意留白，不是 bug。

---

## 7. 讲义与仓库对不上的地方

讲义 p52 列的交付物清单和代码页里的文件路径，**在本仓库里基本都不存在**。别照着找。

| 讲义写的路径 / 能力 | 实际情况 |
|---|---|
| `pipelines/assets/ticket_silver.py` | 不存在。`pipelines/assets/` 整个目录都没有；Week06 资产在 `pipelines/data_factory/assets.py` |
| `pipelines/partitions.py` | 不存在。实际是 `pipelines/data_factory/partitions.py` |
| `pipelines/jobs/backfill_*.py` | 不存在。`pipelines/jobs/` 目录没有；补数逻辑在 `pipelines/data_factory/backfill_plan.py`，而且它是**dry-run 规划器，不是能执行的 Dagster backfill job** |
| `pipelines/lineage/setup.py` + `dagster_openlineage` | 不存在。仓库**完全没有 OpenLineage 集成**，`pyproject.toml` 里也没有 `dagster-openlineage` 依赖。L04 在仓库里的替身是 `run_evidence` 的 snapshot / invocation / trace 字段 |
| `runbooks/ticket_silver_schema_drift.md` | 不存在。Week06 只有一份 `runbooks/week06-data-factory.md`，它的 "Recovery Decision Tree" 一节对应讲义 R2 |
| `.github/workflows/branch_deploy.yml` | 不存在。`.github/workflows/` 下只有 `query-rewrite-gate.yml` / `rag-eval-gate.yml` / `week14-governance-gate.yml`。Branch Deployments 与 slim CI 是概念讲解，没有可跑实现 |
| `tests/contract/test_ticket.py`（讲义 Runbook 样例里的命令） | 不存在。Week06 的契约测试是 `tests/contract/test_week06_run_evidence_schema.py` |
| `MultiPartitionsDefinition` / tenant 维度分区 / 复合分区 | 讲义 L02 的重头戏，**仓库只实现了 `DailyPartitionsDefinition`**。runbook 的 Known Limitations 明确写了 "does not run full dynamic partitions" |
| `owners=[...]` / `FreshnessPolicy` / `criticality: P1` tag | 仓库 asset 的 `tags` 只有 `{"week": "06", "layer": ...}`，没有 owner、没有 freshness policy、没有 criticality。L05 的"无主资产不准上 prod"CI 检查也没有 |
| `iceberg.rollback_to_snapshot` 兜底 | 属于 Week04 范围。Week06 只**读** Week04 报告里的 `snapshot_id`，不做任何回滚 |
| `postmortems/template.md` | **存在**，但内容是 Week12 trace 导向的 7 节（Summary / Trace Evidence / Root Cause / Fix / Verify / Lessons / Action Items），与讲义 L05 的 8 节（含"做得好的地方""Runbook 升级建议"）不是同一份 |
| Dagster Cloud / Dagster+ | runbook 的 Known Limitations 明确写 "does not introduce Dagster+"。L01 提到的 Dagster Cloud Asset Graph、L05 的 Branch Deployments 都需要 Dagster+ |
| Game Day / Skill Pack 落地 | 无对应实现。Skill Pack 见 `runbooks/week09-agent-skills.md`，是 Week09 的内容 |

**仓库内部还有一处不一致**（不是讲义的问题，但会浪费时间）：`runbooks/week06-data-factory.md`、`docs/blueprints/week06/week06-data-factory-blueprint.md` 和 `week06-asset-graph.md` 三处都引用了同一张图 `docs/assets/week06/week06-data-factory-code-map.png`，但 `docs/assets/` 目录不存在，图渲染不出来。看代码阅读顺序请直接读 blueprint 的文字说明：先读 `config.py` / `asset_keys.py` / `partitions.py`，再顺 `assets.py` 主链，最后看 `checks.py` / `backfill_plan.py` / `evidence.py` 和测试。

---

## 8. 动手清单

统一走 Docker devbox（Podman 把 `docker compose` 换成 `podman compose`，同一个 compose 文件）。

```bash
# 0. 前置：起最小依赖
cp infra/env/.env.example infra/env/.env.local
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml \
  up -d --build postgres minio minio_init

# 下面所有命令共用的前缀，本文档记作 DEVBOX
DEVBOX="docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox"

# 1. 契约合法 + definitions 可加载
$DEVBOX pytest tests/contract/test_week06_run_evidence_schema.py \
               tests/integration/test_week06_definitions_loadable.py -q
# 2. 生成 backfill dry-run plan
$DEVBOX python -m pipelines.data_factory.backfill_plan --partition 2026-04-17 --mode dry-run
# 3. 跑通整张 asset graph（一个分区）
$DEVBOX pytest tests/integration/test_week06_asset_graph_smoke.py -q
# 4. checks + evidence
$DEVBOX pytest tests/integration/test_week06_asset_checks.py \
               tests/integration/test_week06_run_evidence_generation.py -q

# 5. UI 路径：起全栈，打开 http://localhost:3000 找 week06_data_factory group
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml up -d --build
```

**验收标准不是"跑过了"，而是能回答这五个问题**：

1. 九个 asset 的依赖关系是什么？为什么 `backfill_plan` 是 `run_evidence` 的上游而不是下游？
2. `2026-04-17` 这个 demo partition 为什么是它？换成 `2026-03-01` 会让哪个 check 变成 `warning`？
3. 五个 check 里哪几个真正读了种子数据？哪个在 Dagster UI 上是空跑的？
4. 本次 `downstream_decision` 是什么？为什么不是 `proceed_to_week07`？要变成它得改哪个环境变量？
5. evidence JSON 里 `lakehouse_snapshot_id` / `dbt_invocation_id` 是有值还是 `not_available` reason code？为什么这样设计比伪造成 passed 更重要？

**加分练习**：

- 在种子 JSONL 里插一条重复 `ticket_id`，确认 `duplicate_idempotency` → `failed`、`run_evidence.status` → `failed`、`downstream_decision` → `hold_downstream`。**这是把 L03 三层幂等的第一层跑通的最短路径。**
- 把 `WEEK06_DEFAULT_PARTITION` 改成种子里没有的日期，看 `partition_completeness` 从 `passed` 变 `warning`，然后解释为什么 `downstream_decision` 仍然是 `dry_run_only`。
- 按讲义 L02 的复合分区思路，把 `partitions.py` 改成 `MultiPartitionsDefinition({"date": ..., "tenant": ...})`，看会连带改动 `assets.py` 哪几处、schema 的 `partition_key` 正则会不会失效——这最能体会"分区键一旦定下不要原地改"。

---

## 9. 易错点与边界

**概念层面**

- **Asset ≠ Task**。Task 描述"要执行的动作"，Asset 声明"应该存在的数据对象"；框架从 Asset 反推要跑哪些动作，不是反过来。
- **分区 ≠ 查询优化**。分区首要目的是可寻址性（能精确指着一格重跑），性能只是副产品。
- **Backfill ≠ Replay ≠ rerun**。backfill 补历史空洞、replay 重跑旧批次、rerun 是"用今天的代码改写历史事实"——第三个是事故来源。
- **幂等 ≠ 写入幂等**。写入层幂等只是三层里的一层，副作用层和下游层才是 99% 事故的真凶。
- **血缘 ≠ 血缘文档，表级血缘 ≠ 字段级血缘**。文档是人写的会过期，血缘是运行时事件流不会过期；表级只能回答"哪些表受影响"，回答不了"改这一个字段谁受影响"。
- **Runbook ≠ 故障文档 ≠ Postmortem**。没有具体命令、没有验证步骤、没人演练过的都不算 Runbook；Runbook 是事故进行时的指令脚本，Postmortem 是事故之后的组织学习产物。
- **`skipped` ≠ `failed` ≠ `not_available`**。Week06 里 `skipped` 是操作者刻意不执行（默认 dry-run 不写库），`not_available` 是可选下游证据缺失，`failed` 是必需 check 挂了。三者对应完全不同的 `downstream_decision`。
- **`snapshot_id` ≠ 分区键**。分区键定位"哪一格"，snapshot_id 定位"这一格的哪一次物化"。下游锁版本锁的是后者。

**范围边界（Week06 到底做到哪）**

Week06 交付的**不是一套生产级数据工厂，而是资产化编排的最小可读闭环**：一条 daily 分区的九节点 asset graph、五个 check、一份 dry-run backfill plan、一份 schema 合法的 run evidence。

runbook 的 Known Limitations 把刻意不做的写得很清楚：不引入 Dagster+（所以没有 Branch Deployments、没有 Cloud Asset Graph）；不做完整动态分区和复合分区；不重写历史数据，backfill 只有 dry-run 规划；不把 Week04/Week05 变成必需依赖，缺失时写 `not_available`；不复制 Week03 的 ingest 写入逻辑（`pipelines/ingestion/ticket_ingest.py` 是被调用不是被抄），默认 `WEEK06_INGEST_DRY_RUN=true` 不动 PostgreSQL；不做 Week07 解析和 Week08 检索。

留给后面的：真正的血缘后端与 OpenLineage 事件流、Skill Pack（Week09）、下游层幂等与 asset reconciliation（Week14 治理周）、trace 与可观测（Week12）。Week06 的产出物身份是**给 Week07 非结构化数据交付一个稳定、可追溯的结构化上游**。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. "Task"这个抽象具体在哪个诉求上服务不了 AI 下游？举一个 Airflow 能跑通但下游依然无法消费的场景。
2. 资产化四条军规里，哪一条最容易被"我们也用了 Dagster"糊弄过去？为什么？
3. 为什么"分区不是性能优化"？如果只把分区当查询加速，在一次事故补数时会具体损失什么？
4. 时间分区为什么必须用 `event_time` 而不能用 wall-clock？迟到数据会让这两者产生什么错位？
5. 业务从单租户变多租户，为什么正确做法是"新建复合分区 + 老数据归 default tenant"，而不是原地给老分区加维度？
6. "补数 = 时间旅行"和"补数 = 再跑一次脚本"，后者具体会制造什么新问题？`source_snapshot_at` 在其中起什么作用？
7. 幂等三层里，为什么说 99% 的补数事故不在写入层？各举一个副作用层和下游层的失败例子。
8. 表 ID 用 `uuid_v4()` 什么时候是对的，什么时候是隐患？确定性合成主键的代价是什么？
9. 为什么说"血缘文档"这四个字本身就是问题？运行时血缘凭什么不会过期？
10. 字段级血缘在哪四类 SQL 结构上会断链？为什么说 90% 自动 + 10% 手工补就是最佳实践？
11. 一份 Runbook 缺了 R4 Verification 会怎样？为什么"没人测试"这个反模式必须靠 Game Day 而不是靠 review 解决？
12. 本仓库的 `downstream_decision` 为什么在默认课堂模式下永远拿不到 `manual_review_required`？要改哪里？

---

## 11. 一句话收口

Week06 是整门课的**编排控制面**：Week02 定了什么数据有资格进来，Week03-05 把数据搬进来并算成指标，Week06 则回答"这份数据现在是哪一版、坏了怎么精准修、改了谁受影响、凌晨两点谁能照着修"。它把前五周的可执行路径升级成可寻址、可版本、可责任、可观测的资产，Week07 之后所有非结构化与 AI 链路的可追溯性，都建立在这一层之上。
