# Deterministic workflows / 确定性工作流

Workflow contracts describe a bounded sequence of registered reads and controlled actions. Definitions live in [`contracts/workflows/`](../contracts/workflows/); they contain no executable expressions or model-generated steps. Dataset import remains the existing dataset API's responsibility.

工作流合同把已注册的只读函数和受控动作组成有界步骤，定义放在 `contracts/workflows/`。合同不执行表达式源码，也不包含自由 Agent 子步骤。数据集仍通过既有数据集接口导入。

## Inspect and validate / 查看与校验

```bash
uv run datakeel workflow list
uv run datakeel workflow validate contracts/workflows/dataset-health.yaml
```

`list` loads and validates every bundled YAML. `validate` checks a single file without running it and exits nonzero on failure. Both the source checkout and installed wheel use the same contracts.

`list` 加载并校验全部内置 YAML；`validate` 只校验指定文件，不执行工作流，有错误时退出码非零。源码安装和 wheel 安装使用同一份合同。

| ID | Definition / 定义 |
| --- | --- |
| `dataset-health` | Process an imported dataset, wait for the worker, inspect quality/report/evidence, then branch at score 80. / 处理已导入的数据集，等待 worker，读取质量、报告与证据，以 80 分为界给出结论。 |
| `metric-change` | Read the current definition and answer, inspect impact, apply a reversible override, then ask the same question and compare rows. / 先读当前定义和改前答案，查看影响面，再自动执行可逆修改，重问同一问题并比较 rows。 |
| `low-quality-cleanup` | Find low-quality files, quarantine them, pause for deletion approval, then inspect quality. An empty selection ends without an action. / 查找低质文件并自动隔离，删除前暂停签批，随后复查质量；没有命中时直接结束。 |

## YAML reference / YAML 参考

A complete read-only definition:

下面是一份完整的只读定义：

```yaml
id: quality-summary
name: Quality summary / 质量摘要
description: Read the current score of an imported dataset.
inputs:
  dataset_id:
    type: string
    description: Imported dataset identifier / 已导入的数据集 ID
    required: true
triggers:
  keywords:
    - [quality summary]
    - [质量摘要]
  classification_keywords: [summary, 摘要]
  threshold: 1
  margin: 1
entry: quality
steps:
  - id: quality
    type: tool
    tool: get_quality
    arguments:
      dataset_id: ${inputs.dataset_id}
    next: result
  - id: result
    type: output
    value:
      total: ${steps.quality.data.total}
      message: "Quality score: ${steps.quality.data.total}"
```

Definitions require `id`, `name`, `description`, `inputs`, `triggers`, `entry` and `steps`. Workflow and step IDs start with a lowercase letter and contain at most 64 lowercase letters, digits, `_` or `-`. There are 1–100 steps. Unknown fields are rejected. `entry` and every outgoing edge must name a declared step, and the whole graph must be acyclic, including unreachable steps.

定义必须包含上述七个顶层字段。工作流及步骤 ID 以小写字母开头，最多 64 个小写字母、数字、下划线或连字符；步骤数为 1–100。未知字段会被拒绝。`entry` 和所有后继边必须指向已声明步骤，整个图不得有环，即使环不在入口可达路径上也不允许。

### Inputs / 输入

Each input declares `type`: `string`, `number`, `integer`, `boolean`, `object` or `array`. Optional `description` defaults to an empty string, `required` to `true`, and `default` to `null`. A non-null default supplies an omitted value. Required inputs without a supplied value or default are rejected; unknown keys and wrong types are rejected too. Booleans do not count as numeric inputs.

每个输入声明上述六种类型之一。`description` 默认空字符串，`required` 默认 `true`，`default` 默认 `null`。非空默认值用于填补省略的输入。必填项既未提供也无默认值时拒绝运行；未知键及类型不符同样拒绝。布尔值不算数字。

The metric workflow defaults to `retail_revenue`, an override of `measure.column` to `ecommerce/main/orders/list_amount`, question `上个季度华东区零售额是多少`, and fixed `reference_instant: 2026-10-01T00:00:00Z`. Keep the reference instant explicit when comparing answers.

指标工作流默认使用 `retail_revenue`，把 `measure.column` 改为 `ecommerce/main/orders/list_amount`，前后都问「上个季度华东区零售额是多少」，固定参考时刻为 `2026-10-01T00:00:00Z`。对比答案时应显式指定参考时刻。

### Step types / 步骤类型

| `type` | Fields / 字段 | Behavior / 行为 |
| --- | --- | --- |
| `tool` | `id`, `tool`, `arguments`, `next` | Call a registered read, or prepare and automatically execute a reversible action. / 调用已注册只读函数，或准备并自动执行可逆动作。 |
| `wait` | `id`, `task_id`, `next`, optional `timeout_seconds`, `poll_interval` | Poll one task until completion or failure. Defaults: 60 seconds and 0.25 seconds; maxima: 3600 and 60. Both must be positive. / 轮询一个任务直到完成或失败；超时默认 60 秒、间隔默认 0.25 秒，上限分别为 3600 和 60 秒，均须为正数。 |
| `branch` | `id`, `ref`, `op`, `value`, `then`, `otherwise` | Compare one complete reference and select an explicit edge. / 对完整引用进行比较，选择已声明的后继边。 |
| `approval` | `id`, `action`, `arguments`, `next` | Only an irreversible controlled action is allowed. Preparation, approval pause and execution remain separate. / 仅用于不可逆受控动作；准备、暂停等签批、执行相互分离。 |
| `output` | `id`, `value` | Resolve a JSON template and end this path. / 解析 JSON 模板并结束当前路径。 |

A `run_pipeline` tool step only queues work. Its following `wait` step references `${steps.pipeline.task_id}`. The worker must run separately when using `datakeel api`; `datakeel demo` supervises both roles.

`run_pipeline` 工具步只负责排队，后面的 `wait` 步通过 `${steps.pipeline.task_id}` 读取任务 ID。单独使用 `datakeel api` 时还须启动 worker；`datakeel demo` 会同时管理两者。

Branches allow only `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, and `in`. Ordered comparisons require numbers; `in` requires an array on the right. There is no Python, JavaScript, SQL, or general expression evaluation.

分支操作符仅限上述白名单；大小比较要求数值，`in` 的右侧要求数组。不执行 Python、JavaScript、SQL 或任意表达式。

```yaml
- id: score
  type: branch
  ref: ${steps.quality.data.total}
  op: gte
  value: 80
  then: healthy
  otherwise: review
```

### References and pure functions / 引用与纯函数

`${inputs.dataset_id}` reads an input; `${steps.quality.data.total}` reads an earlier output. Dot-separated object keys and zero-based array indexes are supported. A whole-string reference preserves its JSON type. A reference inside other text renders as text; non-string values use JSON. References must name an earlier step executed on **every** path to the current step. A branch-only output cannot be read after two branches merge unless it exists on both paths.

`${inputs.dataset_id}` 读取输入，`${steps.quality.data.total}` 读取前序输出。支持点分隔的对象键及从零开始的数组下标。整个字符串只有一个引用时保留原 JSON 类型；嵌在文字中时转成文本，非字符串值使用 JSON。被引用步骤必须在到达当前步骤的**每一条**路径上都已执行，不能在分支合并后读取仅其中一条路径才有的输出。

Read tools return the complete `FunctionResult`, so values are below `.data`. Actions return `ActionRun`, so fields such as `.task_id` are directly below the step. Known output schemas are checked during loading; dynamic fields are resolved when their step runs.

只读函数输出完整 `FunctionResult`，业务值位于 `.data` 下；动作输出 `ActionRun`，因此 `.task_id` 等字段直接位于步骤输出下。已知输出 schema 的字段在加载时检查，动态字段在执行该步骤时解析。

Each pure function is an object with exactly one reserved key and a two-element argument array:

每个纯函数是只含一个保留键的对象，参数必须为两个元素的数组：

| Function / 函数 | Result / 结果 |
| --- | --- |
| `{"$merge": [base, override]}` | Deeply merge two objects; the override wins, arrays are replaced. / 深合并两个对象，后者覆盖前者，数组整体替换。 |
| `{"$equals": [left, right]}` | Compare JSON values for equality. / 比较 JSON 值是否相等。 |
| `{"$rows_equal": [before, after]}` | Compare two row arrays, preserving order. / 比较两个 rows 数组，顺序参与比较。 |
| `{"$pluck": [items, "asset_ref.asset_id"]}` | Extract a literal property path from every array element. / 从数组每个元素提取指定的固定属性路径。 |

```yaml
definition:
  $merge:
    - ${steps.current.data.definition}
    - ${inputs.override}
```

This preserves the full metric definition while changing only the requested nested fields. Templates can nest references and these pure functions. Unknown `$` functions, extra function keys, malformed references and wrong argument counts are rejected.

这样可以保留完整指标定义，只覆盖指定嵌套字段。模板允许嵌套引用和上述纯函数；未知 `$` 函数、额外函数键、引用语法错误及参数数量错误都会被拒绝。

### Trigger vocabulary / 触发词声明

`triggers.keywords` is a list of keyword groups. A group matches when all its phrases occur in the normalized message; each matching group contributes one point. The score is the count of matched groups. Phrase matching is case-insensitive and normalizes runs of whitespace. A candidate reaches its `threshold` when `score >= threshold`; an unambiguous winner must also lead the second score by at least its `margin`. Defaults and bundled values are `threshold: 1`, `margin: 1`. `classification_keywords` provides additional vocabulary for resolving close candidates.

`triggers.keywords` 是关键词组列表；一组内的短语全部命中才得一分，分数是命中组数之和。匹配忽略大小写并归一连续空白。候选分数满足 `score >= threshold` 才过阈值，直接命中还须领先第二名至少 `margin` 分。默认值及内置值均为 `threshold: 1`、`margin: 1`。`classification_keywords` 提供分差不足时使用的额外词汇。

## Invalid definitions / 错误示例

Errors identify the file and either a schema field or a named step. For example, replacing `tool: get_quality` in the example with `tool: missing_tool` reports:

错误包含文件名及 schema 字段或步骤位置。例如，将示例中的工具改为未注册的 `missing_tool` 会报告：

```text
quality-summary.yaml:steps[quality]: unknown tool: missing_tool
```

| Invalid change / 非法改动 | Rejection / 拒绝原因 |
| --- | --- |
| Set `quality.next: quality` / 指回自身 | `cycle detected` |
| Use `${inputs.missing}` / 引用未声明输入 | `unknown input: missing` |
| Use `${steps.missing.data.total}` / 引用不存在步骤 | `unknown step: missing` |
| Use `${steps.quality.data.missing}` / 引用已知 schema 中不存在的字段 | `unknown output reference` |
| Set `tool: delete_files` / 工具步直接删除 | `irreversible action requires an approval step` |
| Set approval `action: quarantine_files` / 可逆隔离放签批步 | `approval requires an irreversible action` |
| Set branch `op: eval` / 使用非白名单操作符 | Schema error at the branch's `op` / 指向分支 `op` 的 schema 错误 |
| Omit required `dataset_id` at run time / 运行时缺少必填输入 | `inputs.dataset_id: required input is missing` |

## Add a workflow / 添加工作流

1. Copy a small existing definition into `contracts/workflows/<id>.yaml`. Declare typed inputs and explicit defaults; reuse registered functions and actions. / 复制一份小型定义，声明输入类型及默认值，复用已注册函数和动作。
2. Connect every path to an `output` step. Use `approval` only for irreversible actions and `wait` after queued work. / 每条路径以 `output` 结束；不可逆动作使用 `approval`，排队任务之后使用 `wait`。
3. Add Chinese and English keyword groups that describe the complete workflow, including enough intent to distinguish single-step requests. / 编写描述完整工作流的中英文关键词组，避免把单步请求误认为多步工作流。
4. Run the validation command, add isolated regression cases for success, branches and failure, then run `make check`. / 运行校验命令，添加成功、分支及失败的隔离回归测试，再运行 `make check`。

Restart the API process to refresh cached intent definitions after changing workflow triggers.

修改工作流触发词后，重启 API 进程以刷新缓存的意图定义。

Keep generated fixtures isolated and preserve the existing action authorization chain. Contracts do not create new tools or broaden an actor's permissions.

使用独立生成样例，保留既有动作授权链。工作流合同不创建新工具，也不扩大执行人的权限。

## Run and resume / 运行与恢复

Open **Workflows / 工作流**, choose a definition, and review the generated input form. Starting is always explicit. The saved run page shows each step's status, output summary and failure reason. A suggestion in Agent opens this form and only prefills the conversation's dataset; it does not start a run.

打开「工作流」，选择定义并核对按 schema 生成的输入表单，再显式发起运行。运行页展示各步骤状态、输出摘要及失败原因。Agent 的工作流建议只打开表单，预填会话中已选的数据集，不自动运行。

For deletion, reversible quarantine runs first. The workflow then pauses with a frozen plan. Open **Review approval / 查看签批**, approve the plan, return to the run, and click **Continue after approval / 签批后继续**. Approval alone does not resume a workflow. If the approval page has already executed the action, continuation reuses its receipt. A resume request cannot grant approval by itself.

清理流程先自动执行可逆隔离，再携冻结计划暂停。点击「查看签批」审阅并签批，随后返回运行页点击「签批后继续」。签批本身不会自动续跑；若审批页已经执行动作，续跑复用原回执。恢复请求本身不授予签批权限。

CLI commands use the same database and object-store settings as API and worker:

CLI 使用与 API、worker 一致的数据库和对象存储配置：

```bash
uv run datakeel workflow run dataset-health --input dataset_id=DATASET_ID
uv run datakeel workflow run metric-change --input 'override={"measure":{"column":"ecommerce/main/orders/list_amount"}}'
uv run datakeel workflow run low-quality-cleanup --input dataset_id=DATASET_ID --input quality_max=60
uv run datakeel workflow resume RUN_ID --plan PLAN_ID
```

Replace the uppercase placeholders with actual IDs. `--input k=v` accepts JSON numbers, booleans, arrays and objects; other values stay strings. Repeated keys are rejected. `--idempotency-key KEY` makes an intentional retry use the original request identity. On pause, the CLI prints the plan ID, approval URL and resume command.

将大写占位符替换为真实 ID。`--input k=v` 支持 JSON 数字、布尔、数组及对象，其余保留为字符串；不允许重复键。使用 `--idempotency-key KEY` 可在主动重试时保持原请求身份。暂停时 CLI 输出计划 ID、审批地址及恢复命令。

If a task times out, inspect its reason and confirm a worker is running with `uv run datakeel worker`. Failures do not retry or continue to later steps. A disconnected live run becomes `INTERRUPTED`; after process restart, unfinished runs outside approval pause are also interrupted. Reload the saved record to inspect it. Only approval pauses can resume; an interrupted run cannot restart from its middle.

任务超时后先查看原因，并确认已运行 `uv run datakeel worker`。失败不会重试，也不会执行后续步骤。运行中断开连接会标为 `INTERRUPTED`；进程重启时，未处于签批暂停的未完成运行也会中断。重新加载运行记录即可检查状态；只有签批暂停支持恢复，普通中断不支持从中途续跑。

## HTTP and SSE / HTTP 与 SSE

All workflow resources share `/api/workflows`:

全部工作流资源统一使用 `/api/workflows` 前缀：

| Method / 方法 | Path / 路径 | Result / 结果 |
| --- | --- | --- |
| `GET` | `/api/workflows` | Validated definitions and input schemas / 定义及输入 schema |
| `GET` | `/api/workflows/{workflow_id}` | One definition / 单份定义 |
| `POST` | `/api/workflows/{workflow_id}/runs` | Start or replay a run as SSE / 发起或重放运行，返回 SSE |
| `GET` | `/api/workflows/runs` | Run history / 运行记录 |
| `GET` | `/api/workflows/runs/{run_id}` | Durable run and step timeline / 持久运行及步骤时间线 |
| `POST` | `/api/workflows/runs/{run_id}/resume` | Explicit signed continuation as SSE / 显式签批恢复，返回 SSE |
| `GET` | `/api/workflows/runs/{run_id}/audit` | Resume authorization and interruption audit / 恢复授权及中断审计 |

Start body / 发起请求体：

```json
{"inputs":{"dataset_id":"DATASET_ID","quality_max":60},"idempotency_key":"cleanup-demo-1"}
```

Resume body / 恢复请求体：

```json
{"plan_id":"PLAN_ID","idempotency_key":"cleanup-resume-1"}
```

A start requires `idempotency_key`; replaying the same key returns the same run instead of creating another. Recovery also has a separate key, and concurrent recovery of one run is serialized. Keys do not replace the database's signed approval checks.

发起请求必须包含 `idempotency_key`，相同键重放返回同一个运行，不重复创建。恢复也有独立的幂等键，同一运行的并发恢复会串行化。幂等键不替代数据库内的真实签批校验。

Each SSE frame has `id`, `event` and a JSON `data` payload. Event names are `run`, `step`, and `done`. Every payload contains `{id, event, run, step_id}`; `step_id` can be null. `run` is a complete snapshot with `id`, `workflow_id`, `status`, `inputs`, `steps`, `pending_plan_id`, `error`, `created_at`, and `updated_at`. A step includes `id`, `type`, `status`, `output`, `error`, `plan_id`, `started_at`, and `finished_at`.

每个 SSE 帧具有 `id`、`event` 和 JSON 格式的 `data`。事件名为 `run`、`step`、`done`，载荷统一为 `{id, event, run, step_id}`，其中 `step_id` 可为空。`run` 包含完整运行快照及上述字段；每个步骤也保存完整状态、输出、错误及时间。

Run states: `PENDING`, `RUNNING`, `PAUSED`, `SUCCEEDED`, `FAILED`, `INTERRUPTED`. Step states: `PENDING`, `RUNNING`, `PAUSED`, `SUCCEEDED`, `SKIPPED`, `FAILED`. A `done` frame marks the end of this request, including a pause or failure; inspect `run.status` to determine the outcome. A stream ending without `done` is not proof of success.

运行状态和步骤状态分别如上。`done` 只表示本次请求结束，暂停和失败也会发送它；应查看 `run.status` 判断结果。没有 `done` 就结束的流不能当作成功。

## Intent and model routing / 意图与模型路由

Below-threshold messages go to the free Agent. A confident keyword winner yields a suggestion directly; close candidates use a separate classifier. Excluded phrases in `triggers.excluded_keywords` set that workflow's keyword score to zero. The fake classifier reads only the contract's classification vocabulary and can abstain. Classifier failure or exhausted classification budget falls back to the free Agent. Normal Agent calls remain subject to the same remaining conversation/day budget; an exhausted shared budget still produces the normal budget stop. Classification reserves and settles its own budget and trace, and does not consume conversation turns.

未过阈值的消息交给自由 Agent；明确的关键词优胜者直接给出建议，分差不足时使用独立分类器。命中 `triggers.excluded_keywords` 排除短语时，对应工作流关键词得分归零。假分类器只读合同声明的分类词汇，也可以弃权。分类失败或分类预算不足时回到自由 Agent。正常 Agent 调用仍受同一会话/日预算的剩余额度约束；共享预算耗尽时仍按原有预算机制停止。分类调用独立预留、结算预算和记录 trace，不占会话轮数。

Agent SSE adds `route` before `done`: `route` contains `workflow_id`, `score`, `reason`, `branch` (`keyword`, `classifier`, `free_agent`), scored `candidates`, and `inputs.dataset_id`. Only a matched workflow emits a separate `route` event; free-Agent decisions are attached to `done.route`. Decisions remain in the conversation's saved events and can also be queried at `GET /api/agent/conversations/{id}/routes`. Resume emits no intent route.

Agent 在 `done` 前新增 `route` 事件，字段如上；仅命中工作流时单独发送 `route`，自由 Agent 决策附在 `done.route`。决策保存在会话事件中，也可通过 `GET /api/agent/conversations/{id}/routes` 查询。恢复不进行意图路由。

Model configuration lives in [`contracts/routing/models.yaml`](../contracts/routing/models.yaml). `DATAKEEL_MODEL_ROUTING_FILE` selects another file. Each provider declares `tiers.simple`, `tiers.multi_step`, `tiers.high_risk` and a `fallbacks` mapping from one model name to the next. The bundled configuration has no backup links. All referenced models must have same-provider prices in `contracts/model-prices.yaml`.

模型配置位于上述 YAML，可用 `DATAKEEL_MODEL_ROUTING_FILE` 指向另一份配置。每个 provider 声明三个档位以及主模型到下一模型的 `fallbacks` 映射；默认配置不启用备用链。每个引用模型都必须在价格表中具有同 provider 的价格。

Before each call, loaded controlled actions or an already produced plan select `high_risk`; otherwise an earlier tool result in this response selects `multi_step`; otherwise the tier is `simple`. An explicit conversation model stays pinned. Only `model: auto` selects by tier. Fake conversations always use their configured model.

每次调用前，已加载受控动作或本轮已产生计划时选 `high_risk`；否则，本轮已产生工具结果时选 `multi_step`；其余选 `simple`。会话显式指定的模型优先，只有 `model: auto` 按档位选择；fake 会话始终使用会话模型。

Timeout, HTTP 429 and HTTP 5xx may advance a configured same-provider chain, at most two backups after the primary. HTTP 400 and 401 do not switch. Each attempt independently reserves/settles budget and writes a trace. The existing `done` event includes `model_routes`, an ordered list of attempts with `tier`, `model`, `pinned`, `fallback_reason` and `attempt`; it persists with the conversation and appears in Agent.

超时、HTTP 429 和 5xx 可沿同 provider 的备用链切换，主模型外最多两个备用；400 和 401 不切换。每次尝试独立预留、结算预算并写 trace。既有 `done` 事件增加 `model_routes`，按调用顺序记录每次尝试的档位、模型、固定模型标记、切换理由及尝试序号，持久保存在会话中并显示在 Agent 页。

```bash
uv run datakeel routing validate
uv run datakeel routing validate path/to/models.yaml
uv run datakeel eval-route
uv run datakeel eval-route --json
```

Validation runs at startup too. Unknown tiers, missing providers or models, unpriced models, cross-provider chains, cycles and more than two backups are errors with locations; invalid custom configuration never silently falls back to defaults. The offline evaluation reports accuracy and workflow/branch/tier confusion matrices using frozen cases and no provider calls.

启动时也会校验。未知档位、缺少 provider 或模型、无价格模型、跨 provider 链、环及超过两个备用均报带位置的错误；非法自定义配置不会静默退回默认。离线评测使用冻结用例，报告准确率及工作流、分支、档位混淆矩阵，不调用真实 provider。
