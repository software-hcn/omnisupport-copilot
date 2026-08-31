# Week 07 · 非结构化数据工厂

> **一句话**：把 PDF / 网页 / 图 / 音 / 视频从"一堆字符串"变成"带证据锚点、过得了质量门禁、Week08 敢直接索引的 chunk"——五节课其实是同一条流水线上的五道工序。
>
> 讲义：`pdf/doc/week07-非结构化数据工厂.pdf`（60 页 / 5 课时）

---

## 0. 本周主干

五节课是一条链，不是五个话题。前一节的输出就是后一节的输入：

```
L01 Parse       文档 ≠ 字符串，要保结构        → ParsedSection（page/bbox/section_path）
      ↓
L02 Chunk       按语义切，不按字数切            → DocumentChunk（span/heading_path/context_prefix）
      ↓
L03 Evidence    每个 chunk 必须能回到原文       → EvidenceAnchor（谁/在哪/怎么解释）
      ↓
L04 Quality     不达标的切片不许进索引          → gate_decision = pass / warn / block
      ↓
L05 Multimodal  音视频图换物理载体，范式不变    → 同一套 anchor + 同一套 gate
      ↓
                allowed_for_indexing=true 的 chunk → Week08 的起跑线
```

讲义里有三句话值得原样记住：

- **"文档不是字符串"**——不保结构，LLM 永远答不对多栏财报。
- **"切片决定 RAG 的召回上限"**——Reranker 只能从候选里选最好，候选里没有正确答案，神仙也无解。
- **"音频有 segment 就像 PDF 有 page，视频有时间戳就像合同有 bbox"**——多模态不是新范式，是同一套范式换物理载体。

还有一条工程判断贯穿全周：**能力缺失要显式记录，不能悄悄降级。** 仓库里所有 `parser_backend` / `parser_capability` / `reason_codes` 字段都是为这条服务的。

---

## 1. L01 · Parse：从"抽正文"到"保结构"

### 核心论点

同一份 PDF，当字符串处理和当结构化资产处理，下游 RAG 效果差 3-5 倍。差别不在美观，在语义：

| 维度 | 当字符串 | 当结构化资产 | 丢了的后果 |
|---|---|---|---|
| 多栏 layout | 抽成单栏、跨栏串行 | 识别 column 分别处理 | 财报数字串到隔壁表 |
| 表格 | 空格分隔的乱码 | markdown table / 保 cell 边界 | LLM 根本看不懂 |
| 标题层级 | 全是 plain text | H1/H2/H3 进 chunk metadata | 检索精度掉 |
| 图表 / 公式 | 直接丢 | caption + LaTeX + 引用 ref | 专业 RAG 直接废 |
| 页眉页脚 | 混进正文搅乱 chunk | 识别 + 剥离 + 入 metadata | 噪声推高幻觉率 |
| 坐标 | 没有 | 每个 chunk 带 page + bbox | 前端无法高亮原文 |

### 5 阶段 pipeline（最小不可分）

`Load → Layout → Extract → Normalize → Persist`。每阶段是一个独立可测、可换工具、可监控的工程对象，缺一个就有盲区。Load 优先级最高（mimetype / 编码 / 扫描 vs 文本型判断，错了后面全错）；Persist 的要点是**原文档 + chunks + bbox + version_id 一起落地**，只存 markdown 删原件就等于自断追溯。

### PDF 类型识别是入口

走对工具能省 70% 成本。判据就是文字层覆盖率：

| 类型 | 判据 | 建议路由 |
|---|---|---|
| `text_based` | text coverage > 0.8 | Marker / Docling / LlamaParse |
| `scanned` | text coverage < 0.2 | Mistral OCR / Azure DI 等 OCR 优先 |
| `hybrid` | 介于中间 | 文本抽取 + OCR 双管 fallback |

仓库把这段逻辑落成了 `pipelines/parse/pdf_typer.py`，阈值和讲义完全一致（`> 0.8` / `< 0.2`），并且给出 `recommended_route` 字段。

### IDP 工具栈（记结论就够）

讲义横评了七八家，实际有用的判断只有一句：**开源 Marker 起步，企业合规上 LlamaParse，量大走 Mistral OCR，这三个覆盖 80% 场景。** 剩下的分工：Docling（IBM，中文友好、表格 SOTA）、Azure DI / Textract（老牌合规）、GROBID / Nougat（只在论文 RAG）、Claude / GPT-5 Vision 作为 5% 疑难的兜底。

成本量级值得记住：IDP 主干约 $0.002-0.01/页，纯 VLM 截图约 $0.05/页。**无脑上 VLM 处理 PDF 的成本是 IDP 主干的 100-300 倍**，讲义给了一个真实账单：10 万页 PDF 全走 Claude Vision 月账单 $40K，切到 Marker + 5% VLM 兜底后降到 $3.5K，效果反而更好。

### 表格：3 大难点 + 3 种存储策略

难点是 layout 识别（哪些区域是表）、cell 边界（合并单元格、多行）、语义保留（纯 markdown 丢上下文，5 列以上检索就掉精度）。

| 表规模 | 策略 | 说明 |
|---|---|---|
| 小表（< 20 行） | markdown chunk | 直接当一个 chunk 存 |
| 中表 | 描述 + markdown 双轨 | LLM 生成 2-3 句表格描述，描述和 markdown 都进 embedding。2026 主流默认 |
| 大表 | 转 SQL Table | 交给 NL2SQL Agent，财报场景必上 |

仓库的 `pipelines/parse/table_extractor.py` 把这三档写成了 `choose_table_strategy(row_count, has_business_keys)`，阈值是 `< 20` / `<= 200 且无业务主键` / 其余走 `sql_table`。

---

## 2. L02 · Chunk：从"按字数切"到"按语义切"

### 核心论点

切片是 RAG 链路里 ROI 最高的动作，因为它决定召回上限。两种失败方式：

- 正确答案根本没被切进任何 chunk → ANN 召不回 → reranker 排不到 → LLM 必错。
- 正确答案在 chunk 里但和上下文断裂 → LLM 看到孤立信息 → 低置信、幻觉或拒答。

排障映射也很直接：答案漂/上下文断裂 → 暴力按字符切；财务数字串错表 → 表格被拦腰切断；代码理解错 → 按行切代码；多轮对话理解错 → 一问一答被拆开。

### 四种切片策略

| 策略 | 做法 | 什么时候用 |
|---|---|---|
| Fixed-size | 每 N 字符/token + overlap 50-100 | 只在 demo；纯散文/邮件勉强能用 |
| **Structure-aware** | 按 heading / section 切，保 H1/H2 层级 metadata | **90% 场景的最佳起点**，IDP 输出后直接吃 |
| Semantic | LLM 或 embedding 相邻度按主题切 | 论文、长报告等高价值场景，cost 高 |
| **Late Chunking** | 先 embed 整段再按边界池化 | 长文档（> 2k token）、chunk 间互相引用强 |

组合结论：**Structure-aware 起步 + 长文档加 Late Chunking + 高价值场景加 Contextual Retrieval。**

### 粒度权衡

默认从 **300-600 token** 起步，然后按 retrieval 指标反推调，不要凭感觉：

| 粒度 | chunk_size | 优势 | 代价 | 场景 |
|---|---|---|---|---|
| 超细 | 50-150 | 命中精确 | 孤立信息易幻觉 | 事实问答 / FAQ |
| 细 | 300-600 | 默认起点、平衡 | 复杂查询上下文可能不够 | 通用 RAG |
| 中 | 600-1200 | 上下文充足、推理好 | 检索精度略降 | 论文 / 长报告 |
| 粗 | 1200-2000 | 完整段落、理解强 | 召不回精确事实 | 法律 / 合同 |
| 超粗 | > 2000 | 不损上下文 | 召回质量差 | LongContext + RAG 混合 |

调参方法论：先 default → 跑 200 sample 评测 → 看哪个指标失守 → 反推调哪个参数。阈值参考：Recall@5 > 0.80、Recall@20 > 0.92、MRR > 0.65、Faithfulness > 0.85、Context Precision > 0.80、P95 < 3s。Week11 评测周深化。

### 两个 2024 改变游戏规则的做法

**Late Chunking（Jina 2024.09）**：把"先切再 embed"颠倒成"先 embed 再切"。整段过 encoder 拿 token-level embedding，再按 chunk 边界对 token embedding 做 mean pool。长文档检索 nDCG@10 平均 +9%。ROI 高的原因是**不动切片机制，只换 embed 顺序**。限制：OpenAI embedding 不支持，需要 Jina v3 / Voyage v3 这类原生支持的模型。

**Contextual Retrieval（Anthropic 2024.09）**：也不动切片机制，而是给每个 chunk 自动加一句"这个 chunk 在全文中的位置/所属节"的摘要前缀，拼在 chunk 前面再 embed。Recall@20 错误率 -35%，配合 Contextual BM25 达 -49%。成本靠 Prompt Caching 压住（整篇文档进 cache，read 价 0.1x），Haiku 跑一本 1000 chunk 的书 $5 以内。**什么时候不上**：chunk 已经自带 H1/H2 上下文，或文档本身很短（< 5k token）。

### 六种特殊内容必须走单独分支

通用切片器 demo 够用，生产里至少要六个分支，漏一个就有 30% 的 bad case：

| 类型 | 错误做法 | 正确做法 |
|---|---|---|
| 表格 | 混进文本流一起切 | 独立 chunk + 描述双轨 |
| 代码 | 按行切 | AST 按函数切 |
| 公式 | 抽成乱码 | 保 LaTeX / MathML |
| 列表 | 断在 item 中间 | 整个列表当原子 chunk |
| 对话 / FAQ | 问答分开 | turn-aware，Q+A 保一组 |
| 引用 / 脚注 | 混入正文 | 进 metadata，不进正文 |

### 代码切片：必须走 AST

代码不能按行切。TreeSitter 一套接口覆盖 50+ 语言（和 GitHub Code Search 同款引擎），四种切法：按函数、大类拆方法、小文件整切、始终保住 imports 和类上下文作为 anchor。单 chunk 上限 1500-2000 token，超了就拆方法。

代码 embedding 也不能凑合：通用 text embedding 在 CodeSearchNet 上掉约 20% NDCG。英文选 Voyage code-3，中文选 BGE-Code-v1，不要图省事用 OpenAI ada。

---

## 3. L03 · Evidence：证据链

### 核心论点

客户对 RAG 系统最常见的两个质疑是"这答案哪来的"和"让我看原文"。**证据链必须从 day 1 设计**，因为它的丢失点在 Parse 阶段——等到评审现场才发现 page_no / bbox 没存，只能重跑全量 PDF + 重建索引。

### 证据链五个等级

| 等级 | 能力 | 颗粒度 | 场景 |
|---|---|---|---|
| L0 | 只给答案，无 source | 无 | Demo only，客户必拒 |
| L1 | 给文档名 | 文档级 | 内部使用 |
| L2 | 页码 + section 标题 | 段落级 | 内部知识库 |
| **L3** | 页码 + bbox + 段落引用 | 坐标级 | **To B 生产及格线** |
| **L4** | 字符级 + Citations API | token 级 | 金融 / 法律 / 医疗合规必备 |

判断：2025 起 To B RAG 必须 L3 起步，金融法律医疗必须 L4。

（讲义这一页的标题写"4 LEVELS"，正文列了 L0-L4 共五档，以正文为准。）

### EvidenceAnchor 的三组字段

| 组 | 字段 | 缺了会怎样 |
|---|---|---|
| **Identity** 能回原资料 | `doc_id` / `version_id` / `chunk_id` / `source` | 客户问追溯，找不到是哪份哪版 |
| **Location** 能定位 | `page_no` / `bbox` / `span_start` / `span_end` | 前端没法高亮 |
| **Context** 能解释 | `heading_path` / `rerank_score` / `retrieval_method` / `release_id` | 审计断链，说不清是哪次发布命中的 |

### 五层端到端无损传递

```
Parse     → doc_id / page_no / bbox / span 必须入
Chunk     → heading_path / version / chunk_id 入 metadata
Index     → metadata 必须跟 vector 同库存
Retrieve  → 标记 rerank_score / retrieval_method
Generate  → release_id / cited_text 回写 evidence
```

**90% 的团队断在 Index 这一步**：为了 ANN 性能把业务 metadata 砍掉，上线后客户问追溯只能空白响应。pgvector / Milvus 2.5+ 都支持 hybrid metadata，不要为了省 10% 内存丢业务字段。

### 四个反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 没存 bbox（只有文本 + page） | 前端不能高亮原文 | Parse 阶段必入 bbox |
| 存了不传（API 只返回答案） | 客户问追溯空白 | 回答结构必带 evidence[] |
| 传了不对齐（cite 第 1 个但实际看第 3 个） | **假证据比没证据更危险** | Citations API 做强对齐 |
| 评测不验证 citation | 上线后 30% citation 是错的 | 把 citation accuracy 纳入评测 |

Anthropic Citations API（2025.1 GA）的价值在于模型自己输出字符级 `cited_text` + `document_index`，不再靠 prompt hack 让 LLM"说出来源"。公开数据：幻觉率 -50%，准确率 +18%，不增加延迟。

**注意仓库的立场比讲义更严格**：Week07 明确规定 citation 只能来自 `evidence_anchor`，不允许 LLM 生成。Citations API 属于 Week08 之后的生成层话题。

---

## 4. L04 · Quality：切片质检与门禁

### 核心论点

**质检不是"看几个 chunk"，是 CI 门禁的工程流程。** BI 时代的 not_null / unique 在这里不够用：对象从表/行/列变成 chunk/文档/多模态，指标从 not_null/unique/range 变成完整性/噪声/证据/连贯，评测者从人工+规则变成 LLM-as-Judge+规则，抽样从全表或随机变成分层+困难+对抗，门禁从"block 写入"变成"`gate_decision=block` 阻断索引构建"。

一句话概括：RAG 质检不是数据质检的延伸，是**语义质检的新建**——工具和思路都要换。

### 质检四大维度

| 维度 | 看什么 | 指标阈值 | 不达标的根因 |
|---|---|---|---|
| 完整性 | 内容是否全部入库、关键 entity 是否召回 | coverage > 95% | 切片粒度太大 / split 漏了 |
| 噪声 | 页眉页脚 / 水印 / 空 chunk / 重复 chunk | noise_ratio < 3% | IDP layout 还原弱 |
| 证据 | EvidenceAnchor 必填字段是否完整 | evidence_complete = 100% | Parse 阶段砍了字段 |
| 连贯 | 句子结构是否完整、有没有切在句中 | sentence_break_rate < 1% | splitter 算法过粗 |

再加两个检索侧指标构成"生产准入条件"：Recall@5 > 80%、Faithfulness > 85%。

### 抽样策略：纯随机是错误起点

生产级配比是 **70% 分层 + 20% 困难 + 10% 对抗**：

| 类型 | 占比 | 怎么选 | 目的 |
|---|---|---|---|
| 分层 | 70% | 按 doc_type + 长度 + 章节均匀采样 | 保证覆盖代表性 |
| 困难 | 20% | 历史 bad case + LLM-judge 低分 + 复杂 layout 页 | 聚焦关键风险 |
| 对抗 | 10% | 边界 case、极长极短、极复杂表格 | 验证 robustness |

规模：小项目 50，生产 200，关键场景 500。讲义给的对比数据：纯随机 100 sample 漏检率 25%，70/20/10 分层 200 sample 漏检率 4%。

### 门禁流程五个卡点

`①切片完成 → ②抽样标注 → ③跑评测出 quality_report → ④CI 判断 block/pass/warn → ⑤通过后才启动索引构建`

五步不可分。讲义那个"停服 36 小时"的事故根因就是漏了第 ③ 步，直接从切片跳到索引。

### 版本对比四种比法

改切片策略不能靠拍脑袋，四种比法配合用：**A 指标对比**（新旧版跑同一 eval set，不能退步 3%，PR merge 时强制）、**B 答案 diff**（同 query 跑新旧版，LLM-as-judge 评优劣，prompt 大改时用）、**C Bad case 回归**（老 bad case 必须都能修，迭代必跑）、**D 流量 A/B**（5% canary 监控 CSAT / citation accuracy，退化自动回滚）。A 跑 CI，B 评 prompt，C 防回归，D 上线兜底。

### Drift 三个监控点

上线 1-3 个月效果一定会漂：

| 监控点 | 统计量 | 告警阈值 | 修法 |
|---|---|---|---|
| Chunk 数量漂 | 新增 chunk 数周环比 | 突变 > 50% | 全量重切 + 复评 |
| Embedding 分布漂 | KL divergence / MMD | > 0.15 | re-embed 增量数据 |
| Answer 质量漂 | Faithfulness / CSAT 周环比 | Faith < 0.85 | 回滚 release_id |

### 增量更新

文档改一行不能全量重切。做法是：重新 parse → 算每个 chunk 的 **content hash** → diff 出 added / removed / kept → 只对增量做 embed + index → 绑定新 `version_id`。关键设计是**用 content hash 当主键，不依赖易碎的 byte range**（hash 不变即 chunk 不变）。讲义的 ROI 数据：1000 页 PDF 全量重切 $5 / 15 min，增量只重切 50 chunk 是 $0.5 / 30 sec。

---

## 5. L05 · Multimodal：换轨不换范式

### 核心论点

音频、视频、图片本质就是"另一种非结构化数据"，L01-L04 那套 Parse / Chunk / Evidence / Quality 完全可以套用，只是物理载体换了。接到"音视频 AI"项目不必从零造管道，**90% 工作量可复用**。

### 音频 vs 文档：五个维度同构

| 维度 | 文档（PDF） | 音频（mp3） | 同构关系 |
|---|---|---|---|
| Parse | Marker → markdown | Whisper → 文字 + 时间戳 | 都抽语义 |
| Chunk | 按 heading / 句子 | 按 speaker / 话题 | 都按结构 |
| Evidence | `page_no` + `bbox` | `segment_ts` + `speaker_id` | 都可定位 |
| Quality | 四维质检 / coverage | 四维质检 / WER + diarization acc | 都可量化 |
| Index / Retrieve | pgvector + hybrid | 同 store 同链路 | 完全一致 |
| 前端 | 高亮原 PDF | 跳转音频时刻 | 统一 UX |

### 三轨道模型

音视频工程化的统一抽象是三条独立处理的轨 + 一个对齐主键：**Audio Track**（ASR Whisper-v3-Turbo + Diarization pyannote 3.1，产出 speaker + 时间戳 + 文字）、**Vision Track**（ffmpeg / scene-detect 抽关键帧 + VLM caption，产出 frame_path + caption + OCR）、**Time-Stamp Track**（把前两条对齐）。

**`segment_ts` 是主键**，把三条独立处理的结果黏合起来。视频完整流水线：`Demux → ASR → Diarization → KeyFrame → VLM Caption → Align`。讲义给的量级：1 小时视频全流程 < 25 min，成本 < $8。

### 选型速查

Vision LLM：中文用 Qwen2.5-VL（自托管）或 Gemini（SaaS），英文用 Claude Sonnet / GPT-5，视频专门走 Gemini 2.5。跨模态 embedding：中文 BGE-VL 或 Jina-CLIP v2，英文 SigLIP。**Gemini 原生视频 vs 三轨自建**的分界很清楚：demo / PoC / 短视频 / 不需要 evidence 跳转用 Gemini；长视频、需要精确 evidence、中文 ASR、数据隐私自控用三轨自建。

Multimodal RAG 三种架构中，**B（文/图/音独立 store，query 时并行检索，结果一起喂 multimodal LLM）是 2026 生产推荐**：灵活且模态间不互相污染。A（全转文本单 store）早期够用但丢图细节、无跨模态搜；C（CLIP 统一空间图文同 store）能以图搜文，但 cost 高、效果不如专模型，主要用于电商以图搜图。

### 多模态五个反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 所有 PDF 都截图给 VLM | cost 10-30x，中文 OCR 反而更差 | IDP 主干 + VLM 兜底 5% 疑难 |
| 音频不做 diarization | 多人会议混成一段，找不到说话人 | pyannote 或 SaaS speaker 必上 |
| 视频不切 chunk | 一长串 transcript，召回质量极差 | 按话题 / 场景切 |
| 图 embedding 用 text 模型 | 跨模态搜效果差 | CLIP / SigLIP / Jina-CLIP |
| 不存原文件（只存 markdown） | 客户问追溯回不去原文 | 原文件 + chunk 并存 versioning |

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

### 主链路（`--parser auto` 真正会执行的）

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 Load 阶段 + 类型识别 | `pipelines/parse_normalize/raw_loader.py` | `_document_from_asset()`：checksum 校验、sidecar 发现、raw 不可用时的 synthetic fallback |
| L01 解析后端路由 | `pipelines/parse_normalize/parser_adapter.py` | `parse_document()` 的 `auto` 分支：pdf→idp、image→ocr、audio/video→media、其余→unstructured |
| L01 Marker / Docling IDP | `pipelines/parse/marker_pipeline.py` | `parse_pdf_with_idp()`，两个后端都是 try-import，失败返回 None |
| L01 五阶段的 Persist | `pipelines/parse_normalize/run_parse.py` | `_persist_to_db()` 和 `_ensure_week07_parse_schema()` 的加列 DDL |
| L02 结构感知切片 | `pipelines/chunker/structure_aware.py` | `split_section_text()`：`BOUNDARY_RE` 中英文句末标点、`HARD_BOUNDARY_TYPES` 整块不切 |
| L02 切片编排 | `pipelines/parse_normalize/chunking.py` | `chunk_sections()`：chunk_id 怎么算、reason_codes 怎么继承 |
| L02 Contextual Retrieval | `pipelines/chunker/contextual.py` | `build_context_prefix()`——注意这是**拼接式**前缀，不调 LLM |
| L03 EvidenceAnchor 生成 | `pipelines/parse_normalize/evidence_anchor.py` | `anchor_type` 六选一的判定逻辑（page / object / timestamp / frame / section / fallback） |
| L03 数据结构定义 | `pipelines/parse_normalize/models.py` | `ParsedSection` / `DocumentChunk` / `EvidenceAnchor` / `ParserCapability` 四个 dataclass |
| L04 质量门禁 | `pipelines/parse_normalize/quality_gate.py` | `evaluate_quality_gate()`：哪些进 errors、哪些进 warnings |
| L04 四维质量报告 | `pipelines/quality/report.py` | `build_quality_report()`：完整性/噪声/证据/连贯四个 score 的算法 |
| L04 报告落盘 | `pipelines/parse_normalize/reporting.py` | `week8_ready_gate.json` 里的 `consumer_rules` |
| L05 多模态素材清单 | `data/seed_manifests/manifest_week07_multimodal_v1.json` | 四个资产的 sidecar 字段：`transcript_object_path` / `ocr_text_path` / `keyframe_ocr_path` |
| Dagster 资产化 | `pipelines/parse_normalize/assets.py` | `parsed_doc_sections` / `knowledge_chunks` 两个 asset 只是 CLI 的薄封装 |

### 契约与测试

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| Section 契约 | `contracts/data/knowledge_section.schema.json` | PDF 的条件必填：`asset_type=pdf` 就必须有 `page_no`+`bbox`，bbox 为 null 则必须给 `bbox_missing_reason` |
| Chunk 契约 | `contracts/data/document_chunk.schema.json` | `evidence_anchor_ids` 的 `minItems: 1`、`anchor_count` 的 `minimum: 1` |
| Evidence 契约 | `contracts/data/evidence_anchor.schema.json` | `anchor_type` 六种枚举、`parser_backend` 十四种枚举 |
| Run evidence 契约 | `contracts/data/parse_run.schema.json` | `week8_ready` 布尔 + `artifacts` 四个路径 |
| 质检抽样契约 | `contracts/data/chunk_quality_sample.schema.json` | `checks` 四个必填布尔 |
| 契约测试 | `tests/contract/test_week07_parse_contracts.py` | 两个 negative fixture：缺 anchor、PDF 缺 page |
| 端到端测试 | `tests/integration/test_week07_parse_pipeline.py`<br>`tests/integration/test_week07_quality_gate.py`<br>`tests/integration/test_week07_multimodal_pipeline.py`<br>`tests/integration/test_week07_ppt_alignment.py` | 第三个验证四种模态都被解析；第四个是"讲义概念都有对应代码"的守护测试 |
| DB 迁移 | `infra/migrations/004_week07_parse_normalize.sql`<br>`005_week07_multimodal_parse.sql`<br>`006_week07_ppt_alignment.sql` | 三次 additive 迁移的演进顺序 |

### 讲义概念的"占位实现"（存在但没接进主链路）

这一组都只被 `tests/integration/test_week07_ppt_alignment.py` 引用，`run_parse.py` 一个都没调。**看的时候要知道它们是概念锚点，不是运行时。**

| 模块 | 讲义里是什么 | 仓库里实际是什么 |
|---|---|---|
| `pipelines/parse/pdf_typer.py` | PyMuPDF 判 text/scanned/hybrid | 完整实现了，阈值也对，但 `parser_adapter.py` 没有调用它 |
| `pipelines/parse/table_extractor.py` | Camelot / LlamaParse 抽表 | 只是一个 `choose_table_strategy()` 决策函数，不抽表 |
| `pipelines/chunker/late_chunking.py` | Jina v3 token-level pooling | 只返回一个 `LateChunkingPlan`，`model_available` 默认 False，`enabled` 恒为 False |
| `pipelines/chunker/code_ast.py` | TreeSitter AST 切函数 | 正则匹配 `def/class/function/const`，`parser_backend` 直接写死 `regex_fallback` |
| `pipelines/quality/drift_detector.py` | 三个监控点 + KL divergence | 一个 `compare_metric(current, baseline, threshold=0.1)` 阈值比较 |
| `pipelines/incremental/update.py` | content hash diff 出 added/removed/kept | 只比 `source_fingerprint`，返回 insert / skip / reparse 三态 |
| `pipelines/audio/process.py` | Whisper + pyannote | 只解析 transcript sidecar 的 JSONL |
| `pipelines/video/pipeline.py` | Demux + ASR + KeyFrame + VLM 六步 | 一个 `align_video_tracks()` 对齐 helper |
| `pipelines/multimodal/clip_embed.py` | CLIP / SigLIP 跨模态检索 | `importlib.util.find_spec("sentence_transformers")` 探测依赖在不在 |

### 代码里值得单独看、讲义没展开的细节

**IDP 优先但会显式降级，降级痕迹留在数据里。** `parser_adapter.py` 的 `auto` 对 PDF 先试 marker 再试 docling，失败时走 `_parse_with_pypdf(parser_backend="pypdf_baseline", fallback_used=True)`，并写入不同的 warning 区分原因：

```python
"idp_requires_local_path_pypdf_baseline_used"   # 只有 S3 路径没有本地文件
"idp_parser_unavailable_pypdf_baseline_used"    # marker/docling 没装
"idp_text_empty_pypdf_baseline_used"            # 装了但一个 block 都没抽出来
```

这三种情况在 artifacts 里都表现为 `pypdf_baseline`，但 warning 不同——排查时先看 warning 再看 backend。

**`ParserCapability` 是能力自述，不是配置。** 每种 backend 声明自己保不保 page / bbox / table / layout / heading，能不能 OCR、抽 transcript、抽 keyframe。这份 capability 会一路带到 chunk 和 anchor 上，Week08 靠它判断"这条证据能不能当 Docling 级坐标用"。pypdf_baseline 的 `preserves_bbox=False`，所以 PDF 的 anchor 一定带 `bbox_missing_reason="pypdf_no_bbox"`。

**PII 命中会直接一票否决索引资格。** `quality_gate.py` 里一个很粗糙但很硬的正则（邮箱 + 类 SSN 数字）一旦命中，`allowed_for_indexing` 直接为 False：

```python
chunk.allowed_for_indexing = (
    chunk.anchor_count > 0
    and bool(chunk.content.strip())
    and "source_path_missing_synthetic_fallback" not in chunk.reason_codes
    and not MEDIA_BLOCKING_REASON_CODES.intersection(set(chunk.reason_codes))
    and not chunk.pii_detected
)
```

注意这和 `quality_status` 是两个层次：`quality_status` 是整批的结论（pass/warn/fail），`allowed_for_indexing` 是单条 chunk 的资格。整批 warn，单条仍可能不许索引。

**媒体解析失败宁可不产 chunk，也不产垃圾。** `MEDIA_BLOCKING_REASON_CODES` 那四个 reason code（transcript 缺失、OCR 空、视频既无转写也无关键帧 OCR、二进制文本回退）会被判为 error 而不是 warning。对应的测试 `test_week07_audio_without_transcript_does_not_index_binary_garbage` 断言的是 `chunks == []` 且 `status == "failed"`——**宁可整批 fail，也不许把二进制乱码当 chunk 索引。**

**`week8_ready` 比 `quality_status == "pass"` 多一条**：还要求没有任何 `source_path_missing_synthetic_fallback` chunk。也就是说，manifest 指向的原始文件必须真实存在，用 manifest metadata 拼出来的占位文本可以 warn 通过，但绝不能 ready。

**`chunk_id` 是内容寻址的，不是自增的**：`stable_id("chunk", source_fingerprint, section_id, section_chunk_index, chunk_strategy_version)`。这意味着换 chunk 策略版本 → 所有 chunk_id 全变 → Week08 必须用新的 `index_release_id` 重建索引。这是讲义"增量更新用 content hash 当主键"的仓库版实现。

**`structure_aware.py` 的边界正则同时认中英文句末标点**（`[。！？.!?]`），并且 `HARD_BOUNDARY_TYPES = {"table", "code", "image", "transcript"}` 里的 section 无论多长都不切——这正是讲义"表格独立 chunk""列表当原子 chunk"的落地。

**chunk_size 默认 512 字符（不是 token）**，overlap 64，可被 manifest 的 `ingest_config` 覆盖。多模态 manifest 里设的是 320 / 40。

---

## 7. 讲义与仓库对不上的地方

讲义 p60 列的"本周交付物"里有几条要么路径不存在、要么实现和讲义描述差得远。**别浪费时间去找。**

| 讲义写的 | 实际情况 |
|---|---|
| `services/rag_api/models.py`（EvidenceAnchor Pydantic schema） | **不存在**。`services/` 下只有 `graph/models.py` 和 `copilot_api/app/models.py`。EvidenceAnchor 实际在 `pipelines/parse_normalize/models.py`，是 **dataclass 不是 Pydantic**，字段名也不同（`data_release_id` 不是 `release_id`，多了 `anchor_type` / `parser_capability` / `bbox_missing_reason`） |
| `services/audio_pipeline/models.py`（AudioSegment） | **不存在**。音频段的结构在 `pipelines/audio/process.py` 的 `AudioSegment` dataclass，只有 text/speaker/start_ts/end_ts 四个字段 |
| `pipelines/quality/report.py` 的 QualityReport 字段 | 文件存在，但字段和讲义完全不同。**没有** `sample_size` / `sampling` / `recall_at_5` / `recall_at_20` / `mrr` / `faithfulness_llm_judge` / `block_reasons` / `drift_metrics` / `embedding_drift_kl`。实际只有 `gate_decision` + 四个 score + metrics 字典。检索类指标是 Week11 的事 |
| 70/20/10 分层抽样 | **仓库没有实现**。`quality_gate.py` 的抽样是 `chunks[:min(5, len(chunks))]`——取前 5 条，纯截断，不分层 |
| `pipelines/incremental/update.py` 的 content hash diff | 文件存在但只做 fingerprint 三态比较，**没有** added / removed / kept 的集合运算，也没有 index.insert / index.delete |
| 讲义各处的 SaaS API 代码（LlamaParse / Anthropic Citations / Gemini video / Whisper） | 仓库一律不调用外部 API。Week07 明确"不做 embedding、不建 pgvector index、不调用 LLM" |
| `docs/assets/week07/parse-normalize-code-architecture.png` | **不存在**。`runbooks/week07-unstructured-data.md` 和 `docs/blueprints/week07/ppt-alignment-roadmap.md` 都引用了这张架构图，但 `docs/assets/` 目录整个都没有 |
| `data/week07_media/` 的三个媒体文件 | 仓库里只有 `workspace_recovery_manual.pdf` 和三个 sidecar（`.ocr.txt` / `.transcript.jsonl` ×2）。**`workspace_recovery_evidence.png`、`support_call_recovery.wav`、`workspace_recovery_demo.mp4` 都不在**，需要先跑 `scripts/week07/generate_multimodal_fixtures.py` 生成。runbook 写的"The repository ships generated fixtures"与实际不符 |
| `pipelines/parse_normalize/doc_parser.py` | 文件存在但是**遗留的第二套实现**（`DoclingParser` / `UnstructuredParser` / `SlidingWindowChunker`），不在 `run_parse.py` 主链路上，没有 evidence anchor / quality gate / 版本字段。除了 Week03 一份旧 blueprint，没有任何代码引用它。**读代码时不要从这里入手** |

另外两处是讲义自身的小问题：p27 标题写"4 LEVELS OF EVIDENCE"但正文列了 L0-L4 五档；每页页码（如 `03 / 66`）与实际 60 页不符，都是模板噪音。

---

## 8. 动手清单

统一走 Docker devbox（Podman 用同一个 compose 文件）。下面所有命令都要加同一个前缀，为了省版面只写一次：

```bash
DEVBOX="docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox"
```

```bash
# 0. 先补齐多模态素材（png / wav / mp4 不在仓库里）
$DEVBOX python scripts/week07/generate_multimodal_fixtures.py

# 1. 契约测试：5 个 schema 合法 + 2 个 negative fixture 必须失败
$DEVBOX pytest tests/contract/test_week07_parse_contracts.py -v

# 2. 默认 manifest 的 dry-run（S3 占位路径，会走 synthetic fallback）
$DEVBOX python -m pipelines.parse_normalize.run_parse \
    --manifest-path data/seed_manifests/manifest_workspace_helpcenter_v1.json \
    --parser auto --chunk-strategy section_aware_v1 \
    --data-release-id week07-dev-local --dry-run \
    --artifacts-dir artifacts/week07 \
    --report-json reports/week07/parse_run_report.json \
    --quality-report-md reports/week07/chunk_quality_report.md \
    --week8-gate-json reports/week07/week8_ready_gate.json

# 3. 真实多模态 dry-run（PDF + 图 OCR + 音频 + 视频）
$DEVBOX python -m pipelines.parse_normalize.run_parse \
    --manifest-path data/seed_manifests/manifest_week07_multimodal_v1.json \
    --parser auto --chunk-strategy section_aware_v1 \
    --data-release-id week07-multimodal-local --dry-run \
    --artifacts-dir artifacts/week07-multimodal \
    --report-json reports/week07/parse_run_report_multimodal.json \
    --quality-report-md reports/week07/chunk_quality_report_multimodal.md \
    --week8-gate-json reports/week07/week8_ready_gate_multimodal.json

# 4. 集成测试
$DEVBOX pytest tests/integration/test_week07_parse_pipeline.py \
    tests/integration/test_week07_quality_gate.py \
    tests/integration/test_week07_multimodal_pipeline.py \
    tests/integration/test_week07_ppt_alignment.py -v
```

**验收标准不是"跑过了"，而是能回答这六个问题**（答案都在 `artifacts/week07*/` 和 `reports/week07/` 里）：

1. 第 2 步和第 3 步的 `week8_ready` 分别是什么？为什么第 2 步是 false？（提示：看 warnings 里的 `source_path_missing_synthetic_fallback`）
2. 打开 `sections.json`，PDF 的 `parser_backend` 是 `marker` / `docling` 还是 `pypdf_baseline`？对应的 warning 是哪一条？说明降级的具体原因是什么。
3. 打开 `evidence_anchors.json`，四种 `asset_type` 分别产生了哪种 `anchor_type`？PDF 的 `bbox` 是不是 null？`bbox_missing_reason` 写了什么？
4. `chunks.json` 里 `allowed_for_indexing=false` 的 chunk 有几条？逐条说清是因为哪个条件不满足。
5. `chunk_quality_report.md` 里 `gate_decision` 是什么？它和 `quality_status` 是什么映射关系？
6. `week8_ready_gate.json` 的 `consumer_rules` 四条分别约束 Week08 不许做什么？

**加分练习**：

- 把 `manifest_week07_multimodal_v1.json` 里 audio 那条的 `transcript_object_path` 删掉再跑，确认整批变成 `failed` 且 `chunks == []`——理解"宁可不产 chunk 也不产垃圾"。
- 改 `--chunk-strategy` 传一个别的字符串，看 `chunk_sections()` 直接抛 `ValueError`，理解为什么策略版本必须是白名单而不是自由字符串。
- 在某条 chunk 内容里塞一个邮箱地址，确认 `pii_detected=true` 且 `allowed_for_indexing` 变 false，同时整批 `quality_status` 只是 `warn`——体会"整批结论"和"单条资格"是两件事。
- 对比 `manifest_week07_multimodal_v1.json` 里 `chunk_size: 320` 和默认 512 的产物差异，数一下 chunk 数量和 `span_start/span_end` 的变化。

---

## 9. 易错点与边界

**概念层面**

- **Parse ≠ 抽文本**。抽文本产出字符串，parse 产出带 page / bbox / section_path / capability 的结构对象。
- **chunk metadata ≠ evidence anchor**。metadata 是 chunk 自带的属性；anchor 是独立的、可被 citation 直接引用的记录，有自己的 schema 和主键。仓库里 anchor 是单独一张表、单独一个 artifact 文件。
- **`quality_status` ≠ `allowed_for_indexing`**。前者是整批 run 的结论，后者是单条 chunk 的索引资格。
- **`week8_ready` ≠ `quality_status == "pass"`**。ready 额外要求没有 synthetic fallback chunk。
- **Late Chunking ≠ Contextual Retrieval**。前者改的是 embed 顺序（先整段 embed 再池化），后者改的是 chunk 内容（加一段 LLM 生成的上下文前缀）。两者都不动切片算法本身，但作用层不同，可以叠加。
- **降级 ≠ 失败**。`pypdf_baseline` 是合法输出，只是能力更弱；关键是它被显式标记出来，下游不会误当成 Docling 级坐标。
- **"仓库有这个文件" ≠ "这个功能接进主链路了"**。见第 6 节的占位实现清单。

**范围边界（Week07 到底做到哪）**

Week07 交付的是**从原始文件到"可索引资格判定"的这一段**，明确不做：

- 不做 embedding、不建 pgvector ANN index（Week08）
- 不实现 RAG 生成、不产生 citation 文本（Week08 之后）
- 不允许 LLM 生成 citation——citation 只能来自 `evidence_anchor`
- 不做 HITL 工作流（Week12 方向）
- 不接管 Week06 的 data factory 编排
- 讲义大量提到的 Ragas / DeepEval / Phoenix、Recall@5 / MRR / Faithfulness，属于 Week11 评测周，本周的 quality gate 只管结构性质量

Week08 能消费的：`chunks.json` / `evidence_anchors.json` / `week8_ready_gate.json`，以及 `chunk_strategy_version` / `parse_strategy_version` / `source_fingerprint` / `doc_version` / `quality_status`。
Week08 不能假设的：无 anchor 的 chunk 可索引、LLM 生成的 citation 有效、`allowed_for_indexing=false` 的数据可索引、fallback 输出有完整坐标、策略版本可以忽略。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. "文档不是字符串"这句话，用一个具体的多栏 PDF 场景说清它造成的下游后果。为什么这不是模型能力问题？
2. PDF 类型识别为什么被称为"整个 pipeline 的入口"？text-based / scanned / hybrid 三种类型各自应该路由到什么后端？
3. Late Chunking 和 Contextual Retrieval 都号称"不动切片机制"，它们各自改的是哪一环？为什么 OpenAI embedding 用不了 Late Chunking？
4. 代码为什么不能按行切？如果一个函数超过了 max_size 上限，应该怎么处理？为什么无论怎么切都要保住 imports？
5. 证据链 L2 和 L3 的差别是什么？为什么"页码 + section 标题"在 To B 生产里不够用？
6. "传了不对齐"的反模式为什么比"没存 bbox"更危险？五层传递中为什么 Index 是断链高发地？
7. 纯随机抽样 100 个 chunk 为什么是错误起点？70/20/10 三部分各自解决什么问题？
8. 在本仓库里，一条 chunk 的 `quality_status` 是 `warn` 但 `allowed_for_indexing` 是 `false`，可能是哪几个原因造成的？
9. `week8_ready` 为什么要额外排除 `source_path_missing_synthetic_fallback`？如果不排除会发生什么？
10. 音频没有 transcript sidecar 时，仓库为什么宁可整批 `failed` 也不产出 chunk？如果退而求其次产出"二进制解码文本"会污染下游哪几个环节？
11. 讲义主推 Marker / LlamaParse，仓库默认却降级到 pypdf baseline。这个降级在数据里留下了哪些痕迹？Week08 怎么知道自己拿到的是低保真证据？
12. `chunk_id` 用 `source_fingerprint + section_id + section_chunk_index + chunk_strategy_version` 哈希生成，而不是自增 ID。这个设计对"换切片策略"这件事意味着什么？

---

## 11. 一句话收口

Week07 是整门课**从"结构化数据治理"跨到"非结构化资产化"的那一步**：它把 Week02 定下的 contract 思维、Week03 的 run evidence 思维，原样搬到了 PDF / 图 / 音 / 视频上——同一套 identity、同一套 provenance、同一套 gate。做扎实了，Week08 的检索、Week11 的评测、Week14 的审计才有可引用的地基；做糊了，后面每一周都在给一堆无法追溯的字符串做包装。
