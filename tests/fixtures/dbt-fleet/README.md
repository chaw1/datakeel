# Generated multi-version dbt artifacts

These artifacts come from the fictional project in `project/`, built with three
isolated development environments (all Apache-2.0 licensed):

| Directory | dbt-core | dbt-duckdb | Manifest schema |
|---|---|---|---|
| `v10/` | 1.6.18 | 1.6.2 | v10 |
| `v11/` | 1.7.19 | 1.7.5 | v11 |
| `v12/` | 1.9.4 | 1.9.3 | v12 |

The project needs no external data or services. dbt is a fixture-generation tool
only and is not a Datakeel dependency. For v12, copy `unit/unit_tests.yml` into
`models/` first; earlier manifest versions have no unit-test collection. Then run:

```sh
DBT_SEND_ANONYMOUS_USAGE_STATS=false DO_NOT_TRACK=1 dbt build --profiles-dir profiles
cp target/run_results.json build_run_results.json
DBT_SEND_ANONYMOUS_USAGE_STATS=false DO_NOT_TRACK=1 dbt docs generate --profiles-dir profiles
```

`manifest.json` and `catalog.json` come from `docs generate`; `run_results.json`
comes from the build. Absolute development paths were replaced with `/project`,
invocation identities were zeroed, and the bundled macro and documentation
collections were emptied. Project resources, compiled SQL and results are kept.

The project deliberately covers shapes absent from the `dbt/` fixture: sources
with physical identifiers that are also seeds, source-level owner metadata, a
custom staging schema, an ephemeral model inlined as a CTE, `select *` through a
CTE, a model alias, an incremental model, a check snapshot, a singular test that
warns, a relationships test with two parents, an exposure owned only by email, a
simple metric and a filtered metric.
