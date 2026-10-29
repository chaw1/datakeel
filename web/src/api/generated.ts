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
         *
         *     Releases and selected versions accept an explicit object/byte budget up to the
         *     configured ceiling; the budget is frozen into the plan that the user approves.
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
    "/api/actions/{plan_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Export
         * @description Download a completed export while rechecking current source export grants.
         */
        get: operations["download_export_api_actions__plan_id__export_get"];
        put?: never;
        post?: never;
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
    "/api/ask/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Conversations
         * @description List this actor's threads while omitting histories requiring absent grants.
         */
        get: operations["list_conversations_api_ask_conversations_get"];
        put?: never;
        /**
         * Create Conversation
         * @description Create a question thread independently of Agent runtime conversations.
         */
        post: operations["create_conversation_api_ask_conversations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ask/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Open Conversation
         * @description Recover saved turns only after owner and current asset authorization checks.
         */
        get: operations["open_conversation_api_ask_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Conversation
         * @description Delete an owned thread and its persisted question history.
         */
        delete: operations["delete_conversation_api_ask_conversations__conversation_id__delete"];
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
    "/api/catalog/import/airflow": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Airflow
         * @description Import one offline Airflow REST v1 export supplied by the caller.
         */
        post: operations["airflow_api_catalog_import_airflow_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/import/dbt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Dbt
         * @description Import decoded dbt artifacts without reading paths on the HTTP server.
         */
        post: operations["dbt_api_catalog_import_dbt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/import/objects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Objects
         * @description Browse imported orchestration and consumer nodes without changing old filters.
         */
        get: operations["objects_api_catalog_import_objects_get"];
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
    "/api/custom-operators": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Versions
         * @description List immutable approved code versions that may enter an operator chain.
         */
        get: operations["versions_api_custom_operators_get"];
        put?: never;
        /**
         * Submit
         * @description Prepare code review; submission alone never authorizes execution.
         */
        post: operations["submit_api_custom_operators_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/custom-operators/configuration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Configuration
         * @description Expose the backend and an explicit warning flag for unsafe local development.
         */
        get: operations["configuration_api_custom_operators_configuration_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/custom-operators/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Runs
         * @description Read successful and failed sandbox attempts without exposing host paths.
         */
        get: operations["runs_api_custom_operators_runs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/custom-operators/submissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Submissions
         * @description Read submitted code, static findings and the durable review status.
         */
        get: operations["submissions_api_custom_operators_submissions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/custom-operators/{code_hash}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Version
         * @description Read full approved code and its reviewed declarations by content hash.
         */
        get: operations["version_api_custom_operators__code_hash__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/custom-operators/{code_hash}/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Run
         * @description Enqueue an approved custom version against the selected dataset snapshot.
         */
        post: operations["run_api_custom_operators__code_hash__runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Market
         * @description Search measured asset cards using the declared deterministic sort contract.
         */
        get: operations["market_api_data_assets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/applications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Applications
         * @description Read request progress by asset or the existing operator identity.
         */
        get: operations["applications_api_data_assets_applications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/applications/{application_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Application
         * @description Read one durable request and its granted authorization identity.
         */
        get: operations["application_api_data_assets_applications__application_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Audit
         * @description Filter append-only allowed uses by asset and operator.
         */
        get: operations["audit_api_data_assets_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Grants
         * @description Read issued grants, retaining revoked and expired records as history.
         */
        get: operations["grants_api_data_assets_grants_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/grants/{grant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Grant
         * @description Read the exact granted scope, expiry, subject and revocation attribution.
         */
        get: operations["grant_api_data_assets_grants__grant_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Card
         * @description Aggregate current quality, lineage, freshness, related metrics and usage.
         */
        get: operations["card_api_data_assets__asset_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/{asset_id}/applications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Asset Applications
         * @description Read the request and approval progress displayed beside a card.
         */
        get: operations["asset_applications_api_data_assets__asset_id__applications_get"];
        put?: never;
        /**
         * Apply
         * @description Submit a purpose and bounded expiry; approval remains a controlled action.
         */
        post: operations["apply_api_data_assets__asset_id__applications_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/{asset_id}/control-history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Controls
         * @description Read append-only request and authorization decisions for an asset.
         */
        get: operations["controls_api_data_assets__asset_id__control_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-assets/{asset_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * History
         * @description Read every frozen card revision and its controlled operation attribution.
         */
        get: operations["history_api_data_assets__asset_id__history_get"];
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
    "/api/datasets/{dataset_id}/annotation-quality": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Overview
         * @description Read metrics, findings, repair comparisons and approved inspection history.
         */
        get: operations["overview_api_datasets__dataset_id__annotation_quality_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/annotation-quality/acceptance/prepare": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Prepare Acceptance
         * @description Prepare a typed inspection plan whose approval and execution use existing actions.
         */
        post: operations["prepare_acceptance_api_datasets__dataset_id__annotation_quality_acceptance_prepare_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/annotation-quality/batches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Import Batch
         * @description Append a frozen imported annotation batch; acceptance is a separate signed action.
         */
        post: operations["import_batch_api_datasets__dataset_id__annotation_quality_batches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/annotation-quality/rework/{batch_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Rework Export
         * @description Export suspected errors and signed rejected-unit details for a repair review.
         */
        get: operations["rework_export_api_datasets__dataset_id__annotation_quality_rework__batch_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/annotation-quality/samples": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sample
         * @description Freeze reproducible unit selection without declaring acceptance or rejection.
         */
        post: operations["sample_api_datasets__dataset_id__annotation_quality_samples_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/datasheets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Documents
         * @description List frozen drafts with their current version-expiry marker.
         */
        get: operations["documents_api_datasets__dataset_id__datasheets_get"];
        put?: never;
        /**
         * Generate
         * @description Freeze actual facts into a draft action; external model calls require approval.
         */
        post: operations["generate_api_datasets__dataset_id__datasheets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/text-governance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Reports
         * @description Read bounded reports for one pinned version or the latest immutable version.
         */
        get: operations["reports_api_datasets__dataset_id__text_governance_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/text-governance/analyze": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Analyze
         * @description Stream uploaded JSONL into a reproducible dry run without publishing clean files.
         */
        post: operations["analyze_api_datasets__dataset_id__text_governance_analyze_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{dataset_id}/text-governance/evaluations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Evaluations
         * @description List the user's own registered evaluation file references.
         */
        get: operations["evaluations_api_datasets__dataset_id__text_governance_evaluations_get"];
        put?: never;
        /**
         * Register
         * @description Register an exact uploaded JSONL or text manifest selection for contamination checks.
         */
        post: operations["register_api_datasets__dataset_id__text_governance_evaluations_post"];
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
    "/api/datasets/{identifier}/diff": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Version Diff
         * @description Compare any two same-dataset versions by stable file identity, hash, and metadata.
         */
        get: operations["version_diff_api_datasets__identifier__diff_get"];
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
    "/api/datasets/{identifier}/files/{file_id}/pointcloud-preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Pointcloud Preview
         * @description View a PNG preview from the same dataset/version scope as its point cloud.
         */
        get: operations["pointcloud_preview_api_datasets__identifier__files__file_id__pointcloud_preview_get"];
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
    "/api/datasets/{identifier}/releases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Releases
         * @description List approved immutable publications without exposing object locations.
         */
        get: operations["releases_api_datasets__identifier__releases_get"];
        put?: never;
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
    "/api/datasets/{identifier}/versions/{version_id}/training/compare": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Comparison
         * @description Compare two split sets from this same version, including changed sample assignments.
         */
        get: operations["comparison_api_datasets__identifier__versions__version_id__training_compare_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/versions/{version_id}/training/import-annotations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Import Annotations
         * @description Import typed COCO or YOLO detection annotations through the existing review store.
         */
        post: operations["import_annotations_api_datasets__identifier__versions__version_id__training_import_annotations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/versions/{version_id}/training/leakage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Preview Report
         * @description Inspect external directory splits without persisting their assignments.
         */
        post: operations["preview_report_api_datasets__identifier__versions__version_id__training_leakage_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/versions/{version_id}/training/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Preview
         * @description Calculate seeded class distributions without creating a saved split set.
         */
        post: operations["preview_api_datasets__identifier__versions__version_id__training_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/versions/{version_id}/training/splits": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Splits
         * @description List the named immutable split sets saved on this exact source version.
         */
        get: operations["splits_api_datasets__identifier__versions__version_id__training_splits_get"];
        put?: never;
        /**
         * Generate Split
         * @description Generate or import directory assignments and persist a named immutable split set.
         */
        post: operations["generate_split_api_datasets__identifier__versions__version_id__training_splits_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/versions/{version_id}/training/splits/{split_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Split Detail
         * @description Read saved assignments, configuration and per-class distributions.
         */
        get: operations["split_detail_api_datasets__identifier__versions__version_id__training_splits__split_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasets/{identifier}/versions/{version_id}/training/splits/{split_id}/leakage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Leakage
         * @description Return direct cross-split sample pairs, signal types and Hamming distances.
         */
        get: operations["leakage_api_datasets__identifier__versions__version_id__training_splits__split_id__leakage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasheets/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Job
         * @description Read queued, complete, failed or cancelled optional model generation.
         */
        get: operations["job_api_datasheets_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasheets/{before_id}/compare/{after_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Compare
         * @description Compare frozen fact values between two saved snapshots of the same dataset.
         */
        get: operations["compare_api_datasheets__before_id__compare__after_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasheets/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Document
         * @description Read one immutable cited document with current publication and expiry state.
         */
        get: operations["document_api_datasheets__document_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasheets/{document_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download
         * @description Download escaped Markdown or standalone HTML with sentence-level fact links.
         */
        get: operations["download_api_datasheets__document_id__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/datasheets/{document_id}/publish": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Publish
         * @description Prepare publication for explicit review through the existing approval gate.
         */
        post: operations["publish_api_datasheets__document_id__publish_post"];
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
    "/api/kg/entities/{entity_id}/links": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Associations
         * @description Show exact catalog matches and human decisions for one graph entity.
         */
        get: operations["associations_api_kg_entities__entity_id__links_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/evaluations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Evaluations
         * @description Read prior graph evaluations in newest-first order.
         */
        get: operations["evaluations_api_kg_evaluations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/graph": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Graph
         * @description Return a bounded graph with accepted alias display groups.
         */
        post: operations["graph_api_kg_graph_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/images/{file_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Image Content
         * @description Serve orientation-corrected original pixels in the same coordinate system as evidence.
         */
        get: operations["image_content_api_kg_images__file_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/links": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Links
         * @description Read reviewable associations from the latest graph of each selected dataset.
         */
        get: operations["links_api_kg_links_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/links/rerun": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Rerun Links
         * @description Refresh deterministic catalog associations without calling a model.
         */
        post: operations["rerun_links_api_kg_links_rerun_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Profiles
         * @description List profiles containing only credential environment variable names.
         */
        get: operations["profiles_api_kg_profiles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/query": {
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
         * @description Read filtered entities and candidate or decided relationships.
         */
        post: operations["query_api_kg_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/relations/{assertion_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Relation
         * @description Explain the exact source checks and model attribution for one relationship.
         */
        get: operations["relation_api_kg_relations__assertion_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Runs
         * @description Read extraction reports without exposing private frozen request data.
         */
        get: operations["runs_api_kg_runs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/runs/{extraction_id}/traces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Traces
         * @description List every metered model attempt belonging to one existing extraction run.
         */
        get: operations["traces_api_kg_runs__extraction_id__traces_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/schemas": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Schemas
         * @description List validated graph vocabularies available to extraction plans.
         */
        get: operations["schemas_api_kg_schemas_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/sources/{file_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Source
         * @description Read the frozen normalized text underlying displayed code-point offsets.
         */
        get: operations["source_api_kg_sources__file_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/transcription-profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Transcription Profiles
         * @description List validated image transcription configurations without reading credentials.
         */
        get: operations["list_transcription_profiles_api_kg_transcription_profiles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/kg/transcription-selection": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Select Transcription
         * @description Show whether the complete version can safely default to the packaged image replay.
         */
        get: operations["select_transcription_api_kg_transcription_selection_get"];
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
    "/api/openlineage/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ingest
         * @description Record one standard run transition and enrich its mapped catalog objects.
         */
        post: operations["ingest_api_openlineage_events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/production/functions/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Read Function
         * @description Read progress, workload, rework, agreement, confidence, labels and next task.
         */
        post: operations["read_function_api_production_functions__name__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/production/objects/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Objects
         * @description Project registered people and production objects with their exact AssetRef identity.
         */
        get: operations["objects_api_production_objects__kind__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/production/projects/{project_id}/workbench": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Project Workbench
         * @description Read exact production configuration, role scopes, measurements and a task page.
         */
        get: operations["project_workbench_api_production_projects__project_id__workbench_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/production/tasks/{task_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Task Content
         * @description View a version-pinned source or a small image preview under the same source grants.
         */
        get: operations["task_content_api_production_tasks__task_id__content_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/production/tasks/{task_id}/workbench": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Task Workbench
         * @description Read one sample with its complete revision, assignment and review evidence.
         */
        get: operations["task_workbench_api_production_tasks__task_id__workbench_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/production/workbench": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Workbench
         * @description Discover readable production projects and the server-selected human identity.
         */
        get: operations["workbench_api_production_workbench_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/issues": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Issues
         * @description Read merged failure episodes, recovery, ownership and resolution.
         */
        get: operations["issues_api_quality_issues_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report
         * @description Explain table quality using persisted observations and deterministic prose.
         */
        get: operations["report_api_quality_report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/rules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Rules
         * @description List exact current definitions with the latest result of each revision.
         */
        get: operations["rules_api_quality_rules_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/rules/{rule_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Rule
         * @description Read a rule definition and the exact revision's latest observation.
         */
        get: operations["rule_api_quality_rules__rule_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/rules/{rule_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * History
         * @description Read append-only accepted rule revisions, including a deletion tombstone.
         */
        get: operations["history_api_quality_rules__rule_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/rules/{rule_id}/results": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Results
         * @description Read a bounded newest-first trend, including observations of older revisions.
         */
        get: operations["results_api_quality_rules__rule_id__results_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Run
         * @description Read the durable task and terminal result identity for a scheduled execution.
         */
        get: operations["run_api_quality_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/quality/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Summary
         * @description Score current evidence without treating missing history as a pass.
         */
        get: operations["summary_api_quality_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/releases/{release_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Release
         * @description Read the exact metadata and measurements frozen at publication.
         */
        get: operations["release_api_releases__release_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/releases/{release_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export
         * @description Download a verified portable tar containing the manifest and independent records.
         */
        post: operations["export_api_releases__release_id__export_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/releases/{release_id}/files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Release Files
         * @description Page through frozen release entries independently of mutable source settings.
         */
        get: operations["release_files_api_releases__release_id__files_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/releases/{release_id}/reconcile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Verify
         * @description Verify current stored bytes and archive the complete receipt.
         */
        post: operations["verify_api_releases__release_id__reconcile_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/releases/{release_id}/reconciliations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * History
         * @description Read prior six-category receipts including per-file differences.
         */
        get: operations["history_api_releases__release_id__reconciliations_get"];
        put?: never;
        post?: never;
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
    "/api/standards/analysis-report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Analysis Report
         * @description Build the deterministic analysis report from the same checked column population.
         */
        get: operations["analysis_report_api_standards_analysis_report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/checks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Checks
         * @description Read redacted rule violations for the currently confirmed mappings.
         */
        get: operations["checks_api_standards_checks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/code-lists": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Code Lists
         * @description Search reference data names and bilingual value labels by lifecycle status.
         */
        get: operations["code_lists_api_standards_code_lists_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/contract": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Contract
         * @description Read the effective YAML-compatible contract without internal connection metadata.
         */
        get: operations["contract_api_standards_contract_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/coverage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Coverage
         * @description Group mapped-column coverage and compliance by source, table and owner.
         */
        get: operations["coverage_api_standards_coverage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export
         * @description Export the same strict field and code-list definitions as portable YAML.
         */
        get: operations["export_api_standards_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/fields": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Fields
         * @description Search bilingual field standards and optionally select their lifecycle status.
         */
        get: operations["fields_api_standards_fields_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * History
         * @description Read append-only versions with exact action and actor attribution.
         */
        get: operations["history_api_standards_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/mappings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Mappings
         * @description List only associations explicitly confirmed through controlled actions.
         */
        get: operations["mappings_api_standards_mappings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Profiles
         * @description Read column metadata and observed counts without exposing source sample values.
         */
        get: operations["profiles_api_standards_profiles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/quality": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Quality
         * @description Score observed completeness, consistency and domain rules for confirmed mappings.
         */
        get: operations["quality_api_standards_quality_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report
         * @description Read conformance checks and grouped coverage for all columns or one table.
         */
        get: operations["report_api_standards_report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/schema": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Schema
         * @description Return the JSON Schema applied to contract import and controlled edits.
         */
        get: operations["schema_api_standards_schema_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/standards/suggestions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Suggestions
         * @description Explain up to three rule candidates per column without confirming them.
         */
        get: operations["suggestions_api_standards_suggestions_get"];
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
    "/api/training-governance/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report
         * @description Return bounded redacted findings and any approved clean-version reference.
         */
        get: operations["report_api_training_governance__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/training-governance/{run_id}/clean": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Clean
         * @description Prepare mandatory human approval bound to this exact dry run and frozen sources.
         */
        post: operations["clean_api_training_governance__run_id__clean_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/training-governance/{run_id}/ledger": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Ledger
         * @description Download every keep, drop and redact decision with redacted evidence and reasons.
         */
        get: operations["ledger_api_training_governance__run_id__ledger_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/uploads": {
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
         * @description Declare file size, SHA-256, chunk size and a reusable idempotency key.
         */
        post: operations["start_api_uploads_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/uploads/{identifier}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Status
         * @description Read missing ordinals so reconnection sends only absent chunks.
         */
        get: operations["status_api_uploads__identifier__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/uploads/{identifier}/chunks/{ordinal}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Chunk
         * @description Stream at most the configured chunk limit under a process-shared concurrency cap.
         */
        put: operations["chunk_api_uploads__identifier__chunks__ordinal__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/uploads/{identifier}/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Complete
         * @description Verify every chunk and both whole-file hashes before atomic dataset publication.
         */
        post: operations["complete_api_uploads__identifier__complete_post"];
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
        /** @enum {string} */
        AccessEntry: "ask" | "export" | "download" | "mcp" | "agent";
        /** @enum {string} */
        AccessScope: "query" | "export" | "download";
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
            kg_estimate?: components["schemas"]["KGEstimate"] | null;
            /** Object Count */
            object_count: number;
            /** Total Bytes */
            total_bytes: number;
            transcription_estimate?: components["schemas"]["TranscriptionEstimate"] | null;
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
            action_type: "manage_users" | "manage_skills" | "define_role" | "update_role" | "create_label_set" | "publish_label_set" | "register_model" | "update_model" | "import_predictions" | "run_prelabel" | "finalize_project" | "create_project" | "split_packages" | "assign_tasks" | "claim_task" | "release_task" | "save_revision" | "submit_task" | "review_task" | "reopen_task" | "upgrade_project" | "create_data_asset" | "update_data_asset" | "publish_data_asset" | "withdraw_data_asset" | "decide_asset_application" | "revoke_asset_grant" | "quarantine_files" | "unquarantine_files" | "create_version_from_selection" | "run_pipeline" | "save_metadata" | "delete_files" | "export_dataset" | "decide_assertions" | "import_catalog" | "confirm_metric_draft" | "restore_catalog" | "update_metric" | "rollback_metric" | "update_term" | "rollback_term" | "run_kg_extraction" | "submit_custom_operator" | "publish_release" | "import_standards" | "update_standard" | "update_code_list" | "confirm_standard_mapping" | "rollback_standards" | "create_quality_rule" | "update_quality_rule" | "delete_quality_rule" | "run_quality_rule" | "change_quality_issue" | "annotation_acceptance" | "generate_datasheet" | "publish_datasheet" | "clean_training_data";
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
            action_type: "manage_users" | "manage_skills" | "define_role" | "update_role" | "create_label_set" | "publish_label_set" | "register_model" | "update_model" | "import_predictions" | "run_prelabel" | "finalize_project" | "create_project" | "split_packages" | "assign_tasks" | "claim_task" | "release_task" | "save_revision" | "submit_task" | "review_task" | "reopen_task" | "upgrade_project" | "create_data_asset" | "update_data_asset" | "publish_data_asset" | "withdraw_data_asset" | "decide_asset_application" | "revoke_asset_grant" | "quarantine_files" | "unquarantine_files" | "create_version_from_selection" | "run_pipeline" | "save_metadata" | "delete_files" | "export_dataset" | "decide_assertions" | "import_catalog" | "confirm_metric_draft" | "restore_catalog" | "update_metric" | "rollback_metric" | "update_term" | "rollback_term" | "run_kg_extraction" | "submit_custom_operator" | "publish_release" | "import_standards" | "update_standard" | "update_code_list" | "confirm_standard_mapping" | "rollback_standards" | "create_quality_rule" | "update_quality_rule" | "delete_quality_rule" | "run_quality_rule" | "change_quality_issue" | "annotation_acceptance" | "generate_datasheet" | "publish_datasheet" | "clean_training_data";
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
            /** Examples */
            examples?: {
                [key: string]: string[];
            };
            /** Handler */
            handler: string;
            /** Id */
            id: string;
            /** Inverse Of */
            inverse_of?: string | null;
            params_schema: components["schemas"]["JsonDocument"];
            /** Phrases */
            phrases?: {
                [key: string]: string[];
            };
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
         * AgreementValue
         * @description Represent an estimate or an explicit undefined estimate without NaN.
         */
        AgreementValue: {
            /** Observed Agreement */
            observed_agreement?: number | null;
            /** Reason */
            reason?: string | null;
            /**
             * Sample Count
             * @default 0
             */
            sample_count: number;
            /** Value */
            value: number | null;
        };
        /**
         * AirflowImportRequest
         * @description Supply an offline Airflow REST v1 export and a stable import source identity.
         */
        AirflowImportRequest: {
            document: components["schemas"]["JsonDocument"];
            /**
             * Name
             * @default Airflow
             */
            name: string;
            /** Source Id */
            source_id: string;
        };
        /**
         * AnnotationAcceptanceParams
         * @description Review every frozen sampled unit through the signed controlled action boundary.
         */
        AnnotationAcceptanceParams: {
            /** Batch Id */
            batch_id: string;
            /** Checks */
            checks: components["schemas"]["InspectionCheck"][];
            /** Dataset Id */
            dataset_id: string;
            /** Sampling Id */
            sampling_id: string;
            /** Version Id */
            version_id: string;
        };
        /**
         * AnnotationBatch
         * @description Freeze distinct sample/annotator records and review policy.
         *
         *     ``label_mode`` declares whether one sample may carry several labels; ``auto``
         *     infers single-select behaviour from the batch itself. ``outlier_policy`` belongs
         *     to the frozen batch, so its digest and every rework comparison bind the thresholds.
         */
        AnnotationBatch: {
            /** Annotations */
            annotations: components["schemas"]["AnnotationRecord"][];
            /**
             * Exclusive Label Groups
             * @default []
             */
            exclusive_label_groups: string[][];
            /**
             * Iou Threshold
             * @default 0.5
             */
            iou_threshold: number;
            /**
             * Label Mode
             * @default auto
             * @enum {string}
             */
            label_mode: "auto" | "single" | "multi";
            /**
             * Near Duplicates
             * @default []
             */
            near_duplicates: components["schemas"]["NearDuplicatePair"][];
            outlier_policy?: components["schemas"]["OutlierPolicy"];
        };
        /**
         * AnnotationBox
         * @description Preserve an xyxy box, including invalid coordinates for rule review.
         */
        AnnotationBox: {
            /** Attributes */
            attributes?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Category */
            category: string;
            /** X1 */
            x1: number;
            /** X2 */
            x2: number;
            /** Y1 */
            y1: number;
            /** Y2 */
            y2: number;
        };
        /**
         * AnnotationFinding
         * @description Provide a stable repair identity and human-readable evidence for a suspicion.
         */
        AnnotationFinding: {
            /** Annotator Id */
            annotator_id: string;
            /**
             * Code
             * @enum {string}
             */
            code: "minority_label" | "near_duplicate_conflict" | "bbox_size_outlier" | "bbox_aspect_outlier" | "invalid_bbox" | "multilabel_conflict" | "invalid_span" | "bbox_category_minority" | "bbox_missing" | "bbox_extra" | "duplicate_bbox" | "span_category_minority" | "span_boundary_minority" | "span_missing" | "span_extra" | "duplicate_span" | "span_length_outlier" | "rare_category";
            /** Evidence */
            evidence: string[];
            /** Finding Id */
            finding_id: string;
            /** Reason */
            reason: string;
            /**
             * Related Sample Ids
             * @default []
             */
            related_sample_ids: string[];
            /** Sample Id */
            sample_id: string;
        };
        /**
         * AnnotationImportRequest
         * @description Append one immutable annotation revision with an explicit retry identity.
         */
        AnnotationImportRequest: {
            batch: components["schemas"]["AnnotationBatch"];
            /** Idempotency Key */
            idempotency_key: string;
            /**
             * Name
             * @default Annotation batch
             */
            name: string;
            /** Rework Of */
            rework_of?: string | null;
            /** Version Id */
            version_id: string;
        };
        /**
         * AnnotationPoint
         * @description Keep one finite source-image pixel coordinate in a polygon.
         */
        AnnotationPoint: {
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /**
         * AnnotationPolygon
         * @description Preserve a closed polygon without duplicating its first vertex at the end.
         */
        AnnotationPolygon: {
            /** Attributes */
            attributes?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Category */
            category: string;
            /** Points */
            points: components["schemas"]["AnnotationPoint"][];
        };
        /**
         * AnnotationQAResult
         * @description Bundle deterministic metrics and review candidates for one frozen batch.
         */
        AnnotationQAResult: {
            /** Annotator Count */
            annotator_count: number;
            /**
             * Boxes
             * @default []
             */
            boxes: components["schemas"]["BoxAgreement"][];
            classification: components["schemas"]["ClassificationAgreement"];
            /**
             * Findings
             * @default []
             */
            findings: components["schemas"]["AnnotationFinding"][];
            /** Sample Count */
            sample_count: number;
            /**
             * Spans
             * @default []
             */
            spans: components["schemas"]["SpanAgreement"][];
        };
        /**
         * AnnotationQualityOverview
         * @description Read a dataset or exact version's annotation and inspection audit history.
         */
        AnnotationQualityOverview: {
            /**
             * Batches
             * @default []
             */
            batches: components["schemas"]["AnnotationQualityReport"][];
            /** Dataset Id */
            dataset_id: string;
            /**
             * Inspections
             * @default []
             */
            inspections: components["schemas"]["SamplingInspection"][];
            latest?: components["schemas"]["AnnotationQualityReport"] | null;
            /**
             * Sampling Plans
             * @default []
             */
            sampling_plans: components["schemas"]["SamplingPlan"][];
            /** Version Id */
            version_id: string | null;
        };
        /**
         * AnnotationQualityReport
         * @description Expose saved metrics and repair comparison without mutable database rows.
         */
        AnnotationQualityReport: {
            /** Annotation Count */
            annotation_count: number;
            /** Batch Digest */
            batch_digest: string;
            comparison?: components["schemas"]["ReworkComparison"] | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            result: components["schemas"]["AnnotationQAResult"];
            /** Rework Of */
            rework_of?: string | null;
            /** Sample Count */
            sample_count: number;
            /** Version Id */
            version_id: string;
        };
        /**
         * AnnotationRecord
         * @description Describe one annotator's work; None is missing and an empty tuple is reviewed empty.
         */
        AnnotationRecord: {
            /** Annotator Id */
            annotator_id: string;
            /** Attributes */
            attributes?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Boxes */
            boxes?: components["schemas"]["AnnotationBox"][] | null;
            /** Image Height */
            image_height?: number | null;
            /** Image Width */
            image_width?: number | null;
            /** Labels */
            labels?: string[] | null;
            /** Polygons */
            polygons?: components["schemas"]["AnnotationPolygon"][] | null;
            /** Sample Id */
            sample_id: string;
            /** Spans */
            spans?: components["schemas"]["AnnotationSpan"][] | null;
            /** Text Length */
            text_length?: number | null;
        };
        /**
         * AnnotationRevision
         * @description Append one annotation and its precise human or model provenance forever.
         */
        AnnotationRevision: {
            /** Actor */
            actor: string;
            annotation: components["schemas"]["AnnotationRecord"];
            /** Confidence */
            confidence?: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Model Name */
            model_name?: string | null;
            /** Model Version */
            model_version?: string | null;
            /** Previous Revision Id */
            previous_revision_id: string | null;
            /**
             * Source
             * @default human
             * @enum {string}
             */
            source: "human" | "model";
            /** Task Id */
            task_id: string;
        };
        /**
         * AnnotationSpan
         * @description Preserve a half-open character span for agreement and boundary review.
         */
        AnnotationSpan: {
            /** Attributes */
            attributes?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Category */
            category: string;
            /** End */
            end: number;
            /** Start */
            start: number;
        };
        /**
         * AnnotatorWorkload
         * @description Report distinct handled tasks, submissions and human rework decisions.
         */
        AnnotatorWorkload: {
            /** Actor */
            actor: string;
            /** Assigned */
            assigned: number;
            /** Completed */
            completed: number;
            /** Review Count */
            review_count: number;
            /** Rework Count */
            rework_count: number;
            /** Rework Rate */
            rework_rate: number;
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
             * Answer Kind
             * @default metric
             * @enum {string}
             */
            answer_kind: "metric" | "knowledge" | "profile";
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
            chart?: components["schemas"]["ChartSpec"] | null;
            comparison?: components["schemas"]["AskComparison"] | null;
            /** Conversation Id */
            conversation_id?: string | null;
            /** Id */
            id?: string;
            interpretation?: components["schemas"]["AskInterpretation"] | null;
            /**
             * Interpreted Question
             * @default
             */
            interpreted_question: string;
            knowledge?: components["schemas"]["KnowledgeAnswer"] | null;
            lineage?: components["schemas"]["LineageReference"] | null;
            /**
             * Matches
             * @default []
             */
            matches: components["schemas"]["MatchEvidence"][];
            /** Message */
            message: string;
            metric_card?: components["schemas"]["MetricCard"] | null;
            profile?: components["schemas"]["ProfileAnswer"] | null;
            query_frame?: components["schemas"]["AskQueryFrame"] | null;
            /** Question */
            question: string;
            recognition?: components["schemas"]["KnowledgeRecognition"] | null;
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
            /**
             * Subject Candidates
             * @default []
             */
            subject_candidates: components["schemas"]["KnowledgeSubject"][];
            time_range?: components["schemas"]["TimeRange"] | null;
        };
        /**
         * AskComparison
         * @description Expose the actual second query result and its arithmetic comparison.
         */
        AskComparison: {
            /**
             * Changes
             * @default []
             */
            changes: components["schemas"]["ComparisonChange"][];
            /**
             * Mode
             * @enum {string}
             */
            mode: "year_over_year" | "period_over_period";
            previous_result: components["schemas"]["QueryResult"];
            previous_sql: components["schemas"]["CompiledQuery"];
            previous_time_range: components["schemas"]["TimeRange"];
        };
        /**
         * AskConversation
         * @description Return an actor-owned question thread and its replayable turns.
         */
        AskConversation: {
            /** Actor */
            actor: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            current_frame?: components["schemas"]["AskQueryFrame"] | null;
            /** Id */
            id: string;
            /** Title */
            title: string;
            /**
             * Turns
             * @default []
             */
            turns: components["schemas"]["AskAnswer"][];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * AskInterpretation
         * @description Record how a numeric question was understood, including fragments left unexplained.
         */
        AskInterpretation: {
            /**
             * Group By
             * @default []
             */
            group_by: string[];
            /** Metric Id */
            metric_id?: string | null;
            /**
             * Slices
             * @default []
             */
            slices: components["schemas"]["DimensionSlice"][];
            /** Time Basis */
            time_basis?: ("period" | "as_of") | null;
            time_range?: components["schemas"]["TimeRange"] | null;
            /**
             * Unconsumed
             * @default []
             */
            unconsumed: string[];
        };
        /**
         * AskQueryFrame
         * @description Retain the complete resolved query, independently of conversational phrasing.
         */
        AskQueryFrame: {
            /** Comparison */
            comparison?: ("year_over_year" | "period_over_period") | null;
            /**
             * Group By
             * @default []
             */
            group_by: string[];
            /** Metric Id */
            metric_id: string;
            /**
             * Share Of Result Rows
             * @default false
             */
            share_of_result_rows: boolean;
            /**
             * Slices
             * @default []
             */
            slices: components["schemas"]["DimensionSlice"][];
            /** Time Basis */
            time_basis?: ("period" | "as_of") | null;
            /** Time Grain */
            time_grain?: ("day" | "month" | "quarter" | "year") | null;
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
            /** Conversation Id */
            conversation_id?: string | null;
            /** Knowledge Intent */
            knowledge_intent?: ("owner" | "upstream" | "downstream" | "owned") | null;
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
            /** Subject Id */
            subject_id?: string | null;
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
            /** Verification */
            verification?: ("verified" | "needs_review") | null;
            verification_detail?: components["schemas"]["VerificationDetail"] | null;
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
         * AssetApplication
         * @description Track a usage request and its explicit controlled approval decision.
         */
        AssetApplication: {
            /** Applicant */
            applicant: string;
            /** Asset Id */
            asset_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Decided At */
            decided_at?: string | null;
            /** Decided By */
            decided_by?: string | null;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Grant Id */
            grant_id?: string | null;
            /** Id */
            id: string;
            /** Purpose */
            purpose: string;
            /** Scopes */
            scopes: components["schemas"]["AccessScope"][];
            /**
             * Status
             * @default pending
             * @enum {string}
             */
            status: "pending" | "approved" | "rejected";
        };
        /**
         * AssetApplicationCreate
         * @description Carry the existing local operator identity and requested usage terms.
         */
        AssetApplicationCreate: {
            /**
             * Applicant
             * @default local-user
             */
            applicant: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Operation Id */
            operation_id?: string | null;
            /** Purpose */
            purpose: string;
            /** Scopes */
            scopes: components["schemas"]["AccessScope"][];
        };
        /** @enum {string} */
        AssetClassification: "public" | "internal" | "request" | "restricted";
        /**
         * AssetControlEvent
         * @description Preserve append-only application and grant decisions alongside asset history.
         */
        AssetControlEvent: {
            /** Action */
            action: string;
            /** Actor */
            actor: string;
            /** Asset Id */
            asset_id: string;
            /** Id */
            id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Operation Id */
            operation_id: string;
            /** Subject Id */
            subject_id: string;
        };
        /**
         * AssetGrant
         * @description Authorize exactly one subject, asset, and set of scopes until expiry.
         */
        AssetGrant: {
            /** Application Id */
            application_id: string;
            /** Asset Id */
            asset_id: string;
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
            /** Granted By */
            granted_by: string;
            /** Id */
            id: string;
            /** Revoked At */
            revoked_at?: string | null;
            /** Revoked By */
            revoked_by?: string | null;
            /** Scopes */
            scopes: components["schemas"]["AccessScope"][];
            /** Subject */
            subject: string;
        };
        /**
         * AssetHistory
         * @description Retain an immutable full asset snapshot for every controlled revision.
         */
        AssetHistory: {
            /** Action */
            action: string;
            /** Actor */
            actor: string;
            asset: components["schemas"]["DataAsset"];
            /** Asset Id */
            asset_id: string;
            /** Id */
            id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Operation Id */
            operation_id: string;
        };
        /**
         * AssetMarketPage
         * @description Return deterministic market ordering and the complete matching count.
         */
        AssetMarketPage: {
            /** Items */
            items: components["schemas"]["DataAssetCard"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
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
        /** @enum {string} */
        AssetSort: "popular" | "freshness" | "quality" | "downstream" | "name";
        /** @enum {string} */
        AssetStatus: "draft" | "published" | "withdrawn";
        /**
         * AssetUsage
         * @description Record one allowed asset use; stored records can never be updated or deleted.
         */
        AssetUsage: {
            /** Actor */
            actor: string;
            /** Asset Id */
            asset_id: string;
            entry: components["schemas"]["AccessEntry"];
            /** Grant Id */
            grant_id?: string | null;
            /** Id */
            id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            scope: components["schemas"]["AccessScope"];
        };
        /**
         * Assignment
         * @description Identify an actor's exclusive effective assignment for one task stage.
         */
        Assignment: {
            /**
             * Active
             * @default true
             */
            active: boolean;
            /** Actor */
            actor: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /**
             * Lease Expires At
             * Format: date-time
             */
            lease_expires_at: string;
            /**
             * Stage
             * @enum {string}
             */
            stage: "annotation" | "review";
            /** Task Id */
            task_id: string;
        };
        /**
         * AutoRoutingConfig
         * @description Keep every numerical routing threshold in the signed transcription profile.
         *
         *     Image analysis is bounded by downsampling, never by source filename or identity.
         *     Ratios use OCR line heights so the same signals survive image resizing.
         *     Document padding bounds the sparse-text denominator around OCR content; contrast
         *     rejects surrounding dark scenery. Grey-row comparisons require aligned nearby
         *     rows and abrupt local background changes; strike limits reject thick or extended
         *     background lines.
         */
        AutoRoutingConfig: {
            /**
             * Analysis Max Side
             * @default 1200
             */
            analysis_max_side: number;
            /**
             * Background Percentile
             * @default 90
             */
            background_percentile: number;
            /**
             * Connector Min Coverage
             * @default 0.72
             */
            connector_min_coverage: number;
            /**
             * Connector Min Height Ratio
             * @default 1.5
             */
            connector_min_height_ratio: number;
            /**
             * Connector Projection Margin Ratio
             * @default 0.5
             */
            connector_projection_margin_ratio: number;
            /**
             * Connector Tolerance Ratio
             * @default 0.12
             */
            connector_tolerance_ratio: number;
            /**
             * Dark Pixel Threshold
             * @default 160
             */
            dark_pixel_threshold: number;
            /**
             * Document Analysis Max Side
             * @default 256
             */
            document_analysis_max_side: number;
            /**
             * Document Min Component Area Ratio
             * @default 0.5
             */
            document_min_component_area_ratio: number;
            /**
             * Document Min Contrast
             * @default 25
             */
            document_min_contrast: number;
            /**
             * Document Padding Height Ratio
             * @default 3
             */
            document_padding_height_ratio: number;
            /**
             * Grey Alignment Height Ratio
             * @default 1
             */
            grey_alignment_height_ratio: number;
            /**
             * Grey Background Step Height Ratio
             * @default 0.2
             */
            grey_background_step_height_ratio: number;
            /**
             * Grey Context Height Ratio
             * @default 0.5
             */
            grey_context_height_ratio: number;
            /**
             * Grey Edge Probe Height Ratio
             * @default 0.05
             */
            grey_edge_probe_height_ratio: number;
            /**
             * Grey Max Brightness
             * @default 235
             */
            grey_max_brightness: number;
            /**
             * Grey Max Line Height Ratio
             * @default 1.6
             */
            grey_max_line_height_ratio: number;
            /**
             * Grey Max Neighbor Height Ratio
             * @default 8
             */
            grey_max_neighbor_height_ratio: number;
            /**
             * Grey Min Brightness
             * @default 100
             */
            grey_min_brightness: number;
            /**
             * Grey Min Contrast
             * @default 15
             */
            grey_min_contrast: number;
            /**
             * Grey Min Edge Concentration
             * @default 0.75
             */
            grey_min_edge_concentration: number;
            /**
             * Grey Min Row Fraction
             * @default 0.6
             */
            grey_min_row_fraction: number;
            /**
             * Grey Min Text Brightness
             * @default 110
             */
            grey_min_text_brightness: number;
            /**
             * Max Box Area Per Character
             * @default 2
             */
            max_box_area_per_character: number;
            /**
             * Max Connector Neighbors
             * @default 12
             */
            max_connector_neighbors: number;
            /**
             * Max Unmatched Ink Fraction
             * @default 0.85
             */
            max_unmatched_ink_fraction: number;
            /**
             * Min Mean Confidence
             * @default 0.85
             */
            min_mean_confidence: number;
            /**
             * Min Text Area Ratio
             * @default 0.003
             */
            min_text_area_ratio: number;
            /**
             * Sparse Max Characters
             * @default 16
             */
            sparse_max_characters: number;
            /**
             * Strike Max Extension Ratio
             * @default 1
             */
            strike_max_extension_ratio: number;
            /**
             * Strike Max Thickness Ratio
             * @default 0.2
             */
            strike_max_thickness_ratio: number;
            /**
             * Strike Min Width Ratio
             * @default 0.75
             */
            strike_min_width_ratio: number;
            /**
             * Strike Vertical Margin
             * @default 0.25
             */
            strike_vertical_margin: number;
            /**
             * Text Mask Padding Ratio
             * @default 0.08
             */
            text_mask_padding_ratio: number;
            /**
             * Version
             * @default auto-v2
             * @enum {string}
             */
            version: "auto-v1" | "auto-v2";
        };
        /**
         * BoxAgreement
         * @description Summarize descending-IoU greedy one-to-one matches across shared samples.
         */
        BoxAgreement: {
            /** Annotator A */
            annotator_a: string;
            /** Annotator B */
            annotator_b: string;
            /** Box Count A */
            box_count_a: number;
            /** Box Count B */
            box_count_b: number;
            /** Category Agreement */
            category_agreement: number | null;
            /** Match Rate */
            match_rate: number | null;
            /** Matched Count */
            matched_count: number;
            /** Mean Iou */
            mean_iou: number | null;
            /** Sample Count */
            sample_count: number;
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
         * BusinessSynonyms
         * @description Declare interchangeable business terms without broadening field aliases.
         */
        BusinessSynonyms: {
            /** Alternatives */
            alternatives: string[];
            /** Canonical */
            canonical: string;
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
            /** English Name */
            english_name?: string | null;
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
         * ChartSpec
         * @description Describe presentation without copying, rounding, or replacing result data.
         */
        ChartSpec: {
            /**
             * Available Types
             * @default [
             *       "table"
             *     ]
             */
            available_types: components["schemas"]["ChartType"][];
            /** Description */
            description: string;
            /** @default number */
            number_format: components["schemas"]["NumberFormat"];
            /** Series */
            series?: string | null;
            /**
             * Show Percent
             * @default false
             */
            show_percent: boolean;
            /**
             * Sort
             * @default source
             * @constant
             */
            sort: "source";
            /** Title */
            title: string;
            type: components["schemas"]["ChartType"];
            /** Unit */
            unit?: string | null;
            /** X */
            x?: string | null;
            /**
             * Y
             * @default []
             */
            y: string[];
        };
        /** @enum {string} */
        ChartType: "scalar" | "line" | "bar" | "horizontal_bar" | "grouped_bar" | "stacked_bar" | "table";
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
         * CheckResult
         * @description Report one of the six independent reconciliation categories.
         */
        CheckResult: {
            /**
             * Differences
             * @default []
             */
            differences: components["schemas"]["Difference"][];
            /**
             * Name
             * @enum {string}
             */
            name: "file_count" | "bytes" | "hashes" | "annotations" | "metadata" | "lineage";
            /** Passed */
            passed: boolean;
        };
        /**
         * ClassConfusion
         * @description Expose a per-label binary confusion matrix with the left annotator as reference.
         */
        ClassConfusion: {
            /** Category */
            category: string;
            /** False Negative */
            false_negative: number;
            /** False Positive */
            false_positive: number;
            /** True Negative */
            true_negative: number;
            /** True Positive */
            true_positive: number;
        };
        /**
         * ClassificationAgreement
         * @description Report nominal label-set agreement; Fleiss uses equal-sized rating panels.
         */
        ClassificationAgreement: {
            fleiss_kappa: components["schemas"]["AgreementValue"];
            krippendorff_alpha: components["schemas"]["AgreementValue"];
            /**
             * Pairs
             * @default []
             */
            pairs: components["schemas"]["ClassificationPair"][];
        };
        /**
         * ClassificationPair
         * @description Report Cohen kappa over complete nominal label sets and per-class membership.
         *
         *     ``matrix[i][j]`` counts samples that annotator_a put in ``categories[i]`` and
         *     annotator_b put in ``categories[j]``; a multilabel set is one category joined
         *     with ``+`` and a reviewed empty set is ``(empty)``.
         */
        ClassificationPair: {
            /** Annotator A */
            annotator_a: string;
            /** Annotator B */
            annotator_b: string;
            /**
             * Categories
             * @default []
             */
            categories: string[];
            cohen_kappa: components["schemas"]["AgreementValue"];
            /**
             * Confusion
             * @default []
             */
            confusion: components["schemas"]["ClassConfusion"][];
            /**
             * Matrix
             * @default []
             */
            matrix: number[][];
        };
        /**
         * CocoBox
         * @description Store standard absolute xywh coordinates with explicit image/category identities.
         */
        CocoBox: {
            /** Area */
            area?: number | null;
            /** Attributes */
            attributes?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Bbox */
            bbox: [
                number,
                number,
                number,
                number
            ];
            /** Category Id */
            category_id: number;
            /** Id */
            id: number;
            /** Image Id */
            image_id: number;
            /**
             * Iscrowd
             * @default 0
             * @enum {integer}
             */
            iscrowd: 0 | 1;
        };
        /**
         * CocoCategory
         * @description Describe a standard COCO detection category.
         */
        CocoCategory: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /**
             * Supercategory
             * @default
             */
            supercategory: string;
        };
        /**
         * CocoDataset
         * @description Accept standard detection COCO while ignoring unrelated upstream extensions.
         */
        CocoDataset: {
            /** Annotations */
            annotations: components["schemas"]["CocoBox"][];
            /** Categories */
            categories: components["schemas"]["CocoCategory"][];
            /** Images */
            images: components["schemas"]["CocoImage"][];
        };
        /**
         * CocoImage
         * @description Describe an image in a standard COCO detection document.
         */
        CocoImage: {
            /** Datakeel Sample Id */
            datakeel_sample_id?: string | null;
            /** File Name */
            file_name: string;
            /** Height */
            height: number;
            /** Id */
            id: number;
            /** Width */
            width: number;
        };
        /**
         * CodeEntry
         * @description Assign bilingual business labels to one scalar reference value.
         */
        CodeEntry: {
            /**
             * Label En
             * @default
             */
            label_en: string;
            /** Label Zh */
            label_zh: string;
            value: components["schemas"]["Scalar"];
        };
        /**
         * CodeList
         * @description Version a reference code list independently of field standards.
         */
        CodeList: {
            /** Code */
            code: string;
            /**
             * Entries
             * @default []
             */
            entries: components["schemas"]["CodeEntry"][];
            /** Name */
            name: string;
            /** @default draft */
            status: components["schemas"]["StandardStatus"];
            /**
             * Version
             * @default 1
             */
            version: number;
        };
        /**
         * ColumnCheck
         * @description Report checks over observations; row_count defines the checked population.
         */
        ColumnCheck: {
            /**
             * Checked Rules
             * @default []
             */
            checked_rules: components["schemas"]["ViolationRule"][];
            /** Column Id */
            column_id: string;
            /**
             * Compliant
             * @description Return whether every evaluated constraint passed.
             */
            readonly compliant: boolean;
            /**
             * Fully Checked
             * @description Return whether every declared constraint had sufficient evidence.
             */
            readonly fully_checked: boolean;
            /** Row Count */
            row_count: number;
            /**
             * Skipped Rules
             * @default []
             */
            skipped_rules: string[];
            /** Standard Code */
            standard_code: string;
            /**
             * Violations
             * @default []
             */
            violations: components["schemas"]["StandardViolation"][];
        };
        /**
         * ColumnMapping
         * @description Represent a human-confirmed column-to-standard association.
         */
        ColumnMapping: {
            /** Column Id */
            column_id: string;
            /** Standard Code */
            standard_code: string;
        };
        /**
         * ColumnProfile
         * @description Carry bounded observations without retaining database handles or row objects.
         */
        ColumnProfile: {
            /** Column Id */
            column_id: string;
            /** Data Type */
            data_type: string;
            /** Length */
            length?: number | null;
            /** Name */
            name: string;
            /**
             * Null Count
             * @default 0
             */
            null_count: number;
            /**
             * Owner
             * @default
             */
            owner: string;
            /** Precision */
            precision?: number | null;
            /**
             * Row Count
             * @default 0
             */
            row_count: number;
            /** Scale */
            scale?: number | null;
            sensitivity?: components["schemas"]["Sensitivity"] | null;
            /**
             * Source Id
             * @default
             */
            source_id: string;
            /**
             * Table Id
             * @default
             */
            table_id: string;
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
            /** Unit */
            unit?: string | null;
            /**
             * Values
             * @default []
             */
            values: components["schemas"]["StandardValue"][];
        };
        /**
         * ComparisonChange
         * @description Compare corresponding result rows without substituting a missing baseline.
         */
        ComparisonChange: {
            /** Current Value */
            current_value?: number | null;
            /** Delta */
            delta?: number | null;
            /**
             * Dimensions
             * @default []
             */
            dimensions: components["schemas"]["Scalar"][];
            /** Percent Change */
            percent_change?: number | null;
            /** Previous Value */
            previous_value?: number | null;
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
         * ConfidenceBucket
         * @description Count model revisions in a half-open bucket, with 1 included in the last.
         */
        ConfidenceBucket: {
            /** Count */
            count: number;
            /** Lower */
            lower: number;
            /** Upper */
            upper: number;
        };
        /**
         * ConfidenceDistribution
         * @description Count all model-source revision confidence observations for a project.
         */
        ConfidenceDistribution: {
            /** Buckets */
            buckets: components["schemas"]["ConfidenceBucket"][];
            /** Project Id */
            project_id: string;
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
         * CoverageGroup
         * @description Summarize coverage and mapped-column compliance within one metadata group.
         */
        CoverageGroup: {
            /** Compliance */
            compliance: number;
            /** Compliant Columns */
            compliant_columns: number;
            /** Coverage */
            coverage: number;
            /** Key */
            key: string;
            /** Mapped Columns */
            mapped_columns: number;
            /** Total Columns */
            total_columns: number;
        };
        /**
         * CustomOperatorConfiguration
         * @description Disclose whether the local service enables the unsafe development backend.
         */
        CustomOperatorConfiguration: {
            /**
             * Backend
             * @enum {string}
             */
            backend: "container" | "subprocess";
            /** Container Image */
            container_image: string;
            /** Subprocess Enabled */
            subprocess_enabled: boolean;
        };
        /**
         * CustomOperatorRun
         * @description Keep immutable execution attribution for successful and failed attempts.
         */
        CustomOperatorRun: {
            /** Attempt Id */
            attempt_id: string;
            /**
             * Backend
             * @default container
             * @enum {string}
             */
            backend: "container" | "subprocess";
            /** Code Hash */
            code_hash: string;
            /**
             * Completed At
             * Format: date-time
             */
            completed_at: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Exit Reason */
            exit_reason: string;
            /** Id */
            id: string;
            /** Image Digest */
            image_digest: string;
            /** Node Id */
            node_id: string;
            /** Operator */
            operator: string;
            /** Output Count */
            output_count: number;
            /** Params Digest */
            params_digest: string;
            resources: components["schemas"]["JsonDocument"];
            /** Shard Id */
            shard_id: string;
            /** Success */
            success: boolean;
            /** Task Id */
            task_id: string;
        };
        /**
         * CustomOperatorSubmission
         * @description Accept one complete Python source file with schemas declared as literals.
         */
        CustomOperatorSubmission: {
            /** Code */
            code: string;
            /**
             * Modality
             * @default any
             * @enum {string}
             */
            modality: "any" | "text" | "image";
            /** Name */
            name: string;
        };
        /**
         * CustomOperatorVersion
         * @description Identify an approved source version by its complete content digest.
         */
        CustomOperatorVersion: {
            /**
             * Approved At
             * Format: date-time
             */
            approved_at: string;
            /** Approved By */
            approved_by: string;
            /** Code */
            code: string;
            /** Code Hash */
            code_hash: string;
            /** Id */
            id: string;
            metadata_schema: components["schemas"]["JsonDocument"];
            /**
             * Modality
             * @default any
             * @enum {string}
             */
            modality: "any" | "text" | "image";
            /** Name */
            name: string;
            parameter_schema: components["schemas"]["JsonDocument"];
            /** Plan Id */
            plan_id: string;
            /** Static Checks */
            static_checks: components["schemas"]["StaticCheck"][];
        };
        /**
         * DataAsset
         * @description Expose one current asset revision without mutable persistence records.
         */
        DataAsset: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            definition: components["schemas"]["DataAssetDefinition"];
            /** Id */
            id: string;
            /** Revision */
            revision: number;
            /** @default draft */
            status: components["schemas"]["AssetStatus"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * DataAssetCard
         * @description Aggregate measured quality, lineage, freshness and factual usage statistics.
         */
        DataAssetCard: {
            asset: components["schemas"]["DataAsset"];
            /**
             * Downstream
             * @default []
             */
            downstream: components["schemas"]["AssetRef"][];
            /**
             * Downstream Count
             * @default 0
             */
            downstream_count: number;
            /** Freshness Seconds */
            freshness_seconds?: number | null;
            /** Quality Score */
            quality_score?: number | null;
            /**
             * Quality Trend
             * @default []
             */
            quality_trend: components["schemas"]["QualityPoint"][];
            /**
             * Related Metrics
             * @default []
             */
            related_metrics: components["schemas"]["AssetRef"][];
            /** Standard Coverage */
            standard_coverage?: number | null;
            /** Updated At */
            updated_at?: string | null;
            /**
             * Upstream
             * @default []
             */
            upstream: components["schemas"]["AssetRef"][];
            /**
             * Usage Count
             * @default 0
             */
            usage_count: number;
            /**
             * User Count
             * @default 0
             */
            user_count: number;
            version_release?: components["schemas"]["JsonDocument"] | null;
        };
        /**
         * DataAssetDefinition
         * @description Package an existing resource with business-facing, sanitized documentation.
         */
        DataAssetDefinition: {
            /** @default internal */
            classification: components["schemas"]["AssetClassification"];
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Instructions
             * @default
             */
            instructions: string;
            /** Name */
            name: string;
            /**
             * Name En
             * @default
             */
            name_en: string;
            /** Owner */
            owner: string;
            /**
             * Sample
             * @default
             */
            sample: string;
            /**
             * Scenarios
             * @default []
             */
            scenarios: string[];
            /**
             * Synonyms
             * @default []
             */
            synonyms: string[];
            /**
             * Tags
             * @default []
             */
            tags: string[];
            target: components["schemas"]["AssetRef"];
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
         * DatasheetComparison
         * @description Compare saved documents without re-reading mutable platform state.
         */
        DatasheetComparison: {
            /** After Id */
            after_id: string;
            /** Before Id */
            before_id: string;
            /**
             * Changed Chapters
             * @default []
             */
            changed_chapters: ("motivation" | "composition" | "collection" | "preprocessing" | "uses" | "distribution" | "maintenance")[];
            /**
             * Changes
             * @default []
             */
            changes: components["schemas"]["DatasheetFactChange"][];
        };
        /**
         * DatasheetDocument
         * @description Bind checked documentation to one immutable dataset version and fact snapshot.
         */
        DatasheetDocument: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /**
             * Dropped Sentences
             * @default []
             */
            dropped_sentences: components["schemas"]["DroppedSentence"][];
            /** Facts */
            facts: components["schemas"]["DatasheetFact"][];
            /** Id */
            id: string;
            /**
             * Language
             * @default zh
             * @enum {string}
             */
            language: "zh" | "en";
            /**
             * Mode
             * @default template
             * @enum {string}
             */
            mode: "template" | "model";
            /**
             * Published
             * @default false
             */
            published: boolean;
            /** Sections */
            sections: components["schemas"]["DatasheetSection"][];
            /**
             * Stale
             * @default false
             */
            stale: boolean;
            /** Version Id */
            version_id: string;
        };
        /**
         * DatasheetFact
         * @description Freeze one deterministic platform value together with its source coordinates.
         */
        DatasheetFact: {
            /**
             * Chapter
             * @enum {string}
             */
            chapter: "motivation" | "composition" | "collection" | "preprocessing" | "uses" | "distribution" | "maintenance";
            /** Field */
            field: string;
            /** Id */
            id: string;
            /**
             * Kind
             * @default text
             * @enum {string}
             */
            kind: "count" | "ratio" | "percent" | "score" | "bytes" | "amount" | "duration" | "date" | "name" | "status" | "text" | "number" | "record";
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Source Id */
            source_id: string;
            /** Source Type */
            source_type: string;
            /** Unit */
            unit?: string | null;
            value: components["schemas"]["JsonValue"];
        };
        /**
         * DatasheetFactChange
         * @description Describe one stable fact identity added, removed, or changed between drafts.
         */
        DatasheetFactChange: {
            after?: components["schemas"]["JsonValue"];
            before?: components["schemas"]["JsonValue"];
            /** Fact Id */
            fact_id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "added" | "removed" | "changed";
        };
        /**
         * DatasheetJob
         * @description Expose durable task progress without leaking the frozen outgoing fact payload.
         */
        DatasheetJob: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Document Id */
            document_id?: string | null;
            /** Error */
            error?: string | null;
            /** Id */
            id: string;
            /**
             * Language
             * @enum {string}
             */
            language: "zh" | "en";
            /**
             * Provider
             * @default fake
             * @enum {string}
             */
            provider: "fake" | "openai" | "anthropic";
            /**
             * Status
             * @default QUEUED
             * @enum {string}
             */
            status: "QUEUED" | "COMPLETED" | "FAILED" | "CANCELLED";
            /** Task Id */
            task_id: string;
            /** Version Id */
            version_id: string;
        };
        /**
         * DatasheetSection
         * @description Represent one fixed chapter and disclose when usable facts are absent.
         */
        DatasheetSection: {
            /**
             * Key
             * @enum {string}
             */
            key: "motivation" | "composition" | "collection" | "preprocessing" | "uses" | "distribution" | "maintenance";
            /**
             * Missing
             * @default false
             */
            missing: boolean;
            /**
             * Sentences
             * @default []
             */
            sentences: components["schemas"]["DatasheetSentence"][];
            /** Title */
            title: string;
        };
        /**
         * DatasheetSentence
         * @description Carry proposed text and explicit references before independent verification.
         */
        DatasheetSentence: {
            /**
             * Fact Ids
             * @default []
             */
            fact_ids: string[];
            /** Text */
            text: string;
        };
        /**
         * DbtImportRequest
         * @description Supply decoded dbt artifacts and the matching physical catalog source identity.
         */
        DbtImportRequest: {
            catalog?: components["schemas"]["JsonDocument"] | null;
            manifest: components["schemas"]["JsonDocument"];
            /**
             * Name
             * @default dbt
             */
            name: string;
            run_results?: components["schemas"]["JsonDocument"] | null;
            /** Source Id */
            source_id: string;
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
         * DeviceGapRank
         * @description Expose only aggregates reproduced exactly by the attached source intervals.
         */
        DeviceGapRank: {
            /** Device */
            device: string;
            /** Evidence */
            evidence: components["schemas"]["ProfileGapEvidence"][];
            /** Interval Count */
            interval_count: number;
            /** Total Gap Ms */
            total_gap_ms: number;
        };
        /**
         * DiffCounts
         * @description Complete five-way counts, independent of the requested page and filter.
         */
        DiffCounts: {
            /**
             * Added
             * @default 0
             */
            added: number;
            /**
             * Content Changed
             * @default 0
             */
            content_changed: number;
            /**
             * Metadata Changed
             * @default 0
             */
            metadata_changed: number;
            /**
             * Removed
             * @default 0
             */
            removed: number;
            /**
             * Unchanged
             * @default 0
             */
            unchanged: number;
        };
        /**
         * DiffFile
         * @description One stable file identity compared across two immutable manifests.
         */
        DiffFile: {
            after?: components["schemas"]["ReleaseFile"] | null;
            before?: components["schemas"]["ReleaseFile"] | null;
            /**
             * Category
             * @enum {string}
             */
            category: "added" | "removed" | "content_changed" | "metadata_changed" | "unchanged";
            /** File Id */
            file_id: string;
        };
        /**
         * Difference
         * @description Explain one failed check with machine-readable expected and actual values.
         */
        Difference: {
            actual?: components["schemas"]["JsonValue"];
            expected?: components["schemas"]["JsonValue"];
            /** Path */
            path: string;
            /** Reason */
            reason: string;
        };
        /**
         * DimensionSlice
         * @description Select a single dimension value by registered dimension identity.
         */
        DimensionSlice: {
            /** Dimension Id */
            dimension_id: string;
            value: components["schemas"]["Scalar"];
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
         * DqIssue
         * @description Track a contiguous failure episode through human confirmation.
         */
        DqIssue: {
            /** Assignee */
            assignee?: string | null;
            /**
             * Can Resolve
             * @default false
             */
            can_resolve: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Failures */
            failures: number;
            /** First Result Id */
            first_result_id: string;
            /** Id */
            id: string;
            /** Last Result Id */
            last_result_id: string;
            /** Revision */
            revision: number;
            /** Rule Id */
            rule_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "open" | "claimed" | "recovered" | "resolved";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** @enum {string} */
        DqKind: "not_null" | "unique" | "range" | "accepted_values" | "regex" | "referential_integrity" | "freshness" | "volume_change" | "distribution_drift" | "sql_assertion";
        /**
         * DqMetrics
         * @description Retain non-sensitive aggregate values for historical baselines.
         */
        DqMetrics: {
            /**
             * Bin Edges
             * @default []
             */
            bin_edges: number[];
            /**
             * Histogram
             * @default []
             */
            histogram: number[];
            /** Mean */
            mean?: number | null;
            /**
             * Null Rate
             * @default 0
             */
            null_rate: number;
            /**
             * Row Count
             * @default 0
             */
            row_count: number;
            /** Stddev */
            stddev?: number | null;
        };
        /**
         * DqParameters
         * @description Type all optional rule parameters, with kind-specific invariants on the rule.
         */
        DqParameters: {
            /**
             * Baseline Runs
             * @default 3
             */
            baseline_runs: number;
            /**
             * Bin Edges
             * @default []
             */
            bin_edges: number[];
            /** Bindings */
            bindings?: {
                [key: string]: components["schemas"]["Scalar"];
            };
            /** Maximum */
            maximum?: number | null;
            /** Minimum */
            minimum?: number | null;
            /** Pattern */
            pattern?: string | null;
            /** Reference Column */
            reference_column?: string | null;
            /** Reference Schema */
            reference_schema?: string | null;
            /** Reference Table */
            reference_table?: string | null;
            /** Sql */
            sql?: string | null;
            /**
             * Statistic
             * @default mean
             * @enum {string}
             */
            statistic: "mean" | "stddev" | "null_rate" | "psi";
            /**
             * Values
             * @default []
             */
            values: components["schemas"]["Scalar"][];
        };
        /**
         * DqReport
         * @description Provide a model-free analysis report grounded in persisted rule observations.
         */
        DqReport: {
            /** Body */
            body: string;
            summary: components["schemas"]["DqSummary"];
        };
        /**
         * DqResult
         * @description Record one immutable evaluation, including explicit non-verdict states.
         */
        DqResult: {
            /** Actual Value */
            actual_value?: number | null;
            /**
             * Coverage
             * @default unknown
             * @enum {string}
             */
            coverage: "complete" | "unknown";
            /**
             * Duration Ms
             * @default 0
             */
            duration_ms: number;
            /**
             * Failed Count
             * @default 0
             */
            failed_count: number;
            /** Id */
            id?: string;
            /**
             * Message
             * @default
             */
            message: string;
            metrics?: components["schemas"]["DqMetrics"];
            /**
             * Passed
             * @description Distinguish measured verdicts from failures to obtain an observation.
             */
            readonly passed: boolean | null;
            /**
             * Row Count
             * @default 0
             */
            row_count: number;
            /**
             * Rows Scanned
             * @default 0
             */
            rows_scanned: number;
            /** Rows Total */
            rows_total?: number | null;
            /** Rule Id */
            rule_id: string;
            /**
             * Rule Revision
             * @default 1
             */
            rule_revision: number;
            /**
             * Samples
             * @default []
             */
            samples: components["schemas"]["DqSample"][];
            /**
             * Started At
             * Format: date-time
             */
            started_at?: string;
            /**
             * Status
             * @enum {string}
             */
            status: "passed" | "failed" | "baseline_insufficient" | "error";
            /**
             * Threshold
             * @default 0
             */
            threshold: number;
        };
        /**
         * DqRule
         * @description Version a complete YAML or web quality rule and its execution limits.
         */
        DqRule: {
            /** Cron */
            cron?: string | null;
            /** Dataset Id */
            dataset_id?: string | null;
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
            /** Id */
            id: string;
            kind: components["schemas"]["DqKind"];
            /**
             * Max Rows
             * @default 10000
             */
            max_rows: number;
            /** Name */
            name: string;
            /** Owner */
            owner: string;
            params?: components["schemas"]["DqParameters"];
            /**
             * Revision
             * @default 1
             */
            revision: number;
            /**
             * Severity
             * @default error
             * @enum {string}
             */
            severity: "warn" | "error";
            target: components["schemas"]["DqTarget"];
            /**
             * Threshold
             * @default 0
             */
            threshold: number;
            /**
             * Timeout Ms
             * @default 5000
             */
            timeout_ms: number;
        };
        /**
         * DqRuleHistory
         * @description Preserve each accepted rule mutation and its accountable actor.
         */
        DqRuleHistory: {
            /** Actor */
            actor: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "create" | "update" | "delete";
            /** Revision */
            revision: number;
            rule: components["schemas"]["DqRule"];
            /** Rule Id */
            rule_id: string;
        };
        /**
         * DqRuleView
         * @description Pair a current rule definition with its most recent observation.
         */
        DqRuleView: {
            latest_result?: components["schemas"]["DqResult"] | null;
            /** Next Due At */
            next_due_at?: string | null;
            rule: components["schemas"]["DqRule"];
        };
        /**
         * DqRun
         * @description Expose one idempotent manual request or scheduled minute slot.
         */
        DqRun: {
            /** Error */
            error?: string | null;
            /** Id */
            id: string;
            /** Result Id */
            result_id?: string | null;
            /** Rule Id */
            rule_id: string;
            /** Rule Revision */
            rule_revision: number;
            /** Slot */
            slot: string;
            /** State */
            state: string;
            /** Task Id */
            task_id: string;
        };
        /**
         * DqSample
         * @description Expose only row ordinal and a redacted marker, never business cell contents.
         */
        DqSample: {
            /** Column */
            column?: string | null;
            /** Row Number */
            row_number: number;
            /**
             * Value
             * @default [REDACTED]
             * @constant
             */
            value: "[REDACTED]";
        };
        /**
         * DqSummary
         * @description Score only observed rules while keeping non-verdict states explicit.
         */
        DqSummary: {
            /**
             * Baseline Insufficient
             * @default 0
             */
            baseline_insufficient: number;
            /**
             * Errors
             * @default 0
             */
            errors: number;
            /**
             * Failed
             * @default 0
             */
            failed: number;
            /**
             * Open Issues
             * @default 0
             */
            open_issues: number;
            /**
             * Passed
             * @default 0
             */
            passed: number;
            /**
             * Pending
             * @default 0
             */
            pending: number;
            /**
             * Rules
             * @default []
             */
            rules: components["schemas"]["DqRuleView"][];
            /** Score */
            score?: number | null;
            /**
             * Total
             * @default 0
             */
            total: number;
        };
        /**
         * DqTarget
         * @description Identify a table in an existing catalog business source.
         */
        DqTarget: {
            /** Column */
            column?: string | null;
            /** Schema Name */
            schema_name?: string | null;
            /** Source Id */
            source_id: string;
            /** Table */
            table: string;
        };
        /**
         * DroppedSentence
         * @description Preserve rejected text and every independent citation failure reason.
         */
        DroppedSentence: {
            /**
             * Fact Ids
             * @default []
             */
            fact_ids: string[];
            /** Reasons */
            reasons: string[];
            /** Text */
            text: string;
        };
        /**
         * EffectiveScopes
         * @description Report current server authority and the legacy zero-user compatibility mode.
         */
        EffectiveScopes: {
            /** Actor */
            actor: string;
            /** Project Id */
            project_id?: string | null;
            /**
             * Scopes
             * @default []
             */
            scopes: string[];
            /**
             * Zero Users
             * @default false
             */
            zero_users: boolean;
        };
        /**
         * EntityLink
         * @description Expose the reviewable assertion and its graph and catalog endpoints.
         */
        EntityLink: {
            assertion: components["schemas"]["Assertion"];
            /** Basis */
            basis: string[];
            entity: components["schemas"]["KGEntity"];
            /**
             * Match Kind
             * @enum {string}
             */
            match_kind: "unique" | "ambiguous";
            target: components["schemas"]["CatalogObject"];
        };
        /**
         * EntityType
         * @description Declare an entity category and explicitly permitted spelling aliases.
         */
        EntityType: {
            /** Aliases */
            aliases?: {
                [key: string]: string[];
            };
            /** Description */
            description: string;
            /** Name */
            name: string;
            /**
             * Person
             * @default false
             */
            person: boolean;
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
            has_near_duplicate_in?: ("train" | "val" | "test") | null;
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
            split?: ("train" | "val" | "test") | null;
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
            split: ("train" | "val" | "test") | null;
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
         * ExtractedEntity
         * @description Carry a model-provided name and category before product validation.
         */
        ExtractedEntity: {
            /** Name */
            name: string;
            /** Type */
            type: string;
        };
        /**
         * ExtractedRelation
         * @description Carry a directed model claim and its purported verbatim evidence.
         */
        ExtractedRelation: {
            /** Evidence */
            evidence: string;
            /** Head */
            head: string;
            /** Relation */
            relation: string;
            /** Tail */
            tail: string;
        };
        /**
         * ExtractionProfile
         * @description Declare transport settings while allowing only environment variable key names.
         */
        ExtractionProfile: {
            /** Api Key Env */
            api_key_env?: string | null;
            /** Base Url */
            base_url?: string | null;
            /**
             * Chunk Overlap
             * @default 0
             */
            chunk_overlap: number;
            /**
             * Chunk Size
             * @default 12000
             */
            chunk_size: number;
            /**
             * Extractor
             * @enum {string}
             */
            extractor: "llm" | "fake" | "replay" | "gliner2";
            /** Id */
            id: string;
            /**
             * Max Output Tokens
             * @default 4096
             */
            max_output_tokens: number;
            /** Model */
            model: string;
            /**
             * Output Method
             * @default json_schema
             * @enum {string}
             */
            output_method: "json_schema" | "function_calling" | "json_mode";
            /**
             * Prompt Version
             * @default text-kg-v3
             * @enum {string}
             */
            prompt_version: "text-kg-v3" | "image-kg-v1";
            /** Provider */
            provider: string;
            /** Recording */
            recording?: string | null;
            /** Request Parameters */
            request_parameters?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /**
             * Temperature
             * @default 0
             */
            temperature: number;
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
         * FieldStandard
         * @description Describe the approved business meaning and permitted shape of a field.
         */
        FieldStandard: {
            /**
             * Aliases
             * @default []
             */
            aliases: string[];
            /** Code */
            code: string;
            /** Code List */
            code_list?: string | null;
            /** Data Type */
            data_type: string;
            /** Description */
            description: string;
            /** Length */
            length?: number | null;
            /** Maximum */
            maximum?: number | null;
            /** Minimum */
            minimum?: number | null;
            /** Name En */
            name_en: string;
            /** Name Zh */
            name_zh: string;
            /**
             * Owner
             * @default
             */
            owner: string;
            /** Pattern */
            pattern?: string | null;
            /** Precision */
            precision?: number | null;
            /**
             * Required
             * @default false
             */
            required: boolean;
            /** Scale */
            scale?: number | null;
            /** @default internal */
            sensitivity: components["schemas"]["Sensitivity"];
            /** @default draft */
            status: components["schemas"]["StandardStatus"];
            /** Unit */
            unit?: string | null;
            /**
             * Version
             * @default 1
             */
            version: number;
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
            media?: components["schemas"]["MediaFileView"] | null;
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
         * FunctionResult
         * @description Return replayable read results and explicit identities for tool auditing.
         */
        FunctionResult: {
            /** Asset Refs */
            asset_refs: components["schemas"]["AssetRef"][];
            data: components["schemas"]["JsonValue"];
            /** Function */
            function: string;
            skipped?: components["schemas"]["SkippedEntries"] | null;
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
         * GenerateDatasheetRequest
         * @description Choose a version, language and optional existing model configuration.
         */
        GenerateDatasheetRequest: {
            budget?: components["schemas"]["BudgetLimits-Input"];
            /**
             * Language
             * @default zh
             * @enum {string}
             */
            language: "zh" | "en";
            /**
             * Max Output Tokens
             * @default 4096
             */
            max_output_tokens: number;
            /**
             * Mode
             * @default template
             * @enum {string}
             */
            mode: "template" | "model";
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
            /** Request Parameters */
            request_parameters?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Version Id */
            version_id: string;
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
            /** English Name */
            english_name?: string | null;
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
         * ImageAutoMetrics
         * @description Score actual routing, outbound calls and product extraction on labelled images.
         */
        ImageAutoMetrics: {
            /** Cases */
            cases: number;
            /** External Images */
            external_images: number;
            /** External Ratio */
            external_ratio: number;
            /** Extraction F1 */
            extraction_f1: number;
            /** Labelled Cases */
            labelled_cases: number;
            /** Route Accuracy */
            route_accuracy?: number | null;
            /** Route Correct */
            route_correct: number;
            /** Routes */
            routes: components["schemas"]["ImageRouteResult"][];
            /** Vlm Images */
            vlm_images: number;
            /** Vlm Ratio */
            vlm_ratio: number;
        };
        /**
         * ImageGroupMetrics
         * @description Report an explicit image group or language slice with geometric and text quality.
         */
        ImageGroupMetrics: {
            /** Box Hit Rate */
            box_hit_rate: number;
            /** Box Hits */
            box_hits: number;
            /** Box True Positives */
            box_true_positives: number;
            /** Cer */
            cer?: number | null;
            /** Identifier Preservation */
            identifier_preservation?: number | null;
            metrics: components["schemas"]["KGMetrics"];
            /** Name */
            name: string;
            /**
             * Transcription Failures
             * @default 0
             */
            transcription_failures: number;
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
         * ImageRouteResult
         * @description Retain an observed route without using the expected route to choose a backend.
         */
        ImageRouteResult: {
            /** Case Id */
            case_id: string;
            /** Expected Route */
            expected_route?: ("ocr" | "vlm") | null;
            /**
             * External
             * @default false
             */
            external: boolean;
            /**
             * Reasons
             * @default []
             */
            reasons: ("low_confidence" | "structure_diagram" | "struck_or_greyed_rows" | "sparse_text" | "ocr_failed" | "clean_text")[];
            /** Route */
            route: ("ocr" | "vlm") | null;
        };
        /**
         * ImageScoringView
         * @description Keep clean, scan, diagram and bilingual slices in stable display order.
         */
        ImageScoringView: {
            /** Groups */
            groups: components["schemas"]["ImageGroupMetrics"][];
        };
        /**
         * ImageTransfer
         * @description Bind every potentially outbound image to the consent envelope.
         */
        ImageTransfer: {
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /** Image Hash */
            image_hash: string;
            /**
             * Mode
             * @enum {string}
             */
            mode: "ocr" | "vlm" | "auto";
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
         * InspectionCheck
         * @description Record one reviewed sampled unit; multiple errors count as one defective unit.
         */
        InspectionCheck: {
            /** Defective */
            defective: boolean;
            /**
             * Reason
             * @default
             */
            reason: string;
            /** Sample Id */
            sample_id: string;
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
         * KGBlockFailure
         * @description Explain a failed or unexecuted block using source offsets rather than silent omission.
         */
        KGBlockFailure: {
            /**
             * Attempted
             * @default true
             */
            attempted: boolean;
            /** End */
            end: number;
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /** Reason */
            reason: string;
            /** Start */
            start: number;
        };
        /**
         * KGBlockedRelation
         * @description Explain each relation excluded by the actual product pipeline.
         */
        KGBlockedRelation: {
            /** Case Id */
            case_id: string;
            /** Evidence */
            evidence: string;
            /** Head */
            head: string;
            /** Reason */
            reason: string;
            /** Relation */
            relation: string;
            /** Tail */
            tail: string;
        };
        /**
         * KGEntity
         * @description Expose the deterministic entity identity alongside its readable spelling.
         */
        KGEntity: {
            asset_ref: components["schemas"]["AssetRef"];
            /** Name */
            name: string;
            /** Type */
            type: string;
        };
        /**
         * KGEntityView
         * @description Expose all source mentions for one deterministic entity identity.
         */
        KGEntityView: {
            asset_ref: components["schemas"]["AssetRef"];
            /**
             * Mention Count
             * @default 0
             */
            mention_count: number;
            /**
             * Mentions
             * @default []
             */
            mentions: components["schemas"]["Assertion"][];
            /** Name */
            name: string;
            /** Type */
            type: string;
        };
        /**
         * KGEstimate
         * @description Bind visible outbound impact and its exact price snapshot to the plan digest.
         */
        KGEstimate: {
            /** Blocks */
            blocks: number;
            /** Cost Upper Usd */
            cost_upper_usd?: string | null;
            /** Documents */
            documents: number;
            /** Extraction Input Basis */
            extraction_input_basis?: "transcription_limit" | null;
            /** Input Tokens */
            input_tokens: number;
            /** Max Output Tokens */
            max_output_tokens: number;
            /** Model */
            model: string;
            price?: components["schemas"]["ModelPrice"] | null;
            /** Price Version */
            price_version?: string | null;
            /** Target Host */
            target_host: string | null;
        };
        /**
         * KGEvalFailure
         * @description Identify an unsuccessful source block without copying its text or provider body.
         */
        KGEvalFailure: {
            /** Case Id */
            case_id: string;
            /** End */
            end: number;
            /** Message */
            message?: string | null;
            /** Reason */
            reason: string;
            /** Start */
            start: number;
        };
        /**
         * KGEvalReport
         * @description Persist independent recording and production-path scores from one execution.
         */
        KGEvalReport: {
            /**
             * Blocked Relations
             * @default []
             */
            blocked_relations: components["schemas"]["KGBlockedRelation"][];
            /** Cost Usd */
            cost_usd?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at?: string;
            /** Elapsed Seconds */
            elapsed_seconds: number;
            /** Extraction Cost Usd */
            extraction_cost_usd?: string | null;
            /**
             * Failures
             * @default []
             */
            failures: components["schemas"]["KGEvalFailure"][];
            /** Id */
            id?: string;
            image_auto?: components["schemas"]["ImageAutoMetrics"] | null;
            image_product?: components["schemas"]["ImageScoringView"] | null;
            image_recording?: components["schemas"]["ImageScoringView"] | null;
            /**
             * Input Tokens
             * @default 0
             */
            input_tokens: number;
            /**
             * Metric Convention
             * @default Independent benchmark normalization and aliases; tolerated triples contribute neither TP nor FP; unmapped endpoints count as FP; empty precision and recall are zero. Recording verification preserves original span checks; product verification uses the production evidence/head/tail checks. Recorded usage is not replay execution usage.
             */
            metric_convention: string;
            /** Model */
            model: string;
            /**
             * Output Tokens
             * @default 0
             */
            output_tokens: number;
            product: components["schemas"]["KGScoringView"];
            /** Profile */
            profile: string;
            /**
             * Provider
             * @default kg
             * @constant
             */
            provider: "kg";
            recording: components["schemas"]["KGScoringView"];
            /**
             * Schema Version
             * @default 1.0
             * @constant
             */
            schema_version: "1.0";
            /**
             * Suite
             * @default text
             * @enum {string}
             */
            suite: "text" | "image";
            /** Suite Digest */
            suite_digest: string;
            /** Transcription Cost Usd */
            transcription_cost_usd?: string | null;
            /** Transcription Profile */
            transcription_profile?: string | null;
        };
        /**
         * KGGraph
         * @description Bound the displayed projection without changing underlying assertions.
         */
        KGGraph: {
            /** Dataset Id */
            dataset_id?: string | null;
            /**
             * Edges
             * @default []
             */
            edges: components["schemas"]["KGGraphEdge"][];
            /**
             * Nodes
             * @default []
             */
            nodes: components["schemas"]["KGGraphNode"][];
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * KGGraphEdge
         * @description Keep graph styling tied to the independent review and verification states.
         */
        KGGraphEdge: {
            /** Id */
            id: string;
            /** Predicate */
            predicate: string;
            /** Source */
            source: string;
            /**
             * Status
             * @enum {string}
             */
            status: "candidate" | "accepted" | "rejected";
            /** Target */
            target: string;
            /** Verification */
            verification?: ("verified" | "needs_review") | null;
        };
        /**
         * KGGraphNode
         * @description Represent one displayed entity or an accepted pair alias group.
         */
        KGGraphNode: {
            /** Entity Type */
            entity_type: string;
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Members */
            members: string[];
        };
        /**
         * KGMetrics
         * @description Preserve the independent scorer's published denominators and supporting measurements.
         */
        KGMetrics: {
            /** Cost Usd */
            cost_usd?: string | null;
            /** Endpoint In Text */
            endpoint_in_text: number;
            /** Endpoint Unmapped */
            endpoint_unmapped: number;
            entity_typed: components["schemas"]["PRF"];
            entity_untyped: components["schemas"]["PRF"];
            /** Errors */
            errors: number;
            /** Evidence Located */
            evidence_located: number;
            /** Failed Blocks */
            failed_blocks: number;
            /** Input Tokens */
            input_tokens?: number | null;
            /** Label Outside Schema */
            label_outside_schema: number;
            /** Latency Mean S */
            latency_mean_s: number;
            /** Latency Total S */
            latency_total_s: number;
            /** Missing */
            missing: string[];
            /** Output Tokens */
            output_tokens?: number | null;
            /** Passages */
            passages: number;
            /** Pred Relations */
            pred_relations: number;
            relation_pair: components["schemas"]["PRF"];
            relation_strict: components["schemas"]["PRF"];
            /** Trap Hits */
            trap_hits: number;
            /** Verified Ratio */
            verified_ratio: number;
        };
        /**
         * KGQuery
         * @description Select one dataset-version graph with explicit bounded result filters.
         */
        KGQuery: {
            /** Dataset Id */
            dataset_id?: string | null;
            /** Entity Type */
            entity_type?: string | null;
            /**
             * Limit
             * @default 100
             */
            limit: number;
            /** Name */
            name?: string | null;
            /** Status */
            status?: ("candidate" | "accepted" | "rejected") | null;
            /** Verification */
            verification?: ("verified" | "needs_review") | null;
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * KGQueryResult
         * @description Return entities and relations from exactly one dataset version.
         */
        KGQueryResult: {
            /** Dataset Id */
            dataset_id?: string | null;
            /**
             * Entities
             * @default []
             */
            entities: components["schemas"]["KGEntityView"][];
            /**
             * Relations
             * @default []
             */
            relations: components["schemas"]["KGRelationView"][];
            /**
             * Truncated
             * @default false
             */
            truncated: boolean;
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * KGRelationExplanation
         * @description Keep all checks and original documents together for a human review drawer.
         */
        KGRelationExplanation: {
            relation: components["schemas"]["KGRelationView"];
            /** Sources */
            sources: components["schemas"]["KGSourceText"][];
            /**
             * Summary
             * @default
             */
            summary: string;
        };
        /**
         * KGRelationView
         * @description Present an assertion with readable endpoints and extraction attribution.
         */
        KGRelationView: {
            assertion: components["schemas"]["Assertion"];
            /** Extraction Id */
            extraction_id: string;
            /** Extractor */
            extractor: string;
            head: components["schemas"]["KGEntity"];
            /** Image Located */
            image_located?: boolean | null;
            /** Model */
            model: string;
            tail: components["schemas"]["KGEntity"];
            /** Transcriber */
            transcriber?: string | null;
            /** Transcription Model */
            transcription_model?: string | null;
            /** Transcription Profile Id */
            transcription_profile_id?: string | null;
        };
        /**
         * KGReport
         * @description Summarize extraction, cache reuse, verification, billing and partial documents.
         */
        KGReport: {
            /**
             * Accounted Cost Usd
             * @default 0
             */
            accounted_cost_usd: string;
            /**
             * Blocks
             * @default 0
             */
            blocks: number;
            /**
             * Cached
             * @default 0
             */
            cached: number;
            /**
             * Cloud Calls
             * @default 0
             */
            cloud_calls: number;
            /** Cloud Cost Usd */
            cloud_cost_usd?: string | null;
            /** Cost Usd */
            cost_usd?: string | null;
            /**
             * Documents
             * @default 0
             */
            documents: number;
            /**
             * Elapsed Seconds
             * @default 0
             */
            elapsed_seconds: number;
            /**
             * Entities
             * @default 0
             */
            entities: number;
            /**
             * Entities Needs Review
             * @default 0
             */
            entities_needs_review: number;
            /**
             * Entities Verified
             * @default 0
             */
            entities_verified: number;
            /** Error */
            error?: string | null;
            /**
             * Extracted
             * @default 0
             */
            extracted: number;
            /** Extraction Cost Usd */
            extraction_cost_usd?: string | null;
            /**
             * Failed
             * @default 0
             */
            failed: number;
            /**
             * Failures
             * @default []
             */
            failures: components["schemas"]["KGBlockFailure"][];
            /**
             * Ignored Top Level Keys
             * @default 0
             */
            ignored_top_level_keys: number;
            /**
             * Input Tokens
             * @default 0
             */
            input_tokens: number;
            /**
             * Located Relations
             * @default 0
             */
            located_relations: number;
            /**
             * Model Calls
             * @default 0
             */
            model_calls: number;
            /**
             * Needs Review
             * @default 0
             */
            needs_review: number;
            /**
             * Output Tokens
             * @default 0
             */
            output_tokens: number;
            /**
             * Partial Documents
             * @default []
             */
            partial_documents: string[];
            /**
             * Proposals
             * @default []
             */
            proposals: components["schemas"]["SchemaProposal"][];
            /**
             * Relations
             * @default 0
             */
            relations: number;
            /**
             * Relations Needs Review
             * @default 0
             */
            relations_needs_review: number;
            /**
             * Relations Verified
             * @default 0
             */
            relations_verified: number;
            /** Transcription Cost Upper Usd */
            transcription_cost_upper_usd?: string | null;
            /** Transcription Cost Usd */
            transcription_cost_usd?: string | null;
            /**
             * Transcription External Images
             * @default 0
             */
            transcription_external_images: number;
            /**
             * Transcription Failed
             * @default 0
             */
            transcription_failed: number;
            /**
             * Transcriptions
             * @default []
             */
            transcriptions: components["schemas"]["TranscriptionObservation"][];
            /**
             * Unexecuted
             * @default 0
             */
            unexecuted: number;
            /**
             * Unlocated Relations
             * @default 0
             */
            unlocated_relations: number;
            /**
             * Verified
             * @default 0
             */
            verified: number;
        };
        /**
         * KGRun
         * @description Expose one durable worker run independently of its internal frozen inputs.
         */
        KGRun: {
            /** Completed At */
            completed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Extractor */
            extractor: string;
            /** Id */
            id: string;
            /** Model */
            model: string;
            /** Profile Id */
            profile_id: string;
            report?: components["schemas"]["KGReport"];
            /** Schema Id */
            schema_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "running" | "completed" | "partial" | "budget_exceeded" | "failed";
            /** Task Id */
            task_id?: string | null;
            /** Version Id */
            version_id: string;
        };
        /**
         * KGSchema
         * @description Describe a checked vocabulary without changing it during extraction.
         */
        KGSchema: {
            /** Entity Types */
            entity_types: components["schemas"]["EntityType"][];
            /**
             * Examples
             * @default []
             */
            examples: components["schemas"]["SchemaExample"][];
            /** Id */
            id: string;
            /** Relations */
            relations: components["schemas"]["RelationType"][];
            /** Rules */
            rules: string[];
            /** Version */
            version: string;
        };
        /**
         * KGScoringView
         * @description Show all predictions, language slices, and the verification-only subset.
         */
        KGScoringView: {
            all: components["schemas"]["KGMetrics"];
            en: components["schemas"]["KGMetrics"];
            verified: components["schemas"]["KGMetrics"];
            zh: components["schemas"]["KGMetrics"];
        };
        /**
         * KGSourceText
         * @description Return the precise decoded text used by verification offsets.
         */
        KGSourceText: {
            asset_ref: components["schemas"]["AssetRef"];
            /** Filename */
            filename: string;
            /** Height */
            height?: number | null;
            /** Image Url */
            image_url?: string | null;
            /** Text */
            text: string;
            /** Transcriber */
            transcriber?: string | null;
            /** Transcription Model */
            transcription_model?: string | null;
            /** Transcription Profile Id */
            transcription_profile_id?: string | null;
            /** Width */
            width?: number | null;
        };
        /**
         * KGTranscriptionSelection
         * @description Offer a replay default only when every selected image has a matching recording.
         */
        KGTranscriptionSelection: {
            /** Default Profile Id */
            default_profile_id?: string | null;
            /** Image Count */
            image_count: number;
        };
        /**
         * KnowledgeAnswer
         * @description Keep system records and document claims in separate, auditable collections.
         */
        KnowledgeAnswer: {
            /**
             * Claims
             * @default []
             */
            claims: components["schemas"]["KnowledgeClaim"][];
            /**
             * Intent
             * @enum {string}
             */
            intent: "owner" | "upstream" | "downstream" | "owned" | "related";
            /**
             * Intent Candidates
             * @default []
             */
            intent_candidates: ("owner" | "upstream" | "downstream" | "owned" | "related")[];
            /**
             * Pending Ambiguous Links
             * @default 0
             */
            pending_ambiguous_links: number;
            /** Reason Code */
            reason_code?: ("unknown_subject" | "ambiguous_subject" | "no_knowledge" | "unsupported_phrasing" | "pending_links" | "ambiguous_intent") | null;
            subject?: components["schemas"]["KnowledgeSubject"] | null;
            /**
             * System Message
             * @default
             */
            system_message: string;
            /**
             * System Records
             * @default []
             */
            system_records: components["schemas"]["KnowledgeSystemRecord"][];
        };
        /**
         * KnowledgeClaim
         * @description Carry one visible document assertion with independent review and source checks.
         */
        KnowledgeClaim: {
            /** Assertion Id */
            assertion_id: string;
            /** Consistency */
            consistency?: ("consistent" | "not_in_system" | "not_in_catalog") | null;
            /** Evidence */
            evidence: components["schemas"]["KnowledgeEvidence"][];
            head: components["schemas"]["KGEntity"];
            other_end: components["schemas"]["KnowledgeOtherEnd"];
            /** Predicate */
            predicate: string;
            /**
             * Relation Status
             * @enum {string}
             */
            relation_status: "candidate" | "accepted";
            subject_link?: components["schemas"]["KnowledgeSubjectLink"] | null;
            tail: components["schemas"]["KGEntity"];
            /**
             * Verification
             * @enum {string}
             */
            verification: "verified" | "needs_review";
        };
        /**
         * KnowledgeEvidence
         * @description Retain the verified evidence fragment and its immutable source document.
         */
        KnowledgeEvidence: {
            /** Document */
            document: string;
            /** End */
            end?: number | null;
            source: components["schemas"]["AssetRef"];
            /** Start */
            start?: number | null;
            /** Text */
            text: string;
        };
        /**
         * KnowledgeOtherEnd
         * @description Distinguish a linked data asset from missing and inapplicable catalog identities.
         */
        KnowledgeOtherEnd: {
            /** Assertion Id */
            assertion_id?: string | null;
            /** Asset Name */
            asset_name?: string | null;
            asset_ref?: components["schemas"]["AssetRef"] | null;
            entity: components["schemas"]["KGEntity"];
            /** Link Status */
            link_status?: ("candidate" | "accepted") | null;
            /**
             * Status
             * @enum {string}
             */
            status: "not_applicable" | "linked" | "not_in_catalog" | "link_rejected";
        };
        /**
         * KnowledgeRecognition
         * @description Record subject, interrogative focus, direction and the deterministic decision rule.
         */
        KnowledgeRecognition: {
            /** Direction */
            direction?: ("upstream" | "downstream") | null;
            /**
             * Direction Text
             * @default []
             */
            direction_text: string[];
            /**
             * Focus
             * @default unknown
             * @enum {string}
             */
            focus: "person" | "table" | "metric" | "location" | "list" | "unknown";
            /**
             * Focus Text
             * @default
             */
            focus_text: string;
            /** Rule Id */
            rule_id: string;
            /**
             * Subjects
             * @default []
             */
            subjects: components["schemas"]["KnowledgeSubjectMatch"][];
        };
        /**
         * KnowledgeSubject
         * @description Identify a resolved subject or a safe clarification or suggestion candidate.
         */
        KnowledgeSubject: {
            asset_ref: components["schemas"]["AssetRef"];
            /** Dataset Id */
            dataset_id?: string | null;
            /** Dataset Name */
            dataset_name?: string | null;
            /** Entity Type */
            entity_type?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "metric" | "table" | "view" | "owner" | "kg_entity";
            /** Name */
            name: string;
        };
        /**
         * KnowledgeSubjectLink
         * @description Explain the exact entity-to-asset assertion used to join a document claim.
         */
        KnowledgeSubjectLink: {
            /** Assertion Id */
            assertion_id: string;
            asset_ref: components["schemas"]["AssetRef"];
            entity: components["schemas"]["KGEntity"];
            /**
             * Link Status
             * @enum {string}
             */
            link_status: "candidate" | "accepted";
        };
        /**
         * KnowledgeSubjectMatch
         * @description Explain a registered subject name found before interpreting the question.
         */
        KnowledgeSubjectMatch: {
            subject: components["schemas"]["KnowledgeSubject"];
            /** Text */
            text: string;
        };
        /**
         * KnowledgeSystemRecord
         * @description Expose a registered asset without conflating it with a document assertion.
         */
        KnowledgeSystemRecord: {
            asset_ref: components["schemas"]["AssetRef"];
            /** Name */
            name: string;
            /**
             * Relation
             * @enum {string}
             */
            relation: "owner" | "upstream" | "downstream" | "owned";
        };
        /**
         * LabelCount
         * @description Count samples carrying a category, counting each category once per sample.
         */
        LabelCount: {
            /** Count */
            count: number;
            /** Label */
            label: string;
        };
        /**
         * LabelMigration
         * @description Declare how existing annotations are reviewed when label identities change.
         */
        LabelMigration: {
            /**
             * Operation
             * @enum {string}
             */
            operation: "rename" | "delete" | "merge" | "split";
            /**
             * Reason
             * @default
             */
            reason: string;
            /** Source Ids */
            source_ids: string[];
            /**
             * Strategy
             * @default map
             * @enum {string}
             */
            strategy: "map" | "drop" | "manual";
            /**
             * Target Ids
             * @default []
             */
            target_ids: string[];
        };
        /**
         * LabelSet
         * @description Keep one draft or immutable published vocabulary version.
         */
        LabelSet: {
            /**
             * Affected Annotations
             * @default 0
             */
            affected_annotations: number;
            /**
             * Affected Revisions
             * @default 0
             */
            affected_revisions: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Labels */
            labels: components["schemas"]["ProductionLabel"][];
            /**
             * Migration
             * @default []
             */
            migration: components["schemas"]["LabelMigration"][];
            /** Name */
            name: string;
            /** Previous Version */
            previous_version?: number | null;
            /**
             * Published
             * @default false
             */
            published: boolean;
            /** Published At */
            published_at?: string | null;
            /** Version */
            version: number;
        };
        /** @enum {string} */
        LeakageKind: "exact" | "image" | "text" | "group";
        /**
         * LeakagePair
         * @description Describe one direct cross-partition match and the measured signal distance.
         */
        LeakagePair: {
            /** Detail */
            detail: string;
            /** Distance */
            distance: number;
            kind: components["schemas"]["LeakageKind"];
            /** Left Id */
            left_id: string;
            left_split: components["schemas"]["SplitName"];
            /** Right Id */
            right_id: string;
            right_split: components["schemas"]["SplitName"];
        };
        /**
         * LeakageReport
         * @description Return direct pair evidence without merging transitive neighbors into false pairs.
         */
        LeakageReport: {
            /**
             * Checked Signals
             * @default [
             *       "exact",
             *       "image",
             *       "text",
             *       "group"
             *     ]
             */
            checked_signals: components["schemas"]["LeakageKind"][];
            /** Dataset Id */
            dataset_id: string;
            /** Pairs */
            pairs: components["schemas"]["LeakagePair"][];
            /** Sample Count */
            sample_count: number;
            /** Split Set Id */
            split_set_id: string;
            /** Version Id */
            version_id: string;
        };
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
         * LinkRunResult
         * @description Summarize an idempotent association refresh without exposing storage rows.
         */
        LinkRunResult: {
            /** Created */
            created: number;
            /** Entities */
            entities: number;
            /** Invalidated */
            invalidated: number;
            /** Links */
            links: number;
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
         * MappingCandidate
         * @description Explain one deterministic recommendation without confirming a mapping.
         */
        MappingCandidate: {
            /**
             * Low Confidence
             * @default false
             */
            low_confidence: boolean;
            /** Reasons */
            reasons: string[];
            /** Score */
            score: number;
            /** Standard Code */
            standard_code: string;
        };
        /**
         * MappingSuggestion
         * @description Return at most three candidates, distinguishing weak evidence for human review.
         */
        MappingSuggestion: {
            /**
             * Candidates
             * @default []
             */
            candidates: components["schemas"]["MappingCandidate"][];
            /** Column Id */
            column_id: string;
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
            match_kind: "exact" | "synonym" | "normalized" | "prefix" | "dimension_value" | "time";
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
         * MediaAlignment
         * @description Describe a recording's shared signal relative to the first input.
         *
         *     A positive offset means the shared signal occurs later in this recording;
         *     subtract the offset from this recording's timestamps to match the reference.
         *     Unalignable signals have a null offset, never an invented zero offset.
         */
        MediaAlignment: {
            /**
             * Aligned
             * @default false
             */
            aligned: boolean;
            /**
             * Confidence
             * @default 0
             */
            confidence: number;
            /** Offset Ms */
            offset_ms?: number | null;
            /**
             * Reason
             * @enum {string}
             */
            reason: "reference" | "matched" | "silence" | "ambiguous" | "no_common_signal" | "missing_audio";
            /** Reference File Id */
            reference_file_id: string;
        };
        /**
         * MediaFailure
         * @description Name a recording that could not be processed, the operator and the reason.
         */
        MediaFailure: {
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /** Operator */
            operator: string;
            /** Reason */
            reason: string;
        };
        /**
         * MediaFileScore
         * @description Explain one recording or clip's measured signal deductions.
         */
        MediaFileScore: {
            /** Accepted Lufs */
            accepted_lufs?: [
                number,
                number
            ] | null;
            /** Dimensions */
            dimensions: {
                [key: string]: number;
            };
            /** Duration Ms */
            duration_ms: number;
            /** Effective Duration Ms */
            effective_duration_ms: number;
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /** Loudness Lufs */
            loudness_lufs?: number | null;
            /** Loudness Tolerance Lu */
            loudness_tolerance_lu?: number | null;
            /** Reasons */
            reasons: string[];
            /** Total */
            total: number;
        };
        /**
         * MediaFileView
         * @description Expose typed recording measurements and source ranges to object pages.
         */
        MediaFileView: {
            alignment?: components["schemas"]["MediaAlignment"] | null;
            /** History */
            history?: components["schemas"]["MediaStep"][];
            /** Issues */
            issues?: components["schemas"]["MediaInterval"][];
            /** Metrics */
            metrics?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            probe: components["schemas"]["MediaProbe"];
            /** Source Asset Id */
            source_asset_id?: string | null;
            /** Source End Ms */
            source_end_ms?: number | null;
            /** Source File Id */
            source_file_id?: string | null;
            /**
             * Source Start Ms
             * @default 0
             */
            source_start_ms: number;
        };
        /**
         * MediaInterval
         * @description Locate a measured issue in the recording's local timeline.
         */
        MediaInterval: {
            /** Code */
            code: string;
            /** End Ms */
            end_ms: number;
            /**
             * Severity
             * @default warning
             * @enum {string}
             */
            severity: "info" | "warning" | "critical";
            /** Start Ms */
            start_ms: number;
        };
        /**
         * MediaProbe
         * @description Describe decoded recording properties in milliseconds and display coordinates.
         */
        MediaProbe: {
            /**
             * Audio Tracks
             * @default 0
             */
            audio_tracks: number;
            /**
             * Channels
             * @default 0
             */
            channels: number;
            /**
             * Codec
             * @default
             */
            codec: string;
            /** Declared Duration Ms */
            declared_duration_ms?: number | null;
            /** Duration Ms */
            duration_ms: number;
            /**
             * Format
             * @default
             */
            format: string;
            /**
             * Frame Rate
             * @default 0
             */
            frame_rate: number;
            /**
             * Height
             * @default 0
             */
            height: number;
            /**
             * Rotation
             * @default 0
             */
            rotation: number;
            /**
             * Sample Rate
             * @default 0
             */
            sample_rate: number;
            /**
             * Width
             * @default 0
             */
            width: number;
        };
        /**
         * MediaStep
         * @description Freeze one transformation and its immediate source time range.
         */
        MediaStep: {
            /** End Ms */
            end_ms?: number | null;
            /** Operator */
            operator: string;
            /** Parameters */
            parameters: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Parameters Digest */
            parameters_digest: string;
            /** Source File Id */
            source_file_id: string;
            /**
             * Start Ms
             * @default 0
             */
            start_ms: number;
            /**
             * Version
             * @default 1.0.0
             */
            version: string;
        };
        /**
         * MediaSummary
         * @description Aggregate original recordings separately from their derived clips.
         *
         *     Recordings that failed are listed in ``failures`` instead of being scored;
         *     ``partial`` is true when some recordings failed while others were processed.
         */
        MediaSummary: {
            /**
             * Clip Count
             * @default 0
             */
            clip_count: number;
            /**
             * Duplicate Count
             * @default 0
             */
            duplicate_count: number;
            /**
             * Effective Duration Ms
             * @default 0
             */
            effective_duration_ms: number;
            /** Failures */
            failures?: components["schemas"]["MediaFailure"][];
            /** Files */
            files?: components["schemas"]["MediaFileScore"][];
            /** Issue Distribution */
            issue_distribution?: {
                [key: string]: number;
            };
            /**
             * Original Duration Ms
             * @default 0
             */
            original_duration_ms: number;
            /**
             * Partial
             * @default false
             */
            partial: boolean;
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
         * MetadataImportReport
         * @description Add explicit soft deletion and semantic draft counts to an import summary.
         */
        MetadataImportReport: {
            /**
             * Changed
             * @default 0
             */
            changed: number;
            /**
             * Deleted
             * @default 0
             */
            deleted: number;
            /**
             * Drafts
             * @default 0
             */
            drafts: number;
            /** Event Id */
            event_id?: string | null;
            /**
             * Failed Sql Count
             * @description Count individually reported failed SQL statements.
             */
            readonly failed_sql_count: number;
            /**
             * Link Count
             * @default 0
             */
            link_count: number;
            /**
             * New
             * @default 0
             */
            new: number;
            /**
             * Notes
             * @description Explanations of how this import treated missing artifacts.
             * @default []
             */
            notes: string[];
            /** Object Count */
            object_count: number;
            /**
             * Parse Failures
             * @default []
             */
            parse_failures: components["schemas"]["SqlFailure"][];
            /**
             * Retained Columns
             * @description Reflected columns kept from the previous import because catalog.json was not provided.
             * @default 0
             */
            retained_columns: number;
            /**
             * Snapshot Version
             * @default 0
             */
            snapshot_version: number;
            /**
             * Unchanged
             * @default 0
             */
            unchanged: number;
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
            /** Owner English Name */
            owner_english_name?: string | null;
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
            /** English Name */
            english_name?: string | null;
            /** Filters */
            filters?: components["schemas"]["MetricFilter"][];
            /** Id */
            id: string;
            measure: components["schemas"]["Measure"];
            /** Name */
            name: string;
            /**
             * Number Format
             * @default number
             * @enum {string}
             */
            number_format: "number" | "integer" | "percent";
            /** Owner */
            owner: string;
            /** Synonyms */
            synonyms?: string[];
            time: components["schemas"]["MetricTime"];
            /** Unit */
            unit?: string | null;
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
            call_type: "conversation" | "intent_classifier" | "extraction" | "transcription";
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
            observed_usage?: components["schemas"]["TokenUsage"] | null;
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
         * ModelPrice
         * @description Store USD per million tokens, including the five-minute cache-write tier.
         */
        ModelPrice: {
            /** Cache Read */
            cache_read: string;
            /** Cache Write */
            cache_write: string;
            /** Input */
            input: string;
            /** Model */
            model: string;
            /** Output */
            output: string;
            /** Provider */
            provider: string;
            /** Source */
            source: string;
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
         * NearDuplicatePair
         * @description Identify a reviewed or computed near-duplicate relation, not a proven error.
         */
        NearDuplicatePair: {
            /** Other Sample Id */
            other_sample_id: string;
            /** Sample Id */
            sample_id: string;
            /**
             * Similarity
             * @default 1
             */
            similarity: number;
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
        /** @enum {string} */
        NumberFormat: "number" | "integer" | "percent";
        /**
         * OCRReference
         * @description Keep the local attempt for human comparison without feeding it to extraction.
         */
        OCRReference: {
            /** Error */
            error?: string | null;
            /** Text */
            text: string;
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
            has_near_duplicate_in?: ("train" | "val" | "test") | null;
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
            split?: ("train" | "val" | "test") | null;
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
         * OpenLineageDataset
         * @description Preserve schema and run-specific facets on a dataset reference.
         */
        OpenLineageDataset: {
            facets?: components["schemas"]["JsonDocument"];
            inputFacets?: components["schemas"]["JsonDocument"] | null;
            /** Name */
            name: string;
            /** Namespace */
            namespace: string;
            outputFacets?: components["schemas"]["JsonDocument"] | null;
        };
        /**
         * OpenLineageEntity
         * @description Read standard extensible job/dataset entities, ignoring producer extensions.
         */
        OpenLineageEntity: {
            facets?: components["schemas"]["JsonDocument"];
            /** Name */
            name: string;
            /** Namespace */
            namespace: string;
        };
        /**
         * OpenLineageReceipt
         * @description Report durable insertion and the effective state after out-of-order delivery.
         */
        OpenLineageReceipt: {
            /** Event Id */
            event_id: string;
            /** Inserted */
            inserted: boolean;
            /** Job Id */
            job_id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Run Id */
            run_id: string;
            /**
             * State
             * @enum {string}
             */
            state: "START" | "RUNNING" | "COMPLETE" | "ABORT" | "FAIL" | "OTHER";
        };
        /**
         * OpenLineageRun
         * @description Read a standard run identity and its extensible facet document.
         */
        OpenLineageRun: {
            facets?: components["schemas"]["JsonDocument"];
            /** Runid */
            runId: string;
        };
        /**
         * OpenLineageRunEvent
         * @description Accept standard run transitions with camel-case interchange fields.
         *
         *     START/RUNNING are in progress; COMPLETE/ABORT/FAIL are terminal; OTHER only
         *     carries metadata and never changes an observed run state.
         *
         *     OpenLineage permits producer extensions; unknown interchange properties are
         *     ignored while all metadata kept across internal boundaries remains typed.
         */
        OpenLineageRunEvent: {
            /**
             * Eventtime
             * Format: date-time
             */
            eventTime: string;
            /**
             * Eventtype
             * @enum {string}
             */
            eventType: "START" | "RUNNING" | "COMPLETE" | "ABORT" | "FAIL" | "OTHER";
            /**
             * Inputs
             * @default []
             */
            inputs: components["schemas"]["OpenLineageDataset"][];
            job: components["schemas"]["OpenLineageEntity"];
            /**
             * Outputs
             * @default []
             */
            outputs: components["schemas"]["OpenLineageDataset"][];
            /** Producer */
            producer: string;
            run: components["schemas"]["OpenLineageRun"];
            /** Schemaurl */
            schemaURL: string;
        };
        /**
         * OutlierPolicy
         * @description Tune the robust size, aspect-ratio and span-length outlier rules of one batch.
         *
         *     Defaults: modified z above 3.5 (above 5 when another annotator drew a matching
         *     item), at least 4x area or 3x aspect-ratio / span-length deviation from the
         *     category median, cohorts of at least ten items, and a cohort where more than
         *     10% would be flagged is treated as multimodal and skipped.
         */
        OutlierPolicy: {
            /**
             * Area Factor
             * @default 4
             */
            area_factor: number;
            /**
             * Aspect Factor
             * @default 3
             */
            aspect_factor: number;
            /**
             * Corroborated Z
             * @default 5
             */
            corroborated_z: number;
            /**
             * Max Flagged Share
             * @default 0.1
             */
            max_flagged_share: number;
            /**
             * Min Cohort
             * @default 10
             */
            min_cohort: number;
            /**
             * Modified Z
             * @default 3.5
             */
            modified_z: number;
            /**
             * Span Length Factor
             * @default 3
             */
            span_length_factor: number;
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
         * PRF
         * @description Expose three-decimal benchmark precision, recall, F1, and exact counts.
         */
        PRF: {
            /** F1 */
            f1: number;
            /** Fn */
            fn: number;
            /** Fp */
            fp: number;
            /** P */
            p: number;
            /** R */
            r: number;
            /** Tp */
            tp: number;
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
         * PrelabelAccuracy
         * @description Report exact model-draft agreement only against approved human reference revisions.
         */
        PrelabelAccuracy: {
            /** Assessed Tasks */
            assessed_tasks: number;
            /** Exact Match Rate */
            exact_match_rate?: number | null;
            /** Exact Match Tasks */
            exact_match_tasks: number;
            /** Project Id */
            project_id: string;
        };
        /**
         * ProductionLabel
         * @description Describe a stable label identity and its optional tree presentation.
         */
        ProductionLabel: {
            /** Attributes */
            attributes?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Color */
            color?: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Parent Id */
            parent_id?: string | null;
            /** Shortcut */
            shortcut?: string | null;
        };
        /**
         * ProductionProgress
         * @description Project current counters and repeatedly reworked tasks without counting all tasks.
         */
        ProductionProgress: {
            /** Counts */
            counts: components["schemas"]["StateCount"][];
            /** Package Id */
            package_id?: string | null;
            /** Project Id */
            project_id: string;
            /**
             * Rework Task Ids
             * @default []
             */
            rework_task_ids: string[];
            /** Status */
            status: string;
            /** Total */
            total: number;
        };
        /**
         * ProductionTask
         * @description Track one sample, its immutable revision heads and explicit rework round.
         */
        ProductionTask: {
            /** Annotator Id */
            annotator_id?: string | null;
            /** Approved Revision Id */
            approved_revision_id?: string | null;
            /** Confidence */
            confidence?: number | null;
            /** Id */
            id: string;
            /** Latest Revision Id */
            latest_revision_id?: string | null;
            /** Package Id */
            package_id: string;
            /**
             * Priority
             * @default 0
             */
            priority: number;
            /** Project Id */
            project_id: string;
            /**
             * Round
             * @default 0
             */
            round: number;
            /** Sample Id */
            sample_id: string;
            /**
             * State
             * @default pending
             * @enum {string}
             */
            state: "pending" | "in_progress" | "submitted" | "in_review" | "approved" | "finalized";
        };
        /**
         * ProductionTemplate
         * @description Configure one supported core annotation representation and validation rules.
         */
        ProductionTemplate: {
            /**
             * Annotation Type
             * @default box
             * @enum {string}
             */
            annotation_type: "box" | "polygon" | "keypoints" | "classification" | "text_span";
            /**
             * Archived
             * @default false
             */
            archived: boolean;
            /** Component Config */
            component_config?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Revision
             * @default 1
             */
            revision: number;
            /** Validation Rules */
            validation_rules?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
        };
        /**
         * ProductionWorkload
         * @description Contain exact workload and rework measurements for one project.
         */
        ProductionWorkload: {
            /** Annotators */
            annotators: components["schemas"]["AnnotatorWorkload"][];
            /** Project Id */
            project_id: string;
        };
        /**
         * ProfileAnswer
         * @description Keep sampling-axis measurements distinct from per-column missing-value claims.
         */
        ProfileAnswer: {
            /**
             * Candidates
             * @default []
             */
            candidates: components["schemas"]["ProfileDataset"][];
            dataset?: components["schemas"]["ProfileDataset"] | null;
            /**
             * Intent
             * @default device_gaps
             * @constant
             */
            intent: "device_gaps";
            /**
             * Ranking
             * @default []
             */
            ranking: components["schemas"]["DeviceGapRank"][];
            /** Reason Code */
            reason_code?: ("no_profile" | "ambiguous_dataset" | "unknown_subject" | "unknown_column" | "incomplete_profile" | "no_recorded_gaps") | null;
            /** Requested Column */
            requested_column?: string | null;
            /**
             * Scope
             * @default sampling_time_axis
             * @constant
             */
            scope: "sampling_time_axis";
            /**
             * Sort By
             * @default gap_count
             * @enum {string}
             */
            sort_by: "gap_count" | "total_gap_ms";
        };
        /**
         * ProfileColumnBrief
         * @description Describe a column using aggregate profile evidence only.
         */
        ProfileColumnBrief: {
            /** Inferred Type */
            inferred_type: string;
            /** Name */
            name: string;
            /** Null Rate */
            null_rate: number;
            /**
             * Pii Kinds
             * @default []
             */
            pii_kinds: string[];
            /** Unique Rate */
            unique_rate: number;
        };
        /**
         * ProfileDataset
         * @description Pin a dataset candidate to its current immutable published version.
         */
        ProfileDataset: {
            /** Dataset Id */
            dataset_id: string;
            /** Dataset Name */
            dataset_name: string;
            /** Version Id */
            version_id: string;
        };
        /**
         * ProfileGapEvidence
         * @description Bind one sampling-axis gap to a file version, bounding rows and UTC interval.
         */
        ProfileGapEvidence: {
            /** Dataset Id */
            dataset_id: string;
            /** Device */
            device: string;
            /** End Ms */
            end_ms: number;
            /** Expected Interval Ms */
            expected_interval_ms: number;
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /** Gap Ms */
            gap_ms: number;
            /**
             * Row Coordinates
             * @default original_source
             * @constant
             */
            row_coordinates: "original_source";
            /** Rows */
            rows: [
                number,
                number
            ];
            /** Source File Id */
            source_file_id: string;
            /** Source Version Id */
            source_version_id: string;
            /** Start Ms */
            start_ms: number;
            /** Time Column */
            time_column: string;
            /** Version Id */
            version_id: string;
        };
        /**
         * Project
         * @description Bind production to immutable input data and published annotation rules.
         */
        Project: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Finalized Version Id */
            finalized_version_id?: string | null;
            /**
             * Guidelines
             * @default
             */
            guidelines: string;
            /** Id */
            id: string;
            /** Label Set Id */
            label_set_id: string;
            /** Label Set Version */
            label_set_version: number;
            /** Name */
            name: string;
            /**
             * Review Prompt Shown
             * @default false
             */
            review_prompt_shown: boolean;
            /** Template Id */
            template_id?: string | null;
            /** Version Id */
            version_id: string;
            /**
             * Workflow Tier
             * @default personal
             * @enum {string}
             */
            workflow_tier: "personal" | "group" | "team";
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
         * QualityPoint
         * @description Associate a measured quality score with its evidence timestamp.
         */
        QualityPoint: {
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Score */
            score: number;
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
            media?: components["schemas"]["MediaSummary"] | null;
            rules?: components["schemas"]["DqSummary"] | null;
            tabular?: components["schemas"]["TabularAssessment"] | null;
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
         * ReconcileReport
         * @description Archive a complete offline or platform-side verification result.
         */
        ReconcileReport: {
            /** Categories */
            categories: components["schemas"]["CheckResult"][];
            /** Created At */
            created_at?: number;
            /** Id */
            id?: string;
            /** Passed */
            passed: boolean;
            /** Release Id */
            release_id?: string | null;
        };
        /**
         * RelationType
         * @description Constrain a directed relation to declared endpoint categories.
         */
        RelationType: {
            /** Description */
            description: string;
            /** Domain */
            domain: string[];
            /** Name */
            name: string;
            /** Range */
            range: string[];
        };
        /**
         * ReleaseFile
         * @description Portable release file facts without internal storage locations.
         */
        ReleaseFile: {
            /** Annotation Count */
            annotation_count: number;
            /** Filename */
            filename: string;
            /** Id */
            id: string;
            /** Label Count */
            label_count: number;
            /** Lineage Refs */
            lineage_refs: string[];
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
            /** Source Version */
            source_version: string;
        };
        /**
         * ReleaseFiles
         * @description Bounded portable entries from an immutable published release.
         */
        ReleaseFiles: {
            /** Files */
            files: components["schemas"]["ReleaseFile"][];
            /** Next Offset */
            next_offset?: number | null;
        };
        /**
         * ReleaseView
         * @description Immutable published manifest identity, provenance, and release notes.
         */
        ReleaseView: {
            /** Created At */
            created_at: number;
            /** Dataset Id */
            dataset_id: string;
            /** File Count */
            file_count: number;
            /** Id */
            id: string;
            /** Manifest Sha256 */
            manifest_sha256: string;
            /** Metadata */
            metadata: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Notes */
            notes: string;
            summary: components["schemas"]["VersionSummary"];
            /** Tag */
            tag: string;
            /** Total Bytes */
            total_bytes: number;
            /** Version Id */
            version_id: string;
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
         * Review
         * @description Retain a human decision against an exact submitted revision and round.
         */
        Review: {
            /** Actor */
            actor: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "rework";
            /** Id */
            id: string;
            /**
             * Issues
             * @default []
             */
            issues: string[];
            /** Revision Id */
            revision_id: string;
            /** Round */
            round: number;
            /** Task Id */
            task_id: string;
        };
        /**
         * ReworkComparison
         * @description Compare rule findings only on preserved sample/annotator review identities.
         *
         *     Record counts compare sample/annotator records directly. Inspection counts
         *     cover units that an approved inspection of the original batch marked
         *     defective, and how many of those units have any changed record after rework.
         */
        ReworkComparison: {
            /**
             * Added Records
             * @default 0
             */
            added_records: number;
            /** After Count */
            after_count: number;
            /** Before Count */
            before_count: number;
            /**
             * Changed Records
             * @default 0
             */
            changed_records: number;
            /**
             * Corrected
             * @default []
             */
            corrected: components["schemas"]["AnnotationFinding"][];
            /** Corrected Count */
            corrected_count: number;
            /**
             * Inspection Defects
             * @default 0
             */
            inspection_defects: number;
            /**
             * Inspection Defects Changed
             * @default 0
             */
            inspection_defects_changed: number;
            /**
             * Introduced
             * @default []
             */
            introduced: components["schemas"]["AnnotationFinding"][];
            /** Introduced Count */
            introduced_count: number;
            /**
             * Remaining
             * @default []
             */
            remaining: components["schemas"]["AnnotationFinding"][];
            /** Remaining Count */
            remaining_count: number;
            /**
             * Removed Records
             * @default 0
             */
            removed_records: number;
            /**
             * Unassessed
             * @default []
             */
            unassessed: components["schemas"]["AnnotationFinding"][];
            /** Unassessed Count */
            unassessed_count: number;
            /**
             * Unchanged Records
             * @default 0
             */
            unchanged_records: number;
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
            /** Classifier Selection */
            classifier_selection?: string | null;
            /**
             * Classifier Used
             * @default false
             */
            classifier_used: boolean;
            inputs?: components["schemas"]["RouteInputs"];
            /** Reason */
            reason: string;
            /**
             * Requires Confirmation
             * @default false
             */
            requires_confirmation: boolean;
            /**
             * Score
             * @default 0
             */
            score: number;
            /** Verification Passed */
            verification_passed?: boolean | null;
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
        /**
         * RunCustomOperatorRequest
         * @description Select a dataset snapshot and parameters for one immutable custom operator.
         */
        RunCustomOperatorRequest: {
            /** Dataset Id */
            dataset_id: string;
            /** Name */
            name?: string | null;
            /** Params */
            params?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * SamplingInspection
         * @description Archive the approved inspection decision and complete error details.
         */
        SamplingInspection: {
            /** Acceptance Number */
            acceptance_number: number;
            /** Accepted */
            accepted: boolean;
            /** Action Plan Id */
            action_plan_id: string;
            /** Actor */
            actor: string;
            /** Batch Id */
            batch_id: string;
            /** Checks */
            checks: components["schemas"]["InspectionCheck"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Defective Count */
            defective_count: number;
            /** Id */
            id: string;
            /** Sampling Id */
            sampling_id: string;
            /** Version Id */
            version_id: string;
        };
        /**
         * SamplingPlan
         * @description Bind reproducible selected units and table lookup to an immutable batch digest.
         */
        SamplingPlan: {
            /** Acceptance Number */
            acceptance_number: number;
            /** Aql */
            aql?: number | null;
            /** Batch Digest */
            batch_digest: string;
            /** Batch Id */
            batch_id: string;
            /** Code Letter */
            code_letter?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Effective Code Letter */
            effective_code_letter?: string | null;
            /** Id */
            id: string;
            /** Lot Size */
            lot_size: number;
            /**
             * Method
             * @enum {string}
             */
            method: "aql" | "ratio";
            /** Ratio */
            ratio?: number | null;
            /** Rejection Number */
            rejection_number: number;
            /** Sample Ids */
            sample_ids: string[];
            /** Sample Size */
            sample_size: number;
            /** Seed */
            seed: number;
            /** Version Id */
            version_id: string;
        };
        /**
         * SamplingRequest
         * @description Choose normal single AQL inspection or a separately declared fixed fraction.
         */
        SamplingRequest: {
            /** Acceptance Number */
            acceptance_number?: number | null;
            /**
             * Aql
             * @default 2.5
             */
            aql: number;
            /** Batch Id */
            batch_id: string;
            /**
             * Method
             * @default aql
             * @enum {string}
             */
            method: "aql" | "ratio";
            /** Ratio */
            ratio?: number | null;
            /**
             * Seed
             * @default 0
             */
            seed: number;
        };
        Scalar: string | number | boolean | null;
        /**
         * SchemaExample
         * @description Demonstrate extraction using evidence copied from the example text.
         */
        SchemaExample: {
            /**
             * Entities
             * @default []
             */
            entities: components["schemas"]["ExtractedEntity"][];
            /**
             * Relations
             * @default []
             */
            relations: components["schemas"]["ExtractedRelation"][];
            /** Text */
            text: string;
        };
        /**
         * SchemaProposal
         * @description Count excluded claims without silently extending the active vocabulary.
         */
        SchemaProposal: {
            /** Count */
            count: number;
            /**
             * Entity Samples
             * @default []
             */
            entity_samples: components["schemas"]["ExtractedEntity"][];
            /**
             * Reason
             * @enum {string}
             */
            reason: "unknown_relation" | "domain_range" | "endpoint_ambiguous" | "unknown_entity_type";
            /** Samples */
            samples: components["schemas"]["ExtractedRelation"][];
        };
        /**
         * SearchResult
         * @description Expose stable object identity without private paths or connection metadata.
         */
        SearchResult: {
            /** Dataset Id */
            dataset_id?: string | null;
            /** English Name */
            english_name?: string | null;
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
        /** @enum {string} */
        Sensitivity: "public" | "internal" | "confidential" | "restricted";
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
         * SkippedEntries
         * @description Identify entries a list-style read left out because the caller lacks a grant.
         *
         *     Only entry and asset identifiers are reported, never the skipped content.
         */
        SkippedEntries: {
            /** Assets */
            assets: string[];
            /** Count */
            count: number;
            /** Ids */
            ids: string[];
            /** Reason */
            reason: string;
        };
        /**
         * SpanAgreement
         * @description Summarize exact and positive-overlap maximum-cardinality matching F1.
         */
        SpanAgreement: {
            /** Annotator A */
            annotator_a: string;
            /** Annotator B */
            annotator_b: string;
            /** Exact F1 */
            exact_f1: number | null;
            /** Exact Matches */
            exact_matches: number;
            /** Overlap F1 */
            overlap_f1: number | null;
            /** Overlap Matches */
            overlap_matches: number;
            /** Sample Count */
            sample_count: number;
            /** Span Count A */
            span_count_a: number;
            /** Span Count B */
            span_count_b: number;
        };
        /**
         * SplitComparison
         * @description Compare two immutable partition memberships from the same source version.
         */
        SplitComparison: {
            /** Changed Sample Ids */
            changed_sample_ids: string[];
            /** Left */
            left: components["schemas"]["SplitDistribution"][];
            /** Left Id */
            left_id: string;
            /** Right */
            right: components["schemas"]["SplitDistribution"][];
            /** Right Id */
            right_id: string;
        };
        /**
         * SplitDistribution
         * @description Report membership and multilabel category prevalence for one partition.
         */
        SplitDistribution: {
            /** Count */
            count: number;
            /**
             * Labels
             * @default []
             */
            labels: components["schemas"]["LabelCount"][];
            split: components["schemas"]["SplitName"];
        };
        /**
         * SplitMember
         * @description Freeze assignment, original content identity and annotation revision together.
         */
        SplitMember: {
            /**
             * Annotations
             * @default []
             */
            annotations: components["schemas"]["AnnotationRecord"][];
            /**
             * Labels
             * @default []
             */
            labels: string[];
            /** Sample Id */
            sample_id: string;
            /** Sha256 */
            sha256: string;
            split: components["schemas"]["SplitName"];
        };
        /** @enum {string} */
        SplitName: "train" | "val" | "test";
        /**
         * SplitRatios
         * @description Select two or three nonempty partitions with normalized finite proportions.
         */
        SplitRatios: {
            /**
             * Test
             * @default 0.1
             */
            test: number;
            /**
             * Train
             * @default 0.8
             */
            train: number;
            /**
             * Val
             * @default 0.1
             */
            val: number;
        };
        /**
         * SplitRequest
         * @description Freeze the complete versioned partition policy, including comparison thresholds.
         */
        SplitRequest: {
            /**
             * Avoid Leakage
             * @default true
             */
            avoid_leakage: boolean;
            /** Group Field */
            group_field?: string | null;
            /**
             * Image Threshold
             * @default 8
             */
            image_threshold: number;
            /** Name */
            name: string;
            ratios?: components["schemas"]["SplitRatios"];
            /**
             * Seed
             * @default 42
             */
            seed: number;
            /**
             * Source
             * @default generated
             * @enum {string}
             */
            source: "generated" | "directory";
            /**
             * Stratify
             * @description Use every label in iterative multilabel stratification.
             * @default true
             */
            stratify: boolean;
            /**
             * Text Threshold
             * @description Maximum 64-bit text simhash Hamming distance.
             * @default 3
             */
            text_threshold: number;
        };
        /**
         * SplitSet
         * @description Expose an immutable named partition belonging to exactly one source version.
         */
        SplitSet: {
            /**
             * Algorithm Version
             * @default 1.0
             */
            algorithm_version: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Distributions */
            distributions: components["schemas"]["SplitDistribution"][];
            /** Id */
            id: string;
            /** Members */
            members: components["schemas"]["SplitMember"][];
            request: components["schemas"]["SplitRequest"];
            /** Version Id */
            version_id: string;
        };
        /**
         * SqlFailure
         * @description Keep the SQL origin and actionable parsing reason in import statistics.
         */
        SqlFailure: {
            /** Origin */
            origin: string;
            /** Reason */
            reason: string;
        };
        /**
         * StandardDimension
         * @description Score the fraction of evaluated column rules that passed in one dimension.
         */
        StandardDimension: {
            /** Checked Rules */
            checked_rules: number;
            /** Failed Rules */
            failed_rules: number;
            /** Score */
            score: number | null;
            /** Violation Count */
            violation_count: number;
            /** Weight */
            weight: number;
        };
        /**
         * StandardQualityIssue
         * @description Locate a measured standards issue without copying source values.
         */
        StandardQualityIssue: {
            /** Column Id */
            column_id: string;
            /** Count */
            count: number;
            /** Dimension */
            dimension: string;
            /** Message */
            message: string;
            /** Rule */
            rule: string;
        };
        /** @enum {string} */
        StandardStatus: "draft" | "active" | "deprecated";
        StandardValue: components["schemas"]["Scalar"] | string;
        /**
         * StandardViolation
         * @description Count one failed constraint and expose only redacted representative values.
         */
        StandardViolation: {
            /** Count */
            count: number;
            /** Message */
            message: string;
            rule: components["schemas"]["ViolationRule"];
            /**
             * Samples
             * @default []
             */
            samples: string[];
        };
        /**
         * StandardsContract
         * @description Combine strict field and reference-data declarations in one YAML document.
         */
        StandardsContract: {
            /**
             * Code Lists
             * @default []
             */
            code_lists: components["schemas"]["CodeList"][];
            /**
             * Standards
             * @default []
             */
            standards: components["schemas"]["FieldStandard"][];
            /**
             * Synonyms
             * @default []
             */
            synonyms: components["schemas"]["BusinessSynonyms"][];
        };
        /**
         * StandardsCoverage
         * @description Expose global, database, table and owner coverage plus bounded violations.
         */
        StandardsCoverage: {
            overall: components["schemas"]["CoverageGroup"];
            /**
             * Owners
             * @default []
             */
            owners: components["schemas"]["CoverageGroup"][];
            /**
             * Sources
             * @default []
             */
            sources: components["schemas"]["CoverageGroup"][];
            /**
             * Tables
             * @default []
             */
            tables: components["schemas"]["CoverageGroup"][];
            /**
             * Violation Top
             * @default []
             */
            violation_top: components["schemas"]["ViolationSummary"][];
        };
        /** @enum {string} */
        StandardsGrade: "unmeasured" | "excellent" | "good" | "fair" | "poor";
        /**
         * StandardsHistory
         * @description Expose every committed standards revision in ascending order.
         */
        StandardsHistory: {
            /** Revisions */
            revisions: components["schemas"]["StandardsRevision"][];
        };
        /**
         * StandardsQuality
         * @description Keep column quality distinct from the existing file-manifest quality contract.
         */
        StandardsQuality: {
            /** Column Count */
            column_count: number;
            /** Dimensions */
            dimensions: {
                [key: string]: components["schemas"]["StandardDimension"];
            };
            /** Fully Checked Columns */
            fully_checked_columns: number;
            grade: components["schemas"]["StandardsGrade"];
            /** Issues */
            issues: components["schemas"]["StandardQualityIssue"][];
            /** Mapped Columns */
            mapped_columns: number;
            /** Skipped Rules */
            skipped_rules: number;
            /** Total */
            total: number | null;
        };
        /**
         * StandardsReport
         * @description Combine metadata, confirmed associations, checks and coverage without raw values.
         */
        StandardsReport: {
            /** Checks */
            checks: components["schemas"]["ColumnCheck"][];
            coverage: components["schemas"]["StandardsCoverage"];
            /** Mappings */
            mappings: components["schemas"]["ColumnMapping"][];
            /** Profiles */
            profiles: components["schemas"]["ColumnProfile"][];
        };
        /**
         * StandardsRevision
         * @description Attribute one immutable state transition to its controlled action.
         */
        StandardsRevision: {
            /** Action Type */
            action_type: string;
            /** Actor */
            actor: string;
            contract?: components["schemas"]["StandardsContract"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Event Id */
            event_id: string;
            /**
             * Mappings
             * @default []
             */
            mappings: components["schemas"]["ColumnMapping"][];
            /** Plan Id */
            plan_id: string;
            /**
             * Revision
             * @default 0
             */
            revision: number;
        };
        /**
         * StateCount
         * @description Expose one incrementally maintained state counter.
         */
        StateCount: {
            /**
             * Count
             * @default 0
             */
            count: number;
            /**
             * State
             * @enum {string}
             */
            state: "pending" | "in_progress" | "submitted" | "in_review" | "approved" | "finalized";
        };
        /**
         * StaticCheck
         * @description Display advisory source findings without treating them as containment.
         */
        StaticCheck: {
            /** Code */
            code: string;
            /** Column */
            column: number;
            /** Line */
            line: number;
            /** Message */
            message: string;
        };
        /**
         * TabularAssessment
         * @description Carry all profiled file evidence between scoring and report assembly.
         */
        TabularAssessment: {
            /**
             * Files
             * @default []
             */
            files: components["schemas"]["TabularFileAssessment"][];
            /** Scores */
            scores: {
                [key: string]: number;
            };
        };
        /**
         * TabularFileAssessment
         * @description Expose deterministic per-file scores and report aggregates.
         */
        TabularFileAssessment: {
            /**
             * Anomaly Intervals
             * @default 0
             */
            anomaly_intervals: number;
            /**
             * Columns
             * @default []
             */
            columns: components["schemas"]["ProfileColumnBrief"][];
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /**
             * Findings
             * @default []
             */
            findings: components["schemas"]["TabularFinding"][];
            /** Row Count */
            row_count: number;
            /** Scores */
            scores: {
                [key: string]: number;
            };
            /**
             * Total Gap Ms
             * @default 0
             */
            total_gap_ms: number;
        };
        /**
         * TabularFinding
         * @description Retain a precise recorded reason without retaining sensitive source cell values.
         */
        TabularFinding: {
            /** Column */
            column: string;
            /** Detail */
            detail: string;
            /**
             * Device
             * @default
             */
            device: string;
            /**
             * Dimension
             * @enum {string}
             */
            dimension: "completeness" | "consistency" | "uniqueness" | "distribution";
            /** End Ms */
            end_ms?: number | null;
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /** Recommendation */
            recommendation: string;
            /**
             * Rows
             * @default []
             */
            rows: number[];
            /** Rule */
            rule: string;
            /** Start Ms */
            start_ms?: number | null;
            /** Threshold */
            threshold?: number | null;
            /**
             * Window
             * @default 1
             */
            window: number;
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
         * TaskPackage
         * @description Describe a reproducible partition whose status comes from task counters.
         */
        TaskPackage: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Project Id */
            project_id: string;
            /**
             * Split Rule
             * @default count
             */
            split_rule: string;
            /** Task Count */
            task_count: number;
        };
        /**
         * TaskView
         * @description Persisted task state and derived completion progress.
         *
         *     ``failed_files`` lists recordings published with a processing failure, and
         *     ``partial`` marks a completed task whose output includes such failures.
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
            /** Failed Files */
            failed_files?: components["schemas"]["MediaFailure"][];
            /** Finished At */
            finished_at: number | null;
            /** Id */
            id: string;
            /** Input Version Id */
            input_version_id: string | null;
            /**
             * Partial
             * @default false
             */
            partial: boolean;
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
         * TrainingAnalysisRequest
         * @description Analyze selected uploaded JSONL files with a completely frozen rule configuration.
         */
        TrainingAnalysisRequest: {
            config?: components["schemas"]["TrainingConfig"];
            /**
             * Evaluation Ids
             * @default []
             */
            evaluation_ids: string[];
            /**
             * File Ids
             * @default []
             */
            file_ids: string[];
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * TrainingAnnotationImport
         * @description Import portable detections or lossless core records into immutable annotation history.
         */
        TrainingAnnotationImport: {
            /** Annotations Jsonl */
            annotations_jsonl?: string | null;
            /**
             * Annotator Id
             * @default training
             */
            annotator_id: string;
            coco?: components["schemas"]["CocoDataset"] | null;
            /**
             * Format
             * @enum {string}
             */
            format: "coco" | "yolo" | "annotations_jsonl";
            /** Idempotency Key */
            idempotency_key: string;
            /**
             * Name
             * @default Training annotations
             */
            name: string;
            /** Sample Ids */
            sample_ids?: {
                [key: string]: string;
            };
            yolo?: components["schemas"]["YoloDataset"] | null;
        };
        /**
         * TrainingConfig
         * @description Freeze all rule thresholds so a dry run can be reproduced exactly.
         */
        TrainingConfig: {
            /**
             * Contamination Ngram
             * @default 13
             */
            contamination_ngram: number;
            /**
             * Contamination Threshold
             * @default 0.2
             */
            contamination_threshold: number;
            /**
             * Format
             * @default auto
             * @enum {string}
             */
            format: "auto" | "messages" | "instruction" | "preference";
            /**
             * Max Line Bytes
             * @default 1048576
             */
            max_line_bytes: number;
            /**
             * Max Tokens
             * @default 8192
             */
            max_tokens: number;
            /**
             * Near Distance
             * @default 8
             */
            near_distance: number;
            /**
             * Near Similarity
             * @default 0.9
             */
            near_similarity: number;
            /**
             * Refusal Phrases
             * @default [
             *       "as an ai language model",
             *       "as an artificial intelligence",
             *       "i cannot assist with",
             *       "作为一个ai",
             *       "作为人工智能",
             *       "作为一个人工智能",
             *       "我无法协助"
             *     ]
             */
            refusal_phrases: string[];
            /**
             * Repetition Threshold
             * @default 0.45
             */
            repetition_threshold: number;
            /**
             * Sample Limit
             * @default 50
             */
            sample_limit: number;
        };
        /**
         * TrainingEvaluation
         * @description Identify an immutable user-registered evaluation snapshot.
         */
        TrainingEvaluation: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** File Ids */
            file_ids: string[];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Source Dataset Id */
            source_dataset_id: string;
            /** Version Id */
            version_id: string;
        };
        /**
         * TrainingEvaluationRequest
         * @description Register evaluation files from an existing uploaded dataset, never an arbitrary path.
         */
        TrainingEvaluationRequest: {
            /** File Ids */
            file_ids: string[];
            /** Name */
            name: string;
            /** Source Dataset Id */
            source_dataset_id: string;
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * TrainingFileSummary
         * @description Aggregate one source without retaining every parsed record in memory.
         */
        TrainingFileSummary: {
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /** Issue Counts */
            issue_counts?: {
                [key: string]: number;
            };
            /** Records */
            records: number;
            /** Valid Records */
            valid_records: number;
        };
        /**
         * TrainingGovernanceRun
         * @description Present bounded redacted findings and the complete decision-ledger fingerprint.
         */
        TrainingGovernanceRun: {
            /** Cleaned Version Id */
            cleaned_version_id?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Dataset Id */
            dataset_id: string;
            /** Id */
            id: string;
            /** Ledger Sha256 */
            ledger_sha256: string;
            report: components["schemas"]["TrainingReport"];
            /** Version Id */
            version_id: string;
        };
        /**
         * TrainingIssue
         * @description Locate a measured rule signal; evidence is always redacted for presentation.
         */
        TrainingIssue: {
            /** Code */
            code: string;
            /** End */
            end?: number | null;
            /**
             * Evidence
             * @default
             */
            evidence: string;
            /**
             * Field
             * @default record
             */
            field: string;
            /** Message */
            message: string;
            /** Related Id */
            related_id?: string | null;
            /** Start */
            start?: number | null;
        };
        /**
         * TrainingRecord
         * @description Carry a bounded, redacted record preview and its stable source identity.
         */
        TrainingRecord: {
            /** Content Hash */
            content_hash: string;
            /**
             * Decision
             * @default keep
             * @enum {string}
             */
            decision: "keep" | "drop" | "redact";
            /**
             * Estimated Tokens
             * @default 0
             */
            estimated_tokens: number;
            /** File Id */
            file_id: string;
            /**
             * Format
             * @enum {string}
             */
            format: "auto" | "messages" | "instruction" | "preference";
            /** Id */
            id: string;
            /**
             * Issues
             * @default []
             */
            issues: components["schemas"]["TrainingIssue"][];
            /**
             * Language
             * @default unknown
             * @enum {string}
             */
            language: "zh" | "en" | "mixed" | "unknown";
            /**
             * Language Confidence
             * @default 0
             */
            language_confidence: number;
            /** Line */
            line: number;
            /**
             * Preview
             * @default
             */
            preview: string;
            /**
             * Reasons
             * @default []
             */
            reasons: string[];
        };
        /**
         * TrainingReport
         * @description Expose deterministic counts and bounded samples; the full ledger stays on disk.
         */
        TrainingReport: {
            /**
             * Chosen Longer Ratio
             * @default 0
             */
            chosen_longer_ratio: number;
            config: components["schemas"]["TrainingConfig"];
            /**
             * Contamination Hits
             * @default []
             */
            contamination_hits: components["schemas"]["TrainingIssue"][];
            /**
             * Dedup Backend
             * @default python
             */
            dedup_backend: string;
            /**
             * Dropped
             * @default 0
             */
            dropped: number;
            /**
             * Duplicate Clusters
             * @default []
             */
            duplicate_clusters: string[][];
            /** Evaluation Sha256 */
            evaluation_sha256?: {
                [key: string]: string;
            };
            /**
             * Files
             * @default []
             */
            files: components["schemas"]["TrainingFileSummary"][];
            /** Formats */
            formats?: {
                [key: string]: number;
            };
            /** Issue Counts */
            issue_counts?: {
                [key: string]: number;
            };
            /**
             * Kept
             * @default 0
             */
            kept: number;
            /** Languages */
            languages?: {
                [key: string]: number;
            };
            /**
             * Ledger Sha256
             * @default
             */
            ledger_sha256: string;
            /**
             * Pii Records
             * @default 0
             */
            pii_records: number;
            /**
             * Preference Records
             * @default 0
             */
            preference_records: number;
            /**
             * Records
             * @default 0
             */
            records: number;
            /**
             * Redacted
             * @default 0
             */
            redacted: number;
            /**
             * Rule Version
             * @default 1.0
             */
            rule_version: string;
            /**
             * Samples
             * @default []
             */
            samples: components["schemas"]["TrainingRecord"][];
            /** Source Sha256 */
            source_sha256?: {
                [key: string]: string;
            };
            /**
             * Valid Records
             * @default 0
             */
            valid_records: number;
        };
        /**
         * TranscriptionEstimate
         * @description Show the image transfer envelope independently from downstream extraction.
         */
        TranscriptionEstimate: {
            /**
             * Auto Images
             * @default 0
             */
            auto_images: number;
            /** Cost Upper Usd */
            cost_upper_usd?: string | null;
            /** Image Tokens */
            image_tokens: number;
            /** Images */
            images: number;
            /** Max Output Tokens */
            max_output_tokens: number;
            /** Model */
            model: string;
            /**
             * Possible External Images
             * @default []
             */
            possible_external_images: components["schemas"]["ImageTransfer"][];
            price?: components["schemas"]["ModelPrice"] | null;
            /** Price Version */
            price_version?: string | null;
            /** Target Host */
            target_host: string | null;
        };
        /**
         * TranscriptionObservation
         * @description Expose one selected route, cache outcome and explicit quality failure per image.
         */
        TranscriptionObservation: {
            /** Backend */
            backend: string;
            /**
             * Cached
             * @default false
             */
            cached: boolean;
            /** Error */
            error?: string | null;
            /**
             * External
             * @default false
             */
            external: boolean;
            /** File Id */
            file_id: string;
            /** Filename */
            filename: string;
            /**
             * Ignored Field Count
             * @default 0
             */
            ignored_field_count: number;
            /**
             * Mode
             * @enum {string}
             */
            mode: "ocr" | "vlm" | "auto";
            /** Model */
            model: string;
            ocr_reference?: components["schemas"]["OCRReference"] | null;
            /**
             * Quality Issues
             * @default []
             */
            quality_issues: ("empty" | "truncated" | "repeated" | "timeout" | "provider_error" | "provider_quota_exhausted" | "recording_missing" | "ocr_not_installed" | "api_key_missing" | "mode_mismatch" | "image_decode_error" | "outbound_not_approved" | "coordinates_unreliable" | "unparseable_structured_output")[];
            /**
             * Reasons
             * @default []
             */
            reasons: ("low_confidence" | "structure_diagram" | "struck_or_greyed_rows" | "sparse_text" | "ocr_failed" | "clean_text")[];
            /**
             * Status
             * @default completed
             * @enum {string}
             */
            status: "completed" | "failed" | "unexecuted";
        };
        /**
         * TranscriptionProfile
         * @description Select a backend without embedding credentials or unrestricted request options.
         */
        TranscriptionProfile: {
            /** Api Key Env */
            api_key_env?: string | null;
            auto_routing?: components["schemas"]["AutoRoutingConfig"];
            /**
             * Backend
             * @enum {string}
             */
            backend: "ocr" | "vlm" | "replay" | "fake";
            /** Base Url */
            base_url?: string | null;
            /**
             * Coordinate Min Median Iou
             * @default 0.3
             */
            coordinate_min_median_iou: number;
            /**
             * Coordinate Space
             * @default pixel
             * @enum {string}
             */
            coordinate_space: "pixel" | "normalized_1000" | "normalized_1";
            /** Id */
            id: string;
            /**
             * Interface
             * @default openai
             * @enum {string}
             */
            interface: "openai" | "ollama";
            /**
             * Max Output Tokens
             * @default 4096
             */
            max_output_tokens: number;
            /**
             * Mode
             * @default ocr
             * @enum {string}
             */
            mode: "ocr" | "vlm" | "auto";
            /** Model */
            model: string;
            /**
             * Ocr Model Version
             * @default rapidocr-3.10.0-defaults
             */
            ocr_model_version: string;
            /**
             * Prompt Version
             * @default image-transcription-v1
             * @enum {string}
             */
            prompt_version: "image-transcription-v1" | "image-transcription-v2";
            /** Recording */
            recording?: string | null;
            /** Request Parameters */
            request_parameters?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /**
             * Timeout Seconds
             * @default 120
             */
            timeout_seconds: number;
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
        /**
         * UploadInput
         * @description Declare one file's immutable identity before sending bounded chunks.
         */
        UploadInput: {
            /** Chunk Bytes */
            chunk_bytes: number;
            /** Filename */
            filename: string;
            /** Idempotency Key */
            idempotency_key: string;
            /** Metadata */
            metadata?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Name */
            name: string;
            /** Sha256 */
            sha256: string;
            /** Total Bytes */
            total_bytes: number;
        };
        /**
         * UploadView
         * @description Expose durable progress without physical paths or uploaded data.
         */
        UploadView: {
            /** Chunk Bytes */
            chunk_bytes: number;
            /** Chunk Count */
            chunk_count: number;
            /** Dataset Id */
            dataset_id?: string | null;
            /** Filename */
            filename: string;
            /** Id */
            id: string;
            /** Missing Chunks */
            missing_chunks: number[];
            /** Received Chunks */
            received_chunks: number[];
            /** Sha256 */
            sha256: string;
            /**
             * State
             * @enum {string}
             */
            state: "UPLOADING" | "COMPLETE";
            /** Total Bytes */
            total_bytes: number;
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
         * VerificationDetail
         * @description Keep independently checked evidence and endpoint locations structured.
         */
        VerificationDetail: {
            evidence?: components["schemas"]["TextSpan"] | null;
            head?: components["schemas"]["TextSpan"] | null;
            /**
             * Issues
             * @default []
             */
            issues: components["schemas"]["VerificationIssue"][];
            /**
             * Locations
             * @default []
             */
            locations: components["schemas"]["VerificationLocation"][];
            tail?: components["schemas"]["TextSpan"] | null;
        };
        /**
         * VerificationIssue
         * @description Identify the exact source check that needs human review.
         */
        VerificationIssue: {
            /**
             * Code
             * @enum {string}
             */
            code: "evidence" | "head" | "tail" | "endpoint_undeclared" | "image_unlocated" | "handwriting_name";
            /** Role */
            role?: ("head" | "tail") | null;
        };
        /**
         * VerificationLocation
         * @description Retain document-specific endpoint checks when cross-block claims are merged.
         */
        VerificationLocation: {
            evidence?: components["schemas"]["TextSpan"] | null;
            head?: components["schemas"]["TextSpan"] | null;
            /**
             * Issues
             * @default []
             */
            issues: components["schemas"]["VerificationIssue"][];
            source: components["schemas"]["AssetRef"];
            tail?: components["schemas"]["TextSpan"] | null;
        };
        /**
         * VersionDiff
         * @description A bounded page of comparisons with whole-version measurement summaries.
         */
        VersionDiff: {
            after_summary: components["schemas"]["VersionSummary"];
            /** After Version */
            after_version: string;
            before_summary: components["schemas"]["VersionSummary"];
            /** Before Version */
            before_version: string;
            counts: components["schemas"]["DiffCounts"];
            /** Dataset Id */
            dataset_id: string;
            /** Files */
            files: components["schemas"]["DiffFile"][];
            /** Next Offset */
            next_offset?: number | null;
        };
        /**
         * VersionSummary
         * @description Observed annotations, mean file quality, and version-scoped review states.
         */
        VersionSummary: {
            /**
             * Annotation Count
             * @default 0
             */
            annotation_count: number;
            /** Evidence Decisions */
            evidence_decisions?: {
                [key: string]: number;
            };
            /**
             * Label Count
             * @default 0
             */
            label_count: number;
            /**
             * Quality Basis
             * @default mean_file_quality
             * @constant
             */
            quality_basis: "mean_file_quality";
            /**
             * Quality Score
             * @default 0
             */
            quality_score: number;
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
        /** @enum {string} */
        ViolationRule: "type" | "length" | "precision" | "code_list" | "range" | "pattern" | "required" | "unit" | "sensitivity";
        /**
         * ViolationSummary
         * @description Rank columns by observed violations without including raw sample values.
         */
        ViolationSummary: {
            /** Column Id */
            column_id: string;
            /** Rules */
            rules: components["schemas"]["ViolationRule"][];
            /** Standard Code */
            standard_code: string;
            /** Violation Count */
            violation_count: number;
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
         * WorkbenchIndex
         * @description List only readable projects and the caller's actual global server identity.
         */
        WorkbenchIndex: {
            /** Actor */
            actor: string;
            effective_scopes: components["schemas"]["EffectiveScopes"];
            /** Projects */
            projects: components["schemas"]["Project"][];
            /** Zero Users */
            zero_users: boolean;
        };
        /**
         * WorkbenchProject
         * @description Reuse production facts and measurements for role-specific workbench pages.
         */
        WorkbenchProject: {
            agreement: components["schemas"]["AnnotationQAResult"];
            confidence: components["schemas"]["ConfidenceDistribution"];
            effective_scopes: components["schemas"]["EffectiveScopes"];
            label_set: components["schemas"]["LabelSet"];
            /** Next Cursor */
            next_cursor?: string | null;
            /** Packages */
            packages: components["schemas"]["TaskPackage"][];
            prelabel_accuracy: components["schemas"]["PrelabelAccuracy"];
            progress: components["schemas"]["ProductionProgress"];
            project: components["schemas"]["Project"];
            /**
             * Task Risks
             * @default []
             */
            task_risks: components["schemas"]["WorkbenchTaskRisk"][];
            /** Tasks */
            tasks: components["schemas"]["ProductionTask"][];
            template: components["schemas"]["ProductionTemplate"] | null;
            workload: components["schemas"]["ProductionWorkload"];
        };
        /**
         * WorkbenchSample
         * @description Expose source content without returning a private path or object-store key.
         */
        WorkbenchSample: {
            /** Content Url */
            content_url: string;
            /** Id */
            id: string;
            /** Image Height */
            image_height?: number | null;
            /** Image Width */
            image_width?: number | null;
            /** Media Type */
            media_type: string;
            /** Name */
            name: string;
            /** Text */
            text?: string | null;
            /** Thumbnail Url */
            thumbnail_url?: string | null;
        };
        /**
         * WorkbenchTask
         * @description Return one sample and its exact append-only revision and review histories.
         */
        WorkbenchTask: {
            /** Assignments */
            assignments: components["schemas"]["Assignment"][];
            /** Reviews */
            reviews: components["schemas"]["Review"][];
            /** Revisions */
            revisions: components["schemas"]["AnnotationRevision"][];
            sample: components["schemas"]["WorkbenchSample"];
            task: components["schemas"]["ProductionTask"];
        };
        /**
         * WorkbenchTaskRisk
         * @description Measure the current human annotation's content difference from its latest model draft.
         */
        WorkbenchTaskRisk: {
            /** Model Confidence */
            model_confidence?: number | null;
            /** Prelabel Difference */
            prelabel_difference?: number | null;
            /** Task Id */
            task_id: string;
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
         * WorkflowConcepts
         * @description Declare a workflow's objects, requesting verbs and required follow-ups, with paraphrases.
         *
         *     ``outcomes`` lists what a request must also ask for when the workflow bundles more than
         *     one action, so that a request for the first action alone stays a single step.
         *     ``exclusions`` lists wording that puts a request outside the workflow (for example one
         *     selected item for a bulk cleanup); it blocks selection and verification but keeps the
         *     rule score, so the classifier is still consulted and can abstain.
         */
        WorkflowConcepts: {
            /** Actions */
            actions?: string[];
            /** Entities */
            entities?: string[];
            /** Exclusions */
            exclusions?: string[];
            /** Outcomes */
            outcomes?: string[];
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
            /** Classification Groups */
            classification_groups?: string[][];
            /** Classification Keywords */
            classification_keywords?: string[];
            concepts?: components["schemas"]["WorkflowConcepts"] | null;
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
            /** Verification Keywords */
            verification_keywords?: string[];
        };
        /**
         * YoloDataset
         * @description Provide zero-indexed category names and one label text per source image.
         */
        YoloDataset: {
            /** Images */
            images: components["schemas"]["YoloImage"][];
            /** Names */
            names: string[];
        };
        /**
         * YoloImage
         * @description Carry normalized YOLO text together with the dimensions needed to restore pixels.
         */
        YoloImage: {
            /** Height */
            height: number;
            /** Labels */
            labels: string;
            /** Sample Id */
            sample_id: string;
            /** Width */
            width: number;
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
            query?: {
                max_objects?: number | null;
                max_bytes?: number | null;
            };
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
    download_export_api_actions__plan_id__export_get: {
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
    list_conversations_api_ask_conversations_get: {
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
                    "application/json": components["schemas"]["AskConversation"][];
                };
            };
        };
    };
    create_conversation_api_ask_conversations_post: {
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
                    "application/json": components["schemas"]["AskConversation"];
                };
            };
        };
    };
    open_conversation_api_ask_conversations__conversation_id__get: {
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
                    "application/json": components["schemas"]["AskConversation"];
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
    delete_conversation_api_ask_conversations__conversation_id__delete: {
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
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    airflow_api_catalog_import_airflow_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AirflowImportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetadataImportReport"];
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
    dbt_api_catalog_import_dbt_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DbtImportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MetadataImportReport"];
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
    objects_api_catalog_import_objects_get: {
        parameters: {
            query?: {
                kind?: ("source" | "table" | "column" | "dag" | "airflow_task" | "exposure" | "metric_draft" | "job") | null;
                source_id?: string | null;
                offset?: number;
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
    versions_api_custom_operators_get: {
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
                    "application/json": components["schemas"]["CustomOperatorVersion"][];
                };
            };
        };
    };
    submit_api_custom_operators_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CustomOperatorSubmission"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
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
    configuration_api_custom_operators_configuration_get: {
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
                    "application/json": components["schemas"]["CustomOperatorConfiguration"];
                };
            };
        };
    };
    runs_api_custom_operators_runs_get: {
        parameters: {
            query?: {
                code_hash?: string | null;
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
                    "application/json": components["schemas"]["CustomOperatorRun"][];
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
    submissions_api_custom_operators_submissions_get: {
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
    version_api_custom_operators__code_hash__get: {
        parameters: {
            query?: {
                name?: string | null;
            };
            header?: never;
            path: {
                code_hash: string;
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
                    "application/json": components["schemas"]["CustomOperatorVersion"];
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
    run_api_custom_operators__code_hash__runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                code_hash: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunCustomOperatorRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
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
    market_api_data_assets_get: {
        parameters: {
            query?: {
                search?: string;
                classification?: components["schemas"]["AssetClassification"] | null;
                tag?: string | null;
                status?: components["schemas"]["AssetStatus"] | null;
                sort?: components["schemas"]["AssetSort"];
                offset?: number;
                limit?: number;
                include_unpublished?: boolean;
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
                    "application/json": components["schemas"]["AssetMarketPage"];
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
    applications_api_data_assets_applications_get: {
        parameters: {
            query?: {
                asset_id?: string | null;
                applicant?: string | null;
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
                    "application/json": components["schemas"]["AssetApplication"][];
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
    application_api_data_assets_applications__application_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                application_id: string;
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
                    "application/json": components["schemas"]["AssetApplication"];
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
    audit_api_data_assets_audit_get: {
        parameters: {
            query?: {
                asset_id?: string | null;
                actor?: string | null;
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
                    "application/json": components["schemas"]["AssetUsage"][];
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
    grants_api_data_assets_grants_get: {
        parameters: {
            query?: {
                asset_id?: string | null;
                subject?: string | null;
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
                    "application/json": components["schemas"]["AssetGrant"][];
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
    grant_api_data_assets_grants__grant_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                grant_id: string;
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
                    "application/json": components["schemas"]["AssetGrant"];
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
    card_api_data_assets__asset_id__get: {
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
                    "application/json": components["schemas"]["DataAssetCard"];
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
    asset_applications_api_data_assets__asset_id__applications_get: {
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
                    "application/json": components["schemas"]["AssetApplication"][];
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
    apply_api_data_assets__asset_id__applications_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssetApplicationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssetApplication"];
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
    controls_api_data_assets__asset_id__control_history_get: {
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
                    "application/json": components["schemas"]["AssetControlEvent"][];
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
    history_api_data_assets__asset_id__history_get: {
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
                    "application/json": components["schemas"]["AssetHistory"][];
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
    overview_api_datasets__dataset_id__annotation_quality_get: {
        parameters: {
            query?: {
                version_id?: string | null;
            };
            header?: never;
            path: {
                dataset_id: string;
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
                    "application/json": components["schemas"]["AnnotationQualityOverview"];
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
    prepare_acceptance_api_datasets__dataset_id__annotation_quality_acceptance_prepare_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnotationAcceptanceParams"];
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
    import_batch_api_datasets__dataset_id__annotation_quality_batches_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnotationImportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnotationQualityReport"];
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
    rework_export_api_datasets__dataset_id__annotation_quality_rework__batch_id__get: {
        parameters: {
            query?: {
                format?: "json" | "csv";
            };
            header?: never;
            path: {
                dataset_id: string;
                batch_id: string;
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
                    "text/csv": unknown;
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
    sample_api_datasets__dataset_id__annotation_quality_samples_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SamplingRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SamplingPlan"];
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
    documents_api_datasets__dataset_id__datasheets_get: {
        parameters: {
            query?: {
                version_id?: string | null;
            };
            header?: never;
            path: {
                dataset_id: string;
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
                    "application/json": components["schemas"]["DatasheetDocument"][];
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
    generate_api_datasets__dataset_id__datasheets_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateDatasheetRequest"];
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
    reports_api_datasets__dataset_id__text_governance_get: {
        parameters: {
            query?: {
                version_id?: string | null;
            };
            header?: never;
            path: {
                dataset_id: string;
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
                    "application/json": components["schemas"]["TrainingGovernanceRun"][];
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
    analyze_api_datasets__dataset_id__text_governance_analyze_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TrainingAnalysisRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TrainingGovernanceRun"];
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
    evaluations_api_datasets__dataset_id__text_governance_evaluations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
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
                    "application/json": components["schemas"]["TrainingEvaluation"][];
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
    register_api_datasets__dataset_id__text_governance_evaluations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TrainingEvaluationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TrainingEvaluation"];
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
    version_diff_api_datasets__identifier__diff_get: {
        parameters: {
            query: {
                before: string;
                after: string;
                offset?: number;
                limit?: number;
                category?: ("added" | "removed" | "content_changed" | "metadata_changed" | "unchanged") | null;
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
                    "application/json": components["schemas"]["VersionDiff"];
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
                offset?: number;
                limit?: number | null;
                q?: string;
                modality?: string | null;
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
    pointcloud_preview_api_datasets__identifier__files__file_id__pointcloud_preview_get: {
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
                    "image/png": string;
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
    releases_api_datasets__identifier__releases_get: {
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
                    "application/json": components["schemas"]["ReleaseView"][];
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
    comparison_api_datasets__identifier__versions__version_id__training_compare_get: {
        parameters: {
            query: {
                left: string;
                right: string;
            };
            header?: never;
            path: {
                identifier: string;
                version_id: string;
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
                    "application/json": components["schemas"]["SplitComparison"];
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
    import_annotations_api_datasets__identifier__versions__version_id__training_import_annotations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TrainingAnnotationImport"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnotationQualityReport"];
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
    preview_report_api_datasets__identifier__versions__version_id__training_leakage_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SplitRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeakageReport"];
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
    preview_api_datasets__identifier__versions__version_id__training_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SplitRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SplitSet"];
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
    splits_api_datasets__identifier__versions__version_id__training_splits_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                version_id: string;
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
                    "application/json": components["schemas"]["SplitSet"][];
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
    generate_split_api_datasets__identifier__versions__version_id__training_splits_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SplitRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SplitSet"];
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
    split_detail_api_datasets__identifier__versions__version_id__training_splits__split_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                version_id: string;
                split_id: string;
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
                    "application/json": components["schemas"]["SplitSet"];
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
    leakage_api_datasets__identifier__versions__version_id__training_splits__split_id__leakage_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                version_id: string;
                split_id: string;
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
                    "application/json": components["schemas"]["LeakageReport"];
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
    job_api_datasheets_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
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
                    "application/json": components["schemas"]["DatasheetJob"];
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
    compare_api_datasheets__before_id__compare__after_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                before_id: string;
                after_id: string;
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
                    "application/json": components["schemas"]["DatasheetComparison"];
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
    document_api_datasheets__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
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
                    "application/json": components["schemas"]["DatasheetDocument"];
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
    download_api_datasheets__document_id__download_get: {
        parameters: {
            query?: {
                format?: "markdown" | "html";
            };
            header?: never;
            path: {
                document_id: string;
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
                    "text/html": unknown;
                    "text/markdown": unknown;
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
    publish_api_datasheets__document_id__publish_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
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
    associations_api_kg_entities__entity_id__links_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entity_id: string;
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
                    "application/json": components["schemas"]["EntityLink"][];
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
    evaluations_api_kg_evaluations_get: {
        parameters: {
            query?: {
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
                    "application/json": components["schemas"]["KGEvalReport"][];
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
    graph_api_kg_graph_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KGQuery"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KGGraph"];
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
    image_content_api_kg_images__file_id__get: {
        parameters: {
            query: {
                version_id: string;
                extraction_id: string;
            };
            header?: never;
            path: {
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
                    "image/png": string;
                };
            };
            /** @description Image or extraction run not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid image request or image revision */
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
    links_api_kg_links_get: {
        parameters: {
            query?: {
                dataset_id?: string | null;
                status?: ("candidate" | "accepted" | "rejected") | null;
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
                    "application/json": components["schemas"]["EntityLink"][];
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
    rerun_links_api_kg_links_rerun_post: {
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
                    "application/json": components["schemas"]["LinkRunResult"];
                };
            };
        };
    };
    profiles_api_kg_profiles_get: {
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
                    "application/json": components["schemas"]["ExtractionProfile"][];
                };
            };
        };
    };
    query_api_kg_query_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KGQuery"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KGQueryResult"];
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
    relation_api_kg_relations__assertion_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                assertion_id: string;
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
                    "application/json": components["schemas"]["KGRelationExplanation"];
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
    runs_api_kg_runs_get: {
        parameters: {
            query?: {
                dataset_id?: string | null;
                version_id?: string | null;
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
                    "application/json": components["schemas"]["KGRun"][];
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
    traces_api_kg_runs__extraction_id__traces_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                extraction_id: string;
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
    schemas_api_kg_schemas_get: {
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
                    "application/json": components["schemas"]["KGSchema"][];
                };
            };
        };
    };
    source_api_kg_sources__file_id__get: {
        parameters: {
            query: {
                version_id: string;
                extraction_id?: string | null;
            };
            header?: never;
            path: {
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
                    "application/json": components["schemas"]["KGSourceText"];
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
    list_transcription_profiles_api_kg_transcription_profiles_get: {
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
                    "application/json": components["schemas"]["TranscriptionProfile"][];
                };
            };
        };
    };
    select_transcription_api_kg_transcription_selection_get: {
        parameters: {
            query: {
                dataset_id: string;
                version_id: string;
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
                    "application/json": components["schemas"]["KGTranscriptionSelection"];
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
    ingest_api_openlineage_events_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpenLineageRunEvent"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpenLineageReceipt"];
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
    read_function_api_production_functions__name__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
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
                    "application/json": components["schemas"]["FunctionResult"];
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
    objects_api_production_objects__kind__get: {
        parameters: {
            query?: {
                object_id?: string | null;
                project_id?: string | null;
                task_id?: string | null;
                version?: number | null;
                limit?: number;
            };
            header?: never;
            path: {
                kind: "user" | "team" | "role" | "skill" | "label_set" | "template" | "project" | "task_package" | "production_task" | "assignment" | "annotation_revision" | "review" | "model" | "prelabel_run";
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
                    "application/json": components["schemas"]["FunctionResult"];
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
    project_workbench_api_production_projects__project_id__workbench_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                view?: "all" | "mine" | "review";
                package_id?: string | null;
            };
            header?: never;
            path: {
                project_id: string;
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
                    "application/json": components["schemas"]["WorkbenchProject"];
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
    task_content_api_production_tasks__task_id__content_get: {
        parameters: {
            query?: {
                thumbnail?: boolean;
            };
            header?: never;
            path: {
                task_id: string;
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
    task_workbench_api_production_tasks__task_id__workbench_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
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
                    "application/json": components["schemas"]["WorkbenchTask"];
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
    workbench_api_production_workbench_get: {
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
                    "application/json": components["schemas"]["WorkbenchIndex"];
                };
            };
        };
    };
    issues_api_quality_issues_get: {
        parameters: {
            query?: {
                rule_id?: string | null;
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
                    "application/json": components["schemas"]["DqIssue"][];
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
    report_api_quality_report_get: {
        parameters: {
            query?: {
                source_id?: string | null;
                table?: string | null;
                schema_name?: string | null;
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
                    "application/json": components["schemas"]["DqReport"];
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
    rules_api_quality_rules_get: {
        parameters: {
            query?: {
                source_id?: string | null;
                table?: string | null;
                schema_name?: string | null;
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
                    "application/json": components["schemas"]["DqRuleView"][];
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
    rule_api_quality_rules__rule_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
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
                    "application/json": components["schemas"]["DqRuleView"];
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
    history_api_quality_rules__rule_id__history_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
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
                    "application/json": components["schemas"]["DqRuleHistory"][];
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
    results_api_quality_rules__rule_id__results_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                rule_id: string;
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
                    "application/json": components["schemas"]["DqResult"][];
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
    run_api_quality_runs__run_id__get: {
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
                    "application/json": components["schemas"]["DqRun"];
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
    summary_api_quality_summary_get: {
        parameters: {
            query?: {
                source_id?: string | null;
                table?: string | null;
                schema_name?: string | null;
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
                    "application/json": components["schemas"]["DqSummary"];
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
    release_api_releases__release_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                release_id: string;
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
                    "application/json": components["schemas"]["ReleaseView"];
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
    export_api_releases__release_id__export_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                release_id: string;
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
                content?: never;
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
    release_files_api_releases__release_id__files_get: {
        parameters: {
            query?: {
                offset?: number;
                limit?: number;
            };
            header?: never;
            path: {
                release_id: string;
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
                    "application/json": components["schemas"]["ReleaseFiles"];
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
    verify_api_releases__release_id__reconcile_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                release_id: string;
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
                    "application/json": components["schemas"]["ReconcileReport"];
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
    history_api_releases__release_id__reconciliations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                release_id: string;
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
                    "application/json": components["schemas"]["ReconcileReport"][];
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
    analysis_report_api_standards_analysis_report_get: {
        parameters: {
            query?: {
                table_id?: string | null;
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
    checks_api_standards_checks_get: {
        parameters: {
            query?: {
                table_id?: string | null;
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
                    "application/json": components["schemas"]["ColumnCheck"][];
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
    code_lists_api_standards_code_lists_get: {
        parameters: {
            query?: {
                search?: string;
                status?: components["schemas"]["StandardStatus"] | null;
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
                    "application/json": components["schemas"]["CodeList"][];
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
    contract_api_standards_contract_get: {
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
                    "application/json": components["schemas"]["StandardsContract"];
                };
            };
        };
    };
    coverage_api_standards_coverage_get: {
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
                    "application/json": components["schemas"]["StandardsCoverage"];
                };
            };
        };
    };
    export_api_standards_export_get: {
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
                    "text/plain": string;
                };
            };
        };
    };
    fields_api_standards_fields_get: {
        parameters: {
            query?: {
                search?: string;
                status?: components["schemas"]["StandardStatus"] | null;
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
                    "application/json": components["schemas"]["FieldStandard"][];
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
    history_api_standards_history_get: {
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
                    "application/json": components["schemas"]["StandardsHistory"];
                };
            };
        };
    };
    mappings_api_standards_mappings_get: {
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
                    "application/json": components["schemas"]["ColumnMapping"][];
                };
            };
        };
    };
    profiles_api_standards_profiles_get: {
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
                    "application/json": components["schemas"]["ColumnProfile"][];
                };
            };
        };
    };
    quality_api_standards_quality_get: {
        parameters: {
            query?: {
                table_id?: string | null;
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
                    "application/json": components["schemas"]["StandardsQuality"];
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
    report_api_standards_report_get: {
        parameters: {
            query?: {
                table_id?: string | null;
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
                    "application/json": components["schemas"]["StandardsReport"];
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
    schema_api_standards_schema_get: {
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
                    "application/json": components["schemas"]["JsonDocument"];
                };
            };
        };
    };
    suggestions_api_standards_suggestions_get: {
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
                    "application/json": components["schemas"]["MappingSuggestion"][];
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
    report_api_training_governance__run_id__get: {
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
                    "application/json": components["schemas"]["TrainingGovernanceRun"];
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
    clean_api_training_governance__run_id__clean_post: {
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
    ledger_api_training_governance__run_id__ledger_get: {
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
                content?: never;
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
    start_api_uploads_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UploadInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadView"];
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
    status_api_uploads__identifier__get: {
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
                    "application/json": components["schemas"]["UploadView"];
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
    chunk_api_uploads__identifier__chunks__ordinal__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                identifier: string;
                ordinal: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/octet-stream": string;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadView"];
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
    complete_api_uploads__identifier__complete_post: {
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
                    "application/json": components["schemas"]["UploadView"];
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
