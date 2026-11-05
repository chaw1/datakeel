# Persistence schema composition

`datakeel.persistence.migrate(database)` is an explicit demo/generated-fixture initializer.
For SQLite it delegates to `versioning`: only missing/empty stores initialize; current stores
validate and return, while known unversioned stores require `datakeel db upgrade`. API, worker,
ordinary database CLI and MCP perform admission only. The old API migration keyword cannot
bypass admission. Offline trace export retains its existing read-only path and never migrates.

`versioning` sits below the persistence composition root and above domain/storage adapters.
It owns frozen version targets, baseline/data validation, the system ledger, maintenance exclusion,
SQLite recovery packages and forward campaigns. It never calls latest metadata/installers on an
existing database. See [maintenance and recovery](DATABASE_MAINTENANCE.md).

`storage.database` owns engines/sessions and the legacy explicit empty-schema fixture transaction.
Its typed contribution initializer refuses nonempty databases. The neutral schema contracts and
mapping base remain in `core.schema`; `storage.base.Base` is the same base for legacy adapters.
Contributions assemble a specified schema; version definitions own production upgrades. Frozen
v1 SQL is independent of later model imports. The nullable helper has separate low-level tests.

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
no additional allowance is added. Total application and storage exception counts cannot increase.

`persistence/canonical_tables.json` is a byte copy of the independently frozen 99-table inventory,
including its original source-module provenance. It is never inferred from imported models or
rewritten to accommodate omissions. `make check-python-static` checks its frozen digest, all
transitional Row imports, storage lines/files, import exceptions and the 980-line schema budget.
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

The `persistence`, `versioning`, `dataset_store` and `worker_store` coverage owners each require 90%, alongside
the existing overall and critical-package coverage gates. Local targeted coverage reports do
not replace the complete two-stack CI gate.
