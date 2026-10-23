# Delegation and memory / 委派与记忆

The Agent uses the same controlled tools and human approval policy as other interfaces. The default `fake-demo` provider is local and deterministic. Try `Delegate a catalog review` / `委派目录分析` to run a real child conversation with scripted local responses.

Agent 与其他入口共用受控工具及人工签批规则。默认 `fake-demo` 完全在本机运行；输入 `委派目录分析` 可观察独立子会话和真实工具调用。

## Specialist definitions / 子 Agent 定义

Definitions live in `contracts/agents/*.yaml` and are bundled in the wheel. For example:

定义位于 `contracts/agents/*.yaml`，随 wheel 打包。例如：

```yaml
name: catalog-analyst
description: Inspect datasets, lineage, metrics and downstream impact.
max_turns: 4
tools:
  - list_datasets
  - search_files
  - get_lineage
  - list_metrics
  - explain_metric
  - impact_of
  - delegate_agent
```

Names must be unique lowercase identifiers. `description` and `tools` are required; `max_turns` defaults to 4 and accepts 1–4. Unknown fields, unknown tools, irreversible actions and duplicate names are rejected with file/field locations. `tool_search` is automatically available but exposes only the specialist's declared tools. `evidence-reviewer` may prepare reversible `decide_assertions`; `metric-manager` may prepare `update_metric` and `rollback_metric`. Approval and execution controls are never model-callable.

名字必须唯一且为小写标识符；说明和工具范围必填，轮数默认 4、范围 1–4。未知字段、未知工具、不可逆动作及重名均在加载时拒绝，并指出文件和字段。子 Agent 可用 `tool_search`，但只能发现其声明范围内的工具。证据审核可准备可逆的断言审核；指标管理可准备指标修改和回滚。模型不能自行签批或调用执行控制接口。

The main Agent discovers `delegate_agent` through `tool_search`, then calls it with `{"agent":"catalog-analyst","task":"Inspect available datasets"}`. Children have separate histories, checkpoint threads and canaries. Child model calls reserve and settle against the root conversation budget, without incrementing root turns. Replaying a completed `tool_call_id` returns the stored conclusion without new calls or charges. Nested delegation cannot widen its parent's tool scope.

主 Agent 先发现委派工具，再传入子 Agent 名和任务。子会话的历史、checkpoint 和 canary 独立，模型用量统一记入根会话预算，不增加主会话轮数。相同工具调用 ID 重放只返回缓存结论，不新增模型调用或扣费。嵌套委派的权限不能超出父级范围。

`DATAKEEL_DELEGATION_MAX_DEPTH` defaults to 2 (main is depth 0); `DATAKEEL_DELEGATION_MAX_PARALLEL` defaults to 3 requests in one model response. Execution is serial. Excess requests fail as tool results; a child budget or canary stop stops the parent response. Children never handle irreversible actions or nested approval pauses.

深度默认最多到第 2 层，主 Agent 为第 0 层；同一模型回复默认最多委派 3 项任务，始终串行。两个设置均经统一配置校验。超过限制返回工具错误；子会话预算或 canary 停止向父级传播。不可逆动作只能由主会话准备并等待人工签批。

## Prompt safety / 提示词安全

A private per-conversation sentinel follows `core_tools` in its own volatile `canary` segment. Instructions and core schemas retain the shared stable prefix. Before saving any model reply, the runtime checks text and tool parameters for the full sentinel or 16 consecutive random characters, ignoring case and whitespace. It also checks child conclusions and ancestor sentinels. A match emits the existing `stopped` event with `stop_reason=canary_leak`, suppresses the entire reply and tool execution, and writes a content-free `CANARY_LEAK` audit. The sentinel is absent from transcripts, events, checkpoint state and configuration.

每个会话的私有标记放在常驻工具之后的独立易变段，不改变共享稳定前缀。模型回复保存前检查文本、工具参数、子 Agent 结论及祖先标记；完整标记或随机部分连续 16 位泄漏即停止。停止事件只含安全原因，不保存或显示泄漏回复，也不执行其中工具。

Every tool result enters the prompt as compact JSON `["data-only", tool_name, data]`; the transcript retains its original content. Retrieved memories use the same data-only designation. These boundaries reduce instruction confusion but do not prove model obedience. Injected data can still induce reversible actions, which retain audit and rollback paths. Irreversible actions always require human approval. Canary detection is an additional output guard, not a complete injection detector.

工具结果与记忆在提示词中标为数据；工具原始结果仍留在历史中。模型仍可能受注入诱导执行可逆动作，此类动作有审计与回滚；不可逆动作必须人工签批。Canary 是输出泄漏防线，不能证明所有注入都被识别。

## Explicit memory / 显式记忆

Use the Memory page or `POST /api/agent/memories` to create a global entry (`dataset_id: null`) or a dataset entry. The Agent may discover `write_memory` with `tool_search`. Writes redact email addresses and phone numbers before persistence. There is no automatic conversation extraction. Sources link to their conversations; the page supports dataset filtering and confirmed deletion.

在「记忆」页或 API 显式添加全局/数据集条目，也可让 Agent 发现 `write_memory` 工具后写入。持久化前统一脱敏邮箱及电话，不自动从对话抽取记忆。界面显示来源会话、作用域、创建时间、当前强度与最近使用时间，支持筛选和确认删除。

| Parameter / 参数 | Behavior / 行为 |
| --- | --- |
| Tokenization / 分词 | Chinese character bigrams; lowercase English words / 中文字二元组、英文小写单词 |
| Relevance / 相关度 | BM25, k1=1.2, b=0.75; at least 2 distinct overlapping tokens and positive score / 至少两个不同词元重合且分数为正 |
| Ranking / 排序 | BM25 × current strength; last use descending, never-used last; then ID ascending / 分数降序、最近使用降序、ID 升序 |
| Selection / 取用 | Global + current dataset; top 3; at most 1200 estimated tokens including segment overhead / 全局加当前数据集，最多三条，含段开销不超过 1200 字节估算词元 |
| Strength / 强度 | New=1; `max(0.05, s0 * 2^(-elapsed_days/14))`; first actual use per user question adds 0.5, cap 3 / 初始 1，半衰期默认 14 天，每次用户提问首次实际取用加 0.5、上限 3 |
| Consolidation / 凝练 | Over 200 active entries: normalized exact duplicates, then character-bigram Jaccard ≥0.8 within one scope; keep strongest and union provenance; archive weakest excess / 同作用域合并，保留最强条目及来源并集，再归档最弱超额条目 |

Whole trailing entries are removed to fit the prompt cap; text is never cut mid-entry. No match means no `memory` segment. Selection reads current storage before each model call. Each fallback attempt re-reads current memory before reservation. A snapshot already sent to an in-flight provider cannot be recalled; later attempts omit deleted entries.

段超限时从末尾整条移除，不截断内容；没有匹配就不生成记忆段。每次调用模型前重新读取存储，每次备用尝试也重新检索；已发给进行中调用的快照无法撤回，但后续尝试不再发送已删条目。

Each memory gains strength only after its first actual provider attempt in one user question, even if that attempt fails. Multiple model calls, fallback attempts and delegated children share this limit. Every actual use still updates `last_used_at` and the current response's used memory IDs; only the first use changes `reinforced_at`. A new user message starts a new allowance. Approval resume adds no user message and remains in the original question, including after a process restart or checkpoint recovery. A budget rejection before a provider attempt does not count as use. The service exposes injectable clocks and policy defaults for deterministic tests.

每次用户提问中，每条记忆只在首次实际模型尝试后增强，即使该尝试失败也计入。多次模型调用、备用模型和委派子 Agent 共用这一限制。每次实际取用仍更新 `last_used_at` 和本次响应的取用记忆 ID；仅首次增强更新 `reinforced_at`。下一条用户消息重新允许增强；审批恢复不新增用户消息，仍属于原提问，进程重启或 checkpoint 恢复也不重置。预算在模型尝试前拒绝不算取用。服务支持注入时钟及策略参数，便于确定性验证。

Deletion hard-deletes the entry and its archived source entries recursively. Audit retains identities, not content. Future retrieval cannot reinject deleted entries. `done.used_memory_ids` contains only identities; the UI resolves current content and shows deleted entries as unavailable. Historical user messages and explicit write-tool parameters remain original conversation history; deleting memory does not rewrite that history.

删除会递归硬删条目及已归档来源，审计仅留 ID；之后的检索不会再注入该记忆。界面按 `done.used_memory_ids` 查当前内容，已删条目标为不可用。删除记忆不会改写原始历史用户消息或显式写入工具参数。

## HTTP and events / 接口与事件

| Endpoint / 接口 | Purpose / 用途 |
| --- | --- |
| `GET /api/agent/conversations/definitions/agents` | Validated packaged definitions / 已校验的内置定义 |
| `GET /api/agent/conversations/{id}/tree` | Child nodes, tools, tokens and model traces / 调用树、工具、用量及模型记录 |
| `GET/POST /api/agent/memories` | List/create; optional dataset filter / 列表和添加，可按数据集过滤 |
| `GET/DELETE /api/agent/memories/{id}` | Read/hard-delete / 查看和硬删 |
| `GET /api/agent/memories/audit` | Content-free deletion audit / 不含内容的删除审计 |

No SSE event type is added. Existing events gain defaulted `agent_path`, `agent_name`, `conversation_id`, `tokens` and `used_memory_ids` fields. Parent `tool_call` precedes child events; parent `tool_result` follows them. Paths such as `main/catalog-analyst#1` support collapsible nesting. Child `done` events do not finish the root response. Session lists show roots only.

SSE 类型保持不变，只增加带默认值的关联字段。父工具调用、子事件、父工具结果按序出现；路径支持折叠显示。子会话的 done 不结束主响应，会话列表只显示根会话。

## Golden extensions / Golden 扩展

The fake runtime consumes one shared serial script queue across root and child model calls. Optional `agent` labels must match the consuming Agent name (`main` for the root); a mismatch fails the golden even if `provider_error` was expected. Specify fixed tool-call IDs to keep suite digests reproducible. Example reply:

假模型的父子调用串行消费同一脚本队列；可选 `agent` 标签必须匹配实际调用方，否则 golden 失败。工具调用应填固定 ID，保证题集摘要可复现。例如：

```yaml
script:
  - agent: catalog-analyst
    tool_calls:
      - id: catalog-read-1
        name: list_datasets
        arguments: {}
  - agent: catalog-analyst
    content: Catalog review complete.
  - agent: main
    content: The specialist reviewed the catalog.
```

Each turn may set `new_conversation: true` to retain the isolated database while starting a new root conversation, or `delete_memories: true` to invoke real memory deletion after that turn. Expectations support `memory_count`, `memory_used` and `context_not_contains`. `fixture_kind: injection` builds a separate extracted caption fixture; existing evidence samples remain unchanged. Fake scripts alone may use `{{canary}}` and `{{canary_fragment}}`, expanded from the current request at execution time. These are test fixtures, never persisted secrets. Root turns exclude child calls; token totals include all calls.

每轮可设置 `new_conversation` 新建根会话并复用隔离数据库，或设置 `delete_memories` 在本轮后调用真实删除服务。新增断言可检查条目数、是否取用、上下文禁止内容。注入用独立 caption 样例，不修改既有证据数据。仅 fake 脚本支持运行时替换 canary 占位符；主轮数不含子调用，token 汇总包含全部调用。
