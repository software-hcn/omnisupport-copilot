# Week 01 · 从 Demo 到上线：AI 为什么不能直接用？

> **一句话**：能演示只说明局部成立，能上线要求整条交付链可控——先立标准、边界和工程基线，再谈智能。
>
> 讲义：`pdf/doc/week01-从 Demo 到上线：AI 为什么不能直接用？.pdf`（86 页 / 4 课时）
>
> 抽取说明：这份 PPT 几乎全是图片页，文本层抽不出来。下面按幻灯片内容重写，不是对仓库蓝图的转述。

---

## 0. 本周主干

四节课是同一根轴上的四次收窄：先承认 Demo 不是生产，再把"做完了"改成可签字，再选对路线，最后把项目骨架钉死。

```
L01 事故诊断     三案 → 五步复盘 → 五层模型     「Demo 幻觉为什么必炸」
      ↓
L02 可签字交付   五层 Done × 四角色签字          「什么叫真正 Done」
      ↓
L03 路线判断     脚本 RAG ≠ 目标架构             「先选路，再写检索」
      ↓
L04 工程基线     三类边界 + 七层 + 五步承诺      「第一周就必须定的东西」
      ↓
                 两份工件 → 后面 14 周按层补链
```

本周最值得原样记住的判断：

- **能演示，只说明局部成立；能上线，要求链路可控。**
- **企业 AI 的难点不在回答，而在负责。**
- **主要问题从来不是模型够不够聪明，而是路线是不是一开始就走对了。**
- **先定层，再定动作。顺序不能倒。**

后面 14 周不是"加料"，是在补同一条链。Week01 只交付诊断工具和开工条件，不交付 RAG 效果。

---

## 1. L01 · 拆掉 Demo 幻觉

### 核心论点

这不是事故八卦课。三个真实案例要用来建立**交付视角**：表面事故、首层失控、放大层、工程动作，必须分层看，不能一出事就去调 Prompt。

### 三案对照（同一套拆解模板）

| 案例 | 表面事故 | 首层失控 | 放大层 | 工程动作 |
|---|---|---|---|---|
| **Air Canada** | 政策答错，旅客照做，企业担责 | 知识层没把规则来源和版本约束住 | 生成层把不可靠内容包装成可信答复 | 来源约束、引用、拒答边界、人工升级 |
| **NYC MyCity** | 官方 bot 给出错误甚至潜在违法建议 | 检索层没把法规来源和边界约束住 | 治理 / 观测没把高风险场景拦下来 | 来源白名单、高风险拒答、升级路径、审计可见 |
| **DoNotPay** | 能力宣称越过监管和专业服务边界 | 工具 / 动作层没划清能做什么、不能做什么 | 治理层没把宣称、证据和责任绑在一起 | 收紧能力主张、限制动作、人工复核、发布治理 |

三案不是三类八卦，是三层失守：知识版本、检索边界、动作权限。后面整门课都在补这三层。

### 固定五步复盘（顺序不能倒）

1. **补背景**：先事实和责任上下文，不要上来猜技术原因
2. **看表面事故**：外部世界看到的失败是什么
3. **找首层失控**：哪一层最先裂开
4. **找放大层**：哪一层把裂缝放大成事故
5. **定工程动作**：补什么、拦什么、改什么

**先定层，再定动作。** 一上来改 Prompt / 换模型，就是把步骤 5 提到了步骤 1。

### 五层诊断模型（整门课的地图）

Week01 先给诊断工具，Week02–15 按层开处方：

| 层 | 周次 | 它回答什么 |
|---|---|---|
| 数据与输入 | W02–04 | 数据从哪来，怎么稳定进系统 |
| 检索与证据 | W07–08（W13 用 GraphRAG 补位） | 搜得到、答得稳、引得回 |
| 工具与动作 | W09–10 | 从会答到能办，边界划在哪 |
| 评测与观测 | W11–12 | 效果怎么量、问题怎么找 |
| 治理与发布 | W14–15 | 怎么稳定跑、怎么发、怎么回滚 |

W05–06 是横切：把口径和资产化贯穿整条链，不是另起一层。

### Demo 世界 vs 生产世界

| 维度 | Demo | 生产 |
|---|---|---|
| 数据 | 静态样例、手工准备、无版本 | 持续更新、口径漂移、权限和 PII |
| 用户 | 提问友好、上下文完整 | 问题歧义、分布极广、会撞边界 |
| 系统 | 单人掌控、单路径 | 跨系统、高并发、失败要系统处理 |
| 治理 | 先做出来再说 | 评测、观测、责任、发布回滚必须前置 |

Demo 允许人肉补上下文。生产要求系统把**证据、边界、观测、回滚**一起补上。这不是同一个世界。

### 交付链：记住顺序，不要只记名词

业务目标 → 数据盘点 → 数据契约 → 采集入湖 → 索引检索 → 生成与工具 → 评测观测 → 版本治理 → 上线回滚。

顺序一乱，后面就会边做边返工。整门课围着这条固定主链转，不围着"本周新名词"转。

### 课堂版 Launch Readiness

先问有没有这 6 类能力，而不是问"答得像不像人"：

1. 数据版本和更新边界
2. 权限与 PII 分层
3. 证据引用与来源约束
4. 工具动作和参数约束
5. 评测与观测
6. 回滚、HITL 与责任边界

分数低不代表项目没价值，只说明它还停在 Demo 阶段，后面有明确的补课顺序。

---

## 2. L02 · 可签字交付

### 核心论点

知识库问答 + 工单联动，什么时候才算真正 Done？不是 AI 答得更像人，而是**业务、架构、合规、运维**四类角色都拿得到签字证据。

现场演示顺，不等于任何角色敢放行。

### 五层 Done（前三层先站住）

| 层 | 签字时问什么 | 缺了会怎样 |
|---|---|---|
| **业务** | 改善什么结果、谁签字、灰度范围和失败容忍度 | 看起来有用，也不验收 |
| **质量** | 评测集 / 坏例池、阈值和门禁、变更后能否回归 | "感觉还行"无法复现 |
| **安全** | PII 和权限边界、动作是否分级、哪些必须进 HITL | 没人敢授权 |
| **运行** | 日志、版本、回滚、审计、成本、值班 | 出事只能人肉翻日志 |
| **治理** | 发布、责任边界、灰度与回滚策略 | 昨天对、今天错，回不去 |

先看前三层：业务、质量、安全站住，才有资格谈运行和治理。

### 四角色签字板

| 角色 | 先看什么 | 第一句追问 | 没有证据时 |
|---|---|---|---|
| 业务 | 结果 | 首问解决率和建单负担真的会改善吗？目标场景、成功指标、试点范围是什么？ | 延后上线，先补验收口径 |
| 架构 | 链路 | 数据、索引、Prompt、工具链能不能持续演进？契约、版本、回放是否稳定？ | 系统能跑，也不给生产准入 |
| 合规 | 边界 | PII、权限、动作分级、审计是否前置？ | 能力宣称直接越界 |
| 运维 | 恢复 | 出事能不能定位、重放、回滚？成本是否可见？ | 每次都靠临时救火 |

### Demo 到 Production 中间差的是签字条件

不是差一点工程细节，而是五类签字条件：业务、质量、安全、运行、治理。讲义把这画成峡谷：**Can demo ≠ Can ship**。要过峡谷，立刻需要验收、监控、回滚和护栏。

### 三张模板（本周就能写）

**交付标准计分卡**——先写签什么，再谈工程动作：

```yaml
scene: "客服问答 + 建单联动"
business_goal: "减少重复查询"
success_metrics:
  - "FAQ 首问解决率"
  - "建议建单采纳率"
status: "可灰度"
```

**质量门禁表**——把"看起来不错"切成"门禁过没过"：

```yaml
metric: "FAQ 首问解决率"
threshold: ">= 72%"
eval_dataset: "客服坏例池 v1"
fallback_action: "降级到知识检索"
```

失败后的 fallback 必须一起写清。门禁没有 fallback，就不是门禁，是愿望。

---

## 3. L03 · 路线判断

### 核心论点

别一上来就写 RAG。企业 AI 的主问题不是模型聪不聪明，而是**路线一开始对不对**。路线错了，后面每一层能力都变成补救；路线立住，后面 14 周才是按顺序补链。

### 两类必炸事故（路线错的早期信号）

| 事故 | 症状 | 本质 | 上线后果 |
|---|---|---|---|
| 规则漂移 | 规则已更新，答案还停在旧版 | 数据版本和更新链路没进系统 | 不是答错一条，是整个事实口径错 |
| 口径冲突 | 同名术语各部门定义不同，系统当同一词 | 契约和语义层没前置，检索只靠相似度 | 答案流畅，业务不敢用 |

这两类事故，换更强模型几乎没用。

### 脚本式 RAG：为什么快，为什么不是架构

最短可用路径：`上传文档 → Chunk / Embedding → 向量检索 → LLM 回答`。

链外留下的，全是昂贵能力：数据契约、版本、权限边界、bad-case 回放、治理 / 发布。**它快，不是因为它完整，而是因为这些能力都还在链外。**

### 真正的目标对象

不是"一个 RAG 系统"，是一条企业 AI 数据工程链：

```
输入资产 → 检索生成 → 工具行为 → 治理发布
```

| 段 | 要求 |
|---|---|
| 数据 | 输入做成可追溯资产，不是临时喂给模型的原料 |
| 检索与生成 | 像样不够，要带证据、能回归、可校验 |
| 工具与行为 | 从会答到能办，权限必须前置 |
| 治理与发布 | 评测、Tracing、版本、回滚、责任收成正式上线能力 |

### 八层目标架构

前四层决定有没有事实土壤，后四层决定能不能真正负责：

| 层 | 名字 | 它先保证什么 |
|---|---|---|
| 1 | 数据源 | owner、刷新频率、使用边界 |
| 2 | 数据入口 | 解析、清洗、PII、元数据一次做对，脏输入不往下传 |
| 3 | 数据底座 | 预留 time travel / 回放 / 回滚，旧数据不能互相覆盖 |
| 4 | 契约语义 | 术语、字段、权限标准统一，冻结 ≠ 限制 ≠ 停用 |
| 5 | 索引资产 | 索引可版本化，不要留一个黑盒向量库 |
| 6 | 检索生成 | 回答带证据、可校验、可回归、问题能重放 |
| 7 | 行为工具 | 会答 → 能办；动作分级和 HITL 做成规则 |
| 8 | 治理发布 | 评测、Tracing、版本、回滚连起来，责任可追 |

映射到 OmniSupport 时记住两句口诀：

- **索引 + 检索生成：先保证据。** 缺了：召回不可解释、证据不稳、坏例难复现。
- **工具行为：先保边界。** 缺了：从会答滑向越权执行。

### Week02–15 是在补链，不是加料

| 周次 | 补哪一层 | 对应的上线问题 |
|---|---|---|
| W02 | 输入资产与契约 | 哪些数据配进系统，哪些输入必须带边界 |
| W03 | 采集与原始保留 | 出问题后能不能回看原始事实 |
| W04–08 | 湖仓、索引、检索与服务化 | 索引、回答、证据为什么要变成可交付资产 |
| W09–10 | 工具层与动作边界 | 从会答到能办，为什么要先有权限和 HITL |
| W11–15 | 评测、Tracing、治理与发布 | 上线之后最贵的是回滚、责任和治理闭环 |

---

## 4. L04 · 工程基线：先定开工条件

### 核心论点

项目能不能开工，先看基线和边界定没定。Week01 不是把代码仓库跑起来就算完，而是回答：**一个企业级 AI 项目凭什么有资格开始。** 定错了，后面 14 周会反复返工。

贯穿 15 周的实施原则（仓库蓝图原文，讲义也用这五个词）：

**Data-first / Workflow-first / Evidence-first / Release-aware / Dual-scale**

### 冲突开场：E1042 为什么不是一个"回答"问题

Demo 级系统：搜 `E1042` / `rollback` / `gateway upgrade`，拼一句"建议先回滚再查依赖版本"。演示时看起来很懂。

生产级系统还必须继续判断：当前客户 SLA 和订阅权限是什么？这条产品线允不允许自动建单或回滚？回滚是不是高风险、必须进 HITL？答案有没有 evidence / `trace_id` / `release_id`？要不要同步进审计日志？

**企业 AI 的难点不在回答，而在负责。** Week01 的目标不是加功能，是把系统能负责到哪一步写清楚。

### 三类边界（工程基线真正要写的东西）

工程基线不是一组目录，是上线前必须先定义的三条边界：

| 边界 | 它在定义什么 | 不先定会发生什么 |
|---|---|---|
| **系统边界** | 什么数据和证据能进系统；哪些真实来源可被引用；输出必须遵循什么结构、字段、口径 | 旧规则、脏输入、同名对象混进来；答复看起来完整，但没有证据和口径约束 |
| **行为边界** | 系统能答、能建议、能执行什么；哪些必须保持人工、哪些永远不自动；证据不足 / 权限不足 / 状态冲突时怎么降级 | 系统显得无所不能，没人敢授权；高风险动作现场拍板 |
| **工程边界** | 环境、健康检查、Tracing、契约、Runbook 如何统一；种子数据、评测输入、发布版本如何可复现；失败后如何定位、重放、回滚 | 每周补漏；同一问题反复出现，因为没有共同基准 |

仓库里的落点：系统边界 → `docs/blueprints/boundary-checklist.md` + `contracts/`；行为边界 → 工具契约 + HITL；工程边界 → Compose / seed / contract test / runbook。

### 七层架构：从输入到负责

讲义把 OmniSupport 画成"从海底到水面"的七层，旁边再加一条贯穿的观测 / 治理：

```
User / Copilot UI
  Layer 7  Agent / Tool      工单工具 / KPI / HITL / JSON Schema / audit
  Layer 6  Serving           pgvector + BM25 → RRF → rerank → RAG API
                             citations / evidence_ids / confidence / trace_id / release_id
  Layer 5  Lakehouse         Bronze 保真 / Silver 统一 / Gold 服务视图；snapshot / time travel
  Layer 4  Parse / Normalize IDP / ASR / 视频切片 / OCR / PII 脱敏 / 统一 metadata
  Layer 3  Landing / Raw     MinIO，原始保真
  Layer 2  Data Contracts    schema / pii_level / quality_gate / owner；不合格自动拦截
  Layer 1  Source            Workspace / Edge Gateway / Studio；文档、工单、音视频
  贯穿     Observability     OTel + Phoenix / OpenLineage / evals / lakeFS
```

真正的企业 AI 不是靠检索和生成两层撑起来的。仓库蓝图把观测收成 Layer 7，讲义有时把它单列为第 8 层——同一件事，数层时不要较真，认职责。

### HITL 不是系统失败

触发条件：高风险操作、证据不足、状态冲突、权限不足。成熟标志不是"全自动"，是**知道什么时候该停**。最危险的状态不是系统不会做，而是不知道该把决策权交回给人。

### 五步工程基线（五个工程承诺）

| 步 | 承诺 | 含义 |
|---|---|---|
| 01 | 配置隔离 | 密钥和环境不写进代码，`.env.local` 与示例分离 |
| 02 | 环境同构 | Docker Compose 一条命令，本机和同学看到同一套服务 |
| 03 | 能力可验 | health / 冒烟 / 关键字段（`answer` / `citations` / `release_id` / `trace_id`）能检查 |
| 04 | 输入可复现 | 稳定种子数据，测试、演示、回归共用 |
| 05 | 边界可检查 | 契约测试先入场，系统边界能被自动化检查 |

缺一项，后面的协作和验收就没有共同基准。Week01 的"基线演示"本质上是在演示这五个承诺，不是在演示模型有多聪明。

### 本周要交的两份工件

讲义要求学员交：

1. **业务验收口径 & 风险边界清单**：业务目标、目标用户、禁止场景、PII / 动作分级、HITL 节点、失败降级、验收口径
2. **AI 系统落地蓝图**：一句话定义、核心对象、七层架构、首周运行基线、后续 14 周路线

仓库里已经写好了，分别是 `docs/blueprints/boundary-checklist.md` 和 `docs/blueprints/project-blueprint.md`。学习任务不是再写一份，是**对着讲义的字段把这两份读懂，并指出哪里已经落地、哪里还是后续周的预埋。**

---

## 6. 概念 → 代码映射

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| 工程基线 / Compose | `infra/docker-compose.yml` | postgres / minio / rag_api / tool_api / dagster / otel / phoenix 的启动顺序和端口 |
| 配置隔离 | `infra/env/.env.example` | 可复制为 `.env.local`；密钥可空，走 deterministic fallback |
| 七层架构与原则 | `docs/blueprints/project-blueprint.md` | Data-first 五原则、数据模型、逐周计划 |
| 系统 / 行为 / 风险边界 | `docs/blueprints/boundary-checklist.md` | 做什么/不做什么、PII、工具权限矩阵、HITL 触发 |
| 开工 Runbook | `runbooks/week01-startup.md` | Docker-only 路径、健康检查、seed、契约测试、RAG 冒烟 |
| 四类数据契约 | `contracts/data/{doc_asset,ticket,audio_asset,video_asset}_contract.json` | Week01 就要存在；资格规则 Week02 才跑起来 |
| 工具契约 | `contracts/tools/tool_contract_schema.json` 与 `contracts/tools/tools/*.json` | `search_knowledge` / `get_ticket_status` / `create_ticket` / `query_support_kpis_v1` |
| Release 契约 | `contracts/release/release_manifest_schema.json` | `release_id` 从第一周就预埋 |
| 种子 Manifest | `data/seed_manifests/manifest_{edge_gateway_pdf,tickets_synthetic,workspace_helpcenter}_v1.json` | Week01 baseline 三份；dry-run 应全部 `accept` |
| 输入可复现 | `data/synthetic_generators/ticket_simulator.py` | 合成工单，测试/演示/回归共用 |
| 边界可检查 | `tests/contract/test_json_schemas.py` | 文件头写明 Week01 DoD：契约测试必须绿 |
| 能力可验 | `services/rag_api/`、`services/tool_api/` | `/health`、`/api/v1/query` 响应含 citations / release_id / trace_id |
| 原始区 | MinIO buckets（compose 初始化） | 对应 Layer 3 Landing |
| 库初始化 | `infra/migrations/001_init.sql` | 结构化底座，后续周用 additive migration |

代码里值得单独看、讲义没展开的细节：

- RAG API 在没有模型密钥时走 **deterministic fallback**，这是"能力可验"故意设计成不依赖 LLM。
- PostgreSQL 映射到宿主机 `15432` 而不是 `5432`，避免和本机数据库抢端口。
- `test_json_schemas.py` 会校验后续周才真正用到的 release v2 / canary / compliance schema——契约可以先于实现存在，这就是"预埋"。

---

## 7. 讲义与仓库对不上的地方

| 讲义写法 | 实际情况 |
|---|---|
| 数据契约是 YAML | 仓库统一 JSON Schema；YAML 只出现在讲义示意图里 |
| 八层目标架构 | 蓝图写成七层，观测/治理有时单列第 8 层。认职责，别死磕编号 |
| 学员从零写两份工件 | 仓库已有 `project-blueprint.md` 和 `boundary-checklist.md` |
| 蓝图里 rag_api / tool_api / pipelines 仍标未完成 | 那是 Week01 当时的交付清单；当前主仓这些目录都已实现，不要按蓝图勾选框理解"现在还没有" |
| 没有 `tests/contract/test_week01_*.py` | Week01 DoD 就是 `tests/contract/test_json_schemas.py` + 全量 contract 测试 |
| 5 课时 | 讲义只标了 LESSON 01–04；五步承诺和两份工件收在 L04 后半 |

---

## 8. 动手清单

所有命令走 Docker，不要先配本地 Python。

```bash
cp infra/env/.env.example infra/env/.env.local

docker compose --env-file infra/env/.env.local \
  -f infra/docker-compose.yml up -d --build

curl -s http://localhost:8000/health
curl -s http://localhost:8001/health
# 浏览器: Dagster :3000 / MinIO :9001 / Phoenix :6006

docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python data/synthetic_generators/ticket_simulator.py --count 500 \
    --output data/canonization/tickets/tickets-seed-001.jsonl

docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m pipelines.ingestion.seed_loader \
    --manifest-path data/seed_manifests/manifest_edge_gateway_pdf_v1.json \
    --manifest-path data/seed_manifests/manifest_tickets_synthetic_v1.json \
    --manifest-path data/seed_manifests/manifest_workspace_helpcenter_v1.json

docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/contract/test_json_schemas.py -v

curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "如何配置 Northstar Workspace SSO？"}'
```

**验收标准不是"容器起来了"，而是能回答：**

1. 五个工程承诺分别对应哪条命令 / 哪份文件？缺了 seed 或契约测试，缺的是哪一条？
2. RAG 响应里有没有 `citations` / `evidence_ids` / `confidence` / `release_id` / `trace_id`？没有密钥时为什么仍然算"能力可验"？
3. 三份 baseline manifest 是 accept 还是出现了 warn / quarantine / reject？
4. `boundary-checklist.md` 里系统不做的五件事，和 Compose 里实际启动的服务，对得上吗？
5. E1042 这类故障，当前基线能"答一句"，还是已经能负责（权限 / HITL / 审计）？答不上来是正常的——那是 Week10+ 的课，但你要能指出缺口在哪一层。

**加分练习**：合上讲义，用五步复盘拆一次"回答突然变差"。如果第一步就写"换模型"，这周没过。

### 动手清单参考答案

先自己答完上面的验收问题和加分练习，再往下对。

1. **配置隔离** = 复制 `.env.example` → `.env.local`；**环境同构** = Compose `up`；**能力可验** = `/health` 与 `/api/v1/query`；**输入可复现** = `ticket_simulator` + 三份 baseline manifest 的 seed_loader；**边界可检查** = `pytest tests/contract/test_json_schemas.py`。缺 seed 缺的是第 4 条，缺契约测试缺的是第 5 条。
2. 应有 `citations` / `evidence_ids` / `confidence` / `release_id` / `trace_id`（字段名以实际响应为准）。没有密钥时走 deterministic fallback，工程链路仍可检查——证明的是「能力可验」，不是「模型效果」。
3. Week01 预期三份 baseline 全部 `accept`，不应出现 warn / quarantine / reject。出现后者说明 manifest、契约或门禁策略被改坏了。
4. 对得上：边界清单禁止开放域聊天、无限制自动执行、在线学习、实时通话、跨租户访问；Compose 只起 RAG/Tool/Dagster/MinIO/Phoenix 等受控服务，没有「万能聊天」或跨租户旁路。
5. 当前基线主要能「答一句」（RAG fallback）。权限矩阵、HITL、审计追责在边界清单和契约里是**预埋**，真正负责要到 Week10+。缺口在工具/动作层和治理层，不在「再换一个模型」。

加分练习：五步必须是补背景 → 看表面事故 → 找首层失控 → 找放大层 → 定工程动作。第一步写「换模型」是把第 5 步提前到第 1 步，本周没过。

---

## 9. 易错点与边界

**概念层面**

- 能答 ≠ 能上线。演示顺只说明局部路径成立。
- 脚本 RAG ≠ 生产架构。快是因为契约、版本、权限、回放、治理都在链外。
- HITL ≠ 系统失败。它是系统知道该停。
- 工程基线 ≠ 目录树。它是系统 / 行为 / 工程三条边界。
- 换模型解决不了规则漂移和口径冲突。
- 七层 / 八层 / 五层诊断是三个切面：诊断用五层，目标架构用八层，仓库实现用七层。不要合并成一张表去死记。

**范围边界（Week01 到底做到哪）**

Week01 交付的是**可演进的工程骨架**，不是可用的客服 Copilot。刻意不做：真正的 ingest 可靠性（W03）、Lakehouse 状态账本（W04）、语义层（W05）、资产化编排（W06）、结构保真解析（W07）、混合检索效果（W08）、Skill / 受控动作（W09–10）、评测门禁（W11）、全链路 tracing（W12）、GraphRAG（W13）、发布回滚（W14）、成本与 SLO（W15）。

预埋允许存在：`release_id` / `trace_id` 字段、四类数据契约、工具契约、HITL 触发条件写在边界清单里。预埋 ≠ 已经实现。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 用 Air Canada 走一遍五步复盘。如果你的"工程动作"第一条是改 Prompt，错在哪？
2. Demo 世界和生产世界在数据、用户、系统、治理上各差什么？举一个本项目里的对应例子。
3. 为什么 Launch Readiness 的 6 类能力里没有"模型效果"？
4. 业务方和架构方签字时各看什么？现场 demo 很顺，谁仍然会拦，为什么？
5. 质量门禁表为什么必须写 `fallback_action`？只写阈值会怎样？
6. 规则漂移和口径冲突，为什么都不是"换更大模型"能修的？
7. 脚本式 RAG 的四步链路上，契约、版本、权限、回放分别缺在哪一节之外？
8. 八层里"前四层"和"后四层"的分工用一句话怎么说？索引资产层为什么强调"不要黑盒向量库"？
9. E1042 在 Demo 和生产里的处理差在哪几项判断？哪些判断本周的仓库已经能做，哪些还不能？
10. 系统边界、行为边界、工程边界各举一个仓库里的文件。如果只定义了目录和 Compose，缺的是哪类边界？
11. 五个工程承诺缺了"输入可复现"，Week03 的 replay 会碰到什么具体困难？
12. HITL 的四个触发条件和"系统失败"的区别是什么？什么样的自动化才是不成熟？

### 自测题参考答案

先自己答完上面的题，再往下对。

1. 表面：政策答错、旅客照做、企业担责。首层失控：知识层没锁规则来源和版本。放大层：生成把不可靠内容包装成可信答复。工程动作：来源约束、引用、拒答、人工升级。第一条写改 Prompt，错在没先定层——Prompt 是放大层的症状修补。
2. 数据：静态样例 vs 持续更新/口径漂移/PII。用户：友好完整 vs 歧义/长尾/撞边界。系统：单人单路径 vs 跨系统并发与失败处理。治理：先做出来再说 vs 评测/观测/回滚前置。本项目例子：种子 JSONL 是 Demo 数据；`ticket_fact` + PII 分级 + release_id 才是生产侧。
3. 因为「答得像人」不能签字。6 类能力问的是版本、PII、证据、工具约束、评测观测、回滚/HITL——模型效果没有这些底座，会高自信地错。
4. 业务看结果（首问解决率、试点范围）；架构看链路（数据/索引/Prompt/工具能否演进，契约与回放）。现场顺只说明局部路径成立：业务会因没有验收口径拦，架构会因没有版本/契约不给生产准入。
5. 没有 fallback，门禁只是愿望：失败后现场拍板。必须写成「过不了则降级到知识检索 / HOLD / 回滚」。
6. 规则漂移是版本和更新链路没进系统；口径冲突是契约和语义层没前置。更大模型不会给字段装上版本，也不会统一各部门定义。
7. 最短链是上传 → chunk/embed → 向量检索 → LLM。契约缺在上传之外，版本缺在索引之外，权限缺在输出之外，回放/治理缺在整条主链之外。
8. 前四层决定有没有事实土壤（源、入口、底座、契约语义）；后四层决定能不能负责（索引资产、检索生成、行为工具、治理发布）。黑盒向量库无法绑定「哪一版文档资产」，事故无法回看。
9. Demo：搜 E1042 拼一句回滚建议。生产还要问 SLA/权限、产品线是否允许自动动作、是否 HITL、有无 evidence/trace/release、要不要审计。本周仓库能做 health、契约形状、带 release/trace 的 fallback 回答；还不能做真实权限执行、HITL 审批、金融审计。
10. 系统边界：`boundary-checklist.md` 或 `contracts/data/`。行为边界：`contracts/tools/`。工程边界：Compose + `test_json_schemas.py` + `runbooks/week01-startup.md`。只有目录和 Compose，缺的是系统/行为边界（谁能进、谁能做）。
11. replay 没有稳定种子和同一份 manifest，无法证明「重跑的是当初那批输入」。Week03 会变成对着漂移的文件赌博。
12. 触发：高风险、证据不足、状态冲突、权限不足。这是设计上的停，不是崩溃。不成熟的自动化是「不知道该把决策权交回给人」。

---

## 11. 一句话收口

Week01 是整门课的**诊断器和开工许可证**：它不教你把 RAG 做准，而是逼你先承认 Demo 与生产不是同一个世界，然后用五层模型、签字条件、路线和三类边界，把后面 14 周要补的链钉在同一张图上。骨架立住，后面每一周才有工程意义；骨架歪了，后面都在补救。
