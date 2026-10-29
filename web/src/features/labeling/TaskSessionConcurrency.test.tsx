import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { getTaskWorkbench } from "../../api/production";
import { labelingProject, labelingTask } from "../../test/labelingFixtures";

import { mutateProduction } from "./actions";
import { TaskSession } from "./TaskSession";

import type { TaskWorkbench } from "../../api/production";

vi.mock("../../api/production", () => ({ getTaskWorkbench: vi.fn() }));
vi.mock("./actions", () => ({
  mutateProduction: vi.fn(),
  actionDetails: vi.fn(),
}));
vi.mock("./editors/AnnotationEditor", () => ({ AnnotationEditor: () => null }));

it("stops a pending review before mutation if identity verification begins during its read", async () => {
  const task: TaskWorkbench = {
    ...labelingTask,
    task: {
      ...labelingTask.task,
      state: "submitted",
      latest_revision_id: "displayed-head",
    },
    revisions: [
      {
        id: "displayed-head",
        task_id: "task-1",
        actor: "annotator",
        source: "human",
        previous_revision_id: null,
        created_at: "2026-10-30T00:00:00Z",
        annotation: {
          sample_id: "sample-1",
          annotator_id: "annotator",
          labels: ["cat"],
        },
      },
    ],
  };
  let finish!: (value: TaskWorkbench) => void;
  vi.mocked(getTaskWorkbench).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const verified = vi.fn(() => true);
  render(
    <TaskSession
      task={task}
      project={{
        ...labelingProject,
        project: { ...labelingProject.project, workflow_tier: "group" },
        effective_scopes: {
          actor: "local",
          zero_users: false,
          scopes: ["production:review"],
        },
      }}
      actor="local"
      canSync
      isIdentityVerified={verified}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      onSnapshot={vi.fn()}
      registerGuard={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Approve revision" }));
  await waitFor(() => {
    expect(getTaskWorkbench).toHaveBeenCalledTimes(1);
  });
  verified.mockReturnValue(false);
  await act(async () => {
    finish(task);
    await Promise.resolve();
  });
  expect(
    await screen.findByText("Offline · edits retained on this device"),
  ).toBeVisible();
  expect(mutateProduction).not.toHaveBeenCalled();
});
