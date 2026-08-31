# Week 04 · Lakehouse 底座：表状态可复现

> **一句话**：把"表里现在有什么"升级成"当时那一版表状态是什么"——用 Iceberg 的 snapshot / manifest / metadata log，给索引、评测、发布装上一个可命名、可回看、可验收的数据锚点。
>
> 讲义：`pdf/doc/week04-Lakehouse 底座.pdf`（124 页 / 5 课时）

---

## 0. 本周主干

Week03 交付的是 ingest correctness（可采、可重跑、可补数），Week04 要交付的是 **table state reproducibility**（可快照、可回看、可验收）。五节课是"判断 → 机制 → 建模 → 实现 → 验收"的直线：

```
L01 Memory          为什么需要"有记忆的表"        判断
      ↓
L02 State Model     snapshot / manifest / log     机制
      ↓
L03 Bronze/Silver   最小 4 表 + source mapping    建模
      ↓
L04 PyIceberg       catalog / warehouse / write   实现
      ↓
L05 Baseline        files / history / snapshots   验收
      ↓
                    → Week05 transform / Week08 retrieval / Week11+ eval & release
```

课程给了一组四比喻，用来划清"能查"和"能回看"的边界，值得单独记住：

**raw bucket 是文件柜，Postgres 当前表是业务视图，pgvector 是搜索目录，Iceberg table 才是数据账本。**
只有账本会为每次提交留下可检查的状态证据。

---

## 1. L01 · 为什么需要"有记忆的表"

### 核心论点

危险的不是表不存在，而是 **状态说不清**。你有数据、有索引、有答案、有日志，但说不清它们对应哪一版状态，复盘就只能变成猜谜。

课程用的坏案例（Northstar Edge Gateway）值得记住形状：周一回答"回滚到 5.7.9"，周三回答"更换硬件"。raw bucket 能查、Postgres 能查、向量索引有结果、prompt 仓库有版本——但没人能说清周一基于哪版文档资产、周三的索引重建消费了哪批文档、评测分数的变化发生在数据变更之前还是索引重建之后。

### 四类数据对象：谁能承担状态账本

| 对象 | 能查当前 | 能回看历史状态 | 该承担的角色 |
|---|---|---|---|
| raw bucket | 能，但要靠路径/清单 | 弱，除非额外版本化 + manifest | 保存原始输入 |
| PostgreSQL 当前表 | 能 | 弱，默认只代表当前业务视图 | 当前事实查询 |
| pgvector / 向量索引 | 能召回 | 弱，索引不等于状态账本 | 服务检索，不负责状态记忆 |
| Iceberg snapshot-able table | 能 | 强，snapshot / history / files 可 inspect | 提交历史与状态锚点 |

"可查"和"可回看"的差异体现在四个场景：历史回看（靠日志备份猜 vs 绑定 snapshot/history）、评测绑定（"可能数据变了" vs 绑定具体 snapshot）、索引重建（只知道重建过 vs 知道消费了哪版文档资产）、release 复盘（代码和 prompt 有版本但数据缺锚点 vs release = 代码 + prompt + table snapshot）。

### 有记忆的表要留下的五类证据

提交后的表状态（每次写入形成状态变更）、当前版本由哪些 files 构成（由 metadata 组织，不靠目录猜）、snapshot 之间的父子关系、schema / partition 演进记录、可引用的状态锚点（供 time travel / baseline / release 绑定）。

### 复盘八问（排障口令）

答案变了，不要先问模型换没换，先问状态能不能绑定：

`raw 文档版本 → ingest batch → Iceberg snapshot → index version → prompt version → eval drift point → business boundary → rollback target`

最后一问是收口：**要回到哪个数据状态，而不只是回滚代码。**

### Iceberg 不是银弹

这是全周最需要提前立住的边界，避免把 Week04 误解成万能湖仓方案：不自动修数据质量（坏数据写进去，snapshot 只帮你记住坏在哪一版）、不自动让 RAG 变准、不替代 Week02 contract（谁能进仍由 contract 管）、不替代 eval / tracing、不自动完成治理回滚（回滚需要策略、审批、runbook 和验证）。

---

## 2. L02 · Iceberg 的状态模型

### 核心论点

**Iceberg 不是"按日期分目录"的升级版。** 它用 metadata 把一次表状态提交组织成可追踪对象，这才让 time travel、schema evolution 和 reliable read 成立。

### 状态对象：每个对象只回答一个问题

| 对象 | 是什么 | 工程上解决什么 |
|---|---|---|
| table metadata file | 表的状态说明书 | 存 schema、snapshots 列表、current snapshot 引用 |
| snapshot | 一版表状态 | 让一次提交可命名、可引用、可回看 |
| manifest list | snapshot 的 manifest 索引 | 不必读完所有 manifest 就能规划 scan |
| manifest | data files 清单 + 统计 | 确定哪些 file 属于这一版状态 |
| data file | 实际 Parquet 文件 | 承载数据，但单独不代表表状态 |
| metadata log | metadata 文件演进记录 | 支撑状态证据链 |
| history | 谁在何时成为 current | 支撑复盘和 baseline |

读取链路是固定的：`current metadata pointer → metadata.json → snapshot → manifest list → manifest files → data files`。

### Git 类比：有用，但有边界

| Git | Iceberg | 类比到哪里为止 |
|---|---|---|
| commit | snapshot | 记录表状态，不是代码 diff |
| commit history | metadata log / history | 记录状态演进，不是开发分支历史 |
| 文件清单 | manifest / manifest list | 额外记录 data file 统计信息 |
| 工作目录文件 | data files | 文件本身不等于表状态 |
| checkout old commit | time travel old snapshot | 回到旧状态集合，不复制旧表 |

### Time travel 为什么不是复制整张表

它只是换一个入口读同一批文件：给定 `snapshot_id` → 找到该 snapshot 的 manifest list → 展开 manifest → 得到那一版引用的 files 集合。代价不是存储，而是 **保留策略**：旧 snapshot 一旦 expire，可回看的时间窗就缩短了。

### Metadata inspection 的观察顺序

不要各看各的，顺序是有意义的：

`snapshots`（有没有明确的状态提交）→ `history`（当前状态如何演进）→ `files`（文件是否过碎过散）→ `metadata log`（状态链是否有足够历史）→ 写进 baseline report。

### 常见 inspection 字段

| 字段 | 回答什么 | 为什么重要 |
|---|---|---|
| `snapshot_id` | 是哪一版状态 | index / eval / release 的绑定对象 |
| `parent_snapshot_id` | 上一版是谁 | 构成状态时间线 |
| `made_current_at` / `timestamp_ms` | 何时成为 current | 坏案例复盘定位时间点 |
| `operation` | append / overwrite / replace | 解释状态变化类型 |
| `manifest_list` | snapshot 指向的 manifest list | 从状态到文件清单的桥 |
| `file_path` | 实际 data file 路径 | 文件证据入口 |
| `record_count` / `file_size` | 规模与小文件信号 | baseline 的核心指标 |
| `latest_schema_id` | 当前 schema 版本 | schema evolution 证据 |

### 可靠性与并发的机制底座

三个机制互相咬合：**atomic metadata swap**（提交时替换 current table metadata file path，不是原地改文件）、**optimistic concurrency**（写者基于当前状态写新 metadata，冲突后 retry 并重新校验假设是否成立）、**reliable read**（读者始终读一个一致的 snapshot，不需要持锁）。

### Schema / Partition evolution 的边界

Iceberg 支持 add / drop / rename / update / reorder，并且 schema 变更是 **metadata change，不需要重写 data files**；partition spec 也可以更新（旧数据保持旧布局，新数据进新布局）。但课程边界很明确：**Week04 只演示 add-column**，复杂兼容性、权限语义、下游消费留给后续治理周。

---

## 3. L03 · Bronze / Silver 最小表设计

### 核心论点

**表越多不代表越生产级。** 第一版 Lakehouse 的能力不是表的数量，而是这些表能真实写入、形成 snapshot、被回看、被验收。第一版失败通常不是表太少，而是最小闭环没站稳、层数却先堆起来。

### 最小 4 表地图

| 表 | 层级 | 从哪里来 | 解决什么 | 后续消费 |
|---|---|---|---|---|
| `bronze.raw_ticket_event` | Bronze | Week03 ticket ingest | 保留工单原始事件与 replay 入口 | `silver.ticket_fact` / Week05 |
| `bronze.raw_doc_asset` | Bronze | MinIO raw docs / doc ingest | 保留文档资产与版本状态 | `silver.knowledge_doc` / Week08 |
| `silver.ticket_fact` | Silver | `raw_ticket_event` | 统一工单事实与当前状态 | Week05 semantic layer |
| `silver.knowledge_doc` | Silver | `raw_doc_asset` | 统一知识文档资产状态 | Week08 retrieval consistency |

三层的正确角色：**Bronze** 是尽量保真的入湖记录，保留输入状态与 replay 入口；**Silver** 是稳定可消费的业务对象，统一事实与资产状态；**Gold** 是语义层、指标层、服务层与消费接口，Week05+ 才展开。

### 本周明确不交付什么

`knowledge_section` 和 `evidence_anchor` 只预留边界（Week07/08 展开 evidence serving）；`support_kpi_mart`（Week05+ 指标层）和 `kb_serving_asset`（Serving/RAG 周）完全不做。

注意：这四张表的 schema 在 `iceberg_schemas.py` 里都已经定义了。**schema 文件出现的表不等于本周要物化的表**——这正是课程点名的 scope creep 陷阱。

### Source-to-Iceberg mapping 必须先于建表

理由很具体：coding agent 最容易在字段名、nullable、时间语义、去重键上跑偏。mapping 至少要有七列，每一列对应一种跑偏方式：

| 列 | 缺失时会发生什么 |
|---|---|
| source object / source field | agent 随意猜源、字段名误写 |
| target table / field | 目标表混乱 |
| transform（派生 / cast / normalize） | 时间语义被悄悄改掉 |
| required | nullable 随意扩散 |
| dedupe key | 重复写入 |
| idempotency strategy | 重跑产生不可解释的重复 |

**Schema source of truth 的优先级**：`iceberg_schemas.py` > 实际 DDL / source 表定义 > Week02 data contract > Week03 manifest / ingest 输出。课程页面不是权威，不要照抄 PPT 里的字段。

### Hidden partitioning vs 手工目录分区

这不是路径风格问题，是状态演进与查询边界问题：

| 维度 | 手工目录分区 | Iceberg hidden partitioning |
|---|---|---|
| 查询写法 | 容易依赖目录字段 | 写逻辑字段，由表格式做 transform 与 pruning |
| 布局演进 | 改布局往往要新表 / 改查询 | partition evolution，新旧布局共存 |
| 回放边界 | 靠路径约定 | 绑定 metadata / partition spec |
| baseline 记录 | 容易只记录路径 | 记录 table + snapshot + files + partition distribution |

分区判断准则：**分区字段必须服务查询模式和回放边界，不是为了高级感。** 小数据集盲目分区只增加复杂度；spec 变化必须进 baseline report。

### 两个设计事故（都很容易犯）

- **Bronze 过早做业务解释**：Bronze 里提前合并 status，看起来"干净"、Silver 写起来省事、第一次 demo 很顺；但保真入口丢了，出现 bad case 时无法判断是源数据问题还是 transform 问题，replay/backfill 失效。
- **Silver blind append**：每批 ticket 更新都 append 一批，写入总是成功、snapshot 也在增长、row count 看起来更丰富；但同一 ticket 多行、查当前事实取到旧状态、KPI 漂移。**Silver 不是 raw event dump**，当前事实需要稳定 key 与语义。

其余常见错误：分区字段和查询无关、用技术字段替代业务键（业务 dedupe/idempotency 不稳）、课程页面随意发明字段。

---

## 4. L04 · PyIceberg 本地最小闭环

### 核心论点

Week04 不是重型基础设施秀。先用 **PyIceberg + PostgreSQL SQL Catalog + MinIO warehouse** 让核心机制可见、可跑、可验收，再谈平台全家桶。

### 路线选型

| 路线 | 本地复杂度 | 结论与理由 |
|---|---|---|
| PyIceberg + PostgreSQL SQL Catalog + MinIO | 中 | 推荐主线，完整覆盖 catalog / warehouse / write / inspect / evolution |
| PyIceberg + SQLite Catalog | 低 | 适合个人探索，但与多容器教学基线不一致 |
| REST Catalog | 中高 | 覆盖 catalog 机制，但学生本地排错成本偏高 |
| Spark + Hive / Nessie / Trino | 高 | 都会抢走状态模型的注意力 |

四个排除理由各不相同，值得分开记：Spark 把注意力带到分布式计算；Hive Metastore 本地负担偏重；Nessie 引入 catalog branching，那是 release/branching 语义（后续周）；Trino 把重点带到查询服务层。

### 三层配置必须拆开

| 概念 | 是什么 | 本仓库取值 |
|---|---|---|
| Catalog | 记录表在哪里、metadata 在哪里 | `sql` type，`postgresql+psycopg2://...@postgres:5432/omnisupport` |
| Warehouse | Iceberg metadata 和 data files 的存储根 | `s3://omni-lakehouse/warehouse` |
| Table Location | 某张表在 warehouse 里的具体位置 | `{warehouse}/{namespace}.db/{table}` |

**最常见的误解**：PostgreSQL 不存所有 Iceberg 数据文件（它只存 catalog 层的表指针），MinIO 也不是普通文件堆（它同时存 metadata 和 parquet）。

配置必须走 env，不能写死在课程代码里。写错的后果分层很清楚：catalog type 错 → 加载方式错；uri 错 → namespace/table 读写失败；warehouse root 错 → 文件落错 bucket；s3 endpoint 错 → **本机能跑但容器里失败**；access key 错 → 写文件权限失败；namespace 错 → 表注册到错误空间。

一次 materialize 背后至少发生十件事：`读 env 配置 → load SQL Catalog → ensure namespace → ensure table schema → 读取输入 → 按 mapping 转换成 Arrow → append/overwrite → 产生 snapshot → inspect history/files/snapshots → 输出 report`。

### 五条最小防线

这些防线决定 Week04 是工程闭环，而不是"脚本碰巧跑过"。

| 防线 | 作用 | 缺失后果 |
|---|---|---|
| dry-run | 先展示计划与影响，不污染表状态 | 试错直接写坏表 |
| materialization plan | 明确 source / target / schema / dedupe key | agent 随意猜字段 |
| schema validation | 写入前确认字段、类型、nullable | 写入后才发现 schema 错 |
| deterministic dedupe | 同一输入重复到达，结果可预测 | 重复不可解释 |
| idempotency | 同一次 materialization 重跑无不可解释副作用 | 重跑越写越脏 |

### PyIceberg 本周要用的 API

```python
load_catalog(...)                      # 加载 SQL Catalog
catalog.create_namespace / list_namespaces
catalog.create_table                   # 本仓库用 create_table_if_not_exists
catalog.load_table                     # 定位已有表
table.append / table.overwrite         # 形成新 snapshot
table.scan().to_arrow()                # 验证数据可读
table.metadata.snapshots / table.history() /
  table.scan().plan_files() / table.metadata.metadata_log   # 状态检查
table.update_schema().add_column()     # add-column 演进
```

### append vs overwrite 的边界

append 适合新批次追加到 Bronze 或新增事实状态，风险是重复输入必须靠 dedupe / idempotency 解释。overwrite 适合可控重写目标状态或分区，风险一句话：**不要无解释地覆盖历史。** 无论哪种，写入动作必须能在 report 里被解释，schema evolution 必须记录兼容性说明，time travel 检查则依赖 snapshot 保留策略。

**为什么 Dagster 本周只做 thin wrapper**：核心逻辑先放在可直接调用的 Python module，CLI / devbox 先跑通；`pyproject.toml` 改了不等于 Dagster 容器就可用；asset factory / partition / backfill 留到 Week06。本周重点是 PyIceberg table state，不是 orchestration 厚包装。

### 排错先定位层级

| 现象 | 可能原因 | 排查动作 |
|---|---|---|
| catalog load 失败 | catalog type / uri / env 错 | 打印配置来源，**不打印 secret** |
| MinIO endpoint 连不上 | 容器内外 endpoint 不一致 | 区分 `localhost` 与服务名 `minio` |
| bucket 不存在 | warehouse root 不可写 | 确认 bucket / access key |
| schema 不匹配 | source of truth 不一致 | 回到 `iceberg_schemas.py` / mapping |
| 重跑出现重复 | dedupe / idempotency 不清 | 先看 key 和 report |
| inspect 没有 snapshot | 只 ensure 了表，没写入数据 | 确认 append/overwrite 是否真的发生 |

---

## 5. L05 · 性能基线不是调优冲动

### 核心论点

**没有 baseline，就没有真正的优化，只有一堆模糊感受。** Week04 的验收不是"我们用了 Iceberg"，而是"团队已经有第一份可复核的数据状态基线"。

### 四个概念必须分开

| 概念 | 目标 | Week04 是否主做 |
|---|---|---|
| Baseline | 记录当前状态：表、files、snapshots、history、schema evolution | 主做 |
| Benchmark | 测性能上限：吞吐、延迟、并发 | 不做 |
| Tuning | 改变系统行为求更好表现：compaction、partition、cache | 不做 |
| Maintenance | 控制 snapshots、metadata、orphan files、small files | 只讲边界 |

### 必须记录的指标

| 指标 | 异常信号 |
|---|---|
| row count | 与 source coverage 不一致 |
| snapshot count | 过多或过少都要解释 |
| file count / avg / min / max file size | 文件特别碎，小文件过多或极端不均 |
| partition distribution | 极不均匀或不符合查询模式 |
| latest snapshot time | 与 ingest / release 时间对不上 |
| metadata log entry count | 保留策略可能不足 |

### 组合口径：三个视角必须一起读

单看 `snapshots` 只知道提交了几次，单看 `files` 只知道文件碎不碎。要能连起来回答一句话：**这次写入产生了哪个 snapshot？当前引用哪些 files？是否与 source coverage 对得上？** Data owner 的阅读顺序是：表清单（4 表是否都形成状态）→ snapshot（本周几次提交）→ files（是否过碎过小）→ schema evolution（add-column 有没有留证据）→ 结论（哪些异常本周修，哪些留后续）。

### 异常先记录，不急着修

| 现象 | 可能原因 | 本周是否修 |
|---|---|---|
| snapshot 特别多 | 频繁小批写入 / 重试 / 多次 demo | 记录，不急着 expire |
| 文件特别小 | 每次 append 数据量太小 | 记录，不急着 compaction |
| row count 和源表不一致 | mapping / dedupe / missing handling 问题 | **优先解释** |
| schema id 变了但无记录 | schema evolution 没写 notes | 本周补文档 |
| time travel 读不到旧 snapshot | snapshot 过期或未形成旧状态 | 先解释保留边界 |

### 维护动作的时机

四类动作本周都只讲边界不做：`expire snapshots`（历史太多且已有保留策略时才考虑，代价是缩短 time travel 历史）、`orphan file cleanup`（出现未被 metadata 引用的遗留文件，只记录风险）、`compaction`（小文件明显影响读取时，且必须先有 baseline）、`metadata cleanup`（记录 metadata log 和保留策略即可）。

讲义三个事故的形状是同一个：**看起来维护成功（metadata 变小、当前表仍可读），实际旧状态不可回看、评测和 release 复盘断链。**

### 报告分级

**无效**：只有截图；只有命令没有结果；只有"成功了"没有状态证据。**合格**：覆盖 4 表、snapshot、files、history、time travel、schema evolution。**优秀**：再加上环境说明、命令/输出来源、异常解释和下一步建议，可以直接交接给团队。

---

## 6. 概念 → 代码映射

以下路径均已在仓库中核对存在。

| 讲义概念 | 仓库位置 | 重点看什么 |
|---|---|---|
| L01 Week04 为什么存在 | `docs/blueprints/week04/lakehouse_foundation_v1.md` | 技术选型理由 + 七条 explicit non-goals |
| L02 状态模型 / inspection | `pipelines/lakehouse/inspect_metadata.py` | 四个 view：`snapshots` / `history` / `files` / `metadata-log` |
| L02 time travel | `pipelines/lakehouse/demo_time_travel.py` | `table.scan(snapshot_id=...)` 与当前行数对比 |
| L03 最小 4 表 schema | `pipelines/lakehouse/iceberg_schemas.py` | `BRONZE_SCHEMAS` / `SILVER_SCHEMAS` / `GOLD_SCHEMAS` 三层字典 |
| L03 4 表设计说明 | `docs/blueprints/week04/bronze_silver_table_design_v1.md` | Design Rules 五条 |
| L03 source mapping | `docs/blueprints/week04/source_to_iceberg_mapping_v1.md` | 字段级映射 + Field Gaps 一节 |
| L03 源表 DDL | `infra/migrations/001_init.sql` | `raw_doc_asset` / `raw_ticket_event` / `ticket_fact` / `knowledge_doc` |
| L04 配置层 | `pipelines/lakehouse/settings.py` | `LakehouseSettings` 默认值、`validate()`、`to_safe_dict()` |
| L04 catalog / namespace / 建表 | `pipelines/lakehouse/catalog.py` | `CORE_TABLES`、`ensure_lakehouse_bucket()`、`ensure_core_tables()` |
| L04 materialization | `pipelines/lakehouse/materialize.py` | `TABLE_QUERIES` 四条 SQL、`--plan` / `--dry-run` 分支 |
| L04 schema evolution | `pipelines/lakehouse/demo_schema_evolution.py` | 只允许 `add_column`，默认加 `source_checksum_algo` |
| L04 运行时计划 | `docs/blueprints/week04/catalog_runtime_plan_v1.md` | 15 个必需 env key |
| L04 Dagster thin wrapper | `pipelines/lakehouse/assets.py` | `_try_ensure_week04_tables()` 的 best-effort 降级 |
| L04 环境定义 | `infra/docker-compose.yml`（`minio` / `minio_init` / `devbox` / `dagster`）<br>`infra/env/.env.example`（L79-97）<br>`infra/devbox.Dockerfile` | `omni-lakehouse` bucket 在 `minio_init` 里创建；`ICEBERG_*` env 在 devbox 和 dagster 两处都注入 |
| L05 baseline 生成 | `pipelines/lakehouse/perf_baseline.py` | `table_baseline()` 输出的指标字段、`known_limits` |
| L05 baseline 模板 | `docs/blueprints/week04/perf_baseline_template.md` | Minimum fields 清单 |
| 全周运行路径 | `runbooks/week04/README.md`<br>`pipelines/lakehouse/README.md` | 11 步 + Troubleshooting 表；Core reading order 七个文件 |
| 契约测试 | `tests/contract/test_week4_iceberg_schema_contract.py` | env key 齐全性 + 4 表必须有 time 字段和 trace 字段 |
| 集成测试 | `tests/integration/test_week4_catalog_smoke.py`<br>`test_week4_lakehouse_smoke.py`<br>`test_week4_time_travel.py`<br>`test_week4_perf_baseline.py` | 全部用 `pytest.importorskip("pyiceberg")` 做软依赖 |
| 课程站同步包 | `docs/blueprints/week04/course_site_sync_packet_v1.md` | 只允许同步仓库里真实存在的命令 |

### 代码里值得单独看、讲义没展开的细节

**四张核心表实际上没有分区。** `iceberg_schemas.py` 为每张表都写了 `partition_spec`（如 `[("ingest_ts", "day")]`、`[("product_line", "identity"), ("created_at", "month")]`）和 `sort_order`，但 `catalog.py::ensure_core_tables()` 调 `create_table_if_not_exists` 时只传了 `identifier` / `schema` / `location` / `properties`，**没有传 partition spec**。所以 L03 讲的 hidden partitioning 在本周是纯概念，`perf_baseline.py` 的 `known_limits` 也承认了这一点："Partition distribution is omitted for unpartitioned Student Core Pack tables."

**四张表全部用 overwrite，不是 append。** `materialize.py` 里只有 `table.overwrite(...)` 一条写入路径。这是有意的保守选择（`lakehouse_foundation_v1.md` 的 Write Modes 表给了理由：Silver 是当前状态表，不能 blind append），但要意识到：讲义 L02/L03 的 snapshot 时间线示例是 append 语义，而代码里每次 materialize 都是全量重写。

**dedupe 只在 Bronze 的 ticket 表里做，而且写在 SQL 里**：`SELECT DISTINCT ON (source_id, source_fingerprint) ... ORDER BY source_id, source_fingerprint, ingest_ts DESC`。去重键是 `source_id + source_fingerprint`（不是 `event_id`——mapping 文档明确说 PostgreSQL 的默认 UUID 不是自然键），冲突时保留 `ingest_ts` 最新的一行。

**`--plan` 和 `--dry-run` 不是一回事。** `--plan` 完全不连 catalog（`catalog = None if plan else ...`），只读源库统计行数；`--dry-run` 仍然会 `load_lakehouse_catalog` 并 `ensure_core_tables`，只是不写 snapshot。想彻底离线验证走 `--plan`。

**源表为空时，表建出来但没有 snapshot。** `materialize.py` 判断 `arrow_table.num_rows == 0` 就跳过写入，返回 `snapshot_id: null` 和 note。这正是讲义排错表里"inspect 没有 snapshot"的根因，也会让 `demo_time_travel` 返回 `status: "no_snapshots"`。先跑 Week03 ingest 灌数据，再跑 Week04。

**snapshot 上挂了业务 property，这是全周最有价值的一行设计。** `table.overwrite()` 传入的 `snapshot_properties` 包含 `omni.week`、`omni.data_release_id`（默认 `week04-dev-local`）、`omni.ingest_batch_id`（默认 `week04-smoke`）、`omni.write_mode`。这就是把"数据状态"和"release / batch"真正绑在一起的地方，也是 Week11+ 评测和发布能引用数据状态的技术前提。

**time travel demo 默认选的是最旧的 snapshot，不是上一版。** `snapshot_id = snapshots[0].snapshot_id`——`table.metadata.snapshots` 通常按时间正序，所以默认对比的是"第一版 vs 当前版"。要演示"上一版"，得手动传 `--snapshot-id`。

**`settings.py` 把路线选型写成了硬约束，并内建 secret 脱敏。** `validate()` 要求 catalog type 必须是 `sql`、catalog uri 必须以 `postgresql` 开头、warehouse 必须是 `s3://` 且带 bucket 名——REST catalog / SQLite catalog 在代码层就被拒了，不只是文档上"不推荐"。`to_safe_dict()` 把 `s3_secret_access_key` 替换为 `***` 并用 `_redact_password()` 给 DSN 密码打码，正好落实"打印配置来源，不打印 secret"的排错纪律。

**pyiceberg 是 dev 可选依赖，不是主依赖。** `pyproject.toml` 里 `pyiceberg[sql-postgres,pyarrow]>=0.11.1,<0.12` 位于 `[project.optional-dependencies] dev`。所以四个集成测试都用 `pytest.importorskip("pyiceberg")`——环境没装就静默跳过，不会报红。**"测试通过"可能只是"测试被跳过"**，验收时要确认真的跑了。

---

## 7. 讲义与仓库对不上的地方

**最大的一条：讲义整体停留在"代码尚未落地"的阶段。** L01 p18 和 L04 p88 反复写"不要伪造命令""待 Week4 项目代码落地后同步 `pipelines.lakehouse.*` 的真实命令"，只给了 `mkdir` / `touch` 占位。但仓库里代码已经完整落地，真实命令在 `README.md` 的 "Week04 Lakehouse 最小闭环" 和 `runbooks/week04/README.md` 里。**直接用 runbook，忽略讲义的占位页。**

讲义点名的产出工件，有一半不在仓库里：

| 讲义写的路径 | 实际情况 |
|---|---|
| `docs/blueprints/week04/state_memory_questions_v1.md` | 不存在。复盘八问只在讲义 p12，仓库里没有对应文件 |
| `snapshot_state_model_v1.md` / `time_travel_demo_notes.md`（L02 产出） | 都不存在。time travel 的证据是运行时生成的 `reports/week04/time_travel_demo_report.md` |
| `reports/week04/schema_evolution_demo_notes.md`（L04 产出） | 不存在。实际是 `demo_schema_evolution --out` 生成 `schema_evolution_demo_report.md` |
| `runbooks/week04/baseline_inspection_notes.md`（L05 产出） | 不存在。runbook 只有 `README.md` 一个文件 |
| `reports/week04/iceberg_baseline_report.md` | 仓库里没有，需要自己跑 `perf_baseline` 生成。注意 `reports/week04/.gitignore` 忽略 `*.md` / `*.json` / `*.png`，跑出来的报告不会进 git |

其余对不上的地方：

- **L01 p17 说 `pipelines/lakehouse/assets.py` 是"后续 Dagster thin wrapper 入口"**——它已经存在，而且已经写了 `_try_ensure_week04_tables()` 的 best-effort 逻辑，失败时返回 `devbox_cli_primary_path`。
- **`docs/assets/week04/lakehouse-code-relationship.png` 不存在。** `runbooks/week04/README.md` 和 `pipelines/lakehouse/README.md` 都用 `![...]` 引用了它，整个 `docs/assets/` 目录都没有。两处 Markdown 的图会是坏链。
- **"Dagster 用上游镜像所以没有 pyiceberg"这个理由已经过时。** `lakehouse_foundation_v1.md` 说 compose 用 `dagster/dagster-k8s` 上游镜像、`catalog_runtime_plan_v1.md` 也这么写；但 `infra/docker-compose.yml` 的 `dagster` service 实际是 `build: infra/dagster.Dockerfile`，而那个 Dockerfile 执行了 `pip install -e ".[dev]"`，pyiceberg 是装上的。thin wrapper 的结论本周仍然成立（Week06 才做编排），但文档给的理由和代码不一致。
- **`write_mode` 字符串在两处不一致。** `catalog.py::_write_mode()` 给 bronze 表写的表属性是 `deterministic_full_refresh_from_deduped_source`，而 `materialize.py::_write_mode()` 写进 snapshot property 和 report 的是 `deduped_full_refresh`。同一张表在表属性和运行报告里 write_mode 不同名，做 baseline 交叉核对时会踩。
- **`assets.py` 的 docstring 超出了本周边界**：写着"Week04: 真实建表，写入 ticket_fact/knowledge_doc/knowledge_section/evidence_anchor"，但代码只 ensure 前两张，而 L03 明确说 `knowledge_section` / `evidence_anchor` 本周只预留边界。
- **讲义的 "INDUSTRY SIGNALS" 页（p19 / p46 / p71 / p97 / p119）** 五次重复引用 Iceberg 官方文档的同几句话（atomic metadata swap、hidden partitioning、expire snapshots 缩短 time travel、PyIceberg 无需 JVM）。这些判断已经融进上面各节，单独看没有增量。

---

## 8. 动手清单

所有命令统一走 Docker devbox。**顺序不能乱**：源库没数据的话，后面全是空 snapshot。前置条件是 Week03 ingest 已经往 PostgreSQL 灌过数据。

```bash
# 起依赖：minio_init 会创建 omni-lakehouse bucket
cp infra/env/.env.example infra/env/.env.local
docker compose --env-file infra/env/.env.local -f infra/docker-compose.yml \
  up -d --build postgres minio minio_init

# 下面所有命令统一用这个前缀
DEV="docker compose --profile tools --env-file infra/env/.env.local \
  -f infra/docker-compose.yml run --rm devbox"

# 1. 校验环境契约，期望 ok: true
$DEV python -m pipelines.lakehouse.settings --check
# 2. catalog + bucket + namespace + 4 表 ensure
$DEV python -m pipelines.lakehouse.catalog --smoke
# 3. 先 dry-run 看源行数，再真写
$DEV python -m pipelines.lakehouse.materialize --all-core --dry-run
$DEV python -m pipelines.lakehouse.materialize --all-core \
      --report-json reports/week04/materialization_report.json
# 4. 按 snapshots → history → files → metadata-log 的顺序 inspect
$DEV python -m pipelines.lakehouse.inspect_metadata \
      --table silver.ticket_fact --view snapshots
# 5. time travel（先把第 3 步跑两遍，否则只有一个 snapshot 没法对比）
$DEV python -m pipelines.lakehouse.demo_time_travel \
      --table silver.ticket_fact --out reports/week04/time_travel_demo_report.md
# 6. add-column schema evolution
$DEV python -m pipelines.lakehouse.demo_schema_evolution \
      --table bronze.raw_doc_asset --add-column source_checksum_algo \
      --out reports/week04/schema_evolution_demo_report.md
# 7. baseline report
$DEV python -m pipelines.lakehouse.perf_baseline --all-core \
      --out reports/week04/iceberg_baseline_report.md
# 8. 测试
$DEV pytest tests/contract/test_week4_iceberg_schema_contract.py \
            tests/integration/test_week4_catalog_smoke.py \
            tests/integration/test_week4_lakehouse_smoke.py \
            tests/integration/test_week4_time_travel.py \
            tests/integration/test_week4_perf_baseline.py -v
```

**验收标准不是"跑过了"，而是能回答这七个问题**：

1. 四张核心表分别在 warehouse 的哪个 location？catalog 里注册在哪个 namespace？
2. 这次 materialize 产生了哪些 `snapshot_id`？每个 snapshot 的 `operation` 是什么？
3. 当前 snapshot 引用了多少个 data file？总行数与 PostgreSQL 源表对不对得上？对不上是 dedupe 还是 missing handling？
4. `snapshot_properties` 里的 `omni.data_release_id` 是什么？Week11 的评测要绑定的就是这个值。
5. time travel 选中的 snapshot 行数和当前行数差多少？差值能否用两次 materialize 之间源库的变化解释？
6. add-column 之后 `latest_schema_id` 变了没有？新字段在旧 snapshot 里读出来是什么？
7. baseline report 里的 file_count / avg_file_size 是否偏小？如果偏小，本周为什么**不**做 compaction？

**加分练习**：

- 只跑 `catalog --smoke` 不跑 materialize，然后 inspect snapshots——亲自制造一次"表存在但没有状态证据"，这是讲义 anti-pattern 里排第二的错误。
- 跑两次 materialize，用 `--view history` 对比 `made_current_at`，再用 `demo_time_travel --snapshot-id <第一次的 id>` 验证旧状态还在。
- 把 `iceberg_schemas.py` 里某张表的 `partition_spec` 改掉再跑 `catalog --smoke`，观察表的 partition 有没有变化——你会发现完全没变，因为建表时根本没传 partition spec。这是理解"schema 文件不等于落地状态"最快的方式。
- 故意把 `ICEBERG_S3_ENDPOINT` 改成 `http://localhost:9000` 再跑 smoke，体会"本机能跑、容器里失败"这类问题。

### 动手清单参考答案

先自己答完上面的验收问题和加分练习，再往下对。

1. Warehouse 根是 `s3://omni-lakehouse/warehouse`；四张表 location 是 `{warehouse}/{namespace}.db/{table}`，即 `.../bronze.db/raw_ticket_event`、`.../bronze.db/raw_doc_asset`、`.../silver.db/ticket_fact`、`.../silver.db/knowledge_doc`。Catalog 命名空间是 `bronze` / `silver`（PostgreSQL SQL Catalog 只存表指针，Parquet 在 MinIO）。
2. 真写走 `table.overwrite`，`operation` 应是 overwrite / replace 一类，不是 append。`snapshot_id` 在 `reports/week04/materialization_report.json` 里；源表为空会 `snapshot_id: null`（只 ensure 不提交）。要有可对比的历史，第 3 步需跑两遍。
3. 用 `--view files` 看当前 snapshot 的 data file 数和 `record_count`。对不上优先查 Bronze ticket 的 `DISTINCT ON (source_id, source_fingerprint)`（去重会少于源行），其次才是空源跳过写入。不要假设「写入成功 = 行数相等」。
4. 默认 `omni.data_release_id=week04-dev-local`（可用 `WEEK04_DATA_RELEASE_ID` 覆盖），和 `omni.ingest_batch_id` / `omni.week` / `omni.write_mode` 一起写进 snapshot property。Week11 评测要绑的是这个数据状态，不是「当时代码能跑」。
5. demo 默认拿**最旧** snapshot 对比当前。两次 materialize 之间源库没变，行数差可以是 0；有变，差值应能用源表变化解释。对不上就先查是不是看错了 snapshot（不是「上一版」除非手动传 `--snapshot-id`）。
6. add-column 后 `latest_schema_id` 应增加。演进是 metadata change，不重写旧 Parquet；旧 snapshot 读新列一般是 null。这只证明「能回看旧状态 + 新字段有版本」，不是随便 rename/drop。
7. smoke 数据量小，`file_count` 往往偏多、`avg_file_size` 偏小。本周正确动作是记进 baseline，**不做 compaction**：没有基线的清理看起来像维护成功，实际缩短可回看历史。compaction / expire 是后续维护，且要先有保留策略。

加分练习：
- 只跑 `catalog --smoke` 再 inspect：表在、snapshots 空。这就是「表存在 ≠ 有状态证据」——ensure 不等于提交。
- 跑两次 materialize 后，`--view history` 应看到两次 `made_current_at`；用第一次的 `snapshot_id` 做 time travel，旧行数仍在。说明 overwrite 仍留 snapshot 链，不是物理删表。
- 改 `iceberg_schemas.py` 的 `partition_spec` 再 `--smoke`：已存在的表 **partition 不变**。建表调用没传 spec，schema 文件里的分区只是概念。看完改动应还原，避免本地 schema 和笔记不一致。
- 容器里把 endpoint 写成 `localhost:9000`：本机进程也许能打到 MinIO，devbox 里会连错。这只说明配置要走服务名 `minio`，改完记得改回 `.env.local`。

---

## 9. 易错点与边界

**概念层面**

- snapshot ≠ 一个文件。它是一版可命名、可引用、可回看的表状态，指向一组 metadata 和 data files。
- manifest ≠ 目录清单。它记录 data files **加统计信息**（record_count、size、lower/upper bounds），是 scan planning 的输入。
- time travel ≠ 复制多份表。它换的是读取入口（snapshot id → manifest list → files），不复制数据。
- Iceberg ≠ 按日期分目录的升级版。`s3://table/date=.../` 表达不了原子提交、schema 版本和状态绑定。
- 有对象存储 ≠ Lakehouse；有向量库 ≠ 能复现回答。前者缺提交历史，后者不是数据账本。
- Baseline ≠ benchmark ≠ tuning。baseline 记录当前状态，benchmark 测上限，tuning 改行为。
- Bronze ≠ Silver。Bronze 保真（不做业务解释），Silver 统一（不 blind append）。schema evolution 支持 ≠ 可以随便改：本周只做 add-column，rename / drop / retype 会打破下游承诺。
- cleanup 越早 ≠ 越好。expire snapshots 会直接缩短可回看历史，必须先有保留策略和 baseline 记录。
- 表存在 ≠ 有状态证据（只 ensure 不写入，snapshot 是空的）；写入成功 ≠ 验收通过（要能 inspect 并组合解释）。

**范围边界（Week04 到底做到哪）**

README 的 "Week04 Lakehouse 最小闭环" 一节把边界写死了，`lakehouse_foundation_v1.md` 的 explicit non-goals 也是同一份清单：

- **不引入 Spark / Hive Metastore / Nessie / Trino / REST catalog**。理由各不相同（分布式计算、本地负担、branching 语义、查询层、排错成本），但结论一致：都会抢走"状态模型"这条主线的注意力。
- **不做 dbt semantic layer，不做 Gold mart，不把 RAG / 索引迁到 Iceberg**。`support_kpi_mart` / `kb_serving_asset` 虽然在 `GOLD_SCHEMAS` 里有定义，但本周一张都不物化；`knowledge_section` / `evidence_anchor` 也只预留边界，Week07/08 才展开。
- **Dagster 不是主执行路径**，只做 thin wrapper；devbox CLI 才是 source of truth。asset factory / partition / backfill 是 Week06。
- **不做 compaction / expire snapshots / orphan cleanup，只做 add-column 级 schema evolution**，其余只讲边界和风险。

留给后面的接口很清楚：Week05 transform 消费哪版 Silver、Week06 把 materialization 与 baseline 证据挂进资产图、Week08 索引对应哪版文档资产、Week11+ 评测与发布绑定数据状态而不只绑代码。

---

## 10. 自测题

答不上来说明这一节需要回看。

1. raw bucket、PostgreSQL 当前表、pgvector、Iceberg table 都能"查到数据"，为什么只有最后一个能承担状态账本？前三个各缺什么？
2. 用 Northstar 那个坏案例说明：如果周一和周三都有 snapshot 绑定，复盘流程会和现在有什么具体不同？
3. snapshot、manifest list、manifest、data file 四层，读一次旧状态时它们分别被用在哪一步？为什么说 time travel 不是复制表？
4. Git 的 commit 类比 Iceberg 的 snapshot，这个类比在哪里失效？
5. atomic metadata swap 解决了什么问题？如果 Iceberg 靠"列目录"确定当前状态，并发写入会出什么事？
6. 为什么本周只做最小 4 表？如果一上来铺十几张 Gold 表，最先返工的会是什么？
7. Bronze 过早做业务解释和 Silver blind append，两个错误各会在什么时候暴露？哪一个更难补救？
8. Catalog、Warehouse、Table Location 三者的区别是什么？如果把 `ICEBERG_S3_ENDPOINT` 写成 `localhost:9000`，什么时候能跑、什么时候会失败？
9. 本仓库四张表全部用 `overwrite` 而不是 `append`，理由是什么？这个选择让哪一类事故不可能发生，又让哪一类信息丢失了？
10. `--plan` 和 `--dry-run` 有什么区别？想在完全不碰 catalog 的情况下核对源行数，该用哪个？
11. baseline、benchmark、tuning 的区别是什么？为什么看到 file_count 很高、avg_file_size 很小时，本周的正确动作是"记录"而不是 compaction？
12. 团队为了省存储跑了一次 expire snapshots，当前表读起来完全正常。三周后 Week11 的评测要复现一个旧结果，会发生什么？这件事该在哪份文档里提前定好？

### 自测题参考答案

先自己答完上面的题，再往下对。

1. 都能查当前，但只有 Iceberg 用 snapshot / history / files 留下可命名的提交。raw bucket 缺强制版本化；Postgres 默认只是当前业务视图；pgvector 是搜索目录，不是数据账本。
2. 有 snapshot 绑定后，复盘变成：周一答「回滚到 5.7.9」对应哪版 `raw_doc_asset` snapshot，周三换硬件对应哪次索引重建消费的文档资产，分数变化发生在数据变更前还是后。没有账本就只能对着 raw / 日志猜。
3. 读旧状态：`snapshot_id` → 该 snapshot 的 manifest list → manifest（files + 统计）→ data files。Time travel 只换读取入口，不复制整张表；代价是 snapshot 保留策略。
4. 类比到「commit ≈ 一版表状态」为止。Iceberg 不记录代码 diff、不是开发分支；manifest 还带 file 统计；checkout 是换 snapshot 入口而不是检出另一份工作区。
5. atomic metadata swap 让「当前表状态」一次切到新 metadata 文件，读者始终读一致 snapshot。若靠列目录当 current，并发写入会半份可见、互相覆盖，可靠读和 optimistic retry 都没有锚点。
6. 第一版能力是 4 表能写入、出 snapshot、能回看、能验收。先铺十几张 Gold，最小闭环没站稳，最先返工的是层职责和 source mapping（字段名、时间语义、去重键），不是缺表。
7. Bronze 过早做业务解释：出 bad case 时分不清源问题还是 transform 问题，replay 入口丢了，更难补。Silver blind append：当时看起来行数变多，查当前事实却取到旧状态、KPI 漂；有稳定 key 还能修，但已经污染过消费。
8. Catalog 记表和 metadata 指针；Warehouse 是 metadata + data files 的存储根；Table Location 是某张表在 warehouse 里的路径。`localhost:9000` 在宿主机也许能跑，容器内必须用服务名 `minio`，否则 endpoint 连不上。
9. Silver 是当前状态表，不能 blind append；代码四张表一律 overwrite，Silver 多版本并存那类事故被挡住。代价是讲义里的 append 时间线变弱：每次 materialize 是全量重写，增量事件史要靠 snapshot 链而不是行追加。
10. `--plan` 不连 catalog，只读源库行数；`--dry-run` 仍会 load catalog、ensure 表，只是不写 snapshot。完全不碰 catalog 核对源行数，用 `--plan`。
11. Baseline 记录当前状态；benchmark 测上限；tuning 改行为。file 又碎又小是小批写入的预期信号，本周只记录。没有 baseline 就 compaction，会把「现在什么样」抹掉，后面无法判断是变好还是变差。
12. 当前表仍可读，但旧 snapshot 过期，Week11 无法 time travel 到当时那版数据，评测和 release 复盘断链。保留策略应写在 baseline / `perf_baseline_template.md`（以及 runbook 的维护边界）里，expire 之前先有记录。

---

## 11. 一句话收口

Week04 是整门课第一次把"状态记忆"从流程文档落到数据实体层：Week03 交付的是 ingest baseline（可采、可重跑、可补数），Week04 把它升级成 Lakehouse state baseline（可快照、可回看、可验收）。往后 Week05 的口径、Week08 的索引一致性、Week11+ 的评测与发布治理，绑定的都不再只是代码和 prompt，而是一个能被命名的 `snapshot_id`。
