# 架构决策

> 数据进来、处理、质量、血缘、证据、受控动作的一体化平台：单机一条命令即可启动，需要时通过增加副本扩展可用性与并发能力，保持统一架构。
> 本文记录已经确定的架构与扩展边界。实现规范见 [CODE_STANDARDS.md](CODE_STANDARDS.md)。

## 1. 一条主线

数据进来 → 语义识别（文件是什么）→ 预处理算子链 → 质量评分 → 元数据/标准 → 血缘事件 → 分析报告。
Agent 全程用对话操作，但只能走受控动作；harness 让 Agent 可量、可回放、可跑分。

企业版的东西不要：多租户/统一认证、项目/考培/任务大厅、标注工具矩阵、桌面端、k8s/GitOps、模型服务治理。

## 2. 定了的决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 形态 | 模块化单体，进程只有两个：`api` 和 `worker` | api 无状态加副本=高可用；worker 用 DB 行锁领任务加副本=并发；一期不引 MQ/Temporal，接口留好 |
| 语言 | Python 3.12 为主；可选独立 Rust 扩展只加速 64 位近重复哈希比较；Go 只在将来高并发入口（直传网关、MCP 网关）考虑 | 数据面与控制面共享 Python 生态和 pydantic 模型 |
| 事实源 | PostgreSQL 唯一事实源；开发/demo 用 SQLite | 血缘事件、审计、任务、元数据全在一处；图/搜索/向量都是可重建的派生索引 |
| 对象存储 | S3 协议；本地用 MinIO 或本地目录后端 | 一期不接 LakeFS（BSL、重）；版本用 manifest 快照 |
| 队列 | PostgreSQL `FOR UPDATE SKIP LOCKED` 分片领取 + reaper 兜底 | 用数据库行锁与租约恢复保证领取一致性；量上来再换 NATS/Temporal |
| 缓存 | Redis 可选，只做缓存与限流 | 不做必需依赖 |
| Web 框架 | FastAPI + uvicorn；pydantic v2 做一切 schema | MCP 工具 schema 从 pydantic 直接生成 |
| 前端 | React + TypeScript + Vite | 类型检查、组件生态与交互式血缘图支持 |
| 包管理 | uv + hatchling + ruff + pyright + pytest | 高增长仓库通行配置 |
| License | Apache-2.0 | 企业采购友好 |
| 血缘 | AssetRef + append-only LineageEvent，OpenLineage 兼容导出 | 事件表是唯一事实源，图是投影 |
| 语义 | 单一 YAML 语义合同 → 生成 Python/TS 快照 + golden 语料门禁 | 用统一合同描述格式识别并验证生成结果 |
| 算子 | manifest 驱动 + 类型化槽位 DAG（条件/路由节点） | 保持算子职责明确、可组合、可独立测试 |
| 确认门 | Action 声明影响面与可逆性；门控不可逆与外发操作；审批 token 绑定参数一次性；落库 | 审批绑定冻结计划与执行人，持久化决策和消费状态 |
| Harness | 每次模型调用一条 trace（分段 token/成本/缓存命中）；预算持久化；golden set + 变异测试 | 对调用成本、预算约束和行为回归提供可核验记录 |
| Agent 执行 | LangGraph 同步持久化图；模型适配分别在 `runtime/` 与 `extraction_runtime/` | 中断后从已落盘节点继续，抽取不借用会话图，Datakeel 保持动作授权、审计与预算的事实源 |

## 3. 目录结构

```
datakeel/
  pyproject.toml            # uv 工作区，一个包，多个子模块
  datakeel/
    core/                   # 领域内核：AssetRef、LineageEvent、Action、语义合同解析、manifest
    semantic/               # 语义合同 YAML + 生成快照 + golden 校验
    operators/              # 算子：file/ image/ text/ (audio/ video/ 二期)，每个算子一个文件
    pipeline/               # DAG 引擎：槽位类型、拓扑执行、条件、路由
    quality/                # 五维评分、问题分级、规则基线报告
    lineage/                # 事件写入、幂等、投影、图查询、OpenLineage/Croissant 导出
    governance/             # 标准模板、元数据校验、变更日志、合规评分
    standards/              # 字段标准和码表合同、规则映射建议、落标检查与覆盖率
    storage/                # DB（SQLAlchemy，Postgres/SQLite 双栈）、对象存储（S3/本地）
    worker/                 # 任务领取、分片、reaper、outbox relay
    api/                    # FastAPI 路由；/admin 只读看板
    agent/                  # 会话、上下文、工具发现、确认门、预算计量
    runtime/                # LangGraph 图、chat model 适配和同步 checkpoint saver
    kg/                     # 文本切块、schema、核对、实体身份与候选断言
    extraction_runtime/     # 抽取模型适配；显式配置及注入传输
    kg_eval/                # 独立录制评分与产品候选评分
    harness/                # 二期：trace、成本、golden runner
    mcp/                    # 二期：FastMCP server
    cli.py                  # `datakeel demo | api | worker | migrate`
    web_dist/               # web/ 的构建产物（提交入库，含 .source-hash）
  web/                      # React 前端（Vite 源码）
  contracts/                # semantic/*.yaml、operator manifest、golden 语料
  examples/sample-data/     # 200 图 + 200 文本样例（可再生成，不进 LFS）
  tests/
  docs/
```

## 4. 扩展路径（现在不做，但不堵路）

- api 多副本：无状态，前面放任意反代。
- worker 多副本：直接加进程；队列分 GPU/IO/CPU 三类（manifest 标注）。
- 大流量入口：直传网关、MCP 网关换 Go 实现，协议不变。
- 队列升级：worker 的领取接口抽象成 `TaskSource`，Postgres 版 → NATS/Temporal 版。
- 图/搜索/向量：全是事件表的派生索引，可整体重建。
- 多租户：AssetRef 预留 `namespace` 字段，一期恒为 `default`。

## 5. 实现边界

**数据处理**：语义合同 YAML 与解析逻辑、golden 语料、DAG 引擎与槽位类型、可组合算子、五维质量评分、报告基线、分片领取、reaper 与 outbox。

**交互与治理**：分模块的 Agent 主循环、证据分级、治理与血缘服务层、MCP 工具、前端、确认门、预算与 trace。实现规模与依赖方向统一由代码规范和自动门禁约束。

**公开数据边界**：代码、样例、测试与截图不包含客户名、内网地址、凭证或租户数据；样例在本地生成。

## 6. Agent 执行与恢复

`agent/` 暴露 Datakeel 的冻结类型接口，负责会话、上下文、工具发现、打转检测和模型调用计量；`runtime/` 负责 LangGraph 节点调度和会话模型适配。Fake/Demo provider 保持原生类型，经 runtime 内的 `ScriptedChatModel` 包装，harness 仍直接使用同一脚本接口。框架及 SDK 导入限制在 runtime 与下文的 extraction_runtime 两个适配边界，其它包只消费 Datakeel 类型；import-linter 对整个应用强制这一边界。

每次模型调用仍单独 reserve/settle 并写一条 trace。模型 SDK 自动重试关闭，输入上界和分段 token 仍由 Datakeel 估算；观测用量已包含缓存 token，缓存读写只作为子集记录。无用量响应保留保守预留并标记 `billing_status=unknown`。LangSmith 追踪在 runtime 强制关闭，环境中的第三方追踪开关不能启用它。

可逆动作按原策略自动执行，dry-run 只出计划；仅 `requires_approval=True` 的计划进入 `approval_gate`。该节点只调用 interrupt，不执行动作或写其它业务事实。图使用 `durability="sync"`；状态只存 ID 与基本类型，严格白名单序列化不允许还原任意类。响应 lease token 不进入图 config、state 或 checkpoint metadata。

`runtime/saver.py` 实现框架同步 saver 契约，持久化模型及类型化 bytes 读写由 `storage/checkpoint_store.py` 完成。SQLite 和 PostgreSQL 使用各自的冲突写入语法，并通过现有数据库写锁管理事务。checkpoint 与 pending writes 使用二进制列；transcript、trace、预算、工具调用和动作回执仍存原有表，清理 checkpoint 不会删除这些审计事实。

恢复先确认会话针对该计划仍有挂起 interrupt 或该审批门之后尚未完成的执行 checkpoint，再验证数据库中的真实签批记录。恢复请求本身不授予执行权限：签批必须匹配计划摘要、有效期和计划 actor。已存在且状态不是 `DENIED` 的动作 run 返回原回执，历史拒绝记录不代表已经执行；没有可复用 run 时以计划固有的 `operation_id` 执行。结果经 workspace facts 进入模型上下文，不重复写同一 `tool_call_id` 的工具结果。工具派发也按 `tool_call_id` 幂等，因此动作已提交而 checkpoint 尚未更新的进程故障不会造成第二次动作或工具调用。

新用户消息会作废当前挂起 interrupt 并追加审计，随后按正常会话处理。恢复拥有独立响应 lease 与幂等键，不追加用户消息；协议沿用既有七类 SSE 事件。恢复授权和失败语义详见 [ACTIONS.md](ACTIONS.md)。

会话创建、查询、消息、恢复与恢复审计统一使用 `/api/agent/conversations` 前缀；恢复入口为 `POST /api/agent/conversations/{id}/resume`，审计入口为 `GET /api/agent/conversations/{id}/audit`。

消息与恢复共享进程释放型会话锁：PostgreSQL 使用按 schema 与会话划分的 session advisory lock，SQLite 使用按数据库与会话划分的文件锁。同一会话只允许一个响应写入者；进程退出或被杀后锁由系统释放，后继写入者取得锁后才能回收遗留 response lease，避免仅凭超时抢占仍在执行的请求。签批校验成功、恢复拒绝和暂停作废均写入独立审计表，并可经恢复审计接口查询。


## 7. 确定性工作流 / Deterministic workflows

`workflows/` is a framework-free domain package: frozen YAML schemas, graph validation, input binding, JSON reference resolution and existing tool/task execution. `runtime/workflow_graph.py` compiles each checked step into LangGraph nodes and uses the same strict synchronous saver. `routing/` may read workflow declarations but cannot start a run. Both domain packages have their own 1500-line limit and 90% coverage gate.

`workflows/` 负责定义和执行的领域规则，`runtime/` 负责图调度，`routing/` 只读取工作流词汇并给出建议。工具步调用现有读函数或准备可逆动作后自动执行；任务等待在节点内轮询，时钟与 sleep 可注入，不使用 interrupt。分支只能使用 ref/op/value 白名单，output 只使用变量与声明的纯函数。输入和定义在启动时冻结，恢复不读取后来改动的 YAML。

An irreversible step has separate preparation, `approval_gate`, and execution nodes. The gate only interrupts. Preparation uses a stable run-scoped tool call ID; execution reuses `execute_approved` and existing receipts. The pure approval policy checks original digest, signed actor, expiry, consumed state and run ownership. Workflow run, step, audit and resume records live in four independent tables; plans use the run ID as `session_id` and `datakeel-workflow` as `agent_id`. A signed action still requires an explicit workflow resume request.

运行采用同步 SSE。每个启动幂等键绑定工作流与输入；每个恢复键绑定运行与计划。消息锁机制以工作流运行 ID 为命名空间，在进程退出时自动释放；并发恢复只能有一个写入者。普通断线或重启后的运行标为 `INTERRUPTED`，没有通用中途续跑；持久签批暂停及其尚未完成的执行节点允许从真实签批记录恢复。事件在产生时冻结完整运行快照，避免消费时读到更后一步的状态。审计不依赖 checkpoint 的保留。

See [WORKFLOWS.md](WORKFLOWS.md) for declarations, endpoints, events and examples. 详细引用语法、CLI、API 与错误示例见工作流文档。

## 8. 意图与模型路由 / Intent and model routing

Intent scoring first filters each workflow's request scope for negation, inactive topics, read-only requests and step restrictions, then uses vocabulary, exclusions, thresholds and score margins declared in workflow YAML. A clear winner produces a suggestion; ambiguous scores and positive partial matches use an independent classifier limited to the top three candidates. Incomplete keyword conjunctions retain fractional scores, and broader declarative entity/action/scope groups can also establish partial eligibility without promoting it to a direct route. A classifier choice must pass a literal critical entity-or-verb check; abstention or failed verification returns to the free Agent. Decisions retain scores, classifier usage and choice, verification outcome and confirmation policy. A classified workflow with writes or approval steps keeps conversational reads available but blocks writes and delegation until the user explicitly starts the workflow. The offline classifier does not consume the scripted Agent queue. Real classification uses the configured conversation model, has its own reserve/settle trace marked `intent_classifier`, and does not increment Agent turns. No new tools, context segments or ChatMessage fields are introduced.

会话路由只建议，执行仍由用户显式启动。命中建议以 `route` 事件在 `done` 前发出；自由路由决策保存在 `done.route`，可经会话路由接口查询。恢复请求不重新路由。预填只来自会话的 dataset_id，不从用户文本推断额外执行参数。

Before every conversational model call, loaded controlled actions or a plan in the current response select the high-risk tier; a prior tool result selects multi-step; otherwise the tier is simple. Explicit models are pinned; only `model=auto` selects from provider configuration. Fake mode keeps the configured model. All referenced models must have a declared price and belong to the same provider. Startup and CLI validation reject missing models, unknown tiers, cyclic chains and more than two backups.

只有超时、429 与 5xx 可触发备用模型；400、401 不切换。每次尝试单独预留和结算预算并写 trace，后一条记录切换原因。SDK 自动重试仍关闭，HTTP 客户端仍忽略代理环境变量，追踪仍强制关闭。`done.model_routes` 暴露本次响应的档位、pinned 状态、模型及备用尝试，分类与备用尝试不额外消耗 max_turns。

## 9. Canary and untrusted data / Canary 与不可信数据

Each conversation has a private `dkc_` sentinel with 24 random hexadecimal characters in a separate nullable storage column. Legacy rows acquire a sentinel once after additive migration. It is never part of public conversation models, transcript, graph state, runnable config or checkpoint metadata. The model sees a short volatile `canary` segment after the stable instructions and core tool schemas. Scripted request objects remain on ephemeral model instances rather than framework metadata.

模型节点在计费完成后、追加 assistant 消息前检测泄漏：忽略大小写与空白，完整值或随机部分连续 16 位均触发 `stopped` / `canary_leak`。该回复不产生 text 或工具执行，审计只记 `CANARY_LEAK` 和原因，不存秘密。计费记录仍保留真实用量。

Tool history is encoded as `["data-only", tool_name, payload]` only when assembling a prompt; stored tool results retain their original JSON. The envelope's fixed overhead is 17 UTF-8 bytes, plus source-tool name and any JSON encoding required for non-JSON text. The canary segment consumes 66 units under the conservative byte estimator, including its 16-unit segment allowance. Empty context segments are omitted.

Tool discovery keeps complete schemas in the transcript for recovery and audit. At the prompt boundary, a historical discovery result omits only the duplicate parameters of a definition identical to one in the current request's native tools. Different, unknown and legacy definitions remain intact. Accounting uses the resulting prompt with the same UTF-8 byte bound and unchanged budget limits.

威胁模型：信封区分数据和指令，canary 检测部分提示泄漏；二者不保证模型完全免受提示注入。恶意 caption 或元数据仍可能诱导可逆动作自动执行，这些动作有审计和回滚。不可逆动作始终由受控动作签批边界保护，没有人类签批不能执行。各项测试只用独立生成样例和离线模型。

## 10. Delegation / 委派

`delegation/` owns frozen YAML definitions, scope/depth/batch policy, tool-call replay and call-tree projections. `runtime/delegation_graph.py` only wires serial independent graph instances. Children have separate conversation IDs, histories, response leases, canaries and checkpoint threads; parent/root IDs and parent tool-call IDs retain ancestry. Storage migrations add nullable/defaulted columns to existing databases. Root session lists hide children.

`delegation/` 管定义、权限、深度与数量限制、幂等结果和调用树；runtime 只接图。子会话具备独立历史和 checkpoint，预算预留与结算统一归根会话；trace 保留实际子会话及父工具调用 ID。子调用不增加主轮数；已完成委派重放不增 trace 或预算。越权调用留审计，嵌套权限只能收窄；不可逆动作在定义加载时拒绝，主会话继续遵循签批边界。

SSE reuses existing event types with defaulted path/name/usage fields. Child results enter the parent's prompt in the same data-only envelope as every other tool. Child and ancestor canaries are checked before persistence, and returned conclusions are checked again. The API exposes the measured tree without exporting private canaries or mutable database rows.

## 11. Cross-conversation memory / 跨会话记忆

`memory/` owns explicit writes, shared PII redaction, deterministic BM25 retrieval, lazy strength decay and consolidation. `storage/memory_store.py` owns transactional rows and returns frozen core models. Memory and delegation each have a 1500-line limit and a ≥90% coverage gate; all same-layer imports are explicit in `.importlinter`. No runtime dependency or vector service is added.

记忆只由用户或显式工具写入，作用域为全局或指定数据集。检索依据当前用户消息，至少两个不同词元重合，按 BM25 × 衰减强度取前三条，含段开销不超过 1200 字节估算词元。无匹配不增加上下文段。每次模型调用及备用尝试前重查，已删条目不进入后续请求；具体常量与同分规则见 [Agent reference](AGENT.md)。

每次用户提问中，同一条记忆仅在首次实际 provider 尝试后增强 0.5；失败尝试也计入。根会话、多步工具调用、备用模型和全部委派子会话共用去重范围。`MemoryUseRow` 按根会话 ID、用户消息序号与记忆 ID 持久化取用标记，并在记忆写事务中原子去重，因此进程重启或 checkpoint 恢复不会重复增强。每次实际取用仍更新 `last_used_at` 和本次响应的取用 ID，仅首次增强更新 `reinforced_at`。新用户消息开启新的增强范围；审批恢复不追加用户消息，沿用原范围。模型尝试前被预算拒绝不记录取用。

Consolidation merges only within one scope, keeps the strongest entry, unions provenance, then archives excess weak entries. Hard deletion recursively removes archived source entries and writes an ID-only audit. Checkpoints and response events store only used memory IDs; the UI resolves current entries so deleted content is unavailable there. Original user speech and explicit tool parameters retain normal transcript semantics; deletion does not rewrite prior speech. Retrieval never uses archived or deleted entries, and no automatic conversation summarization writes memory.

## 12. Text knowledge graphs / 文本知识图谱

`kg/` owns frozen schema/profile loading, NFC source coordinates, bounded chunking, endpoint resolution, source verification, deterministic entity identity and candidate assembly. It depends on core models, not chat frameworks or the conversation runtime. `extraction_runtime/` owns the narrow model boundary, with injected synchronous transports and lazy credential reads. Application code constructs adapters and injects the typed `ExtractorAdapter`; replay and fake paths do not construct model SDK clients. `kg_eval/` owns independent gold alignment and recording scores, then calls the actual product assembly for a separate candidate view. Size limits are 1500 lines each for `kg` and `kg_eval`, and 600 for `extraction_runtime`; all three have independent coverage gates.

实体注册为 `kg_entity`，带数据集和版本作用域。提及使用 `kg.mentions`，关系使用 schema 中允许的 `kg.<relation>`，均为既有证据断言，复用来源锚点、人工决定和重建流程。实体 asset_id 由数据集、类型、归一名称确定，跨数据集版本稳定，`AssetRef.version` 单独携带版本；断言身份同时覆盖来源位置和抽取配置。每个不同出现位置保留独立提及断言，跨块重复副本去重；重复三元组合并多篇原文的位置，模型与配置变化不能冒充旧抽取。同一版本三元组或实体提及继承最新人工结论，追加审计说明来源；证据并集不使已审核结果回到候选。`status` 表达人审状态，`verification` 与 detail 表达原文核对，二者独立。

An `evidence.kg` COMPLETE lineage event records source assets, the schema and extractor attribution, graph entities and a knowledge bundle. Assertions and append-only decisions remain the evidence fact source. The entity table and bounded graph are projections; they do not add inferred relations. Accepted explicit same-as pairs merge only display nodes. Rejected decisions remain visible and preserve the underlying entity identities. Rebuilding evidence re-registers dynamic schemas from stored events before replaying typed assertions.

`run_kg_extraction` 复用受控动作及现有任务队列。准备冻结文件修订号、块位置与哈希、录制哈希、schema、配置和计费估算，不在计划或工具消息中复制全文；授权后重新读取并核对全部指纹，校验通过的原文快照内部保留供来源展示；外发由服务端按字面主机分类，不查 DNS。worker 在真实授权之后才创建抽取器，每块请求先预留预算再结算，trace 使用 `call_type=extraction`，不会增加会话轮数。未知价格保留保守费用占用与显式 unknown；有完整用量时 token 预算按实际扣，无用量才保留最坏 token 预留。租约围栏同时保护成功缓存及事实发布；截断和解析失败不进入缓存。重跑复用成功块，完整替换文档才使旧断言失效，部分失败仍保留先前成功事实与失败说明。

`query_kg` and `explain_relation` share the ontology registry with MCP. Agent discovers these reads and `run_kg_extraction` through `tool_search`, preserving the original resident-tool prompt size. HTTP exposes bounded queries, exact source explanations, run reports and saved evaluation comparisons. Evaluation history uses `kg_eval_runs` so the original conversation/evidence/ask report schemas remain unchanged. Four additional goldens and three mutations exercise the new boundaries; the original 32 YAML cases and 21 mutation anchors remain unchanged. See [KG.md](KG.md) for the bilingual configuration and threat model.


## 13. Image knowledge graphs / 图片知识图谱

`transcription/` owns typed profile/recording loaders, optional CPU OCR, injected HTTP visual transports, corrected image decoding, quality policy and OCR alignment. It is a framework-free domain package with a 1500-line ceiling and at least 90% coverage, including its transactional `storage/transcription_*.py` adapters. Core runtime requirements do not change.

图片复用 `run_kg_extraction`：准备只冻结原始内容哈希、校正尺寸、两阶段配置与录制哈希，任何非回环端点都使整个动作需要签批。授权后的 worker 先转写再走既有文本抽取；两阶段共享持久预算，视觉调用独立标记 `transcription`。成功转写进入新表，失败保持逐图报告与部分完成。

Transcripts are deterministic `image_transcript` assets with content-hash versions. Text spans reference the transcript; image regions reference original image content in EXIF-corrected pixel coordinates. Image responses and external requests strip metadata. OCR matching and validated v2 visual transcription lines supply rectangles; malformed visual coordinates retain text without inventing positions. Missing locations and explicitly marked handwritten person types add structured review issues without promoting candidates to accepted facts.

来源展示读取冻结运行快照；人审将派生资产解析回同数据集版本的原始 manifest，避免同内容图片跨版本错指。替换来源时同步作废旧转写稿断言并保留审计与人工结论。证据重建复用持久化的 knowledge bundle，不构造转写或抽取客户端。图片评测分别报告录制评分与实际写入后读回的候选断言评分；外部用例与内置录制采用同一质量和对齐规则。

Auto transcription is local OCR followed by a versioned pure routing policy. The profile owns every threshold; the signed plan and auto cache identity bind the complete configuration. Preparation invokes no transcription or routing backend and lists every potentially outbound image at worst-case cost. The worker validates each selected file ID and image hash against that envelope before a visual request, with per-image failures and independent OCR reference text excluded from extraction. Explicit batch/per-image modes override the profile default.

auto 先本地 OCR，再按纯函数规则决定是否转交视觉模型；版本和全部阈值冻结在配置、签批和缓存中。逐图签批清单按最坏情况准备，执行前再次核对身份与哈希。实际路线、原因、外发数及两阶段费用单独报告，失败保持逐图隔离。

## 14. Dataset releases and recipient verification / 数据集发布与收货对账

Version comparison expands legacy JSON manifests inside the database and merges two streams ordered by stable file identity. Each request retains only its bounded result page and constant-size summaries; metadata classification preserves JSON types. New releases use the existing irreversible controlled-action and approval protocol. Private object keys stay in storage; frozen public file facts and dataset metadata form separate release rows. Database constraints seal entries when their release header is inserted and reject later source-version, header or entry mutations. Content-addressed local objects and conditional S3 writes reject replacement with different bytes.

`delivery/` is a framework-free domain package for canonical manifests, safe tar reading and six independent recipient checks. The exported JSON Schema lives in `contracts/` and is also included in the wheel. `storage/delivery_service.py` materializes actual backend objects, validates exports and archives platform reconciliation receipts. The CLI dispatches recipient verification before settings, routing or database initialization. `MANIFEST.json` records expected facts; `RECORDS.json` supplies receipt-side metadata and annotation statistics, without trying to infer annotation semantics from arbitrary payloads. The manifest checksum provides integrity; it is not a sender signature.

版本清单和已有生成版本行为保持兼容。发布冻结文件事实、来源、元数据及统计；后续变更必须生成其他版本。离线交付包只携带相对路径、公开元数据和版本血缘，不携带对象键或凭证。平台对账和收货命令调用同一套六类规则，平台结果独立存档。

Resumable uploads stage bounded, atomically committed chunks under the configured local home. Shared process-released locks serialize writers and cap concurrent streams; whole-file and freshly read backend hashes are checked before a dataset transaction commits. The same declaration key resumes one upload, identical chunks merge, and conflicting retries are rejected. Multiple hosts require shared durable staging or sticky routing. Completed staging is retained; automatic cleanup is outside this implementation. See [the release guide](RELEASES.md) and [中文说明](RELEASES.zh.md).
