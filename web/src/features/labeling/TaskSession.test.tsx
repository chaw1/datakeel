import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as production from "../../api/production";
import { translator } from "../../i18n/context";
import { labelingProject, labelingTask } from "../../test/labelingFixtures";

import * as actions from "./actions";
import { TaskSession } from "./TaskSession";

import type { AnnotationRecord } from "../../api/production";
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
function mount(options: { canSync?: boolean; scopes?: string[] } = {}) {
  const props = {
    task: labelingTask,
    project: options.scopes
      ? {
          ...labelingProject,
          effective_scopes: {
            actor: "local",
            zero_users: false,
            scopes: options.scopes,
          },
        }
      : labelingProject,
    actor: "local",
    canSync: options.canSync ?? true,
    onNavigate: vi.fn(),
    onChanged: vi.fn(),
    onSnapshot: vi.fn(),
    registerGuard: vi.fn(),
  };
  return { ...render(<TaskSession {...props} />), props };
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
