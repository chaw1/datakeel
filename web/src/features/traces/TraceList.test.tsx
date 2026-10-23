import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { cost, trace } from "../../test/agentFixtures";

import { CostTable } from "./CostTable";
import { TraceList } from "./TraceList";

it("renders measured segment tokens, cache hit, latency, and precise cost", () => {
  render(<TraceList traces={[trace]} />);
  const chart = screen.getByRole("region", { name: "Input token segments" });
  expect(within(chart).getByText("instructions")).toBeVisible();
  expect(within(chart).getByText("40")).toBeVisible();
  expect(within(chart).getByText("60")).toBeVisible();
  expect(within(chart).getByText("Total input: 100 tokens")).toBeVisible();
  expect(screen.getByText("40.0%")).toBeVisible();
  expect(screen.getByText("12.5 ms")).toBeVisible();
  expect(screen.getByText("$0.000240")).toBeVisible();
});
it("links a cost summary row to its conversation traces", async () => {
  const user = userEvent.setup();
  const select = vi.fn();
  render(<CostTable costs={[cost]} onConversation={select} />);
  await user.click(
    screen.getByRole("button", { name: "View trace for conversation-1" }),
  );
  expect(select).toHaveBeenCalledWith("conversation-1");
});

it("labels unknown provider billing as an estimate without displaying zero measured usage", () => {
  render(
    <TraceList
      traces={[
        {
          ...trace,
          billing_status: "unknown",
          accounted_tokens: 4096,
          usage: {
            input_tokens: 0,
            output_tokens: 0,
            cache_read_tokens: 0,
            cache_write_tokens: 0,
          },
          budget_exceeded: true,
          cost_usd: "0.03",
        },
      ]}
    />,
  );
  expect(
    screen.getByText("Billing unknown (conservative estimate)"),
  ).toBeVisible();
  expect(screen.getByText("Tokens charged to budget: 4,096")).toBeVisible();
  expect(
    screen.getByText("Budget exceeded; tools were not executed."),
  ).toBeVisible();
  expect(
    screen.queryByRole("region", { name: "Input token segments" }),
  ).not.toBeInTheDocument();
});
it("shows the estimated contribution in aggregated costs", () => {
  render(
    <CostTable
      costs={[{ ...cost, unknown_calls: 2, unknown_cost_usd: "0.01" }]}
      onConversation={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("columnheader", { name: "Unknown billing calls" }),
  ).toBeVisible();
  expect(screen.getByText("$0.010000")).toBeVisible();
});
