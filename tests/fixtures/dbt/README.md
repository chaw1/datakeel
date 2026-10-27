# Generated dbt artifacts

These artifacts were generated from the fictional project in `project/` using
dbt-core 1.8.9 and dbt-duckdb 1.8.4, both Apache-2.0 licensed. The project does
not require external data or services. dbt is a fixture-generation tool only.

From a copy of `project/`, run in an isolated development environment:

```sh
DBT_SEND_ANONYMOUS_USAGE_STATS=false DO_NOT_TRACK=1 dbt build --profiles-dir profiles
cp target/run_results.json build_run_results.json
DBT_SEND_ANONYMOUS_USAGE_STATS=false DO_NOT_TRACK=1 dbt docs generate --profiles-dir profiles
```

`manifest.json` and `catalog.json` come from `docs generate`;
`run_results.json` comes from the successful build, including three passing data
tests. Absolute development paths were replaced with portable placeholders.
The manifest's unrelated bundled macro and documentation collections were emptied;
all project resource declarations, compiled SQL and quality evidence are retained.

The source and seed intentionally identify the same physical `raw_orders` table.
The `orders` model intentionally uses the quoted physical alias `Orders Daily`.
