# Dataset comparison and delivery

[中文](RELEASES.zh.md) · [Guided tour](DEMO.en.md)

Open a dataset in **Data library → Versions**. Select two versions from this dataset, then click **Compare versions**. The five categories are added, removed, content changed (SHA-256 changed), metadata only, and unchanged. Each category has a whole-comparison count and bounded file pages. Annotation counts, label counts, mean file quality and evidence decision counts appear beside the file differences. Missing quality values are represented by the version summary's recorded measurement rules.

Legacy versions preserve file manifests without historical governance snapshots. Comparison quality scores use the dataset's current quality configuration; evidence decision summaries use the current active decisions associated with each version.

The equivalent local command is:

```bash
uv run datakeel version-diff DATASET_ID BEFORE_VERSION AFTER_VERSION --limit 50 --category content_changed --json
```

`--offset` selects another page; omitting `--category` returns a mixed page. The API is `GET /api/datasets/{dataset}/diff?before={version}&after={version}&offset=0&limit=50`. Versions from different datasets are rejected. Files align by their manifest file ID: shared IDs compare SHA-256 and then metadata; a derived artifact with a new ID is a new file.

## Publish and inspect

In **Versions → Publish a release**, select a source version, enter a semantic tag such as `v1.2.0` and release notes, then click **Review release plan**. Inspect the frozen parameters, file impact, digest and irreversible status. **Approve and publish release** signs and executes this exact plan. Preparing a plan does not publish anything. The same pending plan is also available in **Approvals**.

Changing the source version, tag, notes or either budget field clears the displayed plan immediately; review a new plan before approving the edited form. A response to a preparation request started before the edit cannot restore the old plan. The frozen plan already prepared on the server remains available in **Approvals** with its original parameters.

The resulting release appears in the list, with its file count shown as **2 files** (or **2 个文件** in Chinese). Expand its tag to see the source version, manifest SHA-256, notes, total bytes and paginated frozen files. Publication freezes the current governance metadata, quality measurements and evidence decision summary captured when its release plan was prepared. Release files, metadata and hashes are immutable. Subsequent changes require another version and another release; the existing version-generation workflow is unchanged.

For automation, use the existing controlled-action protocol with `POST /api/actions/publish_release/prepare` and parameters `dataset_id`, `version_id`, `tag`, `notes`; sign the returned plan at `POST /api/approvals/{plan_id}` and execute it at `POST /api/actions/{plan_id}/execute`. Approval and execution must carry the returned digest, and execution uses the plan's operation ID. Read releases with `GET /api/datasets/{dataset}/releases`, `GET /api/releases/{release}` and `GET /api/releases/{release}/files?offset=0&limit=50`.

### Large releases and versions

Controlled actions normally stop at 10,000 objects and 10 GiB per plan. A release or a version selected from evidence freezes a whole manifest, so `publish_release` and `create_version_from_selection` may request a larger budget explicitly. Without one, a plan above the default is refused with the impact it measured and how to request more. The budget is stored in the plan's `context` (`max_objects`, `max_bytes`), is covered by the plan digest and appears as **Authorized budget** on the approval sheet. Approval and execution check the frozen impact against it again.

- Web: in **Publish a release**, fill **Maximum files** and/or **Maximum size (GiB)**. Empty fields keep the default.
- HTTP: `POST /api/actions/publish_release/prepare?max_objects=20000&max_bytes=2147483648`; the body is unchanged. Other action types reject these query parameters.
- CLI: `uv run datakeel release-plan prepare publish_release params.json --max-objects 20000`, then `release-plan approve PLAN_ID --digest DIGEST` and `release-plan execute PLAN_ID --digest DIGEST`. `params.json` holds the same JSON body as the HTTP request; `create_version_from_selection` works the same way.

Requests are capped by `DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS` (default 1,000,000) and `DATAKEEL_RELEASE_BUDGET_MAX_BYTES` (default 1 TiB). A request above the ceiling is rejected with `422` and names both settings. If an operator lowers the ceiling after preparation, a plan whose explicit budget no longer fits cannot be approved or executed; plans on the default budget are unaffected. Execution still reads and hashes every published object, so very large releases take correspondingly long.

## Export and verify independently

Click **Export delivery package** in the release detail to download a gzip tar archive. The equivalent command writes an archive or a new directory:

```bash
uv run datakeel release-export RELEASE_ID --output delivery.tar.gz
uv run datakeel release-export RELEASE_ID --output delivery-directory
```

The HTTP equivalent is `POST /api/releases/{release_id}/export`, which returns the tar archive with media type `application/gzip`. Archives are reproducible: members are sorted by path, owner and group names are empty, uid/gid are 0, permissions are `0644`, modification times are 0, and the gzip header carries no file name or timestamp. Repeated exports of one release are byte-identical and never reveal the server's system account names.

The package contains:

- `MANIFEST.json`: expected relative paths, byte counts, SHA-256, media types, source versions, lineage references, annotation and label counts, metadata and required metadata fields, plus a canonical manifest hash.
- `RECORDS.json`: the independently checked receipt-side dataset metadata, plus metadata, annotation and label totals, and lineage for each payload.
- `files/`: the actual file content.

Keep both JSON files with the payload. Paths are relative; credentials and internal physical storage paths are excluded. Metadata is filtered by field role and value structure: fields declared as locations (`path`, fields ending in `path` such as `source_path`, `object_key`, `storage_uri`), credential fields, storage URIs such as `file://` or `s3://`, and URLs carrying credentials are removed. Every other value is kept as is, so labels that start with `/` (for example `/m/01yrx`) remain and are counted. The manifest schema is [contracts/delivery-manifest.schema.json](../contracts/delivery-manifest.schema.json) and export validates it. The manifest hash detects a changed manifest; it is an integrity checksum, not a digital signature proving a sender's identity. Keep a trusted copy of that hash when authenticity matters.

Payload paths contain an ordinal directory and a percent-encoded basename; long encoded names are shortened with a digest suffix. Follow the exact paths in `MANIFEST.json`; do not decode or rename them before verification. The source release snapshot hash shown in the Web and the delivery manifest's canonical hash cover different serializations and are not interchangeable. The delivery checksum hashes UTF-8 JSON with sorted object keys, compact separators and unescaped Unicode, excluding only the top-level `manifest_sha256` field. Export includes schema defaults; verification hashes the fields actually received, so removing a default-valued field is detected. Use the hash from the expected delivery manifest when comparing delivery manifests.

The recipient can run reconciliation with an installed Datakeel command, without an API, database, object store or model service:

```bash
datakeel reconcile delivery.tar.gz --manifest MANIFEST.json
datakeel reconcile delivery-directory --manifest MANIFEST.json --json
```

The default manifest path is resolved inside the delivery. Human output includes Chinese and English; `--json` emits a structured report. Exit status is `0` only when all six categories pass, `1` on a mismatch, and `2` when the delivery or manifest cannot be read or validated. An invalid input with `--json` returns `error: "invalid_delivery"` and an error-class `reason`, without echoing its contents. Checks cover file count; total and per-file byte sizes; SHA-256; annotation and label counts; required metadata fields and values; and valid lineage references to registered source versions. Metadata and annotation checks compare `RECORDS.json` with `MANIFEST.json`; they do not infer annotation semantics from arbitrary media bytes. Missing receipt records fail rather than silently passing.

For annotation statistics, an explicit nonnegative integer `annotation_count` or `label_count` in metadata takes precedence. Otherwise the registered plural collection (`annotations` or `labels`), then singular collection (`annotation` or `label`), supplies its list length; a present nonempty scalar or object counts as one, and no registered value counts as zero. Receipt-side collection-derived statistics are checked against the declared counts when those fields are present. An explicit count remains authoritative even if a collection is also present; a changed collection is independently caught by metadata comparison.

Metadata checks compare dataset and file fields, required-field presence and complete JSON values. Object-key ordering does not matter; array order and scalar representations do. For example, `true`, `1`, `1.0` and `"1"` are distinct. Required fields may contain JSON `null` when the expected value is also `null`; this check does not impose a separate non-null business rule.

To demonstrate corruption, extract a copy of the package, change one payload byte and run the same command:

```bash
mkdir received
tar -xzf delivery.tar.gz -C received
python3 - <<'PY'
import json
from pathlib import Path

root = Path("received")
manifest = json.loads((root / "MANIFEST.json").read_text())
payload = root / manifest["files"][0]["path"]
with payload.open("r+b") as stream:
    first = stream.read(1)
    stream.seek(0)
    stream.write(bytes([first[0] ^ 1]) if first else b"x")
PY
datakeel reconcile received --manifest MANIFEST.json
```

The hash category names the altered file and its expected and actual values. A nonempty file changed in place keeps its size, so the byte category still passes. For metadata, annotation or lineage exercises, change the corresponding record in `RECORDS.json` and retain the expected manifest.

## Archive a platform-side check

In release details, click **Reconcile stored objects**. The platform reads actual stored objects and archives the same six categories and differences. Reloading keeps the history. API equivalents are `POST /api/releases/{release}/reconcile` and `GET /api/releases/{release}/reconciliations`; the local command is:

```bash
uv run datakeel release-reconcile RELEASE_ID --json
```

## Resume a chunked upload

`POST /api/uploads` accepts `idempotency_key`, `name`, `filename`, `total_bytes`, the complete source `sha256`, `chunk_bytes` and optional `metadata`. Keep the returned upload ID. `GET /api/uploads/{id}` returns `received_chunks` and `missing_chunks`, so a new client can send only missing zero-based chunks. Upload each exact-sized chunk using `PUT /api/uploads/{id}/chunks/{ordinal}` with `Content-Type: application/octet-stream` and raw bytes. Submit `POST /api/uploads/{id}/complete` without a body to verify and import the file. The receipt then contains state `COMPLETE` and `dataset_id`.

Identical chunk retries merge; a conflicting duplicate is rejected. Chunks may arrive out of order. Overlapping writes to the same upload are rejected with `409`; the client can retry after the first write finishes. The same initialization idempotency key resumes the same declaration, and changing that declaration returns `409`. Independent keys represent independent imports. Completion retries return the existing result. The whole source SHA-256 is checked before import, and the actual persisted object is read and hashed again before the dataset transaction commits. Invalid lengths, missing chunks or a mismatched hash return `422` without creating the dataset; unknown upload IDs return `404`.

Busy initialization, chunk and completion requests return `409` with `detail: "Upload is busy; retry after the active upload operation completes"`. The message identifies the upload operation; conversation conflicts retain their existing wording. A saturated global upload-writer limit continues to report its upload concurrency limit.

Configuration bounds are `DATAKEEL_UPLOAD_MAX_CHUNK_BYTES` (default 8 MiB, maximum 64 MiB), `DATAKEEL_UPLOAD_MAX_CONCURRENCY` (default 4, maximum 32), and `DATAKEEL_UPLOAD_MAX_FILE_BYTES` (default 5 GiB, maximum 1 TiB). An upload may contain at most 100,000 chunks; choose a chunk size consistent with that bound. Exceeding the concurrent-writer limit returns `409`.

Upload chunks are staged under `uploads/<upload ID>/` in the configured `DATAKEEL_HOME`. After a successful completion commits the dataset, the staged chunks are deleted; if the process stops between that commit and the deletion, calling completion again finishes the cleanup. Unfinished uploads, and uploads whose completion failed because of missing chunks, wrong sizes or a hash mismatch, keep their chunks so they can be resumed or inspected. This release has no abort endpoint and no automatic expiry; an operator removes that directory when it is no longer needed. Plan disk capacity for chunks of unfinished uploads and the temporary full-file assembly. Resume survives a client or process restart on the same persistent filesystem. Multiple API hosts must use the same staging volume and database, or route an upload consistently to its original host; sharing only PostgreSQL does not share chunk bytes. Process locks protect overlapping writers but do not replicate staging files.

The release browser walkthrough can be replayed with `npm --prefix web run smoke:release -- http://127.0.0.1:8816 OUTPUT_DIRECTORY`. It creates generated fixtures, compares two versions, approves publication through the UI, downloads and verifies a package, changes one payload byte, and checks that an archived platform report survives reloading. The chosen output directory receives screenshots and machine-readable results. It permits only requests to the given loopback origin and requires zero browser errors.

## v0.13.0 release notes

v0.13.0 combines twelve accepted feature tracks with two release fixes. Every track keeps the existing controlled-action rules: changes are prepared as frozen plans, irreversible or outbound plans need a human signature, and reads go through the data-asset access guard.

| Track | What you can do now |
|---|---|
| Sensor time series and table profiling | Normalize mixed timestamp formats, order and deduplicate readings, find sampling gaps, stuck values, robust outliers, out-of-range values and unit mismatches, and profile table columns. Clean control data with the same trend, cycle and noise produces no findings. Ask can answer sensor-profile questions. |
| Rust near-duplicate acceleration | An optional native extension speeds up perceptual-hash near-duplicate search (about 400 times faster on 100,000 clustered hashes) with bit-identical results. An exact mode finds pairs that differ only in the prefix bits. `DATAKEEL_ACCEL=auto|off|required` selects the backend. |
| Custom operators in a sandbox | Submit a Python operator, review its code and hash on the approval sheet, and run it in a container with no network, a read-only root, a non-root user, no capabilities and a seccomp filter. Outputs must be declared flat files. |
| Image auto mode | Each image is routed to OCR or a visual model automatically. Visual-model boxes in a declared coordinate space (for example `normalized_1000`) are converted to pixels; boxes that fail the OCR cross-check are dropped and marked `coordinates_unreliable` instead of being drawn in the wrong place. |
| Version comparison, releases and delivery | Compare two versions in five categories, publish an immutable release after approval, export a delivery package with its own manifest, reconcile it offline or on the platform, and resume chunked uploads. |
| Data asset market and access | Publish datasets, tables and metrics as assets with public, restricted or apply-first policies. Users apply for query or download access; grants expire or can be revoked. Ask, export, download, Agent and MCP reads share one guard, and every governed read is audited. |
| Data standards and conformance | Import field standards, code lists and synonyms, review suggested column mappings, confirm or roll them back through approved plans, and see which tables conform least. |
| Better question understanding | English metric questions resolve with the same time ranges and filters as Chinese ones; generic wording asks for clarification instead of guessing; workflow requests are recognized more often, and questions about a workflow no longer start it. |
| Data quality rules and monitoring | Define not-null, unique, range, accepted-values, regex, referential-integrity, SQL-assertion, volume-change, freshness and distribution-drift rules on SQLite or PostgreSQL tables. Scheduled runs open, merge and recover issues and send HMAC-signed webhooks. SQL assertions may only call allow-listed functions. |
| dbt, Airflow and OpenLineage import | Import dbt manifests, run results and catalogs, Airflow exports and OpenLineage events into the catalog with column-level lineage. Re-importing without `catalog.json` keeps the previous columns; run-only changes no longer count as changes; Airflow dataset URIs attach to matching database sources. A 1,000-model project imports in about 10 seconds. |
| Annotation quality and sampling acceptance | Measure agreement (Cohen and Fleiss kappa, Krippendorff alpha, box IoU and span matching), flag suspect labels with batch-level outlier thresholds, draw ISO 2859-1 (AQL) or fixed-ratio samples, record an accept or reject decision through an approved plan, and compare rework rounds. |
| Dataset datasheets | Generate a seven-chapter datasheet for a dataset version in English or Chinese, from an offline template or a configured model. Every retained sentence cites frozen platform facts; sentences whose numbers, dates, percentages or names the cited facts do not support are removed and listed with the reason. Publication needs approval, and a newer dataset version marks older datasheets out of date. |

Two release fixes accompany these tracks:

- **Large releases and versions.** Publishing a release and creating a version from a selection now accept an explicit budget, up to a configurable ceiling of 1,000,000 objects and 1 TiB by default. The requested budget is frozen into the plan the user approves. See [Large releases](#large-releases-and-versions).
- **Version comparison on ICU databases.** Comparison now orders file IDs by code point on PostgreSQL (`COLLATE "C"`), so mixed-case or hyphenated IDs are classified correctly on databases whose default collation is ICU. If a database still returns files out of order, the comparison stops with an error instead of misclassifying files.

## v0.13.1 release notes

v0.13.1 adds two accepted feature tracks on top of v0.13.0. Both run entirely on local tools, use no model service, and keep the controlled-action and access-guard rules of v0.13.0.

| Track | What you can do now |
|---|---|
| Audio and video preprocessing | Probe recordings with user-installed `ffmpeg`/`ffprobe`; find black, solid, frozen and blurred frames, repeated video, silence, clipping, loudness outside an accepted range and repeated audio; align several recordings of the same event; cut fixed-window clips only from clean ranges and normalize them; keep the original recordings next to the clips with source-time lineage. Long recordings get a timeout that scales with duration and resolution; a recording that fails is listed with its operator and reason while the rest of the batch completes; truncated files are reported against the duration their header promised. `demo-media` runs the chain on generated recordings or on your own local files. |
| Image quality and point clouds | Score images for blur, exposure, noise, resolution and solid color with the measured reason for each failed check; probe PLY/PCD point clouds, suspect unit mismatches, clean invalid coordinates, downsample by voxel, flag statistical outliers that are isolated points or separated clusters while keeping occluded or distant real structure, and view a top-down PNG preview on the file object page. Undeclared capture forms only receive sparse-coverage hints; declared forms are judged. An unreadable image or scan is listed with its reason and the batch still completes. |

Known limits are documented in [Audio and video preprocessing](MEDIA.md) and [Image and point-cloud quality](MEDIA_QUALITY.md). In short: clipping in lossy-encoded speech and music is only partly recalled and works as a file-level hint rather than a per-segment map; fine-textured frames may not match across frame rates; a transport stream with flipped bits is not flagged; sparse clusters close to real structure can be missed; and point-cloud defaults were calibrated on generated scans only.

Integration changes in this version:

- Quality scoring applies tabular rules, image and point-cloud multipliers and recording deductions in that order. The quality view carries a `media` summary only when recordings were measured; image and point-cloud observations are stored under `image_pointcloud` in the dimension details and reported in their own chapters.
- The image and point-cloud preset pipeline is `datakeel.pipeline.image_pointcloud.image_pointcloud_pipeline()`; `datakeel.pipeline.media.media_pipeline()` is the audio/video chain.
- Point-cloud preview downloads go through the same data-asset download guard as file downloads.
- Lineage records an approved custom operator's code hash as its operator version.

## v0.14.0 release notes

v0.14.0 adds two accepted feature tracks on top of v0.13.1 and one global hardening. Both tracks run entirely on local tools, use no model service, and keep the controlled-action and access-guard rules.

| Track | What you can do now |
|---|---|
| Scale benchmark and capacity baseline | Run `python -m scripts.scale_bench B1 --size M --stack sqlite --seed 23 --output result.json` (B1–B7, S/M/L, SQLite or PostgreSQL) and get one JSON with machine, commit, scale, fixture fingerprint, latencies, counts, peak RSS and cleanup status; the same seed reproduces the same fixture on both stacks. Eight hot paths were bounded (file pages and global search, catalog and lineage reads, frozen file selection and object projection, task leases and final-state reads, upload completion) and `make check-scale` fails if version comparison turns quadratic again. [Capacity baseline](CAPACITY.md) states what was measured at M and L scale, which targets are met and which are not, and when to move from SQLite to PostgreSQL. |
| Ask charts and follow-up questions | Every Ask answer carries a chart chosen from the result shape; the Web page draws it as SVG and lets you switch to the source table with the keyboard. Keep asking in one thread: `那华南呢`, `上个月呢`, `按渠道拆开`, `换成订单数`, `同比`, `what about South China`, `what about August 2026`; each turn shows "Understood as" with the complete question, ambiguous follow-ups clarify without a number, and every turn re-checks asset grants. Threads persist across restarts on SQLite and PostgreSQL, can be listed, reopened and deleted, and are retained for `DATAKEEL_ASK_CONVERSATION_RETENTION_DAYS` (default 30). HTTP, CLI, Agent tools and MCP share the same `conversation_id`. |

**Approval is done by people only.** The MCP server no longer lists `approve_plan` or `execute_plan`; it exposes 57 tools — 20 reads and 37 actions that prepare frozen plans. A call by either name through MCP is refused with a reason and recorded as a failed invocation, and the plan stays prepared until a person approves and executes it on the Web UI or CLI. This is a behavior change for MCP hosts that scripted the approval step; the built-in Agent already used the UI approval flow.

Known limits are documented in [Capacity baseline](CAPACITY.md) and [Charts and follow-up questions](ASK.md). In short: at M scale the PostgreSQL deep page, the filename+modality filter on both stacks, SQLite global search, SQLite peak memory in B1, depth-5 lineage and the fifty-user p95 are above their targets, and B5 on SQLite showed one or two HTTP 500s per ~1,300 requests whose cause is not yet confirmed; the catalog search figures were remeasured after escaped-payload detection and rose on both stacks. In Ask, a complete new question inside a thread (including an unanswerable one) starts a new frame, so a later `那华南呢` refers to the new topic.

Integration changes in this version:

- The media observation index decodes only version manifests that carry an image or point-cloud measurement, so the default file projection reads one manifest and one file-state batch however many versions a dataset has.
- Inside a conversation, a question-form sentence that no slot explains (`why did brand awareness drop`) is answered like a new question — unanswerable with the three nearest metrics — rather than as a follow-up with one candidate.

## v0.15.0 release notes

v0.15.0 adds four feature tracks on top of v0.14.0 and two batches of smaller fixes. No track calls a model service: checks run on local rules and statistics, production models are fake or imported offline, and every write still goes through controlled actions and the access guards.

| Track | What you can do now |
|---|---|
| Training splits and exports | In **Versions → Training sets**, preview and save a seeded train/validation/test split of an immutable version. Stratification balances every label, including multi-label samples, and metadata groups and duplicate components never cross sets. Leakage checks list exact copies, near-duplicate images (dHash), near-duplicate text (SimHash) and shared groups pair by pair. Export COCO, YOLO, ImageFolder, Hugging Face imagefolder or text JSONL through the approved `export_dataset` action; the archive is bound to a version, split and annotator and reproduces byte for byte. The same steps are available as `datakeel training …`, over HTTP and as the read tools `training_distribution` and `training_leakage`. [Training guide](TRAINING.md). |
| LLM training-data governance | Open a dataset's **Text data governance** tab to check SFT, instruction and preference JSONL records for structure, length, language, quality heuristics, exact and near duplicates, prompt conflicts, PII and credentials, and overlap with your own evaluation sets. Analysis changes nothing; a cleaned version is created only after a person approves the `clean_training_data` plan, and it keeps lineage. `datakeel training-quality` and the read tool `get_training_quality` answer what is wrong with a dataset. With the optional Rust extension, 100,000 records were checked in under a minute on the development machine. [LLM data guide](LLM_DATA.md). |
| Production projects and roles | Pin a dataset version and a published label set, split tasks into packages, import offline COCO/YOLO predictions, annotate with append-only revisions, review and return work in a group project, and finalize approved work into an ordinary dataset version. Users, teams and five editable role templates decide who may do what, and the server computes each actor's scopes. `datakeel production demo` creates a small personal project. [Production workflows](PRODUCTION.md), [identity and HTTP access](IDENTITY_ACCESS.md). |
| Annotation workbench | Open **Annotation workbench** (`#/labeling`) to label boxes, polygons, classes and text spans with the keyboard or the pointer. Annotators see **My tasks**, reviewers the **Review queue**, project managers the **Project cockpit**, and personal projects **My data**. Edits are kept as a local draft and saved after half a second; going offline, reloading or a conflicting save does not silently lose work. Undo and redo, prefetching of the next two tasks and progressive loading of large images keep it responsive. Finalized records export and re-import losslessly as `annotations_jsonl`. [Workbench guide](ANNOTATION_WORKBENCH.md). |
| Smaller fixes | Quality rules scan whole tables and report their coverage; annotation consensus counts one vote per person; data-standard suggestions keep amount, cycle, status and date/time apart; datasheet number checks match the counted object; audio operators decode in chunks (peak memory for a generated 30-minute recording fell from 5.78 GB to 142 MB); upload and release pages show clearer messages; the privacy detector reads Chinese credential labels and stops at adjacent Chinese text. |

**Roles take effect once the first user is registered.** An installation with no registered users behaves exactly as before. After registration, HTTP writes act as the `X-Datakeel-Actor` header, every action and legacy write route checks a scope the server computes from global and project role bindings, and unknown, disabled or archived actors can only read. Training-split, annotation-import and text-cleaning writes are mapped to `export_dataset`, `save_metadata` and `clean_training_data`. The actor header is attribution inside a locally trusted installation, not authentication; deployment-level authentication remains your own boundary.

**MCP now exposes 92 tools instead of 57**: 33 read functions and 59 actions that only prepare plans. There is still no approve or execute tool. MCP hosts that pin the tool list must refresh it.

**Other behavior changes.** `text.pii_redact` with its default replacement writes typed placeholders such as `[EMAIL]` and `[PHONE]` instead of `[REDACTED]`; memory writes keep `[REDACTED]`. Phone detection needs complete digit boundaries: 12- and 14-digit bare order numbers are no longer phones, and landlines with a parenthesized area code are now found. COCO, YOLO and Hugging Face imagefolder exports refuse images whose EXIF orientation rotates or mirrors them. A quality rule's `max_rows` now bounds a streaming batch rather than the number of rows checked. No CLI command, HTTP path, MCP tool, operator or table was renamed; OpenAPI grows from 144 to 164 paths without removing any. The mutation gate has 376 anchors, the golden suite 52 cases and the operator catalog 42 operators.

Known limits:

- Training exports: text near-duplicate detection uses character trigrams, so texts of up to 80 characters that differ only in digits are not reported, and this includes a whole Chinese paragraph of that length. Cropping more than 10% from any side of an image is outside the near-duplicate guarantee. Stratification is a bounded search: some small proportions are unreachable, and the report then shows the real distribution.
- Privacy detection is rule-based. It over-redacts in a few cases: generic English labels such as `The secret: practice every day.`, and numbers shaped like a parenthesized area code such as `编号（010）2024-0315号` or `(300) 200 3000`. It does not detect prefixed keys such as `DB_PASSWORD=` or `mysql_pwd=`, `password is …`, `私钥：`, a full-width `＝`, or passwords shorter than eight characters; two landlines separated only by a space are both missed; and the marks `～ · ｜ 〉 』 〕 〗` right after a bare credential are removed with it. A Chinese host name stays visible after the user name and password are masked. Near-duplicate lookup caps candidates per record and can miss matches in dense corpora. The safety word-list screen is not included. The one-minute figure for 100,000 records needs the Rust extension; pure Python gives identical results more slowly.
- Production: tasks written while the instance had no users belong to `local`; if users are registered and the project is upgraded later, those tasks stay assigned to the unregistered `local` until `local` is registered with the annotator role. Ordinary image imports do not record width and height, so YOLO prediction imports need `image_width` and `image_height`, and a multi-image COCO results array needs matching IDs and dimensions. `reopen_task` also increments the round of pending and in-progress tasks. A project manager can export training sets only through a global role binding, and `datasets:export` also allows `publish_datasheet`. Templates are shared by every project that uses them. Team-tier heartbeats, skill dispatch, separate annotator and reviewer duties and package acceptance are reserved for a later version.
- Workbench: the canvas is a fixed 480 px high, boxes are not colored by label and show no label name, attributes are edited as JSON, arrow keys move a box one source pixel at a time, the task list shows sample IDs instead of file names, the finalization plan shows raw parameters, and an open task does not refresh when someone else returns it. Prelabel accuracy counts exact matches only, which is strict for boxes. While drawing a polygon, a click on an existing annotation does not add a point, and holding Option+P across a page boundary can skip a task. Large images load progressively rather than as tiles, and there is no service worker, so a fully offline reload depends on the browser cache.
- Datasheets: the number check is still rule-based; on an adversarial held-out set it removed 6 of 48 correct sentences and kept 8 of 77 unsupported ones.

Integration changes in this version:

- PostgreSQL startup changes a training, LLM-data or production trigger only when it is missing or bound to the wrong function, so a restart never waits behind uncommitted writes, and triggers left on the wrong function are rebound.
- Training-split, annotation-import and text-governance write routes are mapped to role scopes, the text-governance clean route records the HTTP actor, and the `project_manager` template gains `datasets:export`.
- COCO prediction import binds images to the `datakeel_sample_id` written by training exports first, so a finalized version exported as COCO imports back without renaming.
- On macOS, Option+N and Option+P navigate workbench tasks only when focus is outside a text field.
- The Agent discovers `production_prelabel_accuracy` through `tool_search` like the other production reads, so its schema is not sent with every request.
- The LLM training-data modules are named `llm_data` in code to keep them apart from training splits; public names are unchanged.

## v0.16.0 release notes

v0.16.0 adds the production team tier on top of v0.15.0 and makes the test and mutation gates run in parallel. Like v0.15.0 it calls no model service, and every write still goes through controlled actions and the access guards.

| Track | What you can do now |
|---|---|
| Team tier | Set a project to `workflow_tier: "team"` (or upgrade a group project) to run it with several annotators and reviewers. Claims and assignments become leases of `lease_minutes` that the holder renews with `heartbeat`; a reaper in the worker (or `datakeel production reap`) returns abandoned work to its queue without losing a revision, and releases every lease exactly once. Choose per project whether managers assign, the system dispatches by skill (level threshold, then fewest active tasks, then user id) or people claim, and cap each person with `max_active_tasks`. Nobody reviews a task they annotated in any round. When a package is fully approved, `package_acceptance` previews a P26 sample and a person signs `accept_package`: a pass accepts the package, a fail sends the whole package back for rework. A team project finalizes only after every package is accepted. Managers can take work back with `revoke_assignment`, including tasks still held by the unregistered `local`. [Production workflows](PRODUCTION.md#team-tier). |
| Team-tier capacity (B8) | `python -m scripts.scale_bench B8` runs 50 virtual annotators for 10 minutes against 10,000 tasks with two reaper processes, then checks the database for overlapping claims and double releases. On a quiet development machine PostgreSQL measured next-task p95 69–72 ms and save p95 66–67 ms over two runs, SQLite next-task p95 17 ms and save p95 52–55 ms, both with 0 duplicate claims. [Capacity](CAPACITY.md). |
| Faster gates | `make check` runs pytest on parallel workers, each test on its own copy of a migrated database, and the mutation gate runs mutations side by side in separate source copies. On the 15-core development machine the SQLite pytest step fell from 94 minutes to about 12.5 and the PostgreSQL step from more than 85 minutes to about 18. `DATAKEEL_TEST_WORKERS` picks the worker count; `1` runs serially. No test or threshold changed. [Test execution guide](TEST_SPEED.md). |

**The team tier now enforces its rules.** In v0.15.0 a team project still behaved like a group project. Now an expired lease turns the holder's save, submit, heartbeat and review into an explicit 409 and the reaper reclaims the work; annotators cannot review their own tasks; `max_active_tasks` refuses claims and assignments above the cap; and finalization requires every package to be accepted. Upgrading to the team tier starts a full lease for every open assignment. Group and personal projects behave exactly as before.

**`reopen_task` changed.** It counts a rework round only when submitted, in-review or approved work is sent back. Reopening a pending or in-progress task now leaves its round, state, assignment and revisions as they are; before, it added a round and sent in-progress work back to pending.

**MCP now exposes 99 tools instead of 92**: 36 read functions (new: `lease_status`, `skill_workload`, `package_acceptance`) and 63 actions that only prepare plans (new: `heartbeat`, `revoke_assignment`, `configure_project`, `accept_package`). There is still no approve or execute tool. MCP hosts that pin the tool list must refresh it.

**New scope `production:accept`.** `accept_package` needs it; the `project_manager` and `administrator` templates have it and the acceptance observer stays read-only. `heartbeat` uses the existing `production:claim`. Built-in templates you have not edited pick this up on upgrade; an edited template keeps its saved scopes, so add `production:accept` yourself where needed.

**PostgreSQL locking changed for production work.** Claim, release, heartbeat, save, submit and review no longer take the table-wide action lock. They first take a `lineage_events` lock that conflicts only with table-wide actions, then their task row, so annotators run concurrently while every action still locks tables before rows. Counting a person's load is serialized per project and person with an advisory lock. SQLite is unchanged.

**Other behavior changes.** Running the PostgreSQL test suite needs a database role with `CREATEDB`, because each test gets its own cloned database. `assign_tasks` gains `strategy: "skill"` and returns `unassigned`; projects gain `lease_minutes`, `dispatch_strategy`, `skill_requirement` and `max_active_tasks`. The only new CLI command is `datakeel production reap`. Nothing was renamed or removed: OpenAPI keeps 164 paths, adds the `SkillRequirement` schema (376 to 377), four `action_type` values and fields that are optional or have defaults. The database gains two append-only tables and one nullable column. The mutation gate has 386 anchors, the golden suite 52 cases and the operator catalog 42 operators.

Known limits:

- Revoking or reassigning a task whose holder keeps autosaving usually fails with a 409 ("Action target state changed after preparation"). The manager's plan freezes the whole task, including its latest revision, and every save changes it; in a public reproduction with a save every 2 seconds and 3 seconds between preparing and confirming, none of six revokes went through. Nothing is lost; prepare again and confirm quickly. The fix, freezing only the state, round and holder, is planned with the next workbench update.
- Right after an upgrade to the team tier, `lease_status` shows each open assignment's old recorded expiry, which is already in the past, while `seconds_remaining` reflects the lease actually enforced. The first heartbeat corrects it. Assignments that were already open in a project upgraded to the team tier under v0.15.0 have no enforced deadline until their first heartbeat.
- Two rules are still open and may change: the load cap counts submitted work waiting for review, and a single `assign_tasks` request may pass a `max_active_tasks` above the project's cap. Rework goes only to the original annotator; after a revoke it cannot be assigned to anyone else (409), so rework whose annotator has left stays stuck until that person returns.
- The annotation workbench does not send heartbeats yet and has no screens for leases, revoking, team settings or package acceptance. In a team project, renew leases and run these actions through the API, CLI or MCP-prepared plans until the next workbench update.
- Skill requirements are set per project or per request, not per package. `datakeel production reap --now` records the time you pass as the release time.
- PostgreSQL makes about 50 database round trips per production action, so its latency rises steeply when CPU is contended; keep headroom (see [Capacity](CAPACITY.md)).
- Tests: on PostgreSQL every per-test database drop forces a checkpoint, which keeps the parallel PostgreSQL pytest step at about 18–21 minutes on the development machine. Where Docker resolves the sandbox base image over a slow registry connection, the first sandbox security test can wait about two minutes while the other workers stay idle. The custom scheduler builds on private pytest-xdist interfaces, so the dependency is pinned below 4. CI timings with four workers are estimates until the first CI run.

Integration changes in this version:

- Merging the team tier with v0.15.0's `production_prelabel_accuracy` combined both sides: the production read dispatcher serves all thirteen reads, `production_prelabel_accuracy` and the three team reads are deferred Agent tools, the production guides list all of them, and the counts were recomputed (MCP 99, Agent deferred 92, ontology functions 36, mutation anchors 386).
- `web/src/api/generated.ts` was regenerated from the merged OpenAPI; the automatic merge had missed the new `Project` and `Assignment` fields and `SkillRequirement`.
- The approval sheet labels `heartbeat`, `revoke_assignment`, `configure_project` and `accept_package` in English and Chinese, and the workbench test fixtures carry the new project fields, so the frontend type-checks again.
- The production guide no longer says the workbench sends heartbeats; the identity guide lists the team-tier scopes.
- The concurrent two-scheduler worker test waits at a barrier so both schedulers deterministically read the due window.

## v0.17.0 release notes

v0.17.0 makes the annotation workbench comfortable for long sessions and gives the v0.16.0 team tier its screens. It calls no model service; every write still goes through controlled actions and the access guards, and MCP and agents can still only prepare plans.

| Track | What you can do now |
|---|---|
| Full-window work area | An open task fills the window below the module and operation bars: on a 1440×1000 window the canvas takes 0.816 of the height and on 1280×720 0.744 (about 0.71 in the team tier, which adds the lease timer), with no page scroll. **Hide details** collapses the right drawer (664 → 919 px of canvas width at 1440). Boxes and polygons use their label's colour, or a fixed eight-colour palette, with a label-name chip that keeps its screen size at any zoom. Tasks are named and searched by file name everywhere. [Workbench guide](ANNOTATION_WORKBENCH.md). |
| Attribute forms | Templates define typed attribute fields (`boolean`, `enum`, `multi_enum`, `number`, `text`) with Chinese and English names, `required`, a default and a target of every shape or the whole record. The workbench renders a keyboard-reachable form; a missing required field blocks autosave and submission and names the shape and field, and the server returns 422 for the same mistakes from any client. [Attribute fields](PRODUCTION.md#labels-predictions-and-finalization). |
| Precise keyboard editing | Arrow keys move by one source-image pixel and Shift+arrows by ten at any zoom; `R` switches between moving, the right/bottom edges and the left/top edges of a box, or to the selected polygon point. `Alt+N` / `Alt+P` pressed during loading are queued, so rapid presses across page edges land on the right task. |
| Tasks that refresh themselves | An open task polls a small status read every 5 seconds (30 while hidden) and says when it was returned for rework, changed elsewhere or got someone else's revision. In the team tier the page renews its lease automatically, shows the time left and, when the lease expires or a manager takes the task back, locks editing and lets you export the draft. The design compares polling, server-sent events and WebSocket. [Open tasks refresh themselves](ANNOTATION_WORKBENCH.md#open-tasks-refresh-themselves). |
| Team-tier cockpit | Managers see each package's acceptance state and sampling, accept or reject a package by marking the sampled tasks, preview a skill dispatch (who gets how many, why a task is skipped) before signing it, and take work back from **Who holds what**. Each step shows a plan in plain words before anyone signs. The finalization plan likewise says how many approved tasks go into which dataset version and what blocks it. |

**Reclaiming and dispatching no longer fail while the holder keeps saving.** `revoke_assignment` and `assign_tasks` plans now freeze only each task's state, round and current holders, so autosaves, model draft imports and lease renewals between preparing and confirming leave them valid; a submission, a new round or a new holder still voids them. With a save every 2 seconds and 3 seconds between preparing and confirming, six of six reclaims succeeded on SQLite and on PostgreSQL (none did in v0.16.0). Other actions freeze exactly what they did before.

**`lease_status` shows the deadline actually enforced**, including after an upgrade to the team tier restarted a lease.

**Templates with attribute fields reject human revisions that break them.** A person's `save_revision` with a wrong type or a missing required field fails with 422 naming the key and the shape, and `submit_task` checks the head revision again. Model revisions are only type-checked. Templates without attribute fields behave as before.

**Workbench changes you will notice.** Shift+arrows no longer resize a box; use `R` to switch to its edges. In the team tier the review view and the opened task hide approve and return controls for work you annotated (the server already refused it). Raw JSON attribute editing is offered only to project managers, under **Advanced: raw attributes**; tasks on templates without attribute fields still open and save as before. A concurrent change shows "Someone else just changed this task" with **Try again** instead of raw server text.

**Other changes.** New HTTP reads: `GET /api/production/tasks/{id}/status`, `GET /api/production/projects/{id}/task-samples` and `POST /api/production/projects/{id}/dispatch-preview` (computes without locking or writing), plus a `search` query on the project workbench list. OpenAPI grows from 164 to 167 paths and from 377 to 389 schemas; nothing was removed and no required field was added. MCP still has 99 tools; the `create_label_set` template only gains the optional `attributes`. No CLI command, table or migration changed. The mutation gate has 402 anchors (sixteen added), the golden suite 52 cases and the operator catalog 42 operators.

Known limits:

- Datasets record only a file's base name at import, so the workbench shows and searches file names, not paths inside the dataset: files with the same name in different folders look identical and searching a folder name finds nothing.
- A template with both box and polygon components shows two canvases stacked.
- At fit zoom a very long label name can be partly covered by a neighbouring chip, and at high zoom a chip stays at its shape's top-left corner even when that corner is off screen.
- Attribute fields apply to every shape or to the record; they cannot yet depend on the label.
- A dispatch preview does not reserve anything; if loads change before execution, the receipt is authoritative.
- Still open from v0.16.0: the load cap counts submitted work waiting for review, a single `assign_tasks` request may pass a `max_active_tasks` above the project's cap, and rework goes only to the original annotator, so rework whose annotator has left stays stuck. Skill requirements are set per project or per request, not per package. Assignments that were already open when a project was upgraded to the team tier under v0.15.0 have no enforced deadline until their first heartbeat, which the workbench now sends when the task is opened. PostgreSQL makes about 50 database round trips per production action, so keep CPU headroom (see [Capacity](CAPACITY.md)).

Integration changes in this version:

- The production guide no longer says the workbench does not send heartbeats; it links to the workbench's automatic renewal.
- The README states the new mutation count and what the v0.17.0 anchors protect, and the workbench pointer mentions attribute forms and the team-tier cockpit.
- The workbench guide states that tasks on older templates still open and save and that only project managers see raw JSON attributes; the API descriptions of the sample `path` now say it is the file name until imports record a path inside the dataset; the two workbench limits on file names and long label chips are in the [backlog](BACKLOG.md).

## v0.18.0 release notes

v0.18.0 brings GitHub CI down to about half an hour, closes gaps in redaction, lets reclaimed early work go to a named person, keeps folder paths and image sizes at import, and stops long label chips from getting in the way. It calls no model service; every write still goes through controlled actions and the access guards, and MCP and agents can still only prepare plans.

| Track | What you can do now |
|---|---|
| CI in about half an hour | Each stack (SQLite and PostgreSQL) runs a gate job, four pytest shards, two mutation shards and a report job. The report checks that every collected test ran in exactly one shard, then merges coverage and mutation results and applies the unchanged thresholds. Three green runs took 27–29 minutes instead of about two and a half hours. A pull request starts one run, a tag push none, and one stack failing no longer cancels the other. [CI layout](TEST_SPEED.md#ci-layout--ci-分片). |
| Redaction that fits real text | The English labels `secret`, `token`, `key` and `auth` mask only credential-like values, so prose such as `The secret: practice every day.` stays; passwords mask from four characters; `DB_PASSWORD=`, `GITHUB_TOKEN=` and other configuration keys are labels. Phones in brackets follow mainland and North American rules, a bracketed mobile prefix such as `(138) 1234 5678` is masked whole, and order or reference numbers are left alone. [Training data governance](LLM_DATA.md). |
| Assign to a named person | In the team-tier cockpit a manager ticks unheld tasks, picks a registered annotator (shown with what they hold now), and signs a named assignment. Work assigned to `local` before anyone registered can be taken back and handed to a real person without registering `local`. [Workbench guide](ANNOTATION_WORKBENCH.md#saving-and-review). |
| Folders and image sizes kept at import | Importing a directory records each file's path inside it; the workbench shows it on hover and finds tasks by folder name, and the machine's own path is never returned. Image imports record width and height from the header, so YOLO predictions need no size when the image has one; without any size the import is refused with the image named. |
| Label chips out of the way | A chip is no wider than its shape (56–160 px), ends in an ellipsis with the full name on hover, stays inside the visible canvas when zoomed, and never takes the pointer, so drawing and selecting on top of it work as on the canvas. Without a lease timer the personal tier's canvas regains height (0.826 of a 1440×1000 window, 0.758 of 1280×720). |

**Redaction masks less prose and more real secrets.** After `secret`, `token`, `key` or `auth` a value is masked only when it has no whitespace, at least eight characters and looks issued: two of letters, digits and symbols, all digits, all letters with a capital after the first, or a random-looking hex/base64 string of sixteen characters or more. In v0.17.0 any eight characters after `secret` or `token` were masked. Password-class labels now mask from four characters instead of eight, and configuration keys whose last segment is a credential word (`DB_PASSWORD=`, `REDIS_PASS=`, `STRIPE_SECRET_KEY=`) count as labels.

**Phone detection is stricter.** A bracketed area code must be mainland (starting with 0, or `+86`) or North American (area and exchange both starting 2–9), so `(555) 123-4567` is no longer a phone. Digits right after 编号, 订单号, 批次, `No.`, `Order` or `#`, or right before 号, are references. Two phones separated by one space are reported separately, and a phone never starts or ends inside a pair of brackets.

**YOLO imports without a size are refused as a whole.** When neither the request nor the recorded image has a size, the import returns 422 naming the image and the prediction file instead of listing a failure. Datasets imported before v0.18.0 have no recorded sizes: pass `image_width`/`image_height`, use a complete COCO document, or import the images again. A multi-image COCO results array lists results for unknown images as `unknown_image` (with how many were not imported) and images without a size as `unknown_size`.

**The mutation gate survives a slow runner.** A subprocess that times out is measured once more in a fresh copy; a second timeout is listed as an environment failure, the report is still written and the gate fails with one line naming the mutation and command. A timeout never counts as a kill.

**Other changes.** New HTTP read `GET /api/production/projects/{id}/assignees?stage=annotation` (or `review`), for callers who may assign. OpenAPI grows from 167 to 168 paths, 180 to 181 operations and 389 to 391 schemas; nothing was removed and no required field was added; the description of the workbench sample `path` now says it is the path under the imported directory. MCP still has 99 tools with unchanged schemas. No CLI command, table or migration changed. The mutation gate has 438 anchors (thirty-six added), the golden suite 52 cases and the operator catalog 42 operators.

Known limits:

- After `secret`, `token`, `key` or `auth`, an all-caps word (`token: IMPORTANT`), a camel-case word (`auth: JavaScript`) or eight or more digits (`key: 20261030`) is masked, because the rule cannot tell them from issued credentials.
- Files imported on their own still show only the file name. Datasets imported before v0.18.0 show only file names and have no recorded image sizes until they are imported again.
- The cockpit assigns annotation work by name; review work is not offered there, although the list read accepts `stage=review`. MCP always acts as `local`, so once people are registered it is refused like an HTTP call without a registered actor.
- Still open from earlier versions: a template with both box and polygon components shows two canvases stacked; attribute fields cannot depend on the label; a dispatch preview reserves nothing; the load cap counts submitted work waiting for review; a single `assign_tasks` request may pass a `max_active_tasks` above the project's cap; rework goes only to the original annotator; skill requirements are set per project or per request, not per package; PostgreSQL makes about 50 database round trips per production action (see [Capacity](CAPACITY.md)).

Integration changes in this version:

- The README states the new mutation count, what the v0.18.0 anchors protect and how a timed-out mutation is handled, and the workbench pointer mentions assigning by name and folder paths.
- The two workbench limits fixed here (file names only, long label chips) moved from the backlog's open list to its done list.


## v0.19.0 release notes

v0.19.0 adds AI prelabel with a cloud vision model, accuracy measured by IoU, confidence tiers and an AI pre-review of every submission; shows, labels, imports and exports photos upright; locks each project to its template version; and tightens workbench rules for load limits and rework. MCP and agents can still only prepare plans, and every write still goes through controlled actions and the access guards. The only network calls are to a cloud model you register; tests and the demo never make them.

| Track | What you can do now |
|---|---|
| AI prelabel with a cloud model | Register an OpenAI-compatible vision endpoint with `provider: "cloud"` (tested with Alibaba Cloud Bailian; qwen3.5-flash cost about ¥0.0016 per image in our benchmark), prepare `run_prelabel` with a budget and see the estimate before signing. The budget is a hard ceiling, failures are listed by file name, reruns only fill what is missing and skip tasks a person already saved, and only the credential's name is stored. The cockpit shows **Prelabel runs** (refreshed every five seconds) and **Prelabel spend by model**. [AI prelabel](PRODUCTION.md#ai-prelabel-confidence-tiers-and-ai-pre-review). |
| Accuracy and confidence tiers | **Prelabel accuracy** leads with F1 at IoU 0.5 (one-to-one matching within a label from the highest IoU down) and lists IoU 0.75 and attribute agreement under **How it is measured**. **Confidence tiers** come from a calibration curve on approved work or from `configure_project`: in group and team projects a high draft on a task no one holds goes straight to submission, a medium draft stays for correction, and a low draft starts the annotator from empty with **Use model draft** one click away. A task someone holds only gets the draft. |
| AI pre-review | Each submission gets a risk score from weighted reasons: data-quality rules, the locked template, disagreement with a confident draft, a swapped label, a size outlier, near-duplicate images annotated differently and mutually exclusive labels. Reviewers see the reasons with **Locate** buttons, the queue is ordered by risk, and **Review sampling** lets a signed decision skip review for a share of low-risk work (high risk is always reviewed; every skip is audited). |
| Photos upright | The EXIF orientation is applied in the workbench, thumbnails, imports, exports and evidence, so a phone photo looks and is labelled the way a browser shows it. Older annotations are converted when read; original files and stored rows are never changed. Rotated images export as upright lossless PNG with the transform recorded in `MANIFEST.json`. [Image orientation](ANNOTATION_WORKBENCH.md#image-orientation). |
| Template versions per project | A project keeps the template version it was created with. The **Template version** card says "Current template v1, latest v2"; **Prepare upgrade** lists label and attribute changes and which existing annotations would fail, and **Sign and upgrade** changes only that project. |
| Fairer workbench rules | The load limit counts only open annotation work, so submitted tasks free a slot. A single dispatch may only lower the project's limit. A reclaimed rework round can go to a named person, and neither the original nor the new annotator may review it. |

**Photos are upright everywhere.** Imports record the upright `width`/`height` with `stored_width`, `stored_height` and `orientation`; earlier datasets read them from the image header. Revisions, annotation batches and training splits saved before this version are stored-frame data and are converted when read, with `coordinate_conversion` saying how. YOLO predictions use the upright size; a COCO file whose declared size matches only the stored size is converted on import, and `coordinate_frame` overrides the inference. COCO, YOLO, HF and classification ImageFolder exports no longer refuse rotated or mirrored images. The workbench serves rotated JPEGs as JPEG at quality 95 and other formats as lossless PNG, with an `ETag` so repeated opens return 304.

**Evidence boxes on rotated photos need one more extraction.** `evidence.image_phash` and `evidence.annotation_labels` are now version 1.1. `datakeel rebuild-evidence` only replays stored results and leaves old boxes where they were; run the extraction again for each paired dataset with rotated photos, as the [workbench guide](ANNOTATION_WORKBENCH.md#image-orientation) shows. Only those two extractors reread the images; the old assertions are retired as `extractor_version_changed` and stay in the audit.

**Editing a shared template no longer changes existing projects.** Saving, submission checks, the workbench form and finalization read the project's locked version. Upgrading an earlier database locks every project to the template revision it was using, and opening it again writes nothing. Upgrades are the new controlled action `upgrade_project_template`, which needs human approval.

**A model draft cannot be submitted as a person's work.** `submit_task` returns 422 while the current revision is a model draft; the workbench saves the annotator's own revision first when they submit a draft unchanged.

**Pass-through is answered for.** A passed-through revision records the model, confidence, thresholds and the person who ran the prelabel; that person becomes the annotator, cannot review it in team projects, even after its rework goes to someone else, and each pass-through has an audit line. With fewer than 30 measured objects, high drafts are held as drafts. Starting or widening pass-through needs a signature. Pass-through applies only to tasks no one holds: an assigned or claimed task, touched or not, or a rework round back with its annotator only gets the draft and keeps its state and holder; **Prelabel runs** shows "Held by someone, drafts only: N".

**The load limit and dispatch limit changed.** Submitted work no longer counts against a person's limit and returned rework counts again; claiming, named assignment, skill dispatch and the picker's "open now" all use this count. An `assign_tasks` request with `max_active_tasks` above the project setting is refused with 422.

**Ask in English answers in English.** The "Understood as" line, recognised conditions, knowledge answers and chart titles use English names, and the **Recorded reason** follows the interface language. A recognised time expression that cannot be turned into a range (last century, the nineties, 上个世纪, 去年同期, a fiscal year, Q5) is refused with the reason instead of being dropped.

**Other changes.** An object page shows only its own kind's tabs, and the metric page no longer requests releases. Label chips are drawn above every shape. The operation bar shows the sample's relative path, and the search says "relative path or file name". MCP has 101 tools (37 read functions and 64 prepare-only actions): `assignees` and `upgrade_project_template` are new, and six tools gain optional fields. OpenAPI keeps 168 paths and 181 operations and grows from 391 to 404 schemas; nothing was removed and no request gained a required field. The database gains `production_template_versions`, `production_ai_reviews` and a nullable `coordinate_frame` on three tables, added automatically when an earlier database is opened. No CLI command or operator changed. The mutation gate has 546 anchors (108 added), the golden suite 52 cases and the operator catalog 42 operators.

Known limits:

- A cloud prelabel run is synchronous for the caller, who waits for the finished receipt; other projects keep working because no lock is held while the model answers. A process killed mid-run leaves the run `running` until the next run takes it over after 10 minutes.
- A model's first estimate uses a prior of 160 output tokens per call; crowded scenes with many labels may cost about twice that. Try a small budget first (later estimates learn from it) or raise `expected_output_tokens`.
- Keychain credentials use the macOS `security` command; elsewhere use an environment variable. qwen3.7-flash returned HTTP 403 for the tested account and is not in the benchmark.
- Confidence thresholds have no cockpit editor; set them with `configure_project`. Under the local identity only the person who prepared a plan can sign it.
- Tasks a person already saved are skipped by later prelabel runs, also with a newer model; reopen the task or use a new project to prelabel it again. The cockpit does not show the skipped count yet (it is in the run record, receipt and estimate). `import_predictions` still places a model draft on top of a person's revision.
- Returned rework may put its holder above the load limit; it is not a new dispatch. The group tier has no reclaim button (use the API), and review separation is enforced only in the team tier.
- For square images and for orientations 2–4, a COCO file or evidence sidecar cannot be told apart by size; its boxes are taken as upright unless `coordinate_frame` says otherwise. The canvas re-encodes rotated JPEGs at quality 95, so it is not byte-identical; exports are lossless.
- The selected shape's transform handles can sit under a label chip; chips never take the pointer, so the handles still work.
- Still open from earlier versions: a template with both box and polygon components shows two canvases stacked; attribute fields cannot depend on the label; a dispatch preview reserves nothing; the cockpit assigns only annotation work by name; MCP always acts as `local`; skill requirements are set per project or per request, not per package; PostgreSQL makes about 50 database round trips per production action (see [Capacity](CAPACITY.md)).

Integration changes in this version:

- The prelabel model now sees the upright pixels the workbench shows, so drafts on rotated photos land on the object; accuracy and AI pre-review read drafts saved before this version upright; cloud prelabel and AI pre-review use the template version the project is locked to.
- Whoever triggered a pass-through stays out of review after a manager hands its rework to someone else, on the server and in the workbench.
- High-confidence pass-through only applies to tasks no one holds, in every tier. Assigned or claimed work, touched or not, and a rework round back with its annotator only get the draft; state and holder stay, the tier is recorded as `draft` with the note `held`, and the run's `held_drafts` and **Prelabel runs** give the count. Before, an import could pass a returned rework round through and record the trigger as its annotator.
- The README states 101 MCP tools, 546 mutation anchors and what the v0.19.0 anchors protect, and the workbench pointer mentions template upgrades, AI prelabel and upright photos.
