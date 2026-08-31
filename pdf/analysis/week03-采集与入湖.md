# Week 03 · 采集与入湖：Batch / CDC / Stream 的组合拳

> **一句话**：把 Week02 的 contract / manifest / gate 从"规则文件"变成"运行时对象"——用 batch_id、checkpoint、run report、recovery plan 四件事，把"采到一次"升级成"可重跑、可补数、可回放、可解释"。
>
> 讲义：`pdf/doc/week03-采集与入湖——Batch  CDC  Stream 的组合拳.pdf`（128 页 / 5 课时）

---

## 0. 本周主干

五节课是一条递进链，每一节都在给上一节补一个缺失的运行时对象：

```
L01 可靠性基线      run / state / evidence / recovery 四个前提
      ↓                        （心智：ingest 成功 ≠ ingest 可靠）
L02 Batch 主链路    幂等写入 + 重跑 + 完整性校验 + reconcile
      ↓                        （边界最清晰：source + window + batch_id）
L03 增量 / CDC      cursor / watermark / checkpoint + dedupe/idempotency key
      ↓                        （工程诚实：at-least-once，不承诺 exactly-once）
L04 资产流          asset / materialization / partition / backfill / asset check
      ↓                        （视角切换：任务跑了 → 资产可消费）
L05 恢复与补数      retry / rerun / replay / restore / backfill + runbook
      ↓
                    ingestion baseline → Week04 lakehouse / Week06 orchestration
```

两个值得单独记的口诀，以及一个五层记忆法：

**「manifest 决定这次接什么，state 决定接到哪里，report 决定到底发生了什么。」**
**「先定位，后恢复；先边界，后命令。」**
五个恢复动作对应五个层级：**retry 执行级 / rerun 同 job 再执行 / replay 输入级 / restore 系统级回退 / backfill 历史空洞**。

---

## 1. L01 · 从"能采上来"到"可重复采集"

生产里最危险的不是采不到，而是**采到了却复现不了**——今天能采，明天漂，后天想重跑却找不到证据。真正的风险不是一次失败，而是系统持续把不可解释的输入向下游传播。

### Ingest baseline 的五个条件

少一条，后面的 lakehouse、RAG、eval 都踩在不稳定输入上：

| 条件 | 具体表现 | 缺了会怎样 |
|---|---|---|
| 输入边界明确 | manifest / source / batch window 显式声明 | 不知道这次到底接了谁 |
| 执行可以重复 | rerun 不制造额外副作用 | 失败恢复变成赌博 |
| 状态可以持久化 | `run_id` / `checkpoint` / `cursor` / `watermark` 不能只在日志里 | crash 后不知道从哪继续 |
| 结果可以解释 | run evidence / report | 失败后无人能复盘 |
| 恢复有路径 | retry / replay / backfill 有边界 | 每次都靠临时救火脚本 |

### 五个追踪锚点 + 三个状态对象

**锚点不是日志装饰，而是恢复和审计的入口。先问有没有锚点，再问有没有工具。** 五个锚点：`manifest_id`（引用哪份输入声明）、`batch_id`（业务时间边界）、`run_id`（这次执行的唯一身份）、`source_fingerprint`（来源有没有变）、`trace_id`（跨模块排障链路）。

三个状态对象要严格分开（L03 会再深化）：

| 对象 | 回答什么 |
|---|---|
| `checkpoint` | 状态**落在哪里**：文件、表、asset metadata，还是只有日志 |
| `cursor` | 下一次**从哪里继续读**：`updated_at` / offset / LSN / sequence |
| `watermark` | 系统**已确认处理到哪里**：用于迟到、乱序、补数判断 |

### 四类事故（本周的排障母题）

| 事故 | 成因 | 屏幕上的样子 | 实际坏在哪 |
|---|---|---|---|
| **Duplicate** | 重放/重试/cursor 粒度不足 | 报表数值高一点、RAG chunk 出现重复内容 | retry 变成重复副作用，dedupe/idempotency key 缺位 |
| **Gap** | 窗口错位、失败未补、source 漏读 | 系统没报错，数据只是少一点，报告仍能生成 | **state 先于事实前进**，watermark 与写入结果不一致 |
| **Mismatch / Drift** | 上游改口径，contract 未更新 | 字段还在、schema 仍过，只是"偶尔不准" | load semantics 漂移，cursor 失去业务含义 |
| **No Traceability** | 无 `run_id` / `manifest_id` / coverage | 日志里有 done，表里有数据 | 没法证明"这批数据"是什么 |

Gap 的机制值得单独记：读了一半失败 → checkpoint 还是更新了 → 下次从新位置继续 → 缺口被固化。**这是增量系统最致命的一类 bug，因为监控不报错。**

### 排障顺序与六个必答问题

不要一上来重跑。顺序固定：`manifest_id`（这次声明是什么）→ `run_id`（哪次执行出问题）→ `checkpoint / cursor`（状态走到哪）→ manifest coverage（哪些 source 被覆盖）→ 判定事故类别。

如果今晚 ingest 失败，第二天必须能回答：哪个 manifest 在跑 / 跑到哪个 source（读取、校验、写入还是对账失败）/ 哪些已写入 / 哪些未写入（缺口能否被 bounded replay 覆盖）/ 下游看到什么（旧数据、新数据还是半成品）/ 恢复动作是什么。答不出来就不算有 baseline。

Week02 的工件在这里全部换了身份：contract 从字段规则变成 **admission gate**，manifest 从装车单变成 **batch boundary**，gate action 从 pass/fail 变成**分流路径**，run evidence 从观察记录变成**恢复依据**。Week03 不推翻 Week02，而是消费 Week02。

---

## 2. L02 · 批量采集主链路

先讲 batch 不是因为它落后，而是因为它**边界最清晰**：source + window + `batch_id` 可显式声明，因此最适合训练幂等、重跑、完整性校验、reconcile，也为后续 incremental / CDC 提供可靠参照物。

### 四个概念不要混用（batch baseline 的四道门）

| 概念 | 解决什么 | 没有它会怎样 |
|---|---|---|
| **幂等写入** | 重复到达/重复执行时不制造额外副作用 | 重跑后越写越脏 |
| **重跑 rerun** | 同一条 job 失败后能安全再执行 | 失败恢复变成赌博 |
| **完整性校验** | 写完后验证数量、错误、跳过是否合理 | 写完了但不知道写对没 |
| **reconcile** | manifest 声明、写入结果、异常记录能否对上 | 少/多/错都无法解释 |

**幂等 ≠ 去重**：幂等保护写入副作用，去重判断输入是否重复。

### Bronze / Silver 写入语义不同，幂等策略也不同

**不要把所有层都当成 append，也不要一律 upsert。每一层有自己的写入承诺。**

| 层级 | 写入目的 | 幂等判断 |
|---|---|---|
| Bronze `raw_ticket_event` | 保存事件/来源证据 | `event_id` 或 `source_id + event_time` 去重 |
| Silver `ticket_fact` | 形成可消费事实表 | `ticket_id` upsert，保留更新时间 |
| Report / State | 解释本次运行结果 | `run_id + batch_id` 唯一化 |
| Quarantine | 隔离坏记录 | `reason_code + source pointer` 可复盘 |

### 完整性校验的六个数与 reconcile 的五个对象

六个数：`total`（输入总量）/ `valid`（合同内合法）/ `invalid`（坏记录）/ `inserted`（新增写入）/ `skipped`（幂等跳过）/ `errors`（执行错误）。**Total ≠ Valid ≠ Inserted，这三个差异就是对账入口。**

| 对账对象 | 要问的问题 | 失败信号 |
|---|---|---|
| Manifest coverage | manifest 里的 source 都被处理了吗 | source missing / skipped without reason |
| Source count | 输入记录量与读取量一致吗 | `total` 不一致 |
| Valid / Invalid | 合法、非法、隔离是否闭合 | `valid + invalid != total` |
| Bronze / Silver | 写入层之间能否互相解释 | Bronze 有，Silver 缺 |
| Unexplained gap | 有没有未解释缺口 | report 里没有 `reason_code` |

**Reconcile 的目标不是"数值漂亮"，而是"缺口可解释"。**

### rerun vs replay vs backfill

| 动作 | 对象 | 典型场景 | 风险 |
|---|---|---|---|
| `rerun` | 同一条 job | 执行中断、依赖服务短暂失败 | 没有幂等就重复写 |
| `replay` | 同一批输入 | 验证幂等、重放 source 批次 | 输入版本混淆 |
| `backfill` | 历史范围/分区 | 补历史空洞或重算旧分区 | 影响范围过大 |

**rerun 是执行级再跑，replay 是输入级重放。**

重跑设计的"四个同一"：同一批次（`batch_id` / `manifest_id` 不变，避免把重跑当新数据）、同一输入（`source_fingerprint` 不变）、同一状态（checkpoint / report 能解释从哪恢复）、同一策略（contract / gate action 不要悄悄变化）。再加可观察输出（`inserted` / `skipped` / `errors` 可比较）和可记录结论（runbook 写清为什么 rerun 而不是 replay）。

### dry-run 的边界

| 阶段 | 能验证什么 | 验证不了什么 |
|---|---|---|
| dry-run | manifest / schema / contract / 大致路径 | DB constraint / transaction / upsert conflict |
| real write | 实际写入、约束、错误处理 | 是否有完整解释（仍要看 report） |
| integrity check | 数量、错误、跳过是否闭合 | 业务语义是否完全正确 |
| reconcile | manifest 与结果是否对上 | 上游未来是否继续稳定 |

### 真实写入的坑：不是所有失败都在 schema 层

DB constraint（唯一键/非空/外键）、upsert conflict（覆盖历史证据）、transaction failure（半批写入）、clock drift（窗口边界与更新时间错位）、retry storm（错误重试放大重复写）、partial commit（Bronze/Silver 不一致）、quarantine missing（坏记录直接丢失）、weak report（无法解释结果）。最容易 quietly fail 的四处：`status` 合法但语义漂、`updated_at` 口径不清（发生时间 / 更新时间 / 入湖时间混用）、`ticket_id` 非稳定主键导致 upsert 对错对象、Bronze 写成 Silver 不全。

设计说明模板就是五问：source 是谁（`source_id` / owner / `contract_ref`）→ batch 边界是什么（`batch_id` / window / fingerprint）→ idempotency key 是什么（`event_id` / `ticket_id` / run+sink key）→ integrity check 看什么（六个数）→ 失败后怎么办（rerun / replay / backfill 的选择）。

---

## 3. L03 · 增量与 CDC

增量真正难在**状态与恢复**，不在"少读一点数据"。全量简单在"边界大但清楚"，增量难在"边界小但持续变化"：重复不再只来自重跑（cursor 粒度、slot 重发、retry 都会），迟到要有 watermark 策略，乱序会与业务语义错位，恢复必须知道 checkpoint / LSN / offset，解释也从"一次 run report"变成"持续状态 + 分区 report"。

### 五个概念必须拆开

**混用这些词，是增量系统最常见的设计味道。**

| 概念 | 回答什么 | 例子 |
|---|---|---|
| `cursor` | 下一次从哪里继续读 | `updated_at` / offset / LSN |
| `watermark` | 当前承认处理到哪里 | 迟到/乱序判断基准 |
| `checkpoint` | 这个边界落在哪里（持久化） | state 文件 / state 表 / asset metadata |
| `dedupe key` | 两条**输入**是否同一事件 | `event_id` / `ticket_id+updated_at` / `source_id+LSN` |
| `idempotency key` | 重复**写入**是否有副作用 | `batch_id+primary_key` / `run_id+sink_key` |

另外两个容易混进来的：`primary key`（目标表里一个事实对象如何定位，如 `ticket_id` / `doc_id+version`）、`trace key`（跨系统排障，如 `trace_id` / `run_id`）。**写入层幂等不能替代输入层去重。**

### cursor 字段怎么选：每种都有风险

**不要问"哪个字段好"，先问来源是否保证它的语义。**

| 字段 | 适合场景 | 主要风险 |
|---|---|---|
| `updated_at` | 常规数据库表增量 | 被回写、没更新、粒度太粗 |
| `event_time` | 事件发生时间 | 迟到和乱序会打穿窗口 |
| `sequence_id` | 单调递增业务序列 | 需要来源保证单调 |
| `LSN` | 数据库 WAL / CDC | 偏日志位置，不等于业务语义 |
| `offset` | 消息/日志流位置 | 只代表读取位置，不代表数据事实 |

`updated_at` 的八个坑：被回写、没更新（数据变了 cursor 没变）、粒度太粗（一天内多次变化无法区分）、语义漂移（业务更新时间 → ETL 时间）、时区不统一、NULL/default、源端延迟、并发写入顺序不可控。**它可以用，但必须配合窗口、容忍区、dedupe 和 report。**

### 迟到 / 重复 / 乱序的第一轮决策表

**不要把所有异常都 reject。** 这张表就是 runbook 的前身（讲义建议照骨架写成 CSV）：

| case | condition | action | evidence |
|---|---|---|---|
| `late_in_window` | `event_time < watermark` 但在容忍区内 | accept + mark late | `event_time` / `observed_at` |
| `late_out_of_window` | 超出容忍区 | quarantine / backfill review | window / `reason_code` |
| `duplicate_input` | 同一 dedupe key | skip / merge | `original_event_id` |
| `duplicate_write` | 同一 idempotency key | skip write | `sink_key` |
| `semantic_drift` | schema ok，含义变了 | quarantine + owner review | contract version |

**动作背后必须有 `reason_code`，否则后面无法回放。**

### CDC 解决什么、没解决什么

CDC 是 **snapshot + change stream 的组合，不是 exactly-once 魔法**。

- PostgreSQL logical replication：publication / subscription 声明与消费变化；**先 initial snapshot 建立起点，再持续发送 INSERT/UPDATE/DELETE**；同一 subscription 内按发布顺序应用。
- logical decoding + replication slot：从 WAL 抽取持久化变化，slot 代表可重放的 change stream。但**slot 位置只在 checkpoint 持久化，crash 后最近的 changes 可能再次发送**——这是 documented behavior，不是 bug。所以客户端必须自己 dedupe + 幂等写入。
- Debezium 默认 **at-least-once**，不漏 change 但 record 可能多次投递，且**自身不实现内部去重层**；exactly-once 需要 Kafka Connect distributed mode + 版本与配置前置条件，官方仍提示边界。

**"at-least-once + 幂等写入 + 去重 + 可回放恢复" 比空喊 exactly-once 更可靠。** 在真实系统里，重复、重发、迟到、crash recovery 都不是罕见异常，而是**运行语义**。可交付的目标是：能复现、能定位、能补数、能解释。

### 增量链路最常见的假动作

**共同点：把恢复问题推给未来。**

| 假动作 | 为什么危险 | 修正 |
|---|---|---|
| 只存 `last_updated_at` | 不知道状态来自哪次 run | checkpoint 带 `run_id` / source / report |
| 只看 offset | offset 不是业务事实 | offset + dedupe + 业务 key |
| 遇到重复就删 | 可能删除真实多版本 | 保留证据并定义 dedupe 规则 |
| 承诺 exactly-once | 忽略 crash 现实 | 讲清 at-least-once + 幂等 |
| 没有容忍窗口 | 迟到数据被静默丢弃 | watermark + late policy |

---

## 4. L04 · 从任务流到资产流

**任务流回答"跑没跑"，资产流回答"什么数据资产可不可信"。**

| 任务流回答 | 数据工程真正关心 |
|---|---|
| 哪个脚本跑了 / 失败 / 慢 | 哪个资产已产生 / 分区缺失 / 版本不可信 |
| `job exit code = 0` | 哪个下游资产应该阻断 |
| 重跑某个脚本 | 补哪一个 asset + partition |

### 五个关键概念

| 概念 | Week03 里最该抓住什么 | 典型误解 |
|---|---|---|
| **Asset** | 采集链路真正持续存在的**持久化结果对象**（表、文件、清单、模型） | 把函数当资产 |
| **Materialization** | 一次资产被成功产出的**证据** | 把 job 成功当资产成功 |
| **Partition** | 未来增量、回放、补数的窗口/子集 | 等 Week06 再想 |
| **Backfill** | 对缺失/需重算的**分区资产**补跑 | 遇到问题全链路重跑 |
| **Asset Check** | 资产健康状态约束 | 只是另一个测试框架 |

Dagster 官方定义支撑这几条：asset 是持久化存储中的对象；asset definition 描述资产应该存在以及如何生成；materialize 是运行函数并把结果保存到持久化存储；**asset definition 知道 dependencies，ops 本身不天然知道**。

### 三个对象必须分开

**manifest 不是 asset，job 成功不等于下游可消费。** `manifest` 回答"这次 ingest 想接什么、怎么接"（错误：把它当资产）；`asset` 回答"实际产生了什么持久化结果"（错误：把函数名当资产名）；`job` 只是**触发** materialization 的执行动作（错误：把 job 成功当资产可消费）；`asset check` 回答资产是否满足健康约束（错误：只看脚本退出码）。

### 一次 materialization 该挂哪些 metadata

**materialization metadata 是 run evidence 的资产化版本。** 八组：`identity`（`run_id` / `batch_id` / `asset_key`）、`manifest`（`manifest_id` / `contract_ref`）、`source`（`source_id` / `source_fingerprint`）、`coverage`（source coverage / partition key）、`counts`（`row_count` / `reject_count` / `skipped`）、`quality`（check result / `reason_code`）、`state`（checkpoint / watermark after）、`lineage`（upstream / downstream assets）。

### Partition、Backfill、Asset Check

分区不是只为大数据性能，**也为恢复边界服务**：ticket events 按天、doc snapshot 按 manifest batch、replay 只重放受影响窗口、backfill 补齐旧分区。**没有 partition 思维，backfill 很容易变成"重跑全链路"。**

**backfill 的主语是 asset + partition，不是脚本名字。** 两种触发：分区没 materialize（补缺失），或 contract/逻辑变化影响历史（重算旧分区）。

Asset check 能表达：关键字段 null ratio 阈值、某窗口记录数不能异常低、schema shape 与 contract 对齐、freshness、异常比例可解释、lineage（来源资产必须存在）、PII boundary（敏感字段不得进入通用 serving）、gate action（fail / warn / quarantine）。**后面很多 gate 会长成 asset check。**

这节课的正确姿势不是大重构：不要重写 Dagster 全栈、不要自己造 orchestration、不要立刻补全 sensors/schedules、不要把脚本名当资产名。要做的是读懂资产图、识别已有资产、补 metadata / partition / policy，为 Week04（Iceberg 需要稳定 asset 边界与 partition 语义）和 Week06（恢复围绕 asset + partition）接力。

---

## 5. L05 · 故障自愈与补数

### 五个动作先拆开

**它们不是同义词，主语不同，边界也不同。**

| 动作 | 真正解决什么 | 什么时候用 | 最容易被误用成 |
|---|---|---|---|
| `retry` | 执行级短暂失败 | 网络抖动、服务临时不可用 | 无脑重试 |
| `rerun` | 同一 job 再执行 | 上次执行中断 | replay |
| `replay` | 同一批输入重放 | 验证幂等、同批重走 | 新数据 ingest |
| `restore` | **回到已知可用状态** | 下游/状态被污染 | replay |
| `backfill` | 补历史空洞或重算旧分区 | 历史缺口、逻辑变更 | 全链路重跑 |

`restore` 要单独看：当状态表、对象存储或下游表**已被污染**时，直接 replay 只会扩大问题，必须先回到已知可用快照/备份。**遇到污染，先问当前状态能不能信。**

"出故障就全量重跑"不是成熟答案：成本高、可能覆盖或污染更多资产、不知道到底修复了什么、无法形成可复用流程。**成熟团队默认做 scoped recovery。**

### 恢复决策树与锚点

```
异常出现（gap / duplicate / drift / failure）
      ↓
当前状态能信吗？（state / sink / run log 是否一致）
      ├─ 不能信 → 先 restore 到已知可用状态
      └─ 能信   → 判断层级：执行层 retry/rerun？同批 replay？历史 backfill？
      ↓
记录：run log / recovery report / runbook
```

恢复不是命令选择，而是**锚点驱动的判断**：contract（输入是否合格）→ manifest（恢复哪批/哪源）→ state/checkpoint（从哪里恢复）→ run log/report（失败在哪层）→ recovery decision → runbook。**缺任何一个锚点，恢复就会变成猜。**

### replay 还是 backfill

| 场景 | 推荐动作 | 为什么 |
|---|---|---|
| 网络抖动中断 | retry / rerun | 输入没变，执行层短暂失败 |
| 合法 manifest 想重走同一批验证幂等 | replay | 同批输入重放 |
| 某日期分区没入湖 | backfill | 补历史空洞 |
| contract 变了需要重算历史 | backfill | 重算旧分区 |
| replay 后仍少数据 | 先查 state / run log 再决定 | 先定位缺口范围 |

**恢复动作不是越大越安全，越精准越可控。**

### 决策文档六项、Runbook 六模块

恢复决策至少写：场景描述、当前症状、目标动作、**为什么不是另外几个**（排除理由）、输入边界（manifest / source / window / partition）、验收标准（恢复后如何证明成功）。

Runbook 六模块：触发条件（什么信号进入 runbook，不要只写"失败时"）、前置检查（先查 contract / manifest / state / report 四个锚点）、执行命令（统一 Docker-first，命令要可复制）、风险提醒（会影响哪些资产/分区）、验证方式（counts / reconcile / checks）、升级路径（何时人工 review / owner 介入）。

**Runbook 为什么不是最后才写**：它逼你讲清术语、暴露缺失能力（没有 state、report、command 就写不出来）、缩短恢复时间、连接 Week12 tracing 与 Week14 governance。**它是生产能力的压力测试。** 角色边界同样重要——生产里恢复失败常常不是技术不会，而是责任不清：判断者（依据 report/state）、批准者（确认影响范围）、执行者（按 runbook）、记录者（写 recovery report）、Owner（解释 source/contract 语义）、Reviewer、Escalation、Auditor。

### 讲义自认的能力边界（很诚实，值得记）

**还没有的**：通用 replay service、自动 checkpoint/state manager、一键 backfill engine、recovery policy engine。**已有的**：contract / manifest / dry-run、asset entry / report 思维、runbook 文档入口、恢复决策边界。

**成熟不是假装全自动，而是把边界讲清、证据写实。**

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 baseline 定义与边界 | `docs/blueprints/week03/ingestion_baseline_v1.md` | "当前还没有 fully automated 的部分"这一节 |
| L01/L05 Docker-first 全流程 | `runbooks/ingestion_runbook_v1.md` | Step 1-7，本周唯一权威命令清单 |
| L01 run evidence 落盘 | `pipelines/ingestion/reporting.py` | `summarize_status()` / `recommend_recovery_action()` |
| L02 admission gate | `pipelines/ingestion/seed_loader.py` | `--manifest-path` 逐份锁定、`_write_report_json()` |
| L02 batch 设计说明 | `docs/blueprints/week03/batch_ingestion_design_v1.md` | 四个最小对象与责任边界 |
| L02 ticket batch 主链路 | `pipelines/ingestion/ticket_ingest.py` | `upsert_ticket_bronze()` 的 `ON CONFLICT DO NOTHING` vs `upsert_ticket_silver()` 的 `DO UPDATE` |
| L02 Bronze 幂等键 | `infra/migrations/007_week03_ticket_ingest_idempotency.sql` | 先去重历史行，再建 `uq_raw_ticket_event_source_fingerprint` |
| L02 document batch 链路 | `pipelines/ingestion/doc_ingest.py` | `raw_bucket_for()` 分模态桶、MinIO 不可用时降级 |
| L02 幂等回归测试 | `tests/integration/test_ticket_ingest_idempotency.py` | 跑两遍断言 `second["bronze_duplicates"] == 1` 且 raw 只有 1 行 |
| L02 完整性数字 | `ticket_ingest.py` 里的 `stats` dict | `total/valid/invalid/processed/inserted/skipped/errors` + `bronze_*` / `silver_upserted` |
| L03 增量策略 | `docs/blueprints/week03/incremental_ingest_strategy_v1.md` | 五种 `load_mode` 对 checkpoint 的最小要求 |
| L03 checkpoint 状态对象 | `pipelines/ingestion/ingest_state.py` | `IngestCheckpoint` 五个字段、`upsert_checkpoint()` 的合并语义 |
| L03 状态文件实体 | `data/canonization/checkpoints/week03_ingest_state.json` | `schema_version` + `checkpoints[]` |
| L03 状态读写测试 | `tests/integration/test_ingest_state.py` | 写入-读回闭环 |
| L03 `load_mode` 校验 | `pipelines/ingestion/seed_loader.py`（约 204-224 行） | 每种 mode 强制哪些 `selection_window` 字段 |
| L04 资产化入口 | `pipelines/ingestion/assets.py` | `seed_manifests` / `raw_doc_assets` / `raw_ticket_events` / `ingest_all_job` |
| L04 Definitions 注册 | `pipelines/definitions.py` | ingestion assets 与 Week06 asset checks 分别从哪注册 |
| L04 资产流向记录 | `docs/blueprints/week03/asset_flow_plan_v1.md` | Document / Ticket 两条 flow 的完整落点链 |
| L04 partition / asset check 的真身 | `pipelines/data_factory/partitions.py`<br>`pipelines/data_factory/checks.py`<br>`pipelines/data_factory/backfill_plan.py` | 讲义 L04 讲的概念，实现在 Week06 目录 |
| L05 五类恢复动作 | `pipelines/ingestion/replay_backfill.py` | `VALID_MODES`、`_build_execution_plan()` |
| L05 恢复策略文档 | `docs/blueprints/week03/replay_backfill_strategy_v1.md` | plan-first + `--execute --input` 两段式 |
| L05 恢复计划测试 | `tests/integration/test_replay_backfill_dry_run.py` | 四种 mode 都能出 plan、非法 mode 被拒 |
| L05 run evidence 实物 | `reports/week03/seed_loader_smoke_report.json`<br>`ticket_ingest_smoke_report.json`<br>`doc_ingest_smoke_report.json`<br>`recovery_decision_log.json` | 对照讲义 smoke report 六字段组，看哪些真落盘了 |

### 代码里值得单独看、但讲义没展开的细节

**1. Bronze 幂等键不是讲义说的 `event_id`，而是 `(source_id, source_fingerprint)`。** `event_id` 在 `raw_ticket_event` 里是 `gen_random_uuid()` 默认值，每次插入都不同，当不了去重键。真正的去重键是整条 payload 的 SHA256：

```python
def ticket_source_fingerprint(ticket: dict) -> str:
    return hashlib.sha256(json.dumps(ticket, sort_keys=True).encode()).hexdigest()
```

代价是：**只要原始 JSON 有任何一个字节变化，就会被当成新事件写入 Bronze**。这是"保留全部来源证据"和"严格去重"之间的显式取舍。

**2. `ensure_ticket_bronze_idempotency()` 在每次真实写入前都会跑一遍**，等价于内联执行 migration 007（兼容老的本地 DB volume），代价是每次 ingest 都做一次 DELETE + `CREATE INDEX IF NOT EXISTS`。

**3. checkpoint 只在 `errors == 0 and invalid == 0` 时才写**，否则记 `checkpoint_skipped_reason = "ingest_not_clean"`。这是讲义 Gap 事故（state 先于事实前进）的直接防御。`--no-checkpoint` 可关掉（记 `state_path_disabled`），**dry-run 完全不写 checkpoint**。

**4. cursor 取值是 `updated_at or created_at`，用字符串比较取最大值**（`if cursor and cursor > source_cursors.get(source_id, "")`）。这正好踩在讲义 L03 警告的 `updated_at` 风险上：字符串比较依赖 ISO-8601 且时区统一，一旦上游给出带偏移量的时间戳（如 `+08:00`），排序就会错。

**5. `reporting.py` 的推荐动作是硬编码优先级**，讲义没提，但它就是自动化恢复决策树的雏形：`errors or invalid → rerun_after_fix`；`quarantined → replay_after_repair`；`warnings → retry_after_metadata_repair`；否则 `proceed_to_next_stage`。注意它把 quarantine 映射到 replay、warn 映射到 retry，方向与 L05 的场景表一致。

**6. Silver 的 `ticket_fact` 是全字段 upsert，会覆盖历史值**；`doc_ingest.py` 的 `raw_doc_asset` 用 `ON CONFLICT (source_id) DO UPDATE ... quality_gate = 'pending'`——**同一个 source 重跑会把质量门禁状态重置回 pending**。这是讲义 "upsert conflict 覆盖历史证据" 那个坑的真实样本。

**7. `pipelines/ingestion/assets.py` 里的三个 Dagster asset 目前不写 DB**，文件里还留着 `# TODO(Week03): 写入 PostgreSQL raw_doc_asset 表`。真实写入走 `doc_ingest.py` / `ticket_ingest.py` CLI，两条路是**并行**而非串联的。讲义说"repo 已有资产化入口"是对的，但不要误以为 materialize 一次资产就完成了 ingest。

**8. ingestion assets 没有 partition、没有 asset check，materialization metadata 只到 count 级别。** 讲义 L04 讲的 partition / backfill / asset check 在仓库里的实现全部在 `pipelines/data_factory/`（Week06）。Week03 只提供了 asset key 和 job。

---

## 7. 讲义与仓库对不上的地方

| 讲义写的路径 / 命令 | 实际情况 |
|---|---|
| `docs/blueprints/week03/checkpoint_state_v1.md`（p71、p127 列为交付物） | **不存在**。checkpoint 说明实际写在 `incremental_ingest_strategy_v1.md` 和 `batch_ingestion_design_v1.md` 里 |
| `docs/blueprints/week03/late_arrival_decision_table.csv`（p71/p72） | **不存在**。迟到/重复/乱序决策表只在讲义里，仓库没有落地 CSV |
| `docs/blueprints/week03/partition_backfill_strategy_v1.md`（p97） | **不存在**。对应内容在 `replay_backfill_strategy_v1.md` + Week06 的 `pipelines/data_factory/backfill_plan.py` |
| `reports/week03/*.md`（p20、p39、p112 反复出现） | 实际是 **4 个 JSON**：`seed_loader_smoke_report.json` / `ticket_ingest_smoke_report.json` / `doc_ingest_smoke_report.json` / `recovery_decision_log.json`。没有任何 `.md` 报告 |
| `reports/week03/ingest_smoke_report.md`（p21）<br>`dagster_materialization_smoke_report.md`（p97）<br>`recovery_drill_report.md`（p118/123/127） | 三份都不存在。恢复证据实际是 `recovery_decision_log.json` |
| p21 要求写 `ingestion_baseline_v1.md` | **已存在且已定稿**，不用自己新建 |
| p45 的 `python -m pipelines.ingestion.ticket_ingest --dry-run --limit 20 --batch-id week03-smoke` | **照抄会失败**：`--input` 是 required 参数。正确命令见 `runbooks/ingestion_runbook_v1.md` Step 3，输入用 `tests/integration/fixtures/week03/tickets-smoke.jsonl` |
| p71 的 `mkdir -p docs/blueprints/week03 && touch ...` | 目录已存在且有 5 份文档，直接 touch 不会覆盖，但别以为要从零写 |
| p85 说 assets 已"接入真实采集器" | `raw_doc_assets` / `raw_ticket_events` 仍是 `TODO(Week03)`，只 stage 元数据不写 DB |
| 按名字去 `pipelines/incremental/` 找 Week03 增量实现 | 找错地方。`pipelines/incremental/update.py` 的 docstring 明确写 "for Week07 parse outputs"，只有一个 `decide_incremental_update()` 做 fingerprint 比较。**Week03 的增量状态在 `pipelines/ingestion/ingest_state.py`** |

另外三处**仓库内部**的不一致，也别浪费时间找：

- `runbooks/ingestion_runbook_v1.md` 引用架构图 `docs/assets/week03/ingest-detailed-architecture.png`，但整个 `docs/assets/` 目录不存在，图是断链的。
- 同一份 runbook 说 state 在 `data/state/`，实际路径是 `data/canonization/checkpoints/week03_ingest_state.json`（见 `ingest_state.py` 的 `DEFAULT_STATE_PATH`）。
- 已落盘的 `reports/week03/ticket_ingest_smoke_report.json` 是旧格式，缺少当前代码会生成的 `processed` / `bronze_inserted` / `bronze_duplicates` / `silver_upserted` 和整个 `checkpoint` 块。自己跑一次就能看到差异。

---

## 8. 动手清单

统一走 Docker devbox。完整版见 `runbooks/ingestion_runbook_v1.md`，下面是压缩后的主干。所有命令共用同一前缀：

```bash
DC="docker compose --profile tools --env-file infra/env/.env.local -f infra/docker-compose.yml run --rm devbox"

# 0. 起服务
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml up -d --build

# 1. contract 仍是门禁
$DC pytest tests/contract/ -v

# 2. admission gate + run evidence 落盘
$DC python -m pipelines.ingestion.seed_loader \
    --manifest-dir data/seed_manifests \
    --report-json reports/week03/seed_loader_smoke_report.json

# 3. batch 主链路 dry-run（注意 --input 必填）
$DC python -m pipelines.ingestion.ticket_ingest \
    --input tests/integration/fixtures/week03/tickets-smoke.jsonl \
    --batch-id batch-week03-ticket-smoke --dry-run \
    --report-json reports/week03/ticket_ingest_smoke_report.json

# 4. 真实写入两次验证幂等：去掉 --dry-run，重复执行同一条命令
#    第二次的 bronze_duplicates 应等于第一次的 bronze_inserted

# 5. 恢复计划（默认只出 plan，不改 DB）
$DC python -m pipelines.ingestion.replay_backfill \
    --mode replay --source-id structured:tickets:seed_batch_001 --dry-run \
    --report-json reports/week03/recovery_decision_log.json

# 6. Week03 集成测试
$DC pytest tests/integration/test_ingest_state.py \
           tests/integration/test_ticket_ingest_idempotency.py \
           tests/integration/test_replay_backfill_dry_run.py -v

# 7. Dagster 资产图：http://localhost:3000
```

**验收标准不是"跑过了"，而是能回答这七个问题**：

1. `total` / `valid` / `invalid` / `inserted` / `skipped` / `errors` 分别是多少？三个差值各自由什么解释？
2. 第二次真实写入时 `bronze_inserted` 为什么变 0、`bronze_duplicates` 为什么变 1？Silver 层同时发生了什么？
3. `week03_ingest_state.json` 里 `last_processed_cursor` 从哪个字段来？这一批有一条 invalid 记录时 checkpoint 会不会写？为什么这个设计能防 Gap 事故？
4. `recovery_decision_log.json` 里的 `execution_plan` 为什么是这几步？`checkpoint_snapshot` 从哪读的？
5. 用 `--mode backfill` 但不给 `--start-cursor` / `--end-cursor`，`warnings` 和 `status` 会变成什么？
6. Dagster UI 里 `seed_manifests → raw_ticket_events` 的 materialization 带了哪些 metadata？它和 `ticket_ingest.py` 写的 report 是同一份证据吗？
7. 这次运行的 `manifest_id` / `batch_id` / `run_id` / `source_fingerprint` 分别落在哪个文件的哪个字段里？

**加分练习**：

- 复制一条 smoke fixture 记录，只改 `subject` 里一个字符，真实写入后观察 Bronze 行数，理解 fingerprint 幂等的粒度代价。
- 手动把 `week03_ingest_state.json` 的 `last_processed_cursor` 改成未来时间，再跑 replay plan，看 plan 是否还成立——这是"state 先于事实前进"的手工复现。
- 照 L03 骨架把迟到/重复/乱序决策表写成 `docs/blueprints/week03/late_arrival_decision_table.csv`（仓库缺这一份），每行必须有 `reason_code`。

### 动手清单参考答案

先自己答完上面的验收问题和加分练习，再往下对。

1. smoke fixture 两条都合法时，dry-run 预期 `total=2`、`valid=2`、`invalid=0`、`inserted=0`、`skipped=2`、`errors=0`（dry-run 不写库，合法行记 skipped）。三个差值：`total−valid=invalid`（合同外）；`valid−inserted` 在 dry-run 里是「没落盘」，真实写入里才拆成 inserted / skipped；`errors` 是执行失败，不是非法记录。Reconcile 要的是缺口可解释，不是数字好看。
2. 第二次真实写入，Bronze 唯一键 `(source_id, source_fingerprint)` 冲突走 `ON CONFLICT DO NOTHING`，所以 `bronze_inserted=0`、`bronze_duplicates` 等于第一次的 `bronze_inserted`。Silver 仍 `DO UPDATE`，`silver_upserted` 还会加：当前事实被刷新，来源事件不再多一行。
3. `last_processed_cursor` 来自 `updated_at or created_at`（字符串取最大）。这一批只要有 `invalid` 或 `errors`，checkpoint **不写**（`checkpoint_skipped_reason=ingest_not_clean`）；dry-run 也完全不写。这样 state 不会在事实写完之前前进，避免「读一半失败 → 水位已推 → 缺口被固化」。
4. `--mode replay` 的 plan 是：锁定 source → 先看 checkpoint → 按已有 `batch_id` / `last_success_batch_id` 重放已知批次 → 先写 recovery report 再碰存储。`checkpoint_snapshot` 从 `data/canonization/checkpoints/week03_ingest_state.json` 读（`ingest_state.py` 的 `DEFAULT_STATE_PATH`），不是 runbook 里写的 `data/state/`。
5. 缺 `--start-cursor` / `--end-cursor` 时，plan 仍会出「先构造历史窗口」几步，但 `warnings` 会出现 `Backfill mode expects both start_cursor and end_cursor.`，`status` 变成 `warning`（有 warning 就不是 `ok`）。说明 backfill 没有边界就不能当真执行。
6. Dagster 里 `seed_manifests` 主要挂 `manifest_count` / `manifest_ids`；`raw_ticket_events` 主要挂 `event_source_count`。这是资产化入口的 count 级 metadata，**不是** `ticket_ingest.py` 那份带六个数和 checkpoint 的 report。两条路并行：asset 目前不写 DB（仍有 `TODO(Week03)`），真实写入走 CLI。
7. `manifest_id` 在 seed_loader 报告的 `results[].manifest_id` 和 Dagster `manifest_ids`；`batch_id` 在 CLI 参数、两份 smoke report、checkpoint 的 `last_success_batch_id`；`run_id` 在 seed_loader 是 `seed-loader::{batch_id}`，ticket_ingest 是 `ticket-ingest::{batch_id}`；`source_fingerprint` 落在 Bronze 行上（payload SHA256），不在 Dagster metadata 里。不要去找不存在的 `reports/week03/*.md`。

加分练习：
- 只改 `subject` 一个字符后再写入：Bronze 会**多一行**。说明幂等键是整条 JSON 的 fingerprint，任何字节变化都算新事件——这是「保留来源证据」和「严格去重」的代价，不是让你去改生产库。
- 把 `last_processed_cursor` 改到未来再出 replay plan：plan 仍会引用这份超前 state，等于把还没发生的窗口当成已处理。看完后把 state 文件恢复；这只用来理解 Gap，不要带着脏 state 做真实写入。
- 补 `docs/blueprints/week03/late_arrival_decision_table.csv` 后，每行应能看到 `case / condition / action / evidence / reason_code`。没有 `reason_code` 的动作后面无法回放，表格才算落地讲义那张决策表。

---

## 9. 易错点与边界

**概念层面**

- 幂等 ≠ 去重。幂等保护**写入副作用**，去重判断**输入**是否重复。
- dedupe key ≠ idempotency key。前者在输入层判断"是不是同一事件"，后者在写入层判断"这次写入是不是同一副作用"。写入层幂等不能替代输入层去重。
- cursor ≠ watermark ≠ checkpoint（继续读的位置 / 承认处理到哪 / 状态落在哪）；rerun ≠ replay ≠ backfill ≠ restore（执行级 / 输入级 / 历史分区级 / 系统级回退）。
- manifest ≠ asset，materialization ≠ job 成功。job exit code 0 不代表下游可消费。
- CDC ≠ exactly-once。CDC = snapshot + change stream，crash 后重发是 documented behavior；有 replication slot 也不等于不重不漏。
- dry-run 通过 ≠ 可上线。dry-run 验证不了 DB constraint、transaction、upsert conflict。
- Bronze 幂等策略 ≠ Silver 幂等策略。Bronze 保证据（`DO NOTHING`），Silver 保当前事实（`DO UPDATE`）。

**范围边界（Week03 到底做到哪）**

Week03 交付的**不是完整采集平台，而是一组最低运行时承诺**。仓库明确"还没有"的四件事：通用 replay service、自动 checkpoint/state manager、一键 backfill engine、recovery policy engine。state 目前是 JSON 文件而不是 DB state table；`doc_ingest.py` 不写 checkpoint；本地不搭 Kafka / Debezium / Flink。

刻意留给后面的：**Week04** Iceberg Bronze/Silver、snapshot / time travel（需要 Week03 稳定的 asset 边界、partition 语义与 run evidence）；**Week06** 把 `replay_backfill.py` 的 plan 升级成 orchestrated recovery job，partition / asset check / backfill 的真实实现；**Week08** run evidence 支撑 citation 与 evidence serving；**Week11+** trace / state / release 进入评测与治理闭环。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. Ingest baseline 的五个条件是什么？如果只能保住一条，你保哪条？为什么？
2. Gap 事故为什么比显式失败更危险？"state 先于事实前进"的完整链条是什么？仓库里哪一段代码在防它？
3. 幂等和去重的区别用一句话怎么说？dedupe key 和 idempotency key 各举一个本项目里的具体例子。
4. `raw_ticket_event` 和 `ticket_fact` 为什么一个用 `ON CONFLICT DO NOTHING`、一个用 `DO UPDATE`？如果把 Bronze 也改成 upsert，会丢什么？
5. reconcile 的五个对账对象里，"Bronze 有、Silver 缺"说明发生了什么？该选 rerun 还是 replay？
6. `updated_at` 有八个坑，挑三个说清具体的失败场景。什么情况下你宁可用 `sequence_id`？
7. 为什么讲义拒绝承诺 exactly-once？"at-least-once + 幂等 + dedupe + 可回放"这四件事分别挡住了哪种失败？
8. PostgreSQL logical decoding 在 crash 后可能重发最近 changes——这是 bug 还是 documented behavior？它对客户端提出了什么强制要求？
9. manifest、asset、job、asset check 四个对象各回答什么问题？"把脚本名当资产名"具体会导致什么后果？
10. 为什么 backfill 的主语必须是 asset + partition？没有 partition 思维，backfill 会退化成什么？
11. `restore` 和 `replay` 的区别是什么？什么信号出现时你必须先 restore？
12. 恢复决策文档里"为什么不是另外几个动作"这一项为什么不能省？它防的是什么？

### 自测题参考答案

先自己答完上面的题，再往下对。

1. 五个条件：输入边界明确、执行可重复、状态可持久化、结果可解释、恢复有路径。若只能保一条，保「结果可解释」（run evidence / report）——没有它，其余四条坏了你也不知道，恢复只能猜。
2. Gap 不报错：读一半失败 → checkpoint 仍被更新 → 下次从新位置继续 → 缺口被固化。仓库里 `ticket_ingest.py` 只在 `errors==0 and invalid==0` 时写 checkpoint，dry-run 完全不写，就是防「state 先于事实前进」。
3. 幂等保护**写入副作用**，去重判断**输入**是否同一事件。本项目 dedupe / Bronze 幂等键是 `(source_id, source_fingerprint)`（payload SHA256，不是 `event_id`）；Silver 的对象键是 `ticket_id` upsert。写入层幂等不能替代输入层去重。
4. Bronze 要保留来源证据，重复到达 `DO NOTHING`；Silver 要当前事实，所以 `DO UPDATE`。Bronze 也改成 upsert，会覆盖历史事件，bad case 时分不清是源数据问题还是后来被改掉的。
5. 「Bronze 有、Silver 缺」是部分提交：执行层写崩或事务不完整。优先 **rerun** 同一 job（依赖幂等把缺口补上）；只有怀疑输入批次本身，才 replay。先定位再选动作。
6. 挑三个即可：被回写（cursor 乱跳）、数据变了但 `updated_at` 没变（漏数）、语义漂成 ETL 时间（窗口不再表示业务变化）。来源能保证单调序列时，宁可用 `sequence_id`，少吃迟到和回写。
7. CDC / slot 崩溃后会重发，exactly-once 在真实 crash 里站不住。at-least-once 防漏；幂等防重复写入副作用；dedupe 防同一输入当两件事；可回放让缺口能 bounded 恢复。
8. 是 documented behavior，不是 bug。客户端必须自己做 dedupe + 幂等写入，不能把 slot 位置当成「不重不漏」。
9. manifest 回答这次想接什么；asset 回答实际产生了什么持久化结果；job 只是触发 materialization；asset check 回答资产是否健康。把脚本名当资产名，下游会绑到一次执行而不是可消费对象，重跑/补数都会找错主语。
10. 主语必须是 asset + partition，这样 backfill 只补缺失或重算旧窗口。没有 partition 思维，backfill 会退化成「重跑全链路」。
11. replay 是同一批输入重放；restore 是回到已知可用快照。state / sink / 下游表已被污染时必须先 restore——再 replay 只会把脏状态扩得更大。
12. 逼你写清排除理由，防止「动作越大越安全」和层选错（执行级问题却做历史 backfill）。缺这一项，runbook 就变成命令菜单而不是锚点驱动的判断。

---

## 11. 一句话收口

Week03 是整门课的**运行时地基**：它把 Week02 的准入规则变成可执行、可重跑、可补数、可解释的采集基线。这周做得越扎实，Week04 的 lakehouse 版本控制、Week06 的编排恢复、Week08 的 citation 证据链就越不需要回头补——因为它们全部建立在"这批数据是什么、从哪来、怎么恢复"这三个问题有答案的前提上。
