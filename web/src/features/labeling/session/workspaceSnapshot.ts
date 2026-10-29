import type {
  ProjectWorkbench,
  TaskWorkbench,
  WorkbenchIndex,
} from "../../../api/production";

export interface WorkspaceSnapshot {
  index: WorkbenchIndex;
  project: ProjectWorkbench | null;
  task: TaskWorkbench | null;
}

const ACTOR_KEY = "datakeel.labeling.workspace-actor";
const PREFIX = "datakeel.labeling.workspace:";

function storageKey(actor: string) {
  return `${PREFIX}${encodeURIComponent(actor)}`;
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function scopes(value: unknown, actor: string) {
  return (
    record(value) &&
    value.actor === actor &&
    Array.isArray(value.scopes) &&
    value.scopes.every((scope: unknown) => typeof scope === "string") &&
    typeof value.zero_users === "boolean"
  );
}

function validProject(project: unknown, index: Record<string, unknown>) {
  if (project === null) return true;
  if (
    !record(project) ||
    !record(project.project) ||
    typeof project.project.id !== "string" ||
    !scopes(project.effective_scopes, String(index.actor)) ||
    !Array.isArray(project.tasks) ||
    !Array.isArray(project.packages) ||
    !record(project.label_set) ||
    !Array.isArray(project.label_set.labels) ||
    !record(project.progress) ||
    !record(project.workload) ||
    !record(project.confidence) ||
    !record(project.prelabel_accuracy) ||
    !record(project.agreement) ||
    !(project.template === null || record(project.template))
  )
    return false;
  const projects = index.projects;
  const projectId = project.project.id;
  return (
    Array.isArray(projects) &&
    projects.some((item: unknown) => record(item) && item.id === projectId)
  );
}

function validTask(task: unknown, project: unknown) {
  if (task === null) return true;
  if (
    !record(task) ||
    !record(task.task) ||
    !record(task.sample) ||
    !record(project) ||
    !record(project.project) ||
    task.task.project_id !== project.project.id ||
    task.task.sample_id !== task.sample.id ||
    typeof task.task.id !== "string" ||
    typeof task.sample.content_url !== "string" ||
    !Array.isArray(task.revisions) ||
    !Array.isArray(task.reviews) ||
    !Array.isArray(task.assignments)
  )
    return false;
  const taskId = task.task.id;
  return (
    Array.isArray(project.tasks) &&
    project.tasks.some((item: unknown) => record(item) && item.id === taskId)
  );
}

function validSnapshot(
  value: unknown,
  actor: string,
): value is WorkspaceSnapshot {
  return (
    record(value) &&
    record(value.index) &&
    value.index.actor === actor &&
    typeof value.index.zero_users === "boolean" &&
    scopes(value.index.effective_scopes, actor) &&
    Array.isArray(value.index.projects) &&
    validProject(value.project, value.index) &&
    validTask(value.task, value.project)
  );
}

/** Restore only this tab's last verified actor; a supplied actor must match exactly. */
export function readWorkspaceSnapshot(
  expectedActor?: string,
): WorkspaceSnapshot | null {
  try {
    const actor = sessionStorage.getItem(ACTOR_KEY);
    if (!actor || (expectedActor !== undefined && expectedActor !== actor))
      return null;
    const stored = sessionStorage.getItem(storageKey(actor));
    if (stored === null) return null;
    const envelope: unknown = JSON.parse(stored);
    if (
      !record(envelope) ||
      envelope.version !== 1 ||
      !validSnapshot(envelope.value, actor)
    )
      return null;
    return envelope.value;
  } catch {
    return null;
  }
}

/** Cache API view data, never authentication headers or credentials. */
export function writeWorkspaceSnapshot(value: WorkspaceSnapshot): boolean {
  const actor = value.index.actor;
  if (!actor || !validSnapshot(value, actor)) return false;
  try {
    const previous = sessionStorage.getItem(ACTOR_KEY);
    if (previous && previous !== actor)
      sessionStorage.removeItem(storageKey(previous));
    sessionStorage.setItem(
      storageKey(actor),
      JSON.stringify({ version: 1, value }),
    );
    sessionStorage.setItem(ACTOR_KEY, actor);
    return true;
  } catch {
    return false;
  }
}

export function clearWorkspaceSnapshot(): boolean {
  try {
    const actor = sessionStorage.getItem(ACTOR_KEY);
    if (actor) sessionStorage.removeItem(storageKey(actor));
    sessionStorage.removeItem(ACTOR_KEY);
    return true;
  } catch {
    return false;
  }
}
