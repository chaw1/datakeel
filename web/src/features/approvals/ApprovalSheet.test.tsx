import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { actionPlan, actionRun } from "../../test/actionFixtures";
import { PlanCard } from "../actions/PlanCard";

import { ApprovalSheet } from "./ApprovalSheet";

import type { ActionPlan } from "../../api/types";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const sourcePlan: ActionPlan = {
  ...actionPlan,
  id: "12345678-frozen-plan",
  session_id: "conversation-42",
  plan_digest: "a".repeat(64),
  manifest: {
    ...actionPlan.manifest,
    objects: [
      {
        ...actionPlan.manifest.objects[0],
        asset_ref: {
          ...actionPlan.manifest.objects[0].asset_ref,
          version: "version-7",
        },
        properties: { filename: "text/note-0031.txt", quality: 41 },
      },
    ],
  },
};

it("renders the frozen plan fields, source conversation, object context and irreversible stamp", async () => {
  const user = userEvent.setup();
  render(<ApprovalSheet plan={sourcePlan} onOpenReceipt={vi.fn()} />);
  expect(screen.getByText("12345678")).toHaveAttribute("title", sourcePlan.id);
  expect(screen.getByText("delete_files")).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Conversation conversa" }),
  ).toHaveAttribute("href", "#/agent?conversation=conversation-42");
  expect(screen.getByText("None; data stays in this workspace")).toBeVisible();
  expect(screen.getByText("Irreversible")).toHaveClass("approval-irreversible");
  expect(screen.getByText("This action cannot be undone.")).toBeVisible();
  expect(screen.getByText("Approver").parentElement).toHaveTextContent("local");
  const file = screen.getByRole("link", { name: "text/note-0031.txt" });
  expect(file.getAttribute("href")).toContain("#/object/file/");
  expect(file.getAttribute("href")).toContain("dataset=dataset-1");
  expect(file.getAttribute("href")).toContain("version=version-7");
  expect(file.parentElement).toHaveTextContent("quality 41.0");
  expect(
    screen.getByText(/Approval applies only to this digest/),
  ).toBeVisible();
  await user.click(screen.getByText("Frozen parameters"));
  expect(screen.getByText(/"include_deleted": false/)).toBeVisible();
});

it("copies the exact displayed digest and reports a clipboard failure without executing", async () => {
  const user = userEvent.setup();
  const write = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const { rerender } = render(
    <ApprovalSheet plan={sourcePlan} onOpenReceipt={vi.fn()} />,
  );
  await user.click(screen.getByRole("button", { name: "Copy plan digest" }));
  expect(write).toHaveBeenCalledWith(sourcePlan.plan_digest);
  expect(screen.getByRole("button", { name: "Copied" })).toBeVisible();
  write.mockRejectedValueOnce(new Error("Clipboard unavailable"));
  rerender(
    <ApprovalSheet key="retry" plan={sourcePlan} onOpenReceipt={vi.fn()} />,
  );
  await user.click(screen.getByRole("button", { name: "Copy plan digest" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "The digest could not be copied.",
  );
  expect(fetch).not.toHaveBeenCalled();
});

it("counts down to expiry and disables both controls without a server request", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-23T00:00:00Z"));
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(
    <ApprovalSheet
      plan={{ ...sourcePlan, expires_at: "2026-10-23T00:00:02Z" }}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByText("0m 2s remaining")).toBeVisible();
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(screen.getByText("0m 1s remaining")).toBeVisible();
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(screen.getByText("Expired")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Approve and delete files" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Return" })).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
});

it("shows every frozen object in bounded batches without fetching or altering the plan", async () => {
  const user = userEvent.setup();
  const plan = {
    ...sourcePlan,
    impact: { ...sourcePlan.impact, object_count: 7 },
    manifest: {
      ...sourcePlan.manifest,
      objects: Array.from({ length: 7 }, (_, index) => ({
        ...sourcePlan.manifest.objects[0],
        asset_ref: {
          ...sourcePlan.manifest.objects[0].asset_ref,
          asset_id: `file-${String(index)}`,
        },
        properties: { filename: `note-${String(index)}.txt` },
      })),
    },
  };
  const frozen = JSON.stringify(plan);
  render(<ApprovalSheet plan={plan} onOpenReceipt={vi.fn()} />);
  const list = screen.getByRole("region", { name: "Affected objects · 7" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(5);
  await user.click(
    within(list).getByRole("button", {
      name: "Show next objects (2 remaining)",
    }),
  );
  expect(within(list).getAllByRole("listitem")).toHaveLength(7);
  expect(JSON.stringify(plan)).toBe(frozen);
});

it("requires approval for a reversible external transfer and refreshes the caller with the real receipt", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(path.endsWith("/execute") ? actionRun : sourcePlan),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const resolved = vi.fn();
  render(
    <ApprovalSheet
      plan={{
        ...sourcePlan,
        action_type: "export_dataset",
        external: true,
        reversible: true,
      }}
      onOpenReceipt={vi.fn()}
      onResolved={resolved}
    />,
  );
  expect(screen.getByText(/External transfer ·/)).toBeVisible();
  expect(screen.getByText("Reversible")).not.toHaveClass(
    "approval-irreversible",
  );
  await user.click(
    screen.getByRole("button", { name: "Approve and export dataset" }),
  );
  expect(await screen.findByRole("region", { name: "Receipt" })).toBeVisible();
  expect(fetch.mock.calls.map(([path]) => path)).toEqual([
    `/api/approvals/${sourcePlan.id}`,
    `/api/actions/${sourcePlan.id}/execute`,
  ]);
  expect(resolved).toHaveBeenCalledWith(actionRun);
});

it("resets a prior approval when a replacement plan has a different frozen digest", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(sourcePlan)))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Temporary failure" }), {
        status: 500,
      }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(sourcePlan)))
    .mockResolvedValueOnce(new Response(JSON.stringify(actionRun)));
  vi.stubGlobal("fetch", fetch);
  const { rerender } = render(
    <PlanCard plan={sourcePlan} onOpenReceipt={vi.fn()} />,
  );
  await user.click(
    screen.getByRole("button", { name: "Approve and delete files" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Temporary failure",
  );
  rerender(
    <PlanCard
      plan={{ ...sourcePlan, plan_digest: "replacement-digest" }}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Approve and delete files" }),
  );
  expect(await screen.findByRole("region", { name: "Receipt" })).toBeVisible();
  expect(fetch).toHaveBeenNthCalledWith(
    3,
    `/api/approvals/${sourcePlan.id}`,
    expect.objectContaining({
      body: JSON.stringify({
        approve: true,
        plan_digest: "replacement-digest",
        actor: "local",
        reason: "",
      }),
    }),
  );
});

it("keeps read-only previews inert and renders the required Chinese wording", () => {
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <ApprovalSheet plan={sourcePlan} readOnly onOpenReceipt={vi.fn()} />
    </I18nContext.Provider>,
  );
  expect(
    screen.getByText(
      "签批只对这份摘要有效。参数一改，这张单子作废，需要重新提交。",
    ),
  ).toBeVisible();
  expect(screen.getByText("不可逆")).toHaveClass("approval-irreversible");
  expect(
    screen.queryByRole("button", { name: "签批并删除文件" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "退回" }),
  ).not.toBeInTheDocument();
});
