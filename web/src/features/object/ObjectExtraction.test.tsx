import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import * as objects from "../../api/objects";
import { actionPlan, actionRun } from "../../test/actionFixtures";
import { mention } from "../../test/evidenceFixtures";
import { dataset, imageFile, version } from "../../test/fixtures";

import { ObjectPage } from "./ObjectPage";
import { objectData, sample } from "./testFixtures";

import type { ObjectData } from "../../api/objects";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("preserves a queued extraction across object reload and refreshes evidence after completion", async () => {
  const source = {
    ...version,
    manifest: [
      {
        ...imageFile,
        metadata: {
          evidence_sample: { sample_key: "train/image.png", split: "train" },
        },
      },
    ],
  };
  const data = { ...objectData, versions: [source] };
  const load = vi.spyOn(objects, "loadObject").mockResolvedValue(data);
  let complete = false;
  let resolveReload!: (value: ObjectData) => void;
  const delayedReload = new Promise<ObjectData>((resolve) => {
    resolveReload = resolve;
  });
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/prepare")
            ? { ...actionPlan, action_type: "run_pipeline", reversible: true }
            : path.endsWith("/execute")
              ? {
                  ...actionRun,
                  action_type: "run_pipeline",
                  status: "QUEUED",
                  receipt: null,
                  task_id: "task-queued",
                }
              : path === "/api/actions/runs"
                ? [
                    {
                      ...actionRun,
                      action_type: "run_pipeline",
                      status: complete ? "SUCCEEDED" : "QUEUED",
                      task_id: "task-queued",
                    },
                  ]
                : path.endsWith("/versions")
                  ? [source]
                  : path === "/api/evidence/query"
                    ? {
                        items: [
                          { ...sample, assertions: complete ? [mention] : [] },
                        ],
                        next_cursor: null,
                        total: 1,
                        truncated: false,
                      }
                    : dataset,
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const changed = vi.fn();
  render(
    <ObjectPage
      target={{ ...objectData.target, tab: "evidence" }}
      onDataChanged={changed}
    />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Prepare evidence extraction" }),
  );
  const execute = await screen.findByRole("button", { name: "Execute action" });
  load.mockReturnValueOnce(delayedReload);
  vi.useFakeTimers();
  await act(async () => {
    fireEvent.click(execute);
    await Promise.resolve();
  });
  expect(changed).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("heading", { level: 1, name: data.name }),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Open pipeline task" }),
  ).toHaveAttribute("href", "#/runs?type=pipeline&run=task-queued");
  expect(
    screen.queryByRole("button", { name: "Prepare evidence extraction" }),
  ).not.toBeInTheDocument();
  await act(async () => {
    resolveReload({ ...data });
    await delayedReload;
  });
  expect(screen.getByRole("link", { name: "Open action run" })).toBeVisible();
  complete = true;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(screen.getByRole("table", { name: "Evidence results" })).toBeVisible();
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/prepare")),
  ).toHaveLength(1);
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/execute")),
  ).toHaveLength(1);
  expect(fetch.mock.calls.some(([path]) => path === "/api/actions/runs")).toBe(
    true,
  );
});
