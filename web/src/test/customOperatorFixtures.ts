import { actionPlan, actionRun } from "./actionFixtures";

import type {
  CustomOperatorRun,
  CustomOperatorVersion,
} from "../api/customOperators";
import type { ActionPlan, ActionRun } from "../api/types";

export const customCode =
  'PARAMETER_SCHEMA = {"type": "object"}\nOUTPUT_METADATA_SCHEMA = {"type": "object"}\nimport socket\ndef run(inputs, params, ctx):\n    return []\n# last source line <script>literal</script>\n';
export const customHash = "a".repeat(64);
export const customPlan: ActionPlan = {
  ...actionPlan,
  action_type: "submit_custom_operator",
  canonical_params: {
    name: "fixture_filter",
    code: customCode,
    code_hash: customHash,
    modality: "text",
    parameter_schema: { type: "object" },
    metadata_schema: { type: "object" },
    static_checks: [
      {
        line: 3,
        column: 0,
        code: "risky_capability",
        message: "Review use of socket; static checks do not provide isolation",
      },
    ],
  },
};
export const customVersion: CustomOperatorVersion = {
  id: `custom.fixture_filter@${customHash}`,
  name: "fixture_filter",
  code: customCode,
  code_hash: customHash,
  modality: "text",
  parameter_schema: { type: "object" },
  metadata_schema: { type: "object" },
  static_checks: [
    {
      line: 3,
      column: 0,
      code: "risky_capability",
      message: "Review use of socket; static checks do not provide isolation",
    },
  ],
  plan_id: customPlan.id,
  approved_by: "local",
  approved_at: "2026-10-27T00:00:00Z",
};
export const customRun: CustomOperatorRun = {
  id: "sandbox-run-1",
  operator: customVersion.id,
  code_hash: customHash,
  image_digest: `python@sha256:${"b".repeat(64)}`,
  backend: "container",
  params_digest: "c".repeat(64),
  task_id: "task-1",
  shard_id: "shard-1",
  node_id: "custom",
  attempt_id: "attempt-1",
  created_at: "2026-10-27T00:00:00Z",
  completed_at: "2026-10-27T00:00:01Z",
  success: false,
  exit_reason: "timeout",
  resources: { wall_seconds: 1 },
  output_count: 0,
};
export const customActionRun: ActionRun = {
  ...actionRun,
  action_type: "run_pipeline",
  status: "QUEUED",
  receipt: null,
};
