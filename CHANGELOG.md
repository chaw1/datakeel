# Changelog

All notable changes are documented here using the Keep a Changelog format.

## [Unreleased]

## [0.12.0] - 2026-10-25

### Added

- Image and scan knowledge extraction through a separate, versioned transcript asset followed by the existing text pipeline. OCR, OpenAI-compatible visual endpoints, native Ollama, offline replay and scripted fixtures share explicit OCR/VLM modes, per-file overrides and quality failures. Only transcript blocks use the image prompt; text documents keep their existing cache and extractor identities.
- OCR-grounded image evidence with multiple rectangles, transcript evidence/head/tail highlights, structured unlocated and handwritten-name review reasons, source APIs and deterministic evidence rebuilding. Extracted relationships remain candidates until reviewed.
- Independent transcription consent estimates and fingerprints, metadata-free EXIF-corrected pixels with transparent areas composited on white, durable transcript reuse and budget traces. Either outbound endpoint requires human approval before any model executes. Reports show transcription and extraction costs separately.
- Per-image typed failures for missing recordings, missing OCR packages, missing API keys, mode mismatches, undecodable or oversized images and provider quota exhaustion; other images and text documents continue and the document is marked partial.
- A packaged 60-image offline benchmark with recording and persisted-product scores, per-group/language metrics, OCR/transcription quality measurements and external case directories. Both localization views enclose a relationship's rectangles in one bounding rectangle. Original image bytes and model attributions are preserved.
- Bilingual image demo, source drawers, route/failure reports, an explicit transcription choice for images without demo recordings, and approval cards, plus three image goldens and three regression mutations.

### Changed

- Version advances to 0.12.0. Core runtime requirements remain unchanged. OCR packages (RapidOCR, ONNX Runtime and OpenCV) are installed by users and are not Datakeel dependencies; see `docs/KG.md` for their licensing notes. Automatic routing, cloud localization, handwriting benchmarks and the redrawn diagram are deferred.

### Fixed

- The related-knowledge heading on the Ask page meets the 18px serif typography rule.

## [0.11.0] - 2026-10-25

### Added

- Deterministic, reviewable `link.maps_to` associations between graph entities and catalog tables, views or semantic metrics. Publication, catalog refresh and semantic changes rerun associations; human link decisions survive dataset and catalog versions.
- Bilingual owner, upstream, downstream and responsibility questions through the existing HTTP, CLI, Agent and MCP `ask_data` entry points. Answers separate system records from document claims and preserve evidence fragments, source documents, review labels, verification and consistency markers.
- Knowledge answer cards, entity association review and asset navigation, plus an association filter for bulk review. Metric-value answers include up to five related claims without changing their numeric behavior.
- Six fictional enterprise documents and an attributed offline recording in the demo. Separate initial and reviewed knowledge evaluations include 23 cases each, while the original 20 metric cases keep their own fixture and statistics. Four additional JSON-asserting goldens bring the suite to 40, and knowledge mutations bring the mutation suite to 35.
- Regression mutations detect reversed catalog hierarchy, source/result slots with topic references, and grouping dimensions incorrectly routed to knowledge.
- Independent development and held-out language corpora with 226 knowledge questions and 64 metric counterexamples, plus focus, direction and numeric-safety regression mutations.

### Changed

- Package, API and frontend versions advance to 0.11.0. OpenAPI additions preserve existing metric fields; runtime dependencies are unchanged and enterprise replay resources ship in wheels.

### Fixed

- Compose bilingual knowledge intents from subjects, relationship words and fillers; prioritize numeric/ranking questions and refuse unsupported knowledge phrasing instead of returning unrelated values. Compare complete subject names across catalog and graph entities before scanning, and preserve identifier and metric-suffix boundaries.
- Retain document relationships when the other endpoint's association is rejected, show unresolved association counts in every answer state, and audit knowledge clarifications and refusals. Association reads filter unrelated assertions and events in SQL.
- Distinguish same-name graph candidates by source dataset and entity type, localize relationship labels, and omit metric-only match evidence on knowledge cards. Shared matching vocabulary and YAML review decisions replace duplicated rules and fixture identities in code.
- Resolve knowledge direction from the interrogative's source or result role, including topic references, missing-source impacts and flow destinations. Recognize neutral catalog relations and list commands, and preserve metric routing for grouped dimensions and dated metric requests.
- Recognize explicit destination complements and dashboard display consumers while preserving scalar-value requests.
- Infer default knowledge direction from table, view and metric levels; recover requested noun-phrase heads separated from question words and prefer explicit active, passive and nominal input/result roles, including usage questions with who or 谁. Bound focus and direction to the main question while preserving subject coordinates and supported pronoun references.
- Recognize bilingual hierarchy, flow and impact expressions through shared vocabulary. Catalog-object count questions return typed lists and separate system/document counts while business measurements retain numeric routing. Use linked catalog subtypes for table/view counts and explain exclusions when document dataset types are unknown.
- Route explicit value, reading, amount and quantity requests to metrics while preserving catalog counts and reading as a dependency verb. Treat formula questions and explicit supplier/input roles as upstream, preserve main ownership requests, and distinguish receivers from inputs in production clauses and supported pronoun references.
- Preserve explicit predicate roles when requested objects carry hierarchy modifiers, and resolve supported topic omissions, recipient usage frames and restrictive-clause attachments. Distinguish scalar-total requests from ownership or source questions and from relative clauses inside metric grouping or filters; preserve explicit value requests when a complete metric alias hides the quantity cue.
- Preserve knowledge questions following grouping modifiers and scalar output nouns following grouped metric commands. Bind missing-source conditions to their own clause and distinguish active usage from passive resources in production-purpose questions.
- Resolve longest registered subjects before interpreting bilingual question focus and dependency direction. Typed knowledge questions cannot execute numeric queries; grouped metric phrases and numeric rankings retain the metric route.
- Explain recognition rules and offer intent clarification buttons. Merge same-name people or teams with catalog roles for questions, preserve rejected-link distinctions, and use the sole remaining association candidate with its pending review label.
- Preserve numeric results when optional related knowledge has an unavailable source revision. Display asset names and candidate provenance, retaining raw identifiers in evidence drawers.

## [0.10.0] - 2026-10-24

### Added

- Schema-driven text knowledge graphs with UTF-8/NFC source coordinates, bounded paragraph/sentence chunking, deterministic entity identities, merged mention/evidence locations and explicit endpoint checks. Pending-review candidates remain available for human decisions; schema proposals never change the vocabulary automatically.
- Durable `run_kg_extraction` actions with fingerprint-bound source/configuration/recording inputs, external-transfer approval, worker lease fencing, successful-block cache reuse, partial-run reports and per-request extraction budgets/traces. Unknown billing remains explicit, and truncated output never becomes a successful cache entry.
- Shared Agent/MCP `query_kg` and `explain_relation` reads, bounded graph/source/history APIs, and a bilingual Knowledge graph workspace for entities, relations, source highlights, review decisions, graph display, schema proposals and evaluation comparisons.
- Offline `eval-kg` with independent recording and production-candidate scores, language and verified-only slices, external same-schema cases and opt-in real-provider YAML profiles. Recorded usage is separate from replay's zero model cost. Optional separately installed GLiNER2 extracts entities only.
- A demo with 24 recorded passages, three attributed fake scripted long documents and one deliberate truncation; four graph goldens and three mutations bring the suites to 36 conversations and 24 mutations without changing the original golden files or mutation anchors.

### Changed

- Graph reads are discovered on demand, preserving the original resident-tool prompt size and existing conversation budgets. Harness observations exclude action runs used only to prepare fixtures.
- Package, API and frontend versions advance to 0.10.0. Graph contracts ship in wheels; model extraction has a separate 600-line adapter boundary without additions to the locked runtime dependency closure.

### Fixed

- Fresh evaluations normalize external combining-character text before measuring spans, while historical recording inputs retain their original scoring coordinates.
- Chunk-local evidence selection distinguishes repeated sentences at block boundaries; same-as review changes affect only display grouping, preserving source assertions and audit history.
- Extraction prompt v3 preserves every schema example's full source, entities and relations while keeping approval estimates and model requests on the same prompt.
- The bundled Ollama profile uses 1000-code-point chunks with 100-code-point overlap to retain cross-sentence context within a conservative input allowance.
- Long source highlights wrap naturally within paragraphs while retaining keyboard activation and visible focus.
- Extraction approval plans now bind document and block fingerprints without copying source text or recordings into Agent/MCP results. Workers verify all approved inputs before constructing an extractor; existing run history keeps its source snapshots.
- Accepted and rejected graph relationships and entity mentions retain human decisions when evidence or extraction profiles change, with inherited-decision audit provenance.
- Structured extraction prompts use concrete examples; valid data accompanying schema echoes is retained with ignored-key counts. Parse failures and truncation retain provider usage, unknown-price token budgets use complete observed usage, and failed runs preserve completed work and costs.
- The cloud profile uses `deepseek-flash` and a documented conservative peak-price snapshot. Compressed model responses are decoded once, and Ollama uses bounded default chunks with server-side context guidance.
- Evaluation reports include failed case IDs, offsets and reasons. Entity type spelling is normalized, while unknown types and their relations produce counted schema proposals with samples.

## [0.9.0] - 2026-10-24

### Added

- Packaged, validated specialist definitions with serial delegated conversations, bounded tool scopes/depth/batches, root-budget accounting, call-tree traces and idempotent conclusion replay.
- Explicit scoped memory with PII redaction, deterministic BM25 retrieval, decayed strength, provenance-preserving consolidation and recursive hard deletion with content-free audit.
- Bilingual nested Agent steps, safe canary stops, current memory-use references and a Memory management page with filtering, creation and confirmed deletion.
- Twelve advanced golden cases and five guard mutations, bringing the suites to 32 conversations and 21 mutations; shared script ownership and multi-conversation fixtures are documented in `docs/AGENT.md`.
- Private per-conversation canaries stop leaked model text and tool arguments before transcript, checkpoint or tool dispatch. Tool results enter prompts in compact data-only JSON envelopes; raw audit transcripts remain unchanged.

### Fixed

- Memory strength increases at most once per user question across model steps, fallback attempts, delegated children and approval recovery. Durable use records preserve this limit after restarts; later uses still refresh the last-use time and response memory references, and a new user message permits another increase.
- Phone redaction preserves ISO dates, slash-separated dates and time values while continuing to redact local and international phone numbers.

## [0.8.0] - 2026-10-24

### Added

- Typed YAML workflows for dataset health checks, reversible metric changes with before/after answers, and low-quality sample cleanup with human-approved deletion. Tool, wait, branch, approval and output steps support located validation, deep overrides and deterministic JSON references.
- Explicit workflow start, history, timeline, audit and resume endpoints under `/api/workflows`, synchronous SSE snapshots, and `workflow list`, `validate`, `run` and `resume` commands. Starts and resumes have independent idempotency keys; signed pauses survive process restarts and reuse existing action receipts.
- Intent suggestions with bilingual contract vocabulary, independent metered classification for ambiguous matches, queryable route decisions and a `route` SSE event before `done`. Suggestions never start workflows; only the selected dataset is used for prefilling inputs.
- Simple, multi-step and high-risk model tiers, provider-specific validated configuration, explicit `auto` selection and pinned conversation models. Same-provider fallback chains allow at most two backups for timeout, 429 or server failures; every attempt reserves and settles its own budget and trace.
- Offline `eval-route` confusion matrices, `routing validate`, and `DATAKEEL_MODEL_ROUTING_FILE`. Workflow and routing contracts are included in wheels; both domain packages have independent size and coverage gates.
- Bilingual workflow forms, run history and timelines, links to human approval, explicit signed continuation, and Agent displays for route suggestions, model tiers and fallback attempts. The tour creates a separate generated cleanup dataset.

### Changed

- Approval recovery shares a pure signed-record policy across conversations and workflows. Workflow facts, steps, audit and resume keys are independent of conversation tables.
- Non-paused runs interrupted by client disconnects or process restarts become `INTERRUPTED`; they cannot resume midway. Waiting tasks fail explicitly on timeout or task failure, with a worker startup hint.
- `done` events add optional route and model-attempt metadata without changing existing event ordering. Classification and fallback attempts do not consume additional Agent turns. Existing golden inputs, context segments and tool discovery are unchanged.
- Package, API and frontend release identifiers advance to 0.8.0 without adding runtime dependencies.

### Fixed

- Workflow intent routing matches semantic groups with interchangeable synonyms and English word boundaries. Single-object deletion and descriptive metric edits remain free Agent requests; `eval-route` also checks the frozen intent regression corpus.
- Workflow timelines show bilingual step titles and readable summaries for file counts, branch decisions, action receipts, quality scores and before/after answers. Original outputs remain available in expandable details, and historical titles come from each run's frozen definition.
- Agent model routing uses one compact row per response; fallback attempt details expand only when a backup was used.

## [0.7.0] - 2026-10-24

### Added

- Durable Agent approval pauses and a resume SSE endpoint backed by synchronous checkpoints in the existing SQLite or PostgreSQL database. Resume validates the persisted approval and reuses existing action receipts after process restarts.
- A SQLAlchemy checkpoint saver with binary storage, deterministic pending-write ordering and a fixed serialization allowlist. Conversation, tool, trace, budget and action audit records remain independent of checkpoints.
- Runtime-only framework import boundaries, a separate 1500-line runtime package limit and a 90% runtime coverage gate. The dependency inventory includes exact `orjson` and `regex` license exceptions and verified legacy metadata evidence.

### Changed

- LangGraph replaces the handwritten Agent loop, and LangChain chat models replace the protocol-specific HTTP providers. Fake/Demo providers retain the existing scripted interface through an adapter; the twenty golden cases, context segments, tool set, budgets and seven SSE event types are preserved.
- Approval recovery uses an independent response lease and adds no user message. A new message invalidates a pending pause with an audit event. Tool calls are deduplicated by their original call identifier, including the action-commit/checkpoint-write failure window.
- LangSmith tracing is forcibly disabled even when third-party tracing environment variables are set. Model retries remain disabled, and explicitly injected HTTP clients ignore proxy environment variables.
- Package, API and frontend release identifiers advance to 0.7.0.
- Runtime framework dependency declarations use upper bounds or documented exact pins; locked package versions are unchanged.
- `make check` scans tracked and untracked publishable worktree files for private content before other checks. Reserved example email domains are accepted, generated sample contacts use `example.org`, and commit identities still require GitHub noreply addresses.

### Deprecated

- `DATAKEEL_OPENAI_URL` and `DATAKEEL_ANTHROPIC_URL` complete endpoints are supported for one more release only with the standard `/chat/completions` and `/v1/messages` suffixes. Prefer `DATAKEEL_OPENAI_BASE_URL` and `DATAKEEL_ANTHROPIC_BASE_URL`; explicit base URLs take precedence.

### Fixed

- Cache-read and cache-write tokens are recorded as subsets of the model's reported input usage instead of being added twice. Missing usage remains unknown and retains the conservative budget reservation.
- Resume attempts with missing, mismatched, expired or wrong-actor approval, or a plan outside the conversation, are rejected with audit evidence before action dispatch.
- CI starts the Postgres service container; its health-check command is double-quoted for the runner.
- English object headings, breadcrumbs, command search and approval object names reuse the catalog translations shown on graph cards. Catalog types and qualified field names share the same fallback; Chinese labels and non-catalog object names retain their existing behavior.

### Performance

- A fresh `uv run datakeel demo --once` has a three-run median of 5.86 s, down from 13.02 s on the same M-series laptop (measured range: 5.85–6.12 s). Object access and input hashes are reused within each batch, evidence projections use bounded bulk queries and inserts, small image work runs with bounded concurrency, and offline commands defer server imports. These extend the existing settings, contract and assertion-grouping caches. Generated image bytes, evidence/catalog rebuild hashes and evaluation outcomes are preserved.

## [0.6.1] - 2026-10-23

### Added

- Metric history provides a rollback button for each previous definition, with the existing reversible action sheet and a refreshed version after execution.

### Changed

- The sidebar reads the application version from the frontend package; API and OpenLineage release identifiers reuse the Python package version.
- The bilingual tour completes metric rollback through the interface and includes a rollback review screenshot. README and tour images are captured from fresh generated demos.

### Fixed

- Metric update and rollback sheets list the affected metric and its version transition, with consistent object counts and no file-size summary.
- The workbench no longer claims five recent actions when fewer exist. Internal milestone labels are removed from the sidebar, and the favicon uses the current blue and paper palette.

## [0.6.0] - 2026-10-23

### Added

- Bilingual contribution and security guidance, the Contributor Covenant 2.1, issue and pull-request templates, and a contributor-neutral working agreement.
- A runtime license gate covering the locked Python dependency closure and frontend packages measured during the production build, with generated third-party notices and fail-closed license checks.
- Local public-repository export in history and snapshot modes, with reviewed content/message rewrites, normalized commit identities, full-history scanning and machine-readable reports.
- A bilingual ten-minute tour with directly generated screenshots and a repeatable local walkthrough covering evidence review, versioning, approval, traceable answers and metric rollback.

### Changed

- Unapproved, rejected and already-consumed approval executions now all persist `DENIED` runs with distinct `reason` values; authorization HTTP errors remain compatible.
- Package, API, UI, smoke reports and OpenLineage producer identify release 0.6.0.

### Fixed

- Metric updates reject missing catalog tables and fields before saving a plan; YAML imports continue to register unresolved definitions.
- Completed, failed and cancelled tasks persist their finish time. Existing databases gain nullable columns automatically, preserving old records and unknown durations.
- The English metric detail heading uses the same sample-name translation as relationship cards. The evidence benchmark entrypoint and failure cleanup are covered by the module coverage gate.
- Relationship cards show readable file, version and catalog names, distinguish same-named fields by table, and provide visible controls for horizontally overflowing graphs. Graph counts use a single separator.
- Chinese interface labels and English singular/plural forms are consistent; the workbench title explicitly counts pending approvals, active pipelines and datasets with quality alerts.
- Evidence source letters follow matrix column order, and Ask reference times explicitly use UTC.

## [0.5.0] - 2026-10-23

### Added

- A bilingual proofreading workspace with six navigation groups, live workbench counts, merged pipeline/action history and eight object archives with source-linked facts and canonical hash URLs.
- Numbered caption/matrix/image anchors, accessible evidence states, deduplicated source footnotes and digest-bound approval sheets. Evidence lists fit six complete samples at 1440×900 and support review-priority, filename and quality sorting, keyboard review and composition guards.
- Read-only object search with ⌘K / Ctrl+K, unique UUID-prefix navigation and conversation drafts. Ask answers reference metric, SQL, fields and time; clarification candidates resolve the original question through an optional metric identifier.
- Self-hosted Latin Source Serif 4 and Source Code Pro fonts, three light/dark palettes, persisted system/explicit themes, token and contrast gates with negative tests, and a reproducible 36-image screenshot matrix.

### Changed

- Relationship graphs use archive cards, group only same-name action runs, retain all member IDs and fold excess neighbors by edge kind to stay within 25 visible nodes. Legacy lineage/report/run URLs preserve their destinations.
- Optional dataset quality summaries, graph folding and evidence ordering retain the earlier API defaults. Controlled action parameters, frozen manifests, approval/receipt rules and original P1–P4 workflows remain compatible.
- Release identifiers advance to 0.5.0. Dates use MM-DD HH:mm, large headings/numbers use serif type, and the bundled UI requires no external font or service requests.

## [0.4.0] - 2026-10-23

### Added

- A deterministic Fictional Kitchen Co. demo alongside both existing file scenarios: four SQLite sources, 20 tables and four views, 128 catalog fields and 51,992 generated rows, with independent gold answers. The semantic layer contains 13 metrics, 12 dimensions and 32 terms, including distinct shipment, invoiced-sales and retail definitions.
- Registered source, table, column, metric, dimension, term, owner and question identities; schema-validated properties; SQLite metadata and foreign-key reflection; and field derivation parsed from views or supplied SQL. Versioned catalog snapshots and separate catalog edges rebuild from events with `rebuild-catalog` and canonical hash verification. Import receipts report changes, unchanged objects and SQL parse failures.
- YAML metric definitions with required time columns, typed filters, explicit unresolved-reference reasons and authoritative catalog versions. Parameterized SQLite/PostgreSQL SELECT compilation and database-enforced read-only execution include time and row limits. The only new runtime dependency is `sqlglot` 30.24.0 (MIT).
- A deterministic parse → resolve → compile → execute → explain question pipeline, explicit refusal and clarification states, fixed-reference demo questions, saved answer replay, source-field references and NFC text-span matching evidence. Namespaced question predicates reuse assertion provenance, review audits and `rebuild-evidence`.
- Reversible `import_catalog` / `restore_catalog`, `update_metric` / `rollback_metric` and `update_term` / `rollback_term` actions. Metric history exposes every version and audits containing plan, actor and version transitions; rollback restores old semantics as a new version.
- `ask_data`, `list_metrics`, `explain_metric` and `impact_of` functions shared by Agent and MCP, plus paginated catalog, table detail, metric history, impact and answer/replay HTTP endpoints. MCP now exposes 13 read functions, 14 prepare-only actions and two explicit approval/execution controls.
- Chinese/English Data catalog and Ask data pages: source/table/field browsing, metric cards and controlled editing, paginated glossary, bounded impact trees, result evidence, collapsible SQL, term highlights, refusal/clarification candidates and replay. The existing graph displays catalog edges in bounded subgraphs with columns by object type; metric history links to its JSON API.
- `ask --reference-instant`, `eval-ask` and `rebuild-catalog` CLI commands. The isolated 20-question benchmark persists `provider=ask` results, numeric correctness, refusal/clarification counts, state-appropriate evidence completeness and truthful report thresholds. Four enterprise golden cases bring the total to 20; two SQL-boundary/refusal mutations bring the mutation suite to ten.

### Changed

- Object and predicate kinds use validated registries while original file/version behavior remains compatible. Catalog and question identities are excluded from file-selection object sets and frozen manifests.
- `demo` imports the enterprise scenario through controlled actions, keeps existing metric changes on subsequent runs, and retains `--legacy-only`. Unchanged imports add no catalog event; metric reference resolution reflects the current catalog without rewriting historical definitions.
- Relative dates accept an explicit reference instant; demo and question evaluation use `2026-10-01T00:00:00Z` and show half-open date ranges. Candidate-ID reranking is an interface with fake unit tests only and never enters demo, golden or evaluation; no real model is required for questions.
- Catalog, metric and question modules join the 90% module coverage gates. Release identifiers and bilingual documentation advance to 0.4.0 while preserving earlier dataset, evidence, approval, export and evaluation workflows.

## [0.3.0] - 2026-10-22

### Added

- A reproducible 1,000-sample paired image/caption/annotation demo (800 train, 200 val), with independent gold for near duplicates, annotation conflicts, corrupt images and missing annotations. The original 400-file demo remains available.
- Versioned assertions with canonical concept IDs, present/absent/unknown semantics, NFC code-point text anchors, original-pixel image boxes and extraction-event provenance. Human review changes status only and appends reversible decision audits.
- Five deterministic evidence operators in the existing worker/DAG, with content/selector/version/contract-aware incremental caching, failure counters, invalidation audits and content-addressed knowledge bundles. `rebuild-evidence` restores projections and review state and verifies canonical hashes.
- Evidence filtering and cursor pagination, source-version details, `query_evidence` / `get_evidence` / `explain_sample` read functions, and the reversible `decide_assertions` action. MCP now exposes nine reads, eight prepare-only actions and two explicit approval/execution controls.
- Chinese/English Evidence pages with filters, thumbnails, caption highlights, annotation overlays, review controls and exact-ID/source-version selection actions. Deletion stays behind the existing approval flow; the existing lineage view distinguishes semantic and lineage edges.
- `eval-evidence` with 15 declared baseline/evidence query pairs, fresh local extraction, precision/recall and direct/cross-split pair metrics, three-state counts, timing and persisted `provider=evidence` reports. Threshold outcomes are reported without treating an unmet metric threshold as command failure.
- Four evidence golden conversations, bringing the total to 16, and two new mutations, bringing the total to eight. The unknown-state mutation verifies production rejection and the actual explanation check through an explicitly recorded bypass confined to its temporary mutant copy; the threshold mutation uses a real-image non-transitive chain.

### Changed

- ObjectSet 1.1 adds assertion, split and near-duplicate filters while preserving 1.0 frozen-manifest serialization and digests. Action preparation freezes matching objects; later assertion reviews do not resample them.
- Extended the existing lineage graph endpoint with bounded deterministic semantic traversal; direct near-duplicate assertions project to the existing `similar_to` link type and remain separate from derivation events.
- The offline evidence chat calls real read functions and acts on at most two displayed samples per response; the full result remains available through Evidence pagination. Fake model extraction is limited to interface unit tests and does not enter extraction, evaluation or budgets.
- Evidence domains join the existing 90% module coverage gates. No new runtime dependency is added; the declared Pydantic minimum is 2.12 for compatible omission of new default fields.
- Package, API, UI and producer identify release 0.3.0; bilingual READMEs document evidence inspection, extraction, rebuild and evaluation.

### Fixed

- Replaced the unused action compensation field with readable `inverse_of` relationships for quarantine/unquarantine, and documented the three-turn no-new-asset-reference guard.
- Reusing the same operation ID returns its original receipt; a new execute request on a rejected or consumed plan records `DENIED`; a mismatched plan digest returns 409 without creating a run.
- Bound evidence downloads and materialized selections to exact source versions, prevented ambiguous same-ID/multiple-version materialization, and retained legacy query, approval and export compatibility.

## [0.2.0] - 2026-10-22

### Added

- Versioned ontology schemas for datasets, versions, files, artifacts and tasks, with distinct link semantics, six read-only functions and revision-frozen object sets.
- Seven controlled actions with parameter-bound plans, impact summaries, expiring single-use approvals, durable audit and attributable success/failure lineage receipts. Reversible actions run automatically through the Agent; deletion and external export require human approval.
- FastMCP stdio and SSE services, generated tool schemas and persisted tool-invocation records. Action tools prepare plans; approval and execution are separate tools.
- An offline chat demo, injectable OpenAI and Anthropic protocol adapters, persistent complete conversation history, on-demand tool discovery, four loop guards and dry-run mode.
- Persistent conversation/day token and monetary budgets, per-call traces, cache accounting and cost summaries. Unknown provider billing retains zero observed usage while conservatively charging the reservation; observed overages stop tool dispatch.
- Twelve offline golden conversations, evaluation comparison reports and six mutations verified against the golden suite.
- Agent chat, approval inbox, action history, ontology and trace/cost pages, Chinese/English switching, quarantine filters and receipt navigation.

### Changed

- Enforced the repository standards through `make check`: Ruff ALL, strict Python/TypeScript checks, dependency boundaries, source-size limits, coverage thresholds and complete frontend checks, with SQLite/PostgreSQL CI and a local CI script.
- Replaced boundary dictionaries and database-row leakage with frozen typed models and storage services; split API routers and frontend domains while retaining phase-one workflows.
- OpenAPI, package version and OpenLineage producer identify release 0.2.0. README examples include local MCP clients, offline evaluation and provider configuration.

### Fixed

- Prevented stale target state, modified canonical parameters, expired or reused approvals from authorizing execution; accepted worker tasks retain their authorization after plan expiry while rechecking target state.
- Preserved failure evidence and removed only newly created export artifacts when an export or transaction fails.
- Retained complete tool-call exchanges and request replay boundaries after interrupted conversation streams, refreshing later approval and execution results on reload.

## [0.1.0] - 2026-10-22

### Added

- Generated 400-file local demo, eleven file/image/text operators, immutable dataset versions and downloadable artifacts.
- Typed pipeline DAGs, PostgreSQL/SQLite task queues, shard leases and transactional terminal events.
- Five-dimensional quality scoring, six-chapter baseline reports, metadata governance, lineage graphs and OpenLineage/Croissant exports.
- Bundled React interface and separate API/worker commands with local or S3-compatible object storage.
