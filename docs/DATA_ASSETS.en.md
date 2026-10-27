# Publishing and using data assets

[中文](DATA_ASSETS.md)

A data asset packages an existing dataset (optionally pinned to a version), catalog table or semantic metric. Its card holds bilingual names, business definition, owner, classification, tags, synonyms, scenarios, instructions and a manually sanitized sample. Keep private source data out of published card text. Creation, editing, publication and withdrawal retain immutable revisions. An existing card cannot be retargeted.

The asset market supports name, synonym, tag and owner searches, classification and tag filters, and deterministic sorting. Details aggregate quality and its trend, upstream/downstream lineage, source freshness, related metrics, uses and users. For multiple sources, quality uses the lowest measured source score. The trend starts once all sources with quality evidence have observations, then updates at source-version timestamps. Unknown sources receive no invented score. Missing evidence is shown as unavailable; empty release and standards extensions stay hidden. Withdrawn cards disappear from the default market but retain their underlying access policy. Drafts do not establish read policies.

All card changes prepare ordinary controlled action plans and require explicit execution after review; reversible operations keep the existing automatic approval policy. Changing a published or withdrawn request/restricted card to public or internal opens reading to everyone, so that edit requires human approval and is never executed automatically by the Agent. An application declares purpose, query/export/download scopes and an aware expiry. Approving or rejecting an application and revoking a grant require separate human-approved controlled actions. A grant binds its subject, asset, exact scopes, creation/expiry times and revocation status. Expiry is evaluated on every read without a cleanup job. If several protected cards cover one accessed resource, every policy must authorize it.

Operator identifiers are local attribution, not authentication. Web questions default to `local-user` and expose an operator field. Agent and MCP use the existing `local` actor, overriding nested question parameters. Apply as the same operator used for reading. HTTP downloads, exports, saved-answer replay and evidence reads accept `X-Datakeel-Actor`, defaulting to `local-user`. This service does not provide an identity boundary for untrusted remote users.

Public and internal cards allow reads with usage audit; request and restricted cards require a current grant for the required scope. Questions check the resolved metric and compiled table/column dependencies before SQL execution. Native tools, HTTP and controlled exports, and downloads share one guard. Registered lineage, manifests and catalog ownership resolve derived resources to underlying policies. Unversioned reads conservatively match all protected versions; exact versions preserve version boundaries. Protecting a metric does not automatically protect unrelated reads that do not use it.

Evidence candidates, graph queries, relation explanations, frozen source text, and metadata in file/version listings, object-set evaluations and task artifacts use query scope and the `ask` audit entry. Corrected image pixels use download scope and the `download` entry. Source-bearing action previews, saved plans and receipts also check current authorization. Export plans use export scope; other plans use query scope. Collections return only currently readable plans while retaining stored history. Graph run listings return only reports of currently readable sources, because report samples quote extracted text. Lineage file, graph entity and transcript nodes quote source content; a view containing an unreadable protected source is denied with an application hint, while catalog metadata nodes such as tables, fields and metrics stay visible like asset cards. Controlled-action reads keep the existing `local` operator default and accept the same HTTP actor header. Nested Agent/MCP source reads only check authorization; the outer tool records one successful use per matched asset.

Saved answers, tool caches, delegated caches and Agent message idempotency replays check current authorization again. After revocation, provider requests and public conversation/memory reads exclude inaccessible historical tool results, derived replies and events; original user speech remains. Memory use stores resource attribution without memory text, so hard deletion of the memory entry does not remove the authorization basis for old derived replies. Original stored history and append-only audit remain intact; user-authored global memory without provenance has no reliable asset identity to infer.

Audit contains operator, asset, actual entry, scope, UTC timestamp and grant ID; unrestricted uses without a grant have a null grant ID. Query audit by asset or person in the detail and global audit views. SQLite and PostgreSQL triggers reject updates and deletes of usage, card revisions and application/grant decision history. Market metrics describe observed use and lineage, without subjective business valuation.

[`contracts/assets/ranking.yaml`](../contracts/assets/ranking.yaml) defines ranking. Default popularity is uses + 2 × users + downstream dependencies, descending; ties use source update time descending and asset ID ascending. Freshness sorts age ascending, quality sorts score descending, downstream sorts count descending, and name sorts case-insensitively ascending. Unknown values sort last; all share the same stable ties. This release uses the fixed default contract and does not expose custom weight configuration. Invalid contracts fail explicitly. Card copy edits do not reset source freshness.

Inspect `/api/docs` for schemas. The market and detail routes are `/api/data-assets` and `/api/data-assets/{id}`. Submit with `POST /api/data-assets/{id}/applications`; query `/applications`, `/grants`, `/audit`, card `/history` and `/control-history`. The six controlled actions are `create_data_asset`, `update_data_asset`, `publish_data_asset`, `withdraw_data_asset`, `decide_asset_application` and `revoke_asset_grant`, using the existing prepare, approve and execute endpoints.

CLI commands use the same models and service:

```sh
uv run datakeel data-assets list --search Shipment
uv run datakeel data-assets show ASSET_ID
uv run datakeel data-assets prepare create_data_asset definition.json
uv run datakeel data-assets execute PLAN_ID --digest PLAN_DIGEST
uv run datakeel data-assets apply application.json --applicant local
uv run datakeel data-assets prepare decide_asset_application decision.json
uv run datakeel data-assets approve PLAN_ID --digest PLAN_DIGEST
uv run datakeel data-assets execute PLAN_ID --digest PLAN_DIGEST
uv run datakeel data-assets audit --actor local
```

`definition.json` contains `{"definition":{"target":{"asset_type":"metric","asset_id":"shipment_amount"},"name":"Shipment amount","owner":"Data owner","classification":"request"}}`. An application JSON contains `asset_id`, `purpose`, `scopes:["query"]`, and a future timezone-aware `expires_at`. A decision contains `application_id`, `approve:true`, and an optional reason. See the [demo tour](DEMO.en.md) for the complete flow.
