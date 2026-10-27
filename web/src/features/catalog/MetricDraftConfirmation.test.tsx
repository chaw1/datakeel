import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";

import { metric, table } from "./fixtures";
import { MetricDraftConfirmation } from "./MetricDraftConfirmation";

it("prepares a draft then requires explicit approval before installing semantics", async () => {
  const plan = {
    ...actionPlan,
    action_type: "confirm_metric_draft" as const,
    reversible: true,
    external: false,
    canonical_params: {
      draft_id: "draft/orders",
      definition: metric.definition,
    },
  };
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/execute")
            ? { ...actionRun, action_type: "confirm_metric_draft" }
            : plan,
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const changed = vi.fn();
  const user = userEvent.setup();
  render(
    <MetricDraftConfirmation
      item={{
        ...table,
        asset_ref: {
          ...table.asset_ref,
          asset_type: "metric_draft",
          asset_id: "draft/orders",
        },
        properties: { status: "draft", definition: { ...metric.definition } },
      }}
      onChanged={changed}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Review metric confirmation" }),
  );
  const sign = await screen.findByRole("button", {
    name: "Approve and confirm metric draft",
  });
  expect(fetch.mock.calls.map(([path]) => path)).toEqual([
    "/api/actions/confirm_metric_draft/prepare",
  ]);
  expect(changed).not.toHaveBeenCalled();
  await user.click(sign);
  expect(
    await screen.findByText("This metric draft has been confirmed."),
  ).toBeVisible();
  expect(fetch.mock.calls.map(([path]) => path)).toEqual([
    "/api/actions/confirm_metric_draft/prepare",
    "/api/approvals/plan-1",
    "/api/actions/plan-1/execute",
  ]);
  expect(changed).toHaveBeenCalledOnce();
});

it("blocks deleted drafts and retains their raw source details", () => {
  render(
    <MetricDraftConfirmation
      item={{
        ...table,
        properties: { source_deleted: true, raw: { name: "orders" } },
      }}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByText("Deleted at source")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Review metric confirmation" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/"orders"/)).toBeInTheDocument();
});
