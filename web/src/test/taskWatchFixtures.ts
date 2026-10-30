import { act } from "@testing-library/react";
import { vi } from "vitest";

import { labelingProject, labelingTask } from "./labelingFixtures";

import type {
  ProjectWorkbench,
  TaskWorkbench,
  WorkbenchTaskStatus,
} from "../api/production";

/** A team-tier task held by "local", with a ten-minute lease, for lease and reclaim tests. */
export const assignment = {
  id: "assignment-1",
  task_id: "task-1",
  actor: "local",
  stage: "annotation" as const,
  active: true,
  created_at: "2026-10-30T00:00:00Z",
  lease_expires_at: "2026-10-30T00:10:00Z",
};
export const team: ProjectWorkbench = {
  ...labelingProject,
  project: { ...labelingProject.project, workflow_tier: "team" },
};
export const held: TaskWorkbench = {
  ...labelingTask,
  task: { ...labelingTask.task, state: "in_progress" },
  assignments: [assignment],
};
export function status(
  overrides: Partial<WorkbenchTaskStatus> = {},
): WorkbenchTaskStatus {
  return {
    task: held.task,
    assignments: [assignment],
    leases: [
      {
        assignment_id: "assignment-1",
        actor: "local",
        stage: "annotation",
        expires_at: "2026-10-30T00:10:00Z",
        seconds_remaining: 600,
        enforced: true,
      },
    ],
    releases: [],
    observed_at: "2026-10-30T00:00:00Z",
    ...overrides,
  };
}
export const revoked = {
  assignment_id: "assignment-1",
  task_id: "task-1",
  project_id: "project",
  actor: "local",
  stage: "annotation" as const,
  reason: "revoked" as const,
  note: "",
  lease_expires_at: "2026-10-30T00:10:00Z",
  released_at: "2026-10-30T00:01:00Z",
  released_by: "manager",
};

/** Advance fake timers, then let reads, renders and the effects they schedule settle. */
export async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  for (let step = 0; step < 3; step++)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
}
