import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import { dataset, imageFile, version } from "../../test/fixtures";

import { EvidenceExtraction } from "./EvidenceExtraction";
import { extractionInput } from "./extraction";

import type { ActionRun } from "../../api/types";

const source = {
  ...version,
  id: "original-version",
  manifest: [
    {
      ...imageFile,
      metadata: {
        evidence_sample: {
          sample_key: "train/sample/image.png",
          split: "train",
          caption: null,
          annotation: null,
        },
      },
    },
  ],
};
const prepared = {
  ...actionPlan,
  action_type: "run_pipeline",
  reversible: true,
};
const queued: ActionRun = {
  ...actionRun,
  action_type: "run_pipeline",
  status: "QUEUED",
  receipt: null,
  task_id: "pipeline-task",
};
function api() {
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/versions")
            ? [
                { ...source, id: "derived", created_at: source.created_at + 1 },
                source,
              ]
            : path.endsWith("/prepare")
              ? prepared
              : path.endsWith("/execute")
                ? queued
                : [queued],
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
afterEach(() => {
  vi.useRealTimers();
});

it("prepares a pinned evidence pipeline and executes only after the plan is reviewed", async () => {
  const fetch = api();
  const changed = vi.fn();
  const user = userEvent.setup();
  render(<EvidenceExtraction datasetId={dataset.id} onDataChanged={changed} />);
  await user.click(
    await screen.findByRole("button", { name: "Prepare evidence extraction" }),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/run_pipeline/prepare",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify(extractionInput(dataset.id, source.id)),
    }),
  );
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  await user.click(
    await screen.findByRole("button", { name: "Execute action" }),
  );
  expect(
    await screen.findByRole("link", { name: "Open pipeline task" }),
  ).toHaveAttribute("href", "#/runs?type=pipeline&run=pipeline-task");
  expect(screen.getByRole("link", { name: "Open action run" })).toHaveAttribute(
    "href",
    "#/object/action_run/run-1?tab=relations",
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/plan-1/execute",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        plan_digest: actionPlan.plan_digest,
        actor: "local",
        operation_id: actionPlan.operation_id,
      }),
    }),
  );
  expect(
    fetch.mock.calls.some(([path]) => path.startsWith("/api/approvals")),
  ).toBe(false);
  expect(changed).toHaveBeenCalledOnce();
});

it("keeps an explicitly selected evidence source even when it is not the oldest version", async () => {
  const fetch = api();
  const user = userEvent.setup();
  render(<EvidenceExtraction datasetId={dataset.id} sourceVersion="derived" />);
  await user.click(
    await screen.findByRole("button", { name: "Prepare evidence extraction" }),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/run_pipeline/prepare",
    expect.objectContaining({
      body: JSON.stringify(extractionInput(dataset.id, "derived")),
    }),
  );
});

it("retries a version read failure and a failed prepare without starting a task", async () => {
  const fetch = api();
  fetch.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: "temporarily unavailable" }), {
      status: 503,
    }),
  );
  const user = userEvent.setup();
  render(<EvidenceExtraction datasetId={dataset.id} />);
  await user.click(await screen.findByRole("button", { name: "Retry" }));
  const prepare = await screen.findByRole("button", {
    name: "Prepare evidence extraction",
  });
  fetch.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: "source changed" }), { status: 409 }),
  );
  await user.click(prepare);
  expect(await screen.findByRole("alert")).toHaveTextContent("source changed");
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  await user.click(prepare);
  expect(
    await screen.findByRole("button", { name: "Execute action" }),
  ).toBeVisible();
});

it.each(["SUCCEEDED", "FAILED"] as const)(
  "polls a queued run to %s and only refreshes evidence on success",
  async (status) => {
    const fetch = api();
    const changed = vi.fn();
    const complete = vi.fn();
    const user = userEvent.setup();
    const view = render(
      <EvidenceExtraction
        datasetId={dataset.id}
        onDataChanged={changed}
        onComplete={complete}
      />,
    );
    await user.click(
      await screen.findByRole("button", {
        name: "Prepare evidence extraction",
      }),
    );
    const execute = await screen.findByRole("button", {
      name: "Execute action",
    });
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(execute);
      await Promise.resolve();
    });
    expect(
      screen.getByRole("link", { name: "Open pipeline task" }),
    ).toBeVisible();
    fetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify([{ ...queued, status, receipt: actionRun.receipt }]),
      ),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(changed).toHaveBeenCalledTimes(2);
    expect(complete).toHaveBeenCalledTimes(status === "SUCCEEDED" ? 1 : 0);
    expect(
      screen.getByRole("link", { name: "View lineage receipt" }),
    ).toBeVisible();
    const count = fetch.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(fetch).toHaveBeenCalledTimes(count);
    view.unmount();
  },
);

it("stops pending run polling after leaving the evidence workspace", async () => {
  const fetch = api();
  const user = userEvent.setup();
  const view = render(<EvidenceExtraction datasetId={dataset.id} />);
  await user.click(
    await screen.findByRole("button", { name: "Prepare evidence extraction" }),
  );
  const execute = await screen.findByRole("button", {
    name: "Execute action",
  });
  vi.useFakeTimers();
  await act(async () => {
    fireEvent.click(execute);
    await Promise.resolve();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/runs",
    expect.objectContaining({ method: "GET" }),
  );
  view.unmount();
  const count = fetch.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10000);
  });
  expect(fetch).toHaveBeenCalledTimes(count);
});

it("does not silently substitute another version when the requested source is gone", async () => {
  const fetch = api();
  render(<EvidenceExtraction datasetId={dataset.id} sourceVersion="gone" />);
  await waitFor(() => {
    expect(
      screen.getByText(
        "No source version is available for evidence extraction.",
      ),
    ).toBeVisible();
  });
  expect(
    screen.queryByRole("button", { name: "Prepare evidence extraction" }),
  ).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("blocks preparation during composition and prevents native composition Enter", async () => {
  const fetch = api();
  const user = userEvent.setup();
  render(<EvidenceExtraction datasetId={dataset.id} />);
  const prepare = await screen.findByRole("button", {
    name: "Prepare evidence extraction",
  });
  fireEvent.compositionStart(prepare);
  await user.click(prepare);
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/prepare"))).toBe(
    false,
  );
  expect(fireEvent.keyDown(prepare, { key: "Enter", isComposing: true })).toBe(
    false,
  );
  fireEvent.compositionEnd(prepare);
  expect(fireEvent.keyDown(prepare, { key: "Enter", isComposing: true })).toBe(
    false,
  );
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/prepare"))).toBe(
    false,
  );
  await user.click(prepare);
  expect(
    await screen.findByRole("button", { name: "Execute action" }),
  ).toBeVisible();
});
