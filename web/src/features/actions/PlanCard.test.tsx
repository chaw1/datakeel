import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";

import { PlanCard } from "./PlanCard";

it("approves the displayed digest before executing and links its receipt", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(path.endsWith("/execute") ? actionRun : actionPlan),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<PlanCard plan={actionPlan} onOpenReceipt={open} />);
  await user.click(
    screen.getByRole("button", { name: "Approve and delete files" }),
  );
  await screen.findByRole("region", { name: "Receipt" });
  expect(fetch.mock.calls.map(([path]) => path)).toEqual([
    "/api/approvals/plan-1",
    "/api/actions/plan-1/execute",
  ]);
  expect(fetch).toHaveBeenNthCalledWith(
    1,
    "/api/approvals/plan-1",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        approve: true,
        plan_digest: "plan-digest",
        actor: "local",
        reason: "",
      }),
    }),
  );
  expect(fetch).toHaveBeenNthCalledWith(
    2,
    "/api/actions/plan-1/execute",
    expect.objectContaining({
      body: JSON.stringify({
        plan_digest: "plan-digest",
        actor: "local",
        operation_id: "operation-1",
      }),
    }),
  );
  await user.click(screen.getByRole("link", { name: "View lineage receipt" }));
  expect(open).toHaveBeenCalledWith({
    datasetId: "dataset-1",
    assetId: "run-1",
    eventId: "receipt-1",
  });
});
it("rejects an irreversible plan without executing", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(actionPlan))),
  );
  vi.stubGlobal("fetch", fetch);
  render(<PlanCard plan={actionPlan} onOpenReceipt={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Return" }));
  expect(
    await screen.findByText("The plan was rejected. No action was executed."),
  ).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith(
    "/api/approvals/plan-1",
    expect.objectContaining({
      body: JSON.stringify({
        approve: false,
        plan_digest: "plan-digest",
        actor: "local",
        reason: "",
      }),
    }),
  );
});
it("disables execution for an expired plan", () => {
  vi.stubGlobal("fetch", vi.fn());
  render(
    <PlanCard
      plan={{ ...actionPlan, expires_at: "2020-01-01T00:00:00Z" }}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Approve and delete files" }),
  ).toBeDisabled();
});
it("executes a reversible plan without requesting approval", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(actionRun))),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <PlanCard
      plan={{
        ...actionPlan,
        action_type: "quarantine_files",
        reversible: true,
      }}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Execute action" }));
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/plan-1/execute",
    expect.objectContaining({ method: "POST" }),
  );
});
it("shows a server rejection and does not invent a receipt", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Plan digest mismatch" }), {
          status: 409,
        }),
      ),
    ),
  );
  render(<PlanCard plan={actionPlan} onOpenReceipt={vi.fn()} />);
  await user.click(
    screen.getByRole("button", { name: "Approve and delete files" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Plan digest mismatch",
  );
  expect(
    screen.queryByRole("region", { name: "Receipt" }),
  ).not.toBeInTheDocument();
});

it("retries a failed execute request without approving the plan twice", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(actionPlan)))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Conflict" }), { status: 409 }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(actionRun)));
  vi.stubGlobal("fetch", fetch);
  render(<PlanCard plan={actionPlan} onOpenReceipt={vi.fn()} />);
  await user.click(
    screen.getByRole("button", { name: "Approve and delete files" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("409 Conflict");
  await user.click(
    screen.getByRole("button", { name: "Approve and delete files" }),
  );
  expect(await screen.findByRole("region", { name: "Receipt" })).toBeVisible();
  expect(fetch.mock.calls.map((call: unknown[]) => call[0])).toEqual([
    "/api/approvals/plan-1",
    "/api/actions/plan-1/execute",
    "/api/actions/plan-1/execute",
  ]);
});
