import { get, post } from "./client";

import type { components } from "./generated";

export type AnnotationRecord = components["schemas"]["AnnotationRecord"];
export type ProductionLabel = components["schemas"]["ProductionLabel"];
export type ProductionTemplate = components["schemas"]["ProductionTemplate"];
export type WorkbenchIndex = components["schemas"]["WorkbenchIndex"];
export type ProjectWorkbench = components["schemas"]["WorkbenchProject"];
export type TaskWorkbench = components["schemas"]["WorkbenchTask"];
export type ProductionTask = components["schemas"]["ProductionTask"];
export type Assignment = components["schemas"]["Assignment"];
export type EffectiveScopes = components["schemas"]["EffectiveScopes"];
export type WorkbenchSampleName = components["schemas"]["WorkbenchSampleName"];
export type WorkbenchTaskStatus = components["schemas"]["WorkbenchTaskStatus"];
export type SkillDispatchPreview =
  components["schemas"]["SkillDispatchPreview"];
export type SkillDispatchPreviewRequest =
  components["schemas"]["SkillDispatchPreviewRequest"];

export function getWorkbench() {
  return get<WorkbenchIndex>("/api/production/workbench");
}

export function getProjectWorkbench(
  projectId: string,
  options: {
    limit?: number;
    cursor?: string;
    view?: "all" | "mine" | "review";
    packageId?: string;
    search?: string;
  } = {},
) {
  const query = new URLSearchParams();
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.view !== undefined) query.set("view", options.view);
  if (options.packageId) query.set("package_id", options.packageId);
  if (options.search) query.set("search", options.search);
  const suffix = query.size ? `?${query.toString()}` : "";
  return get<ProjectWorkbench>(
    `/api/production/projects/${encodeURIComponent(projectId)}/workbench${suffix}`,
  );
}

export function getTaskWorkbench(taskId: string) {
  return get<TaskWorkbench>(
    `/api/production/tasks/${encodeURIComponent(taskId)}/workbench`,
  );
}

/** Name up to 500 tasks of one project by the file name recorded at import. */
export function getTaskSamples(projectId: string, taskIds: readonly string[]) {
  const query = new URLSearchParams();
  for (const id of taskIds.slice(0, 500)) query.append("task_id", id);
  return get<components["schemas"]["WorkbenchTaskSamples"]>(
    `/api/production/projects/${encodeURIComponent(projectId)}/task-samples?${query.toString()}`,
  );
}

/** Cheap poll of a task's state, holders, effective leases and releases. */
export function getTaskStatus(taskId: string) {
  return get<WorkbenchTaskStatus>(
    `/api/production/tasks/${encodeURIComponent(taskId)}/status`,
  );
}

/** Preview a skill dispatch with the same rules as execution, without writing. */
export function previewDispatch(
  projectId: string,
  request: SkillDispatchPreviewRequest,
) {
  return post<SkillDispatchPreview>(
    `/api/production/projects/${encodeURIComponent(projectId)}/dispatch-preview`,
    request,
  );
}

/** Mirrors `PackageSampling`: the reproducible P26 sample of one package. */
export interface PackageSampling {
  lot_size: number;
  sample_size: number;
  sample_ids: string[];
  task_ids: string[];
  acceptance_number: number;
  rejection_number: number;
  method: "aql" | "ratio";
  aql?: number | null;
  ratio?: number | null;
  seed: number;
}

/** Mirrors `PackageInspection`: one signed package decision. */
export interface PackageInspection {
  id: string;
  package_id: string;
  defective_count: number;
  accepted: boolean;
  returned_task_ids: string[];
  actor: string;
  created_at: string;
  sampling: PackageSampling;
}

/** Mirrors `PackageAcceptance`, returned by the `package_acceptance` read function. */
export interface PackageAcceptance {
  project_id: string;
  package_id: string;
  status: "in_progress" | "ready" | "accepted" | "rejected";
  total: number;
  approved: number;
  sampling: PackageSampling | null;
  latest: PackageInspection | null;
  inspections: number;
}

/** Mirrors `LeaseStatus`, returned by the `lease_status` read function. */
export interface LeaseStatus {
  project_id: string;
  observed_at: string;
  active: { assignment: Assignment; seconds_remaining: number }[];
  overdue: { assignment: Assignment; seconds_remaining: number }[];
  reclaimed: components["schemas"]["LeaseRelease"][];
}

/** Call a read-only production function; the same numbers agents and MCP read. */
export async function readProduction<T>(
  name: "package_acceptance" | "lease_status" | "skill_workload",
  body: Record<string, string | number>,
) {
  const result = await post<{ data: T }>(
    `/api/production/functions/${name}`,
    body,
  );
  return result.data;
}
