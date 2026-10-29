# Production workflows

[中文](PRODUCTION.zh.md)

Production projects pin a dataset version, a published label-set version and an optional annotation template. The output is another dataset version plus an ordinary annotation batch. Release reconciliation and datasheet facts consume the same version manifest and annotation metadata.

## Objects and relationships

`GET /api/ontology` describes fourteen added object kinds: `user`, `team`, `role`, `skill`, `label_set`, `template`, `project`, `task_package`, `production_task`, `assignment`, `annotation_revision`, `review`, `model`, `prelabel_run`. The original worker `task` remains a separate identity. All objects use `AssetRef`; label-set identity includes its version. Team and skill edits are available now; skill dispatch is reserved for the next phase.

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
| `team` | Upgrade retains all data. Heartbeats, skill dispatch, separation of annotator/reviewer and package acceptance are reserved for the next phase. |

`upgrade_project` permits only forward transitions. Downgrading is rejected because completed review history cannot be reinterpreted as an earlier workflow. A second project participant produces `suggest_review: true` once in the relevant receipt. It never changes the tier automatically. Assignment leases have expiry timestamps; this phase does not expire or renew them automatically.

## Controlled writes

Each request has a required client-generated `request_id`. Prepare, inspect and execute through the existing action protocol. Actions always record audit, lineage and a durable receipt, including actions without an approval step.

| Actions | Approval |
| --- | --- |
| `create_label_set`, `split_packages`, `assign_tasks`, `claim_task`, `release_task`, `save_revision`, `submit_task`, `review_task`, `reopen_task`, `upgrade_project`, `manage_users`, `manage_skills`, `import_predictions` | None |
| `publish_label_set`, `create_project`, `register_model`, `update_model`, `define_role`, `update_role`, `finalize_project` | Human approval |
| `run_prelabel` | Human approval if task count × configured unit price exceeds the request budget |

`create_label_set` also manages template definitions with `target: "template"` and `operation: "create" | "update" | "delete"`. User/team operations are under `manage_users`; skill operations are under `manage_skills`. The action schemas specify all fields, authorization scopes and bilingual examples. `heartbeat` and `accept_package` are not registered in this phase.

A repeated preparation with the same actor/action/request ID and identical input returns the original plan. Repeated successful execution returns its original run and receipt. Reusing the ID with changed input or caller limits is a conflict. A premature missing-approval attempt is audited and can be retried after signing. To correct failed inputs, use a fresh request ID. `save_revision.previous_revision_id` must equal the server head; HTTP 409 includes `latest_revision`. Both databases reject direct UPDATE and DELETE of revision history, and enforce one active assignment per task/stage with a unique partial index. Losing a claim selects the next available task.

## Roles and identity

With zero registered users, authorization preserves local unrestricted behavior, including existing actions and evaluations. The first registered user receives the administrator template unless roles were explicitly supplied. Once any user is registered, unknown, disabled or archived actors have read-only authority; archiving the last user does not restore anonymous writes.

Effective scopes are the union of active global role bindings and bindings to the actual project. Caller-declared scopes only narrow this union. A project role cannot authorize another project's tasks, and a batch cannot mix projects. Claim/release use `production:claim` plus the stage's annotation or review permission; reviewers do not acquire annotation-edit permissions merely to claim review work.

Five editable templates are available: `administrator`, `project_manager`, `annotator`, `reviewer`, `acceptance`. Acceptance has no write scopes. Roles can use only registered action scopes, never `*` or invented scopes. Role plans list every allowed and denied action. Definitions and updates become effective only after human approval and execution; the signer's current grant ceiling is checked at both points. A separate authorized administrator may sign a role plan; the original actor executes it. Other action approval identity contracts remain unchanged. Asset applicants still cannot approve their own applications.

HTTP actor selection uses `X-Datakeel-Actor` after registration, and decision bodies must name that same actor. Legacy mutation routes enforce the corresponding server scope. Runtime session ownership is stored separately from the legacy conversation display actor, so a request cannot borrow a privileged Agent/workflow session. These names describe actors in a locally trusted installation; deployment-level authentication remains an independent boundary.

MCP and Agent expose production reads and prepare-only writes. They cannot sign or execute production plans. Existing non-production reversible Agent behavior remains compatible. Humans use Web approval cards or explicit CLI/API calls.

## Labels, predictions and finalization

Publish a draft label set to seal that version permanently. New versions declare a migration for every renamed or removed label: rename, delete, merge or split. Splits require manual review. Publishing does not rewrite historical revisions. Impact counts are exact current annotation instances (each classification label, box or span) in tasks of projects pinned to the old version; superseded historical revisions are excluded. A separate affected-revision count is reported. `label_set_diff` recomputes current impact rather than estimating from totals.

`register_model` supports `fake` and `import`. No provider makes network calls. Import files as text in `files` with `filename`, `content`, and optional exact sample identity/dimensions. COCO boxes are pixel `xywh`; YOLO rows are normalized `class cx cy width height [confidence]`. The internal representation is pixel `xyxy`. Category mapping resolves label identities/names explicitly; unmapped categories, out-of-bounds boxes, empty images and malformed files are reported per image/file while valid images continue. COCO result arrays need exact image identities or an explicit single-file sample binding, plus explicit category mapping. Model revisions retain name, version, average box confidence and previous-head identity.

Templates currently validate core boxes, classification and text spans. Polygon/keypoint template identities can be recorded, but saving their unsupported content is explicitly rejected pending their content models. Supported validation rules are `min_annotations` and `max_annotations`.

Only approved tasks can finalize. The transaction freezes their approved revisions, writes native annotations and exact annotation/label counts into the new manifest, imports an ordinary `AnnotationBatch`, updates counters and records the producing project in lineage. Input versions and historic revisions remain intact.

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

REST equivalents are `POST /api/actions/{action_type}/prepare`, `GET /api/actions/plans/{id}`, `POST /api/approvals/{id}`, `POST /api/actions/{id}/execute`. Supply the returned digest for decisions. Read functions are available through `POST /api/production/functions/{name}` and through Agent/MCP: `project_progress`, `package_status`, `annotator_workload`, `rework_rate`, `annotation_consistency`, `prelabel_confidence`, `label_set_diff`, `next_task`, `production_objects`. Agreement reuses the existing annotation-quality evaluator; confidence counts all model revisions with recorded confidence. Rework rate is rework decisions divided by all review decisions per original annotator.

## Implementation choices and sources

| Choice | Alternatives | Reason and source |
| --- | --- | --- |
| Transactional six-state counters | Recount all tasks on each read; asynchronous cache | Bounded progress reads and no stale cache window: [task transitions](../datakeel/storage/production_tasks.py), [queries](../datakeel/storage/production_queries.py). |
| Append-only revisions and partial unique assignment index | Mutable annotation row; application-only ownership checks | Keep auditable history and enforce concurrent ownership in both databases: [constraints](../datakeel/storage/production_rows.py). |
| Existing role/action scopes | Separate authorization service/library | One declared policy and audit source, no runtime dependency: [registry](../datakeel/actions/registry.py), [server authorization](../datakeel/storage/identity_authorization.py). |
| Typed local COCO/YOLO parser | Add a format dependency; read arbitrary server paths | Reuse existing pixel-coordinate convention with bounded input and per-file errors: [legacy adapter](../datakeel/storage/annotation_legacy.py), [parsers](../datakeel/storage/production_prediction_parsing.py). |
| Version plus existing annotation import | A separate production-only export format | Existing release and datasheet consumers retain their contracts: [finalizer](../datakeel/storage/production_finalize.py), [annotation importer](../datakeel/storage/annotation_store.py). |

Generated regression fixtures cover both workflows, two-database claim races, independent read goldens, exact migration counts, partial prediction failure, immutable history, optimistic conflicts and role grant ceilings. The capacity benchmark measures reads and the complete prepare-plus-execute save path on 10,000-task projects.
