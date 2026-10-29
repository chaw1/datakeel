# Quality rules / 数据质量规则

[English tour](DEMO.en.md) · [中文导览](DEMO.md)

Quality rules monitor registered SQLite or PostgreSQL business sources. Definitions are immutable revisions; the worker executes bounded, read-only checks and stores their observations, issues and alert deliveries. No language model is needed.

质量规则监控已登记的 SQLite 或 PostgreSQL 业务数据源。定义按版本保留；worker 执行有界只读检查，并持久化结果、问题单和告警投递。整个流程不需要语言模型。

Register either source through the existing `import_catalog` controlled action. PostgreSQL reflection uses a read-only transaction and a five-second connection/statement timeout. Without `schemas`, it imports only the connection's default schema (normally `public`); list additional business schemas explicitly in `CatalogImportRequest.schemas`. System schemas are rejected. SQLite reflection opens an existing file in read-only mode.

两种数据源均通过既有 `import_catalog` 受控动作登记。PostgreSQL 反射使用只读事务，连接与语句超时均为五秒；省略 `schemas` 时仅导入连接的默认 schema（通常为 `public`），其他业务 schema 需在 `CatalogImportRequest.schemas` 中显式列出，系统 schema 会被拒绝。SQLite 只读打开已有文件。

## Define a contract / 定义合同

Contracts live in `contracts/quality-rules/`; `schema.json` describes the complete frozen boundary. `version: 1` contains a `rules` list with unique IDs. Change `source_id`, schema, table and column to registered catalog identities before creating a rule. Table and column names are local names, rather than slash-separated catalog IDs. If a schema is omitted, preparation resolves exactly one matching catalog table and freezes its schema; ambiguous tables require an explicit schema.

YAML 合同位于 `contracts/quality-rules/`，完整字段由 `schema.json` 描述。`version: 1` 下的 `rules` 列表要求 ID 唯一。新建规则前，使用目录中已登记的数据源、schema、表和列。表、列使用自身名称，不使用带斜杠的目录 ID。省略 schema 时，准备计划必须唯一解析到一张表，并冻结其 schema；存在歧义时必须显式填写。

Rule IDs are URL-safe ASCII identifiers: start with a letter or digit, then use letters, digits, `_`, `.`, `:`, or `-` (at most 200 characters). Use `name` for Chinese or other display text; spaces and slashes are not valid in IDs.

规则 ID 使用 URL 安全的 ASCII 标识：首字符为字母或数字，后续可包含字母、数字、`_`、`.`、`:`、`-`，最长 200 字符。中文等展示文案放在 `name` 中，ID 不允许空格或斜杠。

```yaml
version: 1
rules:
  - id: orders_amount_nonnegative
    name: Orders have nonnegative paid amounts
    target:
      source_id: ecommerce
      schema_name: main
      table: orders
      column: paid_amount
    kind: range
    params:
      minimum: 0
    severity: error
    threshold: 0
    cron: "0 9 * * *"
    owner: commerce-team
    timeout_ms: 5000
    max_rows: 10000
    enabled: true
```

Validate YAML and prepare imports with the CLI below, using the same `DATAKEEL_HOME` and database settings as the running demo. Validation does not connect to a business source. Import only prepares plans and prints their IDs; review and approve them in **Approvals** before execution. The target source must already be registered in that workspace.

CLI 使用与运行中 demo 相同的 `DATAKEEL_HOME` 和数据库配置。校验不连接业务数据源；导入只准备计划并输出计划 ID，执行前需到「审批待办」审阅并签批。目标数据源必须已在该工作区登记。

```bash
uv run datakeel quality validate quality-rules.yaml
uv run datakeel quality import quality-rules.yaml
# Review and execute the prepared plans in the Approvals page first.
uv run datakeel quality list
uv run datakeel quality run orders_amount_nonnegative
uv run datakeel quality report --source-id ecommerce --table orders --schema-name main
```

`run` queues a task; a running `datakeel worker` is required for results. `datakeel demo` starts its worker automatically. `load_contract(Path(...))` is also available from `datakeel.quality.dq_contracts` for callers that only need a validated frozen contract.

`run` 只入队，需要运行 `datakeel worker` 才会产出结果；`datakeel demo` 自动启动 worker。只需校验后的冻结合同，也可调用 `datakeel.quality.dq_contracts.load_contract(Path(...))`。

The same fields are available in **Quality rules → Create rule**. Parameters use a JSON object, with a starting example for each type. Every create, edit and deletion prepares a frozen controlled-action plan and requires approval. Editing or deleting includes `expected_revision`; stale plans are rejected. Deleted IDs remain tombstones, so use a new ID for a replacement. History and prior results are retained.

Web 的「质量规则 → 新建规则」提供相同字段。参数为 JSON 对象，切换规则类型会提供起始示例。增删改均生成冻结的受控动作计划并要求签批；修改和删除携带 `expected_revision`，过期版本的计划会被拒绝。删除保留墓碑，替代规则需使用新 ID，原历史与结果仍保留。

## Types and thresholds / 类型与阈值

Every measured assertion passes when `actual_value <= threshold`. Column checks use the fraction of violating rows; SQL assertions use the number of returned violations; freshness uses seconds; volume and non-PSI drift use absolute relative change. Range boundaries are inclusive. NULL is checked by `not_null`; other column constraints ignore NULL, so combine them with a non-null rule when needed. Uniqueness counts every row participating in a duplicate group.

得到可判定观测时，`actual_value <= threshold` 为通过。列约束的实际值是违规行比例；SQL 断言是返回的违规行数；新鲜度是秒数；量级变化和非 PSI 漂移是绝对相对变化率。范围包含上下边界。NULL 由非空规则检查，其他列约束忽略 NULL，需要时组合使用。唯一性将重复组中的每行都计为违规。

| `kind`                  | Check / 检查                                                            | Example `params` / 参数示例                                                                | Example threshold / 阈值示例 |
| ----------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------- |
| `not_null`              | No NULLs / 非空                                                         | `{}`                                                                                       | `0`                          |
| `unique`                | No repeated non-NULL values / 非空值不重复                              | `{}`                                                                                       | `0`                          |
| `range`                 | Inclusive numeric bounds / 数值范围                                     | `{"minimum": 0, "maximum": 100}`                                                           | `0`                          |
| `accepted_values`       | Declared values or code-table membership / 枚举或码表                   | `{"values": ["active", "pending"]}`                                                        | `0`                          |
| `regex`                 | Bounded full-string match / 有界整串正则匹配                            | `{"pattern": "^[A-Z]+$"}`                                                                  | `0`                          |
| `referential_integrity` | Non-NULL value exists in reference column / 引用列存在                  | `{"reference_table": "customers", "reference_column": "id"}`                               | `0`                          |
| `freshness`             | Seconds since latest timestamp / 最新时间戳距今秒数                     | `{}`                                                                                       | `86400`                      |
| `volume_change`         | Row count deviation from baseline / 行数相对基线变化                    | `{"baseline_runs": 3}`                                                                     | `0.5`                        |
| `distribution_drift`    | Mean, standard deviation, NULL rate or PSI / 均值、标准差、空值率或 PSI | `{"baseline_runs": 3, "statistic": "mean"}`                                                | `0.2`                        |
| `sql_assertion`         | SELECT returns violating rows / SELECT 返回违规行                       | `{"sql": "SELECT * FROM orders WHERE paid_amount < :minimum", "bindings": {"minimum": 0}}` | `0`                          |

`accepted_values` can instead use `reference_table`, `reference_column` and optional `reference_schema`. Drift supports `statistic: mean | stddev | null_rate | psi`; PSI uses explicit strictly increasing `bin_edges` when given; otherwise the first numeric observation of a rule revision fixes its decile cut points and every later observation of that revision reuses them, so bins follow the column's own scale. A target column is required except for volume and SQL rules. SQL must be a single read-only SELECT within the declared target table. Unqualified table references, including nested reads and self-joins, bind to the rule's frozen target schema. Write statements, multiple statements, cross-table reads and CTEs are rejected; bound values go in `bindings`. A read-only transaction does not stop every server function, so assertions may only call functions that the SQL parser recognises as standard built-ins plus a few pure date helpers (`julianday`, `datetime`, `time`, `unixepoch`, `total` on SQLite; `age`, `make_date`, `json_typeof`, `jsonb_typeof` on PostgreSQL). Calls such as `pg_sleep`, `setval`, `pg_terminate_backend`, `query_to_xml`, `pg_read_file`, `load_extension` or `randomblob`, and any schema-qualified function call, are rejected when the rule is prepared.

取值集合也可用 `reference_table`、`reference_column` 和可选 `reference_schema` 引用码表。漂移支持 `mean | stddev | null_rate | psi`，PSI 指定严格递增的 `bin_edges` 时按其分箱；未指定时，规则版本的第一次数值观测按自身十分位数确定分箱边界，同一版本此后沿用，分箱随列的数值量级自适应。量级变化和 SQL 之外的规则必须指定列。自定义 SQL 限制为声明目标表上的单条只读 SELECT；未限定的表引用（含子查询与自连接）绑定到规则冻结的目标 schema。拒绝写操作、多语句、跨表读取和 CTE。值通过 `bindings` 绑定。只读事务挡不住所有服务器函数，因此断言只能调用 SQL 解析器识别的标准内置函数，以及少数纯日期函数（SQLite 的 `julianday`、`datetime`、`time`、`unixepoch`、`total`；PostgreSQL 的 `age`、`make_date`、`json_typeof`、`jsonb_typeof`）。`pg_sleep`、`setval`、`pg_terminate_backend`、`query_to_xml`、`pg_read_file`、`load_extension`、`randomblob` 等调用，以及任何带 schema 前缀的函数调用，在准备规则时即被拒绝。

Preparing a rule checks the reflected column type. On PostgreSQL, `not_null` and NULL-rate drift work on every type because they only test whether a cell is NULL (a JSON `null` literal is a value, not SQL NULL). `unique` needs a scalar column (number, text, UUID, boolean, date/timestamp or time); `accepted_values` needs text, number, boolean or UUID; `regex` needs text or UUID; `referential_integrity` needs text, number, UUID or date/timestamp, with a comparable reference column (UUID and text compare as canonical lower-case text); `range` and numeric drift need a number; `freshness` needs a DATE or TIMESTAMP column. JSON/JSONB, arrays, BYTEA, INTERVAL, network and other types are therefore limited to NULL checks, and incompatible combinations are rejected with the reason. Constraint equality preserves scalar types and case-sensitive text equality; PostgreSQL numeric membership uses JSONB numeric equality. Streamed numeric statistics use floating point. SQLite columns are dynamically typed, so only declared BLOB columns are restricted to NULL checks. The reference table and column must also be registered in the catalog.

准备规则时会检查目录中反射到的列类型。PostgreSQL 上，`not_null` 和空值率漂移只判断单元格是否为 NULL，适用于所有类型（JSON 的 `null` 字面量是值，不是 SQL NULL）。`unique` 需要标量列（数值、文本、UUID、布尔、日期/时间戳或时间）；`accepted_values` 需要文本、数值、布尔或 UUID；`regex` 需要文本或 UUID；`referential_integrity` 需要文本、数值、UUID 或日期/时间戳，且引用列类型可比较（UUID 与文本按规范小写文本比较）；`range` 和数值漂移需要数值列；`freshness` 需要 DATE 或 TIMESTAMP 列。因此 JSON/JSONB、数组、BYTEA、INTERVAL、网络地址等类型只能做 NULL 检查，不兼容的组合会在准备时说明原因并拒绝。约束比较保持标量类型与文本大小写敏感，PostgreSQL 的数值集合按 JSONB 数值等价比较；流式数值统计使用浮点数。SQLite 为动态类型，只有声明为 BLOB 的列限制为 NULL 检查。引用表和引用列也必须已在目录中登记。

Volume and drift use the most recent `baseline_runs` eligible observations of the same rule revision: prior passes and cold-start observations. Failed or execution-error results do not enter the baseline. Until enough observations exist, the status is `baseline_insufficient`, with no passing verdict and no failure issue. Changing the rule revision starts a new baseline. Relative change is `abs(current - baseline) / abs(baseline)`; with a zero baseline, unchanged zero maps to 0 and a nonzero current value maps to 1.

量级变化和漂移采用同一规则版本最近 `baseline_runs` 次有效观测：包括通过结果和冷启动观测，排除失败与执行错误。历史不足时为 `baseline_insufficient`，既不判通过，也不开失败问题单。规则换版后重新积累基线。相对变化按 `abs(当前值 - 基线) / abs(基线)` 计算；基线为零时，当前仍为零记 0，否则记 1。

## Worker scheduling and read limits / 调度与只读边界

Cron uses five numeric UTC fields: minute, hour, day of month, month and weekday. Lists, ranges and steps are supported; Sunday is 0 or 7. When both day-of-month and weekday are restricted, either match is sufficient. No system cron is installed. Each worker tick finds every enabled rule's **newest matching minute within the last 24 hours** and enqueues it only if that rule revision has no run for that minute. A minute missed because the worker was busy with a long task or stopped therefore runs once at the next tick; several missed minutes collapse into the newest one, matches older than 24 hours are skipped, and a revision never catches up minutes from before it was accepted. A unique rule/revision/minute slot prevents duplicate scheduling across workers. Idle ticks only read; scheduling locks are taken only when a slot is due. Execution uses the existing task shard leases and reaper; a task's frozen rule is unaffected by later edits.

cron 使用五段 UTC 数值：分钟、小时、日期、月份、星期，支持列表、范围和步长，星期日可为 0 或 7。日期和星期都有限制时，满足其一即可。无需安装系统定时任务。worker 每次 tick 为每条启用规则找出**最近 24 小时内最新的匹配分钟**，该规则版本在这一分钟尚无执行记录时才入队。因此 worker 忙于长任务或停机而错过的计划会在下一次 tick 补跑一次；连续错过多次只补最近一次，超过 24 小时的跳过，规则版本生效之前的分钟不补跑。规则、版本、分钟的唯一槽位防止多个 worker 重复排队。空闲 tick 只读，到点才加调度锁。执行沿用任务分片租约及 reaper，已排队任务使用冻结规则，不受后续修改影响。

Checks use the existing read-only query boundary, with a rule timeout of 1–60,000 milliseconds (default 5,000). `max_rows` remains compatible with existing YAML: 1–100,000, default 10,000. It now bounds each streaming batch (also capped at 4,096) and the number of returned SQL-assertion violation rows; **it never caps the target or reference table**. Column constraints count violations inside the database; uniqueness counts every non-NULL member of a repeated group. Reference membership stays inside the database instead of loading a Python set. Column moments share the constraint aggregate snapshot. Regex matching and distribution statistics read fixed-size batches; PostgreSQL uses a server cursor. Adaptive PSI moments, exact deciles and histogram counts share one database-sorted stream, retaining only nine boundaries. Memory is independent of table length, apart from individual cell size. Rules currently scan independently. A timeout yields an `error` with unknown coverage and no verdict, never a partial pass. SQL assertions run without a source-row preflight; too many returned violations yield an explicit `Quality assertion result row limit exceeded` error. Volume and freshness use a single database-side `COUNT(*)` / `MAX(timestamp)` statement.

执行复用既有只读查询边界，超时允许 1–60,000 毫秒，默认 5,000 毫秒。保留兼容旧 YAML 的 `max_rows`（1–100,000，默认 10,000），但含义改为每个流式读取块的行数上限（另有固定 4,096 行上限）以及 SQL 断言返回的违规结果行数上限，**不再限制目标表或引用表总行数**。列约束由数据库统计违规数，唯一性将重复组中的每个非空成员都计为违规；引用关系在数据库内比较，不在 Python 中装入整张码表。列统计与约束聚合使用同一查询快照，正则和分布统计采用固定块读取，PostgreSQL 使用服务端游标。自适应 PSI 在同一次数据库排序流中统计矩、精确十分位边界和桶计数，仅保留九个边界值。除单个单元格大小外，内存不随表长增长。各规则仍独立扫描；超时返回覆盖范围未知、无结论的 `error`，不会部分通过。SQL 断言取消源表行数预检，返回违规行过多则明确报 `Quality assertion result row limit exceeded`。量级变化和新鲜度仍使用单条库内 `COUNT(*)` / `MAX(时间列)`。

Every new measured result records `rows_total`, `rows_scanned` and `coverage: complete` (100%), including cold-start observations. For assertions these counts describe the declared target table; `row_count` retains its compatible meaning of returned violation rows. Errors and legacy results use `coverage: unknown` rather than inventing a percentage. Coverage appears in API result payloads, analysis-report chapters and the web run details. Aggregated constraint samples expose at most the first failing row ordinal; regex/assertion samples retain up to five ordinals. All samples redact values.

新产生的完整观测（含冷启动）带 `rows_total`、`rows_scanned` 及 `coverage: complete`（100%）。断言的覆盖行数指声明的目标表，原有 `row_count` 仍表示返回的违规结果行数。错误和历史旧结果显示 `coverage: unknown`，不虚构百分比。API、分析报告章节和 Web 运行详情均展示覆盖范围。库内聚合约束最多保留首个违规行序号，正则和断言最多保留五个，所有样例值均脱敏。

On SQLite, freshness compares text timestamps chronologically with `julianday()` (honouring offsets such as `+08:00` and `Z`, with millisecond precision). Non-NULL cells that are not text starting with `YYYY-MM-DD` fail and are counted in the message. PostgreSQL requires DATE or TIMESTAMP, reads naive timestamps as UTC and rejects `infinity` / `-infinity` in the same way.

SQLite 上新鲜度用 `julianday()` 按时间比较文本时间戳（识别时区偏移，精度为毫秒）；非空但不是以 `YYYY-MM-DD` 开头的文本会失败并在消息中计数。PostgreSQL 要求 DATE 或 TIMESTAMP，无时区时间按 UTC 解释，同样拒绝 `infinity` / `-infinity`。


## Results, issues and alerts / 结果、问题单与告警

The rule page shows current definitions, latest current-revision status, recent results and an SVG trend with actual values and thresholds. Results and issues refresh every five seconds while a rule is open. Historical result rows retain the observed threshold and revision. Table object pages link to rules for their exact source, schema and table. **Run now** prepares a controlled action; executing it queues a worker task and does not run SQL in the browser request.

规则页展示定义、当前版本最近状态、历史结果以及实际值和阈值的 SVG 趋势。打开规则后，结果与问题单每五秒刷新。历史结果保留当时阈值和版本。表对象页关联精确的数据源、schema、表上的规则。「立即运行」准备受控动作，执行后交给 worker 队列，不在浏览器请求中执行 SQL。

Failure and execution-error observations create an issue; later failures merge into the active issue. A pass changes that issue to `recovered`, awaiting human confirmation. A failure before confirmation reopens the same episode. Users can claim or reassign an active issue through controlled actions with revision checks; claiming a recovered issue preserves its recovery status. The API's `can_resolve` allows confirmation after recovery, or when the rule has been disabled or deleted. Active failing rules cannot be resolved manually. The page shows all issues when no rule is selected, including issues of retired rules. Resolving closes the episode; a later failure creates a new issue. `baseline_insufficient` does not open or recover an issue.

规则失败或执行错误会开问题单，后续失败合并到当前单中。恢复通过后改为 `recovered`（已恢复待确认）；确认前再次失败，仍重开同一张单。用户可通过带版本校验的受控动作认领或重新分配当前问题单，认领已恢复问题不改变恢复状态。接口的 `can_resolve` 允许已恢复或规则已禁用、已删除的问题单人工关闭，仍在持续失败的有效规则不能直接解决。不选规则时，页面展示全部问题单，包含废止规则的遗留问题。解决关闭当前事件，后续失败再开新单。基线不足不会开单，也不会将已有问题单标为恢复。

Alerts are disabled unless both `DATAKEEL_DQ_WEBHOOK_URL` and `DATAKEEL_DQ_WEBHOOK_SECRET` are configured. Deliveries use a durable outbox and the headers `X-Datakeel-Event-Id`, `X-Datakeel-Timestamp` and `X-Datakeel-Signature`. Verify the exact raw body with HMAC-SHA256 over `timestamp + "." + body`; the signature value is `sha256=` plus the hexadecimal digest. Alerts follow issue state changes only: a new issue or a failure after recovery sends `quality.failed`, and a recovery sends `quality.recovered`. Further failures within an active episode raise the issue's failure count without another alert. Deduplicate by event ID. Non-2xx responses and transport failures retry with exponential backoff: `DATAKEEL_DQ_WEBHOOK_RETRY_SECONDS` defaults to 5, capped at one hour per delay; `DATAKEEL_DQ_WEBHOOK_MAX_ATTEMPTS` defaults to 8. Proxies and redirects are disabled. Use a local mock receiver for development and tests.

只有同时配置 `DATAKEEL_DQ_WEBHOOK_URL` 和 `DATAKEEL_DQ_WEBHOOK_SECRET` 才投递告警。持久 outbox 使用 `X-Datakeel-Event-Id`、`X-Datakeel-Timestamp`、`X-Datakeel-Signature` 请求头。以原始请求体，对 `时间戳 + "." + 请求体` 做 HMAC-SHA256，签名值为 `sha256=` 加十六进制摘要。告警只跟随问题单状态变化：新开问题单或恢复后再次失败发送 `quality.failed`，恢复发送 `quality.recovered`；同一事件内的后续失败只累加问题单失败次数，不重复告警。接收端按事件 ID 去重。非 2xx 和传输失败指数退避重试，`DATAKEEL_DQ_WEBHOOK_RETRY_SECONDS` 默认 5 秒，单次延迟最多一小时；`DATAKEEL_DQ_WEBHOOK_MAX_ATTEMPTS` 默认 8 次。投递禁用环境代理和重定向。开发、测试使用本地模拟接收器。

## Scores, reports and reads / 评分、报告与只读接口

Only enabled rules with a measured pass, failure or execution error contribute to the score. An `error` severity has weight 2; `warn` has weight 1. Pending and insufficient-baseline rules remain visible but do not count as passes. Set optional `dataset_id` to associate a rule with a file dataset: when measured rules exist, file quality and database rules each contribute 50%; a dataset without files uses the rule score alone. The quality view exposes the `database_rules` dimension and detailed rule summary; analysis reports include the stored observations.

只有启用且已通过、失败或执行错误的规则进入评分，`error` 严重级别权重 2，`warn` 权重 1。未执行、基线不足保持可见，不计为通过。可用 `dataset_id` 将规则关联到文件数据集：有可测规则时，文件质量和数据库规则各占 50%；无文件时只使用规则分数。质量页新增 `database_rules` 维度和规则摘要，分析报告纳入持久化观测。

| Read endpoint / 只读接口                       | Purpose / 用途                                                                                          |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `GET /api/quality/rules`                       | List current rules; optional exact `source_id`, `table`, `schema_name` filters / 当前规则及精确目标筛选 |
| `GET /api/quality/rules/{id}`                  | Current rule and latest current-revision result / 当前定义及当前版本最近结果                            |
| `GET /api/quality/rules/{id}/results?limit=50` | Newest-first retained results / 最新在前的历史结果                                                      |
| `GET /api/quality/rules/{id}/history`          | Create, edit and deletion history / 增删改历史                                                          |
| `GET /api/quality/issues?rule_id=...`          | Active and resolved episodes / 当前和已解决的问题单                                                     |
| `GET /api/quality/summary`                     | Score and verdict counts with the same target filters / 评分与状态统计                                  |
| `GET /api/quality/report`                      | Deterministic analysis with the same target filters / 确定性分析报告                                    |
| `GET /api/quality/runs/{id}`                   | Queued task and terminal result identity / 排队任务及最终结果 ID                                        |

Agent read tools can list failing rules and explain recent table quality using the same persisted results. Definitions and issue changes continue through the controlled-action boundary.

Agent 的只读工具可根据相同持久化结果列出报错规则、说明表最近质量；规则定义和问题单变更仍由受控动作边界执行。
