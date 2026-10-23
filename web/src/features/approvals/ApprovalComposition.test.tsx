import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";

import { ApprovalList } from "./ApprovalList";
import { ApprovalSheet } from "./ApprovalSheet";

it.each([
  ["Return", false, 1],
  ["Approve and delete files", false, 2],
  ["Execute action", true, 1],
] as const)(
  "keeps %s inert throughout composition and cancels native key activation",
  async (name, reversible, calls) => {
    const fetch = vi.fn((path: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(path.endsWith("/execute") ? actionRun : actionPlan),
        ),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(
      <ApprovalSheet
        plan={{ ...actionPlan, reversible }}
        onOpenReceipt={vi.fn()}
      />,
    );
    const button = screen.getByRole("button", { name });
    fireEvent.compositionStart(button);
    await user.click(button);
    expect(fetch).not.toHaveBeenCalled();
    for (const key of ["Enter", " "])
      expect(fireEvent.keyDown(button, { key, isComposing: true })).toBe(false);
    fireEvent.compositionEnd(button);
    expect(fireEvent.keyDown(button, { key: "Enter", isComposing: true })).toBe(
      false,
    );
    expect(fireEvent.keyDown(button, { key: "Enter", keyCode: 229 })).toBe(
      false,
    );
    expect(fetch).not.toHaveBeenCalled();
    await user.click(button);
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(calls);
    });
    expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
      name !== "Return",
    );
  },
);

it("protects batch rejection as well as each individual sheet", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(actionPlan))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const resolved = vi.fn();
  render(
    <ApprovalList
      plans={[actionPlan]}
      onResolved={resolved}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByRole("checkbox", { name: "Select delete_files plan" }),
  );
  const button = screen.getByRole("button", { name: "Reject selected" });
  fireEvent.compositionStart(button);
  await user.click(button);
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.compositionEnd(button);
  expect(fireEvent.keyDown(button, { key: "Enter", isComposing: true })).toBe(
    false,
  );
  await user.click(button);
  await waitFor(() => {
    expect(resolved).toHaveBeenCalledWith(null);
  });
  expect(fetch).toHaveBeenCalledExactlyOnceWith(
    "/api/approvals/plan-1",
    expect.objectContaining({ method: "POST" }),
  );
});
