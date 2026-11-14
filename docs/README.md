# Datakeel Documentation

[简体中文](README.zh.md) · [Back to README](../README.md) · [10-Minute Tour](DEMO.en.md) · [API Reference](API_REFERENCE.md)

This index organizes Datakeel's user guides, contracts, deployment recipes and engineering references by workflow.

## 1. Getting started

| Guide | Description | Languages |
| --- | --- | --- |
| [Ten-minute tour](DEMO.en.md) | End-to-end offline walkthrough across workbench, evidence, Ask data, workflows, KG, sandboxed operators and delivery | [EN](DEMO.en.md) · [ZH](DEMO.md) |
| [API & pipeline reference](API_REFERENCE.md) | HTTP endpoint table, DAG sharding, ObjectSet 1.1 queries, metric YAML schema, quality weights and OpenTelemetry trace export | [EN](API_REFERENCE.md) · [ZH](API_REFERENCE.zh.md) |

## 2. Multimodal evidence, media & knowledge graphs

| Guide | Description | Languages |
| --- | --- | --- |
| [Image and point-cloud quality](MEDIA_QUALITY.md) | Five-check image usability scoring, PLY/PCD cleaning, voxel downsampling, outlier filtering and top-down PNG previews | EN / ZH |
| [Audio and video preprocessing](MEDIA.md) | Local `ffmpeg`/`ffprobe` preprocessing, generated recording fixtures and source-time lineage | EN / ZH |
| [Text and image knowledge graphs](KG.md) | Entity mentions, cross-chunk relation merging, image OCR/vision routing, catalog associations and outbound consent | EN / ZH |
| [Fake vector kernel](VECTOR_FAKE.md) | Offline fake vector DAG nodes (`evidence.vector_embed`, semantic duplicate/cluster/outlier/coverage-gap) and read-only queries | EN |
| [Offline vector evaluation](VECTOR_OFFLINE_EVALUATION.md) | Development-only FAISS exact comparison and cold/hot/incremental synthetic benchmark | EN / ZH |
| [Custom operators](CUSTOM_OPERATORS.md) | Single-file Python operator submission, static review, SHA-256 approval and container sandbox execution | EN / ZH |
| [Near-duplicate acceleration](RUST_ACCEL.md) | Optional `datakeel-accel` Rust extension (`DATAKEEL_ACCEL=auto\|off\|required`) for 64-bit dHash and training-text fingerprints | EN / ZH |

## 3. Annotation production, training sets & delivery

| Guide | Description | Languages |
| --- | --- | --- |
| [Production workflows](PRODUCTION.md) | Label sets, immutable revisions, group/team assignment, review/rework and finalization to dataset versions | [EN](PRODUCTION.md) · [ZH](PRODUCTION.zh.md) |
| [Annotation workbench](ANNOTATION_WORKBENCH.md) | Keyboard editing, EXIF-upright display, template attribute forms, offline drafts and team cockpit | [EN](ANNOTATION_WORKBENCH.md) · [ZH](ANNOTATION_WORKBENCH.zh.md) |
| [Annotation quality](ANNOTATION_QA.md) | Offline agreement metrics across classification labels, 2D boxes and text spans with sampling acceptance | EN / ZH |
| [Training splits and exports](TRAINING.md) | Seeded/stratified splits, exact/SimHash/dHash/group leakage checks and reproducible COCO/YOLO/HF/JSONL exports | [EN](TRAINING.md) · [ZH](TRAINING.zh.md) |
| [LLM training-data governance](LLM_DATA.md) | Dry-run checks for SFT/instruction/preference JSONL (structure, language, duplicates, PII/secrets, eval contamination) | [EN](LLM_DATA.md) · [ZH](LLM_DATA.zh.md) |
| [Dataset datasheets](DATASHEETS.md) | Seven-chapter datasheets enforcing sentence-level fact citations with Markdown and HTML downloads | EN / ZH |
| [Dataset comparison and delivery](RELEASES.md) | Version diffs, immutable releases, reproducible tar/directory delivery packages and `datakeel reconcile` | [EN](RELEASES.md) · [ZH](RELEASES.zh.md) |

## 4. Enterprise catalog, Ask data & governance

| Guide | Description | Languages |
| --- | --- | --- |
| [Ask charts and follow-up questions](ASK.md) | Deterministic chart selection, follow-up resolution, bilingual time parsing and refusal guardrails | [EN](ASK.md) · [ZH](ASK.zh.md) |
| [Import engineering metadata](METADATA_IMPORTS.en.md) | Local dbt artifacts, live/offline Airflow REST v1 metadata, authenticated OpenLineage events and metric drafts | [EN](METADATA_IMPORTS.en.md) · [ZH](METADATA_IMPORTS.md) |
| [Data standards and conformance](STANDARDS.md) | Portable field standards, bilingual code lists, rule mapping suggestions and conformance coverage | EN / ZH |
| [Quality rules](QUALITY_RULES.md) | Immutable SQLite/PostgreSQL table contracts, worker cron checks, issue assignment and signed alerts | EN / ZH |
| [Publishing and using data assets](DATA_ASSETS.en.md) | Public/internal/request-required/restricted classifications, grant applications, approvals and query/export/download scopes | [EN](DATA_ASSETS.en.md) · [ZH](DATA_ASSETS.md) |
| [Table and time-series profiling](TIMESERIES.md) | Local CSV/TSV profiling, deterministic anomaly detection and controlled catalog profiles | EN / ZH |

## 5. Controlled actions, Agent, workflows & access

| Guide | Description | Languages |
| --- | --- | --- |
| [Controlled action outcomes](ACTIONS.md) | Frozen plan digests, expiry, reversibility, one-time approvals and resuming checkpointed Agent pauses | EN / ZH |
| [Deterministic workflows](WORKFLOWS.md) | YAML workflow contracts, CLI/HTTP/SSE execution, intent routing validation and approval pause recovery | EN / ZH |
| [Delegation and memory](AGENT.md) | Nested read-only subagents, untrusted tool envelopes, canary guards, cross-conversation memory and persistent budgets | EN / ZH |
| [One sentence to plan (beta)](ONE_SENTENCE.md) | Natural-language multi-step action chain planning, missing-parameter follow-ups and confirmation before writes | [EN](ONE_SENTENCE.md) · [ZH](ONE_SENTENCE.zh.md) |
| [Identity and HTTP access](IDENTITY_ACCESS.md) | Registered operators, role bindings, action scope resolution and zero-user local compatibility | [EN](IDENTITY_ACCESS.md) · [ZH](IDENTITY_ACCESS.zh.md) |

## 6. Architecture, deployment & operations

| Guide | Description | Languages |
| --- | --- | --- |
| [Architecture decisions](ARCHITECTURE.md) | Modular monolith, `api`/`worker` processes, SQLite/PostgreSQL fact store, S3/local storage and dependency direction | ZH |
| [Persistence schema composition](PERSISTENCE_SCHEMA.md) | Schema baseline ownership, SQLite versioned upgrades and PostgreSQL migration alignment | EN |
| [Small-team deployment](DEPLOYMENT.md) | Loopback defaults behind Caddy or nginx + oauth2-proxy, Docker Compose and six-point verification checklist | [EN](DEPLOYMENT.md) · [ZH](DEPLOYMENT.zh.md) |
| [SQLite database maintenance](DATABASE_MAINTENANCE.md) | Explicit `db status`/`db upgrade` workflow, maintenance lock and hash-verified local recovery packages | EN |
| [Capacity and scale workloads](CAPACITY.md) | Reproducible S/M/L workloads, dual-stack benchmark results and B8 team-claim measurements | EN / ZH |

## 7. Engineering standards, verification & community

| Guide | Description | Languages |
| --- | --- | --- |
| [Code standards](CODE_STANDARDS.md) | Formatting, Ruff ALL, strict Pyright, `import-linter`, file/function size limits, coverage thresholds and license policy | ZH |
| [Offline evaluation & quality gates](VERIFICATION.md) | 58 golden cases, 856 mutation anchors, `eval-evidence`/`eval-ask`, screenshot matrix and `make check` | [EN](VERIFICATION.md) · [ZH](VERIFICATION.zh.md) |
| [Test execution speed](TEST_SPEED.md) | Worker scheduling, PostgreSQL template cloning and parallel CI shard merging | EN / ZH |
| [Public repository export](PUBLIC_EXPORT.md) | Clean history/snapshot export workflow, public-content scan rules and fresh-clone validation | EN / ZH |
| [UI direction & proofreading design](design/UI-DIRECTION-B.md) | Proofreading & provenance archive design tokens and color palettes | ZH |
| [Backlog](BACKLOG.md) | Completed milestones and open engineering improvements | ZH |
| [Contracts guide](../contracts/README.md) | Semantic file-format contracts, operator manifest generation and drift checks | EN |
| [Contributing](../CONTRIBUTING.md) · [Support](../SUPPORT.md) · [Security](../SECURITY.md) · [Changelog](../CHANGELOG.md) | Contributor setup, community support, private vulnerability reporting and release history | EN / ZH |
