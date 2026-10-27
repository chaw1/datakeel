import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { actionPlan, actionRun } from "../../test/actionFixtures";
import { dqRule } from "../../test/qualityRuleFixtures";

import { ApprovalSheet } from "./ApprovalSheet";

import type { ActionPlan } from "../../api/types";
import type { Locale } from "../../i18n/context";

function planFor(action: ActionPlan["action_type"]): ActionPlan {
  const params =
    action === "create_quality_rule"
      ? { rule: { ...dqRule, revision: 1 } }
      : action === "update_quality_rule"
        ? { rule: { ...dqRule, revision: 3 }, expected_revision: 2 }
        : action === "change_quality_issue"
          ? {
              issue_id: "issue-frozen",
              status: "claimed",
              assignee: "quality-reviewer",
              expected_revision: 5,
            }
          : {
              rule_id: dqRule.id,
              ...(action === "delete_quality_rule"
                ? { expected_revision: 2 }
                : {}),
            };
  return {
    ...actionPlan,
    action_type: action,
    canonical_params: params,
    manifest: { ...actionPlan.manifest, objects: [], total_bytes: 0 },
    impact: { object_count: 1, total_bytes: 0, external: false },
    reversible:
      action === "run_quality_rule" || action === "change_quality_issue",
  };
}

function renderPlan(
  plan: ActionPlan,
  locale: Locale = "en",
  onResolved = vi.fn(),
) {
  return render(
    <I18nContext.Provider
      value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
    >
      <ApprovalSheet
        plan={plan}
        onResolved={onResolved}
        onOpenReceipt={vi.fn()}
      />
    </I18nContext.Provider>,
  );
}

it.each(["en", "zh"] as const)(
  "shows one frozen quality target for every action in %s without reading current state",
  (locale) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const t = translator(locale);
    for (const action of [
      "create_quality_rule",
      "update_quality_rule",
      "delete_quality_rule",
      "run_quality_rule",
      "change_quality_issue",
    ] as const) {
      const plan = planFor(action);
      const before = JSON.stringify(plan);
      const view = renderPlan(plan, locale);
      const objects = screen.getByRole("region", {
        name: t("approvalObjects", { count: 1 }),
      });
      expect(within(objects).getAllByRole("listitem")).toHaveLength(1);
      expect(
        within(objects).getByText(
          action === "change_quality_issue" ? "issue-frozen" : dqRule.id,
        ),
      ).toBeVisible();
      expect(
        screen.queryByText(t("approvalNoObjects")),
      ).not.toBeInTheDocument();
      if (
        action === "create_quality_rule" ||
        action === "update_quality_rule"
      ) {
        expect(within(objects).getByText(dqRule.name)).toBeVisible();
        expect(
          within(objects).getByText("ecommerce / main / orders / paid_amount"),
        ).toBeVisible();
        expect(
          within(objects).getByText(
            action === "create_quality_rule"
              ? t("dqRevision", { revision: 1 })
              : t("dqApprovalRevisionChange", { from: 2, to: 3 }),
          ),
        ).toBeVisible();
      }
      if (action === "delete_quality_rule")
        expect(
          within(objects).getByText(
            t("dqApprovalReviewedRevision", { revision: 2 }),
          ),
        ).toBeVisible();
      if (action === "change_quality_issue") {
        expect(within(objects).getByText(t("dqClaimed"))).toBeVisible();
        expect(within(objects).getByText("quality-reviewer")).toBeVisible();
      }
      expect(JSON.stringify(plan)).toBe(before);
      view.unmount();
    }
    expect(fetch).not.toHaveBeenCalled();
  },
);

it("keeps approval and execution bound to the displayed frozen quality plan", async () => {
  const plan = planFor("create_quality_rule");
  const fetch = vi.fn((url: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          url.includes("/api/approvals/")
            ? { ...plan, status: "APPROVED" }
            : { ...actionRun, action_type: plan.action_type },
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const onResolved = vi.fn();
  renderPlan(plan, "en", onResolved);
  expect(fetch).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", {
      name: "Approve and create quality rule",
    }),
  );
  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    `/api/approvals/${plan.id}`,
    `/api/actions/${plan.id}/execute`,
  ]);
  expect(onResolved).toHaveBeenCalledOnce();
  const objects = screen.getByRole("region", { name: "Affected objects · 1" });
  expect(within(objects).getByText(dqRule.name)).toBeVisible();
});
