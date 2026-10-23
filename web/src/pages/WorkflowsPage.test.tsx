import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { dataset } from "../test/fixtures";
import {
  completedWorkflow,
  pausedWorkflow,
  workflow,
  workflowStream,
} from "../test/workflowFixtures";

import { WorkflowsPage } from "./WorkflowsPage";

function mockApi() {
  const requests: { path: string; body: unknown }[] = [];
  let run = pausedWorkflow;
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        requests.push({
          path,
          body: JSON.parse(
            typeof init.body === "string" ? init.body : "null",
          ) as unknown,
        });
        if (path.endsWith("/resume")) run = completedWorkflow;
        return Promise.resolve(workflowStream(run));
      }
      const value =
        path === "/api/workflows"
          ? [workflow]
          : path === "/api/workflows/runs"
            ? [run]
            : path.includes("/runs/")
              ? run
              : workflow;
      return Promise.resolve(new Response(JSON.stringify(value)));
    }),
  );
  return requests;
}

it("starts explicitly, records the run URL, and continues only from a paused run", async () => {
  window.location.hash = `#/workflows?workflow=${workflow.id}&dataset=${dataset.id}`;
  const requests = mockApi();
  render(<WorkflowsPage datasets={[dataset]} onDataChanged={vi.fn()} />);
  const submit = await screen.findByRole("button", { name: "Run workflow" });
  expect(requests).toEqual([]);
  await userEvent.click(submit);
  const details = await screen.findByRole("region", { name: "Run details" });
  expect(details).toHaveAttribute("data-run-status", "PAUSED");
  expect(window.location.hash).toBe("#/workflows?run=workflow-run-1");
  expect(
    within(details).getByRole("link", { name: "Review approval" }),
  ).toHaveAttribute(
    "href",
    "#/approvals?plan=plan-1&workflow_run=workflow-run-1",
  );
  expect(requests[0].body).toHaveProperty("idempotency_key");
  expect(requests[0]).toMatchObject({
    path: `/api/workflows/${workflow.id}/runs`,
    body: {
      inputs: { dataset_id: dataset.id, quality_max: 60 },
    },
  });
  await userEvent.click(
    within(details).getByRole("button", { name: "Continue after approval" }),
  );
  await waitFor(() => {
    expect(details).toHaveAttribute("data-run-status", "SUCCEEDED");
  });
  expect(requests).toHaveLength(2);
  expect(requests[1].body).toHaveProperty("idempotency_key");
  expect(requests[1]).toMatchObject({
    path: "/api/workflows/runs/workflow-run-1/resume",
    body: { plan_id: "plan-1" },
  });
  expect(
    screen.queryByRole("button", { name: "Continue after approval" }),
  ).not.toBeInTheDocument();
  expect(
    await within(
      screen.getByRole("region", { name: "Workflow history" }),
    ).findByText("Succeeded"),
  ).toBeVisible();
});

it("reloads a saved interrupted run and never offers resume", async () => {
  window.location.hash = "#/workflows?run=workflow-run-1";
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path === "/api/workflows"
              ? [workflow]
              : path === "/api/workflows/runs"
                ? []
                : path.includes("/runs/")
                  ? {
                      ...pausedWorkflow,
                      status: "INTERRUPTED",
                      error: "Client disconnected",
                      pending_plan_id: null,
                    }
                  : workflow,
          ),
        ),
      ),
    ),
  );
  render(<WorkflowsPage datasets={[]} onDataChanged={vi.fn()} />);
  expect(await screen.findByText("Client disconnected")).toBeVisible();
  expect(
    screen.getByText(/cannot continue from the interrupted step/),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Continue after approval" }),
  ).not.toBeInTheDocument();
});

it("keeps the stream open after its first snapshot and explains a missing done event", async () => {
  window.location.hash = `#/workflows?workflow=${workflow.id}&dataset=${dataset.id}`;
  let writer: ReadableStreamDefaultController<Uint8Array> | undefined;
  let signal: AbortSignal | null | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(value) {
      writer = value;
    },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        signal = init.signal;
        return Promise.resolve(
          new Response(stream, {
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify(
            path === "/api/workflows"
              ? [workflow]
              : path === "/api/workflows/runs"
                ? []
                : path.includes("/runs/")
                  ? pausedWorkflow
                  : workflow,
          ),
        ),
      );
    }),
  );
  render(<WorkflowsPage datasets={[dataset]} onDataChanged={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Run workflow" }),
  );
  await act(async () => {
    writer?.enqueue(
      new TextEncoder().encode(
        `event: run\ndata: ${JSON.stringify({ id: "live", event: "run", run: { ...pausedWorkflow, status: "RUNNING" } })}\n\n`,
      ),
    );
    await Promise.resolve();
  });
  expect(
    await screen.findByRole("region", { name: "Run details" }),
  ).toHaveAttribute("data-run-status", "RUNNING");
  expect(signal?.aborted).toBe(false);
  expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
  await act(async () => {
    writer?.close();
    await Promise.resolve();
  });
  expect(await screen.findByText(/stream was interrupted/)).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: "Reload saved run" }),
  );
  expect(
    await screen.findByRole("button", { name: "Continue after approval" }),
  ).toBeVisible();
});

it("keeps an unapproved run paused and reports its server denial without calling it interrupted", async () => {
  window.location.hash = "#/workflows?run=workflow-run-1";
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Signed approval required" }), {
            status: 403,
          }),
        );
      return Promise.resolve(
        new Response(
          JSON.stringify(
            path === "/api/workflows"
              ? [workflow]
              : path === "/api/workflows/runs"
                ? [pausedWorkflow]
                : path.includes("/runs/")
                  ? pausedWorkflow
                  : workflow,
          ),
        ),
      );
    }),
  );
  render(<WorkflowsPage datasets={[]} onDataChanged={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue after approval" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "403 Signed approval required",
  );
  expect(
    screen.queryByText(/The stream was interrupted/),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Run details" })).toHaveAttribute(
    "data-run-status",
    "PAUSED",
  );
});
