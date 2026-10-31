# 数据生产流程

[English](PRODUCTION.md)

项目绑定输入数据集版本、已发布标签集版本和可选标注模板，输出新的数据集版本及标准标注批次。定稿会把原生标注和准确的标注/标签统计写入新 manifest，发布对账和说明书沿用现有版本合同。

## 对象与关系

`GET /api/ontology` 注册十四个新增对象：用户 `user`、团队 `team`、角色 `role`、技能 `skill`、标签集 `label_set`、模板 `template`、项目 `project`、任务包 `task_package`、生产任务 `production_task`、指派 `assignment`、标注修订 `annotation_revision`、审核 `review`、模型 `model`、预标注运行 `prelabel_run`。原有 worker 的 `task` 身份保持独立。全部对象使用 `AssetRef`；标签集身份带版本。

项目包含任务包，包包含任务；任务关联指派、修订和审核。用户团队、角色和技能、指派人、审核目标、上一修订以及项目输入配置使用统一链接合同。通过 `GET /api/production/objects/{kind}` 读取事实投影，可按 `object_id`、`project_id`、`task_id`、`version`、`limit` 筛选。团队和技能提供增删改；团队档的技能派单比较的就是技能的 `level`（1–10）。

## 状态机与档位

| 六个状态 | 含义 |
| --- | --- |
| `pending` | 待标，包括返工任务 |
| `in_progress` | 已指派或正在标注 |
| `submitted` | 一条确定修订已提交待审 |
| `in_review` | 审核员领取了待审任务 |
| `approved` | 一条确定修订已通过，可参与定稿 |
| `finalized` | 定稿修订已进入新数据集版本 |

返工回到 `pending`，轮次加一，保留原标注员；项目经理可以把退回的这一轮收回，再点名派给别人（见「派单」）。不做自动升级；进度函数列出返工至少三轮的任务。任务包和项目由同事务维护的六个状态计数汇总，不另存可变状态，不在每次查询时全表计数。

| 档位 | 行为 |
| --- | --- |
| 个人 `personal`，默认 | 保存或导入预测后提交即通过。没有指派和审核记录，动作审计记 `SYSTEM_APPROVAL`。 |
| 小组 `group` | 点名派单或自行抢单，提交、审核、带问题返工、原人再提交、通过。允许自标自审。 |
| 团队 `team` | 在小组档规则上，加上强制租约与心跳、按项目选的派单方式（指派、技能匹配、抢单）、严格标审分离，以及定稿前每个任务包都走 P26 抽检验收。见[团队档](#团队档)。 |

`upgrade_project` 只允许向前升档。拒绝降档，因为已经发生的审核历史不能解释成早期流程。项目加入第二位参与者时，相关回执只返回一次 `suggest_review: true`，不自动升档。每条指派都记录租约到期时间，只有团队档会执行（小组档和个人档行为不变）。

个人档升档时，已有人工保存、仍可编辑的任务会补上原作者的标注指派。原作者可按现有持有人校验继续保存、提交送审或释放，不需要重开任务，轮次不增加；任务状态和修订历史保持不变。无作者任务、纯模型预测和已通过任务不新增指派。保留历史所有权不会授予角色范围，仍需通过当前账号权限校验；释放后必须重新领取或被指派才能继续。

## 受控动作

每个新增动作都有必填的客户端 `request_id`。所有写操作走原有准备、签批、执行协议，并落审计、血缘和回执。高频动作不要求签批，准备后由人明确执行。

| 动作 | 是否签批 |
| --- | --- |
| `create_label_set`、`split_packages`、`assign_tasks`、`claim_task`、`release_task`、`heartbeat`、`save_revision`、`submit_task`、`review_task`、`reopen_task`、`revoke_assignment`、`configure_project`（下列情形除外）、`upgrade_project`、`manage_users`、`manage_skills`、`import_predictions` | 否 |
| `publish_label_set`、`create_project`、`register_model`、`update_model`、`define_role`、`update_role`、`accept_package`、`upgrade_project_template`、`finalize_project` | 人工签批 |
| `run_prelabel` | 冻结的估价超过请求预算时签批：云端模型按 token 和图片计价（见 [AI 预标注](#ai-预标注置信度分流与-ai-预审)），其他提供方按任务数 × 单价 |
| 调低 `review_sample_rate` 的 `configure_project` | 人工签批 |
| 开启或放宽高置信度直通的 `configure_project` | 人工签批 |

模板增删改使用 `create_label_set` 的 `target: "template"` 和 `operation: "create" | "update" | "delete"`；用户和团队使用 `manage_users`，技能使用 `manage_skills`。本体动作 schema 给出字段、范围、中英文说法和例句。

**模板版本。** 模板每写一次（`create_label_set` 的 `target: "template"`，归档也算）就追加一个不可改的版本；两种数据库都拒绝对已存版本 UPDATE 和 DELETE。项目建好时锁定当时模板的修订号（`template_version`），和它已发布的 `label_set_version` 放在一起。保存、提交检查、工作台表单和定稿都按锁定的版本读，所以改了或归档了共用模板、发布了标签集新版本，已有项目都不变。

`upgrade_project_template`（`production:manage`，人工签批；MCP 和 Agent 只能准备计划）把一个还没定稿的项目升上去。`template_version` 默认是模板最新修订，`label_set_version` 默认是最新发布版本；降级、目标版本已归档、升级后什么都没变的，一律拒绝。计划里项目对象带 `template_upgrade`：

- 模板和标签集从哪版升到哪版；
- 标签新增、删除、改名（标识不变、名字变了）、其它改动；属性（`target:key`）新增、删除、修改、新变成必填；模板其它设置改了哪些；
- `task_count`：项目里全部任务（全部切换版本）；
- `annotated_task_count`：有已有标注的任务数，已有标注指任务的当前（最新）修订，没有修订的任务不算；`annotation_object_count`：这些修订里分类标签、框、多边形、文本片段的个数；
- `invalid_task_count` 和 `invalid_tasks`：在目标版本下过不了提交检查的已有标注（规则和 `submit_task` 一样：目标标签集版本里的标签、模板组件和数量规则、必填和类型），逐条列出所有问题；`invalid_object_count`：自身标签或属性不合格的标注对象个数。

计划冻结项目和每条任务的头修订，准备之后、签批之前有人保存、模板又出新版或锁定版本变了，计划作废，执行时会重算。签批只改这个项目的 `template_version` 和 `label_set_version`；修订、任务状态和其它项目都不动，不合格的标注走正常的保存和返工流程改。v0.18.0 及以前的库在启动时迁移：给每个模板的当前修订补一条版本记录，没锁定的项目锁到这一版，也就是它实际在用的那一版，所以行为不变；重复执行不会再写任何东西。

同一操作人、动作、请求 ID 和完全相同的输入重发，返回原计划；成功执行重发返回原 run 和回执。输入或调用方限制不同会冲突。计划只冻结它的结论所依赖的事实，执行时这些事实变了就拒绝：单任务的看内容动作（`submit_task`、`review_task`、`reopen_task`、`release_task`、`heartbeat`）冻结整条任务、有效指派和项目；`revoke_assignment` 和 `assign_tasks` 只冻结每条任务的状态、轮次和当前持有人（指派 ID、人、阶段），所以从准备到确认之间持有人的自动保存、模型草稿导入和续租都不会让人已经看过的收回或派单失效，提交、轮次变化或换了持有人则会。验收和定稿照旧冻结准确的已通过修订。签批前误点执行的拒绝有审计，签批后仍可执行。修正失败请求要使用新 ID。保存修订的 `previous_revision_id` 必须匹配服务端最新版，否则 HTTP 409 返回 `latest_revision`。两栈都用数据库约束禁止修订 UPDATE/DELETE，并以部分唯一索引保证一个任务同阶段只有一个有效指派。并发抢单的失败方继续选择下一条。

## 身份和角色护栏

实例零登记用户时，保持本机全范围体验，已有动作和评测行为不变。首位登记用户没有显式角色时自动获得管理员。登记后，未知、禁用或归档操作人只有读取权限；最后一人归档也不会恢复匿名写权限。

服务端有效范围等于有效的全平台角色与当前真实项目角色的并集；调用方自报的 scopes 只能收窄。项目级角色不能用于另一个项目，批量任务不能跨项目。领取/放弃需要 `production:claim`，还要按阶段分别具备标注或审核权限，质检员不会因为能领取审核而获得改标注权限。

内置模板为 `administrator`、`project_manager`、`annotator`、`reviewer`、`acceptance`。验收方没有任何写范围，能读进度和预览。项目经理另含 `datasets:export`，可为定稿版本保存训练切分并导出。模板可修改，也可新增角色。范围只能取自已注册动作，不能造新范围或使用 `*`。角色计划逐条列出允许和禁止的动作；执行前角色不生效。签批和执行时都检查签批人当前授予上限。允许另一位有权限的管理员签角色计划，由原发起者执行；其它动作保留原审批身份约束。资产访问申请仍禁止申请人自批。

登记后 HTTP 从 `X-Datakeel-Actor` 取操作人，签批/执行请求体的 actor 必须一致。旧的直接写入接口也检查服务端范围。Agent 和确定性工作流的真实会话归属另存于服务端，保留旧会话显示 actor 的 schema，防止借用高权限会话。这是本机可信安装的操作人选择合同，部署级身份认证属于另一层边界。

MCP 和 Agent 可调只读函数、可准备生产写计划，不能代人签批或执行生产计划。旧有非生产可逆动作行为保留兼容。人通过 Web 审批卡、CLI 或显式 API 请求签批和执行。

## 团队档

团队档是在小组档上多加的规则；对象、状态和动作都一样，小组档和个人档行为完全不变。

**租约。** 领取或被指派就是一份租约，时长 `lease_minutes`（默认 10 分钟，按项目设，`configure_project` 可改）。持有人用 `heartbeat` 续租：标注工作台打开任务期间会自动续租（见[打开中的任务自己刷新](ANNOTATION_WORKBENCH.zh.md#打开中的任务自己刷新)），也可以通过 API、命令行或 MCP 准备的计划来发。过期后持有人的所有写操作（`save_revision`、`submit_task`、`heartbeat`、`review_task`）都会明确报「租约已过期」冲突，不会悄悄成功；已被收回时错误里也会说明。回收器（reaper）跑在现有 worker 循环里，也可以手动 `datakeel production reap [--now ISO] [--limit N]`。过期的标注退回 `pending`，过期的审核退回 `submitted`；已保存的修订和修订指针都保留，下一位持有人接着改。租约只在本阶段进行中才计时：任务等审核时，标注员保留的指派不会被收回；返工退回时重新起租。每次收回在只追加表 `production_lease_releases` 里记一行，主键就是指派 ID；回收器在任务行锁下（PG 用 `FOR UPDATE SKIP LOCKED`）重读指派再决定，所以多个回收进程并发或重复跑，每份租约都只收回一次，中途崩溃重跑即可。小组档升到团队档时，进行中的指派按升档时刻重新起一份完整租约；只改执行用的到期时间列，指派记录本身不变，下次心跳两者一起续；收回记录写的是实际执行的到期时间。

**派单。** `dispatch_strategy` 按项目设：`assign`（经理指派，禁止自领）、`skill`（经理用 `assign_tasks` 加 `strategy: "skill"` 派；自领也要够格）、`claim`（自领，默认）。三种都写同一张指派表，「一个任务同阶段只有一个有效指派」的唯一索引照常生效；每条指派用 `dispatch` 记来源（`assign`、`skill`、`claim`、`preserved`）。技能要求写明标注类型、领域和 `min_level`。某人绑定的有效技能类型和领域都匹配、等级不低于要求才算够格；等级只做门槛。在够格且有该阶段权限的人里，任务按优先级从高到低、再按任务 ID 排，每条派给本项目该阶段负载最少的人，并列取用户 ID 最小的；每派一条就把这人负载加一，所以同样输入结果完全可复现。负载只算正在做的：标注阶段任务还在待标（含退回的返工）或标注中的有效指派，审核阶段正在审的有效指派。已提交等审核、已通过的不算，尽管标注指派要到通过才结束。自领、点名派单、技能派单、驾驶舱选人框的「手上 N 个」、派单预览和 `skill_workload` 都用这同一个数。自领和技能派单在原标注员仍是在用账号时把返工留给原标注员；原标注员被停用后，技能派单可以派给别人。项目经理也可以先把退回的返工收回（`revoke_assignment`），再点名派给别人：准备好的计划在 `transfers` 里逐条写明（任务、第几轮、从原标注员转给谁），这一项由服务端填写，签批到执行之间如果有变就拒绝执行；转出后新的人就是这一轮的标注员（指派上的 `transferred_from` 记着原标注员）。审核派单跳过任何一轮标过这条任务的人，所以原标注员和新标注员都审不了它。`max_active_tasks`（项目设置或单次请求）限制每人手上正在做的任务数；单次请求只能等于或低于项目设置，高于项目设置返回 422 并写明项目设置是多少：技能批量派到上限就停，没派出的任务在 `unassigned` 里带原因列出；指名批量超上限整批拒绝（报错写明此人现有几条、这次要加几条、上限多少）；到上限再自领会被拒。所有要数负载的路径都先按（项目, 人）串行到事务结束，同一人并发领取、或领取和派单撞在一起，都不会数到同一个负载。

**标审分离。** 团队档里，任何一轮标过这条任务的人都不能审它：当前标注员、所有人工修订的作者、所有曾持有标注指派的人都排除在外。领取审核（审核队列直接跳过）、指派审核、提交审核结论三处都检查，所以改派、事后换角色、重开都绕不过去。小组档仍允许自标自审。

**抽检验收。** 一个任务包的任务全部通过后，`package_acceptance` 给出 P26 抽样预览（`method` 取 `aql` 配 `aql`，或 `ratio` 配 `ratio` 和 `acceptance_number`，另有 `seed`）；抽样单位是包里的样本，批量、样本量、抽中的样本和判定数与 P26 `annotation_qa` 抽检走同一段代码。人签 `accept_package`，对每个抽中的单位各给一条检查结果（必须恰好是抽中的那些）。不合格数不超过接收数就收；否则包里每条任务（抽没抽中都算）退回 `pending`，轮次加一，仍归原标注员。团队档定稿要求每个任务包最近一次结论是「收」，且覆盖当前的通过版本；重开再通过的任务需要重新验收。

**管理与轮次。** `revoke_assignment`（范围 `production:assign`，项目经理和管理员有）把进行中的标注或审核退回队列，保留修订，并记下收回原因；任何持有人都能收回，包括还没人登记时指派给 `local` 的任务。已提交或已通过的工作改用重开。`reopen_task` 只有把已提交或已通过的工作退回才算一轮返工；重开待标或标注中的任务，轮次、状态、指派和修订都不变（设计稿第 5 节），之后照常可以收回再改派给别人，新的人拿到的仍是第 0 轮的普通任务。

**只读。** `lease_status` 按到期时间列出计时中的租约，分为正常、`expiring_within_seconds`（默认 120 秒）内将到期、已过期三类，并附最近收回记录和原因。每条指派给出实际生效的到期时间；升团队档时重新起租的指派，给的是重新起租后的截止，而不是旧记录里的时间。`skill_workload` 按有效技能汇总正在做的任务数（同上面的负载口径）和已完成任务数。`package_acceptance` 返回任务包状态（`in_progress`、`ready`、`accepted`、`rejected`）、进度、就绪时的抽样预览和最近一次结论。

**角色。** `heartbeat`（`production:claim`）放在标注员和质检员模板；`configure_project`、`upgrade_project_template`（`production:manage`）、`revoke_assignment`（`production:assign`）、`accept_package`（`production:accept`）放在项目经理模板；管理员拥有全部范围，验收方仍然只读。MCP 和 Agent 只能准备这些计划，不能签批或执行。

## 标签改版、预测与定稿

标签集发布后该版本不可改。新版本必须给改名、删除、合并、拆分提供完整来源和目标映射；拆分必须人工处理。发布不会改写历史修订。影响数精确统计旧版本项目中每任务最新修订内受影响的分类标签、框、文本片段实例，另报受影响修订数；被后续修订替代的历史不属于迁移目标。`label_set_diff` 按当前事实重新计算，不估算。

模型提供方有 `fake`、`import` 和 `cloud`，只有 `cloud` 连网，见 [AI 预标注](#ai-预标注置信度分流与-ai-预审)。`files` 上传文本内容、文件名和可选的明确样本身份/尺寸。COCO 使用像素 `xywh`，YOLO 使用归一化 `class cx cy width height [confidence]`，内部统一像素 `xyxy`。类别明确映射到标签 ID 或名称；未知类别、越界框、空图、坏文件逐图/逐文件报告，其余图片继续。COCO results 数组必须能精确定位图片，或由单文件显式绑定 sample_id，并提供类别映射，不猜序号。模型修订保存模型名、版本、框置信度均值及上一版指针。COCO 图片若带 Datakeel 训练导出写入的 `datakeel_sample_id` 扩展字段，会先按该样本身份精确绑定，定稿版本导出的 COCO 无需改名即可导回。YOLO 导出的标签文件名是哈希，需按训练包 `MANIFEST.json` 为每个文件填 `sample_id`，类别序号按 `data.yaml` 映射。

预测框四条边允许绝对 `1e-7` 像素的浮点舍入容差，通过后把坐标裁回图片边界。容差不随图片尺寸放大，只吸收转换噪声；超过容差或裁剪后没有正面积的框仍然拒绝。

图片导入时读图片头，把摆正后（按 EXIF Orientation 变换后）的宽高记在清单元数据的 `width`、`height` 里，旁边记 `stored_width`、`stored_height` 和 `orientation`；读不出来宽高记为 `null`（未知），读不出方向按 1。预测一律存成摆正后的坐标：YOLO 按摆正后的宽高解释归一化坐标（Ultralytics 训练和推理都先按 EXIF 摆正）。COCO 图片条目的 `width`/`height` 和摆正后的宽高一致就按摆正后的方向；只和存储方向的宽高一致（转了 90°）就按存储方向读，导入时换算过来；正方形图分不出来，默认按摆正后的方向。文件上的 `coordinate_frame: "display" | "stored"` 可以覆盖上面的推断。YOLO 没带 `image_width`、`image_height` 时用记下的宽高；这张图也没有记录时，整份导入返回 422，写明是哪张图、哪个预测文件。完整 COCO 文档可在 `images` 中逐图提供尺寸。多图 COCO results 数组可以整份导入：按 `image_id` 分组，`image_id` 要精确匹配项目样本 ID 或唯一文件名，不按项目顺序猜配导出序号；对不上任何图的组列为 `unknown_image` 并写明有几条结果没导入，对上了但没有宽高的图列为 `unknown_size`，不会静默丢掉。

模板校验框、多边形、分类和文本片段，`component_config.components` 可配置启用组件集合，支持 `min_annotations`、`max_annotations`；`label_mode: "single"` 约束单选。关键点内容仍不支持。

**属性字段。** 模板最多定义 50 个带类型的 `attributes`。每个字段有 `key`（标识符）、`name_zh`、`name_en`、`type`、`target`、`required` 和可选的 `default`：

| `type` | 存的值 | 额外定义 |
| --- | --- | --- |
| `boolean` | `true` / `false` | — |
| `enum` | 一个选项的 `value` | `options`（`value`、`name_zh`、`name_en`），至少一个、不重复 |
| `multi_enum` | 不重复的选项值列表 | 同上 `options` |
| `number` | 有限数字（布尔不算） | 可选 `minimum`、`maximum` |
| `text` | 字符串 | `max_length`（默认 200，最多 2000） |

`target: "object"`（默认）作用于每个框、多边形和文本片段；`target: "record"` 作用于整条标注记录，分类任务的属性就放这里。同一 target 下 key 不重复；选项和范围要符合类型；默认值本身必须合法。工作台按这些字段渲染表单；没有定义字段的老模板照旧使用自由的属性字典。

人工 `save_revision` 每次按项目锁定的模板版本检查：类型不对或缺必填项返回 HTTP 422，并写明 key 和位置，例如 `Attribute "kind" is required on box 1`、`Attribute "count" on polygon 2 must be a number between 0 and 10`、`Attribute "quality" is required on the record`（位置从 1 数）。缺 key 或为 `null` 算缺失；必填时空的 `multi_enum` 列表和空白文本也算缺失。`submit_task` 对头修订再查一次，所以保存之后项目升级带来的新必填项会挡住提交，填好才行。模型修订（导入和预标注）只查类型，不会因为人还没填某个字段而导入失败。模板没定义的 key 原样保留。编辑和训练集无损往返见[工作台指南](ANNOTATION_WORKBENCH.zh.md)。

定稿要求所有任务有已通过修订，团队档还要求每个任务包都已验收。同一事务冻结这些修订，写新版本的原生标注、精确标注/标签统计，复用 `import_annotations` 的事务内入口生成标准 `AnnotationBatch`，更新状态计数并记下生产项目血缘。输入版本和历史修订保持原样。

## AI 预标注、置信度分流与 AI 预审

### 云端模型

`register_model` 用 `provider: "cloud"` 登记一个 OpenAI 兼容的视觉接口，首个实测的是阿里云百炼（DashScope 兼容模式）。能力填 `box` 和/或 `classification`；一次运行只补模型和项目模板都启用的组件。例：

```json
{"id": "qwen-flash", "name": "qwen3.5-flash", "version": "2026-10", "provider": "cloud",
 "capabilities": ["box"], "currency": "CNY",
 "cloud": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen3.5-flash",
           "credential_env": "DASHSCOPE_API_KEY", "input_price": 0.0002, "output_price": 0.002}}
```

| `cloud` 字段 | 默认 | 含义 |
| --- | --- | --- |
| `base_url` | — | HTTPS 地址（只有本机回环允许 HTTP）；带用户名密码、查询串或片段的地址直接拒绝 |
| `model` | — | 提供方的模型名 |
| `credential_env`、`credential_source` | —、`env` | 只存凭证的**名字**：环境变量名；`credential_source` 为 `keychain` 时是系统钥匙串账户名（macOS `security find-generic-password -a <名字> -w`） |
| `input_price`、`output_price` | — | 每千 token 单价，币种取模型的 `currency`；模型上的 `unit_price` 另按张计费 |
| `coordinate_space` | `normalized_1000` | 模型框坐标是 0–1000 网格，或发出图片的 `pixel` 像素坐标 |
| `max_image_side`、`token_patch` | 1280、32 | 图片长边缩到这个尺寸；每 32×32 像素块算一个图片 token |
| `expected_output_tokens`、`max_output_tokens` | 160、2048 | 估价用的输出长度先验；回复上限 |
| `cross_check`、`confidence_source` | `true`、`combined` | 是否再发一张左右镜像图；对象置信度怎么来（见分档） |
| `request_parameters` | `{"enable_thinking": false}` | 额外请求体字段；模型名、消息、温度和 token 上限不能覆盖 |

库里只存凭证的名字。密钥在运行开始时读取，只放进 `Authorization: Bearer` 请求头，从不写进数据库、日志、回执、血缘或 API 返回；读不到就在发出任何请求前失败。请求不走代理设置、不跟随重定向、不重试。

**像素和坐标。** 模型看到的就是工作台显示的像素（`task_content`，按存储方向，不做 EXIF 旋转），缩小后重新编码成不带元数据的 JPEG。每张图并行发两次：原图和左右镜像。框用图片转写同一个坐标换算函数换算，先按发出的那张图校验，再镜像回来、缩放到原图像素。越界、零面积、标签不认识、格式坏的框丢弃，连同原因列在运行的 `dropped` 里。回复是裸 JSON 数组、用 `bbox_2d`/`bbox` 键、或中途被截断时，完整的对象都保留。

**估价和预算。** 准备 `run_prelabel` 时在计划里冻结一个 `prelabel_estimate` 对象：要发的图数、每张的输入和输出 token、每张和总价，以及按最长回复算的上限。输入 token 由两部分相加：指令（UTF-8 字节数 / 3.3 + 25，按百炼实测校准）和图片块（至少 4 块，另加 2 个起止 token）。输出 token 从 `expected_output_tokens` 起步，向同一模型以往成功调用的实测均值靠拢，本项目的调用优先（先验按 20 次调用计权）。估价超过请求的 `budget` 要签批。签批之后预算仍是硬上限：图片每批最多 4 张发出，只有「已实际花费 + 这张的预计价格」（本次已有完成的图片后用本次实测均价）不超预算才放行。中途停下的运行记录 `stopped`：停在哪个样本前、完成和剩余张数、已花费、预算和下一张的预计价格；已做完的保留。

**记录和失败。** 每次运行保存每次调用的视图、结果、token、价格和耗时，token 合计，估价，丢弃项，跳过的样本，阈值和分档；没有返回 usage 的回复按估价计费。工作台项目读取增加 `prelabel_spend`：按模型汇总运行数、图片数、token 和费用。单张失败——`timeout`、`rate_limited`、`network_error`、`provider_error_<状态码>`、`invalid_response`、`image_unreadable`、`revision_rejected`、`task_changed`——列进失败清单，`filename` 是图片文件名（清单里的相对路径），`sample_id` 单独一栏，其他图片继续；提供方返回的正文从不保存。同一动作重跑只发可编辑（待领取或进行中）且还没有同名同版本模型草稿的任务，所以失败和没发的图会补上，不会重复花钱。头修订是人保存的任务也跳过：不调模型、不花钱、不算进估价。运行在 `human_edited_sample_ids` 里列出这些任务，估价用 `human_edited` 计数。

**模型回答期间不占锁。** 对调用方来说，执行云端 `run_prelabel` 仍然是同步的，但调用模型时不开任何事务。动作自己的事务只做几件事：查凭证、占下本项目的运行位、冻结目标任务、估价和阈值，把运行记成 `running`（动作运行记 `RUNNING`，先不发回执）。提交之后，图片每批 4 张在事务外发出；每批结果用一个独立的短事务写入：拿和单任务动作一样的锁，重读并锁住这几条任务；如果某条任务在这期间已经有了本模型版本的草稿，或者头修订变了，就跳过它（记 `task_changed`：这张图照样计费、列进失败清单，人的改动留在最上面）。最后一个短事务把运行记为 `completed`，写审计，发唯一的一张回执，所以 `execute` 返回的仍是跑完的结果。同一项目同时只能有一个 `running` 的云端运行：第二次发起直接报冲突，一张图都不发，不会重复花钱，也不会重复写修订。如果一个运行 10 分钟没有更新进度（进程已经死了），下一次发起时把它记为 `abandoned`，对应的动作运行记 `FAILED`；原来那个进程如果还活着，发现自己被接管后不再写入、也不再发图。工作台项目读取返回 `prelabel_progress`，列出最近几次云端运行的状态、计划张数、已完成、失败、花费、预算和最后更新时间；有运行在跑时驾驶舱每 5 秒刷新一次。实测：跑 40 张图、提供方每次延迟 0.6 秒期间，另一个项目的打开、保存、提交，p95 在 SQLite 上是 3、14、9 毫秒，在 PG 上是 22、64、64 毫秒，0 报错。选同步分段而不是后台 worker，是为了让 API、命令行和 MCP 调用方照旧拿到一张跑完的回执，也不用多起一个进程。

### 预标注准确率

`production_prelabel_accuracy` 把每个已通过或已定稿的人工修订和它最近的前序模型修订比较。除了原有的完全一致字段，还返回 `iou_50` 和 `iou_75`：模型对象数、人工对象数、命中数、精确率、召回率、F1，以及所有对象都命中的任务数和占比；另有 `attribute_agreement`，只统计已匹配对象的属性一致度。同一标签内一对一匹配，按 IoU 从高到低贪心，与 COCO 一致；IoU ≥ 0.5（或 0.75）算命中。框用框 IoU，多边形用精确面积 IoU，文本片段用字符区间 IoU，分类的标签集合完全相同才算命中。属性不同不影响几何命中。驾驶舱主数字是 IoU 0.5 的 F1；悬停显示规则、精确率、召回率和 0.75 的数字。

### 置信度分档

每个模型对象的置信度按 `confidence_source` 取：`self`（模型自报的概率）、`cross_check`（它在镜像回复里同标签匹配的 IoU）或 `combined`（两者均值，默认；在下面的实测里最能区分对错）。任务的档位取最低对象的档位；没有对象的草稿算低档。`configure_project` 可以设 `confidence_high` 和 `confidence_low`（低 ≤ 高；`clear: ["confidence_thresholds"]` 改回实测）。没设时按已通过的数据反推：每个审过的模型对象，和通过的人工对象同标签且 IoU ≥ 0.5 算命中；再用保序回归（pool adjacent violators，自己实现，见[置信度分档](../datakeel/annotation_qa/confidence_tiers.py)）拟合一条单调不减的「置信度 → 命中率」校准曲线：相邻两组置信度如果命中率倒挂，就合并成一段。高档阈值是校准命中率 ≥ 95% 的最低置信度；低档阈值是校准命中率 ≥ 50% 的最低置信度，低于它的对象进低档。没有哪段到 50% 时，低档阈值取 1.0，注明 `no_low_threshold`。实测对象不到 30 个时用默认 0.85 和 0.5，注明 `insufficient_samples`，并且 `pass_through` 为 false。工作台项目读取返回 `confidence_thresholds`，带来源、对象数、各档实测命中情况，以及校准曲线的 `segments`（每段的置信度区间、对象数、命中数和命中率）。

运行后，小组档和团队档里没人动过的任务按档分流：高档直接提交，由 AI 预审和抽检比例决定要不要人审；中档保留草稿供修改；低档草稿仍可查看，但工作台从空白开始标。个人档只显示档位。运行的 `tiers` 列出每个任务的档位、去向和草稿修订。

**直通有人负责。** 只有高档阈值是实测或人为配置出来的，高档草稿才直接提交。还在用默认值（冷启动）时，高档按中档留成草稿，注明 `insufficient_samples`，工作台写明「样本不足，暂不直通」。直通的修订来源仍是 `source: "model"`，并带 `pass_through`：模型 ID、置信度、当时的高低阈值及其来源和对象数，以及 `triggered_by`，也就是执行这次动作的人。这个人记为该任务的标注人：团队档标审分离照常生效，他不能审这些任务（小组档和个人档按原规则）；审核记录里的标注人也写他，不会写成审核员。动作审计里每条直通一行，开头是 `模型高置信度直通 / Model high-confidence pass-through`，后面是任务、修订、模型、置信度、阈值和触发人。开启或放宽直通要签批，包括两种情况：用手工高档阈值替换冷启动默认值，或者把高档阈值调得比现在低。这样的 `configure_project` 计划需要签批，审计里写「放宽高置信度直通 / High-confidence pass-through relaxed」，附原来的阈值、新的阈值和签批人。调高阈值或清回默认值不用签批。

**模型草稿不能当成人的活交出去。** 头修订是模型草稿时，`submit_task` 直接拒绝（422）：标注员要先存一条自己的修订，改过或不改都行（低档就是空白开始的那份，中档就是确认后的草稿）。在工作台里不改直接提交时，界面会先替他存这一份。

### 提交时的 AI 预审

每次提交在有人审之前先打分。P26 的可疑规则在提交的头修订上运行，并带上本项目最多 500 个已提交、审核中、已通过或已定稿的其他任务做参照（按感知哈希找近重复图）；同时按锁定模板复核；人工头修订偏离一个高置信模型草稿时，加一条分歧原因（权重 0.5 × 草稿置信度 × 内容差异）。每条命中有固定权重，风险分是它们的 noisy-OR：`1 − ∏(1 − 权重)`，所以多一条原因分数只会升不会降。风险 ≥ 0.3 为高风险；除了 `rare_category`（0.2）每条规则单独命中就是高风险。分数、每条原因及证据、指向的框/多边形/片段、抽检抽签值和决定，都只追加地存下，并绑定到被提交的那个修订。和草稿比、和近重复图比，都只比两边都记录了的标注类型：只出框的模型草稿不代表图片的分类；空列表则是记录了「没有」，照样比较。

审核队列按风险分排，其次是返工轮次、模型置信度和草稿差异。`review_sample_rate`（默认 1 = 全部审，即原有行为）控制低风险抽检：用任务、轮次和修订算出可复现的抽签值，低于比例就进审核，否则直接通过，并在动作审计里记「AI 预审低风险，按抽检比例免审 / AI pre-review low risk, exempt by review sampling」及比例、风险分和抽签值。高风险总是要审。调低比例是签字决定：调低比例的 `configure_project` 计划要签批。个人档里预审结果只展示给标注员，从不拦提交。

50 张 COCO 图实测（80 个标签，两个视图都发；P/R 按 IoU 0.5，只算回复能解析的图）：

| 模型 | F1@0.5 | F1@0.75 | 精确率 | 召回率 | 格式失败 | 每张费用（元） | 中位耗时 | 置信度 AUROC 自报 / 镜像 / 合成 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3.5-flash | 0.560 | 0.420 | 0.704 | 0.464 | 1/50 | 0.0016 | 2.0 秒 | 0.71 / 0.78 / 0.80 |
| qwen3.5-plus | 0.644 | 0.502 | 0.729 | 0.576 | 2/50 | 0.0046 | 3.6 秒 | 0.75 / 0.81 / 0.82 |
| qwen3.6-plus | 0.522 | 0.404 | 0.667 | 0.429 | 7/50 | 0.0129 | 3.8 秒 | 0.77 / 0.77 / 0.80 |

qwen3.7-flash 对这个账号返回 HTTP 403。格式失败是被截断或格式坏的回复，现在的解析能救回其中一部分。qwen3.5-flash 是能用的最便宜的默认；qwen3.5-plus 价格约 3 倍，F1 高约 15%。

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

工作台还用几个 HTTP 只读接口读同一套事实，权限与项目、任务一致：`GET /api/production/workbench`；`GET /api/production/projects/{id}/workbench`（分页、`view` 取 `all`/`mine`/`review`、`package_id`，以及 `search`：按相对路径或文件名做不区分大小写的子串匹配，先过滤再分页；本页每条任务和每条返工多轮的任务都在 `task_samples` 里带文件名和相对路径，没记相对路径时相对路径就是文件名）；`GET /api/production/projects/{id}/task-samples?task_id=…`（一次最多 500 条，只返回属于该项目的任务，别的项目的 ID 忽略）；`GET /api/production/tasks/{id}/workbench`；`GET /api/production/tasks/{id}/status`——轻量轮询，返回任务、指派、每个计时中租约的实际生效 `expires_at`、`seconds_remaining`、`enforced`，以及最近 10 条租约释放记录，不读源文件。样本名取自钉住版本 manifest 的文件名，从不返回服务器路径或对象存储 key。团队档的 `review` 视图不列调用者标过的任务，口径与领取审核相同。`POST /api/production/projects/{id}/dispatch-preview` 不加锁、不写库，算出此刻 `assign_tasks`（`strategy: "skill"`）会怎么派：合格人员、每条任务派给谁、每人当前负载和新增条数、没派出去的任务及原因（`task_state_not_dispatchable`、`already_assigned`、`load_limit_reached`、`no_qualified_person`）。它和执行共用匹配代码；预览到执行之间负载变了，执行结果以回执为准。

REST 使用 `POST /api/actions/{action_type}/prepare`、`GET /api/actions/plans/{id}`、`POST /api/approvals/{id}`、`POST /api/actions/{id}/execute`，决定时带回计划摘要。只读函数统一使用 `POST /api/production/functions/{name}`，也注册给 Agent/MCP：项目进度 `project_progress`、包状态 `package_status`、工作量 `annotator_workload`、返工率 `rework_rate`、一致性 `annotation_consistency`、置信度分布 `prelabel_confidence`、标签集差异 `label_set_diff`、下一条任务 `next_task`、对象投影 `production_objects`、预标注完全一致率 `production_prelabel_accuracy`，团队档另有租约状态 `lease_status`、按技能工作量 `skill_workload`、任务包验收 `package_acceptance`，以及可派人名单 `assignees`（参数 `project_id`、`stage`：能按名字派这一阶段任务的人和他们手上的任务数，和 `GET /api/production/projects/{id}/assignees` 返回一致，调用方不能派单时同样被拒）。

一致性复用现有标注质检；置信度分布统计所有有置信度的模型修订。返工率为每个原标注员收到的返工决定数除以其全部审核决定数。`production_prelabel_accuracy` 对已通过/定稿的人工修订与其最近前序模型修订比较，返回参考任务数、完全一致数和比率（无参考时为 null），以及[预标注准确率](#预标注准确率)里说的 IoU 精确率、召回率和 F1；属性、重复形状及已审核空值区别均纳入比较。

## 实现选择与来源

| 选择 | 对照方案 | 原因与来源 |
| --- | --- | --- |
| 同事务维护六状态汇总 | 每次全表计数；异步缓存 | 有界查询、无缓存陈旧窗口。[状态迁移](../datakeel/storage/production_tasks.py)、[查询](../datakeel/storage/production_queries.py)。 |
| 只追加修订、部分唯一指派索引 | 原地覆盖；仅应用判断 | 保留审计历史，两栈都以数据库约束处理并发。[约束实现](../datakeel/storage/production_rows.py)。 |
| 复用动作范围的角色 | 额外授权服务或库 | 保持同一权限和审计事实源，不加运行依赖。[注册表](../datakeel/actions/registry.py)、[服务端授权](../datakeel/storage/identity_authorization.py)。 |
| 类型化 COCO/YOLO 文本解析 | 增加格式库；读取任意服务端路径 | 延续像素坐标约定，限制输入并逐文件报告。[原有适配](../datakeel/storage/annotation_legacy.py)、[解析器](../datakeel/storage/production_prediction_parsing.py)。 |
| 回收器放在现有 worker 里，每条指派一行收回记录，任务行锁 + `SKIP LOCKED` | 单独调度进程；每条指派一个定时器；PG advisory lock；直接删过期行 | 不加进程不加依赖，崩溃重跑安全，主键保证只收回一次。和 [Amazon SQS 可见性超时](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)、[Kubernetes Lease](https://kubernetes.io/docs/concepts/architecture/leases/) 同一模型；[`SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) 与现有 [worker 队列](../datakeel/storage/task_queue.py)一致。[回收器](../datakeel/storage/production_reaper.py)。 |
| 技能匹配：等级做门槛，再按当前负载最少，再按用户 ID 最小 | 等级和负载加权打分；全局最优匹配（[匈牙利算法 `linear_sum_assignment`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)）；轮流派 | 门槛做法与 [MTurk 资格要求](https://docs.aws.amazon.com/AWSMechTurk/latest/AWSMturkAPI/ApiReference_QualificationRequirementDataStructureArticle.html)（`GreaterThanOrEqualTo`）一致，等级不会拿来和负载互换；「派给最闲的人」好解释、可复现、不加依赖，验收方能独立算出同样结果。[派单](../datakeel/storage/production_dispatch.py)、[规则](../datakeel/storage/production_dispatch_rules.py)。 |
| PG 上单任务动作不再拿全表动作锁；计数在提交前按固定顺序一次写入 | 每个动作都 `LOCK TABLE`；按项目加 advisory lock；每次状态迁移当场改计数 | B8 实测：全表锁把吞吐压在每秒 13 次（保存 p95 4.4 秒）；按项目加锁对单项目同样串行。去掉全表锁后，事务中途写计数行会让一次收回多条的回收器和领取互相死锁，所以改成每个事务在提交前按排序一次写完计数，回收器每收回一条单独提交。任务行锁和指派唯一索引保证这几个动作安全。[锁](../datakeel/storage/action_locks.py)、[计数](../datakeel/storage/production_counters.py)、[容量](CAPACITY.md)。 |
| 所有动作先拿表级锁、再拿行锁：单任务动作一开始就拿 `lineage_events` 的 `ROW EXCLUSIVE`（4 张谓词表里它只写这一张，用来写回执） | 带表锁的动作先按 ID 锁任务行再拿表锁；把回执挪出持有行锁的那段；只在最外层对 `40P01` 重试一次 | 原来单任务动作先锁任务行、后插回执；项目经理的动作持有 `lineage_events` 的 `SHARE ROW EXCLUSIVE` 去等这条任务行，两边互等，用户收到 500。全局统一「先表后行」就没有环，这是 [PostgreSQL 死锁说明](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS)推荐的做法；`ROW EXCLUSIVE` 和 `SHARE ROW EXCLUSIVE` 冲突、和自己不冲突（[冲突表](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-TABLES)），标注员之间照样并发，和多粒度锁里的意向锁同理（Gray、Lorie、Putzolu，*Granularity of Locks in a Large Shared Data Base*，VLDB 1975）。先锁行要提前知道每个动作会碰的全部行（还有项目、任务包、成员行），漏一个就回到死锁；回执挪出事务就不再原子；只重试等于把环藏起来。B8 PG 50 人照样达标。[锁](../datakeel/storage/action_locks.py)、[容量](CAPACITY.md)。 |
| 数负载前按（项目, 人）拿事务级 advisory lock，多人按用户 ID 排序；不持锁就不许数 | 锁这个人的用户行；每人一行负载计数、带条件更新；`SERIALIZABLE` 加重试；靠表锁 | 领取只锁自己拿到的那条任务，同一人的两个领取会同时看到「还没到上限」。[事务级 advisory lock](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) 不改表结构，提交或回滚自动释放，也不碰别的动作会改的行（用户行会被 `manage_users` 改写）；计数行要迁移，而且每种结束指派的路径都得维护它；`SERIALIZABLE` 在 50 人时会变成重试风暴。SQLite 写入本来就串行。「数之前断言已持锁」借鉴 Linux 的 `lockdep_assert_held`。[负载锁](../datakeel/storage/production_load_locks.py)。 |
| 模板属性字段：模板上一列带类型的字段（`boolean`、`enum`、`multi_enum`、带范围的 `number`、`text`），作用于每个形状或整条记录，保存和提交时校验 | [CVAT](https://docs.cvat.ai/docs/workspace/tasks-page/) 按标签定义属性（select、radio、checkbox、`min;max;step` 的 number、text；[`mutable`、`default_value`](https://docs.cvat.ai/docs/api_sdk/sdk/reference/models/attribute/)）；[Label Studio](https://labelstud.io/tags/choices) 控件标签的 `required`、`perRegion`、`whenLabelValue`；[Labelbox](https://docs.labelbox.com/reference/ontology) 的单选、多选、自由文本分类，可全局也可挂在工具下；直接写一份 [JSON Schema](https://json-schema.org/draft/2020-12/json-schema-validation) | 五种类型覆盖 CVAT 的输入类型（radio 和 select 都是 `enum`）和 Labelbox 的三类分类；`target` 对应 Label Studio 的 `perRegion`。中英文名跟界面语言走。封闭的类型列表能渲染成全键盘表单，报错能指到 key 和第几个形状；任意 JSON Schema（组合、条件、引用）做不到这一点，除非再引一个 schema 转表单的引擎，即新依赖。按标签生效（CVAT、`whenLabelValue`）和逐帧可变对单张图片暂时用不上，以后可作为可选过滤条件加上。模型草稿只查类型，因为必填项由人而不是模型补齐。[模型](../datakeel/core/production_attributes.py)、[保存校验](../datakeel/storage/production_catalog.py)。 |
| 每个项目锁定一个模板版本；签批 `upgrade_project_template` 只升一个项目，计划写明确切影响 | 项目跟着共用模板的当前修订走（原来的做法）；每个项目复制一份模板；模板分版本但所有项目一起升 | 改共用模板不能改变正在进行的工作的校验和表单，升一个项目也不能动到别的项目。版本按模板存一份、项目引用，和标签集的 `label_set_version` 一个做法。Label Studio 改标注配置时作用于整个项目，并先拿已有标注检查（[项目 API](https://api.labelstud.io/api-reference/api-reference/projects/update)）；CVAT 提示给有标注的任务改标签可能丢标注（[标签](https://docs.cvat.ai/docs/manual/basics/creating_an_annotation_task/)）。这里锁定是显式的，签批之前计划就列出每一条会不合格的已有标注：[版本](../datakeel/storage/production_template_versions.py)、[计划](../datakeel/storage/production_template_upgrade.py)。 |
| 云端预标注走 OpenAI 兼容的对话接口，用现有的 `httpx`；百炼 `qwen3.5-flash` 为实测默认 | 厂商 SDK（`openai`、`dashscope`）或 LiteLLM 这类路由；本地模型（不在范围内）；`qwen3.5-plus`、`qwen3.6-plus`、`qwen3.7-flash` | 一种协议就能接百炼和大多数 OpenAI 兼容服务，不加新依赖，离线测试用桩传输层。上面的实测里 flash 是能用的最便宜的，plus 价格 3 倍、F1 高约 15%，3.6-plus 更慢更贵、格式失败更多，3.7-flash 对本账号不开放。价格和 token 规则：[百炼价格](https://help.aliyun.com/zh/model-studio/model-pricing)、[图片 token](https://help.aliyun.com/zh/model-studio/vision)、[OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[下线机制](https://help.aliyun.com/zh/model-studio/model-depreciation)；0–1000 网格：[Qwen3-VL 定位示例](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/2d_grounding.ipynb)、[Qwen3-VL 技术报告](https://arxiv.org/abs/2511.21631)；公开定位分：[Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B)、[Qwen3.5-397B-A17B](https://huggingface.co/Qwen/Qwen3.5-397B-A17B)。[客户端](../datakeel/prelabel/client.py)、[运行](../datakeel/storage/production_cloud_prelabel.py)。 |
| 估价按指令长度和图片块算，输出 token 从先验向该模型实测调用靠拢，每张图发出前查预算 | 每张固定价；接入提供方分词器；只给最长回复的上限 | 百炼实测：1438 字节的指令是 460 token；回复从稀疏图的约 50 token 到 COCO 拥挤场景的 317–411 token，固定先验能差 2 倍；向实测均值靠拢（经验贝叶斯均值）就能修正，不用加分词器依赖。演练：冷启动整跑实际为估价的 0.90，热重跑 1.05。[估价](../datakeel/prelabel/estimate.py)。 |
| 准确率：同标签内一对一贪心匹配，IoU 高的先配，算 IoU 0.5 和 0.75 的 P/R/F1 | `pycocotools` COCOeval（按检测分数顺序，算各召回点的 AP）；匈牙利最优匹配；只看完全一致 | 草稿没有可靠的排序分数，驾驶舱要的是经理能据此行动的计数；COCO 按分数顺序给每个检测配最好的未匹配真值，先取最好的一对则不会让弱重叠抢在强重叠前面。数值与一份独立的 numpy 实现逐值相等。[COCO 检测评测](https://cocodataset.org/#detection-eval)、[`cocoeval.py`](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/cocoeval.py)、[匹配](../datakeel/annotation_qa/prelabel_match.py)。 |
| 对象置信度 = 模型自报概率与镜像图一致度（IoU）的均值 | 只用自报概率；只用镜像一致度；token 对数概率；多次采样 | 三个模型上都是合成的最能区分对错（AUROC 0.80–0.82，自报 0.71–0.77）。模型口头报的置信度偏高（[Xiong 等，ICLR 2024](https://arxiv.org/abs/2306.13063)）；翻转后的一致度就是测试时增强（[Wang 等，2019](https://arxiv.org/abs/1807.07356)）。坐标 token 的对数概率不是每个模型都给，也衡量不了框放得准不准；多次采样比一次镜像调用更贵。镜像可以关掉。[交叉核对](../datakeel/annotation_qa/prelabel_crosscheck.py)。 |
| 风险分 = 各规则固定权重的 noisy-OR，0.3 起为高风险 | 加权求和截到 1；取最大权重；用审核结果训练分类器 | Noisy-OR（Pearl，《Probabilistic Reasoning in Intelligent Systems》，1988，§4.3）把每条原因看成一个独立的出错概率：有界，多一条原因不会降，几条弱原因互相印证会累加——取最大值会忽略，求和截断会饱和。新项目没有审核结果可训；植入错误的测试里至少 80% 落在风险最高的五分之一。[风险分](../datakeel/annotation_qa/risk_scoring.py)。 |
| 新版本加既有标注导入 | 另造生产专用导出格式 | 发布和说明书继续读取既有合同。[定稿](../datakeel/storage/production_finalize.py)、[标注导入](../datakeel/storage/annotation_store.py)。 |

回归使用生成数据，覆盖两条流程、两栈抢单、独立只读 golden、精确迁移数、预测部分失败、只追加历史、乐观冲突与授权上限。容量验证在一万任务项目测量只读下一条和完整准备加执行的保存链。
