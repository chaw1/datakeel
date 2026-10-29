import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { actionPlan, actionRun } from "../../test/actionFixtures";

import { approvalActions } from "./approvalActions";
import { ApprovalSheet } from "./ApprovalSheet";

import type { ActionPlan } from "../../api/types";
import type { Locale } from "../../i18n/context";

const productionActions = [
  "manage_users",
  "manage_skills",
  "define_role",
  "update_role",
  "create_label_set",
  "publish_label_set",
  "register_model",
  "update_model",
  "import_predictions",
  "run_prelabel",
  "finalize_project",
  "create_project",
  "split_packages",
  "assign_tasks",
  "claim_task",
  "release_task",
  "save_revision",
  "submit_task",
  "review_task",
  "reopen_task",
  "upgrade_project",
] as const satisfies readonly ActionPlan["action_type"][];

const rolePlan: ActionPlan = {
  ...actionPlan,
  action_type: "define_role",
  canonical_params: {
    request_id: "role-request",
    role_id: "project-coordinator",
    project_id: "project-reviewed",
    scopes: ["production:assign"],
    allowed_actions: ["assign_tasks"],
    denied_actions: ["finalize_project", "save_revision"],
  },
  manifest: {
    ...actionPlan.manifest,
    objects: [
      {
        asset_ref: {
          asset_type: "role",
          asset_id: "project-coordinator",
          namespace: "default",
        },
        revision: "role-frozen",
        state_revision: 0,
        properties: { name: "Project coordinator" },
        size: 0,
      },
    ],
    total_bytes: 0,
  },
  impact: { object_count: 1, total_bytes: 0, external: false },
  reversible: false,
};

function renderPlan(plan: ActionPlan, locale: Locale) {
  return render(
    <I18nContext.Provider
      value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
    >
      <ApprovalSheet plan={plan} onOpenReceipt={vi.fn()} />
    </I18nContext.Provider>,
  );
}

it.each(["en", "zh"] as const)(
  "labels every registered production action in %s",
  (locale) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const t = translator(locale);
    for (const action of productionActions) {
      const label = approvalActions[action];
      const view = renderPlan({ ...rolePlan, action_type: action }, locale);
      expect(
        screen.getByRole("heading", { level: 3, name: t(label) }),
      ).toBeVisible();
      expect(translator("en")(label)).not.toBe(translator("zh")(label));
      view.unmount();
    }
    expect(fetch).not.toHaveBeenCalled();
  },
);

it.each(["en", "zh"] as const)(
  "shows frozen role grants, denied actions, impact and required approval in %s",
  async (locale) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const t = translator(locale);
    const user = userEvent.setup();
    const frozen = JSON.stringify(rolePlan);
    renderPlan(rolePlan, locale);
    expect(
      screen.getByText(t("approvalImpact")).parentElement,
    ).toHaveTextContent(t("approvalImpactSummary", { count: 1, size: "0 B" }));
    expect(
      screen.getByText(t("approvalRequired")).parentElement,
    ).toHaveTextContent(t("yes"));
    expect(screen.getByText("Project coordinator")).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: t("approvalSignAction", { action: t("productionDefineRole") }),
      }),
    ).toBeEnabled();
    await user.click(screen.getByText(t("planParameters")));
    const parameters = screen.getByText(/"allowed_actions"/);
    expect(parameters).toHaveTextContent('"assign_tasks"');
    expect(parameters).toHaveTextContent('"denied_actions"');
    expect(parameters).toHaveTextContent('"finalize_project"');
    expect(parameters).toHaveTextContent('"save_revision"');
    expect(parameters).toHaveTextContent('"project-reviewed"');
    expect(JSON.stringify(rolePlan)).toBe(frozen);
    expect(fetch).not.toHaveBeenCalled();
  },
);

it.each(["claim_task", "save_revision", "submit_task", "review_task"] as const)(
  "executes frequent %s without requesting approval",
  async (action) => {
    const fetch = vi
      .fn<(url: string) => Promise<Response>>()
      .mockResolvedValue(
        new Response(JSON.stringify({ ...actionRun, action_type: action })),
      );
    vi.stubGlobal("fetch", fetch);
    const plan = { ...rolePlan, action_type: action, reversible: true };
    renderPlan(plan, "en");
    expect(
      screen.getByText("Approval required").parentElement,
    ).toHaveTextContent("No");
    expect(screen.queryByRole("button", { name: "Return" })).toBeNull();
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Execute action" }));
    expect(
      await screen.findByRole("region", { name: "Receipt" }),
    ).toBeVisible();
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      `/api/actions/${plan.id}/execute`,
    ]);
  },
);
