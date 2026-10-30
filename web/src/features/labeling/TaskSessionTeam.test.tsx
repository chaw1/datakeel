import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import * as production from "../../api/production";
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
