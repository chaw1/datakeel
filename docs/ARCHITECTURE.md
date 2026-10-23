# 架构决策

> 数据进来、处理、质量、血缘、证据、受控动作的一体化平台：单机一条命令即可启动，需要时通过增加副本扩展可用性与并发能力，保持统一架构。
> 本文记录已经确定的架构与扩展边界。实现规范见 [CODE_STANDARDS.md](CODE_STANDARDS.md)。

## 1. 一条主线

数据进来 → 语义识别（文件是什么）→ 预处理算子链 → 质量评分 → 元数据/标准 → 血缘事件 → 分析报告。
Agent 全程用对话操作，但只能走受控动作；harness 让 Agent 可量、可回放、可跑分。

企业版的东西不要：多租户/统一认证、项目/考培/任务大厅、标注工具矩阵、桌面端、离线交付、k8s/GitOps、模型服务治理。

## 2. 定了的决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 形态 | 模块化单体，进程只有两个：`api` 和 `worker` | api 无状态加副本=高可用；worker 用 DB 行锁领任务加副本=并发；一期不引 MQ/Temporal，接口留好 |
| 语言 | Python 3.12 为主；Go 只在将来高并发入口（直传网关、MCP 网关）考虑 | 数据面与控制面共享 Python 生态和 pydantic 模型 |
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
| Agent 执行 | LangGraph 同步持久化图；LangChain chat model 适配；框架依赖仅在 `runtime/` | 中断后从已落盘节点继续，Datakeel 保持动作授权、审计与预算的事实源 |

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
    storage/                # DB（SQLAlchemy，Postgres/SQLite 双栈）、对象存储（S3/本地）
    worker/                 # 任务领取、分片、reaper、outbox relay
    api/                    # FastAPI 路由；/admin 只读看板
    agent/                  # 会话、上下文、工具发现、确认门、预算计量
    runtime/                # LangGraph 图、chat model 适配和同步 checkpoint saver
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

`agent/` 暴露 Datakeel 的冻结类型接口，负责会话、上下文、工具发现、打转检测和模型调用计量；`runtime/` 负责 LangGraph 节点调度和 LangChain chat model 适配。Fake/Demo provider 保持原生类型，经 runtime 内的 `ScriptedChatModel` 包装，harness 仍直接使用同一脚本接口。框架包及 SDK 的直接导入只允许出现在 runtime，import-linter 对整个应用强制这一边界。

每次模型调用仍单独 reserve/settle 并写一条 trace。模型 SDK 自动重试关闭，输入上界和分段 token 仍由 Datakeel 估算；观测用量已包含缓存 token，缓存读写只作为子集记录。无用量响应保留保守预留并标记 `billing_status=unknown`。LangSmith 追踪在 runtime 强制关闭，环境中的第三方追踪开关不能启用它。

可逆动作按原策略自动执行，dry-run 只出计划；仅 `requires_approval=True` 的计划进入 `approval_gate`。该节点只调用 interrupt，不执行动作或写其它业务事实。图使用 `durability="sync"`；状态只存 ID 与基本类型，严格白名单序列化不允许还原任意类。响应 lease token 不进入图 config、state 或 checkpoint metadata。

`runtime/saver.py` 实现框架同步 saver 契约，持久化模型及类型化 bytes 读写由 `storage/checkpoint_store.py` 完成。SQLite 和 PostgreSQL 使用各自的冲突写入语法，并通过现有数据库写锁管理事务。checkpoint 与 pending writes 使用二进制列；transcript、trace、预算、工具调用和动作回执仍存原有表，清理 checkpoint 不会删除这些审计事实。

恢复先确认会话针对该计划仍有挂起 interrupt 或该审批门之后尚未完成的执行 checkpoint，再验证数据库中的真实签批记录。恢复请求本身不授予执行权限：签批必须匹配计划摘要、有效期和计划 actor。已存在且状态不是 `DENIED` 的动作 run 返回原回执，历史拒绝记录不代表已经执行；没有可复用 run 时以计划固有的 `operation_id` 执行。结果经 workspace facts 进入模型上下文，不重复写同一 `tool_call_id` 的工具结果。工具派发也按 `tool_call_id` 幂等，因此动作已提交而 checkpoint 尚未更新的进程故障不会造成第二次动作或工具调用。

新用户消息会作废当前挂起 interrupt 并追加审计，随后按正常会话处理。恢复拥有独立响应 lease 与幂等键，不追加用户消息；协议沿用既有七类 SSE 事件。恢复授权和失败语义详见 [ACTIONS.md](ACTIONS.md)。

消息与恢复共享进程释放型会话锁：PostgreSQL 使用按 schema 与会话划分的 session advisory lock，SQLite 使用按数据库与会话划分的文件锁。同一会话只允许一个响应写入者；进程退出或被杀后锁由系统释放，后继写入者取得锁后才能回收遗留 response lease，避免仅凭超时抢占仍在执行的请求。签批校验成功、恢复拒绝和暂停作废均写入独立审计表，并可经恢复审计接口查询。
