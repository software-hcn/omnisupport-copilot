# Week 02 · 输入确定性保障：数据盘点与数据契约

> **一句话**：把"我们有哪些数据"变成"什么数据能带着资格进入系统"——用 inventory / metadata / contract / manifest 四件工件，搭一条可放行、可拦截、可审计的输入门禁链。
>
> 讲义：`pdf/doc/week02-输入确定性保障——数据盘点与数据契约.pdf`（125 页 / 5 课时）

---

## 0. 本周主干

五节课其实是一条流水线，每一节的产出都是下一节的输入：

```
L01 风险判断          为什么输入会先于模型摧毁系统
      ↓
L02 资产盘点          asset_inventory_v1.csv        「世界地图」
      ↓
L03 元数据 + PII      metadata_minimums / pii_matrix 「运行时接口」
      ↓
L04 数据契约          contracts/data/*.json          「合格标准」
      ↓
L05 Manifest + 门禁   data/seed_manifests/*.json     「本次装车单」
      ↓
                     run evidence → Week03 的起跑线
```

课程用了一个很好的记忆法，值得单独记住：

**Inventory 是世界地图，Contract 是合格标准，Manifest 是本次装车单，Run evidence 是通关结果。**

---

## 1. L01 · 输入风险为什么先于模型风险

### 核心论点

生产里最危险的不是系统挂掉，而是**系统还在跑，并且高自信地错**。服务没挂、字段还在、contract 看起来还合法，但事实、引用和动作已经开始稳定偏移。这种"静默失败"比显式报错危险得多，因为团队感知不到，会持续把错误当正常输入消费。

### 三条底线（本周最重要的分类框架）

课程把笼统的"数据质量不好"拆成三条可执行的底线，后面每一节都在回扣它们：

| 底线 | 它回答什么 | 关键字段 | 坏掉的表现 | 常见误解 |
|---|---|---|---|---|
| **事实底线** | 它说的是不是真的 | 枚举、主键、时间窗、增量窗口 | 状态语义漂移 → KPI 与 route 一起偏 | 字段没报错就算对 |
| **证据底线** | 我能不能回到来源 | `doc_version` / `page_no` / `bbox` / `section_path` | chunk 还能召回，但 citation 断了 | 正文还在就够了 |
| **边界底线** | 谁能看、谁能搜、谁能做 | PII 分级 / `tenant` / `role` / access policy | 越权检索、PII 暴露、误动作 | 输出前再补一层审核就行 |

### 排障口令（很实用，值得背）

看到 AI 系统"变歪"时，先做判断再做动作：

- **同样的问题突然系统性偏** → 先查输入层（schema、枚举、时间窗、增量窗口）
- **只有少数问法出错** → 才看 prompt / retrieval
- **citation 开始失效** → 查 metadata / provenance
- **tool 参数开始越界** → 查 policy / contract / access boundary

反过来说，最常见的误诊是：答案忽高忽低就去调 prompt 换模型，引用不稳就去调 top-k 和 rerank，有人看到不该看的就加一道输出审查。这三种反应都在修症状。

---

## 2. L02 · 资产盘点不是列目录

### 三种对象必须分层

这是 L02 最容易混的地方，混掉之后 metadata 和 contract 都会写歪：

| 对象 | 回答什么 | 例子 |
|---|---|---|
| **Source System** 资源目录 | 哪里有什么资源 | Zendesk / Jira / CMS / S3 / ASR |
| **Input Asset** 输入地图 | 哪些资源能以什么资格进系统 | `ticket_event` / `doc_asset` / `audio_segment` / `video_segment` |
| **Serving Object** 服务对象 | 最终被哪个运行时能力消费 | retrieval chunk / KPI mart / tool input view / audit evidence |

判断准则：如果一个字段既像源系统字段、又像运行时字段，先停下来问它到底属于哪一层。

### 资格审查四问

盘点一个资产时，依次问：

1. **事实（Fact）**——它说的事实能不能被稳定解释？
2. **证据（Evidence）**——它能不能回到原始来源？
3. **边界（Boundary）**——谁能看、谁能搜、谁能传工具？
4. **责任（Owner）**——谁负责更新、修复和解释口径？

### 盘点表的四组字段

不要让 inventory 退化成"三列清单"：

- **Identity**：`asset_id` / `asset_class` / `asset_name` / `product_line`
- **Source & Freshness**：`source_system` / `source_uri` / `refresh_policy` / `update_window`
- **Evidence & Lineage**：`evidence_locator` / `source_fingerprint` / `doc_version` / `ingest_batch_id`
- **Governance & Admission**：`owner_team` / `pii_level` / `access_policy` / `admission_status` / `quality_notes`

### 分层准入（admission ladder）

不是所有资产都该 `ready_now`。这四个状态会被 L04 的 contract gate 和 L05 的 manifest 直接消费：

| 状态 | 含义 | 判据 |
|---|---|---|
| `ready_now` | 可直接进入下一步 | 字段齐、owner 明确、证据定位可用、PII/access 可判断 |
| `conditional` | 带条件进入 | 可试运行，但必须带 quality_notes / risk_notes / 补齐项 |
| `hold` | 暂缓 | 证据定位、权限、版本或更新窗口不清 |
| `exclude` | 明确排除 | 不合规、不可授权、价值低 |

---

## 3. L03 · 最小元数据与 PII 动作矩阵

### 核心论点

**metadata 不是备注，而是检索、引用、权限、审计的 runtime interface。** 缺 metadata 的系统通常不是"答不了"，而是"答了也无法证明、无法过滤、无法追责"。

每个 metadata 字段都要能回答"谁消费它、它影响什么决策"：

| 字段 | 谁消费 | 直接影响 |
|---|---|---|
| `access_scope` | retrieval / tool 层 | 权限过滤：谁能搜、谁能触发工具 |
| `page_no` / `bbox` / `section_path` | citation / audit | 引用能不能回到原文页、区域、章节 |
| `speaker_role` / `start_ts` / `end_ts` | transcript QA / HITL | 对话责任、片段定位、人工复核 |
| `schema_version` | contract 兼容性检查 | 新增字段还是 breaking change |
| `pii_level` | policy engine | 是否可入模、可展示、可传工具 |

### 统一方法：shared core + modality extension

所有输入先继承一组共享核心字段，再按模态补最小扩展：

**共享核心**：`source_id` / `asset_type` / `source_system`（身份），`source_fingerprint` / `schema_version`（版本与追溯），`owner` / `access_scope` / `pii_level`（治理），`observed_at`（时间）

**四类模态扩展**：

| 模态 | 必须补的字段 | 丢了会怎样 |
|---|---|---|
| ticket | `tenant_id` / `status` / `opened_at` / `updated_at` / `requester_role` / `product_line` | 多租户过滤不稳、增量 ingest 不准、tool 错路由 |
| document | `doc_version` / `page_no` / `bbox` / `section_path` / `license_tag` | citation 失真、entitlement 失控、审计无法回指 |
| audio | `call_id` / `speaker_role` / `start_ts` / `end_ts` / `confidence` / `pii_redaction_flag` | 对话审计失效、HITL 无法回听正确片段 |
| video | `video_id` / `segment_ts` / `frame_ts` / `transcript_ref` / `image_caption` / `ocr_text` | 关键帧证据链断裂、命中后无法落到片段 |

### 顺序很关键：metadata 必须先于 chunking

- **错误顺序**：`raw text → chunk → embedding`。后果是 chunk 命中以后，才发现不知道页码、章节、坐标、权限。
- **正确顺序**：`raw asset → shared core → modality extension → chunk/segment → gate`。每个片段天然带证据锚点和策略上下文。

这条顺序会在 Week07 被真正落地成 evidence anchor。

### PII 从布尔值升级成动作矩阵

`contains_pii = true/false` 回答不了系统真正要做什么。要拆成 **字段级分级 × 六类系统动作**：

动作维度：`store_raw` / `embed` / `retrieve` / `display` / `pass_to_tool` / `human_review`

| 等级 | 典型内容 | store_raw | embed | retrieve | display | pass_to_tool | human_review |
|---|---|---|---|---|---|---|---|
| `public` | 公开帮助文档、错误码 | 允许 | 允许 | 允许 | 允许 | 允许 | 可选 |
| `internal` | 内部 SOP、运维说明 | 允许 | 条件允许 | 内部范围 | 条件允许 | 条件允许 | 建议 |
| `sensitive` | 姓名、邮箱、手机号、截图中个人信息 | 允许但标注 | 脱敏后 | 条件允许 | 裁剪后 | 默认限制 | 建议 |
| `restricted` | token、密钥、支付信息、证件号 | 条件隔离 | 默认禁止 | 默认禁止 | 默认禁止 | 默认禁止 | 必须 |

一个值得记的设计权衡：**先脱敏再入模**（风险低，但可能损失时间、空间、实体上下文）vs **保真存储 + 查询裁剪**（证据链完整，但需要更强的 policy gate）。课程给的默认答案是：sensitive 优先脱敏后消费，restricted 默认不进入通用 serving。

---

## 4. L04 · 把 Data Contract 做成工程门禁

### 四个对象彻底分开

这是全周最重要的一张对照表：

| 对象 | 回答什么 | 一句话 | 变化频率 |
|---|---|---|---|
| **JSON Schema** | 字段形状、类型、枚举是否合法 | 看长相 | 低 |
| **Data Contract** | shape + semantics + evidence + policy + quality 是否构成准入标准 | 看资格 | 低 |
| **Manifest** | 本次 ingest 接哪一批、按什么模式接 | 看批次 | 高 |
| **Policy** | 哪些字段、动作、角色受限，如何脱敏拦截 | 看边界 | 贯穿 |

关键判断：**schema 能过，不代表系统安全。** 生产里最常见的事故不是字段消失，而是字段"看起来还在"——`status` 仍是 string 但生命周期语义漂了，`updated_at` 仍是 timestamp 但变成了 ETL 时间。

### 一份可执行 Contract 的五层

把 contract 当分层防线，不是当更长的字段表。每一层对应一个 gate question：

| 层 | gate 会问什么 | ticket 示例 | document 示例 |
|---|---|---|---|
| 1 Shape / Schema | 结构是否完整 | `status` 存在且为 string | `page_no` 是否为 int |
| 2 Semantics | 语义是否漂移 | `updated_at` 代表什么时间 | `doc_version` 是否正式版本 |
| 3 Metadata / Evidence | 能否引用与追责 | `ticket_id` / `tenant_id` | `page_no` / `section_path` / `bbox` |
| 4 Policy / Access / PII | 是否越权违规 | `requester_email` 是否 mask | `license_tag` 是否允许分发 |
| 5 Quality / Freshness / SLA | 放行、警告还是拦截 | 枚举违规率、新鲜度 | 版本延迟、缺页率 |

判断标准很直接：**如果 contract 不能影响运行时动作，它就只是文档。** 它必须能校验、能拦截、能报警、能进 CI/CD、能讨论兼容性。

### 兼容性三级

兼容性不是技术问题，而是**下游承诺问题**。不要在"全放行"和"全拦截"之间摇摆：

| 级别 | 什么情况 | 默认动作 |
|---|---|---|
| `additive` | 新增可选字段（如 `priority_label`） | 通常放行，但要记录 |
| `conditional` | 扩充 status 枚举、收紧 freshness 阈值 | review 下游是否准备好 |
| `breaking` | 删除/重命名字段、语义漂移、locator 改义 | 默认拦截或给迁移窗口 |

三个值得反复练的案例：

- `ticket.status` 新增 `in_progress` → **conditional**（结构没坏，但穿透统计与 tool route，要 review 路由/指标/UI）
- `document.doc_version` 从 optional 改 required → **breaking**（老数据直接不再合法，需要迁移窗口 + fixture 回归）
- `audio.speaker_role` 枚举从 4 个缩成 2 个 → **breaking**（老转写样本失配，归因语义会塌，需拦截 + 补映射规则）

**语义漂移即使 schema 不变，也可以是 breaking。**

### 怎么读 contract test 的失败

| 失败现象 | 先怀疑什么 | 判断要点 |
|---|---|---|
| required 缺失 | fixture 漏字段，或 contract required 过严 | 先分清是历史数据问题还是契约升级问题 |
| enum 不匹配 | 上游枚举漂移，或 fixture 过时 | 不要立刻放宽 enum，先确认下游动作 |
| format 错误 | contract 太松/太严，或样例是脏数据 | 标准不是为了过测试，而是为了可消费 |
| compatibility 报 breaking | 下游承诺被打破 | 不能只看技术上还能不能跑 |

---

## 5. L05 · Manifest 与运行时门禁

### Manifest 不是文件清单

只列路径不会留下 ingest 语义，也无法复现一次运行。Manifest 要表达的是**本次 ingest 的运行时意图**：绑定 contract、声明 load_mode、定义 window/cursor/snapshot、携带 owner/pii_level/release_id、为 dry-run 与 run evidence 留锚点。

Manifest 的字段组，每组各守一道门：

| 字段组 | 守的门 | 缺了会怎样 |
|---|---|---|
| source identity | 这批数据到底是谁 | 无法路由 |
| location | 系统去哪里读 | 变成脚本硬编码 |
| contract binding (`contract_ref`) | 服从哪份 gate | 没有统一 gate |
| load semantics (`load_mode` / cursor / window) | 这次是怎么接的 | state 建不起来 |
| policy context (`pii_level` / `access_scope` / `release_id`) | 运行时边界与版本 | 边界失控 |
| evidence context (`generated_at` / `manifest_version`) | 以后怎么追 | 不可追溯 |

### 五种采集模式

别死记名字，背后是**五种批次关系**：

| 模式 | 是什么 | 必须声明 | 风险 |
|---|---|---|---|
| `full_snapshot` | 某个时点的完整世界 | `snapshot_date` | 成本高、重复索引 |
| `incremental_cursor` | 最近变化过的对象 | `cursor_field` + `window_*` | 漏数、重数、时区错误 |
| `cdc` | 事件流而非静态表 | `checkpoint_field` / `cdc_cursor` | 配置复杂、补数难 |
| `replay` | **不是新数据**，是重跑旧批次 | `replay_from_batch` / `replay_reason` | 重复写入、版本混淆 |
| `backfill` | **不是在线变化**，是补历史空洞 | `backfill_range` / `reason` | 影响范围过大、资源争抢 |

选模式时问三个问题：这一批和上一批是什么关系？这次覆盖完整世界还是只接变化？如果失败，应该重放、补数，还是继续追增量？

生产里最常踩的四个坑（都不是语法问题，而是批次语义问题）：**时区漂移**（window 没统一时区）、**cursor 不稳**（`updated_at` 被回写或延迟写入）、**重复写入**（replay 没有幂等键）、**状态缺失**（没有 release_id / manifest_version，无法定位哪一轮坏了）。

### 门禁不是二元判断，而是四类动作

这是 L05 的核心。四类动作不是结果标签，而是**后续处理路径**：

| 动作 | 系统行为 | 什么时候用 | 下一步 |
|---|---|---|---|
| `accept` | 记录合格，进入下一层 | 字段/元数据/PII/枚举全通过 | → ingest baseline |
| `warn` | 放行但必须记日志 | 非关键描述字段缺失、可容忍延迟 | → observability debt |
| `quarantine` | 隔离，暂不进主链路 | 个别记录坏了，整批还有可用部分 | → patch / replay |
| `reject` | 整个 source 不接收 | manifest 严重错误、contract 不匹配、关键字段缺失 | → 先修准入 |

决策树的顺序是固定的：manifest 可读？→ contract 已绑定？→ 关键字段/PII policy 通过？→ 是否只是局部质量问题？→ 是否是非关键小问题？

### run evidence 必须留下什么

没有 run evidence 的 dry-run，只是"看起来跑过一次"。至少要有五组：

- **identity**：`run_id` / `release_id` / `manifest_version` / `git_sha`
- **source linkage**：`source_id` / `asset_type` / `contract_ref` / `owner`
- **gate result**：四类动作 + `reason_code`
- **window state**：`load_mode` / cursor / window / snapshot_date
- **next action**：patch / replay / backfill / continue incremental

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L02 资产盘点表 | `docs/blueprints/week02/asset_inventory_v1.csv` | 四组字段是否齐、admission_status 怎么填 |
| L03 最小元数据标准 | `docs/blueprints/week02/metadata_minimums_v1.md` | shared core + 四类扩展 |
| L03 PII 动作矩阵 | `docs/blueprints/week02/pii_policy_matrix_v1.csv` | 等级 × 动作，不是 true/false |
| L04 四类数据契约 | `contracts/data/ticket_contract.json`<br>`contracts/data/doc_asset_contract.json`<br>`contracts/data/audio_asset_contract.json`<br>`contracts/data/video_asset_contract.json` | `required` 列表、`enum` 定义、`additionalProperties: false` |
| L04 正反例 fixture | `tests/contract/fixtures/week02/sample_records.json` | 每类资产的 good / bad 样例 |
| L04 契约测试 | `tests/contract/test_json_schemas.py` | schema 能否加载、fixture 是否满足 |
| L05 Manifest schema | `data/seed_manifests/source_manifest_schema.json` | `contract_ref` / `load_mode` / `selection_window` / `gate_policy` |
| L05 三份现有 manifest | `data/seed_manifests/manifest_tickets_synthetic_v1.json`<br>`manifest_edge_gateway_pdf_v1.json`<br>`manifest_workspace_helpcenter_v1.json` | 对比三种 modality 的写法差异 |
| L05 练习 manifest | `data/seed_manifests/manifest_week02_practice_v1.json` | 自己补齐的那一份 |
| L05 门禁执行 | `pipelines/ingestion/seed_loader.py` | `_evaluate_asset_gate()` 和 `_combine_judgments()` |
| L05 门禁测试 | `tests/contract/test_week02_gate.py` | 四类动作的判定逻辑 |
| L05 采集策略文档 | `docs/blueprints/week02/ingest_strategy_v1.md` | 五种 load_mode 的选型记录 |

### 代码里几个值得单独看的细节

**门禁默认策略**在 `seed_loader.py` 里是硬编码的默认值（约第 62 行），讲义没展开，但它体现了课程的风险偏好：

```python
"on_missing_checksum":  "warn"        # 校验和缺失 → 只警告
"on_partial_metadata":  "warn"        # 元数据不全 → 只警告
"on_missing_metadata":  "quarantine"  # 元数据缺失 → 隔离
"on_pii_gap":           "quarantine"  # PII 缺口   → 隔离
"on_contract_mismatch": "reject"      # 契约不匹配 → 拒收
"on_unknown_license":   "reject"      # 许可未知   → 拒收
```

严重性用数值排序（`accept=0 < warn=1 < quarantine=2 < reject=3`），一个 manifest 里多个资产的判定会取**最严的那个**。这就是 `_combine_judgments()` 做的事。

**`source_manifest_schema.json` 的 `contract_ref` 是 enum 而不是自由字符串**——只允许四个 `omni://contracts/data/*/v1`。这意味着 manifest 不可能绑到一个不存在的契约上，是 L04"contract 必须能进入运行时"的直接体现。

**`ticket_contract.json` 的 `status` enum 已经包含 `in_progress`**，正好就是讲义 L04 举的 conditional 变更案例。可以对照着看：新增枚举值之后，下游 KPI（Week05）和 tool route（Week10）分别在哪里消费它。

---

## 7. 讲义与仓库对不上的地方

这几处讲义写了但仓库里没有，**别浪费时间去找**：

| 讲义写的路径 | 实际情况 |
|---|---|
| `data/asset_inventory/week02_asset_inventory.csv` | 不存在，实际是 `docs/blueprints/week02/asset_inventory_v1.csv` |
| `tests/inventory/test_asset_inventory.py` | 不存在，inventory 没有独立测试；契约相关测试在 `tests/contract/` |
| YAML 格式的 manifest | 讲义 L05 已明确纠正：仓库统一用 JSON manifest 体系，早期页面提到的 YAML 是过时说法 |

---

## 8. 动手清单

所有命令统一走 Docker devbox，避免"你本机能跑我本机不能跑"。

```bash
# 1. 跑契约测试：验证四类 contract 结构合法、fixture 站得住
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  pytest tests/contract/ -v

# 2. 跑 seed_loader dry-run：验证 manifest → contract → gate 闭环
docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox \
  python -m pipelines.ingestion.seed_loader \
    --manifest-dir data/seed_manifests
```

**验收标准不是"跑过了"，而是能回答这四个问题**：

1. 哪个 manifest 被读取？本次批次边界是否明确？
2. 它引用了哪份 contract？source 和准入标准是否闭环？
3. 哪些 source 被 accept / warn / quarantine / reject？为什么？
4. 有没有 `release_id` / `source_id` / `owner`？Week03 能不能接上？

**加分练习**（能真正检验理解）：

- 故意改坏一个 `enum` 或 `required` 字段，确认 contract test 会失败，然后判断这是 additive / conditional / breaking 中的哪一类
- 在 `sample_records.json` 里加一条 negative case（比如 document 只有 text 没有 locator），确认它被正确拦截——**没有 negative case 的 contract test，只能证明"样例能跑"，证明不了"系统能守门"**

---

## 9. 易错点与边界

**概念层面**

- Manifest ≠ 文件清单。它是一次 ingest 批次的运行时声明。
- Contract ≠ ingest plan。contract 定义"什么样的数据合格"，manifest 定义"这次接哪一批"。
- `quarantine` ≠ `reject`。quarantine 可隔离观察、后续 patch/replay；reject 是整批不能接。
- schema 通过 ≠ 系统安全。语义漂移一样会把系统带偏。
- 兼容性 ≠ 字段是否存在。还要看枚举、语义、policy、evidence。

**范围边界（Week02 到底做到哪）**

Week02 交付的**不是完整的 ingest 系统，而是一个可信的 ingest baseline**。刻意留给 Week03 的部分是：真正的 batch/incremental 实现、幂等、补数、回放、失败恢复、真正的数据搬运与入湖、运行时调度。

Week03 的 state、watermark、idempotency 不是凭空长出来的，它们直接来自 Week02 manifest 的 `load_mode`、contract 的 shape、gate 的分流动作。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 举一个"系统没挂但已经坏了"的具体例子，说清它属于事实、证据、边界哪条底线。
2. 用户反馈"最近工单相关的回答忽高忽低"，你的排查顺序是什么？为什么不先调 prompt？
3. Source system、input asset、serving object 的区别是什么？各举一个本项目里的例子。
4. 为什么 metadata 必须先于 chunking？错误顺序的具体后果是什么？
5. `contains_pii = true` 为什么不够用？六个动作维度分别是什么？
6. JSON Schema 和 Data Contract 的区别用一句话怎么说？Contract 的五层分别守什么？
7. `ticket.status` 新增一个枚举值，为什么是 conditional 而不是 additive？
8. 五种 load_mode 中，replay 和 backfill 的本质区别是什么？各自最大的风险是什么？
9. 什么情况该 quarantine 而不是 reject？两者对下游的处理路径有什么不同？
10. 一次 dry-run 跑完，run evidence 里必须留下哪五组信息？少了 `release_id` 会导致什么问题？

---

## 11. 一句话收口

Week02 不是"治理补丁周"，而是整门课的**数据入口控制面**。做得越扎实，后面的 ingest、RAG、Agent、评测与治理越稳——因为所有下游都建立在"输入是否可信、可追溯、可合规"这个前提上。
