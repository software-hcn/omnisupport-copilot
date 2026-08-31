# Week 13 · GraphRAG：跨文档关系与全局归纳

> **一句话**：给 Week08 向量 RAG 补上一层「看关系、做归纳」的派生能力——只在全局归纳 / 关系遍历 / 交叉验证 / 时间序列这四类主场题型上场，FAQ 和定义题继续走 hybrid。
>
> 讲义：`pdf/doc/week13-GraphRAG·跨文档关系与全局归纳.pdf`（53 页 / 5 课时）

---

## 0. 本周主干

五节课是一条「该不该上图 → 怎么建 → 怎么搜 → 怎么喂模型 → 怎么用数据决定去留」的闭环，不是另起一条 RAG：

```
Week07 evidence-ready chunks + Week08 hybrid RAG
      ↓
L01 Boundary     5 条准入：全过才上 / 过 3 项做 PoC / 不到 3 项别上
      ↓
L02 Build        schema.yaml → extract → align → community → graph_release
      ↓
L03 Search       classifier 路由：hybrid / local / global / multi-hop / DRIFT
      ↓
L04 Augment      图→文本 + 4 套 prompt + chunk/graph 双链 citation
      ↓
L05 Compare      按题型 A/B → routing_policy 写入 release manifest
      ↓
                 Week14 把 graph_release 跟 data/index/prompt/skill 原子绑定
```

讲义里三条口令值得单独记住：

| 口令 | 它挡住什么 |
|---|---|
| **GraphRAG 不是更好的 RAG，是补位** | 「答不准就上图」这种工程债 |
| **图是 silver chunks 上长出来的派生层，不是独立链** | 另搭抽取 / 另选图库 / 另起服务，契约和血缘全断 |
| **别问「成不成功」，问「哪些题型成功、哪些其实没必要」** | 总体 F 涨 2 个点就全量上线 |

---

## 1. L01 · Boundary：何时上图

### 核心论点

向量检索有一个水面下的假设：**答案藏在语义相近的某几个 chunk 里**。这个假设覆盖大多数客服 / FAQ，但碰到「过去半年所有 P0 故障的共性是什么」就必然翻车——答案不在某几个 chunk，而在 chunk 之间的关系。

搞错定位的两种死法一样常见：该上不上，和不该上瞎上。后者更糟，因为 FAQ 类查询会被拖慢、加噪、加钱，而质量不会涨。

### 向量必败的 4 类 vs 千万别上图的 3 类

| 向量死角（上图主场） | 典型问法 | 向量为什么失败 | 图怎么解 |
|---|---|---|---|
| **全局归纳** | 「过去 6 个月主要故障类型」 | 答案散在 100+ 文档 | 社区检测 + 主题聚合 |
| **关系遍历** | 「A 的子公司的供应商有哪些」 | 多跳关系编码不进向量 | 有界路径遍历 |
| **交叉验证** | 「X 在合同 / 邮件 / 工单里各怎么描述」 | 同一实体跨文档语义不一致 | 实体对齐 + 多源聚合 |
| **时间序列** | 「产品 V1→V2→V3 的演进」 | 时序关系被相似度抹平 | 带时间属性的关系边 |

| 向量主场（禁止上图） | 典型问法 | 上图会怎样 |
|---|---|---|
| FAQ / 操作类 | 「怎么重置密码」 | 答案就在 1–2 个 chunk，纯浪费 |
| 定义 / 概念类 | 「什么是 SLA」 | 单点知识，图引入噪声 |
| 短对话 / 闲聊 | 客服寒暄 | 关系简单，向量 + Tool 足够 |

识别口令：问题里带「所有 / 共性 / 分布 / 演进 / 之间的关系」，基本就是向量死角。先数历史问题日志里这 4 类占多少，这个比例决定上不上图。

### 成本账：2024 吓人，2026 重写了，但课堂不跟论文走

讲义用微软 demo 的 **$33,000 全量索引** 说明 2024 为什么怕上图，再用 LazyGraphRAG（建图只抽名词短语，LLM 留到查询时）把索引成本改写成「约等于向量」。仓库更保守：Student Core **构图不烧 LLM**，抽取走已审查 annotations；图存在 PostgreSQL，Neo4j 只是 `GraphStore` 可替换边界。课堂要学的是 **schema-first + 证据绑定 + 按题型路由**，不是再引入一套外部框架。

### 上图前的 5 个判断标准

| 判断项 | 具体问题 | 阈值 | 不达标 |
|---|---|---|---|
| 题型占比 | 归纳 / 多跳类占多少 | > 20% | 收益抵不过成本 |
| 数据规模 | 文档数量 | > 1k | 图结构没意义 |
| 关系密度 | 实体间是否真有结构 | 高（产品 / 组织 / 时序） | 低密度图是摆设 |
| 查询频率 | 主场题型 QPS | > 0.1 | 摊不平构建成本 |
| 工程能力 | 有没有 Week06–12 底子 | 齐全 | 没底子上图是空中楼阁 |

用法：5 项全过 → 上；只过 3 项 → 先做 PoC 跑按题型 A/B；不到 3 项 → 别折腾。最后一项解释了为什么 GraphRAG 放在第 13 周而不是第 3 周。

讲义的试水顺序（Contextual Retrieval → LazyGraphRAG → Neo4j）当行业背景即可；本仓库已有 Week08 hybrid，下一步就是这套受治理的派生图。

---

## 2. L02 · Build：schema-first + 实体对齐

### 核心论点

90% 的 GraphRAG 失败死在构建，不在图算法。让 LLM 自由抽，会出现 8 种「产品」类型、同一公司 5 个名字、关系动词五花八门——社区检测、路径遍历全被噪声击穿。

第一性原理：**先定 schema，再做抽取。** 节点类型 5–20 种、关系类型 10–30 种，禁止 LLM 自创类型，禁止 `related_to` 这种含糊动词。

### OmniSupport 真实 schema（不要按讲义里的 Customer/Ticket 去找）

仓库落地的是客服知识图，不是讲义示意的工单图：

| 层 | 允许的类型 |
|---|---|
| 实体 | `PRODUCT` / `ISSUE` / `SYMPTOM` / `RESOLUTION` / `VERSION` / `DOCUMENT` |
| 关系 | `HAS_ISSUE` / `HAS_SYMPTOM` / `RESOLVED_BY` / `APPLIES_TO_VERSION` / `SUPERSEDES` / `DOCUMENTS` |
| 质量门 | 实体/关系置信度 ≥ 0.85；模糊自动合并 0.96；模糊送审 0.88；边必须带 evidence；查询最多 3 hop |

`Workspace` 和 `Northstar Workspace` 在 schema 里是同一 `PRODUCT` 的别名。契约测试会断言它们合并成一个节点。

### 三种抽取策略 vs 仓库默认

| 策略 | 精度 | 成本 / 1k chunks | 适用 |
|---|---|---|---|
| 纯规则 NER + 词典 | 70–80% | < $1 | 已知实体 / 简单场景 |
| 纯 LLM 自由抽 | 85–92% | $50–200 | 复杂关系，但不可治理 |
| **LLM + Schema 约束** | 88–94% | $30–100 | 讲义推荐的生产主链路 |
| 规则先行 + LLM 兜底 | 85–93% | $10–40 | 大规模、成本敏感 |

仓库 Student Core 再往下走一档：`SchemaConstrainedExtractor` 只接受 **已审查 annotations** 或 `Type: value` 标注行。未知类型、低置信、无证据的边直接 reject / quarantine，不入库。生产 LLM/NER 适配器可以实现同一 `Extractor` 协议，但输出必须先过这个校验器。

口令：**宁可漏抽，不要错抽。** 错抽进图会污染下游所有推理。

### 实体对齐：最被低估的难点

| 对齐问题 | 表现 | 工程解法 |
|---|---|---|
| 命名变体 | Acme Inc / Acme Corp / Acme | 别名词典 + 字符相似 |
| 缩写 / 翻译 | OpenAI / OAI / 开放 AI | 别名集合；讲义还加 LLM 判断 |
| 类型冲突 | 同名不同类 | 按 `entity_type` 分桶，不跨类合并 |
| 时间漂移 | Twitter → X | 时序图（`valid_from` / `valid_to`）；讲义指向 Graphiti / Zep |

讲义给了 4 阶段漏斗（词典 70% → 字符相似 → embedding → LLM 兜底），目标是 95% 免费完成。仓库更保守，没有 embedding / LLM 判断：

1. schema 别名命中 → `accepted / schema_alias`
2. 同 type 精确归一化命中 → `accepted / exact_match`
3. 模糊分 ≥ 0.96 且与第二名差距 ≥ 0.03 → `accepted / unique_fuzzy`
4. 模糊分 ≥ 0.88 但不够唯一 → **`quarantined`，不强制合并**
5. 否则新建节点

模糊匹配进隔离而不是「差不多就并」，是 ADR-0013 的硬决策。图废掉的最快方式就是把两个不同实体合成一个。

### 图是派生资产，一次构建吃一个上游 release

- 上游：Week07 的 evidence-ready chunk（课堂 fixture：`data/week13/graph_source_chunks_v1.jsonl`）
- 下游：`graph_release` + `entity_node` + `relation_edge` + `community` + `evidence_projection`
- 一个 `graph_release` 只消费 **恰好一个** `data_release_id`；上游换版就出新的 graph release，禁止原地改图
- `graph_evidence_projection` 把 citation 字段冻在该 release 上，防止后来 chunk 更新把旧图证据悄悄改写
- 回滚是切 `GRAPH_RELEASE_ID` 或把路由切回 `hybrid`，不是删表

社区检测：讲义用 Leiden + 每社区 LLM 摘要（预计算）。Student Core 用确定性连通分量（BFS）+ 「`TYPE: name, name`」摘要，保证同输入同 ID、同拓扑。这是课堂可复现，不是声称 Leiden 过时。

---

## 3. L03 · Search：Local / Global / Multi-hop

### 核心论点

图检索的工程价值 = **召回向量召不回的东西**。向量找「长得像答案」的 chunk，图找「通过关系链到答案」的实体。生产里从来不是图取代向量，而是按题型路由、低置信降级。

### 模式对照（连同仓库默认）

| 模式 | 解什么题 | 运行时行为 | 代价 |
|---|---|---|---|
| `hybrid` | FAQ、事实、操作步骤 | Week08 pgvector + FTS + RRF | 低 |
| `graph_local` | 一个问题及其直接症状 / 解决方案 | 种子实体 + **1 hop** 扩展 | 低 |
| `graph_global` | 跨文档共性 / 分布 | 预计算社区摘要，按 query 排序 | 建图贵、查询便宜 |
| `graph_multihop` | 显式关系链 | 有界递归遍历，**最多 3 hop** | 中，最易爆炸 |
| `graph_drift` | 焦点实体 + 更大背景 | local 路径 ∪ global 社区 | 中 |
| `auto` | 运行时分类 | 确定性分类器；吃不准就 hybrid | — |

讲义中的 DRIFT 是微软把 Local+Global 揉进一次查询；仓库实现是直白并集（有界路径 ∪ 社区再序列化），不依赖微软框架。

### 分类器怎么选模式

讲义用小模型结构化输出 4 类（`focal / global / multihop / factual`），`confidence < 0.7` 降级走向量。仓库是正则分类器，阈值同样 0.70，优先级写死：

```
multi-hop 信号 → graph_multihop
global ∩ local → graph_drift
仅 global     → graph_global
仅 local      → graph_local
FAQ / 是什么  → hybrid
无图信号 / 低置信 → hybrid
```

测试里的对照样例值得背：

| 问句 | 路由 |
|---|---|
| 「怎么重置密码」 | `hybrid` |
| 「SSO login loop 的原因和解决方案是什么」 | `graph_local` |
| 「过去半年所有故障的共性是什么」 | `graph_global` |
| 「哪些问题导致哪些症状并由什么方案解决」 | `graph_multihop` |

### Multi-hop 四道护栏

| 坑 | 后果 | 仓库怎么焊 |
|---|---|---|
| 无跳数限制 | 召回上千节点，撑爆上下文 | `max_hops` clamp 到 `[1, 3]`，API 与 store 双层限制 |
| 关系不过滤 | 噪声边带偏语义 | schema allowlist；未知关系构建期就 reject |
| 不打分 | 强弱边平等 | 路径 score = 边置信度均值 |
| 不验证路径 | 「有路径就相关」 | 生成层模板要求逐步走边；缺证据必须 abstain |

无图证据、release 非 `active`、运行时异常：`/rag/answer` **降级 hybrid**，并在 `graph_debug.fallback_reason` 留下原因。默认检索模式始终是 `hybrid`。课堂遍历是 PostgreSQL `WITH RECURSIVE` / 内存 BFS。

---

## 4. L04 · Augment：图→文本 + 分模式模板

### 核心论点

LLM 不会读图。把 `{src, edge, tgt}` JSON 丢进 prompt，召回再准生成也会稀烂。图增强生成的核心工程问题不是图算法，是 **图→文本的翻译质量**。口令：**能用文本就别用 JSON。**

### 三种序列化 × 对应模式

| 策略 | 形态 | 配合模式 | 优点 | 局限 |
|---|---|---|---|---|
| 路径 → 句子 | `A -[HAS_ISSUE]-> B -[RESOLVED_BY]-> C` | Multi-hop | LLM 友好、可审计 | 长路径冗长 |
| 子图 → 结构文本 | 焦点实体 + 邻居关系 | Local | 结构清晰 | 吃上下文 |
| 社区 → 摘要块 | `Community N (k entities): …` | Global | token 效率高 | 丢局部细节 |

仓库 `serialize_graph_context()` 把路径和社区编成带 `Evidence: ev-…` 的文本块，**硬截断 6000 字符**。citation 不由模型发明，只从已持久化的 evidence metadata 组装。

### 为什么不能一套 prompt 打天下

| 模板 | 强制约束 |
|---|---|
| `graph_local_v1.md` | 只用返回的局部子图解释焦点实体、直接邻居、症状和已验证方案；区分「已持久化关系」和「解读」；不要推广到路径之外 |
| `graph_global_v1.md` | 只归纳返回的社区；未覆盖的社区不得说成「全部文档」 |
| `graph_multihop_v1.md` | 一跳一跳走，给每条关系命名，不许跳过中间实体；缺证据的 hop 必须弃权 |
| `graph_drift_v1.md` | 先局部路径，社区只提供有界全局背景；局部事实和全局规律分开引用 |

讲义写 3 套，仓库多了 DRIFT 第 4 套。都挂在 `graph_prompt_manifest.yml` 上，走 Week08 的 Prompt as Code。

### 双链证据

图给线索（结构），原文给凭证（可引用）。合规和信任上，**证据永远比线索重要**。响应里必须同时有：

- Week08 的 `citations` / `evidence_ids`（chunk 链）
- `retrieval_mode` + `graph_debug.paths` / communities（图链）
- `trace_id` / `release_id` / `graph_release_id`

五步流水线里真正新增的只有两块：**Serialize** 和 **Cite 里的图证据**。Route / Retrieve / Generate 都是在 Week08 上插槽。

### 五个反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 直接 JSON 喂模型 | LLM 解读差 | path / table / summary |
| 一套模板通用 | 归纳变枚举、聚焦变发散 | 分模式模板 |
| 只给图不给原文 | 客户问「凭什么」答不上 | `source_chunks` 必带 |
| 不暴露 mode | 评测无法分层 | `retrieval_mode` 必填 |
| 路径 7+ 跳 | LLM 失焦、成本爆炸 | `max_hops ≤ 3` |

---

## 5. L05 · Compare：按题型 A/B + 治理纳入

### 核心论点

总体指标「F 从 0.85 涨到 0.87」会骗人：70% 简单题图可能更差，30% 归纳题图好一大截，一平均略涨。真正该算的是：**主场题型收益 × 占比 − 额外成本，> 0 才上。**

### A/B 四要素

| 设计项 | 做法 | 缺了会怎样 |
|---|---|---|
| 并行运行 | 同 query 同时跑 vector / graph | 时间偏差污染结论 |
| 按题型分层 | `factual / local / global / multi_hop` 分别统计 | 加权平均掩盖局部翻车 |
| 多模型 Judge | Week11 交叉评审 | 单一 judge 偏见 |
| 影子流量 | 5–10% 真实流量只评不返 | 实验室样本好看、上线拉胯 |

### 讲义 200 样本 vs 仓库门禁

讲义 OmniSupport 示意表（用来给业务讲清「必须按题型路由」）：

| 题型 | 占比 | Vec 忠实度 | Graph 忠实度 | 推荐 |
|---|---|---|---|---|
| 局部聚焦 | 35% | 0.91 | 0.88 | Vector |
| 全局归纳 | 20% | 0.52 | 0.83 | Graph |
| 多跳推理 | 17.5% | 0.61 | 0.84 | Graph |
| 具体事实 | 27.5% | 0.93 | 0.90 | Vector |

仓库门禁更硬，不看总体平均。`evals/week13/ab.py` 对每一类：

| 条件 | `decision` | 路由 |
|---|---|---|
| Δquality ≥ 0.08 且 cost_ratio ≤ 5.0 | `graph` | local→`graph_local`，global→`graph_global`，multi_hop→`graph_multihop`；factual 即使 graph 赢也仍标 `hybrid` |
| Δquality ≤ 0.02 | `vector` | `hybrid` |
| 样本不足 / 结论不明 | `need_more_data` | `hybrid`（先不放图） |
| 缺类或缺样本 | gate `fail` | 不能上线 |

课程 fixture 里 `local` 是图赢（约 +0.14），和讲义「局部聚焦 Vector 胜」不是同一划分——见第 7 节。课程 fixture **不能当生产上线证据**，必须换成真实影子流量 / 标注集。

### 接入治理的 5 类必做

| 能力 | 本周落到哪 | 不做的后果 |
|---|---|---|
| 评测 | 题型分层 A/B + golden | 不知道图是否劣化 |
| 可观测 | rag.py 打 `omni.graph.*` OTel span | 出问题不知哪段慢 |
| 告警 / SLO | 图查询失败降级 hybrid | 图挂了客户先发现 |
| 治理 | release manifest 绑 `graph_release_id` + `category_routes` | 图版本和向量版本错位 |
| Bad case | 错路径 / 错社区进 Week12 档案 | 同类错反复发生 |

回滚三板斧：切上一个 active `graph_release_id`；路由统一 `hybrid`；问题 release 标 `deprecated`，图和 build report 留着审计。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 派生资产决策 | `docs/adr/0013-week13-graphrag-derived-asset.md` | 图不是第二套 ingest；PG 是可跑基线，Neo4j 走 `GraphStore` |
| L01 运行时全图 | `docs/blueprints/week13/week13-graphrag-blueprint.md` | 构建→路由→生成→A/B 的文件级阅读路径 |
| L02 图 schema + 校验 | `pipelines/graph/schema.yaml`<br>`pipelines/graph/schema.py` | allowlist、别名、`quality_gate`；未知类型抛错 |
| L02 抽取 / 对齐 / 社区 / 构建 | `pipelines/graph/extract.py`<br>`pipelines/graph/align.py`<br>`pipelines/graph/community.py`<br>`pipelines/graph/build.py` | annotations 优先；隔离不强制合并；BFS 社区；一 release 一数据版本 |
| L02 事务持久化 | `pipelines/graph/store.py` | 部分写入不能变 active；内容变必须换 ID |
| L02 表结构 | `infra/migrations/010_week13_graphrag.sql` | 边 `CHECK cardinality(evidence_ids) > 0`；`valid_from`/`valid_to` 预留 |
| L02 构图输入 + Dagster | `data/week13/graph_source_chunks_v1.jsonl`<br>`pipelines/graph/assets.py` | 两条产品线 fixture；UI 只出报告，真写入用 CLI |
| L03 题型分类 | `services/graph/classifier.py` | 正则 + 0.70 阈值，吃不准回 hybrid |
| L03 四种检索 | `services/graph/retrieval.py` | local=1 hop；multi-hop/DRIFT clamp 3；无证据只警告不编造 |
| L03 图存储边界 | `services/graph/store.py` | `GraphStore` 协议、PG 递归、内存测试适配器 |
| L04 图→文本 | `services/graph/serialize.py` | 路径句子 + 社区摘要，`max_chars=6000` |
| L04 分模式模板 | `services/rag_api/app/prompts/graph_*_v1.md`<br>`services/rag_api/app/prompts/graph_prompt_manifest.yml` | 4 套约束，不是 1 套通用 |
| L04 运行时接入 | `services/rag_api/app/routers/rag.py` | 默认 hybrid；图失败记 `fallback_reason` 后降级 |
| L05 按题型 A/B | `evals/week13/ab.py`<br>`evals/graphrag_ab.py`<br>`evals/fixtures/week13/graphrag_ab_cases_v1.jsonl` | 逻辑 vs CLI；fixture 只验门禁形状，不是生产证据 |
| L05 构建 / A/B 契约 | `contracts/graph/graph_build_report.schema.json`<br>`contracts/graph/graphrag_ab_report.schema.json` | status、evidence、routing_policy |
| L05 release 绑定 | `contracts/release/release_manifest_example.json` | `graph_release_id` + `category_routes.factual=hybrid` |
| 契约 / 集成测试 | `tests/contract/test_week13_graphrag_contracts.py`<br>`tests/integration/test_week13_graphrag_pipeline.py`<br>`tests/integration/test_week13_graph_postgres.py`<br>`tests/integration/test_week13_rag_api_real_graph.py`<br>`tests/integration/test_week13_definitions_loadable.py` | 未知关系拒绝、别名合并、真 PG 多跳、API citation |
| 操作手册 | `runbooks/week13-graphrag.md` | 迁移、构图、curl、A/B、回滚 |

### 代码里几个值得单独看的细节

**质量门硬编码在 schema，不是 prompt。** `quality_gate` 把「什么能进图」焊死：

```yaml
min_entity_confidence: 0.85
min_relation_confidence: 0.85
fuzzy_auto_merge_threshold: 0.96
fuzzy_review_threshold: 0.88
max_query_hops: 3
require_evidence_for_edges: true
```

**构建 `status` 极严。** `entities` 和 `edges` 都非空，且 `quarantined`、`rejected` 都为空才是 `pass`，否则 `warn`。隔离一条别名模糊匹配，整次构建就不能当生产 release。

**同一 `graph_release_id` 不可变。** 内容或 `index_release_id` 变了还用旧 ID，`persist_graph_build` 抛 `already exists with different content`。版本切换靠新 ID + 路由，不靠覆盖。

**SQL 比 Python 更早挡住无证据边：** `graph_relation_edge.evidence_ids` 有 `CHECK (cardinality(evidence_ids) > 0)`。`graph_evidence_projection` 把 `page_no` / `section_path` / `bbox` / `doc_version` 按 release 冻结——这是 Week07 证据锚点在图层的延续。

**factual 即使图质量更高也不会被 A/B 改成图模式。** `routing_policy` 里 factual 的 graph 分支写死 `hybrid`。这是「FAQ 不要上图」在评测层的落实。

---

## 7. 讲义与仓库对不上的地方

这几处讲义写了但仓库里没有或语义不同，**别浪费时间去找**：

| 讲义写的 | 实际情况 |
|---|---|
| `pipelines/assets/graph.py`（`@asset entity_node`，silver.chunks 上游） | 不存在。Dagster 入口是 `pipelines/graph/assets.py` 的 `week13_graph_release` / `week13_graph_build`，输入是 jsonl fixture，不是直接读 silver 表 |
| `schema.yaml` 里 Customer / Ticket / `SUBMITTED_BY` / `RELATED_TO` | 示意 schema。仓库是 PRODUCT / ISSUE / SYMPTOM / RESOLUTION / VERSION / DOCUMENT |
| `extract.py` 调 `gpt-4o` + pydantic `response_format` | Student Core 是确定性抽取器；LLM 抽取是协议扩展，不是默认路径 |
| `align.py` 用 rapidfuzz + embedding + LLM 四段漏斗 | 仓库是别名 / 精确 / SequenceMatcher + quarantine，没有 LLM 对齐 |
| Leiden + `leidenalg` / `igraph` 社区摘要 | `community.py` 是 BFS 连通分量 + 确定性摘要 |
| `services/graph/local_search.py`、`multihop.py`（Neo4j APOC / Cypher） | 不存在。检索在 `retrieval.py`，存储是 PostgreSQL `GraphStore` |
| `prompts/graph_local.j2` 等 Jinja 三套 | 实际是 `services/rag_api/app/prompts/graph_*_v1.md`，且多了 `graph_drift_v1.md` |
| `services/graph/response.py` 的 ChunkEvidence / GraphEvidence | 不存在。响应模型在 `services/rag_api/app/models/rag_models.py`（`citations` + `graph_debug`） |
| `evals/graphrag_ab.py` 现场调两路 RAG + Ragas | 该文件只是 CLI；打分逻辑在 `evals/week13/ab.py`，读的是已经成对标注的 jsonl，不在线打模型 |
| 分类器 4 类名 `focal / global / multihop / factual` | 仓库是 `factual / local / global / multi_hop`，另有运行时 `graph_drift` |
| `release/manifests/rag-v2026.05.18-001.yaml` | 不存在。JSON：`contracts/release/release_manifest_example.json` |
| 讲义 A/B：局部聚焦 Vector 胜 | 仓库把 FAQ 划进 `factual→hybrid`，把「一问题的症状/方案」划进 `local→graph_local`；fixture 里 local 是图赢。两套「local」不是同一题型 |
| 「生产默认 Neo4j + neo4j-graphrag」 | ADR：课堂 PG；生产可换图引擎，但 schema / 证据 / release / 评测轨道不能绕开 |

---

## 8. 动手清单

所有命令统一走 Docker / Compose，避免本机 Python 环境漂移。在仓库根目录执行。

```bash
# 1. 起依赖（已有 volume 不会自动跑 initdb）
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml up -d --build \
  postgres minio minio_init rag_api

# 2. 手工打 Week13 增量迁移，确认 graph_* 表
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml exec -T postgres \
  psql -U omni -d omnisupport < infra/migrations/010_week13_graphrag.sql
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml exec postgres \
  psql -U omni -d omnisupport -c "\dt graph_*"

# 3. 先出可审查构图报告（不写库）
docker compose --profile tools --env-file infra/env/.env.local -f infra/docker-compose.yml run --rm devbox \
  python -m pipelines.graph.build \
    --input data/week13/graph_source_chunks_v1.jsonl \
    --graph-release-id graph-week13-dev-v1 \
    --output reports/week13/graph-build-report.json

# 4. 同一事务写入 PG（不是 dry-run）
docker compose --profile tools --env-file infra/env/.env.local -f infra/docker-compose.yml run --rm devbox \
  python -m pipelines.graph.build \
    --input data/week13/graph_source_chunks_v1.jsonl \
    --graph-release-id graph-week13-dev-v1 \
    --output reports/week13/graph-build-report.json \
    --persist \
    --index-release-id index-week08-dev

# 5. 多跳真检索（没配外部 LLM 时返回证据摘要，但路径和 citation 必须是真的）
curl -sS http://localhost:8000/rag/answer \
  -H 'Content-Type: application/json' \
  -H 'X-Service-Token: dev-internal-token-change-in-prod' \
  -H 'X-Actor-ID: instructor-local' \
  -H 'X-Actor-Role: instructor' \
  -H 'X-Tenant-ID: course-legacy' \
  -d '{"question":"Northstar Workspace SSO login loop 的问题、症状和解决方案关系链","retrieval_mode":"graph_multihop","graph_release_id":"graph-week13-dev-v1","max_graph_hops":3,"include_debug":true}'

# 6. 按题型 A/B 门禁
docker compose --profile tools --env-file infra/env/.env.local -f infra/docker-compose.yml run --rm devbox \
  python -m evals.graphrag_ab \
    --cases evals/fixtures/week13/graphrag_ab_cases_v1.jsonl \
    --vector-release-id index-week08-dev \
    --graph-release-id graph-week13-dev-v1 \
    --output reports/week13/graphrag-ab-report.json

# 7. Week13 全套测试
docker compose --profile tools --env-file infra/env/.env.local -f infra/docker-compose.yml run --rm devbox \
  pytest \
    tests/contract/test_week13_graphrag_contracts.py \
    tests/integration/test_week13_graphrag_pipeline.py \
    tests/integration/test_week13_graph_postgres.py \
    tests/integration/test_week13_rag_api_real_graph.py \
    tests/integration/test_week13_definitions_loadable.py \
    -v
```

**验收标准不是「跑过了」，而是能回答这六个问题：**

1. 构图报告 `status=pass`，且每条边 `evidence_ids` 非空？`Workspace` 有没有和 `Northstar Workspace` 并成一个 PRODUCT？
2. `graph_release` 是 `active`，且绑定了哪个 `index_release_id` / `data_release_id`？
3. 多跳请求的 `retrieval_mode`、`citations`、`graph_debug.paths` 是否非空？`fallback_reason` 是不是 null？
4. 「怎么重置密码」走 `auto` 时有没有仍落在 `hybrid`？有没有因为开了 Week13 就把 FAQ 送进图？
5. A/B 报告的 `routing_policy` 是不是按类给的，而不是一个全局开关？
6. 图失败时 API 是否降级 hybrid，而不是 500 或编造 citation？

**加分练习：**

- 在 schema 里加一种未声明关系，确认构建 `rejected` 且边列表仍为空
- 把 `Workspace` 别名删掉再构图，确认出现两个 PRODUCT 节点——这就是对齐失败如何把图切碎
- 用同一个 `graph-week13-dev-v1` 改输入再 `--persist`，确认被不可变 release 挡住，必须换新 ID

Dagster 的 `week13_graphrag` group 只看编排和报告；真写入用第 4 步 CLI。

### 动手清单参考答案

先自己答完上面的验收问题和加分练习，再往下对。

1. 通过的构图报告应是 `status=pass`（`entities` / `edges` 都非空，且 `quarantined`、`rejected` 都为空），每条边的 `evidence_ids` 必须非空——`quality_gate.require_evidence_for_edges` 和 SQL `CHECK (cardinality(evidence_ids) > 0)` 都会挡住无证据边。`Workspace` 与 `Northstar Workspace` 在 schema 里是同一 `PRODUCT` 的别名，契约测试会断言它们合并成一个节点；没合并就是对齐失败，后面的路径会碎。
2. persist 之后该 `graph_release` 应为 `active`，并绑上命令里的 `index_release_id=index-week08-dev`；一个 graph release 只消费恰好一个 `data_release_id`。图是 Week07 silver chunks 上长出来的派生层，上游换版就出新的 graph release，禁止原地改图。
3. 成功的多跳响应里 `retrieval_mode` 应是 `graph_multihop`，`citations` 与 `graph_debug.paths` 非空，`fallback_reason` 为 null。没配外部 LLM 时可以返回证据摘要，但路径和 citation 必须是已持久化的真证据，不能编。
4. 「怎么重置密码」走 `auto` 必须仍落在 `hybrid`。GraphRAG 是补位不是更好的 RAG：FAQ / 定义是向量主场，开了 Week13 也不许把 FAQ 送进图——分类器碰到 FAQ / 「是什么」信号直接 hybrid。
5. A/B 的 `routing_policy` 必须按 `factual / local / global / multi_hop` 分别给决策，不是一个全局开关。`Δquality ≥ 0.08` 且 `cost_ratio ≤ 5.0` 才给该类开图，但 `factual` 即使图质量更高也仍标 `hybrid`。课程 fixture 只验门禁形状，不能当生产上线证据。
6. 无图证据、release 非 `active`、运行时异常时，`/rag/answer` 降级 `hybrid` 并在 `graph_debug.fallback_reason` 留下原因，而不是 500 或编造 citation。默认检索模式始终是 `hybrid`。

加分练习：在 schema 里加未声明关系，构建应 `rejected` 且边列表仍为空——schema-first 禁止 LLM 自创类型，未知关系构建期就 reject。把 `Workspace` 别名删掉再构图，会出现两个 PRODUCT 节点，这就是对齐失败如何把图切碎。用同一个 `graph-week13-dev-v1` 改输入再 `--persist`，会被不可变 release 挡住（`already exists with different content`），必须换新 ID，不能原地覆盖。

---

## 9. 易错点与边界

**概念层面**

- GraphRAG ≠ 更好的 RAG。它是向量主场之外的补位。
- schema 通过 ≠ 图能用。没对齐的别名会把同一实体切成多个节点，路径全部碎掉。
- Local ≠ 「所有带实体的问题」。FAQ / 定义仍是 hybrid；local 是「已知锚点的一跳邻居」。
- Global ≠ 每次查询跑社区检测。社区是构图时预计算、查询时只检索摘要。
- DRIFT ≠ 第三种独立图。它是 local 路径 + global 社区的一次查询。
- quarantine ≠ reject。quarantine 等人审；reject 是类型非法、无证据、低置信，不能进图。
- 总体平均上涨 ≠ 可以全量开图。按类 Δquality 和 cost_ratio 过门才给该类开图。
- 图线索 ≠ 引用凭证。没有 chunk citation 的图答案在合规上站不住。

**范围边界（Week13 到底做到哪）**

Week13 交付的是一条 **受治理的图检索扩展**：schema-first 构建、PG 可运行存储、分模式检索与生成、按题型 A/B、release 绑定。刻意不做的：

| 留给谁 | 什么 |
|---|---|
| 生产适配器 / 课外 | Neo4j 集群、LazyGraphRAG、Graphiti 时序记忆、Leiden + LLM 社区摘要 |
| Week11 | 多模型 Judge、真实影子流量、Ragas 在线打分 |
| Week12 | Phoenix 上把 Graph 特有 bad case 闭环（错路径 / 错社区） |
| Week14 | data / index / prompt / skill / **graph** 五件套原子绑定与秒级回滚 |

Student Core 的 PostgreSQL 图是「课堂能跑、契约能守」的基线，不是「PG 取代所有图数据库」的声明。换引擎时必须保住：类型 schema、证据 ID、scope、hop/token 预算、trace、按类 A/B。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 业务说「最近答案不准，上 GraphRAG 吧」。你先问哪 5 件事？只过 3 项时该做什么？
2. 「怎么重置密码」和「过去半年 P0 共性」为什么必须走两条检索路？用向量假设（答案在相近 chunk 里）解释。
3. 为什么 GraphRAG 必须建成 Week06/07 的派生资产，而不能另起一套抽取服务？断掉的是哪四样能力？
4. schema-first 相对「让 LLM 自由抽」到底焊死了什么？仓库里未知关系进图会怎样？
5. `Workspace` 和 `Northstar Workspace` 为什么必须是一个节点？对齐失败对 multi-hop 的具体破坏是什么？
6. 模糊分 0.90 的两个同类型实体，仓库会合并还是隔离？为什么不跟讲义那样交给 LLM 判断？
7. Local / Global / Multi-hop / DRIFT 各解哪类题？Local 为什么是 1 hop 而 Multi-hop 才允许到 3？
8. 分类器低置信时为什么必须回 hybrid，而不是「试试图也好」？
9. 为什么把图 JSON 塞进 prompt 会让生成变差？三种序列化各服务哪种模式？
10. 只返回图路径、不带 `evidence_ids`，在合规上错在哪？双链分别守什么？
11. 总体 faithfulness +0.02、成本 ×5，能不能全量开 GraphRAG？即使图质量更高，`factual` 的 routing_policy 为什么仍写死 `hybrid`？
12. 图 release 已经 active，上游 chunk 改了一段原文。旧的 graph citation 会不会跟着变？哪个表挡住了这件事？

### 自测题参考答案

先自己答完上面的题，再往下对。

1. 先问上图前的 5 件事：归纳/多跳题型占比是否 > 20%、文档规模是否 > 1k、实体间是否真有结构密度、主场题型 QPS 是否 > 0.1、Week06–12 底子齐不齐。GraphRAG 是补位不是更好的 RAG，「答不准就上图」是工程债。5 项全过才上；只过 3 项做 PoC、跑按题型 A/B；不到 3 项别上。
2. 向量假设是「答案藏在语义相近的某几个 chunk 里」。「怎么重置密码」答案就在 1–2 个 chunk，必须走 hybrid；「过去半年 P0 共性」散在 100+ 文档、答案在关系里，向量必败，走 `graph_global`。FAQ 上图只会拖慢、加噪、加钱，质量不涨。
3. 图必须建成 Week06/07 的派生资产：一个 `graph_release` 只消费恰好一个 `data_release_id`，citation 冻在该 release 上。另起抽取服务会把契约、血缘、证据锚点、release 版本绑定四样一起切断——另选图库、另起服务同样如此。回滚是切 `GRAPH_RELEASE_ID` 或把路由切回 hybrid，不是删表。
4. schema-first 焊死的是类型 allowlist：节点 5–20 种、关系 10–30 种，禁止 LLM 自创类型，禁止 `related_to` 这种含糊动词。仓库里未知关系构建期直接 reject / quarantine，不入库；宁可漏抽，不要错抽。Student Core 抽取只接受已审查 annotations，不是让模型自由抽。
5. 二者在 schema 里是同一 `PRODUCT` 的别名，必须并成一个节点。对齐失败会把同一实体切成多个节点，多跳路径在「问题 → 症状 → 方案」中间断开，召回看起来有边、推理走不通。
6. 模糊分 0.90：自动合并线是 0.96，送审线是 0.88。0.90 落在模糊带但够不上 unique_fuzzy，仓库送 **quarantine 隔离**，不强制合并，更不交给 LLM 判断。图废掉的最快方式就是把两个不同实体合成一个——这是 ADR-0013 的硬决策；仓库没有 embedding / LLM 对齐漏斗。
7. Local 解「一个问题及其直接症状/方案」，种子实体 **1 hop**；Global 解跨文档共性/分布，查预计算社区摘要；Multi-hop 解显式关系链，有界递归 **最多 3 hop**；DRIFT 是 local 路径 ∪ global 社区的一次查询，不是第三种独立图。Local 是已知锚点的直接邻居，1 hop 足够；多跳才需要有界遍历，再长会撑爆上下文、LLM 失焦。
8. 分类器阈值 0.70，吃不准必须回 hybrid。低置信时「试试图也好」会把 FAQ 拖进贵路径，加噪加钱还可能 500。无图证据 / release 非 active / 运行时异常同样降级 hybrid，并记下 `fallback_reason`，默认模式始终是 hybrid。
9. LLM 不会读 `{src, edge, tgt}` JSON，召回再准生成也会稀烂。口令：能用文本就别用 JSON。路径 → 句子服务 Multi-hop；子图 → 结构文本服务 Local；社区 → 摘要块服务 Global。仓库硬截断 6000 字符，citation 只从已持久化 evidence 组装。
10. 图给线索（结构），原文给凭证（可引用）。合规上证据永远比线索重要：只返回路径、不带 `evidence_ids` / chunk citation，客户问「凭什么」答不上，审计也站不住。双链分别守：chunk 链（`citations` / `evidence_ids`）和 图链（`retrieval_mode` + `graph_debug.paths` / communities），外加 `trace_id` / `release_id` / `graph_release_id`。
11. 不能全量开。总体 faithfulness +0.02、成本 ×5 会骗人：简单题图可能更差，归纳题图好一大截，一平均略涨。真正该算的是主场题型收益 × 占比 − 额外成本，> 0 才上，而且必须按题型 A/B。`factual` 的 routing_policy 写死 `hybrid`，是「FAQ 不要上图」在评测层的落实——即使图质量更高也不改。
12. 旧的 graph citation **不会**跟着变。`graph_evidence_projection` 把 `page_no` / `section_path` / `bbox` / `doc_version` 按该 graph release 冻结，防止后来 chunk 更新把旧图证据悄悄改写。上游换版应出新的 graph release，禁止原地改图。

---

## 11. 一句话收口

Week13 不是「给 RAG 换一个更强的检索器」，而是给整门课补上 **关系层这个派生控制面**：该上场时（归纳 / 多跳 / 交叉验证 / 时序）用有界的图证据说话，不该上场时（FAQ / 定义）老老实实走 Week08 hybrid——图的质量、成本、版本和回滚，全部接在已经建好的契约、评测和 release 轨道上。
