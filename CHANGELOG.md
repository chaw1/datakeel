# Changelog

All notable changes are documented here using the Keep a Changelog format.

## [Unreleased]

## [0.17.0] - 2026-10-30

### Added

- The annotation workbench gives an open task the whole window: the work area fills the height below the module and operation bars and follows resizes, image tools sit in a narrow left rail, and **Hide details** collapses the right drawer to widen the canvas. Boxes and polygons are drawn in their label's colour (labels without one take a fixed eight-colour palette, `--label-1`…`--label-8`, checked by `check:contrast` in both themes) with a label-name chip that keeps its screen size at any zoom. Task lists, the review queue and the cockpit name tasks by sample file name and search by it. See the [workbench guide](docs/ANNOTATION_WORKBENCH.md).
- Template attribute fields. A template may define up to 50 typed `attributes` (`boolean`, `enum`, `multi_enum`, `number` with an optional range, `text` with `max_length`), each with `key`, `name_zh`, `name_en`, `required`, an optional `default` and a `target` of `object` (every box, polygon and text span) or `record`. The workbench renders them as a keyboard-reachable form; a missing required field blocks autosave and submission and names the shape and field. The server applies the same rules (below). See [attribute fields](docs/PRODUCTION.md#labels-predictions-and-finalization) and the comparison with CVAT, Label Studio, Labelbox and JSON Schema in the production guide.
- Open tasks refresh themselves. The page polls the new `GET /api/production/tasks/{id}/status` every 5 seconds (every 30 seconds while the tab is hidden, with an immediate read when it is shown again) and says within that interval when the task was returned for rework, changed state elsewhere or received someone else's revision; local drafts are kept. In the team tier the page renews the lease with `heartbeat` when the task opens and then every 2 minutes, or every third of the lease when the lease is shorter, shows the time left and offers **Renew now** after a failed renewal. When the lease expires or the task is taken back, editing locks, nothing more is sent and the draft can be exported as JSON. The design compares polling, server-sent events and WebSocket.
- Team-tier cockpit: package acceptance state and sampling for every package, **Accept package** (mark each sampled task, prepare an `accept_package` plan that states the outcome, then sign it), **Dispatch by skill** (preview each person's current and added load and why each unassigned task was skipped, then prepare and sign `assign_tasks` with `strategy: "skill"`) and **Who holds what** (`lease_status`, with a signed `revoke_assignment` to take a task back). MCP and agents can still only prepare these plans.
- The finalization plan is stated in plain words: how many approved tasks are finalized, into which dataset as a new version built on which version, and how many unapproved tasks block it; the digest and raw parameters move under **Details**.
- New workbench reads under the existing project and task grants: `GET /api/production/projects/{id}/task-samples` (file names for up to 500 tasks), `POST /api/production/projects/{id}/dispatch-preview` (computes without locking or writing what a skill dispatch would do now, sharing its matching code with execution) and `GET /api/production/tasks/{id}/status`. `GET /api/production/projects/{id}/workbench` accepts `search`, a case-insensitive substring of the sample file name applied before paging, and returns `task_samples`. Sample names come from the pinned manifest's file name; server paths and object keys are never returned.

### Changed

- **`revoke_assignment` and `assign_tasks` plans now freeze only each task's state, round and current holders.** A holder's autosaves, a model draft import or a lease renewal between preparing and confirming no longer void a reclaim or dispatch with "Action target state changed after preparation"; a submission, a round change or a new holder still does. In v0.16.0 a reclaim of a task whose holder kept autosaving usually failed. `submit_task`, `review_task`, `reopen_task`, `release_task` and `heartbeat` still freeze the whole task, its active assignments and the project, and acceptance and finalization still freeze the exact approved revisions.
- **`lease_status` reports the deadline actually enforced.** After an upgrade to the team tier restarted a lease, the listed assignment's `lease_expires_at` is the restarted deadline instead of the stale recorded one.
- **Templates that define attribute fields reject human revisions that break them.** `save_revision` from a person fails with HTTP 422 naming the key and the position (for example `Attribute "colour" is required on box 1`) for a wrong type or a missing required field, and `submit_task` rechecks the head revision, so a field made required after a save blocks submission until it is filled. Model revisions are type-checked only. Templates without attribute fields, and keys a template does not define, behave as before.
- **Workbench keyboard steps changed.** Arrow keys move a box, a polygon or the polygon drawing cursor by one source-image pixel and Shift+arrows by ten, whatever the zoom. `R` switches the arrows to a box's right/bottom edges, then its left/top edges, then back to moving (Shift+arrows no longer resize), and to the selected point of a polygon. The left rail states the current mode.
- **In the team tier the workbench review view omits tasks the caller annotated**, by the same rule the review claim applies, and an opened task that this person annotated in any round shows no approve or return controls; the server refused such a review before as well.
- **Raw JSON attribute editing in the workbench is offered only to project managers**, under **Advanced: raw attributes**; annotators and reviewers no longer see it and edit attributes through the template form. Tasks on templates without attribute fields still open and save as before.
- A concurrent-change 409 in the workbench is shown as "Someone else just changed this task" with **Try again** instead of the raw server text.
- Package, API and frontend versions advance to 0.17.0. The mutation gate has 402 anchors (386 before; sixteen `workbench-*` and `production-team-*` anchors added, none removed), the golden suite 52 cases and the operator catalog 42 operators, both unchanged. MCP still lists 99 tools (36 read functions and 63 prepare-only actions); the only schema change is the optional `attributes` on the `create_label_set` template. OpenAPI grows from 164 to 167 paths, 177 to 180 operations and 377 to 389 schemas, adds the optional `ProductionTemplate.attributes`, `WorkbenchProject.task_samples` and the `search` query, and neither removes anything nor adds a required field. No CLI command, MCP tool, operator or table was added, renamed or removed, and there is no database migration.

### Fixed

- The mutation gate gives each full golden evaluation 900 seconds instead of 300. Mutations run in parallel, and on a slow shared CI runner one evaluation exceeded 300 seconds and aborted the whole gate; test subprocesses keep their 300-second limit.
- The scale benchmark's HTTP workload checks its deadline after each request, so every virtual user measures at least one route. On a slow CI runner a user scheduled after a 1-second test deadline previously sent nothing, and the four-route check failed.
- `Alt+N` / `Alt+P` pressed while a page or task is still loading are queued and replayed in order, so rapid presses across page edges land on the right task.
- While drawing a polygon, a click on top of an existing shape adds a point, including the first one.
- After a task is taken back, a save refused because the caller no longer holds it locks the page instead of showing a raw 403 and **Retry save**; **Back to list** leaves at once and reloads the list.
- The production guide no longer says the workbench does not send heartbeats.
- The workbench guide states exactly what older templates keep and who sees raw JSON attributes, and the API descriptions of the sample `path` (`task-samples`, `WorkbenchSampleName`) say what it is today: the file name, because imports record no path inside the dataset yet.

## [0.16.0] - 2026-10-30

### Added

- Team tier for production projects (`workflow_tier: "team"`): enforced assignment leases renewed with `heartbeat` and released by a reaper that runs in the existing worker loop or as `datakeel production reap [--now ISO] [--limit N]`; a per-project `dispatch_strategy` (`assign`, `skill` or `claim`), `lease_minutes` and `max_active_tasks`, changed in place with `configure_project`; skill dispatch through `assign_tasks` with `strategy: "skill"` (level threshold, then fewest active assignments, then smallest user id, so a batch is reproducible), listing skipped tasks in `unassigned`; strict separation of annotator and reviewer; package acceptance with `accept_package`, which samples with the same code path as P26 `annotation_qa` and returns the whole package for rework when it rejects; and `revoke_assignment`, which takes in-flight work back from any holder, including the unregistered `local`. New reads are `lease_status`, `skill_workload` and `package_acceptance`. Each lease is released exactly once (one row per assignment in the append-only `production_lease_releases`), and inspections are kept in the append-only `production_package_inspections`. See [Team tier](docs/PRODUCTION.md#team-tier).
- B8 team-tier capacity workload (`python -m scripts.scale_bench B8`): virtual annotators claim, save three times and submit for 10 minutes against 10,000 tasks while two reaper processes run, then the database is checked for overlapping claims and double releases. On a quiet development machine, 50 annotators on PostgreSQL measured next-task p95 69–72 ms and save p95 66–67 ms over two runs, and 50 on SQLite next-task p95 17 ms and save p95 52–55 ms, with 0 duplicate claims and every abandoned lease reaped once. See [capacity](docs/CAPACITY.md).
- Parallel tests and mutations. `make check` runs pytest through `python -m scripts.run_pytest` on pytest-xdist with a `loadgroup` scheduler: the real sandbox security group runs alone first, then long tests are dispatched early. Every `db` fixture receives a complete copy of a per-worker migrated template (an SQLite backup, or a PostgreSQL database created from that template), and every test has its own home directory. `scripts/mutate.py` runs mutations concurrently, each still in its own source copy. `DATAKEEL_TEST_WORKERS` sets the worker count (default `min(16, CPU count)`; `1` runs serially); CI sets 4. On the 15-core development machine the SQLite pytest step fell from 94 minutes serial to about 12.5, the PostgreSQL step from more than 85 minutes to about 18, and the 250 mutations of that time ran in about 7 minutes. No test is skipped, deselected or repeated, and the coverage thresholds are unchanged. See the [test execution guide](docs/TEST_SPEED.md).

### Changed

- **The team tier now enforces its rules; group and personal projects are unchanged.** In v0.15.0 a team project behaved like a group project. Now a lease expires `lease_minutes` (default 10) after the claim or the last heartbeat: the holder's `save_revision`, `submit_task`, `heartbeat` and `review_task` then fail with an explicit lease-expired 409, and the reaper returns expired annotation work to `pending` and expired review work to `submitted`, keeping every revision. Nobody who annotated a task in any round can claim, be assigned or record its review, so group-style self-review is refused. `max_active_tasks` caps each person's active assignments per stage: a claim at the cap is refused, a named batch above it is rejected whole, and a skill batch stops at it. A team project finalizes only when every package's latest acceptance covers its current approved revisions, so reopening and re-approving a task needs a new acceptance. Upgrading a project to the team tier gives every open assignment a full lease from the upgrade moment.
- **`reopen_task` counts a rework round only when submitted, in-review or approved work is sent back.** Reopening a `pending` or `in_progress` task now leaves its round, state, assignment and revisions as they are (previously the round increased and an in-progress task returned to `pending`); the action audit still records the request.
- **MCP lists 99 tools instead of 92: 36 read functions and 63 prepare-only actions.** New reads are `lease_status`, `skill_workload` and `package_acceptance`; new actions are `heartbeat`, `revoke_assignment`, `configure_project` and `accept_package`. There is still no approve or execute tool. Hosts that pin the tool list must refresh it. The Agent finds the three new reads through `tool_search` (resident tools stay at 10, deferred tools grow from 85 to 92), and the ontology lists 36 functions instead of 33.
- **New authorization scope `production:accept` for `accept_package`**, held by the `project_manager` and `administrator` templates; the acceptance observer stays read-only. `heartbeat` uses `production:claim` (annotator and reviewer templates), `configure_project` uses `production:manage` and `revoke_assignment` uses `production:assign`. Unedited built-in templates pick these up automatically; a template you edited keeps its saved scopes, so add `production:accept` to it if its holders accept packages.
- **PostgreSQL lock model for production actions.** The six single-task actions (`claim_task`, `release_task`, `heartbeat`, `save_revision`, `submit_task`, `review_task`) no longer take `SHARE ROW EXCLUSIVE` on `datasets, lineage_events, versions, file_states`; they take `ROW EXCLUSIVE` on `lineage_events` first and then lock their task row. Every other action keeps the table-wide lock, which still excludes them, so all actions lock tables before rows. Claims, named assignment and skill dispatch take a transaction-level advisory lock per (project, person), in user-id order, before counting a load. Package and project counters change once at commit in a fixed order, a known member no longer locks the project row, and the reaper commits each release separately. SQLite already serializes writers and is unchanged.
- `assign_tasks` accepts `strategy` (`assign` by default, or `skill`), `candidates`, `skill_requirement` and `max_active_tasks`; `actor` is required only for named assignment, and the result adds `unassigned`. `create_project` accepts `lease_minutes`, `dispatch_strategy`, `skill_requirement` and `max_active_tasks`. Assignments record `dispatch`, `ended_at` and `end_reason`. A load-cap error names the current load, how many tasks the request adds and the cap.
- **Running the PostgreSQL test suite now needs a role with `CREATEDB`**, because each test receives its own cloned database; the fixture accepts only `localhost` or `127.0.0.1`. `pytest-xdist` (below 4) is a new development dependency.
- Package, API and frontend versions advance to 0.16.0. The mutation gate has 386 anchors (376 before; ten `production-team-*` anchors added, none removed), the golden suite 52 cases and the operator catalog 42 operators, both unchanged. OpenAPI keeps 164 paths and 177 operations; schemas grow from 376 to 377 (`SkillRequirement`), the `ActionPlan` and `ActionRun` `action_type` enums gain the four new actions, and `Project` and `Assignment` gain fields that are optional or have defaults, with nothing removed and no new required field. `datakeel production reap` is the only new CLI command; no CLI command, HTTP path, MCP tool, operator or table was renamed or removed. Schema changes are additive: two append-only tables and the nullable, indexed `production_assignments.lease_expires_at`.

### Fixed

- The approval sheet labels the four new team actions in English and Chinese; without these labels the frontend no longer type-checked after the merge.
- The `manage_skills` description no longer says that skill-based dispatch is disabled.
- Test isolation under parallel workers: the concurrent two-scheduler worker test uses a barrier so both schedulers read the due window, the point-cloud module that shares one seeded random generator stays on one worker in collection order, PostgreSQL test copies keep a pooled connection and drop reliably, and sandbox test images no longer carry a measurement prefix.

## [0.15.0] - 2026-10-30

### Added

- Training splits and exports: **Versions → Training sets**, `datakeel training distribution|create|list|leakage|compare`, the read tools `training_distribution` and `training_leakage`, and `/api/datasets/{dataset}/versions/{version}/training` preview and save seeded train/validation/test splits as immutable, version-owned snapshots. Stratification balances every label, including multi-label samples (algorithm `1.3-iterative-text`; the source can be `all`, `classification`, `detection` or `spans`); metadata groups and duplicate components are never split, and `test=0` gives two sets. Leakage checks report exact content (SHA-256), near-duplicate images (dHash, default distance ≤ 8), near-duplicate text (64-bit SimHash over normalized character trigrams, default distance ≤ 3) and shared groups pair by pair. The existing `export_dataset` action writes COCO, YOLO, ImageFolder, Hugging Face imagefolder and text JSONL archives (`.tar`, `.tar.gz` or `.tgz`) bound to a version, split and annotator, reproducible byte for byte; `POST .../training/import-annotations` brings COCO or YOLO labels back as a new review batch. See the [training guide](docs/TRAINING.md).
- LLM training-data governance: the **Text data governance** tab, `/api/datasets/{id}/text-governance`, `/api/training-governance/{run_id}`, `datakeel training-quality`, the read tool `get_training_quality` and the operator `text.training_quality` check SFT, instruction and preference JSONL line by line for structure, length, language, quality heuristics, exact and bounded near duplicates, prompt conflicts, PII and credentials, and overlap with registered evaluation sets. Analysis is a dry run; the `clean_training_data` action prepares a cleaning plan that a person approves before a reproducible cleaned version with lineage is created. Recorded signals feed quality scores and datasheets. The optional Rust extension (`make check-rust`) adds fingerprint and long-text similarity kernels with identical results. Code modules are named `llm_data`; the public tool, CLI, API, operator and table names keep the `training` prefix. See the [LLM data guide](docs/LLM_DATA.md).
- Production projects: fourteen ontology object kinds (users, teams, roles, skills, label sets, templates, projects, task packages, tasks, assignments, revisions, reviews, models and prelabel runs); personal and group tiers with a forward-only upgrade to team; named assignment and claim with one active assignment per task; append-only revisions with an optimistic lock (HTTP 409 returns `latest_revision`); label-set versions with declared migrations and exact impact counts; offline COCO/YOLO prediction import; and finalization into an ordinary dataset version and annotation batch. Twenty-one controlled actions (for example `define_role`, `save_revision`, `finalize_project`) and ten read functions (for example `project_progress`, `next_task`, `production_prelabel_accuracy`) are available through `datakeel production`, REST, the Agent and MCP; `datakeel production demo` creates a personal project. See [production workflows](docs/PRODUCTION.md) and [identity and HTTP access](docs/IDENTITY_ACCESS.md).
- Annotation workbench (`#/labeling`): box, polygon, classification and text-span editors; **My data**, **My tasks**, **Review queue** and **Project cockpit** shown by effective role; an immediate local draft with a 500 ms debounced save, offline retry and an explicit choice on a revision conflict; undo and redo; prefetch of the next two tasks; progressive loading of large images (a 1024-pixel preview, then the original); keyboard operation for every field (`?` lists shortcuts). Finalized records round-trip losslessly through `export_dataset` with `format: "annotations_jsonl"` and the matching import. The canvas uses konva 10.9.0 and react-konva 19.3.2. See the [workbench guide](docs/ANNOTATION_WORKBENCH.md).
- Quality-rule results record `rows_total`, `rows_scanned` and `coverage` in the API, report and Web run details.

### Changed

- **Role-based authorization applies as soon as one user is registered.** With zero registered users nothing changes. The first registered user receives the administrator template; from then on HTTP writes act as `X-Datakeel-Actor`, every action and legacy write route needs a server-computed scope (global role bindings plus bindings for the action's own project), caller-declared scopes can only narrow it, and unknown, disabled or archived actors are read-only; archiving the last user does not reopen anonymous writes. Agent and workflow sessions stay bound to the actor that created them. Training-split and annotation-import writes map to `export_dataset` and `save_metadata`, text-governance writes to `clean_training_data`; the `project_manager` template includes `datasets:export`. Local CLI commands outside `datakeel production` remain a trusted local boundary.
- **MCP lists 92 tools instead of 57: 33 read functions and 59 prepare-only actions.** New reads are `training_distribution`, `training_leakage`, `get_training_quality` and ten production reads; new actions are `clean_training_data` and twenty-one production and role actions. There is still no approve or execute tool. Hosts that pin the tool list must refresh it.
- **`text.pii_redact` with its default replacement now writes typed placeholders** (`[EMAIL]`, `[PHONE]`, `[CREDENTIAL_URL]`, `[SECRET]`, `[CHINA_ID]`, `[BANK_CARD]`, `[IP]`) instead of `[REDACTED]`. A custom `replacement` is still used verbatim, and explicit memory writes keep `[REDACTED]`. The shared detector, also used by table PII inference and memory writes, adds checksum-valid Chinese identity numbers, Luhn-valid bank cards, IP addresses, key and token patterns, credential URLs, and labelled credentials in English and Chinese (`password：`, `密码：`, `密码是：`). Credential URLs and bare credential values stop before adjacent Chinese text and closing punctuation, and a URL with a Chinese or empty host still has its user name and password redacted.
- **Phone detection boundaries changed.** A candidate needs complete digit boundaries, so 12- and 14-digit bare order or ticket numbers are no longer treated as phones, and landlines with a parenthesized area code in ASCII or full-width brackets, such as `(0571) 8888-6666`, are now detected.
- **COCO, YOLO and Hugging Face imagefolder exports refuse images whose EXIF orientation rotates or mirrors them**, because the exported boxes would not match the pixels a loader shows. Normalize such images before import; ImageFolder exports are unaffected.
- **Quality rules scan the whole target table.** `max_rows` keeps its YAML range but now bounds each streaming batch and the returned SQL-assertion violations instead of the number of rows checked; a rule that errors reports coverage `unknown` rather than passing a partial scan.
- Annotation consensus counts one vote per annotator; extra boxes or spans from the same annotator in one cluster are reported as `duplicate_bbox` or `duplicate_span`.
- Data-standard suggestions treat amount, cycle, status and date/time as mutually exclusive context groups, with date and time compatible: `order_status` and `订单周期` no longer suggest `order_date`, while `order_time` still does. Chinese `周期` normalizes to `cycle`, so `账单周期` and `billingCycle` behave the same; billing synonyms map invoice to bill/billing and keep receipt separate.
- Datasheet number checks match the counted object and field label; record-state wording (candidate, needs review and their Chinese forms) and field short names derive from product states and bilingual field names instead of fixed lists.
- Audio operators decode in 65,536-sample chunks; on a generated 30-minute mono recording the default pipeline's peak memory fell from 5.78 GB to 142 MB with identical outputs.
- Busy upload initialization, chunk and completion requests return `409` with `Upload is busy; retry after the active upload operation completes`. Editing the release form clears the displayed plan, and release lists show file counts with a unit (for example **2 files** / **2 个文件**).
- Export receipts keep the versioned dataset reference beside the unversioned one, so lineage for an export lists one more, more precise input.
- Package, API and frontend versions advance to 0.15.0. The mutation gate has 376 anchors (192 before), the golden suite 52 cases (49 before) and the operator catalog 42 operators (`text.training_quality` added). OpenAPI grows from 144 to 164 paths without removing a path or method, and no CLI command, HTTP path, MCP tool, operator or table was renamed.

### Fixed

- PostgreSQL startup issues trigger DDL only when a training, LLM-data or production trigger is missing or bound to the wrong function, so a restart no longer waits behind uncommitted version or production writes; triggers left on the wrong function are rebound.
- COCO prediction import binds images to the `datakeel_sample_id` written by Datakeel training exports first, so a finalized version exported as COCO imports back as predictions without renaming.
- On macOS, Option+N and Option+P navigate workbench tasks only when focus is outside a text field, so typing `ñ` or `π` there still works.
- The Agent discovers `production_prelabel_accuracy` through `tool_search` like the other production reads instead of receiving its schema with every request, which kept conversations within their token ceilings.
- The Darwin local subprocess sandbox measures worker memory with libproc and stops a live worker it cannot measure (previously an unreadable measurement let it continue), while a worker that is already exiting is no longer reported as a runtime error.

## [0.14.0] - 2026-10-29

### Added

- Scale benchmark and capacity baseline: `python -m scripts.scale_bench <B1..B7> --size S|M|L --stack sqlite|postgres` runs file import and paging, parallel import, catalog and lineage, Ask over large fact tables, fifty concurrent users, ten thousand worker tasks under SIGKILL and a million-edge graph with a fixture fingerprint, a failure envelope and self-cleanup; `make check-scale` guards version comparison against quadratic regressions. [Capacity baseline](docs/CAPACITY.md) records the measured M/L figures, the targets not yet met and when to prefer PostgreSQL.
- Bounded reads: `GET /api/datasets/{id}/files` accepts optional `offset`, `limit`, `q` and `modality`; file pages, global search, catalog and lineage reads, frozen file selection, object projection, task leases and upload completion no longer read the whole dataset or its version history.
- Ask charts: an answer carries a declarative chart chosen from the result shape (value card, line, vertical or horizontal bars, grouped bars or table); the Web Ask page draws it as SVG with keyboard switching to the source table; metric contracts register units and number formats; the compiler buckets by day, month, quarter or year.
- Ask conversations: HTTP, CLI, Agent tools and MCP accept `conversation_id` to keep asking in one thread; a follow-up changes only the named part (dimension value, time, grouping, metric, year-over-year, period-over-period or share) and shows "Understood as" with the complete question; ambiguous follow-ups clarify and return no number; threads persist in SQLite or PostgreSQL, are re-authorized on every turn and can be listed, reopened and deleted; `DATAKEEL_ASK_CONVERSATION_RETENTION_DAYS` sets retention.

### Changed

- **MCP no longer exposes `approve_plan` or `execute_plan`.** The server lists 57 tools (20 read functions and 37 plan-only actions). A call named `approve_plan` or `execute_plan` through MCP is refused with a reason and audited as a failed invocation; a person reviews, approves and executes prepared plans on the Web UI or CLI. Hosts that scripted approval through MCP must move that step to the CLI or Web UI.
- Package, API and frontend versions advance to 0.14.0. The mutation gate has 192 anchors.
- The media observation index decodes only version manifests that carry an image or point-cloud measurement, so the default file projection reads one manifest and one file-state batch regardless of version count.

### Fixed

- Inside a conversation, a question-form sentence that no slot explains (for example `why did brand awareness drop`) is answered like a new question — unanswerable with the three nearest metrics — instead of being treated as a follow-up with the previous metric as the only candidate.

## [0.13.1] - 2026-10-28

### Added

- Audio and video preprocessing with user-installed `ffmpeg`/`ffprobe`: probe, invalid frames (black, solid, frozen, blurred), repeated video, fixed-window segmentation on packet timestamps, normalization, voice activity, edge-silence trimming, loudness against a configurable accepted range, clipping, repeated audio and multi-recording alignment. A recording that fails stays in the output with its operator and reason instead of failing the task; `demo-media` runs the chain on generated or your own local recordings; recording and clip pages show probes, issue intervals, alignment, processing history and clip links.
- Image quality measurement (blur, exposure, noise, resolution and solid color with each failed check's measured reason, EXIF orientation and 16-bit depth handled) and point-cloud operators for PLY/PCD files: probe, unit check, cleanup, voxel downsampling, statistical outliers that separate isolated points and separated clusters from occluded or distant structure, and top-down PNG previews on the file object page. An unreadable image or scan is listed with its reason and the rest of the batch completes. `scripts/demo_media.py` runs an offline end-to-end example.

### Changed

- Package, API and frontend versions advance to 0.13.1.
- Quality scoring applies tabular rules, image and point-cloud multipliers and recording deductions in that order. The quality view's `media` summary is present only when recordings were measured; image and point-cloud observations live under `image_pointcloud` in the dimension details.
- The image and point-cloud preset is `datakeel.pipeline.image_pointcloud.image_pointcloud_pipeline()`; `datakeel.pipeline.media.media_pipeline()` is the audio/video chain.
- Point-cloud preview downloads pass through the same data-asset download guard as file downloads.
- Lineage records an approved custom operator's code hash as its operator version.

### Fixed

- 修正：ffmpeg 6.1 下冻帧边界与 TS 切片首帧。Video clips start at their first kept frame with audio cut at the same instant, so ffmpeg 6.1 no longer duplicates the first frame of a clip (9.0 shifted it by a frame); the freeze detector's identical-frame floor sits above the residue 6.1's encoder leaves after a cut. Supported ffmpeg is 6.1 or newer, verified on 6.1 and 9.0.

## [0.13.0] - 2026-10-28

### Added

- Sensor time-series and table profiling: mixed timestamp normalization, ordering and deduplication, sampling gaps, stuck values, robust outliers, range and unit checks, column profiles, and sensor-profile answers in Ask.
- Optional Rust acceleration for perceptual-hash near-duplicate search with bit-identical results and an exact mode; `DATAKEEL_ACCEL=auto|off|required` selects the backend.
- Custom Python operators reviewed by code hash and run in a container sandbox without network, with a read-only root, a non-root user, no capabilities and a seccomp filter.
- Image auto mode: local OCR followed by a versioned routing policy; declared visual coordinate spaces are converted to pixels and boxes that fail the OCR cross-check are dropped and marked `coordinates_unreliable`.
- Version comparison in five categories, immutable releases published through approval, delivery packages with offline and platform reconciliation, and resumable chunked uploads.
- Data asset publication with public, restricted and apply-first policies, access applications, expiring or revocable grants, one access guard for Ask, export, download, Agent and MCP reads, and audited governed reads.
- Field standards, code lists and synonyms with reviewed column mappings, approved confirmation and rollback, and table conformance reports.
- Data quality rules for SQLite and PostgreSQL tables (not-null, unique, range, accepted values, regex, referential integrity, allow-listed SQL assertions, volume change, freshness and distribution drift) with scheduled runs, issue recovery and HMAC-signed webhooks.
- dbt manifest, run-result and catalog import, Airflow exports and OpenLineage events with column-level lineage and reviewed metric drafts.
- Annotation agreement (Cohen and Fleiss kappa, Krippendorff alpha, box IoU, span matching), suspect-label detection, ISO 2859-1 (AQL) or fixed-ratio sampling, approved acceptance decisions and rework comparison.
- Seven-chapter dataset datasheets from an offline template or a configured model; every retained sentence cites frozen platform facts, unsupported sentences are removed with their reason, publication needs approval and newer versions mark older datasheets out of date.
- `release-plan prepare|approve|reject|execute` CLI commands for large releases and selected versions.

### Changed

- Package, API and frontend versions advance to 0.13.0. The MCP server exposes 59 tools: 20 read functions, 37 plan-only actions and the approve/execute controls. Its shared tool output schema is compacted so the tool list stays within the 1 MiB SSE event limit.
- English and Chinese metric questions resolve time ranges and filters the same way; generic wording asks for clarification, and questions about a workflow no longer start it.
- `publish_release` and `create_version_from_selection` accept an explicit object/byte budget through HTTP query parameters, the CLI or the release form, capped by `DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS` (default 1,000,000) and `DATAKEEL_RELEASE_BUDGET_MAX_BYTES` (default 1 TiB). The budget is frozen into the approved plan and shown on the approval sheet; other actions keep the 10,000-object / 10 GiB default.
- The Web byte formatter shows GB and TB for large sizes.

### Fixed

- Version comparison orders manifest streams by code point on PostgreSQL (`COLLATE "C"`), so mixed-case or hyphenated file IDs align on databases with ICU or locale collations; an out-of-order stream now stops with an error instead of misclassifying files.
- Profile answers in Ask pass through the data-asset access guard.
- Offline CLI imports no longer load chat-model SDKs through the datasheet worker.

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
