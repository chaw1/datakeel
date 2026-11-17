# 动作声明内核

当前只有 `quarantine_files` 与 `unquarantine_files` 使用结构化声明。其余 63 个动作的
schema、scope、可逆性及展示文案仍从旧定义投影，IR 明确记录 `legacy_projection=true`
和 `semantics=opaque`。内部 IR 不新增公共对象、HTTP 路由或 MCP 工具，也不是公开 SDK。

`file_declarations.DECLARATIONS` 是唯一的结构化 owner 激活点。公共 `POLICIES` 保持
旧表顺序并覆盖已激活 owner；声明的 `compatibility=replace` 占原槽位，新探针默认 append。
被声明完全替代的旧参数、policy、inverse 和执行 stanza 已移除。回退使用本片父提交
`8bd850ce9fc2fc43af91b5cd0738adfd7a58d09d` 的源码状态，恢复旧 registry/parameters、
动作事务入口与授权入口；不能仅删除声明而留下不完整 owner。参数表、registry、
Agent/intents、HTTP 和 MCP 都读取同一组声明。额外 ID 仅用于候选外的一次性扩展探针。

声明、授权策略、审批策略、handler set、条件及效果使用 frozen/extra-forbid 模型。
旧双语展示示例与结构化参数示例分开保存。内部资产词汇区分已有 28 个公共对象与
reference-only kinds，不把 action run、release 或 quality rule 擅自变为公共 schema 对象。

生命周期依次处理规范参数、manifest、references、snapshot 与 impact，再由原执行事务
复核 actor、服务端 scopes、digest、有效期、预算和真实签批。动态 hook 只能收紧审批；
执行失败先回滚数据库及声明拥有的外部资源，再记录失败回执与审计。同步回执和生成
deferred 回执通过同一归属构造器。生产动作原有慢任务仍保留自己的 completion 路径；
`persistence/task_completion.py` 与 worker 的事务语义保持原样。

`authorization.AUTHORIZATION` 是独立安全数据，缺项拒绝。生产动作的人工入口限制与
Agent 自动执行资格不再读取展示文案。Agent 只自动执行声明允许且无需审批的可逆非生产
计划；模型工具发现不授予签批权，MCP 继续只读/prepare-only。领域更严格的拒绝继续生效。

前端描述从激活声明生成到 `web/src/api/actionDeclarations.ts`。现有审批标题和专用内容
继续使用既有文案；声明中新动作使用通用审批卡与声明标题，无动作 ID 专用分支。
声明导出包含双语标题，`approvalActions` 与共享 translator 可直接供未修改的 ChainCard 使用。
`npm run generate:api` 同时检查此派生文件，原 `generated.ts` 字节兼容仍独立比较。

独立验收应使用立即父提交的候选外 runner 与冻结历史结果，不能把 IR、自身生成测试或
shadow 比较当成独立 oracle。受影响 SQLite 测试与命名变异锚在本片运行；完整双栈 CI、
全仓覆盖率和 PostgreSQL 验证须如实另列。源码预算与最终验收状态以本片交付记录为准。

声明数据保存在 `datakeel/actions/file_declarations.json`，Python loader 绑定固定的参数和
不可变示例模型，再完整校验 ActionDeclaration（含 extra-forbid 的嵌套授权和 handler）。
`authorization.json` 是独立权限数据，缺项及未知 policy 字段拒绝；
`execution_targets.json` 与 `reference_assets.json` 分别保存目标和封闭引用词汇。
以上 JSON、生成 TS、Python 解析与生成器都须单独列出来源及行数，不能只报告 Python 缩减。
