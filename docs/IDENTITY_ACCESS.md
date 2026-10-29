# Identity and HTTP access

Registered roles are the source of action authority. Global bindings and bindings for the action's actual project are combined. An action's declared caller scopes can narrow that result. Task and package targets are resolved to their stored project, and mixed-project task batches are rejected.

An instance with no registered users preserves the local single-user behavior. The first registered user receives `administrator` unless explicit `role_ids` are supplied. Once users exist, unknown and disabled actors can read but cannot mutate business objects. Deleting users archives their identity, so deleting the final account does not reopen anonymous writes.

Five editable role templates are available: `administrator`, `project_manager`, `annotator`, `reviewer`, and `acceptance`. The acceptance template has no write scopes. `project_manager` also includes `datasets:export`, so finalized project versions can be split and exported for training; dataset writes such as text cleaning and annotation imports stay with `administrator` or a custom role. Custom role scopes must come from the registered action policies. A role plan lists all allowed and denied actions, including actions sharing a scope. Preparing or approving a role does not install it; only execution does. Role project scope cannot be moved by an update: define a different role for another project.

Role approval may be signed by another administrator. The actual signer is recorded, and their current grant ceiling is checked both at approval and at execution. Execution remains owned by the preparing actor. Binding an existing role also checks the grant ceiling, so user administration cannot indirectly mint privileges. Other actions retain their existing actor rules, including independent review for asset access applications.

## Legacy HTTP mutation matrix

The HTTP dependency classifies matched route templates without changing their request or response schemas. It uses the request's `X-Datakeel-Actor`, then resolves the listed existing action policy. Legacy dataset endpoints have global scope; project-scoped authority applies through the production action endpoints, which resolve the actual project internally. All GET, HEAD, and OPTIONS requests keep their read behavior.

| Method and route | Existing action policy | Effective scope |
| --- | --- | --- |
| POST `/api/datasets` | `save_metadata` | `datasets:write` |
| PUT `/api/datasets/{identifier}/metadata` or `/template` | `save_metadata` | `datasets:write` |
| PUT `/api/datasets/{identifier}/quality/config` | `create_quality_rule` | `quality:write` |
| POST `/api/tasks` | `run_pipeline` | `pipelines:run` |
| POST `/api/uploads`, PUT upload chunks, POST upload completion | `save_metadata` | `datasets:write` |
| POST `/api/lineage/events` or `/api/openlineage/events` | `import_catalog` | `catalog:write` |
| POST `/api/catalog/import/dbt` or `/airflow` | `import_catalog` | `catalog:write` |
| POST `/api/custom-operators` | `submit_custom_operator` | `operators:submit` |
| POST `/api/custom-operators/{code_hash}/runs` | `run_pipeline` | `pipelines:run` |
| POST `/api/datasets/{dataset_id}/annotation-quality/batches` | `save_metadata` | `datasets:write` |
| POST annotation-quality `/samples` or `/acceptance/prepare` | `annotation_acceptance` | `annotations:accept` |
| POST `/api/evidence/assertions/decide` or `/api/kg/links/rerun` | `decide_assertions` | `evidence:write` |
| POST `/api/datasets/{dataset_id}/datasheets` | `generate_datasheet` | `datasets:write` |
| POST `/api/datasheets/{document_id}/publish` | `publish_datasheet` | `datasets:export` |
| POST `/api/agent/memories`, DELETE `/api/agent/memories/{memory_id}` | `manage_users` | `users:manage` |
| POST version `/training/splits` | `export_dataset` | `datasets:export` |
| POST version `/training/import-annotations` | `save_metadata` | `datasets:write` |
| POST dataset `/text-governance/analyze` or `/text-governance/evaluations`, POST `/api/training-governance/{run_id}/clean` | `clean_training_data` | `datasets:write` |

Catalog ingestion includes lineage observations because both publish catalog facts. Dataset imports, binary uploads, and legacy annotation batches share the existing dataset-write authority. Explicit memory administration uses the existing user-administration scope. Saved training splits exist only to define export packages, so they share the export scope; text dry runs and evaluation registrations are durable inputs of the cleaning action and share its scope. These mappings add no permission vocabulary.

Read computations remain available through POST: ontology evaluation, production functions, training split previews and leakage checks, evidence queries, graph queries, and questions. Query conversations, access applications, release download/reconciliation, and their supporting audit state remain available; an access application cannot grant access. Agent conversations and deterministic workflows may start read operations. Their business action tools independently enforce the current actor's server authority. The generic action preparation, approval, and execution routes enforce their own action and project policy. After registration, a newly added mutation route without a classification is rejected. A route-inventory regression test checks that every current mutation route is explicitly classified.

## Runtime identities and compatibility

Agent conversations and deterministic workflow runs have a server-owned session-to-actor binding. New HTTP sessions use the actual request actor. Send, resume, and workflow-start replay reject another actor, and delegated sessions inherit the parent binding. Tool calls use this binding rather than an implicit `local` identity. Legacy unbound sessions belong to `local`.

The existing public conversation `actor: local` field remains a compatibility field. The binding is authoritative for execution and audit. New production action tools only prepare plans; human approval and execution use the Web or CLI paths. Successful request replay rechecks current server authority and returns its original receipt without repeating a mutation.

| Implementation choice | Result | Reason and source |
| --- | --- | --- |
| Change every legacy request schema to add an actor field | Not selected | Would change the existing HTTP contracts; the request header already provides actor attribution. See [action routes](../datakeel/api/routes/actions.py). |
| Authorize by HTTP method alone | Not selected | Read queries use POST and must remain available. See [query routes](../datakeel/api/routes/evidence.py). |
| Explicit matched-route matrix plus existing controlled-action policies | Selected | Keeps old schemas, preserves read computations, reuses registered scopes, and detects unclassified writes. See [HTTP access policy](../datakeel/api/identity_access.py) and [regression tests](../tests/api/test_identity_access.py). |
| Change legacy conversation response actor schemas | Not selected | Existing clients retain their response shape. |
| Server-owned runtime identity binding | Selected | Retains old responses while attributing tools, delegation, and resume to the actual caller. See [runtime bindings](../datakeel/storage/identity_sessions.py). |

Existing non-production CLI management commands use the local process identity and remain part of the local trusted library boundary. Production CLI commands accept an explicit actor and pass through the same controlled action authorization. Direct Python storage calls and SQL require access to the local database; HTTP role checks protect the application transport rather than creating a database authentication layer.

History projection, cached response replay, and source-attributed memory retrieval check the runtime owner's current asset grants. HTTP memory reads use the request actor. Agent and workflow history lists include only sessions owned by that actor; direct history, tree, audit and routing reads reject another owner. This preserves the existing asset-grant rules when different people use the same installation.
