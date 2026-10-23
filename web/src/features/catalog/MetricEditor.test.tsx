import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { metric, metricPlan, metricRun, mockCatalogFetch } from "./fixtures";
import { MetricEditor } from "./MetricEditor";

it("prepares a changed measure for review and executes only when the plan is confirmed", async () => {
  const fetch = mockCatalogFetch();
  const changed = vi.fn();
  const user = userEvent.setup();
  render(
    <MetricEditor card={metric} onChanged={changed} onOpenReceipt={vi.fn()} />,
  );
  await screen.findByRole("option", { name: "list_amount" });
  await user.selectOptions(
    screen.getByLabelText("Amount or count field"),
    "ecommerce/main/orders/list_amount",
  );
  await user.clear(screen.getByLabelText("Also called"));
  await user.type(
    screen.getByLabelText("Also called"),
    "Retail total, Online receipts",
  );
  await user.clear(screen.getByLabelText("Value"));
  await user.type(screen.getByLabelText("Value"), "12.5");
  await user.click(screen.getByRole("button", { name: "Review change" }));
  expect(
    await screen.findByRole("article", { name: "Action plan: update_metric" }),
  ).toBeVisible();
  const prepared = fetch.mock.calls.find(([path]) => path.endsWith("/prepare"));
  expect(prepared?.[1]?.body).toBe(
    JSON.stringify({
      definition: {
        ...metric.definition,
        synonyms: ["Retail total", "Online receipts"],
        filters: [
          { column: "ecommerce/main/orders/status", op: "eq", value: 12.5 },
        ],
        measure: {
          ...metric.definition.measure,
          column: "ecommerce/main/orders/list_amount",
        },
      },
    }),
  );
  expect(fetch).not.toHaveBeenCalledWith(
    expect.stringContaining("/execute"),
    expect.any(Object),
  );
  await user.click(screen.getByRole("button", { name: "Execute action" }));
  expect(
    await screen.findByText(
      "New metric version saved. Future answers use this definition.",
    ),
  ).toBeVisible();
  expect(changed).toHaveBeenCalledOnce();
});

it("shows prepare failures and keeps the edited form available for retry", async () => {
  const fetch = mockCatalogFetch();
  fetch.mockImplementation((input: string) =>
    Promise.resolve(
      input.endsWith("/prepare")
        ? new Response(JSON.stringify({ detail: "Definition changed" }), {
            status: 409,
          })
        : new Response(
            JSON.stringify({
              columns: [],
              table: {},
              metrics: [],
              owners: [],
              neighbors: {},
            }),
          ),
    ),
  );
  const user = userEvent.setup();
  render(
    <MetricEditor card={metric} onChanged={vi.fn()} onOpenReceipt={vi.fn()} />,
  );
  await user.click(screen.getByRole("button", { name: "Review change" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Definition changed",
  );
  expect(screen.getByLabelText("Metric name")).toHaveValue("Retail revenue");
});

it("keeps failed execution receipts visible without claiming the change succeeded", async () => {
  const fetch = mockCatalogFetch();
  fetch.mockImplementation((input: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          input.endsWith("/prepare")
            ? metricPlan
            : input.endsWith("/execute")
              ? { ...metricRun, status: "FAILED", error: "Changed target" }
              : { columns: [] },
        ),
      ),
    ),
  );
  const changed = vi.fn();
  const user = userEvent.setup();
  render(
    <MetricEditor card={metric} onChanged={changed} onOpenReceipt={vi.fn()} />,
  );
  await user.click(screen.getByRole("button", { name: "Review change" }));
  await user.click(
    await screen.findByRole("button", { name: "Execute action" }),
  );
  await waitFor(() => {
    expect(screen.getByText("Changed target")).toBeVisible();
  });
  expect(changed).not.toHaveBeenCalled();
});
