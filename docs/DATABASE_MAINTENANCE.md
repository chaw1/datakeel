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
fixtures and six-cell upgrade/restore qualification belong to the later slice. Versioned PostgreSQL
maintenance commands are refused; existing PostgreSQL applications retain W3 initialization and
idempotent startup. Ordinary CLI and evidence benchmark PostgreSQL entries run the W3 typed
initializer; worker and MCP entries reuse caller-initialized schemas. None runs SQLite admission
on PostgreSQL. This does not claim versioned PostgreSQL support. There are no new dependencies.

`status` parses only maintenance location settings, opens existing databases with `mode=ro`, and
never initializes the home, database or maintenance lock. General worker/model configuration cannot
prevent inspection. API, worker, MCP and ordinary database CLI commands require a verified current
SQLite store by default. `create_app(..., run_migrations=False)` skips migration and admission when
the caller already initialized its database; recovery and routes still need usable application
tables. Trace export retains its existing read-only path and never migrates. Demo and
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
The second version adds the three vector tables, their indexes and nullable shard lease, reaching
102 business tables plus the ledger. The third version adds the nullable task display rank and
rebuilds the claim-order index to cover it, keeping the same 102 business tables plus the ledger.
Baseline validation includes every user table,
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
do not edit a shared frozen file in place or add future files to V1's source list. The v2 entry points explicitly use `campaign_v2.py` and `inspect_v2.py`; the v1 runner and its
19-file closure remain byte-for-byte frozen. V2 binds both the reused frozen helpers and its own
runner, inspection, additive fact projection, handler and DDL artifacts in a separate checksum.
The v3 entry points explicitly use `campaign_v3.py` and `inspect_v3.py`; V3 reuses the frozen v2
helpers and the frozen shard alternate form, and binds its own runner, inspection, handler and
DDL artifact in a separate checksum without editing any v1/v2 closure file.
Changing any frozen helper rejects existing ledger checksums in both status and upgrade before
backup or forward execution. Restore the matching program sources or an independently verified
recovery point; never rewrite/re-sign applied ledger rows. Development databases made by the
incomplete pre-FIX1 checksum are likewise rejected and are not silently restamped.
Forward handlers use only the supplied connection, perform no external side effects and cannot
control transactions or attach databases. DDL, data, postcondition/fact checks and ledger insertion
commit together under `BEGIN IMMEDIATE`. The OS releases the campaign lock on process death;
it stays held across all version commits while a process is alive.


V2's complete `sqlite_b2.json` target was exported from a real empty SQLite database initialized
with typed schema contributions and every installer. Runtime upgrades load only this frozen target,
never latest `create_all`. SQLite's actual `ADD COLUMN` result retains old column order, so the
separately frozen `sqlite_b2_altered_shards.json` admits exactly that one equivalent physical form;
all other objects must still match the complete target. Extra columns, partial vector schemas,
missing indexes/triggers and unknown tables remain invalid.

V3's complete `sqlite_b3.json` target is exported the same way from the current typed schema.
`display_rank` is declared as the typed model's last column, so the real `ALTER TABLE` result
equals the typed export and needs no separate alternate; the only remaining physical duality is
the inherited `task_shards` form, which reuses the frozen `sqlite_b2_altered_shards.json`. The v3
forward adds the nullable column, drops the previous claim-order index and recreates it with the
display rank. Existing rows keep NULL ranks; the first claim per project backfills the persisted
display order idempotently under the project row lock, so the migration itself adds no facts.

Unversioned recognition checks all registered targets. A complete current 102-table baseline is
reported as `unversioned` / `sqlite-b3`; explicit upgrade validates its facts and stamps all three
ledger rows in one transaction without replaying any DDL. A complete v2-era baseline without the
display rank is still recognized as `sqlite-b2`, stamped, then runs the additive v3 step. A
complete 99-table baseline stamps v1 then runs the additive v2 and v3 steps. A v1 or v2 ledger is
`pending` until explicit upgrade. Neither startup nor ordinary initialization upgrades
pending/unversioned databases. Missing/empty file and memory fixtures apply v1, v2 then v3.
Already-current stores only validate and return; repeating upgrade creates no backup. Requesting
v1 or v2 on an unversioned v3 database is a refused downgrade, not a partial stamp.

The campaign checks every old column, SQLite row identity and blob byte before committing an
additive version. New tables must be empty and added fields must be NULL; existing vector facts,
non-NULL leases and NULL display ranks on a complete baseline are preserved during stamping. Full
target/data validation, fact checks and ledger insertion share the same transaction.
Latest-baseline stamping also rolls all ledger rows back together on failure. The public status
schema, recovery package format and restored-home isolation remain unchanged. PostgreSQL retains
W3 additive migration: the nullable rank is added at startup and the claim-order index converges
to the display-rank definition on the first migration after upgrade.

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
