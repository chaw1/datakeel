import type { Translate } from "../../i18n/context";
import type { MessageKey } from "../../i18n/en";

const names: Partial<Record<string, MessageKey>> = {
  "dataset-health": "workflowHealth",
  "metric-change": "workflowMetric",
  "low-quality-cleanup": "workflowCleanup",
};
const descriptions: Partial<Record<string, MessageKey>> = {
  "dataset-health": "workflowHealthDescription",
  "metric-change": "workflowMetricDescription",
  "low-quality-cleanup": "workflowCleanupDescription",
};
const inputs: Partial<Record<string, MessageKey>> = {
  dataset_id: "workflowSelectDataset",
  metric_id: "workflowMetricId",
  override: "workflowOverride",
  question: "workflowQuestion",
  reference_instant: "workflowReference",
  quality_max: "workflowQualityMax",
};
const steps: Partial<Record<string, MessageKey>> = {
  tool: "workflowTool",
  wait: "workflowWait",
  branch: "workflowBranch",
  approval: "workflowApprovalStep",
  output: "workflowOutputStep",
};
export function workflowName(id: string, t: Translate, fallback = id) {
  return names[id] ? t(names[id]) : fallback;
}
export function workflowDescription(
  id: string,
  t: Translate,
  fallback: string,
) {
  return descriptions[id] ? t(descriptions[id]) : fallback;
}
export function inputLabel(id: string, t: Translate) {
  return inputs[id] ? t(inputs[id]) : id;
}
export function stepLabel(type: string, t: Translate) {
  return steps[type] ? t(steps[type]) : type;
}
export function workflowHref(runId: string) {
  return `#/workflows?${new URLSearchParams({ run: runId }).toString()}`;
}
