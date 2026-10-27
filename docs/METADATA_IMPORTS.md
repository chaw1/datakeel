# 外部工程元数据导入

[English](METADATA_IMPORTS.en.md)

Datakeel 读取本地 dbt 产物、Airflow REST API v1（实时拉取或离线导出），以及经过鉴权的 OpenLineage RunEvent。导入只处理元数据，不执行 dbt 模型或 Airflow 任务，也不安装这两个系统的运行时。

## dbt 产物

支持 manifest v10、v11、v12（dbt 1.6 至 1.9 及以后生成的 v12）；其他版本会明确报错。`manifest.json` 必填，`catalog.json` 和 `run_results.json` 可选。请使用同一次构建生成的文件。

```sh
uv run datakeel import dbt \
  --source-id warehouse --name 'Analytics warehouse' \
  --manifest ./target/manifest.json \
  --catalog ./target/catalog.json \
  --run-results ./target/run_results.json
```

models、sources、seeds、snapshots 导入为表；列、描述、`meta.owner` 或 `config.meta.owner`、标签保留在目录中。`depends_on` 生成表级血缘，编译后的 SQL 经既有解析器推导列级血缘。SQL 解析失败逐条写入导入摘要，不会冒充成功推导。测试定义及最近结果作为对象的质量证据保存，exposures 作为下游消费者。

负责人依次取资源的 `meta.owner`、`config.meta.owner`，来源表再回退到 source 级 `meta.owner`（dbt 1.6/1.7 写在 `source_meta`）；exposure 取 `owner.name` 或 `owner.email`。ephemeral 模型没有物理表，仍按 dbt 记录的 schema 和模型名登记为目录节点，`materialized` 标为 `ephemeral`，以保持表级血缘连续；引用它的模型在编译 SQL 中已内联 CTE，列级血缘直接指向物理来源。SQL 解析方言取自 `metadata.adapter_type`（`sqlserver`、`synapse` 映射为 T-SQL，`glue` 映射为 Spark，未知适配器用通用 SQL）。

`--source-id` 必须与已有数据库导入使用的 ID 一致，并代表一个物理数据库范围；内部对象标识为 `source/schema/table`，使用 relation 的 schema 和表名匹配同一张表。同一来源内若出现不同数据库中同 schema、同表名的冲突，导入会明确拒绝，需为数据库分别指定来源 ID。dbt 的 `unique_id` 用于识别同一来源中的对象，不能用可变显示名替代。目录对象的集成元数据保存原始身份、负责人、描述、标签、运行及质量证据；Web 的“集成元数据”区域可直接查看。

### 指标草稿需要人工确认

dbt semantic models 和 metrics 先生成 `metric_draft`，不会直接进入可执行语义层。在“目录 → 导入元数据”中按“指标草稿”筛选，打开草稿后审查定义。可编辑指标定义 JSON；无法直接映射为完整定义的草稿，必须补全负责人、度量、时间列等字段。点击“审阅指标确认计划”后会显示冻结参数、影响面和摘要，只有在标准签批单中明确签批并执行后才生效。

HTTP 使用同一受控动作：先 `POST /api/actions/confirm_metric_draft/prepare`，请求内容为 `{"draft_id":"...","definition":{...}}`；已有完整建议定义时可省略 `definition`。随后通过既有 approvals 和 execute 接口签批及执行。删除、已确认或版本不匹配的草稿不能重新确认。

## Airflow

选用 **Airflow REST API v1**（Airflow 2.x 的稳定接口），两种入口：从配置的调度器实时拉取，或导入离线导出的 JSON。两者生成同一份文档，导入结果一致。

### 实时拉取（CLI）

连接信息只走配置，不写在命令或产物里：

| 环境变量 | 说明 |
|---|---|
| `DATAKEEL_AIRFLOW_URL` | 必填，Web 服务器地址，例如 `https://airflow.example`，自动拼接 `/api/v1/` |
| `DATAKEEL_AIRFLOW_TOKEN` | 可选，以 `Authorization: Bearer` 发送 |
| `DATAKEEL_AIRFLOW_USERNAME` / `DATAKEEL_AIRFLOW_PASSWORD` | 可选，未设 token 时用 HTTP Basic（Airflow 默认的 basic_auth 后端） |
| `DATAKEEL_AIRFLOW_TIMEOUT` | 单次请求超时秒数，默认 30 |
| `DATAKEEL_AIRFLOW_RUN_LIMIT` | 每个 DAG 读取的最近运行数，默认 10 |

```sh
uv run datakeel import airflow --source-id scheduler --api [--dag daily_orders ...]
```

只发 GET 请求：`/dags`（按 `limit`/`offset` 和 `total_entries` 翻页）、`/dags/{dag_id}/tasks`、`/dags/{dag_id}/dagRuns`（最近 N 次）、每次运行的 `/taskInstances`、`/datasets`（Airflow 2.4 之前没有此接口，返回 404 时跳过）。不跟随重定向，不读取代理环境变量；HTTP 错误、连接失败或非 JSON 响应会中止导入，不写入半份结果。`--dag` 可重复，只拉取指定 DAG。Airflow 3 的 REST API v2 不在本次范围。

### 离线导出

导出过程由用户在其授权环境完成，Datakeel 只读取提交的文件。

```sh
uv run datakeel import airflow \
  --source-id scheduler --name 'Daily jobs' --file ./airflow-export.json
```

导出使用顶层 `dags` 数组。每个 DAG 可内含 `tasks`、`dag_runs` 和 `task_instances` 数组；也可按 REST v1 分页响应整理为顶层映射：

```json
{
  "dags": [{"dag_id": "daily_orders", "owners": ["Data team"], "schedule_interval": {"__type": "CronExpression", "value": "@daily"}}],
  "tasks": {"daily_orders": {"tasks": [{"task_id": "build_orders", "owner": "Data team", "inlets": ["postgres://warehouse.example:5432/analytics.public.raw_orders"], "outlets": ["postgres://warehouse.example:5432/analytics.public.orders"]}]}},
  "dag_runs": {"daily_orders": {"dag_runs": [{"dag_run_id": "scheduled-example", "state": "success", "end_date": "2026-10-25T01:00:00Z"}]}},
  "task_instances": {"daily_orders": {"task_instances": [{"task_id": "build_orders", "state": "success", "end_date": "2026-10-25T01:00:00Z"}]}}
}
```

REST v1 Task 响应未必提供 inlets/outlets，可在离线任务条目补充这两个字段；标准 `datasets` 集合中的 `producing_tasks` 和 `consuming_dags` 也可生成依赖。

DAG 和任务保留负责人、调度、最近运行状态；inlets/outlets 生成输入表 → 任务 → 输出表血缘。成功运行时间成为输出表的新鲜度证据。在“已导入对象”中可筛选 DAG、Airflow 任务并查看详情；表的对象页也展示最近成功运行时间。它表示已导入的最近成功证据，不是实时心跳。

## HTTP 和 Web

- `POST /api/catalog/import/dbt`：`source_id`、可选 `name`、`manifest`，以及可选 `catalog`、`run_results`。
- `POST /api/catalog/import/airflow`：`source_id`、可选 `name`、`document`。
- `GET /api/catalog/import/objects`：按 `kind`、`source_id`、`offset`、`limit` 浏览导入对象；`limit` 为 1–1000。

HTTP 中的产物字段必须是已解析的 JSON 对象，不能传服务器路径。Web 在“目录 → 导入元数据”中选择本地 JSON 文件，先在浏览器解析，再提交内容。支持 dbt 三份产物和 Airflow 导出文件。表格、字段、DAG、任务、消费者、指标草稿和 OpenLineage 作业均可从导入对象列表浏览及打开血缘。

CLI、API、Web 返回相同摘要：`new`、`changed`、`deleted`、`unchanged`、`drafts`、对象和血缘数量、SQL 解析失败。重复导入同一来源会比较稳定身份和实际内容；删除对象标记“来源已删除”，保留审计和原有证据，不物理删除。

## OpenLineage 事件

设置 `DATAKEEL_OPENLINEAGE_TOKEN`，调用方以 `Authorization: Bearer <token>` 向 `POST /api/openlineage/events` 发送标准 RunEvent。未配置 token 或鉴权失败均拒绝写入。凭证使用环境变量或受保护的本地配置，不放入产物或仓库。

`DATAKEEL_OPENLINEAGE_NAMESPACES` 可设置 JSON 映射，例如：

```json
{"postgres://warehouse.example:5432":{"source_id":"warehouse","database":"analytics"}}
```

映射应在首次接收事件前配置；之后修改映射不会自动重命名历史占位对象。未配置映射时，系统按规范化 namespace 和数据库生成独立来源，不推断主机归属。

namespace 与 dataset name 共同决定外部身份，映射到已有物理表；未知 dataset 自动创建占位对象。START、COMPLETE、FAIL 记录运行状态和血缘，同一 job + runId + eventType 重复投递不重复记账；完成、失败后迟到的 START 不覆盖终态。规范中的其他类型也接收：RUNNING 与 START 同属进行中；ABORT 为终态，不算成功，也不在血缘图上连边；OTHER 只补充元数据，不改变已观测的状态。作业的集成详情保存运行记录与最近成功时间。

独立接口与新对象类型保持既有目录查询和 OpenAPI schema 的兼容性。运行 `uv run datakeel api` 后可在 `/api/docs` 查看当前完整契约。

## 格式参考

- [Airflow REST API v1 (2.10.5)](https://airflow.apache.org/docs/apache-airflow/2.10.5/stable-rest-api-ref.html)
- [OpenLineage RunEvent](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md)
- [OpenLineage namespace and dataset naming](https://openlineage.io/docs/spec/naming/)
