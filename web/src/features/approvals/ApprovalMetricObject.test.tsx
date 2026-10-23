import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { actionPlan } from "../../test/actionFixtures";
import { metric } from "../catalog/fixtures";

import { ApprovalSheet } from "./ApprovalSheet";

import type { MetricHistory } from "../../api/objects";
import type { ActionPlan } from "../../api/types";
import type { Locale } from "../../i18n/context";

const metricPlan: ActionPlan = {
  ...actionPlan,
  id: "metric-update",
  action_type: "update_metric",
  reversible: true,
  canonical_params: { definition: metric.definition },
  manifest: { ...actionPlan.manifest, objects: [], total_bytes: 0 },
  impact: { object_count: 1, total_bytes: 0, external: false },
  created_at: "2026-10-22T00:01:00Z",
};
const rollbackPlan: ActionPlan = {
  ...metricPlan,
  id: "metric-rollback",
  action_type: "rollback_metric",
  canonical_params: { metric_id: metric.definition.id, version: 1 },
  created_at: "2026-10-22T00:03:00Z",
};
const history: MetricHistory = {
  metric_id: metric.definition.id,
  versions: [1, 2].map((version) => ({
    ...metric,
    definition: { ...metric.definition, version },
  })),
  audit: [
    {
      plan_id: metricPlan.id,
      actor: "local",
      metric_id: metric.definition.id,
      from_version: 1,
      to_version: 2,
      event_id: "update-event",
      action_type: "update_metric",
      created_at: "2026-10-22T00:02:00Z",
    },
  ],
};

function renderPlan(plan: ActionPlan, locale: Locale = "en") {
  return render(
    <I18nContext.Provider
      value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
    >
      <ApprovalSheet plan={plan} onOpenReceipt={vi.fn()} />
    </I18nContext.Provider>,
  );
}

function renderHistory(value: MetricHistory, plan = rollbackPlan) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(value)))),
  );
  renderPlan(plan);
}

it.each([
  ["en", "update_metric", 1],
  ["zh", "update_metric", 1],
  ["en", "rollback_metric", 2],
  ["zh", "rollback_metric", 2],
] as const)(
  "shows one metric and its version transition without bytes for %s %s",
  async (locale, action, version) => {
    const fetch = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(history))),
    );
    vi.stubGlobal("fetch", fetch);
    const plan = action === "update_metric" ? metricPlan : rollbackPlan;
    const frozen = JSON.stringify(plan);
    renderPlan(plan, locale);
    const t = translator(locale);
    expect(
      screen.getByText(t("approvalImpact")).nextElementSibling,
    ).toHaveTextContent(t("approvalMetricImpactSummary", { count: 1 }));
    const list = screen.getByRole("region", {
      name: t("approvalObjects", { count: 1 }),
    });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(
      await within(list).findByText(
        t("approvalMetricVersions", { from: version, to: version + 1 }),
      ),
    ).toBeVisible();
    expect(
      within(list).getByRole("link", {
        name: locale === "zh" ? "零售额" : "Retail revenue",
      }),
    ).toHaveAttribute("href", "#/object/metric/retail_revenue?tab=facts");
    expect(screen.queryByText(/\b0 B\b/)).not.toBeInTheDocument();
    expect(screen.queryByText(t("approvalNoObjects"))).not.toBeInTheDocument();
    expect(JSON.stringify(plan)).toBe(frozen);
    if (action === "rollback_metric")
      expect(fetch).toHaveBeenCalledExactlyOnceWith(
        "/api/catalog/metrics/retail_revenue/history",
        expect.objectContaining({ method: "GET" }),
      );
    else expect(fetch).not.toHaveBeenCalled();
  },
);

it.each(["metric-rollback", "concurrent-plan"])(
  "keeps a rollback's prepared versions when %s has already changed the metric",
  async (planId) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              ...history,
              versions: [
                ...history.versions,
                { ...metric, definition: { ...metric.definition, version: 3 } },
              ],
              audit: [
                ...history.audit,
                {
                  ...history.audit[0],
                  plan_id: planId,
                  from_version: 2,
                  to_version: 3,
                  created_at: "2026-10-22T00:04:00Z",
                },
              ],
            }),
          ),
        ),
      ),
    );
    renderPlan(rollbackPlan);
    expect(await screen.findByText("Version 2 → 3")).toBeVisible();
    expect(screen.queryByText("Version 3 → 4")).not.toBeInTheDocument();
  },
);

it("shows a recoverable history error without inventing a rollback version", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "History unavailable" }), {
        status: 503,
      }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(history)));
  vi.stubGlobal("fetch", fetch);
  renderPlan(rollbackPlan);
  expect(screen.getByText("Loading metric version…")).toBeVisible();
  expect(
    await screen.findByText("The metric version could not be loaded."),
  ).toBeVisible();
  expect(screen.queryByText(/Version \d →/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Version 2 → 3")).toBeVisible();
});

it.each([
  ["2026-10-22T00:03:00.123100Z", "2026-10-22T00:03:00.123900Z", 2],
  ["2026-10-22T00:03:00.123900Z", "2026-10-22T00:03:00.123100Z", 1],
  ["2026-10-22T00:03:00.123100Z", "2026-10-22T08:03:00.123900+08:00", 2],
] as const)(
  "retains microseconds when audit %s precedes or follows plan %s",
  async (changedAt, preparedAt, version) => {
    renderHistory(
      {
        ...history,
        audit: [{ ...history.audit[0], created_at: changedAt }],
      },
      { ...rollbackPlan, created_at: preparedAt },
    );
    expect(
      await screen.findByText(
        `Version ${String(version)} → ${String(version + 1)}`,
      ),
    ).toBeVisible();
  },
);

it.each([1, 2])(
  "does not guess a prepared version when revision %s was imported without an audit",
  async (missingFromVersion) => {
    renderHistory({
      ...history,
      versions: [1, 2, 3].map((version) => ({
        ...metric,
        definition: { ...metric.definition, version },
      })),
      audit: [1, 2]
        .filter((version) => version !== missingFromVersion)
        .map((version) => ({
          ...history.audit[0],
          from_version: version,
          to_version: version + 1,
        })),
    });
    expect(
      await screen.findByText("The metric version could not be loaded."),
    ).toBeVisible();
    expect(screen.queryByText(/Version \d →/)).not.toBeInTheDocument();
  },
);

it("shows the original version when the metric has no changes or audits", async () => {
  renderHistory({ ...history, versions: [metric], audit: [] });
  expect(await screen.findByText("Version 1 → 2")).toBeVisible();
});

it("uses the plan's own executed audit even when earlier versions were imported", async () => {
  renderHistory({
    ...history,
    audit: [
      {
        ...history.audit[0],
        plan_id: rollbackPlan.id,
        from_version: 2,
        to_version: 3,
      },
    ],
  });
  expect(await screen.findByText("Version 2 → 3")).toBeVisible();
});
