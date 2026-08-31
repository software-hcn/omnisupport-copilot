# Week 10 · 受控 Agent

> **一句话**：把「答得稳的 RAG」升级成「办得对的 Copilot」——工具先契约化，路由先写死高确定性，高风险先 HITL，每个动作五元绑定可重放。风险从答错一句话，变成做错一件事。
>
> 讲义：`pdf/doc/Week10-受控 Agent.pdf`（48 页 / 5 课时）

---

## 0. 本周主干

五节课不是五个功能点，是同一条控制面从内到外加锁：

```
L01 Tool     工具契约 Schema / 幂等 / 权限 / 审计     「四证齐全才能上线」
      ↓
L02 Route    规则路由 + 5 级降级                       「该写死的别交给模型」
      ↓
L03 HITL     异步审批 + checkpoint + 审计               「决策权移交，不是弹窗」
      ↓
L04 Trace    五元绑定 + 同一条 trace_id                  「100% 可重放」
      ↓
L05 Loop     Week1-10 装成操作员                         「办得对，且能证明」
```

仓库里的运行时决策链（以 `ControlledAgent.invoke` 为准）：

```
选工具（规则 / workflow，不是 LLM 自由选）
  → 加载 Tool Contract → JSON Schema 校验 → allowed_roles
  → HITL 条件（命中则落 checkpoint，停止执行）
  → 幂等键（同 key 同参数回缓存；同 key 不同参数拒）
  → 执行 / FallbackChain
  → 写 action lineage（+ 生产路径再写 audit_log）
```

贯穿全周的铁律就一句：**function 的护栏在编译期，Tool 的护栏必须搬到运行时**——因为决定调不调的是概率模型，不是你写死的 if-else。

---

## 1. L01 · 工具契约：四证齐全才能上线

### 核心论点

Agent 调工具不是「AI 替你写代码」，是「AI 在生产系统里替你按按钮」。按钮底下没护栏，事故形态是重复退款、越权写入、审计时谁批的都说不清。讲义用过一个真实口径：写类工具不带幂等键，一律不准上线。

### 普通 function vs 受控 Tool

| 维度 | 普通 function | 受控 Tool |
|---|---|---|
| 谁决定调用 | 开发者写死 | LLM 运行时推理 |
| 输入约束 | 语言类型检查 | JSON Schema + 业务规则 |
| 错误处理 | 抛异常 / None | 结构化 `failure_codes` + 可路由 |
| 权限 | 靠调用方上下文 | 工具内嵌 `allowed_roles` |
| 幂等 | 可有可无 | 写类必须 |
| 审计 | 事后翻日志 | 实时结构化事件 |

### 四个工程承诺（出厂标配，不是高级特性）

| 承诺 | 守什么 | 仓库里落在哪 |
|---|---|---|
| **Schema** | in/out 形状、enum、required、`additionalProperties: false` | `input_schema` / `output_schema` |
| **幂等** | 同一次动作重试/重发/双发 = 一次 | `idempotent` + `idempotency_key_fields` |
| **权限** | 调用前校验 actor / role | `allowed_roles` |
| **审计** | 每次调用留下谁、什么参数、什么结果 | `audit_fields` + lineage / `audit_log` |

统一契约的 required 列表在 `contracts/tools/tool_contract_schema.json`：`name` / `version` / `description` / `input_schema` / `output_schema` / `allowed_roles` / `idempotent` / `audit_fields` / `failure_codes` / `hitl_conditions`。少一项，契约测试直接打回。

### 幂等三种实现，按动作类型选

| 策略 | 怎么做 | 适合 | 局限 |
|---|---|---|---|
| 自然幂等 | 同请求多次结果一致（UPSERT） | status 更新、配置修改 | 只对可重复操作有效 |
| `idempotency_key` | 客户端传 key，服务端去重 | 建工单、付款、发邮件 | 要维护去重表 |
| 乐观锁 + 版本号 | 带 version 做 CAS | 高并发更新 | 失败要重试 |

2024 年起的默认：**写类工具走 `idempotency_key`**。同 key + 同参数指纹 = 回缓存；同 key + 不同参数 = 冲突拒绝，不是「再执行一次」。

仓库实现没有讲义里的 Redis 装饰器，而是两层同一语义：课堂用 `InMemoryIdempotencyStore`，生产表是 `tool_idempotency`（见第 6 节）。

### 四类工具风险（上线前先归档）

| 风险 | 例子 | 关键风险 | 控制策略 |
|---|---|---|---|
| Read-only | `knowledge_search` / `query_support_kpis_v1` / `get_ticket_status` | 数据泄露 | tenant / role 过滤 |
| Write 内部 | `ticket_update` 的 note / status / assign | 状态错乱 | Schema + 幂等 + 审计 |
| Write 外部 | 发邮件、对外通知 | 不可逆、影响外部 | HITL |
| Financial | `refund_payment` / 大额 `grant_service_credit` | 直接资金损失 | HITL + 审计（讲义还要求双签） |

`ticket_update.json` 把这四档写成了输入枚举 `risk_level`：`read_only` / `internal_write` / `external_write` / `financial`。契约注释写得很清楚：**由规则层或工作流层给出，不交给 LLM 自由判断。**

财务类和外部不可逆类，不管模型当时多自信，一律强制 HITL。模型的自信不能当审批。

---

## 2. L02 · 路由 + 降级：选对一个，错了能降

### 第一性原理

工具一过 5 个，把清单全塞给 LLM 再写一句「请合理选用」，误选率开始飙——查询调成写入、失败陷入无限重试、多步编排漏一步还查不出来。问题不是模型不够聪明，是你把高确定性决策交给了概率模型。

**该写死的别交给模型。** 只把真正需要判断的窄决策留给 LLM。

### 三种调度策略（按确定性 × 风险选）

| 策略 | 做法 | 适合 | 工程负担 |
|---|---|---|---|
| LLM 自由选 | 全部工具暴露，模型自选 | 工具 < 5、场景多变、风险低（FAQ） | 最低 |
| 规则 + LLM | 关键词 / 意图先过滤，再让模型在子集里选 | 工具 5–20（默认起步） | 中 |
| 显式 Workflow | 代码定义节点，模型只在节点内窄决策 | 高价值、流程清晰、退款 | 最高 |

| 场景 | 确定性 | 风险 | 建议 |
|---|---|---|---|
| 客服 FAQ | 低 | 低（答错） | 自由选 |
| 多产品线路由 | 中 | 中（误导） | 规则 + LLM |
| 工单状态更新 | 高 | 中（数据错乱） | 规则 + LLM（带 confirm） |
| 退款 / 资金 | 高 | 高（资金损失） | **显式 Workflow + HITL** |
| 多步骤报表 | 中 | 低 | 显式 Workflow |

口诀：风险低可以放手，风险一高就把方向盘抢回代码。本仓库的 `ControlledAgent` 本身就是 Workflow 侧：调用方点名工具，Agent 只做控制面，不负责「猜该调哪个」。

### 降级链：失败也要显式声明路径

讲义给的 5 级是生产 SLO 地基，每一级应对一个工程对象，不是「LLM 临场决定降到哪」：

| 级 | 名称 | 做什么 |
|---|---|---|
| 1 | Primary | 主工具，独立超时 |
| 2 | Retry | 同链路有限次，指数退避 |
| 3 | Fallback / Cache | 备用或标记 stale 的缓存 |
| 4 | HITL | 转人工（异步，不阻塞） |
| 5 | Graceful | 返回可展示的降级文案，禁止模型临场编道歉 |

仓库里的 `FallbackChain` 更瘦：一组命名 step 顺序试，全失败再走可选的 `graceful_response`；**HITL 不在这条链上**，它是执行前的硬门（见 L03）。课堂 demo 验证的是 `primary_vector_search` 超时 → `lexical_cache`，并要求结果仍带 `evidence_anchor`。

### RAG 也是一种工具

很多团队 RAG 一套、Tool 一套，这是 Week08/10 之间最常见的工程债。把 Week08 包成 `knowledge_search` 之后：同一套 schema、同一套 fallback、同一套 audit。Agent 眼里只剩一种调用，治理才能统一。

`knowledge_search` 输出强制 `evidence_anchor`（`source_id` / `source_url` / `page_no` / `section_path`），并带 `trace_id` / `release_id`。低分检索走 fallback，而不是让模型补一句「据我所知」。

---

## 3. L03 · HITL：决策权移交，不是加个按钮

### 核心论点

真正的 HITL 是工程化的决策权移交：可观测、可追责、可回放，而且 **Agent 绝不能在等审批时挂死**。只做确认弹窗，会缺 SLA、降级、审计、异步——上线后两个死法：Agent 挂死，或被悄悄绕过。

| 维度 | UI HITL（demo 够用） | 工程化 HITL |
|---|---|---|
| 形态 | 弹窗 / 按钮 | 审批工作流 + audit event |
| 同步性 | 阻塞等 | 异步，释放会话资源 |
| SLA | 没有 | timeout + 降级 |
| 审计 | 没有或事后补 | 发起 / 通知 / 决策三段 |
| 回放 | 不可能 | who / when / why |
| Agent 状态 | 干等 | checkpoint，可 resume |

机制名字叫 **Checkpoint + Resume**：冻结现场、释放资源、等回调、恢复继续。

### 什么时候必须拦（规则强制，禁止 LLM 自觉）

| 类别 | 典型动作 | 审批层级 |
|---|---|---|
| 强制 · 财务 | 退款 / 转账 / 优惠券 | 财务 |
| 强制 · 不可逆 | 删数据 / 对外邮件 | 业务负责人 |
| 强制 · 合规 | 导出 PII / 跨域 / 法务 | 合规 |
| 条件 · 金额 | 超自动审批额度 | 主管 |
| 条件 · 异常模式 | 短时多次重试，疑似滥用 | 安全 |

`ticket_update.json` 落地的条件语言（由 `HITLPolicy` 解析，支持 `AND` 与比较符）：

| 条件 | 动作 |
|---|---|
| `operation == 'refund_payment'` | `require_approval` |
| `operation == 'grant_service_credit' AND amount_cents >= 50000` | `require_approval`（500 美元档） |
| `risk_level == 'external_write'` | `pause_and_notify` |
| `risk_level == 'financial'` | `require_approval` |

多条同时命中时，优先级是 `reject` > `require_approval` > `pause_and_notify`（`HITLPolicy.ACTION_PRIORITY`）。

### 四种介入时点

| 模式 | 时点 | 典型场景 | 本仓库 |
|---|---|---|---|
| Pre-Confirm | 执行前 | 高额退款、删数据 | **已做**：`require_approval` → `awaiting_approval` |
| Approval | 执行后、生效前 | 邮件草稿审 | 未做 |
| Review | 执行后采样 | 内部导出 10% 抽审 | 未做 |
| Escalation | 模型不确定 | confidence < 0.7 | 仅弱类比：`knowledge_search` 的 `min_score < 0.4` → `pause_and_notify`（判的是**输入阈值**，不是检索结果） |

不可逆动作必须卡在执行前。可逆但要质量的，用 Review 采样，别让审批拖死主路径。

### 五条原则 / 五个反模式（压缩记）

原则：一屏能决策；拒绝必填理由（这是免费训练数据）；单层决策不要逐级签；超时必有降级；audit 只追加不改。

反模式：同步等审批；没有超时；审批材料太长；不写三段 audit；**让 LLM 判断要不要 HITL**。最后一条最坑——漏审一次就是不可逆资金损失。规则的事交给规则。

课堂路径：`ControlledAgent.invoke` 命中 HITL → `HITLCheckpointStore.create` → 返回 `awaiting_approval` → `decide` → `resume_approved`。生产路径把 checkpoint 写进 Postgres `hitl_approval_request`，审批 API 是 `POST /api/v1/approvals/{approval_id}/decision`。

---

## 4. L04 · 行为血缘：一个动作绑齐才能追责

### 三层 Trace，一根 `trace_id`

| 层 | 答什么 | 工具 | 粒度 |
|---|---|---|---|
| Data Lineage | 这表/文件怎么来的 | OpenLineage（Week06） | 表 / 字段 |
| Call Trace | 这次请求花在哪 | OpenTelemetry（Week12） | 服务 / span |
| Action Lineage | **AI 为什么这么做** | OL + OTel + audit | 动作 + 依据 |

Action Lineage 不是新系统，是用同一个 `trace_id` 把已有三层缝起来。少那根线，就只剩三堆对不上的日志。

### 五元绑定（少一维，复盘就多一个「说不清」）

| 维度 | 绑什么 | 来自哪周 | 仓库字段 |
|---|---|---|---|
| Data Snapshot | 当时数据世界 | Week04 Iceberg | `bindings.data_snapshot_id`（或 `data_release_id`） |
| Evidence | 引用了哪条证据 | Week07/08 `evidence_anchor` | `bindings.evidence_ids` |
| Prompt | 行为约束版本 | Week08 Prompt as Code | `bindings.prompt_release_id` |
| Model | 推理大脑 | Week08 release | `bindings.model_version` |
| Skill / Tool | 工艺 + 工具版本 | Week09 / 本周契约 | `bindings.skill_release_id` + 事件上的 `tool_name`/`tool_version` |

讲义把 Tool 和 Skill 合成第五元；仓库把 Skill 放进 `bindings`，Tool 版本放在 lineage 事件顶层。语义一样：出事时能 100% 重放现场。绑不齐，这个动作就不算可追责，也不该上生产。

### 重放的价值

| 场景 | 需要什么 | 没血缘的代价 |
|---|---|---|
| 客户投诉复盘 | 重放当时依据 | 人工翻日志几小时到几天 |
| Bug 回归 | 历史 case 对比 | 全靠猜 |
| 合规审计 | 为什么这条决策合规 | 审查直接失败 |
| 模型 A/B | 严格对比两个模型版本 | 做不成严格实验 |

`ActionLineageEvent.to_openlineage_event()` 把动作映射成 job/inputs/outputs/facets 视图，复用 Week06 的图，不另造一套 Agent 血缘库。课堂模块不真的向 Marquez 发事件。

---

## 5. L05 · 端到端闭环：组装成操作员

### Demo ≠ 上线

| 少了哪一周 | 会缺什么 | 后果 |
|---|---|---|
| Week02 契约 | 输入不可信 | 答案地基是流沙 |
| Week06/07 资产化 | 数据不稳、答不了复杂问题 | 一问深就露馅 |
| Week08 RAG 服务化 | 答案没有证据 | 合规第一关过不了 |
| Week09 Skill | 没有可治理的工艺 | 想优化无从下手 |
| Week10 契约 + HITL + 血缘 | 动作没有边界 | 一动手就是事故 |

Agent 不是聊天黑盒，是 Router → Tools（RAG / KPI / Update）→ HITL → Trace 的有序组合。你能指着任意一段说清「它在干嘛、出事怎么办」，这才叫受控。

### 三类必跑路径（出事的永远不是 happy path）

| 路径 | 场景 | 验证什么 | 仓库入口 |
|---|---|---|---|
| Happy | 低风险内部写 | 自动执行 + 二次命中幂等缓存 | `demos/e2e_happy_path.py` |
| Fallback | 主检索超时 | 降到 cache，仍带 evidence | `demos/e2e_fallback_path.py` |
| HITL | 退款 | 先 `awaiting_approval`，审批后才执行 | `demos/e2e_hitl_path.py` |

讲义还要求 Composite（多工具同一 `trace_id`）和 Replay（重放上周投诉）。仓库课堂包只自动化了前三条。

### 五个 SLO（上线 ≠ 跑通）

| 指标 | 含义 | 目标 | 违反的代价 |
|---|---|---|---|
| Resolution Rate | 一次解决率 | > 65% | 工单成本 / NPS |
| Evidence Coverage | 答案带证据率 | **= 100%** | 合规 / 信任 |
| Tool Success Rate | 工具调用成功率 | > 98% | 体验断崖 |
| HITL SLA | 审批时限内响应 | > 95% | 事务挂死 |
| Hallucination Rate | 幻觉率（抽样） | < 2% | 风险 + 合规 |

Evidence Coverage 没有「大概」：差一条没证据的答案，可能就是一次合规事故。这些指标的量化门禁交给 Week11。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| 统一工具契约 Schema | `contracts/tools/tool_contract_schema.json` | required 十项、`hitl_conditions.action` 三枚举、`additionalProperties: false` |
| 写动作契约 | `contracts/tools/tools/ticket_update.json` | `idempotency_key` required、`risk_level`、财务 `allOf` 强制 `amount_cents`+`evidence_ids` |
| RAG-as-tool | `contracts/tools/tools/knowledge_search.json` | 输出 `evidence_anchor` required、`idempotency_key_fields` |
| Week05 KPI 工具 | `contracts/tools/tools/query_support_kpis_v1.json` | 只读、registry 批准的指标，不接受裸 SQL |
| 只读工单 / 建单 | `contracts/tools/tools/get_ticket_status.json`<br>`contracts/tools/tools/create_ticket.json` | 读 vs 写的幂等与 HITL 差异 |
| 契约只读发现 | `tools/registry.py` | OpenAI `strict: true`、MCP `destructiveHint` |
| API 侧发现 | `services/tool_api/app/tool_contract_registry.py`<br>`services/tool_api/app/routers/tool_contracts.py` | `GET /api/v1/tool-contracts*`，不执行动作 |
| 幂等 | `tools/idempotency.py` | `stable_digest`；同 key 不同参数抛 `IdempotencyConflict` |
| 降级链 | `tools/fallback.py` | 逐步尝试 + `fallback_attempts` 审计；可 `graceful_response` |
| HITL 规则 + checkpoint | `agent/hitl.py` | 条件语言、`ACTION_PRIORITY`、内存 store |
| HITL 审批契约 | `contracts/agent/hitl_approval.schema.json` | `pending/approved/rejected/expired` |
| 控制面编排 | `agent/copilot.py` | **不是 LLM wrapper**；校验 → 权限 → HITL → 幂等 → 执行 → lineage |
| 动作血缘 | `agent/lineage.py`<br>`contracts/agent/action_lineage_event.schema.json` | 五元 `bindings`；`to_openlineage_event()` |
| 生产工单 + HITL + 审计 | `services/tool_api/app/routers/tickets.py`<br>`services/tool_api/app/main.py` | `POST /api/v1/tools/ticket_update`、`POST /api/v1/approvals/{id}/decision` |
| 三张运行时表 | `infra/migrations/008_week10_controlled_agent.sql` | `tool_idempotency` / `hitl_approval_request` / `agent_action_lineage` |
| 契约测试 | `tests/contract/test_week10_controlled_agent_contracts.py` | 全量契约过 schema；退款必须 `require_approval` |
| 集成测试 | `tests/integration/test_week10_controlled_agent.py` | 低风险执行、幂等缓存、HITL 先拦、fallback、越权仍写 lineage |
| 课堂三条路径 | `demos/e2e_happy_path.py`<br>`demos/e2e_fallback_path.py`<br>`demos/e2e_hitl_path.py` | 与 L05 三类必跑一一对应 |
| 蓝图 / Runbook | `docs/blueprints/week10/week10-controlled-agent-blueprint.md`<br>`runbooks/week10-controlled-agent.md` | 范围边界和 Docker 命令 |

### 代码里值得单独看、讲义没展开的细节

**1. 课堂 Agent 与生产 API 的检查顺序不一致。**

`ControlledAgent.invoke`：Schema → 角色 → **HITL** → 幂等 → 执行。HITL 命中就停，幂等还没走，同一笔退款连点两次会建**两张**审批单。

`tickets.py`：Schema → 角色 → **先查 `tool_idempotency`** → HITL → 执行。第一次 `awaiting_approval` 就会 `remember`，重放同 key 直接回缓存。蓝图写的也是「先幂等后 HITL」。学控制面用 `copilot.py`，学生产语义用 `tickets.py`。

**2. 幂等键不是客户端字符串原样当主键。**

`derive_idempotency_key()` 用契约声明的字段（`ticket_update` 只有 `idempotency_key`）再加 tool name 做 digest。`knowledge_search` 则用 `query` + `product_line` + `top_k` 合成，查询类不必让调用方手写 key。

**3. 越权也要留血缘。**

`test_permission_denial_emits_lineage_without_execution`：`end_user` 调 `ticket_update` 返回 `denied` / `PERMISSION_DENIED`，但仍写一条 `status=denied` 的 lineage。拒了不等于没发生过。

**4. 有两份 Registry。**

`tools/registry.py` 给课堂 Agent / 测试；`services/tool_api/app/tool_contract_registry.py` 给 HTTP 发现。职责相同（只读、导出 OpenAI/MCP），不要改一份忘另一份。

**5. HITL 条件语言只看 payload 字段。**

`knowledge_search` 的 `min_score < 0.4` 判的是**请求里的阈值**，不是检索分数。把 `min_score` 设成 0.3 就会 `pause_and_notify`，即使还没搜。不要把它理解成「结果太差自动升级人工」。

---

## 7. 讲义与仓库对不上的地方

| 讲义写的 | 实际情况 |
|---|---|
| `tools/*_contract.json` | 不存在。统一在 `contracts/tools/tools/*.json`，元 schema 是 `contracts/tools/tool_contract_schema.json` |
| `idempotency: "required"` / `"natural"` | 仓库是布尔 `idempotent` + 可选 `idempotency_key_fields` |
| Redis + `@idempotent_tool` 装饰器、TTL 24h | 课堂是内存 store；生产是 Postgres `tool_idempotency`，冲突语义一致，没有 Redis TTL |
| 5 级链把 HITL 放在 cache 之后 | `FallbackChain` 只有 named steps + 可选 graceful；HITL 是执行前硬门，不在降级链里 |
| `ticket_query`、`/api/hitl/{rid}/decide` | 读工具是 `get_ticket_status`；审批是 `POST /api/v1/approvals/{approval_id}/decision` |
| `ticket_id` 为 uuid、status 四枚举 | 工单 ID 是 `TKT-YYYYMMDD-XXXXXX`；`ticket_update` 的 status 含 `open`/`escalated` |
| `knowledge_search` 必填 `tenant`，`idempotency: natural` | 必填是 `query` + `trace_id`；幂等字段是 query/product_line/top_k |
| `agent/lineage.py` 调 OpenLineage Client 真发事件 | 只有 `to_openlineage_event()` 字典视图，课堂不连 Marquez |
| 架构图 `docs/assets/week10/week10-controlled-agent-code-architecture.png` | 蓝图/Runbook 引用了，仓库里没有这个文件 |
| Composite / Replay 两条 demo | 只有 happy / fallback / HITL 三条脚本 |
| 仅一份 `knowledge_search` | 另外还有 `search_knowledge.json`（产品检索契约），契约测试以 `knowledge_search` 为准 |

另有一处仓库内部也不齐：`get_ticket_status.json` 的 ID 正则是 `TKT-[0-9]{8}-[0-9]{6}`，而 `ticket_update` 与 API 允许 `[0-9A-Z]{6}`。对照契约时以写工具和集成测试里的 ID 为准。

---

## 8. 动手清单

所有命令走 Docker devbox。

```bash
# 1. 契约：所有工具过统一 schema；ticket_update 必须有幂等键 / HITL / 审计字段
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/contract/test_week10_controlled_agent_contracts.py -v

# 2. 控制面：低风险执行、幂等缓存、金融 HITL、fallback、越权血缘
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/integration/test_week10_controlled_agent.py -v

# 3. 三条课堂路径（无需外部 LLM）
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python demos/e2e_happy_path.py

docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python demos/e2e_fallback_path.py

docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python demos/e2e_hitl_path.py
```

契约只读发现（不改工单、不调外部系统）：

```bash
docker compose --env-file infra/env/.env.local \
  -f infra/docker-compose.yml up -d --build postgres tool_api

curl http://localhost:8001/api/v1/tool-contracts
curl http://localhost:8001/api/v1/tool-contracts/ticket_update
curl http://localhost:8001/api/v1/tool-contracts/exports/openai
curl http://localhost:8001/api/v1/tool-contracts/exports/mcp
```

**验收标准不是「跑过了」，而是能回答：**

1. `ticket_update` 凭什么不能被 LLM 自由调用？契约里哪四组字段在拦？
2. 同一 `idempotency_key` 第二次为什么是 `cached` 而不是再写一次？参数改了会怎样？
3. `refund_payment` 第一次返回什么 status？审批前 `executor` 有没有被调用？
4. RAG 主路失败时，降到了哪一级？结果里还有没有 `evidence_anchor`？
5. 越权调用有没有留下 lineage？少了这一条，审计怎么证明「系统拒绝过」？

**加分练习**

- 删掉 `ticket_update` 某条 `require_approval` 条件，确认契约测试失败，再判断这是漏审还是「测试过严」。
- 用同一 `idempotency_key` 换 `reason` 再调，确认拿到 `IDEMPOTENCY_CONFLICT`，而不是第二次成功。
- 对比 `copilot.py` 与 `tickets.py`：连点两笔未审批退款，课堂路径会不会造出两张 approval。

---

## 9. 易错点与边界

**概念层面**

- 受控 Tool ≠ 普通 function。护栏必须在运行时，编译期拦不住模型临场误判。
- 路由 ≠ 「把工具列表交给 LLM」。高确定性、高风险走规则或 Workflow。
- Fallback 链 ≠ HITL。前者是主路失败后的降级；后者是执行前的审批门。仓库把它们做成了两个模块。
- HITL ≠ 确认弹窗。缺异步 / checkpoint / SLA / 三段 audit，就只是 UI。
- 数据血缘 ≠ 动作血缘。前者追表怎么来，后者追 AI 为什么按那个按钮。
- schema 能过 ≠ 可以执行。还要过角色、幂等、HITL，通过了才写 lineage。
- `pause_and_notify` ≠ `require_approval`。前者暂停并通知，后者必须有人批才能 resume；冲突时取更严的。

**范围边界（Week10 到底做到哪）**

蓝图写得很硬：Week10 教的是**控制面**。学生核心包是真实 JSON 契约、确定性 Python（HITL / 幂等 / fallback / lineage）、只读契约发现、无外部 LLM 的 E2E。

刻意不做（留给后续 / capstone）：完整生产工单变更服务、真实支付/退款通道、长流程工作流引擎、LLM 自主规划。

注意：`services/tool_api/app/routers/tickets.py` 已经按 Week15 产品面写了真实 `ticket_fact` 变更和 `financial_adjustment` 记账——那是后面周次的落地，不要当成「Week10 课堂作业要接支付网关」。课堂主线仍是 `ControlledAgent` + 三个 demo。

Week11 起才把「办得对」变成可量化门禁（评测 / Golden Set / 回归）。没有评测的 Copilot，上线三天你会知道它行，三个月后你不知道它已经歪了。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 为什么「function 能过单测」挡不住 Agent 把查询调成删除？四证里哪一证是专门挡这件事的？
2. 同一次退款被前端重发三次，没有幂等键会发生什么？有 key 但参数被改了一个零，系统应该缓存还是拒绝？为什么？
3. 工具数到 12 个还让 LLM 自由选，最典型的事故形态是什么？工单更新和退款分别该用三种策略里的哪一种？
4. 讲义 5 级降级里 HITL 排第 4，仓库为什么没把它放进 `FallbackChain`？这两类失败的处理时机有什么不同？
5. 为什么不能让模型自己判断「这单要不要送审」？漏审和误送审，哪个更不可接受？`HITLPolicy` 多条件命中时选哪条动作？
6. UI 确认弹窗缺了哪四样会在生产翻车？Checkpoint + Resume 分别解决什么？
7. 数据血缘、调用链、动作血缘各回答什么问题？只用 OpenTelemetry span、不绑 `data_snapshot_id`，客户投诉退款额算错时你还能否 100% 重放？
8. 五元绑定少了 `prompt_release_id` 和少了 `evidence_ids`，复盘时分别会卡在哪一步？
9. Happy / Fallback / HITL 三条路径各自证明控制面的哪一层？只跑 Happy 上线，最可能在哪种事故上裸奔？
10. `ControlledAgent` 对未审批退款不走幂等、`tickets.py` 会缓存 `awaiting_approval`，这两种选择各自防什么、各自引入什么重复提交风险？
11. 为什么 RAG 必须包成工具，而不是 Agent 里另写一套检索调用？输出少了 `evidence_anchor` 会破坏 Week08 的哪条承诺？
12. Week10 交付的是「能办事的 Copilot」还是「控制面」？如果有人要在本周接真实退款 API，你用蓝图的哪句话拦住？

---

## 11. 一句话收口

Week10 不是给 RAG 加几只手，而是给动作加控制面：契约定边界，路由锁确定性，HITL 移交决策权，血缘保证可重放。前 9 周解决「答得稳」，这一周第一次让系统「办得对」——而且办错了能追到人、追到版本、追到当时那份数据。
