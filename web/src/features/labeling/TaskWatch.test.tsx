import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import * as production from "../../api/production";
import { labelingProject } from "../../test/labelingFixtures";
import {
  advance,
  held,
  revoked,
  status,
  team,
} from "../../test/taskWatchFixtures";

import * as actions from "./actions";
import { TaskSession } from "./TaskSession";
import {
  HEARTBEAT_INTERVAL_MS,
  HIDDEN_WATCH_INTERVAL_MS,
  WATCH_INTERVAL_MS,
  heartbeatInterval,
} from "./useTaskWatch";

import type { AnnotationRecord, TaskWorkbench } from "../../api/production";
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

function mount(task = held, project = team) {
  render(
    <TaskSession
      task={task}
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
const heartbeats = () =>
  vi
    .mocked(actions.mutateProduction)
    .mock.calls.filter(([name]) => name === "heartbeat");

it("renews a team lease on open and every two minutes and shows the time left", async () => {
  mount();
  await advance(10);
  expect(heartbeats()).toHaveLength(1);
  expect(heartbeats()[0][1]).toEqual({
    task_id: "task-1",
    stage: "annotation",
  });
  expect(screen.getByText("Lease 10:00 left · renewed 1 times")).toBeVisible();
  await advance(HEARTBEAT_INTERVAL_MS * 3);
  expect(heartbeats()).toHaveLength(4);
});

it("renews at min(2 minutes, lease / 3), so a one-minute lease survives three minutes of work", async () => {
  expect(heartbeatInterval(60)).toBe(20_000);
  expect(heartbeatInterval(600)).toBe(HEARTBEAT_INTERVAL_MS);
  expect(heartbeatInterval(null)).toBe(HEARTBEAT_INTERVAL_MS);
  let renewedAt = Date.now();
  vi.mocked(actions.mutateProduction).mockImplementation((name) => {
    if (name === "heartbeat") renewedAt = Date.now();
    return Promise.resolve({ status: "SUCCEEDED" } as ActionRun);
  });
  // The server's lease runs one minute from the latest renewal.
  vi.mocked(production.getTaskStatus).mockImplementation(() =>
    Promise.resolve(
      status({
        leases: [
          {
            ...status().leases[0],
            seconds_remaining: Math.max(
              0,
              Math.round(60 - (Date.now() - renewedAt) / 1000),
            ),
          },
        ],
      }),
    ),
  );
  mount(held, {
    ...team,
    project: { ...team.project, lease_minutes: 1 },
  });
  await advance(10);
  for (let second = 0; second < 180; second += 5) await advance(5_000);
  expect(screen.queryByText("This task was taken back")).toBeNull();
  expect(heartbeats().length).toBeGreaterThanOrEqual(9);
});

it("slows status reads to every 30 s while hidden, catches up when shown, and keeps renewing", async () => {
  let hidden = false;
  const visibility = vi
    .spyOn(document, "visibilityState", "get")
    .mockImplementation(() => (hidden ? "hidden" : "visible"));
  mount();
  await advance(10);
  const reads = () => vi.mocked(production.getTaskStatus).mock.calls.length;
  hidden = true;
  const hiddenAt = reads();
  await advance(HIDDEN_WATCH_INTERVAL_MS - WATCH_INTERVAL_MS);
  expect(reads()).toBe(hiddenAt);
  await advance(WATCH_INTERVAL_MS);
  expect(reads()).toBe(hiddenAt + 1);
  const beats = heartbeats().length;
  await advance(HEARTBEAT_INTERVAL_MS);
  expect(heartbeats().length).toBe(beats + 1);
  hidden = false;
  const shownAt = reads();
  document.dispatchEvent(new Event("visibilitychange"));
  await advance(1);
  expect(reads()).toBe(shownAt + 1);
  visibility.mockRestore();
});

it("never renews silently: a failed renewal is shown with a retry", async () => {
  vi.mocked(actions.mutateProduction).mockRejectedValue(
    new ApiError(503, "503 Database is busy"),
  );
  mount();
  await advance(10);
  expect(
    screen.getByText(
      "Could not renew the lease: Database is busy. It will be retried automatically.",
    ),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Renew now" })).toBeEnabled();
});

it("locks editing within 10 s of a reclaim, keeps the draft and offers an export", async () => {
  const created = vi.fn(() => "blob:draft");
  URL.createObjectURL = created;
  URL.revokeObjectURL = vi.fn();
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => undefined);
  mount();
  await advance(10);
  fireEvent.click(screen.getByTestId("edit"));
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({ leases: [], releases: [revoked] }),
  );
  await advance(WATCH_INTERVAL_MS);
  expect(screen.getByText("This task was taken back")).toBeVisible();
  expect(screen.getByTestId("edit")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Export draft" }));
  expect(click).toHaveBeenCalledOnce();
  const blob = (created.mock.calls[0] as unknown as [Blob])[0];
  const reader = new FileReader();
  const read = new Promise<string>((resolve) => {
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
  });
  reader.readAsText(blob);
  await advance(10);
  expect(JSON.parse(await read)).toMatchObject({
    labels: ["draft"],
  });
  const heartbeatCount = heartbeats().length;
  await advance(HEARTBEAT_INTERVAL_MS);
  expect(heartbeats()).toHaveLength(heartbeatCount);
});

it("locks editing when the lease runs out on this page", async () => {
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({
      leases: [{ ...status().leases[0], seconds_remaining: 3 }],
    }),
  );
  vi.mocked(actions.mutateProduction).mockRejectedValue(
    new ApiError(503, "503 Unavailable"),
  );
  mount();
  await advance(10);
  await advance(4_000);
  expect(screen.getByText("This task was taken back")).toBeVisible();
});

it("notices a return for rework and an edit made elsewhere, offering reload or back", async () => {
  const submitted: TaskWorkbench = {
    ...held,
    task: { ...held.task, state: "submitted" },
  };
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({ task: submitted.task, leases: [] }),
  );
  mount(submitted, labelingProject);
  await advance(10);
  expect(screen.queryByRole("button", { name: "Back to list" })).toBeNull();
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({ task: { ...held.task, state: "in_progress" }, leases: [] }),
  );
  await advance(WATCH_INTERVAL_MS);
  expect(screen.getByText("This task was returned for rework.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Back to list" })).toBeVisible();
  vi.mocked(production.getTaskStatus).mockResolvedValue(
    status({
      task: { ...held.task, latest_revision_id: "elsewhere" },
      leases: [],
    }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Reload server revision" }),
  );
  await advance(WATCH_INTERVAL_MS);
  expect(
    screen.getByText("Someone else just saved a newer version of this task."),
  ).toBeVisible();
});

it("turns a save refused for an expired lease into the reclaim lock, without raw server text", async () => {
  vi.mocked(actions.mutateProduction).mockImplementation((name) =>
    name === "save_revision"
      ? Promise.reject(
          new ApiError(
            409,
            "409 Assignment lease expired at 2026-10-30T00:10:00Z. Claim it again to continue",
          ),
        )
      : Promise.resolve({ status: "SUCCEEDED" } as ActionRun),
  );
  mount();
  await advance(10);
  fireEvent.click(screen.getByTestId("edit"));
  await advance(WATCH_INTERVAL_MS);
  expect(screen.getByText("This task was taken back")).toBeVisible();
  expect(screen.queryByText(/Claim it again/)).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Overwrite with my edits" }),
  ).toBeNull();
});
