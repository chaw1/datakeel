import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  getProjectWorkbench,
  getTaskWorkbench,
  getWorkbench,
} from "../../api/production";
import {
  labelingIndex,
  labelingProject,
  labelingTask,
} from "../../test/labelingFixtures";

import { draftKey } from "./session/draftStorage";
import {
  readWorkspaceSnapshot,
  writeWorkspaceSnapshot,
} from "./session/workspaceSnapshot";
import { useLabelingWorkspace } from "./useLabelingWorkspace";

import type { TaskWorkbench } from "../../api/production";

vi.mock("../../api/production", () => ({
  getWorkbench: vi.fn(),
  getProjectWorkbench: vi.fn(),
  getTaskWorkbench: vi.fn(),
}));

function textTask(id = "task-1"): TaskWorkbench {
  const task = labelingProject.tasks.find((item) => item.id === id) ?? {
    ...labelingTask.task,
    id,
  };
  return {
    ...labelingTask,
    task,
    sample: {
      ...labelingTask.sample,
      id: task.sample_id,
      media_type: "text/plain",
      content_url: "",
      text: "Generated text",
    },
  };
}

function boot() {
  expect(
    writeWorkspaceSnapshot({
      index: labelingIndex,
      project: labelingProject,
      task: textTask(),
    }),
  ).toBe(true);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(getWorkbench).mockReset().mockResolvedValue(labelingIndex);
  vi.mocked(getProjectWorkbench).mockReset().mockResolvedValue(labelingProject);
  vi.mocked(getTaskWorkbench)
    .mockReset()
    .mockImplementation((id) => Promise.resolve(textTask(id)));
});
afterEach(() => {
  sessionStorage.clear();
});

it("does not mount a cached task under a different project requested in the URL", async () => {
  boot();
  const other = {
    ...labelingProject,
    project: { ...labelingProject.project, id: "other-project" },
    tasks: [],
  };
  vi.mocked(getWorkbench).mockResolvedValue({
    ...labelingIndex,
    projects: [labelingProject.project, other.project],
  });
  vi.mocked(getProjectWorkbench).mockResolvedValue(other);
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=other-project")),
  );
  expect(result.current.task).toBeNull();
  expect(result.current.project).toBeNull();
  await waitFor(() => {
    expect(result.current.project?.project.id).toBe("other-project");
  });
  expect(result.current.task).toBeNull();
  expect(getTaskWorkbench).not.toHaveBeenCalled();
});

it("restores the same tab's offline task and keeps syncing disabled until identity revalidation", async () => {
  boot();
  const key = draftKey("local:project:task-1");
  const annotation = {
    sample_id: "sample-1",
    annotator_id: "local",
    labels: ["retained"],
  };
  localStorage.setItem(
    key,
    JSON.stringify({
      version: 1,
      annotation,
      base: { annotation: { ...annotation, labels: [] }, revisionId: null },
    }),
  );
  vi.mocked(getWorkbench).mockRejectedValueOnce(new TypeError("Offline"));
  vi.mocked(getProjectWorkbench).mockRejectedValueOnce(
    new TypeError("Offline"),
  );
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  expect(result.current.task?.task.id).toBe("task-1");
  expect(result.current.verified).toBe(false);
  await waitFor(() => {
    expect(result.current.error).toBe("Offline");
  });
  expect(localStorage.getItem(key)).toContain("retained");
  act(() => {
    window.dispatchEvent(new Event("online"));
  });
  await waitFor(() => {
    expect(result.current.verified).toBe(true);
  });
  expect(result.current.index?.actor).toBe("local");
  expect(result.current.task?.task.id).toBe("task-1");
  expect(getWorkbench).toHaveBeenCalledTimes(2);
});

it.each([
  [["production:review", "production:claim"], "reviews", "review"],
  [["production:manage", "production:finalize"], "cockpit", "all"],
  [["production:annotate", "production:review"], "tasks", "mine"],
] as const)(
  "restores a group snapshot with scopes %j into its first navigable view",
  async (scopes, expected, request) => {
    const group = {
      ...labelingProject,
      project: { ...labelingProject.project, workflow_tier: "group" as const },
      effective_scopes: {
        actor: "local",
        zero_users: false,
        scopes: [...scopes],
      },
    };
    expect(
      writeWorkspaceSnapshot({
        index: labelingIndex,
        project: group,
        task: null,
      }),
    ).toBe(true);
    vi.mocked(getProjectWorkbench).mockResolvedValue(group);
    const { result } = renderHook(() =>
      useLabelingWorkspace(new URLSearchParams("project=project")),
    );
    expect(result.current.view).toBe(expected);
    await waitFor(() => {
      expect(result.current.project).not.toBeNull();
    });
    expect(result.current.view).toBe(expected);
    expect(getProjectWorkbench).toHaveBeenLastCalledWith(
      "project",
      expect.objectContaining({ view: request }),
    );
  },
);

it("corrects a stale view when fresh scopes no longer include it", async () => {
  const reviewer = {
    ...labelingProject,
    project: { ...labelingProject.project, workflow_tier: "group" as const },
    effective_scopes: {
      actor: "local",
      zero_users: false,
      scopes: ["production:annotate", "production:review"],
    },
  };
  vi.mocked(getProjectWorkbench).mockResolvedValue(reviewer);
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.view).toBe("tasks");
  });
  await act(async () => {
    await result.current.selectView("reviews");
  });
  vi.mocked(getProjectWorkbench).mockResolvedValue({
    ...reviewer,
    effective_scopes: {
      ...reviewer.effective_scopes,
      scopes: ["production:annotate"],
    },
  });
  act(() => {
    result.current.changed();
  });
  await waitFor(() => {
    expect(result.current.view).toBe("tasks");
  });
});

it("sends package filtering to the server before paging and resets the cursor when it changes", async () => {
  vi.mocked(getProjectWorkbench).mockResolvedValue({
    ...labelingProject,
    next_cursor: "next-page",
  });
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.project).not.toBeNull();
  });
  await act(async () => {
    await result.current.selectPackage("package-two");
  });
  await waitFor(() => {
    expect(getProjectWorkbench).toHaveBeenLastCalledWith(
      "project",
      expect.objectContaining({ packageId: "package-two", cursor: "" }),
    );
  });
  await act(async () => {
    await result.current.paginate(1);
  });
  await waitFor(() => {
    expect(getProjectWorkbench).toHaveBeenLastCalledWith(
      "project",
      expect.objectContaining({
        packageId: "package-two",
        cursor: "next-page",
      }),
    );
  });
  expect(result.current.page).toBe(1);
  await act(async () => {
    await result.current.selectPackage("package-three");
  });
  await waitFor(() => {
    expect(getProjectWorkbench).toHaveBeenLastCalledWith(
      "project",
      expect.objectContaining({ packageId: "package-three", cursor: "" }),
    );
  });
  expect(result.current.page).toBe(0);
});

it("moves across task pages with Next/Previous and reports the true ends", async () => {
  const second = {
    ...labelingProject,
    tasks: [{ ...labelingProject.tasks[0], id: "task-3", sample_id: "s3" }],
    next_cursor: null,
  };
  vi.mocked(getProjectWorkbench).mockImplementation((_id, query) =>
    Promise.resolve(
      query?.cursor === "page-2"
        ? second
        : { ...labelingProject, next_cursor: "page-2" },
    ),
  );
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.project).not.toBeNull();
  });
  await act(async () => {
    await result.current.open("task-2");
  });
  expect(result.current.navigation).toEqual({ previous: true, next: true });
  await act(async () => {
    await result.current.navigate(1);
  });
  expect(result.current.task?.task.id).toBe("task-3");
  expect(result.current.page).toBe(1);
  expect(result.current.navigation).toEqual({ previous: true, next: false });
  await act(async () => {
    await result.current.navigate(1);
  });
  expect(result.current.task?.task.id).toBe("task-3");
  expect(result.current.notice).toBe("last");
  await act(async () => {
    await result.current.navigate(-1);
  });
  await waitFor(() => {
    expect(result.current.task?.task.id).toBe("task-2");
  });
  expect(result.current.page).toBe(0);
  expect(result.current.notice).toBeNull();
  expect(getProjectWorkbench).toHaveBeenCalledWith(
    "project",
    expect.objectContaining({ cursor: "page-2", limit: 100 }),
  );
});

it("stops at the first task when Previous is requested instead of wrapping to the last", async () => {
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.project).not.toBeNull();
  });
  await act(async () => {
    await result.current.open("task-1");
  });
  expect(result.current.task?.task.id).toBe("task-1");
  await act(async () => {
    await result.current.navigate(-1);
  });
  expect(result.current.task?.task.id).toBe("task-1");
});

it("clears busy on a cached navigation and ignores a superseded request's late failure", async () => {
  const slow = deferred<TaskWorkbench>();
  vi.mocked(getTaskWorkbench).mockImplementation((id) =>
    id === "slow-task" ? slow.promise : Promise.resolve(textTask(id)),
  );
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.project).not.toBeNull();
  });
  result.current.cache.set("task-1", textTask());
  let opening!: Promise<void>;
  await act(async () => {
    opening = result.current.open("slow-task");
    await Promise.resolve();
  });
  expect(result.current.busy).toBe(true);
  await act(async () => {
    await result.current.open("task-1");
  });
  expect(result.current.task?.task.id).toBe("task-1");
  expect(result.current.busy).toBe(false);
  await act(async () => {
    slow.reject(new Error("Superseded request"));
    await opening;
  });
  expect(result.current.task?.task.id).toBe("task-1");
  expect(result.current.busy).toBe(false);
  expect(result.current.error).toBe("");
});

it("persists a clean saved head immediately and restores it on an offline reload", async () => {
  boot();
  const first = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(first.result.current.verified).toBe(true);
  });
  const annotation = {
    sample_id: "sample-1",
    annotator_id: "local",
    labels: ["saved-label"],
  };
  const fresh: TaskWorkbench = {
    ...textTask(),
    task: { ...textTask().task, latest_revision_id: "saved-head" },
    revisions: [
      {
        id: "saved-head",
        task_id: "task-1",
        actor: "local",
        annotation,
        previous_revision_id: null,
        source: "human",
        created_at: "2026-10-30T00:00:00Z",
      },
    ],
  };
  act(() => {
    first.result.current.receiveTask(fresh);
    expect(readWorkspaceSnapshot("local")?.task?.task.latest_revision_id).toBe(
      "saved-head",
    );
  });
  expect(first.result.current.cache.peek("task-1")).toEqual(fresh);
  act(() => {
    first.result.current.receiveTask(textTask("task-2"));
  });
  expect(first.result.current.task?.task.id).toBe("task-1");
  expect(first.result.current.cache.peek("task-2")?.task.id).toBe("task-2");
  first.unmount();
  vi.mocked(getWorkbench).mockRejectedValueOnce(new TypeError("Offline"));
  vi.mocked(getProjectWorkbench).mockRejectedValueOnce(
    new TypeError("Offline"),
  );
  const next = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  expect(next.result.current.verified).toBe(false);
  expect(next.result.current.task?.task.latest_revision_id).toBe("saved-head");
  expect(next.result.current.task?.revisions[0].annotation).toEqual(annotation);
  await waitFor(() => {
    expect(next.result.current.error).toBe("Offline");
  });
});
