import type {
  Dataset,
  DatasetData,
  FileItem,
  Graph,
  LineageEvent,
  Quality,
  Report,
  Task,
  Version,
} from "../api/types";
export const file: FileItem = {
  id: "file-1",
  filename: "sample.txt",
  sha256: "a".repeat(64),
  size: 120,
  modality: "text",
  metadata: {},
};
export const imageFile: FileItem = {
  ...file,
  id: "file-2",
  filename: "photo.png",
  modality: "image",
};
export const version: Version = {
  id: "version-1",
  created_at: 1700000000,
  file_count: 1,
  manifest: [{ ...file, filename: "processed.txt" }],
};
export const dataset: Dataset = {
  id: "dataset-1",
  name: "Sample collection",
  file_count: 2,
  created_at: 1700000000,
  metadata: {},
  quality_config: {
    allowed_formats: {},
    distribution_field: "modality",
    exclude_annotation_when_absent: true,
    min_image_height: 1,
    min_image_width: 1,
    min_size_bytes: 1,
    thresholds: {},
    weights: {},
  },
  template: null,
  compliance: {},
};
export const task: Task = {
  id: "task-1",
  dataset_id: dataset.id,
  input_version_id: null,
  state: "COMPLETED",
  progress: 100,
  total_shards: 2,
  completed_shards: 2,
  error: null,
  created_at: 1700000000,
  finished_at: null,
  shards: [],
  partial: false,
};
export const event: LineageEvent = {
  event_id: "event-1",
  event_type: "TRANSFORM",
  idempotency_key: "transform-1",
  on_behalf_of: "local",
  operator: "text.clean",
  run_state: "COMPLETED",
  source_module: "pipeline",
  occurred_at: "2026-10-22T00:00:00Z",
};
export const graph: Graph = {
  truncated: false,
  nodes: [
    {
      id: "source",
      asset_id: "source",
      asset_type: "file",
      namespace: "default",
      label: "Source file",
    },
    {
      id: "output",
      asset_id: "output",
      asset_type: "artifact",
      namespace: "default",
      label: "Cleaned file",
    },
  ],
  edges: [
    {
      source: "source",
      kind: "lineage",
      target: "output",
      event_id: "event-1",
      operator: "text.clean",
      event,
    },
  ],
  events: [event],
};
export const quality: Quality = {
  total: 83.5,
  grade: "good",
  file_count: 2,
  config: {
    allowed_formats: {},
    distribution_field: "modality",
    exclude_annotation_when_absent: true,
    min_image_height: 1,
    min_image_width: 1,
    min_size_bytes: 1,
    thresholds: {},
    weights: {},
  },
  dimensions: {
    completeness: {
      score: 100,
      weight: 25,
      included: true,
      details: { missing: 0 },
    },
    annotation: { score: 0, weight: 0, included: false, details: {} },
  },
  issues: [
    {
      dimension: "consistency",
      severity: "warning",
      message: "One small file",
    },
  ],
};
export const report: Report = {
  chapters: [{ title: "Dataset summary", body: "A synthetic sample dataset." }],
  body: "baseline",
  baseline: "baseline",
  baseline_verification: "Verified against measurements",
  fallback: true,
  source: "baseline",
};
export const workspace: DatasetData = {
  files: [file, imageFile],
  versions: [version],
  tasks: [task],
  graph,
  quality,
  report,
  errors: [],
};
export function mockApi(path: string): unknown {
  if (path === "/api/datasets") return [dataset];
  if (path === "/api/tasks") return [task];
  if (path.startsWith("/api/lineage")) return graph;
  if (path.endsWith("/files")) return workspace.files;
  if (path.endsWith("/versions")) return workspace.versions;
  if (path.endsWith("/quality")) return quality;
  if (path.endsWith("/report")) return report;
  return null;
}
