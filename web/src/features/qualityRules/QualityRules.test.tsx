import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import {
  dqIssue,
  dqRule,
  dqView,
  mockQualityRulesApi,
} from "../../test/qualityRuleFixtures";
import { table } from "../catalog/fixtures";

import { RuleDetails } from "./RuleDetails";
import { RuleEditor } from "./RuleEditor";
import { RuleIssues } from "./RuleIssues";
import { RuleTrend } from "./RuleTrend";
import { TableQualityRules } from "./TableQualityRules";
import { useQualityPolling } from "./useQualityPolling";

it("loads table rules with exact source, schema and table identity", async () => {
  const fetch = mockQualityRulesApi();
  render(<TableQualityRules table={table} />);
  expect(
    await screen.findByRole("link", { name: dqRule.name }),
  ).toHaveAttribute(
    "href",
    "#/quality-rules?source_id=ecommerce&table=orders&schema_name=main&rule=orders-amount",
  );
  expect(screen.getByText("Failed")).toBeVisible();
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/quality/rules?source_id=ecommerce&table=orders&schema_name=main",
  );
});

it("validates the parameter object before preparing and offers all ten rule types", async () => {
  const fetch = mockQualityRulesApi();
  const user = userEvent.setup();
  render(<RuleEditor rule={dqRule} onPrepared={vi.fn()} onCancel={vi.fn()} />);
  expect(
    screen
      .getByRole("combobox", { name: "Rule type" })
      .querySelectorAll("option"),
  ).toHaveLength(10);
  const parameters = screen.getByRole("textbox", { name: "Parameters (JSON)" });
  await user.clear(parameters);
  await user.paste("[]");
  await user.click(screen.getByRole("button", { name: "Review change" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Parameters must be a valid JSON object.",
  );
  expect(fetch).not.toHaveBeenCalled();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Rule type" }),
    "sql_assertion",
  );
  expect((parameters as HTMLTextAreaElement).value).toContain(
    "SELECT * FROM orders",
  );
});

it("keeps no numeric observations distinct from a passing trend", () => {
  render(<RuleTrend results={[]} />);
  expect(
    screen.getByText(
      "A trend appears after numeric observations are available.",
    ),
  ).toBeVisible();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("creates a definition through preparation without executing the plan", async () => {
  const fetch = mockQualityRulesApi();
  const user = userEvent.setup();
  const onPrepared = vi.fn();
  render(<RuleEditor onPrepared={onPrepared} onCancel={vi.fn()} />);
  await user.type(
    screen.getByRole("textbox", { name: "Rule ID" }),
    "orders_unique",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Rule name" }),
    "Order IDs are unique",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Source ID" }),
    "ecommerce",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Table name" }),
    "orders",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Column (optional for table rules)" }),
    "id",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Rule type" }),
    "unique",
  );
  await user.click(screen.getByRole("button", { name: "Review change" }));
  expect(onPrepared).toHaveBeenCalledOnce();
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/actions/create_quality_rule/prepare",
  );
  expect(fetch.mock.calls[0][1]?.body).toContain('"kind":"unique"');
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});

it("offers resolution only after recovery and keeps recovered issues assignable", async () => {
  mockQualityRulesApi();
  const user = userEvent.setup();
  const onPrepared = vi.fn();
  const { rerender } = render(
    <RuleIssues issues={[dqIssue]} onPrepared={onPrepared} />,
  );
  expect(
    screen.queryByRole("button", { name: "Confirm resolution" }),
  ).not.toBeInTheDocument();
  rerender(
    <RuleIssues
      issues={[{ ...dqIssue, status: "recovered", can_resolve: true }]}
      onPrepared={onPrepared}
    />,
  );
  expect(screen.getByRole("button", { name: "Claim issue" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Confirm resolution" }));
  expect(onPrepared).toHaveBeenCalledOnce();
});

it("keeps the default scan budget and prepares an explicit 20000-row budget within the declared upper bound", async () => {
  const fetch = mockQualityRulesApi();
  const user = userEvent.setup();
  const onPrepared = vi.fn();
  render(
    <RuleEditor rule={dqRule} onPrepared={onPrepared} onCancel={vi.fn()} />,
  );
  const limit = screen.getByRole("spinbutton", {
    name: "Batch / assertion result row limit",
  });
  expect(limit).toHaveValue(10000);
  expect(limit).toHaveAttribute("max", "100000");
  await user.clear(limit);
  await user.type(limit, "20000");
  await user.click(screen.getByRole("button", { name: "Review change" }));
  expect(onPrepared).toHaveBeenCalledOnce();
  expect(fetch.mock.calls[0][1]?.body).toContain('"max_rows":20000');
});

it("preserves the persisted claim owner after refresh and ignores assignment drafts when confirming recovery", async () => {
  const fetch = mockQualityRulesApi();
  const user = userEvent.setup();
  const onPrepared = vi.fn();
  const initial = render(
    <RuleIssues issues={[dqIssue]} onPrepared={onPrepared} />,
  );
  const ownerLabel = `Assignee for ${dqRule.id}`;
  await user.clear(screen.getByRole("textbox", { name: ownerLabel }));
  await user.type(
    screen.getByRole("textbox", { name: ownerLabel }),
    "quality-reviewer",
  );
  await user.click(screen.getByRole("button", { name: "Claim issue" }));
  expect(fetch.mock.calls[0][1]?.body).toContain(
    '"assignee":"quality-reviewer"',
  );
  initial.unmount();
  render(
    <RuleIssues
      issues={[
        {
          ...dqIssue,
          status: "recovered",
          assignee: "quality-reviewer",
          can_resolve: true,
          revision: 5,
        },
      ]}
      onPrepared={onPrepared}
    />,
  );
  expect(screen.getByRole("textbox", { name: ownerLabel })).toHaveValue(
    "quality-reviewer",
  );
  await user.clear(screen.getByRole("textbox", { name: ownerLabel }));
  await user.type(
    screen.getByRole("textbox", { name: ownerLabel }),
    "unsubmitted-owner",
  );
  await user.click(screen.getByRole("button", { name: "Confirm resolution" }));
  const body = fetch.mock.calls.at(-1)?.[1]?.body;
  expect(body).toContain('"status":"resolved"');
  expect(body).toContain('"assignee":"quality-reviewer"');
  expect(body).toContain('"expected_revision":5');
});

it("polls on a stable interval and calls the current reload callback after rerenders", () => {
  vi.useFakeTimers();
  try {
    const original = vi.fn();
    const current = vi.fn();
    const hook = renderHook(
      ({ reload }) => {
        useQualityPolling(reload);
      },
      { initialProps: { reload: original } },
    );
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    hook.rerender({ reload: current });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(original).not.toHaveBeenCalled();
    expect(current).toHaveBeenCalledOnce();
    hook.unmount();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(current).toHaveBeenCalledOnce();
  } finally {
    vi.useRealTimers();
  }
});

it("shows complete coverage in the persisted run details", async () => {
  mockQualityRulesApi();
  render(<RuleDetails view={dqView} onPrepared={vi.fn()} />);
  expect(await screen.findAllByText("100% · 100/100 rows")).toHaveLength(2);
  expect(screen.getByRole("columnheader", { name: "Coverage" })).toBeVisible();
});
