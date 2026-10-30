import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import * as production from "../../api/production";
import { recordFieldFixture } from "../../test/attributeFixtures";
import { labelingProject, labelingTask } from "../../test/labelingFixtures";

import * as actions from "./actions";
import { TaskSession } from "./TaskSession";

import type { AnnotationRecord, ProjectWorkbench } from "../../api/production";
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
  }: {
    value: AnnotationRecord;
    onChange: (value: AnnotationRecord) => void;
  }) => (
    <>
      <button
        type="button"
        data-testid="edit"
        onClick={() => {
          onChange({ ...value, labels: ["cat"] });
        }}
      />
      <button
        type="button"
        data-testid="fill-scene"
        onClick={() => {
          onChange({ ...value, attributes: { scene: "day" } });
        }}
      />
    </>
  ),
}));

const project: ProjectWorkbench = {
  ...labelingProject,
  template: labelingProject.template && {
    ...labelingProject.template,
    attributes: [recordFieldFixture],
  },
};

beforeEach(() => {
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(labelingTask);
  vi.mocked(actions.mutateProduction).mockReset();
  vi.mocked(actions.mutateProduction).mockResolvedValue({
    status: "SUCCEEDED",
  } as ActionRun);
  vi.mocked(actions.actionDetails).mockImplementation(() => ({
    id: "revision",
    task_id: "task-1",
    previous_revision_id: null,
    source: "human",
    actor: "local",
    created_at: "2026-10-30T00:00:00Z",
    annotation: {
      sample_id: "sample-1",
      annotator_id: "local",
      attributes: { scene: "day" },
    },
  }));
});

function mount() {
  render(
    <TaskSession
      task={labelingTask}
      project={project}
      actor="local"
      canSync
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      onSnapshot={vi.fn()}
      registerGuard={vi.fn()}
    />,
  );
}

it("holds back saving and blocks submit until a required attribute is filled", async () => {
  mount();
  fireEvent.click(screen.getByTestId("edit"));
  fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));
  expect(
    await screen.findByText("Cannot submit yet. This item: Scene is required"),
  ).toBeVisible();
  expect(
    screen.getByText("Not saved · fill in the required attributes"),
  ).toHaveAttribute("data-save-state", "incomplete");
  expect(actions.mutateProduction).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId("fill-scene"));
  fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));
  await waitFor(() => {
    expect(actions.mutateProduction).toHaveBeenCalledWith("submit_task", {
      task_id: "task-1",
    });
  });
  expect(vi.mocked(actions.mutateProduction).mock.calls[0][1]).toMatchObject({
    annotation: { attributes: { scene: "day" } },
  });
});

it("explains a concurrent change in plain words and offers to redo the action", async () => {
  mount();
  fireEvent.click(screen.getByTestId("fill-scene"));
  vi.mocked(actions.mutateProduction)
    .mockResolvedValueOnce({ status: "SUCCEEDED" } as ActionRun)
    .mockRejectedValueOnce(
      new ApiError(409, "409 Action target state changed after preparation"),
    );
  fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));
  expect(
    await screen.findByText(
      "Someone else just changed this task. Your edits are kept; try the action again.",
    ),
  ).toBeVisible();
  expect(screen.queryByText(/changed after preparation/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => {
    expect(
      vi
        .mocked(actions.mutateProduction)
        .mock.calls.filter(([name]) => name === "submit_task"),
    ).toHaveLength(2);
  });
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
});
