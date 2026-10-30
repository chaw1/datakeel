import { useLayoutEffect, useRef } from "react";

import { taskNavigation } from "./paging";

import type { ProjectWorkbench, TaskWorkbench } from "../../api/production";

interface Place {
  project: ProjectWorkbench | null;
  task: TaskWorkbench | null;
  page: number;
  cursors: string[];
}

/**
 * Previous/Next keys pressed while a page or task is still loading are queued and replayed
 * in order. Each step starts from where the previous one landed, never from a stale render.
 */
export function useNavigationQueue(
  place: Place,
  {
    mayLeave,
    open,
    close,
    loadPage,
    setNotice,
  }: {
    mayLeave: () => Promise<boolean>;
    open: (taskId: string) => Promise<TaskWorkbench | null>;
    close: () => void;
    /** Load and show an adjacent page; null when it failed or was superseded. */
    loadPage: (
      target: number,
      cursor: string,
      cursors: string[],
    ) => Promise<ProjectWorkbench | null>;
    setNotice: (notice: "first" | "last" | null) => void;
  },
) {
  const latest = useRef(place);
  const queue = useRef<(-1 | 0 | 1)[]>([]);
  const draining = useRef(false);
  useLayoutEffect(() => {
    if (!draining.current) latest.current = place;
  });
  async function step(direction: -1 | 0 | 1) {
    if (!(await mayLeave())) return false;
    const now = latest.current;
    if (direction === 0) {
      close();
      latest.current = { ...now, task: null };
      return true;
    }
    const { position, ...edges } = taskNavigation(
      now.project,
      now.task,
      now.page,
    );
    const next =
      position >= 0 && position + direction >= 0
        ? now.project?.tasks.at(position + direction)
        : undefined;
    if (next) {
      setNotice(null);
      const loaded = await open(next.id);
      if (loaded) latest.current = { ...now, task: loaded };
      return loaded !== null;
    }
    if (!(direction === 1 ? edges.next : edges.previous) || !now.project) {
      setNotice(direction === 1 ? "last" : "first");
      return true;
    }
    // Cross the page boundary: load the adjacent page, then open its edge task.
    const target = now.page + direction;
    const cursor =
      direction === 1
        ? (now.project.next_cursor ?? "")
        : (now.cursors[target] ?? "");
    const cursors =
      direction === 1
        ? [...now.cursors.slice(0, now.page + 1), cursor]
        : now.cursors;
    const data = await loadPage(target, cursor, cursors);
    if (!data) return false;
    latest.current = { project: data, task: now.task, page: target, cursors };
    const edge = direction === 1 ? data.tasks.at(0) : data.tasks.at(-1);
    setNotice(edge ? null : direction === 1 ? "last" : "first");
    if (!edge) return true;
    const loaded = await open(edge.id);
    if (loaded) latest.current = { ...latest.current, task: loaded };
    return loaded !== null;
  }
  return async function navigate(direction: -1 | 0 | 1) {
    queue.current.push(direction);
    if (draining.current) return;
    draining.current = true;
    try {
      for (let next = queue.current.shift(); next !== undefined;) {
        // A refused or failed step drops the rest: replaying them would land somewhere unexpected.
        if (!(await step(next))) queue.current = [];
        next = queue.current.shift();
      }
    } finally {
      draining.current = false;
    }
  };
}
