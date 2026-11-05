# Persistence schema composition

`datakeel.persistence.migrate(database)` is the single application initialization entry point.
API, CLI, evaluation and test-template setup use it. Offline trace export still constructs a
read-only `storage.database.Database` and never migrates.

`create_app(database)` migrates by default. Callers that have already initialized the database
can explicitly use `create_app(database, run_migrations=False)`; they remain responsible for
providing the complete application schema. The scale ASGI workload uses this option after
fixture setup adds its benchmark fact table. Normal initialization still rejects unexpected
tables against the unchanged 99-table inventory plus the explicit three-table vector increment.

`storage.database` owns engines, sessions and the serialized migration transaction. It accepts
frozen `SchemaContribution` values and a separate `CanonicalSchema`; it imports no domain rows
or installers. The neutral contracts and mapping base are in `core.schema`; `storage.base.Base`
remains the same base object for legacy adapters.

Each contribution names one owner, an explicit order, a tuple of Row types and a tuple of typed
installers. The engine checks owners, orders, duplicate tables, table ownership and required
installers before opening the migration transaction. It then preserves the original lock,
`create_all`, nullable-column additions and installer sequence. A live table-set check runs
inside that same transaction after installation. Existing extra columns remain untouched.

`dataset_store` owns the dataset, version, lineage-event and metadata-change mappings.
`worker_store` owns task, shard and outbox mappings. Their modules contain schema only.
Dataset adapters, queue completion rules and all other business behavior remain in their
existing packages. Old storage adapters can import the new Row modules only along the exact
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

The `persistence`, `dataset_store` and `worker_store` coverage owners each require 90%, alongside
the existing overall and critical-package coverage gates. Local targeted coverage reports do
not replace the complete two-stack CI gate.
