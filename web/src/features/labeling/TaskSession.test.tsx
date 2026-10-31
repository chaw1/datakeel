import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import * as production from "../../api/production";
import { translator } from "../../i18n/context";
import { labelingProject, labelingTask } from "../../test/labelingFixtures";

import * as actions from "./actions";
import { TaskSession } from "./TaskSession";

import type { AnnotationRecord, TaskWorkbench } from "../../api/production";
import type { ActionRun } from "../../api/types";

vi.mock("../../api/production", () => ({ getTaskWorkbench: vi.fn() }));
vi.mock("./actions", () => ({
  mutateProduction: vi.fn(),
  actionDetails: vi.fn(),
}));
vi.mock("./editors/AnnotationEditor", () => ({
  AnnotationEditor: ({
    value,
    onChange,
    readOnly,
  }: {
    value: AnnotationRecord;
    onChange: (value: AnnotationRecord) => void;
    readOnly: boolean;
  }) => (
    <button
      type="button"
      disabled={readOnly}
      onClick={() => {
        onChange({
          ...value,
          boxes: [{ category: "cat", x1: 10, y1: 10, x2: 30, y2: 40 }],
        });
      }}
    >
      {translator("en")("wbEditorAddBox")}
    </button>
  ),
}));
beforeEach(() => {
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(labelingTask);
  vi.mocked(actions.mutateProduction).mockResolvedValue({
    status: "SUCCEEDED",
  } as ActionRun);
  vi.mocked(actions.actionDetails).mockReturnValue({
    id: "revision",
    task_id: "task-1",
    previous_revision_id: null,
    object_confidences: [],
    source: "human",
    actor: "local",
    created_at: "2026-10-30T00:00:00Z",
    annotation: {
      sample_id: "sample-1",
      annotator_id: "local",
      boxes: [{ category: "cat", x1: 10, y1: 10, x2: 30, y2: 40 }],
    },
  });
});
function mount(
  options: {
    canSync?: boolean;
    scopes?: string[];
    task?: TaskWorkbench;
    group?: boolean;
    isIdentityVerified?: () => boolean;
  } = {},
) {
  const props = {
    task: options.task ?? labelingTask,
    project: options.scopes
      ? {
          ...labelingProject,
          project: {
            ...labelingProject.project,
            workflow_tier: options.group
              ? ("group" as const)
              : ("personal" as const),
          },
          effective_scopes: {
            actor: "local",
            zero_users: false,
            scopes: options.scopes,
          },
        }
      : labelingProject,
    actor: "local",
    canSync: options.canSync ?? true,
    isIdentityVerified: options.isIdentityVerified,
    onNavigate: vi.fn(),
    onChanged: vi.fn(),
    onSnapshot: vi.fn(),
    registerGuard: vi.fn(),
  };
  return { ...render(<TaskSession {...props} />), props };
}

function reviewTask(id: string): TaskWorkbench {
  return {
    ...labelingTask,
    task: { ...labelingTask.task, state: "submitted", latest_revision_id: id },
    revisions: [
      {
        id,
        task_id: "task-1",
        annotation: {
          sample_id: "sample-1",
          annotator_id: "annotator",
          labels: [id],
        },
        actor: "annotator",
        source: "human",
        previous_revision_id: null,
        object_confidences: [],
        created_at: "2026-10-30T00:00:00Z",
      },
    ],
  };
}
it("saves the current edits before a keyboard submission and exposes help", async () => {
  const { props } = mount();
  fireEvent.click(screen.getByRole("button", { name: "Add box (B)" }));
  const region = screen.getByRole("region", { name: "Annotation workbench" });
  fireEvent.keyDown(region, { key: "?" });
  expect(
    screen.getByRole("heading", { name: "Keyboard shortcuts" }),
  ).toBeVisible();
  fireEvent.keyDown(region, { key: "Enter", ctrlKey: true });
  await waitFor(() => {
    expect(actions.mutateProduction).toHaveBeenCalledWith("submit_task", {
      task_id: "task-1",
    });
  });
  expect(vi.mocked(actions.mutateProduction).mock.calls[0][0]).toBe(
    "save_revision",
  );
  expect(vi.mocked(actions.mutateProduction).mock.calls[0][1]).toMatchObject({
    previous_revision_id: null,
    annotation: {
      boxes: [{ category: "cat", x1: 10, y1: 10, x2: 30, y2: 40 }],
    },
  });
  fireEvent.keyDown(region, { key: "n", altKey: true });
  expect(props.onNavigate).toHaveBeenCalledWith(1);
});
it("hides annotation controls without annotation scope and prevents keyboard bypass", async () => {
  mount({ scopes: ["production:review"] });
  expect(screen.queryByRole("button", { name: "Mark complete" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Save annotation" })).toBeNull();
  expect(screen.getByRole("button", { name: "Add box (B)" })).toBeDisabled();
  fireEvent.keyDown(
    screen.getByRole("region", { name: "Annotation workbench" }),
    { key: "Enter", ctrlKey: true },
  );
  await Promise.resolve();
  expect(actions.mutateProduction).not.toHaveBeenCalled();
});
it("retains local edits until the server verifies the restored identity", async () => {
  const { rerender, props } = mount({ canSync: false });
  fireEvent.click(screen.getByRole("button", { name: "Add box (B)" }));
  fireEvent.keyDown(
    screen.getByRole("region", { name: "Annotation workbench" }),
    { key: "s", ctrlKey: true },
  );
  await screen.findByText(
    "Could not save. Your edits remain on this device; retry when ready.",
  );
  expect(actions.mutateProduction).not.toHaveBeenCalled();
  rerender(<TaskSession {...props} canSync />);
  await waitFor(() => {
    expect(actions.mutateProduction).toHaveBeenCalledWith(
      "save_revision",
      expect.anything(),
    );
  });
});

it("freezes editing and history while the saved head is being submitted", async () => {
  let complete: ((value: ActionRun) => void) | undefined;
  vi.mocked(actions.mutateProduction).mockImplementation((action) =>
    action === "submit_task"
      ? new Promise<ActionRun>((resolve) => {
          complete = resolve;
        })
      : Promise.resolve({ status: "SUCCEEDED" } as ActionRun),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Add box (B)" }));
  fireEvent.keyDown(
    screen.getByRole("region", { name: "Annotation workbench" }),
    { key: "Enter", ctrlKey: true },
  );
  await waitFor(() => {
    expect(complete).toBeTypeOf("function");
  });
  expect(screen.getByRole("button", { name: "Add box (B)" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Redo" })).toBeDisabled();
  complete?.({ status: "SUCCEEDED" } as ActionRun);
  await waitFor(() => {
    expect(screen.getByRole("button", { name: "Mark complete" })).toBeEnabled();
  });
});

it("reloads a changed review head and requires another decision after showing its annotation", async () => {
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(
    reviewTask("new-head"),
  );
  mount({
    task: reviewTask("displayed-head"),
    scopes: ["production:review"],
    group: true,
  });
  fireEvent.click(screen.getByRole("button", { name: "Approve revision" }));
  expect(
    await screen.findByText(
      "A newer revision was found. Review its annotations before making a decision.",
    ),
  ).toBeVisible();
  expect(actions.mutateProduction).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "Approve revision" }),
  ).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Approve revision" }));
  await waitFor(() => {
    expect(actions.mutateProduction).toHaveBeenCalledExactlyOnceWith(
      "review_task",
      {
        task_id: "task-1",
        revision_id: "new-head",
        decision: "approve",
        issues: [],
      },
    );
  });
});

it("keeps the displayed review revision bound when a later server conflict rejects the decision", async () => {
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(
    reviewTask("displayed-head"),
  );
  vi.mocked(actions.mutateProduction).mockRejectedValueOnce(
    new ApiError(409, "Review head changed during execution"),
  );
  mount({
    task: reviewTask("displayed-head"),
    scopes: ["production:review"],
    group: true,
  });
  fireEvent.click(screen.getByRole("button", { name: "Approve revision" }));
  expect(
    await screen.findByText(
      "Someone else just changed this task. Your edits are kept; try the action again.",
    ),
  ).toBeVisible();
  expect(screen.queryByText(/changed during execution/)).toBeNull();
  expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  expect(actions.mutateProduction).toHaveBeenCalledExactlyOnceWith(
    "review_task",
    {
      task_id: "task-1",
      revision_id: "displayed-head",
      decision: "approve",
      issues: [],
    },
  );
});

it("blocks a stale save adapter immediately while live identity verification is pending", async () => {
  const verified = vi.fn(() => false);
  mount({ isIdentityVerified: verified });
  fireEvent.click(screen.getByRole("button", { name: "Add box (B)" }));
  const region = screen.getByRole("region", { name: "Annotation workbench" });
  fireEvent.keyDown(region, { key: "s", ctrlKey: true });
  await screen.findByText(
    "Could not save. Your edits remain on this device; retry when ready.",
  );
  expect(actions.mutateProduction).not.toHaveBeenCalled();
  fireEvent.keyDown(region, { key: "Enter", ctrlKey: true });
  expect(actions.mutateProduction).not.toHaveBeenCalled();
  verified.mockReturnValue(true);
  fireEvent.keyDown(region, { key: "s", ctrlKey: true });
  await waitFor(() => {
    expect(actions.mutateProduction).toHaveBeenCalledWith(
      "save_revision",
      expect.anything(),
    );
  });
});
