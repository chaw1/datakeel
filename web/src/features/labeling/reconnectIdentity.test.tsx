import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as production from "../../api/production";
import { translator } from "../../i18n/context";
import {
  labelingIndex,
  labelingProject,
  labelingTask,
} from "../../test/labelingFixtures";

import * as actions from "./actions";
import { TaskSession } from "./TaskSession";
import { useLabelingWorkspace } from "./useLabelingWorkspace";

import type { AnnotationRecord, WorkbenchIndex } from "../../api/production";

vi.mock("../../api/production", () => ({
  getWorkbench: vi.fn(),
  getProjectWorkbench: vi.fn(),
  getTaskWorkbench: vi.fn(),
}));
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
    <button
      type="button"
      onClick={() => {
        onChange({ ...value, labels: ["cat"] });
      }}
    >
      {translator("en")("wbEditorAddBox")}
    </button>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

it("blocks an old save adapter synchronously until reconnect identity is verified", async () => {
  let online = true;
  vi.spyOn(navigator, "onLine", "get").mockImplementation(() => online);
  let verify: ((value: WorkbenchIndex) => void) | undefined;
  vi.mocked(production.getWorkbench)
    .mockResolvedValueOnce(labelingIndex)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          verify = resolve;
        }),
    );
  vi.mocked(production.getProjectWorkbench).mockResolvedValue(labelingProject);
  vi.mocked(production.getTaskWorkbench).mockResolvedValue({
    ...labelingTask,
    sample: { ...labelingTask.sample, media_type: "text/plain", text: "Text" },
  });
  let workspace: ReturnType<typeof useLabelingWorkspace> | undefined;
  function Harness() {
    workspace = useLabelingWorkspace(new URLSearchParams());
    const state = workspace;
    return state.task && state.project && state.index ? (
      <TaskSession
        key={state.index.actor}
        task={state.task}
        project={state.project}
        actor={state.index.actor}
        canSync={state.verified}
        isIdentityVerified={state.isIdentityVerified}
        onChanged={state.changed}
        onSnapshot={state.receiveTask}
        onNavigate={() => undefined}
        registerGuard={state.registerGuard}
      />
    ) : null;
  }
  render(<Harness />);
  await waitFor(() => {
    expect(workspace?.verified).toBe(true);
  });
  await act(async () => {
    await workspace?.open("task-1");
  });
  act(() => {
    online = false;
    window.dispatchEvent(new Event("offline"));
  });
  fireEvent.click(screen.getByRole("button", { name: "Add box (B)" }));
  const oldNavigate = workspace?.navigate;
  expect(oldNavigate).toBeTypeOf("function");
  let leaving: Promise<void> | undefined;
  act(() => {
    online = true;
    window.dispatchEvent(new Event("online"));
    leaving = oldNavigate?.(0);
  });
  await act(async () => {
    await leaving;
  });
  expect(workspace?.verified).toBe(false);
  expect(workspace?.isIdentityVerified()).toBe(false);
  expect(workspace?.task?.task.id).toBe("task-1");
  expect(actions.mutateProduction).not.toHaveBeenCalled();
  expect(Object.values(localStorage).join(" ")).toContain('"labels":["cat"]');
  const effective = { actor: "actor-b", scopes: ["*"], zero_users: false };
  vi.mocked(production.getProjectWorkbench).mockResolvedValue({
    ...labelingProject,
    effective_scopes: effective,
  });
  await act(async () => {
    verify?.({
      ...labelingIndex,
      actor: "actor-b",
      effective_scopes: effective,
    });
    await Promise.resolve();
  });
  expect(workspace?.index?.actor).toBe("actor-b");
  expect(workspace?.task).toBeNull();
  expect(actions.mutateProduction).not.toHaveBeenCalled();
});
