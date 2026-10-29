# 数据生产流程

[English](PRODUCTION.md)

项目绑定输入数据集版本、已发布标签集版本和可选标注模板，输出新的数据集版本及标准标注批次。定稿会把原生标注和准确的标注/标签统计写入新 manifest，发布对账和说明书沿用现有版本合同。

## 对象与关系

`GET /api/ontology` 注册十四个新增对象：用户 `user`、团队 `team`、角色 `role`、技能 `skill`、标签集 `label_set`、模板 `template`、项目 `project`、任务包 `task_package`、生产任务 `production_task`、指派 `assignment`、标注修订 `annotation_revision`、审核 `review`、模型 `model`、预标注运行 `prelabel_run`。原有 worker 的 `task` 身份保持独立。全部对象使用 `AssetRef`；标签集身份带版本。

项目包含任务包，包包含任务；任务关联指派、修订和审核。用户团队、角色和技能、指派人、审核目标、上一修订以及项目输入配置使用统一链接合同。通过 `GET /api/production/objects/{kind}` 读取事实投影，可按 `object_id`、`project_id`、`task_id`、`version`、`limit` 筛选。团队和技能提供增删改，技能派单留到下一阶段。

## 状态机与档位

| 六个状态 | 含义 |
| --- | --- |
| `pending` | 待标，包括返工任务 |
| `in_progress` | 已指派或正在标注 |
| `submitted` | 一条确定修订已提交待审 |
| `in_review` | 审核员领取了待审任务 |
| `approved` | 一条确定修订已通过，可参与定稿 |
| `finalized` | 定稿修订已进入新数据集版本 |

返工回到 `pending`，轮次加一，保留原标注员。不做自动升级；进度函数列出返工至少三轮的任务。任务包和项目由同事务维护的六个状态计数汇总，不另存可变状态，不在每次查询时全表计数。

| 档位 | 行为 |
| --- | --- |
| 个人 `personal`，默认 | 保存或导入预测后提交即通过。没有指派和审核记录，动作审计记 `SYSTEM_APPROVAL`。 |
| 小组 `group` | 点名派单或自行抢单，提交、审核、带问题返工、原人再提交、通过。允许自标自审。 |
| 团队 `team` | 可以升档且保留全部历史。本期不启用心跳、技能匹配、标审分离和任务包抽检验收。 |

`upgrade_project` 只允许向前升档。拒绝降档，因为已经发生的审核历史不能解释成早期流程。项目加入第二位参与者时，相关回执只返回一次 `suggest_review: true`，不自动升档。指派记录有租约到期时间，本期不自动续租或回收。

个人档升档时，已有人工保存、仍可编辑的任务会补上原作者的标注指派。原作者可按现有持有人校验继续保存、提交送审或释放，不需要重开任务，轮次不增加；任务状态和修订历史保持不变。无作者任务、纯模型预测和已通过任务不新增指派。保留历史所有权不会授予角色范围，仍需通过当前账号权限校验；释放后必须重新领取或被指派才能继续。

## 受控动作

每个新增动作都有必填的客户端 `request_id`。所有写操作走原有准备、签批、执行协议，并落审计、血缘和回执。高频动作不要求签批，准备后由人明确执行。

| 动作 | 是否签批 |
| --- | --- |
| `create_label_set`、`split_packages`、`assign_tasks`、`claim_task`、`release_task`、`save_revision`、`submit_task`、`review_task`、`reopen_task`、`upgrade_project`、`manage_users`、`manage_skills`、`import_predictions` | 否 |
| `publish_label_set`、`create_project`、`register_model`、`update_model`、`define_role`、`update_role`、`finalize_project` | 人工签批 |
| `run_prelabel` | 任务数 × 配置单价超过请求预算时签批 |

模板增删改使用 `create_label_set` 的 `target: "template"` 和 `operation: "create" | "update" | "delete"`；用户和团队使用 `manage_users`，技能使用 `manage_skills`。本体动作 schema 给出字段、范围、中英文说法和例句。本期不注册 `heartbeat` 与 `accept_package`。

同一操作人、动作、请求 ID 和完全相同的输入重发，返回原计划；成功执行重发返回原 run 和回执。输入或调用方限制不同会冲突。签批前误点执行的拒绝有审计，签批后仍可执行。修正失败请求要使用新 ID。保存修订的 `previous_revision_id` 必须匹配服务端最新版，否则 HTTP 409 返回 `latest_revision`。两栈都用数据库约束禁止修订 UPDATE/DELETE，并以部分唯一索引保证一个任务同阶段只有一个有效指派。并发抢单的失败方继续选择下一条。

## 身份和角色护栏

实例零登记用户时，保持本机全范围体验，已有动作和评测行为不变。首位登记用户没有显式角色时自动获得管理员。登记后，未知、禁用或归档操作人只有读取权限；最后一人归档也不会恢复匿名写权限。

服务端有效范围等于有效的全平台角色与当前真实项目角色的并集；调用方自报的 scopes 只能收窄。项目级角色不能用于另一个项目，批量任务不能跨项目。领取/放弃需要 `production:claim`，还要按阶段分别具备标注或审核权限，质检员不会因为能领取审核而获得改标注权限。

内置模板为 `administrator`、`project_manager`、`annotator`、`reviewer`、`acceptance`。验收方没有任何写范围，能读进度和预览。项目经理另含 `datasets:export`，可为定稿版本保存训练切分并导出。模板可修改，也可新增角色。范围只能取自已注册动作，不能造新范围或使用 `*`。角色计划逐条列出允许和禁止的动作；执行前角色不生效。签批和执行时都检查签批人当前授予上限。允许另一位有权限的管理员签角色计划，由原发起者执行；其它动作保留原审批身份约束。资产访问申请仍禁止申请人自批。

登记后 HTTP 从 `X-Datakeel-Actor` 取操作人，签批/执行请求体的 actor 必须一致。旧的直接写入接口也检查服务端范围。Agent 和确定性工作流的真实会话归属另存于服务端，保留旧会话显示 actor 的 schema，防止借用高权限会话。这是本机可信安装的操作人选择合同，部署级身份认证属于另一层边界。

MCP 和 Agent 可调只读函数、可准备生产写计划，不能代人签批或执行生产计划。旧有非生产可逆动作行为保留兼容。人通过 Web 审批卡、CLI 或显式 API 请求签批和执行。

## 标签改版、预测与定稿

标签集发布后该版本不可改。新版本必须给改名、删除、合并、拆分提供完整来源和目标映射；拆分必须人工处理。发布不会改写历史修订。影响数精确统计旧版本项目中每任务最新修订内受影响的分类标签、框、文本片段实例，另报受影响修订数；被后续修订替代的历史不属于迁移目标。`label_set_diff` 按当前事实重新计算，不估算。

模型提供方只有 `fake` 与 `import`，均不连接网络。`files` 上传文本内容、文件名和可选的明确样本身份/尺寸。COCO 使用像素 `xywh`，YOLO 使用归一化 `class cx cy width height [confidence]`，内部统一像素 `xyxy`。类别明确映射到标签 ID 或名称；未知类别、越界框、空图、坏文件逐图/逐文件报告，其余图片继续。COCO results 数组必须能精确定位图片，或由单文件显式绑定 sample_id，并提供类别映射，不猜序号。模型修订保存模型名、版本、框置信度均值及上一版指针。COCO 图片若带 Datakeel 训练导出写入的 `datakeel_sample_id` 扩展字段，会先按该样本身份精确绑定，定稿版本导出的 COCO 无需改名即可导回。YOLO 导出的标签文件名是哈希，需按训练包 `MANIFEST.json` 为每个文件填 `sample_id`，类别序号按 `data.yaml` 映射。

预测框四条边允许绝对 `1e-7` 像素的浮点舍入容差，通过后把坐标裁回图片边界。容差不随图片尺寸放大，只吸收转换噪声；超过容差或裁剪后没有正面积的框仍然拒绝。

普通图片导入目前不会读图片头补齐清单宽高。除非项目绑定的版本已记录尺寸，YOLO 需显式提供 `image_width`、`image_height`。完整 COCO 文档可在 `images` 中逐图提供尺寸；多图 COCO results 数组要求每个 `image_id` 精确匹配项目样本 ID 或唯一文件名，且每图有可用宽高，不按项目顺序猜配导出序号。缺少尺寸时，使用完整 COCO 文档，或按图分文件绑定 `sample_id` 并提供宽高。

模板校验框、多边形、分类和文本片段，`component_config.components` 可配置启用组件集合，支持 `min_annotations`、`max_annotations`；`label_mode: "single"` 约束单选。关键点内容仍不支持。编辑和训练集无损往返见[工作台指南](ANNOTATION_WORKBENCH.zh.md)。

定稿要求所有任务有已通过修订。同一事务冻结这些修订，写新版本的原生标注、精确标注/标签统计，复用 `import_annotations` 的事务内入口生成标准 `AnnotationBatch`，更新状态计数并记下生产项目血缘。输入版本和历史修订保持原样。

## CLI、API 与只读工具

```sh
uv run datakeel production demo
uv run datakeel production prepare create_label_set labels.json --actor local
uv run datakeel production plan PLAN_ID --actor local
uv run datakeel production approve PLAN_ID --digest PLAN_DIGEST --actor local
uv run datakeel production execute PLAN_ID --digest PLAN_DIGEST --actor local
uv run datakeel production read project_progress project.json --actor local
```

演示生成三张图片、已发布标签集、个人项目和导入的假预测。个人档顺序为：建标签集 → 发布 → 建项目 → 切包 → 登记模型 → 导入 COCO/YOLO 预测 → 改修订 → 提交 → 定稿。小组档先登记用户、绑定项目角色，新建时设 `workflow_tier: "group"`，然后派单/抢单 → 保存 → 提交 → 领取审核/审核；返工必须带 `issues`，回到原标注员再次保存提交后通过、定稿。仅对上表要求的步骤签批。

REST 使用 `POST /api/actions/{action_type}/prepare`、`GET /api/actions/plans/{id}`、`POST /api/approvals/{id}`、`POST /api/actions/{id}/execute`，决定时带回计划摘要。只读函数统一使用 `POST /api/production/functions/{name}`，也注册给 Agent/MCP：项目进度 `project_progress`、包状态 `package_status`、工作量 `annotator_workload`、返工率 `rework_rate`、一致性 `annotation_consistency`、置信度分布 `prelabel_confidence`、标签集差异 `label_set_diff`、下一条任务 `next_task`、对象投影 `production_objects`、预标注完全一致率 `production_prelabel_accuracy`。

一致性复用现有标注质检；置信度分布统计所有有置信度的模型修订。返工率为每个原标注员收到的返工决定数除以其全部审核决定数。`production_prelabel_accuracy` 对已通过/定稿的人工修订与其最近前序模型修订比较，返回参考任务数、完全一致数和比率（无参考时为 null）；属性、重复形状及已审核空值区别均纳入比较。

## 实现选择与来源

| 选择 | 对照方案 | 原因与来源 |
| --- | --- | --- |
| 同事务维护六状态汇总 | 每次全表计数；异步缓存 | 有界查询、无缓存陈旧窗口。[状态迁移](../datakeel/storage/production_tasks.py)、[查询](../datakeel/storage/production_queries.py)。 |
| 只追加修订、部分唯一指派索引 | 原地覆盖；仅应用判断 | 保留审计历史，两栈都以数据库约束处理并发。[约束实现](../datakeel/storage/production_rows.py)。 |
| 复用动作范围的角色 | 额外授权服务或库 | 保持同一权限和审计事实源，不加运行依赖。[注册表](../datakeel/actions/registry.py)、[服务端授权](../datakeel/storage/identity_authorization.py)。 |
| 类型化 COCO/YOLO 文本解析 | 增加格式库；读取任意服务端路径 | 延续像素坐标约定，限制输入并逐文件报告。[原有适配](../datakeel/storage/annotation_legacy.py)、[解析器](../datakeel/storage/production_prediction_parsing.py)。 |
| 新版本加既有标注导入 | 另造生产专用导出格式 | 发布和说明书继续读取既有合同。[定稿](../datakeel/storage/production_finalize.py)、[标注导入](../datakeel/storage/annotation_store.py)。 |

回归使用生成数据，覆盖两条流程、两栈抢单、独立只读 golden、精确迁移数、预测部分失败、只追加历史、乐观冲突与授权上限。容量验证在一万任务项目测量只读下一条和完整准备加执行的保存链。
