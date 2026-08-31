# Week 12 · 全链路可观测性

> **一句话**：出事了能不能在客户骂完之前找到卡在哪——用一条 `trace_id` 贯穿 RAG / Tool / HITL，把排障从"翻日志猜"变成"看时间轴定位"，再把事故沉淀进 Week11 反例库。
>
> 讲义：`pdf/doc/week12-全链路可观测性·故障定位的显微镜.pdf`（45 页 / 5 课时）

---

## 0. 本周主干

五节课是一台显微镜的装配顺序，不是五个独立话题：

```
L01 OTel     协议地基：Trace / Span / Context + OpenInference     「能串起来」
      ↓
L02 Spans    6 段 RAG + Tool/HITL，读起来像故事                   「能看清」
      ↓
L03 Dash     5 个必看面板 + DoW 对比 + 钻取到 trace                「能判断」
      ↓
L04 Alert    SLO + 错误预算 + burn rate + 4 级路由                「该叫才叫」
      ↓
L05 Replay   Detect → Triage → Locate → Fix → Verify             「一次事故变复利」
      ↓
             Week13 GraphRAG 接在"看得见"之后
```

贯穿全周的三句口令：

| 口令 | 用来挡什么误解 |
|---|---|
| **log 是点，trace 是因果链** | Agent 一个请求 8-15 hop，日志对不上号 |
| **好 span 读起来像故事** | 接了 OTel 但 span 全叫 `process`，等于没接 |
| **告警看错误预算烧多快，不看一次抖动** | `P99 > 2s` 这种阈值在 LLM 系统里几乎必误报 |

仓库把本周收成**两条验收路径**，缺一条都不算过：

| 路径 | 证明什么 | 入口 |
|---|---|---|
| **Live** | OTLP 真发出去、W3C context 跨服务、Phoenix 能看到整棵树 | `demo_flow.py` → Collector → Phoenix |
| **Closure** | 告警 → incident → postmortem → Week11 反例 → eval gate，且**不改**黄金集 | `run_closure.py` + fixture |

单元测试过了不证明 Phoenix 接线；截一张 Phoenix 图也不证明回归闭环。

---

## 1. L01 · OTel：把请求串成一棵树

### 核心论点

传统 Web 一个请求穿 2-3 个服务，日志够用。Agent 一条请求要过 Router → RAG（召回/重排/生成）→ Tool + fallback → HITL + Audit，**8-15 个 hop**。每个 hop 都有耗时、错误、依赖；日志散在不同服务，时间戳还对不齐。排障必须升级到分布式追踪：一个 `trace_id` 贯穿全链，每一段一个 span。

**Agent 时代，trace 比 log 重要一个数量级**——因为你要回答的不是"有没有报错"，而是"这一次慢在 rerank 还是卡在 `hitl.wait`"。

### 三支柱：各管一摊

| 支柱 | 形态 | 能回答 | 短板 | 典型工具 |
|---|---|---|---|---|
| Logs | 事件级文本 | 单点发生了什么 | 跨服务对不上 | ELK / Loki |
| Metrics | 数值时序 | 趋势、容量、烧不烧 | 知道发烧，不知哪个器官 | Prometheus |
| Traces | 请求级因果链 | 这次穿了哪些 hop、慢/错在哪 | 单条不够看面 | OTel + Phoenix / Jaeger |

Metrics 告诉你系统发烧了；**烧在哪个器官，只有 Traces 能指出来**。三样用同一个 `trace_id` 串起来才完整。

### 三个 API 就上车

| 概念 | 是什么 | 代码里对应 |
|---|---|---|
| **Trace** | 一次完整请求 = 一棵 span 树 | 一个 `trace_id` |
| **Span** | 树上的一步（retrieve / rerank / llm / tool） | `start_as_current_span` / `traced_span` |
| **Context** | 跨服务传递的信封 | W3C `traceparent`（`inject` / FastAPI instrumentor） |

父子关系靠"当前 span"自动嵌：`rag.query` 是根，retrieve / rerank / llm 是子。`set_attribute` 写结构化字段，时间轴自动有起止。

### OpenInference：给 LLM 字段定标准

OTel 的 span 字段是业务无关的。prompt / tokens / tool / retrieval 各家自己造名，换平台就废。Arize 的 OpenInference 把 LLM 语义钉成可互换的属性：

| 类别 | 标准属性 | 用来干什么 |
|---|---|---|
| LLM Call | `llm.model_name` / `invocation_parameters` | 跨工具认出模型 |
| Tokens | `llm.token_count.prompt` / `completion` | 统一算成本 |
| Messages | `llm.input_messages` / `output_messages` | 看 prompt（仓库默认**不存原文**） |
| Tools | `tool.name` / schema | 识别工具调用 |
| Retrieval | `retrieval.documents` / score | RAG span |
| Embeddings | `embedding.model` / text | embedding 调用 |

OTel 官方 `gen_ai.*` 仍在 experimental → stable，和 OpenInference 在收敛。当下跟 OpenInference，埋点抽象一层，以后切官方约定不伤历史数据。

讲义演示的是 `OpenAIInstrumentor().instrument()` 一行自动打 LLM span。仓库**没有走这条路**：业务 span 手写 `traced_span`，HTTP 层用 FastAPI instrumentor，导出走 **OTLP HTTP `:4318`**，经 Collector 进 Phoenix。协议精神一样，接入形状不一样（见第 7 节）。

---

## 2. L02 · Spans：故障定位最小集

### 三条设计原则

| 原则 | 标准 | 反例 | 类比 |
|---|---|---|---|
| **Naming** | `layer.action.strategy`，如 `rag.retrieve.hybrid` | `process` / `call` / `run` | 好函数名 |
| **Attributes** | 关键参数、结果、决策；`_count` / `_ms` 后缀 | 整段 prompt、整表 candidates | 好日志字段 |
| **Status** | OK / ERROR **加上业务级 `error.type`** | 只有"错了" | HTTP status |

`error.type` 是最被低估的字段：`insufficient_evidence` / `tool_timeout` / `low_confidence` 能省半小时翻日志。

### RAG 6 段：少一段就有盲区

讲义给的是"故障定位最小集"。仓库命名按 blueprint 微调，语义对齐：

| 讲义名 | 仓库名 | 定位什么 | 关键属性（仓库） |
|---|---|---|---|
| `rag.query` | `rag.query` | 这次用户操作失败了吗 | `omni.query.sha256` / `length` / `release_id` / tenant |
| `rag.intent_route` | `rag.intent.route` | 为什么走 RAG / graph / hybrid | `omni.route` / confidence / reasons |
| `rag.retrieve.hybrid` | `rag.retrieve.hybrid` + `vector` / `lexical` / `rrf` | 哪一路丢了候选 | `omni.retrieval.vector_hits` / `lexical_hits` / `fused_count` |
| `rag.rerank.cross` | `rag.rerank.cross` | 精排留了多少、丢了多少 | `omni.rerank.input_count` / `output_count` / `dropped_count` |
| `rag.generate.llm` | `llm.generate` | 哪个模型、多少 token、有没有证据 | `llm.model_name` / `token_count.*` / `omni.evidence_count` |
| `rag.audit.write` | `rag.audit.persist` | 运行证据写进去了吗 | `omni.audit.store` |

时间轴的用法：2.4s 里 1850ms 在 `llm.generate`，就去动生成（换模型 / 减 max_tokens / 流式），别先调召回。**看时间轴，不要猜。**

### Tool / HITL：受控 Agent 的行车记录仪

| 仓库 span | 回答什么 |
|---|---|
| `agent.invoke` | 哪一次受控动作失败 |
| `tool.contract.validate` / `agent.permission.evaluate` | 契约和权限在执行前过了没 |
| `tool.execute.{name}` | 哪个工具失败、耗时多少 |
| `tool.fallback.attempt` / `tool.fallback.graceful` | 降级走到第几级 |
| `tool.idempotency.check` | 幂等缓存命中了没 |
| `hitl.evaluate` / `hitl.wait` / `hitl.resume` | 要不要批、等了多久、谁批的 |
| `agent.lineage.persist` | 动作血缘落盘了没 |

`hitl.wait` 的耗时直接对应 Week10 那个"审批卡 40 分钟"的事故；`tool.fallback.*` 对应工具契约的降级链。

### 属性预算：trace 不是第二份数据库

讲义经验值：每个 span **少于 20 个属性**，大体量内容走 artifact。仓库用 SDK 硬限制落实：`SpanLimits(max_attributes=20, max_attribute_length=512)`。

标准写法是 **digest + length**，preview 是显式开关：

| 做法 | 对 | 错 |
|---|---|---|
| 查询 | `omni.query.sha256` + `omni.query.length` | `user.query = 全文` |
| 可选预览 | `safe_preview(..., limit=200)`，且先 redact | 未脱敏的 `input.value` |
| 候选 | hits / fused_count / top chunk id | `json.dumps(candidates)` |
| 完整原文 | 对象存储 / audit 表，span 只留链接或计数 | 把 prompt/answer/chunk 塞进属性 |

默认 `OTEL_CAPTURE_CONTENT=false`。span 是给系统看的，不是第二份用户内容副本。把手机号、身份证塞进第三方 trace SaaS，是合规事件，不是"可观测做得全"。

### 五个反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 名字通用 | 时间轴读不成故事 | `layer.action.strategy` |
| 存原文 | 上传慢、存储爆 | preview + len + digest |
| 有 PII | 数据出境 / 监管事件 | redact 后再 set |
| 少业务状态 | 只知道错了 | `error.type` / `omni.business_status` |
| 不分层 | 看不出依赖 | 父子嵌套，按层组织 |

---

## 3. L03 · Dash：5 张图判断升不升级

### 核心矛盾

**看得多和看得清是反的。** 20 个面板挤一屏，oncall 凌晨 3 点看不见问题。先问"谁在什么场景下做决策"，再画图。

| 角色 | 看什么 | 决策 |
|---|---|---|
| Oncall | 5 张红绿灯 + DoW | 要不要升级 |
| 工程师 | 具体 trace / span、P50/P99 拆解 | 怎么修 |
| PM / 业务 | 一次解决率、CSAT、成本、相对上一版 | 要不要砸资源 |

三拨人塞进同一张 dashboard，结果三拨人都嫌难用。

### 五个必看面板

前四张是 SRE 黄金信号的变体，第五张 Quality 是 LLM 专属——传统系统不用测"答得对不对"。

| 面板 | 仓库 metrics | 诊断 |
|---|---|---|
| **overview** | qps / error_rate / latency_p50_ms / latency_p99_ms | 要不要升级 |
| **quality** | citation_coverage / abstain_rate / low_confidence_rate / bad_case_rate | 要不要回滚 |
| **performance** | retrieve / rerank / generate / hitl_wait 的 p99 | 哪一段慢 |
| **cost** | prompt_tokens / completion_tokens / cost_per_query_usd | 要不要降级模型 |
| **errors** | errors_by_type / tool_failures_by_name / pii_leak_count | 哪类故障在升 |

讲义 Quality 还写了在线 Faithfulness（1% 抽样跑 LLM-judge）。仓库面板用 **citation_coverage / abstain** 代替——可从 span 属性直接算，不必在线全量 RAGAS。P50 看中位体验，P99 看最差用户；只看 P99 会漏掉"大多数人已经变慢"。

五张放同一屏：成本涨同时 P99 也涨，常是 `top_k` 被人调大。分开切会错过关联。

### 对比方式：绝对值会骗人

| 方式 | 怎么比 | 发现什么 |
|---|---|---|
| DoW 同比 | 今天 vs 上周同一天同时段 | 周节律突变 |
| HoH 环比 | 当前小时 vs 上一小时 | 突发故障 |
| 基线 | 7 / 30 日均线 | 慢慢退化 |
| Release | 当前 vs 上一 `release_id` | 上线后退化 |
| 百分位带 | P10–P90 历史带 | 真异常 vs 正常波动 |

"现在 P99=2.1s"几乎没信息量；**"比上周同时段差 30%"才是问题**。电商周一上午本来就比周日高，固定阈值全是误报。

### 钻取链不能断

```
overview 红绿灯 → span / error 拆解 → 一条 sample trace 时间轴 → span 属性 → 回滚或热修
```

面板必须能跳到 Phoenix 里的 `trace_id`。看到异常却点不进去、另开工具重搜，30 秒定位会变成 30 分钟。仓库把这条链写进 `week12_panels.yaml` 的 `drilldown` 字段。

---

## 4. L04 · Alert：该叫人时叫人

### 告警的科学基础不是阈值

`P99 > 2s 就告警` 在 LLM 系统里几乎一定误报：高峰、模型抖动、偶发 429 都会炸。Google SRE 的三个概念要串起来：

| 概念 | 含义 | 例子 |
|---|---|---|
| **SLI** | 实际测到的指标 | 成功响应率、P99、citation_coverage |
| **SLO** | 业务可接受的目标 | 可用性 99.5%，P99 < 3s |
| **错误预算** | `1 − SLO` | 每月 0.5% 可以失败 ≈ 3.6h |
| **Burn rate** | 预算被消耗的速度 | 正常速度不叫；超标才叫 |

同样 P99=4s：高峰偶发一下，预算内；持续半小时狂烧，才是真应急。**告警本质是"错误预算正在以异常速度被烧掉"**，不是"指标超了某个数"。

SLO 不是越高越好。99.9% → 99.99% 成本可能差一个数量级，客服 Copilot 的用户感知不到那 0.09%。从业务"能接受多差"反推，不要从"我想多好"出发。

### 五类 SLO：讲义数字 vs 仓库可执行政策

| 类别 | 讲义 SLI / 目标 | 仓库 `week12_slo.yaml` | 优先级 |
|---|---|---|---|
| 可用性 | 成功响应率 99.5% | `availability: 0.995` | P1 |
| 延迟 | P99 < 3s | `latency_p99_ms: 3000` | P2 |
| 质量 | 在线 Faithfulness > 0.85 | **`citation_coverage: 0.95`**（可从 span 确定计算） | P2 |
| 合规 | PII 泄露 = 0，零容忍 | `pii_leak_count: 0` | P0 |
| 成本 | 日均 cost/query < $0.05 | `cost_per_query_usd: 0.02`（课堂阈值更紧） | P3 |

**PII 和其他 SLO 本质不同**：可用性可以花 0.5% 预算；PII 一次就电话叫醒。不要用同一套 burn-rate 窗口去等合规红线。

### Fast burn / Slow burn

仓库 `burn_rate.yaml` 和 `slo.py` 对齐讲义公式：

| 告警 | 窗口直觉 | 阈值 | 级别 |
|---|---|---|---|
| `CopilotAvailabilityFastBurn` | 按这速度 < 6h 烧光 30 天预算 | 14.4 × 0.005，持续 5m | P1 |
| `CopilotAvailabilitySlowBurn` | 按这速度 < 3 天烧光 | 6 × 0.005，持续 1h | P2 |
| `CopilotPIILeak` | 计数 > 0 | 1m 内 increase > 0 | P0 |

`for: 5m` 是防抖。14.4x 是 Google 多窗口多燃烧率的课堂常数，不是魔法数——改 SLO 目标时要一起改。

### 四级路由：什么都重要 = 什么都不重要

| 级 | 触发 | 响应 SLA | 路由 |
|---|---|---|---|
| P0 | 合规 / 资金 / 数据丢失 | < 5 min 接电话 | 电话 + SMS |
| P1 | 可用性 / 主链路挂 | < 15 min | PagerDuty + Slack |
| P2 | 延迟 / 质量 / 单工具失败 | < 1h | Slack + Email |
| P3 | 成本 / 慢退化 | < 8h（工作日） | Email / 日报 |

Slack `@channel` 是最大反模式：几天后全员屏蔽，等于没有告警。分级的本质是把有限的"被打扰额度"留给真事。

### 告警必须自带上下文

oncall 不该再去查"为什么告警"。最低配置：

- 当前 SLI vs SLO、burn_rate
- `top_error_types`（如 `TOOL_TIMEOUT:1502`）
- **`sample_trace_ids`** → 一键进 Phoenix
- 关联 `incident_id` / `release_id`

之后三步：看上下文 → 点 sample trace 对比 `rag.retrieve.*` / `llm.generate` / `tool.execute.*` / `hitl.wait` → DoW 决定 rollback 还是 hotfix。回滚 `--reason` 要带 incident id。状态机 `triggered → ack → mitigated → resolved` 用来算 MTTR。

`slo.py` 的 `evaluate_slo()` 会把失败 `trace_id` 和 `error_type` 写进每条 alert——契约测试和 closure 路径都在验这件事。

---

## 5. L05 · Replay：一次事故变成反例哨兵

### Bad case 不是垃圾

客户标好了"这个答案是错的、正确应该是什么"，这是花钱买不到的金标准。三条复利出口：

| 出口 | 接到哪 | 下次发生什么 |
|---|---|---|
| 反例库 | Week11 eval set（adversarial） | 同类错，CI 直接拦 |
| Runbook | Week09 / Week12 runbook | 同类 5 分钟定位 |
| 微调集（可选） | 长期改基础能力 | 免费标注 |

扫掉它的团队，永远为同一个坑付费。

### 五步：没产物 = 复盘没发生

| 步 | 动作 | SLA | 产物 |
|---|---|---|---|
| 1 Detect | 收集 bad case + `trace_id` + 反馈 | < 1h | incident ticket |
| 2 Triage | 严重度 + 路由 | < 30min | P0–P3 |
| 3 Locate | 按 trace 定位根因层 | < 2h | 根因（layer / category / detail） |
| 4 Fix | 改 prompt / 索引 / 工具 / Skill | 紧急 < 24h | PR + 回归 |
| 5 Verify | 加反例 + 跑 gate + 更新 runbook | < 48h | postmortem；**第 5 步最容易被省** |

### 五分钟根因树

打开时间轴 → 看哪段异常 → 看 span 属性 → 对上五类根因 → 回到对应周去修：

| 根因层 | 症状 | Trace 看什么 | 修哪里 |
|---|---|---|---|
| 检索漏召 | 答案缺关键事实 | `retrieve.*` hits 很少 | Week08 hybrid + Week07 chunk |
| 重排丢失 | 召回了但排到很后 | `rerank` kept / dropped 异常 | Week08 阈值 / reranker |
| LLM 编造 | 有答案但引用错 | `llm.generate` 的 `evidence_count=0` | Week08 prompt + Schema |
| 工具失败 | Agent 报错 / 部分响应 | `tool.execute.*` ERROR | Week10 契约 / fallback |
| HITL 阻塞 | 响应卡死 | `hitl.wait` 时长 | Week10 异步 + SLA |

可观测负责"看见在哪一层"；前几周负责"怎么修那一层"。fixture `incident_bad_citation.json` 就是第三类：retrieve OK、`llm.generate` 的 `evidence_count=0`。

### 复盘模板 7 段

仓库 `postmortems/template.md` 和 `incident.py` 的 `render_postmortem()` 对齐讲义：Summary / Trace Evidence / Root Cause / Fix / Verify / Lessons / Action Items。Action Items 勾完才能 archive。

### 进评测集：讲义原地 bump，仓库旁路写出

讲义伪代码是改 `evals/v2.3.0.json` 再 `bump_patch`。仓库明确禁止这条路：

- `prepare_regression_assets()` 从黄金集**拷一份**，追加 `W12-INC-...` 样本，写到 `reports/week12/regression/`
- 规范集 `evals/sets/rag_qa_golden_v2_3_0.jsonl` 字节级不变
- 用临时 prediction 跑 Week11 gate；`actual_bad_answer` 和 `trace_id` 留在 sample metadata

生产故障自动变评测，是 Week11 + Week12 合体；**变的是临时回归资产，不是课堂黄金集。**

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| OTel 接入 / Resource / sampler / 导出 | `observability/runtime/setup.py` | HTTP OTLP `/v1/traces`、`ParentBased` 采样、`SpanLimits(20, 512)`、`BatchSpanProcessor` |
| FastAPI 自动埋点 + 响应头 | `services/rag_api/app/observability.py`<br>`services/rag_api/app/main.py`<br>`services/tool_api/app/main.py` | `setup_telemetry` / `instrument_fastapi_app`；`X-Trace-ID` |
| Span API + OpenInference kind | `observability/runtime/spans.py` | `openinference.span.kind`、属性截断、异常时 `error.type` |
| PII 红线 | `observability/runtime/privacy.py` | `hash_text` / `safe_preview` / redact 规则 |
| RAG 6 段 span | `services/rag_api/app/routers/rag.py`<br>`services/rag_api/app/retrieval.py` | `rag.query` → intent → hybrid/vector/lexical/rrf → rerank → `llm.generate` → `rag.audit.persist` |
| Tool / HITL / 血缘 | `agent/copilot.py`<br>`services/tool_api/app/routers/tickets.py`<br>`tools/fallback.py` | `agent.invoke`、`tool.execute.*`、`hitl.*`、`tool.fallback.*` |
| Collector → Phoenix | `observability/otel/config.yaml` | 收 4317/4318，转发 Phoenix gRPC 4317 |
| 5 个面板 | `observability/dashboards/week12_panels.yaml` | 五面板名、角色、`drilldown` 链 |
| SLO 数字 | `observability/slo/week12_slo.yaml` | 五 objectives + 14.4 / 6.0 burn |
| Burn-rate 规则 | `observability/alerts/burn_rate.yaml` | Fast / Slow / PII，runbook 锚点 |
| 可执行 SLO | `observability/week12/slo.py` | fixture → SLI / 预算 / 带 `sample_trace_ids` 的 alerts |
| Live 分布式 trace | `observability/week12/demo_flow.py`<br>`observability/week12/verify_phoenix.py` | `inject(headers)`；Phoenix 断言同一棵树 |
| Incident 契约 + 复盘 | `contracts/observability/incident.schema.json`<br>`observability/week12/incident.py`<br>`postmortems/template.md` | 必填 `trace_id` / root_cause / 正反答案；7 段渲染 |
| Bad case → Week11 | `observability/week12/badcase.py`<br>`tools/badcase_to_eval.py` | 旁路写出；不改黄金集 |
| 闭环编排 | `observability/week12/run_closure.py` | alert → postmortem → eval gate → `closure-report.json` |
| 契约 / 集成测试 | `tests/contract/test_week12_observability_contracts.py`<br>`tests/integration/test_week12_observability_loop.py` | span 名存在于运行时路径；脱敏；gate 不污染黄金集 |
| 课堂 fixture | `tests/fixtures/week12/telemetry_window_bad.jsonl`<br>`tests/fixtures/week12/incident_bad_citation.json` | 快烧窗口；citation mismatch 样本 |
| 操作手册 / 蓝图 | `runbooks/week12-observability.md`<br>`docs/blueprints/week12/week12-observability-blueprint.md` | 两条路径怎么跑；生产扩什么、合同不改什么 |

### 代码里值得单独看、讲义没展开的细节

**默认不采内容。** `rag.py` 只在 `settings.otel_capture_content` 为真时写 `input.value` / `output.value`，且走 `safe_preview`。查询身份永远是 sha256 + length。这比讲义的 `query.text[:200]` 更严。

**同一条 asyncpg 连接不能并发。** `hybrid_retrieve` 里 vector / lexical **顺序**执行，集成测试专门锁了这件事。时间轴上两路 retrieve 看起来像串行，是连接模型限制，不是"没做 hybrid"。生产 fan-out 要两条连接再 `gather`。

**跨服务靠 W3C，不靠你手抄 trace_id。** `demo_flow.py` 用 `opentelemetry.propagate.inject` 把 `traceparent` 打进 HTTP 头。手工分别 curl RAG 和 Tool、不带头，会得到两个 `trace_id`——这是 runbook 里最常见的假失败。

**Closure 的 pass 条件有两截。** `run_closure.py` 要求：窗口里**真的产出了 alert**，并且 Week11 `gate.status=pass`。只有回归绿、告警空，整体仍是 fail——闭环证明的是"侦测得到 + 修得住"，不是"评测单独能跑"。

---

## 7. 讲义与仓库对不上的地方

这几处讲义写了但不要按路径去翻；精神在，落点换了。

| 讲义写的 | 实际情况 |
|---|---|
| `pipelines/observability/setup.py` | 不存在。运行时在 `observability/runtime/setup.py` |
| `services/rag/traced.py` | 不存在。span 写在 `services/rag_api/app/routers/rag.py` + `retrieval.py` |
| `observability/dashboards/*.py` | 不存在 `.py` 面板。定义是 `observability/dashboards/week12_panels.yaml` |
| `OpenAIInstrumentor` / `LangChainInstrumentor` + gRPC `:4317` | 业务 span 手写；FastAPI instrumentor；服务导出 **OTLP HTTP `:4318`**。Collector 仍收 4317/4318，再转 Phoenix 4317 |
| span 名 `rag.intent_route` / `rag.generate.llm` / `rag.audit.write` / `tool.call.*` / `tool.idempotent_check` | 仓库：`rag.intent.route` / `llm.generate` / `rag.audit.persist` / `tool.execute.*` / `tool.idempotency.check` |
| 在线 Faithfulness SLO > 0.85；cost < $0.05 | 可执行政策用 `citation_coverage: 0.95` 和 `cost_per_query_usd: 0.02` |
| `add_badcase_to_evalset` 原地改黄金集并 bump 版本 | **禁止。** 只写 `reports/week12/regression/`，`evals/sets/rag_qa_golden_v2_3_0.jsonl` 保持不变 |
| `omni rag release rollback ...` CLI | 仓库没有这条命令。回滚语义仍绑 Week08 `release_id`，操作走现有发布/runbook，不要找 `omni` 二进制 |

`tools/badcase_to_eval.py` **存在**，但是 `badcase.py` 的 CLI 薄封装，不会按讲义那样改 `evals/v2.3.0.json`。

---

## 8. 动手清单

所有命令从仓库根目录走 Docker。先起真实运行时，再跑两条路径。

```bash
# 0. 起 RAG / Tool / Collector / Phoenix
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml up -d --build \
  postgres minio phoenix otel_collector rag_api tool_api

# 健康检查：两个 API + Phoenix；Collector 日志应有 Everything is ready
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8001/health
curl -fsS http://localhost:6006/healthz

# 1. 契约：incident schema、五面板、SLO、告警、必备 span 名
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/contract/test_week12_observability_contracts.py -v

# 2. Live：发一条跨服务 trace，用 Phoenix REST 断言同一棵树
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  sh -lc '
    python -m observability.week12.demo_flow > /tmp/week12-demo.json
    cat /tmp/week12-demo.json
    TRACE_ID=$(python -c "import json; print(json.load(open(\"/tmp/week12-demo.json\"))[\"trace_id\"])")
    python -m observability.week12.verify_phoenix --trace-id "$TRACE_ID"
  '

# 3. Closure：fixture → 快烧告警 → postmortem → 临时 Week11 集 → gate
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m observability.week12.run_closure --output-dir reports/week12

# 4. 本周测试（含脱敏、SLO 上下文、不污染黄金集）
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/contract/test_week12_observability_contracts.py \
         tests/integration/test_week12_observability_loop.py -v
```

浏览器打开 `http://localhost:6006`，项目 `omnisupport-copilot`，最新一条时间轴应从 `omni.demo.flow` 读到 retrieve / generate / audit / tool / HITL。

**验收标准不是"命令退出码 0"**，而是能回答：

1. Live 结果里 `same_distributed_trace=true` 吗？RAG 和 Tool 的 `trace_id` 是否同一个？
2. Phoenix 里能否指出慢/错发生在哪一个 span 名？
3. Closure 的 alerts 是否包含 `copilot_availability_burn_fast`，且带 `sample_trace_ids`？
4. `reports/week12/postmortems/` 和 `regression/` 是否生成？`eval_gate.status` 是否 pass？
5. `evals/sets/rag_qa_golden_v2_3_0.jsonl` 是否**完全没被改**？

**加分：**

- 不注入 `traceparent` 分别打两个 API，确认会得到两个 `trace_id`，再回去跑 `demo_flow.py`
- 把 fixture 里的失败条改成全 OK，确认 `run_closure` 因"没有 alert"而 fail
- 在 span 属性里故意塞邮箱/手机号，确认 `safe_preview` 测例会红——这是 P0 红线的课堂版

排障速查（runbook 原文）：`trace_not_found` 先等 batch flush、核对 `OTEL_PROJECT_NAME`；Phoenix 空先重建 `rag_api tool_api` 镜像；Collector `connection refused` 按 compose 依赖重建 Phoenix 与 Collector。

### 动手清单参考答案

先自己答完上面的验收问题和加分练习，再往下对。

1. Live 路径要 `same_distributed_trace=true`，RAG 和 Tool 是同一个 `trace_id`。靠 `demo_flow.py` 的 W3C `traceparent` inject，不是手抄 id。单元测试过了不证明 Phoenix 接线。
2. 能。打开 Phoenix 项目 `omnisupport-copilot`，从 `omni.demo.flow` 读到 retrieve / generate / audit / tool / HITL，指出慢/错发生在哪一个 span 名（例如 `llm.generate` vs `hitl.wait`）。截一张图不算验收。
3. Closure 的 alerts 应包含 `copilot_availability_burn_fast`（对讲义/契约里的 FastBurn），且带 `sample_trace_ids`。`run_closure.py` 还要求窗口里**真的产出了 alert**——回归绿但告警空，整体仍是 fail。
4. 应生成 `reports/week12/postmortems/` 和 `reports/week12/regression/`，临时集上的 `eval_gate.status` 为 pass。Closure 证明的是告警 → incident → postmortem → Week11 反例 → eval gate。
5. **必须完全没被改。** 规范集 `evals/sets/rag_qa_golden_v2_3_0.jsonl` 字节级不变；坏样本只写到旁路目录。改黄金集会把 Week11 基线 digest 砸掉。

加分：不注入 `traceparent` 分别打两个 API，会得到两个 `trace_id`——这是 runbook 里最常见的假失败。fixture 全改 OK 后 `run_closure` 因「没有 alert」而 fail，闭环验的是「侦测得到 + 修得住」。span 里塞邮箱/手机号，`safe_preview` 测例应红——PII 是 P0，不是「可观测做得全」。

---

## 9. 易错点与边界

**概念层面**

- 接了 OTel ≠ 可观测。span 名叫 `process`、属性只剩 input/output 原文，是伪可观测。
- Trace ≠ Log 聚合。没有同一个 `trace_id` 和父子树，就没有因果链。
- Dashboard ≠ 指标墙。5 张决策图 + 钻取，比 20 张曲线有用。
- 告警阈值 ≠ SLO。前者看一次抖动，后者看预算燃烧速度。
- PII SLO ≠ 可用性 SLO。前者零容忍、P0、不等 burn 窗口。
- 复盘开会 ≠ Verify。没把 case 送进回归、没更新 runbook，同类事故必重发。
- 改黄金集 ≠ 复利。课堂闭环是**旁路资产**；污染 `rag_qa_golden_v2_3_0` 会把 Week11 基线砸掉。

**范围边界（Week12 做到哪）**

Student Core Pack：自托管 Phoenix、OTel Collector、五面板定义、可执行 SLO、bad-case → Week11 gate。

刻意不做、留给生产扩容的：托管 trace 存储与留存策略、尾部采样、Prometheus/Grafana 或企业 APM、真正的 on-call 路由、incident 工单系统对接。**契约和 span 名保持不变**，换后端不换语义。

本周也不引入图检索——那是 Week13 GraphRAG。`rag.py` 里已有 `rag.retrieve.graph` 等后续 span，学 Week12 时把它当成"同一套命名会继续长"，不要当成必须在本周调通的能力。

Week12 合上的是 Week08 服务路径、Week10 受控动作、Week11 评测门禁：看得见、叫得对人、修完还能拦住。

---

## 10. 自测题

答不上来说明这一节要回看。

1. 客户只说"今天 Copilot 很慢"，为什么先打开一条 trace 的时间轴，而不是先 `grep` 日志或先调 prompt？
2. Logs / Metrics / Traces 各能回答什么、各不能回答什么？缺了 Traces，oncall 会卡在哪一步？
3. 为什么 span 要叫 `rag.retrieve.hybrid` 而不是 `process`？少了 `rag.rerank.cross` 或 `rag.audit.persist`，出事时分别会瞎掉什么？
4. `query.text = 用户原文` 和 `omni.query.sha256 + length` 的取舍是什么？什么条件下才允许 `safe_preview`？
5. 五个必看面板里，为什么 Quality 必须和 Overview 同屏？只看 P99、不看 P50 和 Error Rate，会漏掉哪类事故？
6. "现在 P99=2.1s"为什么几乎没有信息量？什么时候该用 DoW，什么时候该用 Release 对比？
7. 同样一次 P99=4s，什么情况下不该叫人，什么情况下该 P1？14.4x 和 6x 分别在防什么？
8. PII 泄露为什么不能走"等 burn-rate 窗口"？P0 和 P2 的路由如果都进同一个 Slack 频道，会发生什么？
9. 告警 payload 里没有 `sample_trace_ids`，oncall 路径会在哪断掉？
10. `evidence_count=0` 但 retrieve hits 正常，根因应判哪一层？对应回到哪一周修？为什么不是先换向量库？
11. 为什么把 bad case 写进规范黄金集会破坏 Week11？仓库用什么机制既回归又不变黄金集？
12. Live 路径绿、Closure 路径没跑（或反过来），为什么还不能说 Week12 验收通过？

### 自测题参考答案

先自己答完上面的题，再往下对。

1. Agent 一条请求 8–15 hop，日志散在不同服务、时间戳还对不齐。时间轴直接告诉你 2.4s 里 1850ms 在 `llm.generate` 还是卡在 `hitl.wait`。先 `grep` 是对点不对链；先调 prompt 是还没定位就开药。
2. Logs 答单点发生了什么，跨服务对不上。Metrics 答趋势/容量/烧不烧，知道发烧不知哪个器官。Traces 答这一次穿了哪些 hop、慢/错在哪。缺 Traces，oncall 卡在「系统病了，猜是哪一段」。
3. 好 span 读起来像故事，`layer.action.strategy` 才能在时间轴上定位。少 `rag.rerank.cross`：召回了但精排丢掉时你会误判成「没检索到」。少 `rag.audit.persist`：看不见运行证据有没有落盘，复盘缺最后一环。
4. 原文进 span 是存储爆炸 + PII 出境；身份用 `omni.query.sha256` + `length`。`safe_preview` 必须显式开（`OTEL_CAPTURE_CONTENT`）、先 redact、再限长（仓库 200）。默认 false。span 不是第二份用户内容副本。
5. Quality 是 LLM 专属（citation / abstain / bad case），传统黄金信号没有「答得对不对」；和 Overview 同屏才能发现「成本涨同时 P99 也涨」这类共变（常是 `top_k` 被调大）。只看 P99 会漏掉「大多数人已经变慢」（P50）和「在报错而不是变慢」（Error Rate）。
6. 绝对值没有对照：电商周一本来就比周日高。DoW（今天 vs 上周同一天同时段）抓周节律突变；Release（当前 vs 上一 `release_id`）抓上线后退化。HoH 抓突发，基线抓慢退化。
7. 高峰偶发一下、错误预算内：不该叫人。持续半小时按 14.4x 狂烧 30 天预算：P1。14.4x FastBurn 防的是「几小时烧光月度预算」；6x SlowBurn 防的是「三天烧光」的慢漏。告警看 burn rate，不看一次 `P99>2s`。
8. PII 是零容忍、P0、计数 > 0 就电话叫醒，可用性才有 0.5% 预算可以花——不要用同一套 burn 窗口去等合规红线。P0 和 P2 都进同一个 Slack，几天后全员屏蔽，等于没有告警。分级是把有限的被打扰额度留给真事。
9. 钻取链在「面板 → 一条 sample trace」处断开。oncall 还得另开工具重搜 `trace_id`，30 秒定位变成 30 分钟。告警最低配置必须带 `sample_trace_ids`、当前 SLI vs SLO、`top_error_types`。
10. retrieve hits 正常但 `llm.generate` 的 `evidence_count=0`，根因是**生成层编造**（fixture `incident_bad_citation.json` 就是这一类）。回到 Week08 prompt + Schema 把引用约束住；若 hits 本身很少，才回 Week07 chunk / Week08 hybrid。**不要先换向量库**——可观测指出的是哪一层，前几周负责怎么修那一层。
11. 黄金集 digest 锁的是文件字节，原地追加样本会改 hash、打歪 Week11 基线和 CI。仓库 `prepare_regression_assets()` 拷一份到 `reports/week12/regression/`，追加 `W12-INC-...`，规范集 `rag_qa_golden_v2_3_0.jsonl` 保持不变。变的是临时回归资产，不是课堂黄金集。
12. 两条路径证明的不是同一件事：**Live** 证明 OTLP 真发出去、W3C 跨服务、Phoenix 能看到整棵树；**Closure** 证明告警 → 复盘 → 旁路反例 → eval gate，且不改黄金集。缺一条都不算过。单测绿 ≠ Phoenix 接线；截图绿 ≠ 回归闭环。

---

## 11. 一句话收口

Week12 不是"再加一套监控演示"，而是给前 11 周装上诊断回路：Week08 的 RAG、Week10 的受控动作、Week11 的评测门禁，第一次能在同一条 `trace_id` 上被看见、被叫停、被沉淀。评测告诉你系统好不好；可观测告诉你出事卡在哪——两边合上，Copilot 才从"能答"变成"能运营"。
