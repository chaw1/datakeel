import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionRun } from "../test/actionFixtures";

import { ActionRunsPage } from "./ActionRunsPage";
it("renders action history and a persisted receipt", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([actionRun])))),
  );
  render(<ActionRunsPage onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByRole("link", { name: "View lineage receipt" }),
  ).toBeVisible();
});

it("filters denied attempts separately from successful executions", async () => {
  const denied = {
    ...actionRun,
    id: "denied-run",
    status: "DENIED",
    reason: "Human approval was rejected",
    error: "Legacy error detail",
    receipt: null,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify([actionRun, denied]))),
    ),
  );
  const user = userEvent.setup();
  render(<ActionRunsPage onOpenReceipt={vi.fn()} />);
  await screen.findByText("denied-run");
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Filter run status" }),
    "DENIED",
  );
  expect(screen.getByText("Human approval was rejected")).toBeVisible();
  expect(screen.queryByText("Legacy error detail")).not.toBeInTheDocument();
  expect(screen.getByText("Denied", { selector: ".badge" })).toHaveClass("red");
  expect(screen.queryByText(actionRun.id)).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Receipt" })).toHaveClass(
    "receipt-failed",
  );
});

it("shows the real empty state after a successful empty response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([])))),
  );
  render(<ActionRunsPage onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByText("No actions have been executed yet."),
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
    .mockResolvedValueOnce(new Response(JSON.stringify([actionRun])));
  vi.stubGlobal("fetch", fetch);
  render(<ActionRunsPage onOpenReceipt={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "500 Service unavailable",
  );
  expect(
    screen.queryByText("No actions have been executed yet."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(
    await screen.findByRole("link", { name: "View lineage receipt" }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
});
