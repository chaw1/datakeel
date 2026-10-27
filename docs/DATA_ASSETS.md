# 数据资产上架与使用

[English](DATA_ASSETS.en.md)

数据资产引用已有数据集（可固定版本）、目录表或语义指标。卡片保存中英文名称、业务定义、负责人、四种分级、标签、同义词、场景、使用说明及手动脱敏样例。不要在公开卡片填写原始私密数据。草稿、上架和下架均保留完整修订历史；修改已创建资产不能换绑底层对象。

在「资产市场」搜索名称、同义词、标签或负责人，按分级或标签筛选，进入详情查看质量趋势、上下游、来源更新时间、相关指标、使用次数和人数。多来源资产的质量分取有测量依据的来源最低分；趋势在所有有质量证据的来源均有观测后，按来源版本时间更新。未知来源不编造质量分。质量没有来源证据时显示暂无数据；版本发布和标准覆盖率扩展位为空时隐藏。下架使卡片退出默认市场，不解除已建立的底层访问策略。草稿尚未建立读取策略。

创建、编辑、上架、下架通过既有受控动作准备计划，审阅后确认执行；可逆操作沿用自动批准规则；但把已上架或已下架的「需申请」「受限」资产改为「公开」「内部」会向所有人开放读取，这类修改必须人工审批，Agent 不会自动执行。申请人填写用途、查询/导出/下载范围和到期时间。批准或拒绝申请、撤销授权必须另行准备动作，经人工审批后显式执行。操作人、资产、范围、起止时间和撤销状态共同决定授权是否有效；到期不需要后台清理任务。多个资产引用同一受保护资源时须分别获得授权。

身份沿用本地操作人标识，这不是认证系统。Web 问数可以选择操作人，默认 `local-user`；Agent 与 MCP 固定为既有 `local` 操作人，忽略工具参数中试图改写身份的 `actor`。申请应使用读取时的同一标识。HTTP 下载、导出、保存答案重放和证据阅读可用 `X-Datakeel-Actor` 传递该标识，默认 `local-user`。不要将服务直接作为面向不可信用户的身份认证边界。

公开和内部资产允许读取并记录使用；需申请和受限资产要求当前有效且包含所需范围的授权。问数在执行 SQL 前检查指标及实际表列依赖；工具、HTTP 导出、受控导出和文件下载复用同一服务守卫。按已登记的血缘、manifest、目录父子关系解析派生资源，防止绕过底层数据集策略。未固定版本的读取保守匹配该资源全部受控版本；精确固定版本遵守版本策略。仅登记指标不会自动限制不读取该指标的其它独立资源。

证据候选、图谱、关系解释、冻结原文、文件/版本清单、对象集求值、任务产物以及数据集质量评估和报告中的元数据属于查询范围，使用 `ask` 审计入口；原始校正图片属于下载范围，使用 `download` 入口。含来源数据的动作预览、保存计划及回执重读也检查当前权限，导出计划使用导出范围，其它计划使用查询范围；集合视图仅返回当前可读的计划，不改写原历史。图谱运行列表只返回当前可读来源的运行报告（报告样例会引用抽取原文）；血缘图中的文件、图谱实体和转写节点会引用来源内容，含无权读取的受保护来源时拒绝并提示申请，表、字段、指标等目录元数据节点与资产卡片一样保持可见。控制动作读取沿用原 `local` 操作人默认值，也可通过上述 HTTP 标头指定读取人。Agent/MCP 的内部来源读取只检查权限，最外层工具每次成功读取按匹配资产各记一条审计。

保存答案、工具缓存、委派缓存和同一请求编号的 Agent 消息重放均重新检查当前授权。授权撤销后，新模型请求及会话/记忆的公开读取不再返回失权的旧工具结果、派生回复和事件；用户话语仍保留。记忆取用保存无原文的资源归属快照，避免后续硬删除记忆条目后丢失旧派生回复的授权依据。原始存储历史和只增审计不被改写；用户主动写入且没有来源归属的全局记忆无法反推出数据资产归属。

使用审计保存操作人、资产、实际入口、范围、UTC 时间和授权编号；公开/内部无授权读取的编号为空。可以在详情页或全局审计按资产和人查询。SQLite 和 PostgreSQL 数据库触发器拒绝修改或删除使用审计、资产修订历史和申请/授权决定历史。市场热度只来自客观使用和血缘指标，不评价业务价值。

排序合同为 [`contracts/assets/ranking.yaml`](../contracts/assets/ranking.yaml)。默认热度分数为使用次数 + 2 × 使用人数 + 下游依赖数，降序；同分依次按来源更新时间降序、资产编号升序。其它排序为新鲜度年龄升序、质量分降序、下游数降序、名称不区分大小写升序，未知值排后，同样稳定打破平局。本版本使用固定的默认合同，不提供自定义权重配置；合同异常直接报错，不静默退回。质量、趋势和新鲜度来自底层事实，卡片文字修改不会重置新鲜度。

API 可在 `/api/docs` 查看。市场与详情是 `/api/data-assets`、`/api/data-assets/{id}`，申请是 `POST /api/data-assets/{id}/applications`，申请/授权/审计分别为 `/applications`、`/grants`、`/audit` 子路径。六个动作名为 `create_data_asset`、`update_data_asset`、`publish_data_asset`、`withdraw_data_asset`、`decide_asset_application`、`revoke_asset_grant`，沿用 `/api/actions/{action}/prepare`、`/api/approvals/{plan_id}`、`/api/actions/{plan_id}/execute`。

CLI 使用相同模型和服务，例如：

```sh
uv run datakeel data-assets list --search 出货额
uv run datakeel data-assets show ASSET_ID
uv run datakeel data-assets prepare create_data_asset definition.json
uv run datakeel data-assets execute PLAN_ID --digest PLAN_DIGEST
uv run datakeel data-assets apply application.json --applicant local
uv run datakeel data-assets prepare decide_asset_application decision.json
uv run datakeel data-assets approve PLAN_ID --digest PLAN_DIGEST
uv run datakeel data-assets execute PLAN_ID --digest PLAN_DIGEST
uv run datakeel data-assets audit --actor local
```

`definition.json` 包含 `{"definition":{"target":{"asset_type":"metric","asset_id":"shipment_amount"},"name":"出货额","owner":"数据负责人","classification":"request"}}`。`application.json` 包含 `asset_id`、`purpose`、`scopes:["query"]`、未来的带时区 `expires_at`；`decision.json` 包含 `application_id`、`approve:true`，可附审批理由。拒绝和撤销同样保留决定历史。完整示例见[演示导览](DEMO.md)。
