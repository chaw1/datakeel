# 身份与 HTTP 访问

动作授权以服务端保存的角色绑定为准。全平台角色与动作实际项目的角色求并集，调用方声明的 scopes 只能收窄。任务、任务包会解析到数据库中的项目；跨项目的批量任务动作被拒绝。

实例没有登记用户时，保留原来的本机单人体验。首位用户未显式指定 `role_ids` 时自动持有 `administrator`。登记后，未知或已停用的操作人可以读，但不能修改业务对象。删除用户采用归档，删除最后一个用户不会恢复匿名写权限。

五个可修改模板为管理员 `administrator`、项目经理 `project_manager`、标注员 `annotator`、质检员 `reviewer`、验收方 `acceptance`。验收方没有写范围。自定义角色的范围只能来自已注册动作。角色计划列出全部允许和禁止的动作，并按共享范围准确计算。准备或签批不会启用角色，执行后才生效。更新角色不能改变其项目作用范围；换项目时另建角色。

角色可由另一位管理员签批，审计记录真实签批人；签批和执行时都会重新检查签批人当前拥有的范围。执行仍由计划发起人请求。绑定已有角色同样不能超出操作人的授权范围，避免通过用户管理间接提权。其他动作保持原有身份约束，其中资产访问申请仍禁止申请人自批。

## 旧 HTTP 写入口矩阵

HTTP 依赖按已经匹配的路由模板检查权限，不改变请求和响应 schema。操作人取 `X-Datakeel-Actor`，权限取下表中现有动作的策略。旧数据集入口属于全平台范围；项目角色通过生产动作入口生效，实际项目由服务端解析。GET、HEAD、OPTIONS 保持读取行为。

| 方法及入口 | 复用动作 | 有效范围 |
| --- | --- | --- |
| POST `/api/datasets` | `save_metadata` | `datasets:write` |
| PUT 数据集 `/metadata`、`/template` | `save_metadata` | `datasets:write` |
| PUT 数据集 `/quality/config` | `create_quality_rule` | `quality:write` |
| POST `/api/tasks` | `run_pipeline` | `pipelines:run` |
| POST `/api/uploads`、PUT 分块、POST 完成上传 | `save_metadata` | `datasets:write` |
| POST `/api/lineage/events`、`/api/openlineage/events` | `import_catalog` | `catalog:write` |
| POST `/api/catalog/import/dbt`、`/airflow` | `import_catalog` | `catalog:write` |
| POST `/api/custom-operators` | `submit_custom_operator` | `operators:submit` |
| POST `/api/custom-operators/{code_hash}/runs` | `run_pipeline` | `pipelines:run` |
| POST 数据集 annotation-quality `/batches` | `save_metadata` | `datasets:write` |
| POST annotation-quality `/samples`、`/acceptance/prepare` | `annotation_acceptance` | `annotations:accept` |
| POST `/api/evidence/assertions/decide`、`/api/kg/links/rerun` | `decide_assertions` | `evidence:write` |
| POST 数据集 `/datasheets` | `generate_datasheet` | `datasets:write` |
| POST `/api/datasheets/{document_id}/publish` | `publish_datasheet` | `datasets:export` |
| POST `/api/agent/memories`、DELETE 某条 memory | `manage_users` | `users:manage` |

血缘观察与目录导入一起归入目录事实写入；数据集导入、二进制上传、旧标注批次导入复用数据集写范围；显式 memory 管理复用用户管理范围。没有新增脱离动作注册表的权限词汇。

POST 只读计算继续可用，包括本体查询、生产只读函数、证据查询、图查询和提问。提问会话、访问申请、发布物下载及对账，以及它们的审计状态仍可使用；提交申请本身不会授予访问权。Agent 和确定性工作流可启动读取，其内部业务动作仍按实际操作人的服务端范围检查。通用计划准备、签批和执行入口自行检查动作与项目范围。登记用户后，未分类的新写入口一律拒绝；路由清单回归测试保证当前每个写入口都显式分类。

## 运行时身份与兼容

Agent 会话与确定性工作流保存服务端拥有的「会话 → 操作人」绑定。新 HTTP 会话绑定真实请求操作人；发送、恢复以及工作流启动重放拒绝其他操作人借用。委派子会话继承父会话身份。工具调用使用该绑定，不再隐式借用 `local`。历史无绑定会话仍属于 `local`。

旧公开会话响应中的 `actor: local` 保留为兼容字段；执行和审计以服务端绑定为准。新增生产写工具只准备计划，签批与执行由人在 Web 或 CLI 完成。成功请求的重放会重新检查当前权限，返回原回执，不重复修改。

| 方案 | 结论 | 原因与来源 |
| --- | --- | --- |
| 每个旧请求增加 actor 字段 | 不采用 | 会改变现有契约；已有请求头可承载身份。见[动作入口](../datakeel/api/routes/actions.py)。 |
| 仅按 HTTP 方法拦截 | 不采用 | 只读查询也使用 POST。见[证据查询入口](../datakeel/api/routes/evidence.py)。 |
| 显式匹配路由矩阵，并复用受控动作权限 | 采用 | 保留旧 schema、只读计算和注册范围，并检测未分类写入口。见[策略](../datakeel/api/identity_access.py)及[回归测试](../tests/api/test_identity_access.py)。 |
| 改旧会话响应的 actor schema | 不采用 | 客户端继续使用原响应结构。 |
| 服务端运行时身份绑定 | 采用 | 保留原响应，同时让工具、委派和恢复使用真实操作人。见[身份绑定](../datakeel/storage/identity_sessions.py)。 |

旧的非生产 CLI 管理命令仍使用本机进程身份，属于既有本地受信任库边界。生产 CLI 支持显式操作人，并经过同一套受控动作授权。直接调用 Python 存储函数或 SQL 需要持有本机数据库访问权；HTTP 角色检查约束应用入口，不替代数据库认证。

历史上下文投影、已缓存回复重放、带来源的 memory 检索，均按运行时会话归属检查当前资产授权；HTTP memory 读取使用请求操作人。Agent 和工作流历史列表仅包含该操作人的会话，直接历史、调用树、审计与路由记录拒绝其他人借用。多人共用实例时，原有资产授权规则继续生效。
