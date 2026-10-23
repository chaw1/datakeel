# Fictional Kitchen Co.

Generate the entire local enterprise fixture with:

```bash
uv run python -m examples.enterprise.generate
```

`--output /path/to/directory` selects another output directory. The default is
`examples/enterprise/generated/`, which is ignored by Git. The generator is also
packaged as `datakeel.sample_enterprise.generate_enterprise` for the demo command.

The four sources contain 20 tables, four views, and 51,992 rows. They represent
ERP, CRM, ecommerce, and after-sales data; all names and records are synthetic.
Each view explicitly selects at least five source fields for lineage extraction.
Primary keys and local foreign keys are valid. No source requires a network.
Generating again produces byte-identical `.dump` exports and `gold.json`, as
required by D3. The SQLite files also match under the same Python/SQLite runtime.

The reference instant is 2026-10-01T00:00:00Z. “上个季度” means the half-open interval
2026-07-01 through 2026-10-01; “近30天” means 2026-09-01 through 2026-10-01.
Amounts are integer yuan. `gold.json` is calculated directly from Python rows;
it does not read the semantic YAML, compiler, ask parser, or SQL executor.

`contracts/semantic-layer/` contains 13 metrics, 12 dimensions, and 32 glossary
entries. Shipment amount, booked sales amount, and terminal retail amount use
different source fields, status filters, and owners. The shared synonym “营业额”
deliberately requires clarification. `contracts/ask/questions.yaml` defines
14 answerable questions, four unsupported questions, and two clarification cases.
