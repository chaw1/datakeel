import { get } from "./client";

import type { components } from "./generated";

export type AnnotationRecord = components["schemas"]["AnnotationRecord"];
export type ProductionLabel = components["schemas"]["ProductionLabel"];
export type ProductionTemplate = components["schemas"]["ProductionTemplate"];
export type WorkbenchIndex = components["schemas"]["WorkbenchIndex"];
export type ProjectWorkbench = components["schemas"]["WorkbenchProject"];
export type TaskWorkbench = components["schemas"]["WorkbenchTask"];
export type ProductionTask = components["schemas"]["ProductionTask"];
export type EffectiveScopes = components["schemas"]["EffectiveScopes"];

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
  } = {},
) {
  const query = new URLSearchParams();
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.view !== undefined) query.set("view", options.view);
  if (options.packageId) query.set("package_id", options.packageId);
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
