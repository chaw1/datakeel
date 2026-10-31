import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import * as production from "../../api/production";
import { draft } from "../../test/taskAiFixtures";
import {
  advance,
  held,
  revoked,
  status,
  team,
} from "../../test/taskWatchFixtures";

import * as actions from "./actions";
import { TaskSession } from "./TaskSession";
import { WATCH_INTERVAL_MS } from "./useTaskWatch";

import type { AnnotationRecord } from "../../api/production";
import type { ActionRun } from "../../api/types";

vi.mock("../../api/production", () => ({
  getTaskWorkbench: vi.fn(),
  getTaskStatus: vi.fn(),
}));
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
      data-testid="edit"
      disabled={readOnly}
      onClick={() => {
        onChange({ ...value, labels: ["draft"] });
      }}
    />
  ),
}));

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(held);
  vi.mocked(production.getTaskStatus).mockResolvedValue(status());
  vi.mocked(actions.mutateProduction)
    .mockReset()
    .mockResolvedValue({ status: "SUCCEEDED" } as ActionRun);
});
afterEach(() => {
  vi.useRealTimers();
});

it("lets the person leave a reclaimed task with an unsaved draft and refreshes the list", async () => {
  const guards: ((() => Promise<boolean>) | null)[] = [];
  const navigate = vi.fn();
  const changed = vi.fn();
  vi.mocked(actions.mutateProduction).mockImplementation((name) =>
    name === "save_revision"
      ? Promise.reject(new ApiError(503, "503 Unavailable"))
      : Promise.resolve({ status: "SUCCEEDED" } as ActionRun),
  );
  render(
    <TaskSession
      task={held}
      project={team}
      actor="local"
      canSync
      onNavigate={navigate}
      onChanged={changed}
      onSnapshot={vi.fn()}
      registerGuard={(guard) => {
        guards.push(guard);
      }}
    />,
  );
  await advance(10);
  fireEvent.click(screen.getByTestId("edit"));
  expect(guards.at(-1)).toBeTypeOf("function");
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({ leases: [], releases: [revoked] }),
  );
  await advance(WATCH_INTERVAL_MS);
  expect(screen.getByText("This task was taken back")).toBeVisible();
  expect(guards.at(-1)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Back to list" }));
  expect(changed).toHaveBeenCalledOnce();
  expect(navigate).toHaveBeenCalledWith(0);
});

it("never offers review controls on work this person annotated in a team project", async () => {
  const submitted = {
    ...held,
    task: { ...held.task, state: "submitted" as const, annotator_id: "local" },
    assignments: [{ ...held.assignments[0], active: false }],
  };
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(submitted);
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({
      task: submitted.task,
      assignments: submitted.assignments,
      leases: [],
    }),
  );
  const view = (actor: string) =>
    render(
      <TaskSession
        task={submitted}
        project={{
          ...team,
          effective_scopes: { actor, zero_users: false, scopes: ["*"] },
        }}
        actor={actor}
        canSync
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        onSnapshot={vi.fn()}
        registerGuard={vi.fn()}
      />,
    );
  const own = view("local");
  await advance(10);
  expect(screen.queryByRole("button", { name: "Approve revision" })).toBeNull();
  own.unmount();
  view("rev");
  await advance(10);
  expect(
    screen.getByRole("button", { name: "Approve revision" }),
  ).toBeVisible();
});

it("keeps whoever triggered a pass-through out of review after its rework went to someone else", async () => {
  const passThrough = {
    ...draft,
    actor: "pm",
    pass_through: {
      model_id: "vision",
      confidence: 0.95,
      high: 0.9,
      low: 0.5,
      threshold_source: "configured" as const,
      reviewed_objects: 40,
      triggered_by: "pm",
    },
  };
  const handedOver = {
    ...held,
    task: { ...held.task, state: "submitted" as const, annotator_id: "ann-b" },
    revisions: [passThrough],
    assignments: [{ ...held.assignments[0], actor: "ann-b", active: false }],
  };
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(handedOver);
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({
      task: handedOver.task,
      assignments: handedOver.assignments,
      leases: [],
    }),
  );
  const view = (actor: string) =>
    render(
      <TaskSession
        task={handedOver}
        project={{
          ...team,
          effective_scopes: { actor, zero_users: false, scopes: ["*"] },
        }}
        actor={actor}
        canSync
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        onSnapshot={vi.fn()}
        registerGuard={vi.fn()}
      />,
    );
  const trigger = view("pm");
  await advance(10);
  expect(screen.queryByRole("button", { name: "Approve revision" })).toBeNull();
  trigger.unmount();
  view("rev");
  await advance(10);
  expect(
    screen.getByRole("button", { name: "Approve revision" }),
  ).toBeVisible();
});

it("locks without save errors or raw server text when a take-back beats the holder's autosave", async () => {
  vi.mocked(actions.mutateProduction).mockImplementation((name) =>
    name === "save_revision"
      ? Promise.reject(
          new ApiError(
            403,
            "403 Only the current annotation assignment holder may modify this task",
          ),
        )
      : Promise.resolve({ status: "SUCCEEDED" } as ActionRun),
  );
  render(
    <TaskSession
      task={held}
      project={team}
      actor="local"
      canSync
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      onSnapshot={vi.fn()}
      registerGuard={vi.fn()}
    />,
  );
  await advance(10);
  fireEvent.click(screen.getByTestId("edit"));
  await advance(1_000);
  expect(screen.getByText("This task was taken back")).toBeVisible();
  expect(screen.getByRole("button", { name: "Export draft" })).toBeVisible();
  expect(screen.queryByText(/assignment holder/)).toBeNull();
  expect(screen.queryByText(/Could not save/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
  expect(
    screen.getByText("Not saved · draft kept on this device"),
  ).toBeVisible();
  // The holder keeps pressing Ctrl+S out of habit: nothing more goes to the server.
  const sent = vi.mocked(actions.mutateProduction).mock.calls.length;
  const region = screen.getByRole("region", { name: "Annotation workbench" });
  fireEvent.keyDown(region, { key: "s", ctrlKey: true });
  fireEvent.keyDown(region, { key: "Enter", ctrlKey: true });
  await advance(1_000);
  expect(vi.mocked(actions.mutateProduction).mock.calls).toHaveLength(sent);
});

it("treats a submission that comes back pending one round later as returned, with the reviewer's notes", async () => {
  const returned = {
    ...held,
    task: { ...held.task, state: "pending" as const, round: 1 },
    reviews: [
      {
        id: "review-1",
        task_id: "task-1",
        revision_id: "revision-1",
        decision: "rework" as const,
        issues: ["Box too loose"],
        actor: "rev",
        round: 0,
        created_at: "2026-10-30T00:02:00Z",
      },
    ],
  };
  let submitted = false;
  vi.mocked(actions.mutateProduction).mockImplementation((name) => {
    if (name === "submit_task") submitted = true;
    return Promise.resolve({ status: "SUCCEEDED" } as ActionRun);
  });
  vi.mocked(production.getTaskWorkbench).mockImplementation(() =>
    Promise.resolve(submitted ? returned : held),
  );
  vi.mocked(production.getTaskStatus).mockImplementation(() =>
    Promise.resolve(
      submitted ? status({ task: returned.task, leases: [] }) : status(),
    ),
  );
  render(
    <TaskSession
      task={held}
      project={team}
      actor="local"
      canSync
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      onSnapshot={vi.fn()}
      registerGuard={vi.fn()}
    />,
  );
  await advance(10);
  fireEvent.click(screen.getByRole("button", { name: "Submit annotation" }));
  await advance(10);
  expect(screen.getByText("This task was returned for rework.")).toBeVisible();
  expect(screen.getByText("Reviewer: Box too loose")).toBeVisible();
});
