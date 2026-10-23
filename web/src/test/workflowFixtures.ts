import type {
  WorkflowDefinition,
  WorkflowEvent,
  WorkflowRun,
} from "../api/workflows";

export const workflow: WorkflowDefinition = {
  id: "low-quality-cleanup",
  name: "Cleanup",
  description: "Find and clean up files.",
  inputs: {
    dataset_id: {
      type: "string",
      required: true,
      default: null,
      description: "Dataset",
    },
    quality_max: {
      type: "number",
      required: true,
      default: 60,
      description: "Quality",
    },
  },
  triggers: {
    keywords: [["cleanup"]],
    classification_keywords: ["cleanup"],
    threshold: 1,
    margin: 1,
  },
  entry: "find",
  steps: [
    {
      id: "find",
      type: "tool",
      tool: "search_files",
      arguments: { dataset_id: "${inputs.dataset_id}" },
      next: "delete",
    },
    {
      id: "delete",
      type: "approval",
      action: "delete_files",
      arguments: {},
      next: "result",
    },
    { id: "result", type: "output", value: { conclusion: "cleaned" } },
  ],
};
export const pausedWorkflow: WorkflowRun = {
  id: "workflow-run-1",
  workflow_id: workflow.id,
  status: "PAUSED",
  inputs: { dataset_id: "dataset-1", quality_max: 60 },
  pending_plan_id: "plan-1",
  error: null,
  created_at: "2026-10-24T00:00:00Z",
  updated_at: "2026-10-24T00:00:01Z",
  steps: [
    {
      id: "find",
      type: "tool",
      status: "SUCCEEDED",
      output: { data: { total: 2 } },
      error: null,
      plan_id: null,
      started_at: null,
      finished_at: null,
    },
    {
      id: "delete",
      type: "approval",
      status: "PAUSED",
      output: null,
      error: null,
      plan_id: "plan-1",
      started_at: null,
      finished_at: null,
    },
    {
      id: "result",
      type: "output",
      status: "PENDING",
      output: null,
      error: null,
      plan_id: null,
      started_at: null,
      finished_at: null,
    },
  ],
};
export const completedWorkflow: WorkflowRun = {
  ...pausedWorkflow,
  status: "SUCCEEDED",
  pending_plan_id: null,
  steps: pausedWorkflow.steps.map((step) => ({
    ...step,
    status: "SUCCEEDED",
    output:
      step.id === "result"
        ? { conclusion: "cleaned", total: 80, file_count: 1 }
        : step.output,
  })),
};
export function workflowStream(run: WorkflowRun, done = true) {
  const events: WorkflowEvent[] = [
    { id: "event-run", event: "run", run, step_id: null },
  ];
  if (done)
    events.push({ id: "event-done", event: "done", run, step_id: null });
  return new Response(
    events
      .map(
        (event) => `event: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`,
      )
      .join(""),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}
