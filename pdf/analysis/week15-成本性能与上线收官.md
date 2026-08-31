# Week 15 · 成本性能与上线收官：让系统能长期稳定跑

> **一句话**：前 14 周把能上线、能过监管的系统建出来了；本周补的是运营控制面——账单能拆、异常不白屏、质量有契约、故障有流程——再把 15 周收成一份能给陌生人看的 Capstone 作品。
>
> 讲义：`pdf/doc/Week15-成本性能与上线收官·Capstone课程毕业_v2.pdf`（40 页 / 5 课时）

---

## 0. 本周主干

五节课不是五块补丁，是同一条运营链：先知道钱花在哪，再保证挂了还有回声，再用契约管质量和速度，最后用流程而不是英雄值班。L05 把前 14 周收成可答辩产品。

```
L01 Cost        5 类拆账 + 5 抓手          「账单是工程对象」
      ↓
L02 Resilience  5 级降级 + 多级缓存        「有回声，不白屏」
      ↓
L03 SLO         6 大 SLO + 错误预算        「好不好能签字」
      ↓
L04 Runbook     Wheel + Agentic SRE        「靠流程，不靠老 X」
      ↓
L05 Capstone    15 周收口 + 演进路线       「能向陌生人证明」
```

讲义给了两条该单独记住的口令：

| 口令 | 含义 |
|---|---|
| **成本可控、异常不白屏、质量有契约、故障有流程** | 本周四块运营底线 |
| **8 条工程承诺** | 数据有契约 / 答案有证据 / 行为受控制 / 质量可量化 / 故障可定位 / 版本可回滚 / 监管可审计 / 长期可运营 |

读仓库时先分清两层，否则会在讲义路径里空转：L01–L04 是运营课，示例代码多数是幻灯片；仓库 Week15 真正落地的是 L05 的产品控制面（坐席工作台、租户、HITL、release 绑定）。L01–L04 的相近实现分散在 Week11/12 的 SLO、告警和生成 fallback，不是独立的 Cost/Resilience 服务。

---

## 1. L01 · 成本是工程对象，不是月账单

### 核心论点

只看 LLM 月账单，等于传统团队只看 AWS 总账：无法拆、无法归因、无法按 ROI 优化。成本要做成和 quality 同等的运行时对象——按段拆账、按查询归因、进同一块面板、按 ROI 排序动手。

### 拆账 / 归因 / 监控 / 优化

| 动作 | 回答什么 | 关键字段 |
|---|---|---|
| 拆账 | 钱花在哪一段 | Embedding / 检索 / 生成 / 存储 / 缓存 |
| 归因 | 这笔查询为什么贵 | `release_id` / span / 题型范式 |
| 监控 | 会不会月底超支 | cost/1k queries、日烧、月预算 burn |
| 优化 | 先做哪一件 | ROI = 节省 / 工程投入，不从最贵的砍 |

### 每查询成本：范式差 5 到 15 倍

单位指标是 **cost / 1k queries**，不是模型单价。成本失控经常是「FAQ 走了 GraphRAG Global」，不是「模型贵」。

| 范式 | 主要消耗 | cost / 1k | 大头 |
|---|---|---|---|
| 纯向量 RAG | 向量召回 + 一次生成 | $1.5–3 | 生成 ~60% |
| 混合 RAG（W8） | + BM25 + Cross-Encoder | $2.5–5 | 生成 + rerank |
| Agent 调工具 | 多轮 LLM + tool | $5–15 | 多轮 LLM ~70% |
| GraphRAG Global | 社区摘要 + 二次生成 | $8–25 | 多次 LLM |
| HITL 触发 | 通知 + 人工等待 + 二次生成 | $15–50 | 人工时间 |

Week13 的题型路由在这里变成最大省钱手段：用对范式，比换便宜模型省得多。

### 5 大抓手，按 ROI 排，不按「哪里贵」

| 抓手 | 做法 | 节省 | ROI |
|---|---|---|---|
| Cache 高频查询 | top-100 语义缓存 | 20–40% | 最高 |
| 题型路由 | 简单题不用图、不用长文 | 15–30% | 最高 |
| Embedding 复用 | 同 chunk 不重复 embed | 5–15% | 高 |
| 模型降级 | 简单题走 mini / haiku | 生成 20–50% | 高 |
| Batch 推理 | Embedding / Rerank / 离线评测批量 | Compute ~30% | 中 |

前两件投入小、回本通常不到一周。别一上来搞花哨优化。

语义缓存的工程约束比「加 Redis」重要：`similarity_threshold=0.92` 防误命中答错；key 绑 `tenant` + `release_id`（上新版自动失效，多租户不串缓存）；字面 O(1) 先命中，语义 O(log n) 兜「换了说法的同一问」。讲义给的量级：命中约 35% 流量、3 天回本。仓库里没有 `services/cache/semantic_cache.py`，不要去搜。

2026 工具链压成一句：LiteLLM 做统一网关 + 硬预算；Prompt Caching 缓存系统提示/长上下文（静态段约省 90%）；不赶时间的 Embedding/评测走 Batch（约 -50%）。模型变便宜救不了「没缓存、没路由、没批量」的工程。

---

## 2. L02 · 韧性是降级路径，不是重试 3 次

### 核心论点

AI 系统做不到「永远可用 + 永远快」——单次 LLM 30s timeout 是常态。韧性的本质是**按服务等级保住核心、放弃边缘**，并且每一级预先声明、自动触发。白屏比答得稍差更伤信任。

### 保住什么、放弃什么

| 等级 | 内容 | 态度 |
|---|---|---|
| P0 | 有回声不白屏；不泄露 PII | 红线，掉了=事故 |
| P1 | 答案基本正确、有引用 | 尽量保，可短暂降 |
| P2 | BM25 替向量、mini 替旗舰 | 主动降，用户能用 |
| P3 | 复杂归纳转人工 | 果断拒绝，别硬扛 |

### 5 级降级链

| 级别 | 动作 | 触发 | 用户感受 |
|---|---|---|---|
| L0 全功能 | 旗舰模型 + Hybrid + Graph + Rerank | 正常 | 最佳 |
| L1 轻度 | 换中档模型 | 旗舰排队 / 延迟 > 5s | 略降 |
| L2 中度 | 关 Graph，全走 vector | Graph 慢/错 | 不能跨文档归纳 |
| L3 重度 | BM25 + mini | pgvector / Embedding 挂 | 能用、准度降 |
| L4 兜底 | 缓存命中或引导人工 | 所有路径都挂 | 不白屏 + 转 HITL |

精髓是 L4：天塌了也要返回「已为您预约人工」，而不是 500。降级事件必须进 Week12 metric，否则值班看不见系统跑在哪一级。

### 4 级缓存：降成本的第二身份是韧性

| 级 | 位置 | 内容 | 命中率（讲义） | 价值 |
|---|---|---|---|---|
| L1 Browser | CDN / Edge | 完整 response | 5–10% | 0ms |
| L2 App | Redis | 语义级 response | 20–35% | 成本 + 韧性 |
| L3 Component | 本地 LRU | embed / rerank 中间结果 | 40–60% | 组件成本 |
| L4 Cold | 对象存储 | 完整 trace + bad case | N/A | 复盘 |

全链路 50–70% 命中时，上游挂了高频问题仍有答案。失效必须按 Week14 manifest 字段精细切：data 变清答案；prompt 变只清答案、**留 embedding**；model 变连 rerank 一起清；lakeFS 路径变更只清受影响 chunk。粗暴 `FLUSHALL` 会把命中率打掉 30–50%。

限流用令牌桶而不是硬 429：VIP / Default 分层配额；短时突发排队（讲义示例 5s），超时转 L4 友好文案 + `retry_after_seconds`。用户不应看到 HTTP 429 技术错误。

Hystrix 已退役，Java 侧是 Resilience4j / Sentinel；模型层 fallback 2026 可交给 LiteLLM router。工具不是瓶颈，瓶颈是上线前是否把降级路径写进契约。

仓库实际韧性更窄，但是真的、可演示的：无密钥或生成失败时返回 evidence summary，而不是空 500；Graph 无证据或运行失败回退 Hybrid；query rewrite 熔断后走确定性改写。这是 L4 思想的最小实现，不是 5 级链。

---

## 3. L03 · SLO 是双向契约，不是「再高一点」的 KPI

### SLO ≠ KPI

| 维度 | KPI（错配） | SLO（正确） |
|---|---|---|
| 本质 | 业务方追求目标 | 工程 vs 业务的双向契约 |
| 谁定 | 业务拍 | 双方签 |
| 上限 | 没有，越高越好 | 达到即可 |
| 不达标 | 工程加班赶 | 错误预算耗尽 → 暂停新功能 |
| 超额 | 「很好，继续」 | 用预算做更激进的改动 |

没预算的 SLO 就是 KPI。预算没烧完时，工程有权拒绝「再加一点质量、牺牲速度」。

### Copilot 的 6 大 SLO

传统 SRE 只有可用性/延迟。AI 系统必须加质量类和合规类，否则等于只测「一个会撒谎的系统在不在线」。

| 类别 | 目标（讲义示例） | 错误预算 |
|---|---|---|
| 可用性 | 月成功响应 ≥ 99.5% | 约 3.6h/月 |
| 延迟 | P50 ≤ 1s，P99 ≤ 3s | 与可用性一起烧 |
| Faithfulness | 在线抽样 ≥ 0.85 | 质量类约 15% |
| Citation Coverage | 100%（讲义） | 质量类 |
| Refusal Rate | ≤ 5% | 质量类 |
| PII 泄露 | = 0 | **0%，红线** |
| 合规拦截 | ≥ 99% | 合规 |
| cost/query | 中位数 ≤ $0.05 | 财务约 20% |

仓库 Week12 政策把 citation 写成 0.95、cost/query 写成 $0.02，和讲义数字不完全同一套；读代码时以 yaml 为准，讲义数字用来理解量级。

### 阈值从历史反推，不拍 99.99%

1. 收 30–90 天实际表现 → 2. 算 P50/P95/P99 → 3. 业务表态「能接受多差」→ 4. 取现状与可接受区间的 70–80% 交集 → 5. 试运行 30 天 → 6. 工程 + 业务 + 合规三方签字。跳过第 1、4 步，SLO 会变成工程被卷死的 KPI。

### 错误预算动作

Google 经典双烧：fast 14.4x（约 6h 烧光）P1；slow 6x（约 3 天烧光）P2。策略本身比数字重要：

| 预算剩余 | 自动动作 |
|---|---|
| > 50% | 允许激进改动（预算是用来花的） |
| < 25% | 冻结非关键变更 |
| < 10% | 冻结全部 + incident review |
| PII 一例 | P0 page + freeze，无差别 |

契约文档必须让业务方能签字：目标、预算动作、未达时工程 30 天改进计划、业务同期不得加需求、SLA 修订 30 天通知。讲义路径 `docs/slo/omnisupport-copilot-slo-v1.md` 仓库没有。

2026 做法是 SLO as Code（OpenSLO / Sloth / Pyrra）：yaml 进 Git，burn rate 告警自动生成。有完整 SLO = 用工程运营；没有 = 靠师傅经验和运气。

---

## 4. L04 · 应急是系统属性，不是个人英雄属性

### 4 级成熟度

| 级 | 表现 | 依赖 |
|---|---|---|
| L0 | 打电话找老 X | 个人英雄 |
| L1 | Confluence 几篇，出事找不到 | 文档 + 经验 |
| L2 | 故障分类树 + Runbook 库 | 体系化文档 |
| L3 | Runbook = Week09 Skill Pack + CLI | 工程化执行 |
| L4 | Agentic SRE 自动诊断/修复 | 系统自治，人守红线 |

大多数团队卡在 L1。拐点是升到 L3：告警自动带 Runbook 链接，人能跑、Agent 也能跑。

### 5 大类，先覆盖高频 25–30 个场景（约 80% 半夜起床）

| 类 | 典型 | 占比（讲义） |
|---|---|---|
| Infra | pgvector OOM、Redis 断、对象存储慢 | ~30% |
| Data + Model | 索引重建、LLM 429、Embedding 超时 | ~35% |
| Service + Compliance | RAG 挂、工具失败、HITL 积压、PII 报警 | ~35% |

索引必须有 `symptoms`（给 Week12 告警匹配）、`sla`、`owner`、`skill_pack`。讲义里的 `runbooks/index.yaml` 仓库没有；现有的是按周拆开的 markdown，加上 `observability/alerts/burn_rate.yaml` 里写死的 runbook 链接。

复利链：postmortem → 自动抽 symptoms/diagnosis/fix/rollback → 入索引 + 生成 Skill Pack + 排演练。没演练过的 Runbook 约等于没有。Wheel of Misfortune：每周 30 分钟、随机抽 1 个 oncall + 1 本手册、模拟真告警、1–5 分、发现过期命令当场 PR。写十份不演，不如写三份周周演。

Agentic SRE（Resolve.ai / Cleric 一类）可以把 detect→diagnose→remediate 的脏活做掉、MTTR 号称可砍大半，但回滚生产、冻结服务、动客户数据必须留 HITL。养料正是你结构化的 Runbook / Skill / postmortem。

---

## 5. L05 · Capstone：能向陌生人证明你能做

听完课、跑过 demo 都不算数。面试官要的是实物证据。讲义把作品集分成三列：能 clone 跑通的代码；能 sign-off 的工程产物（release / SLO / Runbook）；能讲清判断的答辩材料。

### 15 周产物地图（截图级清单）

| Week | 主题 | 产物 |
|---|---|---|
| 1–2 | 边界 + 契约 | contract + manifest + inventory |
| 3–4 | 采集 + Lakehouse | ingest + Iceberg |
| 5–6 | 语义层 + 资产化 | dbt + Dagster |
| 7–8 | 非结构化 + RAG | parse/chunk + Hybrid/Rerank |
| 9–10 | Skills + 受控 Agent | Skill Pack + Tool + HITL |
| 11–12 | 评测 + 可观测 | RAGAS + OTel + SLO |
| 13–14 | GraphRAG + 治理 | 图派生 + governed release |
| 15 | 上线收官 | 产品控制面 + 运营课 |

### 15 分钟答辩：先讲问题，别先 show RAG

| 页 | 内容 | 为什么 |
|---|---|---|
| 1 封面 | 项目名 + 结业 | 身份 |
| 2 问题 | 客服在 AI 时代该长什么样 | 听众不关心技术栈 |
| 3 架构 | 数据→检索→生成→Agent→治理 | 30 秒看懂 |
| 4 承诺 | 答得稳 / 办得对 / 可观测 / 可治理 | 对应 W8/W10/W12/W14 |
| 5–7 Demo | Happy Path / HITL / Bad Case | 三种最常被问的场景 |
| 8 数据 | RAGAS + 业务 SLO | 「0.91」比「答得准」硬 |
| 9–10 | 原子绑定回滚 + 合规白皮书 | 80% 候选人没有 |
| 11–12 | 学到的 3 件事 + 下一步 3 件事 | 不是做完就完 |

毕业后深扎，讲义只推一个方向：**评测与 AI 可靠性**——模型会更便宜更强，稀缺的是生产里可信赖。仓库不实现 12 个月职业路线，实现的是可 clone、可登录、可验收的产品。

本地 Docker Compose 是生产形态的**单机参考实现**：验证服务边界、契约、数据链、权限、幂等、审批、可观测和发布闭环。它不冒充多可用区、密钥托管或压测后的生产部署。默认无密钥时生成走 evidence summary fallback，这是可复现模式，不是假装调了模型。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 成本进同一块面板 | `observability/dashboards/week12_panels.yaml` | `cost` panel：`cost_per_query_usd` / token 属性 |
| L01 / L03 单位成本 SLO | `observability/slo/week12_slo.yaml` | `cost_per_query_usd.target: 0.02`，与讲义 $0.05 不同 |
| L01 题型路由即省钱 | `services/rag_api/app/routers/rag.py` | Graph 无证据或异常 → Hybrid，避免贵路径空转 |
| L01 换模型控成本 | `services/rag_api/app/llm.py` | `PROVIDER_DEFAULTS` + `LLM_PROVIDER` / `LLM_MODEL` 覆盖 |
| L02 L4 不白屏 | `services/rag_api/app/generator.py` | 无密钥或生成失败 → `deterministic_fallback` + 证据摘要 |
| L02 熔断思想 | `services/rag_api/app/query_rewrite.py` | 进程内 LRU cache + `_AsyncCircuitBreaker`，开路走确定性改写 |
| L02 P0 不泄露 PII | `observability/runtime/privacy.py` | trace 默认 hash/长度，预览必脱敏 |
| L02 内容不进 trace | `infra/env/.env.example` | `OTEL_CAPTURE_CONTENT=false` |
| L03 6 维 SLO 的仓库子集 | `observability/slo/week12_slo.yaml` | 可用性 99.5%、P99 3s、citation、cost、PII=0 |
| L03 错误预算计算 | `observability/week12/slo.py` | `evaluate_slo()`：burn_rate、remaining、P0/P1 告警 |
| L03 双烧告警 | `observability/alerts/burn_rate.yaml` | 14.4x / 6x，annotations 指向 Week12 runbook |
| L03 业务 SLO 门禁 | `evals/week11/business_slo.py` | 发布前对 target/current 做比较，不是在线 burn |
| L03 SLO 报告契约 | `contracts/observability/slo_report.schema.json` | `error_budget` + `alerts[].sample_trace_ids` 必填 |
| L04 告警→手册 | `runbooks/week12-observability.md` | availability fast burn / PII redline 章节 |
| L04 / L05 产品应急 | `runbooks/enterprise-capstone.md` | 启动、bootstrap、E2E、模型切换、故障定位 |
| L05 产品目标与边界 | `docs/blueprints/capstone/enterprise-capstone-blueprint.md` | 6 条产品承诺、本地≠生产对照表 |
| L05 坐席工作台 | `apps/copilot_console/` | 登录、证据抽屉、HITL 审批、CSP 头在 `nginx.conf` |
| L05 产品 BFF | `services/copilot_api/app/main.py` | 身份、租户 SQL、编排 RAG/Tool、落五类 release |
| L05 身份 | `services/copilot_api/app/security.py` | PBKDF2 + HMAC token，不存明文密码 |
| L05 输出契约 | `contracts/product/copilot_message.schema.json` | citations / evidence / 五类 release / `generation_mode` |
| L05 控制面表 | `infra/migrations/012_week15_capstone_product.sql` | `app_user` / conversation / message / feedback / 财务调整 / 产品审计 |
| L05 课程租户隔离 | `infra/migrations/013_week15_tenant_lineage.sql` | 非 capstone 工单标 `course-legacy` |
| L05 运行时硬化 | `infra/migrations/014_week15_runtime_hardening.sql` | 幂等主键带 `tenant_id`；金额 > 0 |
| L05 生成可审计 | `infra/migrations/015_week15_llm_runtime.sql` | `generation_mode` ∈ llm / deterministic_fallback / not_invoked |
| L05 数据工厂 | `scripts/capstone/generate_demo_data.py` | 固定 seed、`pii_redacted=True`、工单号 ≥ 900001 |
| L05 幂等灌数 | `scripts/capstone/bootstrap.py` | ingest → knowledge → analytics → graph → 激活 `capstone-v1.0.0` |
| L05 Dagster 资产图 | `pipelines/capstone/assets.py` | group `week15_capstone`，终点 `capstone_product_release` |
| L05 资产注册 | `pipelines/definitions.py` | `from pipelines.capstone import assets` |
| L05 图注释 | `data/capstone/graph_annotations_v1.json` | 10 个 source，`review_status=approved` |
| L05 知识资产 | `data/capstone/knowledge/workspace-api-webhook.html` | E2E 必须命中的证据源之一 |
| L05 公共 API 验收 | `scripts/capstone/verify_e2e.py` | 登录→RAG→反馈→KPI→备注→1 美元 HITL→Phoenix 三迹 |
| L05 产品契约测试 | `tests/contract/test_week15_capstone_product.py` | Compose 服务、资产链、迁移、金融动作必须带 evidence |
| L05 安全边界 | `tests/integration/test_week15_capstone_security.py` | 密码往返、内部四头失败关闭、幂等锁按租户 |
| L05 模型选择 | `tests/integration/test_week15_llm_provider.py` | provider 只由配置决定，可覆盖 model/base_url |
| L02 观测运行时 | `observability/runtime/setup.py`<br>`observability/runtime/spans.py` | 属性上限、默认不阻塞请求路径 |

### 代码里几个值得单独看的细节

**生成失败永远有答案。** `generator.py` 把「没配密钥」和「调用异常」收成同一条可审计路径，并写出 `generation_mode`，产品页和 E2E 都能区分「真生成」和「摘要兜底」：

```python
# services/rag_api/app/generator.py（无密钥 / except 两条路径同构）
return answer, confidence, None, {
    "mode": "deterministic_fallback",
    "provider": runtime.provider,
    "model": runtime.model,
}
```

`--require-llm` 会把这条路径判失败。本地演示默认走它，不是缺陷。

**Capstone release 在 dev 用 `signature_algorithm=none`。** `bootstrap.py` 的 `release_stage()` 写入 `governed_release_manifest` 后拨 `release_environment_pointer`。同一 `release_id` 若 digest 变了直接报错，逼你换 `CAPSTONE_RELEASE_ID`。这是 Week14 不可变绑定在毕业项目上的落地，不是「再跑一遍脚本覆盖」。

**金融动作在契约层就被拦住。** `014` 把 `tool_idempotency` 主键改成 `(tenant_id, tool_name, idempotency_key)`；`ticket_update` 的 financial 操作没有 `evidence_ids` 时 contract test 直接 `ValidationError`。HITL 不是 UI 提示，是表 + schema。

**Query rewrite 的 cache 不是语义缓存。** key 是 query + tenant + provider + model 的字面缓存，带 TTL 和 in-flight coalescing。它降的是改写延迟和重复 LLM 调用，对不上讲义 L01 的 0.92 近邻缓存。

---

## 7. 讲义与仓库对不上的地方

这几处讲义写了但仓库里没有，**别浪费时间去找**：

| 讲义写的路径 | 实际情况 |
|---|---|
| `services/cache/semantic_cache.py` | 不存在；没有语义近邻缓存服务 |
| `services/cache/invalidation.py` | 不存在；没有按 manifest 字段精细失效器 |
| `observability/dashboards/cost.py` | 不存在；成本只是 Week12 panel 里的一组 metric |
| `services/rag/resilient_serve.py` | 不存在；真实服务在 `services/rag_api/`，降级是 generator + Graph→Hybrid |
| `services/ratelimit.py` | 不存在；没有令牌桶 / VIP 队列 |
| `observability/slo/budget_policy.yaml` | 不存在；近邻是 `observability/slo/week12_slo.yaml` |
| `docs/slo/omnisupport-copilot-slo-v1.md` | 不存在；没有三方签字的 SLA 文档 |
| `runbooks/index.yaml` | 不存在；Runbook 按周拆 markdown，无故障分类树 |
| `tools/runbook_from_postmortem.py` | 不存在；Week12 有 postmortem 生成，不自动产出 Runbook/Skill |
| LiteLLM 网关 / Prompt Caching / Batch API | 未接入；模型切换靠 `LLM_PROVIDER` 环境变量 |
| 5 级降级链 L0–L4 自动切换 | 未实现；没有 `degradation_level` 字段 |
| Wheel of Misfortune 演练排期 | 文档级建议，仓库无演练 runner |

讲义 L05 说「完整 Capstone 作品集已 push 至 GitHub、25+ 应急手册、合规白皮书、答辩 PPT」——那是课程包装清单。本仓库交付的是可运行产品 + 蓝图 + 企业级 runbook，不是那整套对外材料包。

---

## 8. 动手清单

所有命令在仓库根目录执行，走 Docker Compose 的 capstone 路径（与 README / `runbooks/enterprise-capstone.md` 一致）。只运行一个仓库副本：Compose 容器名统一 `omni_*`，旧 Week worktree 同时 `up` 会把产品页打回 `dev-local`。

```bash
cp infra/env/.env.example infra/env/.env.local

# 1. 起真实运行组件
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml \
  up -d --build
curl -fsS http://localhost:8002/health
# postgres / rag_api / tool_api 都应 ok

# 2. 灌入虚构但结构真实的业务数据（幂等，不应翻倍）
docker compose --profile capstone --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm capstone_bootstrap

# 3. 契约 + 安全 + 模型配置（不依赖已灌库）
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/contract/test_week15_capstone_product.py \
         tests/integration/test_week15_capstone_security.py \
         tests/integration/test_week15_llm_provider.py -v

# 4. 公共 HTTP + Phoenix 端到端
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m scripts.capstone.verify_e2e
```

产品入口 <http://localhost:8010>。坐席 `agent@northstar.demo / Agent@2026`，管理员 `admin@northstar.demo / Admin@2026`。

**验收标准不是「跑过了」，而是能回答这六个问题**：

1. `ticket_fact` 里 `northstar-demo / data-capstone-v1` 是否恰好 240 条？重复 bootstrap 后有没有翻倍？
2. 当前发布知识是否仍是 10 个原始资产、91 个带 embedding 的 chunk？旧课程数据是否被标到 `course-legacy`？
3. Hybrid 问答是否命中 `workspace-api-webhook`，消息是否带 citations、五类 release id、`trace_id`、`generation_mode`？
4. Operations 的 KPI 是否拒绝 raw SQL、返回 `audit_id` 和 `semantic_aggregation` 策略？
5. `add_internal_note` 是否直接 completed，`grant_service_credit` 是否必须 `awaiting_approval`，管理员批准后财务行才落库？
6. Phoenix 里能否用页面上的 trace id 找到 `product.copilot.answer` + `rag.query`，以及 HITL wait / resume 两条独立迹？

**加分练习**：

- 不配密钥跑一遍 E2E，确认 `generation_mode=deterministic_fallback` 且仍有 evidence；配好模型后加 `--require-llm`，确认 fallback 会被判失败。
- Dagster UI（<http://localhost:3000>）筛 group `week15_capstone`，物化 `capstone_product_release` 及全部上游，成功标志是 `RUN_SUCCESS`。
- 故意去掉 financial 动作的 `evidence_ids`，看 contract test 如何失败——这是 L02「P0 边界」在 Tool Contract 上的对应物。
- 用两个租户的同一 `idempotency_key` 打 tool，确认锁 id 不同（`test_week15_capstone_security.py` 已覆盖逻辑）。

全新环境基线（runbook 口径）：240 工单 / 10 原始资产 / 91 chunk / Graph 16 entities、14 edges、2 communities。

---

## 9. 易错点与边界

**概念层面**

- **月账单 ≠ 成本模型。** 不能拆到 span / 范式 / release，就无法优化。
- **重试 ≠ 韧性。** 重试会把慢服务打得更死；韧性是预先声明的降级链。
- **KPI ≠ SLO。** KPI 没有上限；SLO 有错误预算，烧完就停功能。
- **可用性 SLO ≠ AI 质量 SLO。** 服务 99.5% 在线，仍然可以稳定幻觉。
- **Runbook 文档 ≠ 应急能力。** 找不到、不能执行、没演练，等于 L1。
- **Agentic SRE ≠ 把生产交给 Agent。** 诊断可以自动，回滚/冻服务/动客户数据必须 HITL。
- **语义缓存 ≠ query rewrite LRU。** 前者按向量近邻复用答案，后者按字面 key 复用改写结果。
- **deterministic_fallback ≠ 模型降级。** 仓库兜底是证据摘要，不是 haiku 接着生成。
- **本地 Compose ≠ 生产。** 蓝图第 7 节列了 OIDC、HA、mTLS、预算网关等必须另做的事。
- **无密钥 fallback ≠ 生成质量验收。** 工程链通过了，Week11 评测门禁仍然要真实模型。

**范围边界（Week15 到底做到哪）**

仓库交付的是**可答辩的产品控制面**：真实 ingest/index/graph/dbt、可登录工作台、租户隔离、证据问答、受治理 KPI、HITL、Phoenix 追责、governed release 指针。

刻意不做、或只存在于讲义的：语义缓存与精细失效、5 级自动降级、令牌桶、LiteLLM 预算网关、三方签字 SLA 文档、Runbook 索引与 Wheel 演练、Agentic SRE。那些是运营课的判断框架，要靠你在真实环境里继续建。

L01–L04 的「相近实现」来自 Week11 业务 SLO、Week12 面板/告警/错误预算、Week08/13 的 fallback，不是 Week15 新建的 Cost/Resilience 子系统。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. CFO 拿着「上月 LLM 12 万」找上门。为什么只看这张账单无法做工程优化？拆账的 5 类和归因要用的两个键分别是什么？
2. 把 FAQ 丢进 GraphRAG Global，成本可能差一个数量级。题型路由省的是质量还是钱？为什么通常比换 mini 模型更划算？
3. 语义缓存 `threshold=0.92` 为什么要设这么高？key 里去掉 `release_id` 或 `tenant` 各会造成什么事故？
4. OpenAI 大面积 429 时，「重试 3 次」和「L1→L4 降级链」对用户和下游依赖的差别是什么？L4 为什么必须返回 answer 而不是 500？
5. Prompt 变了却把 embedding 缓存全清，错在哪一层函数关系？正确失效范围是什么？
6. 用一句话说清 SLO 和 KPI 的差别。错误预算剩余 20% 和 60% 时，对「再加一个质量需求」的默认答复分别是什么？
7. 一套只有可用性 99.5%、P99 < 3s 的 SLO，漏了哪两类维度？为什么这对 AI 系统特别危险？
8. 凌晨 3 点告警，L1 团队和 L3 团队的第一动作有什么不同？`symptoms` 字段解决的是哪个工程问题？
9. 为什么没演练过的 Runbook 约等于没有？Wheel 里「当场修过期命令」保的是什么性质？
10. 无密钥时产品仍能演示问答，验收时却可能必须 `--require-llm`。这两种模式分别证明什么、不能证明什么？
11. 同一 `idempotency_key` 在两个 `tenant_id` 下为什么必须是两把锁？这和讲义 L02 的哪条 P0 红线是同一类问题？
12. 讲义 5 级降级在仓库里找不到。你用哪三条真实路径向面试官说明「系统异常时不白屏」仍然成立？

---

## 11. 一句话收口

Week15 是整门课的**运营侧收口**：前 14 周解决「能不能建、能不能管、能不能回滚」，这一周问「能不能长期稳、账单会不会把你打穿、3 点钟有没有流程」。讲义把判断框架讲完；仓库把判断收成一套坐席能点、E2E 能绿、release 能指的产品。8 条工程承诺里，前 7 条来自 Week02–14，第 8 条「长期可运营」才是本周要你带走的习惯——成本、降级、SLO、Runbook 都要当成和 contract 一样的工程对象，而不是上线之后再补的 PPT。
