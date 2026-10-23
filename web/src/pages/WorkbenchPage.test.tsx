import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { I18nContext, translator } from "../i18n/context";
import { dashboard } from "../test/dashboardFixtures";

import { WorkbenchPage } from "./WorkbenchPage";

it("counts only datasets strictly below 60 and links to prefiltered queues", () => {
  render(<WorkbenchPage data={dashboard} />);
  expect(
    screen.getByRole("heading", { name: "Quality alerts · 1 dataset" }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Pending approval · 1" }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Running pipelines · 1" }),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "View running pipelines" }),
  ).toHaveAttribute("href", "#/runs?type=pipeline&state=active");
  expect(
    screen.getByRole("link", { name: "Review quality alerts" }),
  ).toHaveAttribute("href", "#/quality?filter=alerts");
  expect(screen.queryByText("Boundary dataset")).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Workbench · 3 need attention" }),
  ).toBeVisible();
});

it("counts approvals, active pipelines and quality alert datasets in Chinese", () => {
  const task = dashboard.tasks[0];
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: () => undefined, t: translator("zh") }}
    >
      <WorkbenchPage
        data={{
          ...dashboard,
          tasks: [
            task,
            { ...task, id: "pending", state: "PENDING" },
            { ...task, id: "queued", state: "QUEUED" },
            { ...task, id: "complete", state: "COMPLETED" },
            { ...task, id: "failed", state: "FAILED" },
          ],
        }}
      />
    </I18nContext.Provider>,
  );
  expect(
    screen.getByRole("heading", { name: "工作台 · 5 项待处理" }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "运行中流水线 · 3 个" }),
  ).toBeVisible();
});

it("keeps the attention title meaningful when no queues need work", () => {
  render(
    <WorkbenchPage
      data={{
        approvals: [],
        tasks: [],
        datasets: [],
        actions: dashboard.actions,
      }}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Workbench · 0 need attention" }),
  ).toBeVisible();
});

it.each(["en", "zh"] as const)(
  "labels recent actions without promising five runs in %s",
  (locale) => {
    const { rerender } = render(<WorkbenchPage data={dashboard} />);
    for (const count of [0, 1, 4, 5]) {
      rerender(
        <I18nContext.Provider
          value={{ locale, setLocale: () => undefined, t: translator(locale) }}
        >
          <WorkbenchPage
            data={{
              ...dashboard,
              actions: Array.from({ length: count }, (_, index) => ({
                ...dashboard.actions[0],
                id: `recent-${String(index)}`,
              })),
            }}
          />
        </I18nContext.Provider>,
      );
      expect(
        screen.getByRole("heading", {
          name: locale === "en" ? "Recent action runs" : "最近动作运行",
        }),
      ).toBeVisible();
      expect(screen.queryByText(/Latest 5|最近 5/)).not.toBeInTheDocument();
    }
  },
);
