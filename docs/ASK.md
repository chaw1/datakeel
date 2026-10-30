# Charts and follow-up questions

[中文](ASK.zh.md) · [Tour](DEMO.en.md)

Ask data uses registered metric definitions and read-only queries. It chooses a chart from the
result shape using deterministic rules, without a model call or an additional chart library.
The chart and table share the exact result rows; metric definitions supply units and formats.

| Result | Default view |
| --- | --- |
| One numeric value | Value card |
| Time series | Line chart |
| Category comparison | Vertical bars |
| More than eight categories, or long labels | Horizontal bars |
| Two dimensions | Grouped bars |
| More than two dimensions, more than thirty categories, or no numeric column | Table |

For an explicitly grouped result, a share question uses bars and adds each row's percentage
of the sum of metric values in the current returned rows. The metric values and SQL stay the
same as the equivalent grouped question. The denominator follows the current filters and
returned row limit; it does not include unreturned source rows. Questions without a clear
grouping, negated share requests, and additional unsupported averages or ratios clarify or
refuse instead of guessing a denominator.
When the returned values sum to zero, no share percentage is calculated.

Every chart has a title and description. In the Web interface, use the view controls with a
keyboard to switch between the automatically selected chart and its source table. The Web
interface does not offer manual selection of another chart type. Both light and dark themes
use the application's existing typography and color tokens.

## Keep asking in one thread

Start a new Ask conversation and ask `上个季度各区域零售额是多少` with the demo reference date
`2026-10-01`. Continue with `那华南呢`, `按月拆开`, or `换成订单数`. English equivalents include
`what about South China`, `by month`, and `switch to order count`. The resolver keeps the
previous metric, time interval, filters and groups, and changes the parts named in the follow-up.
It supports previous-year and previous-period comparisons, and reports an unavailable baseline
instead of inventing a percentage. A complete new question starts a new query frame.

Generic `period over period` compares the current interval with its immediately preceding
matching interval. Explicit month-over-month (`MOM` or `compare with the previous month`)
requires a complete calendar month; quarter-over-quarter (`QOQ` or `compare with the previous
quarter`) requires a complete calendar quarter. A request whose explicit comparison grain
does not match the current interval asks for clarification before querying.

Each turn displays **Understood as / 理解为** followed by the complete question. Check this
before using its result. The English interface shows the English wording
(`interpreted_question_en`): metric and dimension names use their registered English names,
and recorded values such as 华东 stay as recorded. Answers saved before this wording existed
show the question as asked. The recognised subject line also uses the subject's registered
English name (`english_name`); names without one stay as registered.
Ambiguous follow-ups ask for clarification and return no number.
The conversation list can reopen or delete saved threads; reloads and process restarts recover
them from SQLite or PostgreSQL. Separate browser tabs keep separate active thread selections.
`DATAKEEL_ASK_CONVERSATION_RETENTION_DAYS` configures how long threads are retained.
The default is 30 days, with a supported range of 1–3650. Expired threads are cleaned up
during Ask reads, listings and writes; no background erasure task runs while Ask is idle.

Deleting an Ask thread removes its query frames, question and answer rows, and saved answer
replay. It also blocks cached `ask_data` tool replay. Immutable evidence and lineage audit
references remain. Answers already included in a separate Agent transcript or tool audit stay
with that separate record's lifecycle; deleting an Ask thread does not erase those copies.

Every turn and saved-history read checks current asset grants. An earlier answer does not grant
future access. Revoked or expired grants prevent replay and conversation disclosure. Threads
belong to the operator who created them. Ask conversation IDs are separate from Agent runtime
conversation IDs and from the existing clarification `session_id`.

## CLI, HTTP, Agent and MCP

The first command prints JSON including `conversation_id`, `interpreted_question` and `chart`.
Copy its conversation ID into the next command:

```sh
uv run datakeel ask '上个季度华东区零售额是多少' --reference-instant 2026-10-01T00:00:00Z
uv run datakeel ask '那华南呢' --conversation-id YOUR_CONVERSATION_ID --reference-instant 2026-10-01T00:00:00Z
```

`POST /api/ask` accepts the optional `conversation_id`; omitting it starts a new Ask thread.
The response remains the saved answer contract with additive chart and conversation fields.

| HTTP | Purpose |
| --- | --- |
| `POST /api/ask/conversations` | Create an empty thread; no request body |
| `GET /api/ask/conversations` | List this operator's readable threads |
| `GET /api/ask/conversations/{id}` | Open a saved thread and its turns |
| `DELETE /api/ask/conversations/{id}` | Delete the Ask thread and its saved answer replay |
| `GET /api/ask/{answer_id}` | Replay a saved answer after current grant checks |

Use `X-Datakeel-Actor` consistently for thread management and questions; its HTTP default is
`local-user`. The existing question-body `actor` remains supported when the header is absent.
The Agent read tool and MCP `ask_data` share the same request schema: pass the returned
`conversation_id` in subsequent tool calls. Their fixed local operator is `local`. Neither
transport gains write or approval capabilities from an Ask thread.
