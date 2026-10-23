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

Keep generated fixtures isolated and preserve the existing action authorization chain. Contracts do not create new tools or broaden an actor's permissions.

使用独立生成样例，保留既有动作授权链。工作流合同不创建新工具，也不扩大执行人的权限。
