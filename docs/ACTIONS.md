# Controlled action outcomes / 受控动作结果

Every action starts with a frozen plan. Irreversible, outbound and data standard governance actions require explicit human approval bound to that plan. Execution consumes the approval once.

每个动作都先生成冻结计划。不可逆、外发或数据标准治理动作必须获得绑定该计划的人工审批；执行时审批只能消费一次。

| Attempt / 执行条件 | Run status / 运行状态 | `reason` |
| --- | --- | --- |
| Approval missing / 尚未审批 | `DENIED` | `AuthorizationError: Action requires explicit human approval` |
| Approval rejected / 审批被拒 | `DENIED` | `ConflictError: Human approval was rejected` |
| Plan already executed / 计划已执行，审批已消费 | `DENIED` | `ConflictError: Action plan was already executed; approval was consumed` |
| Approval consumed by a failed execution / 执行失败但审批已消费 | `DENIED` | `ConflictError: Human approval was already consumed` |

`GET /api/actions/runs` exposes the persisted `reason`. The existing `error` field carries the same explanation for compatibility. Denied attempts retain an attributed `FAIL` lineage receipt with no business outputs; the action history displays a red **Denied / 拒绝执行** badge and the reason. Execution or worker failures remain `FAILED`.

`GET /api/actions/runs` 返回持久化的 `reason`；原有 `error` 字段保留相同解释以兼容旧客户端。拒绝执行仍产生带操作者信息的 `FAIL` 血缘回执，业务输出为空；动作记录页显示红色「拒绝执行」徽标和原因。执行或工作进程错误仍为 `FAILED`。

The first unauthorized `POST /api/actions/{plan_id}/execute` retains its HTTP 403 (missing approval) or 409 (rejected or consumed approval) response. Repeating the same explicit `operation_id` returns its original run, including a denial, without another mutation or audit entry. A bad plan digest or caller identity is rejected before a run is created. To retry after a recorded denied operation, prepare a new plan and obtain its required approval.

首次未授权执行仍返回 HTTP 403（未审批）或 409（审批被拒或已消费）。同一显式 `operation_id` 重放返回原运行记录，包括拒绝记录，不再变更数据或增加审计。错误的计划摘要或执行人身份在创建运行记录前被拒。对已记录拒绝结果的操作再次尝试时，应重新生成计划并完成所需审批。

## Resuming a paused Agent / 恢复暂停的 Agent

The Agent persists a synchronous checkpoint when a plan requires approval. A process restart does not discard this pause. Reversible actions execute automatically when approval is not required and the conversation is not in dry-run mode. Standard and code-list changes, restores and mapping confirmations always require human approval.

Agent 在计划需要审批时同步保存暂停 checkpoint，进程重启不会丢失该断点。可逆动作在不要求签批且非 dry-run 会话时自动执行。标准和码表变更、历史恢复及映射确认始终需要人工审批。

After approving the plan through the existing approval endpoint or sheet, send `POST /api/agent/conversations/{id}/resume` with the body below. Use a unique key for this resume attempt; replaying the same completed key returns the stored response. The response uses the existing SSE event format and acquires its own conversation response lease. It does not append a user message.

先通过现有审批接口或签批单完成签批，再以以下请求体调用 `POST /api/agent/conversations/{id}/resume`。每次恢复尝试使用独立幂等键；已完成的相同键重放返回已存响应。接口沿用既有 SSE 事件格式，获取独立会话响应 lease，不追加用户消息。

The event types remain `text`, `tool_call`, `tool_result`, `plan`, `receipt`, `stopped` and `done`, with the same fields as message responses. Conversation creation, reads, messages, recovery and recovery audit all use the `/api/agent/conversations` prefix.

事件类型仍为 `text`、`tool_call`、`tool_result`、`plan`、`receipt`、`stopped` 和 `done`，字段与发送消息的响应一致。会话创建、查询、消息、恢复及恢复审计统一使用 `/api/agent/conversations` 前缀。

```json
{
  "plan_id": "the-pending-plan-id",
  "idempotency_key": "resume-request-1"
}
```

Execution follows these checks in order:

1. The conversation must still have this plan's approval pause or its unfinished execution checkpoint.
2. The database approval must be accepted, unexpired, bound to the current plan digest and signed by the plan's actor. The resume body is never an authorization record.
3. If the plan already has an action run whose status is not `DENIED`, return its receipt. This includes a plan executed from the existing approval sheet before resuming the conversation. Earlier denied attempts do not count as execution.
4. Otherwise execute with the plan's own `operation_id`, then continue the graph with the action result in workspace facts. Do not append another tool result for the original call.

恢复依次确认本会话仍保留该计划的审批暂停或尚未完成的执行断点、核对数据库真实签批的接受状态/有效期/摘要/计划 actor，再复用状态不是 `DENIED` 的已有动作 run 的回执；历史拒绝记录不代表已经执行，没有这样的 run 时才使用计划固有 `operation_id` 执行。结果经 workspace facts 交给模型，不为原工具调用再写一条结果。图的 resume 载荷不能单独构成授权，UI 已执行的计划也不会再次执行。

Missing approval, a mismatched digest, an expired approval, a different approval actor, or a plan outside this conversation rejects resume and leaves an attributed audit record available from `GET /api/agent/conversations/{id}/audit`. These checks run before action dispatch, so an invalid resume cannot rely on the execute endpoint to create its evidence. A new user message invalidates the old pause and records the invalidation before continuing the conversation.

无签批、摘要不符、签批已过期、签批 actor 与计划 actor 不同、计划不属于本会话，都会拒绝恢复并留下审计，可通过 `GET /api/agent/conversations/{id}/audit` 查询。校验发生在动作派发前，拒绝证据不依赖执行接口的二次防线。暂停期间的新消息会先使旧断点作废并记录审计，再继续正常对话。

Each audit item exposes `id`, `conversation_id`, `plan_id`, `kind`, `reason` and UTC `created_at`. `kind` is `RESUME_DENIED` for a rejected request, `RESUME_AUTHORIZED` after approval validation, or `INTERRUPT_INVALIDATED` when a new message replaces a pause. Authorization is recorded before execution; it does not by itself report a successful action.

每条审计包含 `id`、`conversation_id`、`plan_id`、`kind`、`reason` 和 UTC `created_at`。`kind` 分别为拒绝恢复的 `RESUME_DENIED`、签批校验通过的 `RESUME_AUTHORIZED`、新消息替换暂停的 `INTERRUPT_INVALIDATED`。授权审计先于执行写入，不代表动作已成功。

Checkpoints contain only execution state. Conversation messages, tool invocations, model traces, budgets, approvals and action receipts remain in their existing tables. Removing a checkpoint prevents continuation from that checkpoint but does not remove the audit history. Tool dispatch is idempotent by `tool_call_id`; recovery after an action commits but before its checkpoint is written reuses the original tool invocation and action receipt.

checkpoint 只保存执行状态；消息、工具调用、trace、预算、签批和动作回执仍在原有表中。删除 checkpoint 会失去该断点的续跑能力，但不会删除审计。工具派发按 `tool_call_id` 幂等；动作已提交、checkpoint 尚未写入时发生进程故障，恢复后仍复用原工具调用记录和动作回执。
