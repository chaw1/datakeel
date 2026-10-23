// Generated from the application OpenAPI schema. Run npm run generate:api.
export interface paths {
    "/api/actions/plans/{plan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Action Plan
         * @description Read the server-owned frozen plan and its current lifecycle status.
         */
        get: operations["action_plan_api_actions_plans__plan_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/actions/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Action Runs
         * @description Read attempts, including DENIED runs with missing/rejected/consumed approval reasons.
         */
        get: operations["action_runs_api_actions_runs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/actions/{action_type}/prepare": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Prepare
         * @description Validate parameters and freeze the exact reviewable impact for the local actor.
         */
        post: operations["prepare_api_actions__action_type__prepare_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/actions/{plan_id}/execute": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Execute
         * @description Execute once; missing/rejected/consumed approvals record DENIED with a reason.
         *
         *     A first denied request retains its 403/409 error response. Read its durable run
         *     through GET /api/actions/runs, or replay its explicit operation_id for that run.
         */
        post: operations["execute_api_actions__plan_id__execute_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List All
         * @description List recoverable local conversations.
         */
        get: operations["list_all_api_agent_conversations_get"];
        put?: never;
        /**
         * Create
         * @description Create a session with persistent limits and optional dataset context.
         */
        post: operations["create_api_agent_conversations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations/definitions/agents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Definitions
         * @description List validated specialist contracts bundled with this installation.
         */
        get: operations["definitions_api_agent_conversations_definitions_agents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get
         * @description Recover all persisted events and current human approval decisions.
         */
        get: operations["get_api_agent_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations/{conversation_id}/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Recovery Audit
         * @description Read persisted resume denials, authorization checks and pause invalidations.
         */
        get: operations["recovery_audit_api_agent_conversations__conversation_id__audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send
         * @description Stream durable events with explicit replay keys and no duplicate execution.
         */
        post: operations["send_api_agent_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations/{conversation_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume
         * @description Continue an approved pause without treating caller input as execution authority.
         */
        post: operations["resume_api_agent_conversations__conversation_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations/{conversation_id}/routes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Routes
         * @description Read persisted workflow suggestions and free-Agent routing decisions.
         */
        get: operations["routes_api_agent_conversations__conversation_id__routes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/conversations/{conversation_id}/tree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Tree
         * @description Read nested specialist sessions and every metered parent and child call.
         */
        get: operations["tree_api_agent_conversations__conversation_id__tree_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/memories": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List All
         * @description List active memories, optionally restricted to global and one dataset scope.
         */
        get: operations["list_all_api_agent_memories_get"];
        put?: never;
        /**
         * Create
         * @description Redact PII and persist an explicitly supplied memory exactly once.
         */
        post: operations["create_api_agent_memories_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/memories/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Audit
         * @description Read hard-deletion evidence that contains no memory content.
         */
        get: operations["audit_api_agent_memories_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/agent/memories/{memory_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get
         * @description Read one memory and its current decayed strength.
         */
        get: operations["get_api_agent_memories__memory_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete
         * @description Hard-delete the memory and archived provenance records in one transaction.
         */
        delete: operations["delete_api_agent_memories__memory_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/approvals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Pending Approvals
         * @description Read irreversible or outbound plans awaiting a local user decision.
         */
        get: operations["pending_approvals_api_approvals_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/approvals/{plan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve
         * @description Approve or reject one displayed plan digest as the local user.
         */
        post: operations["approve_api_approvals__plan_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ask": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ask
         * @description Resolve and execute a read-only registered metric, preserving its full evidence.
         */
        post: operations["ask_api_ask_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ask/{answer_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Replay
         * @description Replay the saved result and original metric revision without rerunning SQL.
         */
        get: operations["replay_api_ask__answer_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/impact": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Impact
         * @description Follow the fixed downstream relationship directions for at most three hops.
         */
        get: operations["impact_api_catalog_impact_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/metrics/{metric_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Metric
         * @description Read the current authoritative metric card, including unresolved reasons.
         */
        get: operations["metric_api_catalog_metrics__metric_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/metrics/{metric_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Metric History
         * @description Read every persisted version of an existing metric in ascending order.
         */
        get: operations["metric_history_api_catalog_metrics__metric_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/neighbors": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Neighbors
         * @description Read the explicitly related metadata surrounding one catalog object.
         */
        get: operations["neighbors_api_catalog_neighbors_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/objects/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Asset
         * @description Read a metadata object by its stable percent-encoded identity.
         */
        get: operations["asset_api_catalog_objects__asset_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/tables/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Table
         * @description Read table fields, owners, semantic consumers, and adjacent relationships.
         */
        get: operations["table_api_catalog_tables__asset_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/{collection}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Collection
         * @description List stable pages filtered by source, containing object, or case-insensitive name.
         */
        get: operations["collection_api_catalog__collection__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Datasets
         * @description List datasets, optionally including the latest read-only quality score.
         */
        get: operations["datasets_api_datasets_get"];
        put?: never;
        /**
         * Create Dataset
         * @description Import uploaded files and their initial immutable manifest.
         */
        post: operations["create_dataset_api_datasets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Dataset
         * @description Read one dataset summary.
         */
        get: operations["dataset_api_datasets__identifier__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/compliance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Compliance
         * @description Read naming, directory, and metadata compliance.
         */
        get: operations["compliance_api_datasets__identifier__compliance_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Files
         * @description Read original or versioned files without exposing local paths.
         */
        get: operations["files_api_datasets__identifier__files_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/files/{file_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download
         * @description Download a file from its dataset, optionally pinned to one immutable version.
         */
        get: operations["download_api_datasets__identifier__files__file_id__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/metadata": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Metadata
         * @description Read metadata and its bound standard.
         */
        get: operations["get_metadata_api_datasets__identifier__metadata_get"];
        /**
         * Metadata
         * @description Replace metadata and atomically record each changed field.
         */
        put: operations["metadata_api_datasets__identifier__metadata_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/metadata/changes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Changes
         * @description Read the dataset's ordered metadata audit trail.
         */
        get: operations["changes_api_datasets__identifier__metadata_changes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/quality": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Quality
         * @description Read the latest manifest quality evaluation.
         */
        get: operations["quality_api_datasets__identifier__quality_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/quality/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Quality Config
         * @description Replace and validate quality scoring overrides.
         */
        put: operations["quality_config_api_datasets__identifier__quality_config_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report
         * @description Read the evidence-based dataset report.
         */
        get: operations["report_api_datasets__identifier__report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/template": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Template
         * @description Bind a JSON Schema standard and calculate compliance.
         */
        put: operations["template_api_datasets__identifier__template_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Versions
         * @description List a dataset's immutable manifest snapshots.
         */
        get: operations["versions_api_datasets__identifier__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evidence/assertions/decide": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Decide
         * @description Apply an explicit local decision through the same frozen-plan action boundary.
         */
        post: operations["decide_api_evidence_assertions_decide_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evidence/assets/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Asset
         * @description Read one sample's active evidence, optionally bound to its displayed source version.
         */
        get: operations["asset_api_evidence_assets__asset_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evidence/query": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Query
         * @description Select versioned samples with bounded, asset-ordered evidence pagination.
         */
        post: operations["query_api_evidence_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export
         * @description Export observations or a selected dataset using a standard vocabulary.
         */
        get: operations["export_api_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/harness/budgets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Budgets
         * @description Inspect durable used and reserved session/day limits.
         */
        get: operations["budgets_api_harness_budgets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/harness/costs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Costs
         * @description Group recorded costs without repricing historical calls.
         */
        get: operations["costs_api_harness_costs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/harness/invocations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Invocations
         * @description Inspect summaries and extracted asset identities without duplicating payloads.
         */
        get: operations["invocations_api_harness_invocations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/harness/traces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Traces
         * @description Read one persisted row for every attempted provider call.
         */
        get: operations["traces_api_harness_traces_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Confirm that the HTTP application is serving requests.
         */
        get: operations["health_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/lineage/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Event
         * @description Append a lineage observation exactly once per idempotency key.
         */
        post: operations["event_api_lineage_events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/lineage/graph": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Lineage
         * @description Read a depth-bounded asset lineage projection.
         */
        get: operations["lineage_api_lineage_graph_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ontology": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Definitions
         * @description List registered types, relationship semantics, read functions and actions.
         */
        get: operations["definitions_api_ontology_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ontology/object-sets/evaluate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Evaluate Objects
         * @description Freeze the current matching assets with their observed revisions.
         */
        post: operations["evaluate_objects_api_ontology_object_sets_evaluate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search
         * @description Return public identities with sufficient context to navigate to their object pages.
         */
        get: operations["search_api_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Tasks
         * @description List durable task states and completion progress.
         */
        get: operations["tasks_api_tasks_get"];
        put?: never;
        /**
         * Submit
         * @description Submit a task idempotently against a validated immutable input snapshot.
         */
        post: operations["submit_api_tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{identifier}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Task
         * @description Read one task with its shard states.
         */
        get: operations["task_api_tasks__identifier__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{identifier}/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Artifacts
         * @description Read published artifacts for a completed task.
         */
        get: operations["artifacts_api_tasks__identifier__artifacts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workflows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Definitions
         * @description List validated bundled workflows and their form input declarations.
         */
        get: operations["definitions_api_workflows_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workflows/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Runs
         * @description List execution history, keeping each explicit run independent of conversations.
         */
        get: operations["runs_api_workflows_runs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workflows/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Run
         * @description Read a full durable timeline after a stream disconnect or page reload.
         */
        get: operations["run_api_workflows_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workflows/runs/{run_id}/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Audit
         * @description Inspect signed-resume authorization and interrupted-run evidence.
         */
        get: operations["audit_api_workflows_runs__run_id__audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workflows/runs/{run_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume
         * @description Continue after a human decision; the request body itself grants no authority.
         */
        post: operations["resume_api_workflows_runs__run_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workflows/{workflow_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Definition
         * @description Read one validated workflow's schema, steps and routing vocabulary.
         */
        get: operations["definition_api_workflows__workflow_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workflows/{workflow_id}/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start
         * @description Start an explicitly requested workflow once and stream its durable snapshots.
         */
        post: operations["start_api_workflows__workflow_id__runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * ActionContext
         * @description Declare the local actor, tool attribution, and enforced request limits.
         */
        ActionContext: {
            /**
             * Actor
             * @default local
             */
            actor: string;
            /** Agent Id */
            agent_id?: string | null;
            /**
             * Max Bytes
             * @default 10737418240
             */
            max_bytes: number;
            /**
             * Max Objects
             * @default 10000
             */
            max_objects: number;
            /** Scopes */
            scopes?: string[];
            /** Session Id */
            session_id?: string | null;
            /**
             * Ttl Seconds
             * @default 900
             */
            ttl_seconds: number;
        };
        /**
         * ActionImpact
         * @description Quantify exactly the frozen affected objects and outbound bytes.
         */
        ActionImpact: {
            /** External */
            external: boolean;
            /** Object Count */
            object_count: number;
            /** Total Bytes */
            total_bytes: number;
        };
        /**
         * ActionPlan
         * @description Bind canonical parameters and selected revisions to a single-use plan.
         */
        ActionPlan: {
            /**
             * Action Type
             * @enum {string}
             */
            action_type: "quarantine_files" | "unquarantine_files" | "create_version_from_selection" | "run_pipeline" | "save_metadata" | "delete_files" | "export_dataset" | "decide_assertions" | "import_catalog" | "restore_catalog" | "update_metric" | "rollback_metric" | "update_term" | "rollback_term";
            /** Actor */
            actor: string;
            /** Agent Id */
            agent_id?: string | null;
            /** Canonical Params */
            canonical_params: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            context: components["schemas"]["ActionContext"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** External */
            external: boolean;
            /** Id */
            id: string;
            impact: components["schemas"]["ActionImpact"];
            manifest: components["schemas"]["FrozenManifest"];
            /** Operation Id */
            operation_id?: string | null;
            /** Plan Digest */
            plan_digest: string;
            /** Reversible */
            reversible: boolean;
            /** Session Id */
            session_id?: string | null;
            /** State Digest */
            state_digest: string;
            /**
             * Status
             * @default PREPARED
             * @enum {string}
             */
            status: "PREPARED" | "APPROVED" | "REJECTED" | "EXECUTED" | "FAILED";
            /** Target Digest */
            target_digest: string;
        };
        /**
         * ActionRun
         * @description Expose durable short execution or asynchronous worker completion.
         */
        ActionRun: {
            /**
             * Action Type
             * @enum {string}
             */
            action_type: "quarantine_files" | "unquarantine_files" | "create_version_from_selection" | "run_pipeline" | "save_metadata" | "delete_files" | "export_dataset" | "decide_assertions" | "import_catalog" | "restore_catalog" | "update_metric" | "rollback_metric" | "update_term" | "rollback_term";
            /** Completed At */
            completed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error */
            error?: string | null;
            /** Id */
            id: string;
            /** Plan Id */
            plan_id: string;
            /**
             * Reason
             * @description DENIED explanation: human approval is missing, rejected, or already consumed. The legacy error field remains available.
             */
            reason?: string | null;
            receipt?: components["schemas"]["LineageEvent"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "DENIED";
            /** Task Id */
            task_id?: string | null;
        };
        /**
         * ActionType
         * @description Declare a controlled mutation's schema, policy, and observable effects.
         */
        ActionType: {
            /** Auth Scope */
            auth_scope: string;
            /** Effects */
            effects: string[];
            /** Handler */
            handler: string;
            /** Id */
            id: string;
            /** Inverse Of */
            inverse_of?: string | null;
            params_schema: components["schemas"]["JsonDocument"];
            /** Preconditions */
            preconditions: string[];
            /** Reversible */
            reversible: boolean;
            /**
             * Version
             * @default 1.0
             */
            version: string;
        };
        /**
         * AgentDefinition
         * @description Limit a named specialist to declared tools and at most four model turns.
         */
        AgentDefinition: {
            /** Description */
            description: string;
            /**
             * Max Turns
             * @default 4
             */
            max_turns: number;
            /** Name */
            name: string;
            /** Tools */
            tools: string[];
        };
        /**
         * AgentEvent
         * @description Persist one replayable text, tool, plan, receipt, or terminal observation.
         */
        AgentEvent: {
            /**
             * Agent Name
             * @default main
             */
            agent_name: string;
            /**
             * Agent Path
             * @default main
             */
            agent_path: string;
            call?: components["schemas"]["ToolCall"] | null;
            /** Conversation Id */
            conversation_id?: string | null;
            /**
             * Event
             * @enum {string}
             */
            event: "text" | "tool_call" | "tool_result" | "plan" | "receipt" | "stopped" | "done" | "route";
            /** Id */
            id?: string;
            /** Model Routes */
            model_routes?: components["schemas"]["ModelRouteDecision"][];
            outcome?: components["schemas"]["ToolOutcome"] | null;
            route?: components["schemas"]["RouteDecision"] | null;
            /** Stop Reason */
            stop_reason?: string | null;
            /** Text */
            text?: string | null;
            /**
             * Tokens
             * @default 0
             */
            tokens: number;
            /** Used Memory Ids */
            used_memory_ids?: string[];
        };
        /**
         * ApprovalDecision
         * @description Bind a human decision to the exact displayed plan digest.
         */
        ApprovalDecision: {
            /**
             * Actor
             * @default local
             */
            actor: string;
            /** Approve */
            approve: boolean;
            /** Plan Digest */
            plan_digest: string;
            /**
             * Reason
             * @default
             */
            reason: string;
        };
        /**
         * ApprovalStep
         * @description Prepare, pause, and execute one irreversible action after authorization.
         */
        ApprovalStep: {
            /** Action */
            action: string;
            arguments: components["schemas"]["JsonDocument"];
            /** Id */
            id: string;
            /** Next */
            next: string;
            title?: components["schemas"]["WorkflowStepTitle"] | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "approval";
        };
        /**
         * AskAnswer
         * @description Persist one fully evidenced answer, refusal, or request for clarification.
         */
        AskAnswer: {
            /**
             * Assertion Ids
             * @default []
             */
            assertion_ids: string[];
            /**
             * Assertions
             * @default []
             */
            assertions: components["schemas"]["Assertion"][];
            /**
             * Candidates
             * @default []
             */
            candidates: components["schemas"]["MetricCard"][];
            /** Id */
            id?: string;
            lineage?: components["schemas"]["LineageReference"] | null;
            /**
             * Matches
             * @default []
             */
            matches: components["schemas"]["MatchEvidence"][];
            /** Message */
            message: string;
            metric_card?: components["schemas"]["MetricCard"] | null;
            /** Question */
            question: string;
            /**
             * Reference Instant
             * Format: date-time
             */
            reference_instant: string;
            result?: components["schemas"]["QueryResult"] | null;
            /** Session Id */
            session_id: string;
            sql?: components["schemas"]["CompiledQuery"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "answered" | "unanswerable" | "clarification";
            time_range?: components["schemas"]["TimeRange"] | null;
        };
        /**
         * AskRequest
         * @description Accept a local question and an explicitly injectable aware time reference.
         */
        AskRequest: {
            /**
             * Actor
             * @default local-user
             */
            actor: string;
            /** Metric Id */
            metric_id?: string | null;
            /** Question */
            question: string;
            /**
             * Reference Instant
             * Format: date-time
             */
            reference_instant?: string;
            /** Session Id */
            session_id?: string | null;
        };
        /**
         * Assertion
         * @description Keep extraction content immutable while exposing a decision overlay.
         */
        Assertion: {
            /** Anchors */
            anchors: components["schemas"]["EvidenceAnchor"][];
            /** Confidence */
            confidence?: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at?: string;
            /** Decided At */
            decided_at?: string | null;
            /** Decided By */
            decided_by?: string | null;
            /** Distance */
            distance?: number | null;
            extractor: components["schemas"]["ExtractorRef"];
            /** Id */
            id?: string;
            /** Object */
            object: components["schemas"]["AssetRef"] | components["schemas"]["EvidenceValue"];
            /** Predicate */
            predicate: string;
            /** Producer Event Id */
            producer_event_id: string;
            /** Reason */
            reason?: string | null;
            /** Run Id */
            run_id: string;
            /**
             * Schema Version
             * @default 1.0
             * @constant
             */
            schema_version: "1.0";
            /**
             * Status
             * @default candidate
             * @enum {string}
             */
            status: "candidate" | "accepted" | "rejected";
            subject: components["schemas"]["AssetRef"];
        };
        /**
         * AssertionFilter
         * @description Match reviewed concept observations or explicit nonexistence of such observations.
         */
        AssertionFilter: {
            /** Concept */
            concept?: string | null;
            /** Min Confidence */
            min_confidence?: number | null;
            /**
             * Operator
             * @default exists
             * @enum {string}
             */
            operator: "exists" | "not_exists";
            /** Predicate */
            predicate: string;
            /** Status */
            status?: ("candidate" | "accepted" | "rejected")[];
            /** Value */
            value?: ("present" | "absent" | "unknown") | null;
        };
        /**
         * AssetRef
         * @description Identify an asset in the sole authoritative storage namespace.
         */
        AssetRef: {
            /** Asset Id */
            asset_id: string;
            /**
             * Asset Type
             * @default dataset
             */
            asset_type: string;
            /** Display Name */
            display_name?: string | null;
            /**
             * Namespace
             * @default default
             */
            namespace: string;
            /** Version */
            version?: string | null;
        };
        /**
         * BranchStep
         * @description Choose an edge using a reference, an allowlisted comparator, and an operand.
         */
        BranchStep: {
            /** Id */
            id: string;
            /**
             * Op
             * @enum {string}
             */
            op: "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in";
            /** Otherwise */
            otherwise: string;
            /** Ref */
            ref: string;
            /** Then */
            then: string;
            title?: components["schemas"]["WorkflowStepTitle"] | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "branch";
            value: components["schemas"]["JsonValue"];
        };
        /**
         * BudgetAccount
         * @description Expose spent and outstanding resources without losing precision.
         */
        BudgetAccount: {
            /** Key */
            key: string;
            /** Reserved Tokens */
            reserved_tokens: number;
            /** Reserved Usd */
            reserved_usd: string;
            /** Spent Usd */
            spent_usd: string;
            /** Token Limit */
            token_limit: number;
            /** Usd Limit */
            usd_limit: string;
            /** Used Tokens */
            used_tokens: number;
        };
        /**
         * BudgetLimits
         * @description Bound actual plus reserved consumption for a conversation and UTC day.
         */
        "BudgetLimits-Input": {
            /**
             * Conversation Tokens
             * @default 100000
             */
            conversation_tokens: number;
            /**
             * Conversation Usd
             * @default 1
             */
            conversation_usd: number | string;
            /**
             * Daily Tokens
             * @default 1000000
             */
            daily_tokens: number;
            /**
             * Daily Usd
             * @default 10
             */
            daily_usd: number | string;
        };
        /**
         * BudgetLimits
         * @description Bound actual plus reserved consumption for a conversation and UTC day.
         */
        "BudgetLimits-Output": {
            /**
             * Conversation Tokens
             * @default 100000
             */
            conversation_tokens: number;
            /**
             * Conversation Usd
             * @default 1
             */
            conversation_usd: string;
            /**
             * Daily Tokens
             * @default 1000000
             */
            daily_tokens: number;
            /**
             * Daily Usd
             * @default 10
             */
            daily_usd: string;
        };
        /**
         * CallTree
         * @description Return independently auditable nodes and their individual model-call traces.
         */
        CallTree: {
            /** Nodes */
            nodes: components["schemas"]["CallTreeNode"][];
            /** Traces */
            traces: components["schemas"]["ModelCallTrace"][];
        };
        /**
         * CallTreeNode
         * @description Expose hierarchy and measured activity without exposing child capability snapshots.
         */
        CallTreeNode: {
            /** Agent Name */
            agent_name: string;
            /** Agent Path */
            agent_path: string;
            /** Depth */
            depth: number;
            /** Id */
            id: string;
            /** Parent Id */
            parent_id: string | null;
            /** Parent Tool Call Id */
            parent_tool_call_id: string | null;
            /** Root Id */
            root_id: string;
            /** Tokens */
            tokens: number;
            /** Tools */
            tools: string[];
        };
        /**
         * CatalogLink
         * @description Declare one explicit relationship, without inferring a Cartesian product.
         */
        CatalogLink: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "contains" | "derived" | "measures" | "sliced_by" | "means" | "owned_by" | "references";
            /** Producer Event Id */
            producer_event_id?: string | null;
            source: components["schemas"]["AssetRef"];
            target: components["schemas"]["AssetRef"];
        };
        /**
         * CatalogObject
         * @description Describe one stable metadata identity and its immutable snapshot attributes.
         */
        CatalogObject: {
            asset_ref: components["schemas"]["AssetRef"];
            /** Name */
            name: string;
            /** Producer Event Id */
            producer_event_id?: string | null;
            properties?: components["schemas"]["JsonDocument"];
            /**
             * Revision
             * @default 1
             */
            revision: number;
            /** Schema Name */
            schema_name?: string | null;
            /** Source Id */
            source_id?: string | null;
            /** Table Id */
            table_id?: string | null;
        };
        /**
         * CatalogPage
         * @description Return one stable catalog page and its full matching count.
         */
        CatalogPage: {
            /** Items */
            items: components["schemas"]["CatalogObject"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /**
         * CatalogTableDetail
         * @description Collect a table's fields, semantic consumers, ownership, and direct relationships.
         */
        CatalogTableDetail: {
            /** Columns */
            columns: components["schemas"]["CatalogObject"][];
            /** Metrics */
            metrics: components["schemas"]["CatalogObject"][];
            neighbors: components["schemas"]["ImpactResult"];
            /** Owners */
            owners: components["schemas"]["CatalogObject"][];
            table: components["schemas"]["CatalogObject"];
        };
        /**
         * ChapterView
         * @description One evidence-grounded report section.
         */
        ChapterView: {
            /** Body */
            body: string;
            /** Title */
            title: string;
        };
        /**
         * ChatMessage
         * @description Persist text and complete tool exchanges without truncating history.
         */
        ChatMessage: {
            /**
             * Content
             * @default
             */
            content: string;
            /** Name */
            name?: string | null;
            /**
             * Role
             * @enum {string}
             */
            role: "system" | "user" | "assistant" | "tool";
            /** Tool Call Id */
            tool_call_id?: string | null;
            /** Tool Calls */
            tool_calls?: components["schemas"]["ToolCall"][];
        };
        /**
         * CompiledQuery
         * @description Carry compiler-generated SELECT SQL, bound parameters, and evidence.
         */
        CompiledQuery: {
            /** Columns */
            columns: string[];
            /**
             * Dialect
             * @enum {string}
             */
            dialect: "sqlite" | "postgres";
            /** Metric Id */
            metric_id: string;
            /** Metric Version */
            metric_version: number;
            /** Parameters */
            parameters?: {
                [key: string]: components["schemas"]["Scalar"];
            };
            /** Source Id */
            source_id: string;
            /** Sql */
            sql: string;
            /** Tables */
            tables: string[];
        };
        /**
         * ComplianceView
         * @description Governance compliance assessment.
         */
        ComplianceView: {
            /** Dimensions */
            dimensions: {
                [key: string]: components["schemas"]["DimensionView"];
            };
            /** Issues */
            issues: components["schemas"]["IssueView"][];
            /** Total */
            total: number;
        };
        /**
         * ConversationAudit
         * @description Expose durable recovery decisions independently of disposable graph checkpoints.
         */
        ConversationAudit: {
            /** Conversation Id */
            conversation_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "RESUME_DENIED" | "RESUME_AUTHORIZED" | "INTERRUPT_INVALIDATED" | "CANARY_LEAK" | "DELEGATION_DENIED";
            /** Plan Id */
            plan_id: string;
            /** Reason */
            reason: string;
        };
        /**
         * ConversationCreate
         * @description Bound a local conversation before accepting its first message.
         */
        "ConversationCreate-Input": {
            budget?: components["schemas"]["BudgetLimits-Input"];
            /** Dataset Id */
            dataset_id?: string | null;
            /**
             * Dry Run
             * @default false
             */
            dry_run: boolean;
            /**
             * Max Output Tokens
             * @default 1024
             */
            max_output_tokens: number;
            /**
             * Max Turns
             * @default 12
             */
            max_turns: number;
            /**
             * Model
             * @default fake-demo
             */
            model: string;
            /**
             * Provider
             * @default fake
             * @enum {string}
             */
            provider: "fake" | "openai" | "anthropic";
        };
        /**
         * ConversationCreate
         * @description Bound a local conversation before accepting its first message.
         */
        "ConversationCreate-Output": {
            budget?: components["schemas"]["BudgetLimits-Output"];
            /** Dataset Id */
            dataset_id?: string | null;
            /**
             * Dry Run
             * @default false
             */
            dry_run: boolean;
            /**
             * Max Output Tokens
             * @default 1024
             */
            max_output_tokens: number;
            /**
             * Max Turns
             * @default 12
             */
            max_turns: number;
            /**
             * Model
             * @default fake-demo
             */
            model: string;
            /**
             * Provider
             * @default fake
             * @enum {string}
             */
            provider: "fake" | "openai" | "anthropic";
        };
        /**
         * ConversationView
         * @description Expose complete memory with current approval and execution card state.
         */
        ConversationView: {
            /**
             * Actor
             * @default local
             * @constant
             */
            actor: "local";
            config: components["schemas"]["ConversationCreate-Output"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Events */
            events: components["schemas"]["AgentEvent"][];
            /** Id */
            id: string;
            /** Messages */
            messages: components["schemas"]["ChatMessage"][];
            /** Pending Plans */
            pending_plans?: components["schemas"]["ActionPlan"][];
            /** Turns */
            turns: number;
        };
        /**
         * CostSummary
         * @description Aggregate recorded calls by one stable reporting dimension.
         */
        CostSummary: {
            /** Cache Read Tokens */
            cache_read_tokens: number;
            /** Cache Write Tokens */
            cache_write_tokens: number;
            /** Calls */
            calls: number;
            /** Cost Usd */
            cost_usd: string;
            /**
             * Group By
             * @enum {string}
             */
            group_by: "conversation" | "day" | "model";
            /** Input Tokens */
            input_tokens: number;
            /** Key */
            key: string;
            /** Output Tokens */
            output_tokens: number;
            /**
             * Unknown Calls
             * @default 0
             */
            unknown_calls: number;
            /**
             * Unknown Cost Usd
             * @default 0
             */
            unknown_cost_usd: string;
        };
        /**
         * DatasetInput
         * @description A local dataset import request.
         */
        DatasetInput: {
            /** Files */
            files?: components["schemas"]["UploadFile"][];
            /** Metadata */
            metadata?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Name */
            name: string;
        };
        /**
         * DatasetQualityView
         * @description Extend an explicitly requested dataset summary with its latest measured score.
         */
        DatasetQualityView: {
            /** Compliance */
            compliance: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Created At */
            created_at: number;
            /** File Count */
            file_count: number;
            /** Id */
            id: string;
            /** Metadata */
            metadata: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Name */
            name: string;
            /** Quality Config */
            quality_config: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Quality Score */
            quality_score: number | null;
            /** Template */
            template: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
        };
        /**
         * DatasetView
         * @description Dataset summary containing its current governance configuration.
         */
        DatasetView: {
            /** Compliance */
            compliance: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Created At */
            created_at: number;
            /** File Count */
            file_count: number;
            /** Id */
            id: string;
            /** Metadata */
            metadata: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Name */
            name: string;
            /** Quality Config */
            quality_config: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Template */
            template: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
        };
        /**
         * DecideAssertionsParams
         * @description Review exact active assertions without accepting caller-supplied actor privileges.
         */
        DecideAssertionsParams: {
            /** Assertion Ids */
            assertion_ids: string[];
            /**
             * Reason
             * @default User decision
             */
            reason: string;
            /**
             * Status
             * @enum {string}
             */
            status: "candidate" | "accepted" | "rejected";
        };
        /**
         * DimensionView
         * @description One weighted measured quality dimension.
         */
        DimensionView: {
            /** Configured Weight */
            configured_weight?: number | null;
            /** Details */
            details: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /**
             * Included
             * @default true
             */
            included: boolean;
            /** Score */
            score: number;
            /** Weight */
            weight: number;
        };
        /**
         * EventRecorded
         * @description Whether an idempotent append inserted a new observation.
         */
        EventRecorded: {
            /** Inserted */
            inserted: boolean;
        };
        /**
         * EvidenceAnchor
         * @description Bind a modality-specific location to exact immutable content.
         */
        EvidenceAnchor: {
            asset_ref: components["schemas"]["AssetRef"];
            /** Content Revision */
            content_revision: string;
            /**
             * Schema Version
             * @default 1.0
             * @constant
             */
            schema_version: "1.0";
            /** Selector */
            selector?: components["schemas"]["Whole"] | components["schemas"]["TextSpan"] | components["schemas"]["ImageRegion"];
        };
        /**
         * EvidenceBox
         * @description Describe a canonical annotation in original-image pixel xyxy coordinates.
         */
        EvidenceBox: {
            /** Bbox */
            bbox: [
                number,
                number,
                number,
                number
            ];
            /** Concept */
            concept: string;
            /** Height */
            height: number;
            /** Width */
            width: number;
        };
        /**
         * EvidenceQuery
         * @description Paginate an evidence ObjectSet by the final asset identity of the previous page.
         */
        EvidenceQuery: {
            /** Assertion Filters */
            assertion_filters?: components["schemas"]["AssertionFilter"][];
            /** Created After */
            created_after?: string | null;
            /** Created Before */
            created_before?: string | null;
            /** Cursor */
            cursor?: string | null;
            /** Dataset Id */
            dataset_id?: string | null;
            /** Filters */
            filters?: components["schemas"]["PropertyFilter"][];
            /** Has Near Duplicate In */
            has_near_duplicate_in?: ("train" | "val") | null;
            /**
             * Include Deleted
             * @default false
             */
            include_deleted: boolean;
            /**
             * Limit
             * @default 1000
             */
            limit: number;
            /**
             * Namespace
             * @default default
             * @constant
             */
            namespace: "default";
            /**
             * Object Type
             * @default file
             * @enum {string}
             */
            object_type: "file";
            /**
             * Page Size
             * @default 50
             */
            page_size: number;
            /** Quality Max */
            quality_max?: number | null;
            /** Quality Min */
            quality_min?: number | null;
            /**
             * Schema Version
             * @default 1.1
             * @enum {string}
             */
            schema_version: "1.0" | "1.1";
            /**
             * Sort
             * @default asset
             * @enum {string}
             */
            sort: "asset" | "review" | "filename" | "quality";
            /** Split */
            split?: ("train" | "val") | null;
            /** Version Ids */
            version_ids?: string[];
        };
        /**
         * EvidenceQueryResult
         * @description Return deterministic, bounded sample pages and their full selected denominator.
         */
        EvidenceQueryResult: {
            /** Items */
            items: components["schemas"]["EvidenceSample"][];
            /** Next Cursor */
            next_cursor: string | null;
            /** Total */
            total: number;
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
        };
        /**
         * EvidenceSample
         * @description Expose evidence and source provenance without private materialized file paths.
         */
        EvidenceSample: {
            /** Annotation Boxes */
            annotation_boxes: components["schemas"]["EvidenceBox"][];
            /** Assertions */
            assertions: components["schemas"]["Assertion"][];
            asset_ref: components["schemas"]["AssetRef"];
            /** Caption */
            caption: string | null;
            /** Caption Spans */
            caption_spans: components["schemas"]["TextSpan"][];
            /** Dataset Id */
            dataset_id: string;
            /** Deleted */
            deleted: boolean;
            /** Filename */
            filename: string;
            /** Image Height */
            image_height?: number | null;
            /** Image Width */
            image_width?: number | null;
            /** Near Duplicates */
            near_duplicates: components["schemas"]["NearDuplicateCandidate"][];
            /** Quality Score */
            quality_score: number;
            /** Quarantined */
            quarantined: boolean;
            /** Source Version */
            source_version: string;
            /** Split */
            split: ("train" | "val") | null;
            /** Thumbnail Url */
            thumbnail_url: string | null;
        };
        /**
         * EvidenceValue
         * @description Represent presence, measured absence, or missing evidence for a concept.
         */
        EvidenceValue: {
            /** Concept */
            concept?: string | null;
            /**
             * Value
             * @enum {string}
             */
            value: "present" | "absent" | "unknown";
        };
        /**
         * ExecuteRequest
         * @description Bind an execution to its digest, caller, and optional replay identity.
         */
        ExecuteRequest: {
            /**
             * Actor
             * @default local
             */
            actor: string;
            /** Canonical Params */
            canonical_params?: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Operation Id */
            operation_id?: string | null;
            /** Plan Digest */
            plan_digest: string;
        };
        /**
         * ExtractorRef
         * @description Identify the implementation and version responsible for an observation.
         */
        ExtractorRef: {
            /** Id */
            id: string;
            /** Version */
            version: string;
        };
        /**
         * FileView
         * @description Public file evidence without a private materialized path.
         */
        FileView: {
            /** Filename */
            filename: string;
            /** Id */
            id: string;
            /** Metadata */
            metadata?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Modality */
            modality: string;
            /** Sha256 */
            sha256: string;
            /** Size */
            size: number;
        };
        /**
         * FrozenManifest
         * @description Freeze exact object revisions for subsequent authorization and execution.
         */
        FrozenManifest: {
            /** Objects */
            objects: components["schemas"]["FrozenObject"][];
            query: components["schemas"]["ObjectSet"];
            /** State Digest */
            state_digest: string;
            /** Total Bytes */
            total_bytes: number;
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
        };
        /**
         * FrozenObject
         * @description Bind an asset identity to immutable content and the observed mutable state.
         */
        FrozenObject: {
            asset_ref: components["schemas"]["AssetRef"];
            /** Properties */
            properties: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Revision */
            revision: string;
            /**
             * Size
             * @default 0
             */
            size: number;
            /**
             * State Revision
             * @default 0
             */
            state_revision: number;
        };
        /**
         * FunctionType
         * @description Describe a read-only function and its validated input/output schemas.
         */
        FunctionType: {
            /** Handler */
            handler: string;
            /** Id */
            id: string;
            input_schema: components["schemas"]["JsonDocument"];
            output_schema: components["schemas"]["JsonDocument"];
            /** Read Scope */
            read_scope: string;
            /**
             * Version
             * @default 1.0
             */
            version: string;
        };
        /**
         * GraphEdge
         * @description Keep event-derived lineage distinct from a reviewed semantic assertion.
         */
        GraphEdge: {
            assertion?: components["schemas"]["Assertion"] | null;
            event?: components["schemas"]["LineageEvent"] | null;
            /** Event Id */
            event_id?: string | null;
            /**
             * Kind
             * @default lineage
             * @enum {string}
             */
            kind: "lineage" | "semantic" | "catalog";
            /** Link Type */
            link_type?: string | null;
            /** Operator */
            operator: string;
            /** Source */
            source: string;
            /** Target */
            target: string;
        };
        /**
         * GraphNode
         * @description Asset identity and display data in a lineage projection.
         */
        GraphNode: {
            /** Asset Id */
            asset_id: string;
            /** Asset Type */
            asset_type: string;
            /** Deleted */
            deleted?: boolean | null;
            /** Display Name */
            display_name?: string | null;
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Namespace */
            namespace: string;
            /** Quarantined */
            quarantined?: boolean | null;
            /** Version */
            version?: string | null;
        };
        /**
         * GraphView
         * @description A bounded lineage projection and the events backing its edges.
         */
        GraphView: {
            /** Edges */
            edges: components["schemas"]["GraphEdge"][];
            /** Events */
            events: components["schemas"]["LineageEvent"][];
            /** Nodes */
            nodes: components["schemas"]["GraphNode"][];
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HealthView
         * @description Service liveness indicator.
         */
        HealthView: {
            /**
             * Status
             * @default ok
             */
            status: string;
        };
        /**
         * IdentityMapping
         * @description Map a public property identity into the existing AssetRef vocabulary.
         */
        IdentityMapping: {
            /** Asset Type */
            asset_type: string;
            /**
             * Id Field
             * @default id
             */
            id_field: string;
            /**
             * Namespace
             * @default default
             */
            namespace: string;
            /** Version Field */
            version_field?: string | null;
        };
        /**
         * ImageRegion
         * @description Locate an xyxy box in the original image pixel coordinate system.
         */
        ImageRegion: {
            /** Bbox */
            bbox: [
                number,
                number,
                number,
                number
            ];
            /** Height */
            height: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "image_region";
            /** Width */
            width: number;
        };
        /**
         * ImpactResult
         * @description Return a bounded downstream dependency traversal and explicit edges.
         */
        ImpactResult: {
            /** Asset Id */
            asset_id: string;
            /** Links */
            links: components["schemas"]["CatalogLink"][];
            /** Objects */
            objects: components["schemas"]["CatalogObject"][];
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
        };
        /**
         * IssueView
         * @description Measured quality or compliance issue.
         */
        IssueView: {
            /** Code */
            code?: string | null;
            /** Dimension */
            dimension: string;
            /** Message */
            message: string;
            /** Severity */
            severity: string;
        };
        /**
         * JsonDocument
         * @description Validate intentionally extensible JSON Schema and interchange documents.
         *
         *     Root documents intentionally allow vocabulary-defined keys. Any return values
         *     below are restricted to the legacy JSON serialization compatibility boundary.
         */
        JsonDocument: {
            [key: string]: components["schemas"]["JsonValue"];
        };
        JsonValue: unknown;
        /**
         * LineageEvent
         * @description Record an immutable attributed transformation or failure.
         */
        LineageEvent: {
            /** Event Id */
            event_id?: string;
            /**
             * Event Type
             * @default TRANSFORM
             */
            event_type: string;
            /** Idempotency Key */
            idempotency_key: string;
            /** Inputs */
            inputs?: components["schemas"]["AssetRef"][];
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at?: string;
            /**
             * On Behalf Of
             * @default local-user
             */
            on_behalf_of: string;
            /** Operator */
            operator: string;
            /** Outputs */
            outputs?: components["schemas"]["AssetRef"][];
            /** Params */
            params?: {
                [key: string]: unknown;
            };
            /** Quality */
            quality?: {
                [key: string]: unknown;
            };
            /**
             * Run State
             * @default COMPLETED
             */
            run_state: string;
            /**
             * Source Module
             * @default pipeline
             */
            source_module: string;
            /** Source Ref */
            source_ref?: string | null;
        };
        /**
         * LineageReference
         * @description Identify the bounded catalog subgraph supporting an answer.
         */
        LineageReference: {
            /** Asset Id */
            asset_id: string;
            /**
             * Hops
             * @default 2
             */
            hops: number;
            /**
             * Include Catalog
             * @default true
             * @constant
             */
            include_catalog: true;
            /**
             * Max Nodes
             * @default 30
             */
            max_nodes: number;
        };
        /**
         * LinkType
         * @description Declare relationship semantics separately from transformation provenance.
         */
        LinkType: {
            /**
             * Cardinality
             * @enum {string}
             */
            cardinality: "one-to-one" | "one-to-many" | "many-to-many";
            /** Description */
            description: string;
            /** Domain */
            domain: string[];
            /** Id */
            id: string;
            /** Range */
            range: string[];
            /** Semantics */
            semantics: string;
            /**
             * Version
             * @default 1.0
             */
            version: string;
        };
        /**
         * MatchEvidence
         * @description Locate a semantic match in NFC-normalized question code points.
         */
        MatchEvidence: {
            /** Dimension Id */
            dimension_id?: string | null;
            /** End */
            end: number;
            /**
             * Match Kind
             * @enum {string}
             */
            match_kind: "exact" | "synonym" | "prefix" | "dimension_value" | "time";
            /** Metric Id */
            metric_id?: string | null;
            /** Source */
            source: string;
            /** Start */
            start: number;
            /** Term Id */
            term_id?: string | null;
            /** Text */
            text: string;
            /** Value */
            value?: string | null;
        };
        /**
         * Measure
         * @description Bind one permitted aggregation to a catalog table and column.
         */
        Measure: {
            /**
             * Aggregation
             * @enum {string}
             */
            aggregation: "sum" | "count" | "avg" | "min" | "max" | "count_distinct";
            /** Column */
            column: string;
            /** Table */
            table: string;
        };
        /**
         * MemoryCreate
         * @description Bind an explicit write to its optional source and replay key.
         */
        MemoryCreate: {
            /** Content */
            content: string;
            /** Dataset Id */
            dataset_id?: string | null;
            /** Idempotency Key */
            idempotency_key?: string;
            /** Source Conversation Id */
            source_conversation_id?: string | null;
        };
        /**
         * MemoryDeletion
         * @description Retain deletion evidence containing identities only, never memory content.
         */
        MemoryDeletion: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Deleted Ids */
            deleted_ids: string[];
            /** Id */
            id: string;
            /**
             * Kind
             * @default MEMORY_DELETED
             * @constant
             */
            kind: "MEMORY_DELETED";
            /** Memory Id */
            memory_id: string;
        };
        /**
         * MemoryEntry
         * @description Expose current strength and provenance without leaking persistence rows.
         */
        MemoryEntry: {
            /**
             * Archived
             * @default false
             */
            archived: boolean;
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Current Strength
             * @default 1
             */
            current_strength: number;
            /** Dataset Id */
            dataset_id?: string | null;
            /** Id */
            id: string;
            /** Last Used At */
            last_used_at?: string | null;
            /**
             * Reinforced At
             * Format: date-time
             */
            reinforced_at: string;
            /** Source Conversation Ids */
            source_conversation_ids?: string[];
            /** Source Memory Ids */
            source_memory_ids?: string[];
            /**
             * Strength
             * @default 1
             */
            strength: number;
        };
        /**
         * MessageInput
         * @description An idempotent user turn, independent of transport reconnects.
         */
        MessageInput: {
            /** Content */
            content: string;
            /** Idempotency Key */
            idempotency_key?: string;
        };
        /**
         * MetadataChangeView
         * @description A field-level audited metadata transition.
         */
        MetadataChangeView: {
            after: components["schemas"]["JsonValue"];
            before: components["schemas"]["JsonValue"];
            /** Field */
            field: string;
            /** Occurred At */
            occurred_at: number;
            /** Reason */
            reason: string;
            /** Source */
            source: string;
        };
        /**
         * MetadataInput
         * @description Replacement metadata with an explicit audit reason.
         */
        MetadataInput: {
            /** Reason */
            reason: string;
            /**
             * Source
             * @default api
             */
            source: string;
            /** Values */
            values: {
                [key: string]: components["schemas"]["JsonValue"];
            };
        };
        /**
         * MetadataSavedView
         * @description Updated metadata and its measured compliance.
         */
        MetadataSavedView: {
            compliance: components["schemas"]["ComplianceView"];
            /** Values */
            values: {
                [key: string]: components["schemas"]["JsonValue"];
            };
        };
        /**
         * MetadataView
         * @description Current metadata and the standard governing future edits.
         */
        MetadataView: {
            /** Template */
            template: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Values */
            values: {
                [key: string]: components["schemas"]["JsonValue"];
            };
        };
        /**
         * MetricAudit
         * @description Attribute an authoritative semantic transition to its controlled plan.
         */
        MetricAudit: {
            /** Action Type */
            action_type: string;
            /** Actor */
            actor: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Event Id */
            event_id: string;
            /** From Version */
            from_version: number;
            /** Metric Id */
            metric_id: string;
            /** Plan Id */
            plan_id: string;
            /** To Version */
            to_version: number;
        };
        /**
         * MetricCard
         * @description Expose a metric revision and explicit reference resolution failures.
         */
        MetricCard: {
            definition: components["schemas"]["MetricDefinition"];
            /** Reasons */
            reasons?: string[];
            /**
             * Status
             * @default resolved
             * @enum {string}
             */
            status: "resolved" | "unresolved";
        };
        /**
         * MetricDefinition
         * @description Define the complete, immutable business meaning of one metric revision.
         */
        MetricDefinition: {
            /** Caveats */
            caveats?: string[];
            /** Description */
            description: string;
            /** Dimensions */
            dimensions?: string[];
            /** Filters */
            filters?: components["schemas"]["MetricFilter"][];
            /** Id */
            id: string;
            measure: components["schemas"]["Measure"];
            /** Name */
            name: string;
            /** Owner */
            owner: string;
            /** Synonyms */
            synonyms?: string[];
            time: components["schemas"]["MetricTime"];
            /**
             * Version
             * @default 1
             */
            version: number;
        };
        /**
         * MetricFilter
         * @description Represent a typed comparison against a registered field.
         */
        MetricFilter: {
            /** Column */
            column: string;
            /**
             * Op
             * @default eq
             * @enum {string}
             */
            op: "eq" | "ne" | "in" | "gte" | "lte";
            /** Value */
            value: components["schemas"]["Scalar"] | components["schemas"]["Scalar"][];
        };
        /**
         * MetricHistory
         * @description Return immutable definitions together with attributable changes.
         */
        MetricHistory: {
            /** Audit */
            audit: components["schemas"]["MetricAudit"][];
            /** Metric Id */
            metric_id: string;
            /** Versions */
            versions: components["schemas"]["MetricCard"][];
        };
        /**
         * MetricTime
         * @description Bind a metric to its registered temporal field and native precision.
         */
        MetricTime: {
            /** Column */
            column: string;
            /**
             * Granularity
             * @default day
             * @enum {string}
             */
            granularity: "day" | "month" | "quarter" | "year";
        };
        /**
         * ModelCallTrace
         * @description Keep observed usage separate from conservative charges for unknown billing.
         */
        ModelCallTrace: {
            /**
             * Accounted Tokens
             * @default 0
             */
            accounted_tokens: number;
            /** Accounting Conversation Id */
            accounting_conversation_id?: string | null;
            /**
             * Agent Path
             * @default main
             */
            agent_path: string;
            /**
             * Billing Status
             * @default actual
             * @enum {string}
             */
            billing_status: "actual" | "unknown";
            /**
             * Budget Exceeded
             * @default false
             */
            budget_exceeded: boolean;
            /**
             * Call Type
             * @default conversation
             * @enum {string}
             */
            call_type: "conversation" | "intent_classifier";
            /** Conversation Id */
            conversation_id: string;
            /** Cost Usd */
            cost_usd: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Depth
             * @default 0
             */
            depth: number;
            /** Id */
            id: string;
            /** Latency Ms */
            latency_ms: number;
            /** Model */
            model: string;
            model_route?: components["schemas"]["ModelRouteDecision"] | null;
            /** Parent Tool Call Id */
            parent_tool_call_id?: string | null;
            /** Price Version */
            price_version: string;
            /** Provider */
            provider: string;
            /** Reservation Id */
            reservation_id: string;
            /** Segments */
            segments: components["schemas"]["TokenSegment"][];
            /** Stop Reason */
            stop_reason: string;
            /** Tool Calls */
            tool_calls: number;
            /** Turn */
            turn: number;
            usage: components["schemas"]["TokenUsage"];
        };
        /**
         * ModelRouteDecision
         * @description Record the selected tier, override policy, and one provider attempt.
         */
        ModelRouteDecision: {
            /**
             * Attempt
             * @default 1
             */
            attempt: number;
            /** Fallback Reason */
            fallback_reason?: string | null;
            /** Model */
            model: string;
            /** Pinned */
            pinned: boolean;
            /**
             * Tier
             * @enum {string}
             */
            tier: "simple" | "multi_step" | "high_risk";
        };
        /**
         * NearDuplicateCandidate
         * @description Explain one directly measured neighboring sample, without transitive expansion.
         */
        NearDuplicateCandidate: {
            /** Assertion Id */
            assertion_id: string;
            asset_ref: components["schemas"]["AssetRef"];
            /** Distance */
            distance: number;
            /** Reason */
            reason: string;
        };
        /**
         * Node
         * @description Declare typed input slots and validated operator parameters.
         */
        Node: {
            /** Id */
            id: string;
            /** Inputs */
            inputs: {
                [key: string]: string;
            };
            /**
             * Kind
             * @default operator
             * @enum {string}
             */
            kind: "operator" | "condition" | "route";
            /** Operator */
            operator?: string | null;
            /** Params */
            params?: {
                [key: string]: unknown;
            };
        };
        /**
         * ObjectSet
         * @description Select assets by type, public properties, quality, and version interval.
         */
        ObjectSet: {
            /** Assertion Filters */
            assertion_filters?: components["schemas"]["AssertionFilter"][];
            /** Created After */
            created_after?: string | null;
            /** Created Before */
            created_before?: string | null;
            /** Dataset Id */
            dataset_id?: string | null;
            /** Filters */
            filters?: components["schemas"]["PropertyFilter"][];
            /** Has Near Duplicate In */
            has_near_duplicate_in?: ("train" | "val") | null;
            /**
             * Include Deleted
             * @default false
             */
            include_deleted: boolean;
            /**
             * Limit
             * @default 1000
             */
            limit: number;
            /**
             * Namespace
             * @default default
             * @constant
             */
            namespace: "default";
            /**
             * Object Type
             * @default file
             */
            object_type: string;
            /** Quality Max */
            quality_max?: number | null;
            /** Quality Min */
            quality_min?: number | null;
            /**
             * Schema Version
             * @default 1.1
             * @enum {string}
             */
            schema_version: "1.0" | "1.1";
            /** Split */
            split?: ("train" | "val") | null;
            /** Version Ids */
            version_ids?: string[];
        };
        /**
         * ObjectType
         * @description Describe one versioned asset object without duplicating its facts.
         */
        ObjectType: {
            /** Description */
            description: string;
            /** Id */
            id: string;
            identity_mapping: components["schemas"]["IdentityMapping"];
            properties: components["schemas"]["JsonDocument"];
            /**
             * Version
             * @default 1.0
             */
            version: string;
        };
        /**
         * OntologyRegistry
         * @description Expose the complete versioned interface registry.
         */
        OntologyRegistry: {
            /** Actions */
            actions: components["schemas"]["ActionType"][];
            /** Functions */
            functions: components["schemas"]["FunctionType"][];
            /** Link Types */
            link_types: components["schemas"]["LinkType"][];
            /** Object Types */
            object_types: components["schemas"]["ObjectType"][];
            /**
             * Version
             * @default 1.0
             */
            version: string;
        };
        /**
         * OutputStep
         * @description Finish a path with a JSON template using only pure expressions.
         */
        OutputStep: {
            /** Id */
            id: string;
            title?: components["schemas"]["WorkflowStepTitle"] | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "output";
            value: components["schemas"]["JsonValue"];
        };
        /**
         * Pipeline
         * @description Describe an acyclic set of nodes and the published output slots.
         */
        Pipeline: {
            /**
             * Max Workers
             * @default 4
             */
            max_workers: number;
            /** Nodes */
            nodes: components["schemas"]["Node"][];
            /** Outputs */
            outputs: string[];
        };
        /**
         * PropertyFilter
         * @description Constrain one public property using an explicit bounded operator.
         */
        PropertyFilter: {
            /** Field */
            field: string;
            /**
             * Operator
             * @default eq
             * @enum {string}
             */
            operator: "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "contains" | "in";
            value: components["schemas"]["JsonValue"];
        };
        /**
         * QualityConfig
         * @description Validated scoring rules for one dataset manifest.
         */
        QualityConfig: {
            /** Allowed Formats */
            allowed_formats: {
                [key: string]: string[];
            };
            /** Distribution Field */
            distribution_field: string;
            /** Exclude Annotation When Absent */
            exclude_annotation_when_absent: boolean;
            /** Min Image Height */
            min_image_height: number;
            /** Min Image Width */
            min_image_width: number;
            /** Min Size Bytes */
            min_size_bytes: number;
            /** Thresholds */
            thresholds: {
                [key: string]: number;
            };
            /** Weights */
            weights: {
                [key: string]: number;
            };
        };
        /**
         * QualityInput
         * @description Partial configuration for the five measured quality dimensions.
         */
        QualityInput: {
            /** Allowed Formats */
            allowed_formats?: {
                [key: string]: string[];
            } | null;
            /** Distribution Field */
            distribution_field?: string | null;
            /** Exclude Annotation When Absent */
            exclude_annotation_when_absent?: boolean | null;
            /** Min Image Height */
            min_image_height?: number | null;
            /** Min Image Width */
            min_image_width?: number | null;
            /** Min Size Bytes */
            min_size_bytes?: number | null;
            /** Thresholds */
            thresholds?: {
                [key: string]: number;
            } | null;
            /** Weights */
            weights?: {
                [key: string]: number;
            } | null;
        };
        /**
         * QualityView
         * @description Five-dimensional quality evaluation.
         */
        QualityView: {
            config: components["schemas"]["QualityConfig"];
            /** Dimensions */
            dimensions: {
                [key: string]: components["schemas"]["DimensionView"];
            };
            /** File Count */
            file_count: number;
            /** Grade */
            grade: string;
            /** Issues */
            issues: components["schemas"]["IssueView"][];
            /** Total */
            total: number;
        };
        /**
         * QueryResult
         * @description Return ordered columns and scalar rows without exposing database handles.
         */
        QueryResult: {
            /** Columns */
            columns: string[];
            /** Rows */
            rows: components["schemas"]["Scalar"][][];
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
        };
        /**
         * ReportView
         * @description Rule report and optional enrichment provenance.
         */
        ReportView: {
            /** Baseline */
            baseline: string;
            /** Baseline Verification */
            baseline_verification: string;
            /** Body */
            body: string;
            /** Chapters */
            chapters: components["schemas"]["ChapterView"][];
            /** Fallback */
            fallback: boolean;
            /** Fallback Reason */
            fallback_reason?: string | null;
            /** Llm Body */
            llm_body?: string | null;
            /** Source */
            source: string;
        };
        /**
         * ResumeInput
         * @description Identify a paused plan without accepting any caller-supplied approval authority.
         */
        ResumeInput: {
            /** Idempotency Key */
            idempotency_key: string;
            /** Plan Id */
            plan_id: string;
        };
        /**
         * RouteCandidate
         * @description Expose the deterministic keyword score for one registered workflow.
         */
        RouteCandidate: {
            /** Score */
            score: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /**
         * RouteDecision
         * @description Persist an auditable suggestion without authorizing workflow execution.
         */
        RouteDecision: {
            /**
             * Branch
             * @enum {string}
             */
            branch: "keyword" | "classifier" | "free_agent";
            /** Candidates */
            candidates: components["schemas"]["RouteCandidate"][];
            inputs?: components["schemas"]["RouteInputs"];
            /** Reason */
            reason: string;
            /**
             * Score
             * @default 0
             */
            score: number;
            /** Workflow Id */
            workflow_id?: string | null;
        };
        /**
         * RouteInputs
         * @description Prefill only the conversation's explicitly selected dataset.
         */
        RouteInputs: {
            /** Dataset Id */
            dataset_id?: string | null;
        };
        Scalar: string | number | boolean | null;
        /**
         * SearchResult
         * @description Expose stable object identity without private paths or connection metadata.
         */
        SearchResult: {
            /** Dataset Id */
            dataset_id?: string | null;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "dataset" | "file" | "version" | "action_run" | "table" | "column" | "metric" | "term";
            /** Name */
            name: string;
            /** Status */
            status?: string | null;
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * ShardView
         * @description Public progress for one shard, excluding internal lease tokens.
         */
        ShardView: {
            /** Attempts */
            attempts: number;
            /** Id */
            id: string;
            /** Ordinal */
            ordinal: number;
            /** State */
            state: string;
        };
        /**
         * TaskInput
         * @description Task target, replay identity, and pipeline execution settings.
         */
        TaskInput: {
            /** Dataset Id */
            dataset_id: string;
            /** Idempotency Key */
            idempotency_key?: string;
            pipeline?: components["schemas"]["Pipeline"] | null;
            /**
             * Queue
             * @default cpu
             * @enum {string}
             */
            queue: "cpu" | "io" | "gpu";
            /**
             * Shards
             * @default 1
             */
            shards: number;
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * TaskView
         * @description Persisted task state and derived completion progress.
         */
        TaskView: {
            /** Completed Shards */
            completed_shards: number;
            /** Created At */
            created_at: number;
            /** Dataset Id */
            dataset_id: string;
            /** Error */
            error: string | null;
            /** Finished At */
            finished_at: number | null;
            /** Id */
            id: string;
            /** Input Version Id */
            input_version_id: string | null;
            /** Progress */
            progress: number;
            /** Shards */
            shards: components["schemas"]["ShardView"][];
            /** State */
            state: string;
            /** Total Shards */
            total_shards: number;
        };
        /**
         * TemplateView
         * @description Saved standard template and resulting compliance.
         */
        TemplateView: {
            compliance: components["schemas"]["ComplianceView"];
            /** Template */
            template: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
        };
        /**
         * TextSpan
         * @description Locate a half-open Unicode code-point interval after NFC normalization.
         */
        TextSpan: {
            /** End */
            end: number;
            /** Start */
            start: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "text_span";
        };
        /**
         * TimeRange
         * @description Select an inclusive start and exclusive end in the metric's date grain.
         */
        TimeRange: {
            /**
             * End
             * Format: date
             */
            end: string;
            /**
             * Start
             * Format: date
             */
            start: string;
        };
        /**
         * TokenSegment
         * @description Attribute input usage to a stable or volatile context segment.
         */
        TokenSegment: {
            /** Name */
            name: string;
            /**
             * Stable
             * @default false
             */
            stable: boolean;
            /** Tokens */
            tokens: number;
        };
        /**
         * TokenUsage
         * @description Count all input tokens once, with cache categories as input subsets.
         */
        TokenUsage: {
            /**
             * Cache Read Tokens
             * @default 0
             */
            cache_read_tokens: number;
            /**
             * Cache Write Tokens
             * @default 0
             */
            cache_write_tokens: number;
            /**
             * Input Tokens
             * @default 0
             */
            input_tokens: number;
            /**
             * Output Tokens
             * @default 0
             */
            output_tokens: number;
        };
        /**
         * ToolCall
         * @description One model-requested invocation with its protocol correlation identifier.
         */
        ToolCall: {
            arguments?: components["schemas"]["JsonDocument"];
            /** Id */
            id?: string;
            /** Name */
            name: string;
        };
        /**
         * ToolInvocation
         * @description Expose one durable tool span without leaking database rows.
         */
        ToolInvocation: {
            /** Actor */
            actor: string;
            /** Agent Id */
            agent_id: string | null;
            /** Argument Keys */
            argument_keys: string[];
            /** Arguments Digest */
            arguments_digest: string;
            /** Asset Refs */
            asset_refs: components["schemas"]["AssetRef"][];
            /** Completed At */
            completed_at: string | null;
            /** Elapsed Ms */
            elapsed_ms: number;
            /** Error */
            error: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Session Id */
            session_id: string | null;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "RUNNING" | "SUCCEEDED" | "FAILED";
        };
        /**
         * ToolOutcome
         * @description Return replayable data and explicit approval state after one tool invocation.
         */
        ToolOutcome: {
            /** Asset Refs */
            asset_refs?: components["schemas"]["AssetRef"][];
            content?: components["schemas"]["JsonDocument"];
            /** Error */
            error?: string | null;
            /** Invocation Id */
            invocation_id?: string | null;
            /** Name */
            name: string;
            plan?: components["schemas"]["ActionPlan"] | null;
            /**
             * Requires Approval
             * @default false
             */
            requires_approval: boolean;
            run?: components["schemas"]["ActionRun"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "SUCCEEDED" | "FAILED";
        };
        /**
         * ToolStep
         * @description Invoke a registered read or prepare and execute a reversible action.
         */
        ToolStep: {
            arguments: components["schemas"]["JsonDocument"];
            /** Id */
            id: string;
            /** Next */
            next: string;
            title?: components["schemas"]["WorkflowStepTitle"] | null;
            /** Tool */
            tool: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "tool";
        };
        /**
         * UploadFile
         * @description One basename and base64-encoded upload payload.
         */
        UploadFile: {
            /** Content Base64 */
            content_base64: string;
            /** Filename */
            filename: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * VersionView
         * @description Immutable manifest snapshot.
         */
        VersionView: {
            /** Created At */
            created_at: number;
            /** File Count */
            file_count: number;
            /** Id */
            id: string;
            /** Manifest */
            manifest: components["schemas"]["FileView"][];
        };
        /**
         * WaitStep
         * @description Poll one queued task with an explicit bounded deadline.
         */
        WaitStep: {
            /** Id */
            id: string;
            /** Next */
            next: string;
            /**
             * Poll Interval
             * @default 0.25
             */
            poll_interval: number;
            task_id: components["schemas"]["JsonValue"];
            /**
             * Timeout Seconds
             * @default 60
             */
            timeout_seconds: number;
            title?: components["schemas"]["WorkflowStepTitle"] | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "wait";
        };
        /**
         * Whole
         * @description Locate the entire revision of an asset.
         */
        Whole: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "whole";
        };
        /**
         * WorkflowAudit
         * @description Retain recovery authorization and interruption reasons beyond checkpoints.
         */
        WorkflowAudit: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "RESUME_DENIED" | "RESUME_AUTHORIZED" | "INTERRUPTED";
            /** Plan Id */
            plan_id?: string | null;
            /** Reason */
            reason: string;
            /** Run Id */
            run_id: string;
        };
        /**
         * WorkflowDefinition
         * @description Bind input declarations, routing vocabulary, and an acyclic step graph.
         */
        WorkflowDefinition: {
            /** Description */
            description: string;
            /** Entry */
            entry: string;
            /** Id */
            id: string;
            /** Inputs */
            inputs: {
                [key: string]: components["schemas"]["WorkflowInput"];
            };
            /** Name */
            name: string;
            /** Steps */
            steps: (components["schemas"]["ToolStep"] | components["schemas"]["ApprovalStep"] | components["schemas"]["WaitStep"] | components["schemas"]["BranchStep"] | components["schemas"]["OutputStep"])[];
            triggers: components["schemas"]["WorkflowTriggers"];
        };
        /**
         * WorkflowEvent
         * @description Send complete snapshots so reconnecting clients can recover through GET.
         */
        WorkflowEvent: {
            /**
             * Event
             * @enum {string}
             */
            event: "run" | "step" | "done";
            /** Id */
            id?: string;
            run: components["schemas"]["WorkflowRun"];
            /** Step Id */
            step_id?: string | null;
        };
        /**
         * WorkflowInput
         * @description Describe one form input and its deterministic default value.
         */
        WorkflowInput: {
            default?: components["schemas"]["JsonValue"];
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Required
             * @default true
             */
            required: boolean;
            /**
             * Type
             * @enum {string}
             */
            type: "string" | "number" | "integer" | "boolean" | "object" | "array";
        };
        /**
         * WorkflowRun
         * @description Read a complete run without exposing persistence rows or checkpoint state.
         */
        WorkflowRun: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error */
            error?: string | null;
            /** Id */
            id: string;
            inputs: components["schemas"]["JsonDocument"];
            /** Pending Plan Id */
            pending_plan_id?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "PENDING" | "RUNNING" | "PAUSED" | "SUCCEEDED" | "FAILED" | "INTERRUPTED";
            /** Steps */
            steps: components["schemas"]["WorkflowStep"][];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Workflow Id */
            workflow_id: string;
        };
        /**
         * WorkflowStart
         * @description Bind an explicit human start to validated inputs and a durable replay key.
         */
        WorkflowStart: {
            /** Idempotency Key */
            idempotency_key: string;
            inputs?: components["schemas"]["JsonDocument"];
        };
        /**
         * WorkflowStep
         * @description Expose one declared step's durable progress and JSON output.
         */
        WorkflowStep: {
            /** Error */
            error?: string | null;
            /** Finished At */
            finished_at?: string | null;
            /** Id */
            id: string;
            output?: components["schemas"]["JsonValue"];
            /** Plan Id */
            plan_id?: string | null;
            /** Started At */
            started_at?: string | null;
            /**
             * Status
             * @default PENDING
             * @enum {string}
             */
            status: "PENDING" | "RUNNING" | "PAUSED" | "SUCCEEDED" | "SKIPPED" | "FAILED";
            title?: components["schemas"]["WorkflowStepTitle"] | null;
            /** Tool */
            tool?: string | null;
            /** Type */
            type: string;
        };
        /**
         * WorkflowStepTitle
         * @description Name a declared step in both supported interface languages.
         */
        WorkflowStepTitle: {
            /** En */
            en: string;
            /** Zh */
            zh: string;
        };
        /**
         * WorkflowTriggers
         * @description Declare multilingual routing vocabulary and auditable score thresholds.
         */
        WorkflowTriggers: {
            /** Classification Keywords */
            classification_keywords?: string[];
            /** Excluded Groups */
            excluded_groups?: string[][];
            /** Excluded Keywords */
            excluded_keywords?: string[];
            /** Excluded Prefixes */
            excluded_prefixes?: string[];
            /** Keywords */
            keywords: string[][];
            /**
             * Margin
             * @default 1
             */
            margin: number;
            /**
             * Threshold
             * @default 1
             */
            threshold: number;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    action_plan_api_actions_plans__plan_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionPlan"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    action_runs_api_actions_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionRun"][];
                };
            };
        };
    };
    prepare_api_actions__action_type__prepare_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                action_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JsonDocument"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionPlan"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    execute_api_actions__plan_id__execute_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExecuteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionRun"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_all_api_agent_conversations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationView"][];
                };
            };
        };
    };
    create_api_agent_conversations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationCreate-Input"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    definitions_api_agent_conversations_definitions_agents_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentDefinition"][];
                };
            };
        };
    };
    get_api_agent_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    recovery_audit_api_agent_conversations__conversation_id__audit_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationAudit"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_api_agent_conversations__conversation_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_api_agent_conversations__conversation_id__resume_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResumeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    routes_api_agent_conversations__conversation_id__routes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RouteDecision"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    tree_api_agent_conversations__conversation_id__tree_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CallTree"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_all_api_agent_memories_get: {
        parameters: {
            query?: {
                dataset_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryEntry"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_api_agent_memories_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MemoryCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryEntry"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    audit_api_agent_memories_audit_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryDeletion"][];
                };
            };
        };
    };
    get_api_agent_memories__memory_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                memory_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryEntry"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_api_agent_memories__memory_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                memory_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryDeletion"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    pending_approvals_api_approvals_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionPlan"][];
                };
            };
        };
    };
    approve_api_approvals__plan_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalDecision"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionPlan"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ask_api_ask_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AskRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AskAnswer"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replay_api_ask__answer_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                answer_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AskAnswer"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    impact_api_catalog_impact_get: {
        parameters: {
            query: {
                asset_id: string;
                max_nodes?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImpactResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    metric_api_catalog_metrics__metric_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                metric_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetricCard"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    metric_history_api_catalog_metrics__metric_id__history_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                metric_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetricHistory"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    neighbors_api_catalog_neighbors_get: {
        parameters: {
            query: {
                asset_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImpactResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    asset_api_catalog_objects__asset_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogObject"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    table_api_catalog_tables__asset_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogTableDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    collection_api_catalog__collection__get: {
        parameters: {
            query?: {
                kind?: ("source" | "table" | "column" | "metric" | "dimension" | "term" | "owner") | null;
                source_id?: string | null;
                parent_id?: string | null;
                search?: string | null;
                offset?: number;
                limit?: number;
            };
            header?: never;
            path: {
                collection: "sources" | "tables" | "columns" | "metrics" | "dimensions" | "terms" | "owners";
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    datasets_api_datasets_get: {
        parameters: {
            query?: {
                include?: "quality" | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": (components["schemas"]["DatasetView"] | components["schemas"]["DatasetQualityView"])[];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_dataset_api_datasets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DatasetInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DatasetView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    dataset_api_datasets__identifier__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DatasetView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    compliance_api_datasets__identifier__compliance_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComplianceView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    files_api_datasets__identifier__files_get: {
        parameters: {
            query?: {
                version?: string | null;
            };
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileView"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_api_datasets__identifier__files__file_id__download_get: {
        parameters: {
            query?: {
                version?: string | null;
            };
            header?: never;
            path: {
                identifier: string;
                file_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_metadata_api_datasets__identifier__metadata_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetadataView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    metadata_api_datasets__identifier__metadata_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MetadataInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetadataSavedView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    changes_api_datasets__identifier__metadata_changes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetadataChangeView"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    quality_api_datasets__identifier__quality_get: {
        parameters: {
            query?: {
                quarantined?: boolean | null;
            };
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QualityView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    quality_config_api_datasets__identifier__quality_config_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QualityInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QualityView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    report_api_datasets__identifier__report_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    template_api_datasets__identifier__template_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JsonDocument"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TemplateView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    versions_api_datasets__identifier__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionView"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decide_api_evidence_assertions_decide_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecideAssertionsParams"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionRun"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    asset_api_evidence_assets__asset_id__get: {
        parameters: {
            query?: {
                version_id?: string | null;
            };
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceSample"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    query_api_evidence_query_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvidenceQuery"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceQueryResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_api_export_get: {
        parameters: {
            query: {
                format: "openlineage" | "croissant";
                dataset_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JsonDocument"] | components["schemas"]["JsonDocument"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    budgets_api_harness_budgets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BudgetAccount"][];
                };
            };
        };
    };
    costs_api_harness_costs_get: {
        parameters: {
            query?: {
                group_by?: "conversation" | "day" | "model";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CostSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    invocations_api_harness_invocations_get: {
        parameters: {
            query?: {
                session_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolInvocation"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    traces_api_harness_traces_get: {
        parameters: {
            query?: {
                conversation_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelCallTrace"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthView"];
                };
            };
        };
    };
    event_api_lineage_events_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LineageEvent"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventRecorded"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    lineage_api_lineage_graph_get: {
        parameters: {
            query?: {
                asset?: string | null;
                asset_id?: string | null;
                direction?: "both" | "upstream" | "downstream";
                depth?: number;
                include_semantic?: boolean;
                include_catalog?: boolean;
                hops?: number | null;
                max_nodes?: number;
                collapse?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GraphView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    definitions_api_ontology_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OntologyRegistry"];
                };
            };
        };
    };
    evaluate_objects_api_ontology_object_sets_evaluate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ObjectSet"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FrozenManifest"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    search_api_search_get: {
        parameters: {
            query?: {
                q?: string;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchResult"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    tasks_api_tasks_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskView"][];
                };
            };
        };
    };
    submit_api_tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    task_api_tasks__identifier__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    artifacts_api_tasks__identifier__artifacts_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileView"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    definitions_api_workflows_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowDefinition"][];
                };
            };
        };
    };
    runs_api_workflows_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowRun"][];
                };
            };
        };
    };
    run_api_workflows_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowRun"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    audit_api_workflows_runs__run_id__audit_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowAudit"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_api_workflows_runs__run_id__resume_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResumeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    definition_api_workflows__workflow_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowDefinition"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_api_workflows__workflow_id__runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkflowStart"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
