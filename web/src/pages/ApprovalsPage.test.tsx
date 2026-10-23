import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan } from "../test/actionFixtures";

import { ApprovalsPage } from "./ApprovalsPage";
it("renders pending approvals from the API", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([actionPlan])))),
  );
  render(<ApprovalsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByRole("button", { name: "Approve and delete files" }),
  ).toBeVisible();
});

it("shows the real empty state after a successful empty response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([])))),
  );
  render(<ApprovalsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByText("No actions are waiting for approval."),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("shows a server failure without claiming empty results and retries successfully", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Service unavailable" }), {
        status: 500,
      }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify([actionPlan])));
  vi.stubGlobal("fetch", fetch);
  render(<ApprovalsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "500 Service unavailable",
  );
  expect(
    screen.queryByText("No actions are waiting for approval."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(
    await screen.findByRole("button", { name: "Approve and delete files" }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
});
