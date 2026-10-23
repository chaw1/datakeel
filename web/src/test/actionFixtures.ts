import { dataset, event, file } from "./fixtures";

import type { ActionPlan, ActionRun, OntologyRegistry } from "../api/types";

const selection = {
  schema_version: "1.0",
  object_type: "file",
  namespace: "default",
  dataset_id: dataset.id,
  include_deleted: false,
  limit: 1000,
} as const;
export const actionPlan: ActionPlan = {
  id: "plan-1",
  operation_id: "operation-1",
  action_type: "delete_files",
  canonical_params: { selection },
  manifest: {
    query: selection,
    objects: [
      {
        asset_ref: {
          asset_id: file.id,
          asset_type: "file",
          namespace: "default",
        },
        revision: file.sha256,
        state_revision: 0,
        properties: {},
        size: file.size,
      },
    ],
    state_digest: "state-digest",
    total_bytes: file.size,
    truncated: false,
  },
  plan_digest: "plan-digest",
  target_digest: "target-digest",
  state_digest: "state-digest",
  created_at: "2026-10-22T00:00:00Z",
  expires_at: new Date(Date.now() + 600000).toISOString(),
  reversible: false,
  external: false,
  impact: { object_count: 1, total_bytes: file.size, external: false },
  actor: "local",
  context: {
    actor: "local",
    scopes: ["*"],
    max_objects: 1000,
    max_bytes: 1000000,
    ttl_seconds: 900,
  },
  status: "PREPARED",
};
export const actionRun: ActionRun = {
  id: "run-1",
  plan_id: actionPlan.id,
  action_type: actionPlan.action_type,
  status: "SUCCEEDED",
  created_at: "2026-10-22T00:00:00Z",
  completed_at: "2026-10-22T00:00:01Z",
  receipt: {
    ...event,
    event_id: "receipt-1",
    operator: "delete_files",
    inputs: [
      { asset_id: dataset.id, asset_type: "dataset", namespace: "default" },
    ],
    outputs: [
      { asset_id: "run-1", asset_type: "action_run", namespace: "default" },
    ],
  },
};
export const ontology: OntologyRegistry = {
  version: "1.0",
  object_types: [
    {
      id: "dataset",
      version: "1.0",
      properties: { type: "object", properties: { id: { type: "string" } } },
      identity_mapping: {
        asset_type: "dataset",
        id_field: "id",
        namespace: "default",
      },
      description: "A dataset.",
    },
  ],
  link_types: [
    {
      id: "derived",
      version: "1.0",
      domain: ["dataset"],
      range: ["file"],
      cardinality: "one-to-many",
      semantics: "derived",
      description: "Transformation evidence.",
    },
  ],
  functions: [
    {
      id: "list_datasets",
      version: "1.0",
      input_schema: { type: "object" },
      output_schema: { type: "array" },
      read_scope: "datasets:read",
      handler: "list_datasets",
    },
  ],
  actions: [
    {
      id: "delete_files",
      version: "1.0",
      params_schema: { type: "object" },
      auth_scope: "files:delete",
      preconditions: ["exists"],
      effects: ["delete"],
      reversible: false,
      handler: "delete_files",
    },
  ],
};
