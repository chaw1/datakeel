# Controlled action outcomes / 受控动作结果

Every action starts with a frozen plan. Irreversible and outbound actions require explicit human approval bound to that plan. Execution consumes the approval once.

每个动作都先生成冻结计划。不可逆或外发动作必须获得绑定该计划的人工审批；执行时审批只能消费一次。

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
