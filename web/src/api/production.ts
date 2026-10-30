import { get, post } from "./client";

import type { components } from "./generated";

export type AnnotationRecord = components["schemas"]["AnnotationRecord"];
export type ProductionLabel = components["schemas"]["ProductionLabel"];
export type ProductionTemplate = components["schemas"]["ProductionTemplate"];
export type WorkbenchIndex = components["schemas"]["WorkbenchIndex"];
export type ProjectWorkbench = components["schemas"]["WorkbenchProject"];
export type TaskWorkbench = components["schemas"]["WorkbenchTask"];
export type ProductionTask = components["schemas"]["ProductionTask"];
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

/** Name up to 500 tasks of one project by file name and dataset path. */
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
