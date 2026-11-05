# Persistence schema composition

`datakeel.persistence.migrate(database)` is the single application initialization entry point.
API, CLI, evaluation and test-template setup use it. Offline trace export still constructs a
read-only `storage.database.Database` and never migrates.

`create_app(database)` migrates by default. Callers that have already initialized the database
can explicitly use `create_app(database, run_migrations=False)`; they remain responsible for
providing the complete application schema. The scale ASGI workload uses this option after
fixture setup adds its benchmark fact table. Normal initialization still rejects unexpected
tables against the unchanged 99-table canonical inventory.

`storage.database` owns engines, sessions and the serialized migration transaction. It accepts
frozen `SchemaContribution` values and a separate `CanonicalSchema`; it imports no domain rows
or installers. The neutral contracts and mapping base are in `core.schema`; `storage.base.Base`
remains the same base object for legacy adapters.

Each contribution names one owner, an explicit order, a tuple of Row types and a tuple of typed
installers. The engine checks owners, orders, duplicate tables, table ownership and required
installers before opening the migration transaction. It then preserves the original lock,
`create_all`, nullable-column additions and installer sequence. A live table-set check runs
inside that same transaction after installation. Existing extra columns remain untouched.

`dataset_store` owns dataset, version, lineage-event, metadata-change, file-state,
file-discovery/checkpoint and upload mappings and their existing SQL adapters. `datasets`
contains frozen input/read/publication models and pure OpenLineage projections. `semantic`
is shared pure code below the domains. `worker_store` still contains only task, shard and
outbox schema; queue completion rules remain in storage. Old storage adapters import Rows only along the exact
baseline edges recorded in `contracts/persistence/schema-baseline.json`. These are temporary
private implementation references, removed with each adapter's migration slice. Row types and
sessions remain forbidden in domain interfaces and public ports.

`persistence.legacy_rows` retains the historical immutable model tuple and explicit imports.
`persistence.legacy` assembles all owners, including temporary contributions for domains whose
migration slices have not started. These modules perform no discovery or mutable registration.
The evaluation initializer imports its engine class and migration entry from the composition
root. Its existing database-initialization allowance is retargeted to that root one for one;
no additional allowance is added. Total application and storage exception counts cannot increase.

`persistence/canonical_tables.json` is a byte copy of the independently frozen 99-table inventory,
including its original source-module provenance. It is never inferred from imported models or
rewritten to accommodate omissions. `make check-python-static` checks its frozen digest, all
transitional Row imports, storage lines/files, import exceptions and the 980-line schema budget.
Dataset adapters and pure contracts have a separate 4022-line budget; moved file Rows count
there, while the original schema composition files remain under their original 980-line gate.
An independent reviewer also supplies the candidate-external canonical copy:

```sh
uv run python -m scripts.check_schema --canonical /path/to/canonical-tables.frozen.json
```

`python -m scripts.export_ddl URL` reads an already existing database without initializing it.
The snapshot contains database version, column types/defaults/nullability, primary and foreign
keys, unique/check constraints, indexes, SQLite raw schema and pragmas, and PostgreSQL catalog
index predicates, triggers, functions, sequences and views. DDL acceptance compares independently
frozen before/after exports on each database stack. A successful SQLite comparison cannot stand
in for PostgreSQL execution. Exporter normalization must pass repeated-baseline checks before
its snapshots can establish equality.

The `persistence`, `datasets`, `dataset_store` and `worker_store` coverage owners each require 90%, alongside
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
