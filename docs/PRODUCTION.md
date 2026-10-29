# Production workflows

[中文](PRODUCTION.zh.md)

Production projects pin a dataset version, a published label-set version and an optional annotation template. The output is another dataset version plus an ordinary annotation batch. Release reconciliation and datasheet facts consume the same version manifest and annotation metadata.

## Objects and relationships

`GET /api/ontology` describes fourteen added object kinds: `user`, `team`, `role`, `skill`, `label_set`, `template`, `project`, `task_package`, `production_task`, `assignment`, `annotation_revision`, `review`, `model`, `prelabel_run`. The original worker `task` remains a separate identity. All objects use `AssetRef`; label-set identity includes its version. Team and skill edits feed team-tier skill dispatch; a skill's `level` (1–10) is what dispatch compares.

Projects contain packages, packages contain tasks, and tasks reference immutable revisions, assignments and reviews. Membership, role bindings, skills, assignment owners, review targets, previous revision pointers and pinned configuration use the shared ontology link vocabulary. Read authoritative projections with `GET /api/production/objects/{kind}`; optional filters are `object_id`, `project_id`, `task_id`, `version`, `limit`.

## Six states and three tiers

| State | Meaning |
| --- | --- |
| `pending` | Ready for annotation, including returned work |
| `in_progress` | Annotation work has begun or was assigned |
| `submitted` | An exact revision awaits review |
| `in_review` | A reviewer has claimed the submitted task |
| `approved` | An exact revision is approved for finalization |
| `finalized` | That revision has entered a new dataset version |

Rework returns a task to `pending`, increments its round and retains the original annotator. There is no automatic escalation; progress lists tasks with at least three rework rounds. Package and project status come from six counters updated in the same transaction as each task transition. They have no separate mutable status.

| Tier | Behavior |
| --- | --- |
| `personal` (default) | Save/import, then submit directly to `approved`. No assignments or review rows; the action audit records `SYSTEM_APPROVAL`. |
| `group` | Named assignment or self-claim, submit, review, return with issues, resubmit, approve. Self-review is allowed. |
| `team` | Group rules plus enforced leases with heartbeats, a per-project dispatch strategy (assign, skill or claim), strict separation of annotator and reviewer, and P26 sampling acceptance of every package before finalization. See [Team tier](#team-tier). |

`upgrade_project` permits only forward transitions. Downgrading is rejected because completed review history cannot be reinterpreted as an earlier workflow. A second project participant produces `suggest_review: true` once in the relevant receipt. It never changes the tier automatically. Every assignment records a lease expiry; only team-tier projects enforce it (group and personal behavior is unchanged).

When a personal project upgrades, editable tasks with saved human work receive an annotation assignment for their existing author. The author can continue saving, submit for review or release the task through the normal holder checks, without reopening or incrementing the round. Task state and revision history are preserved; unowned tasks, model-only predictions and approved work receive no new assignment. Preserving historical ownership grants no role scopes and does not bypass current account authorization. After release, the author must claim or receive an assignment again.

## Controlled writes

Each request has a required client-generated `request_id`. Prepare, inspect and execute through the existing action protocol. Actions always record audit, lineage and a durable receipt, including actions without an approval step.

| Actions | Approval |
| --- | --- |
| `create_label_set`, `split_packages`, `assign_tasks`, `claim_task`, `release_task`, `heartbeat`, `save_revision`, `submit_task`, `review_task`, `reopen_task`, `revoke_assignment`, `configure_project`, `upgrade_project`, `manage_users`, `manage_skills`, `import_predictions` | None |
| `publish_label_set`, `create_project`, `register_model`, `update_model`, `define_role`, `update_role`, `accept_package`, `finalize_project` | Human approval |
| `run_prelabel` | Human approval if task count × configured unit price exceeds the request budget |

`create_label_set` also manages template definitions with `target: "template"` and `operation: "create" | "update" | "delete"`. User/team operations are under `manage_users`; skill operations are under `manage_skills`. The action schemas specify all fields, authorization scopes and bilingual examples.

A repeated preparation with the same actor/action/request ID and identical input returns the original plan. Repeated successful execution returns its original run and receipt. Reusing the ID with changed input or caller limits is a conflict. A premature missing-approval attempt is audited and can be retried after signing. To correct failed inputs, use a fresh request ID. `save_revision.previous_revision_id` must equal the server head; HTTP 409 includes `latest_revision`. Both databases reject direct UPDATE and DELETE of revision history, and enforce one active assignment per task/stage with a unique partial index. Losing a claim selects the next available task.

## Roles and identity

With zero registered users, authorization preserves local unrestricted behavior, including existing actions and evaluations. The first registered user receives the administrator template unless roles were explicitly supplied. Once any user is registered, unknown, disabled or archived actors have read-only authority; archiving the last user does not restore anonymous writes.

Effective scopes are the union of active global role bindings and bindings to the actual project. Caller-declared scopes only narrow this union. A project role cannot authorize another project's tasks, and a batch cannot mix projects. Claim/release use `production:claim` plus the stage's annotation or review permission; reviewers do not acquire annotation-edit permissions merely to claim review work.

Five editable templates are available: `administrator`, `project_manager`, `annotator`, `reviewer`, `acceptance`. Acceptance has no write scopes. `project_manager` also holds `datasets:export` for training splits and exports of finalized versions. Roles can use only registered action scopes, never `*` or invented scopes. Role plans list every allowed and denied action. Definitions and updates become effective only after human approval and execution; the signer's current grant ceiling is checked at both points. A separate authorized administrator may sign a role plan; the original actor executes it. Other action approval identity contracts remain unchanged. Asset applicants still cannot approve their own applications.

HTTP actor selection uses `X-Datakeel-Actor` after registration, and decision bodies must name that same actor. Legacy mutation routes enforce the corresponding server scope. Runtime session ownership is stored separately from the legacy conversation display actor, so a request cannot borrow a privileged Agent/workflow session. These names describe actors in a locally trusted installation; deployment-level authentication remains an independent boundary.

MCP and Agent expose production reads and prepare-only writes. They cannot sign or execute production plans. Existing non-production reversible Agent behavior remains compatible. Humans use Web approval cards or explicit CLI/API calls.

## Team tier

The team tier adds rules on top of the group tier; objects, states and actions are the same, and a group or personal project behaves exactly as before.

**Leases.** A claim or assignment is a lease of `lease_minutes` (default 10, per project, `configure_project` changes it). The holder renews it with `heartbeat` (the workbench sends one every two minutes). After the deadline every holder write (`save_revision`, `submit_task`, `heartbeat`, `review_task`) fails with an explicit "lease expired" conflict instead of succeeding silently; once reclaimed, the error says so. The reaper runs inside the existing worker loop (and as `datakeel production reap [--now ISO] [--limit N]`). It returns expired annotation work to `pending` and expired review work to `submitted`; saved revisions and the revision head are kept, so the next holder continues from them. A lease only runs while its stage is active, so an annotator's retained assignment is not reclaimed while the task waits for review, and a rework return gives it a fresh lease. Each release is one row in the append-only `production_lease_releases` table keyed by the assignment, and the reaper rereads the assignment under the task lock (`FOR UPDATE SKIP LOCKED` on PostgreSQL), so concurrent or repeated reaper processes release each lease exactly once and an interrupted pass can simply run again. Upgrading a group project to the team tier starts enforcing the expiry already recorded on its open assignments.

**Dispatch.** `dispatch_strategy` is per project: `assign` (managers assign; self-claim is refused), `skill` (managers run `assign_tasks` with `strategy: "skill"`; self-claim requires the skill) or `claim` (self-claim, the default). All three write the same assignment table and the one-active-assignment unique index still applies; each assignment records its source in `dispatch` (`assign`, `skill`, `claim` or `preserved`). A skill requirement names an annotation type, a domain and `min_level`. A person qualifies when an active skill bound to them matches type and domain at that level or above; level is only a filter. Among qualified people with the stage permission, tasks are taken by priority (highest first) then task id, and each goes to the person with the fewest active assignments of that stage in the project, ties broken by the smallest user id; the load counts each assignment as it is made, so a batch is reproducible. Rework goes only to the original annotator and review dispatch skips everyone who annotated the task. `max_active_tasks` (project setting, or per request) caps each person's active assignments: skill batches stop at the cap and list skipped tasks in `unassigned` with a reason, named batches above the cap are rejected whole, and claims at the cap are refused.

**Separation of duties.** In the team tier nobody who annotated a task in any round reviews it: the current annotator, every author of a human revision and every past holder of its annotation assignment are excluded. The rule is checked when a review is claimed (the queue skips such tasks), assigned and recorded, so reassignment, a later role change or a reopen cannot launder it. Group projects still allow self-review.

**Package acceptance.** When every task of a package is approved, `package_acceptance` previews the P26 sample for it (`method` `aql` with `aql`, or `ratio` with `ratio` and `acceptance_number`, plus `seed`); the units are the package's samples, and lot, sample size, sample identities and decision numbers are computed by the same code path as P26 `annotation_qa` sampling. A person signs `accept_package` with one check per sampled unit (exactly the sample). The package is accepted when defective units do not exceed the acceptance number; otherwise every task in the package, sampled or not, returns to `pending` with its round increased by one and its original annotator. A team project finalizes only when every package's latest decision is an acceptance covering the current approved revisions, so reopening and re-approving a task requires a new acceptance.

**Administration and rounds.** `revoke_assignment` (scope `production:assign`, held by managers and administrators) returns an in-flight annotation or review stage to its queue, keeps revisions, and records the release with its reason. It works for any holder, including `local` assignments created before anyone registered. Submitted or approved work is reopened instead. `reopen_task` counts a rework round only when submitted or approved work is sent back; reopening a pending or in-progress task leaves its round, state, assignment and revisions as they are (design section 5).

**Reads.** `lease_status` lists running leases by deadline split into live, expiring within `expiring_within_seconds` (default 120) and overdue, plus recent releases with their reason. `skill_workload` sums active assignments and completed tasks per active skill. `package_acceptance` returns a package's status (`in_progress`, `ready`, `accepted`, `rejected`), progress, the sample preview when ready and its latest decision.

**Roles.** `heartbeat` (`production:claim`) is in the annotator and reviewer templates; `configure_project` (`production:manage`), `revoke_assignment` (`production:assign`) and `accept_package` (`production:accept`) are in the project manager template; administrators hold every scope and the acceptance observer stays read-only. MCP and Agent may prepare these plans but never approve or execute them.

## Labels, predictions and finalization

Publish a draft label set to seal that version permanently. New versions declare a migration for every renamed or removed label: rename, delete, merge or split. Splits require manual review. Publishing does not rewrite historical revisions. Impact counts are exact current annotation instances (each classification label, box or span) in tasks of projects pinned to the old version; superseded historical revisions are excluded. A separate affected-revision count is reported. `label_set_diff` recomputes current impact rather than estimating from totals.

`register_model` supports `fake` and `import`. No provider makes network calls. Import files as text in `files` with `filename`, `content`, and optional exact sample identity/dimensions. COCO boxes are pixel `xywh`; YOLO rows are normalized `class cx cy width height [confidence]`. The internal representation is pixel `xyxy`. Category mapping resolves label identities/names explicitly; unmapped categories, out-of-bounds boxes, empty images and malformed files are reported per image/file while valid images continue. COCO result arrays need exact image identities or an explicit single-file sample binding, plus explicit category mapping. Model revisions retain name, version, average box confidence and previous-head identity. COCO images carrying the `datakeel_sample_id` extension written by Datakeel training exports bind to that exact sample first, so a finalized version exported as COCO imports back without renaming. YOLO exports use hashed label filenames; bind each label file with `sample_id` from the archive's `MANIFEST.json` and map class indexes from `data.yaml`.

Prediction bounds allow an absolute `1e-7` pixel rounding tolerance on all four edges, then clip accepted coordinates to the image. This absorbs floating-point conversion noise without scaling the allowance with image size; larger excursions and boxes with no positive area remain invalid.

Ordinary image imports currently do not populate manifest dimensions from image headers. Supply `image_width` and `image_height` for YOLO unless the pinned version already records dimensions. A complete COCO document supplies per-image dimensions in `images`. A multi-image COCO results array requires each `image_id` to match a project sample ID or a unique filename, with dimensions available for every image; exporter sequence numbers are not matched by project order. If dimensions are missing, use a complete COCO document or bind one file per image with `sample_id` and explicit dimensions.

Templates currently validate core boxes, classification and text spans. Polygon/keypoint template identities can be recorded, but saving their unsupported content is explicitly rejected pending their content models. Supported validation rules are `min_annotations` and `max_annotations`.

Only approved tasks can finalize; team projects also need every package accepted. The transaction freezes their approved revisions, writes native annotations and exact annotation/label counts into the new manifest, imports an ordinary `AnnotationBatch`, updates counters and records the producing project in lineage. Input versions and historic revisions remain intact.

## CLI and REST

```sh
uv run datakeel production demo
uv run datakeel production prepare create_label_set labels.json --actor local
uv run datakeel production plan PLAN_ID --actor local
uv run datakeel production approve PLAN_ID --digest PLAN_DIGEST --actor local
uv run datakeel production execute PLAN_ID --digest PLAN_DIGEST --actor local
uv run datakeel production read project_progress project.json --actor local
```

The demo creates three generated images, published labels, a personal project and imported fake predictions. For personal work, use `create_label_set → publish_label_set → create_project → split_packages → register_model → import_predictions → save_revision → submit_task → finalize_project`. For group work, create/bind users with `manage_users`, set `workflow_tier: "group"`, then use `assign_tasks/claim_task → save_revision → submit_task → claim_task(stage=review)/review_task`; a rework decision includes `issues`, and the original annotator saves and submits again before finalization. Sign only the steps listed in the approval table.

REST equivalents are `POST /api/actions/{action_type}/prepare`, `GET /api/actions/plans/{id}`, `POST /api/approvals/{id}`, `POST /api/actions/{id}/execute`. Supply the returned digest for decisions. Read functions are available through `POST /api/production/functions/{name}` and through Agent/MCP: `project_progress`, `package_status`, `annotator_workload`, `rework_rate`, `annotation_consistency`, `prelabel_confidence`, `label_set_diff`, `next_task`, `production_objects`, and for the team tier `lease_status`, `skill_workload`, `package_acceptance`. Agreement reuses the existing annotation-quality evaluator; confidence counts all model revisions with recorded confidence. Rework rate is rework decisions divided by all review decisions per original annotator.

## Implementation choices and sources

| Choice | Alternatives | Reason and source |
| --- | --- | --- |
| Transactional six-state counters | Recount all tasks on each read; asynchronous cache | Bounded progress reads and no stale cache window: [task transitions](../datakeel/storage/production_tasks.py), [queries](../datakeel/storage/production_queries.py). |
| Append-only revisions and partial unique assignment index | Mutable annotation row; application-only ownership checks | Keep auditable history and enforce concurrent ownership in both databases: [constraints](../datakeel/storage/production_rows.py). |
| Existing role/action scopes | Separate authorization service/library | One declared policy and audit source, no runtime dependency: [registry](../datakeel/actions/registry.py), [server authorization](../datakeel/storage/identity_authorization.py). |
| Typed local COCO/YOLO parser | Add a format dependency; read arbitrary server paths | Reuse existing pixel-coordinate convention with bounded input and per-file errors: [legacy adapter](../datakeel/storage/annotation_legacy.py), [parsers](../datakeel/storage/production_prediction_parsing.py). |
| Lease reaper inside the existing worker, one release row per assignment, task lock with `SKIP LOCKED` | A separate scheduler process; per-assignment timers; PostgreSQL advisory locks; deleting expired rows | No new process or dependency, crash-safe reruns and exactly-once release enforced by a primary key. Same visibility-timeout model as [Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html) and [Kubernetes Leases](https://kubernetes.io/docs/concepts/architecture/leases/); [`SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) as already used by the [worker queue](../datakeel/storage/task_queue.py): [reaper](../datakeel/storage/production_reaper.py). |
| Skill match: level threshold, then least active load, then smallest user id | Weighted score of level and load; global optimal matching ([Hungarian, `linear_sum_assignment`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)); round robin | A threshold mirrors [MTurk qualification requirements](https://docs.aws.amazon.com/AWSMechTurk/latest/AWSMturkAPI/ApiReference_QualificationRequirementDataStructureArticle.html) (`GreaterThanOrEqualTo`), so level never trades against load; join-the-shortest-queue balancing is simple to explain and reproduce, needs no dependency and is exactly recomputable by an auditor: [dispatch](../datakeel/storage/production_dispatch.py), [rules](../datakeel/storage/production_dispatch_rules.py). |
| Per-task actions skip the table-wide action lock on PostgreSQL; counters are written at commit in one sorted order | Keep the global `LOCK TABLE` for every action; a per-project advisory lock; counter updates at each transition | Measured with B8: the global lock capped throughput at 13 operations/s (save p95 4.4 s); a project lock would serialize one project the same way. Without it, counter rows written mid-transaction deadlocked a multi-task reaper against claims, so each transaction now applies its counter deltas once, sorted, just before commit, and the reaper commits each release separately. Task row locks and the unique assignment index keep these actions safe: [locks](../datakeel/storage/action_locks.py), [counters](../datakeel/storage/production_counters.py), [CAPACITY](CAPACITY.md). |
| Version plus existing annotation import | A separate production-only export format | Existing release and datasheet consumers retain their contracts: [finalizer](../datakeel/storage/production_finalize.py), [annotation importer](../datakeel/storage/annotation_store.py). |

Generated regression fixtures cover both workflows, two-database claim races, independent read goldens, exact migration counts, partial prediction failure, immutable history, optimistic conflicts and role grant ceilings. The capacity benchmark measures reads and the complete prepare-plus-execute save path on 10,000-task projects.
