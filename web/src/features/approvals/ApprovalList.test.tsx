import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";

import { ApprovalList } from "./ApprovalList";
it("rejects every selected frozen plan through its own API call", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(actionPlan))),
  );
  const resolved = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(
    <ApprovalList
      plans={[
        actionPlan,
        {
          ...actionPlan,
          id: "plan-2",
          action_type: "export_dataset",
          external: true,
          plan_digest: "second-digest",
        },
      ]}
      onResolved={resolved}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByRole("checkbox", { name: "Select delete_files plan" }),
  );
  await user.click(
    screen.getByRole("checkbox", { name: "Select export_dataset plan" }),
  );
  await user.click(screen.getByRole("button", { name: "Reject selected" }));
  await waitFor(() => {
    expect(resolved).toHaveBeenCalledWith(null);
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch).toHaveBeenNthCalledWith(
    2,
    "/api/approvals/plan-2",
    expect.objectContaining({
      body: JSON.stringify({
        approve: false,
        plan_digest: "second-digest",
        actor: "local",
        reason: "",
      }),
    }),
  );
});

it("keeps failed rejections selected and reports partial batch success", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      path.endsWith("plan-1")
        ? new Response(JSON.stringify({ detail: "Expired" }), { status: 409 })
        : new Response(JSON.stringify(actionPlan)),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const resolved = vi.fn();
  render(
    <ApprovalList
      plans={[
        actionPlan,
        { ...actionPlan, id: "plan-2", action_type: "export_dataset" },
      ]}
      onResolved={resolved}
      onOpenReceipt={vi.fn()}
    />,
  );
  const failed = screen.getByRole("checkbox", {
    name: "Select delete_files plan",
  });
  const successful = screen.getByRole("checkbox", {
    name: "Select export_dataset plan",
  });
  await user.click(failed);
  await user.click(successful);
  await user.click(screen.getByRole("button", { name: "Reject selected" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("409 Expired");
  expect(failed).toBeChecked();
  expect(successful).not.toBeChecked();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(resolved).toHaveBeenCalledWith(null);
});
