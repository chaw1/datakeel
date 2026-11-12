# Persistence schema composition

`datakeel.persistence.migrate(database)` is an explicit demo/generated-fixture initializer.
For SQLite it delegates to `versioning`: only missing/empty stores initialize; current stores
validate and return, while known unversioned stores require `datakeel db upgrade`. API, worker,
ordinary database CLI and MCP perform SQLite admission only. `create_app` defaults to checking
SQLite and running the existing W3 PostgreSQL initializer. `run_migrations=False` skips both
migration and admission for a caller-initialized store, including scale fixtures. Offline trace
export retains its existing read-only path and never migrates.

Ordinary CLI and evidence benchmark PostgreSQL entries use the same W3 typed contributions and
canonical schema as the API. SQLite benchmarks use versioned initialization; ordinary SQLite CLI
commands retain strict admission. The early `migrate` maintenance alias remains SQLite-only and
emits the same JSON rejection and exit code 3 on PostgreSQL. Normal initialization rejects unexpected
tables against the unchanged 99-table inventory plus the explicit three-table vector increment.

`versioning` sits below the persistence composition root and above domain/storage adapters.
It owns frozen version targets, baseline/data validation, the system ledger, maintenance exclusion,
SQLite recovery packages and forward campaigns. It never calls latest metadata/installers on an
existing database. See [maintenance and recovery](DATABASE_MAINTENANCE.md).

`storage.database` owns engines/sessions and serialized typed contribution initialization.
SQLite initialization refuses nonempty databases. PostgreSQL retains W3 initialization and
idempotent installers for complete canonical stores, including additive nullable columns;
partial tables, unknown tables and views are refused before DDL. The neutral schema contracts and
mapping base remain in `core.schema`; `storage.base.Base` is the same base for legacy adapters.
Contributions assemble a specified schema; version definitions own production upgrades. Frozen
v1/v2 SQL is independent of later model imports. V2 freezes the full real SQLite typed result
(102 tables), plus the exact ALTER lease-column layout. Production v2 upgrades only add the three
vector tables/indexes and nullable lease; existing v2 baselines receive an atomic ledger-only stamp.
Both file and memory empty initialization apply every version. The nullable helper has separate
low-level tests and remains the PostgreSQL W3 additive path.

`dataset_store` owns dataset, version, lineage-event, metadata-change, file-state,
file-discovery/checkpoint and upload mappings and their existing SQL adapters. `datasets`
contains frozen input/read/publication models and pure OpenLineage projections. `semantic`
is shared pure code below the domains. `worker_store` owns task, shard and outbox mappings, queue leases, terminal transitions and
frozen task projections. Completion domain wiring lives in `persistence.task_completion`. Old storage adapters import Rows only along the exact
baseline edges recorded in `contracts/persistence/schema-baseline.json`. These are temporary
private implementation references, removed with each adapter's migration slice. Row types and
sessions remain forbidden in domain interfaces and public ports.

`persistence.legacy_rows` retains the historical immutable model tuple and explicit imports.
`persistence.legacy` assembles all owners, including temporary contributions for domains whose
migration slices have not started. These modules perform no discovery or mutable registration.
The evaluation initializer imports its engine class and migration entry from the composition
root. Its existing database-initialization allowance is retargeted to that root one for one;
no additional allowance is added for the original schema migration. E2 adapter increments are
separately enumerated below; unlisted paths and Row imports remain rejected.

`persistence/canonical_tables.json` is a byte copy of the independently frozen 99-table inventory,
including its original source-module provenance. It is never inferred from imported models or
rewritten to accommodate omissions. `make check-python-static` checks its frozen digest, all
transitional Row imports, storage lines/files, import exceptions and the 980-line schema budget.
Dataset adapters and pure contracts have a separate 4022-line budget; moved file Rows count
there, while the original schema composition files remain under their original 980-line gate.
The E2 additions remain separate: `persistence/vector_tables.json` assigns three tables to
`vector_store`; `persistence/vector.py` provides their frozen `SchemaContribution`. Existing
owners and installer order stay unchanged. `worker_store.rows.ShardRow` owns the nullable
`lease_expires_at` addition. `contracts/persistence/we-e2-extension.json` independently pins
the vector inventory digest and lists each added storage path, transitional Row edge, import
exception and finite source-line increment. The original baseline and 99-table oracle remain
byte-identical; there is no discovery or blanket storage/schema exemption.

`contracts/persistence/we-e2-ddl.json` retains the 99-table DDL compiled from the preceding
main revision and the exact three-table/lease increment for SQLite and PostgreSQL. Tests compare
all tables, indexes and constraints against that fixture and exercise an existing SQLite shard
through repeated additive migrations. PostgreSQL compilation is an offline oracle, not live
PostgreSQL migration evidence.

Later slices append their own explicit DDL inventories instead of editing the frozen E2 oracle.
`contracts/persistence/b8-ddl-increment.json` carries the nullable `production_tasks.display_rank`
column compiled for both dialects; the same DDL guard merges it over the E2 baseline and
increment. The claim-order index itself is installer-owned: its display-rank definition is frozen
in the SQLite v3 target and PostgreSQL converges it at startup, each covered by its own
regression.

An independent reviewer also supplies candidate-external canonical copies:

```sh
uv run python -m scripts.check_schema --canonical /path/to/canonical-tables.frozen.json \
  --vector-canonical /path/to/vector-tables.frozen.json
```

`python -m scripts.export_ddl URL` reads an already existing database without initializing it.
The snapshot contains database version, column types/defaults/nullability, primary and foreign
keys, unique/check constraints, indexes, SQLite raw schema and pragmas, and PostgreSQL catalog
index predicates, triggers, functions, sequences and views. DDL acceptance compares independently
frozen before/after exports on each database stack. A successful SQLite comparison cannot stand
in for PostgreSQL execution. Exporter normalization must pass repeated-baseline checks before
its snapshots can establish equality.

The `persistence`, `versioning`, `datasets`, `dataset_store` and `worker_store` coverage owners each require 90%, alongside
the existing overall and critical-package coverage gates. Local targeted coverage reports do
not replace the complete two-stack CI gate.

## Dataset transactions and transitional wiring

Application calls use `dataset_store.dataset_service`, `upload_service`, `lineage_service`,
`object_queries`, `profile_queries`, `metadata_store`, `openlineage_store`, `search` and
`version_diff`; database-scoped entry points return frozen models. Publication returns
`PublishedDataset`, configuration reads return `DatasetSettings`, and mutable SQL rows stay
inside adapters. Existing session-bound helpers such as `require_dataset`, `dataset_dict`,
`latest_files` and production row ordering remain internal implementation calls for the listed
legacy adapters. They are not domain ports. These consumers only change imports in this slice;
their behavior migrates with their owning batch. No compatibility module remains in storage.

The dataset contribution contains all eight owned tables and both original installers.
File discovery and lineage installation retain their historical global order. The canonical
owner/provenance artifact is unchanged. Pure datasets, lineage, governance, quality and semantic
code cannot import persistence; dataset adapters cannot import API, worker, CLI or MCP.
Pure rule layers sit below adapters. Remaining upward calls to legacy access, evidence,
catalog, production and object backend adapters are individually listed in `.importlinter`;
application and storage exception totals must still decrease or remain unchanged.

| Attempt | Transaction owner | Work before commit | Work after commit |
| --- | --- | --- | --- |
| Dataset create/import | `create_dataset` / `import_paths` | Objects, dataset flush, version/discovery flush, lineage append | Temporary import cleanup |
| Upload declaration | `start_upload` | Upload lock, write lock, declaration/idempotency check | None |
| Upload completion | `complete_upload` | Existing upload lock; prepare/verify bytes outside writer session; dataset/version/lineage and receipt in one writer session | Discard chunks; retry repeats cleanup |
| OpenLineage observation | `ingest_openlineage` | Write/catalog locks, observation and catalog projections | Frozen receipt |
| Metadata import | `publish_metadata` / `publish_metadata_from_prior` | Write/catalog locks, snapshot and optional run event | Frozen report |
| Export/download authorization | Existing database-scoped service | Existing access audit and read projection | Materialize authorized object |
| Legacy controlled action / worker attempt | Existing action / worker service | Session-bound dataset helpers only flush | Existing receipts/deferred callbacks |

Helpers never commit for their caller. Failed publication rolls back database facts and keeps
previously persisted content-addressed bytes, matching the prior implementation. Failed-action
audits, reaper lease transactions and deferred/post-commit work retain their existing owners.
`tests/dataset_store/test_publication_boundary.py` injects failures after version/discovery,
lineage and receipt writes; the same tests run on both CI stacks. They verify no partial facts,
retained retry input and objects, no successful commit on failure, and one retry commit.


## Worker completion transactions

Applications construct `persistence.task_queue.DatabaseQueue`; `worker.queue` retains the existing
application export. `worker_store.task_queue` owns each writer session and binds a
`TaskCompletionPort` through its injected composition factory. `CompletionRequest` and
`CompletionResult` are frozen, extra-forbid models. Requests carry task identity, associated run/job
IDs and typed products; no Row, Session or untyped mapping crosses that port. Session-bearing
factory and submission-validator callbacks are private constructor wiring, not domain ports.

The composition root alone selects pipeline/evidence, KG, DQ or datasheet publication. It rejects
multiple or empty associations, products without a stored association, missing successful
products and mismatched product types/identities. Existing handler checks still verify actual
job ownership, frozen rule/scope and checked datasheet content. No kind column is introduced.
Queue and terminal modules contain no concrete completion handlers or domain routing helpers.
The port returns the existing terminal operator/display name and generic version-publication
policy. Task queries return frozen task/shard views and keep SQL rows inside the store.

| Attempt | Transaction owner | Ordered work | Following transaction |
| --- | --- | --- | --- |
| Finish, including explicit failure | Queue `finish` | Write lock, parent lock, shard lock/owner and heartbeat fence, bound domain publication, shard output/events, flush, aggregate terminal/domain failure and outbox, flush, bound recovery, commit | Existing action reconciliation/receipt |
| Cancel | Queue `cancel` | Parent lock, terminal guard, sibling fencing, bound domain failure, terminal/outbox, flush, bound recovery, commit | Existing action reconciliation/receipt |
| Reap | Queue `reap`, then each `finish` | Classify expired leases through the bound typed port and commit ordinary requeues first; finish each terminal lease with a fresh parent/shard and cutoff fence | Existing relay/reconciliation |
| Relay / reconcile | Existing queue relay / action reconciler | Each retains its own idempotent receipt/event transaction | No domain adapter commits |

A domain adapter only flushes through its bound session; it never commits, relays or reconciles.
Failure after the terminal outbox SQL write rolls back all generated table facts and leaves the
lease retryable. Four-kind regressions assert one retry commit, no receipt before reconciliation,
one later action receipt, immutable finish time and no publication by duplicate or stale leases.
Existing failure audits, deferred action callbacks and post-commit reconciliation remain in
their original services; action-worker migration belongs to a later slice.

Worker adapters and all four task composition modules share a separate 1096-line budget; the original
980-line schema and 4022-line dataset budgets remain fixed. `worker`, `worker_store` and
`persistence` retain coverage responsibility for completion wiring. The worker store sits above
dataset adapters and below domain services; only its two neutral engine imports and existing
pipeline validation imports have temporary layer allowances. Application/storage exception
counts and storage lines/files remain ratcheted downward. Tests retain their existing node IDs;
new completion modules add measured scheduling durations without removing prior hints.

Vector completion authorization and whole-DAG validation live in `persistence.task_vector`,
using a typed plan read from the session-bound storage adapter. The publication request carries
its frozen pipeline and fenced shard identity. Any vector failure discards every new pending
product and shard output. A separate `recover` call runs only after terminal state/outbox have
been flushed in the queue transaction: SENDING becomes UNKNOWN; only RESERVED is refunded.
A later write failure rolls back publication, terminal/outbox and recovery together.

`ExpirationResult` makes vector attempts immediately terminal with
`vector_lease_expired_outcome_unknown`, even if their DAG was removed. Ordinary leases retain
max-attempt requeue policy. Claim and heartbeat continue refreshing `lease_expires_at`.
Direct vector submissions are rejected at `persistence.task_queue.DatabaseQueue.submit` before
any database/idempotency lookup. No cancel/reaper path sends a request.

Public task query/list consumers use `persistence.task_queries`, which composes the pure
worker-store projection with the optional typed vector report. Completed partial vector results
retain `partial=true`. The removed storage submission/views/completion modules have no shims.
The E2 extension retires their storage/import allowances and allocates the smaller remaining
increment to typed vector authorization reads and report identity detection; no cap increases.
