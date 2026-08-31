# Week 09 · Agent Skills 开放标准

> **一句话**：把团队散落在 Wiki / 脚本 / 口头里的工程工艺，封成可发现、可渐进加载、可版本回滚的 Skill Pack——给 Week10 受控 Agent 备好行动手册，而不是再写一份没人照着做的 SOP。
>
> 讲义：`pdf/doc/week09-Agent Skills 开放标准.pdf`（48 页 / 5 课时）

---

## 0. 本周主干

五节课是一条从「为什么打包」到「怎么像软件一样发布」的链，每一节的产出都是下一节的输入：

```
L01 Why     工艺随人走 → 可移植 Pack              「为什么要封」
      ↓
L02 Pack    一目录 + SKILL.md + 三件配套          「怎么装箱」
      ↓
L03 Load    Discovery → Activation → Execution    「怎么不爆窗口」
      ↓
L04 Author  写给 Agent 立刻执行的指令             「怎么写才不误激活」
      ↓
L05 Govern  版本 + 评测 + Registry + Manifest     「怎么演进、怎么回滚」
      ↓
                     Skill Pack → Week10 受控 Agent 的行动手册
```

两条口诀值得单独记住：

- **scripts 是动词，references 是名词，assets 是形容词。** 放错位置，整个 Pack 就不可治理。
- **MCP 管「连上世界」，Skill 管「连上之后怎么干漂亮」。** Skill 不替代 Tool / Prompt / Workflow / MCP，是把它们组合起来的打包格式。

仓库里的对应关系也很直：五个初始 Skill 分别把 Week02 / 03+06 / 08 的工艺封进 `skills/`，再由 Tool API 做渐进发现，最后把 digest 锁进 release manifest。本周**不执行业务动作**——动作留给 Week10 的 Tool Contract + HITL。

---

## 1. L01 · 为什么要 Skill 化

### 核心论点

生产里最贵的通常不是模型，而是**没被工程化对待的工艺**：补数要先锁分区、契约变更要先看兼容级别、RAG 无引用必须 abstain。这些知识散在 Confluence、代码注释、Prompt 副本、Slack 和「找老 X」里。人走流程消失，文档停更，脚本散仓。Skill 的目标就是把这 6–7 类散落资产收成**一类对象**：一个目录、一份 `SKILL.md`，能被 Agent 发现、被 Git 治理、跨工具搬走。

它和前两层是叠加不是替代：

| 层 | 形态 | 本课落点 | 没有它会怎样 |
|---|---|---|---|
| L1 Data as Code | 数据像代码一样版本化 | Week02 / 06 / 14 | Skill 里的脚本不可复现 |
| L2 Prompt as Code | Prompt 走 Git + 评测 | Week08 L04 | Skill 改了不知道行为漂了 |
| L3 Skill as Pack | 工艺打包成可移植对象 | **本周** | Agent 没有标准行动手册 |

### Skill 跟旁边那些东西差在哪

| 对象 | 解决什么 | 跟 Skill 的关系 |
|---|---|---|
| Tool / Function | 调一个具体函数 | Skill **内部可以指向它**，但不等于它 |
| Prompt 模板 | 约束单次输出 | Skill 可以内嵌，但 Skill 还带步骤/禁区/脚本 |
| Workflow | 编排端到端流程 | Skill 可封装流程，不绑某家编排器 |
| MCP Server | 连接外部系统 | 互补：MCP 是神经系统，Skill 是心智剧本 |
| **Skill Pack** | 把工艺打成可移植对象 | 上面这些的**容器**，不是又一个运行时 |

判断句：**能用一份 Markdown 解决，就别再部署一个服务。** 自研一套 SKILL.md 方言，到 2026 就是纯工程债——跨厂商已经收敛到「一个目录 + YAML 头」。

### 七个信号：中三条就该动手

| 信号 | 严重度 | 本仓库已经在疼的地方 |
|---|---|---|
| 流程靠「找老 X」 | 高 | 补数 / 回放口口相传 → `ingest-backfill-runbook` |
| 同一规范多份副本 | 高 | 契约检查各写一份 → `data-contract-lint` |
| 跨工具迁移痛 | 高 | OpenAI / Claude / Cursor 各做一遍 → `/exports/openai` + `/exports/mcp` |
| Runbook 不可执行 | 中 | Markdown 写着没人照做 |
| 新人 onboarding 慢 | 中 | 没有「照这个包做」 |
| 合规要流程 + 执行证据 | 高 | → `release-check` 绑 digest |
| Agent 开始调工具 | 高 | 没有手册的 Agent 会乱动手 → 直接接 Week10 |

---

## 2. L02 · Skill Pack：一目录 + SKILL.md

### 本质就是文件夹

不需要 SDK、不需要专用运行时。标准结构（Anthropic Agent Skills 规定，本仓库五个 Pack 都按这个长）：

```
skills/<skill-name>/
├── SKILL.md          # 必：YAML 头 + 指令正文
├── scripts/          # 可：系统执行的代码
├── references/       # 可：LLM 按需查的资料
└── assets/           # 可：生成产物时用的模板
```

`SKILL.md` 两段职责必须分开：**YAML 头决定何时用，正文决定怎么做。** 「改 .md 走 PR」这一条，就是工艺第一次能像代码一样被 diff、被 review、被回滚。

### Frontmatter：官方强制 vs 仓库强制

讲义强调官方 spec **只强制 `name` + `description`**。仓库更严：契约 `required` 是三个，测试还额外检查负向路由和产出声明。

| 字段 | 谁强制 | 约束 | 写坏的后果 |
|---|---|---|---|
| `name` | 官方 + 仓库 | `^[a-z][a-z0-9-]*$`，须等于文件夹名 | 发现失败 / registry 直接抛 |
| `description` | 官方 + 仓库 | 仓库 `minLength: 20`；第三人称；做什么 + 何时用 | Stage 1 找不到或误激活 |
| `version` | **仅仓库** | SemVer `x.y.z` | 锁不进 release manifest |
| `not_for` | **仅测试** | 非空字符串数组 | 负向路由缺失，易抢活 |
| `outputs` / `artifacts` | 测试 / 治理 | 产物路径 | 跑完没有可审计出口 |
| `requires` | 可选 | 依赖的其他 skill 名 | 隐式耦合，调试时找不到前置 |
| `evals` | 可选 | 回归入口 | 改手册没有闸门 |
| `status` | 可选 | `draft` / `active` / `deprecated` | 过期 Pack 仍被发现 |

官方可选字段是 `license` / `compatibility` / `metadata` / `allowed-tools`。`version` / `inputs` / `not_for` 都是团队扩展——别把扩展字段当成 spec 必填去网上对线。

`description` 公式：**动词短语 + 输入对象 + Use when X / Y / Z。** 它是 Discovery 阶段 Agent **唯一能看到的东西**。

| 写法 | 问题 |
|---|---|
| `Lint data contract` | 太短，没有触发词 |
| `helps with various data quality tasks` | 太泛，相关问题全误激活 |
| `Internal tool for support team` | 写给人看，Agent 读不懂 |
| `Validate OmniSupport data contracts... before data enters ingestion or indexing.` | 动词具体 + 对象明确 + 边界在句里 |

### 三件配套：别混输入侧和输出侧

| 目录 | 装什么 | 谁读 | 何时进 context |
|---|---|---|---|
| `scripts/` | `.py` / `.sh` | 运行时执行 | **代码不进窗口**，只回结构化结果 |
| `references/` | 规范、正反例、术语 | LLM 按需检索 | Activation 之后、Execution 之时 |
| `assets/` | 空白模板、fixture | 生成产物时填 | 生成阶段 |

最容易混的是 references vs assets：你要「读它来理解」的放 references；你要「拿它来生成」的放 assets。examples 塞进正文会把 Stage 2 撑爆，正确位置是 `references/`。

五个组件的协作顺序是固定的：

```
Frontmatter 匹配查询
    → Markdown 让 LLM 理解任务
        → References 按需补规范
            → Scripts 执行并回 JSON
                → Assets 填模板出产物
```

### scripts 的四条工程底线

讲义给的生产级标准（仓库里目前是占位脚本，标准本身仍要按这个审）：

1. **幂等可重入**——同样输入跑两次结果一致（Week06 三层幂等同样适用）
2. **结构化输出**——`json.dumps`，禁止靠 print 让 Agent 猜
3. **明确错误码**——0 成功 / 1 规则违反 / 2 输入错（本仓库占位脚本基本按这个分）
4. **零隐式依赖**——能用标准库就用标准库；三方必须显式声明

验收一句：把脚本从 Pack 里抠出来，干净机器上一行命令能跑通，才算工程化。

---

## 3. L03 · 渐进加载：规模化时不爆 context

### 为什么必须按需

5 个 Skill 全量塞进窗口看不出来；50 个 × 2K token = 10 万 token 元数据；500 个直接把窗口打爆。Progressive Disclosure 把加载拆成三段，量级差几十倍：

| 阶段 | 加载什么 | 量级 | 仓库对应 |
|---|---|---|---|
| **Stage 1 Discovery** | 只读 frontmatter（name / description / version…） | ~100 token / skill，启动常驻 | `GET /api/v1/skills` → `SkillRegistry.discover()` |
| **Stage 2 Activation** | 命中才读一篇 `SKILL.md` 正文 | 通常 < 5K；官方建议正文 < 500 行 | `GET /api/v1/skills/{name}` → `get_skill()` |
| **Stage 3 Execution** | 按需列/读 scripts、references、assets | 没用到 = 0 token；脚本只回结果 | 响应里列出路径，**本周不远程执行** |

全量加载是线性爆炸，渐进加载把 Discovery 成本压成近似常数。Skill 从 50 涨到 500，启动成本几乎不变。

### description 五条规则（路由失败都从这儿来）

1. 含具体触发关键词（`Use when user mentions X / Y / Z`）
2. 动词具体（Validate / Generate / Plan，不要 helps with）
3. 边界清晰（for X only，不要 various）
4. 长度适中（大约 50–150 token）
5. **带反例**（`Not for…` / `not_for`）——反例比正例更能挡误激活

仓库把反例放在 frontmatter 的 `not_for` 数组，而不是正文 `## NOT-TRIGGER`。Stage 1 就能看到负向提示，这比讲义示例更省 token。

### Routing 按规模选，不要一上来上中台

| 策略 | 做法 | 适合 | 仓库现状 |
|---|---|---|---|
| LLM 直接选 | 把全部 description 交给模型 | < 30 个 | 五个 Pack，够用 |
| 规则 + LLM | 关键词预过滤 top-N 再让模型选 | 中等 | `SkillRegistry.search()` 是词项全匹配预过滤 |
| Embedding + LLM | description 向量检索再精选 | ≥ 50 | **本周不做**，和 Week08 RAG 同构，可后补 |

### 五个反模式

| 反模式 | 正确做法 |
|---|---|
| 启动全加载所有 `SKILL.md` | 只读 frontmatter |
| description 写成内部文档 | 面向 Agent 写 + 触发词 |
| references 堆进正文 | 挪到 `references/` |
| Skill 之间硬依赖、隐式调用 | 保持独立，依赖写进 `requires` |
| 50+ 还在 LLM 直选 | 上 embedding routing |

集成测试把这条纪律钉死了：`GET /api/v1/skills` 的每条记录 **不许带 `body`**；只有 `GET /api/v1/skills/{name}` 才返回正文和三类路径。

---

## 4. L04 · 写给 Agent 的指令，不是 Wiki

### 写作哲学是反的

把 Confluence SOP 加个 YAML 头当 Skill，是本周最高频翻车。Wiki 让人看完自己判断；`SKILL.md` 让 Agent 看完立刻执行。

| 维度 | 人类文档（Wiki） | Agent 指令（SKILL.md） |
|---|---|---|
| 第一段 | 背景 / 历史 / 为什么 | 触发条件 / 何时使用 |
| 步骤 | 可省，留人判断 | 每步一个具体动作 |
| 例子 | 可选 | 正例 + 反例必备 |
| 边界 | 「通常不要…」 | 「禁止 X / Y / Z」 |
| 错误处理 | 出错再说 | 事先声明 failure mode |
| 输出 | 自由描述 | 强制结构化 / JSON |

### 生产级七段，分三组

少一段就对应一类事故：

| 组 | 段落 | 缺了会怎样 |
|---|---|---|
| Identity 发现 | name / version / description / triggers / not-triggers / inputs / outputs | 找不到，或抢兄弟 Skill 的活 |
| Procedure 执行 | Steps / Constraints / Failure Modes | 执行含糊、越界、卡死 |
| Evidence 证据 | Examples / Audit Fields / Citation Format | 产出无法复盘、无法引用 |

仓库五个 Pack 的正文是精简版：`Procedure` + `Safety Boundaries`，把 not-trigger 收进 frontmatter `not_for`。结构比讲义示例短，但对应关系还在——**不要因为正文没写 `## NOT-TRIGGER` 标题就以为没做负向路由。**

### Trigger 必须成对出现

只写「何时用」= 一定误激活。讲义用 `rag-contract-check` 举例：

- 该用：上线前检查 RAG 输出、调试「为什么这条没引用」、CI 预发回归
- 不该用：「模型答得准吗」→ 评测集；「数据质量」→ `data-contract-lint`

把容易抢活的兄弟 Skill **点名**，路由准确率立刻上台阶。仓库里五份 `not_for` 就是这个机制：

| Skill | 明确不管什么 |
|---|---|
| `data-contract-lint` | 无契约语义的 JSON 格式化；跑数据库迁移 |
| `ingest-backfill-runbook` | 无 manifest / 分区范围的 ad hoc SQL；破坏性删数 |
| `rag-contract-check` | 无契约字段的文笔评审；不验 schema 的 prompt 改写 |
| `prompt-release` | 不会入库的一次性 brainstorm；绕过 RAG 契约的改动 |
| `release-check` | 无发布意图的本地草稿；未经审批的紧急回滚命令 |

### 四类硬约束 + 五类失败

约束要写「禁止」不写「建议」——Agent 对建议会打折扣。

| 约束 | 要求 | 本课回扣 |
|---|---|---|
| Evidence | 产出能回到原文 / 字段路径 | Week02/07/08 evidence |
| Schema | 输出符合声明的 schema | Week08 Structured Outputs |
| Audit | `trace_id` / actor / 参数指纹 | 事故复盘的根 |
| Boundary | 不读 X、不调 Y、不动 Z | 最有效的防线是不让进危险区 |

| 失败类型 | 典型场景 | 能否重试 |
|---|---|---|
| Input Invalid | 文件不存在、参数缺 | 否，改输入 |
| Validation Failed | 契约没过 | 否，结果就是 fail |
| Transient | 网络 / 限流 | 是，带 `retry_after` |
| Permanent | 没权限、资源不存在 | 否，升级 |
| Partial Success | 5 条只检了 3 条 | 让 Agent 决策 |

Agent 最怕的不是失败，是**不知道自己失败了**。

写作反模式同样五条：抄 Wiki、只写正向步骤、examples 放正文、不写 audit、约束写得软。笨办法：写完丢给一个干净 Agent 照着跑，它哪步卡住就是哪段没写清。

---

## 5. L05 · 版本 + 评测 + Registry

### 改手册等于改业务行为

Skill 超过 5 个，立刻变成分布式系统问题：改一步措辞会不会带偏下游 Agent？这周突然不灵，是 Skill 改了还是模型升级了？A 团队的 Pack 给 B 团队用，版本兼容吗？治理三支柱缺一不可：

| 支柱 | 做什么 | 本周落地到哪 |
|---|---|---|
| Version | SemVer + digest + 锁进 `skill_release_id` | frontmatter `version`；`SkillMeta.digest` = 整份 `SKILL.md` 的 sha256 |
| Eval | golden set，回归不过不能合 | `evals:` 指向已有 pytest；契约测试卡 Pack 结构 |
| Registry | discovery / get / 导出描述符 | Tool API `/api/v1/skills*` |

讲义里的 PR 五步（Edit → Lint → Eval → Review → Release）和代码 PR 同构。仓库**没有** `.github/workflows/skill-ci.yml`，门禁目前就是 `tests/contract/test_week09_skill_packs.py` + `tests/integration/test_week09_skill_registry.py`。先把这两道闸跑绿，再幻想企业级 Skill 中台。

### Registry 按组织规模选，别一上来上重型

| 架构 | 适用 | 维护成本 |
|---|---|---|
| 项目内 `skills/` 目录 | 小团队 / 课堂 | 低 ← **本周就是这个** |
| 私有 Git 仓库 + 各项目引用 | 10–50 个 Skill | 中 |
| Registry API 服务 | > 50，要跨团队 | 高 |
| 公开 Marketplace | 社区分发 | 极高 |

讲义列的 Registry「五件套」里，本周只做了 **Discovery**（list / get / 关键词 search）和只读导出。SemVer 范围解析、依赖图、跨服务 Audit Log、镜像缓存——blueprint 明确标成 out of scope。没有版本解析和依赖图的 registry，本质还是个文件夹；先承认这一点，别把 `GET /skills` 夸成 npm。

### 把 Skill 锁进 Release Manifest

Week08 已经把 data / index / prompt / eval 绑在同一个 `release_id` 上。本周补上第四（实际是第 N）元：`skill_release_id` + `skills[]`。每条 skill 锁 `name` + `version` + 64 位 hex `digest`。digest 变了就是内容变了，回滚切 `release_id`，不要靠「再改一版措辞」碰运气。

示例在 `contracts/release/release_manifest_example.json`：`skill_release_id = skills-v0.1.0`，列表里锁了 `rag-contract-check@0.1.0`。讲义那份 YAML（`kind: RAGRelease` / `apiVersion: omnisupport.rag/v2`）**不是**本周运行时格式；仓库 Week09 走的是 JSON 的 v1 schema。名为 v2 的 `release_manifest_v2.schema.json` 是 Week14 治理清单，别在本周找 `kind: RAGRelease`。

### 信任边界（压缩版）

装一个会跑代码的 Skill，权限约等于它能碰到的一切。私有数据 + 不可信内容 + 外部传输三件齐，就可以被窃取。课堂默认：只用仓库内自己写的 Pack；脚本只列出不远程执行；破坏性操作必须走「计划 → 校验 → 执行」，对应 `release-check` 的边界——**不自动 rollback，先出 checklist。** 沙箱、Marketplace、跨团队带鉴权的 Registry，全部留给以后。

OpenAI / MCP 导出也守这条：导出的是 **activation descriptor**（参数只有 `task` + `context_summary`），MCP 标注 `readOnlyHint: true` / `destructiveHint: false` / `idempotentHint: true`。Skill 是说明书，不是 `ticket.update`。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| Skill Pack 总览 | `skills/README.md`<br>`docs/blueprints/week09/week09-skill-pack-blueprint.md`<br>`runbooks/week09-agent-skills.md` | 五个初始 Skill；渐进加载口径；out of scope 清单 |
| L02 目录结构 | `skills/data-contract-lint/`<br>`skills/ingest-backfill-runbook/`<br>`skills/rag-contract-check/`<br>`skills/prompt-release/`<br>`skills/release-check/` | 每个目录都有 `SKILL.md` + `scripts/` + `references/` + `assets/` |
| L02 官方字段 + 团队扩展 | `contracts/skills/skill_pack.schema.json` | `required: name/description/version`；`additionalProperties: false`；`not_for` / `requires` / `evals` |
| L02 scripts 占位 | `skills/data-contract-lint/scripts/lint.py`<br>`skills/rag-contract-check/scripts/check_response.py`<br>`skills/ingest-backfill-runbook/scripts/plan.py`<br>`skills/prompt-release/scripts/plan_release.py`<br>`skills/release-check/scripts/check_manifest.py` | JSON stdout + 非零 exit；功能是 stub，不是讲义里的 ODCS 全量 linter |
| L02 references / assets | 各 Pack 下 `references/*.md`、`assets/*` | 输入侧规范 vs 输出侧模板/fixture |
| L03 渐进加载实现 | `services/tool_api/app/skill_registry.py` | `discover()` 只建 `SkillMeta`；`get_skill()` 才读 body 并列三类文件 |
| L03 / L05 HTTP 面 | `services/tool_api/app/routers/skills.py`<br>`services/tool_api/app/main.py`（`prefix="/api/v1"`） | list 不带 body；get 带 body；exports 是激活描述符 |
| L03 路由预过滤 | `SkillRegistry.search()` | 词项必须全部命中 name/description/tags/inputs/outputs |
| L04 负向路由 | 五份 `SKILL.md` 的 `not_for` + `## Safety Boundaries` | 对比讲义的 TRIGGER / NOT-TRIGGER 章节标题 |
| L05 Pack 契约测试 | `tests/contract/test_week09_skill_packs.py` | frontmatter 过 schema；文件夹名 == name；`not_for` / `outputs` 非空；三类子目录非空 |
| L05 Registry 集成测试 | `tests/integration/test_week09_skill_registry.py` | list 无 body、digest 64 位、OpenAI `strict: true`、MCP `readOnlyHint` |
| L05 Skill 锁进发布 | `contracts/release/release_manifest_schema.json`<br>`contracts/release/release_manifest_example.json` | `skill_release_id` 可空；`skills[].digest` 必须 64 hex |
| L05 路径配置 | `services/tool_api/app/config.py`<br>`infra/docker-compose.yml`（`tool_api` 的 `SKILL_REGISTRY_PATH` + `../skills` 只读挂载） | 容器内默认 `/workspace/skills` |
| 上游工艺（被封装者） | `contracts/data/*.json`<br>`data/seed_manifests/source_manifest_schema.json`<br>`contracts/service/rag_request.schema.json`<br>`contracts/service/rag_response.schema.json`<br>`pipelines/data_factory/backfill_plan.py`<br>`services/rag_api/app/prompts/`<br>`evals/week08/run_smoke_eval.py` | Skill 的 `inputs` / `evals` 指向这些，而不是再造一份 |

### 代码里几个讲义没展开的细节

**仓库契约比官方 spec 更严。** 官方只强制 name + description；`skill_pack.schema.json` 把 `version` 也做成 required，并且 `additionalProperties: false`。测试还断言 `version == "0.1.0"`、`not_for` 非空、`outputs` 非空——schema 本身并不 required 后两项。改 Pack 时先看测试，只看 spec 会漏闸。

**digest 吃的是整份 `SKILL.md` 文本**（frontmatter + body），不是脚本树。改一句 Safety Boundaries，digest 就会变，release 里锁的 hash 对不上。scripts / references / assets 的变更**目前不会**反映进这个 digest——这是本周实现的缝，评 skill 是否「整 Pack 指纹」时要心里有数。

**导出不是业务 Tool。** `openai_tool_exports()` 生成 `activate_skill_rag_contract_check` 这类名字，参数只有 `task` 和 `context_summary`，`strict: true`。MCP 侧是 `skills.activate.<name>`。真正改工单仍走 `contracts/tools/`，那是 Week10。

**`search()` 是 AND 词项过滤**，不是 embedding。`"rag citations"` 能命中 `rag-contract-check`，是因为 description 里同时有这两个词。五个 Pack 够用；上了 50 个这条会开始漏和误伤。

---

## 7. 讲义与仓库对不上的地方

这几处讲义写了但仓库里没有或已经改口径，**别浪费时间去找**：

| 讲义写的 | 实际情况 |
|---|---|
| `skills/data-contract-lint/scripts/lint.py` 是 ODCS YAML + jsonschema 的生产级 linter，还有 `fix.py` | `lint.py` 只检查 JSON 是否缺 `$schema` / `type`；没有 `fix.py`。仓库契约是 `contracts/data/*.json`，不是 ODCS YAML |
| `scripts/check.py`（rag-contract-check） | 实际文件名是 `scripts/check_response.py` |
| `references/odcs-spec.md` | 实际是 `references/data-contract-minimums.md` |
| `.github/workflows/skill-ci.yml`、`tools/skill_lint.py` / `script_lint.py` / `skill_eval.py` / `skill_release.sh` | 都不存在。现有 workflow 是 rag-eval / query-rewrite / week14-governance |
| `release/manifests/rag-v2026.05.18-001.yaml`（`kind: RAGRelease`） | 不存在。Week09 绑定在 JSON 的 `release_manifest_schema.json`；`release_manifest_v2.schema.json` 是 Week14 |
| `eval-set-runner` Skill | 五个初始 Pack 里没有这个名字 |
| 远程脚本执行服务、Marketplace、带鉴权的跨团队 Registry | blueprint 明确本周不做 |
| `docs/assets/week09/skill-pack-code-architecture.png` | `docs/assets/` 目录不存在。blueprint / runbook 都引用了这张图，不影响跑命令 |

讲义 SKILL.md 示例用 `## TRIGGER` / `## NOT-TRIGGER` / `## STEPS` / `## CONSTRAINTS` 七段标题；仓库用 frontmatter `not_for` + 正文 Procedure / Safety Boundaries。语义对齐，目录不对齐——对照时看字段，不要按标题全文检索。

---

## 8. 动手清单

统一走 Docker devbox（Podman 把 `docker compose` 换成 `podman compose`，同一个 compose 文件）。

```bash
cp infra/env/.env.example infra/env/.env.local

DEVBOX="docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox"

# 1. Pack 结构 + frontmatter 契约 + release 能绑 skill
$DEVBOX pytest tests/contract/test_week09_skill_packs.py -v

# 2. 渐进加载 + OpenAI/MCP 导出 + HTTP 面
$DEVBOX pytest tests/integration/test_week09_skill_registry.py -v

# 3. （可选）起 Tool API，用 curl 亲眼看 Stage 1 vs Stage 2
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml \
  up -d --build tool_api
curl http://localhost:8001/api/v1/skills
curl http://localhost:8001/api/v1/skills/rag-contract-check
curl http://localhost:8001/api/v1/skills/exports/openai
curl http://localhost:8001/api/v1/skills/exports/mcp

# 4. 跑一个占位脚本，确认「JSON stdout + exit code」这条纪律
$DEVBOX python skills/data-contract-lint/scripts/lint.py \
  contracts/data/ticket_contract.json
$DEVBOX python skills/rag-contract-check/scripts/check_response.py \
  skills/rag-contract-check/assets/response-fixture.json
```

**验收标准不是「跑过了」，而是能回答这五个问题**：

1. `GET /api/v1/skills` 的 payload 里有没有 `body`？`count` 是不是 5？`progressive_disclosure` 三段分别指哪两个函数？
2. `GET /api/v1/skills/rag-contract-check` 多出来的 `scripts` / `references` / `assets` 路径，是否都能在磁盘上找到对应文件？
3. OpenAI 导出的 tool name 为什么是 `activate_skill_*` 而不是 `ticket_update`？MCP 的 `readOnlyHint` 在守哪条边界？
4. `release_manifest_example.json` 里 `skill_release_id` 和 `skills[0].digest` 各锁了什么？digest 跟 `SkillMeta.digest` 算法是否同一套（现状：示例是占位 0，代码是 sha256 全文）？
5. 五个 Pack 各自 `not_for` 挡的是哪类误激活？和它的 `requires` 指向是否闭环（例如 `prompt-release` 依赖 `rag-contract-check`）？

**加分练习**：

- 删掉某个 Pack 的 `not_for` 或把 `name` 改得和文件夹不一致，确认契约测试失败，并判断这是 schema 层失败还是测试附加断言失败
- 把 `description` 改成 `"helps with data"`，先手算 Stage 1 会不会误激活，再跑 `SkillRegistry.search("rag citations")` 看路由是否塌
- 对照讲义的 ODCS `lint.py` 和仓库占位 `lint.py`，列一张「生产级还缺哪四条」——这正好是 L02 脚本四要点的自测

---

## 9. 易错点与边界

**概念层面**

- Skill ≠ Tool。Skill 是行动手册；Tool 是受契约约束的业务动作。导出 `activate_skill_*` 不会改工单。
- Skill ≠ Prompt 模板。Prompt 约束一次生成；Skill 还带步骤、禁区、脚本和产物。
- Skill ≠ MCP。MCP 解决连接；Skill 解决连上之后怎么干。两者叠加，不是二选一。
- `SKILL.md` ≠ Wiki。加 YAML 头不是迁移，是按 Agent 阅读方式重写。
- `not_for` ≠ 可有可无的备注。它是 Stage 1 的负向路由，缺了就会抢活。
- Discovery 列表 ≠ Activation。列表带 body 就是在全量加载，本周测试会抓。
- digest ≠ 整 Pack 指纹（现状）。它只哈希 `SKILL.md`，脚本改了可能锁不住。
- Registry API ≠ npm。没有版本范围解析和依赖图，就还是个带搜索的目录。

**范围边界（Week09 到底做到哪）**

本周交付的是**可发现、可懒加载、可锁版本的工艺容器**，不是能办事的 Agent。刻意不做：远程脚本沙箱、Marketplace、跨团队带鉴权 Registry、自动破坏性动作、embedding 路由。

Week10 要接的不是「再写几个 Pack」，而是：Function Calling / Tool Contract / 动作权限 / HITL。没有本周的手册，Week10 的 Agent 会有手没谱；只有本周的手册、没有 Week10 的权限闸，Agent 会把说明书当成可以随便执行的命令。

五个 Pack 的上游工艺（契约、补数、RAG、Prompt、发布绑定）已经在 Week02–08 做过。本周是**封装和发现**，不是把那些闸门重写一遍。scripts 是占位，真正的质量仍由原来的 pytest / eval 守门——`evals:` 字段就是这条指针。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. 举一个「工艺随人走」的具体例子，说明它破坏的是可复现、可审计、可迁移里的哪一条。为什么堆到 Confluence 解决不了？
2. Skill / Tool / Prompt / MCP 用一句话各回答「我解决什么」。为什么说 Skill 是容器而不是替代品？
3. 官方 spec 只强制两个字段，仓库 schema 强制三个，测试又额外检查两项。各是哪几个？为什么课堂要把 `version` 做成 required？
4. `references/` 和 `assets/` 的边界怎么划？把正反例放进 `SKILL.md` 正文会打爆哪一个加载阶段？
5. 50 个 Skill 启动全加载和只加载 frontmatter，token 量级差在哪？`GET /api/v1/skills` 不返回 `body` 是为了守哪条纪律？
6. 为什么 `description` 必须同时写「做什么」和「何时用」？给 `data-contract-lint` 写一条会误激活的坏 description，再说它坏在哪条规则。
7. Wiki 和 `SKILL.md` 在「边界」和「失败处理」上分别怎么写？「建议不要删除」为什么不够？
8. 只写 TRIGGER 不写 NOT-TRIGGER，`rag-contract-check` 最可能抢走哪个兄弟 Skill 的活？仓库里对应字段叫什么？
9. 改了 `SKILL.md` 里一句禁区，为什么 release 里锁的 digest 对不上，而改了 `scripts/lint.py` 却可能对得上？这说明指纹算法覆盖了什么、没覆盖什么？
10. OpenAI 导出为什么参数只有 `task` 和 `context_summary`？如果 Agent 直接拿 Skill 去改工单，缺的是 Week09 的哪一层，还是 Week10 的哪一层？
11. 讲义的 YAML Release Manifest 和仓库的 JSON `skill_release_id` 是不是同一份工件？事故回滚时你切的是 Skill 文件夹还是 `release_id`？
12. 什么情况下该把「LLM 直选」换成 embedding 路由？本周五个 Pack 为什么还不必上？

---

## 11. 一句话收口

Week09 不是「给 Agent 再写一份文档周」，而是整门课的**工艺控制面**：把 Week02–08 已经跑通的契约、补数、RAG、Prompt 封装成可版本、可发现、可渐进加载的 Skill Pack。手册先于执行——Week10 的受控 Agent 有没有谱，取决于本周这五个目录写得硬不硬、锁得住锁不住。
