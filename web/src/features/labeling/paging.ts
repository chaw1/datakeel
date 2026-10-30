import type { WorkbenchView } from "./model";
import type { ProjectWorkbench, TaskWorkbench } from "../../api/production";

export const PAGE_SIZE = 100;

/** Ask the server for one filtered page of the current role view. */
export function pageQuery(
  view: WorkbenchView,
  packageId: string,
  cursor: string,
  search = "",
) {
  return {
    limit: PAGE_SIZE,
    cursor,
    packageId,
    search: search.trim(),
    view:
      view === "reviews"
        ? ("review" as const)
        : view === "tasks"
          ? ("mine" as const)
          : ("all" as const),
  };
}

/** Previous/next stay available across page boundaries and stop only at the true ends. */
export function taskNavigation(
  project: ProjectWorkbench | null,
  task: TaskWorkbench | null,
  page: number,
) {
  const position = task
    ? (project?.tasks.findIndex((item) => item.id === task.task.id) ?? -1)
    : -1;
  return {
    position,
    previous: position > 0 || (position === 0 && page > 0),
    next:
      position >= 0 &&
      (position < (project?.tasks.length ?? 0) - 1 || !!project?.next_cursor),
  };
}
