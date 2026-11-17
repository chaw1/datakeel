# Datakeel documentation

[简体中文](README.zh.md) · [Repository home](../README.md) · [API reference](API_REFERENCE.md)

## Start here

- **Try the workspace.** Run the offline demo, then inspect sample evidence and follow a change through review and approval. [Quick start](../README.md#quick-start) · [Guided tour](DEMO.en.md)
- **Prepare and deliver an image dataset.** Import a folder, inspect split leakage, save a correction, and approve delivery. [Browser walkthrough](DATASET_DELIVERY.md)
- **Work with business data.** Import engineering metadata, query a registered metric, and trace the result to source fields. [Metadata imports](METADATA_IMPORTS.en.md) · [Ask data](ASK.md)
- **Run a shared instance.** Set up an authenticating proxy and choose a storage backend. [Deployment](DEPLOYMENT.md) · [Database maintenance](DATABASE_MAINTENANCE.md)

## Evidence, media and knowledge graphs

| Guide | Description | Languages |
| --- | --- | --- |
| [Image and point-cloud quality](MEDIA_QUALITY.md) | Five-check image usability scoring, PLY/PCD cleaning, voxel downsampling, outlier filtering and top-down PNG previews | EN / ZH |
| [Audio and video preprocessing](MEDIA.md) | Local `ffmpeg`/`ffprobe` preprocessing, generated recording fixtures and source-time lineage | EN / ZH |
| [Text and image knowledge graphs](KG.md) | Entity mentions, cross-chunk relation merging, image OCR/vision routing, catalog associations and outbound consent | EN / ZH |
| [Vector evidence](VECTOR_FAKE.md) | Offline fixtures, governed cloud embedding, semantic duplicate, cluster and coverage-gap operators, and read-only queries | EN |
| [Offline vector evaluation](VECTOR_OFFLINE_EVALUATION.md) | Development-only FAISS exact comparison and cold/hot/incremental synthetic benchmark | EN / ZH |
| [Custom operators](CUSTOM_OPERATORS.md) | Single-file Python operator submission, static review, SHA-256 approval and container sandbox execution | EN / ZH |
| [Near-duplicate acceleration](RUST_ACCEL.md) | Optional `datakeel-accel` Rust extension (`DATAKEEL_ACCEL=auto\|off\|required`) for 64-bit dHash and training-text fingerprints | EN / ZH |

## Annotation, training sets and delivery

| Guide | Description | Languages |
| --- | --- | --- |
| [Image dataset delivery review](DATASET_DELIVERY.md) | Browser folder import, leakage review, corrected versions, signed release, and offline reconciliation | [EN](DATASET_DELIVERY.md) · [ZH](DATASET_DELIVERY.zh.md) |
| [Production workflows](PRODUCTION.md) | Label sets, immutable revisions, group/team assignment, review/rework and finalization to dataset versions | [EN](PRODUCTION.md) · [ZH](PRODUCTION.zh.md) |
| [Annotation workbench](ANNOTATION_WORKBENCH.md) | Keyboard editing, EXIF-upright display, template attribute forms, offline drafts and team cockpit | [EN](ANNOTATION_WORKBENCH.md) · [ZH](ANNOTATION_WORKBENCH.zh.md) |
| [Annotation quality](ANNOTATION_QA.md) | Offline agreement metrics across classification labels, 2D boxes and text spans with sampling acceptance | EN / ZH |
| [Training splits and exports](TRAINING.md) | Seeded/stratified splits, exact/SimHash/dHash/group leakage checks and reproducible COCO/YOLO/HF/JSONL exports | [EN](TRAINING.md) · [ZH](TRAINING.zh.md) |
| [LLM training-data governance](LLM_DATA.md) | Dry-run checks for SFT/instruction/preference JSONL (structure, language, duplicates, PII/secrets, eval contamination) | [EN](LLM_DATA.md) · [ZH](LLM_DATA.zh.md) |
| [Dataset datasheets](DATASHEETS.md) | Seven-chapter datasheets enforcing sentence-level fact citations with Markdown and HTML downloads | EN / ZH |
| [Dataset comparison and delivery](RELEASES.md) | Version diffs, immutable releases, reproducible tar/directory delivery packages and `datakeel reconcile` | [EN](RELEASES.md) · [ZH](RELEASES.zh.md) |

## Catalog, Ask data and governance

| Guide | Description | Languages |
| --- | --- | --- |
| [Ask charts and follow-up questions](ASK.md) | Deterministic chart selection, follow-up resolution, bilingual time parsing and refusal guardrails | [EN](ASK.md) · [ZH](ASK.zh.md) |
| [Import engineering metadata](METADATA_IMPORTS.en.md) | Local dbt artifacts, live/offline Airflow REST v1 metadata, authenticated OpenLineage events and metric drafts | [EN](METADATA_IMPORTS.en.md) · [ZH](METADATA_IMPORTS.md) |
| [Data standards and conformance](STANDARDS.md) | Portable field standards, bilingual code lists, rule mapping suggestions and conformance coverage | EN / ZH |
| [Quality rules](QUALITY_RULES.md) | Immutable SQLite/PostgreSQL table contracts, worker cron checks, issue assignment and signed alerts | EN / ZH |
| [Publishing and using data assets](DATA_ASSETS.en.md) | Public/internal/request-required/restricted classifications, grant applications, approvals and query/export/download scopes | [EN](DATA_ASSETS.en.md) · [ZH](DATA_ASSETS.md) |
| [Table and time-series profiling](TIMESERIES.md) | Local CSV/TSV profiling, deterministic anomaly detection and controlled catalog profiles | EN / ZH |

## Controlled actions, Agent, workflows and access

| Guide | Description | Languages |
| --- | --- | --- |
| [Controlled action outcomes](ACTIONS.md) | Frozen plan digests, expiry, reversibility, one-time approvals and resuming checkpointed Agent pauses | EN / ZH |
| [Deterministic workflows](WORKFLOWS.md) | YAML workflow contracts, CLI/HTTP/SSE execution, intent routing validation and approval pause recovery | EN / ZH |
| [Delegation and memory](AGENT.md) | Nested read-only subagents, untrusted tool envelopes, canary guards, cross-conversation memory and persistent budgets | EN / ZH |
| [One sentence to plan (beta)](ONE_SENTENCE.md) | Natural-language multi-step action chain planning, missing-parameter follow-ups and confirmation before writes | [EN](ONE_SENTENCE.md) · [ZH](ONE_SENTENCE.zh.md) |
| [Identity and HTTP access](IDENTITY_ACCESS.md) | Registered operators, role bindings, action scope resolution and zero-user local compatibility | [EN](IDENTITY_ACCESS.md) · [ZH](IDENTITY_ACCESS.zh.md) |
| [Action declarations](ACTION_DECLARATIONS.md) | Closed declarative action contracts, `action_store` lifecycle stages, `k1.v1` IR and independent authorization data | ZH |

## API, architecture and operations

| Guide | Description | Languages |
| --- | --- | --- |
| [API and pipeline reference](API_REFERENCE.md) | HTTP endpoints, DAG sharding, ObjectSet 1.1, quality weights, metric contracts, and trace export | [EN](API_REFERENCE.md) · [ZH](API_REFERENCE.zh.md) |
| [Architecture decisions](ARCHITECTURE.md) | Modular monolith, `api`/`worker` processes, SQLite/PostgreSQL fact store, S3/local storage and dependency direction | ZH |
| [Persistence schema composition](PERSISTENCE_SCHEMA.md) | Schema baseline ownership, SQLite versioned upgrades and PostgreSQL migration alignment | EN |
| [Small-team deployment](DEPLOYMENT.md) | Loopback defaults behind Caddy or nginx + oauth2-proxy, Docker Compose and six-point verification checklist | [EN](DEPLOYMENT.md) · [ZH](DEPLOYMENT.zh.md) |
| [SQLite database maintenance](DATABASE_MAINTENANCE.md) | Explicit `db status`/`db upgrade` workflow, maintenance lock and hash-verified local recovery packages | EN |
| [Capacity and scale workloads](CAPACITY.md) | Reproducible S/M/L workloads, dual-stack benchmark results and B8 team-claim measurements | EN / ZH |

## Engineering, verification and community

| Guide | Description | Languages |
| --- | --- | --- |
| [Code standards](CODE_STANDARDS.md) | Formatting, Ruff ALL, strict Pyright, `import-linter`, file/function size limits, coverage thresholds and license policy | ZH |
| [Offline evaluation and quality gates](VERIFICATION.md) | Golden cases, mutation checks, `eval-evidence` and `eval-ask`, screenshot coverage and `make check` | [EN](VERIFICATION.md) · [ZH](VERIFICATION.zh.md) |
| [Test execution speed](TEST_SPEED.md) | Worker scheduling, PostgreSQL template cloning and parallel CI shard merging | EN / ZH |
| [Public repository export](PUBLIC_EXPORT.md) | Clean history/snapshot export workflow, public-content scan rules and fresh-clone validation | EN / ZH |
| [UI direction & proofreading design](design/UI-DIRECTION-B.md) | Proofreading & provenance archive design tokens and color palettes | ZH |
| [Backlog](BACKLOG.md) | Completed milestones and open engineering improvements | ZH |
| [Contracts guide](../contracts/README.md) | Semantic file-format contracts, operator manifest generation and drift checks | EN |
| [Contributing](../CONTRIBUTING.md) · [Support](../SUPPORT.md) · [Security](../SECURITY.md) · [Changelog](../CHANGELOG.md) | Contributor setup, community support, private vulnerability reporting and release history | EN / ZH |
