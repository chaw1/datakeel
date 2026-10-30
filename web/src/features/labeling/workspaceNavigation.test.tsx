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

import { writeWorkspaceSnapshot } from "./session/workspaceSnapshot";
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

it("queues Previous presses made while pages load and lands on the right task across two page edges", async () => {
  const pageOf = (ids: string[], next: string | null) => ({
    ...labelingProject,
    tasks: ids.map((id) => ({
      ...labelingProject.tasks[0],
      id,
      sample_id: `s-${id}`,
    })),
    next_cursor: next,
  });
  const pages: Record<string, ReturnType<typeof pageOf>> = {
    "": pageOf(["t1", "t2"], "p2"),
    p2: pageOf(["t3", "t4"], "p3"),
    p3: pageOf(["t5"], null),
  };
  // Every page and task read resolves late, as on a slow connection.
  const later = <T,>(value: T) =>
    new Promise<T>((resolve) => {
      setTimeout(() => {
        resolve(value);
      }, 100);
    });
  vi.mocked(getProjectWorkbench).mockImplementation((_id, query) =>
    later(pages[query?.cursor ?? ""]),
  );
  vi.mocked(getTaskWorkbench).mockImplementation((id) => later(textTask(id)));
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.project?.tasks.at(0)?.id).toBe("t1");
  });
  await act(async () => {
    await result.current.open("t1");
  });
  for (let index = 0; index < 4; index++)
    await act(async () => {
      await result.current.navigate(1);
    });
  expect(result.current.task?.task.id).toBe("t5");
  expect(result.current.page).toBe(2);
  result.current.cache.clear();
  // Four presses 60 ms apart while each step is still loading: t4, t3 (page edge), t2, t1 (page edge).
  const presses: Promise<void>[] = [];
  for (let index = 0; index < 4; index++) {
    await act(async () => {
      presses.push(result.current.navigate(-1));
      await new Promise((resolve) => setTimeout(resolve, 60));
    });
  }
  await act(async () => {
    await Promise.all(presses);
  });
  await waitFor(() => {
    expect(result.current.task?.task.id).toBe("t1");
  });
  expect(result.current.page).toBe(0);
  expect(result.current.notice).toBeNull();
  expect(result.current.busy).toBe(false);
});
