import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { actionPlan } from "../../test/actionFixtures";
import { metric } from "../catalog/fixtures";

import { ApprovalSheet } from "./ApprovalSheet";

import type { ActionPlan } from "../../api/types";

it.each(["en", "zh"] as const)(
  "shows the frozen metric draft and complete key semantics in %s",
  (locale) => {
    const plan: ActionPlan = {
      ...actionPlan,
      action_type: "confirm_metric_draft",
      reversible: true,
      external: false,
      manifest: { ...actionPlan.manifest, objects: [] },
      impact: { object_count: 1, total_bytes: 0, external: false },
      canonical_params: {
        draft_id: "shop/dbt-draft/metric.shop.revenue",
        definition: metric.definition,
      },
    };
    const frozen = JSON.stringify(plan);
    const t = translator(locale);
    render(
      <I18nContext.Provider value={{ locale, setLocale: vi.fn(), t }}>
        <ApprovalSheet plan={plan} onOpenReceipt={vi.fn()} />
      </I18nContext.Provider>,
    );
    const targets = screen.getByRole("region", {
      name: t("approvalObjects", { count: 1 }),
    });
    expect(
      within(targets).getByText("shop/dbt-draft/metric.shop.revenue"),
    ).toBeVisible();
    expect(
      within(targets).getByText(
        `${metric.definition.name} · ${metric.definition.id}`,
      ),
    ).toBeVisible();
    expect(
      within(targets).getByText(String(metric.definition.version)),
    ).toBeVisible();
    expect(within(targets).getByText(metric.definition.owner)).toBeVisible();
    expect(
      within(targets).getByText(metric.definition.description),
    ).toBeVisible();
    expect(
      within(targets).getByText(metric.definition.measure.table),
    ).toBeVisible();
    expect(
      within(targets).getByText(`sum(${metric.definition.measure.column})`),
    ).toBeVisible();
    expect(
      within(targets).getByText(`${metric.definition.time.column} · day`),
    ).toBeVisible();
    expect(
      within(targets).getByText(JSON.stringify(metric.definition.filters)),
    ).toBeVisible();
    expect(
      within(targets).getByText(JSON.stringify(metric.definition.dimensions)),
    ).toBeVisible();
    expect(
      within(targets).getByText(JSON.stringify(metric.definition.caveats)),
    ).toBeVisible();
    expect(screen.queryByText(t("approvalNoObjects"))).not.toBeInTheDocument();
    expect(screen.queryByText(/\b0 B\b/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: t("approvalSignAction", { action: t("metadataConfirmAction") }),
      }),
    ).toBeVisible();
    expect(JSON.stringify(plan)).toBe(frozen);
  },
);
