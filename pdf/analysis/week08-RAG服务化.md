# Week 08 · RAG 服务化：从「搜得到」到「答得稳」

> **一句话**：把 Week07 的可引用文档资产，组装成一条可上线、可回滚、可审计的生产级 RAG 服务——检索靠 Hybrid + Rerank，输出靠 Schema + Citations，运维靠 Prompt as Code + release_id。
>
> 讲义：`pdf/doc/Week08-RAG服务化.pdf`（56 页 / 5 课时）

---

## 0. 本周主干

五节课是一条从「召回」到「上线」的装配线，每一节都在给上一节的产出加约束：

```
Week07 evidence-ready chunks
  ↓ L01 Retrieve    Query 理解（改写/HyDE/路由）→ Dense + BM25 → RRF   「召得到」
  ↓ L02 Rerank      50 候选 → Cross / ColBERT / LLM → 5 精排 + 阈值    「排得对」
  ↓ L03 Generate    JSON 契约 + Citations + Context 剪枝               「说得清」
  ↓ L04 Prompt+Eval Git + 模板 + Golden set + Canary + Bad Case        「改得动」
  ↓ L05 Release     release_id 原子绑定 4 件套 + Cost                  「回得去」
  → Week11 全量评测 / Week12 追踪与 Bad Case / Week14 发布治理
```

讲义反复用「三件套」组织结论，这套记忆法值得单独记：

| 三件套 | 内容 | 解决什么 |
|---|---|---|
| **召回三件套** | Hybrid (Dense + BM25 + RRF) + Reranker + Contextual Retrieval | 召不回 / 排不对 |
| **输出三件套** | Structured Outputs + Citations + Confidence Score | 无法解析 / 无法追溯 |
| **省钱三件套** | Prompt Cache + Router + Reranker（合计省 65-75%） | 账单爆炸 |
| **上线铁律** | release_id + Canary + 秒级回滚 | 事故找不回上一版 |

另一条贯穿全周的主线是**漏斗**：100 万 chunk → Hybrid 召 50 → Rerank 精排 5 → 阈值过滤 → 干净生成。每一阶段筛掉 95-99%，但不丢分数。

---

## 1. L01 · Retrieve：Query 理解 + 混合检索

### 为什么纯向量必坏

开场案例：客户问「订单号 N-1234-AB 的退款流程」，纯向量召回的全是「退款/流程/客服」的语义近邻，正确订单没进 top-50。不是模型笨，是**字符精确匹配场景向量天然干不过 BM25**。而生产里 30-50% 的 query 都带编号、代码或错误码。

### 检索策略适用场景对比（本节最重要的表）

| 场景 | 纯向量 Dense | 纯 BM25 Sparse | 谁该赢 |
|---|---|---|---|
| 专有名词 / 订单号 / 编号 | 召不回（语义近邻干扰） | 字面匹配精确 | Sparse |
| 代码 / 标识符 / 错误码 | 几乎完全失效 | 必杀 | **Sparse（极高）** |
| 同义改写 / 概念相近 | 召得到 | 字面不匹配 | Dense |
| 长尾语义 / 推理问题 | 优势 | 关键词不全 | Dense |
| 短 query（1-3 字） | 差（向量噪声大） | 中（频率倒数） | Sparse 略优 |
| 多语言 / 跨语种 | 跨语种可召回 | 死锁在原语言 | Dense |

四种策略的选型阶梯（NDCG@10，纯向量 = 基线 100）：

| 策略 | 机制 | 分数 | 代价 | 适用 |
|---|---|---|---|---|
| **Dense** 纯向量 | embedding 相似度 | 100 | 专有名词死 | 对话 / 长尾问题 |
| **Sparse** BM25 / SPLADE | 词频 + 倒文档频率 | 85-95 | 同义词失效 | 专有名词 / 代码 |
| **Hybrid** Dense + BM25 + RRF | 两路并发 + 排名融合 | 115-135 | 索引双份 | **90% 生产场景（默认）** |
| **Hybrid + Rerank** 二阶 | 召 50 → 精排 5 | 140-160 | 贵 + 慢 | 高质量要求场景 |

### RRF：为什么这样设计

公式只有一行：`RRF(d) = Σ_i 1 / (k + rank_i(d))`，k 默认 60，各路检索结果按排名累加后重排。三个设计问题的答案比公式本身重要：

| 问题 | 答案 |
|---|---|
| 为什么 k=60 | Cormack 2009 原始论文实验值；30-100 之间影响很小，别调 |
| 为什么不归一化分数 | Cosine 是 0-1，BM25 可以 50+，尺度差太大；**排名是天然归一化** |
| 为什么不用加权求和 | 需要先归一化（选错就翻车），权重 α/β 是超参数，每个数据集都得重调，不可移植 |

结论：RRF 是「无脑用」的稳定选择，实在不够再上 learned fusion。

### Query 理解层：改写比换向量库便宜 100 倍

真实案例：Hybrid + Cohere Rerank 都堆上了，recall@5 仍然只有 62%。加一层 LLM query rewrite 后跳到 84%，**没换任何检索组件**。根因是用户写「那个上周买的多少钱」，embedding 不知道指哪个 SKU。

四件套及其边界：

| 手段 | 做什么 | 效果 | 场景 | 什么时候**不要**用 |
|---|---|---|---|---|
| ① Query Rewrite | 模糊 → 明确，替代词补约束 | recall 大幅提升 | 对话型 RAG 标配 | 简单关键词（SKU / 编号），已够精确纯浪费 token |
| ② Decomposition | 复合 → 子问 | 拆 multi-fact | Agent 知识库 | 单事实 query |
| ③ HyDE | 让 LLM 先假想答案再 embed | recall +10-20% | 垂直专业领域、query 短而模糊 | **短事实 query**，LLM 假想答案误导性强 |
| ④ Query Router | 判类型分流 | 省钱兜底 | Adaptive RAG 入口 | 单一 query 类型的窄场景 |

顺序判断：**Query Understanding 必须在 Hybrid 之前**。

### Adaptive RAG 路由表

| Query 类型 | 样例 | 路由到 | Latency / Cost | 占比 |
|---|---|---|---|---|
| 简单事实 | "产品 X 价格" | Naive Hybrid RAG | P50 600ms / $0.002 | 60-80% |
| 多步推理 / 多跳 | "客户 X 去年订单 + 退货"<br>"X 公司 CEO 的母校" | Agentic / Iterative RAG | 3-10s / $0.02-0.03 | 13-23% |
| 关系问题 | "A 公司高管之间关系" | Graph RAG | 1-3s / $0.005 | 3-5% |
| 数值计算 | "上季度 GMV 同比" | SQL / Code Interpreter | 1-2s / $0.008 | 2-5% |
| 闲聊 / OOD | "你是谁" | 直接 LLM，不检索 | P50 400ms / $0.001 | 5-10% |

核心判断：**2026 的答案不是「全用 Agentic RAG」，是「Classifier + Multi-Path 路由」**。Classifier 跑一次 < $0.0001，ROI > 50x；Agentic 的代价是 latency 3-10x、token 5-20x。

向量库选型一句话：< 1M chunk 用 pgvector，1M-10M 用 Qdrant / Weaviate，10M+ 上 Milvus / Pinecone，已有 ES 集群就复用 ES。**90% 中小项目 pgvector 够用，别一上来就 Milvus。**

---

## 2. L02 · Rerank：三大门派与质量门禁

### 重排是门禁，不是锦上添花

反面案例：为了召回率把 top-k 调到 50 直接拼 prompt 喂 GPT-4，月账单 $40K，客户还抱怨答非所问。根因是 top-50 里只有 3 条真相关，其余 47 条在**干扰 LLM 注意力**。上 Reranker 前后（讲义给的项目实测）：

| 指标 | Hybrid 50 直喂 LLM | Hybrid 50 + Rerank → 5 | 改善 |
|---|---|---|---|
| 每 query token / 成本 | ~30K / $0.15 | ~3K / $0.015 | -90% |
| 答案准确率 | 约 68% | 约 91% | +34% |
| 幻觉率（LLM-judge） | 约 18% | 约 6% | -67% |
| 延迟 P95 | 4.2s | 2.8s | -33% |

注意**延迟也降了**——context 短了，生成更快。这打破了「加一阶必然更慢」的直觉。

### Bi-encoder vs Cross-encoder

不是同一类模型的两种用法，是**结构差异导致的精度/速度权衡**：

| | Bi-encoder（粗排） | Cross-encoder（精排） |
|---|---|---|
| 结构 | query → vec_q，doc → vec_d，`cosine(vec_q, vec_d)` | `(query + doc) → enc → score`，内部 attention 充分交互 |
| 预计算 | doc 可预先 embed 入库，O(1) 检索 | 每对独立计算，O(N)，不能预计算 |
| 速度 | 毫秒级查 100 万 | 比 bi-encoder 慢 100-1000 倍 |
| 代价 / 收益 | query 与 doc 不交互，匹配粗 | 排序质量天花板 |

### 三大门派全景（2026 的关键更新）

以前认为「Reranker = Cross-Encoder」，现在是三个阵营：

| 门派 | 代表 | 机制 | 延迟 | 精度（BEIR 相对） | 存储 | 场景 |
|---|---|---|---|---|---|---|
| **Cross-Encoder** | Cohere 3.5 / BGE v2-m3 | query + doc 拼接 encode | 20-100 doc 约 200-500ms | baseline +15% | 不存 | 生产 RAG 默认 |
| **ColBERT（Late-Interaction）** | ColBERTv2 / PLAID / Vespa | query/doc 各保留 token 级 vec，MaxSim 打分 | 50-150ms（比 Cross 快 5-10x） | baseline +12% | ~100 vec/doc（压缩后） | 超大库（1B+）在线精排 |
| **LLM-as-Rerank** | GPT-4o / RankGPT | 让 LLM 直接打分排序 | 1-3s | baseline +10-18%（20 doc 内 SOTA） | 不存 | Top 高价值 query 兜底 |

ColBERT 的定位一句话说清：**Bi-encoder 太弱、Cross-Encoder 太慢，ColBERT 是中间最优解**——doc 的 token 级向量可预存，在线只算 query。代价是存储 5-10x 且需要 GPU。

生产推荐组合：Cross-Encoder（Cohere/BGE）打底 + LLM Rerank 对 Top-5 二次过滤，recall 与 precision 双高。选型不用纠结：商业 API 用 Cohere Rerank 3.5（$2/1K queries，100+ 语言），自托管用 BGE Reranker v2-m3（568M，中英双语），垂直领域看 Voyage Rerank-2。**候选不要超过 3 个。**

### Two-stage 漏斗与阈值

`Index 100 万+ → Hybrid 50 候选 → Rerank 5 精排 → 阈值过滤 (score > 0.3) → Generate`。阈值这一步最常被漏掉：`score < 0.3` 的 chunk 大概率是「召回但无关」，剔除后 LLM 的注意力才能集中。

### 五个反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 不上 reranker，top-50 直喂 LLM | token 炸 / 准确率塌 | 强制二阶 retrieval |
| 用 GPT-4o 干 Cross-encoder 的活 | 贵 100 倍 / 慢 10 倍 | 用专门 Cross-encoder |
| top-N 过大，rerank 后还留 20+ | LLM 注意力分散 | top-N = 3-5 |
| 没有阈值过滤，score 0.1 也收 | 低分干扰 LLM | score < 0.3 剔除 |
| 只用排序不存 rerank_score | 前端无法展示置信度 | rerank_score 必入 evidence |

另外，"X 公司 CEO 的母校在哪"这类问题单轮检索必死，需要 **Multi-Hop**：检索 → Rerank → 让 LLM 判断「证据够不够答」→ 不够就生成 sub-query 再 hop。实现三派是 Agentic RAG (LangGraph) / Graph RAG (图遍历) / Iterative RAG (显式 N 轮)。代价是 latency 5-10x、token 3-5x，所以 `max_hops` 必须兜底防爆炸，且只让复杂 query 走。

---

## 3. L03 · Generate：受约束生成与 Context Engineering

### 输出不是字符串，是 JSON 契约

Demo 关心「答得对不对」，生产关心「凭什么这么答」，分水岭在 schema。客户会问三个 Demo 答不出的问题：这答案从哪来的？让我看下原文？换个语言问为什么结果不同？四大约束：

| 约束 | 机制 | 代表实现 | 适用 |
|---|---|---|---|
| **Schema** 结构化 | JSON Schema 强约束，token 100% 合规 | OpenAI Structured Outputs / Pydantic / Outlines | 所有生产 RAG |
| **Citations** 引用证据 | 字符级 / 段落级精度，`cited_text` 直接用 | Anthropic Citations API（2025.1 GA），幻觉率 -50% | To B / 合规场景 |
| **Tool Use** 函数调用 | 约束输出 = 约束行为 | Function Calling | Agent 场景 |
| **Confidence** 置信度 | 每条 evidence 带 score，阈值过滤 + 可视化 | self-consistency / LLM-as-judge | 风险场景 |

工业默认：Structured Outputs + Citations API 是 2025 标配，另外两个按场景上。

### RAGAnswer 契约的字段分组

讲义的 schema 分三组，每组各有明确消费方：**答案组**（`answer` / `evidences[]` / `overall_confidence`）给前端渲染高亮；**审计组**（`release_id` / `parsed_at` / `model_version` / `retrieval_stage` / `prompt_version`）给 Week14 治理、调参和评测；**兜底组**（`fallback_action` = `ask_human` / `say_unknown`）保证 confidence < 0.3 时不让 LLM 硬编。

`evidences` 必须是数组而不是单个——复杂问题需要多源证据。每条 evidence 的锚点字段（`doc_version` / `page_no` / `bbox` / `section_path` / `cited_text`）直接继承 Week07 L03。

### Context Engineering：喂什么比选什么模型更重要

Claude / GPT 都上到 1M context，但实测 > 100k 后开始 lost in the middle。**同样 20 条 evidence，放最前/最后 vs 平均散布，答对率差 12-18%**。这不是 bug，是 attention 概率分布的物理规律。

所以目标不是「塞越多越好」，是让最相关的 5-10 个 chunk 出现在最显眼位置，结构最清晰。讲义给的 XML 标签法则：`<system>` → `<knowledge>`（reranker top-1 放最前，每个 chunk 带 source/page/score）→ `<history>` → `<query>`（**query 放最末位**）。

### Context Pruning 六策略

| 策略 | 机制 | Cost 降幅 | 延迟代价 | 适用 |
|---|---|---|---|---|
| **Top-K 截断** | rerank 后只取 top-5 | 50-70% | 0 | 默认 |
| **Token Budget** | 按分排序到 token 上限 | 50-70% | 0 | chunk 长度差异大 |
| LLM Compression / LongLLMLingua | mini 模型针对 query 压缩 / 快速删冗余 token | 40-70% | +50-500ms | 高质量场景 / 大批量低延迟 |
| Selective Citation | 只保留有 cite 标注的 chunk | 30-50% | 0 | 配合 Citations API |
| Hierarchical Summary | 长文档先摘要再注入 | 60-80% | +1-2s（一次性） | 单 doc > 10k token |

选型顺序：先 Top-K，再 Token Budget，顶到极限上 LongLLMLingua，Compression 仅高价值场景。

### Prompt Caching 的计价逻辑

Anthropic 是 cache write 1.25x 正常价、**cache read 0.1x（便宜 10 倍）**，TTL 默认 5 min（可选 1 hour）；OpenAI 自动缓存无需标记，TTL 5-60 min。生产规则：**system prompt + skills 缓存，检索结果不缓存**（每次都变，缓存无意义还污染前缀）。hit rate 80%+ 可达，token 成本降到 1/3-1/5。

### 五个反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 只输出字符串 | 前端/审计都做不了 | 强制 RAGAnswer schema |
| Prompt 里求 JSON | 5-10% schema 错，上线翻车 | Structured Outputs API |
| Citations 靠 prompt 拼 | LLM 编引用 / 张冠李戴 | Citations 由 retrieval metadata 生成 |
| 没有 confidence | 低质量证据一视同仁 | score + 阈值过滤 |
| 没有 fallback | 低置信度也硬答 | confidence < 0.3 → ask_human |

---

## 4. L04 · Prompt as Code 与三层评测

### 四大支柱，少一个都不算工程化

开场事故：prompt hardcode 在 `.py`，工程师周五改了一句「请按 JSON 输出」的语序就上线，周六排查 4 小时。

| 支柱 | 内容 | 决定什么 |
|---|---|---|
| **Versioned** | Git 管理模板文件，semver，每次改动过 PR + Review，`prompt_id + version` 入 evidence | 能不能回退 / 追责 |
| **Templated** | Jinja2 等模板引擎，业务变量从代码注入，prompt 里不写硬编码值 | 能不能维护 |
| **Tested** | Golden set 50-200 真实样本，CI 跑 Ragas / DeepEval，指标退化阻断 PR | 能不能不翻车 |
| **Released** | canary 5% → 25% → 100%，指标自动监控 + 一键回滚 | 能不能 24×7 运维 |

工具选型：10 人以下团队自研（Git + 模板 + CI，占 70%），30 人+ 上 Phoenix（开源）或 LangSmith（商业）。

### Canary 的三个自动回滚阈值

本节最可操作的产出：Faithfulness 退化 > 3% → **立刻回滚**；P95 延迟上升 > 20% → **立刻回滚**；Cost 上升 > 30% → 告警。

### Eval 三层金字塔

| 层 | 问什么 | 核心指标 | 上线门槛 | 跑多频 |
|---|---|---|---|---|
| **L1 检索质量** | Reranker 排没排对 | Recall@K / MRR / NDCG / context_precision | Recall@5 ≥ 80% | 每次 PR，全量 |
| **L2 端到端** | 答案对不对 | Faithfulness / Answer Correctness / Citation Acc | Faithfulness ≥ 0.85 | 每天，全量 |
| **L3 业务效果** | 用户满意吗 | CSAT / 转化率 / Deflection 率 | CSAT ≥ 4.2/5 | 持续在线 |

Eval set 建设：200-500 真实样本 + 专家标注，Synthetic 起步长期换真，每季度更新。**80% 团队上线后才补 Eval，其实 Day 1 就该建。**

### LLM-as-Judge 的三条纪律

**judge 比生产强一档**（生产 Sonnet → judge Opus）；**拆 atomic claim**（把答案拆成 N 条独立断言，每条判 `supported / partial / unsupported / irrelevant` 并标 `evidence_chunk_id`，`faithfulness_score = supported / total`）；**每条跑 3 次取均**（LLM 输出有方差，σ < 0.05 才可信）。

### Bad Case 库：上线后最重要的资产

产品里加 thumbs down，任何 down 自动入库，每周专家 review 50-100 条。四类标签直接对应四个修法：

| category | 含义 | 修哪里 |
|---|---|---|
| `retrieval_miss` | 没召回到正确 chunk | 修 Hybrid / Query Rewrite |
| `rerank_wrong` | 召回对了但排错 | 调 reranker / 加 LLM judge |
| `hallucination` | context 对了但答案乱编 | 加 Citations / 紧 Schema |
| `knowledge_gap` | 知识库根本没这内容 | 补数据 / 标 fallback |

关键点：bad case 比 golden set 更有信号，因为它是真实用户痛点的快照。每次 prompt / model 大改前全量跑，看新版本是否退步。

### Drift 三个监控点

漂移不是 if，是 when。

| 监控点 | 指标 | 阈值 | 修法 |
|---|---|---|---|
| Embedding 漂移 | KL divergence / MMD（新数据 vs 老索引） | > 0.15 告警 | re-embed 增量数据 |
| Retrieval 漂移 | Recall@5 周环比 | 下降 > 3% 告警 | 扩 golden set，重训 |
| Answer 漂移 | Faithfulness / CSAT 周环比 | Faith < 0.85 告警 | 回滚 release_id |

---

## 5. L05 · Release：原子绑定与秒级回滚

### 事故的真正根因

团队周五上线，周六客户说「同样问题答得跟上周完全不一样」，排查 6 小时才搞清是改了 prompt、换了索引，还是切了模型。根因不是日志差，是**没有一个 ID 把这四件事绑在一起**。

### 原子绑定 4 件套

RAG 服务有四个独立可变的部分，任何一个变了答案行为就会变；各自独立部署，排查事故只能猜。四件套是：**索引**（embedding 模型 / 切片版本 / vector db `snapshot_id`）、**Prompt**（`prompt_id` + `version`，L04 的输出）、**模型**（精确到 build，含 fallback / rerank / embedder）、**Eval**（golden set 跑分快照：faithfulness / context_precision / citation_accuracy）。

`release.yaml` 的关键字段设计：`release_id` 是主键，`status` 走 `canary → active → archived` 流转，`rollout.canary_percent` 控灰度，`rollout.rollback_to` 指向上一版。

### 秒级回滚 = 切指针

回滚不是 `git revert` + 重启 docker，而是改 `ACTIVE_RELEASE` 这一个变量。请求进来时 `load_release()` 读到的 release 明确指向哪个索引、哪个 prompt、哪个模型；答案返回时带上 `release_id`。

**不需要改代码、不需要重新构建镜像、不需要重新跑 CI。** 这就是 `release.yaml` 设计的核心目的：事故响应从 6 小时变 30 秒。

### 灰度的四个分流维度

按 **tenant**（5% 租户先用新版，出问题不影响所有客户）、按 **user 哈希**（20% 用户固定到新版，可监控 cohort 指标）、按 **query 类型**（FAQ 类用 v2.0，订单类留 v1.5，风险隔离）、按 **时段**（低峰期上新版，高峰期回稳定版）。

### Cost Engineering

按 10 万 query/月，无优化 $48K → 全套优化 $9K（-81%）：

| 手段 | Cost 降幅 | 副作用 | 上线难度 |
|---|---|---|---|
| **Prompt Caching** | 60-75% | 冷启动 1.25x 写 | < 1 天 |
| **Reranker 替代硬塞** | context 降 75% | reranker 一次 cost | < 1 天 |
| **Router 便宜模型** | 40-60% | classifier 一次 cost | 2-3 天 |
| Context Pruning | 50-70% | 可能漏关键 chunk | 2-3 天 |
| Embedding 自托管 / 批量化推理 | 1/5 / 50% | 需 GPU 运维 / +24h 时延 | 1 周 / < 1 天 |
| 模型蒸馏 | 80-90% | 需训练 pipeline | 1-2 月 |

前三项就是「省钱三件套」，立刻能省 65-75%，是 ROI 最高组合。

### 五个反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 重启 docker 算回滚 | 事故响应 1 小时起 | release_id 切指针，30 秒 |
| 4 件套独立部署 | 排查事故只能猜 | 原子打包 release.yaml |
| 没 release_id 入审计 | 客户问追溯不到 | release_id 进 response |
| Prompt 改了不重测 | 指标退化才被发现 | CI 强制 Eval 阻断 |
| 不灰度直接全切 | 事故概率 5-10x | 5% → 25% → 100% |

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 索引构建 | `pipelines/indexing/embedder.py`<br>`pipelines/indexing/assets.py`（Dagster） | `build_index()`、`EMBEDDING_DIM` 硬约束、dry-run 分支 |
| L01 Index manifest 与报告 | `pipelines/indexing/index_manifest.py`<br>`pipelines/indexing/reporting.py`<br>`contracts/release/index_manifest.schema.json`<br>`reports/week08/index_build_report.sample.md` | `quality_gate_for()` 的 pass/warn/fail 判定 |
| L01 Hybrid + RRF 真实实现 | `services/rag_api/app/retrieval.py`<br>（兼容层 `pipelines/retrieve/hybrid.py` 只是 re-export） | `vector_search()` / `fts_search()` / `reciprocal_rank_fusion(k=60)` / `hybrid_retrieve()` |
| L01 Query 改写 | `pipelines/query/rewriter.py`（确定性层）<br>`services/rag_api/app/query_rewrite.py`（在线运行时）<br>`services/rag_api/app/prompts/query_rewrite_v1.md` | 保护词处理、recall floor、熔断器；prompt 把 query 当**不可信数据** |
| L01 Adaptive 路由 | `pipelines/query/router.py` | `route_query()` 三条确定性规则 |
| L02 Rerank | `services/rag_api/app/retrieval.py`（`CrossEncoderReranker`）<br>`pipelines/retrieve/rerank.py` | fallback 语义：模型不可用就保留 RRF 排序 |
| L02 Multi-hop | `pipelines/query/multi_hop.py` | `build_multi_hop_plan()` 只返回 plan，不跑循环 |
| L03 生成与剪枝 | `services/rag_api/app/context_pruning.py`<br>`services/rag_api/app/generator.py` | `prune_contexts(max_chunks=5, token_budget=2500)`、`generate_grounded_answer()`、三级降级 |
| L03 Citations 生成 | `services/rag_api/app/routers/rag.py` | `_citation_from_chunk()`——由 router 从 evidence metadata 构造 |
| L03 服务契约 | `contracts/service/rag_request.schema.json` / `rag_response.schema.json` / `citation.schema.json` / `retrieval_debug.schema.json` / `query_rewrite.schema.json`<br>`services/rag_api/app/models/rag_models.py` | response 的 `required` 里那五个 release/trace 字段 |
| L04 Prompt as Code | `services/rag_api/app/prompts/`（`system_v1.md` / `answer_v1.md` / `no_answer_v1.md` / `prompt_manifest.yml`） | 文件化模板 + `prompt_release_id: prompt-week08-v1` |
| L04 契约测试与冒烟评测 | `tests/contract/test_week8_rag_contracts.py` + `tests/contract/fixtures/week08/`<br>`evals/week08/run_smoke_eval.py` + `rag_smoke_cases.yml` | no-answer 也必须带 release ids；六个 case 覆盖 known hit / lexical / 语义改写 / filter / no-answer / 权限 |
| L04 集成测试 | `tests/integration/`：`test_week8_ppt_alignment.py` / `test_week8_hybrid_retrieval.py` / `test_week8_rag_api.py` / `test_week8_index_build.py` / `test_week8_rag_audit.py` / `test_week8_prompt_release.py` / `test_rag_api_smoke.py`<br>改写专项：`test_query_rewrite_production.py` / `test_query_rewrite_eval.py` | 先看 ppt_alignment：讲义提的能力哪些真能跑 |
| L05 审计与 release 字段 | `services/rag_api/app/audit.py`<br>`services/rag_api/app/config.py`<br>`reports/week08/rag_audit_log.sample.jsonl` | `write_rag_audit_log()` 写哪 17 个字段；四个 release id 的默认值 |
| L05 Release manifest 契约 | `contracts/release/release_manifest_schema.json`<br>`release_manifest_v2.schema.json` / `release_manifest_example.json` | schema 已在，rollback 执行器留给 Week14 |
| 本周文档 | `runbooks/week08-rag-engineering.md`<br>`runbooks/query-rewrite-production.md`<br>`docs/blueprints/week08/`（blueprint / scope-boundary / assignment-spec / demo-script / **ppt-alignment-gap-check**） | 先读 gap-check，能省下大量找路径的时间 |

### 代码里值得单独看、讲义没展开的细节

**1. 三路 query 分离，是仓库比讲义更进一步的设计。** 讲义说「改写后拿新 query 去检索」，仓库里 `hybrid_retrieve()` 收三个不同的 query：

```python
vector_query  = semantic_query or query   # 改写/HyDE 后的语义 query → 只进向量检索
keyword_query = lexical_query  or query   # 保留原始词的 query   → 只进 FTS
ranking_query = rerank_query   or query   # 用户原始 query        → 用于 rerank
```

这样改写能扩展语义召回，同时不丢错误码和型号，最终排序还贴着用户原意。讲义里「改写会伤害精确匹配」这个坑，代码是用分离而不是取舍来解的。

**2. 改写的三道安全阀。** `_parse_output()` 里：LLM 输出必须**包含**确定性改写的全部概念，否则把两者拼起来（deterministic 层是召回下限，不是降级备胎）；`remove_invented_protected_terms()` 删掉模型**编造**的标识符（整个 token 删掉，不做模糊纠正）；`preserve_protected_terms()` 补回模型**漏掉**的标识符。保护范围含错误码、CVE、UUID、版本号、`XX-数字` 型编号。

**3. 改写有完整的韧性栈与隐私处理**，讲义一句没提：TTL 缓存（300s / 2048 条）、in-flight 请求合并（同 key 并发只打一次 LLM）、熔断器（5 次失败开路，30s 恢复，half-open 单探针）、超时预算内的指数退避重试（6s / 2 次）。四种模式 `disabled / deterministic / llm / fallback` 全部进 trace 和 audit，`disabled` 就是紧急回滚开关。审计只留哈希：`audit_metadata()` 输出 `original_query_sha256` / `semantic_query_sha256` / 长度 / 计数，契约测试专门断言 `"semantic_query" not in query_rewrite_debug`。

**4. 「BM25」在仓库里其实是 PostgreSQL FTS，而且两路是顺序执行。** 用 `websearch_to_tsquery` + `ts_rank_cd`，做了字段加权（title / section_path / content 为 A，`context_prefix` 为 B）；`_build_fts_query()` 去停用词去重后 OR 拼接**最多 16 个 token**，刻意放宽召回、把精度交给 RRF 和 rerank。并发那一段代码有注释解释：asyncpg 不允许在同一连接上并发操作，而调用方只传进来一个已 acquire 的连接，所以延迟是 sum 而不是讲义宣称的 max。

**5. 漏斗规模是 `top_k * 2`，不是讲义的 50。** 两路各取 `top_k * 2`，rerank 也只对 `merged[:top_k*2]` 打分。默认 `top_k=5` 时实际是「召 10 → 精排 10 → 取 5」。Cross-encoder 默认模型是 `ms-marco-MiniLM-L-6-v2`，加载失败时把 `self._model` 设成哨兵字符串 `"unavailable"`，之后每次 `rerank()` 原样返回 RRF 排序。

**6. 阈值门禁的位置和讲义不同，而且 confidence 的算法很粗糙。** `hybrid_retrieve()` 的 `min_score` 默认 0.0（注释写「过滤在响应层做」），真正门禁在 `generator.py`：`confidence < retrieval_min_score`（默认 **0.6**）就返回 `abstain_reason="low_retrieval_confidence"`，连 LLM 都不调。而 `_estimate_confidence()` 只取 top-1 的 `final_score`（`>1` 时按 `score/0.1` 归一化），RRF 分数量级只有 0.01-0.03（两路都命中 top-1 约 `1/61 × 2 ≈ 0.033`），意味着**关掉 rerank 后 confidence 几乎永远过不了 0.6 门禁**。`routers/query.py` 里还有另一套归一化（`rrf_score * 10`），两处不一致是很好的排查练习。

**7. embedding 维度是硬门禁，且有确定性后门。** `EMBEDDING_DIM = 1536`，provider 输出维度不等于 1536 就整批拒绝写入并记 `dimension mismatch`——不截断也不 padding（Voyage 的 1024 维会直接被拒）。`_deterministic_embedding()` 用 SHA256 生成稳定 1536 维向量，**不是语义模型**，唯一目的是让没有 API key 的 Docker 环境把全链路跑通。IVFFlat 索引首次构建后自动创建，`lists = sqrt(chunk 总数)`。

**8. Prompt as Code 是 Markdown + YAML manifest，不是 Jinja2。** `render_evidence_prompt()` 读 `system_v1.md` + `answer_v1.md` 拼成 system/user 两段，`answer_v1.md` 里写死了「不许发明 URL、页码、doc_version、evidence id」和「只能引用下面出现过的来源编号」。结构化输出只对部分 provider 开：`structured = runtime.provider in {"ollama", "openai"}`，schema 只约束一个 `answer` 字段，长度检查放在反序列化之后（理由是保持 provider grammar 可移植）。

**9. 生成失败有三级降级，每级都带 confidence 和 release ids。** 无证据 → `no_answer_v1.md` + `abstain_reason`；置信度不足 → 不调 LLM；LLM 未配置或调用失败 → 返回 top-1 证据摘要 + `generation_mode="deterministic_fallback"`。**abstain 是一等路径，不是异常。**

**10. `filters` 全量进审计，索引 schema 运行时自愈。** filters dict（五个 metadata 过滤 + 三个 release id + tenant_id + retrieval_mode）整体作为 jsonb 写进 `rag_audit_log`，所以「为什么这条 query 召回是空的」可以事后完整复现。`ensure_week08_index_schema()` 用 `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` 就地升级已有的本地 volume，学员不需要重建数据库。

---

## 7. 讲义与仓库对不上的地方

讲义 p56「本周交付物」列的 14 个路径，大部分与仓库实际不符。**别按讲义的路径去找**：

| 讲义写的路径 | 实际情况 |
|---|---|
| `pipelines/retrieve/hybrid.py`<br>`pipelines/retrieve/rerank.py` | 存在，但都只是 re-export 兼容层；真实实现在 `services/rag_api/app/retrieval.py`。rerank 只有 CrossEncoder，**没有 ColBERT，没有 LLM reranker** |
| `pipelines/retrieve/multi_hop.py` | 路径错。实际是 `pipelines/query/multi_hop.py`，且只返回 plan 对象，运行时循环未实现 |
| `pipelines/query/router.py` | 存在，但是确定性规则路由，**不是 LangGraph**，也不做 fact/relation/compute 分流 |
| `services/rag_api/query_rewriter.py`<br>`services/rag_api/models.py`<br>`services/rag_api/context_pruning.py` | 三个都少了 `app/`。实际是 `app/query_rewrite.py`、`app/models/rag_models.py`、`app/context_pruning.py` |
| `services/rag_api/adaptive.py` | 不存在。讲义的 LangGraph `StateGraph` 示例在仓库里没有对应实现 |
| `services/rag_api/llm_call.py` | 不存在。有 `app/llm.py`，但**没有任何 prompt caching 代码**（全仓库搜不到 `cache_control`） |
| `services/rag_api/release.py` | 不存在。release id 从 `app/config.py` 读环境变量，没有 `ACTIVE_RELEASE` 指针切换机制 |
| `prompts/rag_answer/v1.2.3.j2` | 不存在，仓库根本没有 `prompts/` 目录，也没用 Jinja2。实际是 `services/rag_api/app/prompts/*.md` + `prompt_manifest.yml` |
| `tests/eval/judge.py` | 不存在，LLM-as-Judge 属于 Week11 |
| `data/bad_cases/*.jsonl` | 不存在，Bad Case 库属于 Week12 |
| `monitoring/drift_detector.py` | 不存在，整个 `monitoring/` 目录都没有 |
| `releases/rag-2025-06-01.yaml` | 不存在。有 `contracts/release/release_manifest_schema.json` 和 `release_manifest_example.json`，但没有 `releases/` 目录 |
| `tests/golden/rag_v1.json` | 不存在。Week08 只有 `evals/week08/rag_smoke_cases.yml`（6 个 case，不是 200 个） |

讲义讲了但仓库刻意没有的能力（`docs/blueprints/week08/ppt-alignment-gap-check.md` 里有官方口径，它同时列出了「课堂上不要说」的四句话）：**Cohere Rerank 3.5** → 只有 `sentence-transformers` CrossEncoder；**Anthropic Citations API** → citation 由 retrieval metadata 生成；**Prompt Caching** → 未实现；**Ragas / DeepEval 完整 Eval** → 只有 smoke eval；**Canary / Feature Flag 执行器** → 只有 release id 和 manifest，没有流量分发。

还有一处**仓库内部**的不一致：`runbooks/week08-rag-engineering.md` 和 `docs/blueprints/week08/week08-rag-blueprint.md` 都引用了架构图 `docs/assets/week08/rag-service-code-architecture.png`，但 `docs/assets/` 目录不存在。看不到图不影响跑命令。

---

## 8. 动手清单

统一走 Docker devbox。

```bash
# 0. 起本地栈
cp infra/env/.env.example infra/env/.env.local
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml up -d --build
curl http://localhost:8000/health   # 应返回四个 release_id

DEVBOX="docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox"

# 1. 契约测试
$DEVBOX pytest tests/contract/ -v

# 2. 索引 dry-run（不写 embedding，只出报告）→ 3. 真正建索引
$DEVBOX python -m pipelines.indexing.embedder \
  --index-release-id index-week08-dev --batch-size 32 --dry-run
$DEVBOX python -m pipelines.indexing.embedder \
  --index-release-id index-week08-dev --batch-size 32

# 4. 冒烟评测
$DEVBOX python evals/week08/run_smoke_eval.py

# 5. 调 RAG API（四个 header 都必需）
curl -X POST http://localhost:8000/rag/answer \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: dev-internal-token-change-in-prod" \
  -H "X-Actor-ID: instructor-local" -H "X-Actor-Role: instructor" \
  -H "X-Tenant-ID: course-legacy" \
  -d '{"question":"How do I recover an Edge Gateway after firmware upgrade failure?",
       "product_line":"edge-gateway","top_k":5,
       "index_release_id":"index-week08-dev",
       "prompt_release_id":"prompt-week08-v1","include_debug":true}'
```

**验收标准不是「跑过了」，而是能回答这五个问题**：

1. `include_debug=true` 的响应里，同一个 chunk 的 `vector_score` / `fts_score` / `rrf_score` / `rerank_score` 分别是多少？哪一路把它捞上来的？
2. `retrieval_debug.mode` 是 `hybrid_rrf` 还是 `hybrid_rrf_rerank`？`rerank_fallback` 是 true 吗？为什么？
3. `query_rewrite_debug.mode` 是四种模式里的哪一种？如果是 `fallback`，`fallback_reason` 说了什么？
4. 每条 citation 的 `page_no` / `section_path` / `doc_version` 是从哪来的？为什么 LLM 不可能编造它们？
5. `abstain_reason` 出现时是 `no_retrieval_results` 还是 `low_retrieval_confidence`？索引报告的 `quality_gate` 又是 pass / warn / fail，差在哪？

**加分练习**（真正检验理解）：

- 对同一个问题分别跑只向量、只 FTS、Hybrid RRF 三次，对比 top-5。**必须构造一个带错误码的 query**（比如 `EG-BOOT-004`），你会看到纯向量把它彻底丢掉。
- 卸掉 `sentence-transformers` 或改一个不存在的模型名，确认 API **不报 500 而是回退 RRF**，且 `rerank_fallback=true`。「fallback 不失败」是本周的核心工程要求。
- 把 `query_rewrite_strategy` 依次设成 `llm` / `deterministic` / `disabled`，看同一个 query 的 `semantic_query_sha256` 和召回结果怎么变——这是紧急回滚开关的演练。
- 用一个输出维度不是 1536 的 embedding provider 跑索引，确认它被**拒绝**并在报告里写了 dimension mismatch，而不是静默截断。
- 追一下第 6 条代码细节里 confidence 的算术：算出 RRF 分数量级，解释为什么关掉 rerank 后请求容易 abstain。

### 动手清单参考答案

先自己答完上面的验收问题和加分练习，再往下对。

本周动手清单 curl 的是产品契约 `POST /rag/answer`（四个 header 必需）。课堂短链路是 `POST /api/v1/query`，两条共用 `retrieval.py` / `generator.py`，**不要写反**：Week01 的 `/api/v1/query` 不是本周这条验收 curl，`/rag/answer` 也不是 Week01 的 classroom query。

1. `include_debug=true` 时同一 chunk 四路分：`vector_score` 来自 dense，`fts_score` 来自 PostgreSQL FTS，`rrf_score` 是排名融合（量级约 0.01–0.03），`rerank_score` 是 cross-encoder。哪一路捞上来看谁非空、谁先进入 merged。带错误码的 query 往往只有 `fts_score`。
2. 模型加载成功 → `retrieval_debug.mode=hybrid_rrf_rerank` 且 `rerank_fallback=false`；`sentence-transformers` 不可用或模型名无效 → `hybrid_rrf` 且 `rerank_fallback=true`，**不报 500**。课堂环境常见后者。
3. `query_rewrite_debug.mode` 四选一：`disabled` / `deterministic` / `llm` / `fallback`。没密钥或熔断时走 `fallback`，`fallback_reason` 会写 LLM 不可用 / 超时 / 熔断开路。`disabled` 就是紧急回滚开关。
4. 每条 citation 的 `page_no` / `section_path` / `doc_version` 来自 Week07 evidence metadata，由 `/rag/answer` 的 `_citation_from_chunk()` 从检索结果构造，prompt 写死「不许发明 URL、页码、doc_version」。LLM 看不到编造通道。
5. `no_retrieval_results` = 召回空，去查索引 / filter / 改写；`low_retrieval_confidence` = 有候选但 `confidence < retrieval_min_score`（默认 0.6），去查 rerank 是否 fallback、以及 RRF 量级能不能当置信度。索引报告的 `quality_gate` 是建索引门禁（pass/warn/fail），和单次请求的 abstain 不是同一层。

加分练习：`EG-BOOT-004` 这类错误码，纯向量会丢掉、FTS 能捞到、Hybrid+RRF 能排上。卸掉 cross-encoder 后 `/rag/answer` 回退 RRF 且 `rerank_fallback=true`。三种 `query_rewrite_strategy` 会改变 `semantic_query_sha256` 和向量路召回，lexical 路仍贴原词。非 1536 维 embedding 被整批拒绝并记 dimension mismatch。RRF 两路都命中 top-1 约 `1/61×2≈0.033`，过不了 0.6，关掉 rerank 后请求容易 `low_retrieval_confidence` abstain。

---

## 9. 易错点与边界

**概念层面**

- **RRF ≠ 加权求和。** 加权求和必须归一化 + 调超参，换数据集就得重调；RRF 只看排名，跨数据集稳定，也不需要权重。
- **BM25 ≠ PostgreSQL FTS。** 都是 sparse 检索，但打分公式不同。仓库用的是后者。
- **Bi-encoder ≠ Cross-encoder 的快速版。** 是结构差异：一个 doc 可预计算，一个必须 pair 一起进模型。
- **rerank_score ≠ rrf_score。** 前者是 cross-encoder 的绝对相关性分（可设阈值），后者是排名倒数和（量级只有 0.01-0.03，不能当置信度用）。
- **HyDE ≠ Query Rewrite。** 改写产出的还是 query，HyDE 产出的是**假想文档**，只用来做 embedding；短事实 query 上 HyDE 会因假想答案的误导性而变差。
- **Adaptive RAG ≠ 全用 Agentic RAG。** 是「classifier + 多路径」，让 80% 的简单 query 走便宜路径。
- **Citations ≠ 让 LLM 说出来源。** citation 必须由 retrieval evidence metadata 生成；prompt 里求 LLM 给引用就是给幻觉引用留后门。
- **abstain ≠ error。** no-answer 是一等返回路径，带 `abstain_reason` 和完整 release ids，HTTP 状态仍是 200。
- **三个 release id 各管一段**：`data_release_id` 管 Week07 的 chunk 批次，`index_release_id` 管本次 embedding 版本，`prompt_release_id` 管模板版本。只回滚一个不等于回滚了行为。
- **回滚 ≠ 重启服务。** 回滚是切指针；重启只是把同一个版本再跑一遍。

**范围边界（Week08 到底做到哪）**

Week08 交付的是**生产 RAG 的最小可用控制面**：可版本化索引、Hybrid + RRF、可回退的 rerank、契约化响应、evidence 派生的 citation、release ids、审计日志、smoke eval。

刻意留给后面的：Week10 的 ticket action / HITL 与 tool 调用；Week11 的完整 eval harness、LLM-as-Judge、Ragas 回归；Week12 的完整 tracing、Bad Case 库、Drift Detection；Week13 的 GraphRAG（代码里已有 `graph_*` 接口位，但那是 Week13 的内容）；Week14 的 release manifest 治理、rollback 执行器、Canary 流量分发。

也明确不做的：不引入外部向量数据库作为 Student Core，不重写 Week07 的 parse/chunk/evidence 主逻辑，不允许 generator 临时发明 citation。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 用户问「订单号 N-1234-AB 的退款流程」，纯向量为什么会召不回？把这个失败归到 Dense 的哪一类天然短板上。
2. RRF 为什么不需要分数归一化？如果换成「0.7 × cosine + 0.3 × BM25」，会引入哪两个新的工程问题？`k` 从 60 改成 6 或 600，排序会怎么变？
3. 什么情况下应该上 HyDE，什么情况下上了会更差？给出判断依据，而不是「垂直领域就上」。
4. Cross-Encoder、ColBERT、LLM-as-Rerank：如果库有 10 亿 doc 且要求 P95 < 200ms，选哪个？另外两个为什么不行？
5. 上了 reranker 之后延迟反而下降了，这跟「多加一阶必然更慢」矛盾吗？解释机制。
6. 为什么 citation 必须由 retrieval metadata 生成？举一个「LLM 输出的引用看起来完全合法但是错的」场景。
7. 仓库把一个 query 拆成 semantic / lexical / rerank 三路。如果只用改写后的 semantic query 打全链路，会具体损失什么？
8. `abstain_reason` 是 `no_retrieval_results` 和 `low_retrieval_confidence` 时，你分别该去改哪个环节？
9. Prompt Caching 为什么只缓存 system prompt 而不缓存检索结果？如果把检索结果也标上 cache_control 会发生什么？
10. release_id 绑定的四件套里，如果只做到了「索引 + prompt」两件，事故排查会在哪一步卡住？
11. Canary 的三个自动阈值（faithfulness -3% / P95 +20% / cost +30%）中，为什么 cost 只告警不回滚？
12. Bad case 库的四类标签，为什么比「答错了」一个标签有价值？Week08 的 smoke eval 和 Week11 的完整 eval 差别又在哪？

### 自测题参考答案

先自己答完上面的题，再往下对。

1. 订单号是字符精确匹配。Dense 的短板是专有名词 / 编号：语义近邻全是「退款/流程」，正确订单进不了 top-50。不是模型笨，是向量干不过 BM25/FTS。
2. Cosine 是 0–1，BM25 可以 50+，尺度不可比；**排名是天然归一化**。换成 `0.7×cosine + 0.3×BM25` 要先归一化（选错就翻车），α/β 还得每个数据集重调。`k` 改成 6 会放大 rank 差，改成 600 各路贡献趋于平坦，30–100 之间影响很小。
3. HyDE 适合垂直专业、query 短而模糊（先假想文档再 embed）。短事实 query 上了会更差：LLM 假想答案误导性强。判断依据是 query 类型，不是「垂直领域就上」。
4. 10 亿 doc 且 P95 < 200ms 选 **ColBERT**（token 向量可预存，在线 50–150ms）。Cross-Encoder 是 O(N) 太慢；LLM-as-Rerank 1–3s 更不可能。
5. 不矛盾。rerank 把 50 砍到 5，context 短了生成更快，总延迟下降。加一阶筛的是噪声，不是在更长的 prompt 上再跑一轮。
6. citation 必须由 retrieval metadata 生成，prompt 求 LLM 给来源就是给幻觉留后门。合法但错的场景：模型输出「手册 p12」且格式完全合规，实际命中的是 p3 另一段。
7. 三路分离：semantic 只进向量、lexical 只进 FTS、rerank 贴用户原词。全用改写后的 semantic，会丢掉错误码 / 型号的精确匹配，最终排序也偏离原意。
8. `no_retrieval_results` → 改索引 / Hybrid / Query Rewrite / filters。`low_retrieval_confidence` → 看 0.6 阈值、rerank 是否 fallback、以及有没有把 RRF 量级误当置信度。
9. 检索结果每次都变，缓存无意义还污染前缀，会把旧证据当成新 query 的命中。只缓存稳定的 system prompt + skills。
10. 四件套是索引 / Prompt / 模型 / Eval。只绑索引 + prompt，事故时分不清是换了模型还是 eval 口径变了，只能猜。
11. cost +30% 可能是合理换了更强模型；Faithfulness -3% 和 P95 +20% 直接伤用户，必须立刻回滚。cost 只告警，让人审，不自动切指针。
12. 四类标签指向四个修法：`retrieval_miss` 修 Hybrid/改写，`rerank_wrong` 调 reranker，`hallucination` 加 Citations/Schema，`knowledge_gap` 补数据或 fallback。Week08 smoke 只有 6 个 case 护契约形状；Week11 才是 200+ golden + LLM-as-Judge / Ragas。

---

## 11. 一句话收口

Week08 是整门课的**服务化转折点**：前七周攒下的数据资产（契约、批次、chunk、证据锚点）在这一周第一次被组装成一个对外的接口，并且从第一天就带上了 release id、citation 和审计日志。后面的 Agent（Week09-10）、评测（Week11）、可观测（Week12）、治理（Week14）全都挂在这一周定下的响应契约上——契约字段设计得越干净，后面每一周省的力气越多。
