# SQLite database maintenance

Stop API, worker, demo, schedulers and supervisors, and freeze all writers before an upgrade.
Keep them stopped until upgrade succeeds and the operator decides to restart them. The maintenance
file lock serializes upgrade campaigns; it cannot fence a historical binary or an unrelated writer.
Use one canonical database pathname and one home for the entire campaign.

```sh
datakeel db status
datakeel db upgrade                 # latest registered version
datakeel db upgrade --to 1
datakeel migrate                    # exact compatibility alias of db upgrade
```

S2 supports file SQLite and LocalStore only. PostgreSQL versioning, S3 export, historical release
fixtures and six-cell upgrade/restore qualification belong to the later slice. PostgreSQL service
admission is refused by this slice; the existing explicit empty PostgreSQL fixture initializer is
retained, without claiming versioned PostgreSQL support. There are no new dependencies.

`status` parses only maintenance location settings, opens existing databases with `mode=ro`, and
never initializes the home, database or maintenance lock. General worker/model configuration cannot
prevent inspection. API, worker, MCP and ordinary database CLI commands require a verified current
store. The retained `create_app(..., run_migrations=...)` keyword never authorizes migration or
skips admission. Trace export retains its existing read-only path and never migrates. Demo and
generated fixtures explicitly initialize missing/empty stores; they refuse known unversioned stores.

Every maintenance command emits exactly one JSON document, including argument errors. `--json`
is accepted for compatibility but JSON is always used. The frozen schema is
`versioning.models.DatabaseStatus.model_json_schema()`:

| Field | Meaning |
| --- | --- |
| `format_version` | `1` |
| `state` | `missing`, `empty`, `unversioned`, `current`, `pending`, `ahead`, `invalid`, `isolated` |
| `baseline`, `version`, `pending` | Verified semantic class, committed prefix and remaining versions |
| `release_source` | `unknown`; no release provenance is inferred |
| `ledger_healthy`, `minimum_reader` | Ledger integrity and registered reader requirement |
| `error`, `exit_code` | Classified failure, or null/0 |
| `backup_manifest`, `applied` | Recovery point used by this invocation, and versions it committed |

| Exit | Meaning |
| --- | --- |
| 0 | Successful status/upgrade/restore, including already current |
| 2 | Invalid arguments, unknown target, or requested downgrade |
| 3 | Unknown/mixed/corrupt schema, bad ledger/checksum or invalid location/configuration |
| 4 | Recovery package creation/verification/restore failed; no migration starts |
| 5 | A version failed; that version is rolled back, earlier committed versions remain |
| 6 | Recovery isolation, unsupported newer schema, or insufficient reader capability |

The first registered version creates the frozen 99-table `sqlite-b1` schema and its empty-store
file-discovery checkpoint, or stamps a fully matching unversioned baseline without changing facts.
It adds the explicit `datakeel_schema_versions` system table, with immutable update/delete triggers.
The table-owner inventory remains 99 business tables. Baseline validation includes every user table,
column, constraint, index, view and trigger, SQLite integrity/FK checks, valid JSON and the frozen
business invariants. SQL whitespace normalization preserves quoted contents. Different legal rows
and empty facts belong to the same class. No historical release mapping is asserted by S2.

Version definitions declare source/target semantics, minimum reader, handler, explicit fact-preservation
policy, source closure and checksum. V1's `checksum_sources` lists 19 complete source/data files:
its DDL snapshot and `v1.py`, the full `inspect.py` baseline/JSON/SQL/fact/ledger helpers,
`campaign.py` transaction guard and postchecks, boundary models, and the transitive local
lock/location/recovery/configuration/reference helpers (including their core/routing dependencies).
The hash frames each path and byte length before its complete bytes, then binds the serialized
version, source/target, reader, fact policy and source list. It never hashes just callable names.
Program release provenance (`__version__`), package entry-point wiring and the mutable registry
are outside the migration semantics; no latest ORM/contribution code supplies the target.

All files in an applied version's closure are frozen, including shared helpers and defaults.
Add future definitions in separate files and append registrations without editing that closure.
If a future version needs different inspection, mapping or campaign semantics, retain the old
implementation and introduce a separately versioned helper/runner/model set with explicit dispatch;
do not edit a shared frozen file in place or add future files to V1's source list. The current S2
runner supports its one production version; a future engine dispatch requires its own validation.
Changing any frozen helper rejects existing ledger checksums in both status and upgrade before
backup or forward execution. Restore the matching program sources or an independently verified
recovery point; never rewrite/re-sign applied ledger rows. Development databases made by the
incomplete pre-FIX1 checksum are likewise rejected and are not silently restamped.
Forward handlers use only the supplied connection, perform no external side effects and cannot
control transactions or attach databases. DDL, data, postcondition/fact checks and ledger insertion
commit together under `BEGIN IMMEDIATE`. The OS releases the campaign lock on process death;
it stays held across all version commits while a process is alive.

With pending work, the idle independent source connection's SQLite backup includes committed WAL
facts. The package contains `database.sqlite`, all nested JSON/dedicated-column `object_key` and
`ledger_key` references copied from LocalStore, and actual relocatable configuration/routing
contents. Secret settings and URL credentials are represented only by names; credentials must be
supplied separately. Configuration is a recovery record, never automatically activated.
Each component has a size and SHA-256; verification re-enumerates references from the snapshot.
Missing objects, unsafe paths, truncated manifests and changed hashes fail closed.

A deterministic source inode/path plus registry-checksum campaign directory prevents duplicate
backups after failure, death or contention. Retrying re-verifies the same package and committed
prefix, including its fact fingerprint. No pending work creates no package. Partial package creation
also fails closed: preserve it for diagnosis and restore/rebuild an independently verified recovery
point before retrying; the tool does not silently discard evidence. Changing the registry starts a
new campaign. To use an existing package explicitly:

```sh
datakeel db upgrade --backup-manifest /path/to/package/manifest.json
```

Restore only into a new directory:

```sh
datakeel db restore --manifest /path/to/package/manifest.json --home /path/to/new-recovery-home
```

The restored home contains `datakeel.db`, object copies, configuration and a persistent
`recovery-isolation.json` marker. Worker, service, demo, scheduling, queue relay and webhook relay
admission refuse that marker, including direct scheduler/relay calls. Failed copy verification
leaves a marked, unusable home. Do not remove the marker to run acceptance: use read-only checks,
a separate fake-transport test harness, and another disposable isolated copy for safe local writes.
Keep all services/supervisors disabled and manually reconcile tasks, leases, consumed approvals,
receipts, lineage outbox and `dq_webhook_outbox`, plus effects already sent after the recovery point.
Restoring cannot retract external effects. Historical readers must be operationally disabled on the
upgraded active database and may read only their matching recovery copies. S2 does not claim the
historical-reader or external-effect replay qualification reserved for the later slice.
