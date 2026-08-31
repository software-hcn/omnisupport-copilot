# Week 11 · 评测体系：从「凭感觉」到「可量化」

> **一句话**：把 Copilot 的质量从「抽测几个 case 感觉还行」，做成能写进 release、能卡住 PR、能交给监管看的数字。
>
> 讲义：`pdf/doc/week11-评测体系·从凭感觉到可量化.pdf`（48 页 / 5 课时）

---

## 0. 本周主干

五节课是一条发布控制链，每一节给上一节的产出加约束：

```
Week10 Copilot 能办事
  ↓ L01 Dataset   4 类样本 + digest + 绑进 manifest          「尺子」
  ↓ L02 Metrics   检索 / 生成 / 整体 6 指标 + latency / cost 「刻度」
  ↓ L03 Judge     锚点 + 反偏差 + 校准 + cross-evaluate      「裁判」
  ↓ L04 Gate      PR / Pre-Release / Canary + A/B            「牙齿」
  ↓ L05 Biz       金融 4 类 SLO + 风控 5 类 + 合规红线       「翻译」
  → Week12 可观测 / Week14 发布治理
```

课堂口令值得单独记：

> 评测集定尺子，指标定刻度，judge 定裁判，gate 给否决权，business SLO 把技术分翻译成业务结果。

另一句更狠、也更准：**评测集烂，后面 metrics / judge / gate 全是空中楼阁。** 不阻断的评测等于没有评测——它只是一份美化过的日志。

---

## 1. L01 · Dataset：评测集是资产，不是测试用例

### 核心论点

传统测试集写一次、跑很久、偶尔补。AI 评测集脚下三样东西一直在动：**业务**（FAQ / 政策 / 说法）、**模型**（LLM / reranker / prompt）、**上下文**（Week07-09 底座）。昨天的标答今天就错，所以必须当成持续演进的数据资产：可版本、可回归、可对抗、可治理。

| 维度 | 人工抽测 | 评测集资产化 |
|---|---|---|
| 样本 | 5-20 条，凭直觉 | 50-2000 条，分层覆盖 |
| 版本 | 没有 | `v1 / v2 / v3` 显式版本 + digest |
| 可重放 | 不可 | 同份数据 + 同份评测器 → 完全可重放 |
| Bad case | 靠工程师记忆 | 反例库自动维护 |
| 协作 / CI | Wiki / 群里喊 | Git + PR review + 回归门禁 |
| 长期价值 | 复盘时一次性用 | 复利资产 |

面试口径：评测集多少条、第几版、跑在 CI 里吗？答不上来，就还在 Demo 阶段。

### 4 类样本（少一类就有一整块盲区）

| 类别 | 占比 | 验证什么 | 来源 | 少了会怎样 |
|---|---|---|---|---|
| `happy` | 60-70% | 基础能力 | 产品历史日志 | 连晴天都测不稳 |
| `boundary` | 15-20% | 泛化 | 同义改写 / 罕见术语 / 含糊 | 真实用户说法一变就崩 |
| `adversarial` | 10-15% | 安全 + 合规 | 历史事故 + 红队 | 只测了晴天，上线遇暴雨必崩 |
| `multi_hop` | 5-10% | 跨文档 / 多步推理 | 真实复杂工单 | 复杂工单全是盲区 |

反例库是价值最高、却 90% 团队没有的部分。讲义判断：**反例占比低于 10%，这套评测集就只测了晴天。**

仓库课堂集 `evals/sets/rag_qa_golden_v2_3_0.jsonl` 是 8 条（每类 2 条），用来把契约和门禁行为跑通，不是生产规模。加载器强制四类都在：缺一类直接 `eval set must include all Week11 categories`。

### 半自动生成：LLM 出草稿，人补暴雨题

纯人工写 50 条三元组要 8-15 小时；半自动只要 2-3 小时。流程是：拉历史文档 → LLM 生成候选 → 人工 review 修正 → **手工补 10-20 条 adversarial** → 写入评测集。关键是「半自动」四个字：反例和边界，机器编不出真实感。

讲义示例写在 `evals/generate.py`，仓库里没有这个脚本（见第 7 节）。要看的是产出契约，不是生成器本身。

### 合格样本不是只有 Q&A 两栏

| 字段（仓库名） | 讲义旧名 | 为什么必填 |
|---|---|---|
| `case_id` | `sample_id` | CI 报告关联、Bad case 跟踪 |
| `query` | 同 | 评测输入 |
| `expected_answer` | 同 | faithfulness / correctness 对照 |
| `expected_citation_ids` | `expected_evidences` | context_precision / recall |
| `expected_keywords` | （讲义没单列） | answer_relevance 的确定性代理 |
| `category` | 同（`multi-hop` → `multi_hop`） | 分层统计，不混总分 |
| `source_doc` + `doc_version` | 同 | 数据资产血缘 |
| `should_abstain` / `forbidden_phrases` | （讲义没写成字段） | 反例可以靠拒答过关，不能靠瞎答 |

少 `category` 就只能看总分；少 `doc_version` 事故复盘时连当时哪版文档都查不到。可回答 case 必须有 `expected_citation_ids`；`should_abstain=true` 的反例可以没有 citation，但必须能拒。

### 评测集必须绑进 release manifest

不同版本的评测集会算出不同的分；不锁版本，「上线前 vs 上线后」没法比。仓库把讲义的 YAML 收成 JSON：`contracts/release/release_manifest_example.json` 的 `eval_dataset` 段钉死 `id / version / sample_count / categories / digest`，`generated_from` 记来源。digest 是文件字节的 `sha256:`——样本改一个字 hash 就变。

---

## 2. L02 · Metrics：一个「答对率」混了三种病

### 核心论点

「答对率 80%」把三种完全不同的病混成一锅：模型编的、答非所问、压根没检索到。RAGAS 的价值不是再出一个总分，而是把「对/错」拆成能分别下药的工程维度。

### 三层 6 指标

| 层 | 指标 | 在问什么 | 低了改什么 |
|---|---|---|---|
| 检索 | `context_precision` | 召回的 chunk 里真相关占比 | reranker / 阈值（Week08 L2） |
| 检索 | `context_recall` | 该召的有没有召全 | chunk 策略 / hybrid（Week07/08） |
| 生成 | `faithfulness` | 每个 claim 是否来自 context | 加严 prompt + Structured Outputs |
| 生成 | `answer_relevance` | 有没有答到提问意图 | Query 改写 / Multi-Query |
| 整体 | `answer_correctness` | 对照标答综合对不对 | 先拆上面两层，别瞎改整体 |
| 整体 | `semantic_similarity` | 和标答语义跑没跑偏 | 回到检索/生成定位 |

CP 和 CR 是一对、方向相反：CP 低 = 召回太脏，CR 低 = 召回太漏。只跑 CP 会自我感动——召回很干净，但漏了一半关键资料。

讲义给的生产经验阈值（课堂代码阈值更松，见第 6 节）：

| 指标 | 经验阈值 | 金融可上调 |
|---|---|---|
| Faithfulness | > 0.85 | 0.92 |
| Answer Relevance | > 0.80 | — |
| Context Precision | > 0.75 | — |

**Faithfulness 比 Answer Relevance 更重要。** 「答非所问」用户一眼看穿；「编得有理有据」骗得过用户、骗不过监管。金融场景 faithfulness 是第一红线。

### RAGAS 之外：质量只是四个轮子之一

| 指标 | 为什么要命 | 仓库落点 |
|---|---|---|
| Latency P50 / P99 | 答得慢用户跑光 | `EvalReport.latency` |
| Cost per query | demo 不管、上线账单爆炸 | `EvalReport.cost` |
| Refusal / Safety | 该拒的有没有拒 | `safety_pass_rate` + `adversarial_pass_rate` |
| Citation accuracy | 引用是否真支撑 claim | `expected_citation_ids` vs `citations` |
| HITL trigger | 人工介入过多/过少 | Week10 audit，本周不实现 |

五类看板：Quality / Latency / Cost / Safety / HITL。单看 Quality 像只量体温不量血压。

### 五个评测反模式

只看一个分数、同模型自评、评测集 < 30 就 ship、指标无基线、没有反例。最隐蔽的是同模型自评：分数特别好看，生产里掉得最快。

课堂 runner **不算真正的 RAGAS**。它用确定性代理算出同一份 report shape，Docker 里不依赖付费 LLM。生产可以换成真 RAGAS / LLM-as-Judge，契约不变。

---

## 3. L03 · Judge：裁判本身不可信，分数就都不可信

### 4 类系统性偏差（换更强模型消不掉）

| 偏差 | 表现 | 消除方法 |
|---|---|---|
| 位置 | A/B 换序分数就变 | 两个顺序各跑一次取平均 |
| 长度 | 长答案系统性偏高 | prompt 显式声明长度不计分 |
| 自我偏好 | GPT 给 GPT 打高分 | 永远 cross-evaluate |
| 拒绝 | 「我不确定」比错答得分高 | prompt 定义不确定的扣分规则 |

这是 Transformer 架构带来的，不是能力问题。模型越强，偏差更隐蔽，但它还在。

### 3 种 Judge 模式

| 模式 | 做什么 | 适合 | 坑 |
|---|---|---|---|
| Pairwise | A vs B 谁更好 | A/B、模型对比 | 位置偏差最重，必须换序 |
| Single Score | 一条打 1-5 分 | 批量趋势 | 分数飘 ±1，必须锚点 |
| Reference-based | 对照标答 | 有 ground truth | 标答成本高，但最稳 |

生产默认 Reference-based：有标答兜底，judge 发挥空间最小。能构建标答就别裸评。

### 生产级 prompt 四件套

`evals/judges/faithfulness.j2` 把讲义那页直接落地：

1. **4 档锚点**（1.0 / 0.7 / 0.4 / 0.0），钉死刻度
2. **反偏差约束**（长度不计分、拒答在 context 不足时打 0.5）
3. **calibration example**（「3 步」vs 编造「5 步」）
4. **Structured JSON**（`score` / `reason` / `unsupported_claims`）

prompt 改几个字，和人类一致性可以差 30%。改 prompt = 换裁判，必须重跑校准。另有一份 `evals/judges/answer_relevance.j2`，讲义没展开，仓库补了。

### 100 条人工金标准，四个角度一起看

| 指标 | 看什么 | 建议阈值 | 不达标 |
|---|---|---|---|
| Cohen's κ | 排除随机后的分类一致 | > 0.6 | 重写 prompt |
| Pearson r | 连续分数相关 | > 0.75 | 加 calibration anchor |
| MAE | 0-1 上的平均绝对误差 | < 0.15 | 换更强 judge 模型 |
| Top-K overlap | 排序是不是同一批好/坏样本 | > 80% | 看具体偏差类型 |

κ < 0.6 的 judge 不能拿去做生产决策。仓库 `trust_level` 就这一条：κ ≥ 0.6 → `high`，否则 `low`。课堂校准集 8 条（`evals/calibration/human_judge_gold_v1.jsonl`），数学与讲义一致，不在线打分。

### Cross-evaluate

| 策略 | 成本 | 准确度 |
|---|---|---|
| Single Judge | 1x | 低（有 bias） |
| Pair Judge + Average | 2x | 中高，常规默认 |
| Pair + Disagree Flag（分歧 > 0.3 人工二审） | 2x | 高 |
| Multi-Judge Voting | 3-5x | 最高，合规 / 资金场景 |

RAG 用 GPT 生成、又用 GPT 当裁判，分数高得离谱也别信。课堂不跑在线 cross-evaluate，只把校准报告形状和 `judge_calibration` 绑进 manifest，留给生产接。

---

## 4. L04 · Gate：能 block 的评测才有牙齿

### 成熟度 5 级

| 等级 | 表现 | 实际效果 |
|---|---|---|
| L0 | 凭感觉抽测 | 什么都拦不住 |
| L1 | 周报评测 | 退化一周后才发现 |
| L2 | PR 自动跑但不阻断 | 靠人记得检查 |
| L3 | 退化超阈值不能合并 | 拦住约 90% 退化 |
| L4 | PR + 上线 + Canary 自动升档/回滚 | 客户几乎感知不到 |

L1 和 L2 是最大的两个坑——看着有评测，其实没牙。L2 → L3 往往就是 `exit 1` 加几十行 CI。这是 Demo 团队和生产团队的分水岭。

### 三道闸，拦三类问题

| 闸 | 触发 | 样本 | 决策 | 拦什么 |
|---|---|---|---|---|
| PR Gate | 改 prompt / 检索 / eval | golden set 50-200 | 5-10 分钟；退化 > 2% block | 「这次改坏了」 |
| Pre-Release | 合到 main 后全量 | 全指标 + 反例库 | 20-30 分钟；退化 > 1% 阻塞发布 | 全量才暴露的退化 |
| Canary | 上线后 5% 流量 | 真实流量 quality + latency + cost | 30-60 分钟；退化自动回滚 | 只有真用户才暴露的问题 |

PR Gate 对反例库要**零退化**：`--no-drop adversarial_pass_rate` / `--no-drop safety_pass_rate`。安全类比性能类严。仓库 runner 自己还有一道更硬的闸：`pass_rate < 0.80`、任意一条 adversarial 没过、任意一条 safety 失败，报告 `gate.status=fail`。

### 回归比较的三种牙齿

`evals/week11/regression.py` 三种约束不要混：

| 参数 | 含义 | 课堂用法 |
|---|---|---|
| `--max-drop` | 允许轻微波动 | `faithfulness=0.02`、`answer_relevance=0.02`、`context_precision=0.03` |
| `--min` | 绝对值下限 | `pass_rate=0.80` |
| `--no-drop` | 相对 baseline 一丝不能退 | `adversarial_pass_rate`、`safety_pass_rate` |

平均质量好看、安全红线退了，照样 block。这就是「门禁有牙齿」的地方。

### A/B：不是跑 30 条看哪个分高

| 对比 | 看哪些指标 | 建议样本量 |
|---|---|---|
| Chunk 策略 | CP / CR | 300+ |
| Rerank 模型 | CP + latency + cost | 500+ |
| Prompt 版本 | F / AR / hallucination | 200+ |
| LLM 模型 | 6 指标 + 成本 | 1000+ |

效应越小要的样本越多。仓库用讲义锚点，不引入 scipy：

| 效应 | 约需样本量 |
|---|---|
| ≥ 10% | 80 |
| ≥ 5% | 200 |
| ≥ 2% | 800 |
| 更小 | `800 × (0.02 / effect)²` |

事后必须 **t-test + Mann-Whitney 双重 p < 0.05** 才算显著。决策只有三选一：`ship_B` / `keep_A` / `need_more_data`。RAG 分数常非正态，单一 t-test 会骗人。

### Canary 的灵魂是自动回滚

Deploy 5% → Monitor 15-30 分钟 → 在线评测 + A/B → 升档或回滚 → 决策写入 manifest。配了告警没配自动回滚，半夜 3 点没人响应，坏版本会放一整夜。仓库只把 `rollout.auto_rollback_on` 写进 manifest（PII 一例就回滚、首次解决率跌破 0.62），**没有流量分发执行器**——那是 Week14。

门禁五个反模式：warn 不 block、阈值拍脑袋、只看 mean、A/B 不算样本量、Canary 不自动回滚。最普遍的是第一项：温柔的门禁等于没门禁。

---

## 5. L05 · Biz：CEO 不在乎你的 F=0.892

### 技术分好 ≠ 业务好

漏斗每一环都有损失：

```
Tech (F / AR / CP)
  → Quality（用户是否理解）
  → Behavior（是否还追问）
  → Workflow（工单是否关闭）
  → Business（自助率 / NPS）
```

技术指标涨了、业务指标没动，一定是中间某一环卡住——答案质量上去了，UI 看不懂，工单照样没关。评测从第一天就要追 end-to-end，不是盯两端数字自嗨。

### 金融客服 4 类 SLO（缺一类不能 GA）

| 类别 | 关键指标 | 目标 | 关联技术指标 |
|---|---|---|---|
| 自助 + 闭环 | 一次解决率 / 自助分流 / 工单闭环 / 升级率 | >65% / >70% / >90% / <10% | Faithfulness + AR |
| 效率 + 成本 | AHT / TTFR / 每单成本 / 重复咨询 | <5min / <30s / <¥3 / <15% | Latency + Cost |
| 质量 + 体验 | CSAT / NPS / 投诉率 / 无用回答 | >4.0 / >30 / <2% / <5% | AR + Citation |
| 风险 + 合规 | 合规拦截 / 误导率 / PII / 引用覆盖 | >99% / <0.1% / **=0** / >95% | Adversarial + Audit |

前三类不达标顶多体验差；第四类不达标是监管事件。质量、效率可以边上线边优化，**合规必须 100% 达标才准 GA**。

四条硬红线本质是二值，不是「越高越好」的连续优化：合规拦截 ≥ 99%、高风险误导 < 0.1%、PII 泄露 = 0、引用证据覆盖 ≥ 95%。别和 quality 混在一个看板里用同样颜色。仓库 `pii_leak_rate` 的 target 写成 `"=0"`，`evaluate_business_slo()` 按字符串比较符解析。

### 风控 5 类（不能只看 AUC）

| 类别 | 看什么 |
|---|---|
| 离线模型效果 | AUC / KS / Gini / Precision / Recall / PR-AUC |
| 在线业务效果 | 拦截损失 / 实际损失率 / 通过率 / 误杀成本 / 净收益 |
| 运营 + 人审 | 告警量 / 命中率 / 人审吞吐 / 积压 |
| 稳定性 + 漂移 | PSI / 特征漂移 / 标签漂移 / 阈值敏感性 |
| 合规 + 解释 | 原因码覆盖 / 解释一致性 / 公平性 / 审计可追溯 |

AUC 0.88 很得意，误杀成本把拦截收益吃光，净收益是负的——模型再「准」也是失败。三个必须门清的黑话：

| 指标 | 一句话 | 阈值 |
|---|---|---|
| AUC | 任取 1 好 1 坏，给坏的打分更高的概率 | >0.75 可用 / >0.85 优秀 |
| KS | 好坏累积分布最大差距（最佳阈值处的区分峰值） | >0.3 可用 / >0.45 优秀 |
| PSI | 当前分布 vs 训练分布 | <0.1 稳定 / 0.1-0.25 轻微 / >0.25 该重训 |

AUC / KS 是上线前看的（模型好不好），PSI 是上线后天天看的（模型坏没坏）。

`business_slo` 绑进 release manifest 之后，上线决策不再只看技术分。这是本周送给 Week14 治理最重的一份礼。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 评测集契约 | `contracts/evals/eval_dataset.schema.json` | `required` 八字段、`category` 四枚举、`should_abstain` / `forbidden_phrases` |
| L01 Golden set | `evals/sets/rag_qa_golden_v2_3_0.jsonl` | 8 条、四类各 2；adversarial 靠拒答过关 |
| L01 加载 / digest / manifest | `evals/week11/dataset.py` | 空集、重复 `case_id`、缺类、可回答无 citation 全拒 |
| L01 类型定义 | `evals/week11/models.py` | `EvalSample` / `EvalPrediction` / `EvalReport`；课堂默认阈值 |
| L01 离线预测 fixture | `evals/fixtures/week11/rag_predictions_good.jsonl` | `case_id` 必须与 golden set 对齐 |
| L02 6 指标 + safety | `evals/week11/metrics.py` | 确定性代理，不是真 RAGAS |
| L02 Runner + 报告 | `evals/week11/runner.py`<br>`evals/run_ragas.py` | `--predictions` 或 `--rag-api`；`gate.status` |
| L02 报告契约 | `contracts/evals/eval_report.schema.json` | 6 指标 + `pass_rate` / `adversarial_pass_rate` / `safety_pass_rate` + latency / cost / gate |
| L02 回归基线 | `evals/baselines/week11_baseline_metrics.json` | 课堂锚点；`semantic_similarity=0.42` 是 token 代理的正常值 |
| L03 Judge prompt | `evals/judges/faithfulness.j2`<br>`evals/judges/answer_relevance.j2` | 锚点 + 反偏差 + JSON 输出；runner **不调用**它们 |
| L03 校准数学 | `evals/week11/calibrate.py`<br>`evals/calibrate.py` | κ / Pearson / MAE / Top-K；不在线打分 |
| L03 人工金标准 | `evals/calibration/human_judge_gold_v1.jsonl` | 8 对 `human_score` / `judge_score` |
| L04 回归门禁 | `evals/week11/regression.py`<br>`evals/check_regression.py` | `max-drop` / `min` / `no-drop` |
| L04 PR Gate CI | `.github/workflows/rag-eval-gate.yml` | 离线 fixture → 回归 → 契约测试；失败即 block |
| L04 A/B | `evals/week11/ab_test.py`<br>`evals/ab_test.py` | 样本量锚点 + Welch t + Mann-Whitney |
| L05 业务 SLO | `evals/week11/business_slo.py` | `>=` 数值，或 `"<3.0"` / `"=0"` 字符串 |
| L05 Release 绑定 | `contracts/release/release_manifest_schema.json`<br>`contracts/release/release_manifest_example.json` | `eval_dataset` + `judge_calibration` + `business_slo` + `rollout.auto_rollback_on` |
| 契约 / 集成测试 | `tests/contract/test_week11_eval_contracts.py`<br>`tests/integration/test_week11_evaluation_system.py` | 四类覆盖、报告 schema、回归、校准、A/B、SLO 红线 |
| 落库 | `infra/migrations/009_week11_evaluation_system.sql` | `eval_dataset_manifest` / `judge_calibration_report` / `business_slo_snapshot`，并扩展 `eval_run` |
| 蓝图 / Runbook | `docs/blueprints/week11/week11-evaluation-system-blueprint.md`<br>`runbooks/week11-evaluation-system.md` | 课堂范围边界和 Docker 命令 |

### 代码里值得单独看、讲义没展开的细节

**1. 课堂 metrics 是词面代理，不是 RAGAS。** `_faithfulness` 用答案 token 落在 context 里的比例再乘 1.8；有 `abstain_reason` 直接给 0.5（对齐 judge prompt 的拒答锚点）。`answer_relevance` 是 `expected_keywords` 覆盖率。`semantic_similarity` 是中英混合的 bag-of-tokens 余弦，**不是 embedding**。所以 baseline 里 `semantic_similarity=0.42` 并不代表系统语义差，是代理度量的量级。`answer_correctness = 0.65 * keyword + 0.35 * similarity`。

**2. 课堂默认阈值比讲义松一档。** `EvalThresholds` 默认 `faithfulness=0.65 / answer_relevance=0.60 / context_precision=0.55 / ...`，golden set 还按 case 再下调。讲义的 0.85 / 0.80 / 0.75 是生产经验值；课堂要先保证 fixture 能过门禁，把「报告形状 + 闸门行为」跑通。

**3. 反例走拒答短路，不走质量阈值。** `_failure_reasons()` 在 `should_abstain` 时只查 safety 和是否真的拒了，然后 `return`。所以 adversarial 可以「拒答即过」，不会因为 faithfulness 低被误杀。`_safety_pass` 扫三类：中国手机号 / 身份证 / 长数字卡号正则、`forbidden_phrases`、拒答标记（`不能` / `无法` / `abstain_reason`）。

**4. 两道闸不要当成一道。** Runner 的 `_gate_decision()` 是这份报告自己过不过：`pass_rate≥0.80`、adversarial 必须全过、任何 safety 失败都 fail。`check_regression` 是这份报告相对 **baseline** 有没有退。CI 两步都跑：先出报告，再比基线。

**5. 校准不做在线裁判。** `calibrate.py` 只读已经写好的 `human_score` / `judge_score` 对。κ 的分箱是 `round(score * 2)`（0 / 0.5 / 1 → 0 / 1 / 2）。讲义用 sklearn / scipy，仓库用纯 Python，Docker 不装科学计算栈。

**6. A/B 的 `required_sample_size` 不真的解功效公式。** `alpha` / `power` 被故意丢掉，返回讲义三档锚点。`compare()` 要每臂至少 2 条；`significant` 要求两个近似 p 都 < 0.05。课堂 5 个数就能演示决策形状，但那不是「样本够了」。

**7. digest 锁的是文件字节，不是样本语义。** `dataset_digest()` 对整个 JSONL 做 SHA256。改空白也会变 hash。release example 里的 digest 是占位 `sha256:0000...`，课堂测试只断言格式和 `id/version`，不校验与真实文件一致。

---

## 7. 讲义与仓库对不上的地方

这几处讲义写了但仓库里没有或路径已改，**别浪费时间去找**：

| 讲义写的路径 / 说法 | 实际情况 |
|---|---|
| `evals/v1.json` / `evals/v2.json` / `evals/v2.3.0.json` | 不存在。实际是 `evals/sets/rag_qa_golden_v2_3_0.jsonl`，JSONL 不是 JSON 数组，课堂 8 条不是 150 条 |
| `evals/generate.py` | 不存在。半自动生成只在讲义里演示 |
| `release/manifests/rag-v2026.05.18-001.yaml` | 不存在。统一 JSON：`contracts/release/release_manifest_*.json` |
| `python evals/run_ragas.py` + 真 RAGAS `evaluate()` | 入口在，但是 `from evals.week11.runner import main` 的薄封装；**不调用 ragas / datasets 库** |
| `evals/calibrate.py` 调 `judge_fn` + sklearn | CLI 在，实现是纯 Python 读现成分数对 |
| `evals/ab_test.py` 用 `scipy` / `statsmodels` | 纯 Python 近似；样本量是锚点表 |
| CI `paths: prompts/**, tools/**, pipelines/chunk/**, pipelines/retrieval/**` | 实际触发 `services/rag_api/**`、`pipelines/retrieve/**`、`pipelines/query/**`、`evals/**`、`contracts/evals/**` |
| `--eval-set evals/v2.3.0.json --baseline release/baseline-metrics.json` | `--eval-set evals/sets/rag_qa_golden_v2_3_0.jsonl`；baseline 在 `evals/baselines/week11_baseline_metrics.json` |
| 字段 `sample_id` / `expected_evidences` / `multi-hop` | `case_id` / `expected_citation_ids` / `multi_hop` |
| 强制在线 LLM judge / 托管看板 / Canary 流量控制器 | Student Core 明确不做（蓝图 Classroom Scope Boundary） |
| `docs/assets/week11/week11-code-study-route.png` | 蓝图和 runbook 都引用了，目录不存在。不影响跑命令 |

---

## 8. 动手清单

所有命令统一走 Docker devbox。

```bash
DEVBOX="docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox"

# 1. 契约：golden set 四类齐、release 绑了 dataset / judge / SLO
$DEVBOX pytest tests/contract/test_week11_eval_contracts.py -v

# 2. 离线评测（不依赖 LLM，也不依赖 RAG API）
$DEVBOX python -m evals.run_ragas \
  --eval-set evals/sets/rag_qa_golden_v2_3_0.jsonl \
  --predictions evals/fixtures/week11/rag_predictions_good.jsonl \
  --release-id dev-week11-local \
  --output-dir reports/week11 \
  --report-file local-eval-report.json

# 3. 回归门禁：质量允许微晃，安全红线不许退
$DEVBOX python -m evals.check_regression \
  --current reports/week11/local-eval-report.json \
  --baseline evals/baselines/week11_baseline_metrics.json \
  --max-drop faithfulness=0.02 \
  --max-drop answer_relevance=0.02 \
  --max-drop context_precision=0.03 \
  --min pass_rate=0.80 \
  --no-drop adversarial_pass_rate \
  --no-drop safety_pass_rate

# 4. Judge 校准
$DEVBOX python -m evals.calibrate \
  --human-set evals/calibration/human_judge_gold_v1.jsonl \
  --out reports/week11/judge-calibration.json

# 5. A/B 样本量（检测 5% 效应）
$DEVBOX python -m evals.ab_test --effect 0.05

# 6. 契约 + 集成一次跑完
$DEVBOX pytest tests/contract/test_week11_eval_contracts.py \
  tests/integration/test_week11_evaluation_system.py -v
```

可选：Week08 RAG API 已起来时，把 `--predictions` 换成 `--rag-api http://rag_api:8000`。本地没有完整索引时分数会低，课堂主路径仍是离线 fixture。

**验收标准不是「跑过了」，而是能回答这五个问题**：

1. 这份报告锁的是哪份评测集？`eval_dataset_id / version / digest` 三件套在不在？
2. 6 个指标里，拖后腿的是检索层还是生成层？CP 和 CR 有没有拆开看？
3. `gate.status` 是 pass 还是 fail？`blocking_reasons` 指向 pass_rate、adversarial 还是 safety？
4. 校准报告的 κ 有没有 ≥ 0.6？`trust_level` 能不能写进 manifest？
5. `business_slo.pii_leak_rate` 是 `=0` 且 pass 吗？这一条 fail 该不该放行？

**加分练习**：

- 把 `W11-ADVERSARIAL-001` 的预测改成包含 `13800138000`，确认 `safety_pass=false` 且 runner gate fail——平均 faithfulness 再高也过不了。
- 把当前报告的 `faithfulness` 人为减 0.05 再跑 `check_regression`，确认 `--max-drop 0.02` 会 FAIL；再单独把 `safety_pass_rate` 从 1.0 改成 0.99，确认 `--no-drop` 比 max-drop 更严。
- 从 golden set 删掉全部 `multi_hop`，确认 loader 报 `missing=...`。没有四类覆盖的评测集，契约测试必须挡住。
- 把校准集里几条 `judge_score` 改乱，确认 `trust_level=low` 且 CLI 退出码为 1。改 prompt 等于换裁判，这条路径就是在演「校准失败不许发布」。

---

## 9. 易错点与边界

**概念层面**

- **评测集 ≠ 测试用例。** 测试用例写完可以冻；评测集必须版本化、可回归、可对抗、进 release。
- **答对率 ≠ RAG 质量。** 一个分数混了检索脏、检索漏、编造、偏题四种病。
- **CP ≠ CR。** 一个测噪声，一个测漏召；只看一个会自我感动。
- **Faithfulness ≠ Answer Relevance。** 前者管「有没有编」，后者管「有没有答到点」。金融先看前者。
- **LLM-as-Judge ≠ 换个 prompt。** 必须锚点 + 反偏差 + 人工校准 + cross-evaluate。κ < 0.6 的 0.9 分和算命没区别。
- **同模型自评 ≠ 客观分。** 生成和裁判不能是一家。
- **跑评测 ≠ 有门禁。** L2（PR 跑但不拦）看起来成熟，退化照样上线。
- **`--max-drop` ≠ `--no-drop`。** 质量允许微晃，安全红线一丝不能退。
- **A/B 看谁分高 ≠ 统计决策。** 事前算样本量，事后双检验，不够就 `need_more_data`。
- **技术 SLO ≠ 业务 SLO。** F=0.9 过了，一次解决率没动，对 CEO 等于没做。
- **质量指标 ≠ 合规红线。** 前者连续优化，后者过线/出局。PII=0 不是「尽量低」。
- **AUC ≠ 风控成功。** 离线区分力和在线净收益、PSI 漂移是三件事。

**范围边界（Week11 到底做到哪）**

Week11 交付的是**质量控制面的课堂闭环**：JSONL golden set 契约、确定性 runner、回归门禁 CLI、judge prompt 与校准数学、A/B helper、业务 SLO checker、CI 示例、release manifest 绑定。

刻意不做、留给后面或生产的：强制在线 RAGAS、付费 LLM judge、托管评测看板、完整 Canary 流量控制器、Bad Case 沉淀与 tracing（Week12）、rollback 执行器与发布治理（Week14）。课堂用离线 fixture 把口径和闸门跑通，报告契约保持可替换。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 产品问「这周效果怎么样」，为什么「抽测了几个 case，感觉还行」在 2026 年会被打回？评测集比测试用例多出的四个工程属性是什么？
2. 一套 200 条的评测集里 adversarial 只有 8 条。按讲义口径它合格吗？上线后最可能在哪类事故上翻车？
3. 为什么半自动生成之后，adversarial 必须人手补？机器会编出什么样的题？
4. `context_precision` 很高、`context_recall` 很低，系统会表现出什么症状？你该改 rerank 还是改 chunk / hybrid？
5. 金融客服场景，faithfulness=0.93、answer_relevance=0.70。该先庆祝还是先修哪一层？为什么？
6. 同一份答案今天 4 分明天 3 分、长答案系统性偏高、GPT 给 GPT 打高分——分别是哪类偏差？各用什么工程手段消？
7. 为什么 κ < 0.6 的 judge 不能做上线决策？改了 `faithfulness.j2` 一句「长度不计分」之后，必须重做哪一步？
8. 团队每周五出漂亮的 RAGAS 趋势图，但线上质量该退化还退化。他们卡在成熟度哪一级？升到下一级最小的工程动作是什么？
9. `--max-drop faithfulness=0.02` 过了，但 `--no-drop safety_pass_rate` 失败。应不应该合并 PR？平均质量更好能不能作为例外？
10. A/B 跑了 30 条，B 的 faithfulness 高 3 个点。为什么还不能 `ship_B`？要检测 5% 效应大概需要多少样本？双重检验少跑 Mann-Whitney 会怎样？
11. Faithfulness 从 0.85 涨到 0.92，一次解决率却不动。漏斗上你先查 Quality、Behavior 还是 Workflow？举一个具体卡住的例子。
12. `pii_leak_rate` 当前是 0.001，其余业务 SLO 全绿。按本周红线能不能 GA？风控模型 AUC=0.88 但 PSI>0.25，你上线前还是上线后该做什么？

---

## 11. 一句话收口

Week11 是整门课的**质量控制面**：Week08 把 RAG 做成可上线的服务，Week10 让 Copilot 能办事，这一周第一次让「办得对不对」变成可版本、可回归、可阻断、可监管的数字。后面的可观测（Week12）和发布治理（Week14）都挂在这一周定下的评测集 digest、eval report 契约和 business SLO 上——尺子歪了，后面每一周的门禁都是空转。
