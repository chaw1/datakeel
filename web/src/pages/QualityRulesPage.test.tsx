import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { I18nProvider } from "../i18n/I18nProvider";
import { dqRule, mockQualityRulesApi } from "../test/qualityRuleFixtures";

import { QualityRulesPage } from "./QualityRulesPage";

it("shows registered rules, recent results, the numeric trend and merged issues", async () => {
  mockQualityRulesApi();
  const user = userEvent.setup();
  render(<QualityRulesPage />);
  await user.click(await screen.findByRole("button", { name: dqRule.name }));
  expect(
    await screen.findByRole("img", { name: /Result trend/ }),
  ).toBeVisible();
  expect(screen.getByText("Baseline insufficient")).toBeVisible();
  expect(await screen.findByText("Failures · 3")).toBeVisible();
  expect(screen.getByText("Observed one violating row.")).toBeVisible();
  await user.click(screen.getByText("Redacted failure samples"));
  expect(screen.getByText(/\[REDACTED\]/)).toBeVisible();
  await user.type(
    screen.getByRole("searchbox", { name: "Filter rules" }),
    "not a matching rule",
  );
  expect(
    screen.queryByRole("button", { name: dqRule.name }),
  ).not.toBeInTheDocument();
});

it("prepares an edit and executes only after the frozen plan is approved", async () => {
  const fetch = mockQualityRulesApi();
  const user = userEvent.setup();
  render(<QualityRulesPage />);
  await user.click(await screen.findByRole("button", { name: dqRule.name }));
  await user.click(screen.getByRole("button", { name: "Edit rule" }));
  const name = screen.getByRole("textbox", { name: "Rule name" });
  await user.clear(name);
  await user.type(name, "Updated amount rule");
  await user.click(screen.getByRole("button", { name: "Review change" }));
  const sheet = await screen.findByRole("article", {
    name: "Action plan: update_quality_rule",
  });
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  const prepared = fetch.mock.calls.find(([path]) =>
    path.includes("update_quality_rule/prepare"),
  )?.[1]?.body;
  expect(prepared).toContain('"expected_revision":2');
  expect(prepared).toContain("Updated amount rule");
  await user.click(
    within(sheet).getByRole("button", {
      name: "Approve and update quality rule",
    }),
  );
  expect(
    fetch.mock.calls.filter(([path]) => path.includes("/api/approvals/")),
  ).toHaveLength(1);
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/execute")),
  ).toHaveLength(1);
});

it("prepares deletion without deleting before approval, and supports manual run and issue claim plans", async () => {
  const fetch = mockQualityRulesApi();
  const user = userEvent.setup();
  render(<QualityRulesPage />);
  await user.click(await screen.findByRole("button", { name: dqRule.name }));
  await user.click(screen.getByRole("button", { name: "Delete rule" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: delete_quality_rule",
    }),
  ).toBeVisible();
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await user.click(screen.getByRole("button", { name: "Run now" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: run_quality_rule",
    }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await user.click(await screen.findByRole("button", { name: "Claim issue" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: change_quality_issue",
    }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.find(([path]) =>
      path.includes("change_quality_issue/prepare"),
    )?.[1]?.body,
  ).toContain('"expected_revision":3');
});

it("renders all rule controls in Chinese and preserves exact URL scope filters", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  const fetch = mockQualityRulesApi();
  render(
    <I18nProvider>
      <QualityRulesPage
        params={
          new URLSearchParams({
            source_id: "ecommerce",
            table: "orders",
            schema_name: "main",
          })
        }
      />
    </I18nProvider>,
  );
  expect(
    await screen.findByRole("button", { name: dqRule.name }),
  ).toBeVisible();
  expect(screen.getByRole("heading", { name: "质量规则" })).toBeVisible();
  expect(screen.getByRole("button", { name: "新建规则" })).toBeVisible();
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/quality/rules?source_id=ecommerce&table=orders&schema_name=main",
  );
});

it("keeps issues of retired rules visible and prepares their permitted closure", async () => {
  const fetch = mockQualityRulesApi(true);
  const user = userEvent.setup();
  render(<QualityRulesPage />);
  expect(await screen.findByText(dqRule.id)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Confirm resolution" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: change_quality_issue",
    }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.find(([path]) =>
      path.includes("change_quality_issue/prepare"),
    )?.[1]?.body,
  ).toContain('"status":"resolved"');
});
