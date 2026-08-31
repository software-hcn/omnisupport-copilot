# Week 14 · 治理与版本：数据像代码一样发布、回滚、追责

> **一句话**：把前 13 周攒下来的版本字段收成一条可执行的发布控制面——一次发布锁死 data + index + prompt + model + skills + graph，出事只切一个环境指针，5 秒回到昨天那套组合。
>
> 讲义：`pdf/doc/Week14-治理与版本·数据像代码一样发布回滚追责.pdf`（46 页 / 5 课时）

---

## 0. 本周主干

五节课是一条发布链，不是五个治理话题。每一节的产出都是下一节的输入：

```
L01 Branch     数据也能 Git：branch / commit / tag / merge / revert
      ↓
L02 Bind       6 类对象锁进一个 immutable release_id
      ↓
L03 Impact     改之前先看爆炸半径，血缘接到 OpenLineage
      ↓
L04 Compliance 工程产物自动汇聚成证据包，缺的绝不编
      ↓
L05 Canary     5% → 25% → 50% → 100%；回滚只切指针
      ↓
               Week15 成本 / 性能 / 上线收官
```

课堂口令值得单独记：

> 业务说"昨天回答没问题、今天突然不对"——你能不能在 5 秒内回到昨天那套 data + index + prompt + model？

仓库把这句口令落成**指针模型**：先生成一份不可变 manifest，再原子改 `release_environment_pointer`。服务只认当前指针那一代的全部组件 ID。回滚也是改指针，不删任何 release 证据。

| 口令 | 挡住什么误解 |
|---|---|
| **lakeFS 管湖层分支，Iceberg 管表快照** | 当成二选一，白白丢一半能力 |
| **一次发布 = 六类对象一次锁定** | 数据、索引、Prompt、模型各自发版，出现半发布窗口 |
| **回滚切的是指针，不是重部署** | 出事去重建索引、重拉模型，回到小时级 |
| **红线一票否决，窗口不够就 hold** | 质量涨了也放行；样本不够就升档 |

---

## 1. L01 · Branch：把 Git 模型搬到数据上

### 核心论点

覆盖式更新 + 捞备份，是代码世界早就开除的做法。产品手册被覆盖、当晚 RAG 答错、旧字节没留——这不是运维倒霉，是数据还停在 G1/G2。

| 代际 | 核心能力 | 解决什么 | 局限 |
|---|---|---|---|
| G1 备份 | 定期全量复制 | 大事故能恢复 | 粒度粗、时延高、不能并行开发 |
| G2 快照 | Iceberg / Delta time travel | 可读历史时刻 | 主分支唯一，一改影响所有人 |
| G3 分支 | lakeFS Git-like branch | 并行、隔离、合并、秒级 revert | 需要 PR 流程配合，不是换掉 Lakehouse |

升到 G3 **不用换 Iceberg，也不用换 S3**。lakeFS 是盖在对象存储上的元数据层，COW 开分支几乎零复制。

### Git 概念 1:1 对应

| Git | 数据侧 | OmniSupport 约定 |
|---|---|---|
| branch | 隔离的数据工作区 | `main` / `staging` / `experiment`；仓库策略还有 `feature/{ticket}-{owner}` |
| commit | 一次数据变更 | 必带 `actor` / `change_ticket` / `data_contract_version` / `trace_id` |
| tag | 不可变锚点 | 生产只允许 `refs/tags/data-*` |
| merge | 分支合入主干 | 合入前要过 contract / quality / impact / owner |
| revert | 切回某次 commit | 用户不应感到中间态 |

讲义给的判断清单（符合 3 项以上再上 lakeFS）：团队 > 5 人、每周数据 PR > 5、近半年回滚困难事故 > 3、已有 Git PR 文化、监管要版本审计。不到 2 项就别上——Iceberg time travel 先撑着。

### 分层，不是替代

| 层 | 解决什么 | 工具 | 本仓库 |
|---|---|---|---|
| Storage | 原始字节 | S3 / MinIO | 对象存储，不在本周新建 |
| Table Format | 表 schema / 快照 / 演进 | Iceberg | `iceberg_snapshot_ids` 写进 manifest |
| Repo / Branch | 跨表跨格式的分支隔离 | lakeFS | **只有策略文件**，见第 7 节 |
| Catalog | 多引擎目录 | Polaris / Unity / Nessie | 讲义 2026 选型，仓库未部署 |

`data/lakefs/config.yaml` 把这层说清楚了：生产绑定字段是 `spec.components.data.lakefs_ref`，类型必须是 tag，**禁止把 branch ref 写进 prod**。

---

## 2. L02 · Bind：6 类对象锁进一个 release_id

### 核心论点

传统软件 `git tag` = 行为确定。AI 不是：同一份代码，换数据、换 Prompt、换模型快照，行为可以完全不同。分别发版几乎一定踩坑——合规来问"那条回答当时用的哪份数据、哪个 Prompt、哪个模型"，现场要拼两天。

可部署单元不是一个容器，也不是一份 Prompt。它是一份 **immutable manifest**，一次绑死：

| 组件 | 锁什么 | 影响 | 来自哪周 |
|---|---|---|---|
| **data** | lakeFS ref + Iceberg snapshot | 召回内容 | Week04 / 06 / 07 |
| **index** | 向量 / 词法索引 release，且 `data_release_id` 必须等于 data 的 `release_id` | 召回集合 | Week07 / 08 |
| **prompt** | 模板版本表 | 生成行为 | Week08 |
| **model** | provider + 钉死的 snapshot + system card | 生成行为 | 本周收口 |
| **skills** | Skill Pack 版本列表 | Agent 能调什么 | Week09 / 10 |
| **graph** | GraphRAG schema 版本 | 实体关系归纳 | Week13 |

讲义把这 6 类再加上 **eval / business_slo / rollout**，叫"9 大段"。仓库 v2 还多了一段 `governance`（变更单、数据分级、审批角色）。少绑一类，就留下半发布窗口。

### 命名：别用手写 UUID

| 策略 | 示例 | 结论 |
|---|---|---|
| 纯时间戳 | `2026-05-18T15-00-00Z` | 人读不出"是什么" |
| SemVer | `v3.2.1` | 不可按日单调，易冲突 |
| UUID | `rel-a3f4b2c1` | 半年后无法排序 |
| Hybrid（讲义推荐） | `rag-v2026.05.18-001` | 可读 + 可解析 |
| **仓库实际** | `omni-dev-v2026.07.20-001` | 服务名改成 `omni-{env}`，环境写进 ID |

`release/generator.py` 按 UTC 日期在输出目录里递增序号，**绝不要手写**。生成时会把 spec 里每个 `source_paths` 收成 `artifact_digests`；缺文件、eval 没过、schema 不合法、目标 JSON 已存在，全部失败。SHA 必须是真实 `git rev-parse HEAD`，容器解析不了 host 的 worktree，所以 runbook 要求从宿主机注入。

### 供应链三件小事

| 能力 | 讲义要求 | 仓库怎么做 |
|---|---|---|
| System card | 能力、限制、风险随 release 走 | `docs/blueprints/week14/model-system-card.md`，本地确定性模型，不能授权 tool、不能做发布决策 |
| 快照钉死 | 禁用滚动别名 | prod 拒绝 `*:latest` / `*@latest` |
| 制品签名 | Sigstore / cosign | Student Core 用 HMAC-SHA256；prod 必须签名；密钥走 `WEEK14_RELEASE_SIGNING_KEY` |

`approved_by` 在 prod 强制四人眼：创建者和审批者不能是同一个人。digest 签的是去掉 `integrity` 之后的 canonical JSON——完整性字段自己不签自己。

### 指针为什么必须只有一个

试图分别更新 data / index / prompt / model / skills / graph，中间一定存在"半套新、半套旧"。Week14 的做法：manifest 不可变，环境只改一行 pointer。rollback 把 pointer 指回**直接前一版**，generation + 1，审计链不断。

---

## 3. L03 · Impact：血缘用来防，不是用来验尸

### 核心论点

90% 的重大事故公式只有一句：**上游改了 + 下游没人知道 = 事故**。开会通知破不了这个公式，因为上游根本不知道下游有谁。血缘的最大价值是改之前 30 秒出影响报告，不是事后画 Confluence 图。

| 方向 | 问什么 | 工程用途 |
|---|---|---|
| Upstream 向上 | 这答案是哪来的 | 故障复盘 / 合规审计 |
| Downstream 向下 | 改了它影响谁 | 变更影响分析、PR 卡点 |
| Lateral 横向 | 还有谁用这字段 | 协调改造 |

讲义把 AI 血缘拆成五层：Source → Data（列级）→ Index → Service → Action（Agent 动作）。列级比表级准一个数量级；Agent 会改数据，动作不进血缘，出事连"谁改的"都查不到。

五个反模式：手动维护、只到表级、影响分析不接 PR、Agent 动作不入血缘、asset 没有 owner。失败项目几乎都死在前两个。

### 仓库把"全链路"收成 manifest 差分

`tools/impact_analysis.py` **没有** DataHub 客户端，也不递归 47 个 dashboard。它对比 candidate 与 previous 的 6 个 component，用一张硬编码爆炸半径表：

| 变更组件 | 风险 | 下游 | 必跑测试周 |
|---|---|---|---|
| data | critical | index / graph / eval / rag_api | 04 / 07 / 08 / 11 / 13 |
| index | high | eval / rag_api | 08 / 11 |
| prompt | high | eval / rag_api | 08 / 11 |
| model | critical | eval / rag_api / tool_api | 08 / 10 / 11 |
| skills | high | agent / tool_api | 09 / 10 |
| graph | high | graphrag / eval / rag_api | 13 / 11 |

风险 ≥ high 要 `service_owner`，≥ critical 再加 `data_or_model_owner`。不传 `--previous` 时旧组件为空，**六个都会被标成 changed**——课堂第一次生成可以跑，真晋升必须传上一份。

### OpenLineage：六入一出

`governance/openlineage.py` 把一次 governed release 收成标准 `RunEvent`：六个 component 当 inputs，当前环境的 `release_id` 当唯一 output。可以写本地 fixture，也可以 POST 到真实 backend。这是协议适配，不是 Marquez / DataHub 集群，也没有讲义里的 `AgentActionFacet`。

---

## 4. L04 · Compliance：白皮书是工程产物的商业化输出

### 核心论点

2026 年卡上线的经常不是模型，是法务要一份可解释、可追溯、可审计的材料。正确做法不是外包写三周，而是把 Week11–14 已经产出的 manifest / 评测 / 灰度 / 血缘 **按监管视角重排**。

讲义纠正了三件过时事实（别拿废令去跟法务对齐）：美国 EO 14110 已于 2025-01-20 废除；EU AI Act 高风险义务推迟、GPAI / 标识 2026-08 起执法；中国 GB 45438-2025 内容标识 2025-09-01 起强制。跨国业务按最严（EU 可追溯底座）搭，再叠当地硬门槛。

白皮书 8 段全部来自已有产物：

| 块 | 段落 | 审计员要看什么 | 来源 |
|---|---|---|---|
| Overview | 系统 / 数据契约 / 模型 | 做了什么 | 项目文档 + contract + system card |
| Evidence | manifest / 评测 / trace 抽样 | 工程证据 | Week11 / 12 / 14 |
| Risk | 缓解 + 应急回滚 | 出事能控 | Canary 红线 + runbook + postmortem |

### 仓库生成器更狠：缺证据就 fail，绝不编

`release/compliance/generator.py` 先校验 manifest digest / 签名，再按 `artifact_digests` 重哈希每一个锁定文件，digest 对不上直接抛错。额外传入的 impact / eval / canary 文件只登记真实路径和 SHA。`prod` 必须凑齐 impact + eval + rollout；缺了 `completeness.status = fail`，进程退出码 2。输出是 `compliance-evidence-pack.json` + `release-whitepaper.md` 两份，markdown 写明 **Missing evidence is never synthesized**。

没有 `framework=eu_ai_act` 这种多视角模板，也没有 Sigstore 公证、RFC3161 时间戳、7 年留存导出。那些是生产边界，不是 Student Core。

### 红线是 manifest 字段，不是建议

讲义四类红线：PII 泄露、越权访问、违规话术、未授权 tool。本地 spec 先落地两条可执行规则：

```yaml
red_lines:
  - {metric: pii_leak_rate, operator: ">", threshold: 0}
  - {metric: safety_pass_rate, operator: "<", threshold: 1.0}
```

质量涨了但 PII 漏了，仍然 rollback。缺红线指标本身也当 rollback——观测不完整视为不安全。

---

## 5. L05 · Canary：高频低风险，回滚是指针切换

### 三种发布模式

| 模式 | 做法 | 风险 | 何时用 |
|---|---|---|---|
| Big Bang | 一次 100% | 极高 | 反模式 |
| Blue-Green | 备好再切 100% | 中，无渐进 | 基础设施类 |
| Canary | 5 → 25 → 50 → 100 | 最低 | AI 系统默认 |

SRE 口令：release often, release small。憋季度大版本，出事分不清是 Prompt、数据还是模型的锅。

### 四阶段：指标层层加码

讲义按"观察时长 + 看什么"分层；仓库把每档写成可执行的 `min_samples` / `min_observation_minutes` / `gates` / `baseline_guards`：

| 流量 | 最少样本 | 最少观察 | 质量门 | 相对基线 |
|---|---|---|---|---|
| 5% | 20 | 10 min | correctness ≥ 0.75，p99 ≤ 2500ms | 允许 -0.02 |
| 25% | 100 | 30 min | ≥ 0.78，p99 ≤ 2200ms | 允许 -0.01 |
| 50% | 300 | 60 min | ≥ 0.80，p99 ≤ 2000ms | 不允许退化 |
| 100% | 1000 | 120 min | ≥ 0.82，p99 ≤ 1800ms | 不允许退化 |

5% 样本太小，质量指标噪声大——所以先看能一票否决的红线，流量上去再看软指标。

### 决策顺序（代码比讲义更硬）

`rollout/canary.py` 固定四步，顺序不能改：

1. **红线**（含缺指标）→ `rollback`
2. **样本 / 观察窗不够** → `hold`（代码里绝不豁免）
3. **阶段 gate 或 baseline_guard 失败** → `hold`（讲义示例写成了质量回归直接 rollback，仓库故意更保守：质量问题先停，只有合规/安全红线才自动切回）
4. 全过 → `promote`

决策必须绑 `release_id` + `manifest_digest`。观测载荷若自带另一个 `release_id`，命令失败而不是默默改绑。fixture `canary_red_line_breach.json` 里 correctness 从 0.83 升到 0.92，仍因 `pii_leak_rate: 0.01` 回滚——这就是红线优先的验收。

### 三种回滚速度

| 机制 | 做法 | 速度 |
|---|---|---|
| 重部署 | 回代码、重启、重建索引 | 小时级 |
| 配置滚动 | 改配置再滚动 | 分钟级 |
| **release 指针** | router 指向旧 manifest | 秒级 |

`rollout/rollback.py` 只做第三种：调用 registry，要求 `current` 必须等于此刻 pointer，`target` 必须是当前 release 的 **direct previous**。这两条挡住"回滚到无关版本"和"两个值班同时切"。SQL 里 `generation` 单调递增；审计事件用 `previous_event_digest` 拉链，UPDATE/DELETE 触发器直接拒绝。

prod 升稳定指针之前，5% / 25% / 50% / 100% 的**最新**决策必须全是 `promote`。缺档、乱序、hold、绑错 digest，全在代码里拦住，不是靠约定。

发布成熟度 L0 手动 → L4 全自动。课堂这条链能证明 L4 的控制面，流量分发本身仍留给生产的 Argo Rollouts / OpenFeature，仓库不自建灰度代理。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 lakeFS 策略（不是集群） | `data/lakefs/config.yaml` | branch 命名、merge 四道门、prod 只许 tag |
| L02 发布 spec | `release/specs/week14_local.yaml` | 6 组件 `source_paths`、四阶段、两条红线 |
| L02 自动生成器 | `release/generator.py` | `omni-{env}-v日期-序号`、digest、文件不可覆写 |
| L02 完整性 | `release/integrity.py` | canonical JSON、HMAC、`algorithm: none` |
| L02 发布策略 | `release/policy.py` | 六组件齐全、index 绑 data、prod 四人眼 + 签名 + tag |
| L02 v2 契约 | `contracts/release/release_manifest_v2.schema.json` | `kind: GovernedRelease`，`additionalProperties: false` |
| L02 v1 兼容契约 | `contracts/release/release_manifest_schema.json` | Week01–13 旧练习，**新晋升不要用** |
| L02 v1 示例 | `contracts/release/release_manifest_example.json` | 旧 `dev-YYYYMMDD-seq` 形态 |
| L02 schema 入口 | `release/schema.py` | manifest / canary 校验 |
| L02 模型卡片 | `docs/blueprints/week14/model-system-card.md` | 钉死 snapshot、能力边界 |
| L02 注册表 + 指针 | `release/registry.py` | register / promote / record-rollout / 审计拉链 |
| L03 影响分析 | `tools/impact_analysis.py` | `IMPACT_MAP`，不是 DataHub |
| L03 影响报告契约 | `contracts/release/release_impact_report.schema.json` | `review_required` / `no_change` |
| L03 OpenLineage | `governance/openlineage.py` | 六个 input、一个 governed output |
| L04 证据包 | `release/compliance/generator.py` | 缺证据 fail closed，不合成 |
| L04 证据契约 | `contracts/release/compliance_evidence_pack.schema.json` | `completeness.missing` |
| L05 Canary 引擎 | `rollout/canary.py` | 红线 → hold 窗口 → gate |
| L05 决策契约 | `contracts/release/canary_decision.schema.json` | `promote` / `hold` / `rollback` |
| L05 正反 fixture | `tests/fixtures/week14/canary_5_percent_pass.json`<br>`tests/fixtures/week14/canary_red_line_breach.json` | 质量涨了仍可 rollback |
| L05 回滚 CLI | `rollout/rollback.py` | 只切 pointer |
| 表结构 | `infra/migrations/011_week14_governed_release.sql` | 四张表 + 不可变触发器 |
| CI 门禁 | `.github/workflows/week14-governance-gate.yml` | 生成 → impact → canary → lineage → 证据包 |
| 契约测试 | `tests/contract/test_week14_governed_release_contracts.py` | 篡改、四人眼、digest 链 |
| 集成测试 | `tests/integration/test_week14_governed_release.py` | 真 Postgres：晋升、回滚、generation=3 |
| 蓝图 / Runbook | `docs/blueprints/week14/week14-governed-release-blueprint.md`<br>`runbooks/week14-governed-release.md` | 控制面阅读顺序和课堂命令 |
| spec 锁定的下游产物 | `services/rag_api/app/prompts/prompt_manifest.yml`<br>`skills/release-check/SKILL.md`<br>`pipelines/graph/schema.yaml`<br>`evals/baselines/week11_baseline_metrics.json`<br>`observability/slo/week12_slo.yaml` | 生成器会算 SHA，缺一个就建不出 release |

### 代码里几个值得单独看的细节

**prod 策略**写在 `release/policy.py`，讲义没逐条展开，但体现了本周的风险偏好：

```python
REQUIRED_COMPONENTS = {"data", "index", "prompt", "model", "skills", "graph"}
# eval gate、business SLO 必须 pass
# rollout.stages 必须恰好是 5, 25, 50, 100
# 至少一条 red_line
# prod: approved_by ≠ created_by，必须签名
# prod: lakefs_ref 以 refs/tags/ 开头，模型 snapshot 禁止 latest
```

**四张表的职责**不要混：`governed_release_manifest` 存不可变正文；`release_environment_pointer` 是每个环境唯一的"现在指向谁"；`release_rollout_event` 按阶段追加决策；`release_audit_event` 用 digest 拉链。后三张里清单和审计禁止 UPDATE/DELETE。

**v1 继续活着**：`release_manifest` 旧表 / 旧 schema 给 Week01–13 练习用。新晋升走 `governed_release_manifest` + pointer。不要改名去"统一"，那会把前面各周命令打坏。

---

## 7. 讲义与仓库对不上的地方

这几处讲义写了但仓库里没有或刻意做成适配层，**别浪费时间去找完整产品**：

| 讲义写的 | 实际情况 |
|---|---|
| `lakectl branch/commit/merge/revert`，`lakefs://omni/...` | **没有 lakeFS 集群。** `infra/docker-compose.yml` 无 lakefs 服务。只有 `data/lakefs/config.yaml`：策略、分支命名、合入门禁、prod 禁止 branch ref。endpoint 默认 `http://lakefs:8000`，是给生产另外部署用的占位，不是本仓库能 curl 的服务 |
| `release/manifests/rag-v2026.05.18-001.yaml`，`apiVersion: omnisupport.rag/v5` | 目录不存在。输入是 `release/specs/week14_local.yaml`，输出是 `artifacts/releases/omni-{env}-v*.json`，`api_version: omnisupport.ai/v2` |
| `omni release create` / `omni eval run --branch` / `omni impact analyze` / `omni compliance generate` / `omni release rollback` | 仓库没有 `omni` CLI。一律 `python -m release.generator` 等模块入口，命令以 runbook 为准 |
| `pipelines/update_docs.py` | 不存在 |
| `pipelines/lineage/extended.py`、`AgentActionFacet`、DataHubClient | 不存在。血缘是 `governance/openlineage.py` 的 6+1 事件；影响分析是 manifest 差分 + `IMPACT_MAP` |
| Sigstore / cosign / ed25519 / RFC3161 | Student Core 用 HMAC。蓝图写明生产应换成外部 KMS/Sigstore，密钥不进仓库 |
| 同一 release 生成 EU / 中国 / NIST 三份白皮书 | 只有证据包 + 一页 markdown 清单，按文件名识别 impact/eval/rollout 是否齐全 |
| Argo Rollouts / Flagger / OpenFeature 流量分发 | 决策引擎和 pointer 在仓库里；真正把 5% 流量切出去的代理不在 Student Core |
| `docs/assets/week14/week14-governed-release-control-plane.png` | 蓝图和 runbook 都引用，**目录不存在**。不影响跑命令，阅读顺序以蓝图里的 ASCII 路径为准 |

兼容性边界（官方口径，不是疏漏）：v2 是新契约，不重命名旧表、旧 API、旧课时命令。lakeFS 与 Iceberg 并存，谁也不替代谁。

---

## 8. 动手清单

所有命令统一走 Docker devbox。先起 Postgres 并让 `db_migrate` 应用 `011`——旧 volume 不会重放 `docker-entrypoint-initdb.d`。

```bash
# 1. 迁移（011 只应被 db_migrate 执行一次，不要手工再跑）
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml up -d postgres db_migrate

# 2. 从真实仓库产物生成不可变 manifest（git SHA 必须从宿主机注入）
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m release.generator \
    --spec release/specs/week14_local.yaml \
    --environment dev \
    --created-by "$USER" \
    --git-sha "$(git rev-parse HEAD)" \
    --output-dir artifacts/releases

# 3. 影响分析（真晋升再加 --previous）
RELEASE_MANIFEST=$(ls -t artifacts/releases/*.json | head -1)
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m tools.impact_analysis \
    --candidate "$RELEASE_MANIFEST" \
    --output artifacts/releases/impact-report.json

# 4. 5% canary：期望 promote；换成 canary_red_line_breach.json 必须 rollback
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m rollout.canary \
    --manifest "$RELEASE_MANIFEST" \
    --observation tests/fixtures/week14/canary_5_percent_pass.json \
    --output artifacts/releases/canary-5.json

# 5. 注册 / 记录决策 / 晋升 / 回滚 / OpenLineage —— 见 runbooks/week14-governed-release.md 第 5 节

# 6. 合规证据包
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m release.compliance.generator \
    --manifest "$RELEASE_MANIFEST" \
    --evidence artifacts/releases/impact-report.json \
    --evidence evals/baselines/week11_baseline_metrics.json \
    --evidence artifacts/releases/canary-5.json \
    --output-dir artifacts/compliance

# 7. 契约 + 真库集成测试
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/contract/test_week14_governed_release_contracts.py \
         tests/integration/test_week14_governed_release.py -v
```

Podman 用户把 `docker compose` 换成 `podman compose`，代码路径相同。

**验收标准不是"跑过了"，而是能回答这五个问题**：

1. 生成的 `release_id` 是哪一个？环境有没有写进 ID？六个组件是不是都有 `artifact_digests`？
2. 不传 `--previous` 的影响报告为什么会把六个组件都标成 changed？真晋升缺了它会怎样？
3. 红线 fixture 里 correctness 明显更好，决策为什么仍是 `rollback`？缺 `pii_leak_rate` 呢？
4. 集成测试里第二次 promote 之后 rollback，active 是否回到第一版、`generation` 是否变成 3？审计链的 `previous_event_digest` 是否首尾相接？
5. 证据包有没有编造不存在的评测？把 impact 文件拿掉，`completeness` 是不是 fail？

**加分练习**：

- 生成后再改 manifest 里任意字段，跑 `verify_manifest`，确认 digest mismatch
- 对 prod 只记录 5% 就 `promote`，确认被 `production promotion requires` 拦住
- 把 rollback 目标改成非直接前一版，确认 `direct previous release` 拒绝
- 观测 JSON 里写一个别人的 `release_id`，确认 canary 失败关闭而不是改绑

### 动手清单参考答案

先自己答完上面的验收问题和加分练习，再往下对。

1. `release_id` 形如 `omni-dev-v日期-序号`，环境写进 ID（`omni-{env}`），不要手写 UUID。六个组件 data / index / prompt / model / skills / graph 都必须有 `artifact_digests`——一个 `release_id` 绑死这 6 类，少一类就留半发布窗口。本仓库没有 lakeFS 集群，只有 `data/lakefs/config.yaml` 策略，加上 `release_environment_pointer` 这一行指针；生成器算出的是不可变 manifest，真正「发布」是改指针。
2. 不传 `--previous` 时旧组件视为空，六个都会被标成 changed。课堂第一次生成可以跑；真晋升必须传上一份，否则爆炸半径被高估、审批角色被误触发，影响分析失去「改了什么」的差分意义。
3. 红线优先于质量变好。`canary_red_line_breach.json` 里 correctness 从 0.83 升到 0.92，仍因 `pii_leak_rate: 0.01` 决策 `rollback`。缺 `pii_leak_rate` 不能当成 0，代码视为 `missing_red_line_metric`，同样直接 rollback——观测不完整视为不安全。
4. rollback 只切**直接前一版**指针，不删 release 证据。第二次 promote 后再 rollback：active 回到第一版，`generation` 变成 3（每次指针切换 +1）。审计事件用 `previous_event_digest` 拉链，应首尾相接；UPDATE/DELETE 触发器直接拒绝。
5. 合规生成器缺证据就 fail，绝不编。输出写明 Missing evidence is never synthesized。把 impact 文件拿掉，`completeness.status = fail`，进程退出码 2。prod 必须凑齐 impact + eval + rollout。

加分练习：改 manifest 任意字段再 `verify_manifest`，应 digest mismatch——完整性签的是去掉 `integrity` 之后的 canonical JSON。对 prod 只记录 5% 就 promote，应被 `production promotion requires` 拦住（四档最新决策必须全是 promote）。rollback 目标改成非直接前一版，应被 `direct previous release` 拒绝。观测 JSON 写别人的 `release_id`，canary 失败关闭而不是默默改绑。

---

## 9. 易错点与边界

**概念层面**

- lakeFS ≠ Iceberg。一个管湖的 Git 层，一个管表快照；manifest 里两个字段都要有。
- manifest ≠ 可执行流量。没有 pointer 切换，文件躺在 `artifacts/` 里等于没发布。
- `hold` ≠ `rollback`。窗口不够或质量门没过是停住；红线才自动切回。不要把讲义伪代码里的"质量回归 → rollback"直接抄进对本仓库的预期。
- 缺红线指标 ≠ 当作 0。代码视为 `missing_red_line_metric`，直接 rollback。
- v1 schema 能过 ≠ 已经在走治理发布。新晋升看 v2 + `governed_release_manifest`。
- HMAC 能证明篡改 ≠ 生产供应链。密钥在仓库外，算法可替换，课堂签名不是公证。
- 合规生成器哈希已有文件 ≠ 自动写完法务通稿。EU / 备案编号 / 内容标识字段要生产自己补。

**范围边界（Week14 到底做到哪）**

本周交付的是**发布控制面**：不可变绑定、影响报告、灰度决策、原子指针、审计链、证据包。刻意不做的：完整 lakeFS HA 集群、DataHub 列级图谱、Agent 动作 facet、K8s 流量切分、Sigstore 公证、多框架白皮书模板。这些在蓝图的 Production boundaries 里写死了。

Week15 接的是成本、性能和上线收官，不是回头补一个 lakeFS。控制面站得住，后面优化才有可回滚的对象。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 为什么"分别版本数据 / 索引 / Prompt / 模型"几乎一定出半发布窗口？指针模型怎么消掉这个窗口？
2. lakeFS 和 Iceberg 各管哪一层？生产 data 组件为什么必须是 tag 而不是 branch？
3. 讲义的 `rag-v2026.05.18-001` 和仓库的 `omni-dev-v2026.07.20-001` 差在哪？为什么环境要写进 ID？
4. 生成器为什么拒绝已存在的输出文件？这和"manifest 不可变"是什么关系？
5. 不传 `--previous` 做影响分析，报告会是什么样子？高风险变更会多要哪些审批角色？
6. OpenLineage 事件里 inputs / outputs 各是什么？它为什么证明不了"Agent 改了哪张票"？
7. 合规生成器看到缺 canary 文件时应该 fail 还是用"暂无"填上？为什么后者在审计里更危险？
8. Canary 决策顺序里，红线、观察窗、质量 gate 谁先谁后？质量变好但 PII 泄漏，应 promote 还是 rollback？
9. 为什么 rollback 只允许直接前一版，还要核对 `expected_current_release_id`？跳过这两条会出什么事故？
10. prod 指针晋升需要哪四档决策都是 `promote`？只跑了 5% 的课堂路径，为什么不能说"已经全量上线"？

### 自测题参考答案

先自己答完上面的题，再往下对。

1. 分别发版时，总有一段时间 data 新、index 旧，或 Prompt 新、模型旧——半套新半套旧就是半发布窗口。指针模型消掉它的办法：一份 immutable manifest 一次锁死 6 类对象，环境只改一行 `release_environment_pointer`；服务只认当前指针那一代的全部组件 ID。回滚也是改指针，不重部署、不删证据。
2. lakeFS 管湖层分支（跨表跨格式的 Git-like 隔离），Iceberg 管表快照；二者并存，不是二选一。本仓库 **没有 lakeFS 集群**，只有策略文件 + 发布指针。生产 data 组件必须是 tag（`refs/tags/data-*`），禁止把 branch ref 写进 prod——branch 还会继续变，tag 才是不可变锚点。
3. 讲义 Hybrid 是 `rag-v日期-序号`；仓库改成 `omni-{env}-v日期-序号`，把环境写进 ID，避免跨环境拿错包、也避免「同一天多环境撞名」。生成器按 UTC 日期在输出目录递增序号，绝不要手写 UUID。
4. 已存在的输出文件若允许覆写，manifest 就变成可变对象，digest / 签名 / 审计链全部失真。不可变意味着内容或组件变了必须新文件、新 `release_id`，靠指针切换世代，不靠覆盖昨天那份 JSON。
5. 不传 `--previous`，报告会把六个组件都标成 changed。风险 ≥ high 要 `service_owner`，≥ critical（data / model）再加 `data_or_model_owner`。真晋升缺上一份，等于无法区分「无变化」和「全量变更」。
6. inputs 是六个 component，唯一 output 是当前环境的 `release_id`。这是协议适配，不是 DataHub 集群，也没有 `AgentActionFacet`——所以证明不了「Agent 改了哪张票」。动作不进血缘，出事连谁改的都查不到。
7. 应该 fail closed，不能用「暂无」填上。后者在审计里更危险：把缺失伪装成已覆盖，法务以为证据链完整。仓库口径是 Missing evidence is never synthesized；prod 缺 canary / impact / eval，`completeness.status = fail`。
8. 顺序不能改：红线（含缺指标）→ `rollback`；样本/观察窗不够 → `hold`；阶段 gate 或 baseline_guard 失败 → `hold`；全过 → `promote`。质量变好但 PII 泄漏，应 **rollback**——红线优先于质量变好。缺红线指标视为 `missing_red_line`，同样 rollback，不当作 0。仓库比讲义更保守：质量问题先停（hold），只有合规/安全红线才自动切回。
9. 只允许直接前一版，挡住「回滚到无关版本」；核对 `expected_current_release_id`（代码里 `current` 必须等于此刻 pointer），挡住两个值班同时切。跳过这两条会切到错误世代、双写指针、审计链断裂，5 秒回到昨天变成「回到某个不知道的组合」。
10. prod 升稳定指针之前，5% / 25% / 50% / 100% 的**最新**决策必须全是 `promote`。课堂只跑 5% 只证明决策引擎和指针能切，流量分发（Argo Rollouts / OpenFeature）不在 Student Core；缺档、乱序、hold、绑错 digest 都会拦住。不能把「5% fixture promote 了」说成已经全量上线。

---

## 11. 一句话收口

Week14 不是又一周治理文档，而是整门课的**发布与回滚控制面**。前 13 周所有版本字段，只有锁进同一个 `release_id`、再由一个环境指针原子切换时，"昨天那套 data + index + prompt + model"才真正 5 秒可回——这是实验室 demo 和能过监管、能卖钱的产品之间，最后那道必须跨过去的坎。
