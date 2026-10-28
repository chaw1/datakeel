# Import engineering metadata

[中文](METADATA_IMPORTS.md)

Datakeel reads local dbt artifacts, the Airflow REST API v1 (live or as an offline export), and authenticated OpenLineage RunEvents. Imports process metadata without executing dbt models or Airflow tasks. Neither system becomes a runtime dependency.

## dbt artifacts

Manifest versions 10, 11, and 12 are supported (dbt 1.6 through 1.9 and later v12 producers); other versions fail with an explicit error. `manifest.json` is required. `catalog.json` and `run_results.json` are optional. Use artifacts from the same build.

A missing `catalog.json` only means the warehouse columns were not read this time, not that columns were dropped: a later import keeps the columns, types, and comments reflected by the previous import, column lineage is still derived, and the summary says so through `retained_columns` and `notes`. A column is marked deleted at source only when a supplied `catalog.json` no longer contains it.

```sh
uv run datakeel import dbt \
  --source-id warehouse --name 'Analytics warehouse' \
  --manifest ./target/manifest.json \
  --catalog ./target/catalog.json \
  --run-results ./target/run_results.json
```

Models, sources, seeds, and snapshots become catalog tables with columns, descriptions, owners from `meta.owner` or `config.meta.owner`, and tags. `depends_on` supplies table lineage. Compiled SQL uses the existing parser for column lineage; individual parsing failures remain visible in the summary. Test definitions and latest results are retained as quality evidence. Exposures become downstream consumers.

Objects keep only a result's status, failure count, and the message of a non-success. Fields that change on every invocation, such as timings, threads, and adapter receipts (row counts, query IDs), together with `invocation_id` and `generated_at`, are stored as a separate run record (a `DBT_RUN` event deduplicated by `invocation_id`) and never count as object changes. Rerunning dbt with unchanged code and data and importing again reports everything unchanged; a test that starts failing or a changed failure count is still a change.

Owners come from the resource's `meta.owner`, then `config.meta.owner`; source tables fall back to source-level `meta.owner` (written as `source_meta` by dbt 1.6/1.7); exposures use `owner.name` or `owner.email`. Ephemeral models have no physical table. They are still registered under dbt's recorded schema and model name with `materialized` set to `ephemeral`, so table lineage stays connected; dependent models inline them as CTEs, so column lineage points directly at the physical inputs. The SQL dialect comes from `metadata.adapter_type` (`sqlserver` and `synapse` map to T-SQL, `glue` to Spark, unknown adapters to generic SQL).

Reuse the database import's `--source-id`, which represents one physical database scope. Internal identities use `source/schema/table`; relation schema and table names match an existing table. Conflicting databases with the same schema and table under one source are explicitly rejected; use separate source IDs for those databases. dbt `unique_id` identifies objects within their source; a display name is not a stable identity. Object integration metadata retains external identities, descriptions, ownership, tags, run information, and quality evidence, available in the Web integration metadata section.

### Metric drafts require confirmation

Imported semantic models and metrics first become `metric_draft` objects without changing executable semantics. In **Catalog → Import metadata**, filter by **Metric draft**, select a draft, and review its definition. Edit the metric definition JSON when needed. Drafts without a complete proposed definition need explicit owner, measure, time column, and other required fields. **Review metric confirmation** prepares a frozen plan. The metric takes effect only after explicit approval and execution in the standard approval sheet.

The HTTP equivalent starts with `POST /api/actions/confirm_metric_draft/prepare` and `{"draft_id":"...","definition":{...}}`. The definition can be omitted when the draft already has a complete proposal. Use the existing approval and execution endpoints for the returned plan. Deleted, confirmed, or version-conflicting drafts cannot be confirmed again.

## Airflow

The chosen API is **Airflow REST API v1**, the stable API of Airflow 2.x. There are two entry points: a live pull from the configured scheduler, or an offline JSON export. Both produce the same document and the same import result.

### Live pull (CLI)

Connection details come only from configuration, never from commands or artifacts:

| Variable | Meaning |
|---|---|
| `DATAKEEL_AIRFLOW_URL` | Required web server address such as `https://airflow.example`; `/api/v1/` is appended |
| `DATAKEEL_AIRFLOW_TOKEN` | Optional; sent as `Authorization: Bearer` |
| `DATAKEEL_AIRFLOW_USERNAME` / `DATAKEEL_AIRFLOW_PASSWORD` | Optional HTTP Basic credentials used when no token is set (Airflow's default basic_auth backend) |
| `DATAKEEL_AIRFLOW_TIMEOUT` | Per-request timeout in seconds, default 30 |
| `DATAKEEL_AIRFLOW_RUN_LIMIT` | Recent runs read per DAG, default 10 |

```sh
uv run datakeel import airflow --source-id scheduler --api [--dag daily_orders ...]
```

Only GET requests are sent: `/dags` (paged by `limit`/`offset` and `total_entries`), `/dags/{dag_id}/tasks`, `/dags/{dag_id}/dagRuns` (the latest N), `/taskInstances` for each of those runs, and `/datasets` (skipped on 404 for schedulers older than 2.4). Redirects are not followed and proxy environment variables are ignored. HTTP errors, connection failures, or non-JSON bodies stop the import before anything is published. Repeat `--dag` to pull only selected DAGs. Airflow 3's REST API v2 is out of scope.

### Offline export

Users export metadata from an environment they are authorized to access; Datakeel only reads the submitted file.

```sh
uv run datakeel import airflow \
  --source-id scheduler --name 'Daily jobs' --file ./airflow-export.json
```

The export contains a top-level `dags` array. A DAG can embed `tasks`, `dag_runs`, and `task_instances` arrays. Alternatively, collect the REST v1 responses into top-level maps:

```json
{
  "dags": [{"dag_id": "daily_orders", "owners": ["Data team"], "schedule_interval": {"__type": "CronExpression", "value": "@daily"}}],
  "tasks": {"daily_orders": {"tasks": [{"task_id": "build_orders", "owner": "Data team", "inlets": ["postgres://warehouse.example:5432/analytics.public.raw_orders"], "outlets": ["postgres://warehouse.example:5432/analytics.public.orders"]}]}},
  "dag_runs": {"daily_orders": {"dag_runs": [{"dag_run_id": "scheduled-example", "state": "success", "end_date": "2026-10-25T01:00:00Z"}]}},
  "task_instances": {"daily_orders": {"task_instances": [{"task_id": "build_orders", "state": "success", "end_date": "2026-10-25T01:00:00Z"}]}}
}
```

The REST v1 Task response may omit inlets/outlets; add these fields to offline task entries when needed. Standard dataset `producing_tasks` and `consuming_dags` references can also generate dependencies.

DAGs and tasks retain owners, schedules, and the latest run state. Inlets and outlets produce input table → task → output table lineage. Successful producer task times become output table freshness evidence. Filter **Imported objects** by DAG or Airflow task to inspect details; table object pages also display the last successful run. This is the most recent imported success evidence, not a live heartbeat.

`--source-id` names only the scheduler, which owns the DAGs and tasks. Tables named by inlets and outlets attach to the source that actually holds them. URIs are normalized under the OpenLineage rules (lowercase scheme, default port removed) and then matched in order:

1. An explicit `DATAKEEL_OPENLINEAGE_NAMESPACES` mapping (see below), suited to sources without a server address such as dbt or SQLite.
2. A database-import source whose connection URL names a host and a database, matched on "scheme://host:port + database"; driver suffixes and credentials are ignored. For example, a source at `postgresql+pg8000://etl@warehouse.example:5432/analytics` matches `postgres://warehouse.example:5432/analytics.public.orders`, which merges into the reflected `public.orders`.

Tables that match neither are filed under a placeholder source named `airflow`, marked `unmatched_source` in their details and shown as "Unmatched source" on the object page. The placeholder's schema segment keeps the original namespace and database, so equally named tables on different servers never merge. Importing the matching source and then re-importing Airflow attaches the table to that source and marks the old placeholder as deleted at source.

## HTTP and Web

- `POST /api/catalog/import/dbt`: `source_id`, optional `name`, `manifest`, and optional `catalog` and `run_results`.
- `POST /api/catalog/import/airflow`: `source_id`, optional `name`, and `document`.
- `GET /api/catalog/import/objects`: filter imported objects with `kind`, `source_id`, `offset`, and `limit` (1–1000).

Artifact fields contain decoded JSON objects rather than server paths. In **Catalog → Import metadata**, select local JSON files. The browser parses the files before submitting their contents. The form supports all three dbt artifacts and an offline Airflow export. Imported tables, columns, DAGs, tasks, consumers, metric drafts, and OpenLineage jobs can be browsed and opened in lineage.

CLI, HTTP, and Web share a summary: `new`, `changed`, `deleted`, `unchanged`, `drafts`, object and link counts, and SQL failures. Reimporting the same source compares stable identities and actual contents. Removed objects are marked **Deleted at source**, retaining their audit and evidence instead of being physically deleted.

## OpenLineage events

Configure `DATAKEEL_OPENLINEAGE_TOKEN`. Send standard RunEvents to `POST /api/openlineage/events` using `Authorization: Bearer <token>`. Missing configuration and failed authentication reject writes. Keep credentials in environment variables or protected local configuration, outside artifacts and the repository.

`DATAKEEL_OPENLINEAGE_NAMESPACES` optionally supplies a JSON mapping:

```json
{"postgres://warehouse.example:5432":{"source_id":"warehouse","database":"analytics"}}
```

Configure namespace mappings before receiving events. Later mapping changes do not automatically rename historical placeholders. Without a mapping, normalized namespace and database form an independent source; host ownership is not inferred.

Namespace and dataset name form the external identity and map to existing physical tables. Unknown datasets create placeholders. START, COMPLETE, and FAIL record run state and lineage. Duplicate job + runId + eventType deliveries do not create another record. A late START cannot overwrite a completed or failed state. The other standard types are accepted too: RUNNING is in progress like START; ABORT is terminal, never a success, and draws no lineage-graph edge; OTHER only adds metadata and never changes an observed state. Job integration details retain run history and the latest successful time.

The additional endpoints and object types preserve existing catalog filters and OpenAPI schemas. Start `uv run datakeel api` and visit `/api/docs` for the full current contract.

## Format references

- [Airflow REST API v1 (2.10.5)](https://airflow.apache.org/docs/apache-airflow/2.10.5/stable-rest-api-ref.html)
- [OpenLineage RunEvent](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md)
- [OpenLineage namespace and dataset naming](https://openlineage.io/docs/spec/naming/)
